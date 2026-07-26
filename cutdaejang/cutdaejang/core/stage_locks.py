"""동시 작업 단계 교통정리 (v0.93) — 같은 단계는 한 번에 하나씩.

여러 작업이 동시에 돌 때(v0.90 병렬 큐) 모두가 같은 자원을 나눠 쓰면 전부
기어간다 — TTS·AI 이미지는 같은 API 분당 한도를, 렌더·음성 인식은 같은 CPU
코어를 쪼개 쓰기 때문. 사용자 리포트: "동시 4개인데 0%·5%에서 4분째".

해법: 단계별 전역 락. TTS는 한 작업씩, 렌더도 한 작업씩 — 대신 서로 다른
단계끼리는 겹친다 (A가 렌더하는 동안 B는 목소리 합성). 혼자 돌 때 속도를
지키면서 전체 처리량은 순차보다 좋아진다.
"""

from __future__ import annotations

import functools
import threading

TTS = threading.RLock()      # 목소리 합성 — API 분당 한도 공유 (Gemini·ElevenLabs)
IMAGE = threading.RLock()    # AI 장면 이미지 — API 분당 한도 공유
STT = threading.RLock()      # 음성 인식(Whisper) — CPU 코어 공유
RENDER = threading.RLock()   # ffmpeg 최종 인코딩 — CPU 코어 공유


def guarded(lock: "threading.RLock"):
    """함수 전체를 단계 락으로 감싸는 데코레이터 (RLock — 같은 작업 안 중첩 호출 안전)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*args, **kwargs):
            with lock:
                return fn(*args, **kwargs)
        return wrap
    return deco
