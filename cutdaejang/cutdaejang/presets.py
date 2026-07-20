"""공통 스타일·배치 프리셋 — A(draft)/B(직접 렌더) 출력 간 시각적 일관성의 기준점 (기획안 §1.4, §7-4).

render_engine(ass_writer)이 여기 정의된 값에서 ASS 포맷으로 변환한다.
"""

from __future__ import annotations

from .spec import Canvas, Style

CANVAS_SHORTS = Canvas(w=1080, h=1920, fps=30)
CANVAS_LANDSCAPE = Canvas(w=1920, h=1080, fps=30)  # v1.5 일반 모드

# 스펙에는 파일명 스타일("Pretendard-ExtraBold")로 적더라도
# libass/ASS Fontname은 폰트 내부 패밀리명("Pretendard ExtraBold")이어야 매칭된다.
FONT_FAMILY_ALIASES = {
    "Pretendard-ExtraBold": "Pretendard ExtraBold",
    "Pretendard-Bold": "Pretendard Bold",
    "Pretendard-SemiBold": "Pretendard SemiBold",
    # ⬇ 무료 글씨체 (v0.63 — tools/fetch_fonts.py로 받는 Google Fonts OFL 한글)
    "BlackHanSans-Regular": "Black Han Sans",
    "Jua-Regular": "Jua",
    "DoHyeon-Regular": "Do Hyeon",
    "Gugi-Regular": "Gugi",
    "NanumPenScript-Regular": "Nanum Pen Script",
}

SUBTITLE_STYLE_PRESETS = {
    # 기본 쇼츠 자막: 흰 글자 + 검정 외곽선 3px + 하단 그라데이션
    "shorts_basic": Style(
        font="Pretendard-ExtraBold", size=64, outline=3,
        position="bottom", gradient_overlay=True,
    ),
    # 그라데이션 없이 외곽선만 (밝은 배경 영상용)
    "shorts_outline_only": Style(
        font="Pretendard-ExtraBold", size=64, outline=4,
        position="bottom", gradient_overlay=False,
    ),
    # 중앙 배치 (정보형 쇼츠 — 메인 영상 없이 배경+자막만)
    "shorts_center": Style(
        font="Pretendard-ExtraBold", size=72, outline=3,
        position="center", gradient_overlay=False,
    ),
}


def font_family(spec_font: str) -> str:
    """스펙의 font 값 → ASS/libass용 폰트 패밀리명."""
    return FONT_FAMILY_ALIASES.get(spec_font, spec_font)


def subtitle_alignment(position: str) -> int:
    """ASS Alignment (numpad): 하단중앙=2, 정중앙=5, 상단중앙=8."""
    return {"bottom": 2, "center": 5, "top": 8}[position]


def subtitle_margin_v(position: str, canvas_h: int) -> int:
    """세로 여백 기본값 — 쇼츠 하단 UI(제목·버튼) 안전 영역을 피해 화면 높이 비례로 계산."""
    ratio = {"bottom": 0.25, "center": 0.0, "top": 0.13}[position]  # 하단 UI(~420px) 위
    return round(canvas_h * ratio)


def main_video_target_width(canvas_w: int, layout: str, scale: float) -> int:
    """메인 영상 가로폭(px). full은 캔버스를 가득 채우고, 그 외엔 scale 비율 적용.

    libx264 요구사항(짝수 해상도)에 맞춰 짝수로 내림.
    """
    w = canvas_w if layout == "full" else round(canvas_w * scale)
    return w - (w % 2)


# 상단 제목(훅) 스타일 — 참고 영상처럼 크게·볼드·상단 고정 (기획안 완성도 향상)
# ── 유튜브 쇼츠 안전 영역 (1080×1920 기준, 크리에이터 템플릿 합의값) ──
#  · 상단 0~220px: 시스템 상태바 + Shorts 헤더(검색·카메라·메뉴) → 글자 가림
#  · 하단 0~420px: 영상 제목·채널명·설명·음악 + 진행바
#  · 우측 폭 ~140px(높이 45~85% 구간): 좋아요·댓글·공유·리믹스 버튼 기둥
TITLE_SIZE_RATIO = 0.058      # 캔버스 높이 대비 글자 크기 (1920→약 111px)
TITLE_MARGIN_RATIO = 0.125    # 상단 여백 240px — Shorts 헤더(0~220px) 아래로
TITLE_OUTLINE = 5
TITLE_SHADOW = 1


def title_size(canvas_h: int) -> int:
    return round(canvas_h * TITLE_SIZE_RATIO)


def title_margin_v(canvas_h: int) -> int:
    return round(canvas_h * TITLE_MARGIN_RATIO)


def main_video_y_expr(layout: str, canvas_h: int) -> str:
    """overlay 필터의 y 좌표 식. top은 화면 위 8% 지점, center/full은 세로 중앙."""
    if layout == "top":
        return str(round(canvas_h * 0.08))
    return "(H-h)/2"
