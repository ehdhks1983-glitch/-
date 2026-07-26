"""v0.93 — 🚦 단계 교통정리(동시 작업 속도) + 🎙 쇼핑 카드 목소리·BGM 동기화."""

import threading
import time

from cutdaejang.core import stage_locks
from cutdaejang.gui import webui


def test_stage_locks_wrap_choke_points():
    """무거운 단계 6곳이 전부 단계 락으로 감싸져 있다 (functools.wraps 표식)."""
    from cutdaejang.core import background_generator, edit_mode, tts_engine
    from cutdaejang.core.render_engine import ffmpeg_composer

    for fn in (tts_engine.synth_with_fallback,
               background_generator.generate_scene_images,
               edit_mode.transcribe_segments, edit_mode.transcribe_segments_timed,
               edit_mode.render_edited, edit_mode.render_from_analysis,
               ffmpeg_composer.compose):
        assert hasattr(fn, "__wrapped__"), fn.__name__
    # 락 4종은 서로 다른 객체 (단계끼리는 겹칠 수 있어야 함)
    locks = {id(stage_locks.TTS), id(stage_locks.IMAGE),
             id(stage_locks.STT), id(stage_locks.RENDER)}
    assert len(locks) == 4


def test_tts_stage_blocks_second_job(tmp_path):
    """다른 스레드가 TTS 단계를 잡고 있으면 두 번째 작업의 TTS는 기다린다."""
    from cutdaejang.core import tts_engine

    order = []
    held = threading.Event()
    release = threading.Event()

    def holder():
        with stage_locks.TTS:
            held.set()
            release.wait(5)
            order.append("A")

    t1 = threading.Thread(target=holder)
    t1.start()
    assert held.wait(5)

    def second_job():
        # 빈 문장 → 제공자 호출 없이 즉시 반환하지만, 락은 지나야 한다
        tts_engine.synth_with_fallback([], ["stub"], tmp_path, {})
        order.append("B")

    t2 = threading.Thread(target=second_job)
    t2.start()
    time.sleep(0.4)
    assert "B" not in order          # A가 잡고 있는 동안 B는 대기
    release.set()
    t1.join(5)
    t2.join(5)
    assert order == ["A", "B"]


def test_guarded_reentrant_same_thread():
    """같은 작업(스레드) 안의 중첩 호출은 막히지 않는다 (RLock)."""
    @stage_locks.guarded(stage_locks.RENDER)
    def outer():
        return inner() + 1

    @stage_locks.guarded(stage_locks.RENDER)
    def inner():
        return 1

    assert outer() == 2


def test_v093_ui_wired():
    html = webui._HTML
    # 🎙 쇼핑 카드 목소리·BGM — 목록이 늦게 와도 poll마다 동기화 (빈 셀렉트 버그 수정)
    assert "window._view === 'shop') initShopCard" in html
    # 상단바 줄바꿈 — 진행·대기 바가 제목을 세로로 찌그러뜨리던 문제
    assert "flex-wrap:wrap" in html.split(".topbar {")[1].split("}")[0]
    assert 'id="jobsBar"' in html and "flex:1 1 100%" in html
