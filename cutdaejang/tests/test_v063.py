"""v0.63 — 길이 맞춤·타임코드·프롬프트 글자 금지·글씨체·기울임."""
from pathlib import Path

from cutdaejang.core.render_engine.ass_writer import write_ass
from cutdaejang.core.timeline_calculator import TimelineOptions, build_spec
from cutdaejang.spec import AudioClip, Background, Canvas, Style, Subtitle, TimelineSpec
from cutdaejang.utils import ffmpeg as ff


def _wavs(tmp_path, n, dur=1.0):
    out = []
    for i in range(n):
        p = tmp_path / f"s{i}.wav"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"anullsrc=r=44100:cl=mono:d={dur}", str(p)])
        out.append(str(p))
    return out


def test_pace_to_target_stretches_gaps(tmp_path):
    paths = _wavs(tmp_path, 4)  # 말 4초
    bg = Background(type="image", path="bg.png")
    base = build_spec(["하나", "둘", "셋", "넷"], paths, bg, Style())
    spec = build_spec(["하나", "둘", "셋", "넷"], paths, bg, Style(),
                      opts=TimelineOptions(pace_to_us=8_000_000))
    assert base.duration_us < 6_000_000
    assert abs(spec.duration_us - 8_000_000) < 400_000  # 간격을 늘려 약 8초
    # 자막·오디오 시작이 함께 밀리는지 (마지막 문장 시작 > 기본)
    assert spec.subtitles[-1].start_us > base.subtitles[-1].start_us


def test_pace_cap_prevents_awkward_silence(tmp_path):
    paths = _wavs(tmp_path, 2)  # 경계 1개 → 최대 +2.5초
    bg = Background(type="image", path="bg.png")
    spec = build_spec(["하나", "둘"], paths, bg, Style(),
                      opts=TimelineOptions(pace_to_us=60_000_000))
    assert spec.duration_us < 6_500_000  # 60초를 요청해도 침묵 상한 때문에 조금만 늘음


def test_script_timecode_parser():
    from cutdaejang.gui.webui import _parse_script_lines

    lines, end = _parse_script_lines(
        "0:00-0:03 첫 장면\n0:03–0:06: 둘째\n(0:06~0:28) 셋째\n마무리 멘트")
    assert lines == ["첫 장면", "둘째", "셋째", "마무리 멘트"]
    assert end == 28
    l2, e2 = _parse_script_lines("타임코드 없는 대본\n둘째 줄")
    assert e2 is None and len(l2) == 2


def test_scene_prompt_strips_quotes_and_bans_text():
    from cutdaejang.core.background_generator import scene_prompt_text

    s = scene_prompt_text('스크롤 "당신 블로그 3초 만에" 이탈', "일러스트", "")
    assert "당신 블로그" not in s
    assert "절대 넣지 말 것" in s and "스크롤" in s


def test_hook_font_and_tilt_in_ass(tmp_path):
    spec = TimelineSpec(
        duration_us=1_000_000, canvas=Canvas(540, 960, 24),
        background=Background(type="image", path="bg.png"),
        audio=[AudioClip("s.wav", 0, 900_000)],
        subtitles=[Subtitle("자막", 0, 900_000)], hook="제목",
        style=Style(hook_font="Jua-Regular", hook_tilt=True))
    ass = Path(write_ass(spec, tmp_path / "t.ass")).read_text(encoding="utf-8-sig")
    title = next(ln for ln in ass.splitlines() if ln.startswith("Style: Title"))
    assert title.startswith("Style: Title,Jua,")  # 훅 전용 글씨체 (내부 패밀리명)
    assert ",100,100,0,4," in title               # ScaleX,ScaleY,Spacing,Angle=4 (비스듬히)
    default = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default"))
    assert "Pretendard ExtraBold" in default  # 본문은 기본 유지


def test_fetch_fonts_skip_and_installed(tmp_path):
    """네트워크 없이 스킵·목록 로직 검증 (실다운로드는 개발 환경에서 별도 확인됨)."""
    from cutdaejang.tools import fetch_fonts

    assert fetch_fonts.installed(tmp_path) == []  # 빈 폴더 = 미설치
    for fname, _, _ in fetch_fonts.FONTS:  # 받은 것처럼 가짜 TTF(>10KB) 배치
        (tmp_path / fname).write_bytes(b"0" * 20_000)
    r = fetch_fonts.fetch_all(tmp_path)
    # v1.38: 글씨체가 5종 → 10종으로 늘었다. 숫자를 박아 두면 늘릴 때마다 깨진다
    n = len(fetch_fonts.FONTS)
    assert r["got"] == 0 and r["skip"] == n and not r["fail"]  # 있으면 재다운로드 없음
    assert len(fetch_fonts.installed(tmp_path)) == n
    # 🔎 v1.38 — 폰트가 아닌 가짜 파일이라도 «이름표 확인»이 오작동하면 안 된다
    assert r["mismatch"] == [], "읽을 수 없는 파일을 «이름이 틀렸다»고 하면 안 된다"
    assert (tmp_path / "무료글씨체_라이선스.txt").exists()  # OFL 고지 파일
