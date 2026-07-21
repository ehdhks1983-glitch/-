"""v0.72 — 스레드 짧은 반말체 + 업로드 키트별 사이트 간편링크 + 인스타 비율 안내.

사용자 요청: (1) 인스타에 쇼츠 올리니 비율이 잘려 보임 → 9:16은 정확, 인스타 피드
4:5 크롭이 원인이라 안내 추가. (2) 스레드는 짧은 반말이 대세인데 존댓말 대화체라
안 맞음 → 반말로. (3) 각 키트 옆에 해당 사이트 업로드 링크.
"""

from cutdaejang.core import script_generator as sg
from cutdaejang.gui import webui


# ── 1) 스레드 프롬프트가 '짧은 반말'을 지시한다 ──────────────────────────
def test_threads_prompt_asks_for_banmal():
    p = sg.UPLOAD_KIT_PROMPT
    assert "반말" in p
    assert "존댓말" in p and "금지" in p          # 존댓말·격식체 금지
    assert "80~150자" in p or "150자" in p        # 짧게


_JONDAE_TAILS = ("요", "요?", "세요", "세요?", "습니다", "ㅂ니다", "어요", "예요")


def _is_banmal(text: str) -> bool:
    """마지막 문장이 존댓말로 안 끝나면 반말로 본다 (대략적 판정)."""
    last = text.strip().rstrip("!?.…").split()[-1] if text.strip() else ""
    return not any(text.rstrip().endswith(t) for t in _JONDAE_TAILS)


# ── 2) 스텁 스레드 문구가 반말 + topic 키를 갖는다 (쇼츠·롱폼 both) ──────────
def test_stub_threads_is_banmal_shorts():
    kit = sg.suggest_upload_kit_stub(hook="설악산 한계령", is_shorts=True)
    th = kit["threads"]
    assert th.get("topic"), "스레드 topic 태그 누락"
    assert "요?" not in th["post"] and "세요" not in th["post"], f"존댓말: {th['post']}"
    assert _is_banmal(th["post"]), f"반말 아님: {th['post']}"


def test_stub_threads_is_banmal_longform():
    kit = sg.suggest_upload_kit_stub(hook="블로그 자동화", is_shorts=False)
    th = kit["threads"]
    assert th.get("topic"), "롱폼 스레드 topic 누락(예전 버그)"
    assert "요?" not in th["post"] and "세요" not in th["post"], f"존댓말: {th['post']}"


# ── 3) 스텁 naver_clip 키 (예전 롱폼에서 naverclip 오타 버그) ───────────────
def test_stub_naver_clip_key_both_branches():
    for shorts in (True, False):
        kit = sg.suggest_upload_kit_stub(hook="x", is_shorts=shorts)
        assert "naver_clip" in kit, f"naver_clip 키 없음 (shorts={shorts})"
        assert "naverclip" not in kit, f"오타 키 naverclip 잔존 (shorts={shorts})"
        assert kit["naver_clip"].get("title"), "네이버 클립 제목 비어있음"


# ── 4) normalize_kit 도 반말 스레드를 통과시킨다 (캡·구조 유지) ─────────────
def test_normalize_keeps_threads_post_and_topic():
    out = sg.normalize_kit({"threads": {"post": "이거 진짜 별거 아님. 너넨 어떰?",
                                        "topic": "꿀팁"}})
    assert out["threads"]["post"] == "이거 진짜 별거 아님. 너넨 어떰?"
    assert out["threads"]["topic"] == "꿀팁"


# ── 5) _kit_text 텍스트 파일에 각 플랫폼 업로드 URL이 들어간다 ──────────────
def test_kit_text_has_upload_urls():
    kit = sg.suggest_upload_kit_stub(hook="테스트", is_shorts=True)
    txt = webui._kit_text(kit, "테스트 영상")
    assert "studio.youtube.com" in txt
    assert "tiktok.com/tiktokstudio/upload" in txt
    assert "instagram.com" in txt
    assert "clipcreators.naver.com" in txt
    assert "threads.com" in txt
    # 인스타 릴스 비율 안내도 텍스트에 포함
    assert "릴스" in txt and "잘려" in txt


# ── 6) 키트 UI(HTML)에 5개 사이트 링크 + 인스타 안내 + 스레드 반말 힌트 ───────
def test_html_has_platform_links_and_notes():
    html = webui._HTML
    for url in ("https://studio.youtube.com",
                "https://www.tiktok.com/tiktokstudio/upload",
                "https://www.instagram.com",
                "https://clipcreators.naver.com",
                "https://www.threads.com"):
        assert url in html, f"업로드 링크 누락: {url}"
    # 새 탭 + 보안 rel
    assert 'target="_blank"' in html and 'rel="noopener"' in html
    # 인스타 비율 안내(릴스로 올리기 + 잘려 보이는 건 정상)
    assert "릴스" in html and "9:16" in html
    # 스레드 힌트가 '짧은 반말'로 바뀜(예전 '대화체' 제거)
    assert "짧은 반말" in html


def test_html_threads_hint_no_longer_daehwache():
    # 스레드 summary 힌트에서 '대화체' 표기가 사라졌는지 (반말로 교체)
    html = webui._HTML
    assert "🧵 스레드" in html
    # '대화체 + 토픽' 조합은 더 이상 없어야 함
    assert "대화체 + 토픽" not in html
