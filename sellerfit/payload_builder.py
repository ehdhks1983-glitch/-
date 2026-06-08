"""
payload_builder.py - 쿠팡 Product Creation API JSON 조립
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
도매꾹 상품 정보 + 가격 계산 + 카테고리 + 이미지 + 메타데이터를
쿠팡 Product Creation API가 요구하는 JSON 구조로 변환.

공식 스펙 참조:
  https://developers.coupangcorp.com/hc/en-us/articles/360033877853-Product-Creation

필수 필드 (모두 들어있지 않으면 400 에러):
  - displayCategoryCode, sellerProductName, vendorId
  - saleStartedAt, saleEndedAt, displayProductName, brand
  - deliveryMethod, deliveryCompanyCode, deliveryChargeType
  - returnCenterCode, outboundShippingPlaceCode
  - items[] (최소 1개, 단일상품도 items 배열 필수)
"""

from datetime import datetime
from typing import Dict, List, Optional

from config import coupang_cfg, registration_cfg
from domeggook_client import DomeggookProduct
from pricing import PricingResult
from logger import log


class PayloadBuilder:
    """쿠팡 상품 등록 payload 조립기"""

    # 쿠팡이 허용하는 displayProductName 최대 길이
    # (공식 공지: 2024-03-27부터 100자로 제한)
    MAX_DISPLAY_NAME_LEN = 100
    MAX_SELLER_NAME_LEN = 100
    MAX_BRAND_LEN = 50

    def __init__(self):
        self.vendor_id = coupang_cfg.vendor_id
        self.reg = registration_cfg

    # ═══════════════════════════════════════════════════════════
    # 메인 엔트리
    # ═══════════════════════════════════════════════════════════
    def build(
        self,
        dome_product: DomeggookProduct,
        pricing: PricingResult,
        display_category_code: int,
        image_urls: List[str],
        return_center: Dict,
        outbound_center: Dict,
        brand: str = "",
        required_attributes: List[Dict] = None,
    ) -> Dict:
        """
        상품 등록 payload 조립.

        Args:
            dome_product:   도매꾹 상품 정보
            pricing:        가격 계산 결과
            display_category_code: 쿠팡 카테고리 코드
            image_urls:     쿠팡에 전달할 이미지 URL 리스트
            return_center:  {code, name, address, postcode, phone, ...}
            outbound_center: {code, name, ...}
            brand:          브랜드명 (없으면 기본값)
            required_attributes: 카테고리 메타에서 추출한 필수 구매옵션 리스트
                                 (None이면 빈 배열 → 등록 거부 위험)

        Returns:
            쿠팡 API JSON body
        """
        # ─── 상품명/브랜드 정리 ───
        seller_name = self._truncate(dome_product.title, self.MAX_SELLER_NAME_LEN) \
                      or f"상품_{dome_product.item_no}"
        display_name = self._truncate(dome_product.title, self.MAX_DISPLAY_NAME_LEN) \
                       or seller_name
        brand_clean = self._truncate(brand or "자체브랜드", self.MAX_BRAND_LEN)

        # ─── 날짜 ───
        now = datetime.now()
        sale_start = now.strftime("%Y-%m-%dT%H:%M:%S")
        sale_end = f"{self.reg.sale_end_year}-12-31T23:59:59"

        # ─── 이미지 블록 ───
        images = self._build_images(image_urls)

        # ─── 콘텐츠(상세페이지) ───
        contents = self._build_contents(dome_product, image_urls)

        # ─── 필수 구매옵션(attributes) 자동 생성 ───
        attributes = self._build_attributes(dome_product, required_attributes or [])

        # ─── 검색 키워드 ───
        search_tags = self._build_search_tags(dome_product)

        # ─── 고시정보 ───
        notices = self._build_notices()

        # ─── items (단일상품도 배열 필수) ───
        # 쿠팡 스펙: attributes/notices/contents/searchTags 는 item 안에 들어감
        items = self._build_items(
            dome_product, pricing, display_name, images, contents,
            outbound_center, attributes, notices, search_tags,
        )

        # ─── 반품지/출고지 정보 ───
        return_zipcode = return_center.get("postcode", "") or "00000"
        return_address = return_center.get("address", "") or "주소미등록"
        return_phone = return_center.get("phone", "") or "00-0000-0000"

        payload = {
            # ── 필수 식별 ──
            "displayCategoryCode": display_category_code,
            "sellerProductName": seller_name,
            "vendorId": self.vendor_id,

            # ── 판매 기간 ──
            "saleStartedAt": sale_start,
            "saleEndedAt": sale_end,

            # ── 표시 정보 ──
            "displayProductName": display_name,
            "brand": brand_clean,
            "generalProductName": seller_name,
            "productGroup": seller_name,

            # ── 배송 ──
            "deliveryMethod": self.reg.delivery_method,
            "deliveryCompanyCode": self.reg.delivery_company_code,
            "deliveryChargeType": self.reg.delivery_charge_type,
            "deliveryCharge": self.reg.delivery_charge,
            "freeShipOverAmount": self.reg.free_ship_over_amount,
            "deliveryChargeOnReturn": self.reg.delivery_charge_on_return,
            "remoteAreaDeliverable": self.reg.remote_area_deliverable,
            "unionDeliveryType": self.reg.union_delivery_type,

            # ── 반품지 ──
            "returnCenterCode": return_center.get("code", ""),
            "returnChargeName": return_center.get("name", "반품지"),
            "companyContactNumber": return_phone,
            "returnZipCode": return_zipcode,
            "returnAddress": return_address,
            "returnAddressDetail": return_center.get("address_detail", "") or "-",
            "returnCharge": self.reg.delivery_charge_on_return,

            # ── 출고지 ──
            "outboundShippingPlaceCode": outbound_center.get("code", ""),

            # ── WING 로그인 ID (필수) ──
            "vendorUserId": coupang_cfg.vendor_user_id or self.vendor_id,

            # ── 승인 요청 여부 ──
            # False = 임시저장, True = 즉시 승인 요청
            "requested": self.reg.auto_request_approval,

            # ── 옵션 아이템 ──
            "items": items,

            # ── 확장 메타 (쿠팡은 무시, 우리 추적용) ──
            "extraInfoMessage": "",
        }

        return payload

    # ═══════════════════════════════════════════════════════════
    # items 블록
    # ═══════════════════════════════════════════════════════════
    def _build_items(
        self,
        dome: DomeggookProduct,
        pricing: PricingResult,
        display_name: str,
        images: List[Dict],
        contents: List[Dict],
        outbound_center: Dict,
        attributes: List[Dict],
        notices: List[Dict],
        search_tags: List[str],
    ) -> List[Dict]:
        """
        Slice 1: 단일상품으로 items 1개만 생성.
        Slice 2에서 도매꾹 옵션 → 쿠팡 items 다건 확장 예정.

        쿠팡 스펙: attributes(필수 구매옵션)/notices(고시정보)/contents/searchTags
        는 모두 item 안에 들어감.
        """
        item = {
            "itemName": display_name,
            "originalPrice": pricing.original_price,
            "salePrice": pricing.sale_price,
            "maximumBuyCount": str(self.reg.stock_qty),       # 판매 가능 재고
            "maximumBuyForPerson": str(self.reg.maximum_buy_for_person),
            "maximumBuyForPersonPeriod": "1",  # 1일
            "outboundShippingTimeDay": self.reg.outbound_shipping_time_day,
            "unitCount": 1,
            "adultOnly": "EVERYONE",
            "taxType": "TAX",
            "parallelImported": "NOT_PARALLEL_IMPORTED",
            "overseasPurchased": "NOT_OVERSEAS_PURCHASED",
            "pccNeeded": False,
            "externalVendorSku": f"dome-{dome.item_no}",  # 추적용
            "barcode": "",
            "emptyBarcode": True,
            "emptyBarcodeReason": "상품확보시점에 바코드가 없는 상품",
            "images": images,
            "contents": contents,
            "offerCondition": "NEW",
            "offerDescription": "",
            # ★ 카테고리별 필수 구매옵션
            "attributes": attributes,
            # ★ 고시정보 (item 레벨)
            "notices": notices,
            # ★ 검색어 (item 레벨)
            "searchTags": search_tags,
            "certifications": [],
        }
        return [item]

    # ═══════════════════════════════════════════════════════════
    # attributes 블록 (카테고리 필수 구매옵션 자동 채움)
    # ═══════════════════════════════════════════════════════════
    def _build_attributes(self, dome: DomeggookProduct,
                          required_attrs: List[Dict]) -> List[Dict]:
        """
        카테고리 메타의 필수 구매옵션을 채운다.

        쿠팡 생성 API 형식:
          [{"attributeTypeName": "수량", "attributeValueName": "1개"}]

        값 추론 전략 (Slice 1):
          - dataType=="NUMBER"  → "1" + basicUnit (예: "1개")
          - dataType=="STRING"  → 상품명에서 못 찾으면 "기타" 또는 "단일"
          - 도매꾹 옵션명이 매칭되면 그 값 사용 (간단 매칭)

        ⚠️ Slice 1 한계: 값이 부정확할 수 있음.
           실제 등록 에러 시 사용자가 WING에서 보정하거나 Slice 2에서 정교화.
        """
        if not required_attrs:
            log.warning("[PAYLOAD] 카테고리 필수옵션 정보 없음 → attributes 빈 배열 "
                        "(등록 거부될 수 있음)")
            return []

        result = []
        for attr in required_attrs:
            type_name = attr.get("attributeTypeName", "")
            if not type_name:
                continue
            data_type = (attr.get("dataType") or "STRING").upper()
            basic_unit = attr.get("basicUnit", "") or ""

            # 값 추론
            if data_type == "NUMBER":
                # 숫자형: 기본 1 + 단위
                unit = basic_unit if basic_unit and basic_unit != "없음" else ""
                value = f"1{unit}"
            else:
                # 문자형: 도매꾹 옵션에서 매칭 시도
                value = self._guess_string_attr(type_name, dome)

            result.append({
                "attributeTypeName": type_name,
                "attributeValueName": value,
            })

        log.info(f"[PAYLOAD] 필수옵션 {len(result)}개 자동 채움: "
                 f"{[a['attributeTypeName'] for a in result]}")
        return result

    @staticmethod
    def _guess_string_attr(type_name: str, dome: DomeggookProduct) -> str:
        """문자형 속성값 추론 (도매꾹 옵션/상품명 기반)"""
        # 도매꾹 옵션 중 이름이 비슷한 게 있으면 첫 값 사용
        for opt in dome.options:
            opt_name = opt.get("name", "")
            if opt_name and (opt_name in type_name or type_name in opt_name):
                values = opt.get("values", [])
                if values:
                    return values[0]
        # 매칭 실패 → 무난한 기본값
        return "기타"

    # ═══════════════════════════════════════════════════════════
    # notices 블록 (고시정보 - item 레벨, flat 구조)
    # ═══════════════════════════════════════════════════════════
    def _build_notices(self) -> List[Dict]:
        """
        고시정보 (item 안에 들어감, flat 구조).

        쿠팡 형식:
          [{"noticeCategoryName": "기타 재화",
            "noticeCategoryDetailName": "품명 및 모델명",
            "content": "상세페이지 참조"}, ...]
        """
        category = "기타 재화"
        details = [
            ("품명 및 모델명", "상세페이지 참조"),
            ("법에 의한 인증ㆍ허가 등을 받았음을 확인할 수 있는 경우 그에 대한 사항", "해당없음"),
            ("제조국 또는 원산지", "상세페이지 참조"),
            ("제조자, 수입품의 경우 수입자를 함께 표기", "상세페이지 참조"),
            ("A/S 책임자와 전화번호 또는 소비자상담 관련 전화번호", "판매자 연락처 참조"),
        ]
        return [
            {"noticeCategoryName": category,
             "noticeCategoryDetailName": name, "content": content}
            for name, content in details
        ]


    # ═══════════════════════════════════════════════════════════
    # images 블록
    # ═══════════════════════════════════════════════════════════
    def _build_images(self, urls: List[str]) -> List[Dict]:
        """
        쿠팡 images 포맷:
          [{"imageOrder": 0, "imageType": "REPRESENTATION", "vendorPath": "..."}, ...]
        imageType:
          REPRESENTATION - 대표 (1장 필수)
          DETAIL         - 상세
        """
        if not urls:
            log.warning("[PAYLOAD] 이미지 0장 - 쿠팡 등록 실패 예상")
            return []

        images = []
        # 대표 이미지
        images.append({
            "imageOrder": 0,
            "imageType": "REPRESENTATION",
            "vendorPath": urls[0],
        })
        # 나머지는 상세
        for i, url in enumerate(urls[1:], start=1):
            images.append({
                "imageOrder": i,
                "imageType": "DETAIL",
                "vendorPath": url,
            })

        return images

    # ═══════════════════════════════════════════════════════════
    # contents 블록 (상세페이지)
    # ═══════════════════════════════════════════════════════════
    def _build_contents(self, dome: DomeggookProduct,
                        image_urls: List[str]) -> List[Dict]:
        """
        Slice 1: 최소한의 상세페이지 (이미지 나열 + 원본 HTML)
        Slice 2에서 AI 카피 + 템플릿 30종 적용 예정.

        쿠팡 contents 구조:
          [
            {
              "contentsType": "TEXT" | "HTML" | "IMAGE_NO_SPACE" | "IMAGE",
              "contentDetails": [{"content": "...", "detailType": "TEXT|HTML|IMAGE"}]
            }
          ]
        """
        details = []

        # 이미지 나열 (본문 이미지)
        for url in image_urls[1:]:  # 대표 제외
            details.append({
                "content": url,
                "detailType": "IMAGE",
            })

        # 원본 HTML (있으면)
        if dome.description_html:
            # HTML에 <img src="..."/> 등 위험 태그 있을 수 있어 정리
            safe_html = self._sanitize_html(dome.description_html)
            if safe_html.strip():
                details.append({
                    "content": safe_html,
                    "detailType": "TEXT",  # HTML → TEXT 타입으로 넣으면 쿠팡이 렌더
                })

        if not details:
            return []

        return [{
            "contentsType": "IMAGE_NO_SPACE",
            "contentDetails": details,
        }]

    @staticmethod
    def _sanitize_html(html: str, max_len: int = 50000) -> str:
        """
        상세 HTML 안전 처리.
        쿠팡은 특정 태그/속성만 허용하므로 보수적으로 정리.
        """
        import re
        # 스크립트/스타일/iframe 제거
        html = re.sub(r'<script[^>]*>.*?</script>', '', html,
                      flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html,
                      flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<iframe[^>]*>.*?</iframe>', '', html,
                      flags=re.IGNORECASE | re.DOTALL)
        # onClick 등 이벤트 속성 제거
        html = re.sub(r'\s(on\w+)\s*=\s*["\'][^"\']*["\']', '', html,
                      flags=re.IGNORECASE)
        # 길이 제한
        if len(html) > max_len:
            html = html[:max_len]
        return html

    # ═══════════════════════════════════════════════════════════
    # 검색 키워드
    # ═══════════════════════════════════════════════════════════
    def _build_search_tags(self, dome: DomeggookProduct) -> List[str]:
        """
        searchTags: 각 20자 이내, 최대 20개 (쿠팡 공지 기준).
        도매꾹 키워드 재사용.
        """
        raw = list(dome.keywords or [])
        # 상품명에서 단어 추출 (키워드 부족 시)
        if dome.title:
            tokens = [w.strip() for w in dome.title.split() if 2 <= len(w.strip()) <= 20]
            for t in tokens:
                if t not in raw:
                    raw.append(t)

        tags = []
        for t in raw:
            t = t.strip()
            if not t or len(t) > 20:
                continue
            if t not in tags:
                tags.append(t)
            if len(tags) >= 20:
                break
        return tags

    # ═══════════════════════════════════════════════════════════
    # 고시정보 (stub)
    # ═══════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════
    # 유틸
    # ═══════════════════════════════════════════════════════════
    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if not text:
            return ""
        return text[:max_len].strip()


# ═══════════════════════════════════════════════════════════════
# 검증 헬퍼 (payload 전송 전 로컬 점검)
# ═══════════════════════════════════════════════════════════════
def validate_payload(payload: Dict) -> List[str]:
    """
    전송 전 누락 필드 검사 (하드 에러만 — 이게 있으면 등록 불가).
    Returns: 누락/문제 필드 리스트 (빈 리스트면 OK)
    """
    problems = []
    required = [
        "displayCategoryCode", "sellerProductName", "vendorId",
        "saleStartedAt", "saleEndedAt", "displayProductName", "brand",
        "deliveryMethod", "deliveryCompanyCode", "deliveryChargeType",
        "returnCenterCode", "outboundShippingPlaceCode", "vendorUserId",
    ]
    for k in required:
        v = payload.get(k)
        if v is None or v == "":
            problems.append(f"누락: {k}")

    # items 검증
    items = payload.get("items", [])
    if not items:
        problems.append("누락: items (최소 1개 필요)")
    else:
        for i, item in enumerate(items):
            if not item.get("itemName"):
                problems.append(f"items[{i}].itemName 누락")
            if not item.get("salePrice") or item.get("salePrice", 0) <= 0:
                problems.append(f"items[{i}].salePrice 잘못됨")
            if not item.get("images"):
                problems.append(f"items[{i}].images 누락")

    return problems


def get_payload_warnings(payload: Dict) -> List[str]:
    """
    소프트 경고 (등록은 시도하되, 거부될 수 있는 위험 요소).
    Returns: 경고 리스트
    """
    warnings = []
    items = payload.get("items", [])
    for i, item in enumerate(items):
        attrs = item.get("attributes", [])
        if not attrs:
            warnings.append(
                f"items[{i}].attributes 비어있음 → 카테고리 필수옵션 미충족 시 "
                f"'필수 구매옵션 없음' 에러로 거부될 수 있음")
        else:
            # 값이 빈 attribute 체크
            empty = [a.get("attributeTypeName") for a in attrs
                     if not a.get("attributeValueName")]
            if empty:
                warnings.append(f"items[{i}] 값 미입력 속성: {empty}")
        if not item.get("notices"):
            warnings.append(f"items[{i}].notices(고시정보) 비어있음")
    return warnings


if __name__ == "__main__":
    print("payload_builder.py - 단독 테스트는 main.py를 통해 실행하세요")
