"""v0.53 🔔 효과음 자동 — 합성·배치·믹스·렌더 통합."""

import subprocess

from cutdaejang.core import sfx
from cutdaejang.spec import AudioClip, Sfx, Subtitle, TimelineSpec
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg


@requires_ffmpeg
def test_ensure_sfx_synthesizes_and_user_override(tmp_path):
    """3종 합성 캐시 + 같은 이름의 사용자 파일이 있으면 그걸 우선."""
    paths = sfx.ensure_sfx(tmp_path)
    assert set(paths) == {"pop", "whoosh", "ding"}
    for p in paths.values():
        assert ff.probe_duration_us(p) > 80_000  # 실제 소리 파일
    # 두 번째 호출은 캐시 재사용 (같은 경로)
    assert sfx.ensure_sfx(tmp_path) == paths

    # 사용자가 '뿅.mp3'를 넣으면 합성본 대신 그걸 사용
    user = tmp_path / "뿅.mp3"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "sine=frequency=500:duration=0.3", str(user)])
    paths2 = sfx.ensure_sfx(tmp_path)
    assert paths2["pop"].endswith("뿅.mp3")


def test_build_events_placement(tmp_path):
    """배치 규칙 — 띠링(훅 0.15s)·뿅(강조 문장, 앞머리 제외)·휙(장면 전환)."""
    paths = {"pop": "p.wav", "whoosh": "w.wav", "ding": "d.wav"}
    spec = TimelineSpec(
        duration_us=8_000_000, hook="제목 있음",
        audio=[AudioClip(path="a.wav", start_us=t, end_us=t + 1_000_000)
               for t in (0, 2_000_000, 4_000_000, 6_000_000)],
        subtitles=[
            Subtitle(text="첫 문장 | 강조", highlight="강조", start_us=0, end_us=1_000_000),
            Subtitle(text="평범한 문장", start_us=2_000_000, end_us=3_000_000),
            Subtitle(text="[노랑]색[/] 마크업", start_us=4_000_000, end_us=5_000_000),
            Subtitle(text="강조 단어", highlight="단어", start_us=6_000_000, end_us=7_000_000),
        ])
    ev = sfx.build_events(spec, paths, {"volume_db": -10},
                          scene_starts_us=[0, 3_000_000, 5_500_000])
    names = [(e.name, e.start_us) for e in ev]
    assert ("ding", 150_000) in names                      # 훅 띠링
    pops = [t for n, t in names if n == "pop"]
    assert pops == [4_000_000, 6_000_000]                  # 첫 문장(0s)은 겹침 방지로 제외
    whooshes = [t for n, t in names if n == "whoosh"]
    assert whooshes == [2_880_000, 5_380_000]              # 전환 0.12s 전, 첫 장면 제외
    assert all(e.gain_db in (-10, -13) for e in ev)        # 휙은 -3dB 더 낮게

    # 훅 없음 + 장면 없음 → 뿅만
    spec.hook = ""
    ev2 = sfx.build_events(spec, paths, {})
    assert {e.name for e in ev2} == {"pop"}


@requires_ffmpeg
def test_mix_sfx_audible_at_position(tmp_path):
    """무음 2초 위에 0.5s 지점 띠링 → 그 구간만 소리가 생기는지 실측."""
    silent = str(tmp_path / "voice.m4a")
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono:d=2", "-c:a", "aac", silent])
    paths = sfx.ensure_sfx(tmp_path / "sfx")
    out = str(tmp_path / "mixed.m4a")
    sfx.mix_sfx(silent, [Sfx(path=paths["ding"], start_us=500_000, gain_db=-6,
                             name="ding")], out)
    assert abs(ff.probe_duration_us(out) - 2_000_000) < 150_000  # 길이 유지

    def max_volume(path, ss, t):
        r = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "info", "-ss", str(ss), "-t", str(t), "-i", path,
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True)
        line = next(l for l in r.stderr.splitlines() if "max_volume" in l)
        return float(line.split("max_volume:")[1].replace("dB", "").strip())

    assert max_volume(out, 0.5, 0.4) > -30    # 띠링 구간엔 소리
    assert max_volume(out, 1.5, 0.4) < -60    # 뒤쪽은 여전히 무음

    # 이벤트가 없으면 원본 복사
    out2 = str(tmp_path / "copy.m4a")
    sfx.mix_sfx(silent, [], out2)
    assert max_volume(out2, 0.5, 0.4) < -60


@requires_ffmpeg
def test_run_job_places_sfx_and_renders(tmp_path):
    """통합 — 스텁 생성에서 spec.sfx가 기록되고(띠링+뿅) 렌더가 정상 완료."""
    from cutdaejang.core import orchestrator
    from cutdaejang.core.orchestrator import JobOptions

    res = orchestrator.run_job(
        tmp_path / "jobs", __import__("cutdaejang.core.script_generator",
                                      fromlist=["StubScript"]).StubScript().generate("효과음"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True))
    assert res.status == "ok", res.errors
    spec = TimelineSpec.load(f"{res.job_dir}/spec.json")
    names = {e.name for e in spec.sfx}
    assert "ding" in names and "pop" in names  # 스텁 대본은 훅+강조 문장 보유
    assert all(e.start_us < spec.duration_us for e in spec.sfx)
    from pathlib import Path
    mixed = Path(res.job_dir) / "render" / "voice_sfx.m4a"
    assert mixed.is_file() and ff.probe_duration_us(str(mixed)) > 1_000_000  # 믹스 사용됨

    # 설정으로 끄면 배치 없음
    from cutdaejang import config
    off = config.deep_merge(config.load_settings(), {"sfx": {"enabled": False}})
    res2 = orchestrator.run_job(
        tmp_path / "jobs2", __import__("cutdaejang.core.script_generator",
                                       fromlist=["StubScript"]).StubScript().generate("무음"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True), settings=off)
    spec2 = TimelineSpec.load(f"{res2.job_dir}/spec.json")
    assert spec2.sfx == []
