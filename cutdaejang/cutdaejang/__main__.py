"""컷대장 CLI — GUI(Phase 2, CustomTkinter) 이전의 개발·검증용 진입점.

    python -m cutdaejang doctor                     # 환경 점검 (FFmpeg/libass/GPU/폰트/키)
    python -m cutdaejang demo                       # 오프라인 데모 (스텁 대본+TTS → mp4)
    python -m cutdaejang run --topic "..." --auto   # 주제 → 완성 (자동 모드)
    python -m cutdaejang run --script-file s.json   # 검토 확정된 대본으로 재개
    python -m cutdaejang render --spec spec.json    # 저장된 Timeline Spec 재렌더 (재생성)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from . import __version__, config
from .core import orchestrator, render_engine
from .core.render_engine.ffmpeg_composer import RenderOptions
from .core.script_generator import SCRIPT_PROVIDERS, Script
from .core.tts_engine import PROVIDERS as TTS_PROVIDERS
from .core.tts_engine import STYLE_INSTRUCTIONS
from .spec import TimelineSpec
from .utils import ffmpeg as ff


def _progress_printer(stage: str, frac: float) -> None:
    sys.stdout.write(f"\r[{stage:>10}] {frac * 100:5.1f}%")
    sys.stdout.flush()
    if frac >= 1.0:
        sys.stdout.write("\n")


def cmd_doctor(_: argparse.Namespace) -> int:
    """배포 환경 자가진단 — 고객 PC에서 문제 원인별 안내 (기획안 §7-1, §7-5)."""
    ok = True

    def check(label: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        mark = "✅" if passed else "❌"
        print(f"{mark} {label}" + (f" — {hint}" if hint and not passed else ""))
        ok = ok and passed

    try:
        ffmpeg = ff.ffmpeg_bin()
        check(f"ffmpeg: {ffmpeg}", True)
        filters = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"], capture_output=True, timeout=20
        ).stdout.decode()
        check(
            "libass(subtitles 필터)", " subtitles " in filters,
            "libass 포함 FFmpeg 빌드가 필요합니다 (기획안 §4)",
        )
    except ff.FFmpegError as e:
        check("ffmpeg", False, str(e))
    try:
        check(f"ffprobe: {ff.ffprobe_bin()}", True)
    except ff.FFmpegError as e:
        check("ffprobe", False, str(e))

    font = Path(render_engine.DEFAULT_FONTS_DIR) / "Pretendard-ExtraBold.ttf"
    check(f"폰트 동봉: {font.name}", font.exists(), f"{font} 경로에 TTF를 두세요")

    gpu = ff.nvenc_available()
    print(("✅" if gpu else "ℹ️ ") + f" GPU 인코딩(h264_nvenc): {'사용 가능' if gpu else '미감지 → libx264 사용'}")

    for key, label in (("GEMINI_API_KEY", "Gemini"), ("OPENAI_API_KEY", "OpenAI")):
        present = bool(os.environ.get(key))
        print(("✅" if present else "ℹ️ ") + f" {label} API 키: {'설정됨' if present else '없음 (해당 제공자 사용 불가)'}")

    try:
        import pycapcut  # noqa: F401, PLC0415

        print("✅ pycapcut 설치됨 (출력 A 사용 가능)")
    except ImportError:
        print("ℹ️  pycapcut 없음 — 출력 A(draft) 비활성, 출력 B(mp4)는 정상")

    print("\n진단 결과:", "정상" if ok else "조치 필요")
    return 0 if ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = config.load_settings()
    outputs = tuple(o.strip() for o in args.outputs.split(",") if o.strip())
    chain = (
        list(settings["tts"]["fallback_chain"]) if args.tts == "gemini" else [args.tts]
    )
    opts = orchestrator.JobOptions(
        outputs=outputs,
        auto_mode=args.auto,
        tts_chain=chain,
        voice=args.voice,
        tts_style=args.tts_style,
        target_sec=args.target_sec,
        bgm=args.bgm,
        hook=(getattr(args, "hook", "") or "").replace("\\n", "\n"),
        user_background=args.background,
        main_video_path=args.main_video,
        drafts_dir=args.drafts_dir,
        render=RenderOptions(crf=args.crf, use_gpu=args.gpu),
    )

    def status_note(msg: str) -> None:
        sys.stdout.write(f"\n  ℹ {msg}")
        sys.stdout.flush()

    if args.script_file:
        script = Script.from_json_text(Path(args.script_file).read_text(encoding="utf-8"))
        result = orchestrator.run_job(
            args.workdir, script, opts=opts, settings=settings,
            progress_cb=_progress_printer, status_cb=status_note,
        )
    else:
        if not args.topic:
            print("--topic 또는 --script-file 중 하나가 필요합니다", file=sys.stderr)
            return 2
        provider = SCRIPT_PROVIDERS[args.script_provider]()
        result = orchestrator.run_topic(
            args.workdir, args.topic, provider, opts=opts, settings=settings,
            progress_cb=_progress_printer, status_cb=status_note,
        )

    _record_history(args, result, opts)

    if result.status == "awaiting_review":
        print(f"\n대본 생성 완료 (검토 모드): {result.script_path}")
        print("검토·수정 후 다음으로 재개하세요:")
        print(f"  python -m cutdaejang run --script-file {result.script_path}")
        return 0

    print(f"\n작업 {result.job_id}: {result.status}")
    if result.tts_provider:
        note = f" ({result.fallback_note})" if result.fallback_note else ""
        print(f"  목소리 제공자: {result.tts_provider}{note}")
    if result.mp4:
        print(f"  mp4: {result.mp4.out_path} "
              f"(인코더 {result.mp4.encoder}, 실측 {result.mp4.measured_duration_us / 1e6:.2f}s)")
    if result.draft_path:
        print(f"  draft: {result.draft_path}")
    for e in result.errors:
        print(f"  ⚠ {e}")
    return 0 if result.status == "ok" else 1


def _record_history(args, result, opts) -> None:
    try:
        from .db.jobs import JobStore  # noqa: PLC0415

        store = JobStore(Path(args.workdir) / "history.db")
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
    except Exception as e:  # 히스토리 기록 실패는 작업 성패에 영향 없음
        logging.getLogger("cutdaejang").warning("히스토리 기록 실패: %s", e)


def cmd_demo(args: argparse.Namespace) -> int:
    """API 키 없이 전체 파이프라인 시연 (스텁 대본 + 사인파 TTS + 로컬 배경)."""
    args.topic = args.topic or "컷대장 파이프라인 데모"
    args.script_provider = "stub"
    args.tts = "stub"
    args.auto = True
    args.script_file = None
    return cmd_run(args)


def cmd_edit(args: argparse.Namespace) -> int:
    """내 영상 → 무음컷 + 자동자막 (기획안 v1.5 육성 촬영 모드)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from .core import edit_mode  # noqa: PLC0415
    from .core.stt_engine import STTEngine, make_provider  # noqa: PLC0415
    from .core.video_editor import SilenceOptions  # noqa: PLC0415

    settings = config.load_settings()
    edit_cfg = settings["edit"]
    # 대본 파일이 있으면 STT 대신 그 대본을 씀 (오인식·비용 0)
    script_lines = None
    if getattr(args, "script_file", None):
        script_lines = Path(args.script_file).read_text(encoding="utf-8").splitlines()
    use_stt = not args.no_subtitle and not script_lines
    stt = None
    if use_stt:
        provider = make_provider(args.stt or edit_cfg["stt_provider"], edit_cfg)
        stt = STTEngine(provider, Path(args.workdir) / "cache" / "stt", language=args.language)

    result = edit_mode.edit_video(
        args.video,
        Path(args.workdir) / "edit",
        stt,
        layout=args.layout or edit_cfg["layout"],
        hook=(args.hook or "").replace("\\n", "\n"),
        auto_subtitle=not args.no_subtitle,
        cut_silence=not args.no_cut,
        script_lines=script_lines,
        silence_opts=SilenceOptions(
            noise_db=edit_cfg["noise_db"],
            min_silence_s=edit_cfg["min_silence_s"],
            pad_s=edit_cfg["pad_s"],
        ),
        out_path=args.out,
        progress_cb=_progress_printer,
        status_cb=lambda m: print(f"\n  ℹ {m}"),
    )
    print(f"\n편집 {'완료' if result.ok else '경고'}: {result.out_path}")
    print(f"  원본 {result.original_us / 1e6:.1f}s → 컷 {result.cut_us / 1e6:.1f}s "
          f"(무음 {result.removed_ratio * 100:.0f}% 제거, 구간 {result.segments}개, STT {result.stt_calls}회)")
    for e in result.errors:
        print(f"  ⚠ {e}")
    return 0 if result.ok else 1


def cmd_ui(args: argparse.Namespace) -> int:
    from .gui.webui import serve  # noqa: PLC0415

    return serve(workdir=args.workdir, port=args.port, open_browser=not args.no_open)


def cmd_render(args: argparse.Namespace) -> int:
    spec = TimelineSpec.load(args.spec).resolve_paths(str(Path(args.spec).parent))
    out = args.out or str(Path(args.spec).with_name("output.mp4"))
    result = render_engine.render(
        spec,
        Path(out).parent / "render",
        out_path=out,
        opts=RenderOptions(crf=args.crf, use_gpu=args.gpu),
        progress_cb=lambda f: _progress_printer("render", f),
    )
    print(f"{'완료' if result.ok else '자가검증 실패'}: {result.out_path} "
          f"(인코더 {result.encoder}, {result.measured_duration_us / 1e6:.2f}s, "
          f"{result.width}x{result.height}, 시도 {result.attempts}회)")
    for e in result.errors:
        print(f"  ⚠ {e}")
    return 0 if result.ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="cutdaejang", description=f"컷대장 v{__version__} — 쇼츠·영상 조립 자동화"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="환경 자가진단").set_defaults(func=cmd_doctor)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--workdir", default="jobs", help="작업 폴더 (기본: ./jobs)")
        p.add_argument("--crf", type=int, default=19, help="렌더 품질 CRF (기본 19)")
        p.add_argument("--gpu", choices=("auto", "on", "off"), default="auto")

    run_p = sub.add_parser("run", help="주제/대본 → 산출물")
    add_common(run_p)
    run_p.add_argument("--topic", help="쇼츠 주제")
    run_p.add_argument("--script-file", help="검토 완료된 대본 JSON")
    run_p.add_argument("--auto", action="store_true", help="자동 모드 (검토 게이트 스킵, 기본 OFF)")
    run_p.add_argument("--outputs", default="mp4", help="mp4,draft (기본 mp4)")
    run_p.add_argument("--script-provider", choices=tuple(SCRIPT_PROVIDERS), default="gemini")
    run_p.add_argument("--tts", choices=tuple(TTS_PROVIDERS), default="gemini",
                       help="gemini 선택 시 settings.json의 폴백 체인 적용")
    run_p.add_argument("--voice", default="", help="TTS 보이스명 (비면 설정/프리셋 기준)")
    run_p.add_argument("--tts-style", choices=tuple(STYLE_INSTRUCTIONS), default="",
                       help="보이스 스타일 프리셋 (기본: settings.json)")
    run_p.add_argument("--bgm", default="", help="BGM: 파일명(resources/bgm) 또는 'random'")
    run_p.add_argument("--hook", default="", help="상단 제목(훅). 비우면 대본 제목 사용. 줄바꿈 \\n")
    run_p.add_argument("--target-sec", type=int, default=60)
    run_p.add_argument("--background", help="사용자 배경 이미지 경로")
    run_p.add_argument("--main-video", help="메인 영상 파일 경로")
    run_p.add_argument("--drafts-dir", help="CapCut Drafts 폴더 (출력 A)")
    run_p.set_defaults(func=cmd_run)

    demo_p = sub.add_parser("demo", help="오프라인 데모 (키 불필요)")
    add_common(demo_p)
    demo_p.add_argument("--topic", default=None)
    demo_p.add_argument("--outputs", default="mp4")
    demo_p.add_argument("--voice", default="")
    demo_p.add_argument("--bgm", default="")
    demo_p.add_argument("--target-sec", type=int, default=30)
    demo_p.add_argument("--background", default=None)
    demo_p.add_argument("--main-video", default=None)
    demo_p.add_argument("--drafts-dir", default=None)
    demo_p.set_defaults(func=cmd_demo, tts_style="")

    edit_p = sub.add_parser("edit", help="내 영상 → 무음컷 + 자동자막 (v1.5)")
    edit_p.add_argument("--video", required=True, help="편집할 영상 파일")
    edit_p.add_argument("--workdir", default="jobs")
    edit_p.add_argument("--out", help="출력 mp4 경로")
    edit_p.add_argument("--stt", choices=("whisper", "gemini", "openai", "stub"), default=None)
    edit_p.add_argument("--layout", choices=("shorts", "keep"), default=None)
    edit_p.add_argument("--hook", default="", help="상단 제목(훅). 줄바꿈은 \\n")
    edit_p.add_argument("--script-file", default=None,
                        help="미리 가진 대본 txt (한 줄=자막 한 줄). 있으면 STT 대신 사용")
    edit_p.add_argument("--no-subtitle", action="store_true", help="자동 자막 끄기 (내레이션 없는 영상)")
    edit_p.add_argument("--no-cut", action="store_true", help="무음컷 끄기 (원본 길이 유지)")
    edit_p.add_argument("--language", default="ko")
    edit_p.set_defaults(func=cmd_edit)

    ui_p = sub.add_parser("ui", help="브라우저 UI 실행 (로컬 웹 화면)")
    ui_p.add_argument("--workdir", default="jobs")
    ui_p.add_argument("--port", type=int, default=7860)
    ui_p.add_argument("--no-open", action="store_true", help="브라우저 자동 열기 끄기")
    ui_p.set_defaults(func=cmd_ui)

    render_p = sub.add_parser("render", help="저장된 spec 재렌더 (히스토리 재생성)")
    render_p.add_argument("--spec", required=True, help="spec.json 경로")
    render_p.add_argument("--out", help="출력 mp4 경로")
    render_p.add_argument("--crf", type=int, default=19)
    render_p.add_argument("--gpu", choices=("auto", "on", "off"), default="auto")
    render_p.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
