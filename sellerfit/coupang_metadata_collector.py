"""
coupang_metadata_collector.py - 쿠팡 환경 정보 사전 수집
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
도완님 요청: "정보 최대한 모으기"

쿠팡 WING에서 가져와야 할 환경 설정 데이터를
최초 1회 수집해서 cache/ 폴더에 저장.

수집 대상:
  1. 반품지 목록 (returnCenterCode 확보)
  2. 출고지 목록 (outboundShippingPlaceCode 확보)
  3. (선택) 현재 등록된 상품 통계

이 정보가 없으면 상품 등록 API 호출 자체가 실패함.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import CACHE_DIR
from coupang_wing_client import CoupangWingClient
from logger import log


CACHE_FILE = CACHE_DIR / "coupang_metadata.json"
CACHE_TTL_HOURS = 24  # 1일마다 갱신


class CoupangMetadataCollector:
    """쿠팡 환경 정보 수집 + 캐시"""

    def __init__(self, client: Optional[CoupangWingClient] = None):
        self.client = client or CoupangWingClient()

    # ═══════════════════════════════════════════════════════════
    # 수집
    # ═══════════════════════════════════════════════════════════
    def collect_all(self, force: bool = False) -> Dict:
        """
        모든 메타데이터 수집 + 캐시 저장.

        Args:
            force: True면 캐시 무시하고 재수집

        Returns:
            {
                "vendor_id": "...",
                "return_centers": [...],
                "outbound_centers": [...],
                "default_return_center": {...},
                "default_outbound_center": {...},
                "collected_at": "...",
            }
        """
        # 캐시 유효성 체크
        if not force:
            cached = self.load_cache()
            if cached and self._is_cache_valid(cached):
                log.info("[META] 캐시 사용 (유효)")
                return cached

        log.info("[META] 쿠팡 메타데이터 수집 시작...")

        # 인증 선제 체크
        ok, msg = self.client.verify_connection()
        if not ok:
            log.error(f"[META] 인증 실패로 수집 중단: {msg}")
            return {"error": msg, "collected_at": datetime.now().isoformat()}

        result = {
            "vendor_id": self.client.vendor_id,
            "collected_at": datetime.now().isoformat(),
            "return_centers": [],
            "outbound_centers": [],
            "default_return_center": None,
            "default_outbound_center": None,
        }

        # 반품지
        log.info("[META] 반품지 조회 중...")
        returns = self.client.get_return_centers()
        result["return_centers"] = self._normalize_centers(returns, "return")
        if result["return_centers"]:
            result["default_return_center"] = result["return_centers"][0]
            log.info(f"[META] ✅ 반품지 {len(result['return_centers'])}개 "
                     f"(기본: {result['default_return_center']['code']})")
        else:
            log.warning("[META] ⚠️ 반품지 0개 - WING에서 먼저 등록 필요")

        # 출고지
        log.info("[META] 출고지 조회 중...")
        outbounds = self.client.get_outbound_centers()
        result["outbound_centers"] = self._normalize_centers(outbounds, "outbound")
        if result["outbound_centers"]:
            result["default_outbound_center"] = result["outbound_centers"][0]
            log.info(f"[META] ✅ 출고지 {len(result['outbound_centers'])}개 "
                     f"(기본: {result['default_outbound_center']['code']})")
        else:
            log.warning("[META] ⚠️ 출고지 0개 - WING에서 먼저 등록 필요")

        # 캐시 저장
        self.save_cache(result)

        return result

    @staticmethod
    def _normalize_centers(raw_list: List[Dict], kind: str) -> List[Dict]:
        """반품지/출고지 응답 구조 통일"""
        code_key = "returnCenterCode" if kind == "return" else "outboundShippingPlaceCode"
        normalized = []
        for c in raw_list:
            if not isinstance(c, dict):
                continue
            # 주소 추출 (응답 구조가 복잡해서 폴백 여러 개)
            addresses = c.get("placeAddresses", [])
            addr = ""
            postcode = ""
            phone = ""
            if addresses and isinstance(addresses, list):
                first = addresses[0]
                if isinstance(first, dict):
                    addr = first.get("returnAddress", "") or first.get("address", "")
                    postcode = first.get("returnZipCode", "") or first.get("postcode", "")
                    phone = first.get("companyContactNumber", "") or first.get("contactNumber", "")

            normalized.append({
                "code": str(c.get(code_key, "")),
                "name": c.get("shippingPlaceName", ""),
                "usable": c.get("usable", True),
                "address": addr,
                "postcode": postcode,
                "phone": phone,
                "raw": c,  # 원본 보존
            })
        return normalized

    # ═══════════════════════════════════════════════════════════
    # 캐시 입출력
    # ═══════════════════════════════════════════════════════════
    def load_cache(self) -> Optional[Dict]:
        if not CACHE_FILE.exists():
            return None
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"[META] 캐시 읽기 실패: {e}")
            return None

    def save_cache(self, data: Dict):
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8"
            )
            log.info(f"[META] 캐시 저장: {CACHE_FILE}")
        except Exception as e:
            log.error(f"[META] 캐시 저장 실패: {e}")

    @staticmethod
    def _is_cache_valid(cached: Dict) -> bool:
        collected_at = cached.get("collected_at")
        if not collected_at:
            return False
        try:
            then = datetime.fromisoformat(collected_at)
            delta_hours = (datetime.now() - then).total_seconds() / 3600
            return delta_hours < CACHE_TTL_HOURS
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    collector = CoupangMetadataCollector()
    data = collector.collect_all(force=True)

    if data.get("error"):
        print(f"❌ {data['error']}")
        exit(1)

    print("\n" + "=" * 60)
    print(f"📦 쿠팡 메타데이터 수집 완료")
    print("=" * 60)
    print(f"  벤더 ID:    {data['vendor_id']}")
    print(f"  반품지:     {len(data['return_centers'])}개")
    print(f"  출고지:     {len(data['outbound_centers'])}개")
    if data["default_return_center"]:
        c = data["default_return_center"]
        print(f"  기본반품지: {c['code']} | {c['name']}")
    if data["default_outbound_center"]:
        c = data["default_outbound_center"]
        print(f"  기본출고지: {c['code']} | {c['name']}")
    print(f"  캐시:       {CACHE_FILE}")
