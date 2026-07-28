"""v1.09 — 🗣 말 경계 스냅 + 긴 영상 내레이션 얹기 안정화 (사용자 리포트 "아직도 끊김").

8분30초급에서 남아 있던 끊김 경로 2개를 구조적으로 막는다:
① 목소리 든 영상을 완전 자동(목표초 몽타주)으로 자르면 자막 인식이 꺼져 있을 때
   말 위치를 모른 채 시간으로만 잘라 문장 한가운데가 끊겼다 → 컷 경계를 무음으로 스냅
② 내레이션 베드가 클립 전부를 한 명령줄에 실어 문장 100개↑(긴 영상)에서
   Windows 32K 한계에 깨질 수 있었다 → 40개 묶음 부분 합성 + 필터 파일 경유
"""

from cutdaejang.core.video_editor import shift_ranges_to_silence
from tests.conftest import requires_ffmpeg


def test_snap_moves_cut_out_of_speech():
    """말 한가운데 떨어진 컷 경계가 가장 가까운 무음 지점으로 이동한다."""
    speech = [(1_000_000, 3_000_000), (5_000_000, 7_000_000)]
    out = shift_ranges_to_silence([(2_000_000, 6_200_000)], speech, 10_000_000)
    (s, e), = out
    for x in (s, e):                       # 두 경계 모두 발화 구간 밖
        assert not any(a < x < b for a, b in speech), (s, e)
    assert abs(s - 2_000_000) <= 1_500_000 and abs(e - 6_200_000) <= 1_500_000


def test_snap_keeps_faraway_and_silent_sources():
    speech = [(1_000_000, 3_000_000)]
    # 무음이 허용 이동폭 안에 없으면 그대로 (억지로 안 옮김)
    out = shift_ranges_to_silence([(1_700_000, 2_400_000)], speech, 10_000_000,
                                  max_shift_us=200_000)
    assert out == [(1_700_000, 2_400_000)]
    # 말이 없는 영상은 스냅 없음
    assert shift_ranges_to_silence([(0, 5_000_000)], [], 10_000_000) == [(0, 5_000_000)]
    # 순서·최소 길이 보존 (겹침 방지)
    out2 = shift_ranges_to_silence(
        [(0, 2_900_000), (3_100_000, 6_000_000)], speech, 10_000_000)
    assert out2[0][1] <= out2[1][0] and all(e - s >= 600_000 for s, e in out2)


@requires_ffmpeg
def test_long_bed_survives_many_clips(tmp_path):
    """문장 90개(긴 영상급) 내레이션 베드가 명령줄 한계 없이 완성된다."""
    from cutdaejang.core import edit_mode
    from cutdaejang.spec import Subtitle
    from cutdaejang.utils import ffmpeg as ff

    clips, subs = [], []
    for i in range(90):
        p = tmp_path / f"c{i:03d}.wav"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", "sine=frequency=500:duration=0.35",
                "-ar", "24000", str(p)])
        clips.append(str(p))
        subs.append(Subtitle(text=f"문장{i}", start_us=i * 500_000,
                             end_us=i * 500_000 + 350_000))
    total = 90 * 500_000 + 1_000_000
    out = edit_mode.build_narration_wav(clips, subs, total, tmp_path / "bed.wav")
    dur = ff.probe_duration_us(out)
    assert abs(dur - total) < 200_000, dur          # 전체 길이 유지
    # 묶음 부분 파일이 실제로 만들어졌다 (40개 초과 → 분할 경로)
    assert list(tmp_path.glob("bed_part*.wav")), "묶음 분할이 안 돌았음"


def test_wiring_snap_and_chunked_bed():
    src_w = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert src_w.count("shift_ranges_to_silence") == 2      # 편집 완전자동 + 구간 몽타주
    assert "말이 안 끊기게 컷 지점을 무음에 맞추는 중" in src_w
    src_e = open("cutdaejang/core/edit_mode.py", encoding="utf-8").read()
    body = src_e.split("def build_narration_wav")[1].split("\ndef ")[0]
    assert "_BED_CHUNK" in src_e and "filter_complex_args" in body
    assert '"-filter_complex", fc' not in body               # 명령줄 직접 탑재 제거
