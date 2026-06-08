"""
config.py - SellerFit Slice 1 설정 및 환경변수 관리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모든 설정값은 환경변수 또는 .env 파일에서 로드.
하드코딩 금지 (제8원칙).
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv 미설치여도 환경변수만으로 동작


# ═══════════════════════════════════════════════════════════════
# 경로 상수 (EXE 빌드 대응 - 제6원칙)
# ═══════════════════════════════════════════════════════════════
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

DATA_DIR = BASE_DIR / "data"
SNAPSHOTS_DIR = BASE_DIR / "snapshots"
CACHE_DIR = BASE_DIR / "cache"
LOG_DIR = BASE_DIR / "logs"

for d in (DATA_DIR, SNAPSHOTS_DIR, CACHE_DIR, LOG_DIR):
    d.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# 헬퍼
# ═══════════════════════════════════════════════════════════════
def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").lower()
    if val in ("true", "1", "yes", "y"):
        return True
    if val in ("false", "0", "no", "n"):
        return False
    return default


# ═══════════════════════════════════════════════════════════════
# API 설정
# ═══════════════════════════════════════════════════════════════
@dataclass
class DomeggookConfig:
    """도매꾹 Open API 설정"""
    api_key: str = field(default_factory=lambda: _env("DOMEGGOOK_API_KEY"))
    api_base: str = "https://domeggook.com/ssl/api/"
    api_version: str = "4.4"
    timeout_sec: int = field(default_factory=lambda: _env_int("DOMEGGOOK_TIMEOUT", 15))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class CoupangWingConfig:
    """쿠팡 WING Open API 설정"""
    vendor_id: str = field(default_factory=lambda: _env("COUPANG_WING_VENDOR_ID"))
    access_key: str = field(default_factory=lambda: _env("COUPANG_WING_ACCESS_KEY"))
    secret_key: str = field(default_factory=lambda: _env("COUPANG_WING_SECRET_KEY"))
    # WING 로그인 아이디 (상품 생성 시 vendorUserId 필드로 필요)
    vendor_user_id: str = field(default_factory=lambda: _env("COUPANG_WING_USER_ID"))
    api_base: str = "https://api-gateway.coupang.com"
    timeout_sec: int = field(default_factory=lambda: _env_int("COUPANG_TIMEOUT", 30))

    @property
    def is_configured(self) -> bool:
        return bool(self.vendor_id and self.access_key and self.secret_key)


# ═══════════════════════════════════════════════════════════════
# 가격 계산 설정
# ═══════════════════════════════════════════════════════════════
@dataclass
class PricingConfig:
    """
    가격 계산 설정 (도매가 → 쿠팡 판매가)

    mode:
      "multiply"    → 도매가 × multiplier (예: 2.5배)
      "add_margin"  → 도매가 + (도매가 × margin_rate / 100)  (예: +50%)
      "min_margin"  → 최소 마진율 보장 (판매가 = 도매가 / (1 - min_margin/100))

    도완님 요구: "판매가는 퍼센트나 최소마진 몇% 이런식으로" → mode 선택지 제공
    """
    mode: str = field(default_factory=lambda: _env("PRICING_MODE", "multiply"))
    multiplier: float = field(default_factory=lambda: _env_float("PRICING_MULTIPLIER", 2.5))
    margin_rate_percent: float = field(default_factory=lambda: _env_float("PRICING_MARGIN_RATE", 50.0))
    min_margin_percent: float = field(default_factory=lambda: _env_float("PRICING_MIN_MARGIN", 30.0))
    round_to: int = field(default_factory=lambda: _env_int("PRICING_ROUND_TO", 100))  # 100원 단위 반올림
    add_shipping_fee: bool = field(default_factory=lambda: _env_bool("PRICING_ADD_SHIPPING", False))
    shipping_fee: int = field(default_factory=lambda: _env_int("PRICING_SHIPPING_FEE", 2500))


# ═══════════════════════════════════════════════════════════════
# 상품 등록 설정
# ═══════════════════════════════════════════════════════════════
@dataclass
class ProductRegistrationConfig:
    """
    쿠팡 상품 등록 기본값

    도완님 결정:
      - 배송: 선결제 고정 → deliveryChargeType="NOT_FREE"
      - 옵션: Slice 1은 단일상품만 (items 1개)
      - 이미지: 크롤링 방식 (다운로드 → 쿠팡 업로드)
    """
    # 배송/결제
    delivery_method: str = "SEQUENCIAL"                # 일반배송
    delivery_charge_type: str = "NOT_FREE"             # 유료배송 (선결제)
    delivery_charge: int = field(default_factory=lambda: _env_int("DEFAULT_DELIVERY_CHARGE", 2500))
    delivery_charge_on_return: int = field(default_factory=lambda: _env_int("DEFAULT_RETURN_CHARGE", 2500))
    delivery_company_code: str = field(default_factory=lambda: _env("DEFAULT_DELIVERY_COMPANY", "CJGLS"))
    remote_area_deliverable: str = "N"
    union_delivery_type: str = "UNION_DELIVERY"
    free_ship_over_amount: int = 0

    # 판매 기간
    sale_start_immediate: bool = True                  # True=현재, False=별도 설정
    sale_end_year: int = 2099

    # 승인 요청 여부
    # False = 임시저장 (WING에서 수동 검토 후 승인요청)
    # True  = 자동 승인요청 (즉시 심사 진입)
    auto_request_approval: bool = field(default_factory=lambda: _env_bool("AUTO_REQUEST_APPROVAL", False))

    # 이미지
    max_images: int = field(default_factory=lambda: _env_int("MAX_IMAGES", 10))

    # 수량/구매 제한
    maximum_buy_count: int = field(default_factory=lambda: _env_int("MAX_BUY_COUNT", 999))
    maximum_buy_for_person: int = 0
    stock_qty: int = field(default_factory=lambda: _env_int("STOCK_QTY", 999))

    # 재시도
    retry_count: int = field(default_factory=lambda: _env_int("RETRY_COUNT", 3))
    retry_delay_sec: int = field(default_factory=lambda: _env_int("RETRY_DELAY", 2))


# ═══════════════════════════════════════════════════════════════
# 싱글톤 인스턴스
# ═══════════════════════════════════════════════════════════════
domeggook_cfg = DomeggookConfig()
coupang_cfg = CoupangWingConfig()
pricing_cfg = PricingConfig()
registration_cfg = ProductRegistrationConfig()


def print_config_summary():
    """설정 로드 상태 출력 (시작 시 호출)"""
    print("=" * 60)
    print("  📋 SellerFit Slice 1 - 설정")
    print("=" * 60)
    print(f"  도매꾹 API:   {'✅ 설정됨' if domeggook_cfg.is_configured else '❌ 미설정'}")
    print(f"  쿠팡 WING:    {'✅ 설정됨' if coupang_cfg.is_configured else '❌ 미설정'}")
    print(f"  VendorId:     {coupang_cfg.vendor_id or '(없음)'}")
    print(f"  가격 모드:    {pricing_cfg.mode} "
          f"(배수={pricing_cfg.multiplier}, 마진={pricing_cfg.margin_rate_percent}%)")
    print(f"  배송:         {registration_cfg.delivery_charge}원 "
          f"({'선결제' if registration_cfg.delivery_charge_type == 'NOT_FREE' else '무료'})")
    print(f"  승인 요청:    {'자동' if registration_cfg.auto_request_approval else '임시저장'}")
    print(f"  최대 이미지:  {registration_cfg.max_images}장")
    print("=" * 60)


def validate_or_exit():
    """필수 설정 누락 시 종료"""
    missing = []
    if not domeggook_cfg.is_configured:
        missing.append("DOMEGGOOK_API_KEY")
    if not coupang_cfg.is_configured:
        if not coupang_cfg.vendor_id:
            missing.append("COUPANG_WING_VENDOR_ID")
        if not coupang_cfg.access_key:
            missing.append("COUPANG_WING_ACCESS_KEY")
        if not coupang_cfg.secret_key:
            missing.append("COUPANG_WING_SECRET_KEY")
    if missing:
        print("❌ 필수 환경변수 누락:")
        for k in missing:
            print(f"   - {k}")
        print("\n.env 파일 또는 환경변수로 설정 후 재실행하세요.")
        sys.exit(1)


if __name__ == "__main__":
    print_config_summary()
