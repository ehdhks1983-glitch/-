"""무료 한글 글씨체 자동 받기 (v0.63 → v1.38 10종) — 전부 «재배포 허용»만.

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

import struct
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


def font_names(path) -> set:
    """폰트 파일이 «스스로 말하는» 이름들 (패밀리 + 풀네임).

    🔴 v1.38 (목록 76) — 이게 왜 필요한가.
    자막을 그리는 libass는 «이름»으로 폰트를 찾는다. 이름이 한 글자라도 다르면
    오류를 내지 않고 **조용히 기본 글씨로 그린다.** 회원님은 글씨체를 골랐는데
    영상만 다르게 나온다 — 무엇이 잘못됐는지 알 길이 없다.
    실제로 그런 게 두 개 있었다(Pretendard-Bold · 나눔손글씨 펜).
    그래서 받은 파일에서 이름을 직접 읽어 별칭과 맞는지 확인한다.

    표준 라이브러리만 쓴다(struct). 못 읽으면 빈 집합 — 확인을 못 할 뿐 막지 않는다.
    """
    try:
        b = Path(path).read_bytes()
        num = struct.unpack(">H", b[4:6])[0]
        tables = {}
        for i in range(num):
            s = 12 + i * 16
            tag, _, off, ln = struct.unpack(">4sIII", b[s:s + 16])
            tables[tag] = (off, ln)
        off, _ = tables[b"name"]
        _, cnt, so = struct.unpack(">HHH", b[off:off + 6])
        out = set()
        for i in range(cnt):
            s = off + 6 + i * 12
            pid, _eid, lid, nid, ln, no = struct.unpack(">HHHHHH", b[s:s + 12])
            if pid == 3 and lid == 0x409 and nid in (1, 4):   # 영문 패밀리·풀네임
                out.add(b[off + so + no:off + so + no + ln].decode("utf-16-be", "ignore"))
        return out
    except Exception:  # noqa: BLE001 — 확인용이라 실패해도 받기는 계속된다
        return set()


def check_names(fonts_dir=None) -> list:
    """별칭과 파일의 실제 이름이 어긋난 글씨체 목록 [(스템, 별칭, 실제이름들)]."""
    from .. import presets  # noqa: PLC0415

    out = Path(fonts_dir) if fonts_dir else Path(DEFAULT_FONTS_DIR)
    bad = []
    for fname, _label, _url in FONTS:
        p = out / fname
        if not p.is_file():
            continue
        stem = Path(fname).stem
        alias = presets.FONT_FAMILY_ALIASES.get(stem)
        names = font_names(p)
        if alias and names and alias not in names:
            bad.append((stem, alias, sorted(names)))
    return bad


# 🌏 병기 자막 전용 글씨체 (v1.45 목록 88) — 한글 글씨체에는 가나·간체 한자가
#   없어 병기 언어를 고르면 이것만 «따로» 받는다. 기본 「받기」(FONTS)에 안 끼운
#   이유: 합쳐서 ~16MB — 병기를 안 쓰는 대다수에게 물리기엔 크다.
#   URL은 css2 API(구형 UA)로 실물 확인 후 고정 (2026-08, name1 검증 완료).
LANG_FONTS = {
    "ja": ("NotoSansJP.ttf", "Noto Sans JP",
           "https://fonts.gstatic.com/s/notosansjp/v56/-F6jfjtqLzI2JPCgQBnw7HFyzSD-AsregP8VFPYk75s.ttf"),
    "zh": ("NotoSansSC.ttf", "Noto Sans SC",
           "https://fonts.gstatic.com/s/notosanssc/v40/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaGzjCnYw.ttf"),
}


def lang_font_installed(lang: str, fonts_dir=None) -> bool:
    """병기 언어 글씨체가 준비돼 있나 — en은 모든 글씨체가 라틴을 갖고 있어 True."""
    if lang not in LANG_FONTS:
        return True
    out = Path(fonts_dir) if fonts_dir else Path(DEFAULT_FONTS_DIR)
    f = out / LANG_FONTS[lang][0]
    return f.is_file() and f.stat().st_size > 100_000


def fetch_lang(lang: str, fonts_dir=None) -> dict:
    """병기 언어 글씨체 1종 받기 — {"ok", "file", "mismatch"}"""
    if lang not in LANG_FONTS:
        return {"ok": True, "file": "", "mismatch": False}
    fname, fam, url = LANG_FONTS[lang]
    out = Path(fonts_dir) if fonts_dir else Path(DEFAULT_FONTS_DIR)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / fname
    if not (dest.is_file() and dest.stat().st_size > 100_000):
        fetch(url, dest)
    ok = dest.is_file() and dest.stat().st_size > 100_000
    mism = ok and fam not in font_names(dest)   # 이름표가 다르면 «조용한 폴백» 위험
    return {"ok": ok and not mism, "file": str(dest), "mismatch": mism}


def fetch_all(fonts_dir=None, progress=None) -> dict:
    """글씨체 전부 받기 — 반환 {"got", "skip", "fail": [이름...], "mismatch": [...]}"""
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
    # 🔎 받은 파일이 «우리가 부르는 이름»을 정말 갖고 있는지 (위 font_names 설명 참고).
    #    배포처가 나중에 이름을 바꿔도 «조용한 실패»가 아니라 눈에 보이게 된다.
    return {"got": got, "skip": skip, "fail": fail,
            "mismatch": [s for s, _a, _n in check_names(out)]}


def installed(fonts_dir=None) -> list:
    """설치된 무료 글씨체 파일 스템 목록 (UI 표시용)."""
    out = Path(fonts_dir) if fonts_dir else Path(DEFAULT_FONTS_DIR)
    return [Path(f).stem for f, _, _ in FONTS if (out / f).is_file()]
