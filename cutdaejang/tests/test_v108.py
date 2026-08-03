"""v1.08 — ⚡ 사진 영상 속도 + 🩺 쇼핑 수집 단계 리포트 + 👵 쉬운 설정 (요청 3건).

① 50장 슬라이드쇼가 느린 원인: GPU 미사용 + 장당 고해상 boxblur 24×2회
   → nvenc 자동 + 블러를 1/4 해상도에서 (비용 ~16분의 1, backdrop이라 화질 동일)
② "아직도 1장" 수사용: 수집이 직접/모바일/브라우저 단계별로 몇 장을 건졌는지
   완료 문구·차단 문구에 그대로 표시 — 다음 진단 리포트가 원인을 말해준다
③ 설정창 2층화(👵 자주 바꾸는 것 + 🔧 전문가) + 카드 꾸미기 ↔ 설정 연동
"""

import json
import threading
import urllib.request

import pytest

from cutdaejang.gui import webui
from cutdaejang.tools import product_page as pp
from tests.conftest import requires_ffmpeg


@requires_ffmpeg
def test_photos_to_video_still_correct_after_speedup(tmp_path):
    """블러 경량화·인코더 교체 후에도 결과가 정상 (길이·해상도·블러 배경)."""
    import subprocess

    from cutdaejang.core.video_editor import photos_to_video
    from cutdaejang.utils import ffmpeg as ff

    imgs = []
    for i, c in enumerate(("red", "blue")):
        p = tmp_path / f"p{i}.png"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c={c}:s=640x360", "-frames:v", "1", str(p)])
        imgs.append(str(p))
    out = photos_to_video(imgs, 4_000_000, str(tmp_path / "s.mp4"),
                          size=(360, 640))
    dur = ff.probe_duration_us(out) / 1e6
    assert 3.6 <= dur <= 4.4, dur
    w, h = ff.probe_video_size(out)
    assert (w, h) == (360, 640)
    # 가로 사진 위아래는 블러 배경(빨강 계열) — 위쪽 가장자리 픽셀 확인
    r = subprocess.run([ff.ffmpeg_bin(), "-v", "error", "-i", out,
                        "-vf", "select=eq(n\\,10),crop=4:4:178:20",
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    px = r.stdout
    assert len(px) >= 48, r.stderr[-200:]
    assert sum(px[0::3][:16]) / 16 > 60         # 빨강 성분이 살아 있는 배경


def test_photos_to_video_uses_gpu_and_light_blur():
    src = open("cutdaejang/core/video_editor.py", encoding="utf-8").read()
    body = src.split("def photos_to_video")[1].split("\ndef ")[0]
    assert "nvenc_available()" in body and "h264_nvenc" in body
    assert "boxblur=6:1" in body and "boxblur=24:2" not in body
    assert "veryfast" in body                    # CPU 폴백도 빠른 프리셋


def test_collect_product_reports_stages(monkeypatch):
    """완료 결과에 '직접 N장 · 모바일 N장' 단계 리포트가 실린다."""
    desktop = ('<html><meta property="og:title" content="상품">'
               '<meta property="og:image" content="https://thumbnail1.coupangcdn.com/t/m.jpg">'
               '<p>' + "설명 " * 20 + '</p></html>')
    mobile = ('<html><meta property="og:title" content="상품">'
              + "".join(f'<img src="https://thumbnail{i}.coupangcdn.com/t/{i}.jpg">'
                        for i in range(2, 6)) + "</html>")

    def fake_fetch(url, timeout=20.0, ua="", referer=""):
        if url.startswith("https://m.coupang.com/"):
            return mobile, url
        return desktop, "https://www.coupang.com/vp/products/1"

    monkeypatch.setattr(pp, "_fetch_html", fake_fetch)
    out = pp.collect_product("https://www.coupang.com/vp/products/1")
    assert "직접 1장" in out["via_detail"] and "모바일 4장" in out["via_detail"]


def test_blocked_error_includes_stage_detail(monkeypatch):
    def boom(url, timeout=20.0, ua="", referer=""):
        raise OSError("차단")

    monkeypatch.setattr(pp, "_fetch_html", boom)
    monkeypatch.setattr(pp, "_browser_dump", lambda u, timeout=50.0: "")
    with pytest.raises(pp.ShopBlockedError) as ei:
        pp.collect_product("https://www.coupang.com/vp/products/2")
    msg = str(ei.value)
    assert "직접 실패" in msg and "브라우저 차단" in msg


@pytest.fixture()
def server(tmp_path_factory):
    import os

    from cutdaejang import config

    workdir = tmp_path_factory.mktemp("ui-v108")
    iso = tmp_path_factory.mktemp("iso108")
    (iso / "settings.json").write_text("{}", encoding="utf-8")
    old_env = os.environ.get("CUTDAEJANG_SETTINGS")
    os.environ["CUTDAEJANG_SETTINGS"] = str(iso / "settings.json")
    orig_keys_path = config.api_keys_path
    config.api_keys_path = lambda: iso / "api_keys.json"
    httpd = webui.create_server(str(workdir), port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    config.api_keys_path = orig_keys_path
    if old_env is None:
        os.environ.pop("CUTDAEJANG_SETTINGS", None)
    else:
        os.environ["CUTDAEJANG_SETTINGS"] = old_env


def test_quick_set_roundtrip_and_whitelist(server):
    def post(body):
        req = urllib.request.Request(server + "/api/quick_set",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:  # noqa: F821
            return json.loads(e.read())

    assert post({"patch": {"subtitle": {"font_size": 104, "text_cards": False}}}).get("ok")
    with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
        st = json.loads(r.read())
    assert st["settings"]["subtitle"]["font_size"] == 104
    assert st["settings"]["subtitle"]["text_cards"] is False
    assert post({"patch": {"subtitle": {"font_size": 999}}}).get("ok")   # 상한 클램프
    with urllib.request.urlopen(server + "/api/state", timeout=30) as r:
        st2 = json.loads(r.read())
    assert st2["settings"]["subtitle"]["font_size"] == 128   # v1.24 「특대」(124) 수용
    assert "error" in post({"patch": {"tts": {"rpm_limit": 1}}})         # 화이트리스트 밖


def test_v108_ui_wiring():
    html = webui._HTML
    for tok in ("👵 자주 바꾸는 것", "🔧 전문가 설정", "모든 영상에 항상",
                'class="ezchips"', "function initEzChips", "function markEzChips",
                # v1.35: injectQuickDeco(칩만 끼워 넣기) → mountDeco(선택칸까지 한 상자로) (목록 64)
                "function mountDeco", "function quickSet", "/api/quick_set",
                "qd-size", "qd-cards", "data-lazy"):
        assert tok in html, tok
    assert html.count('id="setTextCards"') == 1          # 누구나 존으로 '이동' (중복 없음)
    src = open(webui.__file__, encoding="utf-8").read()
    assert "via_detail" in src                            # 쇼핑 노트에 단계 리포트
