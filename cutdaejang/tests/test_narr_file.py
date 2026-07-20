"""v0.58 — 직접 녹음한 내레이션 파일 통째 넣기 (analyze_narration_file)."""
from pathlib import Path

from cutdaejang.core import edit_mode
from cutdaejang.utils import ffmpeg as ff


def _make_recording(tmp_path, name="rec.wav"):
    """말소리 흉내: 0.0~1.4s 사인 + 0.8s 무음 + 2.2~3.6s 사인 (총 4초)."""
    p = tmp_path / name
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=4,volume='if(between(t,1.4,2.2),0,1)':eval=frame",
            "-ar", "16000", "-ac", "1", str(p)])
    return str(p)


def test_recording_with_script_maps_to_segments(tmp_path):
    rec = _make_recording(tmp_path)
    subs, dur = edit_mode.analyze_narration_file(
        rec, tmp_path, stt=None, script_lines=["첫 문장입니다", "둘째 문장입니다"])
    assert 3_800_000 < dur < 4_300_000
    assert [s.text for s in subs] == ["첫 문장입니다", "둘째 문장입니다"]
    # 발화 2구간이 잡히면 1:1 매핑 — 첫 자막은 앞 구간, 둘째는 뒤 구간에서 시작
    assert subs[0].start_us < 600_000
    assert subs[1].start_us > 1_500_000
    assert subs[-1].end_us <= dur + 200_000


def test_recording_without_stt_returns_empty_subs(tmp_path):
    rec = _make_recording(tmp_path)
    subs, dur = edit_mode.analyze_narration_file(rec, tmp_path, stt=None)
    assert subs == [] and dur > 3_500_000


def test_recording_with_fake_stt_gets_timed_subs(tmp_path):
    rec = _make_recording(tmp_path)

    class FakeProvider:
        name = "fake"
        def transcribe(self, path, language="ko"):
            return "녹음 인식 문장"

    from cutdaejang.core.stt_engine import STTEngine
    stt = STTEngine(FakeProvider(), tmp_path / "cache")
    subs, dur = edit_mode.analyze_narration_file(rec, tmp_path, stt=stt)
    assert subs and all("녹음 인식" in s.text for s in subs)
    # 시각은 녹음 원본 타임라인 (0 ≤ start < end ≤ 길이)
    for s in subs:
        assert 0 <= s.start_us < s.end_us <= dur + 200_000


def test_recording_silence_only_defaults_to_whole_span(tmp_path):
    p = tmp_path / "silent.wav"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "anullsrc=r=16000:cl=mono:d=2", str(p)])
    subs, dur = edit_mode.analyze_narration_file(
        str(p), tmp_path, stt=None, script_lines=["한 문장"])
    assert len(subs) == 1 and subs[0].text == "한 문장"
    assert 1_800_000 < dur < 2_300_000
