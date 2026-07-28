"""v1.09 — 긴 내레이션 연속 낭독 + 쇼핑 사진 전량 반영·검증."""

import inspect
import math
import struct
import wave
from pathlib import Path

from cutdaejang.core import tts_engine
from cutdaejang.gui import webui
from cutdaejang.tools import product_page
from tests.conftest import requires_ffmpeg


class _PausingGemini:
    """여러 문장 사이에 자연 무음을 만드는 가짜 Gemini TTS."""

    name = "gemini"
    model = "fake-continuity"

    def __init__(self):
        self.calls = 0

    def synthesize(self, text, voice, out_path):
        self.calls += 1
        spoken = text.split("[낭독 원고]\n", 1)[-1]
        count = spoken.count("\n\n") + 1
        rate = 24_000
        tone_n = int(rate * 0.28)
        silence_n = int(rate * 0.14)
        frames = bytearray()
        for i in range(count):
            for n in range(tone_n):
                sample = int(6000 * math.sin(2 * math.pi * 440 * n / rate))
                frames += struct.pack("<h", sample)
            if i + 1 < count:
                frames += b"\0\0" * silence_n
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(frames)
        return str(out_path)


def test_continuity_blocks_cross_section_sized_groups():
    lines = [f"{i}번째 문장 " + ("가" * 90) for i in range(30)]
    blocks = tts_engine.continuity_blocks(lines, max_chars=500, max_sentences=8)
    assert blocks[0][0] == 0 and blocks[-1][1] == len(lines)
    assert all(2 <= end - start <= 8 for start, end in blocks)
    assert len(blocks) < len(lines) // 2


@requires_ffmpeg
def test_continuous_tts_calls_once_and_keeps_sentence_clips(tmp_path):
    provider = _PausingGemini()
    lines = ["첫 구간의 마지막 문장입니다.", "둘째 구간도 같은 목소리입니다.",
             "마지막까지 같은 속도로 읽습니다."]
    eng = tts_engine.TTSEngine(provider, tmp_path / "cache")
    paths = eng.synth_all(lines, continuity=True)
    assert provider.calls == 1                         # 문장별 3회가 아니라 한 호흡 1회
    assert len(paths) == len(lines) and all(p.is_file() for p in paths)
    assert all(".cont-" in p.name for p in paths)
    # 경계 무음의 절반씩이 조각에 중복으로 남아 명시적 문장 간격과 더해지지 않는다.
    assert all(tts_engine.ff.probe_duration_us(str(p)) < 500_000 for p in paths)

    # 다시 만들면 블록·분할 캐시를 그대로 써 API를 추가 호출하지 않는다.
    eng2 = tts_engine.TTSEngine(provider, tmp_path / "cache")
    paths2 = eng2.synth_all(lines, continuity=True)
    assert provider.calls == 1 and paths2 == paths


def test_product_parser_prefers_lazy_and_srcset_without_extension():
    html = """<html><meta property="og:title" content="테스트 상품">
    <img src="/thumb.jpg" data-src="/detail/original"
         srcset="/detail/mid 640w, https://cdn.example.com/detail/large 1600w">
    </html>"""
    out = product_page.parse_product(html, "https://shop.example.com/items/1")
    assert out["images"][0] == "https://shop.example.com/detail/original"
    assert "https://cdn.example.com/detail/large" in out["images"]
    assert "https://shop.example.com/thumb.jpg" in out["images"]

    relative_og = product_page.parse_product(
        '<meta property="og:title" content="상품">'
        '<meta property="og:image" content="/images/cover.jpg">',
        "https://shop.example.com/items/1")
    assert relative_og["images"][0] == "https://shop.example.com/images/cover.jpg"


def test_hi_res_failure_retries_original(monkeypatch, tmp_path):
    from cutdaejang.tools import fetch_web

    tried = []
    tiny = b"\x89PNG\r\n\x1a\n" + b"x" * 100
    valid = b"\x89PNG\r\n\x1a\n" + b"x" * 20_000

    def fake_fetch(url, **_kwargs):
        tried.append(url)
        return tiny if "1024x1024ex" in url else valid

    monkeypatch.setattr(fetch_web, "fetch_bytes", fake_fetch)
    src = "https://thumbnail7.coupangcdn.com/thumbnails/remote/492x492ex/image/a.jpg"
    saved, skipped = product_page.download_images([src], tmp_path, referer="https://coupang.com/p/1")
    assert len(saved) == 1 and skipped == 0
    assert "1024x1024ex" in tried[0] and src in tried


def test_shop_ui_shows_exact_render_order_and_controls():
    html = webui._HTML
    for token in ("영상에 반영할 사진", "function removeShopPhoto",
                  "function moveShopPhoto", "사진 배열과 항상 같은 인덱스",
                  "referer:(($('shopLinkInput')"):
        assert token in html
    body = open(webui.__file__, encoding="utf-8").read().split(
        "def _run_sections", 1)[1].split("\ndef ", 1)[0]
    assert "continuity=True" in body
    assert "gap_us=narr_gap_us" in body
    assert "bed3-final-sync" in body
    assert 'cut_dur > narr_end + 50_000' in body
    assert 'f"sec_{i}_fit.mp4"' in body
    src = open(webui.__file__, encoding="utf-8").read()
    assert "photo_manifest.json" in src
    assert "빠짐없이 내레이션 문장 타이밍에 맞춰 배치" in src


def test_ui_start_message_is_cp949_safe():
    """한국어 Windows의 기본 콘솔에서도 서버가 안내문 출력 중 죽지 않아야 한다."""
    src = inspect.getsource(webui.serve)
    message = src[src.index('print(f"컷대장 UI:'):]
    message.splitlines()[0].encode("cp949")
