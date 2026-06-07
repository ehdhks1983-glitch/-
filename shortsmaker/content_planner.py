"""
content_planner.py - 유튜브 영상 기획 디렉터 (오프라인 템플릿 엔진)

목적 → 타겟 → 상품 → 문제 → 핵심메시지 → 후킹 → 구조 → 대본 → 장면표 → 자막
→ 업로드문구 → 검수 순서로 기획서를 자동 조립한다. (API 키 불필요)
나중에 AI 생성으로 바꾸려면 각 make_* 함수만 교체하면 된다.
"""

import re
from typing import Dict, List

# ─── 선택지 ───
PURPOSES = ["조회수 확보", "신뢰 구축", "문의 유도", "상품 판매", "교육 콘텐츠"]
TARGETS = ["자영업자", "1인 사업자", "크몽 판매자", "블로그 운영자",
           "마케팅 대행사", "스마트스토어/쿠팡 판매자"]
LENGTHS = ["쇼츠 15초", "쇼츠 30초", "쇼츠 60초", "롱폼"]
HOOK_TYPES = ["공감형", "경고형", "반전형", "질문형", "사례형", "숫자형"]

# ─── 타겟별 흔한 문제 (시작점 제안) ───
PROBLEM_LIBRARY: Dict[str, List[str]] = {
    "자영업자": [
        "블로그·SNS를 해야 하는 건 알지만 매일 글 쓸 시간이 없다",
        "어떤 키워드로 글을 써야 할지 모른다",
        "광고비를 써도 문의로 이어지지 않는다",
        "대행사는 비싸고 직접 하기는 어렵다",
    ],
    "1인 사업자": [
        "혼자 다 하려니 마케팅까지 손이 안 간다",
        "콘텐츠를 꾸준히 올릴 시간이 없다",
        "뭐부터 해야 할지 우선순위를 모르겠다",
        "외주를 주자니 비용이 부담된다",
    ],
    "크몽 판매자": [
        "상품을 올려도 상위 노출이 안 된다",
        "상세페이지를 어떻게 써야 팔리는지 모른다",
        "경쟁 상품이 너무 많아 차별화가 어렵다",
        "문의는 오는데 구매로 이어지지 않는다",
    ],
    "블로그 운영자": [
        "매일 글을 발행하는 루틴을 유지하기 어렵다",
        "키워드를 잡아도 상위 노출이 안 된다",
        "글을 써도 방문자가 늘지 않는다",
        "수익화까지 연결이 안 된다",
    ],
    "마케팅 대행사": [
        "처리해야 할 계정·콘텐츠가 너무 많다",
        "반복 작업에 인력이 갈려 나간다",
        "보고서·결과 정리에 시간을 다 쓴다",
        "단가 경쟁이 심해 마진이 안 남는다",
    ],
    "스마트스토어/쿠팡 판매자": [
        "상품 등록·상세 작성이 매번 오래 걸린다",
        "리뷰·CS 관리에 시간을 다 뺏긴다",
        "노출이 안 돼서 매출이 정체다",
        "어떤 키워드로 올려야 할지 모른다",
    ],
}

# ─── 구조 템플릿 ───
SHORTS_ROLES = ["후킹", "문제 공감", "원인 설명", "해결 방향", "자연스러운 CTA"]
LONG_ROLES = ["오프닝 문제 제기", "왜 이 문제가 생기는지", "잘못된 해결 방식",
              "올바른 해결 방식", "실제 예시", "적용 방법", "마무리 CTA"]


def _topic(product: str) -> str:
    """상품명에서 주제어 뽑기 (봇/프로그램/툴 등 접미사 제거)"""
    t = product.strip()
    for suf in ("자동화봇", "자동화 봇", "봇", "프로그램", "프로그램입니다", "툴", "도구", "솔루션", "서비스"):
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
            break
    return t or product.strip() or "이 방법"


def _short(text: str, n: int = 22) -> str:
    text = (text or "").strip().split("\n")[0]
    return text if len(text) <= n else text[: n - 1] + "…"


def _josa(word: str, pair: tuple) -> str:
    """받침 유무로 조사 선택. pair=(받침있을때, 받침없을때) 예: ('이','가')"""
    w = (word or "").strip()
    if not w:
        return pair[1]
    code = ord(w[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return pair[0] if (code - 0xAC00) % 28 != 0 else pair[1]
    return pair[1]


def _ro(word: str) -> str:
    """로/으로 선택 (받침 없거나 ㄹ받침이면 '로')"""
    w = (word or "").strip()
    if not w:
        return "로"
    code = ord(w[-1])
    if 0xAC00 <= code <= 0xD7A3:
        b = (code - 0xAC00) % 28
        return "로" if b in (0, 8) else "으로"
    return "로"


def suggest_problems(target: str) -> List[str]:
    return PROBLEM_LIBRARY.get(target, [
        "해야 하는 건 아는데 시간이 없다",
        "방법을 몰라서 못 한다",
        "돈을 써도 효과를 못 본다",
        "혼자 하기 어렵다",
    ])


def make_message(product: str, problem: str) -> str:
    """핵심 메시지 자동 제안 (사용자가 비웠을 때)"""
    topic = _topic(product)
    return (f"{topic}의 핵심은 '많이 하는 것'이 아니라, "
            f"반복 업무를 끊기지 않게 유지하는 구조입니다")


def make_hooks(product: str, target: str, problem: str,
               message: str, misconception: str) -> Dict[str, str]:
    topic = _topic(product)
    ps = _short(problem)
    mis = misconception.strip() or "방법"
    return {
        "공감형": f"{target} 분들, {ps} 그쵸?",
        "경고형": f"{topic}, 이렇게 하면 오히려 역효과 납니다.",
        "반전형": f"{topic}, 진짜 중요한 건 {mis}{_josa(mis, ('이', '가'))} 아닙니다.",
        "질문형": f"왜 누구는 {topic}{_ro(topic)} 문의가 오고, 누구는 계속 조용할까요?",
        "사례형": "고객 상담하면서 제일 많이 들은 말이 있습니다.",
        "숫자형": f"{target}{_josa(target, ('이', '가'))} {topic}에서 막히는 이유, 딱 3가지입니다.",
    }


def make_structure(length: str, ctx: dict) -> List[dict]:
    """시간 구간별 (역할, 내용) 구조"""
    hook = ctx["hook"]
    problem = ctx["problem"]
    message = ctx["message"]
    product = ctx["product"]
    mis = ctx.get("misconception", "").strip() or "방법"
    cta = "이런 반복 업무를 줄이는 도구를 만들고 있습니다. 필요하면 프로필 링크에서 확인해보세요."

    if length == "롱폼":
        texts = [
            f"{hook}",
            f"문제는 {mis}{_josa(mis, ('이', '가'))} 아니라, {problem} — 이게 매일 반복된다는 점입니다.",
            f"보통은 '{mis}만 좋으면 된다'고 생각하지만 그게 함정입니다.",
            f"진짜 해결책은 {message}.",
            f"실제로 이렇게 바꾸면 {ctx['target']}의 부담이 확 줄어듭니다.",
            f"{product}를 이런 흐름으로 쓰면 됩니다.",
            cta,
        ]
        return [{"role": r, "text": t} for r, t in zip(LONG_ROLES, texts)]

    # 쇼츠
    spans = {"쇼츠 15초": ["0~1초", "2~6초", "7~11초", "12~15초"],
             "쇼츠 30초": ["0~2초", "3~9초", "10~20초", "21~30초"],
             "쇼츠 60초": ["0~3초", "4~18초", "19~45초", "46~60초"]}.get(
        length, ["0~2초", "3~9초", "10~20초", "21~30초"])
    texts = [
        hook,
        f"사실 {problem} — {ctx['target']} 대부분이 겪는 일이죠.",
        f"문제는 {mis}{_josa(mis, ('이', '가'))} 아니라 매일 반복해야 하는 구조입니다. 그래서 {message}.",
        cta,
    ]
    roles = ["후킹", "문제 공감", "원인+해결", "CTA"]
    return [{"span": s, "role": r, "text": t}
            for s, r, t in zip(spans, roles, texts)]


def make_script(length: str, structure: List[dict]) -> str:
    return "\n".join(s["text"] for s in structure)


def make_subtitles(script: str) -> List[str]:
    """대본을 짧은 자막 줄로 쪼갬 (한 줄 ~14자)"""
    # 문장/절 단위로 분리
    chunks = re.split(r"[.!?\n]|, |니다|죠|요(?=\s|$)", script)
    lines: List[str] = []
    for c in chunks:
        c = c.strip(" ,.")
        if not c:
            continue
        # 너무 길면 공백 기준으로 더 쪼갬
        while len(c) > 16:
            cut = c.rfind(" ", 0, 16)
            if cut <= 0:
                cut = 16
            lines.append(c[:cut].strip())
            c = c[cut:].strip()
        if c:
            lines.append(c)
    return [l for l in lines if l]


def make_scene_table(structure: List[dict], ctx: dict) -> List[dict]:
    visuals = [
        f"{ctx['target']}{_josa(ctx['target'], ('이', '가'))} 고민하는 장면 (AI 이미지/실사)",
        "문제 상황 체크리스트 화면",
        f"{ctx['product']} 작동/설명 화면 (화면 녹화)",
        "프로필·상담 링크 안내 (CTA 화면)",
    ]
    rows = []
    for i, s in enumerate(structure):
        rows.append({
            "span": s.get("span", f"구간 {i+1}"),
            "visual": visuals[i] if i < len(visuals) else "관련 화면",
            "subtitle": _short(s["text"], 18),
            "source": "AI 이미지 / 화면 녹화",
        })
    return rows


def make_upload(product: str, target: str, message: str, purpose: str) -> dict:
    topic = _topic(product)
    titles = [
        f"{target}{_josa(target, ('이', '가'))} {topic} 못 하는 진짜 이유",
        f"{topic}, {target}이 꼭 알아야 할 것",
        f"{topic} 자동화, 글쓰기보다 중요한 것",
        f"매일 {topic} 힘든 {target}이라면",
        f"{topic}는 '많이'가 아니라 '꾸준히'입니다",
    ]
    base_tags = ["#" + topic.replace(" ", ""), "#AI자동화", "#자영업자마케팅",
                 "#소상공인", "#1인사업자", "#" + re.sub(r"\s", "", target)]
    desc = (f"{target}을 위한 {topic} 이야기입니다.\n"
            f"{message}\n\n"
            f"반복 업무를 줄이는 자동화에 관심 있다면 프로필 링크를 확인해보세요.")
    return {
        "titles": titles,
        "description": desc,
        "hashtags": " ".join(dict.fromkeys(base_tags)),
        "pinned": f"💬 {topic} 관련해서 가장 궁금한 점을 댓글로 남겨주세요!",
        "cta": "프로필 링크에서 더 자세한 내용을 확인하실 수 있어요.",
    }


def review(ctx: dict, structure: List[dict]) -> dict:
    """기획 검수 — 체크리스트 점수 + 개선 제안"""
    score = 0
    good, fix = [], []
    hook = ctx.get("hook", "")
    # 1. 후킹 강도
    if hook and not hook.startswith("안녕") and ("?" in hook or "않" in hook or "이유" in hook or "역효과" in hook):
        score += 18; good.append("첫 문장(후킹)이 호기심을 자극함")
    else:
        score += 8; fix.append("후킹을 더 강하게 — 질문형/반전형 추천")
    # 2. 타겟 명확성
    if ctx.get("target"):
        score += 16; good.append("타겟이 명확함")
    else:
        fix.append("타겟을 좁혀서 한 명에게 말하듯")
    # 3. 한 메시지
    if ctx.get("message") and len(ctx["message"]) < 80:
        score += 18; good.append("핵심 메시지가 하나로 분명함")
    else:
        score += 8; fix.append("메시지를 한 문장으로 압축")
    # 4. 광고 냄새 (교육형 우선)
    if ctx.get("purpose") in ("신뢰 구축", "문의 유도", "교육 콘텐츠"):
        score += 16; good.append("판매보다 교육형이라 신뢰가 생김")
    else:
        score += 10; fix.append("바로 '구매하세요'보다 문제→해결로 신뢰 먼저")
    # 5. 끝까지 볼 이유 (구조)
    if len(structure) >= 4:
        score += 16; good.append("문제→해결→CTA 구조가 잡힘")
    else:
        score += 8
    # 6. 상품 연결
    if ctx.get("product"):
        score += 16; good.append("실제 상품과 자연스럽게 연결됨")
    else:
        fix.append("마지막에 상품/서비스로 자연 연결 추가")

    score = min(100, score)
    improved_hook = None
    if "후킹" in " ".join(fix):
        improved_hook = f"{_topic(ctx.get('product',''))}, 글만 많이 만들면 오히려 실패합니다."
    return {"score": score, "good": good, "fix": fix, "improved_hook": improved_hook}


def generate_full_plan(inputs: dict) -> dict:
    """입력 → 전체 기획 결과(dict). inputs: purpose,target,product,problem,message,misconception,length,hook_type"""
    product = inputs.get("product", "").strip() or "자동화 도구"
    target = inputs.get("target", "").strip() or "자영업자"
    purpose = inputs.get("purpose", "문의 유도")
    problem = inputs.get("problem", "").strip() or suggest_problems(target)[0]
    message = inputs.get("message", "").strip() or make_message(product, problem)
    misconception = inputs.get("misconception", "").strip()
    length = inputs.get("length", "쇼츠 30초")

    hooks = make_hooks(product, target, problem, message, misconception)
    hook_type = inputs.get("hook_type", "반전형")
    hook = hooks.get(hook_type, hooks["반전형"])

    ctx = {"product": product, "target": target, "purpose": purpose,
           "problem": problem, "message": message, "misconception": misconception,
           "hook": hook}

    structure = make_structure(length, ctx)
    script = make_script(length, structure)
    subtitles = make_subtitles(script)
    scenes = make_scene_table(structure, ctx)
    upload = make_upload(product, target, message, purpose)
    rev = review(ctx, structure)

    return {
        "purpose": purpose, "target": target, "product": product,
        "problem": problem, "message": message, "hook": hook, "hook_type": hook_type,
        "hooks": hooks, "structure": structure, "script": script,
        "subtitles": subtitles, "scenes": scenes, "upload": upload, "review": rev,
        "length": length,
    }


def format_plan(plan: dict) -> str:
    """기획 결과를 복사용 텍스트(기획서)로"""
    L = []
    L.append("━" * 30)
    L.append(f"🎬 영상 기획서  ({plan['length']})")
    L.append("━" * 30)
    L.append(f"\n[1] 영상 목적\n  {plan['purpose']}")
    L.append(f"\n[2] 타겟\n  {plan['target']}")
    L.append(f"\n[3] 상품/서비스\n  {plan['product']}")
    L.append(f"\n[4] 고객 문제\n  {plan['problem']}")
    L.append(f"\n[5] 핵심 메시지 (딱 하나)\n  {plan['message']}")
    L.append("\n[6] 후킹 후보")
    for t, h in plan["hooks"].items():
        mark = "⭐" if t == plan["hook_type"] else "  "
        L.append(f"  {mark} ({t}) {h}")
    L.append(f"\n[7] 영상 구조")
    for s in plan["structure"]:
        span = s.get("span", "")
        L.append(f"  · {span} [{s['role']}] {s['text']}")
    L.append(f"\n[8] 대본\n{plan['script']}")
    L.append("\n[9] 장면 구성표")
    L.append("  시간 | 화면 | 자막 | 소스")
    for r in plan["scenes"]:
        L.append(f"  {r['span']} | {r['visual']} | {r['subtitle']} | {r['source']}")
    L.append("\n[10] 자막 (한 줄씩 크게)")
    for s in plan["subtitles"]:
        L.append(f"  {s}")
    up = plan["upload"]
    L.append("\n[11] 업로드 패키지")
    L.append("  제목 후보:")
    for i, t in enumerate(up["titles"], 1):
        L.append(f"    {i}. {t}")
    L.append(f"  설명:\n    {up['description']}")
    L.append(f"  해시태그: {up['hashtags']}")
    L.append(f"  고정댓글: {up['pinned']}")
    rev = plan["review"]
    L.append(f"\n[12] 검수 리포트 — {rev['score']}점")
    if rev["good"]:
        L.append("  좋은 점:")
        for g in rev["good"]:
            L.append(f"    ✓ {g}")
    if rev["fix"]:
        L.append("  수정 필요:")
        for f in rev["fix"]:
            L.append(f"    △ {f}")
    if rev.get("improved_hook"):
        L.append(f"  개선 후킹 제안: {rev['improved_hook']}")
    L.append("\n" + "━" * 30)
    return "\n".join(L)
