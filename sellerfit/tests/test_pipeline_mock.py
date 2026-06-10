"""
test_pipeline_mock.py - SellerFit 오프라인(가상) 파이프라인 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실제 API 키/네트워크 없이 엔진 로직을 검증한다 (R10 골든 샘플).
  - 도매꾹 XML 파싱 (_parse_xml, 가정한 스키마 기준)
  - 가격 계산 3모드
  - 쿠팡 payload 조립 + validate_payload
  - WingResponse 성공/실패 판정 + sellerProductId 추출

실행:  python tests/test_pipeline_mock.py
종료코드: 모두 통과 0, 하나라도 실패 1
※ 실제 도매꾹 XML 스키마는 도완님 실키로 02_domeggook_raw.xml 확보 후 재확정 (R1).
"""

import os
import sys

# ── sellerfit/ 를 import 경로에 추가 (flat 모듈 구조) ──
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── config가 env에서 읽으므로 가짜 키를 먼저 주입 (네트워크는 안 씀) ──
os.environ.setdefault("DOMEGGOOK_API_KEY", "mock-dome-key")
os.environ.setdefault("COUPANG_WING_VENDOR_ID", "A00012345")
os.environ.setdefault("COUPANG_WING_ACCESS_KEY", "mock-access-key")
os.environ.setdefault("COUPANG_WING_SECRET_KEY", "mock-secret-key")
os.environ.setdefault("COUPANG_WING_USER_ID", "mockuser")

from domeggook_client import DomeggookClient                      # noqa: E402
from pricing import PriceCalculator                              # noqa: E402
from payload_builder import PayloadBuilder, validate_payload     # noqa: E402
from coupang_wing_client import WingResponse                     # noqa: E402


# ═══════════════════════════════════════════════════════════════
# 미니 테스트 프레임워크 (pytest 불필요)
# ═══════════════════════════════════════════════════════════════
_RESULTS = []


def check(name: str, cond, detail: str = ""):
    ok = bool(cond)
    _RESULTS.append(ok)
    mark = "✅" if ok else "❌"
    line = f"{mark} {name}"
    if detail and not ok:
        line += f"  →  {detail}"
    print(line)


def section(title: str):
    print(f"\n── {title} ──")


# ═══════════════════════════════════════════════════════════════
# 가짜 도매꾹 getItemView 응답 (코드가 가정하는 스키마 기준)
# ═══════════════════════════════════════════════════════════════
MOCK_XML = """<?xml version="1.0" encoding="utf-8"?>
<domeggook>
  <basis>
    <status>regular</status>
    <title>스테인리스 진공 텀블러 500ml 보온보냉 휴대용</title>
    <keywords><kw>텀블러</kw><kw>보온병</kw><kw>500ml</kw></keywords>
    <section>주방용품</section>
  </basis>
  <price>
    <dome>1+9850|11+9800|101+9700</dome>
    <supply>9850</supply>
    <resale><minimum>12000</minimum><Recommand>19800</Recommand></resale>
  </price>
  <qty><inventory>500</inventory><domeMoq>1</domeMoq></qty>
  <deli><method>택배</method><pay>선결제</pay></deli>
  <seller><id>seller01</id><nick>도매판매자</nick></seller>
  <thumb>https://image.domeggook.com/thumb/main.jpg</thumb>
  <images>
    <image>https://image.domeggook.com/detail/1.jpg</image>
    <image>https://image.domeggook.com/detail/2.jpg</image>
  </images>
  <options>
    <option><name>색상</name><value>블랙</value><value>화이트</value></option>
  </options>
  <contents><html><![CDATA[<p>상세 설명 <b>텀블러</b> 좋아요</p>]]></html></contents>
</domeggook>
"""

MOCK_RETURN_CENTER = {
    "code": "RC1001", "name": "기본반품지",
    "address": "서울시 강남구 테헤란로 1", "postcode": "06234",
    "phone": "02-1234-5678",
}
MOCK_OUTBOUND_CENTER = {"code": "OB2002", "name": "기본출고지"}

MOCK_REQUIRED_ATTRS = [
    {"attributeTypeName": "수량", "dataType": "NUMBER", "basicUnit": "개",
     "required": "MANDATORY", "exposed": "EXPOSED"},
    {"attributeTypeName": "색상", "dataType": "STRING", "basicUnit": "",
     "required": "NONE", "exposed": "EXPOSED"},
]


# ═══════════════════════════════════════════════════════════════
# 1) 도매꾹 파서
# ═══════════════════════════════════════════════════════════════
def test_parser():
    section("1) 도매꾹 XML 파싱")
    client = DomeggookClient(api_key="mock")
    p = client._parse_xml(MOCK_XML, "23828709")

    check("객체 생성됨", p is not None)
    if p is None:
        return None
    check("제목 파싱", p.title.startswith("스테인리스"), f"title={p.title!r}")
    check("base_price=9850 (tier 첫 단가)", p.base_price == 9850, f"got {p.base_price}")
    check("계단가 3구간", len(p.tier_prices) == 3, f"got {len(p.tier_prices)}")
    check("재고=500", p.inventory == 500, f"got {p.inventory}")
    check("이미지 3장(thumb+상세2)", len(p.images) == 3, f"got {len(p.images)}")
    check("대표이미지=thumb 우선", p.images and p.images[0].endswith("main.jpg"),
          f"first={p.images[0] if p.images else None}")
    check("옵션 1개 파싱", len(p.options) == 1, f"got {len(p.options)}")
    check("키워드 3개", len(p.keywords) == 3, f"got {len(p.keywords)}")
    check("상세 HTML 존재", bool(p.description_html), f"len={len(p.description_html)}")
    check("is_valid (등록가능 최소조건)", p.is_valid)
    return p


# ═══════════════════════════════════════════════════════════════
# 2) 가격 3모드
# ═══════════════════════════════════════════════════════════════
def test_pricing():
    section("2) 가격 계산 3모드")
    base = 9850
    results = {}
    for mode, value_attr, val in (
        ("multiply", "multiplier", 2.5),
        ("add_margin", "margin_rate_percent", 50.0),
        ("min_margin", "min_margin_percent", 30.0),
    ):
        import copy
        from config import pricing_cfg
        cfg = copy.copy(pricing_cfg)
        cfg.mode = mode
        setattr(cfg, value_attr, val)
        r = PriceCalculator(cfg).calculate(base)
        results[mode] = r
        check(f"[{mode}] 판매가>원가", r.sale_price > r.cost,
              f"sale={r.sale_price} cost={r.cost}")
        check(f"[{mode}] 100원 단위", r.sale_price % 100 == 0, f"got {r.sale_price}")
        check(f"[{mode}] 표시원가>판매가", r.original_price > r.sale_price,
              f"orig={r.original_price} sale={r.sale_price}")
    return results["multiply"]


# ═══════════════════════════════════════════════════════════════
# 3) payload 조립 + 검증
# ═══════════════════════════════════════════════════════════════
def test_payload(product, pricing):
    section("3) 쿠팡 payload 조립")
    if product is None or pricing is None:
        check("선행 데이터 존재", False, "파서/가격 실패로 스킵")
        return
    pb = PayloadBuilder()
    payload = pb.build(
        dome_product=product,
        pricing=pricing,
        display_category_code=63800,
        image_urls=product.images,
        return_center=MOCK_RETURN_CENTER,
        outbound_center=MOCK_OUTBOUND_CENTER,
        brand="테스트브랜드",
        required_attributes=MOCK_REQUIRED_ATTRS,
    )

    problems = validate_payload(payload)
    check("validate_payload 통과 (하드에러 0)", problems == [], f"problems={problems}")

    check("displayCategoryCode 세팅", payload.get("displayCategoryCode") == 63800)
    check("vendorId 세팅", bool(payload.get("vendorId")), "env 가짜키 주입 확인")
    check("vendorUserId 세팅", bool(payload.get("vendorUserId")))
    check("items 정확히 1개", len(payload.get("items", [])) == 1,
          f'got {len(payload.get("items", []))}')

    items = payload.get("items", [])
    if not items:
        return
    it = items[0]
    imgs = it.get("images", [])
    check("이미지 3장 전달", len(imgs) == 3, f"got {len(imgs)}")
    check("첫 이미지 REPRESENTATION", imgs and imgs[0]["imageType"] == "REPRESENTATION")
    check("대표 vendorPath 비어있지 않음", imgs and bool(imgs[0]["vendorPath"]),
          "R1: 대표이미지 누락 시 등록거부")
    check("나머지 DETAIL", all(i["imageType"] == "DETAIL" for i in imgs[1:]))
    check("attributes 2개 채움", len(it.get("attributes", [])) == 2,
          f'got {len(it.get("attributes", []))}')
    check("notices(고시정보) 존재", len(it.get("notices", [])) > 0)
    check("searchTags ≤20개", len(it.get("searchTags", [])) <= 20)
    check("searchTags 각 ≤20자",
          all(len(t) <= 20 for t in it.get("searchTags", [])))
    check("salePrice>0", it.get("salePrice", 0) > 0, f'got {it.get("salePrice")}')
    check("outboundShippingTimeDay=2 (config 기본값)",
          it.get("outboundShippingTimeDay") == 2,
          f'got {it.get("outboundShippingTimeDay")!r} (B8: __dict__.get 제거 확인)')
    check("sellerProductName ≤100자", len(payload.get("sellerProductName", "")) <= 100)
    return payload


# ═══════════════════════════════════════════════════════════════
# 4) WingResponse 성공/실패 판정 (B2)
# ═══════════════════════════════════════════════════════════════
def test_wing_response():
    section("4) 쿠팡 응답 판정 + sellerProductId 추출")
    # 성공: code=SUCCESS, data dict
    r1 = WingResponse(200, {"code": "SUCCESS", "data": {"sellerProductId": 12345}})
    check("SUCCESS 문자열 → 성공", r1.is_success)
    spid1 = r1.data.get("sellerProductId") if isinstance(r1.data, dict) else None
    check("sellerProductId 추출(dict)", spid1 == 12345, f"got {spid1}")

    # 성공: code=200(int), data=bare int
    r2 = WingResponse(200, {"code": 200, "data": 67890})
    check("code=200(int) → 성공", r2.is_success)

    # 실패: 400 + 메시지
    r3 = WingResponse(400, {"code": "ERROR", "message": "필수 구매옵션이 누락되었습니다"})
    check("400 → 실패", not r3.is_success)
    check("error_summary에 메시지 포함", "필수 구매옵션" in r3.error_summary,
          f"summary={r3.error_summary}")


# ═══════════════════════════════════════════════════════════════
# 5) 기본 반품지/출고지 선택 (B6)
# ═══════════════════════════════════════════════════════════════
def test_center_selection():
    section("5) 기본 반품지/출고지 선택 (B6: usable 우선)")
    from coupang_metadata_collector import CoupangMetadataCollector as MC

    pick = MC._pick_default([{"code": "C0", "usable": False},
                             {"code": "C1", "usable": True}])
    check("unusable 건너뛰고 usable 선택", pick and pick["code"] == "C1",
          f"picked {pick}")
    check("전부 usable면 첫번째",
          MC._pick_default([{"code": "A", "usable": True},
                            {"code": "B", "usable": True}])["code"] == "A")
    check("usable 키 없으면 첫번째 (하위호환)",
          MC._pick_default([{"code": "X"}, {"code": "Y"}])["code"] == "X")
    check("빈 리스트 → None", MC._pick_default([]) is None)


# ═══════════════════════════════════════════════════════════════
# 6) 가격 재계산 — API 재호출 없음 (F-02)
# ═══════════════════════════════════════════════════════════════
def test_recompute(product):
    section("6) recompute_price (F-02: 도매꾹 재호출 없는 가격 재계산)")
    if product is None:
        check("선행 파서 성공", False, "파서 실패로 스킵")
        return
    from pipeline_service import SellerFitService, PreparedProduct

    svc = SellerFitService()
    prepared = PreparedProduct(item_no="23828709", ok=True)
    prepared.dome_product = product
    prepared.category_code = 63800
    prepared.usable_image_urls = list(product.images)
    prepared.return_center = MOCK_RETURN_CENTER
    prepared.outbound_center = MOCK_OUTBOUND_CENTER
    prepared.brand = "테스트브랜드"
    prepared.required_attributes = MOCK_REQUIRED_ATTRS

    ok = svc.recompute_price(prepared, pricing_mode="multiply", pricing_value=3.0)
    check("재계산 성공", ok)
    check("판매가 9850×3 → 29,600 (100원 올림)", prepared.sale_price == 29600,
          f"got {prepared.sale_price}")
    check("payload 갱신됨", prepared.payload is not None)
    if prepared.payload:
        it = prepared.payload["items"][0]
        check("items.salePrice 동기화", it["salePrice"] == prepared.sale_price,
              f'{it["salePrice"]} vs {prepared.sale_price}')
        check("재계산 payload 검증 통과", validate_payload(prepared.payload) == [])
    check("조회 전 재계산 → 거부",
          not svc.recompute_price(PreparedProduct(item_no="x"), "multiply", 3.0))


# ═══════════════════════════════════════════════════════════════
# 러너
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  🧪 SellerFit 가상 파이프라인 테스트 (네트워크 없음)")
    print("=" * 60)

    product = test_parser()
    pricing = test_pricing()
    test_payload(product, pricing)
    test_wing_response()
    test_center_selection()
    test_recompute(product)

    total = len(_RESULTS)
    passed = sum(_RESULTS)
    print("\n" + "=" * 60)
    print(f"  결과: {passed}/{total} 통과")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
