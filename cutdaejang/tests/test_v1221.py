"""v1.22.1 — 🟢 네이버 클립 한 번에 복사 + 안내 글씨 가독성 (34번).

> "클립도 (실제 업로드 화면처럼) 제목과 태그가 같이 복붙할 수 있게. 밑에
>  글씨들이 카테고리 어떤 걸 하라는 건지 글씨가 너무 안 보여 — 다른 것들도."
"""

from cutdaejang import __version__
from cutdaejang.gui import webui


def test_version():
    assert __version__ == "1.37.0"


def test_clip_combined_copy_and_readable_category():
    html = webui._apply_links(webui._HTML)
    assert "copyKitNaverAll" in html
    assert "한 번에 복사 (제목+태그)" in html
    # 실제 업로드 「설명」 칸 형식: 제목 + 빈 줄 + #태그들 (공백 구분)
    i = html.index("async function copyKitNaverAll")
    body = html[i:i + 900]
    assert "startsWith('#')" in body and "join(' ')" in body
    assert (chr(92) + "n") * 2 in body               # 제목과 태그 사이 빈 줄(\n\n)
    # 카테고리 안내 — 흐린 hint가 아니라 잘 보이는 강조로
    assert "「카테고리」는 이렇게 고르세요" in html
    assert 'id="kitNaverCat" style="margin-top:8px;font-size:14px' in html
    assert "가장 비슷한 항목을 고르면 됩니다" in html


def test_global_hint_contrast_raised():
    html = webui._HTML
    assert "color:#9aa4bb" in html                   # 안내 글씨 전반 대비 상향
    assert "color:#6b7387; margin-top:4px" not in html
