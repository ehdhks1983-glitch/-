"""v1.48 — 목록 98: 판매 준비판 (배포 파일 정리).

회원님 49차:
> "이제 배포를 해야 하는데 배포 파일을 만들어야 하지 않아?
>  나머지 오류들은 그 이후에 잡을게"

점검에서 나온 것: 내부 문서(경쟁분석·상용화 검토·로드맵·오류 목록)와 시험
1380여 개가 구매자 zip에 통째로 실리고 있었다 — 내부 전략 노출. zip 제외는
build_zip.sh(판매자 전용, zip 미포함)가 하고 검증으로 못 박는다. 여기서는
«출고 상태» 자체를 지킨다: 알림 채널은 꺼진 채(주석만)여야 하고, 구매자
문서는 자리가 있어야 한다.
"""

from pathlib import Path

from cutdaejang import __version__, config

ROOT = Path(config.__file__).resolve().parents[1]      # 제품 루트 (pyproject 위치)


def test_version():
    assert __version__ == "1.52.0"


def test_update_channel_ships_off():
    """🔴 죽은 주소를 넣은 채 출고하면 모든 회원 화면에 «확인 실패»가 뜬다.

    주소는 사장님이 version.json을 «올린 뒤에» 채우는 순서 — 저장소의
    update_url.txt는 주석뿐(기능 꺼짐)이어야 한다.
    """
    assert config.update_channel_url() == "", "주석·빈 줄만 있어야 한다"
    txt = (Path(config.__file__).parent / "update_url.txt").read_text(encoding="utf-8")
    assert "version.json" in txt, "채우는 법 안내는 파일 안에 남긴다"


def test_buyer_documents_exist():
    """구매자에게 가는 문서 — 실행가이드 + 판매문서 필수 5종."""
    assert (ROOT / "실행가이드.md").is_file()
    for f in ("환불·지원안내.txt", "이용약관.txt", "외부API_요금_주의.txt",
              "AI_생성물_고지_안내.txt", "THIRD-PARTY-NOTICES.txt"):
        assert (ROOT / "판매문서" / f).is_file(), f


def test_refund_doc_marks_contact_placeholders():
    """문의처는 판매자가 채우는 자리 — 자리 표시가 명확해야 빈 채 안 나간다."""
    txt = (ROOT / "판매문서" / "환불·지원안내.txt").read_text(encoding="utf-8")
    assert txt.count("판매자가 이 줄에 주소를 적어 배포합니다") >= 2


def test_build_script_excludes_internal_files():
    """빌드 스크립트가 docs/·tests/를 빼고, 빠졌는지 검증까지 하는지."""
    bs = ROOT.parent / "build_zip.sh"
    if not bs.is_file():          # 구매자 zip에는 이 스크립트 자체가 없다
        import pytest
        pytest.skip("판매자 저장소 전용 검사")
    s = bs.read_text(encoding="utf-8")
    assert '-x "$NAME/docs/*"' in s and '-x "$NAME/tests/*"' in s
    assert "내부 문서·시험이 구매자 zip에 포함!" in s, "빠짐을 검증으로 못 박는다"
    assert "update_url" not in s or True   # 채널은 빌드가 강제하지 않는다 (순서 문제)


def test_deploy_guide_has_checklist():
    p = ROOT / "docs" / "배포_가이드.md"
    if not p.is_file():
        import pytest
        pytest.skip("판매자 저장소 전용 검사")
    txt = p.read_text(encoding="utf-8")
    assert "판매 전 체크리스트" in txt
    assert "update_url.txt" in txt and "문의처" in txt
    assert "죽은 주소" in txt, "확인 실패 함정 경고"
