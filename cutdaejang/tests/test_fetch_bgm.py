"""무료 BGM 받기 도구 — 목록 무결성·크레딧 생성·재실행 스킵 (네트워크 없이 검증)."""

import http.server
import threading
import urllib.parse

from cutdaejang.tools import fetch_bgm


def test_tracks_wellformed():
    names = [fetch_bgm.save_name(m, t) for m, t in fetch_bgm.TRACKS]
    assert len(names) == len(set(names)) >= 10          # 중복 없이 두 자릿수 곡
    for mood, title in fetch_bgm.TRACKS:
        assert mood and title
        url = fetch_bgm.track_url(title)
        assert url.startswith("https://incompetech.com/")
        assert " " not in url                            # 공백은 %20으로 인코딩
        assert urllib.parse.unquote(url).endswith(f"{title}.mp3")


def test_main_downloads_writes_credits_and_skips_existing(tmp_path):
    calls = []

    def fake_fetch(url, dest, timeout=0):
        calls.append(url)
        dest.write_bytes(b"m" * 200_000)
        return True

    ok, fail = fetch_bgm.main(tmp_path, fetch_fn=fake_fetch)
    assert not fail and len(ok) == len(fetch_bgm.TRACKS)
    assert len(list(tmp_path.glob("*.mp3"))) == len(fetch_bgm.TRACKS)
    credits = (tmp_path / fetch_bgm.CREDIT_FILE).read_text(encoding="utf-8")
    for _, title in fetch_bgm.TRACKS:
        assert f'"{title}" Kevin MacLeod' in credits
    assert "creativecommons.org/licenses/by/4.0" in credits

    # 재실행: 이미 받은 곡은 fetch를 다시 부르지 않음
    calls.clear()
    ok2, fail2 = fetch_bgm.main(tmp_path, fetch_fn=fake_fetch)
    assert not calls and len(ok2) == len(fetch_bgm.TRACKS) and not fail2


def test_fetch_rejects_tiny_response(tmp_path):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"x" * (200_000 if self.path.endswith("big.mp3") else 30)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert fetch_bgm.fetch(f"{base}/small.mp3", tmp_path / "s.mp3") is False  # 오류 페이지 취급
        assert fetch_bgm.fetch(f"{base}/big.mp3", tmp_path / "b.mp3") is True
        assert (tmp_path / "b.mp3").stat().st_size == 200_000
    finally:
        srv.shutdown()
