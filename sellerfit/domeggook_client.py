"""
domeggook_client.py - 도매꾹 Open API 클라이언트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
getItemView API로 상품 상세 정보 수집.

도완님 기존 크롤링 제품과 동일한 엔드포인트지만,
본 모듈은 다음 3가지에 집중:
  1. 원본 XML 백업 (정보 최대한 모으기)
  2. 정제된 dict 반환 (다음 단계에서 사용)
  3. 이미지 URL만 별도로 분리
"""

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict

try:
    import requests
except ImportError:
    raise ImportError("requests 미설치. pip install requests")

from config import domeggook_cfg
from logger import log


# ═══════════════════════════════════════════════════════════════
# 상품 데이터 구조
# ═══════════════════════════════════════════════════════════════
@dataclass
class DomeggookProduct:
    """정제된 도매꾹 상품 정보"""
    item_no: str = ""
    status: str = ""
    title: str = ""
    keywords: List[str] = field(default_factory=list)
    section: str = ""
    category_path: str = ""           # 카테고리 경로 (있으면)

    # 가격
    tier_prices: List[Dict] = field(default_factory=list)  # [{"min_qty":1, "unit_price":9850}, ...]
    supply_price: int = 0             # 공급가
    resale_recommend: int = 0         # 권장판매가
    resale_minimum: int = 0           # 최소판매가

    # 수량/재고
    inventory: int = 0
    dome_moq: int = 1                 # 최소 주문 수량

    # 배송
    delivery_method: str = ""
    delivery_pay: str = ""

    # 이미지
    images: List[str] = field(default_factory=list)

    # 옵션
    options: List[Dict] = field(default_factory=list)

    # 상세 HTML
    description_html: str = ""

    # 판매자
    seller_id: str = ""
    seller_name: str = ""

    # 메타
    raw_xml: str = ""                 # 원본 XML (백업용)

    def to_dict(self) -> dict:
        d = asdict(self)
        # raw_xml은 용량이 크므로 to_dict에서는 길이만 포함
        d["raw_xml_length"] = len(self.raw_xml)
        d["raw_xml"] = d["raw_xml"][:500] + "..." if len(self.raw_xml) > 500 else d["raw_xml"]
        return d

    @property
    def base_price(self) -> int:
        """
        가격 계산의 기준이 되는 1개당 단가.
        우선순위: tier_prices[0] > supply_price > resale_minimum
        """
        if self.tier_prices:
            return self.tier_prices[0].get("unit_price", 0)
        if self.supply_price:
            return self.supply_price
        if self.resale_minimum:
            return self.resale_minimum
        return 0

    @property
    def has_images(self) -> bool:
        return len(self.images) > 0

    @property
    def is_valid(self) -> bool:
        """최소 등록 가능 여부"""
        return (bool(self.item_no) and bool(self.title)
                and self.base_price > 0 and len(self.images) > 0)


# ═══════════════════════════════════════════════════════════════
# API 클라이언트
# ═══════════════════════════════════════════════════════════════
class DomeggookClient:
    """도매꾹 Open API 클라이언트"""

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or domeggook_cfg.api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.UA,
            "Accept-Language": "ko-KR,ko;q=0.9",
        })

    def get_item_view(self, item_no: str, retry: int = 3) -> Tuple[Optional[DomeggookProduct], str]:
        """
        상품 상세 조회.

        Returns:
            (DomeggookProduct 또는 None, raw_xml_text)
        """
        if not self.api_key:
            log.error("[DOME] API Key 미설정")
            return None, ""

        params = {
            "ver": domeggook_cfg.api_version,
            "mode": "getItemView",
            "aid": self.api_key,
            "no": str(item_no),
            "om": "xml",
        }

        for attempt in range(1, retry + 1):
            try:
                log.info(f"[DOME] getItemView({item_no}) 시도 {attempt}/{retry}")
                resp = self.session.get(
                    domeggook_cfg.api_base,
                    params=params,
                    timeout=domeggook_cfg.timeout_sec,
                )

                # 인코딩 자동 감지 (EUC-KR/UTF-8)
                resp.encoding = resp.apparent_encoding or "utf-8"
                body = resp.text

                if resp.status_code == 429:
                    log.warning(f"[DOME] 분당/일일 허용량 초과 (429). 60초 대기 후 재시도")
                    time.sleep(60)
                    continue

                if resp.status_code != 200:
                    log.warning(f"[DOME] HTTP {resp.status_code}: {body[:300]}")
                    if attempt < retry:
                        time.sleep(2 ** attempt)
                        continue
                    return None, body

                # 에러 XML 체크
                if self._is_error_response(body):
                    log.error(f"[DOME] API 에러 응답: {body[:500]}")
                    return None, body

                product = self._parse_xml(body, item_no)
                if product:
                    product.raw_xml = body
                    log.info(f"[DOME] ✅ 파싱 성공 (이미지 {len(product.images)}장, "
                             f"옵션 {len(product.options)}개)")
                return product, body

            except requests.exceptions.Timeout:
                log.warning(f"[DOME] 타임아웃 (시도 {attempt})")
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                log.error(f"[DOME] 오류: {type(e).__name__}: {e}")
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue

        return None, ""

    @staticmethod
    def _is_error_response(body: str) -> bool:
        """도매꾹 표준 오류 메시지 감지"""
        return ("<errors>" in body or
                ("<code>" in body and "<message>" in body and "<basis>" not in body))

    def _parse_xml(self, xml_text: str, item_no: str) -> Optional[DomeggookProduct]:
        """XML → DomeggookProduct 파싱"""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            log.error(f"[DOME] XML 파싱 실패: {e}")
            return None

        def t(path, default=""):
            el = root.find(path)
            return el.text.strip() if el is not None and el.text else default

        def tl(path):
            return [el.text.strip() for el in root.findall(path) if el.text]

        def ti(path, default=0):
            try:
                return int(t(path, str(default)) or default)
            except (ValueError, TypeError):
                return default

        product = DomeggookProduct(item_no=str(item_no))

        # ─── 기본 ───
        product.status = t("basis/status")
        product.title = t("basis/title")
        product.keywords = tl("basis/keywords/kw")
        product.section = t("basis/section")
        product.category_path = t("basis/category/path") or t("basis/categoryPath")

        # ─── 가격 (계단식) ───
        # 형식: "1+9850|11+9800|301+9750|501+9700|1001+9650"
        dome_raw = t("price/dome")
        if dome_raw:
            for tier in dome_raw.split("|"):
                if "+" in tier:
                    qty, price = tier.split("+", 1)
                    try:
                        product.tier_prices.append({
                            "min_qty": int(qty),
                            "unit_price": int(price),
                        })
                    except ValueError:
                        pass

        product.supply_price = ti("price/supply")
        product.resale_minimum = ti("price/resale/minimum")
        product.resale_recommend = ti("price/resale/Recommand")

        # ─── 수량/재고 ───
        product.inventory = ti("qty/inventory")
        product.dome_moq = ti("qty/domeMoq", 1)

        # ─── 배송 ───
        product.delivery_method = t("deli/method")
        product.delivery_pay = t("deli/pay")

        # ─── 판매자 ───
        product.seller_id = t("seller/id")
        product.seller_name = t("seller/nick") or t("seller/name")

        # ─── 이미지 수집 (공식 문서에 정확한 경로 없음 - 여러 경로 시도) ───
        product.images = self._extract_images(root, xml_text)

        # ─── 옵션 ───
        for opt in root.findall("options/option"):
            name = opt.findtext("name", "").strip() if opt.findtext("name") else ""
            values = [v.text.strip() for v in opt.findall("value") if v.text]
            if name or values:
                product.options.append({"name": name, "values": values})

        # ─── 상세 HTML ───
        product.description_html = (
            t("contents/html")
            or t("content")
            or t("description")
            or t("contents")
            or ""
        )

        return product

    @staticmethod
    def _extract_images(root: ET.Element, xml_text: str) -> List[str]:
        """
        이미지 URL 수집 - 공식 문서가 불완전해서 여러 방식으로.

        ※ 순서 중요: 쿠팡은 이미지 배열의 첫 장을 '대표이미지(REPRESENTATION)'로
          사용하므로, 도매꾹의 썸네일/대표(thumb, mainImg)를 맨 앞에 둔다.
        """
        urls_order = []  # 순서 유지 + 중복 제거
        seen = set()

        # 대표이미지 후보를 먼저 (맨 앞), 그 다음 상세이미지
        candidate_paths = [
            "thumb",        # 대표
            "thumbImg",
            "thumbUrl",
            "mainImg",
            "images/image",  # 상세
            "images/img",
            "images/url",
            "image",
            "detailImg",
            "img",
            "pics/pic",
            "mediaList/media",
        ]

        for path in candidate_paths:
            for el in root.findall(path):
                url = el.text.strip() if el.text else ""
                url = DomeggookClient._normalize_image_url(url)
                if url and url not in seen:
                    seen.add(url)
                    urls_order.append(url)

        # 폴백: 정규식으로 XML 텍스트에서 이미지 URL 추출
        if not urls_order:
            log.warning("[DOME] 지정 경로에서 이미지 못 찾음 → 정규식 폴백")
            found = re.findall(
                r'(https?://[^\s<>"\']+\.(?:jpg|jpeg|png|gif|webp))',
                xml_text,
                re.IGNORECASE,
            )
            for url in found:
                url = DomeggookClient._normalize_image_url(url)
                if url and url not in seen:
                    seen.add(url)
                    urls_order.append(url)

        return urls_order

    @staticmethod
    def _normalize_image_url(url: str) -> str:
        """이미지 URL 정규화"""
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return "https://domeggook.com" + url
        if url.startswith("http"):
            return url
        return ""

    def download_image(self, url: str, timeout: int = 15) -> Optional[bytes]:
        """이미지 다운로드 (원본 바이너리)"""
        try:
            resp = self.session.get(url, timeout=timeout, stream=True)
            if resp.status_code == 200:
                return resp.content
            log.warning(f"[DOME] 이미지 HTTP {resp.status_code}: {url[:60]}")
        except Exception as e:
            log.warning(f"[DOME] 이미지 다운로드 실패: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python domeggook_client.py <상품번호>")
        sys.exit(1)

    client = DomeggookClient()
    product, raw = client.get_item_view(sys.argv[1])
    if product:
        print(f"\n✅ 상품명: {product.title}")
        print(f"   기본단가: {product.base_price:,}원")
        print(f"   이미지: {len(product.images)}장")
        print(f"   옵션: {len(product.options)}개")
        print(f"   HTML 길이: {len(product.description_html):,}자")
    else:
        print("❌ 실패")
        sys.exit(1)
