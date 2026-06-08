"""
coupang_wing_client.py - 쿠팡 WING Open API 클라이언트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HMAC-SHA256 인증 + 파트너스 API와 다른 점:
  - 헤더 'X-Requested-By: {vendorId}' 필수
  - api-gateway.coupang.com 도메인 사용
  - vendorId는 경로 또는 쿼리 파라미터로 반복 사용

도완님 기존 coupang_api.py(파트너스)와 완전 별개.
"""

import hmac
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlencode, quote

try:
    import requests
except ImportError:
    raise ImportError("requests 미설치. pip install requests")

from config import coupang_cfg
from logger import log


# ═══════════════════════════════════════════════════════════════
# 엔드포인트 상수 (제8원칙 - 외부값 하드코딩 금지)
# ═══════════════════════════════════════════════════════════════
class Endpoints:
    """쿠팡 WING API 엔드포인트 모음"""
    SELLER_PRODUCTS_PAGING = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    SELLER_PRODUCT_DETAIL = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sellerProductId}"
    PRODUCT_CREATE = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    PRODUCT_MODIFY = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    APPROVAL_REQUEST = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sellerProductId}/approvals"

    CATEGORY_PREDICT = "/v2/providers/openapi/apis/api/v1/categorization/predict"
    CATEGORY_META = "/v2/providers/openapi/apis/api/v1/categories/{displayCategoryCode}/meta"

    RETURN_CENTERS = "/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/returnShippingCenters"
    OUTBOUND_CENTERS = "/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/outboundShippingCenters"


# ═══════════════════════════════════════════════════════════════
# 응답 래퍼
# ═══════════════════════════════════════════════════════════════
class WingResponse:
    """API 응답 래퍼"""
    def __init__(self, status_code: int, body: Any, raw_text: str = ""):
        self.status_code = status_code
        self.body = body if isinstance(body, dict) else {}
        self.raw_text = raw_text

    @property
    def is_success(self) -> bool:
        if self.status_code != 200:
            return False
        if isinstance(self.body, dict):
            code = self.body.get("code", "")
            # 쿠팡은 "SUCCESS" 또는 200 숫자로 응답
            return code in ("SUCCESS", 200, "200")
        return False

    @property
    def data(self) -> Any:
        return self.body.get("data") if isinstance(self.body, dict) else None

    @property
    def message(self) -> str:
        return self.body.get("message", "") if isinstance(self.body, dict) else ""

    @property
    def error_summary(self) -> str:
        if self.is_success:
            return ""
        code = self.body.get("code", "")
        msg = self.body.get("message", "")
        return f"[{self.status_code}] code={code} message={msg}"


# ═══════════════════════════════════════════════════════════════
# 클라이언트
# ═══════════════════════════════════════════════════════════════
class CoupangWingClient:
    """쿠팡 WING Open API 클라이언트"""

    def __init__(self, vendor_id: str = "", access_key: str = "", secret_key: str = ""):
        self.vendor_id = vendor_id or coupang_cfg.vendor_id
        self.access_key = access_key or coupang_cfg.access_key
        self.secret_key = secret_key or coupang_cfg.secret_key
        self.api_base = coupang_cfg.api_base
        self.timeout = coupang_cfg.timeout_sec
        self.session = requests.Session()

    @property
    def is_configured(self) -> bool:
        return bool(self.vendor_id and self.access_key and self.secret_key)

    # ─────────────────────────────────────────────────────
    # HMAC 서명 (쿠팡 공식 스펙)
    # ─────────────────────────────────────────────────────
    def _generate_hmac(self, method: str, url_path: str, query_str: str = "") -> str:
        """
        Authorization: CEA algorithm=HmacSHA256, access-key={ACCESS_KEY},
                       signed-date={yyMMdd'T'HHmmss'Z'}, signature={HMAC}

        서명 message = {datetime}{METHOD}{PATH}{QUERY_STRING}
        """
        dt = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
        message = f"{dt}{method}{url_path}{query_str}"

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return (
            f"CEA algorithm=HmacSHA256, access-key={self.access_key}, "
            f"signed-date={dt}, signature={signature}"
        )

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        retry: int = 2,
    ) -> WingResponse:
        """
        WING API 요청 공통 메서드.
        """
        if not self.is_configured:
            return WingResponse(0, {"error": "API Key 미설정"})

        # vendorId 경로 치환
        path = path.replace("{vendorId}", self.vendor_id)

        # 쿼리 문자열
        query_str = ""
        if params:
            query_str = urlencode(params, quote_via=quote)

        for attempt in range(1, retry + 1):
            try:
                auth = self._generate_hmac(method.upper(), path, query_str)
                headers = {
                    "Authorization": auth,
                    "X-Requested-By": self.vendor_id,  # ★ WING 필수
                    "Content-Type": "application/json;charset=UTF-8",
                    "Accept": "application/json",
                }

                url = self.api_base + path
                if query_str:
                    # 서명에 사용한 query_str을 그대로 재사용 (인코딩 불일치 → 401 방지).
                    # urlencode(params) 재호출 시 기본 quote_plus라 서명(quote)과 달라짐.
                    url += "?" + query_str

                log.debug(f"[WING] {method} {path} attempt={attempt}")

                if method.upper() == "GET":
                    resp = self.session.get(url, headers=headers, timeout=self.timeout)
                elif method.upper() == "POST":
                    resp = self.session.post(url, headers=headers,
                                             json=json_body, timeout=self.timeout)
                elif method.upper() == "PUT":
                    resp = self.session.put(url, headers=headers,
                                            json=json_body, timeout=self.timeout)
                elif method.upper() == "DELETE":
                    resp = self.session.delete(url, headers=headers, timeout=self.timeout)
                else:
                    return WingResponse(0, {"error": f"지원 안 하는 메서드: {method}"})

                try:
                    body = resp.json()
                except Exception:
                    body = {"raw": resp.text[:500]}

                wr = WingResponse(resp.status_code, body, resp.text)

                # 429 재시도
                if resp.status_code == 429 and attempt < retry:
                    log.warning(f"[WING] 429 Too Many Requests - {2 ** attempt}초 대기")
                    time.sleep(2 ** attempt)
                    continue

                # 5xx 재시도
                if 500 <= resp.status_code < 600 and attempt < retry:
                    log.warning(f"[WING] {resp.status_code} 서버 오류 - {2 ** attempt}초 대기")
                    time.sleep(2 ** attempt)
                    continue

                return wr

            except requests.exceptions.Timeout:
                log.warning(f"[WING] 타임아웃 (시도 {attempt}/{retry})")
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue
                return WingResponse(0, {"error": "timeout"})
            except Exception as e:
                log.error(f"[WING] 예외: {type(e).__name__}: {e}")
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue
                return WingResponse(0, {"error": str(e)})

        return WingResponse(0, {"error": "unknown"})

    # ═══════════════════════════════════════════════════════════════
    # ① 연결 검증 (인증 체크용)
    # ═══════════════════════════════════════════════════════════════
    def verify_connection(self) -> Tuple[bool, str]:
        """상품 목록 조회 1건으로 인증 체크"""
        params = {"vendorId": self.vendor_id, "nextToken": "", "maxPerPage": 1}
        resp = self._request("GET", Endpoints.SELLER_PRODUCTS_PAGING, params=params)
        if resp.is_success:
            return True, "인증 성공"
        return False, resp.error_summary

    # ═══════════════════════════════════════════════════════════════
    # ② 반품지/출고지 조회 (상품 등록 필수 정보)
    # ═══════════════════════════════════════════════════════════════
    def get_return_centers(self, page_num: int = 1, page_size: int = 50) -> List[Dict]:
        """반품지 목록"""
        params = {"pageNum": page_num, "pageSize": page_size}
        resp = self._request("GET", Endpoints.RETURN_CENTERS, params=params)
        if not resp.is_success:
            log.warning(f"[WING] 반품지 조회 실패: {resp.error_summary}")
            return []
        data = resp.data or {}
        return data.get("content", []) if isinstance(data, dict) else []

    def get_outbound_centers(self, page_num: int = 1, page_size: int = 50) -> List[Dict]:
        """출고지 목록"""
        params = {"pageNum": page_num, "pageSize": page_size}
        resp = self._request("GET", Endpoints.OUTBOUND_CENTERS, params=params)
        if not resp.is_success:
            log.warning(f"[WING] 출고지 조회 실패: {resp.error_summary}")
            return []
        data = resp.data or {}
        return data.get("content", []) if isinstance(data, dict) else []

    # ═══════════════════════════════════════════════════════════════
    # ③ 카테고리 자동 추천 (도완님 선택: "자동으로 되던데")
    # ═══════════════════════════════════════════════════════════════
    def predict_category(self, product_name: str,
                         brand: str = "",
                         attributes: Optional[dict] = None) -> Dict:
        """
        상품명 기반 카테고리 자동 추천.

        Returns:
            {"predictedCategoryId": 63800, "predictedCategoryName": "..."}  또는 {}
        """
        body = {"productName": product_name}
        if brand:
            body["brand"] = brand
        if attributes:
            body["productAttributes"] = attributes

        resp = self._request("POST", Endpoints.CATEGORY_PREDICT, json_body=body)
        if not resp.is_success:
            log.warning(f"[WING] 카테고리 추천 실패: {resp.error_summary}")
            return {}

        data = resp.data or {}
        return data if isinstance(data, dict) else {}

    def get_category_meta(self, category_code: int) -> Dict:
        """
        카테고리 메타데이터 조회 (필수 옵션/속성/고시정보).
        상품 등록 전 미리 조회해서 payload 완성도 높이기.
        """
        path = Endpoints.CATEGORY_META.replace("{displayCategoryCode}", str(category_code))
        resp = self._request("GET", path)
        if not resp.is_success:
            log.warning(f"[WING] 카테고리 메타 실패: {resp.error_summary}")
            return {}
        return resp.data if isinstance(resp.data, dict) else {}

    def get_required_attributes(self, category_code: int) -> List[Dict]:
        """
        카테고리의 '필수 구매옵션' 속성만 추출.

        쿠팡 규칙 (공식 문서 기준):
          required == "MANDATORY"  → 필수
          exposed  == "EXPOSED"    → 구매옵션 (사실상 필수)
        둘 중 하나라도 해당하면 상품 생성 시 attributeValueName을 반드시 채워야 함.

        Returns:
            [{"attributeTypeName": "수량", "dataType": "NUMBER",
              "basicUnit": "개", "usableUnits": [...],
              "required": "MANDATORY", "exposed": "EXPOSED"}, ...]
        """
        meta = self.get_category_meta(category_code)
        if not meta:
            return []

        attrs = meta.get("attributes", [])
        required = []
        for a in attrs:
            if not isinstance(a, dict):
                continue
            is_mandatory = a.get("required", "").upper() == "MANDATORY"
            is_exposed = a.get("exposed", "").upper() == "EXPOSED"
            if is_mandatory or is_exposed:
                required.append({
                    "attributeTypeName": a.get("attributeTypeName", ""),
                    "dataType": a.get("dataType", "STRING"),
                    "basicUnit": a.get("basicUnit", ""),
                    "usableUnits": a.get("usableUnits", []),
                    "required": a.get("required", ""),
                    "exposed": a.get("exposed", ""),
                })
        log.info(f"[WING] 카테고리 {category_code} 필수옵션 {len(required)}개")
        return required

    # ═══════════════════════════════════════════════════════════════
    # ④ 상품 등록
    # ═══════════════════════════════════════════════════════════════
    def create_product(self, payload: dict) -> WingResponse:
        """
        상품 생성 API 호출.

        payload는 build_product_payload()로 생성한 dict.
        성공 시 응답에 sellerProductId 포함.
        """
        log.info(f"[WING] 상품 등록 요청: {payload.get('sellerProductName', '')[:50]}")
        return self._request("POST", Endpoints.PRODUCT_CREATE, json_body=payload)

    def request_approval(self, seller_product_id: int) -> WingResponse:
        """임시저장 상태의 상품을 승인요청"""
        path = Endpoints.APPROVAL_REQUEST.replace(
            "{sellerProductId}", str(seller_product_id)
        )
        return self._request("PUT", path)

    def get_product_detail(self, seller_product_id: int) -> Dict:
        """등록된 상품 상세 조회"""
        path = Endpoints.SELLER_PRODUCT_DETAIL.replace(
            "{sellerProductId}", str(seller_product_id)
        )
        resp = self._request("GET", path)
        return resp.data if resp.is_success and resp.data else {}


# ═══════════════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    client = CoupangWingClient()
    if not client.is_configured:
        print("❌ 환경변수 설정 필요")
        print("   COUPANG_WING_VENDOR_ID / ACCESS_KEY / SECRET_KEY")
        exit(1)

    print("🔑 인증 검증...")
    ok, msg = client.verify_connection()
    print(f"   {'✅' if ok else '❌'} {msg}")

    if ok:
        print("\n📦 반품지 조회...")
        centers = client.get_return_centers()
        for c in centers[:3]:
            print(f"   • {c.get('returnCenterCode')} | {c.get('shippingPlaceName')}")

        print("\n📂 카테고리 추천 (테스트)...")
        cat = client.predict_category("무선 블루투스 이어폰")
        print(f"   → {cat}")
