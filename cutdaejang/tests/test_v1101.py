"""v1.10.1 — 자연 발화, 내레이션-자막 단일 시간표, 완료 영상 부분 재편집."""

import inspect

from cutdaejang import __version__
from cutdaejang.core import script_generator, tts_engine
from cutdaejang.gui import webui


def test_soft_caption_wrap_does_not_split_spoken_sentence():
    text = "먼저 사람이 하는\n업무를 하는 거였습니다"

    assert script_generator.narration_units(text) == [
        "먼저 사람이 하는 업무를 하는 거였습니다"
    ]


def test_real_sentence_boundaries_are_kept_without_breaking_decimals():
    text = (
        "첫 번째 문장입니다\n"
        "가격은 1.5배입니다. 다음 문장입니다.\n\n"
        "마지막 문장이에요"
    )

    assert script_generator.narration_units(text) == [
        "첫 번째 문장입니다",
        "가격은 1.5배입니다.",
        "다음 문장입니다.",
        "마지막 문장이에요",
    ]


def test_longform_continuity_default_can_hold_forty_short_sentences():
    lines = [f"{i}번째 짧은 문장입니다." for i in range(40)]

    assert tts_engine.CONTINUITY_MAX_SENTENCES == 40
    assert tts_engine.continuity_blocks(lines) == [(0, 40)]


def test_sections_use_one_timeline_for_final_voice_and_subtitles():
    body = inspect.getsource(webui._run_sections)

    assert "narration_units" in body
    assert "split_long_sentences" not in body
    assert "bed3-final-sync" in body
    assert "cut, [], str(job_dir" in body
    assert "all_clips, abs_subs" in body
    # v1.13: 최종 자막 = abs_subs(내레이션) + cap_subs(무낭독 화면 자막 카드).
    # 음성 베드는 여전히 abs_subs만 — 한 타임라인이 음성·자막 공통 기준이다.
    assert "final_subs = sorted(abs_subs + cap_subs" in body
    assert "final, final_subs, synced" in body
    assert body.index("concat_videos(") < body.index("final, final_subs, synced")


def test_done_edit_button_reopens_section_project():
    assert __version__ == "1.28.1"
    html = webui._HTML

    for token in (
        'id="doneEditBtn"',
        "function editDoneVideo",
        "job.mode === 'sections' || !!job.chapters",
        "reEditSections(job.id || currentJob)",
        "✏ 오류 구간만 고치기",
        "setSel('secQualitySel', d.quality)",
        "$('secHook').value = d.hook || ''",
    ):
        assert token in html
