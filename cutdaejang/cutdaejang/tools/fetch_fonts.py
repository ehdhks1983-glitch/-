"""무료 한글 글씨체 5종 자동 받기 (v0.63) — Google Fonts OFL(재배포 허용).

fetch_bgm과 같은 패턴: 이미 있으면 건너뛰고, 받은 파일은 resources/fonts에.
URL은 구글 정적 CDN의 버전 고정 주소라 수년간 안정적이다.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from ..core.render_engine import DEFAULT_FONTS_DIR

# (파일명, 화면 이름, URL) — 파일명 스템은 presets.FONT_FAMILY_ALIASES 키와 일치
FONTS = [
    ("BlackHanSans-Regular.ttf", "블랙한산스 (임팩트 굵은)",
     "https://fonts.gstatic.com/s/blackhansans/v24/ea8Aad44WunzF9a-dL6toA8r8nqV.ttf"),
    ("Jua-Regular.ttf", "주아 (둥근 포근)",
     "https://fonts.gstatic.com/s/jua/v18/co3KmW9ljjAjcw.ttf"),
    ("DoHyeon-Regular.ttf", "도현 (각진 고딕)",
     "https://fonts.gstatic.com/s/dohyeon/v21/TwMN-I8CRRU2zM86HFE3.ttf"),
    ("Gugi-Regular.ttf", "구기 (레트로)",
     "https://fonts.gstatic.com/s/gugi/v21/A2BVn5dXywshVA4.ttf"),
    ("NanumPenScript-Regular.ttf", "나눔손글씨 펜 (손글씨)",
     "https://fonts.gstatic.com/s/nanumpenscript/v25/daaDSSYiLGqEal3MvdA_FOL_3FkN2z4.ttf"),
]

_LICENSE_NOTE = """이 폴더의 아래 글씨체는 SIL Open Font License(OFL)로 배포되는 무료 폰트입니다.
출처: Google Fonts (fonts.google.com) — 영상·상업적 사용 가능, 폰트 자체 재판매만 금지.
Black Han Sans · Jua · Do Hyeon · Gugi · Nanum Pen Script
"""


def fetch(url: str, dest: Path) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "cutdaejang-font-fetch"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < 10_000:  # TTF치고 너무 작으면 오류 페이지일 것
        raise OSError(f"다운로드 크기 이상 ({len(data)}B)")
    dest.write_bytes(data)
    return True


def fetch_all(fonts_dir=None, progress=None) -> dict:
    """글씨체 전부 받기 — 반환 {"got": n, "skip": n, "fail": [이름...]}"""
    out = Path(fonts_dir) if fonts_dir else Path(DEFAULT_FONTS_DIR)
    out.mkdir(parents=True, exist_ok=True)
    got, skip, fail = 0, 0, []
    for fname, label, url in FONTS:
        dest = out / fname
        if dest.is_file() and dest.stat().st_size > 10_000:
            skip += 1
            continue
        try:
            if progress:
                progress(label)
            fetch(url, dest)
            got += 1
        except Exception:  # noqa: BLE001 — 한 개 실패해도 나머지는 계속
            fail.append(label)
    try:
        (out / "무료글씨체_라이선스.txt").write_text(_LICENSE_NOTE, encoding="utf-8")
    except OSError:
        pass
    return {"got": got, "skip": skip, "fail": fail}


def installed(fonts_dir=None) -> list:
    """설치된 무료 글씨체 파일 스템 목록 (UI 표시용)."""
    out = Path(fonts_dir) if fonts_dir else Path(DEFAULT_FONTS_DIR)
    return [Path(f).stem for f, _, _ in FONTS if (out / f).is_file()]
