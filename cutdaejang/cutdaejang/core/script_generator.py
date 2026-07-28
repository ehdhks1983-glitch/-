"""주제 → 구조화 JSON 대본 (기획안 §5.1, 부록 A 프롬프트).

숫자·영어 약어를 한글 발음으로 표기하도록 프롬프트에서 강제한다(TTS 오독 방지, §7-6).
JSON 파싱 실패 시 예외를 던지고, 자동 모드의 1회 재생성 정책은 오케스트레이터가 담당한다.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .tts_engine import _http_post_json


class ScriptError(RuntimeError):
    pass


class ScriptParseError(ScriptError):
    """모델 응답이 유효한 대본 JSON이 아님 (자동 모드: 1회 재생성 대상)."""


CONTEXT_BLOCK = """
[제품/참고 정보 — 사실 근거 (v0.64)]
{context}
- 위 정보에 있는 사실만 사용할 것. 여기 없는 기능·가격·수치·효능은 절대 지어내지 말 것
- 정보를 그대로 낭독하지 말고, 시청자에게 말하듯 자연스럽게 풀어서 쓸 것
"""

PROMPT_TEMPLATE = """\
역할: 유튜브 쇼츠 대본 작가
입력: 주제="{topic}", 톤="{tone}", 목표길이={target_sec}초
규칙:
- 첫 문장은 콜드오픈 훅 — 인사·자기소개·배경 설명 금지, 1초 안에 결론·충격·궁금증부터 던질 것
  ("안녕하세요"·"오늘은 ~알아볼게요" 류로 시작하면 실패) / 마지막 문장은 CTA
- 전체의 약 1/4 지점(3번째 이후) 문장 하나는 이탈을 막는 재훅으로 쓸 것 —
  반전 예고·"진짜 핵심은 지금부터" 류. 그 문장에만 "rehook":true 표시 (정확히 1개)
- 문장당 반드시 {max_chars}자 이내 (자막 1줄). 초과 문장 금지 — 길면 두 문장으로 나눌 것
- 문장들이 한 사람이 이어 말하는 내레이션이어야 함 — 앞 문장을 받아 자연스럽게 잇고
  (그래서·근데·특히·이때·그러면 등), 서로 안 이어지는 나열식·뚝뚝 끊기는 문장 금지.
  소리 내어 읽으면 한 흐름의 이야기로 들려야 함
- 모든 문장은 완결된 구어체 어미로 끝낼 것 ("~요"·"~예요"·"~하세요"·"~합니다") —
  "확인 필수"·"설치 완료"·"주의" 같은 명사형(개조식) 종결 절대 금지. 글자수를 맞추려고
  어미를 자르지 말고, 길면 두 문장으로 나눌 것
- 구어체. 숫자·영어 약어는 한글 발음으로 표기 (TTS 오독 방지. 예: "2026년"→"이천이십육년", "AI"→"에이아이")
- highlight: 각 문장에서 시청자가 기억해야 할 단어 1개 (문장에 그대로 포함된 단어, 없으면 빈 문자열)
- scene: 그 문장이 나올 때 화면에 보여줄 장면 묘사 1줄 (한국어, 그림 생성용. 인물·사물·배경·분위기를
  구체적으로. 글자·문자·로고는 절대 넣지 말 것)
출력(JSON만): {{"title":"","sentences":[{{"text":"","highlight":"","scene":"","rehook":false}},...],"background_prompt":"","hashtags":[""]}}
"""


@dataclass
class Script:
    title: str
    sentences: List[str]
    highlights: List[str] = field(default_factory=list)  # 문장별 강조 단어 (병렬 리스트)
    background_prompt: str = ""
    hashtags: List[str] = field(default_factory=list)
    scene_prompts: List[str] = field(default_factory=list)  # 문장별 장면 묘사 (v0.45 이미지 생성용)
    rehook_idx: int = -1                 # 🪝 재훅 문장 번호 (v0.75 — 없으면 -1)

    def __post_init__(self):
        # highlights/scene_prompts는 항상 sentences와 같은 길이로 정규화
        self.highlights = (self.highlights or [])[: len(self.sentences)]
        self.highlights += [""] * (len(self.sentences) - len(self.highlights))
        self.scene_prompts = (self.scene_prompts or [])[: len(self.sentences)]
        self.scene_prompts += [""] * (len(self.sentences) - len(self.scene_prompts))
        if not (0 <= self.rehook_idx < len(self.sentences)):
            self.rehook_idx = -1

    @classmethod
    def from_json_text(cls, text: str) -> "Script":
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ScriptParseError(f"대본 JSON 파싱 실패: {e}\n원문 앞부분: {cleaned[:200]}") from e
        raw = data.get("sentences")
        if not isinstance(raw, list) or not raw:
            raise ScriptParseError(f"sentences 형식 오류: {raw!r}")

        sentences, highlights, scenes = [], [], []
        rehook_idx = -1
        for item in raw:
            if isinstance(item, str) and item.strip():  # 구버전 문자열 형식 호환
                sentences.append(item.strip())
                highlights.append("")
                scenes.append("")
            elif isinstance(item, dict) and str(item.get("text", "")).strip():
                sentences.append(str(item["text"]).strip())
                highlights.append(str(item.get("highlight", "") or "").strip())
                scenes.append(str(item.get("scene", "") or "").strip())
                if item.get("rehook") is True and rehook_idx < 0:  # 🪝 첫 true만 (v0.75)
                    rehook_idx = len(sentences) - 1
            else:
                raise ScriptParseError(f"sentences 항목 형식 오류: {item!r}")
        # 리스트 병렬 형식({"sentences":[...], "highlights":[...]})도 수용
        if not any(highlights) and isinstance(data.get("highlights"), list):
            highlights = [str(h or "").strip() for h in data["highlights"]]
        if not any(scenes) and isinstance(data.get("scene_prompts"), list):
            scenes = [str(s or "").strip() for s in data["scene_prompts"]]

        return cls(
            title=str(data.get("title", "")),
            sentences=sentences,
            highlights=highlights,
            background_prompt=str(data.get("background_prompt", "")),
            hashtags=[str(h) for h in data.get("hashtags", []) if h],
            scene_prompts=scenes,
            rehook_idx=rehook_idx,
        )

    def to_json(self) -> str:
        sent = []
        for i, (t, h, s) in enumerate(
                zip(self.sentences, self.highlights, self.scene_prompts)):
            d = {"text": t, "highlight": h, "scene": s}
            if i == self.rehook_idx:  # 🪝 재훅 표시 왕복 보존 (v0.75)
                d["rehook"] = True
            sent.append(d)
        return json.dumps(
            {
                "title": self.title,
                "sentences": sent,
                "background_prompt": self.background_prompt,
                "hashtags": self.hashtags,
            },
            ensure_ascii=False,
            indent=2,
        )


_COLOR_MARKUP_RE = re.compile(r"\[[가-힣A-Za-z]+\]|\[/[가-힣A-Za-z]*\]")  # [노랑]…[/] 자막 색


def _chunk_by_words(text: str, limit: int) -> List[str]:
    """단어 경계로 limit자 이하 조각들로 분할 (edit_mode.split_long_subtitles와 동일 규칙)."""
    chunks: List[str] = []
    cur = ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if len(cand) > limit and cur:
            chunks.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    fixed: List[str] = []  # 공백 없는 초장문은 단어 분할이 안 됨 → 글자 단위 강제 분할
    for c in chunks:
        while len(c) > limit:
            fixed.append(c[:limit])
            c = c[limit:]
        fixed.append(c)
    return [c for c in fixed if c]


def split_long_sentences(script: Script, limit: int = 32) -> Script:
    """limit(자막 2줄 분량)를 넘는 문장을 단어 경계로 쪼갠 새 Script를 돌려준다.

    AI가 "N자 이내" 규칙을 어겨도 자막이 3줄 이상으로 화면을 덮지 않게 하는
    안전장치 (v0.77). 문장=클립 1:1 구조라 조각마다 TTS가 따로 합성돼 싱크는
    자연히 맞는다. 강조어는 그 단어가 든 첫 조각에만, 장면 묘사는 첫 조각에만
    남긴다(빈칸은 fill_scene_gaps가 이웃으로 채움). 재훅 번호도 새 위치로 재매핑.
    색 마크업([노랑]…[/])이 든 문장은 쌍이 깨질 수 있어 분할하지 않는다.
    """
    if limit <= 0 or not script.sentences:
        return script
    sents: List[str] = []
    hls: List[str] = []
    scenes: List[str] = []
    rehook = -1
    changed = False
    for i, raw in enumerate(script.sentences):
        text = (raw or "").strip()
        hl = script.highlights[i] if i < len(script.highlights) else ""
        scene = script.scene_prompts[i] if i < len(script.scene_prompts) else ""
        if i == script.rehook_idx:
            rehook = len(sents)  # 분할돼도 첫 조각이 재훅 (원래 시점 보존)
        visible = _COLOR_MARKUP_RE.sub("", text)
        if len(visible) <= limit or visible != text:  # 짧거나 색 마크업 있음 → 그대로
            sents.append(text)
            hls.append(hl)
            scenes.append(scene)
            continue
        changed = True
        placed_hl = False
        for j, c in enumerate(_chunk_by_words(text, limit)):
            sents.append(c)
            if hl and not placed_hl and hl in c:
                hls.append(hl)
                placed_hl = True
            else:
                hls.append("")
            scenes.append(scene if j == 0 else "")
    if not changed:
        return script
    return Script(
        title=script.title,
        sentences=sents,
        highlights=hls,
        background_prompt=script.background_prompt,
        hashtags=list(script.hashtags),
        scene_prompts=scenes,
        rehook_idx=rehook,
    )


_NARRATION_ENDING_RE = re.compile(
    r"(?:습니다|입니다|됩니다|합니다|했습니다|겠습니다|"
    r"이에요|예요|거예요|거에요|네요|군요|죠|까요|나요|세요|십시오|"
    r"어요|아요|해요|돼요|한다|된다|했다|였다|이다|다|자)"
    r"[\"'”’」』)\]]*$"
)
_NARRATION_PUNCT_RE = re.compile(
    r"(?<!\d)[.!?。！？]+(?!\d)[\"'”’」』)\]]*"
)


def narration_units(text: str, hard_limit: int = 360) -> List[str]:
    """내레이션을 화면 줄이 아닌 자연스러운 *발화 문장* 단위로 정리한다.

    입력창의 일반 줄바꿈은 화면 편의를 위한 것일 수 있다. 예를 들어
    ``"먼저 사람이 하는\\n업무를 하는 거였습니다"``를 두 TTS 호출로 나누면
    문장 한가운데에 긴 쉼과 음색 변화가 생긴다. 빈 줄은 문단 경계로 보존하되,
    끝나지 않은 일반 줄바꿈은 이어 붙이고 실제 종결부호·한국어 종결어미에서만
    발화 단위를 만든다.

    비정상적으로 긴 무구두점 원고만 제공자 입력 한도를 피하도록 단어 경계에서
    나눈다. 화면 자막 줄바꿈은 ASS 렌더러가 별도로 처리하므로 ``wrap_chars``와
    의도적으로 무관하다.
    """
    hard_limit = max(120, int(hard_limit or 360))
    paragraphs = re.split(r"\r?\n\s*\r?\n", str(text or "").strip())
    natural: List[str] = []

    for paragraph in paragraphs:
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in paragraph.splitlines()
            if line.strip()
        ]
        if not lines:
            continue
        merged: List[str] = []
        buf = ""
        for line in lines:
            buf = f"{buf} {line}".strip()
            punct = _NARRATION_PUNCT_RE.search(line)
            if ((punct and punct.end() == len(line))
                    or _NARRATION_ENDING_RE.search(line)):
                merged.append(buf)
                buf = ""
        if buf:
            merged.append(buf)

        for phrase in merged:
            start = 0
            for match in _NARRATION_PUNCT_RE.finditer(phrase):
                piece = phrase[start:match.end()].strip()
                if piece:
                    natural.append(piece)
                start = match.end()
            tail = phrase[start:].strip()
            if tail:
                natural.append(tail)

    out: List[str] = []
    for phrase in natural:
        if len(phrase) <= hard_limit:
            out.append(phrase)
            continue
        words = phrase.split()
        cur = ""
        for word in words:
            candidate = f"{cur} {word}".strip()
            if cur and len(candidate) > hard_limit:
                out.append(cur)
                cur = word
            else:
                cur = candidate
        if cur:
            while len(cur) > hard_limit and " " not in cur:
                out.append(cur[:hard_limit])
                cur = cur[hard_limit:]
            if cur:
                out.append(cur)
    return [unit for unit in out if unit]


_HEADER_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$")            # 마크다운 헤더
_SPEAK_RE = re.compile(r"\[\s*말\s*\]")                     # **[말]** 표기
_QUOTE_RE = re.compile(r"^>\s?(.*)$")                       # 블록 인용(> …)


def _clean_section_title(raw: str) -> str:
    t = re.sub(r"[#*`]+", "", raw).strip()
    t = re.sub(r"^[🎬📋📌⭐️\s]+", "", t)
    t = re.sub(r"\(\s*\d+:?\d*\s*[~〜-]\s*\d+:?\d*\s*\)", "", t)  # (0:00 ~ 0:20) 제거
    return t.strip(" -—·").strip()[:60]


def _clean_speak_line(raw: str) -> str:
    t = raw.replace("**", "").strip()
    t = t.strip('"“”')
    t = re.sub(r"^\*\(.*?\)\*$", "", t)                      # *(마무리)* 류 주석 줄
    return t.strip()


def split_script_sections(text: str) -> list:
    """구간 대본(마크다운 + [말] 블록) → [{"title","narration"}] (v0.80, 무키 휴리스틱).

    사용자 촬영 대본 형식 지원: "## 🎬 N. 제목 (0:00~0:20)" 헤더 아래 "**[말]**" 뒤의
    블록 인용(>)들이 그 구간의 내레이션. 같은 헤더 안 [말]이 여러 개면 합친다.
    [말] 블록이 하나도 없으면 빈 줄 기준 문단을 구간으로 (마크다운 잡음 줄 제외).
    """
    lines = (text or "").splitlines()
    sections: list = []
    cur_title = ""
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _HEADER_RE.match(ln.strip())
        if m:
            cur_title = _clean_section_title(m.group(1))
            i += 1
            continue
        if _SPEAK_RE.search(ln):
            i += 1
            spoken: list = []
            while i < len(lines):
                q = _QUOTE_RE.match(lines[i].strip())
                if q is None:
                    if not lines[i].strip():          # 빈 줄은 인용 사이 허용
                        if i + 1 < len(lines) and _QUOTE_RE.match(lines[i + 1].strip()):
                            i += 1
                            continue
                    break
                s = _clean_speak_line(q.group(1))
                if s:
                    spoken.append(s)
                i += 1
            if spoken:
                narr = "\n".join(spoken)
                if sections and sections[-1]["title"] == cur_title:
                    sections[-1]["narration"] += "\n" + narr   # 같은 구간의 [말] 여러 개
                else:
                    sections.append({"title": cur_title or f"구간 {len(sections) + 1}",
                                     "narration": narr})
            continue
        i += 1
    if sections:
        return sections
    # 폴백: [말] 표기가 없는 일반 대본 → 빈 줄 문단 = 구간
    para: list = []
    out: list = []

    def _flush():
        body = "\n".join(para).strip()
        if len(body) >= 10:
            out.append({"title": f"구간 {len(out) + 1}", "narration": body})
        para.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            _flush()
            continue
        if s.startswith(("#", "|", "-", "```", "[", "*", ">")):
            s2 = _clean_speak_line(_QUOTE_RE.match(s).group(1)) if s.startswith(">") else ""
            if s2:
                para.append(s2)
            continue
        para.append(s)
    _flush()
    return out


SECTION_SPLIT_PROMPT = """\
아래는 영상 촬영용 구간 대본이다. 구간(장면)별로 나눠서, 각 구간에서 내레이션으로
소리 내어 읽을 문장만 뽑아라. 화면 지시·자막 문구·편집 메모·체크리스트는 제외.
출력(JSON만): {{"sections":[{{"title":"구간 제목(짧게)","narration":"읽을 문장들(줄바꿈 구분)"}},...]}}
대본:
{text}
"""


def split_script_sections_ai(text: str, model: str = "gemini-2.5-flash",
                             api_key=None) -> list:
    """AI로 구간·내레이션 추출 (형식 자유 대본용). 키 없음/실패 → ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 AI 구간 나누기를 쓸 수 없습니다")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {"contents": [{"parts": [{"text": SECTION_SPLIT_PROMPT.format(
        text=(text or "").strip()[:12000])}]}],
        "generationConfig": {"responseMimeType": "application/json"}}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        out = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        secs = [{"title": str(s.get("title") or "")[:60],
                 "narration": str(s.get("narration") or "").strip()[:2000]}
                for s in (out.get("sections") or []) if str(s.get("narration") or "").strip()]
    except (KeyError, IndexError, json.JSONDecodeError, AttributeError) as e:
        raise ScriptError(f"AI 구간 나누기 응답 예상 밖: {str(e)[:120]}") from e
    if not secs:
        raise ScriptError("AI가 구간을 찾지 못했습니다")
    return secs[:30]


class GeminiScript:
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise ScriptError("GEMINI_API_KEY가 설정되어 있지 않습니다")

    def generate(
        self, topic: str, tone: str = "정보형", target_sec: int = 60, max_chars: int = 22,
        context: str = "",
    ) -> Script:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        prompt = PROMPT_TEMPLATE.format(
            topic=topic, tone=tone, target_sec=target_sec, max_chars=max_chars)
        if (context or "").strip():  # 📇 제품 정보·참고 메모 주입 + 지어내기 가드 (v0.64)
            prompt += CONTEXT_BLOCK.format(context=context.strip()[:1200])
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        data = _http_post_json(url, payload, {"x-goog-api-key": self.api_key})
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ScriptError(f"Gemini 응답 형식 예상 밖: {json.dumps(data)[:300]}") from e
        return Script.from_json_text(text)


PRODUCT_SUMMARY_PROMPT = """\
아래 제품 소개 글을 읽고, 영상 대본 작성에 쓸 제품 프로필로 요약해줘.
출력(JSON만): {{"name":"제품명","desc":"한 줄 소개(40자)","points":"핵심 기능·차별점 3~5개(줄당 1개)",
"target":"타깃 시청자","tone":"어울리는 말투 톤 한 단어","link":"본문 속 URL(없으면 빈칸)"}}
과장 없이 본문에 있는 사실만. 본문:
{text}
"""


def summarize_product(text: str, model: str = "gemini-2.5-flash", api_key=None) -> dict:
    """붙여넣은 제품 소개 글 → 프로필 초안 (v0.64)."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 AI 정리를 쓸 수 없습니다")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {"contents": [{"parts": [{"text": PRODUCT_SUMMARY_PROMPT.format(
        text=text.strip()[:4000])}]}],
        "generationConfig": {"responseMimeType": "application/json"}}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        out = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ScriptError(f"AI 정리 응답 예상 밖: {str(e)[:120]}") from e
    return {k: str(out.get(k) or "")[:500]
            for k in ("name", "desc", "points", "target", "tone", "link")}


ARTICLE_SCRIPT_PROMPT = """\
역할: 유튜브 쇼츠 대본 작가
아래 블로그 글을 {target_sec}초짜리 쇼츠 내레이션 대본으로 다시 써줘.
글 제목: "{title}"
규칙:
- 문장 {n_min}~{n_max}개. 첫 문장은 콜드오픈 훅 — 인사·자기소개 금지, 결론·이득·궁금증부터
- 마지막 문장은 CTA(구매·클릭 강요 말고 "자세한 건 링크에" 정도로 부드럽게)
- 문장당 반드시 22자 이내 (자막 1줄). 초과 문장 금지 — 길면 두 문장으로 나눌 것
- 문장들이 한 사람이 이어 말하는 내레이션이어야 함 — 앞 문장을 받아 자연스럽게 잇고
  (그래서·근데·특히·이때 등), 서로 안 이어지는 나열식·뚝뚝 끊기는 문장 금지
- 모든 문장은 완결된 구어체 어미로 끝낼 것 ("~요"·"~예요"·"~하세요") — "확인 필수"·
  "설치 완료" 같은 명사형(개조식) 종결 절대 금지. 길면 어미를 자르지 말고 두 문장으로
- 구어체. 숫자·영어 약어는 한글 발음으로 표기 (예: "50%"→"오십 퍼센트", "AI"→"에이아이")
- 글에 있는 사실만 사용할 것 — 여기 없는 기능·가격·수치·효능은 절대 지어내지 말 것
- hook: 영상 상단에 붙일 제목 1줄 (15자 안팎, 시선 잡기)
출력(JSON만): {{"title":"","hook":"","sentences":["",...],"hashtags":["",...]}}
본문:
{text}
"""


def summarize_article(title: str, text: str, target_sec: int = 45,
                      model: str = "gemini-2.5-flash", api_key=None) -> dict:
    """🔗 블로그 글 → 쇼츠 내레이션 대본 (v0.78). 키 없으면 ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 AI 대본 요약을 쓸 수 없습니다")
    target_sec = max(15, min(180, int(target_sec or 45)))
    n = max(6, min(20, target_sec // 4))          # 문장 ≈ 4초 (내레이션 페이스)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    prompt = ARTICLE_SCRIPT_PROMPT.format(
        target_sec=target_sec, title=(title or "").strip()[:120],
        n_min=max(4, n - 2), n_max=n + 2, text=(text or "").strip()[:4000])
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseMimeType": "application/json"}}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        out = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        sents = [str(s).strip() for s in out.get("sentences") or [] if str(s).strip()]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ScriptError(f"AI 대본 응답 예상 밖: {str(e)[:120]}") from e
    if not sents:
        raise ScriptError("AI가 대본 문장을 만들지 못했습니다")
    return {"title": str(out.get("title") or title or "")[:100],
            "hook": str(out.get("hook") or "")[:60],
            "sentences": sents[:24],
            "hashtags": [str(h)[:30] for h in (out.get("hashtags") or [])[:10] if h]}


_KO_SENT_RE = re.compile(r"[^.!?…\n]*(?:다\.|요\.|[.!?…]|\n)")


def summarize_article_stub(title: str, text: str, target_sec: int = 45) -> dict:
    """키 없음/AI 실패 폴백 — 본문 앞쪽 문장을 잘라 그대로 대본으로 (v0.78)."""
    n = max(4, min(12, int(target_sec or 45) // 4))
    sents = []
    for m in _KO_SENT_RE.finditer((text or "").strip()):
        s = m.group(0).strip()
        if len(s) < 4:
            continue
        # 어미가 잘려 어색해지지 않게 문장은 통째로 (긴 문장은 v0.77 안전장치가 나눔)
        sents.append(s[:120])
        if len(sents) >= n:
            break
    if not sents:
        sents = [((title or "블로그 글 소개").strip())[:60], "자세한 내용은 본문 링크를 확인해 주세요."]
    return {"title": (title or "").strip()[:100], "hook": (title or "").strip()[:24],
            "sentences": sents, "hashtags": []}


HOOK_PROMPT = """\
역할: 유튜브 쇼츠/영상 썸네일 카피라이터
주제/내용: "{context}"
위 내용으로 시선을 확 잡는 **후킹 제목** {n}개를 지어줘.
규칙:
- 각 제목은 1~2줄, 짧고 강하게 (궁금증·숫자·반전·이득 중 하나 활용)
- 낚시성 과장 금지, 내용과 관련
- 출력은 제목만, 한 줄에 하나씩 (번호·따옴표·설명 없이)
"""


def suggest_hooks(context: str, n: int = 5, model: str = "gemini-2.5-flash",
                  api_key=None) -> list:
    """Gemini로 후킹 제목 후보 n개 생성. 키 없으면 ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 제목 추천을 쓸 수 없습니다")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {"contents": [{"parts": [{"text": HOOK_PROMPT.format(context=context, n=n)}]}]}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"제목 추천 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    hooks = []
    for line in text.splitlines():
        line = re.sub(r'^\s*(?:\d+[.)]\s*|[-*•]\s*|["\'])|["\']\s*$', "", line).strip()
        if line and len(line) <= 40:
            hooks.append(line)
    return hooks[:n]


HIGHLIGHT_PROMPT = """\
역할: 유튜브 쇼츠 편집자
아래는 긴 영상의 자막 목록이야. 각 줄: 번호) [시작시각] (길이) 내용.
목표: 골라 합치면 약 {target}초짜리 쇼츠가 되게, **영상 전체에서 가장 임팩트 있는
순간만** 추려. 핵심만 짧고 굵게.
반드시 지켜:
- ⚠ 앞에서부터 순서대로 채우기 금지 — 0,1,2,3… 같은 연속 번호 나열은 실패다.
- [시작시각]을 보고 영상의 앞·중간·뒷부분을 모두 훑어라. 뒷부분에도 핵심이 있다.
- 서두 훅 1개 + 중간 핵심들 + 마무리(결론·반전) 1개 구조를 권장.
- 숫자·질문·반전·이득·결론이 있는 문장 우선. 지루한 설명·군더더기·중복은 버려.
- 고른 문장은 그 자체로 말이 돼야 한다.
- climax: keep 중에서 "가장 궁금하게 만드는 한 문장"의 번호 (첫 3초 티저로 맨 앞에
  잠깐 보여줄 장면 — 영상 첫 문장 말고 중간·뒷부분에서 고를 것)
자막들:
{lines}
출력(JSON만): {{"keep":[고른 번호들], "climax":번호, "reason":"왜 이렇게 골랐는지 한 줄"}}
"""


def _fmt_sub_lines(subs: list) -> str:
    out = []
    for i, s in enumerate(subs):
        sec = max(0.1, (s.get("end_us", 0) - s.get("start_us", 0)) / 1e6)
        at = int(s.get("start_us", 0) / 1e6)
        out.append(f"{i}) [{at // 60}:{at % 60:02d}] ({sec:.1f}초) {s.get('text','')}")
    return "\n".join(out)


def suggest_highlights(subs: list, target_sec: int = 30,
                       model: str = "gemini-2.5-flash", api_key=None) -> dict:
    """자막 목록 → 쇼츠용 핵심 자막 번호 골라주기 (Gemini). 키 없으면 ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 AI 핵심 추천을 쓸 수 없습니다")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    prompt = HIGHLIGHT_PROMPT.format(target=target_sec, lines=_fmt_sub_lines(subs))
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"핵심 추천 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    obj = json.loads(cleaned)
    keep = sorted({int(i) for i in obj.get("keep", []) if 0 <= int(i) < len(subs)})
    # 게으른 선택 가드: 영상이 목표보다 충분히 긴데 '0부터 연속 번호'거나 전부
    # 앞 40%에 몰려 있으면 실패 취급 → 호출측이 후킹 점수 방식으로 폴백한다.
    if keep and len(subs) >= 6:
        video_end = max(s.get("end_us", 0) for s in subs) / 1e6
        if video_end > target_sec * 1.6:
            is_prefix = keep == list(range(len(keep)))
            last_start = subs[keep[-1]].get("start_us", 0) / 1e6
            front_only = video_end > 0 and last_start <= video_end * 0.4
            if is_prefix or front_only:
                raise ScriptError(
                    "AI가 앞부분만 연속으로 골라(핵심 선별 실패) 무효 처리 — 후킹 점수 방식으로 대체")
    try:  # ⚡ 콜드오픈 티저용 클라이맥스 (v0.75) — keep 안 번호만 인정
        climax = int(obj.get("climax", -1))
    except (TypeError, ValueError):
        climax = -1
    if climax not in keep:
        climax = pick_climax(subs, keep)
    return {"keep": keep, "climax": climax, "reason": str(obj.get("reason", ""))}


REFINE_PROMPT = """\
역할: 유튜브 자막 교정 편집자
아래는 음성 인식(STT)으로 받아쓴 자막이라, 발음·잡음 때문에 잘못 적힌 부분이 있을 수 있어.
각 줄을 자연스럽고 말이 되는 한국어로 고쳐줘.{ctx}
규칙:
- 줄 수와 순서는 절대 그대로 (입력 {n}줄 → 출력 정확히 {n}줄, 1:1 대응)
- 명백한 오인식만 문맥에 맞게 자연스럽게 교정. 없는 내용을 지어내지 마.
- 구어체 유지, 자막용이라 한 줄은 짧고 간결하게
- 도무지 못 고치겠는 줄은 원문 그대로 둬
입력 자막:
{lines}
출력(JSON만): {{"lines":["교정된 1줄","교정된 2줄", ...]}}
"""


def refine_subtitles(texts: list, context: str = "",
                     model: str = "gemini-2.5-flash", api_key=None) -> list:
    """STT 자막을 문맥 기반으로 자연스럽게 교정 (발음 오인식 자동 수정). 키 없으면 ScriptError.

    줄 수·순서는 보존한다. 응답이 어긋나면 해당 줄은 원문을 유지.
    """
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 AI 대본 다듬기를 쓸 수 없습니다")
    src = [str(t or "") for t in texts]
    numbered = "\n".join(f"{i + 1}) {t}" for i, t in enumerate(src))
    ctx = f'\n영상 주제/맥락: "{context.strip()}" (교정에 참고)' if context.strip() else ""
    prompt = REFINE_PROMPT.format(n=len(src), lines=numbered, ctx=ctx)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"대본 다듬기 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    obj = json.loads(cleaned)
    lines = obj.get("lines") or []
    # 줄 수가 어긋나면 있는 만큼만 교체, 나머지는 원문 유지
    out = []
    for i, orig in enumerate(src):
        cand = str(lines[i]).strip() if i < len(lines) else ""
        out.append(cand if cand else orig)
    return out


# 후킹 신호 키워드 — 쇼츠에서 시선을 잡는 표현들
_HOOK_WORDS = (
    "왜", "어떻게", "비법", "꿀팁", "충격", "진짜", "무료", "방법", "핵심", "주의",
    "실수", "비밀", "최고", "제일", "공개", "후기", "추천", "정리", "결론", "반전",
    "이것만", "하지 마", "안 됩니다", "됩니다", "만에", "단 ",
)


def _hook_score(text: str, dur: float, idx: int, total: int) -> float:
    """자막 한 줄의 '후킹 점수' — 숫자·질문·키워드·정보밀도·위치 보정."""
    t = text.strip()
    score = min(len(t) / max(dur, 0.5), 8.0)          # 정보 밀도 (상한)
    if re.search(r"\d", t):
        score += 3.0                                   # 숫자 = 썸네일급 훅
    if "?" in t:
        score += 2.5                                   # 궁금증 유발
    if "!" in t:
        score += 1.5
    score += sum(1.5 for w in _HOOK_WORDS if w in t)
    if idx == 0:
        score += 2.0                                   # 도입부(첫 마디) 보정
    if total > 2 and idx == total - 1:
        score += 1.0                                   # 마무리(결론) 소폭 보정
    return score


def pick_climax(subs: list, keep: list) -> int:
    """keep 중 '첫 3초 티저(콜드오픈)'로 쓸 클라이맥스 한 문장 고르기 (v0.75).

    영상 시작 문장은 제외(어차피 맨 앞이라 티저 의미가 없음) — keep의 2번째부터
    후킹 점수(숫자·질문·키워드·밀도)가 가장 높은 문장. 후보가 없으면 -1.
    """
    cands = [i for i in keep if 0 <= i < len(subs)][1:]  # keep 첫 문장 제외
    best, best_score = -1, -1.0
    for i in cands:
        s = subs[i]
        dur = max(0.1, (s.get("end_us", 0) - s.get("start_us", 0)) / 1e6)
        # idx=1,total=3 → 도입부/마무리 위치 보정 없이 내용 점수만 비교
        score = _hook_score(str(s.get("text") or ""), dur, 1, 3)
        if score > best_score:
            best, best_score = i, score
    return best


def suggest_highlights_heuristic(subs: list, target_sec: int = 30) -> dict:
    """키 없이 쓰는 대역 — 영상 전체에서 '후킹 요소'(숫자·질문·키워드)가 강한
    구간들을 골라 모은다 (연속 구간이 아니라 임팩트 순, 시간순으로 재배열)."""
    n = len(subs)
    if not n:
        return {"keep": [], "reason": "자막이 없습니다"}
    scored = []
    for i, s in enumerate(subs):
        dur = max(0.1, (s.get("end_us", 0) - s.get("start_us", 0)) / 1e6)
        scored.append((_hook_score(str(s.get("text") or ""), dur, i, n), i, dur))
    # 앞·중간·뒤 3등분 버킷에서 점수순으로 번갈아 뽑아 영상 전체를 커버
    # (점수가 비슷할 때 앞 문장부터 연속으로 채워지던 문제 방지)
    video_end = max(s.get("end_us", 0) for s in subs) or 1
    buckets = [[], [], []]
    for score, i, dur in scored:
        b = min(2, int(3 * subs[i].get("start_us", 0) / video_end))
        buckets[b].append((score, i, dur))
    for b in buckets:
        b.sort(key=lambda x: -x[0])
    ptr = [0, 0, 0]
    keep, total = [], 0.0
    while total < target_sec:
        progressed = False
        for b in range(3):
            if total >= target_sec:
                break
            if ptr[b] < len(buckets[b]):
                _score, i, dur = buckets[b][ptr[b]]
                ptr[b] += 1
                keep.append(i)
                total += dur
                progressed = True
        if not progressed:
            break
    keep.sort()                                        # 영상 순서 유지
    return {"keep": keep, "climax": pick_climax(subs, keep),
            "reason": (f"영상 앞·중간·뒤에서 후킹 요소(숫자·질문·키워드)가 강한 "
                       f"{len(keep)}개 구간을 모아 약 {int(total)}초 "
                       f"(대략치 — 제미나이 키를 넣으면 문맥까지 봐요)")}


THUMB_PROMPT = """\
역할: 유튜브 썸네일 카피라이터
대본/주제: "{context}"
위 내용으로 썸네일에 넣을 **짧고 강한 문구** {n}개를 지어줘.
규칙:
- 각 문구는 1~2줄, 한 줄은 아주 짧게(공백 포함 10자 안팎). 두 줄이면 사이에 \\n
- 궁금증·이득·숫자·반전 중 하나로 확 잡기, 과장 낚시는 금지
- 각 문구에서 가장 강조할 단어 1개(highlight)도 골라줘 (문구에 그대로 있는 단어)
출력(JSON만): [{{"title":"1줄\\n2줄","highlight":"강조단어"}}, ...]  (정확히 {n}개)
"""


def suggest_thumbnail_copy(context: str, n: int = 4,
                           model: str = "gemini-2.5-flash", api_key=None) -> list:
    """대본/주제 → 썸네일용 후킹 카피 후보 (title/highlight). 키 없으면 ScriptError."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 썸네일 카피 추천을 쓸 수 없습니다")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": THUMB_PROMPT.format(context=context, n=n)}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ScriptError(f"썸네일 카피 응답 형식 예상 밖: {json.dumps(data)[:200]}") from e
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    arr = json.loads(cleaned)
    out = []
    for it in arr if isinstance(arr, list) else []:
        if isinstance(it, dict) and str(it.get("title", "")).strip():
            out.append({"title": str(it["title"]).strip(),
                        "highlight": str(it.get("highlight", "") or "").strip()})
    return out[:n]


def suggest_thumbnail_copy_stub(context: str, n: int = 4) -> list:
    """오프라인 대역 — 키 없이 UI 확인용 템플릿."""
    c = (context.strip() or "이 영상")[:14]
    base = [
        {"title": f"{c}\n이렇게 하세요", "highlight": "이렇게"},
        {"title": f"{c}\n딱 1분 정리", "highlight": "1분"},
        {"title": f"아직도 몰라요?\n{c}", "highlight": "아직도"},
        {"title": f"{c}\n이게 됩니다!", "highlight": "됩니다!"},
    ]
    return base[:n]


def suggest_hooks_stub(context: str, n: int = 5) -> list:
    """오프라인 대역 — 템플릿 기반 후보 (키 없이 UI 확인용)."""
    c = context.strip() or "이 영상"
    templates = [
        f"{c}, 이거 모르면 손해!",
        f"{c} 3가지 핵심 정리",
        f"아직도 {c} 몰라요?",
        f"{c}, 딱 1분이면 끝",
        f"{c} 이렇게 하면 됩니다",
        f"{c}의 반전 결말",
    ]
    return templates[:n]


class StubScript:
    """오프라인 대역 — 데모·테스트용 고정 대본."""

    name = "stub"

    def generate(
        self, topic: str, tone: str = "정보형", target_sec: int = 60, max_chars: int = 22,
        context: str = "",
    ) -> Script:
        return Script(
            title=f"{topic} — 컷대장 데모",
            sentences=[
                f"{topic}, 삼십 초만 집중해 주세요.",
                "이 영상은 컷대장이 자동으로 조립했습니다.",
                "대본과 목소리, 배경과 자막까지 한 번에요.",
                "구독과 좋아요는 큰 힘이 됩니다!",
            ],
            highlights=["집중", "자동", "한 번에요", "구독"],
            background_prompt=f"{topic}를 상징하는 세로형 미니멀 배경, 어두운 톤",
            hashtags=["쇼츠", "자동화", "컷대장"],
            scene_prompts=[
                f"{topic}를 상징하는 인상적인 첫 장면, 시선을 끄는 구도",
                "작업이 자동으로 조립되는 느낌의 장면, 톱니바퀴와 부품",
                "대본·마이크·자막이 어우러진 제작 장면",
                "밝고 긍정적인 마무리 장면, 엄지척",
            ],
        )


SCRIPT_PROVIDERS = {"gemini": GeminiScript, "stub": StubScript}


# ─────────── v0.31: 영상 AI 분석 → 제목·대본 추천 (멀티모달) ───────────

VIDEO_ANALYZE_PROMPT = """\
역할: 유튜브 쇼츠 기획자. 아래는 한 영상의 장면 캡처들{with_tr}이다.{topic_hint}
영상 내용을 파악해 JSON으로만 답하라 (설명 없이):
{{
 "summary": "영상 내용 한두 문장 요약",
 "titles": ["유튜브 제목 후보 3개 — 짧고 후킹 있게"],
 "hooks": ["영상 위에 크게 얹을 상단 훅 문구 3개 — 1~2줄, 궁금증/숫자/이득"],
 "script": ["이 영상에 어울리는 내레이션 대본 — 화면 순서대로 진행을 설명, 한 문장씩 {n_lines}줄 내외, 각 24자 이내. 앞 문장을 받아 자연스럽게 이어지는 한 흐름의 말이어야 하고, 나열식으로 끊기면 안 됨. 모든 문장은 완결된 구어체 어미('~요'·'~하세요')로 끝낼 것 — '확인 필수' 같은 명사형 종결 금지"],
 "hashtags": ["해시태그 5개"]
}}
낚시성 과장 금지. 화면에 실제로 보이는 것만 근거로. 전부 한국어.
{transcript}"""


def suggest_from_video(frames_b64: list, transcript: str = "", topic: str = "",
                       n_sentences: int = 10,
                       model: str = "gemini-2.5-flash", api_key=None) -> dict:
    """장면 캡처(+자막 텍스트/+주제 힌트)를 Gemini에 보내 제목·훅·대본·해시태그 추천.

    무음 영상(대사 없음)도 화면만 보고 대본을 쓴다. topic이 있으면 그 주제·맥락에
    맞춰 대본 방향을 잡는다 (예: "블로그 글쓰기 시연"). n_sentences로 대본 분량을
    영상 길이·목표에 맞춘다 (짧은 요약 ~ 원본 길이 walkthrough).
    """
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 영상 분석을 쓸 수 없습니다")
    tr = f"\n[영상 속 대사(자동 인식)]\n{transcript.strip()}" if transcript.strip() else ""
    th = (f"\n이 영상의 주제·맥락: {topic.strip()} — 이 주제에 맞춰, 화면에 보이는 진행"
          f"·시연 순서를 설명하는 대본을 써라." if topic.strip() else "")
    n_lines = max(4, min(80, int(n_sentences)))
    prompt = VIDEO_ANALYZE_PROMPT.format(
        with_tr="과 대사" if tr else "", topic_hint=th, transcript=tr, n_lines=n_lines)
    parts = [{"text": prompt}] + [
        {"inline_data": {"mime_type": "image/jpeg", "data": b64}} for b64 in frames_b64
    ]
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"responseMimeType": "application/json"}}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ScriptError(f"영상 분석 응답 형식 예상 밖: {json.dumps(data)[:250]}") from e
    return {
        "summary": str(out.get("summary", "")),
        "titles": [str(x) for x in out.get("titles", [])][:5],
        "hooks": [str(x) for x in out.get("hooks", [])][:5],
        "script": [str(x) for x in out.get("script", [])][:80],  # 원본 길이 walkthrough 허용 (v0.71)
        "hashtags": [str(x) for x in out.get("hashtags", [])][:8],
    }


def suggest_from_video_stub(frames_b64: list, transcript: str = "") -> dict:
    """오프라인 대역 — 파이프라인 점검용 고정 추천."""
    base = transcript.strip().splitlines()[0][:18] if transcript.strip() else "이 영상"
    return {
        "summary": f"{base} 내용을 담은 영상입니다.",
        "titles": [f"{base}, 이렇게 하면 됩니다", f"{base} 핵심 정리", f"{base} 30초 요약"],
        "hooks": [f"{base} | 핵심", "이거 모르면 손해!", "30초만 보세요"],
        "script": [f"{base}를 소개합니다.", "핵심만 빠르게 짚어드릴게요.",
                   "첫째, 준비물을 확인하세요.", "둘째, 순서대로 따라 하세요.",
                   "마지막으로 결과를 확인합니다.", "구독과 좋아요 부탁드려요!"],
        "hashtags": ["쇼츠", "꿀팁", "자동화", "정리", "요약"],
    }


# ── 📦 업로드 키트 (v0.39) — 유튜브 업로드 문구 일괄 생성 ──

YT_CATEGORIES = (
    "인물/블로그", "코미디", "교육", "엔터테인먼트", "노하우/스타일", "게임",
    "음악", "뉴스/정치", "과학기술", "스포츠", "여행/이벤트", "영화/애니메이션",
    "자동차", "반려동물/동물",
)

UPLOAD_KIT_PROMPT = """너는 한국 숏폼 알고리즘·검색(SEO) 전문가다. 아래 영상의 장면 캡처{with_tr}를 보고,
유튜브·틱톡·인스타그램 릴스·네이버 클립·스레드 각각의 알고리즘에 맞춘 업로드 문구를 만든다.
{channel}{stage}
[영상 정보] 길이 {dur}초 · 형태: {shape}{hook}
{transcript}

⚠ 전 플랫폼 공통 원칙 (조회수 안 나오는 채널의 1순위 원인 교정):
- "꿀팁·정리·레전드·대박·필수" 같은 범용 단어만으로 된 제목·태그 금지 — 경쟁이 심해
  작은 채널은 노출 자체가 안 된다. 반드시 이 영상의 구체어(제품·상황·문제·대상)를 쓴다.
- 노출의 시작은 틈새 검색어(롱테일): 사람들이 실제 검색창에 치는 문장형 표현
  ("○○ 안될 때", "○○ 처음 하는 법", "○○ vs △△", "○○ 가격")을 파고든다.
- 영상에 없는 내용으로 낚지 않는다 — 낚시는 초반 이탈을 낳아 알고리즘 점수를 깎는다.

[유튜브 — 노출 = ① 추천 피드에서 안 넘기고 보게 ② 검색·연관 동영상 유입]
- titles: 정확히 4개, 각 40~60자. ① 틈새 검색어로 시작하는 검색형 ② 구체적 숫자·결과 제시형
  ③ 내용 기반 궁금증형 ④ 타깃 호명형("○○ 하는 분만"). 핵심 검색어는 앞 20자 안에(모바일 잘림).
- title_tags: 제목 뒤에 붙일 짧은 해시태그 2~3개(각 8자 이내 단어, ＃ 없이) —
  제목과 합쳐 100자를 넘지 않게.
- description: 첫 125자 안에 핵심 검색어 2개가 자연스럽게 든 요약(검색 미리보기 노출 구간),
  이어서 내용 요약 2~3문장, 마지막 줄에 해시태그 3개. 전체 500자 이내. 이모지 1~3개.
- tags: 유튜브 스튜디오 태그란용 15~20개 (전체 400자 이내) — 구체 검색어 위주(범용 단어 3개 이하),
  자주 틀리는 표기·동의어 변형 포함.
- keywords: 핵심 검색 키워드 정확히 10개.
- niche_keywords: 틈새 롱테일 검색어 5~8개 — 실제 검색창에 칠 법한 문장형(조사 최소화).
  제목·태그·설명에 우선 배치한 그 표현들을 그대로 모은다.
- pinned_comment: 업로드 직후 창작자가 직접 달아 [고정]할 댓글 1개(80자 이내) —
  시청자가 한 단어로도 답할 수 있는 구체 질문. 초기 댓글·참여 신호가 노출을 밀어준다.
- hashtags: 설명문 마지막 줄용 3개(＃ 없이 단어만). 쇼츠면 첫 번째는 반드시 "Shorts".
- category: 다음 중 정확히 하나만 — {cats}
[틱톡 — 캡션·화면 텍스트가 검색에 그대로 인덱싱된다 (틱톡 SEO)]
  tiktok.caption: 150자 이내, 밝고 가벼운 해요체(존댓말) — 반말 금지 (예: "~해요", "~예요", "~해보세요").
  검색어가 든 문장을 캡션 앞부분에 자연스럽게, 이모지 1~2개, 행동 유도 1개.
  tiktok.hashtags: 3~5개(넓은 태그 1~2 + 틈새 태그 2~3, ＃ 없이. fyp·viral 같은 무의미 태그 금지)
[인스타그램 릴스 — 캡션 텍스트가 인스타 검색에 인덱싱된다]
  instagram.caption: 친근한 해요체. 첫 줄은 125자 안에 끝나는 훅(검색어 포함), 빈 줄 하나,
  본문 2~3줄 + 행동 유도. instagram.hashtags: 3~5개(＃ 없이 — 과다 태그는 역효과)
[네이버 클립 — 네이버 검색·클립 탭 노출, 태그가 검색 연결의 핵심]
  naver_clip.title: 검색형 제목 30자 이내 — 네이버에 검색할 법한 명사구를 맨 앞에.
  naver_clip.tags: 10~12개(＃ 없이) — 네이버 검색어 스타일 명사구, 대중 3~4 + 틈새 6~8,
  시의성(계절·시기) 태그 1~2 포함.
  naver_clip.category1: 영상에 가장 맞는 1차 카테고리 1개 — 라이프, 뷰티, 패션, 푸드,
  여행, 건강/운동, 스포츠, 게임, 테크, 자동차, 동물, 육아, 지식/교육, 엔터테인먼트, 음악, 유머 중에서
  naver_clip.category2: 그 1차 안의 세부 주제(2차 카테고리)를 짧게 — 예: 라이프→직장인 일상, 푸드→집밥 레시피
[스레드] threads.post: 80~150자, 친구에게 다정하게 말하는 부드러운 반말 (예: "~했어?", "~인 것 같아", "~해보자").
  절대 금지: "야"·"어이"·"다들" 같은 부름말로 시작, "~했냐"·"~냐"·"~지?" 같은 거칠거나 따지는 어미, 시비조·명령조·훈계조. 존댓말·격식체도 금지.
  내 경험을 나누듯 자연스러운 첫 문장으로 시작하고, 마지막은 부드러운 반말 질문으로 답글 유도 (예: "너희는 어떻게 해?"). 이모지 0~1개. 본문에 해시태그 금지(토픽으로 대신).
  threads.topic: 토픽 태그 딱 1개(스레드는 태그를 1개만 지원)
JSON만 출력:
{{"titles": ["..."], "title_tags": ["..."], "description": "...", "tags": ["..."],
  "keywords": ["..."], "niche_keywords": ["..."], "pinned_comment": "...",
  "hashtags": ["..."], "category": "...", "category_reason": "한 문장",
  "tiktok": {{"caption": "...", "hashtags": ["..."]}},
  "instagram": {{"caption": "...", "hashtags": ["..."]}},
  "naver_clip": {{"title": "...", "tags": ["..."], "category1": "...", "category2": "..."}},
  "threads": {{"post": "...", "topic": "..."}}}}"""

# 📈 채널 단계별 키워드 전략 (v1.02) — "10일 올려도 조회수 0" 리포트의 핵심 교정:
# 작은 채널이 대중 키워드로 경쟁하면 노출 자체가 없다 → 단계에 맞는 배합을 지시.
KIT_STAGE_NOTES = {
    "신규": ("[채널 단계] 신규(구독 1천 미만) — 대중 키워드 경쟁은 무의미하다. "
            "제목·태그를 전부 틈새 검색어 중심으로 짜서 검색·연관 유입에 건다."),
    "성장": ("[채널 단계] 성장 중(구독 1천~1만) — 틈새 검색어 7 : 대중 키워드 3 "
            "비율로 섞는다."),
    "정착": ("[채널 단계] 자리 잡음(구독 1만+) — 대중 키워드·궁금증형 제목 비중을 "
            "높여도 노출이 붙는다."),
}


def suggest_upload_kit(frames_b64: list, transcript: str = "", *, duration_s: int = 0,
                       is_shorts: bool = True, hook: str = "", channel: Optional[dict] = None,
                       stage: str = "", model: str = "gemini-2.5-flash", api_key=None) -> dict:
    """장면 캡처+대본으로 유튜브 업로드 문구(제목·설명·태그·키워드·카테고리) 생성."""
    import os  # noqa: PLC0415

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ScriptError("GEMINI_API_KEY가 없어 업로드 키트 AI 생성을 쓸 수 없습니다")
    ch = ""
    if channel and any((channel or {}).values()):
        ch = ("[채널 정보 — 이 채널 톤에 맞출 것] "
              f"채널명: {channel.get('name') or '-'} / 주제: {channel.get('topic') or '-'} / "
              f"타깃 시청자: {channel.get('audience') or '-'}")
    st = KIT_STAGE_NOTES.get(str(stage or "").strip(), "")
    tr = f"[영상 속 대사]\n{transcript.strip()[:3500]}" if transcript.strip() else ""
    prompt = UPLOAD_KIT_PROMPT.format(
        with_tr="와 대사" if tr else "", channel=ch,
        stage=("\n" + st if st else ""), dur=duration_s or "?",
        shape=("세로 쇼츠" if is_shorts
               else "가로 롱폼 — Shorts 태그·쇼츠 표현 금지, 시청 지속(더 길게 보게) 관점으로"),
        hook=f" · 상단 제목: {hook}" if hook.strip() else "",
        transcript=tr, cats=", ".join(YT_CATEGORIES))
    parts = [{"text": prompt}] + [
        {"inline_data": {"mime_type": "image/jpeg", "data": b64}} for b64 in frames_b64
    ]
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"responseMimeType": "application/json"}}
    data = _http_post_json(url, payload, {"x-goog-api-key": key})
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ScriptError(f"업로드 키트 응답 형식 예상 밖: {json.dumps(data)[:250]}") from e
    return normalize_kit(out)


def _norm_words(lst, n: int, each: int = 30) -> list:
    """해시태그/태그 목록 정규화 — ＃ 제거·공백 정리·개수 제한."""
    out = []
    for x in (lst or []):
        s = str(x).lstrip("#").strip()
        if s:
            out.append(s[:each])
    return out[:n]


def normalize_kit(out: dict) -> dict:
    """모델 응답을 안전한 키트 구조로 정규화 (v0.47 플랫폼별 섹션 포함)."""
    cat = str(out.get("category", "")).strip()
    if cat not in YT_CATEGORIES:  # 목록 밖이면 기본값으로 (붙여넣기 실패 방지)
        cat = "인물/블로그"
    tk = out.get("tiktok") or {}
    ig = out.get("instagram") or {}
    nc = out.get("naver_clip") or {}
    th = out.get("threads") or {}
    return {
        "titles": [str(x)[:60] for x in out.get("titles", [])][:5],
        "title_tags": _norm_words(out.get("title_tags"), 3, each=12),  # 제목 옆 2~3개
        "description": str(out.get("description", ""))[:1200],
        "tags": [str(x).strip()[:30] for x in out.get("tags", []) if str(x).strip()][:20],
        "keywords": [str(x).strip() for x in out.get("keywords", []) if str(x).strip()][:10],
        # 🎯 틈새 롱테일 검색어 + 📌 고정 댓글 (v1.02 — 작은 채널 노출 전략)
        "niche_keywords": [str(x).strip()[:40]
                           for x in out.get("niche_keywords", []) if str(x).strip()][:8],
        "pinned_comment": str(out.get("pinned_comment", "")).strip()[:200],
        "hashtags": _norm_words(out.get("hashtags"), 3),
        "category": cat,
        "category_reason": str(out.get("category_reason", ""))[:200],
        "tiktok": {"caption": str(tk.get("caption", ""))[:300],
                   "hashtags": _norm_words(tk.get("hashtags"), 5)},
        "instagram": {"caption": str(ig.get("caption", ""))[:1000],
                      "hashtags": _norm_words(ig.get("hashtags"), 5)},
        "naver_clip": {"title": str(nc.get("title", ""))[:40],
                       "tags": _norm_words(nc.get("tags"), 12),
                       # 📂 1차/2차 카테고리 추천 (v0.87) — 업로드 화면에서 고르는 용
                       "category1": str(nc.get("category1", "")).strip()[:20],
                       "category2": str(nc.get("category2", "")).strip()[:30]},
        "threads": {"post": str(th.get("post", ""))[:500],
                    "topic": str(th.get("topic", "")).lstrip("#").strip()[:30]},
    }


def suggest_upload_kit_stub(transcript: str = "", hook: str = "",
                            is_shorts: bool = True) -> dict:
    """오프라인 대역 — 키 없이도 형식·흐름 점검용 예시 키트 (v0.62 롱폼 분기)."""
    base = (hook.strip().splitlines()[0] if hook.strip()
            else transcript.strip().splitlines()[0][:18] if transcript.strip() else "이 영상")
    base = base[:24]
    if not is_shorts:  # 🖥 가로 롱폼 — Shorts 태그·쇼츠 표현 없이
        return {
            "titles": [f"{base} — 처음부터 끝까지 정리", f"{base}, 이것만 알면 됩니다",
                       f"{base} 완벽 가이드"],
            "title_tags": ["가이드", "꿀팁"],
            "description": (f"{base}를 순서대로 정리한 영상입니다.\n"
                            "목차 없이도 따라올 수 있게 흐름대로 설명했어요.\n"
                            "#꿀팁 #가이드 #정리"),
            "tags": ["가이드", "꿀팁", "튜토리얼", "정리", "강의", "하는법", "초보",
                     "설명", "추천", "자동화"],
            "keywords": ["가이드", "꿀팁", "하는법", "정리", "강의", "초보 가이드",
                         "추천", "자동화", "튜토리얼", "노하우"],
            "niche_keywords": [f"{base} 처음 하는 법", f"{base} 안될 때",
                               f"{base} 초보 가이드", f"{base} 순서"],
            "pinned_comment": f"{base}에서 제일 막히는 부분이 어디예요? 댓글로 알려주시면 다음 영상에서 다뤄볼게요 🙌",
            "hashtags": ["꿀팁", "가이드", "정리"],
            "category": "노하우/스타일",
            "tiktok": {"caption": f"{base} 핵심 정리 — 풀버전은 유튜브에! 🔍",
                       "hashtags": ["꿀팁", "가이드", "정리"]},
            "instagram": {"caption": f"{base} 완벽 정리 🎯\n풀버전은 프로필 링크에서!",
                          "hashtags": ["꿀팁", "가이드", "정리", "자동화"]},
            "naver_clip": {"title": f"{base} 하는 법 총정리",
                           "tags": ["꿀팁", "가이드", "정리", "하는법", "초보", "설명",
                                    "추천", "자동화", "튜토리얼", "노하우"],
                           "category1": "지식/교육", "category2": "노하우"},
            "threads": {"post": f"{base}, 이거 생각보다 별거 아니더라. 너넨 어떻게 함?",
                        "topic": "꿀팁"},
        }
    return {
        "titles": [f"{base} — 핵심만 30초 정리", f"{base}, 몰라서 손해봤던 것",
                   f"{base} 이렇게 하면 됩니다"],
        "title_tags": ["쇼츠", "꿀팁"],
        "description": (f"{base}의 핵심을 짧게 담았습니다.\n"
                        "처음 보는 분도 따라 할 수 있게 순서대로 정리했어요.\n"
                        "#Shorts #꿀팁 #정리"),
        "tags": ["쇼츠", "꿀팁", "튜토리얼", "정리", "요약", "하는법", "초보",
                 "가이드", "추천", "자동화"],
        "keywords": ["쇼츠", "꿀팁", "하는법", "정리", "요약", "초보 가이드",
                     "추천", "자동화", "튜토리얼", "노하우"],
        "niche_keywords": [f"{base} 하는 법", f"{base} 안될 때", f"{base} 초보",
                           f"{base} 30초 정리"],
        "pinned_comment": f"{base} 해보신 분 있나요? 한 줄 후기 남겨주세요 🙌",
        "hashtags": ["Shorts", "꿀팁", "정리"],
        "category": "노하우/스타일",
        "category_reason": "방법·팁을 알려주는 실용 영상이라 노하우/스타일이 적합합니다.",
        "tiktok": {"caption": f"{base}, 이것만 알면 끝 ✅ 저장해두고 따라 해보세요!",
                   "hashtags": ["꿀팁", "자기계발", "정리법", "라이프핵"]},
        "instagram": {"caption": (f"{base}, 이것만 알면 끝!\n\n"
                                  "핵심만 순서대로 담았어요. 저장해두고 하나씩 따라 해보세요 🙌"),
                      "hashtags": ["릴스", "꿀팁", "자기계발", "정리"]},
        "naver_clip": {"title": f"{base} 핵심 정리",
                       "tags": ["꿀팁", "정리", "하는법", "노하우", "자기계발",
                                "일상꿀팁", "생활정보", "초보가이드", "요약", "튜토리얼"],
                       "category1": "라이프", "category2": "생활 꿀팁"},
        "threads": {"post": (f"{base}, 다들 어렵게 생각하는데 핵심은 딱 하나임. "
                             "너넨 어떻게 함?"),
                    "topic": "꿀팁"},
    }
