"""v1.13 — 🎞 구간 대본 화면 4종 (회원님 요청 8·9·10·12).

  ⑨ 구간을 [🎬 화면 메모 / 🎙 나레이션 / 💬 화면 자막] 3칸으로 —
     촬영 대본을 통째로 붙여넣으면 표기를 알아보고 제자리에 나눠 담는다.
     [화면]은 낭독·표시 모두 안 되고, [자막]은 읽지 않고 카드로 화면에 박힌다.
  ⑧ 대본 칸이 내용에 맞춰 자동으로 늘어나고, 글자를 키우고, [⤢ 크게 보기] 추가
  ⑩ 탐색기에서 파일을 끌어다 놓기 — 경로가 실려 오면 즉시, 아니면 서버로 복사
  ⑫ [💾 임시 저장]·[🗑 지우기] 바를 모든 카드에 + 마지막 저장 시각 표시
"""

import http.client
import inspect
import json
import threading  # noqa: F401 — server fixture 패턴과 동일 구성

import pytest

from cutdaejang import __version__
from cutdaejang.core import script_generator as sg
from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.gui import webui
from cutdaejang.spec import Background, Canvas, Style, Subtitle, TimelineSpec


def test_version():
    assert __version__ == "1.20.1"


# ── ⑨ 촬영 대본 표기 파서 ─────────────────────────────────────
SAMPLE = """① 오프닝 — 0:00 ~ 0:15
[화면] 프로그램 실행 직후 전체 화면. 사이드바를 천천히 훑기.
나레이션 안녕하세요. 티스토리 블로그 AI 퍼블리셔입니다.
[자막] 키워드 입력 → AI 글 작성 → 자동 발행

2-1. 라이선스 인증 (0:15 ~ 0:30)
[화면] 기본 설정 클릭 → 라이선스 인증 카드.
나레이션 먼저 기본 설정으로 들어가서, 맨 아래까지 내려주세요.
받은 키를 붙여넣고 인증하기를 누르면 됩니다.
[자막] 라이선스 1개 = PC 1대 전용
"""


def test_shooting_script_parser_splits_three_fields():
    secs = sg.split_shooting_script(SAMPLE)
    assert len(secs) == 2
    a, b = secs
    assert a["title"] == "오프닝" and a["start"] == "0:00" and a["end"] == "0:15"
    assert b["title"] == "라이선스 인증" and b["start"] == "0:15" and b["end"] == "0:30"
    assert "사이드바" in a["screen"] and "티스토리" in a["narration"]
    assert a["caption"] == "키워드 입력 → AI 글 작성 → 자동 발행"
    # 표기 없는 이어지는 줄은 나레이션으로 계속 (읽을 말이 끊기지 않게)
    assert "인증하기를 누르면" in b["narration"]
    # [화면]·[자막] 줄이 나레이션(=낭독 대상)에 절대 섞이면 안 된다
    for s in secs:
        assert "[화면]" not in s["narration"] and "[자막]" not in s["narration"]


def test_parser_ignores_plain_scripts():
    """표기가 없으면 빈 목록 — 기존 AI·문단 나누기가 그대로 맡는다."""
    assert sg.split_shooting_script("그냥 문단 대본.\n\n두 번째 문단.") == []
    assert sg.split_shooting_script("") == []


def test_split_route_prefers_markers():
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert "split_shooting_script(text)" in src
    body = src.split('"/api/section_split"')[1][:1300]
    assert body.index("split_shooting_script") < body.index("split_script_sections_ai"), \
        "표기 대본은 AI보다 먼저(무비용·정확) 처리해야 한다"
    assert '"via": via' in body


# ── ⑨ 화면 자막 = 무낭독 카드 ─────────────────────────────────
def _ass(subs, text_cards=True):
    import pathlib
    import tempfile

    spec = TimelineSpec(canvas=Canvas(w=1920, h=1080, fps=30),
                        style=Style(text_cards=text_cards), hook="",
                        duration_us=20_000_000, background=Background(), subtitles=subs)
    out = pathlib.Path(tempfile.mkdtemp()) / "c.ass"
    aw.write_ass(spec, out)
    return out.read_text(encoding="utf-8")


def test_marked_caption_is_card_even_when_cards_off():
    """카드 연출을 꺼 둔 회원님도 [자막] 줄은 카드로 봐야 한다 (무낭독 자막의 핵심)."""
    subs = [Subtitle(text="일반 내레이션 자막", start_us=0, end_us=4_000_000),
            Subtitle(text="[카드]라이선스 1개 = PC 1대", start_us=0, end_us=5_000_000)]
    for off_on in (True, False):
        t = _ass(subs, text_cards=off_on)
        card_lines = [l for l in t.splitlines() if ",Card," in l]
        assert card_lines, f"text_cards={off_on}"
        assert any("라이선스" in l for l in card_lines)
        default_lines = [l for l in t.splitlines() if ",Default," in l]
        assert not any("라이선스" in l for l in default_lines), "카드 글이 하단 자막에 중복"
        assert any("일반 내레이션" in l for l in default_lines)


def test_sections_caption_wiring():
    body = inspect.getsource(webui._run_sections)
    assert "cap_subs" in body and "CARD_MARK" in body
    # 내레이션 베드는 클립↔자막 짝이라 캡션(클립 없음)을 절대 넣으면 안 된다
    assert "build_narration_wav(\n                    all_clips, abs_subs" in body \
        or "build_narration_wav(all_clips, abs_subs" in body.replace("\n", " ").replace("  ", " ") \
        or "all_clips, abs_subs, total_us" in body
    assert "abs_subs + cap_subs" in body            # 자막 렌더에는 캡션 합류
    # TTS 낭독 목록은 narration만 — caption이 새어 들어가면 읽어버린다
    assert 'narration_units(str(sec["narration"]))' in body
    assert 'narration_units(str(sec["caption"' not in body


def test_ui_rows_have_three_fields():
    html = webui._HTML
    for tok in ("sec-screen", "sec-cap", "화면 메모", "화면 자막",
                "읽지는 않아요", "영상·소리에 안 들어가요"):
        assert tok in html, tok
    # 페이로드·임시저장·복원·통째 붙여넣기 모두 세 칸을 나른다
    assert html.count("'.sec-screen'") + html.count('".sec-screen"') >= 3
    assert html.count("'.sec-cap'") + html.count('".sec-cap"') >= 3


# ── ⑧ 칸 크기·크게 보기 ──────────────────────────────────────
def test_narration_box_grows_and_zooms():
    html = webui._HTML
    assert "min-height:112px" in html and "font-size:15px" in html   # 기본부터 크게
    assert "function autoGrow" in html
    assert "function secZoomOpen" in html and 'id="secZoom"' in html
    assert "실시간으로 반영" in html                                   # 크게 보기 ↔ 원본 동기화
    assert "_mirrorBound" in html


# ── ⑩ 끌어다 놓기 ────────────────────────────────────────────
def test_drop_bindings_cover_all_file_inputs():
    html = webui._HTML
    assert "function enableDrop" in html and "function bindDrops" in html
    for tok in ("enableDrop($('editVideo'))", "enableDrop($('photoPath'), {multi: true})",
                "enableDrop($('narrFile'))", "enableDrop($('secFullPath')",
                "enableDrop(vi)"):
        assert tok in html, tok
    assert "upload_file?name=" in html
    assert "text/uri-list" in html                    # 경로가 실려 오면 복사 없이 즉시


def test_upload_route_streams_before_json():
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    inner = src.split("def _do_post_inner")[1][:600]
    assert inner.index('"/api/upload_file"') < inner.index("_read_json"), \
        "원본 바이트 업로드는 JSON 파싱 전에 가로채야 한다"
    up = src.split("def _handle_upload")[1].split("\n    def ")[0]
    assert "1024 * 1024" in up and "while remain > 0" in up   # 1MB 스트리밍
    assert "uploads" in up and "uuid" in up


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("v113-jobs")
    iso = tmp_path_factory.mktemp("iso")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(workdir), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1], workdir
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env


def test_upload_file_live(server):
    """드래그 폴백 업로드 E2E — 바이트가 그대로 저장되고 경로가 돌아온다."""
    port, workdir = server
    payload = b"\x00\x01FAKEMP4" * 5000
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    conn.request("POST", "/api/upload_file?name=%ED%85%8C%EC%8A%A4%ED%8A%B8.mp4",
                 body=payload, headers={"Content-Length": str(len(payload)),
                                        "Host": f"127.0.0.1:{port}"})
    d = json.loads(conn.getresponse().read())
    assert d.get("ok"), d
    from pathlib import Path
    p = Path(d["path"])
    assert p.is_file() and p.read_bytes() == payload
    assert p.parent.name == "uploads" and p.suffix == ".mp4"
    assert "테스트" in p.name                       # 한글 이름 보존(+고유 접미)
    # 빈 본문은 친절한 오류
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    conn.request("POST", "/api/upload_file?name=a.mp4", body=b"",
                 headers={"Content-Length": "0", "Host": f"127.0.0.1:{port}"})
    r = conn.getresponse()
    assert r.status == 400 and "빈 파일" in json.loads(r.read())["error"]


# ── ⑫ 모든 카드 임시 저장 바 ─────────────────────────────────
def test_draft_bars_on_every_card():
    html = webui._HTML
    assert "function injectDraftBars" in html
    for tok in ("'gen', 'genCard'", "'edit', 'editCard'",
                "'weblink', 'weblinkCard'", "'shop', 'shopCard'"):
        assert tok in html, tok
    assert "draftSaveNow" in html and "draftClearNow" in html
    assert "지금 화면 입력은 그대로" in html          # 지우기의 범위를 화면에서 설명
    assert "지난 저장:" in html and "자동 저장됨" in html and "_fmtClock" in html
    assert "data._ts = Date.now()" in html            # 저장 시각 기록
    assert "'photoSec'" in html                       # 🖼 사진 카드 값도 임시 저장
