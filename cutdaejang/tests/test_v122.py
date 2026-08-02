"""v1.22 — 🖼 저화질 수집 차단·업스케일(31) + 🎨 카드 룩 다양화(32).

> "화질 떨어지는 걸 크롤링한 것 같은데 기준 미달은 크롤링하지 말고, 화질
>  스케일업 같은 걸 간략히." + "카드 자막이 다 비슷비슷해. 구조가 다양성이
>  있어야 — 판매하면 100명 1000명 쓸 텐데 다 똑같은 구조면 의미가 없잖아."

32 조사 결과(코드 분석): 카드 '종류'는 8개였지만 색·라벨·배치가 전부 하드코딩
("KEY NUMBER"·빨간 바·파란 배지…)이라 **모든 영상·모든 회원이 같은 룩**이었다.
→ 영상마다 시드로 (팔레트 6종 × 배치 변형 3종 × 라벨 로테이션)을 정한다.
같은 대본 재렌더 = 같은 룩(재현 가능), 다른 영상·다른 회원 = 다른 룩.
"""

import pathlib
import subprocess
import tempfile
from dataclasses import replace

from cutdaejang import __version__, config
from cutdaejang.core import text_cards as tc
from cutdaejang.core.render_engine.ass_writer import write_ass
from cutdaejang.spec import Background, Canvas, Style, Subtitle, TimelineSpec
from cutdaejang.tools import fetch_web as fw
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg


def test_version():
    assert __version__ == "1.31.0"


# ── 🎨 32: 테마 시스템 ───────────────────────────────────────────
def test_card_theme_deterministic_and_varied():
    assert tc.card_theme(777) == tc.card_theme(777)
    themes = [tc.card_theme(s) for s in range(1, 40)]
    assert len({t["palette"]["name"] for t in themes}) >= 4    # 팔레트가 실제로 돈다
    assert len({t["variant"] for t in themes}) == 3            # 배치 변형 3종 모두 등장
    assert len({t["labels"]["number"] for t in themes}) >= 3   # 라벨 로테이션


def test_card_theme_classic_is_legacy_look():
    t = tc.card_theme(0)
    assert t["variant"] == 0 and t["labels"]["number"] == "KEY NUMBER"
    assert t["palette"]["accent"] == "#4D8DFF"                 # 예전 색 그대로


def test_derive_card_seed_stable():
    a = tc.derive_card_seed(["문장 하나", "문장 둘"])
    assert a == tc.derive_card_seed(["문장 하나", "문장 둘"]) > 0
    assert a != tc.derive_card_seed(["다른 대본"])


SUBS = [Subtitle(text="딱 3가지만 기억하세요", start_us=0, end_us=2_000_000),
        Subtitle(text="무려 95% 할인입니다", start_us=2_000_000, end_us=4_000_000),
        Subtitle(text="지금 링크를 눌러 확인하세요", start_us=4_000_000, end_us=6_000_000)]


def _render(seed) -> str:
    spec = TimelineSpec(canvas=Canvas(w=1080, h=1920, fps=30),
                        style=replace(Style(), card_seed=seed),
                        duration_us=6_000_000, background=Background(),
                        subtitles=SUBS)
    p = pathlib.Path(tempfile.mkdtemp()) / "c.ass"
    write_ass(spec, p)
    return p.read_text(encoding="utf-8")


def test_ass_differs_by_seed_and_auto_is_stable():
    a, b = _render(11111), _render(22222)
    assert a != b                                # 영상(시드)마다 카드가 다르다
    assert _render(0) == _render(0)              # 같은 대본 자동 시드 = 같은 룩
    classic = _render(-1)
    assert "KEY NUMBER" in classic               # 끄면(클래식) 예전 라벨 그대로
    themed = _render(11111)
    lab = tc.card_theme(11111)["labels"]["number"]
    assert lab in themed                         # 시드 라벨이 실제 ASS에 실림


def test_orchestrator_and_settings_wiring():
    src = open("cutdaejang/core/orchestrator.py", encoding="utf-8").read()
    assert 'card_seed=(-1 if sub.get("card_variety") is False else 0)' in src
    assert config.DEFAULTS["subtitle"]["card_variety"] is True
    html = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert 'id="setCardVariety"' in html and "card_variety: $('setCardVariety')" in html


# ── 🖼 31: 크기 판독·기준 미달 차단·업스케일 ─────────────────────
def test_image_dims_stdlib_sniffer():
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
           + (640).to_bytes(4, "big") + (480).to_bytes(4, "big") + b"\x08")
    assert fw.image_dims(png) == (640, 480)
    gif = b"GIF89a" + (321).to_bytes(2, "little") + (123).to_bytes(2, "little")
    assert fw.image_dims(gif) == (321, 123)
    assert fw.image_dims(b"not an image") == (0, 0)


def _mk_img(d: pathlib.Path, name: str, size: str) -> None:
    subprocess.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"testsrc2=s={size}", "-frames:v", "1", "-q:v", "2",
                    str(d / name)], check=True)


@requires_ffmpeg
def test_download_gate_and_upscale(tmp_path):
    import http.server
    import socketserver
    import threading

    from cutdaejang.tools import product_page as pp

    src_dir = tmp_path / "srv"
    src_dir.mkdir()
    _mk_img(src_dir, "small.jpg", "300x300")     # 기준 미달 (짧은 변 480 미만)
    _mk_img(src_dir, "big.jpg", "1200x1200")

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(src_dir), **k)

        def log_message(self, *a):  # noqa: D102
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        out1 = tmp_path / "o1"
        saved, skipped = pp.download_images([base + "/small.jpg",
                                             base + "/big.jpg"], out1)
        assert len(saved) == 1 and skipped == 1          # 저화질은 수집 제외
        assert fw.image_dims(pathlib.Path(saved[0]).read_bytes())[0] == 1200

        out2 = tmp_path / "o2"
        saved2, _sk = pp.download_images([base + "/small.jpg"], out2)
        assert len(saved2) == 1                          # 전멸이면 큰 순 구제
        w, h = fw.image_dims(pathlib.Path(saved2[0]).read_bytes())
        assert w >= 600 and pathlib.Path(saved2[0]).is_file()   # 업스케일(2.2배 캡)
    finally:
        srv.shutdown()
