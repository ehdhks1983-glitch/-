"""v1.14 — 🤖 AI 영상 만들기 전체 검토 3종 (회원님 영상 리포트 18·19·20).

릴스 30초 영상 2편을 프레임 단위로 분석해 확정한 원인:
  ⑱ 줄바꿈 없는 직접 대본 → "1문장" → 안전분할이 단어 자리에서 절단
     (나레이션 운율 붕괴·자막 마디·카드 과다·장면 1장) → 문장부호 우선 분할
  ⑲ 장면 그림 「내가 직접」 + 자동 실행 → 무안내 단일 배경 → 안내 노트
  ⑳ 위아래 띠 훅: \\N 개행이 이스케이프에 무력화돼 화면에 글자로 노출(재현됨)
     → 나눔 먼저 확정, 조각별 이스케이프
"""

import pathlib
import tempfile
from dataclasses import replace

from cutdaejang import __version__
from cutdaejang.core.script_generator import Script, split_long_sentences
from cutdaejang.core.render_engine.ass_writer import write_ass
from cutdaejang.spec import Background, Canvas, Style, Subtitle, TimelineSpec

PARA = ("직원 여섯 명을 채용했습니다. 월급은 0원입니다. 농담 같죠? 화면 보세요. "
        "키워드만 넣으면 글을 쓰고, 파트너스 링크에 공정위 문구까지 자동. "
        "검수 통과한 글만 올려서 계정도 지킵니다. 이게 전부 한 세트. "
        "자는 동안에도 일합니다. 얼리어답터 채용, 곧 마감.")


def test_version():
    assert __version__ == "1.35.0"


# ── ⑱ 문단째 붙여넣은 대본 → 문장부호에서 먼저 나눈다 ────────────
def test_paragraph_splits_at_sentence_punct():
    out = split_long_sentences(Script(title="t", sentences=[PARA]), limit=32)
    assert len(out.sentences) >= 9
    assert out.sentences[0] == "직원 여섯 명을 채용했습니다."
    assert "월급은 0원입니다." in out.sentences
    assert "농담 같죠?" in out.sentences          # 마디 "…입니다. 농담"이 아니라 문장
    # 어떤 조각도 자막 2줄 한도를 넘지 않는다 + 글자 손실 없음
    assert all(len(s) <= 32 for s in out.sentences)
    assert "".join(out.sentences).replace(" ", "") == PARA.replace(" ", "")


def test_paragraph_split_keeps_highlight_and_rehook():
    s = Script(title="t", sentences=["앞 문장.", PARA],
               highlights=["", "0원"], scene_prompts=["a", "b"], rehook_idx=1)
    out = split_long_sentences(s, limit=32)
    assert out.rehook_idx == 1                    # 재훅 = 문단의 첫 조각 위치
    i = out.highlights.index("0원")
    assert "0원" in out.sentences[i]              # 강조어는 그 문장 조각에
    assert out.scene_prompts.count("b") == 1      # 장면 묘사는 첫 조각에만


def test_markup_sentence_still_not_split():
    long_marked = "[노랑]" + "가나다라 " * 12 + "강조[/노랑] 끝입니다."
    out = split_long_sentences(Script(title="t", sentences=[long_marked]), limit=32)
    assert out.sentences == [long_marked]         # 색 마크업 쌍 보존 (v0.77 규칙 유지)


def test_no_punct_still_word_chunks():
    long = "하나 둘 셋 넷 다섯 여섯 일곱 여덟 아홉 열 열하나 열둘"
    out = split_long_sentences(Script(title="t", sentences=[long]), limit=10)
    assert len(out.sentences) > 1 and all(len(s) <= 10 for s in out.sentences)


# ── ⑳ 위아래 띠 훅 — \N이 코드로 살아 있어야 한다 ────────────────
def _frame_ass(hook: str) -> str:
    spec = TimelineSpec(canvas=Canvas(w=1080, h=1920, fps=30),
                        style=replace(Style(), hook_style="위아래 띠"), hook=hook,
                        duration_us=30_000_000, background=Background(),
                        subtitles=[Subtitle(text="자막", start_us=0, end_us=3_000_000)])
    out = pathlib.Path(tempfile.mkdtemp()) / "h.ass"
    write_ass(spec, out)
    return out.read_text(encoding="utf-8")


def test_frame_band_hook_user_newline_is_real_break():
    t = _frame_ass("직원 6명 채용? \n월급 0원으로 가능합니다.")
    assert "​N" not in t                     # \N 리터럴 노출(U+200B 무력화) 금지
    title = next(l for l in t.splitlines() if "월급" in l)
    assert "채용?\\N월급" in title.replace("{\\1c&HFFFFFF&}", "")  # 사용자 줄바꿈 위치
    assert "6명" in title                          # 숫자 강조는 조각별로 그대로


def test_frame_band_hook_autowrap_still_functional():
    t = _frame_ass("여덟 글자씩 나뉘는 아주 긴 제목입니다")
    assert "​N" not in t
    assert any("\\N" in l for l in t.splitlines() if "제목" in l)  # 자동 2줄도 진짜 개행


# ── ⑲ 「내가 직접」+자동 실행 안내 배선 ──────────────────────────
def test_manual_scene_mode_note_wired():
    src = open("cutdaejang/core/orchestrator.py", encoding="utf-8").read()
    assert "「내가 직접」이라 배경을 한 장으로" in src
    body = src.split("「내가 직접」이라 배경을 한 장으로")[0][-700:]
    assert 'scene_mode == "manual"' in body and "not scene_images" in body
    assert "검토 (대본 확인 후)" in src           # 화면의 실제 라벨 그대로 안내
