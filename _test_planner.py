"""
_test_planner.py — 영상 기획 디렉터 엔진 검증 (display 불필요)
"""
import sys, traceback
import content_planner as cp

results = []
def check(name, fn):
    try:
        fn(); results.append((name, True)); print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, False)); print(f"  ❌ {name}: {e}"); traceback.print_exc()

def t_josa():
    assert cp._josa("실력", ("이", "가")) == "이"      # 받침 O
    assert cp._josa("자동화", ("이", "가")) == "가"     # 받침 X
    assert cp._josa("블로그봇", ("을", "를")) == "을"
    assert cp._ro("블로그") == "로"
    assert cp._ro("플레이스") == "로"                   # 스: 받침X
    assert cp._ro("블로그봇") == "으로"                 # 봇: 받침 ㅅ
check("한글 조사(이/가, 로/으로) 처리", t_josa)

def t_full():
    plan = cp.generate_full_plan({
        "purpose": "문의 유도", "target": "자영업자", "product": "블로그 자동화봇",
        "problem": "매일 블로그 글 쓸 시간이 없다", "message": "",
        "misconception": "글쓰기 실력", "length": "쇼츠 30초", "hook_type": "반전형"})
    assert len(plan["hooks"]) == 6
    assert len(plan["structure"]) >= 4
    assert plan["script"]
    assert len(plan["subtitles"]) >= 3
    assert len(plan["scenes"]) >= 4
    assert len(plan["upload"]["titles"]) == 5
    assert 0 < plan["review"]["score"] <= 100
    # 조사 오류 없어야
    txt = cp.format_plan(plan)
    assert "실력가" not in txt, "조사 오류(실력가) 남아있음"
    assert "실력이 아닙니다" in txt, "올바른 조사(실력이) 누락"
    assert "영상 기획서" in txt and "검수 리포트" in txt
check("전체 기획서 생성 (조사 정상)", t_full)

def t_lengths_targets():
    for length in cp.LENGTHS:
        for target in cp.TARGETS:
            plan = cp.generate_full_plan({
                "purpose": "교육 콘텐츠", "target": target, "product": "플레이스 진단기",
                "problem": cp.suggest_problems(target)[0], "length": length,
                "hook_type": "질문형"})
            assert plan["script"] and plan["review"]["score"] > 0
    print(f"       {len(cp.LENGTHS)}길이 × {len(cp.TARGETS)}타겟 = {len(cp.LENGTHS)*len(cp.TARGETS)}조합 OK")
check("모든 길이×타겟 조합 생성", t_lengths_targets)

def t_message_auto():
    # 메시지 비웠을 때 자동 제안
    plan = cp.generate_full_plan({"target": "크몽 판매자", "product": "상세페이지 자동화",
                                  "problem": "상세 쓰기가 오래 걸린다", "length": "쇼츠 15초"})
    assert plan["message"], "메시지 자동 제안 실패"
check("메시지 미입력 시 자동 생성", t_message_auto)

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*40}\n결과: {passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
