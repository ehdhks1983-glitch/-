"""🛒 쿠팡 파트너스 오픈 API (v0.88) — 상품 검색·딥링크 (표준 라이브러리만).

상품 페이지 크롤링은 봇 차단으로 불가(우회 안 함). 파트너스 회원에게 제공되는
공식 오픈 API로 상품명·가격·대표 이미지·파트너스 추적 링크를 받아온다.
- 인증: CEA(HMAC-SHA256). 서명 메시지 = signed-date + method + path + query.
  signed-date는 GMT "yyMMdd'T'HHmmss'Z'" 형식.
- 키 발급: 쿠팡 파트너스 → 도구 → Open API에서 Access/Secret Key.
※ 실 호출 검증은 사용자의 키·PC에서 이뤄진다 — 실패 시 한국어 안내를 던진다.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

HOST = "https://api-gateway.coupang.com"
_BASE = "/v2/providers/affiliate_open_api/apis/openapi/v1"


class CoupangError(RuntimeError):
    pass


def cea_authorization(method: str, path: str, query: str,
                      access_key: str, secret_key: str,
                      now: Optional[_dt.datetime] = None) -> str:
    """CEA 서명 헤더 생성 — now 주입은 테스트용 (기본: 현재 GMT)."""
    t = (now or _dt.datetime.utcnow()).strftime("%y%m%d") + "T" + \
        (now or _dt.datetime.utcnow()).strftime("%H%M%S") + "Z"
    message = t + method + path + query
    sig = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return (f"CEA algorithm=HmacSHA256, access-key={access_key}, "
            f"signed-date={t}, signature={sig}")


def _call(method: str, path: str, query: str, access: str, secret: str,
          body: Optional[dict] = None, timeout: float = 20.0) -> dict:
    if not access or not secret:
        raise CoupangError("쿠팡 파트너스 API 키가 없어요 — 파트너스 사이트 → 도구 → "
                           "Open API에서 Access/Secret Key를 발급받아 저장해 주세요")
    url = HOST + path + (f"?{query}" if query else "")
    req = urllib.request.Request(
        url, method=method,
        data=(json.dumps(body).encode("utf-8") if body is not None else None),
        headers={"Content-Type": "application/json",
                 "Authorization": cea_authorization(method, path, query, access, secret)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:300]
        if e.code in (401, 403):
            raise CoupangError("파트너스 API가 키를 거부했어요 — Access/Secret Key를 "
                               f"다시 확인해 주세요 ({e.code})") from e
        raise CoupangError(f"파트너스 API 오류 {e.code}: {text}") from e
    except Exception as e:  # noqa: BLE001 — 네트워크 등
        raise CoupangError(f"파트너스 API 연결 실패: {str(e)[:200]} — 인터넷 연결을 확인해 주세요") from e
    if str(out.get("rCode", "0")) not in ("0", "200"):
        raise CoupangError(f"파트너스 API 응답 오류: {out.get('rMessage', '')[:200]}")
    return out


def search_products(keyword: str, access: str, secret: str,
                    limit: int = 8) -> List[dict]:
    """상품 검색 → [{name, price, image, url(파트너스 추적 링크), rocket}]."""
    kw = (keyword or "").strip()
    if not kw:
        raise CoupangError("검색어를 입력해 주세요 (예: 무선 선풍기)")
    path = _BASE + "/products/search"
    query = urllib.parse.urlencode({"keyword": kw, "limit": max(1, min(20, limit))})
    out = _call("GET", path, query, access, secret)
    data = ((out.get("data") or {}).get("productData")) or []
    items = []
    for p in data:
        items.append({
            "name": str(p.get("productName") or "")[:120],
            "price": int(p.get("productPrice") or 0),
            "image": str(p.get("productImage") or ""),
            "url": str(p.get("productUrl") or ""),
            "rocket": bool(p.get("isRocket")),
            "category": str(p.get("categoryName") or ""),
        })
    return items


_THUMB_SIZE_RE = None  # 지연 컴파일 — 모듈 임포트 비용 최소화


def hi_res_image(url: str) -> str:
    """쿠팡 CDN 썸네일 URL을 큰 사이즈로 — 영상 배경엔 492px가 흐릿하다 (v0.90).

    thumbnail*.coupangcdn.com/thumbnails/remote/492x492ex/image/... 형태의
    크기 세그먼트만 1024x1024ex로 바꾼다. 패턴이 아니면 그대로 돌려준다.
    """
    global _THUMB_SIZE_RE
    if _THUMB_SIZE_RE is None:
        import re  # noqa: PLC0415

        _THUMB_SIZE_RE = re.compile(r"/thumbnails/remote/\d+x\d+(ex)?/")
    u = (url or "").strip()
    if "coupangcdn.com" not in u:
        return u
    return _THUMB_SIZE_RE.sub("/thumbnails/remote/1024x1024ex/", u)


def deeplink(urls: List[str], access: str, secret: str) -> List[dict]:
    """쿠팡 상품 URL들 → 파트너스 추적 단축링크 [{origin, short}]."""
    clean = [u.strip() for u in urls if (u or "").strip()][:5]
    if not clean:
        raise CoupangError("변환할 쿠팡 링크가 없어요")
    path = _BASE + "/deeplink"
    out = _call("POST", path, "", access, secret, body={"coupangUrls": clean})
    data = (out.get("data")) or []
    return [{"origin": str(d.get("originalUrl") or ""),
             "short": str(d.get("shortenUrl") or "")} for d in data]
