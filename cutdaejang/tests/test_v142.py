"""v1.42 — 목록 84: ✨ AI 클립이 «되고 있는지» 안 보이던 것.

회원님 42차:
> "AI 클립 눌러서 fal 연동하고 만들었는데, 만들고 있으면 몇 분 남았고
>  로그 상태 같은 게 보여야 할 것 같아. **만드는지 안 만드는지도 모르겠어.**
>  만든 영상은 그리고 어디에?"

돈이 나가는 기능인데 버튼 글자만 「✨ 만드는 중…」이었다 — 멈춘 줄 알고
또 누르면 **또 과금된다.** 조사해 보니 서버는 진행 문구를 계속 만들고
있었는데(`progress_cb → _set_job(note=…)`) **화면이 그걸 버리고 있었다.**
폴링 루프가 완료/실패만 보고 note는 아무 데도 안 띄웠다.

세 물음에 하나씩 답한다:
  ① «만드는지 안 만드는지 모르겠다» → 떠 있는 진행 칸 + 지난 시간
  ② «로그 상태가 보여야» → fal 큐 순번·상태를 그대로 + 📄 로그에도
  ③ «만든 영상은 어디에» → 완성 알림에 파일 경로 (windows\\jobs\\ai_clips\\)
"""

import inspect
import re

from cutdaejang import __version__
from cutdaejang.core import video_gen
from cutdaejang.gui import webui

HTML = webui._apply_links(webui._HTML)
SRC = open(webui.__file__, encoding="utf-8").read()
JS = "\n".join(re.findall(r"<script>(.*?)</script>", HTML, re.S))
POLL = JS.split("async function aiClipGo(")[1].split("\nasync function ")[0]


def test_version():
    assert __version__ == "1.48.0"


# ── ① 만드는지 안 만드는지 ──────────────────────────────────────
def test_there_is_a_visible_progress_box():
    """🔴 버튼 글자 하나로는 부족하다 — 돈이 나가는 동안 떠 있어야 한다."""
    assert 'id="aiClipProg"' in HTML
    assert 'id="aiClipElapsed"' in HTML, "지난 시간"
    assert 'id="aiClipNote"' in HTML, "지금 뭐 하는 중인지"
    seg = HTML.split('id="aiClipProg"')[1][:200]
    assert "position:fixed" in seg, "어느 화면에서 눌렀든 보여야 한다"


def test_the_box_turns_on_when_generation_starts():
    assert "aiClipProgShow(true, '요청을 보내는 중…');" in POLL


def test_the_servers_progress_is_no_longer_thrown_away():
    """🔴 원인 — 서버는 note를 계속 보냈는데 폴링이 완료/실패만 봤다."""
    assert "aiClipProgShow(true, j.note || '만드는 중…', waited);" in POLL


def test_the_box_turns_off_on_every_ending():
    """성공·실패·시간초과 어디서든 꺼져야 한다 — 남으면 «아직 도는 줄» 안다."""
    assert POLL.count("aiClipProgShow(false);") == 3


def test_double_charging_is_still_blocked():
    """멈춘 줄 알고 또 누르는 사고 — 버튼 잠금이 그대로 있어야 한다."""
    assert "btn.disabled = true" in POLL
    assert POLL.count("btn.disabled = false") >= 3


def test_elapsed_time_is_formatted_like_a_clock():
    body = JS.split("function aiClipProgShow(")[1].split("\n}")[0]
    assert "Math.floor(secs / 60)" in body
    assert "String(secs % 60).padStart(2, '0')" in body


# ── ② 로그 상태 ────────────────────────────────────────────────
def test_fal_reports_queue_position_and_elapsed():
    """fal은 «접수 → 큐 대기 → 실행»을 거친다 — 어디쯤인지 말해야 한다."""
    src = inspect.getsource(video_gen._fal)
    assert "queue_position" in src
    assert "대기" in src and "번째" in src
    assert "분" in src and "초 지남" in src
    assert "멈춘 게 아니에요" in src


def test_progress_also_goes_to_the_log_panel():
    """화면을 놓쳐도 📄 로그에서 «왜 오래 걸렸나»를 볼 수 있어야 한다."""
    seg = SRC.split("def _run_gen_clip(")[1].split("\ndef ")[0]
    assert 'logging.getLogger("cutdaejang").info("AI클립 %s", m)' in seg


def test_failure_points_to_the_log():
    assert "「📄 로그」를 펼쳐 보세요" in POLL


# ── ③ 만든 영상은 어디에 ────────────────────────────────────────
def test_the_done_alert_says_where_the_file_is():
    """«어디에?»의 답이 화면에 있어야 한다 — 채팅에서 매번 물으실 수 없다."""
    assert "📁 파일 위치" in POLL
    assert "+ j.clip" in POLL.split("📁 파일 위치")[1][:120]


def test_clips_are_cached_under_ai_clips():
    """경로 규칙이 바뀌면 위 안내가 거짓말이 된다 — 같이 못 박는다."""
    p = video_gen.clip_cache_path("/tmp/wd", "fal", "m", "프롬프트", 5, "720p", "9:16")
    assert p.parent.name == "ai_clips"
    assert p.suffix == ".mp4"
    # 같은 조건 → 같은 파일 (재사용·과금 없음의 근거)
    assert p == video_gen.clip_cache_path("/tmp/wd", "fal", "m", "프롬프트", 5, "720p", "9:16")
    # 비율이 다르면 다른 파일 (v1.25 목록 39-7)
    assert p != video_gen.clip_cache_path("/tmp/wd", "fal", "m", "프롬프트", 5, "720p", "16:9")


# ── 화면이 여전히 성한가 ───────────────────────────────────────
def test_html_is_still_well_formed():
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button", "textarea", "label"):
        assert len(re.findall(rf"<{tag}[\s>]", HTML)) == len(
            re.findall(rf"</{tag}>", HTML)), f"<{tag}> 짝이 안 맞음"
    assert f"(v{__version__})" in HTML
