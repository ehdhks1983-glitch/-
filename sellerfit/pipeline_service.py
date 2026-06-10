"""
pipeline_service.py - GUI용 서비스 레이어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLI(main.py)는 "조회→등록"을 한 번에 실행하지만,
GUI는 사용자가 "조회"로 확인한 뒤 "등록"을 누르는 2단계가 필요.

그래서 파이프라인을 2개 메서드로 분리:
  - fetch_product(item_no, pricing_override)  → 조회만 (등록 X)
  - register_product(prepared)               → 조회 결과로 실제 등록

기존 엔진 모듈(domeggook_client 등)은 그대로 재활용. 수정 없음.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict

from config import registration_cfg, pricing_cfg
from logger import log
from data_snapshot import SnapshotWriter
from domeggook_client import DomeggookClient, DomeggookProduct
from coupang_wing_client import CoupangWingClient
from coupang_metadata_collector import CoupangMetadataCollector
from category_mapper import CategoryMapper
from pricing import PriceCalculator, PricingResult
from image_pipeline import ImagePipeline
from payload_builder import PayloadBuilder, validate_payload, get_payload_warnings


# ═══════════════════════════════════════════════════════════════
# 조회 결과 (GUI 표시 + 등록에 재사용)
# ═══════════════════════════════════════════════════════════════
@dataclass
class PreparedProduct:
    """조회 단계 결과 — 화면 표시용 + 등록에 그대로 전달"""
    item_no: str = ""
    ok: bool = False
    error: str = ""

    # 도매꾹
    dome_product: Optional[DomeggookProduct] = None
    title: str = ""
    base_price: int = 0
    image_count: int = 0
    option_count: int = 0

    # 가격
    pricing: Optional[PricingResult] = None
    sale_price: int = 0
    margin_rate: float = 0.0

    # 카테고리
    category_code: Optional[int] = None
    category_name: str = ""

    # 이미지
    usable_image_urls: List[str] = field(default_factory=list)

    # 쿠팡 환경
    return_center: Optional[Dict] = None
    outbound_center: Optional[Dict] = None

    # 등록 입력 보관 (가격 재계산 시 payload 재조립용 — F-02)
    brand: str = ""
    required_attributes: List[Dict] = field(default_factory=list)

    # 등록용 payload (조회 시 미리 만들어둠)
    payload: Optional[Dict] = None

    # 스냅샷 핸들 (등록까지 같은 폴더에 저장)
    _snap: Optional[SnapshotWriter] = None


# ═══════════════════════════════════════════════════════════════
# 서비스
# ═══════════════════════════════════════════════════════════════
class SellerFitService:
    """GUI ↔ 엔진 연결 서비스"""

    def __init__(self):
        self.dome_client = DomeggookClient()
        self.wing_client = CoupangWingClient()
        self.meta_collector = CoupangMetadataCollector(self.wing_client)
        self.category_mapper = CategoryMapper(self.wing_client)
        self.image_pipeline = ImagePipeline(max_images=registration_cfg.max_images)
        self.payload_builder = PayloadBuilder()

        # 메타데이터 캐시 (한 번만 조회)
        self._meta = None

    # ───────────────────────────────────────────────────────────
    # 환경 점검 (GUI 시작 시 호출)
    # ───────────────────────────────────────────────────────────
    def check_environment(self) -> Dict:
        """
        API 키 + 반품지/출고지 점검.
        Returns: {"ok": bool, "messages": [...], "meta": {...}}
        """
        result = {"ok": False, "messages": [], "meta": None}

        # 1. 설정 체크
        from config import domeggook_cfg, coupang_cfg
        if not domeggook_cfg.is_configured:
            result["messages"].append("❌ 도매꾹 API Key 미설정")
        if not coupang_cfg.is_configured:
            result["messages"].append("❌ 쿠팡 WING API 키 미설정 (VendorId/Access/Secret)")

        if result["messages"]:
            return result

        # 2. 쿠팡 인증 + 반품지/출고지
        meta = self.meta_collector.collect_all()
        if meta.get("error"):
            result["messages"].append(f"❌ 쿠팡 연결 실패: {meta['error']}")
            return result

        if not meta.get("default_return_center"):
            result["messages"].append("❌ 반품지 없음 (WING에서 등록 필요)")
        if not meta.get("default_outbound_center"):
            result["messages"].append("❌ 출고지 없음 (WING에서 등록 필요)")

        if result["messages"]:
            return result

        self._meta = meta
        result["ok"] = True
        result["meta"] = meta
        result["messages"].append(
            f"✅ 준비 완료 (반품지 {len(meta['return_centers'])}개, "
            f"출고지 {len(meta['outbound_centers'])}개)"
        )
        return result

    # ───────────────────────────────────────────────────────────
    # ① 조회 (등록 X)
    # ───────────────────────────────────────────────────────────
    def fetch_product(
        self,
        item_no: str,
        pricing_mode: str = None,
        pricing_value: float = None,
        brand: str = "",
        progress: Optional[Callable[[str], None]] = None,
    ) -> PreparedProduct:
        """
        도매꾹 조회 → 가격/카테고리/이미지 → payload까지 준비 (등록은 안 함).

        Args:
            item_no: 도매꾹 상품번호
            pricing_mode: "multiply"|"add_margin"|"min_margin" (None이면 .env)
            pricing_value: 모드별 수치 (배수 또는 %) (None이면 .env)
            brand: 브랜드명
            progress: 진행상황 콜백 (GUI 로그용)
        """
        def emit(msg):
            log.info(msg)
            if progress:
                progress(msg)

        prepared = PreparedProduct(item_no=item_no, brand=brand)
        snap = SnapshotWriter(item_no)
        prepared._snap = snap

        try:
            # 환경 메타 (캐시)
            if not self._meta:
                emit("쿠팡 환경 확인 중...")
                env = self.check_environment()
                if not env["ok"]:
                    prepared.error = " / ".join(env["messages"])
                    return prepared
            prepared.return_center = self._meta["default_return_center"]
            prepared.outbound_center = self._meta["default_outbound_center"]

            # 1. 도매꾹 조회
            emit(f"도매꾹 상품 조회 중... (no={item_no})")
            dome, raw_xml = self.dome_client.get_item_view(item_no)
            if raw_xml:
                snap.save("02_domeggook_raw", raw_xml, file_ext="xml")
            if not dome:
                prepared.error = "도매꾹 상품 조회 실패"
                emit("❌ 도매꾹 조회 실패")
                return prepared
            snap.save("02_domeggook_parsed", dome.to_dict())

            if not dome.is_valid:
                prepared.error = (f"상품 데이터 부족 (가격={dome.base_price}, "
                                  f"이미지={len(dome.images)}장)")
                emit(f"❌ {prepared.error}")
                return prepared

            prepared.dome_product = dome
            prepared.title = dome.title
            prepared.base_price = dome.base_price
            prepared.image_count = len(dome.images)
            prepared.option_count = len(dome.options)
            emit(f"✅ 상품: {dome.title[:40]}")

            # 2. 가격 계산 (GUI 오버라이드 반영)
            emit("가격 계산 중...")
            calc = self._make_calculator(pricing_mode, pricing_value)
            pricing = calc.calculate(dome.base_price)
            prepared.pricing = pricing
            prepared.sale_price = pricing.sale_price
            prepared.margin_rate = pricing.margin_rate
            snap.save("03_pricing", pricing.to_dict())
            emit(f"✅ 판매가 {pricing.sale_price:,}원 (마진 {pricing.margin_rate:.1f}%)")

            # 3. 카테고리
            emit("카테고리 자동 매핑 중...")
            cat = self.category_mapper.get_category(dome.title, brand=brand)
            snap.save("04_category", cat)
            if not cat.get("display_category_code"):
                prepared.error = "카테고리 추천 실패"
                emit("❌ 카테고리 추천 실패")
                return prepared
            prepared.category_code = cat["display_category_code"]
            prepared.category_name = cat.get("category_name", "")
            emit(f"✅ 카테고리: {prepared.category_name} ({prepared.category_code})")

            # 3-1. 카테고리 필수 구매옵션 조회
            emit("카테고리 필수옵션 확인 중...")
            required_attrs = self.wing_client.get_required_attributes(prepared.category_code)
            snap.save("04b_required_attributes", required_attrs)
            prepared.required_attributes = required_attrs
            if required_attrs:
                emit(f"✅ 필수옵션 {len(required_attrs)}개: "
                     f"{[a['attributeTypeName'] for a in required_attrs][:5]}")
            else:
                emit("⚠️ 필수옵션 정보 없음 (등록 시 거부될 수 있음)")

            # 4. 이미지
            emit("이미지 접근성 확인 중...")
            img = self.image_pipeline.process(dome.images)
            snap.save("05_images", img.to_dict())
            prepared.usable_image_urls = img.usable_urls
            if not img.usable_urls:
                prepared.error = "사용 가능한 이미지 없음"
                emit("❌ 사용 가능한 이미지 없음")
                return prepared
            emit(f"✅ 이미지 {len(img.usable_urls)}장 사용 가능")

            # 5. payload 미리 조립
            emit("쿠팡 등록 양식 준비 중...")
            payload = self.payload_builder.build(
                dome_product=dome,
                pricing=pricing,
                display_category_code=prepared.category_code,
                image_urls=img.usable_urls,
                return_center=prepared.return_center,
                outbound_center=prepared.outbound_center,
                brand=brand,
                required_attributes=required_attrs,
            )
            problems = validate_payload(payload)
            if problems:
                prepared.error = "양식 검증 실패: " + ", ".join(problems[:3])
                emit(f"❌ {prepared.error}")
                snap.save("06_payload_invalid", {"payload": payload, "problems": problems})
                return prepared

            # 소프트 경고 (등록은 가능하나 거부 위험)
            warnings = get_payload_warnings(payload)
            for w in warnings:
                emit(f"⚠️ {w}")

            prepared.payload = payload
            snap.save("06_coupang_payload", payload)

            prepared.ok = True
            emit("✅ 조회 완료 — 등록 준비됨")
            return prepared

        except Exception as e:
            log.exception("fetch_product 예외")
            prepared.error = f"{type(e).__name__}: {e}"
            emit(f"💥 오류: {prepared.error}")
            return prepared

    # ───────────────────────────────────────────────────────────
    # ①-b 가격만 재계산 (도매꾹/쿠팡 재호출 없음 — F-02)
    # ───────────────────────────────────────────────────────────
    def recompute_price(
        self,
        prepared: PreparedProduct,
        pricing_mode: str = None,
        pricing_value: float = None,
        progress: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        조회 완료된 상품의 판매가만 다시 계산하고 payload를 갱신한다.
        도매꾹 호출 한도(분당 180회)를 아끼기 위해 네트워크를 쓰지 않는다.

        Returns: 성공 여부 (검증 실패 시 기존 가격/payload 유지)
        """
        def emit(msg):
            log.info(msg)
            if progress:
                progress(msg)

        if not prepared or not prepared.ok or not prepared.dome_product:
            emit("⚠️ 조회된 상품이 없어 재계산할 수 없습니다. 먼저 조회하세요.")
            return False

        calc = self._make_calculator(pricing_mode, pricing_value)
        pricing = calc.calculate(prepared.dome_product.base_price)

        payload = self.payload_builder.build(
            dome_product=prepared.dome_product,
            pricing=pricing,
            display_category_code=prepared.category_code,
            image_urls=prepared.usable_image_urls,
            return_center=prepared.return_center,
            outbound_center=prepared.outbound_center,
            brand=prepared.brand,
            required_attributes=prepared.required_attributes,
        )
        problems = validate_payload(payload)
        if problems:
            emit(f"⚠️ 재계산 양식 검증 실패 (기존 가격 유지): {problems[:3]}")
            return False

        prepared.pricing = pricing
        prepared.sale_price = pricing.sale_price
        prepared.margin_rate = pricing.margin_rate
        prepared.payload = payload
        if prepared._snap:
            prepared._snap.save("03_pricing", pricing.to_dict())
            prepared._snap.save("06_coupang_payload", payload)
        emit(f"✅ 판매가 {pricing.sale_price:,}원 (마진 {pricing.margin_rate:.1f}%) — 재계산 완료")
        return True

    # ───────────────────────────────────────────────────────────
    # ② 등록 (조회 결과 사용)
    # ───────────────────────────────────────────────────────────
    def register_product(
        self,
        prepared: PreparedProduct,
        request_approval: bool = False,
        progress: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """
        조회로 준비된 payload를 실제 쿠팡에 등록.

        Returns:
            {"ok": bool, "seller_product_id": ..., "error": ...}
        """
        def emit(msg):
            log.info(msg)
            if progress:
                progress(msg)

        result = {"ok": False, "seller_product_id": None, "error": ""}

        if not prepared or not prepared.ok or not prepared.payload:
            result["error"] = "조회가 완료되지 않았습니다. 먼저 조회하세요."
            return result

        snap = prepared._snap

        try:
            emit("쿠팡에 상품 등록 중...")
            resp = self.wing_client.create_product(prepared.payload)
            if snap:
                snap.save("07_coupang_response", {
                    "status_code": resp.status_code,
                    "body": resp.body,
                    "is_success": resp.is_success,
                })

            if not resp.is_success:
                result["error"] = resp.error_summary
                emit(f"❌ 등록 실패: {resp.friendly_message}")
                emit(f"   (상세: {resp.error_summary})")
                if snap:
                    snap.finalize(status="failed_create", summary=result)
                return result

            spid = None
            if isinstance(resp.data, dict):
                spid = resp.data.get("sellerProductId")
            elif isinstance(resp.data, (int, str)):
                spid = resp.data
            result["seller_product_id"] = spid
            emit(f"✅ 등록 성공! 상품ID: {spid}")

            # 승인 요청 (선택)
            if request_approval and spid:
                emit("승인 요청 중...")
                ap = self.wing_client.request_approval(spid)
                if snap:
                    snap.save("08_approval_response",
                              {"status_code": ap.status_code, "body": ap.body})
                if ap.is_success:
                    emit("✅ 승인 요청 완료")
                else:
                    emit(f"⚠️ 승인 요청 실패 (등록은 됨): {ap.friendly_message} "
                         f"/ 상세: {ap.error_summary}")

            result["ok"] = True
            if snap:
                snap.finalize(status="success", summary=result)
            return result

        except Exception as e:
            log.exception("register_product 예외")
            result["error"] = f"{type(e).__name__}: {e}"
            emit(f"💥 오류: {result['error']}")
            if snap:
                snap.finalize(status="exception", summary=result)
            return result

    # ───────────────────────────────────────────────────────────
    # 가격 계산기 (GUI 오버라이드 반영)
    # ───────────────────────────────────────────────────────────
    @staticmethod
    def _make_calculator(mode: str = None, value: float = None) -> PriceCalculator:
        """
        GUI에서 넘어온 모드/수치로 임시 설정 만들어 계산기 생성.
        None이면 .env 기본값 사용.
        """
        if mode is None and value is None:
            return PriceCalculator()  # .env 기본

        # pricing_cfg 복제 후 오버라이드
        import copy
        cfg = copy.copy(pricing_cfg)
        if mode:
            cfg.mode = mode
        if value is not None:
            if (mode or cfg.mode) == "multiply":
                cfg.multiplier = value
            elif (mode or cfg.mode) in ("add_margin",):
                cfg.margin_rate_percent = value
            elif (mode or cfg.mode) in ("min_margin",):
                cfg.min_margin_percent = value
        return PriceCalculator(cfg)
