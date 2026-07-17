"""출력 A: Timeline Spec → CapCut draft (pyCapCut 4트랙 조립, 기획안 §5.4).

트랙 구성(아래→위): 배경 → 메인 영상 → 그라데이션 → 자막 / 오디오는 별도 트랙.
pycapcut의 시간 단위는 μs(SEC=1e6)로 IR과 동일 — 변환 손실 없음.

⚠ PoC 게이트 (기획안 §9 Phase 0, §11 액션 아이템 1·2·5) — 실제 CapCut에서 열림 검증은
Windows + CapCut 설치 환경에서만 가능하다. 아래 항목은 캡컷 실물로 캘리브레이션 필요:
  - ClipSettings.transform_y 좌표 부호·스케일 (여기서는 +y=위, 반캔버스 단위 가정)
  - TextStyle.size 단위 ↔ ASS 픽셀 크기 매핑 (_PX_TO_CAPCUT_SIZE)
  - 임의 크기 이미지의 기본 fit 동작 (컷대장이 만드는 배경은 캔버스와 동일 크기라 무관)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .. import presets
from ..spec import TimelineSpec
from ..utils import ffmpeg as ff


class DraftBuilderUnavailable(RuntimeError):
    """pycapcut 미설치 등으로 출력 A를 사용할 수 없음."""


class DraftBuildError(RuntimeError):
    pass


# ASS 픽셀 크기 → CapCut 텍스트 size 근사 계수 (PoC에서 시각 캘리브레이션 예정)
_PX_TO_CAPCUT_SIZE = 0.15


@dataclass
class DraftResult:
    ok: bool
    draft_path: str
    problems: List[str] = field(default_factory=list)


def _import_pycapcut():
    try:
        import pycapcut  # noqa: PLC0415

        return pycapcut
    except ImportError as e:
        raise DraftBuilderUnavailable(
            "pycapcut이 설치되어 있지 않습니다. `pip install pycapcut` 후 다시 시도하세요. "
            "(출력 B(mp4 직접 렌더)는 pycapcut 없이도 동작합니다)"
        ) from e


def build_draft(spec: TimelineSpec, drafts_dir: str, draft_name: str) -> DraftResult:
    """Timeline Spec을 CapCut Drafts 폴더에 draft로 조립하고 자가검증한다."""
    cc = _import_pycapcut()
    spec.validate()
    missing = spec.missing_files()
    if missing:
        raise DraftBuildError(f"spec이 참조하는 파일 없음: {missing}")

    if not Path(drafts_dir).is_dir():
        raise DraftBuildError(
            f"CapCut Drafts 폴더가 없습니다: {drafts_dir}\n"
            "CapCut이 설치·실행된 적 있는 PC의 Drafts 경로를 지정하세요 "
            "(draft_manager가 자동 감지 예정 — 기획안 §5.7)"
        )

    c = spec.canvas
    folder = cc.DraftFolder(str(drafts_dir))
    script = folder.create_draft(draft_name, c.w, c.h, fps=c.fps, allow_replace=True)

    # ── 트랙 4종 + 오디오 (relative_index가 클수록 위 레이어) ──
    script.add_track(cc.TrackType.video, "background", relative_index=0)
    if spec.main_video is not None:
        script.add_track(cc.TrackType.video, "main", relative_index=1)
    if spec.style.gradient_overlay:
        script.add_track(cc.TrackType.video, "gradient", relative_index=2)
    script.add_track(cc.TrackType.text, "subtitles")
    script.add_track(cc.TrackType.audio, "voice")

    # ── 배경 (이미지 duration = 전체 길이, Ken Burns 키프레임) ──
    if spec.background.type == "image":
        bg_seg = cc.VideoSegment(spec.background.path, cc.trange(0, spec.duration_us))
        if spec.background.motion != "off":
            amt = spec.background.motion_amount
            start_v, end_v = (
                (1.0, 1.0 + amt) if spec.background.motion == "zoom_in" else (1.0 + amt, 1.0)
            )
            try:
                bg_seg.add_keyframe(cc.KeyframeProperty.uniform_scale, 0, start_v)
                bg_seg.add_keyframe(
                    cc.KeyframeProperty.uniform_scale, spec.duration_us, end_v
                )
            except Exception:  # 키프레임 실패는 정적 배경으로 폴백 (PoC에서 캘리브레이션)
                pass
        script.add_segment(bg_seg, "background")
    else:
        raise DraftBuildError(
            "draft 출력은 background.type=image만 지원합니다 "
            "(색상 배경은 이미지로 생성해 전달하세요 — background_generator 사용)"
        )

    # ── 메인 영상 (배치 프리셋: 상단·중앙·풀) ──
    if spec.main_video is not None:
        mv = spec.main_video
        src_dur = ff.probe_duration_us(mv.path)
        use_dur = min(src_dur, spec.duration_us)  # fit=trim; 짧은 영상 정지/루프는 PoC 후 확장
        clip = None
        if mv.layout != "full":
            src_w, src_h = ff.probe_video_size(mv.path)
            target_w = presets.main_video_target_width(c.w, mv.layout, mv.scale)
            scale = target_w / c.w
            ty = 0.0
            if mv.layout == "top":
                scaled_h = target_w * src_h / src_w
                center_from_top = c.h * 0.08 + scaled_h / 2
                ty = (c.h / 2 - center_from_top) / (c.h / 2)  # +y=위 가정 (PoC 확인)
            clip = cc.ClipSettings(scale_x=scale, scale_y=scale, transform_y=ty)
        script.add_segment(
            cc.VideoSegment(
                mv.path,
                cc.trange(0, use_dur),
                source_timerange=cc.trange(0, use_dur),
                volume=0.0,
                clip_settings=clip,
            ),
            "main",
        )

    # ── 하단 그라데이션 (render_engine과 동일한 PNG 재사용) ──
    if spec.style.gradient_overlay:
        gradient_png = str(Path(drafts_dir) / draft_name / "cutdaejang_gradient.png")
        from ..utils.png import bottom_gradient_overlay_png  # noqa: PLC0415

        bottom_gradient_overlay_png(gradient_png, c.w, c.h)
        script.add_segment(
            cc.VideoSegment(gradient_png, cc.trange(0, spec.duration_us)), "gradient"
        )

    # ── 자막 (공통 스타일 프리셋 → CapCut TextStyle 변환, 기획안 §7-4) ──
    style = spec.style
    text_style = cc.TextStyle(
        size=style.size * _PX_TO_CAPCUT_SIZE,
        color=_hex_to_rgb01(style.primary_color),
        align=1,  # 중앙 정렬
    )
    border = cc.TextBorder(color=_hex_to_rgb01(style.outline_color), width=style.outline * 13.0)
    ty_map = {"bottom": -0.71, "center": 0.0, "top": 0.71}
    text_clip = cc.ClipSettings(transform_y=ty_map[style.position])
    for sub in spec.subtitles:
        script.add_segment(
            cc.TextSegment(
                sub.text,
                cc.trange(sub.start_us, sub.end_us - sub.start_us),
                style=text_style,
                border=border,
                clip_settings=text_clip,
            ),
            "subtitles",
        )

    # ── 오디오 ──
    for a in spec.audio:
        script.add_segment(
            cc.AudioSegment(a.path, cc.trange(a.start_us, a.end_us - a.start_us)),
            "voice",
        )

    # ── BGM (별도 오디오 트랙, 볼륨 동일값 — 지시서 PATCH 3) ──
    if spec.bgm is not None:
        script.add_track(cc.TrackType.audio, "bgm")
        bgm_dur = ff.probe_duration_us(spec.bgm.path)
        linear = 10 ** (spec.bgm.volume_db / 20)  # dB → 선형 (예: -20dB → 0.1)
        t = 0
        while t < spec.duration_us and bgm_dur > 0:  # 짧은 음원은 이어붙여 루프
            seg_dur = min(bgm_dur, spec.duration_us - t)
            script.add_segment(
                cc.AudioSegment(
                    spec.bgm.path,
                    cc.trange(t, seg_dur),
                    source_timerange=cc.trange(0, seg_dur),
                    volume=linear,
                ),
                "bgm",
            )
            t += seg_dur

    script.save()

    draft_path = str(Path(drafts_dir) / draft_name)
    problems = _self_check(draft_path, spec)
    return DraftResult(ok=not problems, draft_path=draft_path, problems=problems)


def _hex_to_rgb01(hex_rgb: str) -> tuple:
    rgb = hex_rgb.lstrip("#")
    return tuple(int(rgb[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _self_check(draft_path: str, spec: TimelineSpec) -> List[str]:
    """draft 자가검증 3종: 파일 존재 / JSON 파싱 / 길이·트랙 구성 (기획안 §5.7)."""
    problems = []
    content = Path(draft_path) / "draft_content.json"
    if not content.exists():
        return [f"draft_content.json 없음: {content}"]
    try:
        data = json.loads(content.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"draft_content.json 파싱 실패: {e}"]

    duration = data.get("duration")
    if duration != spec.duration_us:
        problems.append(f"draft duration({duration}) != spec duration({spec.duration_us})")
    track_types = [t.get("type") for t in data.get("tracks", [])]
    for required in ("video", "text", "audio"):
        if required not in track_types:
            problems.append(f"필수 트랙 누락: {required} (실제: {track_types})")
    return problems
