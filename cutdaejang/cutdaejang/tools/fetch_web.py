"""🔗 블로그 글 가져오기 (v0.78) — 글 제목·본문·사진을 내려받아 사진 영상 재료로.

표준 라이브러리만 사용(urllib + html.parser). 네이버 블로그는 모바일 페이지
(m.blog.naver.com)가 iframe 없이 본문을 바로 주므로 그 형태로 정규화해 가져온다.
쿠팡 등 봇 차단 사이트는 우회하지 않고, 무엇이 문제인지 친절히 알려주기만 한다.
"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, List, Optional

# 일반 브라우저형 UA — 위장 목적이 아니라, 기본 파이썬 UA를 일부 CDN이 거절해서.
_UA = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36 cutdaejang")
_PAGE_CAP = 3_000_000        # 페이지 최대 3MB
_IMG_CAP = 15_000_000        # 이미지 1장 최대 15MB
_IMG_MIN = 10_000            # 10KB 미만은 아이콘·빈 이미지로 보고 스킵
_TEXT_CAP = 8_000            # 본문 저장 상한(자)

# 제휴·상품 링크로 인식할 호스트 (제품 프로필 link 칸 자동 채움용)
_PARTNER_HOSTS = ("coupa.ng", "link.coupang.com", "coupang.com",
                  "naver.me", "smartstore.naver.com", "shopping.naver.com")
# 스티커·이모티콘 CDN — 본문 사진이 아님
_STICKER_HOSTS = ("storep-phinf.pstatic.net", "gfmarket-phinf.pstatic.net")
# 프로그램 접근을 막는 것으로 알려진 상품 페이지 호스트 → 전용 안내
_BLOCKED_SHOP_HOSTS = ("coupang.com", "coupa.ng", "link.coupang.com")

_NAVER_BLOG_RE = re.compile(
    r"https?://(?:m\.)?blog\.naver\.com/(?P<id>[A-Za-z0-9_\-.]+)/(?P<log>\d+)")
_NAVER_POSTVIEW_RE = re.compile(
    r"https?://(?:m\.)?blog\.naver\.com/PostView\.(?:naver|nhn)")


def normalize_url(url: str) -> str:
    """네이버 블로그 주소를 모바일(m.blog) 글 주소로 통일. 그 외는 fragment만 제거."""
    url = (url or "").strip()
    url = url.split("#", 1)[0]
    m = _NAVER_BLOG_RE.match(url)
    if m:
        return f"https://m.blog.naver.com/{m.group('id')}/{m.group('log')}"
    if _NAVER_POSTVIEW_RE.match(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        blog_id = (q.get("blogId") or [""])[0]
        log_no = (q.get("logNo") or [""])[0]
        if blog_id and log_no:
            return f"https://m.blog.naver.com/{blog_id}/{log_no}"
    return url


class _ArticleParser(HTMLParser):
    """글 1편에서 제목·본문 텍스트·이미지 URL·링크를 뽑는 관대한 파서.

    본문 우선순위: 네이버 스마트에디터(se-main-container) 안 텍스트 → <p> 전체
    → og:description. 이미지는 lazy 로딩 속성(data-lazy-src 등)을 src보다 우선.
    """

    _SKIP_TAGS = {"script", "style", "noscript", "template"}
    _LAZY_ATTRS = ("data-lazy-src", "data-src", "data-original", "data-image-src")
    # 닫는 태그가 없는(void) 요소 — 본문 컨테이너 깊이 계산에서 제외
    _VOID = {"img", "br", "meta", "link", "input", "hr", "source", "area",
             "base", "col", "embed", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.og = {}
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._se_depth = 0          # se-main-container(스마트에디터 본문) 안 깊이
        self._se_text: List[str] = []
        self._p_depth = 0
        self._p_text: List[str] = []
        self.image_urls: List[str] = []
        self.links: List[str] = []

    # ── 태그 처리 ──────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "meta":
            prop = a.get("property") or a.get("name") or ""
            if prop.startswith("og:") and a.get("content"):
                self.og.setdefault(prop[3:], a["content"].strip())
            return
        if tag == "title":
            self._in_title = True
            return
        cls = a.get("class") or ""
        if tag not in self._VOID:                # 본문 컨테이너 깊이 — 여닫이 대칭 추적
            if self._se_depth:
                self._se_depth += 1
            elif "se-main-container" in cls or a.get("id") == "postViewArea":
                self._se_depth = 1               # 구버전 에디터(postViewArea)도 수용
        if tag == "p":
            self._p_depth += 1
        elif tag == "br" and (self._se_depth or self._p_depth):
            (self._se_text if self._se_depth else self._p_text).append("\n")
        elif tag == "img":
            src = ""
            for k in self._LAZY_ATTRS:           # lazy 속성이 원본 크기인 경우가 많음
                if (a.get(k) or "").strip():
                    src = a[k].strip()
                    break
            src = src or (a.get("src") or "").strip()
            if src:
                self.image_urls.append(src)
        elif tag == "a" and (a.get("href") or "").strip():
            self.links.append(a["href"].strip())

    def handle_startendtag(self, tag, attrs):    # <img .../> 자기닫힘도 동일 처리
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False
        if tag == "p":
            self._p_depth = max(0, self._p_depth - 1)
            (self._se_text if self._se_depth else self._p_text).append("\n")
        if self._se_depth and tag not in self._VOID:
            self._se_depth -= 1
            if self._se_depth == 0 or tag in ("div", "section"):
                self._se_text.append("\n")       # 블록 경계 = 줄바꿈

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title and data.strip():
            self.title += data.strip()
            return
        if self._se_depth:
            self._se_text.append(data)
        elif self._p_depth:
            self._p_text.append(data)


def _clean_text(parts: List[str]) -> str:
    text = "".join(parts)
    text = re.sub(r"[ \t​\xa0]+", " ", text)  # 공백·제로폭·nbsp 정리
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def parse_article_html(html: str, base_url: str) -> dict:
    """HTML → {title, text, image_urls, links, notes}. 네트워크 접근 없음(테스트 용이)."""
    p = _ArticleParser()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 — 깨진 HTML도 그때까지 모은 것으로 진행
        pass
    notes: List[str] = []
    title = (p.og.get("title") or p.title or "").strip()
    text = _clean_text(p._se_text) or _clean_text(p._p_text)
    if not text:
        text = (p.og.get("description") or "").strip()
        if text:
            notes.append("본문을 못 읽어 요약 설명(og:description)만 가져왔어요")
    imgs: List[str] = []
    seen = set()
    og_img = (p.og.get("image") or "").strip()
    # 본문에 사진이 있으면 og 대표 이미지는 제외 — 대부분 본문 첫 사진의 리사이즈
    # 복사본이라 장수가 1장 늘어나는 원인 (v0.79 사용자 리포트: 6장이 7장으로)
    candidates = p.image_urls if p.image_urls else ([og_img] if og_img else [])
    for u in candidates:
        u = urllib.parse.urljoin(base_url, u)
        low = u.lower()
        if not low.startswith(("http://", "https://")):
            continue                              # data: URI 등 제외
        parsed = urllib.parse.urlparse(low)
        if parsed.path.endswith(".gif"):
            continue                              # 움짤·스티커 제외
        if any(h in low for h in _STICKER_HOSTS):
            continue
        key = parsed.netloc + parsed.path         # ?type=w800 같은 크기 쿼리 무시하고 중복 제거
        if key not in seen:
            seen.add(key)
            imgs.append(u)
    links = []
    for u in p.links:
        u = urllib.parse.urljoin(base_url, u)
        host = urllib.parse.urlparse(u).netloc.lower()
        if any(host == h or host.endswith("." + h) for h in _PARTNER_HOSTS):
            links.append(u)
    links = list(dict.fromkeys(links))
    return {"title": title[:150], "text": text[:_TEXT_CAP],
            "image_urls": imgs, "links": links, "notes": notes}


def _friendly_http_error(url: str, code: int) -> ValueError:
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(host == h or host.endswith("." + h) for h in _BLOCKED_SHOP_HOSTS):
        return ValueError(
            "쿠팡 상품 페이지는 프로그램 접근을 막고 있어요 — "
            "상품이 소개된 '블로그 글' 주소를 넣어주세요 (글 안의 사진·설명을 가져옵니다)")
    if code in (401, 403, 429, 451, 503):
        return ValueError(
            f"이 사이트가 자동 접근을 막았어요 (HTTP {code}) — 네이버 블로그 글 주소를 "
            "넣거나, 글 내용을 「대본 직접 넣기」에 붙여넣고 사진을 직접 골라주세요")
    return ValueError(f"페이지를 여는 데 실패했어요 (HTTP {code})")


def _get(url: str, referer: str, timeout: float, cap: int):
    """GET → (본문 bytes, 최종 URL, Content-Type). 리다이렉트는 urllib이 따라감."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — 사용자 입력 URL
        return (resp.read(cap), resp.geturl() or url,
                resp.headers.get("Content-Type", "") if resp.headers else "")


def _decode_html(data: bytes, content_type: str) -> str:
    m = re.search(r"charset=([A-Za-z0-9_\-]+)", content_type or "")
    for enc in ([m.group(1)] if m else []) + ["utf-8", "cp949"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


_MAGIC = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"),
          (b"BM", ".bmp"), (b"GIF8", None))     # GIF는 저장 안 함(움짤·스티커)


def _sniff_ext(data: bytes, url: str) -> Optional[str]:
    """매직바이트로 확장자 결정 — URL의 ?type=w800 같은 쿼리에 속지 않기."""
    for magic, ext in _MAGIC:
        if data.startswith(magic):
            return ext
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        if path.endswith(ext):
            return ext
    return None


def fetch_bytes(url: str, timeout: float = 20.0, cap: int = 15_000_000,
                referer: str = "") -> bytes:
    """단일 파일(이미지 등) 내려받기 — 🛒 파트너스 상품 이미지 CDN용 (v0.88)."""
    data, _final, _ct = _get(
        url, referer=referer or url, timeout=timeout, cap=cap)
    return data


def sniff_image_ext(data: bytes) -> str:
    """매직바이트만으로 이미지 확장자(점 없이) — 모르면 빈 문자열 (v0.88)."""
    ext = _sniff_ext(data, "")
    return (ext or "").lstrip(".")


def fetch_article(url: str, dest_dir, timeout: float = 20.0, max_images: int = 20,
                  progress_cb: Optional[Callable[[str], None]] = None) -> dict:
    """글 1편을 가져와 사진을 dest_dir에 저장.

    반환: {title, text, images(로컬 절대경로), links, source_url, notes}.
    실패(차단·본문 없음)는 사용자에게 보여줄 한국어 메시지의 ValueError.
    """
    def say(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    url = normalize_url(url)
    if not url.startswith(("http://", "https://")):
        raise ValueError("주소가 올바르지 않아요 — http로 시작하는 글 주소를 넣어주세요")
    say("글 페이지 여는 중…")
    try:
        data, landed, ctype = _get(url, referer=url, timeout=timeout, cap=_PAGE_CAP)
    except urllib.error.HTTPError as e:
        raise _friendly_http_error(url, e.code) from e
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise ValueError(f"페이지에 연결하지 못했어요 — 인터넷 연결을 확인해 주세요 ({e})") from e
    final_url = normalize_url(landed)
    if final_url != url:                          # 단축링크(naver.me 등) → 실주소 재수집 1회
        say("연결된 실제 주소로 다시 여는 중…")
        try:
            data, _, ctype = _get(final_url, referer=final_url, timeout=timeout, cap=_PAGE_CAP)
        except urllib.error.HTTPError as e:
            raise _friendly_http_error(final_url, e.code) from e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise ValueError(f"페이지에 연결하지 못했어요 ({e})") from e
        url = final_url
    html = _decode_html(data, ctype)

    art = parse_article_html(html, base_url=url)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("img_*.*"):              # 재수집 시 이전 사진 정리
        try:
            old.unlink()
        except OSError:
            pass
    images: List[str] = []
    seen_sha = set()
    fails = 0
    for i, img_url in enumerate(art["image_urls"]):
        if len(images) >= max_images:
            break
        say(f"사진 받는 중… {len(images) + 1}장째 (남은 후보 {len(art['image_urls']) - i})")
        try:
            raw, _, _ = _get(img_url, referer=url, timeout=timeout, cap=_IMG_CAP)
        except (urllib.error.URLError, OSError, TimeoutError):
            fails += 1
            continue
        if len(raw) < _IMG_MIN:                    # 아이콘·빈 응답
            continue
        ext = _sniff_ext(raw, img_url)
        if not ext:                                # GIF·미지원 형식
            continue
        sha = hashlib.sha1(raw).hexdigest()
        if sha in seen_sha:                        # 같은 사진 중복(썸네일+본문) 제거
            continue
        seen_sha.add(sha)
        out = dest / f"img_{len(images) + 1:02d}{ext}"
        out.write_bytes(raw)
        images.append(str(out))
    notes = list(art["notes"])
    if fails and not images:
        notes.append("사진 다운로드가 모두 차단됐어요 — 사진은 [사진 파일 고르기]로 직접 골라주세요")
    elif fails:
        notes.append(f"사진 {fails}장은 받지 못해 건너뛰었어요")
    if len(art["text"]) < 80 and not images:
        raise ValueError(
            "글에서 본문과 사진을 찾지 못했어요 — 공개된 글인지 확인하고, 네이버 블로그면 "
            "글 주소(blog.naver.com/아이디/글번호)를 그대로 붙여넣어 주세요")
    return {"title": art["title"], "text": art["text"], "images": images,
            "links": art["links"], "source_url": url, "notes": notes}
