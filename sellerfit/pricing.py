"""
pricing.py - 도매가 → 쿠팡 판매가 계산
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
도완님 결정:
  "2. 판매가는 퍼센트나 최소마진 몇% 이런식으로 구조 잡더라구"

3가지 모드 지원 (config.py에서 설정):
  - multiply:    도매가 × multiplier  (예: 2.5배)
  - add_margin:  도매가 × (1 + rate/100)  (예: +50%)
  - min_margin:  최소 마진율 보장 → 판매가 = 도매가 / (1 - min/100)

모든 모드에서:
  - 100원/1000원 단위 반올림 (round_to 설정)
  - 배송비 원가 포함 옵션 (PRICING_ADD_SHIPPING)
  - 원가 + 판매가 + 마진액/마진율 상세 내역 반환
"""

from dataclasses import dataclass, asdict
from typing import Dict

from config import pricing_cfg
from logger import log


@dataclass
class PricingResult:
    """가격 계산 결과 (디버깅/로그용 상세 내역 포함)"""
    dome_base_price: int       # 도매가 (1개당 단가)
    shipping_fee: int          # 배송비 (포함 여부 따라)
    cost: int                  # 원가 (도매가 + (옵션)배송비)
    mode: str                  # 적용 모드
    raw_sale_price: int        # 반올림 전 판매가
    sale_price: int            # 최종 판매가
    original_price: int        # 표시용 원가 (쿠팡 'originalPrice'에 들어감 - 할인 표시)
    margin_amount: int         # 마진 금액
    margin_rate: float         # 마진율 (%)
    round_to: int              # 반올림 단위

    def to_dict(self) -> Dict:
        return asdict(self)


class PriceCalculator:
    """가격 계산기"""

    def __init__(self, cfg=pricing_cfg):
        self.cfg = cfg

    def calculate(self, dome_base_price: int,
                  original_price_ratio: float = 1.2) -> PricingResult:
        """
        도매가 → 쿠팡 판매가 계산.

        Args:
            dome_base_price: 도매꾹 1개당 단가
            original_price_ratio: 쿠팡에서 할인 표시용 '원가'를 판매가의 몇 배로 표시할지
                                 (1.2 = 판매가 × 1.2를 원가로 표시, 기본 20% 할인 느낌)

        Returns:
            PricingResult
        """
        if dome_base_price <= 0:
            log.warning(f"[PRICE] 잘못된 도매가: {dome_base_price}")
            return PricingResult(
                dome_base_price=dome_base_price, shipping_fee=0, cost=0,
                mode=self.cfg.mode, raw_sale_price=0, sale_price=0,
                original_price=0, margin_amount=0, margin_rate=0.0,
                round_to=self.cfg.round_to,
            )

        # 원가 (배송비 포함 옵션)
        shipping = self.cfg.shipping_fee if self.cfg.add_shipping_fee else 0
        cost = dome_base_price + shipping

        # 모드별 계산
        mode = (self.cfg.mode or "multiply").lower()
        if mode == "multiply":
            raw = cost * self.cfg.multiplier
        elif mode in ("add_margin", "margin_rate", "percent"):
            raw = cost * (1.0 + self.cfg.margin_rate_percent / 100.0)
        elif mode in ("min_margin", "minimum_margin"):
            denom = 1.0 - self.cfg.min_margin_percent / 100.0
            if denom <= 0:
                log.warning("[PRICE] min_margin >= 100% 부적절 → multiply로 폴백")
                raw = cost * self.cfg.multiplier
            else:
                raw = cost / denom
        else:
            log.warning(f"[PRICE] 알 수 없는 모드 '{mode}' → multiply 폴백")
            raw = cost * self.cfg.multiplier

        raw_sale = int(round(raw))
        # 반올림 단위
        sale_price = self._round_up(raw_sale, self.cfg.round_to)

        # 원가(할인표시용)
        original_price = self._round_up(int(sale_price * original_price_ratio), self.cfg.round_to)

        # 마진
        margin_amount = sale_price - cost
        margin_rate = (margin_amount / sale_price * 100) if sale_price > 0 else 0.0

        result = PricingResult(
            dome_base_price=dome_base_price,
            shipping_fee=shipping,
            cost=cost,
            mode=mode,
            raw_sale_price=raw_sale,
            sale_price=sale_price,
            original_price=original_price,
            margin_amount=margin_amount,
            margin_rate=round(margin_rate, 2),
            round_to=self.cfg.round_to,
        )

        log.info(
            f"[PRICE] 도매가 {dome_base_price:,}원 → 판매가 {sale_price:,}원 "
            f"(마진 {margin_amount:,}원 / {result.margin_rate:.1f}%, 모드={mode})"
        )
        return result

    @staticmethod
    def _round_up(value: int, unit: int) -> int:
        """올림 (100원/1000원 단위)"""
        if unit <= 1:
            return value
        return ((value + unit - 1) // unit) * unit


# ═══════════════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    calc = PriceCalculator()
    tests = [9850, 3200, 15000, 48000]
    for p in tests:
        r = calc.calculate(p)
        print(f"  {p:>7,}원 → {r.sale_price:>7,}원  "
              f"(마진 {r.margin_rate:5.1f}%, 원가표시 {r.original_price:,})")
