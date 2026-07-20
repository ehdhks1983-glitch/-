"""v0.62 — 롱폼 미세조정(줄바꿈·훅)·키트 롱폼·이전 그림 재사용·대본 배치."""
import json
import re

from cutdaejang.core.render_engine.ass_writer import write_ass
from cutdaejang.spec import AudioClip, Background, Canvas, Subtitle, TimelineSpec


def _spec(canvas, text):
    return TimelineSpec(
        duration_us=5_000_000, canvas=canvas,
        background=Background(type="image", path="bg.png"),
        audio=[AudioClip("s01.m4a", 300_000, 2_000_000)],
        subtitles=[Subtitle(text, 300_000, 2_000_000)],
        hook="상단 제목",
    )


def test_wide_wrap_expands_line_length(tmp_path):
    """가로(16:9)는 한 줄 27자까지 — 세로에서 2줄이던 문장이 가로에선 1줄."""
    text = "가나다라마바사아자차카타파하일이삼"  # 18자 — 세로(16자) 기준 초과
    ass_v = open(write_ass(_spec(Canvas(1080, 1920, 30), text), tmp_path / "v.ass"),
                 encoding="utf-8-sig").read()
    ass_w = open(write_ass(_spec(Canvas(1920, 1080, 30), text), tmp_path / "w.ass"),
                 encoding="utf-8-sig").read()
    line_v = next(ln for ln in ass_v.splitlines() if "가나다라" in ln)
    line_w = next(ln for ln in ass_w.splitlines() if "가나다라" in ln)
    assert "\\N" in line_v      # 세로: 16자 넘어 2줄
    assert "\\N" not in line_w  # 가로: 27자까지 1줄


def test_wide_hook_size_boosted(tmp_path):
    """가로 훅은 높이 비례만으론 작음 → 1.45배 보정."""
    def title_px(ass):
        m = re.search(r"Style: Title,[^,]+,(\d+),", ass)
        return int(m.group(1))

    ass_v = open(write_ass(_spec(Canvas(1080, 1920, 30), "짧은 자막"), tmp_path / "v.ass"),
                 encoding="utf-8-sig").read()
    ass_w = open(write_ass(_spec(Canvas(1920, 1080, 30), "짧은 자막"), tmp_path / "w.ass"),
                 encoding="utf-8-sig").read()
    v, w = title_px(ass_v), title_px(ass_w)
    # 높이 비례(0.5625)만이면 w == round(v*0.5625) — 1.45배 보정으로 그보다 커야 함
    assert w > round(v * 0.5625 * 1.3)
    assert w < v  # 그래도 세로 픽셀보단 작다 (화면 높이가 절반이므로)


def test_upload_kit_stub_longform_has_no_shorts():
    from cutdaejang.core import script_generator as sg

    k = sg.suggest_upload_kit_stub("정리 습관 영상", is_shorts=False)
    s = json.dumps(k, ensure_ascii=False)
    assert "Shorts" not in s and "쇼츠" not in s
    for key in ("titles", "tags", "keywords", "hashtags", "tiktok", "instagram",
                "naverclip", "threads", "category"):
        assert k.get(key), key
    k2 = sg.suggest_upload_kit_stub("정리 습관 영상", is_shorts=True)
    assert "Shorts" in json.dumps(k2, ensure_ascii=False)


def test_reuse_prev_scenes_copies_matching_topic(tmp_path):
    from cutdaejang import presets
    from cutdaejang.gui.webui import _reuse_prev_scenes
    from cutdaejang.utils import ffmpeg as ff

    # 이전 작업: 같은 슬러그, scenes 2장 (1·3번 장면)
    prev = tmp_path / "20260720-100000-정리-습관"
    (prev / "scenes").mkdir(parents=True)
    for n, c in ((1, "red"), (3, "blue")):
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c={c}:s=270x480:d=0.1", "-frames:v", "1",
                str(prev / "scenes" / f"scene_{n:02d}.png")])
    # 다른 주제 폴더는 무시돼야 함
    other = tmp_path / "20260720-110000-다른-주제"
    (other / "scenes").mkdir(parents=True)

    new_id = "20260720-120000-정리-습관"
    got = _reuse_prev_scenes(new_id, str(tmp_path), [0, 1, 2], presets.CANVAS_SHORTS)
    assert got == {0: True, 2: True}  # scene_01→i=0, scene_03→i=2 (i=1은 없음)
    d = tmp_path / new_id / "scenes"
    assert (d / "scene_01.png").exists() and (d / "scene_03.png").exists()
    assert not (d / "scene_02.png").exists()
    w, h = ff.probe_video_size(str(d / "scene_01.png"))
    assert (w, h) == (1080, 1920)  # 현재 캔버스로 정규화

    # 슬러그 없는 잡(스탬프만)은 재사용 안 함
    assert _reuse_prev_scenes("20260720-130000", str(tmp_path), [0],
                              presets.CANVAS_SHORTS) == {}


def test_new_job_id_unique_within_same_second():
    from cutdaejang.core.orchestrator import new_job_id

    ids = [new_job_id("같은 제목") for _ in range(3)]
    assert len(set(ids)) == 3  # 같은 초라도 순번이 붙어 절대 안 겹침
    assert ids[1].startswith(ids[0]) and ids[1].endswith("-1") and ids[2].endswith("-2")
