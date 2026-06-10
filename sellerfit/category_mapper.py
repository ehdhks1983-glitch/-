"""
category_mapper.py - 도매꾹 → 쿠팡 카테고리 매핑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
도완님 결정: "1. 자동으로 되던데" → 쿠팡 predict API 사용

동작:
  1. 도매꾹 상품명으로 쿠팡 카테고리 추천 API 호출
  2. 결과(displayCategoryCode) 반환
  3. 매핑 이력 cache/category_mapping.json 에 축적
     → 나중에 동일/유사 상품명 조회 시 API 호출 없이 즉시 반환
     → 사용량 추적 + 품질 개선 데이터로 활용
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from config import CACHE_DIR
from coupang_wing_client import CoupangWingClient
from logger import log


MAPPING_CACHE = CACHE_DIR / "category_mapping.json"


class CategoryMapper:
    """도매꾹 → 쿠팡 카테고리 매핑 (API 추천 + 로컬 캐시)"""

    def __init__(self, client: Optional[CoupangWingClient] = None):
        self.client = client or CoupangWingClient()
        self._cache = self._load_cache()

    # ═══════════════════════════════════════════════════════════
    # 캐시 로드/저장
    # ═══════════════════════════════════════════════════════════
    def _load_cache(self) -> Dict:
        if not MAPPING_CACHE.exists():
            return {"mappings": {}, "stats": {"api_calls": 0, "cache_hits": 0}}
        try:
            return json.loads(MAPPING_CACHE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"[CAT] 캐시 로드 실패: {e}")
            return {"mappings": {}, "stats": {"api_calls": 0, "cache_hits": 0}}

    def _save_cache(self):
        try:
            MAPPING_CACHE.parent.mkdir(parents=True, exist_ok=True)
            # 원자적 저장: 임시파일에 쓰고 교체 — 중단돼도 기존 캐시 안 깨짐 (F-04)
            tmp = MAPPING_CACHE.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            os.replace(tmp, MAPPING_CACHE)
        except Exception as e:
            log.warning(f"[CAT] 캐시 저장 실패: {e}")

    # ═══════════════════════════════════════════════════════════
    # 핵심: 매핑
    # ═══════════════════════════════════════════════════════════
    def get_category(
        self,
        product_name: str,
        dome_category_path: str = "",
        brand: str = "",
        use_cache: bool = True,
    ) -> Dict:
        """
        도매꾹 상품 정보 → 쿠팡 displayCategoryCode

        Args:
            product_name: 도매꾹 상품명 (필수)
            dome_category_path: 도매꾹 카테고리 경로 (힌트)
            brand: 브랜드명
            use_cache: 캐시 사용 여부

        Returns:
            {
                "display_category_code": 63800,
                "category_name": "...",
                "source": "cache" | "api",
                "confidence": "high" | "medium" | "low" | "unknown"
            }
        """
        if not product_name:
            return self._empty_result()

        cache_key = self._make_cache_key(product_name, brand)

        # 캐시 조회
        if use_cache and cache_key in self._cache["mappings"]:
            cached = self._cache["mappings"][cache_key]
            # 히트 통계는 메모리만 갱신 — 매 히트 디스크 전체 재기록 방지 (F-04).
            # 다음 신규 매핑/저장 시 함께 기록됨 (대량등록 시 수백 회 쓰기 절약)
            self._cache["stats"]["cache_hits"] += 1
            log.info(f"[CAT] 캐시 히트: {product_name[:30]} → {cached['display_category_code']}")
            return {**cached, "source": "cache"}

        # API 호출
        log.info(f"[CAT] API 추천 요청: {product_name[:40]}")
        api_result = self.client.predict_category(product_name, brand=brand)
        self._cache["stats"]["api_calls"] += 1

        if not api_result:
            log.warning("[CAT] 카테고리 추천 실패 - 빈 결과")
            self._save_cache()
            return self._empty_result()

        code = api_result.get("predictedCategoryId")
        name = api_result.get("predictedCategoryName", "")

        if not code:
            log.warning(f"[CAT] 응답에 카테고리 코드 없음: {api_result}")
            self._save_cache()
            return self._empty_result()

        try:
            code = int(code)
        except (ValueError, TypeError):
            log.warning(f"[CAT] 카테고리 코드 타입 오류: {code}")
            self._save_cache()
            return self._empty_result()

        confidence = self._estimate_confidence(api_result)

        result = {
            "display_category_code": code,
            "category_name": name,
            "confidence": confidence,
            "source": "api",
            "api_raw": api_result,
            "cached_at": datetime.now().isoformat(),
            "query": {
                "product_name": product_name,
                "brand": brand,
                "dome_category_path": dome_category_path,
            },
        }

        # 캐시 저장 (source는 저장하지 않음 → 다음 조회시 "cache"로 표시됨)
        cache_entry = {k: v for k, v in result.items() if k != "source"}
        self._cache["mappings"][cache_key] = cache_entry
        self._save_cache()

        log.info(f"[CAT] ✅ 매핑 완료: {code} ({name})")
        return result

    @staticmethod
    def _empty_result() -> Dict:
        return {
            "display_category_code": None,
            "category_name": "",
            "confidence": "unknown",
            "source": "none",
        }

    @staticmethod
    def _estimate_confidence(api_result: Dict) -> str:
        """응답 내 점수 필드 기반 신뢰도 추정 (쿠팡 응답 스펙 변경 대응)"""
        score = api_result.get("confidence") or api_result.get("score") or 0
        try:
            score = float(score)
        except (ValueError, TypeError):
            score = 0
        if score >= 0.8:
            return "high"
        if score >= 0.5:
            return "medium"
        if score > 0:
            return "low"
        # 점수 필드 없으면 기본값
        return "medium"

    @staticmethod
    def _make_cache_key(product_name: str, brand: str = "") -> str:
        """정규화된 캐시 키 (공백/특수문자 제거, 소문자)"""
        import re
        text = f"{brand}_{product_name}".lower().strip()
        text = re.sub(r"[\s\[\](){}<>\-_/\\|!@#$%^&*+=?.,;:'\"`~]+", "", text)
        return text[:200]  # 최대 200자

    # ═══════════════════════════════════════════════════════════
    # 통계
    # ═══════════════════════════════════════════════════════════
    def stats(self) -> Dict:
        s = dict(self._cache.get("stats", {}))
        s["total_mappings"] = len(self._cache.get("mappings", {}))
        total = s.get("api_calls", 0) + s.get("cache_hits", 0)
        s["hit_rate"] = (s.get("cache_hits", 0) / total * 100) if total > 0 else 0
        return s


# ═══════════════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    mapper = CategoryMapper()
    tests = [
        "무선 블루투스 이어폰 5.3",
        "스테인리스 텀블러 500ml",
        "강아지 산책 줄 중형견용",
    ]
    for name in tests:
        r = mapper.get_category(name)
        print(f"  [{r['source']:5}] {name[:25]:25} → {r['display_category_code']} ({r['category_name']})")

    print(f"\n📊 통계: {mapper.stats()}")
