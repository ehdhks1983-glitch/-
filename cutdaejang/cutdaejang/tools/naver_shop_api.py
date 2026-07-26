"""🟢 네이버 쇼핑 검색 API (v0.89) — 상품 검색 (표준 라이브러리만).

네이버 쇼핑커넥트용: 상품 페이지 크롤링은 봇 차단으로 불가하므로, 네이버
개발자센터(developers.naver.com)에서 무료 발급하는 검색 API(Client ID/Secret)로
상품명·가격·대표 이미지·쇼핑몰·카테고리를 받아온다.
※ 커넥트 수익 링크는 쇼핑커넥트 대시보드에서 만들어 붙여넣는 방식 (API 미제공).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import List

_URL = "https://openapi.naver.com/v1/search/shop.json"
_TAG_RE = re.compile(r"<[^>]+>")


class NaverShopError(RuntimeError):
    pass


def hi_res_image(url: str) -> str:
    """네이버 쇼핑 썸네일 URL을 원본 크기로 — ?type=f300 축소 파라미터 제거 (v0.90)."""
    u = (url or "").strip()
    if "pstatic.net" in u and "?type=" in u:
        return u.split("?", 1)[0]
    return u


def search_shop(keyword: str, client_id: str, client_secret: str,
                limit: int = 8, timeout: float = 15.0) -> List[dict]:
    """상품 검색 → [{name, price, image, url, mall, category}]."""
    kw = (keyword or "").strip()
    if not kw:
        raise NaverShopError("검색어를 입력해 주세요 (예: 무선 선풍기)")
    if not client_id or not client_secret:
        raise NaverShopError("네이버 검색 API 키가 없어요 — developers.naver.com에서 "
                             "애플리케이션을 등록하고 Client ID/Secret을 저장해 주세요 (무료)")
    q = urllib.parse.urlencode({"query": kw, "display": max(1, min(20, limit)),
                                "sort": "sim"})
    req = urllib.request.Request(
        f"{_URL}?{q}",
        headers={"X-Naver-Client-Id": client_id,
                 "X-Naver-Client-Secret": client_secret})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise NaverShopError("네이버 API가 키를 거부했어요 — Client ID/Secret을 "
                                 "다시 확인해 주세요 (검색 API 사용 설정 포함)") from e
        raise NaverShopError(f"네이버 검색 API 오류 {e.code}") from e
    except Exception as e:  # noqa: BLE001
        raise NaverShopError(f"네이버 API 연결 실패: {str(e)[:200]} — 인터넷 연결을 확인해 주세요") from e
    items = []
    for it in out.get("items") or []:
        name = _TAG_RE.sub("", str(it.get("title") or ""))   # <b>강조</b> 태그 제거
        cats = " > ".join(c for c in (it.get("category1"), it.get("category2"),
                                      it.get("category3")) if c)
        try:
            price = int(it.get("lprice") or 0)
        except (TypeError, ValueError):
            price = 0
        items.append({"name": name[:120], "price": price,
                      "image": str(it.get("image") or ""),
                      "url": str(it.get("link") or ""),
                      "mall": str(it.get("mallName") or ""),
                      "category": cats})
    return items
