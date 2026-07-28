"""v1.10 — 🖥 편집 완전자동 '긴 영상 1개' 모드 (사용자 리포트).

리포트: "16대 9비율 8분30초짜리를 넣어야하는데 넣을곳이없어 저건 쇼츠잖아"
완전 자동의 [만들기]가 쇼츠 2종(1개/여러 개)뿐이고 직접 입력 길이도 90초까지라
가로 롱폼을 넣을 자리가 실제로 없었다 →
① 만들기 3번째 선택지 '긴 영상 1개 — 원본 비율 그대로'
② 길이 후보를 모드별로 교체(원본 그대로·15/10/5/3분) + 직접 입력 최대 1800초
③ 긴 영상 모드는 세로 강제(ensureShortsLayout)를 끄고 원본 비율로 되돌림
④ 긴 목표(2분↑)는 몽타주 조각을 2배로 — 조각 수 폭증·산만함 방지
"""

from cutdaejang.core.edit_mode import spread_ranges
from cutdaejang.core.video_editor import montage_piece_us


def test_montage_piece_scales_with_target():
    """쇼츠는 촘촘하게, 긴 영상은 조각을 길게."""
    assert montage_piece_us("", 30) == 3_500_000
    assert montage_piece_us("빠르게", 30) == 2_400_000
    assert montage_piece_us("아주 빠르게", 60) == 1_700_000
    # 2분 이상 = 긴 영상 → 2배
    assert montage_piece_us("", 300) == 7_000_000
    assert montage_piece_us("빠르게", 300) == 4_800_000
    assert montage_piece_us("빠르게", 120) == 4_800_000      # 경계 포함
    assert montage_piece_us("빠르게", 119) == 2_400_000
    assert montage_piece_us(None, 0) == 3_500_000            # 값 없음 안전


def test_long_montage_keeps_length_with_fewer_pieces():
    """8분30초 → 5분 압축: 목표 길이는 지키고 조각 수는 쇼츠 밀도보다 확 적다."""
    total, target = 510_000_000, 300_000_000
    long_r = spread_ranges(total, target, piece_us=montage_piece_us("빠르게", 300))
    short_r = spread_ranges(total, target, piece_us=montage_piece_us("빠르게", 30))
    assert abs(sum(e - s for s, e in long_r) - target) < 2_000_000
    assert len(long_r) < len(short_r) / 1.5
    assert all(0 <= s < e <= total for s, e in long_r)
    # 영상 처음~끝을 고르게 (마지막 조각이 뒷부분에서 시작)
    assert long_r[-1][0] > total * 0.85


def test_ui_offers_long_mode():
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert '<option value="long">' in src                      # 만들기 3번째
    assert 'id="autoTargetSec"' in src and 'max="1800"' in src  # 직접 입력 상한 해제
    assert "function rebuildTargetPreset" in src                # 모드별 길이 후보
    assert "'900','15분으로 압축'" in src and "'0','원본 길이 그대로 (자르지 않음)'" in src
    assert "function ensureLongLayout" in src                   # 세로 강제 해제
    assert "'long') return;" in src                             # ensureShortsLayout 조기 반환
    assert 'id="autoLongTip"' in src


def test_backend_wiring_long():
    import cutdaejang.gui.webui as w
    assert "auto_mode" in w._EDIT_LAST_KEYS           # 만들기 방식 기억
    src = open("cutdaejang/gui/webui.py", encoding="utf-8").read()
    assert "ve.montage_piece_us(params.get(\"tempo\"), tgt_auto)" in src
    assert '{"빠르게": 2_400_000, "아주 빠르게": 1_700_000}.get(\n' not in src \
        or src.count('{"빠르게": 2_400_000') == 1   # 편집 몽타주 자리엔 인라인 표 없음
    assert "_tgt_txt" in src and "분 {tgt_auto % 60}초" in src   # 분 단위 안내
    # 저장·복원·전송 3곳에 auto_mode가 실려야 세팅이 기억된다
    assert src.count("auto_mode:") >= 3
