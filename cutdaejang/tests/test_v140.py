"""v1.40 — 목록 82: 「여러 쇼츠로 나누기」가 «그냥 자르기»였던 것.

회원님 40차:
> "롱폼을 쇼츠로 생성할 때 여러 개 생성하면 그냥 줄여서 쇼츠로 여러 개
>  나오는 거 같은데, 1개 할 때는 하이라이트만 잘 추출해서 만들어지는 게
>  맞는지 확인"

**확인해 보니 회원님 말이 맞았다.**

| | 지금까지 |
|---|---|
| 1개 | ✅ 핵심 선별 O (완전 자동은 자동, 검토 화면은 [✨ AI 핵심 추천]을 눌러야) |
| 여러 개 | ❌ `split_into_clips`가 자막을 «순서대로» 묶기만 — 어디가 좋은지 안 봄 |

74번 조사에서 «AI가 하이라이트를 찾아 편집 — 이미 있다»고 적었는데
그건 **«1개일 때만»**이었다. 그때 내가 덜 봤다.

이 판에서 «좋은 대목 N군데»를 골라 각각 쇼츠로 만드는 길을 더한다.
순서대로 방식은 **없애지 않는다** — 강의·인터뷰처럼 전부 쓰고 싶은 경우가 있다.
"""

import re

import pytest

from cutdaejang import __version__
from cutdaejang.core import script_generator as sg
from cutdaejang.core.edit_mode import Subtitle, split_into_clips
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))

FILLER = "그리고 이어서 설명을 조금 더 드리자면 이런 부분도 있습니다"
HOOKS = {8: "그런데 여기서 진짜 놀라운 반전이 있습니다 무려 3배나 차이가 났어요?",
         21: "이 방법을 쓰면 비용이 50% 줄어듭니다 진짜일까요?",
         34: "결론은 이겁니다 딱 2가지만 기억하세요!"}


def _long(n=40, sec=4):
    return [{"text": HOOKS.get(i, FILLER),
             "start_us": i * sec * 1_000_000,
             "end_us": (i + 1) * sec * 1_000_000} for i in range(n)]


def test_version():
    assert __version__ == "1.51.0"


# ══ 지금까지가 «그냥 자르기»였다는 것부터 못 박는다 ═══════════════
def test_the_old_way_really_was_just_chopping():
    """이걸 못 박아 둬야 «고쳤다»는 말이 뜻을 가진다."""
    subs = [Subtitle(text=s["text"], start_us=s["start_us"], end_us=s["end_us"])
            for s in _long()]
    groups = split_into_clips(subs, target_sec=30)
    flat = [i for g in groups for i in g]
    assert flat == list(range(len(subs))), "순서대로 전부 쓰는 게 이 함수의 뜻이다"
    assert groups[0][0] == 0, "첫 조각은 언제나 영상 맨 앞"


# ══ 새 방식 — 좋은 대목만 ═════════════════════════════════════════
def test_it_finds_the_hooks_not_the_beginning():
    """🔴 요점 — 훅이 8·21·34번에 있으면 거기를 찾아야 한다."""
    r = sg.suggest_multi_highlights_heuristic(_long(), target_sec=30, n=3)
    clips = r["clips"]
    assert len(clips) == 3, clips
    found = {h for c in clips for h in HOOKS if h in c["keep"]}
    assert found == set(HOOKS), f"놓친 훅: {set(HOOKS) - found}"


def test_the_clips_never_overlap():
    """같은 대목이 두 쇼츠에 들어가면 «다른 영상»이 아니다."""
    r = sg.suggest_multi_highlights_heuristic(_long(60), target_sec=30, n=4)
    flat = [i for c in r["clips"] for i in c["keep"]]
    assert len(flat) == len(set(flat)), "쇼츠끼리 겹쳤다"


def test_it_throws_the_boring_parts_away():
    """전부 쓰면 그건 그냥 자르기다 — 버리는 게 있어야 «골랐다»."""
    subs = _long(60)
    r = sg.suggest_multi_highlights_heuristic(subs, target_sec=30, n=3)
    used = sum(len(c["keep"]) for c in r["clips"])
    assert used < len(subs) * 0.8, f"{len(subs)}줄 중 {used}줄 — 거의 다 썼다"


def test_each_clip_is_one_continuous_stretch():
    """쇼츠 하나는 «이어지는 이야기»여야 혼자 봐도 말이 된다."""
    r = sg.suggest_multi_highlights_heuristic(_long(), target_sec=30, n=3)
    for c in r["clips"]:
        k = c["keep"]
        assert k == sorted(k)
        assert k[-1] - k[0] == len(k) - 1, f"중간이 비었다: {k}"


def test_clips_come_out_in_video_order():
    """쇼츠 1·2·3이 영상 순서와 다르면 회원님이 헷갈린다."""
    r = sg.suggest_multi_highlights_heuristic(_long(60), target_sec=25, n=4)
    firsts = [c["keep"][0] for c in r["clips"]]
    assert firsts == sorted(firsts), firsts


@pytest.mark.parametrize("subs,n", [([], 3), (_long(3), 3), (_long(40), 1)])
def test_it_does_not_crash_on_odd_input(subs, n):
    r = sg.suggest_multi_highlights_heuristic(subs, target_sec=30, n=n)
    assert isinstance(r.get("clips"), list)
    for c in r["clips"]:
        assert len(c["keep"]) >= 2, "한 문장짜리 쇼츠는 의미가 없다"


def test_asking_for_more_than_exists_just_gives_fewer():
    """20군데를 달라 해도 없으면 없는 대로 — 억지로 채우면 쓰레기가 나온다."""
    r = sg.suggest_multi_highlights_heuristic(_long(12), target_sec=30, n=20)
    assert 0 < len(r["clips"]) <= 20


def test_the_reason_is_shown_in_korean():
    r = sg.suggest_multi_highlights_heuristic(_long(), target_sec=30, n=3)
    assert "후킹" in r["reason"] and "제미나이" in r["reason"]


# ══ AI 쪽 — 게으른 답을 걸러내는가 ═══════════════════════════════
def test_the_ai_answer_is_cleaned_up():
    """번호가 범위를 넘거나 겹쳐 오면 그대로 쓰면 안 된다."""
    subs = _long(20)
    raw = [{"keep": [0, 1, 2, 999, -3], "title": "가"},
           {"keep": [2, 3, 4, 5], "title": "나"},      # 2는 앞에서 이미 씀
           {"keep": [7], "title": "다"}]               # 한 줄짜리 → 버림
    out = sg._clip_groups_sane(raw, subs, want=5)
    flat = [i for g in out for i in g["keep"]]
    assert all(0 <= i < len(subs) for i in flat), flat
    assert len(flat) == len(set(flat)), "겹침을 안 걸렀다"
    assert all(len(g["keep"]) >= 2 for g in out)


def test_the_ai_cannot_just_split_from_the_front():
    """«앞에서부터 N등분»은 그냥 자르기다 — 실패로 보고 점수 방식으로 넘긴다."""
    subs = _long(20)
    lazy = {"clips": [{"keep": [0, 1, 2, 3]}, {"keep": [4, 5, 6, 7]}]}
    groups = sg._clip_groups_sane(lazy["clips"], subs, want=2)
    flat = [i for g in groups for i in g["keep"]]
    assert flat == list(range(8)), "이 모양이 «게으른 답»이다"
    # 실제 가드는 suggest_multi_highlights 안에 있다 (네트워크 없이 문자열로 확인)
    body = open(sg.__file__, encoding="utf-8").read()
    seg = body.split("def suggest_multi_highlights(")[1].split("\ndef ")[0]
    assert "flat == list(range(len(flat)))" in seg
    assert "ScriptError" in seg


def test_the_prompt_forbids_the_lazy_answer():
    for must in ("서로 다른 쇼츠", "겹쳐 쓰지 마라", "등분하지 마라",
                 "적게 줘도 된다", "완결된 이야기"):
        assert must in sg.MULTI_HL_PROMPT, must


# ══ 만드는 경로에 실제로 연결됐는가 ══════════════════════════════
def test_the_split_job_can_pick_the_best_parts():
    body = SRC.split("def _do_edit_split(")[1].split("\ndef ")[0]
    assert 'mode: str = "seq"' in body, "옛 동작이 기본이어야 부르는 쪽이 안 깨진다"
    assert 'if mode == "best" and subs:' in body
    assert "sg.suggest_multi_highlights(" in body
    assert "sg.suggest_multi_highlights_heuristic(" in body, "키 없어도 되게"


def test_it_says_out_loud_what_it_did():
    """골라낸 건지 그냥 자른 건지 모르면 회원님이 확인할 방법이 없다."""
    body = SRC.split("def _do_edit_split(")[1].split("\ndef ")[0]
    assert "«좋은 대목»" in body and "줄 사용" in body
    assert "고를 만한 대목을 못 찾아 순서대로 나눴어요" in body, "되돌아갔으면 말해야 한다"


def test_the_api_takes_the_choice():
    api = SRC.split('elif path == "/api/edit_split":')[1].split("elif path ==")[0]
    assert 'split_mode = "best" if params.get("mode") == "best" else "seq"' in api
    assert "n_clips" in api
    assert "_apply_keys(params)" in api, "제미나이 키가 전달돼야 AI로 고른다"


def test_the_screen_lets_you_choose():
    assert 'id="splitMode"' in HTML and 'id="splitCount"' in HTML
    assert "✨ 핵심만 골라 여러 개" in HTML
    assert "⏱ 처음부터 순서대로 나누기" in HTML
    body = JS.split("async function renderSplit(")[1].split("\n}")[0]
    assert "n_clips:nClips" in body and "mode," in body


def test_the_old_way_is_still_there():
    """강의·인터뷰처럼 «전부 다» 쓰고 싶은 경우가 있다 — 없애면 안 된다."""
    assert 'value="seq"' in HTML
    body = SRC.split("def _do_edit_split(")[1].split("\ndef ")[0]
    # ①「순서대로」를 고른 경우 ②「핵심만」인데 고를 게 없어 되돌아간 경우
    assert body.count("edit_mode.split_into_clips(subs, target_sec=target_sec)") == 2
    assert "else:\n            groups = edit_mode.split_into_clips" in body


def test_the_count_box_hides_when_it_cannot_be_used():
    """순서대로는 «길이»로 개수가 정해진다 — 칸이 보이면 거짓말이다."""
    body = JS.split("function applySplitMode(){")[1].split("\n}")[0]
    assert "splitCountBox" in body and "splitCount" in body
    assert "classList.toggle('hidden', !best)" in body
    assert "applySplitMode();" in JS.split("initTrimBand();")[1][:200]


def test_the_confirm_says_what_will_happen():
    """«지루한 부분은 버려요»를 안 적으면 버려진 걸 나중에 알고 놀란다."""
    body = JS.split("async function renderSplit(")[1].split("\n}")[0]
    assert "지루한 부분은 버려요" in body
    assert "버리는 부분 없이 전부 쇼츠가 돼요" in body


# ══ 화면이 여전히 성한가 ═══════════════════════════════════════
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
