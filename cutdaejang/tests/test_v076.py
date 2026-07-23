"""v0.76 「말 다듬기 팩」 — 필러 컷 + 반복(NG) 테이크 + 카라오케 자막 + 신뢰도.

경쟁 조사 P0: Whisper 단어 타임스탬프를 열어(1회 전사 그대로) ① 홀로 나온
추임새("어·음")를 영상에서 컷 ② 같은 말 반복 테이크 감지 ③ 말하는 단어가
차오르는 \\k 카라오케 자막 ④ 인식 신뢰도 낮은 줄 표시를 얹는다.
"""
import json

import pytest

from cutdaejang.core import edit_mode as em
from cutdaejang.core.render_engine import ass_writer as aw
from cutdaejang.core.stt_engine import STTEngine
from cutdaejang.spec import Subtitle, TimelineSpec
from cutdaejang.utils import ffmpeg as ff


# ── spec: words/conf 필드 후방·전방 호환 ──────────────────────────────


def test_subtitle_new_fields_default_and_roundtrip():
    old = Subtitle(text="x", start_us=0, end_us=1_000_000)
    assert old.words == [] and old.conf == 1.0
    # 옛 spec.json(words 없음) 로드 호환
    spec = TimelineSpec.from_dict({
        "canvas": {"w": 1080, "h": 1920, "fps": 30}, "duration_us": 1_000_000,
        "background": {"type": "color", "color": "#000"},
        "subtitles": [{"text": "a", "start_us": 0, "end_us": 500_000}],
    })
    assert spec.subtitles[0].words == []


# ── STT 엔진: 5-튜플(단어·신뢰도) 변환 + 캐시 ─────────────────────────


class _FakeRich:
    name = "whisper"

    def transcribe(self, p, language="ko"):
        return "안녕 하세요"

    def transcribe_timed(self, p, language="ko"):
        return [(0.5, 2.0, "안녕 하세요",
                 [(0.5, 1.0, "안녕"), (1.2, 1.9, "하세요")], 0.82)]


class _FakeOld3:
    name = "whisper"

    def transcribe(self, p, language="ko"):
        return "옛 형식"

    def transcribe_timed(self, p, language="ko"):
        return [(0.0, 1.0, "옛 형식")]  # 구버전 3-튜플


@pytest.fixture()
def wav(tmp_path):
    p = tmp_path / "a.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "sine=frequency=300:duration=1:sample_rate=16000", str(p)])
    return str(p)


def test_stt_engine_words_conf_and_cache(tmp_path, wav):
    eng = STTEngine(_FakeRich(), tmp_path / "c")
    out = eng.transcribe_timed(wav)
    assert out[0][2] == "안녕 하세요"
    assert out[0][3] == [(500_000, 1_000_000, "안녕"), (1_200_000, 1_900_000, "하세요")]
    assert out[0][4] == 0.82
    # 캐시는 .seg2.json (옛 .seg.json과 분리) + 재호출 시 캐시 히트
    assert list((tmp_path / "c").glob("*.seg2.json"))
    eng2 = STTEngine(_FakeRich(), tmp_path / "c")
    out2 = eng2.transcribe_timed(wav)
    assert out2 == out and eng2.stats["cache_hits"] == 1


def test_stt_engine_tolerates_3tuple_provider(tmp_path, wav):
    out = STTEngine(_FakeOld3(), tmp_path / "c2").transcribe_timed(wav)
    assert out[0][2] == "옛 형식" and out[0][3] == [] and out[0][4] == 1.0


def test_build_subtitles_timed_attaches_relative_words():
    pieces = [[(200_000, 2_000_000, "안녕 하세요",
                [(300_000, 800_000, "안녕"), (1_000_000, 1_800_000, "하세요")], 0.7)]]
    subs = em.build_subtitles_timed([(5_000_000, 8_000_000)], pieces)
    s = subs[0]
    assert s.start_us == 5_200_000 and s.conf == 0.7
    # 단어는 '자막 시작 기준 상대값'
    assert s.words[0] == [100_000, 600_000, "안녕"]


# ── 필러(추임새) 컷 ───────────────────────────────────────────────────


def _sub(text, start, end, words):
    return Subtitle(text=text, start_us=start, end_us=end, words=words)


def test_detect_filler_isolated_only():
    subs = [
        _sub(" 어 안녕하세요", 1_000_000, 4_000_000,
             [[0, 400_000, "어"], [800_000, 2_000_000, "안녕하세요"]]),
        # "그 사람"의 "그" — 다음 단어와 50ms 간격 → 보호
        _sub(" 그 사람이 좋아요", 5_000_000, 8_000_000,
             [[0, 300_000, "그"], [350_000, 1_500_000, "사람이"],
              [1_600_000, 2_500_000, "좋아요"]]),
    ]
    spans = em.detect_filler_spans(subs)
    assert len(spans) == 1
    a, b, w = spans[0]
    assert w.strip() == "어" and a == 1_000_000 - 0 and b > a  # sub.start+0-pad 클램프


def test_apply_filler_cut_shrinks_video_and_text(tmp_path):
    src = tmp_path / "v.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:s=320x180:r=30:d=6",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=6",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-c:a", "aac", "-shortest", str(src)])
    subs = [_sub(" 어 안녕하세요", 1_000_000, 4_000_000,
                 [[0, 500_000, "어"], [900_000, 2_500_000, "안녕하세요"]])]
    spans = em.detect_filler_spans(subs)
    assert spans
    video, out = em.apply_filler_cut(str(src), subs, spans, str(tmp_path / "o.mp4"))
    got = ff.probe_duration_us(video) / 1e6
    removed = sum(b - a for a, b, *_ in spans) / 1e6
    assert got == pytest.approx(6.0 - removed, abs=0.3)
    assert out and "어" not in out[0].text and "안녕하세요" in out[0].text
    assert out[0].words and out[0].words[0][2].strip() == "안녕하세요"


def test_apply_filler_cut_noop_without_spans(tmp_path):
    v, s = em.apply_filler_cut("nope.mp4", [], [], str(tmp_path / "x.mp4"))
    assert v == "nope.mp4" and s == []


# ── 반복(NG) 테이크 ───────────────────────────────────────────────────


def test_detect_repeat_takes_adjacent_and_skip_one():
    texts = ["이 제품 정말 좋아요", "이 제품 정말 좋아요!",   # 인접 반복 → 0 드랍
             "짧", "완전 다른 이야기 하나",
             "마지막 멘트입니다", "네", "마지막 멘트입니다~"]  # 한 칸 건너 반복 → 4 드랍
    assert em.detect_repeat_takes(texts) == [0, 4]


def test_detect_repeat_takes_ignores_short_and_distinct():
    assert em.detect_repeat_takes(["네", "네", "아 진짜 다른 말", "또 전혀 다른 말"]) == []


# ── 카라오케 자막 ─────────────────────────────────────────────────────


class _Sty:
    primary_color = "#FFFFFF"
    highlight_color = "#FFD400"
    fade = True
    anim = "karaoke"
    wrap_chars = 16


def test_karaoke_body_and_fallback():
    s = _sub("안녕 하세요", 0, 2_000_000,
             [[0, 500_000, "안녕"], [700_000, 1_500_000, "하세요"]])
    body = aw.dialogue_text(s, _Sty())
    assert "\\k" in body and "\\2c" in body and "\\fad" in body
    # 단어 사이 200ms 공백도 \k로 싱크 유지
    assert "{\\k20}" in body
    nb = aw.dialogue_text(Subtitle(text="워드없음", start_us=0, end_us=1_000_000), _Sty())
    assert "\\k" not in nb  # 단어 시각 없으면 기존 폴백


def test_write_ass_karaoke_end_to_end(tmp_path):
    from cutdaejang.spec import Background, Canvas, Style

    spec = TimelineSpec(
        canvas=Canvas(w=1080, h=1920, fps=30), duration_us=3_000_000,
        background=Background(type="color", color="#000000"),
        subtitles=[_sub("안녕 하세요", 200_000, 2_000_000,
                        [[0, 500_000, "안녕"], [700_000, 1_500_000, "하세요"]])],
        style=Style(font="Pretendard-ExtraBold", size=84, outline=4, anim="karaoke"),
    )
    out = aw.write_ass(spec, tmp_path / "k.ass")
    text = open(out, encoding="utf-8").read()
    assert "\\k" in text


# ── 검토 데이터 왕복 ──────────────────────────────────────────────────


def test_dicts_roundtrip_keeps_words_and_drops_on_edit():
    s = _sub("안녕 하세요", 0, 2_000_000,
             [[0, 500_000, "안녕"], [700_000, 1_500_000, " 하세요"]])
    s.conf = 0.4
    d = em.subtitles_to_dicts([s])[0]
    assert d["words"] and d["conf"] == 0.4
    # 그대로 돌아오면 단어 유지
    back = em.dicts_to_subtitles([dict(d)])[0]
    assert back.words and back.conf == 0.4
    # 검토에서 글을 고치면 단어 시각은 버림 (싱크 안 맞으니 카라오케 폴백)
    d2 = dict(d); d2["text"] = "완전히 고친 문장"
    assert em.dicts_to_subtitles([d2])[0].words == []


# ── UI 배선 ──────────────────────────────────────────────────────────


def test_webui_wiring_v076():
    from cutdaejang.gui import webui

    assert "filler_cut" in webui._EDIT_LAST_KEYS
    assert "take_clean" in webui._EDIT_LAST_KEYS
    for i in ("editFillerCut", "editTakeClean", "cleanRepeatsBtn"):
        assert f'id="{i}"' in webui._HTML, i
    assert 'value="karaoke"' in webui._HTML
