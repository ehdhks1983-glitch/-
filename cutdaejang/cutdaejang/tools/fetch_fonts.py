"""무료 한글 글씨체 자동 받기 (v0.63 → v1.38 8종) — 전부 «재배포 허용»만.

fetch_bgm과 같은 패턴: 이미 있으면 건너뛰고, 받은 파일은 resources/fonts에.
URL은 배포처의 버전 고정 주소라 수년간 안정적이다.

⚠ 여기 넣는 기준은 «무료»가 아니라 «재배포·번들 허용»이다. 이건 팔리는
프로그램이고, 프로그램이 폰트를 대신 받아 주는 것은 배포에 가깝다.
  · OFL (Pretendard · Google Fonts 5종 · Noto Sans KR) — 허용
  · 에스코어드림 — S-Core 공식 «번들·재배포 가능(저작권 안내 포함)»
  · ❌ 배민 한나체는 넣지 않았다. 배민 글꼴 중 도현·주아는 Google Fonts에
    OFL로 올라와 있는데 한나만 없다 — 즉 OFL로 «풀지 않은» 글꼴이다.
    쓰고 싶은 분은 배민 공식 사이트에서 직접 받아 이 폴더에 넣으면 된다.
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
    # ⬇ v1.38 (목록 76) — 굵기 고르기 + «실패 없는 기본»
    ("Pretendard-Bold.otf", "프리텐다드 Bold (기본보다 얇게)",
     "https://raw.githubusercontent.com/orioncactus/pretendard/main"
     "/packages/pretendard/dist/public/static/Pretendard-Bold.otf"),
    ("Pretendard-SemiBold.otf", "프리텐다드 SemiBold (제일 얇게)",
     "https://raw.githubusercontent.com/orioncactus/pretendard/main"
     "/packages/pretendard/dist/public/static/Pretendard-SemiBold.otf"),
    ("NotoSansKR-Bold.ttf", "노토산스 KR Bold (실패 없는 기본)",
     "https://fonts.gstatic.com/s/notosanskr/v39"
     "/PbyxFmXiEBPT4ITbgNA5Cgms3VYcOA-vvnIzzg01eLQ.ttf"),
    ("SCDreamBold.otf", "에스코어드림 6 Bold (깔끔한 정보형)",
     "https://raw.githubusercontent.com/fonts-archive/S-CoreDream/main/SCDreamBold.otf"),
    ("SCDreamHeavy.otf", "에스코어드림 8 Heavy (굵은 강조)",
     "https://raw.githubusercontent.com/fonts-archive/S-CoreDream/main/SCDreamHeavy.otf"),
]

_LICENSE_NOTE = """이 폴더의 글씨체는 모두 «재배포가 허용된» 무료 폰트입니다.
영상·상업적 사용 가능, 폰트 파일 자체의 재판매만 금지됩니다.

■ SIL Open Font License (OFL)
  · Google Fonts (fonts.google.com)
    Black Han Sans · Jua · Do Hyeon · Gugi · Nanum Pen Script · Noto Sans KR
  · Pretendard — https://github.com/orioncactus/pretendard (길형진, OFL 1.1)

■ 에스코어드림 (S-Core Dream) — https://s-core.co.kr/company/font/
  지적 재산권은 S-Core에 있습니다. 저작권 안내를 포함해 번들·재배포가
  허용되며, 파일을 수정하거나 폰트를 판매하는 것은 금지됩니다.
  배포되는 형태 그대로 사용합니다.

■ 여기 없는 글씨체
  배민 한나체는 넣지 않았습니다. 배민 글꼴 중 도현·주아는 Google Fonts에
  OFL로 올라와 있지만 한나는 없습니다. 쓰시려면 배민 공식 사이트
  (font.woowahan.com)에서 직접 받아 이 폴더에 넣으세요.
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
