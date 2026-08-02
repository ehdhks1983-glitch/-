"""v1.10 — 긴 영상 진입·1800초 상한과 v1.09 누락 안전장치."""

from cutdaejang import __version__
from cutdaejang.core import edit_mode, video_editor
from cutdaejang.gui import webui
from cutdaejang.spec import Subtitle


def test_cut_boundaries_snap_out_of_speech():
    speech = [(1_000_000, 3_000_000), (5_000_000, 7_000_000)]
    ranges = [(2_000_000, 6_200_000)]

    out = video_editor.shift_ranges_to_silence(
        ranges, speech, 10_000_000)

    assert out == [(1_000_000, 7_000_000)]
    assert all(
        not any(start < point < end for start, end in speech)
        for point in out[0]
    )
    assert video_editor.shift_ranges_to_silence(
        ranges, speech, 10_000_000, max_shift_us=100_000) == ranges


def test_long_video_ui_and_narration_chunking(monkeypatch, tmp_path):
    assert __version__ == "1.24.0"
    html = webui._HTML
    first_row = html.split('<div class="home-cards">', 1)[1].split("</div>", 1)[0]
    assert "긴 영상 (가로 16:9)" in first_row
    assert "openMode('sections')" in first_row
    assert 'id="autoTargetSec" value="30" min="0" max="1800"' in html
    assert 'id="genLenCustomMin" min="1" max="30"' in html

    calls = []
    monkeypatch.setattr(
        edit_mode.ff, "filter_complex_args",
        lambda graph, _path: ["-filter_complex", graph],
    )
    monkeypatch.setattr(edit_mode.ff, "run", lambda args: calls.append(args))
    clips = [tmp_path / f"voice_{i:03d}.wav" for i in range(90)]
    subtitles = [
        Subtitle(text=f"문장 {i}", start_us=i * 500_000,
                 end_us=i * 500_000 + 300_000)
        for i in range(90)
    ]

    result = edit_mode.build_narration_wav(
        clips, subtitles, 46_000_000, tmp_path / "narration.wav")

    assert result == str(tmp_path / "narration.wav")
    assert [args.count("-i") for args in calls] == [40, 40, 10, 3]
    joined = "\n".join(" ".join(map(str, args)) for args in calls)
    assert "narration_part00.wav" in joined
    assert "narration_part02.wav" in joined
