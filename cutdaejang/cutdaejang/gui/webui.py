"""컷대장 로컬 웹 UI — 브라우저에서 클릭으로 생성·검토·재생까지.

`python -m cutdaejang ui` 한 줄이면 127.0.0.1 로컬 서버가 뜨고 기본 브라우저가 열린다.
표준 라이브러리(http.server)만 사용 — 추가 설치 없음. 기획안 §6의 GUI(탭① 새 작업,
탭② 대본 검토, 탭③ 히스토리)를 웹 화면 하나로 구현한 확인용 프런트엔드다.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections import deque
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .. import config
from ..core import background_generator, orchestrator, tts_engine
from ..core.orchestrator import JobOptions
from ..core.render_engine.ffmpeg_composer import RenderOptions
from ..core.script_generator import SCRIPT_PROVIDERS, Script
from ..core.tts_engine import GEMINI_VOICES, STYLE_INSTRUCTIONS

_JOBS: dict = {}
_LOCK = threading.Lock()


def _set_job(job_id: str, **fields) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {"id": job_id}).update(fields)


def _get_job(job_id: str) -> Optional[dict]:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _dt_stamp() -> str:
    import datetime  # noqa: PLC0415

    return datetime.datetime.now().strftime("%H%M%S")


# 네이티브 파일 선택 창 — 서버(사용자 PC)에서 tkinter 대화상자를 별도 프로세스로 띄워
# 전체 경로를 돌려받는다. 서버 스레드와 GUI 스레드 충돌을 피하려 subprocess로 분리.
_PICK_FILE_CODE = r"""
import tkinter as tk
from tkinter import filedialog
r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
p = filedialog.askopenfilename(
    title="편집할 영상 선택",
    filetypes=[("영상 파일", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.wmv *.flv"),
               ("모든 파일", "*.*")],
)
r.destroy()
import sys
sys.stdout.write(p or "")
"""


def pick_video_file(timeout: float = 600.0) -> Optional[str]:
    """네이티브 파일 선택 창을 띄우고 선택된 경로 반환. 취소=None, 사용불가=예외."""
    import subprocess  # noqa: PLC0415

    proc = subprocess.run(
        [sys.executable, "-c", _PICK_FILE_CODE],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "파일 선택 창을 열 수 없습니다. 경로를 직접 붙여넣어 주세요. "
            f"({proc.stderr.strip()[-200:]})"
        )
    path = proc.stdout.strip()
    return path or None


def _stt_available() -> dict:
    """편집 모드에서 쓸 수 있는 음성인식 제공자."""
    try:
        import faster_whisper  # noqa: F401, PLC0415

        whisper = True
    except ImportError:
        whisper = False
    return {
        "whisper": whisper,
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
    }


def _env_check() -> dict:
    """UI 첫 화면에서 환경 문제를 미리 알려주기 위한 점검 (실패해도 화면은 뜨게)."""
    from ..core import render_engine  # noqa: PLC0415
    from ..utils import ffmpeg as ff  # noqa: PLC0415

    try:
        ff.ffmpeg_bin()
        ff.ffprobe_bin()
        ffmpeg_ok = True
    except ff.FFmpegError:
        ffmpeg_ok = False
    font_ok = (Path(render_engine.DEFAULT_FONTS_DIR) / "Pretendard-ExtraBold.ttf").exists()
    return {"ffmpeg": ffmpeg_ok, "font": font_ok}


def default_drafts_dir() -> str:
    """Windows 표준 CapCut Drafts 경로 자동 감지 (없으면 빈 문자열)."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        if p.is_dir():
            return str(p)
    return ""


def _apply_keys(params: dict) -> None:
    """UI에서 입력한 API 키를 환경변수로 반영. save_key면 파일에도 저장(선택 기능)."""
    for field, env, name in (
        ("gemini_key", "GEMINI_API_KEY", "gemini"),
        ("openai_key", "OPENAI_API_KEY", "openai"),
        ("elevenlabs_key", "ELEVENLABS_API_KEY", "elevenlabs"),
    ):
        value = (params.get(field) or "").strip()
        if value:
            os.environ[env] = value
            if params.get("save_key"):
                config.save_api_key(name, value)


def _tts_chain(params: dict, settings: dict) -> list:
    provider = params.get("tts_provider", "stub")
    if provider == "gemini":
        return list(settings["tts"]["fallback_chain"])
    if provider == "elevenlabs":  # 내 목소리 — 실패 시 기존 체인으로 폴백
        return ["elevenlabs", *settings["tts"]["fallback_chain"]]
    if provider == "sovits":      # 무료 내 목소리(로컬) — 실패 시 기존 체인으로 폴백
        return ["sovits", *settings["tts"]["fallback_chain"]]
    return [provider]


def _job_options(params: dict, settings: Optional[dict] = None) -> JobOptions:
    settings = settings or config.load_settings()
    outputs = ["mp4"]
    if params.get("draft"):
        outputs.append("draft")
    return JobOptions(
        outputs=tuple(outputs),
        auto_mode=bool(params.get("auto", True)),
        tts_chain=_tts_chain(params, settings),
        voice=params.get("voice", ""),
        tts_style=params.get("tts_style", ""),
        bgm=params.get("bgm", ""),
        hook=(params.get("hook") or "").strip(),
        target_sec=int(params.get("target_sec") or 60),
        drafts_dir=(params.get("drafts_dir") or "").strip() or None,
        render=RenderOptions(use_gpu=params.get("gpu", "auto")),
    )


def _record_history(workdir: str, result, opts: JobOptions) -> None:
    try:
        from ..db.jobs import JobStore  # noqa: PLC0415

        store = JobStore(Path(workdir) / "history.db")
        spec_json = None
        if result.spec_path and Path(result.spec_path).exists():
            spec_json = Path(result.spec_path).read_text(encoding="utf-8")
        store.upsert(
            result.job_id,
            title=result.title,
            mode="auto" if opts.auto_mode else "review",
            outputs=",".join(opts.outputs),
            status=result.status,
            duration_us=json.loads(spec_json)["duration_us"] if spec_json else 0,
            spec_json=spec_json,
            out_mp4=result.mp4.out_path if result.mp4 else None,
            out_draft=result.draft_path or None,
            error="; ".join(result.errors) or None,
            tts_provider=result.tts_provider or None,
        )
        store.close()
    except Exception:
        pass  # 히스토리 기록 실패는 UI 동작에 영향 없음


def _run_pipeline(job_id: str, script: Script, params: dict, workdir: str) -> None:
    settings = config.load_settings()
    opts = _job_options(params, settings)
    try:
        image_provider = None
        if (
            settings["bg"].get("ai_image")
            and os.environ.get("GEMINI_API_KEY")
            and params.get("script_provider") == "gemini"
        ):
            image_provider = background_generator.GeminiImage(
                model=settings["bg"].get("image_model")
            )

        result = orchestrator.run_job(
            workdir, script, opts=opts, settings=settings,
            image_provider=image_provider,
            progress_cb=lambda stage, frac: _set_job(job_id, stage=stage, frac=frac),
            status_cb=lambda msg: _set_job(job_id, note=msg),
            job_id=job_id,
        )
        _set_job(
            job_id,
            status=result.status,
            stage="done",
            frac=1.0,
            note="",
            title=result.title,
            job_dir=result.job_dir,
            mp4=result.mp4.out_path if (result.mp4 and result.mp4.ok) else None,
            draft=result.draft_path or None,
            tts_provider=result.tts_provider,
            requested_tts=params.get("tts_provider", ""),
            fallback_note=result.fallback_note,
            errors=result.errors,
        )
        _record_history(workdir, result, opts)
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("작업 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed", errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _edit_summary(analysis) -> str:
    return (
        f"원본 {analysis.original_us/1e6:.1f}초 → {analysis.cut_us/1e6:.1f}초 "
        f"(무음 {analysis.removed_ratio*100:.0f}% 컷, 자막 {len(analysis.subtitles)}줄, "
        f"음성인식 {analysis.stt_calls}회)"
    )


def _run_edit(job_id: str, params: dict, workdir: str) -> None:
    """1단계: 무음컷 + 자동자막 분석 → 자막 검토 대기 (Phase 1). 자막 없으면 바로 렌더."""
    try:
        _apply_keys(params)
        settings = config.load_settings()
        edit_cfg = settings["edit"]
        from ..core import edit_mode  # noqa: PLC0415
        from ..core.stt_engine import STTEngine, make_provider  # noqa: PLC0415
        from ..core.video_editor import SilenceOptions, resolve_input_video  # noqa: PLC0415

        photo_path = (params.get("photo_path") or "").strip()
        if photo_path:  # 📸 사진들 → 슬라이드쇼 영상 (장수로 전체 길이 균등 분배)
            from ..core.video_editor import photos_to_video, resolve_photo_inputs  # noqa: PLC0415
            try:
                imgs = resolve_photo_inputs(photo_path)
                try:
                    photo_sec = float(params.get("photo_sec") or 15)
                except (TypeError, ValueError):
                    photo_sec = 15.0
                photo_sec = max(3.0, min(180.0, photo_sec))
                _set_job(job_id, stage="cut", frac=0.0,
                         note=f"사진 {len(imgs)}장 → {photo_sec:.0f}초 영상 만드는 중…")
                (Path(workdir) / job_id).mkdir(parents=True, exist_ok=True)
                video = photos_to_video(
                    imgs, int(photo_sec * 1e6),
                    str(Path(workdir) / job_id / "slideshow.mp4"))
            except Exception as ve:  # noqa: BLE001
                _set_job(job_id, status="failed", errors=[str(ve)])
                return
        else:
            try:  # 폴더를 넣으면 안의 최신 영상 자동 선택
                video = resolve_input_video(params.get("video_path") or "")
            except ValueError as ve:
                _set_job(job_id, status="failed", errors=[str(ve)])
                return

        # 사진 영상은 무음이라 음성 인식·무음 컷이 의미 없음 → 자동 비활성
        auto_subtitle = params.get("auto_subtitle", True) and not photo_path
        cut_silence = bool(params.get("cut_silence", True)) and not photo_path
        script_lines = (params.get("script") or "").splitlines()
        has_script = any(ln.strip() for ln in script_lines)
        narr_topic = (params.get("narr_topic") or "").strip()
        stt = None
        if auto_subtitle and not has_script and not narr_topic:  # 대본/내레이션 있으면 STT 생략
            stt_name = params.get("stt_provider") or edit_cfg["stt_provider"]
            # Whisper 모델(정확도)을 이 작업에서 고른 값으로 덮어씀
            stt_cfg = {**edit_cfg, "whisper_model": params.get("whisper_model") or edit_cfg["whisper_model"]}
            stt = STTEngine(
                make_provider(stt_name, stt_cfg),
                Path(workdir) / "cache" / "stt",
                language=params.get("language", "ko"),
            )
        logging.getLogger("cutdaejang").info(
            "편집 시작: %s (내레이션=%s, 자막만=%s, 완전자동=%s)",
            Path(video).name, bool(narr_topic), bool(params.get('narr_subs_only')), bool(params.get("auto_edit")))
        _set_job(job_id, status="running", stage="analyze", frac=0.0, title=Path(video).stem)
        analysis = edit_mode.analyze_video(
            video, Path(workdir) / job_id, stt,
            auto_subtitle=auto_subtitle, cut_silence=cut_silence,
            script_lines=script_lines if has_script else None,
            silence_opts=SilenceOptions(
                noise_db=edit_cfg["noise_db"], min_silence_s=edit_cfg["min_silence_s"],
                pad_s=edit_cfg["pad_s"],
            ),
            progress_cb=lambda stage, frac: _set_job(job_id, stage=stage, frac=frac),
            status_cb=lambda msg: _set_job(job_id, note=msg),
        )
        # 2줄(기본 32자) 넘는 자막은 화면을 덮음 → 여러 개의 짧은 자막으로 자동 분할
        analysis.subtitles = edit_mode.split_long_subtitles(
            analysis.subtitles, settings["subtitle"].get("wrap_chars", 16))
        denoise = params.get("denoise") or False
        # 발화 자막이 없는 영상(화면 녹화·b-roll)은 핵심 선별을 못 함 → 완전 자동 +
        # 목표 초면 영상 전체에서 고르게 조각을 뽑아 목표 길이 몽타주로 먼저 자름
        tgt_auto = int(params.get("auto_target_sec") or 0) if params.get("auto_edit") else 0
        if (tgt_auto > 0 and not analysis.subtitles and not photo_path
                and analysis.cut_us > (tgt_auto + 3) * 1_000_000):
            from ..core import video_editor as ve  # noqa: PLC0415
            _set_job(job_id, stage="cut", note=f"영상 전체에서 고르게 {tgt_auto}초를 뽑는 중…")
            ranges = edit_mode.spread_ranges(analysis.cut_us, tgt_auto * 1_000_000)
            analysis.cut_video = ve.cut_and_concat(
                analysis.cut_video, ranges,
                str(Path(workdir) / job_id / "auto_montage.mp4"))
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            analysis.cut_us = ff.probe_duration_us(analysis.cut_video)
            _set_job(job_id, tts_warn=(
                f"자막(발화)이 없어 영상 전체에서 고르게 {tgt_auto}초를 골라 담았어요"))
        review_subs = analysis.subtitles
        narr_subs_only = bool(params.get("narr_subs_only"))
        if narr_topic:  # AI 내레이션: 대본 생성 → 컷 길이에 비례 배치 (검토에서 수정)
            _set_job(job_id, stage="script", note="AI 대본 작성 중…")
            try:
                provider = SCRIPT_PROVIDERS["gemini"]() if os.environ.get("GEMINI_API_KEY") \
                    else SCRIPT_PROVIDERS["stub"]()
                # 완전 자동 + 목표 초가 있으면 대본을 그 길이로 (영상은 뒤에서 맞춰 자름)
                want = int(params.get("auto_target_sec") or 0) if params.get("auto_edit") else 0
                target = max(15, min(90, want or int(analysis.cut_us / 1e6)))
                script = provider.generate(narr_topic, target_sec=target)
            except Exception:
                script = SCRIPT_PROVIDERS["stub"]().generate(narr_topic)
            review_subs = edit_mode.align_script_to_segments(
                script.sentences, [(0, analysis.cut_us)], total_us=analysis.cut_us)
            for sub, hl in zip(review_subs, script.highlights):
                sub.highlight = hl or ""
        # 분석 결과를 job에 저장 (2단계 렌더에서 사용)
        _set_job(
            job_id, cut_video=analysis.cut_video,
            edit_params={"layout": params.get("layout") or edit_cfg["layout"],
                         "hook": (params.get("hook") or "").strip(),
                         # 자막만 모드면 대본은 쓰되 목소리(TTS)는 넣지 않음
                         "denoise": denoise,
                         "narration": bool(narr_topic) and not narr_subs_only,
                         "narr_voice": (params.get("narr_voice") or "").strip(),
                         "narr_style": (params.get("narr_style") or "").strip(),
                         # 원본 소리: 목소리를 얹을 때만 기본 무음 (자막만이면 유지)
                         "orig_audio": params.get("orig_audio")
                         or ("mute" if narr_topic and not narr_subs_only else "keep"),
                         "bgm": (params.get("bgm") or "").strip(),
                         "bgm_db": params.get("bgm_db"),
                         "hook_scale": params.get("hook_scale"),
                         "wm_path": (params.get("wm_path") or "").strip().strip('"'),
                         "wm_pos": params.get("wm_pos") or "tr",
                         "wm_scale": params.get("wm_scale") or 0.14},
            edit_summary=_edit_summary(analysis),
        )
        wm_p = (params.get("wm_path") or "").strip().strip('"')
        if wm_p and Path(wm_p).is_file():  # 다음에도 쓰게 기억 (브랜딩용)
            config.save_settings({"watermark": {"path": wm_p,
                                                "pos": params.get("wm_pos") or "tr",
                                                "scale": params.get("wm_scale") or 0.14}})
        analysis.subtitles = review_subs
        if params.get("auto_edit"):  # 🤖 완전 자동: 검토 생략, (키 있으면) AI 다듬기+핵심 선별 → 렌더
            from ..core import script_generator as sg  # noqa: PLC0415

            subs_d = edit_mode.subtitles_to_dicts(analysis.subtitles)
            if subs_d and os.environ.get("GEMINI_API_KEY") and not narr_topic and not has_script:
                _set_job(job_id, stage="script", note="AI가 대본을 다듬는 중…")
                try:
                    lines = sg.refine_subtitles([d["text"] for d in subs_d])
                    for d, t in zip(subs_d, lines):
                        if t:
                            d["text"] = t
                except Exception:
                    pass
            keep = None
            tgt = int(params.get("auto_target_sec") or 0)
            # 내레이션 대본은 이미 목표 길이로 새로 쓴 글 → 핵심 선별로 또 자르지 않음
            if subs_d and tgt > 0 and not narr_topic:
                _set_job(job_id, note=f"핵심 구간 골라 {tgt}초 쇼츠 구성 중…")
                try:
                    pick = sg.suggest_highlights(subs_d, target_sec=tgt)
                    pick_src = "AI"
                except Exception as pe:
                    logging.getLogger("cutdaejang").warning(
                        "AI 핵심 추천 무효/실패 → 후킹 점수 방식으로 대체: %s", pe)
                    pick = sg.suggest_highlights_heuristic(subs_d, target_sec=tgt)
                    pick_src = "후킹 점수"
                keep = pick["keep"]
                if keep:  # 어떤 구간을 골랐는지 투명하게 (로그 + 완료 화면)
                    starts = [subs_d[i].get("start_us", 0) / 1e6 for i in keep]
                    fmt = " · ".join(f"{int(x // 60)}:{int(x % 60):02d}" for x in starts)
                    msg = f"✂️ 핵심 {len(keep)}구간({pick_src}): {fmt}"
                    logging.getLogger("cutdaejang").info(
                        "%s | 사유: %s", msg, pick.get("reason", ""))
                    prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                    _set_job(job_id, tts_warn=f"{prev} · {msg}" if prev else msg)
            try:
                auto_speed = float(params.get("speed") or 1.0)
            except (TypeError, ValueError):
                auto_speed = 1.0
            _do_edit_render(job_id, subs_d, (params.get("hook") or "").strip(),
                            params.get("layout") or edit_cfg["layout"],
                            analysis.cut_video, workdir, keep, auto_speed,
                            params.get("quality") or "standard", denoise)
            return
        if analysis.subtitles:  # STT/입력 대본/내레이션 대본이 있으면 검토 화면으로
            _set_job(
                job_id, status="review_subtitle", stage="review", note="",
                subtitles=edit_mode.subtitles_to_dicts(analysis.subtitles),
                cut_seconds=round(analysis.cut_us / 1e6, 1),
            )
        else:
            # 자막 없음(b-roll 등) → 바로 렌더
            _do_edit_render(job_id, [], params.get("hook", ""),
                            params.get("layout") or edit_cfg["layout"],
                            analysis.cut_video, workdir, denoise=denoise)
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("편집 분석 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _do_edit_render(job_id: str, subtitles_dicts: list, hook: str, layout: str,
                    cut_video: str, workdir: str, keep: Optional[list] = None,
                    speed: float = 1.0, quality: str = "standard",
                    denoise=False) -> None:
    """2단계: (수정된) 자막으로 최종 렌더. keep이 일부면 그 구간만 남겨 쇼츠로 재컷."""
    try:
        from ..core import edit_mode  # noqa: PLC0415
        from ..core.orchestrator import build_style  # noqa: PLC0415

        settings = config.load_settings()
        note = "고화질(4K) 렌더는 사양에 따라 몇 분 걸릴 수 있어요…" if quality == "ultra" else ""
        _set_job(job_id, status="running", stage="render", frac=0.0, note=note)
        subs = edit_mode.dicts_to_subtitles(subtitles_dicts)
        out = str(Path(workdir) / job_id / "edited.mp4")
        job = _get_job(job_id) or {}
        ep = job.get("edit_params") or {}
        if not ep.get("narration"):  # 검토에서 길게 고친 줄도 2줄 초과면 분할 (내레이션은 문장=클립 유지)
            subs = edit_mode.split_long_subtitles(
                subs, settings["subtitle"].get("wrap_chars", 16))
        style = build_style(settings)
        try:  # 상단 제목 크기 배수 (훅 스튜디오)
            style.hook_scale = float(ep.get("hook_scale") or 1.0)
        except (TypeError, ValueError):
            style.hook_scale = 1.0
        if ep.get("narr_style"):  # 내레이션 말투 스타일 (Gemini TTS 프롬프트에 반영)
            settings = config.deep_merge(settings, {"tts": {"style_preset": ep["narr_style"]}})
        orig_audio = ep.get("orig_audio") or "keep"
        bgm_path = None
        if ep.get("bgm"):
            b = orchestrator.resolve_bgm(ep["bgm"], settings)
            bgm_path = b.path if b else None
        try:
            bgm_db = float(ep.get("bgm_db"))
        except (TypeError, ValueError):
            bgm_db = float(settings["bgm"].get("volume_db", -16))
        # 핵심 구간만 골랐으면(전체가 아니면) 영상을 그 구간만 다시 잘라 진짜 쇼츠 길이로.
        # 내레이션보다 먼저 잘라야 목소리가 최종 타임라인 기준으로 배치된다.
        if keep is not None and 0 < len(keep) < len(subs):
            _set_job(job_id, stage="cut", frac=0.0,
                     note=f"고른 {len(keep)}개 구간만 남겨 쇼츠로 자르는 중…")
            cut_video, subs = edit_mode.rebuild_from_keep(
                cut_video, subs, keep, str(Path(workdir) / job_id / "short.mp4"),
            )
        narration_wav = None
        if ep.get("narration") and subs:
            import re as _re  # noqa: PLC0415
            from ..core import tts_engine  # noqa: PLC0415

            def _tts_clean(t: str) -> str:  # 색 마크업·강조 표기는 TTS에서 제거
                t = _re.sub(r"\[[가-힣A-Za-z]+\]|\[/[가-힣A-Za-z]*\]", "", t)
                return (t.rsplit("|", 1)[0] if "|" in t else t).strip()

            _set_job(job_id, stage="tts", frac=0.0, note="AI 목소리 만드는 중…")
            narr_voice = ep.get("narr_voice") or ""
            chain = []
            if narr_voice == "__sovits__":
                chain.append("sovits")      # 무료 내 목소리(로컬) — 실패 시 아래로 폴백
            if narr_voice == "__mine__" and os.environ.get("ELEVENLABS_API_KEY"):
                chain.append("elevenlabs")  # 내 목소리 클론 — 실패 시 아래로 폴백
            if os.environ.get("GEMINI_API_KEY"):
                chain.append("gemini")
            if sys.platform == "win32":
                chain.append("windows")
            chain.append("stub")
            # __mine__/__sovits__는 보이스명이 아니라서 비움 → 제공자별 기본값으로 해석
            voice = "" if narr_voice in ("__mine__", "__sovits__") else (
                narr_voice or settings["tts"].get("voice_gemini", ""))
            texts = [_tts_clean(s2.text) or "네" for s2 in subs]
            clips, used, note = tts_engine.synth_with_fallback(
                texts, chain, Path(workdir) / "cache" / "tts", settings,
                voice=voice,
                on_progress=lambda i, n: _set_job(job_id, stage="tts", frac=i / n),
            )
            # 고른 보이스가 반영 안 되는 폴백이면 이유를 사용자에게 알림
            want = {"__mine__": "elevenlabs", "__sovits__": "sovits"}.get(narr_voice)
            warn = ""
            if want and used != want:
                warn = "⚠ 내 목소리 합성에 실패해 다른 목소리로 대체했어요"
            elif used in ("windows", "stub") and narr_voice not in ("", "__mine__", "__sovits__"):
                low = (note or "").lower()
                if os.environ.get("GEMINI_API_KEY") and any(
                        k in low for k in ("429", "resource_exhausted", "quota", "exceed", "한도")):
                    warn = ("⚠ 제미나이 무료 TTS 한도에 걸려 내장 음성으로 대체됐어요 — "
                            "잠시 뒤(한도 리셋 후) 같은 설정으로 다시 만들면 이미 만든 문장은 "
                            "재사용돼 이어서 완성됩니다. 문장 수를 줄이면 한도 안에 들어가요")
                elif os.environ.get("GEMINI_API_KEY"):
                    warn = "⚠ 제미나이 목소리 합성이 실패해 내장 음성으로 대체됐어요 (하단 🪵 로그 참고)"
                else:
                    warn = ("⚠ 제미나이 키가 없거나 실패해 내장 음성으로 만들었어요 — "
                            "보이스 선택은 제미나이 키가 있어야 적용됩니다")
            if warn:
                logging.getLogger("cutdaejang").warning("%s (사유: %s)", warn, (note or "")[:200])
                note = f"{note} · {warn}" if note else warn
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                _set_job(job_id, tts_warn=f"{prev} · {warn}" if prev else warn)  # 완료 화면 보존
            from ..core import video_editor  # noqa: PLC0415
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            cut_us = ff.probe_duration_us(cut_video)
            # 목소리 실제 길이에 맞춰 자막 재배치 → 자막·목소리 싱크 보장
            subs, clips, sync_note = edit_mode.retime_narration(
                clips, subs, cut_us, Path(workdir) / job_id)
            if sync_note:
                note = f"{note} · {sync_note}" if note else sync_note
            # 내레이션이 끝난 뒤 영상 꼬리가 길게 남으면 잘라 템포 유지
            narr_end_us = subs[-1].end_us + 700_000 if subs else cut_us
            if cut_us > narr_end_us + 1_500_000:
                _set_job(job_id, stage="cut", note="내레이션 길이에 맞춰 영상을 다듬는 중…")
                cut_video = video_editor.cut_and_concat(
                    cut_video, [(0, narr_end_us)],
                    str(Path(workdir) / job_id / "narr_fit.mp4"))
                cut_us = ff.probe_duration_us(cut_video)
            narration_wav = edit_mode.build_narration_wav(
                clips, subs, cut_us, Path(workdir) / job_id / "narration.wav")
            if note:
                _set_job(job_id, note=note)
        watermark = None
        if ep.get("wm_path"):
            if Path(ep["wm_path"]).is_file():
                watermark = {"path": ep["wm_path"], "pos": ep.get("wm_pos") or "tr",
                             "scale": ep.get("wm_scale") or 0.14,
                             "opacity": settings["watermark"].get("opacity", 0.85)}
            else:
                logging.getLogger("cutdaejang").warning(
                    "워터마크 파일을 찾지 못해 없이 렌더: %s", ep["wm_path"])
        result = edit_mode.render_from_analysis(
            cut_video, subs, out, style=style,
            layout=layout, hook=hook, speed=speed, quality=quality, denoise=denoise,
            narration_wav=narration_wav,
            orig_audio=orig_audio, bgm_path=bgm_path, bgm_db=bgm_db,
            watermark=watermark,
            progress_cb=lambda f: _set_job(job_id, stage="render", frac=f),
        )
        logging.getLogger("cutdaejang").info(
            "렌더 %s: %s", "완료" if result.ok else "부분 실패", out)
        _set_job(
            job_id,
            status="ok" if result.ok else "partial" if Path(out).exists() else "failed",
            stage="done", frac=1.0,
            note=(_get_job(job_id) or {}).get("tts_warn") or "",
            job_dir=str(Path(workdir) / job_id),
            mp4=out if Path(out).exists() else None,
            errors=result.errors,
        )
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("편집 렌더 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _do_edit_split(job_id: str, subtitles_dicts: list, hook: str, layout: str,
                   cut_video: str, workdir: str, target_sec: float = 30.0,
                   speed: float = 1.0, quality: str = "standard",
                   denoise=False) -> None:
    """긴 영상을 목표 길이 단위 쇼츠 여러 개로 분할 렌더 (edited_1..N.mp4)."""
    try:
        from ..core import edit_mode  # noqa: PLC0415
        from ..core.orchestrator import build_style  # noqa: PLC0415

        settings = config.load_settings()
        subs = edit_mode.dicts_to_subtitles(subtitles_dicts)
        groups = edit_mode.split_into_clips(subs, target_sec=target_sec)
        if not groups:
            _set_job(job_id, status="failed", errors=["나눌 자막이 없습니다"])
            return
        job_dir = Path(workdir) / job_id
        outs, errors = [], []
        style = build_style(settings)
        for gi, idxs in enumerate(groups, 1):
            _set_job(job_id, status="running", stage="render", frac=0.0,
                     note=f"쇼츠 {gi}/{len(groups)} 만드는 중…")
            try:
                clip_video, clip_subs = edit_mode.rebuild_from_keep(
                    cut_video, subs, idxs, str(job_dir / f"short_{gi}.mp4"),
                )
                out = str(job_dir / f"edited_{gi}.mp4")
                base = (gi - 1) / len(groups)
                r = edit_mode.render_from_analysis(
                    clip_video, clip_subs, out, style=style, layout=layout,
                    hook=hook, speed=speed, quality=quality, denoise=denoise,
                    progress_cb=lambda f, b=base, n=len(groups): _set_job(
                        job_id, stage="render", frac=b + f / n),
                )
                if Path(out).exists():
                    outs.append(out)
                errors += r.errors
            except Exception as ce:  # 한 클립 실패해도 나머지는 계속
                errors.append(f"쇼츠 {gi} 실패: {ce}")
        _set_job(
            job_id,
            status="ok" if outs and not errors else "partial" if outs else "failed",
            stage="done", frac=1.0, job_dir=str(job_dir),
            note=f"쇼츠 {len(outs)}개 완성" if outs else "",
            mp4=outs[0] if outs else None, mp4s=outs, errors=errors,
        )
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("분할 렌더 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _run_generate(job_id: str, params: dict, workdir: str) -> None:
    """대본 생성 → 자동 모드면 즉시 파이프라인, 검토 모드면 대기 (기획안 §1.3)."""
    try:
        _apply_keys(params)
        _set_job(job_id, status="running", stage="script", frac=0.0)
        provider = SCRIPT_PROVIDERS[params.get("script_provider", "stub")]()
        script = orchestrator.generate_script(
            provider, params["topic"], _job_options(params)
        )
        job_dir = Path(workdir) / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "script.json").write_text(script.to_json(), encoding="utf-8")

        if params.get("auto", True):
            _run_pipeline(job_id, script, params, workdir)
        else:
            _set_job(
                job_id,
                status="awaiting_review",
                stage="review",
                title=script.title,
                script={"title": script.title, "sentences": script.sentences,
                        "highlights": script.highlights,
                        "background_prompt": script.background_prompt},
            )
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("작업 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed", errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


class _Handler(BaseHTTPRequestHandler):
    server_version = "cutdaejang-ui"

    def log_message(self, *args) -> None:  # 콘솔 소음 제거
        pass

    # ---------- 응답 헬퍼 ----------

    def _send_json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    # ---------- 라우팅 ----------

    def do_GET(self) -> None:  # noqa: N802
        # 작업 id에 한글이 들어가므로 퍼센트 인코딩된 경로를 복원해야 매칭된다
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        if path == "/":
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            self._send_json(self._state())
        elif path.startswith("/video/"):
            self._serve_video(path.split("/", 2)[2])
        elif path.startswith("/cutvideo/"):
            self._serve_cutvideo(path.split("/", 2)[2])
        elif path.startswith("/thumbnail/"):
            job = _get_job(path.split("/", 2)[2])
            tp = job.get("thumbnail") if job else None
            if tp and Path(tp).is_file():
                self._serve_file(tp)
            else:
                self._send_json({"error": "썸네일 없음"}, 404)
        elif path.startswith("/preview/"):
            self._serve_preview(path.split("/", 2)[2])
        elif path.startswith("/bgm/"):
            self._serve_bgm(path.split("/", 2)[2])
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            params = self._read_json()
        except json.JSONDecodeError:
            self._send_json({"error": "잘못된 요청"}, 400)
            return

        workdir = self.server.workdir  # type: ignore[attr-defined]
        if path == "/api/generate":
            topic = (params.get("topic") or "").strip()
            if not topic:
                self._send_json({"error": "주제를 입력하세요"}, 400)
                return
            job_id = orchestrator.new_job_id(topic)
            _set_job(job_id, status="running", stage="script", frac=0.0,
                     title=topic, params=params)
            threading.Thread(
                target=_run_generate, args=(job_id, params, workdir), daemon=True
            ).start()
            self._send_json({"job_id": job_id})
        elif path == "/api/confirm":
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "awaiting_review":
                self._send_json({"error": "검토 대기 중인 작업이 아닙니다"}, 400)
                return
            # "문장 | 강조단어" 형식 지원 (지시서 5-1 검토 모드 강조 수정)
            sentences, highlights = [], []
            for line in params.get("sentences", []):
                line = line.strip()
                if not line:
                    continue
                text, _, hl = line.partition("|")
                sentences.append(text.strip())
                highlights.append(hl.strip())
            if not sentences:
                self._send_json({"error": "문장이 비어 있습니다"}, 400)
                return
            script = Script(
                title=params.get("title") or job.get("title", ""),
                sentences=sentences,
                highlights=highlights,
                background_prompt=(job.get("script") or {}).get("background_prompt", ""),
            )
            _set_job(job["id"], status="running", stage="tts", frac=0.0)
            threading.Thread(
                target=_run_pipeline,
                args=(job["id"], script, job.get("params", {}), workdir),
                daemon=True,
            ).start()
            self._send_json({"ok": True})
        elif path == "/api/edit":
            video = (params.get("video_path") or "").strip().strip('"')
            if not video and not (params.get("photo_path") or "").strip():
                self._send_json({"error": "영상 파일(또는 사진 폴더) 경로를 입력하세요"}, 400)
                return
            if not video:
                video = "사진영상"  # 사진 모드 — 제목용
            job_id = orchestrator.new_job_id(Path(video).stem or "edit")
            _set_job(job_id, status="running", stage="analyze", frac=0.0,
                     title=Path(video).stem, params=params)
            threading.Thread(
                target=_run_edit, args=(job_id, params, workdir), daemon=True
            ).start()
            self._send_json({"job_id": job_id})
        elif path == "/api/edit_render":
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_subtitle":
                self._send_json({"error": "자막 검토 중인 작업이 아닙니다"}, 400)
                return
            ep = job.get("edit_params") or {}
            if params.get("hook_scale") is not None:
                ep["hook_scale"] = params.get("hook_scale")
                _set_job(job["id"], edit_params=ep)
            hook = params.get("hook", ep.get("hook", ""))
            keep = params.get("keep")  # 고른 구간(번호). None이면 전체 유지
            if keep is not None:
                keep = [int(i) for i in keep]
            try:
                speed = float(params.get("speed") or 1.0)
            except (TypeError, ValueError):
                speed = 1.0
            quality = params.get("quality") or "standard"
            # 잡음 제거는 편집 폼에서 정한 값(edit_params)을 따름
            denoise = ep.get("denoise") or False
            threading.Thread(
                target=_do_edit_render,
                args=(job["id"], params.get("subtitles") or [], hook,
                      ep.get("layout", "shorts"), job.get("cut_video"), workdir,
                      keep, speed, quality, denoise),
                daemon=True,
            ).start()
            self._send_json({"ok": True})
        elif path == "/api/refine_subtitles":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            texts = [str((s or {}).get("text", "")) for s in (params.get("subtitles") or [])]
            if not any(t.strip() for t in texts):
                self._send_json({"error": "다듬을 자막이 없습니다"}, 400)
                return
            try:
                lines = sg.refine_subtitles(texts, context=params.get("context", ""))
                self._send_json({"lines": lines})
            except sg.ScriptError as e:
                self._send_json({"error": str(e)}, 400)
            except Exception as e:
                self._send_json({"error": f"대본 다듬기 실패: {e}"}, 500)
        elif path == "/api/suggest_highlights":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            subs = params.get("subtitles") or []
            target = int(params.get("target_sec") or 30)
            if not subs:
                self._send_json({"error": "자막이 없습니다"}, 400)
                return
            try:
                res = sg.suggest_highlights(subs, target_sec=target)
                res["ai"] = True
            except sg.ScriptError:
                res = sg.suggest_highlights_heuristic(subs, target_sec=target)  # 키 없으면 대략치
                res["ai"] = False
            except Exception as e:  # 파싱 등 실패해도 대역으로
                res = sg.suggest_highlights_heuristic(subs, target_sec=target)
                res["ai"] = False
                res["reason"] = res.get("reason", "") + f" (AI 실패: {e})"
            self._send_json(res)
        elif path == "/api/edit_split":
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_subtitle":
                self._send_json({"error": "자막 검토 중인 작업이 아닙니다"}, 400)
                return
            ep = job.get("edit_params") or {}
            try:
                target = float(params.get("target_sec") or 30)
                speed = float(params.get("speed") or 1.0)
            except (TypeError, ValueError):
                target, speed = 30.0, 1.0
            threading.Thread(
                target=_do_edit_split,
                args=(job["id"], params.get("subtitles") or [],
                      params.get("hook", ep.get("hook", "")),
                      ep.get("layout", "shorts"), job.get("cut_video"), workdir,
                      target, speed, params.get("quality") or "standard",
                      ep.get("denoise") or False),
                daemon=True,
            ).start()
            self._send_json({"ok": True})
        elif path == "/api/suggest_thumbnail":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            ctx = (params.get("context") or "").strip()
            if not ctx:
                self._send_json({"error": "주제/대본을 먼저 넣어주세요"}, 400)
                return
            try:
                copies = sg.suggest_thumbnail_copy(ctx)
                ai = True
            except sg.ScriptError:
                copies = sg.suggest_thumbnail_copy_stub(ctx)  # 키 없으면 템플릿
                ai = False
            self._send_json({"copies": copies, "ai": ai})
        elif path == "/api/thumbnail":
            from ..core import thumbnail as thumb  # noqa: PLC0415
            from ..core.orchestrator import build_style  # noqa: PLC0415

            job = _get_job(params.get("job_id", ""))
            bg = (params.get("bg_path") or "").strip() or (job.get("mp4") if job else None)
            if not bg or not Path(bg).is_file():
                self._send_json({"error": "배경으로 쓸 완성 영상(또는 사진)이 없습니다"}, 400)
                return
            title = (params.get("title") or "").strip()
            if not title:
                self._send_json({"error": "썸네일 제목을 입력하세요"}, 400)
                return
            out_dir = Path(job["job_dir"]) if job and job.get("job_dir") else Path(bg).parent
            out = str(out_dir / "thumbnail.png")
            try:
                thumb.make_thumbnail(
                    bg, title, out, highlight=params.get("highlight", ""),
                    badge=(params.get("badge") or "").strip(),
                    style=build_style(config.load_settings()),
                )
                if job:
                    _set_job(job["id"], thumbnail=out)
                    self._send_json({"ok": True, "url": f"/thumbnail/{job['id']}", "path": out})
                else:
                    self._send_json({"ok": True, "path": out})
            except Exception as e:
                import logging  # noqa: PLC0415
                import traceback  # noqa: PLC0415
                logging.getLogger("cutdaejang").error("썸네일 실패\n%s", traceback.format_exc())
                self._send_json({"error": f"썸네일 생성 실패: {e}"}, 500)
        elif path == "/api/pick_file":
            try:
                picked = pick_video_file()
                self._send_json({"path": picked or "", "cancelled": picked is None})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/api/preview":
            self._preview(params)
        elif path == "/api/suggest_hooks":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            ctx = (params.get("context") or "").strip()
            if not ctx:
                self._send_json({"error": "주제/내용을 먼저 입력하세요"}, 400)
                return
            try:
                hooks = sg.suggest_hooks(ctx)
            except sg.ScriptError:
                hooks = sg.suggest_hooks_stub(ctx)  # 키 없으면 템플릿
            self._send_json({"hooks": hooks})
        elif path == "/api/analyze_ai":
            # 🧠 영상 AI 분석 — 장면 캡처+자막을 Gemini에 보내 제목·훅·대본 추천
            _apply_keys(params)
            from ..core import edit_mode, script_generator as sg  # noqa: PLC0415
            job = _get_job(params.get("job_id", ""))
            video = (job or {}).get("cut_video")
            if not video or not Path(video).is_file():
                self._send_json({"error": "분석할 영상이 없습니다 — 먼저 편집을 시작하세요"}, 400)
                return
            transcript = "\n".join(
                (s.get("text") or "") for s in (job.get("subtitles") or []))[:4000]
            try:
                frames = edit_mode.extract_frames_b64(video, n=4)
                if os.environ.get("GEMINI_API_KEY"):
                    out = sg.suggest_from_video(frames, transcript)
                    out["stub"] = False
                else:
                    out = sg.suggest_from_video_stub(frames, transcript)
                    out["stub"] = True
                self._send_json(out)
            except sg.ScriptError as e:
                self._send_json({"error": str(e)}, 400)
        elif path == "/api/sovits_save":
            # GPT-SoVITS 무료 내 목소리 — 참조 녹음/대사/서버 주소 저장
            ref = (params.get("ref_audio") or "").strip().strip('"')
            txt = (params.get("ref_text") or "").strip()
            url = (params.get("url") or "").strip()
            if not ref or not Path(ref).is_file():
                self._send_json({"error": f"참조 녹음 파일을 찾을 수 없습니다: {ref or '(비어 있음)'}"}, 400)
                return
            if not txt:
                self._send_json({"error": "참조 녹음에서 말한 문장을 입력하세요 (정확할수록 품질↑)"}, 400)
                return
            merged = {"tts": {"sovits_ref_audio": ref, "sovits_ref_text": txt}}
            if url:
                merged["tts"]["sovits_url"] = url
            config.save_settings(merged)
            self._send_json({"ok": True})
        elif path == "/api/clone_voice":
            # 내 목소리 등록 (ElevenLabs 인스턴트 클론) → voice_id를 설정에 저장
            _apply_keys(params)
            fname = (params.get("file_path") or "").strip().strip('"')
            vname = (params.get("name") or "내 목소리").strip() or "내 목소리"
            try:
                vid = tts_engine.clone_voice(vname, fname)
                config.save_settings({"tts": {"voice_elevenlabs": vid,
                                              "voice_elevenlabs_name": vname}})
                self._send_json({"ok": True, "voice_id": vid, "name": vname})
            except tts_engine.TTSError as e:
                self._send_json({"error": str(e)}, 400)
        elif path == "/api/pronounce":
            from ..utils.pronounce import pronounce_ko  # noqa: PLC0415

            self._send_json({"lines": [pronounce_ko(l) for l in params.get("lines", [])]})
        elif path == "/api/settings":
            try:
                saved_to = config.save_settings(params.get("settings") or {})
                self._send_json({"ok": True, "path": saved_to})
            except OSError as e:
                self._send_json({"error": f"설정 저장 실패: {e}"}, 500)
        elif path == "/api/keys":
            if params.get("action") == "clear":
                config.clear_api_keys()
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "지원하지 않는 동작"}, 400)
        elif path == "/api/regenerate":
            self._regenerate(params, workdir)
        elif path == "/api/diagnostic":
            self._diagnostic(workdir)
        elif path == "/api/open_folder":
            self._open_folder(params, workdir)
        else:
            self._send_json({"error": "not found"}, 404)

    # ---------- 재생성 (히스토리 → 저장된 spec 재렌더) ----------

    def _regenerate(self, params: dict, workdir: str) -> None:
        from ..db.jobs import JobStore  # noqa: PLC0415
        from ..spec import TimelineSpec  # noqa: PLC0415

        store = JobStore(Path(workdir) / "history.db")
        row = store.get(params.get("job_id", ""))
        store.close()
        if not row or not row["spec_json"]:
            self._send_json({"error": "재생성할 spec이 없습니다"}, 404)
            return
        spec = TimelineSpec.from_json(row["spec_json"])
        missing = spec.missing_files()
        if missing:
            self._send_json(
                {"error": "원본 소재 파일이 삭제되어 재생성 불가: " + ", ".join(missing[:3])}, 409
            )
            return

        new_id = f"{row['id']}-r{_dt_stamp()}"
        title = row["title"] or row["id"]
        _set_job(new_id, status="running", stage="render", frac=0.0, title=f"{title} (재생성)")

        def run():
            try:
                from ..core import render_engine  # noqa: PLC0415
                from ..core.orchestrator import safe_filename  # noqa: PLC0415

                job_dir = Path(workdir) / new_id
                result = render_engine.render(
                    spec, job_dir / "render",
                    out_path=str(job_dir / f"{safe_filename(title)}.mp4"),
                    progress_cb=lambda f: _set_job(new_id, stage="render", frac=f),
                )
                _set_job(
                    new_id,
                    status="ok" if result.ok else "failed",
                    stage="done", frac=1.0, job_dir=str(job_dir),
                    mp4=result.out_path if result.ok else None,
                    errors=[] if result.ok else result.errors,
                )
                try:
                    store2 = JobStore(Path(workdir) / "history.db")
                    store2.upsert(
                        new_id, title=f"{title} (재생성)", mode=row["mode"],
                        outputs="mp4", status="ok" if result.ok else "failed",
                        duration_us=spec.duration_us, spec_json=row["spec_json"],
                        out_mp4=result.out_path if result.ok else None,
                        tts_provider=row["tts_provider"],
                    )
                    store2.close()
                except Exception:
                    pass
            except Exception as e:
                _set_job(new_id, status="failed", errors=[str(e)])

        threading.Thread(target=run, daemon=True).start()
        self._send_json({"job_id": new_id})

    # ---------- 진단 리포트 / 폴더 열기 ----------

    def _diagnostic(self, workdir: str) -> None:
        import datetime as dt  # noqa: PLC0415
        import platform  # noqa: PLC0415
        import subprocess  # noqa: PLC0415

        from .. import __version__  # noqa: PLC0415
        from ..utils import ffmpeg as ff  # noqa: PLC0415

        lines = [
            "=" * 60,
            f"컷대장 진단 리포트  {dt.datetime.now().isoformat(timespec='seconds')}",
            f"버전: v{__version__} / Python {platform.python_version()} / {platform.platform()}",
            "=" * 60,
            "",
            "── 환경 ──",
        ]
        try:
            ver = subprocess.run([ff.ffmpeg_bin(), "-version"], capture_output=True, timeout=15)
            lines.append("ffmpeg: " + ver.stdout.decode("utf-8", "replace").splitlines()[0])
        except Exception as e:
            lines.append(f"ffmpeg: ✘ {e}")
        env = _env_check()
        lines.append(f"libass 폰트 동봉: {'OK' if env['font'] else '없음'}")
        lines += ["", "── 최근 로그 (하단 🪵 패널과 동일) ──", *list(_LOG_BUF)[-150:]]
        try:
            lines.append(f"GPU 인코딩(nvenc): {'사용가능' if ff.nvenc_available() else '미감지(libx264)'}")
        except Exception as e:
            lines.append(f"GPU 감지 오류: {e}")
        for name, on in self._state()["keys"].items():
            lines.append(f"{name} 키: {'설정됨' if on else '없음'}")
        lines.append(f"음성인식 사용가능: {_stt_available()}")

        lines.append("")
        lines.append("── 설정(settings.json) ──")
        try:
            lines.append(json.dumps(config.load_settings(), ensure_ascii=False, indent=2))
        except Exception as e:
            lines.append(f"설정 로드 오류: {e}")

        lines.append("")
        lines.append("── 최근 작업 8건 ──")
        for r in self._state()["history"][:8]:
            lines.append(f"{r['created_at']}  [{r['status']}] {r['title']} (목소리: {r['tts_provider'] or '-'})")

        # 진행 중/방금 끝난 작업의 전체 오류(자르지 않음) + 파라미터(키 제외)
        with _LOCK:
            recent = list(_JOBS.values())[-5:]
        for j in recent:
            if j.get("errors") or j.get("status") == "failed":
                lines.append("")
                lines.append(f"── 작업 상세 ({j['id']}, 상태={j.get('status')}) ──")
                p = dict(j.get("params") or {})
                for k in ("gemini_key", "openai_key"):
                    if p.get(k):
                        p[k] = "***"
                if p:
                    lines.append("입력: " + json.dumps(p, ensure_ascii=False))
                for e in (j.get("errors") or []):
                    lines.append(str(e))  # 전체 (원본 오류·stderr 꼬리 포함)

        log_file = Path(workdir) / "logs" / "cutdaejang.log"
        if log_file.exists():
            lines.append("")
            lines.append("── 로그 (마지막 200줄, 전체 오류 추적 포함) ──")
            lines += log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]

        out = Path(workdir) / f"진단리포트_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        out.write_text("\n".join(lines), encoding="utf-8")
        self._send_json({"path": str(out.resolve())})

    def _open_folder(self, params: dict, workdir: str) -> None:
        job = _get_job(params.get("job_id", ""))
        target = Path(job["job_dir"]) if job and job.get("job_dir") else Path(workdir)
        if not target.is_dir():
            self._send_json({"error": "폴더 없음"}, 404)
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(target))  # noqa: S606
            else:
                import subprocess  # noqa: PLC0415

                subprocess.Popen(["xdg-open", str(target)])
            self._send_json({"ok": True, "path": str(target)})
        except Exception as e:
            self._send_json({"error": str(e), "path": str(target)}, 500)

    # ---------- 목소리 미리듣기 (지시서 PATCH 6) ----------

    def _preview(self, params: dict) -> None:
        _apply_keys(params)
        settings = config.load_settings()
        if params.get("tts_style"):
            settings = config.deep_merge(
                settings, {"tts": {"style_preset": params["tts_style"]}}
            )
        try:
            provider = tts_engine.make_provider(params.get("tts_provider", "stub"), settings)
            engine = tts_engine.TTSEngine(
                provider,
                Path(self.server.workdir) / "cache" / "tts",  # type: ignore[attr-defined]
                settings=settings,
            )
            path = engine.synth_sentence(
                params.get("text") or "안녕하세요, 컷대장 목소리 미리듣기입니다.",
                voice=params.get("voice", ""),
            )
            self._send_json({"url": f"/preview/{path.name}"})
        except tts_engine.TTSError as e:
            self._send_json({"error": str(e)}, 400)

    def _serve_bgm(self, name: str) -> None:
        """BGM 미리듣기 — resources/bgm 폴더 안 음원 파일만 서빙."""
        safe = Path(name).name
        p = orchestrator.DEFAULT_BGM_DIR / safe
        if (safe != name or not p.is_file()
                or p.suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}):
            self._send_json({"error": "not found"}, 404)
            return
        self._serve_file(str(p))

    def _serve_preview(self, name: str) -> None:
        if not (name.endswith(".wav") and name[:-4].isalnum()):  # 캐시 해시 파일만
            self._send_json({"error": "not found"}, 404)
            return
        path = Path(self.server.workdir) / "cache" / "tts" / name  # type: ignore[attr-defined]
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- 상태 ----------

    def _state(self) -> dict:
        with _LOCK:
            jobs = [dict(j) for j in _JOBS.values()]
        for j in jobs:
            j.pop("params", None)  # API 키 등 입력값은 화면으로 돌려보내지 않음
        jobs.sort(key=lambda j: j["id"], reverse=True)

        history = []
        try:
            from ..db.jobs import JobStore  # noqa: PLC0415

            store = JobStore(Path(self.server.workdir) / "history.db")  # type: ignore[attr-defined]
            active_ids = {j["id"] for j in jobs}
            history = [
                {
                    "id": r["id"], "title": r["title"], "mode": r["mode"],
                    "status": r["status"], "created_at": r["created_at"],
                    "has_mp4": bool(r["out_mp4"] and Path(r["out_mp4"]).exists()),
                    "has_spec": bool(r["spec_json"]),
                    "tts_provider": r["tts_provider"] or "",
                    "draft": r["out_draft"] or "",
                }
                for r in store.list(limit=30)
                if r["id"] not in active_ids
            ]
            store.close()
        except Exception:
            pass
        return {
            "jobs": jobs,
            "history": history,
            "drafts_dir": default_drafts_dir(),
            "keys": {
                "gemini": bool(os.environ.get("GEMINI_API_KEY")),
                "openai": bool(os.environ.get("OPENAI_API_KEY")),
                "elevenlabs": bool(os.environ.get("ELEVENLABS_API_KEY")),
            },
            "platform": sys.platform,
            "env": _env_check(),
            "settings": config.load_settings(),
            "bgm_files": sorted(
                p.name
                for p in orchestrator.DEFAULT_BGM_DIR.glob("*")
                if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
            ),
            "voices": GEMINI_VOICES,
            "styles": list(STYLE_INSTRUCTIONS),
            "stt_available": _stt_available(),
            "logs": list(_LOG_BUF)[-120:],
        }

    # ---------- 영상 서빙 (Range 지원 — 브라우저 탐색바용) ----------

    def _video_path(self, job_id: str) -> Optional[str]:
        job = _get_job(job_id)
        if job and job.get("mp4") and Path(job["mp4"]).exists():
            return job["mp4"]
        try:
            from ..db.jobs import JobStore  # noqa: PLC0415

            store = JobStore(Path(self.server.workdir) / "history.db")  # type: ignore[attr-defined]
            row = store.get(job_id)
            store.close()
            if row and row["out_mp4"] and Path(row["out_mp4"]).exists():
                return row["out_mp4"]
        except Exception:
            pass
        return None

    def _serve_cutvideo(self, job_id: str) -> None:
        """자막 검토 중 참고 재생용 컷 영상(자막 없는 상태)."""
        job = _get_job(job_id)
        path = job.get("cut_video") if job else None
        if not path or not Path(path).is_file():
            self._send_json({"error": "컷 영상 없음"}, 404)
            return
        self._serve_file(path)

    def _serve_video(self, job_id: str) -> None:
        path = self._video_path(job_id)
        if not path:
            self._send_json({"error": "영상 없음"}, 404)
            return
        self._serve_file(path)

    def _serve_file(self, path: str) -> None:
        size = os.path.getsize(path)
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            try:
                raw_start, _, raw_end = range_header[6:].partition("-")
                start = int(raw_start) if raw_start else 0
                end = int(raw_end) if raw_end else size - 1
                end = min(end, size - 1)
            except ValueError:
                start, end = 0, size - 1
        length = end - start + 1

        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".mp3": "audio/mpeg", ".wav": "audio/wav",
                 ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".flac": "audio/flac",
                 }.get(Path(path).suffix.lower(), "video/mp4")
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)


_LOG_BUF: deque = deque(maxlen=400)  # 🪵 UI 하단 로그 패널용 링버퍼


class _UILogHandler(logging.Handler):
    def emit(self, record):  # noqa: D102
        try:
            _LOG_BUF.append(
                f"{time.strftime('%H:%M:%S')} [{record.levelname[0]}] {record.getMessage()}")
        except Exception:  # noqa: BLE001
            pass


def _attach_ui_log() -> None:
    lg = logging.getLogger("cutdaejang")
    if not any(isinstance(h, _UILogHandler) for h in lg.handlers):
        lg.addHandler(_UILogHandler())
    if lg.level in (logging.NOTSET, logging.WARNING):
        lg.setLevel(logging.INFO)


def create_server(workdir: str, port: int = 7860) -> ThreadingHTTPServer:
    Path(workdir).mkdir(parents=True, exist_ok=True)
    _attach_ui_log()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    httpd.workdir = str(workdir)  # type: ignore[attr-defined]
    return httpd


def _setup_file_logging(workdir: str) -> None:
    import logging  # noqa: PLC0415

    log_dir = Path(workdir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "cutdaejang.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("cutdaejang")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def serve(workdir: str = "jobs", port: int = 7860, open_browser: bool = True) -> int:
    loaded = config.load_api_keys_into_env()
    if loaded:
        print(f"저장된 API 키 로드: {', '.join(loaded)}")
    _setup_file_logging(workdir)
    httpd = None
    for candidate in range(port, port + 10):  # 이전 서버가 켜져 있어도 다음 포트로
        try:
            httpd = create_server(workdir, candidate)
            break
        except OSError:
            continue
    if httpd is None:
        print(f"[!] {port}~{port + 9} 포트를 모두 사용 중입니다. 켜져 있는 컷대장 창을 닫아주세요.")
        return 1
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"컷대장 UI: {url}   (끝내려면 Ctrl+C — 이 창을 닫으면 UI도 꺼집니다)")
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


# ─────────────────────────── 화면 (단일 페이지) ───────────────────────────

_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>컷대장</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
         background:#0f1117; color:#e8eaf0; }
  .wrap { max-width:860px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:22px; margin:0 0 4px; } h1 small{ color:#8b93a7; font-size:13px; font-weight:400; }
  .card { background:#171a23; border:1px solid #262b3a; border-radius:12px;
          padding:18px; margin-top:16px; }
  label { display:block; font-size:13px; color:#aab2c5; margin:12px 0 4px; }
  input[type=text], input[type=password], input[type=number], select, textarea {
    width:100%; padding:10px 12px; border-radius:8px; border:1px solid #2c3347;
    background:#0f1117; color:#e8eaf0; font-size:14px; }
  textarea { min-height:140px; line-height:1.7; }
  .row { display:flex; gap:12px; flex-wrap:wrap; } .row > div { flex:1; min-width:180px; }
  .toggle { display:flex; gap:8px; margin-top:6px; }
  .toggle label { flex:1; margin:0; text-align:center; padding:10px; border-radius:8px;
    border:1px solid #2c3347; cursor:pointer; color:#aab2c5; font-size:14px; }
  .toggle input { display:none; }
  .toggle input:checked + span { color:#fff; }
  .toggle label:has(input:checked) { background:#243052; border-color:#4266d5; color:#fff; }
  .chk { display:flex; align-items:center; gap:8px; margin-top:12px; font-size:14px; color:#cdd3e0; }
  button { padding:12px 18px; border-radius:9px; border:0; background:#4266d5; color:#fff;
           font-size:15px; font-weight:700; cursor:pointer; width:100%; margin-top:16px; }
  button:disabled { background:#2c3347; color:#6b7387; cursor:default; }
  button.ghost { background:transparent; border:1px solid #2c3347; width:auto; padding:8px 14px;
                 font-size:13px; font-weight:400; margin:0; }
  .bar { height:10px; background:#0f1117; border-radius:6px; overflow:hidden; margin-top:8px; }
  .bar > div { height:100%; background:linear-gradient(90deg,#4266d5,#7a5cf0); width:0%; transition:width .4s; }
  .stage { font-size:13px; color:#8b93a7; margin-top:8px; }
  video { width:100%; max-width:320px; border-radius:12px; margin-top:12px; background:#000; display:block; }
  .err { color:#ff7b8a; font-size:13px; white-space:pre-wrap; margin-top:8px; }
  .ok-badge { color:#5dd39e; } .fail-badge { color:#ff7b8a; }
  table { width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }
  th, td { text-align:left; padding:8px 6px; border-bottom:1px solid #232838; color:#cdd3e0; }
  th { color:#8b93a7; font-weight:400; }
  .hint { font-size:12px; color:#6b7387; margin-top:4px; }
  .banner { background:#3a1520; border:1px solid #ff7b8a; color:#ffb3bd; border-radius:10px;
            padding:12px 14px; margin-top:14px; font-size:13px; }
  .hookcands { display:flex; flex-direction:column; gap:6px; margin-top:8px; }
  .hookcands button { width:100%; text-align:left; background:#12305a; border:1px solid #2c4a7a;
    color:#dfe7f5; border-radius:8px; padding:9px 12px; font-size:14px; cursor:pointer; margin:0; }
  .hookcands button:hover { background:#183c72; }
  .subrow-active { background:#243052; box-shadow:0 0 0 1px #4266d5 inset; }
  .subrow-active input { border-color:#4266d5; }
  /* 자막 검토: 영상 플레이어를 위에 고정(sticky) — 스크롤해도 항상 보임 */
  .playbar { position:sticky; top:0; z-index:6; background:#171a23; padding:8px 0 10px;
             border-bottom:1px solid #262b3a; margin-bottom:8px; }
  .playbar video { max-width:200px; margin:0; }
  .playrow { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:8px; }
  .playrow button { margin:0; }
  .pbtn { width:auto; padding:8px 14px; font-size:14px; }
  .playrow select { width:auto; padding:6px 8px; }
  .subrowbtns button { padding:6px 9px; font-size:12px; }
  .subList-scroll { max-height:46vh; overflow-y:auto; padding-right:4px; }
  .shortsbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:10px;
               padding:8px 10px; border:1px dashed #3a4157; border-radius:10px; }
  .shortsbar button { margin:0; }
  .keepchk { width:18px; height:18px; margin-top:8px; flex:none; cursor:pointer; accent-color:#4266d5; }
  .subrow.dropped { opacity:0.4; }
  .subrow.dropped input[type=text] { text-decoration:line-through; }
  .hidden { display:none !important; }
  code { background:#0f1117; padding:2px 6px; border-radius:4px; font-size:12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>컷대장 <small>쇼츠 자동 조립 — 확인용 UI (v0.35)</small></h1>
  <div class="banner hidden" id="envBanner"></div>

  <div class="toggle" style="margin-top:16px">
    <label><input type="radio" name="appmode" value="ai" checked onchange="switchAppMode()"><span>🎬 주제로 AI 영상 만들기</span></label>
    <label><input type="radio" name="appmode" value="edit" onchange="switchAppMode()"><span>✂️ 내 영상 편집 (무음컷+자동자막)</span></label>
  </div>

  <div class="card hidden" id="editCard">
    <label>영상 파일</label>
    <div style="display:flex; gap:8px">
      <input type="text" id="editVideo" style="flex:1" placeholder="[📁 영상 선택] 을 누르거나 경로를 붙여넣기">
      <button class="ghost" style="white-space:nowrap" onclick="pickFile(event)">📁 영상 선택</button>
    </div>
    <div class="hint">버튼을 누르면 파일 탐색기가 열립니다. (폴더 경로만 넣으면 그 안의 최신 영상을 씁니다)</div>
    <label>상단 제목(훅) <span class="hint">— 줄바꿈 Enter · 숫자는 자동 강조 · <b>| 단어</b> 강조 · 여러 색 <b>[노랑]..[/] [빨강]..[/]</b></span></label>
    <textarea id="editHook" style="min-height:56px" oninput="renderHookPreview()" placeholder="예) [노랑]사진만 넣으면[/] 홍보글이 [초록]뚝딱![/]"></textarea>
    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px" id="hookStudio">
      <span class="hint">단어에 <b>커서만 두고</b>(또는 드래그) 색을 누르세요 · 같은 색 다시 누르면 해제 →</span>
      <span id="hookColorChips"></span>
      <button class="ghost" style="padding:4px 8px" onclick="clearHookMarkup(event)">지우기</button>
      <span class="hint" style="margin-left:6px">· 크기</span>
      <select id="hookSizeSel" style="width:auto;padding:4px 8px" onchange="renderHookPreview()">
        <option value="0.85">작게</option>
        <option value="1" selected>기본</option>
        <option value="1.2">크게</option>
        <option value="1.4">아주 크게</option>
      </select>
    </div>
    <div id="hookPreview" style="margin-top:6px;border-radius:10px;background:#14161c;border:1px solid #2c3350;padding:18px 10px;text-align:center;display:none"></div>
    <div style="display:flex;gap:6px;margin-top:6px">
      <input type="text" id="editHookTopic" style="flex:1" placeholder="영상 주제 키워드 (예: 블로그 자동화)">
      <button class="ghost" style="white-space:nowrap" onclick="suggestHooks(event,'editHookTopic','editHook')">✨ 제목 추천</button>
    </div>
    <div id="editHookCands" class="hookcands"></div>
    <div class="row">
      <div>
        <label>출력 형태</label>
        <div class="toggle">
          <label><input type="radio" name="editLayout" value="shorts" checked><span>쇼츠 (세로 9:16)</span></label>
          <label><input type="radio" name="editLayout" value="keep"><span>원본 비율 유지</span></label>
        </div>
      </div>
      <div>
        <label>음성 인식</label>
        <select id="sttSel"></select>
        <div class="hint" id="sttHint"></div>
        <div id="whisperModelRow" class="hidden" style="margin-top:6px">
          <label style="margin-top:0">정확도(Whisper 모델)</label>
          <select id="whisperModelSel">
            <option value="tiny">tiny — 가장 빠름·정확도 낮음</option>
            <option value="base">base — 빠름</option>
            <option value="small" selected>small — 기본(권장)</option>
            <option value="medium">medium — 느림·정확도↑</option>
            <option value="large-v3">large-v3 — 가장 느림·최고 정확도</option>
          </select>
          <div class="hint">클수록 정확하지만 느리고, 첫 사용 시 모델 다운로드가 큽니다.</div>
        </div>
      </div>
    </div>
    <div style="margin-top:12px;padding:10px 12px;border:1px dashed #3a4157;border-radius:10px">
      <label style="margin-top:0">📸 사진으로 영상 만들기 <span class="hint">(선택 — 영상 대신 사진들로)</span></label>
      <div class="row">
        <div style="flex:2">
          <input type="text" id="photoPath" placeholder="사진 폴더 경로 (안의 사진 전부, 이름순) 또는 파일 경로 여러 개(줄바꿈/세미콜론)">
        </div>
        <div>
          <label class="hint" style="margin:0 0 4px">전체 길이(초)</label>
          <input type="number" id="photoSec" value="15" min="3" max="180" style="width:80px;padding:6px">
        </div>
      </div>
      <div class="hint">예) 사진 5장 + 15초 → 한 장당 3초씩. 가로 사진도 블러 배경으로 세로 쇼츠에 자연스럽게. 여기에 AI 내레이션(또는 자막만)·배경음악·상단 제목을 그대로 얹을 수 있어요. 사진을 넣으면 위 영상 경로는 무시됩니다.</div>
    </div>
    <div style="margin-top:12px;padding:10px 12px;border:1px dashed #3a4157;border-radius:10px">
      <label style="margin-top:0">🎙️ AI 내레이션 추가 <span class="hint">(선택 — 말 없는 영상에 AI 대본+목소리+자막)</span></label>
      <input type="text" id="narrTopic" oninput="onNarrTopicInput()" placeholder="영상 주제/내용 입력 (예: 동네 라멘 맛집 소개) — 비우면 사용 안 함">
      <div class="row" style="margin-top:8px">
        <div>
          <label>목소리(보이스)</label>
          <select id="narrVoiceSel"></select>
        </div>
        <div>
          <label>말투 스타일</label>
          <select id="narrStyleSel"></select>
        </div>
        <div style="display:flex;align-items:flex-end">
          <button class="ghost" style="margin-bottom:1px" onclick="previewNarrVoice(event)">🔊 미리듣기</button>
        </div>
      </div>
      <div class="chk" style="margin-top:6px">
        <input type="checkbox" id="narrSubsOnly" onchange="onNarrTopicInput()">
        <span>🔇 목소리는 빼고 <b>자막만</b> 넣기 (AI가 쓴 대본을 하단 자막으로만)</span>
      </div>
      <div class="hint">넣으면 AI가 대본을 쓰고 목소리(제미나이 키 권장, 없으면 내장 음성)를 입혀요. 보이스·말투는 제미나이 키가 있을 때 적용(내장 음성은 목소리 고정). 대본은 검토 화면에서 수정 가능.</div>
      <details style="margin-top:8px">
        <summary class="hint" style="cursor:pointer">🎤 내 목소리 등록 — 녹음 파일로 내 목소리를 만들어 내레이션에 사용 <b id="myVoiceState"></b></summary>
        <div style="margin-top:8px;padding:8px 10px;border:1px solid #2c3350;border-radius:8px">
          <b style="font-size:13px">방법 A — 무료·내 PC (GPT-SoVITS)</b>
          <span class="hint">프로그램 설치 후 켜두면 무제한 무료. 설치법은 카페가이드 Q12</span>
          <div class="row" style="margin-top:6px">
            <div>
              <label>참조 녹음 (5~10초, 깨끗하게)</label>
              <input type="text" id="sovitsRef" placeholder="예) C:\\Users\\me\\참조녹음.wav">
            </div>
            <div>
              <label>그 녹음에서 말한 문장</label>
              <input type="text" id="sovitsRefText" placeholder="예) 안녕하세요 곰대리입니다 오늘도 좋은 하루 보내세요">
            </div>
            <div style="display:flex;align-items:flex-end">
              <button class="ghost" style="margin-bottom:1px" onclick="saveSovits(event)">저장</button>
            </div>
          </div>
          <div class="hint">GPT-SoVITS 통합패키지의 API 서버(api_v2, 127.0.0.1:9880)를 켜두면 학습 없이(zero-shot) 바로 내 목소리가 나와요. 더 똑같이 만들고 싶으면 GPT-SoVITS에서 한 번만 학습하면 됩니다.</div>
        </div>
        <div style="margin-top:8px;padding:8px 10px;border:1px solid #2c3350;border-radius:8px">
        <b style="font-size:13px">방법 B — 유료·간편 (ElevenLabs, 월 $5)</b>
        <div class="row" style="margin-top:8px">
          <div>
            <label>녹음 파일 (1~3분 낭독, mp3/wav/m4a)</label>
            <input type="text" id="cloneFile" placeholder="예) C:\\Users\\me\\내녹음.mp3">
          </div>
          <div>
            <label>ElevenLabs API 키</label>
            <input type="password" id="elevenKey" placeholder="elevenlabs.io 발급 키">
          </div>
          <div style="display:flex;align-items:flex-end">
            <button class="ghost" style="margin-bottom:1px" onclick="cloneVoice(event)">등록</button>
          </div>
        </div>
        <div class="hint">조용한 곳에서 또박또박 1~3분 읽은 녹음이면 충분해요. 한 번 등록하면 저장됩니다. ⚠ 클로닝은 ElevenLabs <b>유료 구독(Starter, 월 $5)</b>부터 지원.</div>
        </div>
        <div class="hint" style="margin-top:6px">등록하면 위 보이스 목록에 「🎤 내 목소리」가 생겨요. ⚠ 어떤 방식이든 꼭 <b>본인 목소리</b>만 등록하세요 (타인 목소리 무단 클로닝 금지).</div>
      </details>
    </div>
    <div style="margin-top:12px;padding:10px 12px;border:1px dashed #3a4157;border-radius:10px">
      <label style="margin-top:0">📝 대본 직접 입력 <span class="hint">(선택 — 이미 대본이 있을 때)</span></label>
      <textarea id="editScript" oninput="onScriptInput()" style="min-height:64px"
        placeholder="대본이 있으면 여기 붙여넣기 (한 줄 = 자막 한 줄)&#10;예)&#10;오늘은 라멘 맛집을 소개합니다&#10;가격은 육천구백원이에요&#10;&#10;비우면 영상 소리에서 자동으로 자막을 인식합니다"></textarea>
      <div class="hint" id="scriptHint">붙여넣으면 <b>음성 인식을 건너뛰고</b> 이 대본을 영상 타이밍에 맞춰 자막으로 넣어요 (오인식·비용 없음). 내레이션 없는 영상에도 쓸 수 있어요.</div>
    </div>
    <div class="chk" style="margin-top:10px">
      <input type="checkbox" id="autoSubChk" checked onchange="toggleAutoSub()">
      <span>자동 자막 만들기 (말한 내용을 자막으로) — <b>내레이션 없는 영상은 체크 해제</b></span>
    </div>
    <div class="chk">
      <input type="checkbox" id="cutSilenceChk" checked>
      <span>무음(빈) 구간 자동 컷 — 끄면 원본 길이 그대로</span>
    </div>
    <div class="chk" style="gap:8px">
      <span>🔇 잡음 제거</span>
      <select id="denoiseSel" style="width:auto;padding:6px 8px">
        <option value="">끔</option>
        <option value="low">약하게</option>
        <option value="mid">중간 (권장)</option>
        <option value="high">강하게</option>
      </select>
      <span class="hint">배경 잡음·히스·웅웅거림 줄이기 (목소리는 살림)</span>
    </div>
    <div class="chk" style="gap:8px">
      <span>🔈 원본 소리</span>
      <select id="origAudioSel" style="width:auto;padding:6px 8px" onchange="window._origTouched=true">
        <option value="keep">그대로</option>
        <option value="low">작게 (배경으로)</option>
        <option value="mute">무음 (소리 제거)</option>
      </select>
      <span class="hint">영상에 있는 말소리·소음을 뺄 때 '무음' — AI 내레이션을 넣으면 자동으로 무음이 돼요</span>
    </div>
    <div class="chk" style="gap:8px">
      <span>🎵 배경음악</span>
      <select id="bgmEditSel" style="width:auto;max-width:220px;padding:6px 8px">
        <option value="">없음</option>
      </select>
      <select id="bgmVolSel" style="width:auto;padding:6px 8px">
        <option value="-20">은은하게</option>
        <option value="-14" selected>중간</option>
        <option value="-9">크게</option>
      </select>
      <button class="ghost" style="padding:6px 10px" onclick="previewBgm(event,'bgmEditSel','bgmVolSel')">▶ 미리듣기</button>
      <span class="hint">영상 길이만큼 반복+페이드. <b>windows\6_무료음원_받기.bat</b>로 유명 무료 BGM 14곡 자동 채우기</span>
    </div>
    <div class="chk" style="gap:8px">
      <span>🏷️ 워터마크</span>
      <input type="text" id="wmPath" style="flex:1;min-width:180px;padding:6px 8px" placeholder="로고 이미지 경로 (투명 PNG 권장) — 비우면 없음">
      <select id="wmPos" style="width:auto;padding:6px 8px">
        <option value="tr">우상단</option>
        <option value="tl">좌상단</option>
        <option value="br">우하단</option>
        <option value="bl">좌하단</option>
      </select>
      <select id="wmScale" style="width:auto;padding:6px 8px">
        <option value="0.10">작게</option>
        <option value="0.14" selected>중간</option>
        <option value="0.20">크게</option>
      </select>
      <span class="hint">한 번 넣으면 기억돼요. 쇼츠 UI 안전영역을 피해 배치됩니다</span>
    </div>
    <div class="chk" style="gap:8px">
      <input type="checkbox" id="autoEditChk">
      <span>🤖 완전 자동 — 검토 없이 바로 완성</span>
      <span class="hint">목표</span>
      <input type="number" id="autoTargetSec" value="30" min="0" max="90" style="width:64px;padding:6px">
      <span class="hint">초 (0=전체 유지 · 30=핵심만 모아 30초 쇼츠. 키 있으면 AI가 다듬고 골라요)</span>
      <span class="hint">· 재생 속도</span>
      <select id="editSpeedSel" style="width:auto;padding:6px 8px">
        <option value="1">1배</option>
        <option value="1.25">1.25배</option>
        <option value="1.5">1.5배</option>
        <option value="2">2배</option>
      </select>
    </div>
    <div id="editKeyRow" class="hidden">
      <label>Gemini API 키 <span class="hint">(<a href="https://aistudio.google.com/apikey" target="_blank" style="color:#7a9bff">무료 발급</a>)</span></label>
      <input type="password" id="editGeminiKey" placeholder="AIza...">
    </div>
    <div class="hint" style="margin-top:8px">말 안 하는 빈 구간을 잘라내고, 말한 내용을 자동으로 자막으로 붙입니다. 가로 영상은 세로 쇼츠로 자동 배치돼요.</div>
    <div style="display:flex;gap:8px">
      <button id="editBtn" style="flex:1" onclick="startEdit()">✂️ 편집 시작</button>
      <button class="ghost" style="white-space:nowrap" onclick="resetEditForm(event)" title="편집 폼의 모든 입력을 기본값으로 되돌립니다">↺ 초기화</button>
    </div>
  </div>

  <div class="card" id="formCard">
    <label>쇼츠 주제</label>
    <input type="text" id="topic" placeholder="예) 하루 10분 정리 습관" value="하루 10분 정리 습관">
    <label>상단 제목(훅) <span class="hint">— 비우면 대본 제목이 자동으로 위에 크게 표시됩니다</span></label>
    <textarea id="genHook" style="min-height:52px" placeholder="비워두면 AI가 만든 제목을 사용 / 직접 쓰려면 여기에 (줄바꿈 Enter)"></textarea>
    <button class="ghost" style="margin-top:6px" onclick="suggestHooks(event,'topic','genHook')">✨ AI 제목 추천받기</button>
    <div id="genHookCands" class="hookcands"></div>

    <div class="row">
      <div>
        <label>모드</label>
        <div class="toggle">
          <label><input type="radio" name="mode" value="auto" checked><span>자동 (한 번에 완성)</span></label>
          <label><input type="radio" name="mode" value="review"><span>검토 (대본 확인 후)</span></label>
        </div>
      </div>
      <div>
        <label>목소리</label>
        <div class="toggle">
          <label id="provWinLabel" class="hidden"><input type="radio" name="prov" value="windows" id="provWin"><span>내장 음성 (무료)</span></label>
          <label id="provMineLabel" class="hidden"><input type="radio" name="prov" value="elevenlabs" id="provMine"><span>🎤 내 목소리</span></label>
          <label id="provSovitsLabel" class="hidden"><input type="radio" name="prov" value="sovits" id="provSovits"><span>🎤 내 목소리 (무료·내 PC)</span></label>
          <label><input type="radio" name="prov" value="gemini"><span>Gemini (실전 품질)</span></label>
          <label><input type="radio" name="prov" value="stub" checked><span>테스트 톤</span></label>
        </div>
        <div class="hint">내장 음성 = Windows 한국어 음성(키·인터넷 불필요) · Gemini = 성우급 + <b>진짜 대본 생성</b> · 테스트 톤 = "삐-" 소리(기계 점검용)</div>
      </div>
    </div>

    <div id="keyRow" class="hidden">
      <label>Gemini API 키 <span class="hint">(<a href="https://aistudio.google.com/apikey" target="_blank" style="color:#7a9bff">무료 발급</a>)</span></label>
      <input type="password" id="geminiKey" placeholder="AIza...">
      <div class="chk" style="margin-top:8px">
        <input type="checkbox" id="saveKeyChk" checked>
        <span>이 PC에 저장 (다음부터 입력 생략 — 파일로 저장되니 공용 PC에서는 해제)</span>
      </div>
    </div>
    <div id="keySaved" class="hidden hint" style="margin-top:8px">
      🔑 저장된 Gemini 키 사용 중 — <a href="#" onclick="clearKeys(event)" style="color:#ff9aa6">키 삭제</a>
    </div>

    <div id="geminiOpts" class="hidden">
      <div class="row">
        <div>
          <label>보이스</label>
          <select id="voiceSel"></select>
        </div>
        <div>
          <label>말투 스타일</label>
          <select id="styleSel"></select>
        </div>
        <div style="display:flex;align-items:flex-end">
          <button class="ghost" style="margin-bottom:1px" onclick="previewVoice(event)">🔊 미리듣기</button>
        </div>
      </div>
    </div>

    <div class="row">
      <div>
        <label>배경음악 (BGM)</label>
        <div style="display:flex;gap:6px">
          <select id="bgmSel" style="flex:1"><option value="">없음</option></select>
          <button class="ghost" style="white-space:nowrap" onclick="previewBgm(event,'bgmSel',null)">▶ 미리듣기</button>
        </div>
        <div class="hint">windows\6_무료음원_받기.bat로 유명 무료 BGM 자동 채우기. 저작권 확인된 음원만 사용하세요.</div>
      </div>
    </div>

    <div class="chk">
      <input type="checkbox" id="draftChk">
      <span>캡컷 draft도 생성 (출력 A — 캡컷 설치 PC)</span>
    </div>
    <div id="draftRow" class="hidden">
      <label>캡컷 Drafts 폴더</label>
      <input type="text" id="draftsDir" placeholder="자동 감지 실패 시 직접 입력">
    </div>

    <div style="display:flex;gap:8px">
      <button id="goBtn" style="flex:1" onclick="generate()">생성 시작</button>
      <button class="ghost" style="white-space:nowrap" onclick="resetGenForm(event)" title="생성 폼의 입력을 기본값으로 되돌립니다">↺ 초기화</button>
    </div>
  </div>

  <div class="card hidden" id="statusCard">
    <div id="statusTitle" style="font-weight:700"></div>
    <div class="bar"><div id="barFill"></div></div>
    <div class="stage" id="stageText"></div>
    <div class="stage" id="noteText" style="color:#e8b34b"></div>

    <div id="reviewBox" class="hidden">
      <label>제목</label>
      <input type="text" id="rvTitle">
      <label>대본 (한 줄 = 자막 한 줄 = TTS 한 문장 · 강조 단어는 <code>문장 | 단어</code>)</label>
      <textarea id="rvSentences"></textarea>
      <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
        <button class="ghost" onclick="pronounceLines(event)">한글 발음으로 변환 (숫자·영어)</button>
        <span class="hint">예: 2026년→이천이십육년, AI→에이아이 — TTS 오독 방지</span>
      </div>
      <button onclick="confirmScript()">이 대본으로 계속</button>
    </div>

    <div id="subEditBox" class="hidden">
      <div style="font-weight:700;margin-bottom:4px">✏️ 자막 검토·수정</div>
      <div class="hint">틀린 자막을 고치세요. 자막 칸을 누르면 <b>영상이 자동으로 멈춥니다</b>. <b>스페이스바</b>=재생/정지, 각 줄 <b>▶</b>=그 지점부터 듣기, <b>✂</b>=줄 나누기. (자막 없이 완성하려면 전부 비우고 완성)</div>
      <div class="hint">💛 강조(노란 글씨): 문장 끝에 <b>| 단어</b> · 🌈 여러 색: <b>[노랑]...[/] [빨강]...[/] [초록]...[/]</b> — 예: <code>[노랑]월급 3배[/] 밥값은 [빨강]절반?![/]</code></div>
      <div class="playbar">
        <video id="cutPlayer" controls playsinline></video>
        <div class="playrow">
          <button class="ghost pbtn" id="playToggle" onclick="togglePlay(event)">▶ 재생</button>
          <span class="hint" id="playClock" style="min-width:64px">0:00</span>
          <span class="hint">배속</span>
          <select id="playRate" onchange="setPlayRate()">
            <option value="0.75">0.75×</option>
            <option value="1" selected>1×</option>
            <option value="1.25">1.25×</option>
            <option value="1.5">1.5×</option>
            <option value="2">2×</option>
          </select>
          <span class="hint">← 스페이스바로 정지</span>
        </div>
      </div>
      <div class="shortsbar">
        <b style="font-size:13px">✂️ 쇼츠로 줄이기</b>
        <span class="hint">넣을 핵심 구간만 <b>체크 ☑</b> (나머지는 잘려요)</span>
        <span class="hint" id="keepInfo" style="color:#7a9bff;font-weight:700">전체</span>
        <button class="ghost" onclick="selectAll(true,event)">전체 선택</button>
        <button class="ghost" onclick="selectAll(false,event)">전체 해제</button>
        <span style="flex:1;min-width:6px"></span>
        <span class="hint">목표</span>
        <input type="number" id="hlTarget" value="30" min="5" max="90" style="width:54px;padding:6px">
        <span class="hint">초</span>
        <button class="ghost" onclick="aiHighlights(event)" title="AI가 핵심 구간을 골라 체크해줍니다">✨ AI 핵심 추천</button>
        <button class="ghost" onclick="renderSplit(event)" title="전체를 목표 길이 단위로 잘라 쇼츠 여러 개로 저장">🎬 여러 쇼츠로 나누기</button>
      </div>
      <div class="hint" id="hlReason" style="margin-top:4px"></div>
      <div id="subList" class="subList-scroll" style="margin-top:10px"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
        <button class="ghost" onclick="analyzeAI(event)" title="장면 캡처+자막을 AI가 보고 제목·훅·대본을 추천 (제미나이 키 권장)">🧠 AI 영상 분석 (제목·대본)</button>
        <button class="ghost" onclick="refineSubs(event)" title="발음 오인식을 문맥에 맞게 자연스럽게 자동 교정 (제미나이 키 필요)">🪄 AI로 대본 다듬기</button>
        <button class="ghost" onclick="addSubRow(event)">+ 자막 줄 추가</button>
        <button class="ghost" onclick="pronounceSubs(event)">숫자·영어 → 한글</button>
        <button class="ghost" onclick="toggleBulk(event)">📋 대본 일괄 붙여넣기</button>
        <button class="ghost" onclick="downloadScript(event,'txt')">📥 대본 저장(.txt)</button>
        <button class="ghost" onclick="downloadScript(event,'srt')">📥 자막 저장(.srt)</button>
      </div>
      <div id="aiAnalyzeBox" class="hidden" style="margin-top:8px;padding:10px 12px;border:1px solid #2c3350;border-radius:10px">
        <div class="hint" id="aiSummary" style="margin-bottom:6px"></div>
        <b style="font-size:13px">🪝 상단 훅 추천 (클릭하면 채워져요)</b>
        <div id="aiHooks" class="hookcands"></div>
        <b style="font-size:13px">📌 유튜브 제목 추천</b>
        <div id="aiTitles" class="hint" style="white-space:pre-line;margin:4px 0 8px"></div>
        <b style="font-size:13px">📝 추천 내레이션 대본</b>
        <textarea id="aiScript" readonly style="min-height:84px;margin-top:4px"></textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
          <button class="ghost" onclick="applyAiScript(event)">이 대본으로 자막 텍스트 교체</button>
          <button class="ghost" onclick="copyAiScript(event)">📋 복사</button>
          <span class="hint" id="aiTags"></span>
        </div>
      </div>
      <div id="bulkBox" class="hidden" style="margin-top:8px">
        <textarea id="bulkText" style="min-height:90px" placeholder="대본을 한 줄에 한 자막씩 붙여넣고 아래 버튼을 누르면, 위 자막들의 텍스트가 순서대로 교체됩니다 (타이밍은 유지). 줄이 더 많으면 뒤에 추가돼요."></textarea>
        <button class="ghost" onclick="applyBulk(event)">이 대본으로 자막 텍스트 교체</button>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px">
        <span class="hint">⏩ 저장 속도 <span style="color:#8b93a7">(완성 영상에 적용 · 자막도 같이 빨라짐)</span></span>
        <select id="outSpeed" style="width:auto;padding:6px 8px">
          <option value="1">1배 (원본)</option>
          <option value="1.25">1.25배</option>
          <option value="1.5">1.5배</option>
          <option value="2">2배</option>
        </select>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px">
        <span class="hint">🎞️ 화질</span>
        <select id="outQuality" style="width:auto;padding:6px 8px" onchange="qualityHint()">
          <option value="draft">빠름 (초안·가장 빠름)</option>
          <option value="standard" selected>표준 (1080p)</option>
          <option value="high">고화질 (1080p · 선명·저압축)</option>
          <option value="ultra">초고화질 (4K 업스케일 · 유튜브 노출↑ · 느림)</option>
        </select>
        <span class="hint" id="qualityHint"></span>
      </div>
      <button id="renderBtn" onclick="renderEdited()">✅ 이 자막으로 완성</button>
    </div>

    <div id="doneBox" class="hidden">
      <div class="stage" id="providerBadge"></div>
      <video id="player" controls playsinline></video>
      <div class="stage" id="outPaths"></div>
      <button class="ghost" style="margin-top:10px" onclick="openFolder(event)">📂 폴더 열기</button>
      <button class="ghost" style="margin-top:10px" onclick="toggleThumb(event)">🖼️ 유튜브 썸네일 만들기 (16:9)</button>
      <div id="thumbBox" class="hidden" style="margin-top:10px;padding:10px;border:1px dashed #3a4157;border-radius:10px">
        <label style="margin-top:0">썸네일 제목 <span class="hint">— 짧고 강하게. 줄바꿈 Enter. 강조는 <b>| 단어</b></span></label>
        <textarea id="thumbTitle" style="min-height:52px" placeholder="예) 사진만 넣으면&#10;홍보글이 뚝딱! | 뚝딱!"></textarea>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
          <input type="text" id="thumbTopic" style="flex:1;min-width:160px" placeholder="주제/키워드 (예: 블로그 홍보글 자동화)">
          <button class="ghost" style="white-space:nowrap" onclick="suggestThumb(event)">✨ AI 카피 추천</button>
        </div>
        <div id="thumbCands" class="hookcands"></div>
        <div class="row" style="margin-top:6px">
          <div>
            <label style="margin-top:0">우상단 배지 <span class="hint">(선택 · 초록 라벨)</span></label>
            <input type="text" id="thumbBadge" placeholder="예) ✅ 자동 발행  /  직접 쓴 글 아닙니다">
          </div>
          <div>
            <label style="margin-top:0">배경 사진 <span class="hint">(선택 · 비우면 완성 영상 장면)</span></label>
            <input type="text" id="thumbBg" placeholder="내 사진 경로 붙여넣기 (png/jpg)">
          </div>
        </div>
        <button onclick="makeThumb(event)">이 제목으로 썸네일 만들기</button>
        <div id="thumbResult" class="hidden" style="margin-top:10px">
          <img id="thumbImg" style="width:100%;border-radius:10px;border:1px solid #262b3a" alt="썸네일">
          <div class="hint" id="thumbPath" style="margin-top:6px"></div>
        </div>
      </div>
    </div>
    <div class="err hidden" id="errBox"></div>
    <details class="hidden" id="rawErr" style="margin-top:8px">
      <summary class="hint" style="cursor:pointer">자세히 (원본 오류)</summary>
      <pre class="err" id="rawErrText" style="overflow-x:auto"></pre>
    </details>
    <button class="ghost" style="margin-top:14px" onclick="resetForm()">+ 새 작업</button>
  </div>

  <div class="card">
    <div style="font-weight:700">히스토리</div>
    <table id="histTable"><thead>
      <tr><th>시각</th><th>제목</th><th>목소리</th><th>상태</th><th></th></tr>
    </thead><tbody></tbody></table>
  </div>

  <div class="card hidden" id="settingsCard">
    <div style="font-weight:700">⚙ 설정 <span class="hint">(저장하면 다음 작업부터 적용)</span></div>
    <div class="row">
      <div><label>자막 크기(px)</label><input type="number" id="setFontSize" min="40" max="120"></div>
      <div><label>외곽선 두께</label><input type="number" id="setOutline" min="0" max="8"></div>
      <div><label>자막 세로 여백</label><input type="number" id="setMarginV" min="100" max="800" step="10"></div>
      <div><label>한 줄 최대 글자수 <span class="hint">(넘으면 2줄, 0=끔)</span></label><input type="number" id="setWrapChars" min="0" max="40"></div>
    </div>
    <div class="row">
      <div><label>배경 모션</label>
        <select id="setMotion">
          <option value="zoom_in">줌인 (기본)</option>
          <option value="zoom_out">줌아웃</option>
          <option value="off">없음</option>
        </select></div>
      <div><label>줌 정도 (0.02~0.2)</label><input type="number" id="setMotionAmt" min="0.02" max="0.2" step="0.01"></div>
      <div><label>강조 색</label><input type="color" id="setHlColor" style="height:40px;padding:4px"></div>
    </div>
    <div class="row">
      <div><label>BGM 볼륨(dB)</label><input type="number" id="setBgmVol" min="-40" max="0"></div>
      <div><label>문장 간격(ms)</label><input type="number" id="setGap" min="0" max="1000" step="10"></div>
      <div><label>분당 TTS 호출 한도</label><input type="number" id="setRpm" min="1" max="60"></div>
    </div>
    <div class="chk"><input type="checkbox" id="setFade"><span>자막 등장 페이드</span></div>
    <div class="chk"><input type="checkbox" id="setHookBand"><span>상단 제목 배경 띠 (유튜브 썸네일 스타일 · 글자 뒤 어두운 띠)</span></div>
    <div class="chk"><input type="checkbox" id="setBand"><span>자막에도 배경 띠 (하단 자막 뒤에도 어두운 띠)</span></div>
    <div class="chk"><input type="checkbox" id="setDuck"><span>BGM 덕킹 (음성 나올 때 자동 감쇠)</span></div>
    <div class="chk"><input type="checkbox" id="setAiImage"><span>AI 배경 이미지 생성 (실험적 · Gemini · 실패 시 기본 배경) </span></div>
    <div class="hint" style="margin:2px 0 0 26px">끄면 항상 되는 그라데이션 배경을 씁니다. 모델 가용성에 따라 실패할 수 있어요.</div>
    <button onclick="saveSettings()">설정 저장</button>
  </div>

  <details id="logPanel" style="margin-top:16px">
    <summary class="hint" style="cursor:pointer">🪵 작업 로그 — 오류가 나면 펼쳐서 <b>[📋 복사]</b> 후 붙여넣어 주세요 <button class="ghost" style="padding:2px 8px;margin-left:6px" onclick="copyLogs(event)">📋 복사</button></summary>
    <pre id="logBox" style="max-height:260px;overflow:auto;background:#0d0f14;border:1px solid #2c3350;border-radius:8px;padding:10px;font-size:12px;line-height:1.55;white-space:pre-wrap;margin-top:8px">(아직 로그 없음)</pre>
  </details>
  <div style="text-align:center;margin-top:12px">
    <button class="ghost" onclick="toggleSettings()">⚙ 설정</button>
    <button class="ghost" onclick="diagnostic(event)">🩺 진단 리포트 저장 (로그 포함)</button>
  </div>
</div>

<script>
let currentJob = null, timer = null;
const $ = id => document.getElementById(id);
const STAGE_KO = {script:'대본 생성', tts:'목소리 합성(TTS)', background:'배경 준비',
                  timeline:'타임라인 계산', render:'영상 렌더링', draft:'캡컷 draft 조립',
                  review:'대본 검토 대기', done:'완료',
                  analyze:'무음 구간 분석', cut:'무음 잘라내기', stt:'음성 인식(자막 만들기)'};

document.querySelectorAll('input[name=prov]').forEach(r => r.onchange = () => {
  const isGemini = pick('prov') === 'gemini';
  $('keyRow').classList.toggle('hidden', !isGemini || window._hasGeminiKey);
  $('geminiOpts').classList.toggle('hidden', !isGemini);
});
$('draftChk').onchange = () => $('draftRow').classList.toggle('hidden', !$('draftChk').checked);

function pick(name){ return document.querySelector(`input[name=${name}]:checked`).value; }

function switchAppMode(){
  const edit = pick('appmode') === 'edit';
  $('editCard').classList.toggle('hidden', !edit);
  $('formCard').classList.toggle('hidden', edit);
  // 진행/완료 상태 카드는 그 작업을 시작한 모드에서만 보이게 (모드 간 섞임 방지)
  const mismatch = currentJob && window._jobMode &&
    ((edit && window._jobMode !== 'edit') || (!edit && window._jobMode !== 'gen'));
  if(currentJob) $('statusCard').classList.toggle('hidden', !!mismatch);
  if(edit && !window._sttFilled) loadStt();
}

const STT_KO = {whisper:'내장 Whisper (무료·오프라인)', gemini:'Gemini (내 키)', openai:'OpenAI (내 키)'};
async function loadStt(){
  const av = (await (await fetch('/api/state')).json()).stt_available || {};
  const sel = $('sttSel'); sel.innerHTML = '';
  // 사용 가능한 것 우선, 없으면 안내
  const order = ['whisper','gemini','openai'];
  let any = false;
  for(const k of order){ if(av[k]){ sel.add(new Option(STT_KO[k], k)); any = true; } }
  if(!any){
    sel.add(new Option('Gemini (키 입력 필요)', 'gemini'));
  }
  window._sttFilled = true;
  updateSttHint();
  sel.onchange = updateSttHint;
}
function updateSttHint(){
  const v = $('sttSel').value;
  $('editKeyRow').classList.toggle('hidden', v !== 'gemini' || window._hasGeminiKey);
  if($('whisperModelRow')) $('whisperModelRow').classList.toggle('hidden', v !== 'whisper');
  $('sttHint').textContent = v === 'whisper'
    ? '최초 1회 모델 다운로드(수십 MB). 이후 무료·오프라인.'
    : v === 'gemini' ? '내 Gemini 키 사용. 구간마다 호출돼 조금 걸릴 수 있어요.'
    : '내 OpenAI 키 사용.';
}

async function pickFile(ev){
  ev.preventDefault();
  const btn = ev.target;
  btn.disabled = true; btn.textContent = '창 여는 중…';
  try{
    const data = await (await fetch('/api/pick_file', {method:'POST', body:'{}'})).json();
    if(data.error){ alert(data.error); }
    else if(data.path){ $('editVideo').value = data.path; }
    // 취소면 그대로 둠
  } catch(e){ alert('파일 선택 창을 열 수 없습니다: ' + e); }
  finally { btn.disabled = false; btn.textContent = '📁 영상 선택'; }
}

function toggleAutoSub(){
  // 자막 끄면 음성인식 관련 항목 숨김
  const on = $('autoSubChk').checked;
  $('sttSel').closest('div').style.opacity = on ? '1' : '0.4';
  $('sttSel').disabled = !on;
}
function onScriptInput(){
  // 대본을 붙여넣으면 음성 인식은 생략됨을 표시
  const has = ($('editScript').value || '').trim().length > 0;
  $('sttSel').closest('div').style.opacity = has ? '0.4' : ($('autoSubChk').checked ? '1' : '0.4');
  $('sttSel').disabled = has || !$('autoSubChk').checked;
  $('scriptHint').innerHTML = has
    ? '✅ <b>이 대본을 사용</b>합니다 — 음성 인식은 건너뜁니다. (다음 화면에서 타이밍·줄을 다듬을 수 있어요)'
    : '붙여넣으면 <b>음성 인식을 건너뛰고</b> 이 대본을 영상 타이밍에 맞춰 자막으로 넣어요 (오인식·비용 없음). 내레이션 없는 영상에도 쓸 수 있어요.';
}

async function startEdit(){
  const video = $('editVideo').value.trim();
  const photos = ($('photoPath')||{}).value||'';
  if(!video && !photos.trim()){ alert('영상 파일(또는 📸 사진 폴더) 경로를 입력하세요'); return; }
  const nv = ($('narrVoiceSel')||{}).value||'';
  let editKey = $('editGeminiKey').value;
  // 내레이션 보이스는 제미나이 키가 있어야 적용 — 없으면 여기서 물어봐 저장
  const subsOnly = ($('narrSubsOnly')||{}).checked;
  if((($('narrTopic')||{}).value||'').trim() && !window._hasGeminiKey && !editKey){
    editKey = ensureGeminiKey();   // 대본 품질(+목소리)에 필요
    if(!editKey && !subsOnly && nv && nv !== '__mine__' && nv !== '__sovits__'
       && !confirm('제미나이 키가 없으면 보이스 선택 없이 내장 음성으로 만들어져요.\\n그래도 진행할까요?')) return;
  }
  const body = {
    video_path: video, layout: pick('editLayout'), hook: $('editHook').value,
    auto_subtitle: $('autoSubChk').checked, cut_silence: $('cutSilenceChk').checked,
    photo_path: ($('photoPath')||{}).value||'', photo_sec: +(($('photoSec')||{}).value)||15,
    hook_scale: +(($('hookSizeSel')||{}).value)||1,
    denoise: $('denoiseSel').value, narr_topic: ($('narrTopic')||{}).value||'',
    narr_subs_only: (($('narrSubsOnly')||{}).checked)||false,
    narr_voice: nv, narr_style: ($('narrStyleSel')||{}).value||'',
    orig_audio: $('origAudioSel').value,
    bgm: $('bgmEditSel').value, bgm_db: +$('bgmVolSel').value,
    wm_path: ($('wmPath')||{}).value||'', wm_pos: ($('wmPos')||{}).value||'tr',
    wm_scale: +(($('wmScale')||{}).value)||0.14,
    speed: +$('editSpeedSel').value || 1,
    auto_edit: $('autoEditChk').checked, auto_target_sec: +$('autoTargetSec').value||0,
    script: $('editScript').value,
    stt_provider: $('sttSel').value, whisper_model: ($('whisperModelSel')||{}).value || 'small',
    gemini_key: editKey, save_key: true,
  };
  const res = await fetch('/api/edit', {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'edit';
  window._subLoaded = false;
  $('editBtn').disabled = true;
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('subEditBox').classList.add('hidden');
  $('rawErr').classList.add('hidden'); $('noteText').textContent='';
  poll();
  timer = setInterval(poll, 900);
}

// ── 훅 제목 AI 추천 (v0.8) ──
async function suggestHooks(ev, topicId, targetId){
  ev.preventDefault();
  const ctx = ($(topicId).value || '').trim();
  if(!ctx){ alert('주제/키워드를 먼저 입력하세요'); return; }
  const btn = ev.target; btn.disabled = true; const old = btn.textContent; btn.textContent = '추천 중…';
  const cands = $(targetId + 'Cands'); cands.innerHTML = '';
  try {
    const key = ensureGeminiKey();
    const data = await (await fetch('/api/suggest_hooks', {method:'POST',
      body: JSON.stringify({context: ctx, gemini_key: key, save_key: true})})).json();
    if(data.error){ alert(data.error); return; }
    (data.hooks || []).forEach(h => {
      const b = document.createElement('button');
      b.textContent = h;
      b.onclick = (e) => { e.preventDefault(); $(targetId).value = h; cands.innerHTML=''; };
      cands.appendChild(b);
    });
    if(!(data.hooks||[]).length) cands.innerHTML = '<span class="hint">추천 결과가 없습니다. 키워드를 바꿔보세요.</span>';
  } finally { btn.disabled = false; btn.textContent = old; }
}

// ── 자막 검토·수정 (Phase 1) ──
function fmtTime(us){ const s=us/1e6; const m=Math.floor(s/60); return m+':'+(s%60).toFixed(1).padStart(4,'0'); }
function renderSubRows(){
  const box = $('subList'); box.innerHTML='';
  (window._subs||[]).forEach((sub, i) => {
    const row = document.createElement('div');
    const dropped = sub.keep===false;
    row.className='subrow subrowbtns'+(dropped?' dropped':''); row.id='subrow'+i;
    row.style.cssText='display:flex;gap:5px;align-items:flex-start;margin-bottom:6px;padding:3px;border-radius:8px';
    row.innerHTML =
      `<input type="checkbox" class="keepchk" ${dropped?'':'checked'} title="이 구간을 쇼츠에 넣기" onchange="window._subs[${i}].keep=this.checked; renderSubRows(); updateKeepInfo()">`+
      `<button class="ghost" title="이 줄부터 재생" onclick="seekCut(${sub.start_us})">▶</button>`+
      `<span class="hint" style="min-width:50px;padding-top:9px;cursor:pointer" title="이 지점 재생" onclick="seekCut(${sub.start_us})">${fmtTime(sub.start_us)}</span>`+
      `<input type="text" style="flex:1" value="${(sub.text||'').replace(/"/g,'&quot;')}" onfocus="pauseCut()" oninput="window._subs[${i}].text=this.value">`+
      `<button class="ghost" title="위 줄과 합치기" onclick="mergeSub(${i})" ${i===0?'disabled':''}>⬆</button>`+
      `<button class="ghost" title="이 줄을 둘로 나누기" onclick="splitSub(${i})">✂</button>`+
      `<button class="ghost" title="삭제" onclick="delSub(${i})">✕</button>`;
    box.appendChild(row);
  });
  updateKeepInfo();
}
// ── 쇼츠 핵심 추출: 고른 구간만 남기기 (v0.10) ──
function updateKeepInfo(){
  const info=$('keepInfo'); if(!info) return;
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  const kept=subs.filter(s=>s.keep!==false);
  const dur=kept.reduce((a,s)=>a+(s.end_us-s.start_us),0)/1e6;
  const btn=$('renderBtn');
  if(!subs.length){ info.textContent='자막 없음'; if(btn) btn.textContent='✅ 자막 없이 완성'; return; }
  if(kept.length===subs.length){
    info.textContent='전체 '+dur.toFixed(1)+'초';
    if(btn) btn.textContent='✅ 이 자막으로 완성 (전체)';
  } else {
    info.textContent='선택 '+kept.length+'/'+subs.length+'줄 · 약 '+dur.toFixed(1)+'초';
    if(btn) btn.textContent='✂️ 선택 구간만 쇼츠로 완성 (약 '+Math.round(dur)+'초)';
  }
}
function selectAll(on, ev){ if(ev)ev.preventDefault(); (window._subs||[]).forEach(s=>s.keep=on); renderSubRows(); }
async function aiHighlights(ev){
  if(ev)ev.preventDefault();
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  if(!subs.length){ alert('먼저 자막이 있어야 핵심을 고를 수 있어요'); return; }
  const target=parseInt($('hlTarget').value||'30');
  const key=ensureGeminiKey();  // 키 없으면 붙여넣기 창(취소하면 대략 추천으로 진행)
  const btn=ev.target; btn.disabled=true; const old=btn.textContent; btn.textContent='고르는 중…';
  try{
    const data=await (await fetch('/api/suggest_highlights',{method:'POST',
      body:JSON.stringify({subtitles:subs, target_sec:target, gemini_key:key, save_key:true})})).json();
    if(data.error){ alert(data.error); return; }
    const keep=new Set(data.keep||[]);
    let fi=0;
    (window._subs||[]).forEach(s=>{ if(!(s.text||'').trim()) return; s.keep=keep.has(fi); fi++; });
    renderSubRows();
    if(data.ai) window._hasGeminiKey=true;
    const r=$('hlReason'); if(r) r.textContent=(data.ai?'✨ AI 추천: ':'ℹ 대략 추천(제미나이 키 넣으면 문맥으로 골라요): ')+(data.reason||'');
  } finally { btn.disabled=false; btn.textContent=old; }
}
// 제미나이 키 확보 — 저장된 키 없으면 그 자리에서 붙여넣기 (PC에 저장 → 다음부턴 안 물음)
function ensureGeminiKey(){
  if(window._hasGeminiKey) return '';
  const k=(($('editGeminiKey')||{}).value||'') || (($('geminiKey')||{}).value||'');
  if(k.trim()) return k.trim();
  const v=prompt('제미나이(Gemini) API 키를 붙여넣어 주세요.\\n\\n· 무료 발급: aistudio.google.com/apikey\\n· 이 PC에 저장돼 다음부터는 묻지 않아요');
  return (v||'').trim();
}

// AI로 자막(대본) 다듬기 — 발음 오인식을 문맥 기반으로 자연스럽게 교정
// ── 훅 제목 스튜디오 (v0.31) — 색 칩·크기·실시간 미리보기 ──
const HOOK_COLORS = {'노랑':'#FFD400','빨강':'#FF3B30','초록':'#34C759','파랑':'#0A84FF',
  '주황':'#FF9500','분홍':'#FF375F','하늘':'#5AC8FA','민트':'#31E1C4','보라':'#BF5AF2','흰':'#FFFFFF'};

function initHookChips(){
  const box = $('hookColorChips');
  if(!box || box.childElementCount) return;
  for(const name in HOOK_COLORS){
    const b = document.createElement('button');
    b.className = 'ghost'; b.textContent = name;
    b.style.cssText = 'padding:3px 8px;border-color:' + HOOK_COLORS[name] + ';color:' + HOOK_COLORS[name] + (name==='흰' ? ';color:#fff' : '');
    b.onclick = (e) => wrapHookColor(e, name);
    box.appendChild(b);
  }
}

function wrapHookColor(ev, name){
  ev.preventDefault();
  const ta = $('editHook');
  let s = ta.selectionStart, e = ta.selectionEnd;
  const v = ta.value;
  if(!v.trim()){ alert('먼저 상단 제목을 입력하세요'); ta.focus(); return; }
  if(s === e){
    // 드래그 없이도: 커서가 놓인 단어를 자동 선택 (공백·줄바꿈 경계)
    const isSp = (ch) => ch === ' ' || ch === String.fromCharCode(10) || ch === String.fromCharCode(9);
    if(s > 0 && (s >= v.length || isSp(v[s]))) s--;           // 단어 끝에 커서
    while(s > 0 && !isSp(v[s-1]) && v[s-1] !== ']') s--;
    e = s;
    while(e < v.length && !isSp(v[e]) && v[e] !== '[') e++;
    if(s === e){ alert('색을 입힐 단어에 커서를 두거나 드래그로 선택하세요'); ta.focus(); return; }
  }
  let mid = v.slice(s, e);
  const tagRe = new RegExp('[[](?:[가-힣A-Za-z]+|/[가-힣A-Za-z]*)]', 'g');
  const already = new RegExp('^[[]' + name + ']').test(mid) || (
    v.slice(Math.max(0, s - name.length - 2), s) === '[' + name + ']');
  mid = mid.replace(tagRe, '');                               // 선택 안 기존 색 제거(중첩 방지)
  let before = v.slice(0, s), after = v.slice(e);
  // 선택 바로 앞뒤의 여닫는 태그도 정리 ([노랑]단어[/] 전체를 다시 칠할 때)
  before = before.replace(new RegExp('[[][가-힣A-Za-z]+]$'), '');
  after = after.replace(new RegExp('^[[]/[가-힣A-Za-z]*]'), '');
  // 같은 색을 다시 누르면 해제(토글), 다른 색이면 교체
  ta.value = already ? (before + mid + after)
                     : (before + '[' + name + ']' + mid + '[/]' + after);
  ta.focus(); renderHookPreview();
}

function clearHookMarkup(ev){
  ev.preventDefault();
  const re1 = new RegExp('[[](?:[가-힣A-Za-z]+|/[가-힣A-Za-z]*)]', 'g');
  $('editHook').value = $('editHook').value.replace(re1, '');
  renderHookPreview();
}

function hookLineHtml(line){
  const esc = (x) => x.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  let rest = line, out = '', hasMarkup = false;
  const tagRe = new RegExp('[[]([가-힣A-Za-z]+)]');
  while(rest){
    const m = rest.match(tagRe);
    const name = m ? m[1] : null;
    const col = name && (HOOK_COLORS[name] || HOOK_COLORS[name.replace(/색$/,'')]);
    if(!m || !col){
      if(m && m.index !== undefined){ out += esc(rest.slice(0, m.index + m[0].length)); rest = rest.slice(m.index + m[0].length); continue; }
      out += esc(rest); break;
    }
    hasMarkup = true;
    out += esc(rest.slice(0, m.index));
    rest = rest.slice(m.index + m[0].length);
    const close = rest.search(new RegExp('[[]/[가-힣A-Za-z]*]'));
    const next = rest.search(tagRe);
    let end = rest.length;
    if(close >= 0 && (next < 0 || close <= next)) end = close;
    else if(next >= 0) end = next;
    out += '<span style="color:' + col + '">' + esc(rest.slice(0, end)) + '</span>';
    rest = (close >= 0 && close === end) ? rest.slice(end).replace(new RegExp('^[[]/[가-힣A-Za-z]*]'), '') : rest.slice(end);
  }
  if(!hasMarkup){
    // 마크업 없으면: | 단어 강조 → 없으면 숫자 자동 강조 (렌더와 같은 규칙)
    const bar = line.lastIndexOf('|');
    if(bar > 0){
      const word = line.slice(bar + 1).trim();
      const body = line.slice(0, bar).trim();
      out = esc(body).split(esc(word)).join('<span style="color:#FFD400">' + esc(word) + '</span>');
    } else {
      out = esc(line).replace(new RegExp('([0-9]+[가-힣%]*)', 'g'), '<span style="color:#FFD400">$1</span>');
    }
  }
  return out;
}

function renderHookPreview(){
  initHookChips();
  const box = $('hookPreview');
  const raw = $('editHook').value.trim();
  if(!raw){ box.style.display = 'none'; return; }
  const scale = +(($('hookSizeSel')||{}).value) || 1;
  const px = Math.round(24 * scale);
  box.style.display = 'block';
  box.innerHTML = raw.split(new RegExp('[' + String.fromCharCode(10,13) + ']+')).map(l =>
    '<div style="display:inline-block;background:rgba(10,10,14,.72);padding:4px 12px;margin:2px 0;' +
    'font-weight:800;font-size:' + px + 'px;line-height:1.35;color:#fff;letter-spacing:-0.5px">' +
    hookLineHtml(l) + '</div>').join('<br>');
}

async function analyzeAI(ev){
  ev.preventDefault();
  const btn = ev.target; const oldTxt = btn.textContent;
  const key = ensureGeminiKey();
  btn.disabled = true; btn.textContent = '🧠 분석 중…(장면 캡처+AI)';
  try{
    const data = await (await fetch('/api/analyze_ai', {method:'POST', body: JSON.stringify({
      job_id: currentJob, gemini_key: key, save_key: true,
    })})).json();
    if(data.error){ alert(data.error); return; }
    if(key) window._hasGeminiKey = true;
    $('aiAnalyzeBox').classList.remove('hidden');
    $('aiSummary').textContent = (data.stub ? '⚠ 제미나이 키가 없어 예시 추천입니다 — 키를 넣으면 영상 내용 기반으로 추천돼요. ' : '') + (data.summary || '');
    const hooks = $('aiHooks'); hooks.innerHTML = '';
    (data.hooks || []).forEach(h => {
      const b = document.createElement('button');
      b.textContent = h;
      b.onclick = (e) => { e.preventDefault(); $('editHook').value = h; };
      hooks.appendChild(b);
    });
    $('aiTitles').textContent = (data.titles || []).map((t2,i) => (i+1) + '. ' + t2).join('\\n');
    $('aiScript').value = (data.script || []).join('\\n');
    $('aiTags').textContent = (data.hashtags || []).map(h => '#' + h.replace(/^#/, '')).join(' ');
  } finally { btn.disabled = false; btn.textContent = oldTxt; }
}

function applyAiScript(ev){
  ev.preventDefault();
  const lines = $('aiScript').value.split('\\n').map(s => s.trim()).filter(Boolean);
  if(!lines.length){ alert('추천 대본이 없습니다'); return; }
  if(!confirm('자막 텍스트를 추천 대본으로 교체할까요? (타이밍은 유지, 줄이 더 많으면 뒤에 추가)')) return;
  $('bulkText').value = lines.join('\\n');
  applyBulk(ev);
}

async function copyAiScript(ev){
  ev.preventDefault();
  try{ await navigator.clipboard.writeText($('aiScript').value); ev.target.textContent = '✓ 복사됨'; }
  catch(e){ alert('복사 실패 — 직접 드래그해서 복사하세요'); }
}

async function refineSubs(ev){
  if(ev)ev.preventDefault();
  const idxs=[]; (window._subs||[]).forEach((s,i)=>{ if((s.text||'').trim()) idxs.push(i); });
  if(!idxs.length){ alert('다듬을 자막이 없습니다'); return; }
  if(!confirm(idxs.length+'줄을 AI가 문맥에 맞게 자연스럽게 고칩니다. 계속할까요?\\n(제미나이 키가 필요해요)')) return;
  const key=ensureGeminiKey();
  if(!key && !window._hasGeminiKey){ alert('제미나이 키가 있어야 쓸 수 있어요. (무료 발급: aistudio.google.com/apikey)'); return; }
  const btn=ev.target; btn.disabled=true; const old=btn.textContent; btn.textContent='다듬는 중…';
  try{
    const subs=idxs.map(i=>({text:window._subs[i].text}));
    const data=await (await fetch('/api/refine_subtitles',{method:'POST',
      body:JSON.stringify({subtitles:subs, context:$('editHook').value||'', gemini_key:key, save_key:true})})).json();
    if(data.error){ alert(data.error); return; }
    window._hasGeminiKey=true;
    (data.lines||[]).forEach((t,k)=>{ if(idxs[k]!=null && t) window._subs[idxs[k]].text=t; });
    renderSubRows();
    const r=$('hlReason'); if(r) r.textContent='🪄 AI가 대본을 다듬었어요. 어색한 부분은 직접 더 고치세요.';
  } finally { btn.disabled=false; btn.textContent=old; }
}
function seekCut(us){ const p=$('cutPlayer'); p.currentTime=us/1e6; p.play(); }
function fmtClock(sec){ const m=Math.floor(sec/60), s=Math.floor(sec%60); return m+':'+String(s).padStart(2,'0'); }
function togglePlay(ev){ if(ev&&ev.preventDefault)ev.preventDefault(); const p=$('cutPlayer'); if(!p||!p.src) return; if(p.paused) p.play(); else p.pause(); }
function pauseCut(){ const p=$('cutPlayer'); if(p && !p.paused) p.pause(); }  // 자막 편집 시작하면 자동 정지
function setPlayRate(){ const p=$('cutPlayer'); if(p) p.playbackRate=parseFloat($('playRate').value||'1'); }
function qualityHint(){
  const v=($('outQuality')||{}).value, h=$('qualityHint'); if(!h) return;
  h.textContent = v==='ultra' ? '유튜브가 더 좋은 코덱으로 처리 → 체감 화질↑ (원본 화소는 안 늘어요)'
    : v==='high' ? '압축을 덜 해 더 또렷하게 (파일 조금 커짐)' : '';
}
function splitSub(i){
  const s=window._subs, cur=s[i]; if(!cur) return;
  const mid=Math.round((cur.start_us+cur.end_us)/2);
  const words=(cur.text||'').trim().split(/\\s+/).filter(Boolean);
  const half=Math.ceil(words.length/2);
  s.splice(i,1,
    {text:words.slice(0,half).join(' '), start_us:cur.start_us, end_us:mid},
    {text:words.slice(half).join(' '), start_us:mid, end_us:cur.end_us});
  renderSubRows();
}
function fmtSrtTime(us){
  const ms=Math.floor(us/1000), h=Math.floor(ms/3600000), m=Math.floor(ms%3600000/60000),
        sec=Math.floor(ms%60000/1000), mm=ms%1000;
  const p=(n,w)=>String(n).padStart(w,'0');
  return p(h,2)+':'+p(m,2)+':'+p(sec,2)+','+p(mm,3);
}
// 검토 중인 전체 대본을 파일로 다운로드 (수정한 내용 그대로)
function downloadScript(ev, kind){
  if(ev)ev.preventDefault();
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  if(!subs.length){ alert('저장할 대본이 없습니다'); return; }
  const clean=t=>t.replace(/\\[[가-힣A-Za-z]+\\]|\\[\\/[가-힣A-Za-z]*\\]/g,'').replace(/\\s*\\|[^|]*$/,'').trim();
  let content, name;
  if(kind==='srt'){
    content=subs.map((s,i)=>(i+1)+'\\n'+fmtSrtTime(s.start_us)+' --> '+fmtSrtTime(s.end_us)+'\\n'+clean(s.text)+'\\n').join('\\n');
    name='대본.srt';
  } else {
    content=subs.map(s=>clean(s.text)).join('\\n');
    name='대본.txt';
  }
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob(['\\ufeff'+content],{type:'text/plain;charset=utf-8'}));
  a.download=name; a.click(); URL.revokeObjectURL(a.href);
}
function toggleBulk(ev){ if(ev)ev.preventDefault(); $('bulkBox').classList.toggle('hidden'); }
function applyBulk(ev){
  if(ev)ev.preventDefault();
  const lines=($('bulkText').value||'').split('\\n').map(l=>l.trim()).filter(Boolean);
  if(!lines.length){ alert('붙여넣을 대본을 입력하세요'); return; }
  const s=window._subs;
  lines.forEach((t,i)=>{
    if(s[i]) s[i].text=t;
    else { const last=s.length?s[s.length-1].end_us:0; s.push({text:t, start_us:last, end_us:last+1800000}); }
  });
  renderSubRows(); $('bulkBox').classList.add('hidden');
}
// 재생 위치 따라 현재 말하는 자막 줄 하이라이트 (+ 화면 밖이면 스크롤) + 시계 갱신
function hlActiveSub(){
  const p=$('cutPlayer'); if(!p) return;
  const clk=$('playClock'); if(clk) clk.textContent=fmtClock(p.currentTime);
  const us=p.currentTime*1e6;
  let active=-1;
  (window._subs||[]).forEach((s,i)=>{ if(us>=s.start_us && us<s.end_us) active=i; });
  const box=$('subList');
  document.querySelectorAll('.subrow').forEach((r,i)=>{
    const on=(i===active);
    r.classList.toggle('subrow-active', on);
    if(on && box){  // 목록 스크롤 영역 안에서만 가운데로 (전체 페이지는 안 움직임)
      const rb=box.getBoundingClientRect(), rr=r.getBoundingClientRect();
      if(rr.top<rb.top+6 || rr.bottom>rb.bottom-6) r.scrollIntoView({block:'center', behavior:'smooth'});
    }
  });
}
function mergeSub(i){
  if(i<=0) return;
  const s=window._subs;
  s[i-1].text=(s[i-1].text+' '+s[i].text).trim();
  s[i-1].end_us=s[i].end_us;
  s.splice(i,1); renderSubRows();
}
function delSub(i){ window._subs.splice(i,1); renderSubRows(); }
function addSubRow(ev){
  ev.preventDefault();
  const s=window._subs, last=s.length?s[s.length-1].end_us:0;
  s.push({text:'', start_us:last, end_us:last+1500000}); renderSubRows();
}
async function pronounceSubs(ev){
  ev.preventDefault();
  const res=await fetch('/api/pronounce',{method:'POST',body:JSON.stringify({lines:window._subs.map(s=>s.text)})});
  const data=await res.json();
  if(data.lines){ data.lines.forEach((t,i)=>{ if(window._subs[i]) window._subs[i].text=t; }); renderSubRows(); }
}
// 전체를 목표 길이 단위로 잘라 쇼츠 여러 개 생성
async function renderSplit(ev){
  if(ev)ev.preventDefault();
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  if(subs.length<2){ alert('나눌 자막이 부족합니다 (2개 이상 필요)'); return; }
  const target=parseInt($('hlTarget').value||'30');
  if(!confirm('전체를 약 '+target+'초 단위 쇼츠 여러 개로 나눠 저장합니다. 계속할까요?')) return;
  const speed=parseFloat(($('outSpeed')||{}).value||'1');
  const quality=($('outQuality')||{}).value||'standard';
  const res=await fetch('/api/edit_split',{method:'POST',body:JSON.stringify(
    {job_id:currentJob, subtitles:subs, target_sec:target, hook:$('editHook').value, speed, quality})});
  const data=await res.json();
  if(data.error){ alert(data.error); return; }
  $('subEditBox').classList.add('hidden');
  if(!timer) timer=setInterval(poll,900);
  poll();
}

async function renderEdited(){
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  const keepIdx=[]; subs.forEach((s,i)=>{ if(s.keep!==false) keepIdx.push(i); });
  if(subs.length && !keepIdx.length){ alert('쇼츠에 넣을 구간을 하나 이상 ☑ 체크하세요'); return; }
  // 전체 선택(또는 자막 없음)이면 재컷 안 함(null), 일부만이면 그 구간만 남김
  const keep=(!subs.length || keepIdx.length===subs.length) ? null : keepIdx;
  const speed=parseFloat(($('outSpeed')||{}).value || '1');
  const quality=($('outQuality')||{}).value || 'standard';
  const res=await fetch('/api/edit_render',{method:'POST',body:JSON.stringify({job_id:currentJob, subtitles:subs, hook:$('editHook').value, keep, speed, quality, hook_scale:+(($('hookSizeSel')||{}).value)||1})});
  const data=await res.json();
  if(data.error){ alert(data.error); return; }
  $('subEditBox').classList.add('hidden');
  if(!timer) timer=setInterval(poll,900);
  poll();
}

async function generate(){
  const prov = pick('prov');
  const body = {
    topic: $('topic').value, auto: pick('mode') === 'auto',
    script_provider: prov === 'gemini' ? 'gemini' : 'stub',  // 진짜 대본은 Gemini만
    tts_provider: prov,
    voice: prov === 'gemini' ? $('voiceSel').value : '',
    tts_style: prov === 'gemini' ? $('styleSel').value : '',
    bgm: $('bgmSel').value, hook: $('genHook').value,
    gemini_key: $('geminiKey').value,
    save_key: $('saveKeyChk').checked,
    draft: $('draftChk').checked, drafts_dir: $('draftsDir').value,
  };
  const res = await fetch('/api/generate', {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'gen';
  $('goBtn').disabled = true;
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('rawErr').classList.add('hidden'); $('noteText').textContent='';
  poll();
  timer = setInterval(poll, 900);
}

async function previewVoice(ev){
  ev.preventDefault();
  const btn = ev.target;
  btn.disabled = true; btn.textContent = '합성 중...';
  try{
    const res = await fetch('/api/preview', {method:'POST', body: JSON.stringify({
      tts_provider: pick('prov'), voice: $('voiceSel').value,
      tts_style: $('styleSel').value, gemini_key: $('geminiKey').value,
    })});
    const data = await res.json();
    if(data.error){ alert(data.error); } else { new Audio(data.url).play(); }
  } finally { btn.disabled = false; btn.textContent = '🔊 미리듣기'; }
}

// ── 편집 모드 내레이션 (v0.26) ──
function onNarrTopicInput(){
  // AI '목소리'를 얹을 때만 원본 자동 무음 (자막만 모드는 원본 소리 유지)
  if(window._origTouched) return;
  const voiceOn = $('narrTopic').value.trim() && !(($('narrSubsOnly')||{}).checked);
  $('origAudioSel').value = voiceOn ? 'mute' : 'keep';
}

async function previewNarrVoice(ev){
  ev.preventDefault();
  const v = $('narrVoiceSel').value;
  let prov = window._hasGeminiKey ? 'gemini' : (window._isWin ? 'windows' : 'stub');
  let key = '';
  if(v === '__mine__') prov = 'elevenlabs';
  else if(v === '__sovits__') prov = 'sovits';
  else {
    key = ensureGeminiKey();   // 보이스는 제미나이 키가 있어야 적용됨 — 없으면 물어봄
    if(key || window._hasGeminiKey) prov = 'gemini';
    else if(!confirm('제미나이 키가 없으면 보이스 선택이 적용되지 않아요 (내장 음성 하나로 고정).\\n키 없이 내장 음성으로 들어볼까요?')) return;
  }
  const btn = ev.target;
  btn.disabled = true; btn.textContent = '합성 중...';
  try{
    const res = await fetch('/api/preview', {method:'POST', body: JSON.stringify({
      tts_provider: prov, voice: (v === '__mine__' || v === '__sovits__') ? '' : v,
      tts_style: $('narrStyleSel').value, gemini_key: key, save_key: true,
    })});
    const data = await res.json();
    if(data.error){ alert(data.error); } else { if(key) window._hasGeminiKey = true; new Audio(data.url).play(); }
  } finally { btn.disabled = false; btn.textContent = '🔊 미리듣기'; }
}

function previewBgm(ev, selId, volSelId){
  ev.preventDefault();
  const btn = ev.target;
  // 재생 중이면 정지 (토글)
  if(window._bgmAudio){
    window._bgmAudio.pause(); window._bgmAudio = null;
    if(window._bgmBtn) window._bgmBtn.textContent = '▶ 미리듣기';
    if(window._bgmBtn === btn) return;   // 같은 버튼 = 정지만
  }
  let name = $(selId).value;
  if(!name){ alert('먼저 배경음악을 선택하세요 (없음 상태)'); return; }
  if(name === 'random'){
    const files = window._bgmFiles || [];
    if(!files.length){ alert('resources/bgm 폴더에 음원이 없습니다 — 6_무료음원_받기.bat를 실행해보세요'); return; }
    name = files[Math.floor(Math.random() * files.length)];
  }
  const a = new Audio('/bgm/' + encodeURIComponent(name));
  // 실제 믹스 볼륨 느낌으로 미리듣기 (목소리=1.0 대비)
  const db = volSelId ? +$(volSelId).value : -14;
  a.volume = Math.min(1, Math.pow(10, db / 20) * 2);
  a.onended = () => { if(window._bgmBtn) window._bgmBtn.textContent = '▶ 미리듣기'; window._bgmAudio = null; };
  a.onerror = () => alert('음원을 재생할 수 없습니다: ' + name);
  a.play();
  window._bgmAudio = a; window._bgmBtn = btn;
  btn.textContent = '⏹ 정지';
}

async function cloneVoice(ev){
  ev.preventDefault();
  const file = $('cloneFile').value.trim();
  if(!file){ alert('녹음 파일 경로를 입력하세요 (1~3분 낭독 녹음)'); return; }
  const key = $('elevenKey').value.trim();
  if(!key && !window._hasElevenKey){ alert('ElevenLabs API 키를 입력하세요 (elevenlabs.io에서 발급, 클로닝은 Starter 이상)'); return; }
  const btn = ev.target; btn.disabled = true; btn.textContent = '등록 중…(최대 1분)';
  try{
    const data = await (await fetch('/api/clone_voice', {method:'POST', body: JSON.stringify({
      file_path: file, name: '내 목소리', elevenlabs_key: key, save_key: true,
    })})).json();
    if(data.error){ alert(data.error); return; }
    window._hasElevenKey = true;
    addMyVoiceOption(data.name || '내 목소리');
    $('narrVoiceSel').value = '__mine__';
    alert('✅ 내 목소리 등록 완료! 보이스 목록에서 「🎤 내 목소리」가 선택됐어요. 🔊 미리듣기로 확인해보세요.');
  } finally { btn.disabled = false; btn.textContent = '등록'; }
}

async function saveSovits(ev){
  ev.preventDefault();
  const ref = $('sovitsRef').value.trim(), txt = $('sovitsRefText').value.trim();
  if(!ref){ alert('참조 녹음 파일 경로를 입력하세요 (5~10초 낭독)'); return; }
  if(!txt){ alert('참조 녹음에서 말한 문장을 입력하세요'); return; }
  const btn = ev.target; btn.disabled = true; btn.textContent = '저장 중…';
  try{
    const data = await (await fetch('/api/sovits_save', {method:'POST', body: JSON.stringify({
      ref_audio: ref, ref_text: txt,
    })})).json();
    if(data.error){ alert(data.error); return; }
    addSovitsOption();
    $('narrVoiceSel').value = '__sovits__';
    alert('✅ 저장 완료! GPT-SoVITS API 서버(127.0.0.1:9880)를 켜둔 상태에서 🔊 미리듣기로 확인해보세요.');
  } finally { btn.disabled = false; btn.textContent = '저장'; }
}

function addSovitsOption(){
  if(![...$('narrVoiceSel').options].some(o => o.value === '__sovits__'))
    $('narrVoiceSel').add(new Option('🎤 내 목소리 (무료·내 PC)', '__sovits__'), 0);
  $('provSovitsLabel').classList.remove('hidden');
  $('myVoiceState').textContent = '— ✅ 등록됨';
}

function addMyVoiceOption(name){
  if(![...$('narrVoiceSel').options].some(o => o.value === '__mine__'))
    $('narrVoiceSel').add(new Option('🎤 내 목소리 (' + name + ')', '__mine__'), 0);
  $('provMineLabel').classList.remove('hidden');
  $('myVoiceState').textContent = '— ✅ 등록됨';
}

function showErrors(errs){
  const raw = (errs||[]).filter(e => e.startsWith('[원본 오류]'));
  const main = (errs||[]).filter(e => !e.startsWith('[원본 오류]'));
  if(main.length){ $('errBox').classList.remove('hidden'); $('errBox').textContent = main.join('\\n'); }
  $('rawErr').classList.toggle('hidden', raw.length === 0);
  $('rawErrText').textContent = raw.join('\\n');
}

async function clearKeys(ev){
  ev.preventDefault();
  if(!confirm('저장된 API 키를 삭제할까요?')) return;
  await fetch('/api/keys', {method:'POST', body: JSON.stringify({action:'clear'})});
  window._hasGeminiKey = false;
  $('keySaved').classList.add('hidden');
  poll();
}

async function pronounceLines(ev){
  ev.preventDefault();
  const res = await fetch('/api/pronounce', {method:'POST', body: JSON.stringify({
    lines: $('rvSentences').value.split('\\n'),
  })});
  const data = await res.json();
  if(data.lines) $('rvSentences').value = data.lines.join('\\n');
}

async function openFolder(ev){
  ev.preventDefault();
  const res = await fetch('/api/open_folder', {method:'POST', body: JSON.stringify({job_id: currentJob})});
  const data = await res.json();
  if(data.error) alert('폴더를 열 수 없습니다: ' + (data.path || data.error));
}

// ── 유튜브 썸네일 만들기 (16:9) ──
function toggleThumb(ev){
  if(ev)ev.preventDefault();
  const box=$('thumbBox'); box.classList.toggle('hidden');
  if(!box.classList.contains('hidden')){
    if(!$('thumbTitle').value) $('thumbTitle').value = ($('editHook')&&$('editHook').value) || ($('topic')&&$('topic').value) || '';
    if(!$('thumbTopic').value) $('thumbTopic').value = ($('editHookTopic')&&$('editHookTopic').value) || ($('topic')&&$('topic').value) || '';
  }
}
async function suggestThumb(ev){
  if(ev)ev.preventDefault();
  const ctx=($('thumbTopic').value||'').trim() || ($('thumbTitle').value||'').trim();
  if(!ctx){ alert('주제/키워드를 먼저 입력하세요'); return; }
  const key=ensureGeminiKey();
  const btn=ev.target; btn.disabled=true; const old=btn.textContent; btn.textContent='추천 중…';
  const cands=$('thumbCands'); cands.innerHTML='';
  try{
    const data=await (await fetch('/api/suggest_thumbnail',{method:'POST',
      body:JSON.stringify({context:ctx, gemini_key:key, save_key:true})})).json();
    if(data.error){ alert(data.error); return; }
    (data.copies||[]).forEach(c=>{
      const b=document.createElement('button');
      b.textContent=(c.title||'').replace(/\\n/g,' / ')+(c.highlight?('  ✨'+c.highlight):'');
      b.onclick=(e)=>{ e.preventDefault(); $('thumbTitle').value = c.highlight ? (c.title+' | '+c.highlight) : c.title; cands.innerHTML=''; };
      cands.appendChild(b);
    });
    if(!(data.copies||[]).length) cands.innerHTML='<span class="hint">추천 결과가 없습니다.</span>';
  } finally { btn.disabled=false; btn.textContent=old; }
}
async function makeThumb(ev){
  if(ev)ev.preventDefault();
  const title=($('thumbTitle').value||'').trim();
  if(!title){ alert('썸네일 제목을 입력하세요'); return; }
  const btn=ev.target; btn.disabled=true; const old=btn.textContent; btn.textContent='만드는 중…';
  try{
    const data=await (await fetch('/api/thumbnail',{method:'POST',
      body:JSON.stringify({job_id:currentJob, title,
        badge:($('thumbBadge')||{}).value||'', bg_path:($('thumbBg')||{}).value||''})})).json();
    if(data.error){ alert(data.error); return; }
    $('thumbImg').src=(data.url||'')+'?t='+Date.now();
    $('thumbPath').textContent='저장됨: '+(data.path||'');
    $('thumbResult').classList.remove('hidden');
  } finally { btn.disabled=false; btn.textContent=old; }
}

async function diagnostic(ev){
  ev.preventDefault();
  const data = await (await fetch('/api/diagnostic', {method:'POST', body:'{}'})).json();
  alert('진단 리포트 저장됨:\\n' + data.path + '\\n\\n문의할 때 이 파일을 함께 올려주세요.');
}

function toggleSettings(){ $('settingsCard').classList.toggle('hidden'); }

function resetEditForm(ev){
  ev.preventDefault();
  if(!confirm('편집 폼의 모든 입력을 기본값으로 되돌릴까요? (저장된 키·설정은 그대로)')) return;
  const set = (id, v) => { const el = $(id); if(el) el.value = v; };
  const chk = (id, v) => { const el = $(id); if(el) el.checked = v; };
  set('editVideo',''); set('photoPath',''); set('photoSec',15);
  set('editHook',''); set('hookSizeSel','1'); set('editHookTopic','');
  const hc = $('editHookCands'); if(hc) hc.innerHTML='';
  set('narrTopic',''); chk('narrSubsOnly',false); set('narrStyleSel','정보형');
  const nv = $('narrVoiceSel'); if(nv && nv.options.length) nv.selectedIndex = 0;
  set('editScript',''); chk('autoSubChk',true); chk('cutSilenceChk',true);
  set('denoiseSel',''); window._origTouched = false; set('origAudioSel','keep');
  set('bgmEditSel',''); set('bgmVolSel','-14');
  set('wmPath',''); set('wmPos','tr'); set('wmScale','0.14');
  chk('autoEditChk',false); set('autoTargetSec',30); set('editSpeedSel','1');
  const st = $('sttSel'); if(st && st.options.length) st.selectedIndex = 0;
  set('whisperModelSel','small');
  renderHookPreview(); onNarrTopicInput();
  if(typeof toggleAutoSub === 'function') toggleAutoSub();
}

function resetGenForm(ev){
  ev.preventDefault();
  if(!confirm('생성 폼의 입력을 기본값으로 되돌릴까요?')) return;
  const set = (id, v) => { const el = $(id); if(el) el.value = v; };
  set('topic','하루 10분 정리 습관'); set('genHook','');
  const hc = $('genHookCands'); if(hc) hc.innerHTML='';
  set('bgmSel',''); set('voiceSel', ($('voiceSel').options[0]||{}).value || '');
  set('styleSel', ($('styleSel').options[0]||{}).value || '');
}

function updateLogs(lines){
  const box = $('logBox');
  if(!box || !lines) return;
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  box.textContent = (lines.length ? lines.join(String.fromCharCode(10)) : '(아직 로그 없음)');
  if(atBottom) box.scrollTop = box.scrollHeight;
}

async function copyLogs(ev){
  ev.preventDefault(); ev.stopPropagation();
  try{ await navigator.clipboard.writeText($('logBox').textContent); ev.target.textContent = '✓ 복사됨'; }
  catch(e){ alert('복사 실패 — 로그를 드래그해서 복사하세요'); }
}

function fillSettings(s){
  $('setFontSize').value = s.subtitle.font_size;
  $('setOutline').value = s.subtitle.outline;
  $('setMarginV').value = s.subtitle.margin_v;
  $('setWrapChars').value = s.subtitle.wrap_chars != null ? s.subtitle.wrap_chars : 16;
  $('setFade').checked = !!s.subtitle.fade;
  $('setHookBand').checked = s.subtitle.hook_band !== false;
  $('setBand').checked = !!s.subtitle.band;
  $('setHlColor').value = s.subtitle.highlight_color;
  $('setMotion').value = s.bg.motion;
  $('setMotionAmt').value = s.bg.motion_amount;
  $('setAiImage').checked = !!s.bg.ai_image;
  $('setBgmVol').value = s.bgm.volume_db;
  $('setDuck').checked = !!s.bgm.duck;
  $('setGap').value = s.audio.gap_ms;
  $('setRpm').value = s.tts.rpm_limit;
}

async function saveSettings(){
  const body = {settings: {
    subtitle: {font_size: +$('setFontSize').value, outline: +$('setOutline').value,
               margin_v: +$('setMarginV').value, fade: $('setFade').checked,
               highlight_color: $('setHlColor').value.toUpperCase(),
               hook_band: $('setHookBand').checked, band: $('setBand').checked,
               wrap_chars: +$('setWrapChars').value},
    bg: {motion: $('setMotion').value, motion_amount: +$('setMotionAmt').value,
         ai_image: $('setAiImage').checked},
    bgm: {volume_db: +$('setBgmVol').value, duck: $('setDuck').checked},
    audio: {gap_ms: +$('setGap').value},
    tts: {rpm_limit: +$('setRpm').value},
  }};
  const data = await (await fetch('/api/settings', {method:'POST', body: JSON.stringify(body)})).json();
  alert(data.ok ? '저장했습니다. 다음 작업부터 적용됩니다.' : ('저장 실패: ' + data.error));
}

async function regen(id){
  const res = await fetch('/api/regenerate', {method:'POST', body: JSON.stringify({job_id: id})});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'gen';
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('reviewBox').classList.add('hidden');
  if(!timer) timer = setInterval(poll, 900);
}

async function confirmScript(){
  await fetch('/api/confirm', {method:'POST', body: JSON.stringify({
    job_id: currentJob, title: $('rvTitle').value,
    sentences: $('rvSentences').value.split('\\n'),
  })});
  $('reviewBox').classList.add('hidden');
  timer = timer || setInterval(poll, 900);
}

async function poll(){
  const state = await (await fetch('/api/state')).json();
  window._hasGeminiKey = state.keys.gemini;
  if(!$('draftsDir').value && state.drafts_dir) $('draftsDir').value = state.drafts_dir;

  window._isWin = (state.platform || '').startsWith('win');
  window._hasElevenKey = !!(state.keys && state.keys.elevenlabs);
  if(window._isWin){
    $('provWinLabel').classList.remove('hidden');
    if(!window._defaultSet){ window._defaultSet = true; $('provWin').checked = true; }
  }
  if(!window._optsFilled){
    window._optsFilled = true;
    for(const v of state.voices || []){ $('voiceSel').add(new Option(v, v)); $('narrVoiceSel').add(new Option(v, v)); }
    for(const s of state.styles || []){ $('styleSel').add(new Option(s, s)); $('narrStyleSel').add(new Option(s, s)); }
    window._bgmFiles = state.bgm_files || [];
    if((state.bgm_files || []).length){
      $('bgmSel').add(new Option('랜덤', 'random'));
      $('bgmEditSel').add(new Option('랜덤', 'random'));
      for(const f of state.bgm_files){ $('bgmSel').add(new Option(f, f)); $('bgmEditSel').add(new Option(f, f)); }
    }
    if(state.settings) fillSettings(state.settings);
    initHookChips();
    const mv = ((state.settings || {}).tts || {});
    if(mv.voice_elevenlabs) addMyVoiceOption(mv.voice_elevenlabs_name || '내 목소리');
    const wms = ((state.settings || {}).watermark || {});
    if(wms.path){ $('wmPath').value = wms.path; $('wmPos').value = wms.pos || 'tr';
                  $('wmScale').value = String(wms.scale || 0.14); }
    if(mv.sovits_ref_audio){
      addSovitsOption();
      $('sovitsRef').value = mv.sovits_ref_audio;
      $('sovitsRefText').value = mv.sovits_ref_text || '';
    }
  }
  $('keySaved').classList.toggle('hidden', !state.keys.gemini);
  const env = state.env || {};
  const problems = [];
  if(env.ffmpeg === false) problems.push('⚠ FFmpeg가 없습니다 — windows 폴더의 1_설치.bat 을 먼저 실행한 뒤 이 화면을 새로고침하세요.');
  if(env.font === false) problems.push('⚠ 자막 폰트가 없습니다 — zip을 다시 풀어주세요 (resources/fonts 폴더).');
  $('envBanner').classList.toggle('hidden', problems.length === 0);
  $('envBanner').textContent = problems.join('  ');

  renderHistory(state.history);
  updateLogs(state.logs);
  if(!currentJob) return;
  const job = state.jobs.find(j => j.id === currentJob);
  if(!job) return;

  $('statusTitle').textContent = job.title || job.id;
  const frac = job.frac || 0;
  $('barFill').style.width = (job.status==='ok'||job.status==='partial' ? 100 : Math.round(frac*100)) + '%';
  $('stageText').textContent = (STAGE_KO[job.stage] || job.stage || '') +
      (job.status==='running' && job.stage!=='review' ? ` — ${Math.round(frac*100)}%` : '');
  let note = job.status === 'running' ? (job.note || '') : '';
  // 렌더 초반 0%가 '멈춤'으로 보이지 않도록 안내 (배경 줌은 시간이 걸림)
  if(job.status==='running' && job.stage==='render' && frac < 0.02)
    note = note || '영상 렌더링 준비 중… 배경 줌 효과는 사양에 따라 1~5분 걸릴 수 있어요. 검은 창을 닫지 마세요.';
  $('noteText').textContent = note;

  if(job.status === 'awaiting_review' && job.script){
    clearInterval(timer); timer = null;
    $('reviewBox').classList.remove('hidden');
    if(!$('rvTitle').value) $('rvTitle').value = job.script.title;
    if(!$('rvSentences').value){
      const hls = job.script.highlights || [];
      $('rvSentences').value = job.script.sentences
        .map((t, i) => hls[i] ? `${t} | ${hls[i]}` : t).join('\\n');
    }
  }
  if(job.status === 'review_subtitle' && !window._subLoaded){
    clearInterval(timer); timer = null;
    window._subLoaded = true;
    // 강조 단어가 있으면 "문장 | 단어" 형태로 보여줘 그 자리에서 수정 가능
    window._subs = (job.subtitles || []).map(s => ({
      text: s.highlight ? (s.text + ' | ' + s.highlight) : s.text,
      start_us: s.start_us, end_us: s.end_us,
    }));
    $('subEditBox').classList.remove('hidden');
    $('bulkBox').classList.add('hidden'); $('bulkText').value='';
    const cp=$('cutPlayer');
    cp.src = '/cutvideo/' + job.id + '?t=' + Date.now();
    cp.ontimeupdate = hlActiveSub;  // 재생 위치 따라 자막 하이라이트 + 시계
    cp.onplay = () => { $('playToggle').textContent='⏸ 정지'; };
    cp.onpause = () => { $('playToggle').textContent='▶ 재생'; };
    cp.playbackRate = parseFloat(($('playRate')||{}).value || '1');
    if($('hlReason')) $('hlReason').textContent='';
    renderSubRows();
    $('noteText').textContent = job.edit_summary || '';
  }
  const provKo = {gemini:'Gemini', openai:'OpenAI', windows:'Windows 내장 음성', stub:'테스트 톤'};
  if(job.status === 'ok' || job.status === 'partial'){
    clearInterval(timer); timer = null;
    $('stageText').innerHTML = job.status === 'ok'
      ? '<span class="ok-badge">✔ 완료 — 자가검증 통과</span>'
      : '<span class="fail-badge">부분 완료</span>';
    let badge = job.tts_provider ? '목소리: ' + (provKo[job.tts_provider] || job.tts_provider) : '';
    if(job.requested_tts && job.tts_provider && job.requested_tts !== job.tts_provider)
      badge = '⚠ ' + (provKo[job.tts_provider] || job.tts_provider) + '로 대체 생성됨 (원래 선택: ' + (provKo[job.requested_tts] || job.requested_tts) + ')';
    if(job.edit_summary) badge = '✂️ ' + job.edit_summary;  // 편집 모드 요약
    $('providerBadge').textContent = badge;
    if(job.mp4){
      $('doneBox').classList.remove('hidden');
      $('player').src = '/video/' + job.id + '?t=' + Date.now() + '#t=0.1';
      if(job.mp4s && job.mp4s.length > 1){
        $('outPaths').innerHTML = '🎬 쇼츠 ' + job.mp4s.length + '개 완성:<br>' +
          job.mp4s.map((p,i)=>('  '+(i+1)+') '+p)).join('<br>') +
          '<br><span class="hint">(위 플레이어는 1번 쇼츠. 나머지는 [📂 폴더 열기]에서 확인)</span>';
      } else {
        $('outPaths').textContent = 'mp4: ' + job.mp4 + (job.draft ? '  |  draft: ' + job.draft : '');
      }
    }
    showErrors(job.errors);
    $('goBtn').disabled = false; $('editBtn').disabled = false;
  }
  if(job.status === 'failed'){
    clearInterval(timer); timer = null;
    $('stageText').innerHTML = '<span class="fail-badge">✘ 실패</span>';
    if(!(job.errors || []).length) $('errBox').textContent = '알 수 없는 오류';
    showErrors(job.errors);
    $('errBox').classList.remove('hidden');
    $('goBtn').disabled = false; $('editBtn').disabled = false;
  }
}

const PROV_KO = {gemini:'Gemini', openai:'OpenAI', windows:'내장', stub:'톤'};
function renderHistory(rows){
  const tb = $('histTable').querySelector('tbody');
  tb.innerHTML = '';
  for(const r of rows || []){
    const tr = document.createElement('tr');
    const btns = [
      r.has_mp4 ? `<button class="ghost" onclick="playHist('${r.id}')">▶ 재생</button>` : '',
      r.has_spec ? `<button class="ghost" onclick="regen('${r.id}')" title="저장된 설계로 mp4 재렌더">♻ 재생성</button>` : '',
    ].join(' ');
    tr.innerHTML = `<td>${(r.created_at||'').replace('T',' ').slice(5,16)}</td>
      <td>${r.title||r.id}</td><td>${PROV_KO[r.tts_provider]||'-'}</td>
      <td>${r.status==='ok'?'<span class="ok-badge">완료</span>':r.status}</td>
      <td style="white-space:nowrap">${btns}</td>`;
    tb.appendChild(tr);
  }
}

function playHist(id){
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.remove('hidden');
  $('statusTitle').textContent = '히스토리 재생';
  $('stageText').textContent = '';
  $('player').src = '/video/' + id + '?t=' + Date.now() + '#t=0.1';
}

function resetForm(){
  currentJob = null; if(timer){clearInterval(timer); timer=null;}
  window._subLoaded = false; window._subs = [];
  $('statusCard').classList.add('hidden');
  $('reviewBox').classList.add('hidden');
  $('subEditBox').classList.add('hidden');
  $('rvTitle').value = ''; $('rvSentences').value = '';
  $('noteText').textContent = ''; $('providerBadge').textContent = '';
  $('errBox').classList.add('hidden'); $('rawErr').classList.add('hidden');
  if($('thumbBox')){ $('thumbBox').classList.add('hidden'); $('thumbResult').classList.add('hidden');
    $('thumbTitle').value=''; $('thumbCands').innerHTML=''; }
  $('goBtn').disabled = false; $('editBtn').disabled = false;
}

// 스페이스바 = 재생/정지 (자막 검토 화면에서만, 입력창 포커스 땐 제외 — 브루식 단축키)
document.addEventListener('keydown', (e) => {
  if(e.code !== 'Space' && e.key !== ' ') return;
  const t = e.target, tag = (t.tagName || '').toLowerCase();
  if(tag==='input' || tag==='textarea' || tag==='select' || t.isContentEditable) return;
  const box = $('subEditBox');
  if(!box || box.classList.contains('hidden')) return;
  e.preventDefault(); togglePlay();
});

poll(); setInterval(()=>{ if(!currentJob) poll(); }, 5000);
</script>
</body>
</html>
"""
