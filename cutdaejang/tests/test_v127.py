"""v1.27 — 🏃 말 속도 · 🔗 나레이션 끊김 뿌리 뽑기 · ✏ 부분 수정.

회원님 21차 리포트(2026-08-02, 완성 영상 화면 + mp4 2개):
> "목소리 톤 같은 게 너무 느려. 그래서 편집을 누르면 다시 다 넣어야 하는데
>  부분 편집 기능이 있어야 할 것 같아. 나레이션이 맘에 안 들면 나레이션만 변경,
>  속도가 맘에 안 들면 속도 조절, 사진이 맘에 안 들면 사진…"

올려주신 mp4 2개를 20ms 간격 RMS로 재어 본 결과:
· A영상 = 문장 사이 공백 11군데가 전부 440~450ms, B영상 = 9군데가 320~340ms.
  길이가 자로 잰 듯 똑같아 **프로그램이 넣은 침묵**이 확실했다(BGM 없이 -120dB).
· 자막을 태워 읽어 보니 원인이 나왔다 — AI가 **마침표를 찍은 연결 어미**로 줄을
  끝낸다. "…궁금증이 커지고 있고요." "…고척돔에 등장했는데요."
  기존 `_ends_sentence`는 마지막 글자가 '.'이면 문장 끝으로 봐서, 문장 한가운데에
  종결 억양 + 침묵이 들어갔다.
· 게다가 v1.24에서 넣은 `joins`(같은 문장은 붙이기)가 freeze/loop 경로에만 있어,
  영상 길이에 맞추는 기본 경로에서는 아예 적용되지 않고 있었다.

이 파일은 그 세 가지가 실제로 고쳐졌는지를 못 박는다.
"""

import dataclasses
import json
import re
from pathlib import Path

import pytest

from cutdaejang import __version__
from cutdaejang import config
from cutdaejang.core import edit_mode as em
from cutdaejang.core.tts_engine import _speed_filter
from cutdaejang.gui import webui
from cutdaejang.spec import Subtitle

ROOT = Path(__file__).resolve().parents[1]


def test_version():
    assert __version__ == "1.48.0"


# ══ ① 🔗 나레이션 끊김 — 마침표가 있어도 이어지는 말 ═══════════════
# 회원님이 올려주신 A영상 자막에서 그대로 읽어낸 줄들 (마침표까지 원문 그대로)
REAL_CONNECTIVE = [
    "그 이유에 대한 궁금증이 커지고 있고요.",
    "게다가 맷 데이먼 씨가 고척돔에 등장했는데요.",
    "특히 밴쿠버전에서는요.",
    "세금을 냈지만요.",
]
REAL_COMPLETE = [
    "배우 김빈우 씨가 결국 한국을 떠난다고 해요.",
    "오늘은 이 제품을 소개할게요.",
    "가격은 만 원입니다.",
    "정말 좋아요!",
    "어떻게 생각하세요?",
    "지금 바로 확인해 보세요.",
]


@pytest.mark.parametrize("line", REAL_CONNECTIVE)
def test_connective_line_is_not_a_sentence_end(line):
    """마침표가 찍혀 있어도 뒷말로 이어지는 줄 = 아직 문장이 안 끝났다."""
    assert em._ends_connective(line) is True
    assert em._ends_sentence(line) is False, f"여기서 끊기면 안 됨: {line}"


@pytest.mark.parametrize("line", REAL_COMPLETE)
def test_normal_sentence_still_ends(line):
    """오탐 금지 — 멀쩡히 끝난 문장까지 이어 붙이면 숨 쉴 곳이 사라진다."""
    assert em._ends_connective(line) is False
    assert em._ends_sentence(line) is True, f"여기는 끊겨야 함: {line}"


def test_short_line_is_not_treated_as_connective():
    """두 글자 이하는 판단 근거가 부족 — 억지로 이어 붙이지 않는다."""
    assert em._ends_connective("고요.") is False
    assert em._ends_connective("") is False


def test_real_script_now_groups_into_one_breath():
    """A영상과 같은 구성(연결 어미 4줄 섞임)이면 한 호흡으로 묶인다.

    수정 전에는 아홉 줄이 전부 따로 놀아 묶이는 자리가 0곳이었다.
    """
    lines = [
        "배우 김빈우 씨가 결국 한국을 떠난다고 해요.",      # 완결
        "그 이유에 대한 궁금증이 커지고 있고요.",            # 연결 ⬅
        "게다가 맷 데이먼 씨가 고척돔에 등장했는데요.",      # 연결 ⬅
        "팬들의 반응이 뜨거웠습니다.",                        # 완결
        "특히 밴쿠버전에서는요.",                              # 연결 ⬅
        "관중이 가득 들어찼어요.",                            # 완결
        "무려 4경기",                                          # 구두점 없음 ⬅
        "연속 매진이었습니다.",                                # 완결
        "정말 대단하지 않나요?",                               # 완결
    ]
    units = em.group_sentence_units(lines)
    joined = sum(len(g) - 1 for g in units)
    assert joined >= 4, f"이어 붙는 자리가 너무 적음: {units}"
    # 연결 어미 줄은 반드시 다음 줄과 같은 묶음에 들어간다
    for idx in (1, 2, 4, 6):
        grp = next(g for g in units if idx in g)
        assert idx + 1 in grp, f"{idx}번 줄이 혼자 떨어짐: {units}"


def test_punctuationless_script_is_left_alone():
    """음성 인식 자막처럼 구두점이 원래 없는 대본은 묶지 않는다 (안전장치)."""
    lines = ["오늘은 라면을 끓여요", "물을 붓고", "면을 넣고", "삼 분 기다려요"]
    assert em.group_sentence_units(lines) == [[0], [1], [2], [3]]


def test_ai_generate_path_also_groups_sentences():
    """🔴 v1.24의 더 큰 구멍: 문장 묶기가 **편집 모드에만** 들어가 있었다.

    회원님이 쇼핑·블로그 쇼츠를 만드는 「AI 영상 만들기」는 orchestrator를 타는데,
    거기서는 줄마다 따로 합성하고 build_spec이 줄 사이에 무조건 간격을 넣었다.
    """
    src = (ROOT / "cutdaejang/core/orchestrator.py").read_text(encoding="utf-8")
    assert "edit_mode.group_sentence_units(tts_texts)" in src
    assert "edit_mode.split_clip_by_chars(" in src
    assert "joins=narr_joins" in src
    # 분할이 실패해도 그 문장만 예전 방식으로 돌아가 영상이 안 깨진다
    body = src.split("units = edit_mode.group_sentence_units")[1][:2000]
    assert "narr_joins.extend([False] * len(u))" in body


def test_build_spec_zero_gap_where_joined(tmp_path):
    """붙이기로 한 자리는 간격 0, 나머지는 그대로 — 길이 계산도 맞아야 한다."""
    from cutdaejang.core import timeline_calculator as tc
    from cutdaejang.spec import Background, Style
    from cutdaejang.utils import ffmpeg as ff

    paths = []
    for i in range(4):
        p = tmp_path / f"c{i}.wav"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1.0", str(p)])
        paths.append(str(p))
    sents = ["첫 줄이고요", "이어지는 둘째 줄입니다.", "셋째 문장이에요.", "넷째 문장입니다."]
    bg = Background(type="color", color="#101020")

    def gaps(sp):
        return [sp.audio[i + 1].start_us - sp.audio[i].end_us
                for i in range(len(sp.audio) - 1)]

    plain = tc.build_spec(sents, paths, bg, Style(),
                          opts=tc.TimelineOptions(gap_us=220_000))
    assert gaps(plain) == [220_000] * 3          # 예전 동작 그대로

    j0 = tc.build_spec(sents, paths, bg, Style(),
                       opts=tc.TimelineOptions(gap_us=220_000,
                                               joins=[True, False, False]))
    assert gaps(j0) == [0, 220_000, 220_000]
    assert j0.duration_us == plain.duration_us - 220_000

    # 마지막 경계를 붙여도 전체 길이가 어긋나지 않는다 (tail 계산 주의)
    jlast = tc.build_spec(sents, paths, bg, Style(),
                          opts=tc.TimelineOptions(gap_us=220_000,
                                                  joins=[False, False, True]))
    assert gaps(jlast) == [220_000, 220_000, 0]
    assert jlast.duration_us == plain.duration_us - 220_000

    # ⏱ 길이 맞추기는 남은 경계로만 늘린다 — 붙인 자리는 안 벌어진다
    paced = tc.build_spec(sents, paths, bg, Style(),
                          opts=tc.TimelineOptions(gap_us=220_000,
                                                  pace_to_us=8_000_000,
                                                  joins=[True, False, False]))
    g = gaps(paced)
    assert g[0] == 0
    assert g[1] == g[2] > 220_000
    assert abs(paced.duration_us - 8_000_000) < 300_000


def test_sentence_gap_default_is_300ms():
    """문장 사이 기본 쉼.

    v1.27에서 350ms → 300ms로 줄였는데, v1.31에서 그 300ms가 «장부상의 값»이지
    «들리는 값»이 아니었다는 게 드러났다(클립 앞뒤 50ms씩이 더해져 실제 400ms).
    이제 진짜로 들리는 값이라 AI 생성 경로와 같은 250ms로 맞췄다 — 목록 61.
    """
    src = (ROOT / "cutdaejang/core/edit_mode.py").read_text(encoding="utf-8")
    assert "natural_gap = 250_000 if gap_us is None" in src
    assert "natural_gap = 350_000" not in src
    assert "natural_gap = 300_000" not in src
    # 설정 파일에 안 쓰이는 값을 만들지 않았는지 — 읽는 코드가 없으면 없어야 한다
    assert "sentence_gap_ms" not in config.DEFAULTS["audio"]


def test_joins_apply_to_the_main_path_too(tmp_path):
    """🔴 v1.24의 미완성: joins가 freeze/loop 경로에만 있어 기본 경로에서는
    무시됐다. 영상 길이에 맞추는 이 경로에서도 같은 문장은 붙어야 한다."""
    from cutdaejang.utils import ffmpeg as ff

    clips = []
    for i in range(3):
        p = tmp_path / f"c{i}.wav"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=0.5", str(p)])
        clips.append(str(p))
    subs = [Subtitle(text=f"줄{i}", start_us=0, end_us=0) for i in range(3)]

    def run(joins):
        out, _c, _n = em.retime_narration(
            [str(c) for c in clips],
            [dataclasses.replace(s) for s in subs],
            total_us=10_000_000, tmp_dir=tmp_path, fit="drop", joins=joins)
        return out

    apart = run(None)
    together = run([True, False, False])       # 0번과 1번은 같은 문장
    gap_apart = apart[1].start_us - apart[0].end_us
    gap_together = together[1].start_us - together[0].end_us
    assert gap_apart > 0, "원래는 문장 사이에 쉼이 들어가야 정상"
    assert gap_together == 0, f"같은 문장인데 {gap_together}μs 침묵이 들어감"
    # 붙이지 않기로 한 자리는 그대로 쉰다
    assert together[2].start_us - together[1].end_us == gap_apart


# ══ ② 🏃 말 속도 ═══════════════════════════════════════════════
def test_speed_filter_values():
    assert _speed_filter(1.0) == ""            # 보통이면 필터를 아예 안 건다
    assert _speed_filter(None) == ""
    assert _speed_filter("abc") == ""          # 이상한 값도 예외 없이 보통 속도
    assert _speed_filter(0.85) == "atempo=0.850,"
    assert _speed_filter(1.25) == "atempo=1.250,"
    assert _speed_filter(3.0) == "atempo=2.000,"   # atempo 한계까지만
    assert _speed_filter(0.1) == "atempo=0.500,"


def test_speed_applies_to_every_provider():
    """제공자별로 흩어 놓지 않고 후처리 한 곳에서 건다 — 일레븐랩스든 제미나이든."""
    src = (ROOT / "cutdaejang/core/tts_engine.py").read_text(encoding="utf-8")
    body = src.split("def postprocess_clip(")[1].split("\ndef ")[0]
    assert 'speed = _speed_filter(audio_cfg.get("speech_speed", 1.0))' in body
    assert 'f"{speed}{sr},areverse,{sr},"' in body


def test_speed_does_not_break_continuous_reading():
    """🔴 전체 테스트가 잡아낸 결함 — 말 속도가 「이어읽기」를 깨뜨렸다.

    이어읽기는 여러 문장을 한 번에 합성한 뒤 **문장 사이 자연 무음**을 찾아
    조각으로 나눈다. 그런데 블록을 먼저 빠르게 만들어 버리면 그 무음도 같이
    짧아져 경계를 못 찾고, 이어읽기가 통째로 폐기돼 문장별 재합성으로 돌아갔다
    → ①문장마다 목소리 톤이 튐(목록 6번 증상) ②API 호출 3배.
    고친 방법: 블록은 원래 속도로 만들고 속도는 **잘라낸 조각마다** 건다.
    """
    src = (ROOT / "cutdaejang/core/tts_engine.py").read_text(encoding="utf-8")
    blk = src.split("def _synth_continuity_block(")[1].split("\n    def ")[0]
    assert '{**self.settings["audio"], "speech_speed": 1.0}' in blk, \
        "블록을 원래 속도로 만들지 않으면 문장 경계를 못 찾는다"
    split = src.split("def _split_continuity_block(")[1].split("\n    def ")[0]
    assert '_speed_filter(audio_cfg.get("speech_speed", 1.0))' in split
    assert 'f"{speed}{sr},areverse,{sr},"' in split


def test_continuous_reading_survives_fast_speed(tmp_path, monkeypatch):
    """말 속도를 올려도 이어읽기가 살아 있다 — 실제로 합성해서 확인.

    측정: 이 테스트용 소리(문장 사이 쉼이 넉넉함)에서는 2.0배부터 경계 검출이
    깨졌다(호출 1회 → 4회). 화면에서 고를 수 있는 최대는 1.25배지만 설정값은
    2.0까지 허용되고, 진짜 성우 소리는 쉼이 더 짧아 여유가 이보다 좁다.
    """
    import sys

    sys.path.insert(0, str(ROOT))
    from cutdaejang.core import tts_engine as te
    from tests.test_v109 import _PausingGemini

    lines = ["첫 구간의 마지막 문장입니다.", "둘째 구간도 같은 목소리입니다.",
             "마지막까지 같은 속도로 읽습니다."]

    def run(speed):
        prov = _PausingGemini()
        st = config.deep_merge(config.DEFAULTS, {"audio": {"speech_speed": speed}})
        eng = te.TTSEngine(prov, tmp_path / f"cache{speed}", settings=st)
        paths = eng.synth_all(lines, continuity=True)
        total = sum(te.ff.probe_duration_us(str(p)) for p in paths)
        return prov.calls, paths, total

    calls1, paths1, dur1 = run(1.0)
    assert calls1 == 1, "원래 속도에서는 한 호흡 1회 (기존 동작)"

    calls2, paths2, dur2 = run(2.0)
    assert calls2 == 1, f"빠르게에서도 한 호흡 1회여야 함 (실제 {calls2}회)"
    assert all(".cont-" in p.name for p in paths2), "이어읽기 조각이 유지돼야 함"
    assert len(paths2) == len(lines)
    assert dur2 < dur1 * 0.7, f"실제로 짧아져야 함: {dur1} → {dur2}"


def test_speed_is_part_of_the_cache_key():
    """속도를 바꿨는데 예전 소리가 재사용되면 바꾼 티가 안 난다."""
    src = (ROOT / "cutdaejang/core/tts_engine.py").read_text(encoding="utf-8")
    key = src.split("def _cache_key(")[1].split("\n    def ")[0]
    assert '"speech_speed"' in key and "|sp:" in key


def test_speed_default_in_settings():
    assert config.DEFAULTS["audio"]["speech_speed"] == 1.0


def test_speed_param_reaches_settings(tmp_path, monkeypatch):
    """화면에서 고른 말 속도가 settings.audio.speech_speed로 들어간다.

    ⚠ _apply_bg_style은 고른 값을 **파일로 저장**한다 — 테스트가 개발/사용자
    settings.json을 건드리지 않도록 반드시 격리한다 (실제로 한 번 오염시켜
    다른 테스트를 깨뜨린 적이 있다).
    """
    monkeypatch.setenv("CUTDAEJANG_SETTINGS", str(tmp_path / "settings.json"))
    base = config.deep_merge(config.DEFAULTS, {})
    merged = webui._apply_bg_style({"narr_speed": "1.12"}, base)
    assert merged["audio"]["speech_speed"] == pytest.approx(1.12)
    # 범위를 벗어난 값은 잘라서 넣는다 (목소리가 망가지지 않게)
    assert webui._apply_bg_style({"narr_speed": "9"}, base)["audio"]["speech_speed"] == 2.0
    assert webui._apply_bg_style({"narr_speed": "말도안됨"}, base)["audio"][
        "speech_speed"] == 1.0


def test_speed_selects_on_screen():
    html = webui._apply_links(webui._HTML)
    assert 'id="narrSpeedSel"' in html          # 편집(내레이션) 폼
    assert 'id="genSpeedSel"' in html           # AI 영상 만들기 폼
    for opt in ("🐢 느리게", "🐇 빠르게", "⚡ 아주 빠르게"):
        assert opt in html
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert src.count("narr_speed:") == 3        # 편집·AI생성·구간 세 폼 모두


# ══ ③ ✏ 부분 수정 ═════════════════════════════════════════════
def test_retouch_route_exists():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert 'elif path == "/api/retouch":' in src
    assert "def _retouch(self, params: dict, workdir: str)" in src
    assert "def _run_restyle(" in src


def test_retouch_panel_on_done_screen():
    html = webui._apply_links(webui._HTML)
    assert 'id="retouchBox"' in html
    assert "✏ 부분 수정 (말 속도·목소리·꾸미기)" in html
    assert "🎙 목소리만 다시 만들기" in html
    assert "🎨 꾸미기만 다시 입히기" in html
    for sel in ("rtSpeedSel", "rtVoiceSel", "rtSubStyleSel", "rtToneSel"):
        assert f'id="{sel}"' in html
    # 초보자가 "안 고른 것은 그대로"임을 알 수 있어야 한다
    assert html.count('<option value="">그대로</option>') >= 3


def test_retouch_js_is_valid_and_posts():
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    assert "async function retouch(ev, what)" in src
    assert "'/api/retouch'" in src
    assert "function fillRetouchVoices()" in src


def test_reuse_scene_images_finds_existing(tmp_path):
    """부분 수정은 이미 만든 그림을 재사용한다 — 다시 만들면 돈이 또 나간다."""
    scenes = tmp_path / "scenes"
    scenes.mkdir()
    (scenes / "scene_01.png").write_bytes(b"x")
    (scenes / "scene_03.png").write_bytes(b"x")
    got = webui._reuse_scene_images(tmp_path, 4)
    assert len(got) == 4
    assert got[0] and got[0].endswith("scene_01.png")
    assert got[1] is None                       # 없는 자리는 이웃 그림이 채운다
    assert got[2] and got[2].endswith("scene_03.png")
    assert got[3] is None
    # 그림을 한 장도 안 만든 영상이어도 예외 없이 빈 목록
    assert webui._reuse_scene_images(tmp_path / "없음", 3) == [None, None, None]


def test_saved_job_params_prefers_memory_then_history(tmp_path):
    from cutdaejang.db.jobs import JobStore

    store = JobStore(tmp_path / "history.db")
    store.upsert("작업1", title="옛 작업", mode="auto", outputs="mp4", status="ok",
                 params_json=json.dumps({"topic": "히스토리", "voice": "Kore"},
                                        ensure_ascii=False))
    store.close()
    # 진행 중이면 메모리 값이 우선
    saved, row = webui._saved_job_params("작업1", {"params": {"topic": "메모리"}},
                                         str(tmp_path))
    assert saved["topic"] == "메모리"
    assert row["title"] == "옛 작업"
    # 껐다 켠 뒤(메모리 없음)에도 히스토리에서 되살아난다
    saved2, _ = webui._saved_job_params("작업1", {}, str(tmp_path))
    assert saved2 == {"topic": "히스토리", "voice": "Kore"}
    # 모르는 작업이면 조용히 빈 값 (예외로 화면이 죽지 않게)
    assert webui._saved_job_params("없는작업", {}, str(tmp_path))[0] == {}


def test_history_keeps_params_without_secrets():
    """부분 수정이 되려면 만들 때 쓴 입력값이 남아야 한다 — 단, API 키는 빼고."""
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    body = src.split("def _record_history(")[1].split("\ndef ")[0]
    assert "params: Optional[dict] = None" in body
    assert "k not in _PARAM_SECRET_KEYS" in body
    assert "params_json=" in body
    assert "_record_history(workdir, result, opts, params)" in src


def test_restyle_keeps_audio_and_layout():
    """🎨 꾸미기만 다시 = 소리·타이밍·화면 배치는 손대지 않는다."""
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    body = src.split("def _run_restyle(")[1].split("\ndef ")[0]
    assert "dataclasses.replace(spec, style=style)" in body   # 바뀌는 건 style뿐
    for keep in ("size=spec.style.size", "position=spec.style.position",
                 "margin_v=spec.style.margin_v", "wrap_chars=spec.style.wrap_chars"):
        assert keep in body, f"원본 배치를 안 지킴: {keep}"
    # 오디오·자막 시각을 건드리는 코드가 없어야 한다
    assert "audio=" not in body and "subtitles=" not in body


def test_voice_retouch_reruns_the_tested_pipeline():
    """목소리 부분 수정은 spec을 손으로 기우지 않고 검증된 파이프라인을 다시 탄다.

    속도를 바꾸면 클립 길이가 바뀌므로 자막을 다시 배치해야 하는데, 그 계산은
    이미 retime_narration이 하고 있다. 직접 spec을 고치면 목소리와 자막이 어긋난다.
    """
    src = (ROOT / "cutdaejang/gui/webui.py").read_text(encoding="utf-8")
    body = src.split("def _retouch(")[1].split("\n    # ----------")[0]
    assert "_queue_job(new_id, _run_pipeline, new_id, script, new_params, workdir," in body
    assert "_reuse_scene_images(job_dir, len(script.sentences))" in body
    assert 'new_params["auto"] = True' in body
    # 새 목소리·속도만 덮어쓴다
    assert webui._RETOUCH_VOICE_KEYS == ("narr_speed", "tts_provider", "voice",
                                         "tts_style")
    assert "sub_style" in webui._RETOUCH_DECO_KEYS and "tone" in webui._RETOUCH_DECO_KEYS


def test_retouch_explains_its_limits_to_beginners():
    """초보자가 무엇이 바뀌고 무엇이 그대로인지 화면에서 알 수 있어야 한다."""
    html = webui._apply_links(webui._HTML)
    assert "자막이 나오는 시각도 새 목소리 길이에 맞춰" in html
    assert "손대지 않아</b> 가장 빨라요" in html
    assert "AI 그림 값도 안 나가요" in html


# ══ 화면 무결성 (버전 올릴 때마다) ═══════════════════════════════
def test_html_is_still_well_formed():
    html = webui._apply_links(webui._HTML)
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "중복 id"
    for tag in ("div", "details", "select", "button"):
        assert len(re.findall(rf"<{tag}[\s>]", html)) == len(
            re.findall(rf"</{tag}>", html)), f"<{tag}> 짝이 안 맞음"
    # 판이 올라갈 때마다 깨지지 않게 — 화면 제목이 실제 버전과 같은지만 본다
    assert f"(v{__version__})" in html
