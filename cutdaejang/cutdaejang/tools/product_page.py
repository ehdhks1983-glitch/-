"""상품 페이지(쿠팡·스마트스토어 등) 자동 수집 — 링크 하나로 사진·제목·설명 (v0.92).

수집 경로 3단계:
  ① 일반 요청 — fetch_web과 같은 브라우저형 UA로 한 번 요청, 열리면 그대로 파싱
  ② PC에 설치된 엣지/크롬을 헤드리스로 돌려 렌더된 DOM을 파싱
     (UA를 위장하지 않는다 — 헤드리스임을 그대로 알리고, 차단되면 즉시 포기)
  ③ 둘 다 막히면 ValueError로 정직하게 안내 → 화면에서는 페이지 복사→붙여넣기 폴백

사진 파일 자체는 공개 CDN(coupangcdn·pstatic)이라 주소만 얻으면 내려받아진다.
"""

from __future__ import annotations

import html as _html
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# 호스트 목록은 fetch_web 한 곳에서만 관리한다 (v1.12). fetch_web은 표준
# 라이브러리만 import하므로 순환 import가 생기지 않는다(product_page → fetch_web
# 단방향). 아래 함수들 안의 지연 import(UA 공유 등)는 그대로 둔다.
from .fetch_web import SHOP_HOSTS, SHORTENER_HOSTS

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_SHOP_HOSTS = SHOP_HOSTS          # 🛒 원본은 fetch_web.SHOP_HOSTS 하나뿐
_SHORT_HOSTS = SHORTENER_HOSTS    # 🔗 열어봐야 정체를 아는 단축 도메인

# 상품 사진이 올라가는 공개 CDN — 페이지 어디에 있든 주소 패턴으로 전부 긁는다
_IMG_RE = re.compile(
    r"(?:https?:)?//(?:thumbnail|image|static)\d*\.coupangcdn\.com/[^\s\"'<>\\)]+?"
    r"\.(?:jpg|jpeg|png|webp)|"
    # 🟢 v1.12: 네이버(스마트스토어) 상품 사진은 확장자 없이 ?type=w860 같은 크기
    # 쿼리만 붙는 주소가 흔해, .jpg/.png로 끝나는 것만 훑던 이 규칙이 통째로 놓쳤다.
    # pstatic의 phinf 계열(상품·상세 사진 CDN)에 한해 확장자 없는 주소도 잡는다 —
    # 다른 CDN까지 풀면 스크립트·아이콘 주소가 섞인다.
    r"(?:https?:)?//[a-z0-9-]*phinf\.pstatic\.net/[^\s\"'<>\\)]{8,}|"
    r"(?:https?:)?//cdn\.011st\.com/[^\s\"'<>\\)]+?\.(?:jpg|jpeg|png|webp)|"
    r"(?:https?:)?//gdimg\.gmarket\.co\.kr/[^\s\"'<>\\)]+?\.(?:jpg|jpeg|png|webp)|"
    r"(?:https?:)?//image\.auction\.co\.kr/[^\s\"'<>\\)]+?\.(?:jpg|jpeg|png|webp)|"
    r"(?:https?:)?//sitem\.ssgcdn\.com/[^\s\"'<>\\)]+?\.(?:jpg|jpeg|png|webp)", re.I)
# 스티커·아이콘 CDN은 상품 사진이 아니다 (v1.12 — pstatic 수집 범위를 넓히며 추가)
_JUNK_IMG = ("logo", "icon", "sprite", "banner", "btn_", "/common/", "blank.",
             "storep-phinf.", "gfmarket-phinf.", "ssl.pstatic.net")


class ShopBlockedError(ValueError):
    """상품 페이지가 프로그램 접속을 차단 — 화면에서 복사→붙여넣기 안내용."""


def _host_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit((url or "").strip()).netloc.lower().split(":")[0]
    except ValueError:
        return ""


def _host_in(host: str, hosts: Tuple[str, ...]) -> bool:
    # fetch_web와 같은 방식 — 점 경계로 비교해 'mycoupang.com'이 걸리지 않게
    return bool(host) and any(host == h or host.endswith("." + h) for h in hosts)


def is_shop_url(url: str) -> bool:
    return _host_in(_host_of(url), _SHOP_HOSTS)


def is_short_url(url: str) -> bool:
    """naver.me 같은 단축·전달 링크인가 — 열어봐야 상품인지 블로그인지 안다."""
    return _host_in(_host_of(url), _SHORT_HOSTS)


# 중간 안내 페이지(자동 이동)에서 진짜 주소 찾기 — 단축 도메인에서만 쓴다
_REDIRECT_RE = re.compile(
    r"""(?:http-equiv=["']refresh["'][^>]*?url=|location\.(?:href|replace)\s*[=(]\s*)"""
    r"""["']?([^"'\s>)]{4,400})""", re.I)


def _landing_url(url: str, timeout: float = 8.0) -> str:
    """단축링크가 실제로 가리키는 주소만 확인 — 페이지 본문은 받지 않는다.

    HEAD가 막히면 GET으로 앞부분만 읽고, 중간 안내 페이지(meta refresh·
    location.href)면 그 주소를 돌려준다. 못 알아내면 빈 문자열(=판정 포기).
    UA는 평소와 같은 정직한 값이고, 차단이면 그대로 포기한다(우회 없음).
    """
    headers = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5"}
    for method in ("HEAD", "GET"):
        body = ""
        try:
            req = urllib.request.Request(url, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                landed = r.geturl() or url
                if method == "GET":
                    body = r.read(16_000).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            landed = getattr(e, "url", "") or url
            if landed != url:
                return landed          # 최종 주소만 알면 충분(차단 안내는 뒷단계에서)
            continue
        except Exception:  # noqa: BLE001 — 판정 실패는 '쇼핑 아님'으로 조용히
            continue
        if landed != url:
            return landed
        m = _REDIRECT_RE.search(body)
        if m:
            return urllib.parse.urljoin(landed, m.group(1))
    return ""


def resolve_shop_url(url: str, timeout: float = 8.0) -> str:
    """상품 링크면 '열어야 할 주소', 아니면 빈 문자열 (v1.12).

    - 이미 쇼핑 호스트면 원본 그대로 (파트너스 추적 링크를 갈아치우지 않는다)
    - naver.me 등 **알려진 단축 도메인일 때만** 한 번 따라가 최종 host로 재판정
    - 그 밖의 주소는 네트워크를 전혀 건드리지 않는다 → 블로그 수집 흐름 그대로
    """
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return ""
    if is_shop_url(u):
        return u
    if not is_short_url(u):
        return ""
    landed = _landing_url(u, timeout=timeout)
    return landed if landed and is_shop_url(landed) else ""


def _fetch_html(url: str, timeout: float = 20.0, ua: str = "",
                referer: str = "") -> Tuple[str, str]:
    """일반 요청으로 HTML 받기 → (html, 최종 URL). 단축링크 리다이렉트도 따라간다."""
    headers = {
        "User-Agent": ua or _UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final = r.geturl() or url
        raw = r.read(3_000_000)
    return raw.decode("utf-8", errors="replace"), final


def _mobile_variant(url: str) -> str:
    """쿠팡 데스크톱 상품 주소 → 모바일 페이지 주소 (해당 없으면 빈 문자열)."""
    try:
        sp = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if sp.netloc.lower() in ("www.coupang.com", "coupang.com"):
        return urllib.parse.urlunsplit((sp.scheme or "https", "m.coupang.com",
                                        sp.path, sp.query, ""))
    return ""


def _browser_candidates() -> List[str]:
    import os  # noqa: PLC0415

    cands: List[str] = []
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        for base in (pf, pf86):
            cands.append(base + r"\Microsoft\Edge\Application\msedge.exe")
            cands.append(base + r"\Google\Chrome\Application\chrome.exe")
        if local:
            cands.append(local + r"\Google\Chrome\Application\chrome.exe")
    else:
        import shutil  # noqa: PLC0415

        for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
            p = shutil.which(name)
            if p:
                cands.append(p)
    return [c for c in cands if Path(c).is_file()]


def login_profile_dir() -> Path:
    """🔐 컷대장 전용 브라우저 프로필 — 회원님이 여기에 한 번 로그인해 둔다 (v1.12).

    쿠팡·네이버 상품 페이지는 **로그인한 브라우저**에게만 사진이 든 전체 페이지를
    준다. 지금까지는 매번 빈 임시 프로필로 헤드리스를 띄워 로그인이 하나도 없었고,
    그래서 "블로그(제휴) 프로그램에서는 사진이 잘 들어오는데 컷대장만 0장"이었다.
    (그 프로그램은 '크롬 열기'로 회원님 브라우저를 띄우고 거기서 로그인하게 한다.)

    ⚠ 이건 봇 차단 우회가 아니다 — 회원님 본인의 브라우저·본인의 로그인을 쓴다.
    자동 로그인·캡차 우회 같은 것은 하지 않는다.
    """
    import os  # noqa: PLC0415

    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "cutdaejang" / "browser_profile"


def logged_in_hosts() -> List[str]:
    """로그인 프로필에 쿠키가 남아 있는 쇼핑몰 목록 (화면 표시용).

    쿠키 값은 읽지 않는다 — 어느 사이트에 로그인돼 있는지 **호스트 이름만** 본다.
    """
    import shutil  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    prof = login_profile_dir()
    db = next((p for p in (prof / "Default" / "Network" / "Cookies",
                           prof / "Default" / "Cookies") if p.is_file()), None)
    if not db:
        return []
    tmp = Path(tempfile.mkdtemp()) / "c.db"        # 브라우저가 켜져 있으면 잠겨 있음
    try:
        shutil.copy2(db, tmp)
        with sqlite3.connect(f"file:{tmp}?mode=ro", uri=True) as con:
            hosts = {str(r[0]).lstrip(".").lower()
                     for r in con.execute("SELECT DISTINCT host_key FROM cookies")}
    except Exception:  # noqa: BLE001 — 못 읽으면 '모름'으로
        return []
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    known = {"coupang.com": "쿠팡", "naver.com": "네이버",
             "11st.co.kr": "11번가", "gmarket.co.kr": "지마켓", "auction.co.kr": "옥션"}
    return sorted({ko for h in hosts for dom, ko in known.items()
                   if h == dom or h.endswith("." + dom)})


def open_login_browser(url: str = "https://www.coupang.com/") -> str:
    """🌐 [내 크롬 열기] — 전용 프로필로 브라우저를 **눈에 보이게** 띄운다 (v1.12).

    회원님이 그 창에서 쿠팡·네이버에 로그인하면 세션이 이 프로필에 남고, 이후
    사진 수집이 같은 로그인 상태로 페이지를 읽는다. 실패하면 사유 문자열 반환.
    """
    import subprocess  # noqa: PLC0415

    exes = _browser_candidates()
    if not exes:
        return "PC에서 크롬·엣지를 찾지 못했어요 — 크롬을 설치한 뒤 다시 눌러주세요"
    prof = login_profile_dir()
    prof.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(
            [exes[0], f"--user-data-dir={prof}", "--no-first-run",
             "--no-default-browser-check", "--new-window", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001
        return f"브라우저를 열지 못했어요: {str(e)[:120]}"
    return ""


def _collect_profile() -> str:
    """수집용 프로필 경로 — 로그인 프로필이 있으면 **복제해서** 쓴다 (v1.12).

    같은 프로필로 두 개를 동시에 띄울 수 없어(크로미움 제약), 로그인 창을 켜 둔
    채로도 수집이 되도록 쿠키·설정만 임시 폴더로 복사한다. 로그인해 둔 적이
    없으면 예전처럼 빈 임시 프로필(cutdaejang_headless)을 쓴다.
    """
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    src = login_profile_dir()
    if not (src / "Default").is_dir():
        return os.path.join(tempfile.gettempdir(), "cutdaejang_headless")
    dst = Path(tempfile.gettempdir()) / "cutdaejang_session"
    try:
        shutil.rmtree(dst, ignore_errors=True)
        (dst / "Default" / "Network").mkdir(parents=True, exist_ok=True)
        for rel in ("Local State", "Default/Preferences", "Default/Cookies",
                    "Default/Network/Cookies", "Default/Login Data"):
            s = src / rel
            if s.is_file():
                shutil.copy2(s, dst / rel)
    except Exception:  # noqa: BLE001 — 복제 실패면 빈 프로필로 (기존 동작)
        return os.path.join(tempfile.gettempdir(), "cutdaejang_headless")
    return str(dst)


def _browser_args(exe: str, url: str) -> List[str]:
    """헤드리스 실행 인자 — 전용 프로필을 쓴다 (v0.97 핵심 수정 → v1.12 로그인).

    크로미움은 같은 프로필의 브라우저가 이미 떠 있으면 새 프로세스가 기존 창에
    신호만 보내고 즉시 종료한다 → 사용자가 엣지/크롬을 켜 둔 채면 --dump-dom이
    빈손으로 끝났다. 전용 --user-data-dir로 항상 독립 인스턴스를 띄운다.

    v1.12: [내 크롬 열기]로 로그인해 둔 프로필이 있으면 그 **복제본**을 쓴다 —
    로그인 상태 그대로 페이지를 읽어야 쿠팡·네이버가 사진을 다 내려준다.
    """
    return [exe, "--headless=new", "--disable-gpu", "--disable-extensions",
            "--no-first-run", "--no-default-browser-check", "--mute-audio",
            f"--user-data-dir={_collect_profile()}", "--window-size=1280,2400",
            "--virtual-time-budget=12000", "--timeout=30000", "--dump-dom", url]


def _browser_dump(url: str, timeout: float = 50.0) -> str:
    """설치된 엣지/크롬 헤드리스로 렌더된 DOM 받기.

    UA를 바꾸지 않는다(HeadlessChrome으로 자신을 알림) — 사이트가 헤드리스를
    차단하기로 했다면 그 결정을 존중하고 빈 문자열을 돌려준다.
    """
    # timeout은 브라우저 '각각'이 아니라 전체 후보에 대한 총 예산이다. 엣지와
    # 크롬이 모두 설치된 PC에서 각각 50초씩 기다려 UI가 수 분 멈추는 일을 막는다.
    deadline = time.monotonic() + max(1.0, float(timeout))
    for exe in _browser_candidates():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            r = subprocess.run(_browser_args(exe, url),
                               capture_output=True, timeout=max(1.0, remaining))
            out = (r.stdout or b"").decode("utf-8", errors="replace")
            if len(out) > 3000 and "<html" in out.lower():
                return out
        except Exception:  # noqa: BLE001 — 다음 브라우저 후보로
            continue
    return ""


def _meta(html: str, prop: str) -> str:
    for pat in (
        r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop)
        + r'["\'][^>]*?content=["\']([^"\']*)["\']',
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*?(?:property|name)=["\']'
        + re.escape(prop) + r'["\']',
    ):
        m = re.search(pat, html, re.I | re.S)
        if m and m.group(1).strip():
            import html as _h  # noqa: PLC0415

            return _h.unescape(m.group(1).strip())
    return ""


def extract_image_urls(html: str, limit: int = 12, base_url: str = "") -> List[str]:
    # 🧩 v1.04: 상품 사진 주소는 페이지 JSON 안에 "https:\/\/…"(이스케이프)로
    # 실리는 일이 흔한데 그동안 못 잡았다 — 메타태그의 대표 사진 1장만 오던
    # 주범 (사용자 리포트 "아직도 한 장만 들어오네"). 이스케이프를 풀고 긁는다.
    html = _html.unescape(
        ((html or "").replace("\\/", "/")
         .replace("\\u002F", "/").replace("\\u002f", "/")))
    out: List[str] = []
    seen = set()

    def add(raw: str) -> None:
        u = _html.unescape((raw or "").strip().strip("\"'"))
        if not u or u.startswith(("data:", "blob:")):
            return
        if u.startswith("//"):
            u = "https:" + u
        elif base_url:
            u = urllib.parse.urljoin(base_url, u)
        if not u.startswith(("http://", "https://")):
            return
        low = u.lower()
        if any(j in low for j in _JUNK_IMG):
            return
        key = u.replace(" ", "%20")
        if key in seen:
            return
        seen.add(key)
        out.append(key)

    # 태그에 원본/고해상도 후보가 명시됐으면 페이지에 먼저 등장하는 작은
    # ``src`` 썸네일보다 우선한다.
    for tag_m in re.finditer(r"<img\b[^>]*>", html or "", re.I | re.S):
        tag = tag_m.group(0)
        attrs = {
            k.lower(): v for k, _q, v in re.findall(
                r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", tag, re.I | re.S)
        }
        for key in ("data-original", "data-lazy-src", "data-src",
                    "data-image", "data-lazy"):
            add(attrs.get(key, ""))
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
        srcset = attrs.get("data-srcset") or attrs.get("srcset") or ""
        if srcset:
            choices = [x.strip().split()[0] for x in srcset.split(",") if x.strip()]
            for choice in reversed(choices):       # 가장 큰 폭/배율 후보 우선
                add(choice)
                if len(out) >= limit:
                    break
        add(attrs.get("src", ""))
        if len(out) >= limit:
            break

    # <img> 밖의 상품 JSON/스크립트에만 들어 있는 CDN 주소도 뒤이어 수집한다.
    if len(out) < limit:
        for m in _IMG_RE.finditer(html or ""):
            add(m.group(0))
            if len(out) >= limit:
                break
    return out


def parse_product(html: str, base_url: str = "") -> dict:
    """렌더된(또는 원본) HTML → {title, text, images(url 목록)}."""
    title = _meta(html, "og:title")
    if not title:
        m = re.search(r"<title[^>]*>([^<]{2,120})</title>", html or "", re.I)
        title = (m.group(1).strip() if m else "")
    desc = _meta(html, "og:description") or _meta(html, "description")
    imgs = extract_image_urls(html, base_url=base_url)
    og_img = _meta(html, "og:image")
    if og_img:
        og_img = urllib.parse.urljoin(base_url, og_img) if base_url else (
            "https:" + og_img if og_img.startswith("//") else og_img)
    if og_img.startswith("http"):
        # 대표 사진은 태그/JSON 수집 중 이미 발견됐더라도 항상 첫 장으로 보낸다.
        # lazy 원본 우선 수집으로 순서가 바뀐 뒤 og:image가 중간에 남는 회귀 방지.
        imgs = [u for u in imgs if u != og_img]
        imgs.insert(0, og_img)
    price = ""
    pm = re.search(r'"(?:salePrice|discountedPrice|lprice|price)"\s*:\s*"?(\d{3,9})', html or "")
    if pm:
        price = format(int(pm.group(1)), ",")
    text = title
    if price:
        text += f"\n가격: 약 {price}원"
    if desc:
        text += "\n" + desc
    return {"title": title[:80], "text": text.strip(), "images": imgs[:12]}


def _usable(parsed: dict) -> bool:
    """이 단계 결과를 쓸 만한가 — 사진 0장이어도 제목+설명 30자면 통과한다.

    ⚠ 이 느슨함은 실수가 아니라 '사진은 못 가져와도 대본은 만들어 준다'는
    붙여넣기 폴백을 살리려는 것이다. 여기서 실패로 바꾸면 링크만 넣은 회원님이
    대본까지 통째로 잃는다. 대신 그동안 **사진만 0장인 상태가 조용히 성공**해
    회원님이 알 수 없던 게 진짜 문제였으므로, 아래 photo_note()로 반드시 알린다.
    """
    return bool(parsed.get("title")) and (bool(parsed.get("images"))
                                          or len(parsed.get("text") or "") >= 30)


def photo_note(parsed: dict) -> str:
    """사진이 0장이면 그 사실과 단계별 숫자를 한 줄로 — 있으면 빈 문자열 (v1.12)."""
    if parsed.get("images"):
        return ""
    detail = parsed.get("via_detail") or ""
    return ("페이지는 열렸지만 사진 주소를 한 장도 못 찾았어요"
            + (f" [{detail}]" if detail else ""))


def collect_product(url: str, progress_cb: Optional[Callable] = None) -> dict:
    """링크 하나로 상품 정보 수집 → {title, text, images, final_url, via}."""
    say = progress_cb or (lambda m: None)
    say("상품 페이지 여는 중…")
    html_text, final = "", (url or "").strip()
    stages = []                       # 🩺 단계별 결과 (v1.08) — "왜 1장인지" 화면에 보이게
    try:
        html_text, final = _fetch_html(final)
        via = "직접"
    except urllib.error.HTTPError as e:
        final = getattr(e, "url", "") or getattr(e, "filename", "") or final
        via = ""
        stages.append(f"직접 차단({e.code})")
    except Exception:  # noqa: BLE001 — 브라우저 경로로 넘어감
        via = ""
        stages.append("직접 실패")
    parsed = parse_product(html_text, final) if html_text else {}
    if html_text:
        stages.append(f"직접 {len(parsed.get('images') or [])}장")
    # 📱 블로그 수집과 같은 요청 레시피로 모바일 페이지도 시도 (v1.06 — 사용자
    # 지시 "블로그봇의 쿠팡 크롤링 방식을 적용"): 블로그가 사진 5장이 잘 되는
    # 이유가 fetch_web의 모바일 UA(+cutdaejang 표식)·Referer 레시피라, 상품
    # 수집에도 같은 방식을 얹는다. 모바일 페이지는 가볍고 사진이 본문에 그대로.
    if len(parsed.get("images") or []) < 3:
        m_url = _mobile_variant(final)
        if m_url:
            from . import fetch_web  # noqa: PLC0415 — 블로그와 '같은' UA 한 곳 유지
            say("모바일 페이지에서 사진 찾는 중…")
            try:
                m_html, _mf = _fetch_html(m_url, ua=fetch_web._UA, referer=final)
                p_m = parse_product(m_html, m_url)
                stages.append(f"모바일 {len(p_m.get('images') or [])}장")
                merged_m = list(dict.fromkeys(
                    (p_m.get("images") or []) + (parsed.get("images") or [])))[:12]
                if _usable(p_m) and not (parsed and _usable(parsed)):
                    parsed, via = p_m, "모바일"
                if merged_m:
                    parsed = parsed or {}
                    parsed["images"] = merged_m
            except Exception:  # noqa: BLE001 — 모바일 실패는 다음 단계로
                stages.append("모바일 차단")
    # 🖼 사진이 '적으면'(3장 미만) 브라우저로 재시도 (v1.04) — 상품 페이지는
    # 사진을 JS로 늦게 그려서 직접 요청 HTML엔 대표 사진 1장만 오는 일이 흔한데,
    # v0.97은 0장일 때만 재시도해 1장이면 그대로 끝났다 (사용자 리포트
    # "아직도 한 장만 들어오네"). 두 경로에서 모은 사진은 합집합으로 합친다.
    if not (parsed and _usable(parsed)) or len(parsed.get("images") or []) < 3:
        say("사진을 더 실으려고 PC의 엣지/크롬으로 페이지 읽는 중… (최대 30초)")
        dumped = _browser_dump(final)
        if dumped:
            p2 = parse_product(dumped, final)
            stages.append(f"브라우저 {len(p2.get('images') or [])}장")
            merged = list(dict.fromkeys(
                (p2.get("images") or []) + (parsed.get("images") or [])))[:12]
            if _usable(p2):
                p2["images"] = merged
                parsed, via = p2, "브라우저"
            elif parsed and _usable(parsed) and merged:
                parsed["images"] = merged
        else:
            stages.append("브라우저 차단")
    if not (parsed and _usable(parsed)):
        raise ShopBlockedError(
            "쇼핑몰이 프로그램의 자동 접속을 차단했어요"
            + (f" ({' · '.join(stages)})" if stages else "")
            + ". 상품 페이지를 브라우저로 열어뒀으니 Ctrl+A(전체 선택) → "
            "Ctrl+C(복사) 한 뒤, 이 화면에서 Ctrl+V(붙여넣기) 하세요 — "
            "사진·설명이 한 번에 들어와요")
    parsed.update(final_url=final, via=via or "직접",
                  via_detail=" · ".join(stages))
    # 🖼 '사진만 0장'인 채 조용히 성공하던 구멍 (v1.12) — 호출한 쪽이 반드시
    # 회원님께 알리도록 이유를 함께 돌려준다. 대본은 지금처럼 그대로 만들어진다.
    parsed["photo_note"] = photo_note(parsed)
    return parsed


def download_images(urls: List[str], dest_dir, limit: int = 12,
                    min_bytes: int = 12_000, referer: str = "") -> Tuple[List[str], int]:
    """사진 URL들을 고화질 우선으로 내려받아 dest/img_NN.ext 로 저장 → (경로들, 스킵 수)."""
    from . import coupang_api, fetch_web, naver_shop_api  # noqa: PLC0415

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    saved: List[str] = []
    skipped = 0
    for u in list(dict.fromkeys([x for x in urls if str(x or "").startswith("http")]))[:limit]:
        cands = [c for c in (coupang_api.hi_res_image(u),
                             naver_shop_api.hi_res_image(u)) if c != u] + [u]
        ok = False
        for cand in dict.fromkeys(cands):
            try:
                raw = fetch_web.fetch_bytes(cand, referer=referer)
            except Exception:  # noqa: BLE001 — 다음 후보로
                continue
            ext = fetch_web.sniff_image_ext(raw) or ""
            if ext not in ("jpg", "jpeg", "png", "webp", "bmp") or len(raw) < min_bytes:
                continue                       # 고화질 변환 URL 실패면 원본 후보도 시도
            p = dest / f"img_{len(saved) + 1:02d}.{ext}"
            p.write_bytes(raw)
            saved.append(str(p))
            ok = True
            break
        if not ok:
            skipped += 1
    return saved, skipped
