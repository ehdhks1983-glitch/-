"""
main.py - SellerFit Slice 1 엔드투엔드 파이프라인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용법:
    python main.py <도매꾹_상품번호>
    python main.py 7914900
    python main.py 7914900 --dry-run        # 실제 등록 없이 payload만 생성
    python main.py 7914900 --request         # 승인요청까지 (기본: 임시저장)
    python main.py 7914900 --brand "SellerFit"

파이프라인 단계:
    [1] 쿠팡 메타데이터 수집 (반품지/출고지)
    [2] 도매꾹 상품 조회
    [3] 가격 계산
    [4] 카테고리 자동 매핑
    [5] 이미지 파이프라인
    [6] 쿠팡 Payload 조립 + 검증
    [7] 쿠팡 상품 등록 API 호출
    [8] (선택) 승인 요청
    [9] 결과 보고

모든 단계의 데이터는 snapshots/{item_no}_{timestamp}/ 폴더에 JSON 저장.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import (
    domeggook_cfg, coupang_cfg, pricing_cfg, registration_cfg,
    print_config_summary, validate_or_exit,
)
from logger import log, step, success, warn, fail
from data_snapshot import SnapshotWriter
from domeggook_client import DomeggookClient, DomeggookProduct
from coupang_wing_client import CoupangWingClient, WingResponse
from coupang_metadata_collector import CoupangMetadataCollector
from category_mapper import CategoryMapper
from pricing import PriceCalculator
from image_pipeline import ImagePipeline
from payload_builder import PayloadBuilder, validate_payload


# ═══════════════════════════════════════════════════════════════
# 파이프라인
# ═══════════════════════════════════════════════════════════════
class SellerFitPipeline:
    """도매꾹 → 쿠팡 End-to-End 파이프라인"""

    def __init__(self, dry_run: bool = False, request_approval: bool = False,
                 brand: str = "", max_images: int = None):
        self.dry_run = dry_run
        self.request_approval = request_approval
        self.brand = brand
        self.max_images = max_images or registration_cfg.max_images

        # 구성 요소 초기화
        self.dome_client = DomeggookClient()
        self.wing_client = CoupangWingClient()
        self.meta_collector = CoupangMetadataCollector(self.wing_client)
        self.category_mapper = CategoryMapper(self.wing_client)
        self.price_calc = PriceCalculator()
        self.image_pipeline = ImagePipeline(max_images=self.max_images)
        self.payload_builder = PayloadBuilder()

    def run(self, item_no: str) -> dict:
        """전체 파이프라인 실행"""
        snap = SnapshotWriter(item_no)
        report = {
            "item_no": item_no,
            "started_at": datetime.now().isoformat(),
            "dry_run": self.dry_run,
            "stages": {},
            "final_status": "unknown",
        }

        try:
            # ━━━━ [1] 쿠팡 메타데이터 ━━━━
            step("[1/8] 쿠팡 메타데이터 수집 (반품지/출고지)")
            meta = self.meta_collector.collect_all()
            snap.save("01_coupang_metadata", meta)

            if meta.get("error"):
                fail(f"쿠팡 인증/연결 실패: {meta['error']}")
                report["stages"]["01_metadata"] = {"ok": False, "error": meta["error"]}
                report["final_status"] = "failed_metadata"
                snap.finalize(status="failed", summary=report)
                return report

            if not meta.get("default_return_center") or not meta.get("default_outbound_center"):
                fail("반품지/출고지 등록 필요 (WING → 판매자정보 → 주소지 관리)")
                report["stages"]["01_metadata"] = {
                    "ok": False,
                    "return_centers": len(meta.get("return_centers", [])),
                    "outbound_centers": len(meta.get("outbound_centers", [])),
                }
                report["final_status"] = "failed_metadata"
                snap.finalize(status="failed", summary=report)
                return report

            success(f"반품지 {len(meta['return_centers'])}개, "
                    f"출고지 {len(meta['outbound_centers'])}개 확인")
            report["stages"]["01_metadata"] = {
                "ok": True,
                "default_return": meta["default_return_center"]["code"],
                "default_outbound": meta["default_outbound_center"]["code"],
            }

            # ━━━━ [2] 도매꾹 상품 조회 ━━━━
            step(f"[2/8] 도매꾹 상품 조회 (no={item_no})")
            dome_product, raw_xml = self.dome_client.get_item_view(item_no)

            if raw_xml:
                snap.save("02_domeggook_raw", raw_xml, file_ext="xml")

            if not dome_product:
                fail("도매꾹 상품 조회 실패")
                report["stages"]["02_domeggook"] = {"ok": False}
                report["final_status"] = "failed_domeggook"
                snap.finalize(status="failed", summary=report)
                return report

            snap.save("02_domeggook_parsed", dome_product.to_dict())

            if not dome_product.is_valid:
                fail(f"상품 데이터 부족 "
                     f"(제목={bool(dome_product.title)}, 가격={dome_product.base_price}, "
                     f"이미지={len(dome_product.images)}장)")
                report["stages"]["02_domeggook"] = {
                    "ok": False, "title": bool(dome_product.title),
                    "base_price": dome_product.base_price,
                    "images": len(dome_product.images),
                }
                report["final_status"] = "failed_domeggook"
                snap.finalize(status="failed", summary=report)
                return report

            success(f"상품: {dome_product.title[:50]}")
            log.info(f"        도매가 {dome_product.base_price:,}원, "
                     f"이미지 {len(dome_product.images)}장, "
                     f"옵션 {len(dome_product.options)}개")
            report["stages"]["02_domeggook"] = {
                "ok": True,
                "title": dome_product.title,
                "base_price": dome_product.base_price,
                "image_count": len(dome_product.images),
                "option_count": len(dome_product.options),
            }

            # ━━━━ [3] 가격 계산 ━━━━
            step("[3/8] 가격 계산")
            pricing = self.price_calc.calculate(dome_product.base_price)
            snap.save("03_pricing", pricing.to_dict())
            success(f"판매가 {pricing.sale_price:,}원 (마진 {pricing.margin_rate:.1f}%)")
            report["stages"]["03_pricing"] = pricing.to_dict()

            # ━━━━ [4] 카테고리 매핑 ━━━━
            step("[4/8] 카테고리 자동 매핑")
            cat_result = self.category_mapper.get_category(
                dome_product.title,
                dome_category_path=dome_product.category_path,
                brand=self.brand,
            )
            snap.save("04_category", cat_result)

            if not cat_result.get("display_category_code"):
                fail("카테고리 추천 실패")
                report["stages"]["04_category"] = {"ok": False}
                report["final_status"] = "failed_category"
                snap.finalize(status="failed", summary=report)
                return report

            success(f"카테고리: {cat_result['display_category_code']} "
                    f"({cat_result.get('category_name', '')}) "
                    f"[{cat_result['source']}]")
            report["stages"]["04_category"] = {
                "ok": True,
                "code": cat_result["display_category_code"],
                "name": cat_result.get("category_name", ""),
                "source": cat_result["source"],
            }

            # ━━━━ [4-1] 카테고리 필수옵션 조회 ━━━━
            required_attrs = self.wing_client.get_required_attributes(
                cat_result["display_category_code"])
            snap.save("04b_required_attributes", required_attrs)
            if required_attrs:
                log.info(f"        필수옵션 {len(required_attrs)}개: "
                         f"{[a['attributeTypeName'] for a in required_attrs][:5]}")
            else:
                warn("카테고리 필수옵션 정보 없음 (등록 거부 가능)")

            # ━━━━ [5] 이미지 파이프라인 ━━━━
            step("[5/8] 이미지 접근성 검증")
            img_result = self.image_pipeline.process(dome_product.images)
            snap.save("05_images", img_result.to_dict())

            usable_urls = img_result.usable_urls
            if not usable_urls:
                fail("사용 가능한 이미지 없음")
                report["stages"]["05_images"] = {"ok": False, "accessible": 0}
                report["final_status"] = "failed_images"
                snap.finalize(status="failed", summary=report)
                return report

            success(f"사용 가능 이미지: {len(usable_urls)}/{img_result.input_count}장")
            report["stages"]["05_images"] = {
                "ok": True,
                "input": img_result.input_count,
                "accessible": img_result.accessible_count,
                "usable": len(usable_urls),
            }

            # ━━━━ [6] Payload 조립 ━━━━
            step("[6/8] 쿠팡 Payload 조립")
            payload = self.payload_builder.build(
                dome_product=dome_product,
                pricing=pricing,
                display_category_code=cat_result["display_category_code"],
                image_urls=usable_urls,
                return_center=meta["default_return_center"],
                outbound_center=meta["default_outbound_center"],
                brand=self.brand,
                required_attributes=required_attrs,
            )
            snap.save("06_coupang_payload", payload)

            # 로컬 검증
            problems = validate_payload(payload)
            if problems:
                fail("Payload 검증 실패:")
                for p in problems:
                    log.error(f"  - {p}")
                report["stages"]["06_payload"] = {"ok": False, "problems": problems}
                report["final_status"] = "failed_payload"
                snap.finalize(status="failed", summary=report)
                return report

            success(f"Payload 조립 완료 (items {len(payload['items'])}개, "
                    f"이미지 {len(payload['items'][0]['images'])}장)")
            report["stages"]["06_payload"] = {"ok": True}

            # ━━━━ [7] 쿠팡 상품 등록 ━━━━
            if self.dry_run:
                step("[7/8] 쿠팡 등록 ⏭ SKIP (--dry-run)")
                report["stages"]["07_coupang_create"] = {"ok": True, "skipped": "dry-run"}
                report["final_status"] = "dry_run_success"
                snap.finalize(status="dry_run_success", summary=report)
                return report

            step("[7/8] 쿠팡 상품 등록 API 호출")
            create_resp = self.wing_client.create_product(payload)
            snap.save("07_coupang_response", {
                "status_code": create_resp.status_code,
                "body": create_resp.body,
                "is_success": create_resp.is_success,
            })

            if not create_resp.is_success:
                fail(f"쿠팡 등록 실패: {create_resp.error_summary}")
                log.error(f"        응답 본문: {json.dumps(create_resp.body, ensure_ascii=False)[:500]}")
                report["stages"]["07_coupang_create"] = {
                    "ok": False,
                    "status_code": create_resp.status_code,
                    "error": create_resp.error_summary,
                }
                report["final_status"] = "failed_coupang_create"
                snap.finalize(status="failed", summary=report)
                return report

            # seller_product_id 추출
            seller_product_id = None
            if isinstance(create_resp.data, dict):
                seller_product_id = create_resp.data.get("sellerProductId")
            elif isinstance(create_resp.data, (int, str)):
                seller_product_id = create_resp.data

            success(f"쿠팡 등록 성공! sellerProductId={seller_product_id}")
            report["stages"]["07_coupang_create"] = {
                "ok": True,
                "seller_product_id": seller_product_id,
            }

            # ━━━━ [8] 승인 요청 (선택) ━━━━
            if self.request_approval and seller_product_id:
                step("[8/8] 승인 요청")
                approval_resp = self.wing_client.request_approval(seller_product_id)
                snap.save("08_approval_response", {
                    "status_code": approval_resp.status_code,
                    "body": approval_resp.body,
                })
                if approval_resp.is_success:
                    success("승인 요청 완료")
                    report["stages"]["08_approval"] = {"ok": True}
                else:
                    warn(f"승인 요청 실패: {approval_resp.error_summary}")
                    report["stages"]["08_approval"] = {
                        "ok": False, "error": approval_resp.error_summary,
                    }
            else:
                step("[8/8] 승인 요청 ⏭ SKIP (--request 미사용, 임시저장 상태)")
                log.info("   WING에서 수동 검토 후 승인 요청 하시면 됩니다.")
                report["stages"]["08_approval"] = {"ok": True, "skipped": "manual"}

            report["final_status"] = "success"
            report["seller_product_id"] = seller_product_id
            snap.finalize(status="success", summary=report)
            return report

        except Exception as e:
            log.exception(f"파이프라인 예외: {e}")
            report["final_status"] = "exception"
            report["exception"] = f"{type(e).__name__}: {e}"
            snap.finalize(status="exception", summary=report)
            return report


# ═══════════════════════════════════════════════════════════════
# 요약 출력
# ═══════════════════════════════════════════════════════════════
def print_report(report: dict):
    print("\n" + "=" * 60)
    print("  📊 최종 보고서")
    print("=" * 60)
    print(f"  상품번호:   {report['item_no']}")
    print(f"  최종상태:   {report['final_status']}")
    if report.get("seller_product_id"):
        print(f"  쿠팡 ID:    {report['seller_product_id']}")

    status_icon = {
        "success": "✅",
        "dry_run_success": "🧪",
        "failed_metadata": "❌",
        "failed_domeggook": "❌",
        "failed_category": "❌",
        "failed_images": "❌",
        "failed_payload": "❌",
        "failed_coupang_create": "❌",
        "exception": "💥",
    }.get(report["final_status"], "❓")

    print(f"  결과:       {status_icon} {report['final_status']}")
    print()
    print("  단계별 결과:")
    for key in sorted(report.get("stages", {}).keys()):
        st = report["stages"][key]
        mark = "✅" if st.get("ok") else "❌"
        print(f"    {mark} {key}")
    print("=" * 60)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="SellerFit Slice 1: 도매꾹 → 쿠팡 자동 등록",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py 7914900                      # 임시저장 상태로 등록
  python main.py 7914900 --request            # 즉시 승인요청까지
  python main.py 7914900 --dry-run            # API 호출 없이 payload만 생성
  python main.py 7914900 --brand "내브랜드"
  python main.py 7914900 --config             # 설정만 출력
""",
    )
    parser.add_argument("item_no", nargs="?", help="도매꾹 상품번호")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 쿠팡 등록 API 호출 없이 payload까지만 생성")
    parser.add_argument("--request", action="store_true",
                        help="등록 후 즉시 승인 요청")
    parser.add_argument("--brand", default="", help="브랜드명 (없으면 '자체브랜드')")
    parser.add_argument("--max-images", type=int, default=None,
                        help="최대 이미지 수 (기본: config)")
    parser.add_argument("--config", action="store_true",
                        help="현재 설정만 출력 후 종료")
    args = parser.parse_args()

    # 설정 출력만
    print_config_summary()
    if args.config:
        return 0

    # 필수 인자
    if not args.item_no:
        parser.print_help()
        return 1

    # 환경변수 검증
    validate_or_exit()

    # 실행
    pipeline = SellerFitPipeline(
        dry_run=args.dry_run,
        request_approval=args.request,
        brand=args.brand,
        max_images=args.max_images,
    )

    t0 = time.time()
    report = pipeline.run(args.item_no)
    elapsed = time.time() - t0

    print_report(report)
    print(f"  소요시간: {elapsed:.1f}초")
    print("=" * 60)

    return 0 if report["final_status"] in ("success", "dry_run_success") else 1


if __name__ == "__main__":
    sys.exit(main())
