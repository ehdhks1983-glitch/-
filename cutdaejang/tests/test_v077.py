"""v0.77 버그·다듬기 3종 — 제품 배지·즉시 저장, 편집 가로(16:9), 긴 문장 자동 분할."""

import inspect

from cutdaejang.core.script_generator import Script, split_long_sentences
from tests.conftest import requires_ffmpeg


# ── ① 제품 정보 배지 + 해제 + 빈 값 저장 ──────────────────────────


def test_product_badge_markup():
    """생성 폼: 제품이 선택돼 있으면 [생성 시작] 위에 배지 + ✕ 끄기 버튼."""
    from cutdaejang.gui import webui as w

    html = w._HTML
    assert 'id="prodBadge"' in html and 'id="prodBadgeName"' in html
    assert "✕ 제품 끄기" in html
    assert 'onclick="clearGenProduct(event)"' in html
    # 셀렉트를 바꾸면 즉시 저장(+배지 갱신)
    assert 'onchange="onGenProductChange()"' in html
    assert "function updateProductBadge" in html
    assert "function clearGenProduct" in html
    # 페이지 복원·제품 목록 갱신·초기화 각각에서 배지를 다시 그린다
    assert html.count("updateProductBadge()") >= 3
    # 폼 초기화도 제품을 끄고 그 상태를 저장한다
    assert html.count("onGenProductChange()") >= 3


def test_gen_product_empty_value_is_saved(monkeypatch):
    """제품 '없음'(빈 값)도 ui.gen_product=""로 저장 — 옛 제품 부활 방지의 핵심."""
    from cutdaejang import config
    from cutdaejang.gui import webui as w

    captured = {}
    monkeypatch.setattr(w.config, "save_settings",
                        lambda d: captured.update(d) or "mem")
    s = config.load_settings()
    s.setdefault("ui", {})["gen_product"] = "옛제품"
    w._apply_bg_style({"product": ""}, s)
    assert captured.get("ui", {}).get("gen_product") == ""


# ── ② 편집 모드 가로(16:9) ────────────────────────────────────────


def test_quality_canvas_wide():
    from cutdaejang.core import edit_mode as em

    c, _, _, _ = em._quality_canvas("wide", 320, 568, "standard")
    assert (c.w, c.h) == (1920, 1080)
    c2, _, _, _ = em._quality_canvas("shorts", 320, 568, "standard")
    assert (c2.w, c2.h) == (1080, 1920)  # 기존 쇼츠 불변
    c3, _, _, _ = em._quality_canvas("keep", 320, 568, "standard")
    assert (c3.w, c3.h) == (320, 568)    # 기존 원본 유지 불변
    c4, _, _, _ = em._quality_canvas("wide", 320, 568, "ultra")
    assert (c4.w, c4.h) == (3840, 2160)  # 4K 업스케일도 짝수·캡 안


def test_edit_layout_wide_radio():
    from cutdaejang.gui import webui as w

    html = w._HTML
    assert 'name="editLayout" value="wide"' in html
    assert "가로 (16:9)" in html


@requires_ffmpeg
def test_render_edited_wide_e2e(tmp_path):
    """세로 촬영본 → 가로 1920×1080 캔버스(옆은 블러 패드)로 완성."""
    from cutdaejang.core import edit_mode
    from cutdaejang.utils import ffmpeg as ff

    src = tmp_path / "v.mp4"
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=gray:s=180x320:d=3",
            "-f", "lavfi", "-i", "sine=frequency=600:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(src)])
    out = tmp_path / "out.mp4"
    r = edit_mode.render_from_analysis(
        str(src), [], str(out), layout="wide", quality="draft")
    assert r.ok, r.errors
    assert ff.probe_video_size(str(out)) == (1920, 1080)


# ── ③ 긴 문장 자동 분할 안전장치 ──────────────────────────────────


def test_split_long_sentences_basic():
    long = "하나 둘 셋 넷 다섯 여섯 일곱 여덟 아홉 열 열하나 열둘"
    s = Script(title="t", sentences=["짧다", long, "재훅 문장"],
               highlights=["", "여섯", ""], scene_prompts=["a", "b", "c"],
               rehook_idx=2)
    out = split_long_sentences(s, limit=10)
    assert out is not s
    assert all(len(x) <= 10 for x in out.sentences)
    # 글자 하나도 잃지 않는다 (공백 제외 비교)
    assert "".join(out.sentences).replace(" ", "") == \
        "".join(s.sentences).replace(" ", "")
    # 강조어는 그 단어가 든 조각 딱 한 곳에만
    assert out.highlights.count("여섯") == 1
    i = out.highlights.index("여섯")
    assert "여섯" in out.sentences[i]
    # 장면 묘사는 첫 조각에만 (나머지 빈칸은 fill_scene_gaps가 이웃으로 채움)
    assert out.scene_prompts.count("b") == 1
    # 재훅 문장 번호는 새 위치로 재매핑
    assert out.sentences[out.rehook_idx] == "재훅 문장"


def test_split_long_sentences_rehook_on_split_sentence():
    """재훅 문장 자체가 쪼개지면 첫 조각이 재훅(원래 시점 보존)."""
    long = "하나 둘 셋 넷 다섯 여섯 일곱 여덟"
    s = Script(title="t", sentences=["앞", long], highlights=[], rehook_idx=1)
    out = split_long_sentences(s, limit=8)
    assert out.rehook_idx == 1 and out.sentences[1] == out.sentences[out.rehook_idx]
    assert long.startswith(out.sentences[1])


def test_split_long_sentences_noop_returns_same():
    s = Script(title="t", sentences=["짧은 문장", "또 짧다"])
    assert split_long_sentences(s, 32) is s


def test_split_long_sentences_keeps_color_markup():
    """색 마크업([노랑]…[/])이 든 문장은 쌍이 깨질 수 있어 분할하지 않는다."""
    t = "[노랑]가 나 다 라 마 바 사 아 자 차 카 타[/]"
    s = Script(title="t", sentences=[t])
    assert split_long_sentences(s, 10) is s


def test_split_long_sentences_no_space_force():
    t = "가나다라마바사아자차카타파하가나다라"
    out = split_long_sentences(Script(title="", sentences=[t]), 8)
    assert all(len(x) <= 8 for x in out.sentences)
    assert "".join(out.sentences) == t


def test_run_job_wires_safety_split():
    """run_job이 TTS 전에 안전장치를 실제로 거친다 (배선 확인)."""
    from cutdaejang.core import orchestrator

    src = inspect.getsource(orchestrator.run_job)
    assert "split_long_sentences" in src
    assert src.index("split_long_sentences") < src.index("synth_with_fallback")
