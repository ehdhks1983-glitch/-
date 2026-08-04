"""v1.23 — 🔊 미리듣기 전 카드 + 🎨 감성 테마 6종 + 🎵 BGM 확장 + ✨AI 클립 자리 안내.

회원님 지적 4건 (목록 35~38):
35. "블로그 글로 영상만들기인데 나래이션 목소리 듣는곳이없어 아까도 재차말했었어"
    — v1.21에서 쇼핑 카드에만 넣은 게 실수였다. 목소리 셀렉트가 있는 모든 카드
    (블로그 wl · 구간 sec)에 [🔊 미리듣기]를 단다.
36. "무료BGM도 무료로 늘릴수있다면 더늘려줘" — 같은 CC BY 라이브러리에서 +28곡.
37. "감성테마도 다양성이필요해" — 4종 → 10종. 조합 값은 반드시 실존하는
    자막 스타일·톤이어야 한다(없는 값이면 applyTheme가 조용히 건너뛰어 유령 테마가 됨).
38. "AI영상제작…배치가 제대로 안되어있는거같은데" — 사진을 쓰는 카드 3곳에
    [✨ AI 클립]이 어디 있는지·사진 흐름 자동 삽입은 준비 중임을 정직하게 안내.
"""

import re

from cutdaejang import __version__
from cutdaejang.gui import webui
from cutdaejang.tools import fetch_bgm as fb


def test_version():
    assert __version__ == "1.38.0"


# ── 35. 나레이션 미리듣기 — 목소리 고르는 곳 어디에나 ─────────────────
def test_preview_button_on_every_voice_card():
    html = webui._HTML
    # 블로그(wl)·구간(sec)·쇼핑(shop)은 공용 미리듣기를 셀렉트 id로 재사용
    for sel in ("wlVoiceSel", "secVoiceSel", "shopVoiceSel"):
        assert html.count(f"previewNarrVoice(event,'{sel}')") == 1, sel
    # 편집 폼(narr)·AI 생성 폼(voiceSel)은 기존 전용 버튼이 그대로 있어야 한다
    assert "previewNarrVoice(event)" in html
    assert "previewVoice(event)" in html


# ── 37. 감성 테마 10종 — 모든 카드에 배선 + 조합 값 실존 보증 ─────────
def test_theme_selects_offer_ten_themes():
    html = webui._HTML
    sels = re.findall(r'<select id="(\w+ThemeSel)"[^>]*>(.*?)</select>', html, re.S)
    assert {s[0] for s in sels} == {"editThemeSel", "genThemeSel", "wlThemeSel",
                                    "secThemeSel", "shopThemeSel"}
    for sid, body in sels:
        for key in ("insta", "tiktok", "youtube", "cinema",
                    "news", "retro", "cozy", "kids", "luxury", "docu"):
            assert f'value="{key}"' in body, f"{sid}에 {key} 테마가 없어요"


def test_theme_values_actually_exist_as_options():
    """테마가 가리키는 자막 스타일·톤이 실제 옵션에 없으면 조용히 무시돼
    '눌러도 아무 일 없는' 유령 테마가 된다 — 값 실존을 코드로 보증."""
    html = webui._HTML
    themes = re.search(r"const THEMES = \{(.*?)\n\};", html, re.S).group(1)
    pairs = re.findall(r"sub_style: '([^']+)', tone: '([^']+)'", themes)
    assert len(pairs) == 10
    gen_sub = re.search(r'id="genSubStyleSel".*?</select>', html, re.S).group(0)
    gen_tone = re.search(r'id="genToneSel".*?</select>', html, re.S).group(0)
    for s, t in pairs:
        assert f'value="{s}"' in gen_sub, f"자막 스타일이 실존하지 않아요: {s}"
        assert f'value="{t}"' in gen_tone, f"톤이 실존하지 않아요: {t}"


# ── 36. 무료 BGM 확장 ────────────────────────────────────────────
def test_bgm_tracks_expanded_and_unique():
    assert len(fb.TRACKS) >= 80                      # 54 → 82곡
    assert len(set(fb.TRACKS)) == len(fb.TRACKS)     # 중복 등록 없음
    titles = [t for _, t in fb.TRACKS]
    assert len(set(titles)) == len(titles)           # 제목 중복도 없음 (파일명 충돌 방지)
    for _, t in fb.TRACKS:
        u = fb.track_url(t)
        assert u.startswith("https://incompetech.com/") and " " not in u


def test_bgm_fetch_skips_failed_tracks(tmp_path):
    """곡 이름이 사이트에서 바뀌어도 그 곡만 실패로 남고 나머지는 정상 —
    목록이 커져도(82곡) 한 곡 때문에 전체가 멈추지 않는다."""
    calls = []

    def fake_fetch(url, dest, timeout=1.0):
        calls.append(url)
        if "Hyperfun" in url:                        # 새로 추가한 곡 하나가 실패해도
            return False
        dest.write_bytes(b"x" * 200_000)
        return True

    ok, fail = fb.main(bgm_dir=tmp_path, fetch_fn=fake_fetch)
    assert fail == ["Hyperfun"]
    assert len(ok) == len(fb.TRACKS) - 1
    assert (tmp_path / fb.CREDIT_FILE).is_file()     # 성공 곡 크레딧은 그대로 생성


# ── 38. ✨ AI 클립 자리 안내 — 사진 쓰는 카드 3곳 ─────────────────────
def test_ai_clip_guidance_on_photo_cards():
    html = webui._HTML
    # 사진 흐름(photoBlock)·블로그(wl)·쇼핑(shop) 3곳 모두에 같은 안내
    assert html.count("✨ 사진이 부족한 장면은") == 3
    # v1.36 (목록 72 ③): «자동으로 끼워 넣는 기능은 준비 중»이 이제 «된다»로 바뀌었다.
    #   세 화면 모두 옆에 [✨ AI 영상 넣기] 버튼이 붙었다.
    # ⚠ «준비 중»으로 세면 안 된다 — 렌더 진행 문구("영상 렌더링 준비 중…")가 걸린다.
    assert html.count("자동으로 끼워 넣는 기능은 준비 중") == 0
    assert html.count("addAiClipPhoto(event,") == 3
    # 안내가 가리키는 [✨ AI 클립] 버튼은 구간 카드에 실재한다
    assert "aiClipOpen" in html
