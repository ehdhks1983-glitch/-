"""파이프라인 오케스트레이터 (기획안 §3.1, §5.6 + 작업지시서 v0.3).

검토 모드: 대본 생성 → (사용자 확정 후) run_job(script=...)로 재개.
자동 모드: 주제 입력 → 대본·TTS·배경·스펙·렌더까지 무개입 진행.
    실패 정책: 대본 JSON 파싱 실패 1회 재생성 / TTS는 레이트리미터+retryDelay 재시도
    +제공자 폴백 체인(작업 단위) / 렌더 실패 리포트.
모든 산출물은 작업 폴더에 보존, TTS 클립은 workdir/cache/tts에 영구 캐시.
"""

from __future__ import annotations

import datetime as _dt
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .. import config, presets
from ..spec import Background, Bgm, MainVideo, Style
from . import background_generator, render_engine, timeline_calculator, tts_engine
from .render_engine import RenderResult
from .render_engine.ffmpeg_composer import RenderOptions
from .script_generator import Script, ScriptParseError

log = logging.getLogger("cutdaejang")

DEFAULT_BGM_DIR = Path(__file__).resolve().parents[2] / "resources" / "bgm"
_BGM_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


@dataclass
class JobOptions:
    outputs: tuple = ("mp4",)            # mp4 전용 (캡컷 draft 출력은 v0.41에서 제거)
    auto_mode: bool = False
    tts_chain: List[str] = field(default_factory=lambda: ["stub"])
    voice: str = ""
    tts_style: str = ""                  # 비면 settings.tts.style_preset
    tone: str = "정보형"
    target_sec: int = 60
    bgm: str = ""                        # ""(없음) | "random" | 파일명/경로
    hook: str = ""                       # 상단 제목(훅). 비면 대본 제목 사용
    user_background: Optional[str] = None
    main_video_path: Optional[str] = None
    render: RenderOptions = field(default_factory=RenderOptions)


@dataclass
class JobResult:
    job_id: str
    job_dir: str
    status: str = "pending"              # ok | partial | failed | awaiting_review
    title: str = ""
    script_path: str = ""
    spec_path: str = ""
    mp4: Optional[RenderResult] = None
    tts_provider: str = ""               # 실제 사용된 제공자 (폴백 추적)
    bg_source: str = ""                  # 배경 출처: user/ai/ai_fail:사유/local (v0.40)
    fallback_note: Optional[str] = None
    errors: List[str] = field(default_factory=list)


def new_job_id(title_hint: str = "") -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title_hint)[:24].strip("-")
    return f"{stamp}-{slug}" if slug else stamp


def safe_filename(title: str, fallback: str = "output") -> str:
    """제목 → 파일명 (Windows 금지 문자 제거, 길이 제한)."""
    name = re.sub(r'[\\/:*?"<>|\r\n]+', " ", title).strip().rstrip(".")
    name = re.sub(r"\s+", " ", name)[:60].strip()
    return name or fallback


def generate_script(script_provider, topic: str, opts: JobOptions) -> Script:
    """대본 생성 — JSON 파싱 실패 시 1회 재생성 (§5.6)."""
    try:
        return script_provider.generate(topic, tone=opts.tone, target_sec=opts.target_sec)
    except ScriptParseError as e:
        log.warning("대본 파싱 실패 → 1회 재생성: %s", e)
        return script_provider.generate(topic, tone=opts.tone, target_sec=opts.target_sec)


def build_style(settings: dict) -> Style:
    """settings.subtitle → 공통 Style (A/B 출력 동일 기준)."""
    sub = settings["subtitle"]
    return Style(
        font="Pretendard-ExtraBold",
        size=sub["font_size"],
        outline=sub["outline"],
        shadow=sub.get("shadow", 1),
        position="bottom",
        gradient_overlay=True,
        margin_v=sub.get("margin_v"),
        fade=sub.get("fade", True),
        highlight_color=sub.get("highlight_color", "#FFD400"),
        band=sub.get("band", False),
        hook_band=sub.get("hook_band", True),
        wrap_chars=sub.get("wrap_chars", 16),
        anim=sub.get("anim", "none"),
    )


def resolve_bgm(choice: str, settings: dict, bgm_dir: Optional[Path] = None) -> Optional[Bgm]:
    """""(없음) / "random" / 파일명·경로 → Bgm 스펙. 파일이 없으면 None (작업은 계속)."""
    if not choice:
        return None
    bgm_dir = bgm_dir or DEFAULT_BGM_DIR
    path: Optional[Path] = None
    if choice == "random":
        files = sorted(
            p for p in bgm_dir.glob("*") if p.suffix.lower() in _BGM_EXTS and p.is_file()
        )
        path = random.choice(files) if files else None
    else:
        cand = Path(choice)
        path = cand if cand.is_file() else (bgm_dir / choice if (bgm_dir / choice).is_file() else None)
    if path is None:
        log.warning("BGM 파일을 찾지 못해 BGM 없이 진행: %r", choice)
        return None
    cfg = settings["bgm"]
    return Bgm(path=str(path), volume_db=cfg.get("volume_db", -20), duck=cfg.get("duck", False))


def run_job(
    workdir_root,
    script: Script,
    opts: Optional[JobOptions] = None,
    settings: Optional[dict] = None,
    image_provider: Optional[background_generator.GeminiImage] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
    job_id: Optional[str] = None,
    scene_images: Optional[list] = None,
) -> JobResult:
    """확정된 대본으로 ③TTS→④타임라인→⑤배경→⑥출력(A/B)을 수행한다.

    scene_images: 장면 검토 화면(v0.50)에서 미리 만들어 확정한 이미지 경로 목록.
    주어지면 장면 생성 없이 그대로 슬라이드 배경으로 쓴다 (None 항목은 이웃 채움).
    """
    opts = opts or JobOptions()
    settings = settings or config.load_settings()
    if opts.tts_style:
        settings = config.deep_merge(settings, {"tts": {"style_preset": opts.tts_style}})

    job_id = job_id or new_job_id(script.title)
    job_dir = Path(workdir_root) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result = JobResult(job_id=job_id, job_dir=str(job_dir), title=script.title)

    def report(stage: str, frac: float) -> None:
        if progress_cb:
            progress_cb(stage, frac)

    def note(msg: str) -> None:
        log.info("%s", msg)
        if status_cb:
            status_cb(msg)

    script_path = job_dir / "script.json"
    script_path.write_text(script.to_json(), encoding="utf-8")
    result.script_path = str(script_path)

    try:
        # ③ 문장별 TTS — 영구 캐시 + 레이트리미터 + 폴백 체인 (지시서 PATCH 1)
        report("tts", 0.0)
        audio_paths, used_provider, fallback_note = tts_engine.synth_with_fallback(
            script.sentences,
            chain=list(opts.tts_chain),
            cache_root=Path(workdir_root) / "cache" / "tts",
            settings=settings,
            voice=opts.voice,
            status_cb=note,
            on_progress=lambda i, n: report("tts", i / n),
        )
        result.tts_provider = used_provider
        result.fallback_note = fallback_note

        # ⑤ 배경
        report("background", 0.0)
        bg_path = str(job_dir / "background.png")
        canvas = presets.CANVAS_SHORTS
        _, result.bg_source = background_generator.prepare_background(
            bg_path,
            canvas,
            user_image=opts.user_background,
            prompt=script.background_prompt or script.title,
            provider=image_provider,
            on_note=note,
        )
        bg_cfg = settings["bg"]
        background = Background(
            type="image", path=bg_path,
            motion=bg_cfg.get("motion", "zoom_in"),
            motion_amount=bg_cfg.get("motion_amount", 0.08),
        )

        # ④ 타임라인 실측 → Timeline Spec 확정
        report("timeline", 0.0)
        spec = timeline_calculator.build_spec(
            sentences=script.sentences,
            audio_paths=[str(p) for p in audio_paths],
            background=background,
            style=build_style(settings),
            canvas=canvas,
            main_video=(
                MainVideo(path=opts.main_video_path) if opts.main_video_path else None
            ),
            bgm=resolve_bgm(opts.bgm, settings),
            highlights=script.highlights,
            hook=opts.hook or script.title,  # 훅 미지정 시 대본 제목을 상단 제목으로
            opts=timeline_calculator.TimelineOptions(
                gap_us=settings["audio"]["gap_ms"] * 1000
            ),
        )
        # v0.45: 장면별 AI 이미지 배경 — 문장 타이밍(오디오 클립)에 맞춰 이미지가 넘어감.
        # 키 없음/설정 꺼짐/사용자 배경/문장 1개면 기존 단일 배경 유지. 실패는 이웃으로 채움.
        # v0.50: scene_images가 오면(장면 검토에서 확정) 생성 없이 그대로 사용.
        # v0.51: scene_mode(auto/manual/off) + max_scene_images 장수 제한 — manual은
        # 검토에서 확정한 이미지(scene_images)로만 동작 (자동 생성 안 함 = 비용 0).
        scene_mode = bg_cfg.get("scene_mode", "auto")
        use_scene_mode = (bg_cfg.get("scene_images", True) and scene_mode != "off"
                          and not opts.user_background
                          and len(spec.audio) > 1
                          and (scene_images
                               or (image_provider is not None and scene_mode == "auto")))
        if use_scene_mode:
            style = bg_cfg.get("image_style", "일러스트")
            prompts = [sp or s for sp, s in zip(script.scene_prompts, script.sentences)]
            planned = len(prompts)
            if scene_images:
                imgs = list(scene_images)[: len(prompts)]
                imgs += [None] * (len(prompts) - len(imgs))
            else:
                character = bg_cfg.get("character", "")
                sel = background_generator.select_scene_indices(
                    len(prompts), int(bg_cfg.get("max_scene_images", 0) or 0))
                planned = len(sel)
                note(f"장면별 AI 이미지 {planned}장 생성 중… (그림체: {style})")
                imgs = background_generator.generate_scene_images(
                    prompts, image_provider, job_dir / "scenes", canvas, style=style,
                    character=character,
                    on_note=note,
                    on_progress=lambda i, n: report("background", i / max(n, 1)),
                    only_indices=sel if planned < len(prompts) else None,
                )
            ok_n = sum(1 for p in imgs if p)
            # 충분히 성공했을 때만 슬라이드 배경 (장수 제한 시엔 계획 장수 기준).
            # 검토에서 확정한 이미지는 1장이라도 사용자의 선택이므로 그대로 쓴다.
            min_ok = 1 if scene_images else min(planned, max(2, planned // 3))
            if ok_n >= min_ok and ok_n > 0:
                filled = background_generator.fill_scene_gaps(imgs, base=bg_path)
                starts = [a.start_us for a in spec.audio]
                spans = []
                for i, img in enumerate(filled):
                    s0 = 0 if i == 0 else starts[i]
                    s1 = starts[i + 1] if i + 1 < len(starts) else spec.duration_us
                    spans.append((img, s1 - s0))
                spans = background_generator.merge_scene_spans(spans)
                slides = background_generator.scene_slideshow(
                    spans, str(job_dir / "bg_slides.mp4"), canvas,
                    motion=bg_cfg.get("motion", "zoom_in"),
                    motion_amount=bg_cfg.get("motion_amount", 0.08),
                )
                spec.background = Background(type="video", path=slides)
                result.bg_source = f"ai_scenes:{ok_n}/{planned}"
                note(f"장면 이미지 {ok_n}/{planned}장으로 배경 완성")
            else:
                note("장면 이미지가 대부분 실패해 단일 배경으로 진행합니다")

        spec_path = job_dir / "spec.json"
        spec.save(spec_path)
        result.spec_path = str(spec_path)

        # ⑥ 출력 (A/B 독립 — 한쪽 실패가 다른 쪽을 막지 않음)
        if "mp4" in opts.outputs:
            report("render", 0.0)
            try:
                result.mp4 = render_engine.render(
                    spec,
                    job_dir / "render",
                    out_path=str(job_dir / f"{safe_filename(script.title)}.mp4"),
                    opts=opts.render,
                    progress_cb=lambda f: report("render", f),
                )
                if not result.mp4.ok:
                    result.errors += [f"렌더 자가검증 실패: {e}" for e in result.mp4.errors]
            except Exception as e:  # noqa: BLE001 — A/B 독립: mp4 실패가 draft를 막지 않게
                result.errors.append(f"mp4 렌더 실패: {e}")


        mp4_ok = ("mp4" not in opts.outputs) or (result.mp4 is not None and result.mp4.ok)
        result.status = "ok" if (mp4_ok and not result.errors) else "partial"
    except Exception as e:
        log.exception("작업 실패: %s", job_id)
        result.errors.append(str(e))
        raw = getattr(e, "raw", "")
        if raw:
            result.errors.append(f"[원본 오류] {raw[:1500]}")
        result.status = "failed"
    return result


def run_topic(
    workdir_root,
    topic: str,
    script_provider,
    opts: Optional[JobOptions] = None,
    settings: Optional[dict] = None,
    image_provider: Optional[background_generator.GeminiImage] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> JobResult:
    """주제 → 완성까지. 자동 모드가 아니면 대본 생성 후 검토 대기 상태로 반환 (§1.3)."""
    opts = opts or JobOptions()
    try:
        script = generate_script(script_provider, topic, opts)
    except Exception as e:  # noqa: BLE001 — CLI에서도 스택트레이스 대신 실패 결과로
        r = JobResult(job_id=new_job_id(topic or "topic"), status="failed")
        r.errors.append(f"대본 생성 실패: {e}")
        return r

    if not opts.auto_mode:
        job_id = new_job_id(script.title)
        job_dir = Path(workdir_root) / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        script_path = job_dir / "script.json"
        script_path.write_text(script.to_json(), encoding="utf-8")
        return JobResult(
            job_id=job_id,
            job_dir=str(job_dir),
            status="awaiting_review",
            title=script.title,
            script_path=str(script_path),
        )

    return run_job(
        workdir_root, script, opts=opts, settings=settings,
        image_provider=image_provider, progress_cb=progress_cb, status_cb=status_cb,
    )
