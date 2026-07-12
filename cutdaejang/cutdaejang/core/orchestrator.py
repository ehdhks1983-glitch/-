"""파이프라인 오케스트레이터 (기획안 §3.1, §5.6).

검토 모드: 대본 생성 → (사용자 확정 후) run_job(script=...)로 재개.
자동 모드: 주제 입력 → 대본·TTS·배경·스펙·렌더까지 무개입 진행.
    실패 정책: 대본 JSON 파싱 실패 1회 재생성 / TTS 문장 재시도 2회 / 렌더 실패 리포트.
모든 산출물(대본·오디오·배경·스펙·결과)은 작업 폴더에 보존 → 히스토리에서 열람·재생성.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from ..spec import Background, Canvas, MainVideo, Style, TimelineSpec
from .. import presets
from . import background_generator, render_engine, timeline_calculator
from .render_engine import RenderResult
from .render_engine.ffmpeg_composer import RenderOptions
from .script_generator import Script, ScriptParseError
from .tts_engine import TTSEngine

log = logging.getLogger("cutdaejang")


@dataclass
class JobOptions:
    outputs: tuple = ("mp4",)            # "mp4"(출력 B) / "draft"(출력 A)
    auto_mode: bool = False
    voice: str = ""
    tone: str = "정보형"
    target_sec: int = 60
    style_preset: str = "shorts_basic"
    user_background: Optional[str] = None
    main_video_path: Optional[str] = None
    drafts_dir: Optional[str] = None     # 출력 A 사용 시 CapCut Drafts 폴더
    render: RenderOptions = field(default_factory=RenderOptions)
    timeline: timeline_calculator.TimelineOptions = field(
        default_factory=timeline_calculator.TimelineOptions
    )


@dataclass
class JobResult:
    job_id: str
    job_dir: str
    status: str = "pending"              # ok | partial | failed | awaiting_review
    title: str = ""
    script_path: str = ""
    spec_path: str = ""
    mp4: Optional[RenderResult] = None
    draft_path: str = ""
    errors: List[str] = field(default_factory=list)


def new_job_id(title_hint: str = "") -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title_hint)[:24].strip("-")
    return f"{stamp}-{slug}" if slug else stamp


def generate_script(script_provider, topic: str, opts: JobOptions) -> Script:
    """대본 생성 — JSON 파싱 실패 시 1회 재생성 (§5.6)."""
    try:
        return script_provider.generate(topic, tone=opts.tone, target_sec=opts.target_sec)
    except ScriptParseError as e:
        log.warning("대본 파싱 실패 → 1회 재생성: %s", e)
        return script_provider.generate(topic, tone=opts.tone, target_sec=opts.target_sec)


def run_job(
    workdir_root,
    script: Script,
    tts: TTSEngine,
    opts: Optional[JobOptions] = None,
    image_provider: Optional[background_generator.GeminiImage] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    job_id: Optional[str] = None,
) -> JobResult:
    """확정된 대본으로 ③TTS→④타임라인→⑤배경→⑥출력(A/B)을 수행한다."""
    opts = opts or JobOptions()
    job_id = job_id or new_job_id(script.title)
    job_dir = Path(workdir_root) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result = JobResult(job_id=job_id, job_dir=str(job_dir), title=script.title)

    def report(stage: str, frac: float) -> None:
        if progress_cb:
            progress_cb(stage, frac)

    # 대본 보존 (자동 모드 사후 검수용, §1.3)
    script_path = job_dir / "script.json"
    script_path.write_text(script.to_json(), encoding="utf-8")
    result.script_path = str(script_path)

    try:
        # ③ 문장별 TTS
        report("tts", 0.0)
        audio_paths = tts.synth_all(
            script.sentences,
            voice=opts.voice,
            on_progress=lambda i, n: report("tts", i / n),
        )

        # ⑤ 배경
        report("background", 0.0)
        bg_path = str(job_dir / "background.png")
        canvas = presets.CANVAS_SHORTS
        background_generator.prepare_background(
            bg_path,
            canvas,
            user_image=opts.user_background,
            prompt=script.background_prompt or script.title,
            provider=image_provider,
        )

        # ④ 타임라인 실측 → Timeline Spec 확정
        report("timeline", 0.0)
        style = presets.SUBTITLE_STYLE_PRESETS[opts.style_preset]
        main_video = (
            MainVideo(path=opts.main_video_path) if opts.main_video_path else None
        )
        spec = timeline_calculator.build_spec(
            sentences=script.sentences,
            audio_paths=[str(p) for p in audio_paths],
            background=Background(type="image", path=bg_path),
            style=style,
            canvas=canvas,
            main_video=main_video,
            opts=opts.timeline,
        )
        spec_path = job_dir / "spec.json"
        spec.save(spec_path)
        result.spec_path = str(spec_path)

        # ⑥ 출력 (A/B 독립 — 한쪽 실패가 다른 쪽을 막지 않음)
        if "mp4" in opts.outputs:
            report("render", 0.0)
            result.mp4 = render_engine.render(
                spec,
                job_dir / "render",
                out_path=str(job_dir / "output.mp4"),
                opts=opts.render,
                progress_cb=lambda f: report("render", f),
            )
            if not result.mp4.ok:
                result.errors += [f"렌더 자가검증 실패: {e}" for e in result.mp4.errors]

        if "draft" in opts.outputs:
            report("draft", 0.0)
            try:
                from .draft_builder import build_draft  # noqa: PLC0415

                if not opts.drafts_dir:
                    raise ValueError("outputs에 draft가 있지만 drafts_dir가 설정되지 않았습니다")
                draft = build_draft(spec, opts.drafts_dir, f"cutdaejang_{job_id}")
                result.draft_path = draft.draft_path
                if not draft.ok:
                    result.errors += [f"draft 자가검증: {p}" for p in draft.problems]
            except Exception as e:  # draft 실패는 mp4 산출을 무효화하지 않는다
                result.errors.append(f"draft 생성 실패: {e}")

        mp4_ok = ("mp4" not in opts.outputs) or (result.mp4 is not None and result.mp4.ok)
        draft_ok = ("draft" not in opts.outputs) or bool(result.draft_path)
        result.status = "ok" if (mp4_ok and draft_ok and not result.errors) else (
            "partial" if (mp4_ok or draft_ok) else "failed"
        )
    except Exception as e:
        log.exception("작업 실패: %s", job_id)
        result.errors.append(str(e))
        result.status = "failed"
    return result


def run_topic(
    workdir_root,
    topic: str,
    script_provider,
    tts: TTSEngine,
    opts: Optional[JobOptions] = None,
    image_provider: Optional[background_generator.GeminiImage] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
) -> JobResult:
    """주제 → 완성까지. 자동 모드가 아니면 대본 생성 후 검토 대기 상태로 반환 (§1.3)."""
    opts = opts or JobOptions()
    script = generate_script(script_provider, topic, opts)

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
        workdir_root, script, tts, opts=opts,
        image_provider=image_provider, progress_cb=progress_cb,
    )
