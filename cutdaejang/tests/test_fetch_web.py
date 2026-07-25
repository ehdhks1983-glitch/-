"""🔗 fetch_web (v0.78) — URL 정규화·글 파싱·이미지 다운로드 (네트워크는 로컬 서버만)."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cutdaejang.tools import fetch_web as fw

# ── normalize_url ─────────────────────────────────────────────────


def test_normalize_url_naver_forms():
    assert (fw.normalize_url("https://blog.naver.com/abc/223344#comment")
            == "https://m.blog.naver.com/abc/223344")
    assert (fw.normalize_url("https://blog.naver.com/PostView.naver?blogId=abc&logNo=99&nav=1")
            == "https://m.blog.naver.com/abc/99")
    assert (fw.normalize_url("http://blog.naver.com/PostView.nhn?blogId=k.im&logNo=7")
            == "https://m.blog.naver.com/k.im/7")
    assert fw.normalize_url("https://m.blog.naver.com/abc/5") == "https://m.blog.naver.com/abc/5"
    # 그 외 주소는 fragment만 떼고 그대로
    assert fw.normalize_url("https://example.com/post?a=1#x") == "https://example.com/post?a=1"


# ── parse_article_html ────────────────────────────────────────────

_NAVER_HTML = """<html><head><title>탭제목</title>
<meta property="og:title" content="비타민C 세럼 솔직 후기"/>
<meta property="og:description" content="한 달 써봤습니다"/>
<meta property="og:image" content="/og_main.jpg"/></head>
<body><script>var ad = "본문 아님";</script>
<div class="wrap"><div class="se-main-container">
<p class="se-text-paragraph"><span>안녕하세요 오늘은 세럼 후기예요</span></p>
<p class="se-text-paragraph"><span>한 달 동안 아침저녁으로 발라봤어요</span></p>
<div class="se-component se-image">
  <img class="se-image-resource" data-lazy-src="/photo1.jpg?type=w800" src="/tiny_placeholder.png">
</div>
<img src="https://storep-phinf.pstatic.net/sticker/1.png">
<img src="/anim.gif">
<p><span>결론은 재구매 의사 있음!</span></p>
</div></div>
<a href="https://link.coupang.com/a/xyz123">쿠팡에서 보기</a>
<a href="https://smartstore.naver.com/shop/products/1">스토어</a>
<a href="https://other.example.com/no">일반 링크</a>
<p>본문 밖 추천글 목록</p></body></html>"""


def test_parse_naver_smarteditor():
    d = fw.parse_article_html(_NAVER_HTML, "https://m.blog.naver.com/abc/1")
    assert d["title"] == "비타민C 세럼 솔직 후기"
    assert "세럼 후기예요" in d["text"] and "재구매" in d["text"]
    # 컨테이너 밖 텍스트·스크립트는 본문에 안 들어감
    assert "본문 아님" not in d["text"] and "추천글" not in d["text"] and "쿠팡에서" not in d["text"]
    # og 대표 이미지 먼저 + lazy-src 우선(placeholder src 무시), gif·스티커 제외
    assert d["image_urls"] == ["https://m.blog.naver.com/og_main.jpg",
                               "https://m.blog.naver.com/photo1.jpg?type=w800"]
    # 제휴·상품 링크만 수집 (일반 링크 제외)
    assert d["links"] == ["https://link.coupang.com/a/xyz123",
                          "https://smartstore.naver.com/shop/products/1"]


def test_parse_generic_p_fallback():
    d = fw.parse_article_html(
        "<html><head><title>일반 글</title></head><body>"
        "<p>일반 사이트 문단 하나입니다</p><p>문단 둘입니다</p></body></html>",
        "https://example.com/post")
    assert d["title"] == "일반 글"
    assert "문단 하나입니다" in d["text"] and "문단 둘입니다" in d["text"]


def test_parse_og_description_last_resort():
    d = fw.parse_article_html(
        '<html><head><meta property="og:description" content="요약 설명뿐"/></head>'
        "<body><div>p태그 없음</div></body></html>", "https://e.com")
    assert d["text"] == "요약 설명뿐"
    assert any("og:description" in n for n in d["notes"])


# ── fetch_article (로컬 HTTP 서버 — 외부 네트워크 없음) ────────────

_JPG = b"\xff\xd8\xff\xe0" + b"j" * 12_000
_PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 12_000
_GIF = b"GIF89a" + b"g" * 12_000
_ICON = b"\xff\xd8\xff\xe0" + b"i" * 500          # 10KB 미만 → 스킵 대상


class _Handler(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):  # noqa: N802
        _Handler.seen.append((self.path, self.headers.get("User-Agent", ""),
                              self.headers.get("Referer", "")))
        page = ("<html><head><meta property='og:title' content='로컬 글'/></head><body>"
                "<div class='se-main-container'>"
                "<p>로컬 서버로 검증하는 본문입니다. 사진과 링크가 섞여 있어요. "
                "글자 수를 채우려고 문장을 조금 더 길게 씁니다. 충분히 길어졌습니다.</p>"
                "<img data-lazy-src='/big.jpg'><img src='/icon.jpg'>"
                "<img src='/anim.gif'><img src='/noext'><img src='/big.jpg'>"
                "</div><a href='https://coupa.ng/abc'>파트너스</a></body></html>")
        body_by_path = {
            "/post.html": page.encode("utf-8"),
            "/big.jpg": _JPG, "/icon.jpg": _ICON, "/anim.gif": _GIF, "/noext": _PNG,
        }
        if self.path == "/blocked.html":
            self.send_response(403)
            self.end_headers()
            return
        body = body_by_path.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        ctype = "text/html; charset=utf-8" if self.path.endswith(".html") else "image/any"
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # 테스트 출력 오염 방지
        pass


@pytest.fixture
def local_site():
    _Handler.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_fetch_article_end_to_end(local_site, tmp_path):
    from cutdaejang.core.video_editor import resolve_photo_inputs

    out = fw.fetch_article(f"{local_site}/post.html", tmp_path / "wl")
    assert out["title"] == "로컬 글"
    assert "본문입니다" in out["text"]
    # big.jpg(1회 — sha 중복 제거), noext는 매직바이트로 .png 저장 / icon(작음)·gif 스킵
    names = [p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for p in out["images"]]
    assert names == ["img_01.jpg", "img_02.png"], names
    # 결과 경로가 사진 영상 입력 화이트리스트를 그대로 통과
    assert len(resolve_photo_inputs(";".join(out["images"]))) == 2
    assert out["links"] == ["https://coupa.ng/abc"]
    # 모든 요청에 UA·Referer 동봉 (이미지 핫링크 대비)
    for path, ua, ref in _Handler.seen:
        assert "Mozilla" in ua
        if path != "/post.html":
            assert ref.endswith("/post.html"), (path, ref)


def test_fetch_article_blocked_message(local_site, tmp_path):
    with pytest.raises(ValueError) as ei:
        fw.fetch_article(f"{local_site}/blocked.html", tmp_path / "b")
    assert "막았어요" in str(ei.value)


def test_friendly_error_coupang_specific():
    err = fw._friendly_http_error("https://www.coupang.com/vp/products/1", 403)
    assert "쿠팡" in str(err) and "블로그" in str(err)


def test_fetch_article_rejects_non_http(tmp_path):
    with pytest.raises(ValueError):
        fw.fetch_article("ftp://example.com/x", tmp_path)


# ── summarize_article_stub (오프라인 폴백) ────────────────────────


def test_summarize_article_stub_splits_sentences():
    from cutdaejang.core import script_generator as sg

    text = "첫 문장입니다. 둘째 문장이에요! 셋째로 갑니다. 넷째도 있습니다. 다섯째 문장."
    out = sg.summarize_article_stub("제목입니다", text, target_sec=20)
    assert 4 <= len(out["sentences"]) <= 5
    assert out["sentences"][0].startswith("첫 문장")
    assert out["hook"] == "제목입니다"


def test_summarize_article_stub_empty_text():
    from cutdaejang.core import script_generator as sg

    out = sg.summarize_article_stub("제목", "", target_sec=45)
    assert out["sentences"]  # 최소 소개 문장은 나옴
