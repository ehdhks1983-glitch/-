// v21.8.24.13 프롬프트 경량화 + 자동화 패키지 분류 보정 + 중복 방지 프롬프트 생성기
(function(){
  function safe(v, fallback='확인 필요'){ return String(v||'').trim() || fallback; }

  // v21.8.24.13: 이미지 생성 안정화를 위한 프롬프트 경량화 모드
  const PROMPT_SLIM_MODE_V13 = true;
  const PROMPT_MAX_BRIEF_V13 = 1500;
  const PROMPT_MAX_COPY_PLAN_V13 = 1600;
  const PROMPT_MAX_SPECS_V13 = 1800;

  const PROMPT_NOISE_PATTERNS_V13 = [
    /정격\s*세탁\s*:?\s*기\/?건조기/gi,
    /생활가전\s+청소기\s+계절가전\s+뷰티\/?헤어가전\s+건강가전\s+주방가전\s+데스크탑\s+모니터\s+휴대폰\s+태블릿PC\s+스마트워치\/?밴드\s+게임/gi,
    /회사소개\s+Investor\s+Relations\s+인재채용\s+입점/gi,
    /추천상품|함께\s*본\s*상품|다른\s*고객이\s*함께|카테고리\s*메뉴/gi,
    /전체\s*\/\s*패션의류[^\n]*/gi,
    /component\s*=\s*전체[^\n]*/gi
  ];

  function compactTextV13(value='', max=1200){
    let text = String(value || '')
      .replace(/\r/g, '')
      .replace(/\bpasted\b/gi, '')
      .replace(/━{4,}/g, '')
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    if(!text) return '';
    if(max && text.length > max) text = text.slice(0, max).trim() + '\n...';
    return text;
  }

  function cleanPromptSpecTextV13(value='', max=PROMPT_MAX_SPECS_V13){
    let text = String(value || '');
    PROMPT_NOISE_PATTERNS_V13.forEach(re => { text = text.replace(re, ' '); });
    const lines = text.split(/\n+/)
      .map(line => line.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .filter(line => !/(생활가전|청소기|계절가전|뷰티\/헤어가전|건강가전|주방가전|데스크탑|모니터|휴대폰|태블릿PC|스마트워치|회사소개|Investor Relations|인재채용|입점|추천상품|함께 본 상품|카테고리 메뉴)/i.test(line))
      .filter(line => !/^\[미확정 정보\]\s*소재, 정확한 구성 수량, 리뷰\/별점, 상세 설명, 제조국\s*$/i.test(line));
    return compactTextV13([...new Set(lines)].join('\n'), max);
  }

  function extractSectionCopyPlanV13(copyPlan='', section='', max=PROMPT_MAX_COPY_PLAN_V13){
    const text = compactTextV13(copyPlan, 6000);
    if(!text) return '';
    const sec = String(section || '').toUpperCase();
    const lines = text.split(/\n/);
    const hit = lines.findIndex(line => new RegExp(`\\b${sec}\\b|${sec}\\s*섹션|${sec}\\s*컷`, 'i').test(line));
    if(hit >= 0){
      const start = Math.max(0, hit - 4);
      const end = Math.min(lines.length, hit + 18);
      return compactTextV13(lines.slice(start, end).join('\n'), max);
    }
    return compactTextV13(text, max);
  }

  function buildSlimReferenceLockV13(product, analysis={}){
    const extra = analysis.extra_rule ? `\n- 카테고리 주의: ${analysis.extra_rule}` : '';
    return `[원본/팩트 잠금]
- 첨부된 원본 ${product} 사진의 형태·색상·비율·질감·구성품을 유지하세요.
- 원본에 없는 로고, 인증, 수상 배지, 구성품, 소품, 수치, 리뷰/별점, 효과를 만들지 마세요.
- 정보가 부족한 항목은 이미지에서 빼고, 보이는 제품/사용 장면 중심으로 설득하세요.
- 한글 오타, 더미 텍스트, sample/TEXT/샘플/예시/편집/lorem 금지.${extra}`;
  }

  function buildSlimQualityRulesV13(section){
    return `[핵심 제작 규칙]
- 한 섹션에는 한 메시지만: ${section} 역할에 맞는 정보만 사용.
- 모바일 1초 가독성: 메인 카피 크게, 서브/카드는 짧게.
- 카피는 고객 상황 → 이득 중심. 추상어/과장/조건문+질문문 금지.
- 상단 배지/소제목 캡슐은 넣지 말고 첫 문구는 메인 타이틀로 시작.
- 확인된 스펙은 배정된 섹션에서만 크게 표기하고, 다른 섹션에 반복하지 마세요.`;
  }

  function buildSlimCategoryAwareDedupBlockV13(section, contentPlan){
    const key = normalizeSectionV12(section);
    const block = contentPlan?.sectionBlocks?.[key];
    if(!block) return '';
    const main = block.main?.map(g => `${g.label}: ${g.examples}`).join('\n- ') || '대표 메시지/시각 흐름 중심. 구체 스펙은 배정 섹션에서만 사용.';
    const support = block.support?.map(g => g.label).join(', ') || '없음';
    const blocked = block.blocked?.slice(0, 6).map(g => `${g.label}→${g.assigned}`).join(', ') || '없음';
    return `[섹션별 정보 배정 - v21.8.24.13]
현재 상품군: ${contentPlan.categoryLabel || '일반상품'}
현재 섹션 전용:
- ${main}
보조 사용 가능: ${support}
반복 금지: ${blocked}
규칙: 현재 섹션 전용 정보가 아닌 스펙/수치/구성/주의사항/옵션은 큰 제목·큰 숫자·카드 제목으로 쓰지 마세요.`;
  }

  function summarizeDesignBlockV13(designBlock='', layoutBlock=''){
    const design = compactTextV13(designBlock, 900);
    const layout = compactTextV13(layoutBlock, 450);
    return `${layout ? layout + '\n\n' : ''}${design ? design : ''}`.trim();
  }


  const BANNED_COPY_PHRASES = ['첫인상','단정함','비즈니스 무드','깔끔한 인상'];
  const BANNED_COPY_RULE_BLOCK = `[카피 금지어/대체 규칙 - 반드시 준수]
이미지 안 문구와 헤드라인에 다음 표현을 쓰지 마세요: ${BANNED_COPY_PHRASES.join(', ')}.
대체 방향:
- 첫인상 → 꺼내는 순간 / 전달의 순간 / 손끝의 완성도
- 단정함 → 정돈된 형태 / 차분한 균형 / 절제된 디자인
- 비즈니스 무드 → 업무 자리 / 미팅 자리 / 상담 자리
- 깔끔한 인상 → 흐트러짐 없는 보관 / 정리된 전달감 / 정돈된 사용감
추상어보다 링크에서 확인된 스펙, 제품 디테일, 실제 사용 상황을 우선하세요.`;

  // v21.8.24.58: 카피 자연스러움 규칙(단일 출처, 한 곳 관리). buildCopyPlan(2단계)·컴팩트 이미지 프롬프트 양쪽에서 참조.
  // 어색한 한국어("명함, 섞어두지 마세요"처럼 대상-단어 불일치/모호) 방지가 목적. 카피 구조(메인/서브/카드)·길이는 그대로 유지.
  const COPY_OBJECT_WORD_EXAMPLES = '명함은 "섞다"가 아니라 "뒤섞이다 / 구겨지다 / 흐트러지다 / 찾기 힘들다"처럼 실제로 쓰는 표현';
  const COPY_QUALITY_RULES = `[카피 자연스러움 규칙 - 반드시 준수]
1. 소비자가 실제 쓰는 자연스러운 한국어만. 번역투·AI티·어색한 단어 조합 금지.
2. 단어가 대상과 안 맞으면 쓰지 마세요(대상-동사/표현 불일치 금지). 예: ${COPY_OBJECT_WORD_EXAMPLES}.
3. 추상·모호한 '느낌말' 금지 — 무엇이 어떻게 달라지는지 구체적으로. 한 번 읽고 장면이 안 그려지면 탈락.
   나쁜 예(실제로 어색했던 것): "흐름이 달라집니다" / "더 급해집니다" / "매끄러워집니다" / "완성도가 올라갑니다"(무엇이? 모호).
   좋은 예: "명함 찾느라 가방 안 뒤져요" / "건넬 때 바로 꺼냅니다" / "구겨진 명함은 안 줍니다".
4. pain point는 강하게 찌르되 자연스럽게. 과장·미확인 수치 금지.
5. 메인 6~16자 / 서브 14~26자 한 줄 구조 유지.
6. 제품 맥락에 맞는 감정 후킹 사용(예: 명함 케이스 → 미팅 자리·꺼내는 순간·전달의 완성도 같은 비즈니스 맥락). 단 '첫인상' 등 금지어는 직접 쓰지 말고 그 의미만 살릴 것.
7. 자가 점검: 각 문구를 확정하기 전에 "한국 사람이 읽고 바로 이해되는가 / 막연하지 않고 장면이 그려지는가"를 스스로 확인하고, 어색하면 더 쉽고 구체적인 말로 고친 뒤 확정.`;
  const COPY_QUALITY_RULES_SHORT = '쉽고 자연스러운 일상 한국어만(번역투·AI티·어색한 조합 금지). 추상·모호한 느낌말 금지("흐름이 달라집니다"✗) → 무엇이 어떻게 좋아지는지 구체적으로("명함 안 구겨져요"✓). 대상에 안 맞는 단어 금지(명함=섞다✗→뒤섞이다✓).';
  // v21.8.24.82: 섹션마다 같은 특징(고리 등)만 반복/헤드라인 중복되던 문제 →
  //  카피 쓰기 전에 '강점 목록 추출 → 주된 용도 필수 → 섹션에 겹치지 않게 1포인트씩 배정' 하도록 강제하는 config.
  const COPY_MESSAGE_MAP_RULES = `────────────────────
[0단계 - 섹션별 메시지 지도 (카피 쓰기 전에 반드시 먼저)]
────────────────────
카피를 한 줄도 쓰기 전에, 먼저 아래 '메시지 지도'를 정하라.
1) 강점 목록: 이 제품이 '실제로 해주는 것(효과·기능)'을 뽑아라.
   ★주의: '언제·어디서 쓰나'(출근 전·중요한 날·현관/신발장 보관 등 사용 타이밍·장소)는 강점이 아니다.
   이런 '사용 상황·보관' 류 메시지는 전부 합쳐 '최대 1개 섹션'까지만. 나머지는 '제품이 해주는 효과/기능'으로 채워라.
2) ★주된 효과(필수 커버): 이 상품군의 대표 효과를 반드시 '한 섹션이 효과 중심'으로 다뤄라.
   예) 구두약=광택·검은색 복원·스크래치 커버 / 화장품=발색·지속·피부 변화 / 우산=강풍·방수 / 청소용품=때 제거 / 명함케이스=구겨짐 방지·바로 꺼냄.
   가능하면 '쓰기 전 → 쓴 후(Before→After)'의 변화로 보여줘라(예: 칙칙한 앞코 → 다시 검고 또렷하게).
3) 겹치지 않게 배정: 각 섹션에 강점 목록에서 '서로 다른' 포인트를 하나씩. ★한 섹션 = 한 포인트, 같은 포인트 두 섹션 금지.
4) ★의미 중복 금지(매우 중요): 두 섹션이 '거의 같은 말'이면(예: 둘 다 "보관해두고 꺼내 쓰세요") 무조건 다른 포인트로 다시 배정하라. 표현만 바꾼 같은 메시지도 금지.
5) 헤드라인 중복 금지: 비슷한 헤드라인이 2개 이상 나올 것 같으면 포인트를 다시 배정하라.
6) ★한 특징 쏠림 금지(매우 중요): 부차 특징 하나(걸이·고리·가방에 걸기·색상·디자인 등)나 같은 소재(예: '가방')가 '3개 섹션 이상'에 반복되면 실패다.
   부차 특징은 '최대 1개 섹션'만. 우산이라면 '강풍에 안 뒤집힘·원터치 자동개폐·이중 방풍 창살' 같은 주된 효과가 반드시 섹션을 차지해야 한다.
   → 배정을 끝낸 뒤, 같은 단어(가방·걸이·고리 등)가 3섹션 이상 등장하지 않는지 세어보고, 넘으면 다른 강점으로 다시 배정하라.
→ 각 섹션의 '· 배정 포인트:'에 그 섹션이 맡은 포인트를 적고, 카피는 그 포인트만 다룬다. 다른 포인트로 새지 마라.
→ 자가점검: 섹션들을 모아 읽었을 때 '제품이 뭘 해주는지(주된 효과)'가 보이는가? '챙기세요/보관하세요/걸어두세요'만 반복되면 실패 — 효과 섹션을 넣어 다시 짜라.`;

  // v21.8.24.93: '모든 섹션이 카드 3개'라 이미지가 획일화되던 문제 → 섹션 유형별로 카피 구조 자체를 다르게 강제.
  const COPY_SECTION_STRUCTURE_RULES = `────────────────────
[섹션별 카피 구조 - ★섹션마다 다르게(카드 3개 반복 금지)]
────────────────────
모든 섹션을 '메인+서브+카드 3개'로 똑같이 만들지 마라. 그러면 이미지가 전부 똑같아진다.
섹션 유형에 따라 아래처럼 '구조' 자체를 다르게 작성하라(카드 개수가 0개인 섹션도 있어야 정상).
- HERO: 메인 + 서브 + 짧은 포인트 2개(헤드만, 설명 짧게/생략 가능). 강한 첫 후크 하나.
- PROBLEM/PAIN: 메인 + 서브 + 고객 불편 '문장' 2~3개(카드 헤드/설명 형식 말고, 짧은 공감 문장). 제품 자랑 금지.
- SOLUTION: 메인 + 서브 + 사용 흐름 2~3스텝(걸고/꺼내고/쓰고 식의 동사형 장면).
- USP/BENEFIT/FEATURE: 메인 + 서브 + 차별/효익 카드 2~3개(여기는 카드 OK).
- DETAIL/SPEC: 메인 + 서브 + 부분 라벨 2~3개(소재/마감/부분 명칭 — 카드보다 콜아웃 라벨 톤).
- SCENE/USAGE/LIFESTYLE: 메인 + 서브 + 상황 2~3개(언제/어디서 쓰는 장면).
- FAQ/TRUST: 메인 + 서브 + Q&A 2~3개(질문→짧은 답, 카드 아님).
- CTA: 메인 + 서브 + 구매 이유 압축(카드 0~2개, 적게). 마지막은 기능 말고 '구매 후 편해지는 감정'.
→ '· 이미지 안 카드 카피:'에는 위 유형에 맞는 항목을 넣되, PROBLEM처럼 카드가 안 맞는 섹션은 '카드 없음'이라고 적고 그 대신 위 형식(문장/스텝/Q&A)을 써라.
→ 섹션 2개 이상이 같은 문장 구조·같은 카드 구성이면 다시 작성하라.`;

  // v21.8.24.93: 카피가 '기능 설명문'으로 흐르고 후킹이 약하던 문제 → 생활장면형 + 후킹 후보선택 강제.
  const COPY_HOOK_RULES = `────────────────────
[후킹·자연스러움 - ★기능 설명 금지, 생활 장면으로]
────────────────────
1. 제품 특징을 그대로 설명하지 마라. 구매자가 '자기 상황'을 떠올리게 만들어라.
   나쁨: "손잡이에 걸기 쉽게" → 좋음: "가방에 툭 걸어두기"
   나쁨: "고급스러운 디자인" → 좋음: "매일 봐도 부담 없는"
   나쁨: "뛰어난 내구성" → 좋음: "자주 써도 쉽게 안 무너지게"
2. 딱딱한 설명 어미 금지: "~제공합니다 / ~가능합니다 / ~도와줍니다 / ~해드립니다 / ~로 구성".
3. 추상어 금지: 편리한·고급스러운·프리미엄·스마트한·완벽한·다양한·뛰어난·깔끔한(단독).
4. ★메인 카피는 후보를 머릿속으로 2~3개 만들고, 그중 '한국인이 1초에 멈춰 보는 가장 후킹 강한 것 하나'만 최종 출력하라(후보는 출력하지 말 것).
5. 섹션마다 문장 톤을 다르게: HERO=강한 후크 / PROBLEM=공감 / SOLUTION=장면 / USP=비교 / CTA=구매 후 감정.
6. 같은 단어·같은 문형이 2개 섹션 이상 반복되면 다시 써라.
7. ★플랫폼명/판매처/SEO 태그 금지: "도매꾹·도매매·쿠팡·스마트스토어·네이버·11번가" 같은 판매처 이름, "[도매꾹]·[무료배송]·[특가]" 같은 대괄호 태그, "디자인 특허등록 제품·강풍 비바람 강한·10k 이중창살" 같은 검색용 키워드 나열을 메인/서브/카드/제품명 어디에도 쓰지 마라. 제품명을 넣을 땐 짧고 자연스러운 이름만(예: "카라비너 자동우산").
8. ★HERO(첫 섹션) 메인 카피 규칙 - 가장 중요: 첫 화면은 0.5초 안에 '뭐가 좋은지' 또는 '내 얘기네'가 꽂혀야 한다.
   - 알맹이 없는 마무리·상투어 금지: "~다르게 / ~특별하게 / 새로운 시작 / 당신을 위한 / 품격 / 그 이상 / 차원이 다른 / 일상의 변화". (정보량 0)
   - 반드시 둘 중 하나로 써라:
     (A) 핵심 이득을 한 마디로 — 예: "바람 불어도 안 뒤집혀요", "한 손으로 펴고 접어요"
     (B) 구매자의 그 순간 상황 — 예: "또 뒤집힌 우산", "비 오는 날이 늘 짐이었다면"
   - 나쁨: "비 오기 전부터 다르게"(무슨 제품인지·뭐가 좋은지 안 보임) → 좋음: "바람 불어도 끄떡없어요".`;

  // v21.8.24.92: 카피 기획서 자동 검증(린트) — ChatGPT에게 검수를 '시키기만' 하던 것을 코드가 직접 검사.
  // 위반이 나오면 content.js가 위반 목록을 지시문으로 넣어 자동 재기획 1회를 돌린다(사람 개입 0).
  function listPlanSectionsV92(copyPlan){
    const text = String(copyPlan || '');
    const blocks = text.split(/\n(?=\[?\s*섹션\s*\d)/).filter(b => /섹션\s*\d/.test((b.split('\n')[0] || '')));
    return blocks.map(b => {
      const head = (b.split('\n')[0] || '').trim();
      const m = head.match(/섹션\s*(\d+)\s*[-–—]?\s*([^\]\n]*)/);
      const get = (labels) => { for(const l of labels){ const r = b.match(new RegExp('·?\\s*' + l + '\\s*[:：]\\s*([^\\n]+)')); if(r && r[1].trim()) return r[1].trim(); } return ''; };
      let point = get(['배정 포인트', '배정포인트']);
      if(!point){ const pm = b.match(/배정\s*포인트\s*[:：]\s*\n\s*([^\n·]{2,60})/); if(pm) point = pm[1].trim(); }
      const main = get(['메인 카피', '메인카피', '메인']);
      const sub = get(['서브 카피', '서브카피', '서브']);
      const cards = []; const cardRe = /헤드\s*[:：]\s*([^\/\n]+?)\s*\/\s*설명\s*[:：]\s*([^\n]+)/g; let cm;
      while((cm = cardRe.exec(b)) !== null && cards.length < 3) cards.push({ head: cm[1].trim(), desc: cm[2].trim() });
      return { num: m ? parseInt(m[1], 10) : 0, role: ((m && m[2]) || '').trim(), point, main, sub, cards };
    });
  }
  function validateCopyPlanV92(copyPlan, productName){
    const secs = listPlanSectionsV92(copyPlan);
    const violations = [];
    if(secs.length < 2) return { ok: true, sections: secs.length, violations, note: '섹션 2개 미만 — 검증 생략' };
    const norm = s => String(s || '').replace(/[\s,.!?·…'"“”()\[\]]+/g, '');
    // 1) 메인 카피가 같은 말로 시작(중복 헤드라인)
    for(let i = 0; i < secs.length; i++) for(let j = i + 1; j < secs.length; j++){
      const a = norm(secs[i].main), b = norm(secs[j].main);
      if(a && b && (a === b || (a.length >= 4 && b.length >= 4 && a.slice(0, 4) === b.slice(0, 4))))
        violations.push(`섹션${secs[i].num}과 섹션${secs[j].num}의 메인 카피가 같은 말로 시작("${secs[i].main}" / "${secs[j].main}") — 서로 다르게 다시 쓰기`);
    }
    // 2) 배정 포인트 중복(한 섹션 = 한 포인트 위반)
    for(let i = 0; i < secs.length; i++) for(let j = i + 1; j < secs.length; j++){
      const a = norm(secs[i].point), b = norm(secs[j].point);
      if(a && b && a === b)
        violations.push(`섹션${secs[i].num}과 섹션${secs[j].num}의 배정 포인트가 중복("${secs[i].point}") — 서로 다른 포인트로 재배정`);
    }
    // 3) 금지어(메인/카드 헤드의 단독 사용) + 클리셰/도망문구(어디든)
    const bannedHead = /(^|[\s,])(깔끔한|고급스러운|편리한|효율적인|스마트한|프리미엄|완벽한|최고의|강력한|다양한|뛰어난)([\s,]|$)/;
    const cliche = /첫인상|단정함|비즈니스 무드|깔끔한 인상/;
    const escapeRe = /확인\s*필요|미확인|상세페이지\s*참조|상품페이지\s*참고|판매\s*페이지\s*확인/;
    // v21.8.24.93: 딱딱한 설명 어미(상세페이지 카피답지 않음)
    const stiffEnding = /(제공합니다|가능합니다|도와줍니다|해드립니다|드립니다|입니다만|구성됩니다|향상시킵니다|선사합니다)/;
    // v21.8.24.95: 플랫폼명/대괄호 SEO 태그가 카피에 새어들면 잡는다
    const platformRe = /도매꾹|도매매|쿠팡|스마트스토어|11번가|지마켓|G마켓|옥션|위메프|티몬|\[[^\]]*\]/;
    secs.forEach(s => {
      const all = [s.main, s.sub, ...s.cards.map(c => c.head + ' ' + c.desc)].join(' | ');
      if(platformRe.test(all)) violations.push(`섹션${s.num}에 플랫폼명/대괄호 태그(도매꾹·쿠팡·[…] 등) — 이미지 카피에서 제거`);
      if(s.main && bannedHead.test(s.main)) violations.push(`섹션${s.num} 메인 카피에 금지어 단독 사용("${s.main}") — 구체적인 장면 표현으로 교체`);
      s.cards.forEach(c => { if(c.head && bannedHead.test(c.head)) violations.push(`섹션${s.num} 카드 헤드에 금지어("${c.head}") — 교체`); });
      if(cliche.test(all)) violations.push(`섹션${s.num}에 클리셰 표현(첫인상/단정함/비즈니스 무드/깔끔한 인상) — 실제 장면으로 교체`);
      if(escapeRe.test(all)) violations.push(`섹션${s.num}에 도망 문구(확인 필요/상세페이지 참조 류) — 그 항목은 빼고 확인된 내용만`);
      if((s.main && stiffEnding.test(s.main)) || (s.sub && stiffEnding.test(s.sub))) violations.push(`섹션${s.num}에 딱딱한 설명 어미(~제공/가능/도와줍니다 등) — 생활 장면형 구어체로 교체`);
      // v21.8.24.96: FAQ/TRUST 섹션에 '보면 바로 아는 당연한 질문'이 들어가면 잡는다(후킹 0)
      if(/FAQ|TRUST/i.test(s.role) || /FAQ|TRUST/i.test(s.point)){
        const obviousQ = /(고리|손잡이|색상|컬러|접(이|히)|버튼|자동)\s*인가요|있나요|되나요/;
        s.cards.forEach(c => { if(c.head && obviousQ.test(c.head)) violations.push(`섹션${s.num}(FAQ) 당연한 질문("${c.head}") — 내구성/사용한계/관리/실패경험 같은 진짜 구매불안 질문으로 교체`); });
      }
      // 4) 길이 초과(여유 포함: 메인16→18, 서브26→30, 헤드8→10, 설명16→20)
      if(s.main && s.main.length > 18) violations.push(`섹션${s.num} 메인 카피가 너무 김(${s.main.length}자, 기준 16자) — 짧게`);
      if(s.sub && s.sub.length > 30) violations.push(`섹션${s.num} 서브 카피가 너무 김(${s.sub.length}자, 기준 26자) — 짧게`);
      s.cards.forEach(c => {
        if(c.head && c.head.length > 10) violations.push(`섹션${s.num} 카드 헤드가 너무 김("${c.head}", 기준 8자)`);
        if(c.desc && c.desc.length > 20) violations.push(`섹션${s.num} 카드 설명이 너무 김("${c.desc}", 기준 16자)`);
      });
    });
    // 5) 카드 획일화 — 거의 모든 섹션이 카드 3개면(섹션 구조가 안 나뉜 것) 위반
    const card3 = secs.filter(s => s.cards.length >= 3).length;
    if(secs.length >= 5 && card3 >= secs.length - 1)
      violations.push(`거의 모든 섹션(${card3}/${secs.length})이 카드 3개 구조 — 이미지가 똑같아짐. PROBLEM은 공감 문장, SOLUTION은 스텝, HERO는 포인트 2개 등 유형별로 구조를 다르게`);
    // 6) v21.8.24.99: HERO 후킹 약함 — 첫 메인 카피가 알맹이 없는 상투어/추상 마무리면 잡는다.
    //    첫 화면은 '핵심 이득' 또는 '구매자 상황'으로 1초 안에 멈추게 해야 한다.
    {
      const hero = secs.find(s => /HERO/i.test(s.role) || /HERO/i.test(s.point)) || secs[0];
      if(hero && hero.main){
        const m = hero.main;
        const vapidEnding = /(다르게|특별하게|특별함|남다른|새로워요|시작이에요|시작합니다|시작됩니다)\s*$/;
        const vapidPhrase = /당신을\s*위한|품격|그\s*이상|차원이\s*다른|일상의\s*변화|새로운\s*(경험|일상|시작)|특별한\s*(하루|일상|순간)|특별한\s*당신/;
        if(vapidEnding.test(m) || vapidPhrase.test(m))
          violations.push(`섹션${hero.num}(HERO) 메인 카피가 추상적 후크("${m}") — 첫 화면은 '핵심 이득(예: 바람에도 안 뒤집혀요)'이나 '구매자 상황(예: 또 뒤집힌 우산)'으로 1초 안에 멈추게 하세요`);
      }
    }
    // 7) v21.8.24.98: 한 특징/소재에 쏠림 감지 — 같은 핵심 단어가 섹션 과반에 반복되면
    //    '주된 효과(핵심 기능)'를 놓치고 부차 특징(걸이·가방·색상 등) 하나에 쏠린 전형적 실패다(우산인데 방풍·자동개폐 0섹션).
    //    제품명에 들어간 단어(=그 제품의 정체성)는 쏠림 대상에서 제외한다.
    if(secs.length >= 4){
      // 한국어 토큰은 조사가 붙어('가방에/가방이나/가방') 같은 단어가 다른 토큰이 된다 → 앞 2음절 어간으로 묶는다.
      const STOP = /^(그리고|하지만|그래서|그런데|이제|오늘|매일|하루|이틀|순간|상황|장면|생각|마음|느낌|기분|사용|모습|정도|이런|저런|그런|이렇|저렇|당신|우리|이거|저거|그거|여기|저기|거기|바로|진짜|정말|아주|매우|항상|가끔|모두|전부|살짝|조금|한번|다시|먼저|이미|아직|계속|보기|때문|준비|시작|하나|위해|동안|만큼|보다|처럼|그냥|언제|어디|무엇|어떻|그날|그때)$/;
      const nameToks = String(productName || '').match(/[가-힣]{2,}/g) || [];
      const inName = (k) => nameToks.some(nt => nt.includes(k) || k.includes(nt));
      const sectionSets = secs.map(s => {
        const text = [s.main, s.sub, s.point, ...s.cards.flatMap(c => [c.head, c.desc])].join(' ');
        const keys = new Set();
        (text.match(/[가-힣]{2,}/g) || []).forEach(tok => {
          const k = tok.slice(0, 2);          // 앞 2음절 어간(조사 차이 흡수)
          if(STOP.test(k) || inName(k)) return;
          keys.add(k);
        });
        return keys;
      });
      const freq = {};
      sectionSets.forEach(set => set.forEach(k => { freq[k] = (freq[k] || 0) + 1; }));
      let top = '', topN = 0;
      Object.keys(freq).forEach(k => { if(freq[k] > topN){ topN = freq[k]; top = k; } });
      const threshold = Math.max(3, Math.ceil(secs.length * 0.6));
      if(top && topN >= threshold)
        violations.push(`'${top}~'가 ${topN}/${secs.length}개 섹션에 반복 — 한 특징/소재에 쏠렸습니다. 그 특징은 1개 섹션만 다루고, 나머지는 이 상품군의 '주된 효과(핵심 기능, 예: 우산=강풍에 안 뒤집힘·원터치 자동개폐)'를 최소 1섹션 포함해 서로 다른 강점으로 재배정하세요`);
    }
    return { ok: violations.length === 0, sections: secs.length, violations };
  }

  const IMAGE_QUALITY_RULE_BLOCK = `[상세페이지 이미지 퀄리티 강화 규칙 - 최우선]
이 이미지는 단순 제품 홍보 배너가 아니라 한국 이커머스 모바일 상세페이지의 한 섹션입니다.
예쁜 장식보다 구매자가 다음 섹션까지 스크롤하게 만드는 설득 흐름을 우선하세요.

[1섹션 1메시지]
- 한 이미지에는 하나의 핵심 메시지만 담으세요.
- HERO는 구매 이유 하나, PROBLEM은 고객 고민 하나, SOLUTION은 해결 방식 하나, DETAIL은 실제 디테일 하나, CTA는 행동 유도 하나만 강조하세요.
- 제품명, 장점 여러 개, 스펙, 사용법, CTA를 한 장에 모두 넣지 마세요.

[제품 사실성]
- 첨부 원본 제품 사진의 색상, 형태, 소재감, 비율, 구성품, 로고/라벨/마킹 위치를 유지하세요.
- 원본에 없는 구성품, 기능, 인증마크, 수상 배지, 리뷰, 새 로고를 추가하지 마세요.
- 배경과 연출은 바꿀 수 있지만 제품 자체는 원본과 일치해야 합니다.

[모바일 가독성]
- 모바일 화면에서 1초 안에 메인 카피가 읽히도록 가장 크게 배치하세요.
- 서브 카피는 짧게, 카드 헤드는 최대 3개까지만 사용하세요.
- 작은 본문 텍스트를 많이 넣지 말고, PC형 가로 배너처럼 만들지 마세요.

[카피 사용]
- 카피 기획서가 있으면 현재 섹션의 메인 카피, 서브 카피, 카드 카피를 최우선으로 사용하세요.
- 새로운 카피를 마음대로 만들지 마세요.
- 단, 이미지 안에서 너무 길면 의미를 유지한 채 더 짧게 줄이세요.
- 배지 문구는 내부 참고용입니다. 이미지 상단에 소제목/캡슐 배지로 표시하지 마세요.

[섹션별 차별화]
- 모든 섹션이 HERO처럼 보이면 실패입니다.
- 현재 섹션 역할에 맞게 구도와 비주얼 우선순위를 바꾸세요.
- HERO는 제품 전체와 구매 이유, PROBLEM은 고객 고민 장면, SOLUTION은 해결 전환, USP는 차별점 카드, DETAIL은 클로즈업, TRUST/FAQ는 불안 해소, CTA는 최종 행동 유도 중심입니다.

[실패 방지]
- 스펙만 나열하지 마세요.
- 글자를 작게 많이 넣지 마세요.
- 카피가 추상적이면 실패입니다.
- 배경 장식이 제품보다 튀면 실패입니다.
- 한글 오타가 있으면 실패입니다.`;

  const PRODUCT_INFO_INTEGRITY_BLOCK = `[제품 정보 무결성 규칙 - 이미지 안 문구 최우선]
- 확인되지 않은 리뷰 수, 별점, 판매량, 인증, 수상, 효과, 소재명, 전체 사이즈 범위를 절대 만들지 마세요.
- "상세페이지 참조", "상세페이지 정보 참조", "상품페이지 참고", "판매 페이지 확인", "확인 필요", "미확인" 같은 도망 문구를 이미지 안에 넣지 마세요.
- 정보가 부족하면 그 항목을 이미지에서 빼고, 원본 사진에서 보이는 착용컷/형태/색상/라인/구성/사용 장면 중심으로 설득하세요.
- 특정 옵션 하나만 확인된 경우 전체 옵션처럼 단정하지 마세요. 예: 2XL만 보이면 "사이즈는 2XL 기준" 대신 착용컷·길이감·커버 범위처럼 보이는 정보로 전환하세요.
- 사이즈, 소재, 리뷰, 별점, 구성품은 사용자 입력/링크 정보/원본 이미지에서 명확히 확인된 경우에만 이미지 문구로 사용하세요.`;


  // v21.8.24.10: 90점 목표 구매전환 카피 엔진
  const SALES_COPY_90_GLOBAL_BLOCK = `[90점 상세페이지 카피 엔진 - 최우선]
이 섹션의 문구는 예쁜 설명이 아니라 구매 결정을 돕는 판매 문구여야 합니다.
반드시 아래 순서 중 현재 섹션에 맞는 하나를 선택해 카피를 만드세요.

[구매전환 흐름]
고객의 실제 불편 → 그 불편이 생기는 순간 → 이 제품으로 줄어드는 불편 → 구매 전 불안 해소 → 선택 이유

[기능을 효익으로 번역]
- 색상/소재/치수/구성 같은 사실을 그대로 쓰지 말고, 고객이 얻는 상황 이득으로 바꾸세요.
- 예: 색상 3가지 → 업무 자리와 취향에 맞춰 고르는 선택감
- 예: 슬림한 크기 → 가방·데스크·손 안에서 부담이 적은 휴대감
- 예: 수납량 → 명함과 카드를 따로 정리하는 준비감

[뻔한 문구 금지]
다양한 활용, 편안한 사용감, 깔끔한 디자인, 고급스러운 느낌, 실용적인 구성, 부담 없이 사용, 데일리 아이템, 만족도 높은 제품, 추천템 같은 추상 표현은 쓰지 마세요.
반드시 구체적 장면으로 바꾸세요. 예: 상담 전 꺼낼 때, 지갑 속에서 섞일 때, 물놀이 옷 고를 때, 출근 가방 속, 데스크 위.

[이미지 안 문구 길이]
- 메인 카피: 6~16자 권장, 최대 18자
- 서브 카피: 14~28자 권장, 최대 34자
- 카드 제목: 3~9자 권장
- 카드 설명: 10~22자 권장
- 긴 문장 2줄 이상 금지. 이미지 안 문구는 짧고 말하듯 자연스럽게.

[팩트 세이프]
확인되지 않은 기능성 표현은 절대 금지: 자석 내장, 방수, 천연가죽, 스크래치 방지, 내구성 우수, UV 차단, 속건, 냉감, 고탄력, 인증, 1위, 베스트, 리뷰 수, 별점.
확인된 사실만 판매 문구의 근거로 사용하세요.`;


  const KOREAN_COPY_GUARD_BLOCK = `[한국어 카피 문장 검수 - 반드시 준수]
이미지 안 문구는 문법적으로 자연스러운 한국어여야 합니다. 단어를 이어 붙인 조합형 문장은 실패입니다.

[절대 금지 문장 패턴]
- "찾느라 망설인 적 있나요"
- "필요한 순간 찾는다면"
- "꺼내느라 고민한 적 있나요"
- "사용하기 부담된다면"
- "고민했던 부분"
- "~한다면 ~한 적 있나요"처럼 조건문과 질문을 억지로 붙인 문장
- "~하기", "~하기 좋은"으로 끝나는 뻔한 제목 남발

[권장 문장 구조]
문제 공감 섹션은 질문형보다 단정형을 우선합니다.
- 문제 1줄 → 불편 1줄 → 해결 1줄
- 메인 카피와 서브 카피를 이어 읽었을 때 자연스러워야 합니다.
- 고객이 실제로 말할 법한 표현만 사용하세요.

[명함지갑 예시]
나쁜 예: "명함이 자꾸 섞인다면 / 필요한 순간 찾느라 망설인 적 있나요"
좋은 예: "지갑 속 명함이 / 자꾸 섞인다면"
좋은 예: "필요한 순간, / 바로 꺼내기 어렵습니다"
좋은 예: "명함이 섞이면 / 전달의 순간도 흐트러집니다"

[최종 확인]
이미지 안 문구를 만들기 전에 한 번 소리 내어 읽었을 때 어색하면 반드시 다시 쓰세요.`;

  const SALES_COPY_BANNED_WORDS = [
    '다양한 활용','편안한 사용감','깔끔한 디자인','고급스러운 느낌','실용적인 구성','부담 없이 사용','데일리 아이템','만족도 높은 제품','추천템','활용도 높은','프리미엄 감성','완벽한 선택','누구나 만족'
  ];

  const SECTION_COPY_ROLES_90 = {
    HERO:'첫 3초 안에 타겟과 구매 이유를 꽂습니다. 상품명 반복보다 고객이 달라지는 순간을 먼저 말하세요.',
    PROBLEM:'고객이 실제로 겪는 불편을 말합니다. 제품 자랑보다 지갑 속, 여행 전, 업무 전 같은 상황 공감을 우선하세요.',
    PAIN_POINT:'업무/시간/준비 과정에서 생기는 번거로움을 구체적으로 보여주세요.',
    SOLUTION:'고민 다음에 제품이 해답으로 등장합니다. 그래서 어떤 불편이 줄어드는지 한 문장으로 말하세요.',
    OVERVIEW:'제품 전체를 보여주되 구성 나열이 아니라 한 번에 이해되는 구매 이유로 정리하세요.',
    DETAIL:'보이는 디테일을 고객 효익으로 번역하세요. 재질/마감/라인/형태가 실제로 어떤 사용 장면에 좋은지 말하세요.',
    MATERIAL:'확인된 소재만 사용하고, 소재가 주는 인상이나 관리 포인트를 짧게 설명하세요.',
    SIZE:'크기 수치를 고객이 이해할 장면으로 바꾸세요. 손 안, 가방 속, 데스크 위 같은 비교를 사용하세요.',
    SPEC:'확인된 스펙만 표기합니다. 감성 문구보다 정확하고 신뢰감 있게.',
    COLOR_SIZE:'옵션은 색상명 나열로 끝내지 말고, 어느 분위기/상황에 어울리는지 짧게 연결하세요.',
    STORAGE:'수납/보관 불편이 어떻게 줄어드는지 보여주세요. 찾기 쉬움, 섞임 감소, 꺼내기 쉬움 같은 장면.',
    LIFESTYLE:'제품이 쓰이는 실제 순간을 보여주세요. 상담 자리, 출근 가방, 데스크 위처럼 생활 장면 중심.',
    GIFT:'선물받는 사람의 상황을 떠올리게 하세요. 처음 명함을 준비하는 사람, 매일 명함을 쓰는 사람처럼.',
    FAQ:'구매 전 망설임을 줄입니다. 확인된 정보만 짧게 답하고, 모르는 것은 이미지에 넣지 마세요.',
    CTA:'마지막 선택 이유를 한 문장으로 압축합니다. 과한 할인/긴급 표현보다 지금 사도 되는 이유를 말하세요.',
    FIT:'착용 전 불안, 노출 부담, 활동 장면을 고객 언어로 풀어주세요.',
    FABRIC:'확인된 소재 정보가 없으면 소재명 대신 원본에서 보이는 착용/표면 인상만 말하세요.',
    WEAR_SCENE:'물놀이, 여행, 운동, 외출 등 실제 착용 장면을 먼저 말하세요.',
    COMPONENTS:'구성품을 나열하지 말고, 준비가 쉬워지는 이유로 바꾸세요.',
    USAGE:'사용법을 행동 동사로 짧게 보여주세요.',
    BENEFIT:'장점 3개를 고객 이득 3개로 바꾸세요.',
    COMPARISON:'일반 불편과 이 제품의 선택 이유를 과장 없이 대비하세요.',
    BEFORE_AFTER:'효과 보장 없이 정리감, 준비감, 사용 인상 차이를 보여주세요.'
  };

  const CATEGORY_COPY_STRATEGY_90 = {
    fashion_accessory:`[품목별 카피 전략 - 패션잡화/명함지갑]
핵심 고객: 상담, 계약, 미팅, 출근 전 명함을 꺼내는 순간이 신경 쓰이는 사람.
주요 고민: 지갑 안에서 명함이 구겨짐 / 카드와 명함이 섞임 / 필요할 때 바로 찾기 어려움 / 꺼낼 때 첫 순간이 신경 쓰임 / 너무 큰 케이스는 부담스러움.
구매 이유: 명함을 따로 정리 / 손에 잡히는 슬림한 크기 / 블랙·블루·골드 선택 / 업무 자리에서 자연스럽게 사용 / 작은 선물로 부담 적음.
권장 표현: 지갑 속에 구겨진 명함, 꺼내는 순간까지, 상담 전 준비, 손 안에 들어오는 정리감, 명함은 따로, 업무 자리에서 자연스럽게.
주의: 첫인상, 단정함이라는 단어를 직접 반복하지 말고 꺼내는 순간, 전달의 순간, 정돈된 형태로 바꾸세요. 자석 내장 등 미확인 기능 금지.`,
    fashion_clothing:`[품목별 카피 전략 - 의류/래쉬가드]
핵심 고객: 워터파크, 수영장, 바캉스에서 노출 부담은 줄이고 편하게 입을 옷을 찾는 사람.
주요 고민: 몸매가 너무 드러날까 걱정 / 상하의 따로 맞추기 번거로움 / 너무 튀는 색상은 부담 / 큰 사이즈 착용감 불안.
구매 이유: 블랙계열 안정감 / 세트 구성으로 코디 고민 감소 / 화이트블랙 배색 / 물놀이 전 빠른 준비.
권장 표현: 부담은 줄이고 물놀이는 편하게, 코디 고민 없이 한 세트로, 블랙 라인으로 차분하게, 여행 전 빠르게 준비.
주의: UV 차단, 속건, 냉감, 고탄력, 보정 효과를 확인 없이 말하지 마세요.`,
    fitness:`[품목별 카피 전략 - 운동/홈트]
핵심 고객: 집에서 운동하고 싶지만 장비와 공간이 부담스러운 사람.
주요 고민: 사용법이 어려움 / 운동기구가 큼 / 꾸준히 하기 부담 / 구성품이 헷갈림.
구매 이유: 공간 부담 적음 / 구성품 확인 쉬움 / 동작을 단계로 이해 / 보관 가능.
권장 표현: 집에서도 루틴을 시작, 문에 고정하고 바로 당기기, 운동 준비를 간단하게, 보관까지 가볍게.
주의: 근력 향상 보장, 칼로리, 재활/치료성 표현 금지.`,
    digital_automation:`[품목별 카피 전략 - 자동화/디지털]
핵심 고객: 반복 홍보와 콘텐츠 작업을 줄이고 싶은 사장님/운영자.
주요 고민: 매일 작성이 번거로움 / 세팅이 어려움 / 결과 확인이 복잡함 / 시간 소모.
구매 이유: 작업 흐름 단순화 / 기능별 자동화 / 결과물 관리 / 초보자도 따라가는 단계.
권장 표현: 반복 작업은 줄이고, 흐름은 더 단순하게, 입력부터 결과까지 한 화면으로, 매일 하던 일을 더 쉽게.
주의: 수익 보장, 상위노출 보장, 무조건 자동화 같은 과장 금지.`,
    living:`[품목별 카피 전략 - 생활용품]
핵심 고객: 매일 반복되는 작은 불편을 줄이고 싶은 사용자.
주요 고민: 정리 어려움 / 보관 불편 / 세척 부담 / 사용 전후 차이가 궁금함.
구매 이유: 생활 속 불편 감소 / 사용 전후가 보임 / 관리가 쉬움.
권장 표현: 매일 거슬리던 부분부터, 꺼낼 때 더 쉽게, 정리되는 순간이 보이게.`,
    furniture:`[품목별 카피 전략 - 가구/공간]
핵심 고객: 공간 분위기와 실사용 편의를 같이 보는 사람.
주요 고민: 공간에 안 어울릴까 불안 / 크기감 불안 / 소재와 배치감 궁금.
구매 이유: 공간 무드 개선 / 배치 장면 확인 / 디테일 확인.
권장 표현: 공간에 자연스럽게, 앉는 자리의 분위기까지, 놓는 순간 달라지는 코너.`
  };

  function getSectionCopyRole(section){ return SECTION_COPY_ROLES_90[section] || '현재 섹션의 목적 하나만 정하고, 고객 상황과 구매 이유를 짧고 구체적으로 연결하세요.'; }
  function getCategoryCopyStrategy(analysis={}){ return CATEGORY_COPY_STRATEGY_90[analysis.key] || CATEGORY_COPY_STRATEGY_90[analysis.template_type] || `[품목별 카피 전략 - 일반]
고객이 이 상품을 구매하기 직전에 느끼는 불안을 먼저 찾고, 확인된 제품 정보로 그 불안을 줄여주세요.
문구는 제품 설명보다 고객 상황 중심으로 작성하세요.`; }
  function buildSalesCopyQualityBlock(section, analysis={}, data={}){
    const banned = SALES_COPY_BANNED_WORDS.join(', ');
    return `[구매전환 카피 품질 기준 - 90점 목표] ⚠️
${SALES_COPY_90_GLOBAL_BLOCK}

${getCategoryCopyStrategy(analysis)}

[현재 섹션 카피 역할]
${getSectionCopyRole(section)}

${KOREAN_COPY_GUARD_BLOCK}

[생성 전 카피 자가검수]
1. 이 문구가 고객의 실제 상황을 건드리는가?
2. 기능을 그대로 설명하지 않고 고객 효익으로 바꿨는가?
3. ${banned} 같은 뻔한 표현을 쓰지 않았는가?
4. 확인되지 않은 기능/소재/효과를 말하지 않았는가?
5. 이미지 안에서 한눈에 읽힐 만큼 짧은가?
6. 같은 상세페이지의 다른 섹션과 카피 톤이 반복되지 않는가?
위 6개 중 하나라도 실패하면 카피를 다시 짧고 구체적으로 고쳐서 이미지에 넣으세요.`;
  }

  // v21.8.24.21: 기본(슬림) 모드용 전문가 카피 압축본. 풀모드의 90점 엔진/카테고리 전략/한국어 가드 핵심만
  // 짧게 담아, 이미지 생성 안정성을 해치지 않으면서도 "전문가가 쓴 상세페이지 문구"가 나오게 한다.
  function buildSlimSalesCopyBlockV13(section, analysis={}){
    const strat = CATEGORY_COPY_STRATEGY_90[analysis.key] || CATEGORY_COPY_STRATEGY_90[analysis.template_type] || '';
    // 카테고리 전략에서 '핵심 고객/주요 고민' 줄만 뽑아 한 줄로 압축
    const stratHook = strat ? strat.split('\n').filter(l=>/핵심 고객|주요 고민|구매 이유/.test(l)).slice(0,2).join(' ').slice(0,180) : '';
    return `[전문가 카피 규칙(요약) - 이미지 안 문구 최우선]
- 설득 흐름: 고객의 실제 불편 → 그 불편이 생기는 순간 → 이 제품으로 줄어드는 것 → 구매 이유. 사실(색/소재/치수)은 반드시 '고객 이득'으로 번역.
- 이번 섹션 역할: ${getSectionCopyRole(section)}${stratHook ? '\n- 품목 포인트: '+stratHook : ''}
- 길이: 메인 6~16자, 서브 14~26자, 카드제목 3~8자, 카드설명 6~16자. 카드는 2~3개. 한 섹션 한 메시지.
- ⚠️ 글자 최소화: AI는 한글이 많으면 철자가 깨집니다. 짧고 굵게, 긴 문장/작은 글자/빽빽한 텍스트 금지. 줄바꿈은 단어 중간에서 끊지 말 것.
- 금지어: 다양한 활용·편안한 사용감·깔끔한 디자인·고급스러운 느낌·실용적인 구성·데일리 아이템·추천템·첫인상·단정함·비즈니스 무드. 추상어 대신 구체 장면(상담 전, 지갑 속, 출근 가방, 물놀이 등).
- 자연스러운 한국어만. 단어 조합형/번역투 금지. 조건문+질문 억지결합 금지(예: "~한다면 ~한 적 있나요" 금지). 문제 공감은 단정형 우선.
- 확인된 사실만 사용: 미확인 수치·효능·인증·리뷰·별점·소재·전체 사이즈범위 금지.
- 같은 상세페이지 다른 섹션과 카피 톤/단어가 반복되면 실패. 메인=욕구, 서브=근거, 카드=확인 포인트로 역할 분리.`;
  }


  // v21.8.24.12: 카테고리 인식형 섹션 중복 방지 엔진
  // 핵심: 특정 상품(명함지갑)의 "사이즈"만 막는 것이 아니라, 상품군별 핵심 팩트 묶음을 섹션별로 배정합니다.
  const CATEGORY_FACT_GROUPS_V12 = {
    fashion_accessory: [
      {key:'identity', label:'제품 정체성/대표 구매 이유', examples:'축약 제품명, 대표 효익, 구매 순간', primary:['HERO'], support:['CTA']},
      {key:'pain', label:'고객 불편/구매 전 고민', examples:'섞임, 구겨짐, 찾기 어려움, 꺼낼 때의 민망함', primary:['PROBLEM','STORAGE'], support:['FAQ']},
      {key:'solution', label:'해결 방식/사용 이득', examples:'따로 정리, 바로 꺼냄, 작은 휴대감', primary:['SOLUTION','BENEFIT','STORAGE'], support:['CTA']},
      {key:'spec_capacity', label:'크기/수납량/확정 수치', examples:'가로·세로·폭, 수납량, 제조국처럼 확인된 숫자 정보', primary:['SPEC','SIZE'], support:['FAQ']},
      {key:'material_detail', label:'소재/마감/보이는 디테일', examples:'질감, 금속 포인트, 라운드 형태, 마감', primary:['DETAIL','MATERIAL'], support:['FAQ']},
      {key:'color_option', label:'색상/옵션', examples:'확인된 색상, 옵션별 분위기', primary:['COLOR_SIZE','COLLECTION'], support:['FAQ']},
      {key:'usage_scene', label:'사용 장면/타겟 상황', examples:'상담, 계약, 미팅, 출근 가방, 데스크 위', primary:['LIFESTYLE','GIFT','USAGE'], support:['CTA']},
      {key:'caution', label:'주의사항/구매 전 확인', examples:'습기·화기 주의, 혼합 보관 주의 등 확인된 주의사항', primary:['FAQ'], support:[]}
    ],
    fashion_clothing: [
      {key:'identity', label:'제품 정체성/대표 구매 이유', examples:'세트 구성, 착용 목적, 계절/활동 상황', primary:['HERO'], support:['CTA']},
      {key:'pain', label:'착용 전 고민', examples:'노출 부담, 핏 불안, 코디 번거로움', primary:['PROBLEM'], support:['FAQ']},
      {key:'fit', label:'핏/실루엣/착용감', examples:'루즈핏, 슬림핏, 기장감, 착용 장면', primary:['FIT','SIZE'], support:['WEAR_SCENE']},
      {key:'fabric', label:'소재/원단감', examples:'소재명, 두께, 촉감, 신축성은 확인된 경우만', primary:['FABRIC','MATERIAL','DETAIL'], support:['FAQ']},
      {key:'option', label:'색상/사이즈 옵션', examples:'확인된 색상, 확인된 사이즈 옵션, 옵션 선택 기준', primary:['COLOR_SIZE'], support:['FAQ']},
      {key:'scene', label:'착용 장면/스타일링', examples:'여행, 물놀이, 외출, 운동, 데일리 착용', primary:['WEAR_SCENE','LIFESTYLE'], support:['CTA']},
      {key:'care', label:'세탁/관리/주의사항', examples:'세탁법, 건조 주의, 소재 관리', primary:['CARE','FAQ'], support:[]}
    ],
    digital: [
      {key:'identity', label:'제품 정체성/대표 기능', examples:'무엇을 하는 제품인지, 첫 구매 이유', primary:['HERO'], support:['CTA']},
      {key:'pain', label:'사용 전 고민', examples:'스펙 이해 어려움, 호환성, 사용법 불안', primary:['PAIN_POINT','PROBLEM'], support:['FAQ']},
      {key:'feature', label:'핵심 기능', examples:'주요 기능, 버튼/모드/성능 차이', primary:['FEATURE'], support:['BENEFIT']},
      {key:'spec', label:'전원/용량/규격/모델 정보', examples:'전압, 소비전력, 용량, 크기, 무게, 모델명', primary:['SPEC'], support:['FAQ']},
      {key:'usage', label:'사용 흐름', examples:'설치, 연결, 작동, 관리 단계', primary:['USAGE','WORKFLOW'], support:['FAQ']},
      {key:'components', label:'구성품/패키지', examples:'본품, 케이블, 설명서, 포함 구성', primary:['PACKAGE','COMPONENTS'], support:['FAQ']},
      {key:'caution', label:'호환/주의/보증', examples:'호환 조건, 사용 주의, 보증 정보', primary:['FAQ','TRUST'], support:[]}
    ],
    digital_automation: [
      {key:'identity', label:'서비스/프로그램 정체성', examples:'어떤 반복 업무를 줄이는지', primary:['HERO'], support:['CTA']},
      {key:'pain', label:'업무 고민/시간 소모', examples:'반복 작성, 관리 어려움, 세팅 부담', primary:['PAIN_POINT'], support:['FAQ']},
      {key:'workflow', label:'작동 흐름', examples:'입력 → 처리 → 결과 → 관리', primary:['WORKFLOW'], support:['RESULT']},
      {key:'feature', label:'기능 범위', examples:'포함 기능, 버튼, 화면, 결과물', primary:['FEATURE'], support:['PACKAGE']},
      {key:'result', label:'결과 예시/운영 변화', examples:'작업 흐름 개선, 관리 편의', primary:['RESULT'], support:['CTA']},
      {key:'package', label:'구성/지원 범위', examples:'제공 프로그램, 설치, 교육, 업데이트', primary:['PACKAGE'], support:['FAQ']},
      {key:'caution', label:'제한/주의/보장 금지', examples:'상위노출·수익 보장 금지, 사용 조건', primary:['FAQ'], support:[]}
    ],
    furniture: [
      {key:'identity', label:'제품 정체성/공간 변화', examples:'공간에 놓이는 이유, 첫 분위기', primary:['HERO'], support:['CTA']},
      {key:'space_pain', label:'공간 고민', examples:'안 어울림, 칙칙함, 배치 불안', primary:['SPACE_PROBLEM'], support:['FAQ']},
      {key:'mood', label:'공간 연출/무드', examples:'거실, 홈오피스, 상담공간, 침실', primary:['ROOM_MOOD','LIFESTYLE'], support:['CTA']},
      {key:'detail', label:'소재/마감/형태 디테일', examples:'패브릭, 우드, 금속, 퀼팅, 라인', primary:['DETAIL','MATERIAL'], support:['FAQ']},
      {key:'size', label:'크기/배치/내하중', examples:'가로·세로·높이, 설치공간, 내하중', primary:['SIZE_USE','SPEC'], support:['FAQ']},
      {key:'compare', label:'선택 이유/비교', examples:'일반 제품 대비 공간감, 사용 포인트', primary:['COMPARISON','BENEFIT'], support:[]},
      {key:'care', label:'조립/관리/주의', examples:'조립 여부, 관리법, 사용 주의', primary:['FAQ','CARE'], support:[]}
    ],
    beauty: [
      {key:'identity', label:'제품 정체성/사용 무드', examples:'어떤 루틴/무드의 제품인지', primary:['HERO','MOOD'], support:['CTA']},
      {key:'texture', label:'제형/질감', examples:'크림, 세럼, 향, 발림성은 확인된 경우만', primary:['TEXTURE'], support:['FAQ']},
      {key:'point', label:'성분/포인트', examples:'확인된 성분, 향, 사용 포인트', primary:['POINT','INGREDIENT'], support:['FAQ']},
      {key:'usage', label:'사용 순서/사용 부위', examples:'언제, 어디에, 어떻게 쓰는지', primary:['HOW_TO_USE','USE_SCENE'], support:['FAQ']},
      {key:'volume', label:'용량/구성', examples:'용량, 세트 구성, 패키지', primary:['COLLECTION','PACKAGE','SPEC'], support:['FAQ']},
      {key:'caution', label:'주의사항/피부 표현 제한', examples:'확인되지 않은 효능, 의학적 표현 금지', primary:['FAQ'], support:[]}
    ],
    food: [
      {key:'identity', label:'제품 정체성/맛 경험', examples:'무슨 맛/언제 먹는지', primary:['HERO','TASTE_SCENE'], support:['CTA']},
      {key:'taste', label:'맛/섭취 상황', examples:'간식, 아침, 커피와 함께, 선물', primary:['TASTE_SCENE','HOW_TO_EAT'], support:['CTA']},
      {key:'package', label:'중량/구성/패키지', examples:'중량, 개수, 구성, 포장', primary:['PACKAGE','COLLECTION','SPEC'], support:['FAQ']},
      {key:'ingredient', label:'원재료/원산지/알레르기', examples:'원재료, 원산지, 알레르기 정보', primary:['INGREDIENT','POINT'], support:['FAQ']},
      {key:'storage', label:'보관법/유통기한', examples:'냉장/실온, 보관 방법, 유통기한', primary:['STORAGE','FAQ'], support:[]},
      {key:'caution', label:'건강 과장/주의', examples:'효능·치료·의학 표현 금지', primary:['FAQ'], support:[]}
    ],
    fitness: [
      {key:'identity', label:'제품 정체성/운동 시작 이유', examples:'홈트, 루틴, 장비 부담 감소', primary:['HERO'], support:['CTA']},
      {key:'pain', label:'운동 전 고민', examples:'공간 부담, 사용법 어려움, 꾸준함 부담', primary:['PROBLEM'], support:['FAQ']},
      {key:'components', label:'구성품/포함 부품', examples:'밴드, 손잡이, 파우치, 연결부 등 원본 구성', primary:['COMPONENTS'], support:['FAQ']},
      {key:'usage', label:'사용법/동작 흐름', examples:'고정, 잡기, 당기기, 보관', primary:['USAGE','ROUTINE'], support:['CTA']},
      {key:'detail', label:'소재/구조/디테일', examples:'손잡이, D링, 튜빙, 재질', primary:['DETAIL','MATERIAL'], support:['FAQ']},
      {key:'spec', label:'강도/길이/수치', examples:'확인된 강도, 길이, 내하중', primary:['SPEC'], support:['FAQ']},
      {key:'benefit', label:'운동 활용 장점', examples:'부위별 활용, 준비 편의, 보관성', primary:['BENEFIT'], support:['CTA']}
    ],
    living: [
      {key:'identity', label:'제품 정체성/생활 불편 해결', examples:'무엇을 정리/개선하는지', primary:['HERO'], support:['CTA']},
      {key:'pain', label:'생활 속 문제', examples:'반복 불편, 보관, 청소, 위생 고민', primary:['PROBLEM'], support:['FAQ']},
      {key:'solution', label:'해결 방식', examples:'정리, 고정, 세척, 사용 전후', primary:['SOLUTION','BEFORE_AFTER'], support:['BENEFIT']},
      {key:'usage', label:'사용법/설치', examples:'붙이기, 걸기, 세척하기, 접기', primary:['HOW_TO_USE','USAGE'], support:['FAQ']},
      {key:'detail', label:'소재/구조/크기', examples:'소재, 크기, 형태, 구성', primary:['DETAIL','MATERIAL','SIZE'], support:['FAQ']},
      {key:'storage', label:'보관/관리', examples:'보관 위치, 세척, 관리법', primary:['STORAGE','CLEANING'], support:[]}
    ],
    general: [
      {key:'identity', label:'제품 정체성/대표 구매 이유', examples:'무엇이며 왜 필요한지', primary:['HERO','OVERVIEW'], support:['CTA']},
      {key:'pain', label:'고객 고민', examples:'구매 전 불편, 사용 전 걱정', primary:['PROBLEM','PAIN_POINT'], support:['FAQ']},
      {key:'solution', label:'해결 방식/핵심 장점', examples:'제품이 줄여주는 불편, 선택 이유', primary:['SOLUTION','BENEFIT'], support:['CTA']},
      {key:'detail', label:'보이는 디테일/소재/구조', examples:'원본에서 보이는 색상, 재질감, 형태, 마감', primary:['DETAIL','MATERIAL','TEXTURE'], support:['FAQ']},
      {key:'spec', label:'확정 스펙/수치/옵션', examples:'사이즈, 용량, 중량, 전원, 구성 등 확인된 숫자', primary:['SPEC','SIZE','COLOR_SIZE'], support:['FAQ']},
      {key:'usage', label:'사용 장면/방법', examples:'실제 놓는 곳, 착용 장면, 사용 단계', primary:['USAGE','USE_SCENE','LIFESTYLE','HOW_TO_USE'], support:['CTA']},
      {key:'caution', label:'주의사항/구매 전 확인', examples:'관리법, 주의사항, 호환, 보관', primary:['FAQ','CARE'], support:[]}
    ]
  };

  const CATEGORY_FACT_ALIASES_V12 = {
    kitchen:'living', pet:'living', kids:'living', auto:'living', stationery:'general', shoe_care:'living'
  };

  function normalizeSectionV12(section){ return String(section || '').trim().toUpperCase(); }
  function getFactGroupsV12(analysis={}){
    const key = analysis.key || analysis.template_type || 'general';
    const mapped = CATEGORY_FACT_GROUPS_V12[key] ? key : (CATEGORY_FACT_ALIASES_V12[key] || 'general');
    return CATEGORY_FACT_GROUPS_V12[mapped] || CATEGORY_FACT_GROUPS_V12.general;
  }
  function firstExistingSectionV12(sections=[], candidates=[]){
    const set = new Set((sections || []).map(normalizeSectionV12));
    return (candidates || []).map(normalizeSectionV12).find(s => set.has(s)) || '';
  }
  function assignFactGroupsToSectionsV12(sections=[], analysis={}){
    const normalizedSections = (sections || []).map(normalizeSectionV12);
    const groups = getFactGroupsV12(analysis).map(g => Object.assign({}, g));
    return groups.map(group => {
      const primary = firstExistingSectionV12(normalizedSections, group.primary)
        || firstExistingSectionV12(normalizedSections, ['SPEC','DETAIL','BENEFIT','OVERVIEW','FAQ','HERO'])
        || normalizedSections[0]
        || 'HERO';
      const supportCandidates = (group.support || []).filter(s => normalizeSectionV12(s) !== primary);
      const support = firstExistingSectionV12(normalizedSections, supportCandidates);
      return Object.assign({}, group, {assigned: primary, support});
    });
  }
  function buildSectionContentPlan(sections=[], analysis={}, data={}){
    const normalizedSections = (sections || []).map(normalizeSectionV12);
    const assigned = assignFactGroupsToSectionsV12(normalizedSections, analysis);
    const sectionBlocks = {};
    normalizedSections.forEach(section => {
      const main = assigned.filter(g => g.assigned === section);
      const support = assigned.filter(g => g.support === section);
      const blocked = assigned.filter(g => g.assigned !== section && g.support !== section);
      sectionBlocks[section] = {
        main,
        support,
        blocked,
        block: `[카테고리 인식형 섹션 중복 방지 - v21.8.24.12] ⚠️ 최우선
이 상세페이지는 여러 상품군에 대응해야 하므로, "사이즈" 같은 특정 정보 하나만 제한하지 않습니다.
현재 상품군(${analysis.category_group || analysis.key || '일반상품'})에서 중요한 팩트 묶음을 섹션별로 나누어 사용하세요.

[현재 섹션 전용 사용 정보]
${main.length ? main.map(g => `- ${g.label}: ${g.examples}`).join('\n') : '- 이 섹션은 대표 메시지/시각 흐름 중심입니다. 구체 스펙은 배정된 섹션에서만 사용하세요.'}

[현재 섹션 보조 사용 가능 정보]
${support.length ? support.map(g => `- ${g.label}: 짧게 재확인만 가능`).join('\n') : '- 없음. 다른 섹션 정보는 끌어오지 마세요.'}

[현재 섹션에서 반복 금지할 정보]
${blocked.map(g => `- ${g.label} → ${g.assigned}${g.support ? ` / 보조 ${g.support}` : ''} 섹션에 배정됨`).join('\n')}

[중복 방지 강제 규칙]
- 위 "현재 섹션 전용 사용 정보"가 아닌 팩트는 메인 타이틀, 카드 제목, 큰 숫자 인포그래픽으로 쓰지 마세요.
- 확정 스펙/수치/용량/사이즈/중량/전원/수납량/소재/원산지/세탁법/주의사항은 배정된 섹션에서만 크게 보여주세요.
- HERO/PROBLEM/LIFESTYLE/CTA에서는 스펙을 다시 나열하지 말고, 고객 상황과 구매 이유만 말하세요.
- FAQ는 이미 나온 정보를 짧게 재확인하는 곳이지, 새로운 스펙을 추가하는 곳이 아닙니다.
- 같은 숫자, 같은 소재명, 같은 구성품, 같은 옵션명을 여러 장에 반복하면 실패입니다.
- 긴 공식 제품명은 HERO 또는 SPEC에서 1회만 사용하고, 다른 섹션에서는 축약명/제품군명으로 자연스럽게 줄이세요.`
      };
    });
    const globalBlock = `[상세페이지 전체 콘텐츠 배정표 - v21.8.24.12]
${assigned.map(g => `- ${g.label}: 메인 ${g.assigned}${g.support ? ` / 보조 ${g.support}` : ''}`).join('\n')}`;
    return {sections: normalizedSections, assigned, sectionBlocks, globalBlock, categoryLabel: (analysis.category_group || analysis.key || '일반상품')};
  }
  function buildCategoryAwareDedupBlock(section, contentPlan){
    const key = normalizeSectionV12(section);
    if(!contentPlan || !contentPlan.sectionBlocks || !contentPlan.sectionBlocks[key]) return '';
    return `${contentPlan.globalBlock}\n\n${contentPlan.sectionBlocks[key].block}`;
  }

  function multiImageUsageBlock(data){
    const names = Array.isArray(data?.imageNames) ? data.imageNames.filter(Boolean) : [];
    if(names.length < 2) return '';
    return `[첨부 이미지 여러 장 활용 규칙]
첨부 이미지가 ${names.length}장 있습니다. 모든 섹션에서 같은 착용컷/제품컷만 반복하지 마세요.
- HERO: 가장 대표성과 구매욕구가 강한 전체 제품/착용 이미지
- PROBLEM: 고객 고민을 보여주는 장면형 이미지 또는 인물/사용 상황
- SOLUTION/SCENE: 제품이 문제를 줄여주는 사용 장면
- SIZE/DETAIL/FIT: 라인, 길이, 구조, 디테일이 잘 보이는 다른 원본 이미지
- FAQ/TRUST: 정보 전달에 적합한 가장 선명한 이미지
- CTA: 구매욕구가 가장 강한 대표 이미지
같은 포즈, 같은 배경, 같은 제품 배치를 반복하지 말고 섹션마다 다른 원본 이미지를 우선 참고하세요.`;
  }

  function confirmedSpecBlock(specs){
    const s=String(specs||'').trim();
    if(!s || /^확인\s*필요$/i.test(s)) return '';
    return `[확정 상품 정보 - 링크/사용자 입력 우선]
${s}

규칙:
- 위 정보에 명시된 소재/사이즈/색상/구성품/수납/옵션만 확인된 정보로 봅니다.
- 위에 없는 소재, 전체 사이즈 범위, 리뷰 수, 별점, 판매량, 인증, 수상 정보는 이미지 안 문구로 만들지 마세요.
- 특정 옵션명(예: 2XL)만 확인된 경우 전체 사이즈가 그것뿐인 것처럼 쓰지 말고, 필요한 경우 "착용컷 기준" 또는 "선택 옵션 확인" 수준으로만 표현하세요.
- "확인 필요", "상세페이지 참조", "상품페이지 참고" 같은 도망 문구는 이미지 안에 절대 넣지 말고, 정보가 부족한 항목은 이미지에서 제외하세요.`;
  }

  // v20.9 이식: 다양성 7가지 톤 (매 생성마다 랜덤 → 같은 상품도 매번 다른 카피)
  const VARIATION_SEEDS = [
    { name:'직설형', desc:'단도직입, 짧고 강함, 명사 종결 위주', sample:'"이제, 시작입니다"' },
    { name:'질문형', desc:'고객에게 직접 묻는 톤, "-나요?", "-까요?", "-죠?"', sample:'"왜 늘 시작이 어려울까요?"' },
    { name:'시적/감성형', desc:'은유, 짧은 시 같은 카피, 여백감', sample:'"작지만, 충분한 시작"' },
    { name:'대비형', desc:'"X가 아니라 Y" 구조, Before/After 대비', sample:'"의지가 부족한 게 아닙니다, 방법이 어려웠을 뿐"' },
    { name:'숫자/팩트형', desc:'구체적 숫자/수치 카피, 데이터 우선', sample:'"단 3초, 매일 1분"' },
    { name:'단언/선언형', desc:'강한 단언, "-입니다", "-됩니다" 톤', sample:'"이것이, 당신의 답입니다"' },
    { name:'생활밀착형', desc:'일상 장면을 그리는 톤, 친근하게', sample:'"퇴근 후 5분, 바로 시작하세요"' }
  ];
  function pickVariation(){
    const idx = (Date.now() + Math.floor(Math.random()*1000)) % VARIATION_SEEDS.length;
    return VARIATION_SEEDS[idx];
  }

  // ===== v21.4: 디자인 무드 시스템 (팔레트 + 폰트 + 레이아웃 다양화) =====
  const DESIGN_MOODS = {
    orange_minimal: {
      label:'오렌지 미니멀(기존)',
      palettes:[
        '배경 화이트(#FFFFFF)/옅은 그레이(#FAFAFA), 포인트 오렌지(#FF6B1A), 텍스트 차콜(#111111)',
        '배경 웜화이트(#FFFDF9), 포인트 딥오렌지(#F15A24), 텍스트 블랙(#1A1A1A)',
        '배경 라이트그레이(#F5F5F4), 포인트 코랄오렌지(#FF7A45), 텍스트 그레이블랙(#222)'
      ],
      fonts:['굵은 산세리프 한글(Pretendard/애플 SD산돌고딕네오 느낌)'],
      tone:'무인양품 카탈로그 + 애플 광고처럼 미니멀하고 깔끔하게, 넓은 여백'
    },
    dark_premium: {
      label:'다크 프리미엄',
      palettes:[
        '배경 차콜(#1C1C1E)/딥그레이, 포인트 골드(#C9A24B), 텍스트 화이트(#FFFFFF)',
        '배경 블랙(#0E0E10), 포인트 실버화이트(#E8E8E8), 텍스트 라이트그레이(#CCC)',
        '배경 다크네이비(#13182B), 포인트 샴페인골드(#D4B36A), 텍스트 오프화이트(#F2F2F2)'
      ],
      fonts:['고급스러운 볼드 산세리프, 자간 약간 넓게'],
      tone:'테슬라/다이슨/프리미엄 가전 상세페이지처럼 묵직하고 고급스럽게, 강한 명암 대비'
    },
    soft_neutral: {
      label:'감성 뉴트럴',
      palettes:[
        '배경 베이지(#F3EDE3)/크림, 포인트 더스티핑크(#CC9999), 텍스트 웜브라운(#5C4A3A)',
        '배경 아이보리(#FBF7F0), 포인트 세이지그린(#9CA891), 텍스트 토프(#6B5D4F)',
        '배경 오트밀(#EFE8DC), 포인트 테라코타(#C36A4D), 텍스트 다크브라운(#4A3F35)'
      ],
      fonts:['가는~중간 굵기 산세리프 또는 우아한 명조 혼용, 여백 충분히'],
      tone:'무인양품 + 감성 뷰티 브랜드처럼 따뜻하고 부드럽게, 자연광 무드'
    },
    vivid_pop: {
      label:'비비드 팝',
      palettes:[
        '배경 화이트, 포인트 비비드블루(#2563EB)+옐로우(#FACC15) 듀얼, 텍스트 블랙',
        '배경 옅은 민트(#ECFDF5), 포인트 비비드그린(#10B981)+오렌지, 텍스트 차콜',
        '배경 라이트, 포인트 마젠타(#EC4899)+퍼플(#8B5CF6) 듀얼, 텍스트 딥그레이'
      ],
      fonts:['아주 굵은 산세리프, 크고 임팩트 있게'],
      tone:'젊고 에너지 넘치는 SNS 광고 톤, 색 대비 강하게, 다이내믹'
    },
    magazine: {
      label:'매거진 에디토리얼',
      palettes:[
        '배경 화이트/오프화이트, 포인트 블랙 라인, 텍스트 블랙 - 흑백 위주 + 최소 컬러',
        '배경 크림, 포인트 딥레드(#B91C1C), 텍스트 블랙 - 잡지 표지 느낌',
        '배경 라이트그레이, 포인트 잉크블루(#1E3A5F), 텍스트 차콜 - 에디토리얼'
      ],
      fonts:['큰 세리프 헤드라인 + 산세리프 본문 혼용, 매거진 타이포'],
      tone:'보그/킨포크 잡지 에디토리얼처럼, 큰 타이포와 그리드, 여백의 미'
    },
    fresh_clean: {
      label:'프레시 클린',
      palettes:[
        '배경 화이트, 포인트 스카이블루(#38BDF8), 텍스트 네이비(#1E293B) - 청량',
        '배경 옅은 블루(#F0F9FF), 포인트 틸(#14B8A6), 텍스트 슬레이트(#334155)',
        '배경 화이트, 포인트 라임그린(#84CC16), 텍스트 다크그레이 - 위생/신선'
      ],
      fonts:['깔끔한 중간 굵기 산세리프'],
      tone:'위생/신선/건강 느낌, 청량하고 깨끗하게, 밝은 조명'
    }
  };

  const TEMPLATE_TO_MOOD = {
    care_before_after: 'dark_premium',
    usage_components: 'vivid_pop',
    use_detail_components: 'orange_minimal',
    space_mood: 'soft_neutral',
    workflow_function: 'dark_premium',
    function_spec: 'dark_premium',
    wear_fit: 'magazine',
    mood_texture: 'soft_neutral',
    use_clean_storage: 'fresh_clean',
    taste_package: 'soft_neutral',
    pet_use_safety: 'fresh_clean',
    parent_trust: 'fresh_clean',
    install_before_after: 'dark_premium',
    detail_lifestyle: 'magazine',
    problem_solution: 'orange_minimal',
    general_dynamic: 'orange_minimal'
  };

  // v21.8.24.9: 디자인 무드 확장. 기존 6개에 12개를 추가해 상품군/이미지별 톤 반복을 줄입니다.
  Object.assign(DESIGN_MOODS, {
    feminine_soft:{label:'여성감성 소프트', palettes:['크림화이트 배경, 로즈베이지 포인트, 코코아브라운 텍스트','파우더핑크 배경, 모브 포인트, 딥브라운 텍스트','아이보리 배경, 피치코랄 포인트, 차콜 텍스트'], fonts:['부드러운 굵기의 둥근 산세리프, 자연광 느낌'], tone:'여성 의류/뷰티 상세페이지처럼 부드럽고 부담 없는 감성, 넓은 여백'},
    sporty_active:{label:'스포티 액티브', palettes:['화이트/블랙 고대비, 네온오렌지 포인트','딥네이비 배경, 라임 포인트, 화이트 텍스트','쿨그레이 배경, 코발트블루 포인트'], fonts:['두꺼운 스포츠 산세리프, 사선 그래픽 허용'], tone:'운동/아웃도어 광고처럼 역동적이고 시원하게, 강한 대비'},
    clean_white:{label:'클린 화이트', palettes:['순백 배경, 라이트블루 포인트, 슬레이트 텍스트','화이트+옅은 회색, 민트 포인트','화이트 배경, 라이트그레이 라인, 블랙 텍스트'], fonts:['정돈된 산세리프, 표/카드형 정보에 최적화'], tone:'흰 배경 중심의 깨끗한 이커머스 정보형, 제품과 텍스트 위계가 선명하게'},
    modern_lifestyle:{label:'모던 라이프스타일', palettes:['라이트그레이/화이트 배경, 네이비 포인트','웜그레이 배경, 카멜 포인트','미색 배경, 올리브 포인트'], fonts:['모던 산세리프 + 얇은 라인 아이콘'], tone:'집/사무실/일상 공간에 자연스럽게 놓인 브랜드 라이프스타일 무드'},
    highend_brand:{label:'하이엔드 브랜드형', palettes:['오프화이트 배경, 블랙+샴페인골드 포인트','딥그레이 배경, 브론즈 포인트','크림 배경, 먹색 라인'], fonts:['자간 넓은 고급 산세리프, 작은 캡션과 큰 여백'], tone:'백화점 브랜드/고급 잡화 상세페이지처럼 절제되고 비싼 느낌'},
    practical_info:{label:'실용 정보형', palettes:['화이트 배경, 블루 포인트, 보조 회색 카드','라이트그레이 배경, 오렌지 포인트','화이트 배경, 그린 포인트'], fonts:['가독성 좋은 산세리프, 표/아이콘/번호 체계 중심'], tone:'구매 전 필요한 정보를 빠르게 이해시키는 설명서형 상세페이지'},
    gift_premium:{label:'선물 고급 패키지형', palettes:['크림 배경, 버건디 포인트','딥그린 배경, 골드 포인트','샴페인베이지 배경, 블랙 리본 포인트'], fonts:['고급 선물 카드 느낌의 산세리프/세리프 혼용'], tone:'받는 순간의 만족감, 포장감, 선물 가치가 느껴지는 프리미엄 무드'},
    tech_dashboard:{label:'테크 대시보드형', palettes:['딥네이비 배경, 시안 포인트, 화이트 텍스트','블랙 배경, 블루/퍼플 포인트','화이트 배경, 일렉트릭블루 포인트, 대시보드 카드'], fonts:['디지털 제품용 정돈된 산세리프, 데이터 카드/화면 목업 중심'], tone:'SaaS/AI/자동화 서비스 랜딩페이지처럼 기능과 결과가 한눈에 보이게'},
    warm_natural:{label:'웜 내추럴', palettes:['크림/우드톤 배경, 올리브그린 포인트','베이지 배경, 테라코타 포인트','내추럴린넨 배경, 세이지 포인트'], fonts:['따뜻한 느낌의 산세리프, 자연광과 질감 중심'], tone:'생활/주방/반려/키즈 상품에 맞는 자연스럽고 편안한 무드'},
    trendy_mz:{label:'트렌디 MZ형', palettes:['라이트퍼플 배경, 핫핑크+블루 포인트','화이트 배경, 레몬옐로우+코발트 포인트','라이트민트 배경, 퍼플 포인트'], fonts:['굵고 둥근 산세리프, 스티커형 카드/큰 숫자 가능'], tone:'SNS 카드뉴스처럼 빠르게 눈에 띄는 트렌디하고 밝은 스타일'},
    trust_blue:{label:'신뢰 블루 정보형', palettes:['화이트 배경, 딥블루 포인트, 네이비 텍스트','아주 옅은 블루 배경, 블루 포인트','화이트 배경, 블루+그레이 포인트'], fonts:['가독성 좋은 산세리프, 체크리스트/표/FAQ에 적합'], tone:'신뢰와 정확성을 주는 정보 전달형 상세페이지, 과장 없이 명확하게'},
    bold_conversion:{label:'강한 전환형', palettes:['화이트 배경, 레드오렌지 포인트, 블랙 텍스트','블랙 배경, 옐로우 포인트, 화이트 텍스트','딥블루 배경, 오렌지 포인트'], fonts:['초대형 볼드 산세리프, 짧고 강한 문장 중심'], tone:'광고 랜딩/공구 상세페이지처럼 첫눈에 구매 이유가 꽂히는 전환 중심 무드'},
    baby_clean:{label:'프리미엄 베이비 클린형', palettes:['화이트/크림 배경, 소프트블루+베이지 포인트, 그레이 텍스트','웜화이트 배경, 라이트블루 포인트, 토프 텍스트','크림 배경, 민트+베이지 포인트, 차콜 텍스트'], fonts:['부드러운 둥근 산세리프, 넉넉한 여백'], tone:'아기 물티슈/유아용품처럼 깨끗하고 따뜻한 육아용품 무드. 부드러운 자연광, 안심·부드러움이 느껴지게. 어두운/테크 느낌 금지'}
  });

  Object.assign(TEMPLATE_TO_MOOD, {
    usage_components:'sporty_active',
    space_mood:'modern_lifestyle',
    workflow_function:'tech_dashboard',
    function_spec:'tech_dashboard',
    wear_fit:'feminine_soft',
    taste_package:'warm_natural',
    pet_use_safety:'warm_natural',
    detail_lifestyle:'highend_brand',
    intangible_offer:'tech_dashboard',
    general_dynamic:'clean_white'
  });


  // v21.8.24.11: 사용자가 직접 고른 디자인 무드가 기본 템플릿에 묻히지 않도록 강제 규칙을 별도 삽입합니다.
  const DESIGN_MOOD_HARD_RULES = {
    trendy_mz: `필수 요소: 밝은 SNS 카드뉴스 느낌, 비대칭 구도, 스티커형 라벨/말풍선/배지, 굵고 둥근 한글 산세리프, 짧고 경쾌한 카피, 레몬옐로우/코발트블루/퍼플/핫핑크 중 1~2개 포인트.
금지 요소: 베이지/크림 기반 클래식 판매형, 붓글씨/서예풍 제목, 정적인 중앙 제품+하단 3카드 반복, 고급 선물형/감성 뉴트럴 무드, 차분한 잡지형 무드.`,
    dark_premium: `필수 요소: 차콜/블랙/딥네이비 배경, 스포트라이트 조명, 절제된 금색/실버 포인트, 제품 질감 강조, 큰 여백, 짧고 묵직한 카피.
금지 요소: 밝은 파스텔 카드뉴스, 귀여운 스티커, 과한 아이콘, 산만한 컬러 조합.`,
    feminine_soft: `필수 요소: 부드러운 자연광, 크림/로즈/피치 계열, 가벼운 여백, 여성 의류/뷰티 상세페이지 같은 부드러운 타이포.
금지 요소: 딥블랙 하드 조명, 거친 스포츠 사선 그래픽, 공격적인 CTA.`,
    sporty_active: `필수 요소: 사선 구도, 강한 대비, 역동적 제품/사용 장면, 네온/코발트/오렌지 포인트, 굵은 스포츠 타이포.
금지 요소: 정적인 플랫레이만 반복, 베이지 감성 톤, 선물 패키지 무드.`,
    highend_brand: `필수 요소: 오프화이트/블랙/샴페인골드, 자간 넓은 타이포, 고급 잡화 화보 느낌, 작은 캡션과 큰 제품 질감.
금지 요소: MZ 스티커/말풍선, 비비드 컬러 과다, 저가형 공구 배너 느낌.`,
    practical_info: `필수 요소: 표/체크리스트/아이콘/번호 체계, 정보 위계가 선명한 화이트/블루/그레이 계열, 구매 전 확인사항 중심.
금지 요소: 감성 카피만 크고 정보가 없는 구성, 확인 안 된 기능성 문구.`,
    gift_premium: `필수 요소: 선물 카드/패키지 무드, 크림/버건디/딥그린/골드 계열, 받는 사람을 떠올리게 하는 짧은 카피.
금지 요소: 원본에 없는 리본/상자/구성품을 제품 구성처럼 보이게 추가, 과한 할인 CTA.`,
    tech_dashboard: `필수 요소: 대시보드 카드, 화면 목업, 입력→처리→결과 흐름, 딥네이비/시안/퍼플 포인트.
금지 요소: 감성 소품 위주의 라이프스타일, 기능 없는 추상 배경.`,
    bold_conversion: `필수 요소: 초대형 볼드 타이포, 강한 대비, CTA가 명확한 랜딩페이지 느낌, 짧고 행동 지향적인 문구.
금지 요소: 작은 글자 많은 설명서형, 차분한 에디토리얼 무드.`,
    clean_white: `필수 요소: 순백/라이트그레이 배경, 얇은 라인, 정확한 정보 카드, 선명한 위계.
금지 요소: 어두운 무대형 조명, 과한 비비드 컬러.`,
    modern_lifestyle: `필수 요소: 실제 공간/데스크/가방/생활 장면, 라이트그레이/네이비/카멜 계열, 자연스러운 제품 사용 맥락.
금지 요소: 제품만 떠 있는 단순 배너 반복, 확인 안 된 사용 효과.`,
    trust_blue: `필수 요소: 딥블루/네이비 정보 구조, 체크리스트/FAQ/표, 신뢰감 있는 산세리프.
금지 요소: 과장 광고 톤, 감성만 있고 근거 없는 문구.`,
    vivid_pop: `필수 요소: 높은 채도, 강한 대비, 큰 타이포, 젊고 활기찬 카드뉴스 리듬.
금지 요소: 무채색 중심 고급 잡지 톤, 차분한 베이지 톤.`
  };

  function buildMoodHardApplyBlock(key, mood, userSelected){
    const hard = DESIGN_MOOD_HARD_RULES[key] || '';
    const priority = userSelected
      ? '사용자가 직접 선택한 디자인 무드입니다. 자동 추천/기본 템플릿보다 이 무드를 우선합니다.'
      : '자동 추천된 디자인 무드입니다. 아래 무드와 섹션 역할이 충돌하지 않게 적용하세요.';
    return `[선택 디자인 무드 강제 적용] ⚠️
적용 무드: ${mood.label}
${priority}
${hard ? '\n' + hard : ''}
공통 규칙: 선택한 무드와 다른 시각 언어가 섞이면 실패입니다. 배경색, 포인트 컬러, 폰트 성격, 카드 형태, 카피 톤까지 모두 이 무드에 맞추세요.`;
  }

  // v21.8.24.21: 무드 다양성 — 상품군당 '톤이 어울리는' 무드 풀에서 매 생성마다 변주(자동 모드 한정).
  // 사용자가 무드를 직접 고르면 그 무드를 그대로 강제 적용한다.
  const TEMPLATE_TO_MOOD_POOL = {
    care_before_after:['dark_premium','highend_brand','clean_white'],
    usage_components:['sporty_active','vivid_pop','bold_conversion'],
    use_detail_components:['orange_minimal','clean_white','practical_info'],
    space_mood:['modern_lifestyle','soft_neutral','warm_natural'],
    workflow_function:['tech_dashboard','trust_blue','bold_conversion'],
    function_spec:['tech_dashboard','dark_premium','practical_info'],
    wear_fit:['feminine_soft','magazine','soft_neutral'],
    mood_texture:['soft_neutral','feminine_soft','warm_natural'],
    use_clean_storage:['fresh_clean','clean_white','practical_info'],
    taste_package:['warm_natural','soft_neutral','vivid_pop'],
    pet_use_safety:['warm_natural','fresh_clean','feminine_soft'],
    parent_trust:['baby_clean','fresh_clean','warm_natural'],
    install_before_after:['dark_premium','sporty_active','practical_info'],
    detail_lifestyle:['highend_brand','magazine','modern_lifestyle'],
    problem_solution:['orange_minimal','bold_conversion','clean_white'],
    intangible_offer:['tech_dashboard','trust_blue','bold_conversion'],
    general_dynamic:['clean_white','modern_lifestyle','orange_minimal']
  };
  let __lastMoodKey = '';
  function buildDesignBlock(moodKey, analysis, productText){
    const rawKey = String(moodKey || 'auto').trim();
    const userSelected = !!rawKey && rawKey !== 'auto';
    let key = rawKey;
    if(!key || key==='auto'){
      // v21.8.24.85: 자동일 때 매번 같은 무드만 나오던 문제 수정 —
      //  semanticMoodV46가 무드를 '고정'하던 것을, 상품군 풀에 후보로 넣고 '매번 다르게 회전'하도록 변경.
      const semantic = semanticMoodV46(`${productText || ''} ${analysis.category_group || ''} ${analysis.product_type || ''}`);
      const pool = (TEMPLATE_TO_MOOD_POOL[analysis.template_type] || []).slice();
      if(semantic && DESIGN_MOODS[semantic] && pool.indexOf(semantic) < 0) pool.unshift(semantic);
      if(pool.length){
        let mi = Math.floor(Date.now() + Math.random()*1e6) % pool.length;
        if(pool.length > 1 && pool[mi] === __lastMoodKey) mi = (mi + 1) % pool.length;
        key = pool[mi];
        __lastMoodKey = key;
      } else {
        key = (semantic && DESIGN_MOODS[semantic]) ? semantic : (TEMPLATE_TO_MOOD[analysis.template_type] || 'orange_minimal');
      }
    }
    const mood = DESIGN_MOODS[key] || DESIGN_MOODS.orange_minimal;
    const pIdx = (Date.now() + Math.floor(Math.random()*1000)) % mood.palettes.length;
    const palette = mood.palettes[pIdx];
    const font = mood.fonts[Math.floor(Math.random()*mood.fonts.length)];
    const hardBlock = buildMoodHardApplyBlock(key, mood, userSelected);
    return {
      key,
      label: mood.label,
      userSelected,
      block: `${hardBlock}

[디자인 무드 - "${mood.label}"]
컬러: ${palette}
폰트: ${font}
분위기: ${mood.tone}
이 무드를 이미지 전체에 일관되게 적용하세요. 기본 베이지/오렌지 카드형이 선택 무드를 덮어쓰면 실패입니다.`
    };
  }

  // v21.8.24.9: 상세페이지 디자인 틀 라이브러리. 섹션 수가 아니라 구도/프레임을 다양화합니다.
  const DETAILPAGE_LAYOUT_TEMPLATES = {
    hero_split_premium:{label:'프리미엄 좌우 분할형',layout:'좌측 45%는 큰 헤드라인과 짧은 서브카피, 우측 55%는 제품/착용컷을 크게 배치. 하단에는 작은 포인트 2~3개만.',use:'HERO/CTA/대표컷'},
    hero_center_spotlight:{label:'중앙 스포트라이트형',layout:'중앙에 제품을 크게 놓고 배경에 부드러운 원형 스포트라이트. 상단 메인 카피 한 줄, 하단 짧은 근거 카드.',use:'HERO/제품 단독 강조'},
    hero_magazine_cover:{label:'매거진 표지형',layout:'큰 제품/모델 비주얼 위에 잡지 표지처럼 강한 타이포를 겹치되 제품을 가리지 않음. 여백과 자간을 넓게.',use:'HERO/패션/잡화'},
    product_dark_stage:{label:'다크 제품 무대형',layout:'어두운 배경에 제품만 조명으로 강조. 작은 금색/화이트 라인 콜아웃을 사용하고 텍스트는 최소화.',use:'프리미엄/디테일/CTA'},
    three_card_news:{label:'카드뉴스 3분할형',layout:'상단 메인 카피, 중단 제품 또는 상황컷, 하단 3개 카드. 다른 섹션과 반복되지 않을 때만 사용.',use:'BENEFIT/POINT/FAQ'},
    problem_scene_grid:{label:'고민 장면 4분할형',layout:'고객 고민 장면을 2x2 그리드로 보여주고, 제품은 작게 또는 다음 섹션 암시로만 배치.',use:'PROBLEM/PAIN_POINT'},
    problem_speech_bubble:{label:'말풍선 고민형',layout:'고객의 실제 고민을 말풍선/메모 카드로 배치. 배경은 일상 장면, 제품은 보조 역할.',use:'PROBLEM/FAQ'},
    before_after_split:{label:'좌우 Before/After 비교형',layout:'왼쪽은 불편/혼잡/고민, 오른쪽은 정돈/완성/해결 인상. 중앙에 얇은 구분선과 전환 문구.',use:'BEFORE_AFTER/COMPARISON'},
    solution_spotlight:{label:'해결 등장 스포트라이트형',layout:'어두운 고민 장면에서 밝은 제품 등장으로 전환. 제품 주변에 빛/여백을 주어 답처럼 보이게.',use:'SOLUTION'},
    overview_flatlay:{label:'전체 구성 플랫레이형',layout:'제품/구성품을 위에서 내려다보는 정돈된 플랫레이. 얇은 라벨선과 짧은 설명 카드.',use:'OVERVIEW/COMPONENTS'},
    components_labeled_grid:{label:'구성품 라벨 그리드형',layout:'구성품을 겹치지 않게 2~4열 그리드로 정렬. 각 요소에 번호/라벨/역할을 붙임.',use:'COMPONENTS/PACKAGE'},
    detail_macro_callout:{label:'매크로 콜아웃형',layout:'제품 디테일 하나를 화면 70% 이상으로 확대하고, 2~3개 콜아웃 라인으로 핵심만 설명.',use:'DETAIL/MATERIAL/FABRIC'},
    detail_three_zoom:{label:'디테일 3컷 확대형',layout:'큰 전체컷 1개 + 작은 확대컷 3개를 비대칭으로 배치. 각 확대컷에 짧은 라벨.',use:'DETAIL/TEXTURE'},
    material_texture_grid:{label:'재질 텍스처 그리드형',layout:'소재/표면/마감 클로즈업을 작은 패널로 나누어 보여줌. 확인된 소재명만 표기.',use:'MATERIAL/FABRIC/TEXTURE'},
    usage_steps_horizontal:{label:'사용법 가로 3단계형',layout:'STEP 1→2→3 흐름을 가로 또는 세로 카드로 배치. 각 단계는 동사형 짧은 문구.',use:'HOW_TO_USE/INSTALL'},
    usage_lifestyle_sequence:{label:'라이프스타일 시퀀스형',layout:'사용 전/사용 중/사용 후를 사진첩처럼 자연스럽게 이어 붙임. 과한 인포그래픽보다 장면 중심.',use:'USAGE/WEAR_SCENE/USE_SCENE'},
    routine_grid:{label:'루틴/활용 3분할형',layout:'활용 상황을 3개 카드로 분리. 아이콘보다 실제 장면과 짧은 행동 문구 중심.',use:'ROUTINE/EXAMPLES'},
    option_color_cards:{label:'옵션 컬러 카드형',layout:'확인된 색상/옵션만 카드로 정렬. 각 옵션은 작은 제품컷 또는 색상칩 + 이름으로 구성.',use:'COLOR_SIZE/옵션 안내'},
    size_fit_guide:{label:'착용핏/크기 가이드형',layout:'정면/측면/디테일 컷을 나누고 핏·길이감·커버 범위를 시각적으로 표시. 미확정 수치표 금지.',use:'FIT/SIZE/SIZE_USE'},
    spec_table_product:{label:'제품+스펙 테이블형',layout:'좌측 제품, 우측 스펙 표. 확인된 항목만 넣고 미확정/확인 필요 문구는 이미지에서 제외.',use:'SPEC/SIZE'},
    comparison_cards:{label:'비교 카드형',layout:'일반적인 불편 vs 이 제품의 선택 이유를 카드 2~3개로 비교. 과장/보장 표현 금지.',use:'COMPARISON/BENEFIT'},
    benefit_big_numbers:{label:'큰 숫자/핵심 이유형',layout:'구매 이유 3개를 큰 숫자 01/02/03으로 배치. 확인 안 된 수치는 만들지 않음.',use:'BENEFIT/FEATURE'},
    faq_cards:{label:'FAQ 카드 스택형',layout:'Q&A 카드를 세로로 쌓아 구매 전 불안을 해소. 답변은 짧고 확인된 내용만.',use:'FAQ'},
    cta_banner_final:{label:'마지막 CTA 배너형',layout:'제품 마감샷 또는 사용 장면 + 큰 행동 유도 문구 + 하단 버튼 느낌의 CTA. 텍스트는 짧게.',use:'CTA'},
    gift_packaging_scene:{label:'선물 패키지 무드형',layout:'제품을 선물처럼 정돈된 패키지/리본/카드 무드로 연출. 원본에 없는 구성품은 추가하지 않음.',use:'GIFT/잡화'},
    storage_open_detail:{label:'수납 구조 오픈컷형',layout:'열림/수납/내부 구조를 크게 보여주고, 각 공간에 라벨을 붙임. 작은 잡화에 적합.',use:'STORAGE/지갑/케이스'},
    workflow_arrow:{label:'업무 흐름 화살표형',layout:'입력→처리→결과를 큰 화살표/대시보드 카드로 구성. 실제 기능만 설명.',use:'WORKFLOW/디지털'},
    feature_dashboard_cards:{label:'기능 대시보드 카드형',layout:'기능 카드 4개 + 화면 목업/대시보드형 그래픽. 테크 상품에 적합.',use:'FEATURE/RESULT'},
    room_mood_editorial:{label:'공간 에디토리얼형',layout:'제품이 놓인 공간을 잡지 화보처럼 크게 보여주고, 작은 캡션으로 무드와 사용 장면 설명.',use:'ROOM_MOOD/LIFESTYLE'},
    lookbook_collage:{label:'룩북 콜라주형',layout:'착용/사용 장면 2~3개를 콜라주처럼 배치. 패션/라이프스타일에 적합.',use:'WEAR_SCENE/MOOD'},
    trust_checklist:{label:'신뢰 체크리스트형',layout:'체크 아이콘과 짧은 문구로 불안 요소를 정리. 인증/보장/리뷰는 확인된 경우만 사용.',use:'FAQ/SPEC'},
    package_included_boxes:{label:'포함 구성 박스형',layout:'포함 항목을 박스 형태로 정리. 서비스/패키지/세트 상품에 적합.',use:'PACKAGE/COLLECTION'},
    diagonal_dynamic:{label:'사선 역동형',layout:'사선 분할 배경과 큰 제품/사용 장면을 배치. 스포츠/자동차/액티브 상품에 적합.',use:'스포티/활동성'},
    mobile_scroll_story:{label:'모바일 스크롤 스토리형',layout:'상단 강한 한 줄 → 중간 비주얼 → 하단 다음 행동으로 이어지는 세로 스토리 흐름. 모바일 우선.',use:'전 섹션 공통'},
    clean_minimal_list:{label:'클린 리스트형',layout:'큰 여백, 제품컷 하나, 짧은 리스트 3개. 정보가 많은 상품을 깔끔하게 정리.',use:'정보형/FAQ/스펙'},
    editorial_two_column:{label:'에디토리얼 2컬럼형',layout:'왼쪽은 감성 이미지/제품컷, 오른쪽은 큰 타이포와 짧은 설명. 잡지형 고급 무드.',use:'무드/디테일/라이프스타일'}
  };

  const TEMPLATE_TO_LAYOUT_KEYS = {
    wear_fit:['hero_magazine_cover','lookbook_collage','size_fit_guide','option_color_cards','detail_macro_callout','usage_lifestyle_sequence','faq_cards','cta_banner_final'],
    detail_lifestyle:['hero_split_premium','storage_open_detail','detail_three_zoom','option_color_cards','gift_packaging_scene','spec_table_product','editorial_two_column','cta_banner_final'],
    usage_components:['hero_center_spotlight','components_labeled_grid','usage_steps_horizontal','diagonal_dynamic','routine_grid','detail_macro_callout','comparison_cards','cta_banner_final'],
    use_detail_components:['hero_center_spotlight','overview_flatlay','components_labeled_grid','usage_steps_horizontal','detail_macro_callout','benefit_big_numbers','faq_cards','cta_banner_final'],
    space_mood:['room_mood_editorial','editorial_two_column','detail_macro_callout','spec_table_product','comparison_cards','clean_minimal_list','faq_cards','cta_banner_final'],
    workflow_function:['hero_split_premium','workflow_arrow','feature_dashboard_cards','comparison_cards','benefit_big_numbers','package_included_boxes','trust_checklist','cta_banner_final'],
    function_spec:['product_dark_stage','feature_dashboard_cards','spec_table_product','workflow_arrow','comparison_cards','trust_checklist','faq_cards','cta_banner_final'],
    mood_texture:['editorial_two_column','material_texture_grid','detail_macro_callout','lookbook_collage','benefit_big_numbers','faq_cards','cta_banner_final'],
    use_clean_storage:['clean_minimal_list','usage_lifestyle_sequence','spec_table_product','storage_open_detail','trust_checklist','faq_cards','cta_banner_final'],
    taste_package:['hero_center_spotlight','usage_lifestyle_sequence','material_texture_grid','package_included_boxes','faq_cards','cta_banner_final'],
    pet_use_safety:['usage_lifestyle_sequence','trust_checklist','clean_minimal_list','faq_cards','cta_banner_final'],
    parent_trust:['usage_lifestyle_sequence','trust_checklist','components_labeled_grid','faq_cards','cta_banner_final'],
    install_before_after:['diagonal_dynamic','usage_steps_horizontal','before_after_split','detail_macro_callout','spec_table_product','faq_cards','cta_banner_final'],
    problem_solution:['problem_scene_grid','solution_spotlight','before_after_split','benefit_big_numbers','usage_lifestyle_sequence','faq_cards','cta_banner_final'],
    intangible_offer:['hero_split_premium','feature_dashboard_cards','benefit_big_numbers','comparison_cards','before_after_split','package_included_boxes','trust_checklist','cta_banner_final'],
    general_dynamic:['hero_split_premium','overview_flatlay','detail_macro_callout','benefit_big_numbers','faq_cards','cta_banner_final']
  };

  const SECTION_TO_LAYOUT_KEYS = {
    HERO:['hero_split_premium','hero_center_spotlight','hero_magazine_cover','product_dark_stage','mobile_scroll_story'],
    PROBLEM:['problem_scene_grid','problem_speech_bubble'], PAIN_POINT:['problem_scene_grid','problem_speech_bubble'], SPACE_PROBLEM:['problem_scene_grid','before_after_split'],
    SOLUTION:['solution_spotlight'], OVERVIEW:['overview_flatlay','clean_minimal_list'], COMPONENTS:['components_labeled_grid','overview_flatlay'], COLLECTION:['components_labeled_grid','package_included_boxes'], PACKAGE:['package_included_boxes'],
    DETAIL:['detail_macro_callout','detail_three_zoom','editorial_two_column'], TEXTURE:['material_texture_grid','detail_macro_callout'], MATERIAL:['material_texture_grid','detail_macro_callout'], FABRIC:['material_texture_grid','detail_macro_callout'],
    USAGE:['usage_lifestyle_sequence','usage_steps_horizontal'], HOW_TO_USE:['usage_steps_horizontal'], INSTALL:['usage_steps_horizontal','diagonal_dynamic'], ROUTINE:['routine_grid'], EXAMPLES:['routine_grid'],
    BEFORE_AFTER:['before_after_split'], COMPARISON:['comparison_cards','before_after_split'], BENEFIT:['benefit_big_numbers','three_card_news'], FEATURE:['feature_dashboard_cards','benefit_big_numbers'], WORKFLOW:['workflow_arrow','feature_dashboard_cards'], RESULT:['feature_dashboard_cards','benefit_big_numbers'],
    SIZE:['size_fit_guide','spec_table_product'], SIZE_USE:['size_fit_guide'], SIZE_TARGET:['size_fit_guide'], COLOR_SIZE:['option_color_cards'], FIT:['size_fit_guide','lookbook_collage'], WEAR_SCENE:['lookbook_collage','usage_lifestyle_sequence'],
    STORAGE:['storage_open_detail','clean_minimal_list'], CLEANING:['usage_steps_horizontal','clean_minimal_list'], CARE:['usage_steps_horizontal','trust_checklist'],
    MOOD:['editorial_two_column','lookbook_collage'], ROOM_MOOD:['room_mood_editorial','editorial_two_column'], LIFESTYLE:['room_mood_editorial','lookbook_collage'], GIFT:['gift_packaging_scene'],
    POINT:['three_card_news','benefit_big_numbers'], INGREDIENT:['material_texture_grid'], HOW_TO_EAT:['usage_lifestyle_sequence'], USE_SCENE:['usage_lifestyle_sequence'], TASTE_SCENE:['usage_lifestyle_sequence'],
    SPEC:['spec_table_product','clean_minimal_list'], FAQ:['faq_cards','trust_checklist'], CTA:['cta_banner_final','hero_split_premium']
  };

  function hashString(s){ let h=0; String(s||'').split('').forEach(ch=>{ h=((h<<5)-h+ch.charCodeAt(0))|0; }); return Math.abs(h); }
  function uniqueList(list){ return [...new Set((list||[]).filter(Boolean))]; }
  function pickLayoutTemplate(section, analysis={}, idx=0){
    const sectionPool = SECTION_TO_LAYOUT_KEYS[section] || [];
    const templatePool = TEMPLATE_TO_LAYOUT_KEYS[analysis.template_type] || [];
    const fallback = ['hero_split_premium','overview_flatlay','detail_macro_callout','benefit_big_numbers','faq_cards','cta_banner_final','editorial_two_column','mobile_scroll_story'];
    const pool = uniqueList(sectionPool.concat(templatePool).concat(fallback)).filter(k => DETAILPAGE_LAYOUT_TEMPLATES[k]);
    const seed = hashString(`${analysis.template_type||''}|${section}|${idx}|${Date.now()}|${Math.floor(Math.random()*1e6)}`);
    return DETAILPAGE_LAYOUT_TEMPLATES[pool[seed % pool.length]] || DETAILPAGE_LAYOUT_TEMPLATES.mobile_scroll_story;
  }
  function buildLayoutBlock(section, analysis, idx){
    const t = pickLayoutTemplate(section, analysis, idx);
    return `[상세페이지 디자인 틀 - "${t.label}"]\n적용 구도: ${t.layout}\n적합 용도: ${t.use}\n중요: 이 틀을 우선 적용하세요. 같은 상세페이지 안에서 모든 섹션이 상단 제목-중앙 제품-하단 3카드 구조로 반복되면 실패입니다.\n제품 사실성은 유지하되, 구도/여백/콜아웃/카드 배치는 이 틀에 맞게 바꾸세요.`;
  }

  // v20.9 이식: SHOT TYPE 상세 — 섹션마다 "어떤 컷이어야 하는지" 강하게 명시
  const SHOT_TYPES = {
    HERO: `[SHOT TYPE - HERO] ⚠️ 강한 첫인상 (3초 안에 시선 강탈)
잡지 표지/광고 키비주얼처럼 임팩트 있게. 제품 1개를 화면을 압도하는 크기로 메인 배치(클로즈업/영웅샷), 명확한 시선 집중 포인트 1곳.
큰 메인 헤드라인을 과감하게(화면 상단/측면). 제품을 작게 여러 개 흩뿌리거나 밋밋한 카탈로그 나열식으로 만들지 마세요(약해 보임).
배경은 무드에 맞춘 단순/고급 연출(스포트라이트·그림자·여백 활용)로 제품이 주인공이 되게. 하단 카드는 최대 2개 또는 생략.`,
    PROBLEM: `[SHOT TYPE - PROBLEM] ⚠️ 매우 중요
제품 사진을 메인으로 쓰지 마세요. 이 컷은 "고객의 고민 장면"입니다.
다음 중 하나를 메인 비주얼로: (A) 고객이 망설이는 라이프스타일 컷 (B) 실패 흔적(먼지 쌓인 물건, 영수증 등) (C) 고민하는 표정 클로즈업 (D) 3~4분할 고민 장면 그리드.
제품은 등장하지 않거나 작게 구석에. 배경 톤은 약간 차분하게 (감정 환기), 다음 섹션과 대비.`,
    SPACE_PROBLEM: `[SHOT TYPE - SPACE PROBLEM] ⚠️
공간 분위기 고민 장면. 칙칙하거나 정돈 안 된 공간 vs 원하는 무드를 대비. 제품은 아직 등장 안 하거나 작게.`,
    PAIN_POINT: `[SHOT TYPE - PAIN POINT] ⚠️
업무/시간 고민 장면. 반복 작업, 쌓인 일, 늦은 밤 작업 같은 상황 연출. 제품/화면은 보조로만.`,
    PET_PROBLEM:`[SHOT TYPE - PET PROBLEM] ⚠️ 반려 생활의 고민 장면. 반려동물과 보호자의 일상, 관리 어려움 상황. 제품은 작게.`,
    PARENT_PROBLEM:`[SHOT TYPE - PARENT PROBLEM] ⚠️ 부모의 육아 고민 장면. 아이와의 일상, 선택의 어려움. 제품은 작게.`,
    CAR_PROBLEM:`[SHOT TYPE - CAR PROBLEM] ⚠️ 차량 내 불편 장면. 지저분하거나 정리 안 된 차 내부. 제품은 아직 작게.`,
    OVERVIEW: `[SHOT TYPE - OVERVIEW]
원본 제품 전체 구성 소개 컷. 콜아웃 라벨을 활용해 정보 전달 모드로. 화이트 배경, 정렬된 플랫레이.`,
    COMPONENTS: `[SHOT TYPE - COMPONENTS] ⚠️ 매우 중요
구성품을 개별로 분리해 가지런히 정렬. 각 구성품에 라벨 카드/콜아웃. 그리드 또는 가로 정렬. 원본에 보이는 것만, 임의 추가 금지.`,
    COLLECTION:`[SHOT TYPE - COLLECTION] 세트/구성품을 정돈해 배열 + 라벨. 원본에 보이는 구성만.`,
    PACKAGE:`[SHOT TYPE - PACKAGE] 포함 구성/서비스 범위를 박스/카드로 정리. 확인된 구성만.`,
    USAGE: `[SHOT TYPE - USAGE] ⚠️ 매우 중요
실제 사용 장면. 정면 평면샷 금지, 45도 측면/옆모습/뒷모습 우선. 실제 환경(문/벽/공간)이 보이게, 자연광.
사람이 등장하면 얼굴 정면보다 옆/뒤/손 위주. 첨부된 실사용 사진이 있으면 그 앵글/구도를 기준으로.`,
    HOW_TO_USE: `[SHOT TYPE - HOW TO USE] ⚠️
1 사용 전 → 2 제품 사용 → 3 사용 후의 3단계 시퀀스. 각 단계 클로즈업 + 짧은 동사형 설명.`,
    HOW_TO_EAT:`[SHOT TYPE - HOW TO EAT] 섭취/활용 장면. 먹는 상황, 곁들임, 추천 조합을 자연스럽게.`,
    ROUTINE:`[SHOT TYPE - ROUTINE] 부위별/상황별 활용 3분할. 동작 아이콘 + 짧은 설명. 원본 제품이 실제 가능한 범위만.`,
    WORKFLOW:`[SHOT TYPE - WORKFLOW] 입력→처리→결과 흐름도. 단계 카드/화살표. 실제 가능한 기능만.`,
    INSTALL:`[SHOT TYPE - INSTALL] 설치/장착 과정 컷. 차량/공간에 부착하는 단계. 실제 설치 위치가 보이게.`,
    DETAIL: `[SHOT TYPE - DETAIL] ⚠️ 매우 중요
특정 부위를 크게 클로즈업한 매크로샷. 전체샷 금지, 부분만 크게. 손잡이/연결부/마감/소재/라벨 중 하나가 화면의 70%.
또는 매크로 디테일 2~3컷 그리드. 무인양품/다이슨 카탈로그 톤. 차분한 조명, 그림자 강조.`,
    TEXTURE:`[SHOT TYPE - TEXTURE] ⚠️ 제형/질감/재질감 매크로 컷. 크림/원단/표면을 크게. 확인 안 된 효능 표기 금지.`,
    FABRIC:`[SHOT TYPE - FABRIC] ⚠️ 소재 클로즈업. 촉감/두께/신축성을 시각적으로. 확인된 정보만.`,
    MATERIAL:`[SHOT TYPE - MATERIAL] ⚠️ 소재/재질 매크로. 안전성/위생 인상을 시각으로. 확인된 정보만.`,
    BEFORE_AFTER: `[SHOT TYPE - BEFORE AFTER] ⚠️ 매우 중요
좌우 Before/After 비교. 실제 효과 보장 표현 금지, 연출컷으로. "사용 전 혼잡함 / 사용 후 정리된 전달감" 같은 구체 표현.`,
    COMPARISON:`[SHOT TYPE - COMPARISON] ⚠️ 일반 제품 vs 이 제품 비교 카드/표. 과장 없이 시각적 차이와 구매 포인트만.`,
    BENEFIT: `[SHOT TYPE - BENEFIT] ⚠️ 매우 중요
데이터/수치 시각화. 제품 단독샷 금지. 큰 숫자/% 중앙 배치 또는 3개 큰 수치 카드. 와디즈/Tesla 데이터 슬라이드 톤.
※ 확인되지 않은 수치는 만들지 말 것.`,
    FEATURE:`[SHOT TYPE - FEATURE] 기능 카드 4개 또는 기기/화면 목업 + 아이콘. 기능명 + 사용자 이점.`,
    SPEC:`[SHOT TYPE - SPEC] ⚠️ 스펙 테이블/도면 인포그래픽. 원본/입력에 없는 수치는 절대 만들지 말 것. 모르는 항목은 이미지에서 제외하고, "확인 필요" 같은 문구를 이미지 안에 쓰지 말 것.`,
    RESULT:`[SHOT TYPE - RESULT] 사용 후 기대 결과 컷. 작업 흐름 개선/결과 예시. 성과 보장 대신 "흐름 개선" 표현.`,
    SIZE:`[SHOT TYPE - SIZE] ⚠️ 크기/치수 안내. 치수 표시, 손/공간과 비교. 확인 안 된 사이즈 지어내기 금지.`,
    SIZE_USE:`[SHOT TYPE - SIZE USE] ⚠️ 크기/배치/사용감. 치수표, 배치 예시, 거리감. 확인된 수치만.`,
    SIZE_TARGET:`[SHOT TYPE - SIZE TARGET] ⚠️ 대상 크기/적합 대상. 반려동물/아이 크기 기준. 확인된 정보만.`,
    COLOR_SIZE:`[SHOT TYPE - COLOR SIZE] ⚠️ 색상/사이즈 옵션 카드/표. 확인된 옵션만.`,
    STORAGE:`[SHOT TYPE - STORAGE] 보관/휴대 컷. 제품 크기감, 보관 위치, 작은 공간 배치. "신발장 한쪽" 같은 생활 장면.`,
    CLEANING:`[SHOT TYPE - CLEANING] 세척/관리 장면. 물에 헹구거나 닦는 모습. 관리 편의 강조.`,
    CARE:`[SHOT TYPE - CARE] 관리/세탁 안내. 관리 방법을 단계나 아이콘으로.`,
    FIT:`[SHOT TYPE - FIT] ⚠️ 착용 핏. 정면/측면/활동 핏 컷. 사람 옆모습/뒷모습 OK. 핏과 착용 장면 중심.`,
    WEAR_SCENE:`[SHOT TYPE - WEAR SCENE] 착용 상황 라이프스타일. 일상/운동/외출 장면. 사용 상황 중심.`,
    LIFESTYLE:`[SHOT TYPE - LIFESTYLE] 제품을 일상에서 쓰는 무드 컷. 휴대/사용 장면 자연스럽게.`,
    GIFT:`[SHOT TYPE - GIFT] 선물 무드 컷. 패키지/포장 느낌, 주는 상황 연출.`,
    MOOD:`[SHOT TYPE - MOOD] ⚠️ 감성 무드 컷. 제품 + 라이프스타일 오브젝트, 분위기 우선. 뷰티/식품/라이프스타일 톤.`,
    POINT:`[SHOT TYPE - POINT] 성분/향/핵심 포인트 3개 카드. 확인된 정보만.`,
    INGREDIENT:`[SHOT TYPE - INGREDIENT] 원재료/성분 시각화. 재료를 펼쳐 보여주거나 아이콘. 확인된 것만.`,
    ROOM_MOOD:`[SHOT TYPE - ROOM MOOD] ⚠️ 제품이 공간에 주는 분위기. 방/사무실 라이프스타일 연출컷. 공간 변화 중심.`,
    USE_SCENE:`[SHOT TYPE - USE SCENE] 실제 사용 장면. 이 제품이 실제로 쓰이는 순간(휴대·사용)을 그 제품에 어울리는 맥락에서 자연스럽게. 제품과 무관한 공간 연출 금지.`,
    TASTE_SCENE:`[SHOT TYPE - TASTE SCENE] 맛/상황 연출. 먹는 순간, 어울리는 상황을 식욕 돋게.`,
    EXAMPLES:`[SHOT TYPE - EXAMPLES] 활용 예시 모음. 다양한 사용처를 그리드로.`,
    FAQ: `[SHOT TYPE - FAQ]
Q&A 카드 3~4개. Q 굵게 + A 회색. 텍스트 중심, 화이트 배경. 반품/배송/사용법 등 구매 전 망설임 해소.`,
    CTA: `[SHOT TYPE - CTA]
제품의 깔끔한 마감샷 + 강한 오렌지 CTA 배너(하단, 가장 강조). 정제된 단독샷 또는 라이프스타일 마무리. 행동 유도 톤.`,
    SOLUTION:`[SHOT TYPE - SOLUTION] ⚠️ "그래서 우리가 만들었습니다" 해답 등장. 제품 단독 등장, PROBLEM과 시각적 강한 대비. 밝은 배경/스포트라이트.`
  };
  function shotFor(section){ return SHOT_TYPES[section] || ''; }

  // v21.7: 섹션별 세일즈 카피 공식 - 즉흥 미사여구가 아닌 검증된 설득 구조
  const COPY_FORMULAS = {
    HERO: `[카피 공식 - BAB (Before-After-Bridge)]
이 컷의 카피는 "이전 상태 → 바뀐 모습 → 제품이 다리" 구조로 욕망을 자극하세요.
예 구조: (지금의 답답함) → (이렇게 달라집니다) → (이 제품으로). 헤드라인은 'After(바뀐 모습)'를 한 줄로 보여주세요.`,
    PROBLEM: `[카피 공식 - WHY 흐름(질문→원인→해결)]
다짜고짜 장점 나열 금지. ① 고객이 속으로 던지는 질문/고민 한 줄 → ② 그 불편의 원인 → ③ "그래서 이 제품"으로 잇기.
예: "아무거나 사도 괜찮을까? → 종류가 너무 많아 헷갈립니다 → 그래서 이걸로 정리하세요". 단정형 공감 우선.`,
    SPACE_PROBLEM: `[카피 공식 - PAS]\n공간/상황의 불편을 짚고 증폭한 뒤 해결을 암시하세요.`,
    PAIN_POINT: `[카피 공식 - PAS]\n업무/시간 낭비의 고통을 구체적으로 짚고 증폭하세요. "매번 ○○하느라 ○시간" 식.`,
    PET_PROBLEM:`[카피 공식 - PAS]\n반려 생활의 고민을 공감하고 증폭한 뒤 해결을 암시하세요.`,
    PARENT_PROBLEM:`[카피 공식 - PAS]\n부모의 걱정을 공감하고 증폭한 뒤 안심을 암시하세요.`,
    CAR_PROBLEM:`[카피 공식 - PAS]\n차량 내 불편을 짚고 증폭하세요.`,
    SOLUTION:`[카피 공식 - Bridge(전환점)]\n"그래서 만들었습니다" 톤으로 문제→해답 전환을 선언하세요. 안도감과 기대감.`,
    OVERVIEW:`[카피 공식 - 전체 가치 요약]\n"무엇인지 + 왜 좋은지"를 한눈에. 구성을 보여주되 각 요소가 주는 이득을 짧게.`,
    COMPONENTS:`[카피 공식 - 가치 환산]\n구성품을 나열만 하지 말고 "이만큼 다 드립니다" 풍성함/이득으로 연결하세요.`,
    COLLECTION:`[카피 공식 - 가치 환산]\n세트 구성의 풍성함을 이득으로 표현하세요.`,
    PACKAGE:`[카피 공식 - 가치 환산]\n포함 범위를 "이게 다 포함" 이득으로 표현하세요.`,
    USAGE:`[카피 공식 - 쉬움/즉시성 강조]\n"이렇게 쉽게/빠르게 됩니다"로 사용 장벽을 낮추세요. 단계는 짧은 동사형.`,
    HOW_TO_USE:`[카피 공식 - 3스텝 단순화]\n"1→2→3 이게 끝" 식으로 쉬움을 강조하세요.`,
    HOW_TO_EAT:`[카피 공식 - 상황 제안]\n"이럴 때 이렇게" 섭취 상황을 구체적으로 제안하세요.`,
    ROUTINE:`[카피 공식 - 다양한 활용]\n"이것 하나로 이만큼" 활용 범위의 넓음을 이득으로.`,
    WORKFLOW:`[카피 공식 - 자동화 이득]\n"복잡한 게 → 이렇게 간단히" 절감되는 시간/수고를 강조하세요.`,
    INSTALL:`[카피 공식 - 쉬움 강조]\n"누구나 몇 분이면" 설치 장벽을 낮추세요.`,
    DETAIL:`[카피 공식 - FAB (Feature-Advantage-Benefit)]\n디테일(기능/소재)을 보여주되 "그래서 당신에게 이런 점이 좋다"는 이득으로 연결하세요. 단순 스펙 나열 금지.`,
    TEXTURE:`[카피 공식 - 감각 묘사 + FAB]\n질감/제형을 감각적으로 묘사하고 그것이 주는 이득으로 연결하세요.`,
    FABRIC:`[카피 공식 - FAB]\n소재 특성 → 그것이 주는 착용 이득으로 연결하세요.`,
    MATERIAL:`[카피 공식 - FAB]\n소재/재질 → 안전·위생·내구 이득으로 연결하세요.`,
    BEFORE_AFTER:`[카피 공식 - 대비 극대화]\n"전 vs 후"의 차이를 시각+카피로 극대화하세요. 단, 효과 보장 표현 금지, 연출/인상 표현으로.`,
    COMPARISON:`[카피 공식 - 차별화]\n"일반 제품은 ○○, 이건 △△" 우위를 구체적으로. 과장 없이 사실 기반.`,
    BENEFIT:`[카피 공식 - FAB + 숫자]\n핵심 장점을 "기능→이득"으로, 가능하면 구체적 숫자로 신뢰를 더하세요. 확인 안 된 수치 금지.`,
    FEATURE:`[카피 공식 - FAB]\n기능명 + 그 기능이 주는 실제 사용자 이득을 짝지어 표현하세요.`,
    SPEC:`[카피 공식 - 팩트 신뢰]\n수치/스펙은 객관적으로. 확인된 것만, 모르면 표기 안 함. 신뢰감이 카피.`,
    RESULT:`[카피 공식 - 기대 결과]\n"이렇게 됩니다"는 보장이 아닌 기대/개선 톤으로. 과장 금지.`,
    SIZE:`[카피 공식 - 구체 수치]\n크기를 손/공간과 비교해 직관적으로. 확인된 수치만.`,
    SIZE_USE:`[카피 공식 - 구체 수치 + 배치]\n크기와 배치를 직관적으로 보여주세요.`,
    SIZE_TARGET:`[카피 공식 - 적합성]\n"누구에게/어떤 크기에 맞는지" 명확히.`,
    COLOR_SIZE:`[카피 공식 - 선택 이득]\n옵션의 다양함을 선택 이득으로.`,
    STORAGE:`[카피 공식 - 편의 이득]\n"이렇게 간편하게 보관" 공간·편의 이득으로.`,
    CLEANING:`[카피 공식 - 편의 이득]\n"세척이 이렇게 쉽다" 관리 편의를 이득으로.`,
    CARE:`[카피 공식 - 편의 이득]\n관리 방법을 쉬움으로 표현하세요.`,
    FIT:`[카피 공식 - 착용 이득]\n핏이 주는 편안함/멋짐을 이득으로.`,
    WEAR_SCENE:`[카피 공식 - 상황 공감]\n"이런 자리에 딱" 착용 상황을 제안하세요.`,
    LIFESTYLE:`[카피 공식 - 라이프스타일 욕망]\n제품이 있는 일상의 무드를 욕망으로 연결하세요.`,
    GIFT:`[카피 공식 - 선물 가치]\n"받는 사람이 좋아할" 선물 가치를 강조하세요.`,
    MOOD:`[카피 공식 - 감성 욕망]\n제품의 무드/감성을 욕망으로 연결. 정보보다 느낌.`,
    POINT:`[카피 공식 - 핵심 3가지]\n핵심 포인트를 3개로 압축, 각각 이득으로.`,
    INGREDIENT:`[카피 공식 - 신뢰 + 이득]\n원재료/성분의 신뢰성을 이득으로. 확인된 것만.`,
    ROOM_MOOD:`[카피 공식 - 공간 변화 욕망]\n"이 공간이 이렇게 달라진다" 변화를 욕망으로.`,
    USE_SCENE:`[카피 공식 - 상황 제안]\n"이럴 때 이렇게 쓴다" 구체적 사용 상황.`,
    TASTE_SCENE:`[카피 공식 - 식욕 자극]\n맛/상황을 식욕을 돋우는 감각 카피로.`,
    EXAMPLES:`[카피 공식 - 다양한 활용]\n여러 활용 예시로 범용성을 이득으로.`,
    FAQ:`[카피 공식 - 안심 제공]\n구매 전 불안(반품/배송/사용)을 Q&A로 미리 해소해 안심을 주세요.`,
    CTA:`[카피 공식 - 긴급성 + 행동유도]\n"지금 시작하세요" 같은 명확한 행동 지시 + (가능하면 자연스러운 이유). 마지막 한 번의 강한 푸시.`
  };
  function formulaFor(section){ return COPY_FORMULAS[section] || ''; }
  // 같은 상품군이라도 매번 살짝 다른 섹션 조합 (단조로움 방지)
  // HERO는 항상 첫번째, CTA는 항상 마지막 고정. 중간 섹션에서 변주.
  const SECTION_POOL_BY_TEMPLATE = {
    care_before_after:    ['PROBLEM','HOW_TO_USE','BEFORE_AFTER','DETAIL','STORAGE','TEXTURE','COMPARISON','FAQ'],
    usage_components:     ['PROBLEM','COMPONENTS','USAGE','BENEFIT','DETAIL','ROUTINE','SPEC','FAQ'],
    use_detail_components:['PROBLEM','COMPONENTS','USAGE','DETAIL','BENEFIT','SPEC','COMPARISON','FAQ'],
    space_mood:           ['SPACE_PROBLEM','ROOM_MOOD','DETAIL','SIZE_USE','COMPARISON','MATERIAL','LIFESTYLE','FAQ'],
    workflow_function:    ['PAIN_POINT','WORKFLOW','FEATURE','RESULT','PACKAGE','SPEC','COMPARISON','FAQ'],
    function_spec:        ['PAIN_POINT','FEATURE','SPEC','RESULT','WORKFLOW','COMPARISON','PACKAGE','FAQ'],
    wear_fit:             ['PROBLEM','FIT','FABRIC','DETAIL','COLOR_SIZE','WEAR_SCENE','SIZE','FAQ'],
    mood_texture:         ['MOOD','TEXTURE','POINT','INGREDIENT','USE_SCENE','BENEFIT','COLLECTION','FAQ'],
    use_clean_storage:    ['USE_SCENE','MATERIAL','SIZE','CLEANING','STORAGE','DETAIL','COMPARISON','FAQ'],
    taste_package:        ['TASTE_SCENE','INGREDIENT','HOW_TO_EAT','STORAGE','POINT','BENEFIT','COLLECTION','FAQ'],
    pet_use_safety:       ['PET_PROBLEM','USE_SCENE','MATERIAL','SIZE_TARGET','CLEANING','DETAIL','BENEFIT','FAQ'],
    parent_trust:         ['PARENT_PROBLEM','USE_SCENE','MATERIAL','COMPONENTS','SIZE_TARGET','CARE','BENEFIT','FAQ'],
    install_before_after: ['CAR_PROBLEM','INSTALL','BEFORE_AFTER','SIZE_USE','MATERIAL','DETAIL','COMPARISON','FAQ'],
    detail_lifestyle:     ['PROBLEM','SOLUTION','DETAIL','SPEC','LIFESTYLE','COLOR_SIZE','FAQ','GIFT'],
    problem_solution:     ['PROBLEM','SOLUTION','OVERVIEW','DETAIL','USAGE','BENEFIT','COMPARISON','FAQ'],
    intangible_offer:     ['PROBLEM','SOLUTION','OVERVIEW','BENEFIT','COMPARISON','RESULT','PACKAGE','USAGE','BEFORE_AFTER','FAQ'],
    general_dynamic:      ['PROBLEM','OVERVIEW','DETAIL','USAGE','BENEFIT','COMPARISON','SPEC','FAQ']
  };

  const STABLE_SECTION_ORDER_V12 = {
    detail_lifestyle:     ['PROBLEM','SOLUTION','DETAIL','SPEC','LIFESTYLE','COLOR_SIZE','FAQ'],
    wear_fit:             ['PROBLEM','FIT','FABRIC','COLOR_SIZE','WEAR_SCENE','SIZE','FAQ'],
    usage_components:     ['PROBLEM','COMPONENTS','USAGE','DETAIL','BENEFIT','ROUTINE','FAQ'],
    use_detail_components:['PROBLEM','COMPONENTS','USAGE','DETAIL','BENEFIT','SPEC','FAQ'],
    function_spec:        ['PAIN_POINT','FEATURE','SPEC','USAGE','PACKAGE','FAQ'],
    workflow_function:    ['PAIN_POINT','WORKFLOW','FEATURE','RESULT','PACKAGE','FAQ'],
    space_mood:           ['SPACE_PROBLEM','ROOM_MOOD','DETAIL','SIZE_USE','MATERIAL','FAQ'],
    mood_texture:         ['MOOD','TEXTURE','POINT','HOW_TO_USE','COLLECTION','FAQ'],
    taste_package:        ['TASTE_SCENE','PACKAGE','INGREDIENT','HOW_TO_EAT','STORAGE','FAQ'],
    problem_solution:     ['PROBLEM','SOLUTION','OVERVIEW','DETAIL','USAGE','BENEFIT','FAQ'],
    general_dynamic:      ['PROBLEM','SOLUTION','OVERVIEW','DETAIL','USAGE','SPEC','FAQ']
  };

  // v21.8.24.21: 구조 다양성 — 템플릿마다 '전문가 흐름' 청사진을 여러 개 두고 매 생성마다 변주.
  // (역할 무결성은 유지하면서, 같은 상품도 매번 다른 섹션 구성/순서로 만들어진다.)
  const SECTION_BLUEPRINTS_V21 = {
    detail_lifestyle: [
      ['PROBLEM','SOLUTION','DETAIL','SPEC','LIFESTYLE','COLOR_SIZE','FAQ'],
      ['PROBLEM','STORAGE','DETAIL','COLOR_SIZE','LIFESTYLE','GIFT','FAQ'],
      ['LIFESTYLE','PROBLEM','SOLUTION','DETAIL','SPEC','GIFT','FAQ'],
      ['PROBLEM','DETAIL','STORAGE','SPEC','LIFESTYLE','COMPARISON','FAQ']
    ],
    wear_fit: [
      ['PROBLEM','FIT','FABRIC','COLOR_SIZE','WEAR_SCENE','SIZE','FAQ'],
      ['PROBLEM','WEAR_SCENE','FIT','DETAIL','COLOR_SIZE','FABRIC','FAQ'],
      ['FIT','PROBLEM','FABRIC','COLOR_SIZE','WEAR_SCENE','DETAIL','FAQ'],
      ['WEAR_SCENE','FIT','DETAIL','FABRIC','COLOR_SIZE','SIZE','FAQ']
    ],
    usage_components: [
      ['PROBLEM','COMPONENTS','USAGE','DETAIL','BENEFIT','ROUTINE','FAQ'],
      ['PROBLEM','USAGE','COMPONENTS','ROUTINE','BENEFIT','DETAIL','FAQ'],
      ['COMPONENTS','PROBLEM','USAGE','BENEFIT','ROUTINE','SPEC','FAQ'],
      ['PROBLEM','USAGE','BENEFIT','COMPONENTS','DETAIL','COMPARISON','FAQ']
    ],
    use_detail_components: [
      ['PROBLEM','COMPONENTS','USAGE','DETAIL','BENEFIT','SPEC','FAQ'],
      ['PROBLEM','USAGE','DETAIL','COMPONENTS','BENEFIT','COMPARISON','FAQ'],
      ['OVERVIEW','PROBLEM','DETAIL','USAGE','BENEFIT','SPEC','FAQ'],
      ['PROBLEM','DETAIL','COMPONENTS','USAGE','SPEC','BENEFIT','FAQ']
    ],
    function_spec: [
      ['PAIN_POINT','FEATURE','SPEC','USAGE','PACKAGE','FAQ'],
      ['PAIN_POINT','FEATURE','USAGE','SPEC','COMPARISON','FAQ'],
      ['FEATURE','PAIN_POINT','SPEC','RESULT','PACKAGE','FAQ'],
      ['PAIN_POINT','FEATURE','RESULT','SPEC','TRUST','FAQ']
    ],
    workflow_function: [
      ['PAIN_POINT','WORKFLOW','FEATURE','RESULT','PACKAGE','FAQ'],
      ['PAIN_POINT','FEATURE','WORKFLOW','RESULT','COMPARISON','FAQ'],
      ['WORKFLOW','PAIN_POINT','FEATURE','RESULT','PACKAGE','FAQ'],
      ['PAIN_POINT','WORKFLOW','RESULT','FEATURE','PACKAGE','FAQ']
    ],
    space_mood: [
      ['SPACE_PROBLEM','ROOM_MOOD','DETAIL','SIZE_USE','MATERIAL','FAQ'],
      ['SPACE_PROBLEM','ROOM_MOOD','MATERIAL','DETAIL','COMPARISON','FAQ'],
      ['ROOM_MOOD','SPACE_PROBLEM','DETAIL','SIZE_USE','LIFESTYLE','FAQ'],
      ['ROOM_MOOD','DETAIL','MATERIAL','SIZE_USE','COMPARISON','FAQ']
    ],
    mood_texture: [
      ['MOOD','TEXTURE','POINT','HOW_TO_USE','COLLECTION','FAQ'],
      ['MOOD','POINT','TEXTURE','INGREDIENT','USE_SCENE','FAQ'],
      ['TEXTURE','MOOD','POINT','HOW_TO_USE','BENEFIT','FAQ'],
      ['MOOD','TEXTURE','INGREDIENT','POINT','COLLECTION','FAQ']
    ],
    taste_package: [
      ['TASTE_SCENE','PACKAGE','INGREDIENT','HOW_TO_EAT','STORAGE','FAQ'],
      ['TASTE_SCENE','INGREDIENT','HOW_TO_EAT','PACKAGE','POINT','FAQ'],
      ['TASTE_SCENE','HOW_TO_EAT','INGREDIENT','STORAGE','BENEFIT','FAQ'],
      ['TASTE_SCENE','PACKAGE','HOW_TO_EAT','INGREDIENT','STORAGE','FAQ']
    ],
    problem_solution: [
      ['PROBLEM','SOLUTION','OVERVIEW','DETAIL','USAGE','BENEFIT','FAQ'],
      ['PROBLEM','SOLUTION','BEFORE_AFTER','DETAIL','BENEFIT','COMPARISON','FAQ'],
      ['PROBLEM','OVERVIEW','SOLUTION','USAGE','DETAIL','BENEFIT','FAQ'],
      ['PROBLEM','SOLUTION','DETAIL','BEFORE_AFTER','USAGE','BENEFIT','FAQ']
    ],
    general_dynamic: [
      ['PROBLEM','SOLUTION','OVERVIEW','DETAIL','USAGE','SPEC','FAQ'],
      ['PROBLEM','OVERVIEW','DETAIL','USAGE','BENEFIT','COMPARISON','FAQ'],
      ['OVERVIEW','PROBLEM','SOLUTION','DETAIL','BENEFIT','USAGE','FAQ'],
      ['PROBLEM','DETAIL','OVERVIEW','BENEFIT','USAGE','SPEC','FAQ']
    ],
    // v21.8.24.33: 무형(전자책/강의/코칭/템플릿) 전용 구조 — 실물이 약하므로 공감→솔루션→공개→특장점→비교→구성 흐름.
    intangible_offer: [
      ['PROBLEM','SOLUTION','OVERVIEW','BENEFIT','COMPARISON','PACKAGE','FAQ'],
      ['PROBLEM','SOLUTION','BENEFIT','RESULT','COMPARISON','USAGE','FAQ'],
      ['PROBLEM','OVERVIEW','SOLUTION','BENEFIT','BEFORE_AFTER','PACKAGE','FAQ'],
      ['PROBLEM','SOLUTION','OVERVIEW','FEATURE','COMPARISON','PACKAGE','FAQ']
    ],
    // v21.8.24.50: 저관여(저가·소모·생활·잡화)도 2번째 섹션은 'pain+공감'으로 시작(기능 나열 금지).
    // 단 저관여이므로 긴 스토리가 아니라 PROBLEM '한 컷 공감' → 이후 선택 이유·옵션·활용 중심으로 간결히.
    __LOW__: [
      ['PROBLEM','BENEFIT','COLOR_SIZE','USE_SCENE','DETAIL','FAQ'],
      ['PROBLEM','OVERVIEW','BENEFIT','LIFESTYLE','COLOR_SIZE','FAQ'],
      ['PROBLEM','BENEFIT','USE_SCENE','COLOR_SIZE','DETAIL','FAQ'],
      ['PROBLEM','COLOR_SIZE','USE_SCENE','BENEFIT','COMPARISON','FAQ']
    ]
  };
  let __lastBlueprintIdx = {};
  function pickBlueprintMiddle(tmpl, need){
    const variants = SECTION_BLUEPRINTS_V21[tmpl];
    if(!variants || !variants.length) return null;
    // 직전과 다른 청사진을 우선 선택해 연속 생성 시 구조가 겹치지 않게 한다.
    let idx = Math.floor(Date.now() + Math.random()*1e6) % variants.length;
    if(variants.length > 1 && idx === __lastBlueprintIdx[tmpl]) idx = (idx + 1) % variants.length;
    __lastBlueprintIdx[tmpl] = idx;
    const order = variants[idx].slice();
    const hasFaq = order.includes('FAQ');
    let result;
    if(hasFaq && need >= 3){
      const withoutFaq = order.filter(s => s !== 'FAQ');
      result = withoutFaq.slice(0, need - 1).concat('FAQ');
    } else {
      result = order.slice(0, need);
    }
    const fallback = (SECTION_POOL_BY_TEMPLATE[tmpl] || SECTION_POOL_BY_TEMPLATE.general_dynamic || []).concat(['BENEFIT','DETAIL','OVERVIEW','COMPARISON','SPEC','USAGE','SOLUTION','LIFESTYLE']);
    fallback.forEach(s => { if(result.length < need && !result.includes(s)) result.push(s); });
    return result.slice(0, need);
  }

  function pickStableMiddleV12(tmpl, need){
    const order = STABLE_SECTION_ORDER_V12[tmpl];
    if(!order) return null;
    const hasFaq = order.includes('FAQ');
    let result;
    if(hasFaq && need >= 3){
      const withoutFaq = order.filter(s => s !== 'FAQ');
      result = withoutFaq.slice(0, need - 1).concat('FAQ');
    } else {
      result = order.slice(0, need);
    }
    const fallback = (SECTION_POOL_BY_TEMPLATE[tmpl] || SECTION_POOL_BY_TEMPLATE.general_dynamic || []).concat(['BENEFIT','DETAIL','OVERVIEW','COMPARISON','SPEC','USAGE','SOLUTION','LIFESTYLE']);
    fallback.forEach(s => { if(result.length < need && !result.includes(s)) result.push(s); });
    return result.slice(0, need);
  }

  // v21.8.24.50: 템플릿별 'pain/공감' 섹션 키(있는 그대로의 역할에 맞춰 선택)
  function problemKeyForTemplate(tmpl){
    const t = String(tmpl || '');
    if(/workflow|function|digital/.test(t)) return 'PAIN_POINT';
    if(/space/.test(t)) return 'SPACE_PROBLEM';
    if(/pet/.test(t)) return 'PET_PROBLEM';
    if(/parent/.test(t)) return 'PARENT_PROBLEM';
    if(/install/.test(t)) return 'CAR_PROBLEM';
    return 'PROBLEM';
  }
  const PROBLEM_SECTION_RE = /PROBLEM|PAIN/;
  // 맛/감성 선행이 핵심 후크인 카테고리는 강제 삽입에서 제외(미각·무드 오프닝이 더 잘 팔림)
  const SENSORY_LED_TEMPLATES = /mood_texture|taste_package/;
  // v21.8.24.50: 2번째 섹션(HERO 바로 다음)을 반드시 pain+공감으로 보장.
  // 이미 2번째가 문제섹션이면 그대로 두고, 아니면 시퀀스 내 문제섹션을 앞으로 당기거나(중복 없이) 템플릿 기본 문제키를 맨 앞에 배치.
  function ensureEarlyEmpathy(seq, tmpl){
    if(SENSORY_LED_TEMPLATES.test(String(tmpl||''))) return seq; // 미각/무드 선행 카테고리는 그 후크 유지
    const middle = seq.slice(1, -1); // HERO/CTA 제외
    if(PROBLEM_SECTION_RE.test(middle[0] || '')) return seq;
    const existing = middle.find(s => PROBLEM_SECTION_RE.test(s));
    const key = existing || problemKeyForTemplate(tmpl);
    const rest = middle.filter(s => !PROBLEM_SECTION_RE.test(s)); // 기존 문제섹션 제거 후 맨 앞으로(중복 방지)
    return ['HERO', key, ...rest, 'CTA'];
  }
  // v21.8.24.50: 최종 시퀀스 정리 — 2번째=공감 보장 + 섹션 중복 제거(COMPARISON 2번 방지) + HERO/CTA 위치 고정 + 개수 정확 보정
  function finalizeSectionSequence(seq, count, tmpl){
    const withEmpathy = ensureEarlyEmpathy(seq, tmpl);
    let mid = [...new Set(withEmpathy.filter(s => s && s !== 'HERO' && s !== 'CTA'))];
    const needMid = Math.max(1, count - 2); // HERO/CTA 제외한 미들 개수
    // 부족하면 안전 보충(중복·COMPARISON 재중복 제외)
    const FILLER = ['BENEFIT','DETAIL','OVERVIEW','USAGE','SOLUTION','LIFESTYLE','SPEC'];
    for(const f of FILLER){ if(mid.length >= needMid) break; if(!mid.includes(f)) mid.push(f); }
    // 많으면 미들에서 잘라 HERO/CTA 보존(FAQ는 가능하면 마지막 미들로 유지)
    if(mid.length > needMid){
      const hasFaq = mid.includes('FAQ');
      mid = mid.filter(s => s !== 'FAQ').slice(0, hasFaq ? needMid - 1 : needMid);
      if(hasFaq) mid.push('FAQ');
    }
    return ['HERO', ...mid, 'CTA'];
  }

  function pickSections(analysis, sectionCount){
    const count = parseInt(sectionCount || '8', 10) || 8;
    const tmpl = analysis.template_type || 'general_dynamic';
    const recommended = (analysis.recommended_sections && analysis.recommended_sections.length) ? analysis.recommended_sections.slice() : null;

    // v21.8.24.31: 저관여 상품이면 전용 구조(사회적증거·옵션·활용 중심)를 우선 사용.
    // v21.8.24.33: 단, 무형/디지털 서비스는 옵션·활용 구조가 안 맞으므로 저관여 override에서 제외(전용 구조 우선).
    const need = Math.max(1, count - 2);
    const isIntangibleTmpl = /intangible_offer|workflow_function|digital_automation/.test(tmpl);
    if((analysis.involvement || '') === 'low' && !isIntangibleTmpl){
      const lowMid = pickBlueprintMiddle('__LOW__', need);
      if(lowMid) return finalizeSectionSequence(['HERO', ...lowMid, 'CTA'], count, tmpl);
    }
    // v21.8.24.21: 구조 다양성 — 청사진 변주를 먼저 시도(역할 무결성 유지 + 매번 다른 구성),
    // 청사진이 없는 템플릿은 기존 안정 순서로 폴백.
    const variedMiddle = pickBlueprintMiddle(tmpl, need) || pickStableMiddleV12(tmpl, need);
    if(variedMiddle){
      return finalizeSectionSequence(['HERO', ...variedMiddle, 'CTA'], count, tmpl);
    }

    // 풀이 있으면 풀에서 변주, 없으면 추천 섹션 사용
    const pool = SECTION_POOL_BY_TEMPLATE[tmpl];
    let middle;
    if(pool){
      // HERO, CTA 뺀 나머지
      const opener = pool[0];
      const hasFaq = pool.includes('FAQ');
      let rest = pool.slice(1).filter(s=>s!=='FAQ');
      // 풀이 need보다 부족하면 공통 보충 섹션 추가 (중복 제외)
      const FILLER = ['BENEFIT','DETAIL','OVERVIEW','COMPARISON','SPEC','USAGE','SOLUTION','LIFESTYLE'];
      FILLER.forEach(f=>{ if(rest.length < need && f!==opener && !rest.includes(f)) rest.push(f); });
      const shuffledRest = shuffleSeeded(rest.slice());
      let seq = [opener, ...shuffledRest];
      if(hasFaq && need >= 3){
        seq = seq.slice(0, need-1);
        seq.push('FAQ');
      } else {
        seq = seq.slice(0, need);
      }
      middle = seq;
    } else if(recommended){
      const inner = recommended.filter(s=>!/HERO|CTA/i.test(s));
      middle = inner.slice(0, Math.max(1, count-2));
    } else {
      middle = ['PROBLEM','OVERVIEW','DETAIL','USAGE','BENEFIT','SPEC'].slice(0, Math.max(1, count-2));
    }
    const result = ['HERO', ...middle, 'CTA'];
    return finalizeSectionSequence(result, count, tmpl);
  }

  // 시드 기반 셔플 (매 호출 다른 순서, Date 기반)
  function shuffleSeeded(arr){
    let seed = Date.now() % 100000;
    const rand = ()=>{ seed = (seed*9301 + 49297) % 233280; return seed/233280; };
    for(let i=arr.length-1; i>0; i--){
      const j = Math.floor(rand()*(i+1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }
  function defaultRatio(section){
    // v21.8.24.49: 상세페이지는 세로 스크롤 전용 → 정사각(1:1)·가로(3:2) 제거. HERO 포함 전 섹션 4:5(세로)로 통일
    // (폭이 같아 [세로 1장 합치기]가 깔끔하게 이어짐). 9:16 등 다른 세로 비율은 '이미지 비율' 드롭다운에서 직접 선택 시 우선 적용.
    return '4:5';
  }
  function commonLock(product, analysis){
    const careExtra = analysis.key==='shoe_care' ? `
[신발관리용품 추가 고정]
제품 라벨/로고/마킹은 새로 만들지 말고 원본 사진 속 위치와 인상을 최대한 유지하세요.
상품명은 카피 영역에만 사용하고, 제품 라벨 자체를 임의로 홈엔모어 로고처럼 바꾸지 마세요.
원본에 없는 브러시, 천, 상자, 액세서리, 인증마크를 추가하지 마세요.` : '';
    const foodRule = analysis.extra_rule ? `\n[카테고리 주의]\n${analysis.extra_rule}` : '';
    return `[REFERENCE LOCK - 절대 준수]
첨부한 원본 ${product} 제품 사진을 최우선 기준으로 사용하세요.
사진 속 실제 제품의 색상, 모양, 재질감, 광택, 구성품, 라벨/로고/마킹 위치, 패키지 형태를 최대한 유지하세요.
제품을 새로 그리거나 일반화된 다른 제품으로 재해석하지 마세요.
원본에 보이지 않는 구성품, 액세서리, 인증마크, 수상 배지, 새로운 브랜드 로고를 추가하지 마세요.
제품이 여러 장 보이면 가장 선명한 단독/정면/전체 구성 이미지를 제품 사실성 기준으로 삼되, 섹션별로 다른 원본 이미지의 구도/장면/디테일을 적극 활용하세요.${careExtra}${foodRule}

[첨부 이미지 정밀 활용 - 전문가급 핵심] ⚠️
첨부된 원본 제품 사진을 표면적으로만 보지 말고, 다음을 깊게 관찰해서 이미지에 반영하세요:
- 제품의 실제 색감(정확한 톤), 소재의 질감(매트/광택/패브릭/메탈 등), 디테일(스티치, 마감, 버튼, 연결부)
- 이 디테일들이 곧 이 섹션의 "보여줄 무기"입니다. 막연한 제품컷이 아니라, 원본에서 관찰한 실제 특징을 클로즈업/강조로 살리세요.
- 배경/조명을 새로 구성하되 제품 자체의 정체성(색/형태/재질)은 사진과 일치시키세요.
- 사진에서 읽히는 품질감(고급/실용/아기자기 등)을 디자인 톤으로 이어가세요.

[절대 금지]
점 패턴, 추상 도형, 코너 장식, 클립아트 느낌, 더미 텍스트.
"sample", "TEXT", "샘플", "예시", "편집", "lorem" 같은 문구 금지.
한글 문장 중간에 불필요한 영문 혼용 금지. 한글 오타 금지.`;
  }

  const SECTION_GUIDES = {
    HERO: {
      goal:'첫 3초 안에 시선을 강탈하고 구매 욕구를 만든다(강한 첫인상)',
      layout:'큰 메인 헤드라인을 과감하게 + 제품 1개를 압도적으로 크게(영웅샷). 제품 흩뿌리기/카탈로그 나열 금지. 하단 카드는 최대 2개 또는 생략.',
      copy:'헤드라인은 기능 설명("~쉬운/~되는 OO")이 아니라 욕구·이득·호기심을 건드리는 한 방으로. 상품명·기능 나열 대신 고객이 달라지는 순간을 크게.'
    },
    PROBLEM: {
      goal:'고객의 구매 전 불편을 공감시킨다',
      layout:'제품보다 고객 상황/생활 불편 장면을 먼저 보여주고, 3개 고민 카드로 정리.',
      copy:'“내 얘기”처럼 느껴지는 고민을 짧게 쓰고, 제품 언급은 과하지 않게 하세요.'
    },
    HOW_TO_USE: { goal:'관리/케어 상품의 사용 흐름을 쉽게 이해시킨다', layout:'1 사용 전 → 2 제품 사용 → 3 관리 후 느낌의 3단계 시퀀스.', copy:'짧은 동사형 단계와 주의사항을 함께 넣으세요.' },
    USAGE: { goal:'실제 사용 장면을 보여줘 사용 난이도 불안을 줄인다', layout:'라이프스타일 사용 장면 + 우측/하단 3단계 사용법 카드.', copy:'꺼내기, 잡기, 사용하기처럼 행동 중심으로 작성하세요.' },
    COMPONENTS: { goal:'포함 구성품을 한눈에 이해시킨다', layout:'정돈된 플랫레이 + 구성품 라벨 콜아웃 + 하단 역할 카드.', copy:'원본에 보이는 구성품만 라벨로 작성하세요.' },
    DETAIL: { goal:'마감, 소재, 구조, 라벨 등 구매 전 확인 디테일을 설득한다', layout:'큰 클로즈업 1개 + 디테일 확대 박스 2~3개 + 짧은 설명.', copy:'원본에서 보이는 디테일만 말하고 수치/인증은 임의 생성하지 마세요.' },
    BEFORE_AFTER: { goal:'사용 전후 기대감을 만든다', layout:'좌우 Before/After 비교형. 실제 효과 보장 표현은 피하고 이미지 연출컷으로 표시.', copy:'“관리 전 혼잡함 / 관리 후 정리된 전달감”처럼 구체적인 상태 표현만 사용하세요.' },
    STORAGE: { goal:'보관과 휴대 부담을 줄인다', layout:'제품 크기감, 보관 위치, 작은 공간 배치를 보여주는 미니멀 컷.', copy:'“신발장 한쪽”, “서랍 보관”처럼 생활 장면 중심.' },
    BENEFIT: { goal:'구매 이유가 되는 핵심 장점을 압축한다', layout:'3개 장점 카드 또는 큰 숫자(01·02·03) 인포그래픽. "일반 vs 우리제품" 비교 연출은 COMPARISON 섹션에서만(여기선 금지).', copy:'추상어 대신 구체적 상황/대상을 넣으세요.' },
    ROUTINE: { goal:'운동 루틴/활용법을 제안한다', layout:'부위별/상황별 활용 3분할, 동작 아이콘과 짧은 설명.', copy:'원본 제품이 실제 가능한 활용 범위만 말하세요.' },
    SPACE_PROBLEM: { goal:'공간 분위기 문제를 공감시킨다', layout:'칙칙한 공간 vs 원하는 공간 무드 대비.', copy:'공간 고민을 감성적으로 표현하세요.' },
    ROOM_MOOD: { goal:'제품이 공간에 주는 분위기를 보여준다', layout:'방/사무실/상담공간 라이프스타일 연출컷.', copy:'공간 변화 중심 카피.' },
    SIZE_USE: { goal:'크기/배치/사용감을 확인시킨다', layout:'착용컷/제품컷 기준으로 길이감·커버 범위·사용 거리감을 보여준다. 확인 안 된 치수표는 만들지 않는다.', copy:'확인된 사이즈 옵션만 쓰고, 모르면 이미지에서 빼거나 착용컷 기준 표현으로 전환하세요.' },
    COMPARISON: { goal:'경쟁상품 대비 선택 이유를 만든다', layout:'일반 제품 vs 이 제품 비교 카드.', copy:'과장 없이 시각적 차이와 구매 포인트만 정리.' },
    PAIN_POINT: { goal:'기능/디지털 상품의 업무 고민을 공감시킨다', layout:'반복 업무/시간 소모/관리 어려움 장면.', copy:'시간/반복/복잡함 중심.' },
    WORKFLOW: { goal:'작동 흐름을 이해시킨다', layout:'입력 → AI 처리 → 결과 → 관리 흐름도.', copy:'단계 중심, 실제 가능한 기능만.' },
    FEATURE: { goal:'핵심 기능을 설명한다', layout:'기능 카드 4개, 화면/기기 목업, 아이콘.', copy:'기능명 + 사용자가 얻는 이점.' },
    RESULT: { goal:'사용 후 기대 결과를 보여준다', layout:'Before/After 작업 흐름, 결과 예시, 대시보드.', copy:'성과 보장 대신 “작업 흐름 개선” 표현.' },
    PACKAGE: { goal:'포함 구성/서비스 범위를 정리한다', layout:'구성 박스, 포함 항목 카드.', copy:'확인된 구성만.' },
    FIT: { goal:'착용 핏을 보여준다', layout:'정면/측면/활동 핏 컷.', copy:'핏과 착용 장면 중심.' },
    FABRIC: { goal:'소재감을 보여준다', layout:'소재 클로즈업, 촉감/두께/신축성 카드. 확인된 정보만.', copy:'원단감 중심.' },
    COLOR_SIZE: { goal:'색상/사이즈 선택을 돕는다', layout:'확인된 옵션만 카드로 보여주고, 전체 옵션 범위가 불명확하면 착용컷/색상/핏 중심으로 구성.', copy:'확인된 옵션만 쓰고 특정 옵션 하나를 전체 사이즈처럼 단정하지 마세요.' },
    WEAR_SCENE: { goal:'착용 상황을 상상하게 한다', layout:'일상/운동/외출 장면.', copy:'사용 상황 중심.' },
    MOOD: { goal:'감성/무드로 첫 인상을 만든다', layout:'제품 + 라이프스타일 오브젝트, 감성 카피.', copy:'뷰티/식품/라이프스타일 무드.' },
    TEXTURE: { goal:'제형/질감/재질감을 보여준다', layout:'매크로 질감 컷 + 짧은 설명.', copy:'확인되지 않은 효능 금지.' },
    POINT: { goal:'성분/향/포인트를 정리한다', layout:'3개 포인트 카드.', copy:'확인된 정보만.' },
    COLLECTION: { goal:'세트/구성을 보여준다', layout:'구성품 배열과 라벨.', copy:'구성 중심.' },
    FAQ: { goal:'구매 전 망설임을 제거한다', layout:'Q&A 카드 3~4개.', copy:'모르는 항목은 이미지에 쓰지 말고, 원본/입력에서 확인된 불안 요소만 짧게 해소하세요.' },
    CTA: { goal:'마지막 구매 결정을 유도한다', layout:'제품 마감샷 + 큰 오렌지 CTA 배너.', copy:'타겟과 행동을 명확히.' }
  };

  function guideFor(section){
    return SECTION_GUIDES[section] || {goal:'이 섹션의 핵심 메시지를 전달한다', layout:'상품군에 맞는 완성형 상세페이지 섹션 레이아웃.', copy:'한 장당 목적 하나만 담으세요.'};
  }

  function sectionTitle(section){
    const names = {
      HERO:'HERO 대표 컷', PROBLEM:'PROBLEM 고민 공감 컷', HOW_TO_USE:'HOW TO USE 사용법 컷', USAGE:'USAGE 사용 장면 컷',
      COMPONENTS:'COMPONENTS 구성품 컷', DETAIL:'DETAIL 디테일 컷', BEFORE_AFTER:'BEFORE AFTER 비교 컷',
      STORAGE:'STORAGE 보관 컷', BENEFIT:'BENEFIT 핵심 장점 컷', ROUTINE:'ROUTINE 활용 루틴 컷',
      SPACE_PROBLEM:'SPACE PROBLEM 공간 고민 컷', ROOM_MOOD:'ROOM MOOD 공간 연출 컷', SIZE_USE:'SIZE USE 크기/배치 컷',
      COMPARISON:'COMPARISON 비교 컷', PAIN_POINT:'PAIN POINT 업무 고민 컷', WORKFLOW:'WORKFLOW 작동 흐름 컷',
      FEATURE:'FEATURE 기능 설명 컷', RESULT:'RESULT 결과 예시 컷', PACKAGE:'PACKAGE 구성 패키지 컷',
      FIT:'FIT 착용핏 컷', FABRIC:'FABRIC 소재 컷', COLOR_SIZE:'COLOR SIZE 옵션 컷', WEAR_SCENE:'WEAR SCENE 착용 장면 컷',
      MOOD:'MOOD 무드 컷', TEXTURE:'TEXTURE 질감 컷', POINT:'POINT 핵심 포인트 컷', COLLECTION:'COLLECTION 구성 컷',
      FAQ:'FAQ 질문 해소 컷', CTA:'CTA 구매 유도 컷',
      SOLUTION:'SOLUTION 해결 제시 컷', OVERVIEW:'OVERVIEW 전체 소개 컷', SPEC:'SPEC 스펙/수치 컷',
      MATERIAL:'MATERIAL 소재/재질 컷', SIZE:'SIZE 크기 안내 컷', SIZE_TARGET:'SIZE TARGET 적합 대상 컷',
      CLEANING:'CLEANING 세척/관리 컷', CARE:'CARE 관리 안내 컷', INGREDIENT:'INGREDIENT 원재료 컷',
      HOW_TO_EAT:'HOW TO EAT 섭취 장면 컷', USE_SCENE:'USE SCENE 사용 장면 컷', TASTE_SCENE:'TASTE SCENE 맛/상황 컷',
      LIFESTYLE:'LIFESTYLE 라이프스타일 컷', GIFT:'GIFT 선물 무드 컷', INSTALL:'INSTALL 설치 과정 컷',
      CAR_PROBLEM:'CAR PROBLEM 차량 고민 컷', PET_PROBLEM:'PET PROBLEM 반려 고민 컷', PARENT_PROBLEM:'PARENT PROBLEM 육아 고민 컷',
      EXAMPLES:'EXAMPLES 활용 예시 컷'
    };
    return names[section] || `${section} 섹션`;
  }

  // v21.8.24.29: 이미지 생성용 컴팩트 프롬프트. 이미지 모델은 프롬프트가 길면 지시가 희석되어 품질이 떨어진다.
  // "카피를 쓰는 단계"가 아니라 "정해진 카피를 그리는 단계"이므로 핵심만 짧게 전달한다.
  const PROMPT_COMPACT_MODE_V29 = true;
  function compactLineV29(text, label){ const m = String(text || '').match(new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&') + '\\s*[:：]\\s*([^\\n]+)')); return m ? m[1].trim() : ''; }
  // v21.8.24.39: 원문 외국어 여부 판별(중국어/일본어/영어) → 한국어 번역·현지화 지시
  function looksForeignV39(t){
    t = String(t || '');
    if(/[぀-ヿ]/.test(t)) return true;
    const cjk = (t.match(/[㐀-鿿]/g) || []).length;
    const han = (t.match(/[가-힣]/g) || []).length;
    if(cjk >= 2 && cjk >= han) return true;
    const latin = (t.match(/[A-Za-z]/g) || []).length;
    if(latin >= 25 && han < 3) return true;
    return false;
  }
  function extractSectionBlockV29(copyPlan, section){
    const text = String(copyPlan || '');
    if(!text) return '';
    const sec = String(section || '').toUpperCase();
    const blocks = text.split(/\n(?=\[?\s*섹션\s*\d)/);
    return blocks.find(b => new RegExp('섹션\\s*\\d+\\s*[-–—]\\s*' + sec + '\\b', 'i').test(b))
        || blocks.find(b => new RegExp('\\b' + sec + '\\b').test((b.split('\n')[0] || '')))
        || '';
  }
  function parseSectionCopyV29(copyPlan, section){
    const b = extractSectionBlockV29(copyPlan, section);
    if(!b) return null;
    const get = (labels) => { for(const l of labels){ const m = b.match(new RegExp('·?\\s*' + l + '\\s*[:：]\\s*([^\\n]+)')); if(m && m[1].trim()) return m[1].trim(); } return ''; };
    const main = get(['메인 카피', '메인카피', '메인']);
    const sub = get(['서브 카피', '서브카피', '서브']);
    const cards = [];
    const cardRe = /헤드\s*[:：]\s*([^\/\n]+?)\s*\/\s*설명\s*[:：]\s*([^\n]+)/g; let m;
    while((m = cardRe.exec(b)) !== null && cards.length < 3){ cards.push({ head: m[1].trim(), desc: m[2].trim() }); }
    if(!main && !sub && !cards.length) return null;
    return { main, sub, cards };
  }
  // v21.8.24.46: 제품 의미 기반 감성 무드 자동 매핑(원칙3). 기계적/AI티 대신 제품에 맞는 감정 톤을 잡는다.
  const SEMANTIC_MOOD_RULES = [
    [/선풍기|쿨러|냉방|냉감|아이스|에어컨|시원|제빙|얼음/, 'fresh_clean'],
    [/슬리퍼|샌들|비치|수영|물놀이|튜브|래쉬가드|수영복/, 'fresh_clean'],
    [/난방|히터|온열|기모|겨울|보온|전기요|핫팩|패딩/, 'warm_natural'],
    [/화장품|스킨|크림|세럼|뷰티|향수|미스트|바디|클렌징/, 'soft_neutral'],
    [/명함|지갑|벨트|시계|가죽|비즈니스|오피스|만년필/, 'highend_brand'],
    [/캠핑|등산|아웃도어|스포츠|러닝|헬스|자전거/, 'sporty_active'],
    [/조명|무드등|인테리어|러그|커튼|소파|화병|디퓨저/, 'modern_lifestyle'],
    [/유아|아기|영유아|신생아|키즈|베이비|기저귀|분유|젖병|물티슈/, 'baby_clean'],
    [/반려|강아지|고양이|펫/, 'warm_natural'],
    [/전자책|강의|클래스|코칭|템플릿|노션|구독/, 'tech_dashboard']
  ];
  function semanticMoodV46(t){ t = String(t || ''); for(const [re, k] of SEMANTIC_MOOD_RULES){ if(re.test(t)) return k; } return ''; }
  // 프롬프트에 노출할 '감정 단어'(GPT가 무드를 인간 언어로 잡게)
  function emotionWordV46(t){
    t = String(t || '');
    const rules = [
      [/선풍기|쿨러|냉방|냉감|아이스|에어컨|시원|제빙/, '시원하고 청량한'],
      [/슬리퍼|샌들|비치|수영|물놀이|튜브|래쉬가드|수영복|여름/, '시원한 여름'],
      [/난방|히터|온열|기모|겨울|보온|전기요|핫팩/, '따뜻하고 포근한'],
      [/화장품|스킨|크림|세럼|뷰티|향수|미스트|바디/, '감성적이고 깨끗한'],
      [/명함|지갑|벨트|시계|가죽|비즈니스|오피스/, '단정하고 고급스러운'],
      [/주방|식기|조리|컵|텀블러|도마|냄비/, '깔끔하고 위생적인'],
      [/유아|아기|키즈|베이비/, '부드럽고 안심되는'],
      [/반려|강아지|고양이|펫/, '따뜻하고 사랑스러운'],
      [/캠핑|등산|아웃도어|스포츠|운동|러닝|헬스/, '활동적이고 시원한'],
      [/조명|무드등|인테리어|가구|러그|커튼/, '아늑하고 감각적인']
    ];
    for(const [re, w] of rules){ if(re.test(t)) return w; }
    return '제품에 어울리는';
  }

  // v21.8.24.54: 섹션 역할별로 첨부 이미지를 다르게 쓰도록 안내(컴팩트 한 줄). 여러 색/각도 원본을 골고루 활용해 1~2번 쏠림 방지.
  function multiImageHintForSection(section){
    const s = String(section || '');
    if(/COLOR_SIZE|^SIZE$|SIZE_USE|OPTION|COLLECTION/.test(s)) return '첨부에 보이는 색상·옵션 변형을 모두 한 컷에 나란히';
    if(/DETAIL|TEXTURE|MATERIAL|FABRIC/.test(s)) return '다른 각도·클로즈업이 잘 보이는 원본';
    if(/USE_SCENE|USAGE|LIFESTYLE|WEAR_SCENE|SCENE|ROUTINE/.test(s)) return '실제 사용/연출이 담긴 원본';
    if(/HERO|CTA/.test(s)) return '대표성이 가장 강한 원본';
    if(/PROBLEM|PAIN/.test(s)) return '상황·맥락이 드러나는 원본(제품은 작게)';
    return '앞 섹션과 다른 원본 컷';
  }

  // v21.8.24.66: '매번 같은 구조'를 피하는 구도 다양화 — 섹션별 구도 풀에서 '실행 시드'로 하나를 뽑는다.
  // 제품 사실성·섹션 목적·확정 카피는 그대로 두고, 배치·앵글·프레이밍만 매 실행/섹션마다 달라진다.
  let _runVariantSeed = 0;
  const HERO_COMPOSITIONS = [
    '압도적 스케일 + 극적 조명, 다이내믹 사선 앵글, 포컬 1곳',
    '넓은 여백 미니멀, 제품 오프센터 정렬, 부드러운 그림자',
    '강한 대비 배경 위 클로즈업, 색·질감 부각',
    '라이프스타일 사용 맥락 속 키비주얼(손/착용/현장)',
    '정면 정중앙 히어로컷 + 위아래 넉넉한 카피 여백'
  ];
  const SECTION_COMPOSITIONS = [
    '제품 크게 좌측, 우측에 텍스트 블록',
    '제품 중앙, 상단 헤드라인·하단 서브',
    '풀블리드 라이프스타일 배경 위 텍스트 영역',
    '상단 제품 + 하단 3분할 카드',
    '클로즈업 디테일 + 콜아웃 라인',
    '넓은 여백 미니멀, 제품 오프센터 배치',
    '사선 다이내믹 구도, 그림자로 입체감'
  ];
  function pickComposition(section){
    const pool = section === 'HERO' ? HERO_COMPOSITIONS : SECTION_COMPOSITIONS;
    const idx = (hashString(String(section)) + (_runVariantSeed >>> 0)) % pool.length;
    return pool[idx];
  }
  // v21.8.24.94: 섹션 유형별 '시각 구조(Visual DNA)'를 강제 — 모든 섹션이 같은 레이아웃으로 나오던 문제 해결.
  //  레이아웃·제품 크롭·배경·카드유무·앵글을 유형마다 다르게. 이미지 모델이 섹션별로 확연히 다른 그림을 그리게 한다.
  function visualDnaV94(section){
    const s = String(section || '').toUpperCase();
    if(/HERO/.test(s)) return { layout:'대표 히어로컷(제품 전체, 정면/약간 위 앵글)', crop:'제품 전체', bg:'단색~은은한 그라데이션 배경', cards:'카드 없이 메인 카피 중심(포인트 작게)', angle:'정면 히어로' };
    if(/PROBLEM|PAIN/.test(s)) return { layout:'사용 전 불편 상황 연출(제품은 작게/맥락 속)', crop:'제품 작게 또는 손에 든 장면', bg:'생활 공간 맥락(과하지 않게)', cards:'★카드 금지 — 큰 공감 문장 중심', angle:'상황 연출, 와이드' };
    if(/SOLUTION/.test(s)) return { layout:'제품이 문제를 해결하는 사용 장면(동작 중심)', crop:'사용 중인 제품 + 손/동작', bg:'실제 사용 현장', cards:'스텝/장면 위주(딱딱한 카드 지양)', angle:'사용 동작이 보이는 앵글' };
    if(/USP|FEATURE|BENEFIT|POINT|RESULT|FUNCTION/.test(s)) return { layout:'차별점/효익 카드 구성', crop:'제품 + 강조 콜아웃', bg:'깔끔한 정보형 배경', cards:'카드 2~3개 OK(여기서만 카드 강조)', angle:'정보 전달형 정렬' };
    if(/DETAIL|SPEC|TEXTURE|MATERIAL|FABRIC|COMPONENT/.test(s)) return { layout:'부분 클로즈업 + 라벨 콜아웃', crop:'★부분 확대(소재/마감/연결부) — 전체샷 반복 금지', bg:'질감이 살아나는 클로즈업 배경', cards:'카드 대신 선 라벨/콜아웃', angle:'매크로 클로즈업' };
    if(/SCENE|USAGE|LIFESTYLE|WEAR|ROUTINE/.test(s)) return { layout:'실제 사용 라이프스타일 장면', crop:'생활 맥락 속 제품', bg:'일상 공간(집/외출/현장)', cards:'상황 라벨 위주', angle:'라이프스타일 와이드' };
    if(/FAQ|TRUST/.test(s)) return { layout:'구매 전 확인/안심 정보형', crop:'제품 정면 + 부분 표시', bg:'차분한 정보형 배경', cards:'Q&A/체크 항목(가짜 후기·별점 금지)', angle:'정면 정보' };
    if(/CTA/.test(s)) return { layout:'마지막 구매 결정 컷(여운/감정)', crop:'제품 대표컷(앞 섹션과 다른 각도)', bg:'깔끔한 마무리 배경', cards:'카드 최소(0~2개)', angle:'마무리 히어로(앞과 다르게)' };
    if(/OVERVIEW|SOLUTION_INTRO|COLOR_SIZE|COLLECTION|OPTION|PACKAGE/.test(s)) return { layout:'옵션/구성 한눈에 정렬', crop:'옵션·구성 나란히', bg:'정돈된 배경', cards:'정렬형 라벨', angle:'플랫레이~정면' };
    return { layout:'제품 중심 정보형', crop:'제품 위주', bg:'깔끔한 배경', cards:'유형에 맞게', angle:'앞 섹션과 다른 앵글' };
  }
  // v21.8.24.75: 1단계 브리프에서 공식 제품명만 깔끔히 추출(없으면 빈 문자열)
  // v21.8.24.91/95: 상품명에서 플랫폼/SEO 군더더기 제거(이미지에 들어갈 깔끔한 이름).
  function cleanProductNameV91(name){
    let s = String(name || '').trim();
    s = s.split('|')[0];                                  // "… | 쿠팡" 뒤꼬리 제거
    // v95: 앞쪽 대괄호/소괄호 태그 반복 제거 — [도매꾹][무료배송][특가] 등
    for(let i=0;i<5;i++){ const n=s.replace(/^\s*[\[(（【][^\])）】]{0,18}[\])）】]\s*/,''); if(n===s) break; s=n; }
    // v95: 플랫폼명 단독 토큰 제거(앞/중간/끝 어디든)
    s = s.replace(/(^|\s)(도매꾹|도매매|쿠팡|스마트스토어|네이버|11번가|G마켓|지마켓|옥션|위메프|티몬|알리|알리익스프레스|타오바오|1688)(\s|$)/gi,' ');
    // v95: SEO 미끼 수식어 군더더기 제거(상품명이 아니라 검색 키워드)
    s = s.replace(/(디자인\s*특허등록\s*제품|특허\s*등록\s*제품|정품\s*인증|당일\s*발송|무료\s*배송|국내\s*배송|초특가|최저가|역대급|인기\s*상품|베스트|신상|사은품\s*증정|1\s*\+\s*1)/gi,' ');
    // v95: 마케팅 수식어 토큰 제거(핵심 제품명이 앞으로 오게) — 제품 형태어(자동/접이식/슬림/캡형 등)는 남김
    s = s.replace(/(^|\s)(강풍|비바람|방수|발수|초경량|경량|대형|특대|튼튼한|튼튼|강한|고급|최고급|프리미엄|명품|인기|이중창살|\d+k|\d+급)(?=\s|$)/gi,' ');
    s = s.split(/\s*[-–—]\s*/)[0];                        // 첫 하이픈 앞만(부가 설명 컷)
    s = s.replace(/\s{2,}/g,' ').replace(/^[\s,·]+|[\s,·]+$/g,'').trim();
    // v95: 그래도 길면(키워드 나열) → 의미 단위 앞쪽 위주로 6단어까지만
    const words = s.split(/\s+/).filter(Boolean);
    if(words.length > 6) s = words.slice(0, 6).join(' ');
    return s || String(name||'').replace(/^\s*[\[(（【][^\])）】]*[\])）】]\s*/,'').split('|')[0].trim() || '제품';
  }
  function extractProductNameV75(brief){
    const b = String(brief || '').replace(/\s+/g, ' ');
    let m = b.match(/공식\s*제품명[\s:：]*["“']?([^\n.,/"”'\[\]]{2,40})/)
         || b.match(/제품명[\s:：]+["“']?([^\n.,/"”'\[\]]{2,40})/);
    if(m && m[1]) return m[1].trim().replace(/\s*(상세페이지|안에서는|기준).*$/, '').trim();
    return '';
  }
  // v21.8.24.75: 디자인 무드를 '프리미엄 미니멀' vs 'MZ 트렌디'로 분류해 아트디렉션을 적응시킨다.
  function artDirectionV75(moodLabel, analysis){
    const s = `${moodLabel||''} ${analysis.category_group||''} ${analysis.template_type||''}`;
    const isMZ = /MZ|팝|비비드|트렌디|스포티|액티브|발랄|캐주얼|pop|vivid/i.test(s);
    const isPremium = /프리미엄|하이엔드|럭셔리|미니멀|모던|에디토리얼|뷰티|감성|뉴트럴|소프트|brand/i.test(s);
    if(isMZ && !isPremium) return '스티커형 포인트·밑줄 강조·둥근 칩 버튼·강한 타이포(트렌디하지만 저렴해 보이지 않게)';
    if(isPremium) return '넉넉한 여백·큼직한 타이포·장식 최소의 프리미엄 미니멀(고급스럽게)';
    return '깔끔한 카드형 레이아웃·또렷한 타이포·포인트는 절제 있게';
  }
  // v21.8.24.76: 섹션·카테고리에 맞춰 '한국인 모델'을 적절히 배치(착용/사용/라이프스타일/공감엔 모델, 스펙·디테일·CTA는 제품 단독)
  function modelDirectiveV76(section, analysis){
    const cat = analysis.key || '';
    const wearCat = /footwear|fashion_clothing/.test(cat);
    const verb = wearCat ? '착용' : '사용';
    if(/WEAR_SCENE|FIT|USAGE|HOW_TO_USE|ROUTINE|LIFESTYLE|USE_SCENE|MOOD|ROOM_MOOD/i.test(section))
      return `\n[모델] 제품을 실제로 ${verb}하는 자연스러운 한국인 모델을 함께(제품이 주인공, 모델은 맥락·손/동작 위주, 표정·손·비율 왜곡 없이 실제 촬영처럼).`;
    if(/PROBLEM|PAIN/i.test(section))
      return `\n[모델] 그 불편을 겪는 상황의 한국인 모델을 자연스럽게(표정·동작으로 공감, 제품은 작게/맥락).`;
    if(section==='HERO' && /fashion_clothing|footwear|beauty|kids|fitness|sports/.test(cat))
      return `\n[모델] 제품을 ${verb}한 한국인 모델의 라이프스타일 히어로컷(제품이 또렷이 보이게, 얼굴·손 왜곡 없이).`;
    return ''; // SPEC/DETAIL/FABRIC/COMPONENTS/PACKAGE/CTA/FAQ 등은 제품 단독
  }
  function buildCompactImagePrompt({section, product, data, analysis, copyPlan, designBlock, layoutBlock, heroLock, ratio, refStyle, masterBrief, idx, total}){
    const g = guideFor(section);
    const parsed = parseSectionCopyV29(copyPlan, section);
    // v21.8.24.53: 레퍼런스 덤프가 프롬프트를 과하게 늘리고 문장 중간에 잘리던 문제 → 핵심만 간결히(240자).
    const refNote = refStyle ? `\n[레퍼런스 ⚠️우선] 아래 톤·색·여백·카드 스타일을 따라가세요: ${String(refStyle).replace(/#[0-9a-fA-F]{3,6}/g,'').replace(/\s+/g,' ').trim().slice(0,240)}` : '';
    const moodLabel = compactLineV29(designBlock, '적용 무드');
    const moodColor = compactLineV29(designBlock, '컬러');
    const moodWord = emotionWordV46(`${product} ${analysis.category_group || ''} ${analysis.product_type || ''}`);
    // v21.8.24.46: 컷 유형(SHOT TYPE)을 문장 경계로 깔끔히 잘라 사용(이전엔 150자 단어중간 잘림 버그).
    const shotRaw = String(shotFor(section) || '').replace(/\[SHOT TYPE[^\]]*\]/g, '').replace(/⚠️/g, '').replace(/\s+/g, ' ').trim();
    const shotShort = shotRaw.split('.').slice(0, 2).join('.').trim().slice(0, 90).replace(/[.\s]+$/, '');
    // v21.8.24.53: HERO(첫 컷)=썸네일. 잘린 일반 SHOT 대신 강한 비주얼 임팩트 지시를 직접 사용.
    const heroCut = '표지/썸네일급 키비주얼. 제품을 압도적 스케일로, 극적인 조명·여백·다이내믹 앵글, 포컬 1곳. 밋밋한 평면 배치 금지';
    const cutContent = section === 'HERO' ? heroCut : (shotShort || g.layout);
    const imgNames = Array.isArray(data.imageNames) ? data.imageNames.filter(Boolean) : [];
    // v21.8.24.54: 첨부가 여러 장이면 섹션 역할에 맞는 다른 원본을 쓰도록 배분(1~2번째에만 쏠리는 문제 해소).
    const multiImgNote = imgNames.length >= 2 ? ` 첨부 ${imgNames.length}장 중 이 컷엔 ${multiImageHintForSection(section)}(1~2번째에만 쏠리지 말 것).` : '';
    // 확인된 스펙만(도망문구 제외). hint(확인 필요)는 넣지 않는다. v21.8.24.54: 상품명은 [제품]에 이미 있어 줄 통째 제거(중복).
    const specShort = cleanPromptSpecTextV13(data.specs || '', 240)
      .split('\n')
      .filter(l => l && !/^\[/.test(l) && !/확인\s*필요|미확인|별도표기/.test(l) && !/^\s*상품명\s*[:：]/.test(l.trim()))
      .slice(0, 2).join(' / ').slice(0, 110);
    let copyBlock;
    if(data.textOverlay){
      // v21.8.24.41: 글자 오버레이 모드 — AI는 비주얼만, 헤드라인은 제작자가 직접 입힌다(한글 깨짐 0).
      copyBlock = `[글자 처리 - 중요] 이 이미지에는 큰 제목/헤드라인/설명 문장 같은 한글 텍스트를 넣지 마세요(헤드라인·문구는 제작자가 직접 입힙니다).
제품·배경·연출 비주얼에만 집중하고, 상단 약 28% 영역은 헤드라인이 들어갈 자리로 단순하게(여백/배경) 비워두세요. 작은 포인트 아이콘 외 문장형 글자 금지.`;
    } else if(parsed){
      const lines = [];
      if(parsed.main) lines.push(`메인: ${parsed.main}`);
      if(parsed.sub) lines.push(`서브: ${parsed.sub}`);
      parsed.cards.slice(0, 3).forEach(c => lines.push(`카드: ${c.head} — ${c.desc}`));
      copyBlock = `[카피] 아래 문구 그대로(철자 정확). 메인=크고 굵게(최강조), 서브=작게·폰트 구별, 무드에 맞는 한글 폰트:\n${lines.join(' / ')}`;
    } else if(section === 'HERO'){
      // v21.8.24.53: HERO=페이지 최상단 '썸네일'. 가장 크고 강렬한 후크 헤드라인으로 3초 안에 시선 강탈.
      copyBlock = `[카피] 페이지 최상단 썸네일. 메인 1줄(6~14자, 가장 크고 굵게) + 서브 1줄(14~26자, 작게). 핵심 효용을 쉽고 자연스러운 일상 한국어로(부정·문제형 금지).`;
    } else if(/PROBLEM|PAIN/i.test(section)){
      // v21.8.24.50: '문제 제기' 섹션은 기능 소개가 아니라 고객 불편을 콕 찌르는 공감으로 시작.
      copyBlock = `[카피] 고객이 실제 겪는 불편에 공감하는 메인 1줄(6~16자, 굵게) + 서브 1줄(14~26자, 작게). 쉽고 자연스러운 말로(기능·장점·스펙 소개 금지).`;
    } else {
      copyBlock = `[카피] 메인 1줄(6~16자, 굵게) + 서브 1줄(14~26자, 작게). 쉽고 자연스러운 일상 한국어로(전문용어·추상어·과장 금지).`;
    }
    const lowNote = (analysis.involvement === 'low')
      ? `\n[전략] 저관여 상품: 불편 공감은 짧게, 선택 이유·활용 중심으로 간결히.`
      : '';
    // v21.8.24.33: 카테고리 특수 규칙(무형=목업/그래프 중심·보장표현 금지, 식품=건강과장 금지 등)을 컴팩트에도 전달
    const catNote = analysis.extra_rule ? `\n[카테고리 주의] ${String(analysis.extra_rule).slice(0, 150)}` : '';
    // v21.8.24.39: 원문이 외국어(중국어/영어/일본어)면 이미지 안 글자는 자연스러운 한국어로 번역·현지화
    const localizeNote = looksForeignV39(`${product} ${data.specs || ''} ${analysis.category_group || ''}`)
      ? `\n[현지화] 원문이 외국어입니다. 이미지 안 문구는 자연스러운 한국어로 번역·현지화(외국어 단어·번역투·중국어 흔적 금지).`
      : '';
    // v21.8.24.32: 사회적 증거(실제 입력값) 강하게 배치 — 헤드/증명성 섹션 한정. 무결성: 입력된 값만, 숫자/순위 지어내기 금지.
    const reviews = String(data.reviews || '').replace(/\s+/g, ' ').trim();
    const hasProof = reviews.length > 1 && !/^확인\s*필요$|미확인/.test(reviews);
    const proofSection = /HERO|BENEFIT|COMPARISON|SPEC|FAQ|TRUST|CTA|OVERVIEW/i.test(section);
    const proofNote = (hasProof && proofSection)
      ? `\n[사회적 증거 - 확인됨, 이 내용만] ${reviews.slice(0, 120)}\n→ ${section === 'HERO' ? '헤드 상단에 후기·평점·판매량·순위를 눈에 띄게 먼저' : '강점을 입증하는 증명 요소로'} 배치. 입력된 값만 사용, 숫자·순위·리뷰수 지어내기 금지.`
      : '';
    // v21.8.24.54: '화면(모니터·앱)' 절은 화면이 있을 법한 전자/디지털 제품에만(명함지갑 등 일반 제품엔 노이즈).
    const hasScreenRisk = /전자|디지털|가전|노트북|모니터|스마트|기기|소프트웨어|프로그램|앱|어플|강의|템플릿|pc|컴퓨터|태블릿|폰/i.test(`${product} ${analysis.category_group || ''} ${analysis.product_type || ''} ${analysis.template_type || ''}`);
    const screenClause = hasScreenRisk ? '원본 사진 속 화면(모니터·앱 화면)이나 ' : '원본 사진 속 ';
    // v21.8.24.56: 진단 결과 — 마스터 브리프/타겟/고민/장점/경쟁/톤이 컴팩트 프롬프트에 직접 미반영이던 문제 수정.
    // 무결성 원칙: 모두 '사용자 확인 입력'으로만 취급, 과장·허위·지어내기 금지. 빈 값이면 주입 안 함.
    const _clean = (v, n) => String(v || '').replace(/\s+/g, ' ').trim().slice(0, n);
    // P1: 1단계 마스터 브리프(공식 제품명·확정 스펙 등)를 핵심만 간결히 [제품 기준]으로 주입(우선).
    const briefNote = masterBrief ? `\n[제품 기준 - 1단계 확정, 우선] ${_clean(masterBrief, 220)}` : '';
    // P2: 세부 칸을 섹션 역할에 맞게 주입
    const _isProblem = /PROBLEM|PAIN/i.test(section);
    const _isCompare = /COMPARISON|BEFORE_AFTER|\bVS\b/i.test(section);
    const _isBenefit = !_isProblem && /BENEFIT|FEATURE|\bPOINT\b|DETAIL|RESULT|USP|FUNCTION/i.test(section);
    const _target = _clean(data.target, 80);
    const _pain = _clean(data.pain, 120);
    const _benefit = _clean(data.benefits, 140);
    const _comp = _clean(data.competitor, 120);
    const audienceNote = _target ? `\n[타겟 고객 - 확인된 입력] ${_target} — 이 사람이 쓰는 말·관심사에 맞춰 카피와 연출.` : '';
    // 카피 지시 계열은 글자 오버레이 모드(제작자가 직접 문구 입력)에선 충돌하므로 주입 안 함.
    const _copyMode = !data.textOverlay;
    const painNote = (_pain && _isProblem && _copyMode) ? `\n[고객 고민 - 확인된 입력, 이걸 콕 찔러라] ${_pain}` : '';
    const benefitNote = (_benefit && _isBenefit && _copyMode) ? `\n[핵심 장점 - 확인된 입력, 과장 없이 이 범위 안에서] ${_benefit}` : '';
    const compNote = (_comp && _isCompare && _copyMode) ? `\n[비교 기준 - 확인된 입력] ${_comp} 대비 우리 강점 중심으로(경쟁사 비방·허위 비교 금지).` : '';
    // P3: 톤(전환 중심/감성/프리미엄/가성비/전문가형)을 카피 어조에 반영
    const _tone = _clean(data.tone, 30);
    // v21.8.24.60: 카피 지시 3중 블록([카피 자연스러움]+[카피 톤])을 한 줄로 통합 → 프롬프트 단축·어색한 한국어 방지. 톤도 흡수.
    const copyQualityNote = _copyMode ? `\n[문구 원칙] ${COPY_QUALITY_RULES_SHORT}${_tone ? ` 톤: ${_tone}.` : ''}` : '';
    const toneNote = '';
    // v21.8.24.53: 레퍼런스가 있으면 자동 무드(다른 팔레트)와 충돌하므로, 무드 라인은 레퍼런스로 위임(중복·모순·길이 제거).
    const moodLine = refStyle
      ? `[무드] 위 레퍼런스의 톤·색·타이포 그대로(전 섹션 통일).`
      : `[무드] ${moodLabel || analysis.category_group || ''}${moodColor ? ` (${moodColor})` : ''} — ${moodWord} 감성, 전 섹션 톤·폰트·색 통일.`;
    // v21.8.24.63: '사람이 직접 치는 짧은 프롬프트가 더 잘 나온다'는 피드백 반영 —
    // 장황한 지시([전략]/[타겟]/[문구원칙]/긴 [무드]·[컷]·[규칙])를 걷어내고, 제품 사실·확정 카피·비율만 남긴 짧은 프롬프트로.
    const moodShort = refStyle ? '첨부 레퍼런스의 톤·색 그대로' : `${moodLabel || analysis.category_group || moodWord || '깔끔하고 고급스럽게'}${moodColor ? ` (${moodColor})` : ''}`;
    const purposeShort = sectionTitle(section);
    // v21.8.24.66: 고정 컷(cutContent) 대신 실행 시드로 뽑은 구도를 '연출'로 사용 → 매 실행 구조가 달라짐.
    const shotHint = pickComposition(section) || (cutContent ? String(cutContent).split(/[.]/)[0].trim().slice(0, 46) : '');
    let copyLines;
    if(data.textOverlay){
      copyLines = '글자(헤드라인·문장)는 넣지 말고, 상단 약 28%는 카피 자리로 비워둬. 배경·제품만.';
    } else if(parsed){
      const arr = [];
      if(parsed.main) arr.push(`· 메인: ${parsed.main}`);
      if(parsed.sub) arr.push(`· 서브: ${parsed.sub}`);
      parsed.cards.slice(0, 3).forEach(c => arr.push(`· 카드: ${c.head} — ${c.desc}`));
      copyLines = `이 문구를 그대로, 또렷한 한글로 넣어줘:\n${arr.join('\n')}`;
    } else {
      copyLines = String(copyBlock).replace(/^\[카피\]\s*/, '');
    }
    // v21.8.24.75: 브리프 통째 덤프(문장 중간 잘림) 제거 → 확인 스펙만 깔끔히. 제품명은 헤더에 정확히 들어간다.
    const factsLine = specShort ? `확인 스펙: ${specShort}` : '';
    const isHeroish = section === 'HERO';
    const artDir = refStyle ? '첨부 레퍼런스의 톤·색·여백·타이포를 그대로' : artDirectionV75(moodLabel, analysis);
    const purposeLine = isHeroish
      ? '[목적] 첫 화면에서 구매자가 멈춰 보게 만드는 후킹 — 제품 설명이 아니라 "이걸 쓰면 이런 인상/이득"이 한눈에 보이게.'
      : `[목적] ${purposeShort} — 한 컷 한 메시지.`;
    // 카피 블록(요소 위치/스타일 지시 포함). 오버레이 모드면 글자 비우기.
    let copyDirective;
    if(data.textOverlay){
      copyDirective = '[글자] 헤드라인·문장은 넣지 말고 상단 약 28%는 카피 자리로 비워둬. 배경·제품만.';
    } else if(parsed){
      const arr=[];
      if(parsed.main) arr.push(`· 메인(가장 크게·굵게, 최강조): ${parsed.main}`);
      if(parsed.sub) arr.push(`· 서브(작게·선명): ${parsed.sub}`);
      if(isHeroish && product && product!=='첨부한 제품') arr.push(`· 제품명(작게): ${product}`);
      parsed.cards.slice(0,3).forEach(c=>arr.push(`· 칩/카드(둥근 버튼처럼): ${c.head}${c.desc?' — '+c.desc:''}`));
      copyDirective = `[넣을 문구 — 이 글자 그대로, 또렷한 한글(오타·자모깨짐·외국어·장식문자 금지)]\n${arr.join('\n')}`;
    } else {
      copyDirective = `[넣을 문구] ${String(copyLines).replace(/\n/g,' ')}`;
    }
    const textStyle = data.textOverlay ? '' : '\n[텍스트 스타일] 메인은 화면에서 가장 크고 굵게(모바일에서도 잘 보이게), 서브·제품명은 작지만 선명, 칩은 둥근 버튼처럼. 글자 적게·여백 넉넉.';
    // v21.8.24.76: 실사 사진 느낌 강화 + 콘텐츠에 맞는 모델 배치
    const photoReal = refStyle ? '' : '\n[촬영] 실제 DSLR로 찍은 듯한 사실적인 실사 제품 사진 — 자연스러운 조명·그림자·재질 질감·얕은 피사계심도. 일러스트/3D렌더/CG/그림체/플랫 벡터 느낌 금지.';
    const modelLine = data.noModel ? '' : modelDirectiveV76(section, analysis);
    // v21.8.24.88: 기본은 이미지에 가격/금액 표기 안 함(체크 시에만 허용)
    const noPriceClause = data.showPrice ? '' : ' · 가격/금액/할인율/판매가/쿠폰가(가격 표기 금지)';
    // v21.8.24.89: '카피 확정 → 이미지 생성 분리' 7섹션 구조(사용자 검증 고퀄 포맷)로 조립.
    const num = (typeof idx === 'number' ? idx + 1 : '?');
    const tot = total || '?';
    const secType = sectionTitle(section);
    const secPurpose = g.goal || '핵심 메시지를 한 컷으로 전달';
    const tTarget = _target || _clean(analysis.target_customer, 80) || '이 상품을 사려는 일반 소비자';
    const tPain = _pain || _clean(analysis.main_pain_point, 120);
    const tBenefit = _benefit || _clean(analysis.core_value, 140);
    const secMsg = (parsed && parsed.main) ? parsed.main : secPurpose;
    const priceLine = (data.showPrice && _clean(data.price, 30)) ? `\n가격: ${_clean(data.price, 30)}` : '';
    const catRule = analysis.extra_rule ? `\n${_clean(analysis.extra_rule, 150)}` : '';
    // v21.8.24.94: 섹션 유형별 시각 구조(Visual DNA) — [4]에 명시해 섹션마다 확연히 다른 레이아웃/앵글/배경이 나오게.
    const dna = visualDnaV94(section);
    const composeLine = `레이아웃: ${dna.layout} / 제품 크롭: ${dna.crop} / 배경: ${dna.bg} / 카드: ${dna.cards} / 앵글: ${dna.angle}.`;
    return `첨부한 "${product}" 원본 사진을 기준으로, 한국 쇼핑몰 상세페이지에 바로 넣을 수 있는 세로형 섹션 이미지 1장만 생성하세요.
텍스트 설명 없이 이미지만 생성하세요.

━━━━━━━━━━━━━━━━━━━━
[1. 공통 제작 원칙]
━━━━━━━━━━━━━━━━━━━━
당신은 한국 이커머스 상세페이지 전문 디자이너이자 구매설득 카피라이터입니다.
구매자가 "이 제품을 왜 사야 하는지"를 한 컷 안에서 바로 이해하게 만드세요.
- 한 컷 한 메시지 · 모바일에서 1초 안에 이해 · 제품이 주인공
- 첨부 원본의 형태·색상·질감·포인트를 우선 반영
- 원본에 없는 로고/구성품/인증/수치/리뷰/별점 추가 금지, 확인 안 된 효능·과장 금지
- 글자는 적게·크게·선명하게, 여백은 넉넉하게

━━━━━━━━━━━━━━━━━━━━
[2. 제품 정보]
━━━━━━━━━━━━━━━━━━━━
상품명: ${product}
카테고리: ${analysis.category_group || '일반'}
판매 플랫폼: ${data.platform || '쿠팡'}${priceLine}${factsLine ? `\n확인 스펙: ${specShort}` : ''}
제품 재현 기준: 첨부 원본 속 제품의 형태·색상·질감·라벨 느낌·크기감·포인트를 최대한 유지하세요.
금지: 상위노출·판매1위·인증·천연가죽·방수·임의 수치·수납매수·리뷰·별점·확인 안 된 성분/효능${data.showPrice ? '' : '·가격/금액/할인율/판매가'} 표현 금지.${catRule}

━━━━━━━━━━━━━━━━━━━━
[3. 구매 설득 기준]
━━━━━━━━━━━━━━━━━━━━
타겟: ${tTarget}${tPain ? `\n고객 고민: ${tPain}` : ''}${tBenefit ? `\n핵심 장점: ${tBenefit}` : ''}
이 섹션에서 전달할 한 가지 메시지: "${secMsg}"
카피 톤: 쉽고 자연스러운 일상 한국어(전문용어·추상어·과장어·광고성 문구 금지)${_tone ? `, ${_tone} 톤` : ''}.

━━━━━━━━━━━━━━━━━━━━
[4. 현재 섹션 역할]
━━━━━━━━━━━━━━━━━━━━
현재 섹션: ${num}/${tot}번째 · 유형: ${secType}
목적: ${secPurpose}
구도: ${shotHint}.
시각 구조: ${composeLine}${(typeof idx === 'number' && idx > 0) ? `
★이전 섹션과 다르게: 앞 섹션들과 같은 제품 위치·같은 배경·같은 하단 3카드 구조를 반복하지 마세요. 제품 크롭/각도/배치를 바꿔 확연히 다른 컷으로.` : ''}
제품 비중: 화면의 45~55%로 크게.${multiImgNote ? `\n원본 사용:${multiImgNote}` : ''}

━━━━━━━━━━━━━━━━━━━━
[5. 이미지 안에 넣을 문구]
━━━━━━━━━━━━━━━━━━━━
${copyDirective}${textStyle}

━━━━━━━━━━━━━━━━━━━━
[6. 비주얼 스타일]
━━━━━━━━━━━━━━━━━━━━
비율: 세로 ${ratio}
무드: ${moodLabel || moodWord || '신뢰 정보형'}${moodColor ? ` (${moodColor})` : ''}
레이아웃: ${artDir}. 정돈되고 신뢰감 있는 쇼핑몰 상세페이지 느낌.${photoReal}${modelLine}${(typeof idx === 'number' && idx > 0) ? `
통일은 색만(중요): 이 대화에서 앞서 생성한 섹션들과 '배경 색감·포인트 컬러·폰트 느낌'만 통일하세요. 단, 레이아웃·구도·제품 각도·배경 연출·카드 유무는 섹션마다 '다르게' 가세요(여백 스타일까지 똑같이 맞추지 말 것 — 그러면 이미지가 다 똑같아집니다). 인물(모델)이 이미 등장했다면 같은 인물처럼 유지하세요.` : ''}
금지 스타일: 일러스트·3D렌더·CG·그림체·플랫 벡터 금지. 과한 소품·맥락 없는 군중·제품과 무관한 배경 금지.${localizeNote}${refNote}

━━━━━━━━━━━━━━━━━━━━
[7. 최종 검수]
━━━━━━━━━━━━━━━━━━━━
1) 제품이 원본과 다른 형태·색·구성으로 바뀌지 않았는가?  2) 원본에 없는 로고·인증·리뷰·별점·수치가 추가되지 않았는가?
3) 한글 깨짐·자모분리·번역투가 없는가?  4) 글자가 너무 작거나 많아 모바일에서 읽기 어렵지 않은가?
5) 이 섹션 메시지가 한눈에 보이는가?  6) 제품이 화면의 주인공인가?  7) 무드·색감이 전 섹션과 통일되는가?
위 기준을 만족하는 섹션 이미지 1장만 생성하세요. 설명·기획서·체크리스트 없이 이미지만 출력하세요.`;
  }

  function buildPrompt({section, product, data, analysis, variation, masterBrief, copyPlan, heroLock, designBlock, layoutBlock, contentPlan, refStyle, idx, total}){
    const g = guideFor(section);
    const ratio = defaultRatio(section);
    const isHero = section === 'HERO';
    if(PROMPT_COMPACT_MODE_V29){
      return buildCompactImagePrompt({section, product, data, analysis, copyPlan, designBlock, layoutBlock, heroLock, ratio, refStyle, masterBrief, idx, total});
    }
    const lock = commonLock(product, analysis);
    const shot = shotFor(section);
    const formula = formulaFor(section);
    const salesCopyBlock = buildSalesCopyQualityBlock(section, analysis, data);
    const platform = safe(data.platform, '스마트스토어');
    const tone = safe(data.tone, '전환 중심');

    // 마스터 브리프 (있으면 최상단)
    const briefBlock = masterBrief ? `[마스터 브리프 - 이 상세페이지의 헌법, 모든 섹션이 반드시 따를 것] ⚠️ 최우선
아래는 1단계에서 확정한 이 제품의 공식 기준입니다. 공식 제품명은 모든 섹션에서 동일하게, 확인된 스펙 외 수치는 만들지 마세요.
${masterBrief}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

` : '';

    // 카피 기획서 (2단계에서 확정한 섹션별 카피)
    const copyPlanBlock = copyPlan ? `[카피 기획서 - 2단계에서 확정한 섹션별 카피] ⚠️ 이 카피를 사용
아래는 이 상세페이지 전체의 섹션별 카피 기획서입니다.
이번 섹션(${section})에 해당하는 부분을 찾아, 그 "메인 카피 / 서브 카피 / 근거 포인트"를 이미지 안 문구로 사용하세요.
기획서에 없는 내용을 새로 지어내지 말고, 기획서의 전략과 카피를 충실히 시각화하세요.
단, 기획서 문장이 한국어로 어색하거나 이미지 안에서 너무 길면 의미를 유지한 채 자연스럽고 짧게 교정하세요.

${copyPlan}

중요: 위 카피 기획서에 '배지 문구' 또는 섹션 역할용 짧은 문구가 있더라도, 실제 이미지 상단에는 소제목/배지 형태로 넣지 마세요. 최종 이미지에는 메인 카피, 서브 카피, 카드 문구만 사용하세요.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

` : '';

    // HERO 잠금 (2번째 섹션부터)
    const heroLockBlock = heroLock ? `[첫 컷(HERO) 일관성 잠금] ⚠️
방금 이 대화에서 생성한 첫 번째 이미지(HERO)를 시각 기준으로 삼으세요.
제품 모양/색상/구성품을 1번과 100% 동일하게, 배경 톤/조명/여백/오렌지 색감/폰트/카드 시스템을 1번과 통일하세요.
같은 상세페이지의 연속된 장면입니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

` : '';

    // 다양성 톤
    const variationBlock = variation
      ? (copyPlan
        ? `[다양성 참고 - 이번 생성 톤] ⚠️
이번 섹션의 시각적 리듬과 문장 분위기는 "${variation.name}" 톤을 참고하세요. (${variation.desc})
단, 카피 기획서가 제공된 경우 이미지 안 문구는 새로 작성하지 말고 해당 섹션 카피를 우선 사용하세요.

`
        : `[다양성 강제 - 이번 생성 톤] ⚠️
이번 카피는 "${variation.name}" 톤으로 새로 작성하세요. (${variation.desc}) 예: ${variation.sample}
아래 예시 문구를 그대로 베끼지 말고, 이 톤으로 매번 다른 단어/문장 구조를 사용하세요.

`)
      : '';

    const context = `상품군: ${analysis.category_group}
템플릿: ${analysis.template_type}
타겟: ${safe(data.target, analysis.target_customer)}
고객 고민: ${safe(data.pain, analysis.main_pain_point)}
핵심 가치: ${safe(data.benefits, analysis.core_value)}
상품 스펙/구성 참고: ${safe(data.specs, analysis.spec_hint)}
판매 플랫폼: ${platform}
원하는 톤: ${tone}`;
    const specBlock = confirmedSpecBlock(data.specs || analysis.spec_hint || '');
    const multiBlock = multiImageUsageBlock(data);
    const dedupBlock = buildCategoryAwareDedupBlock(section, contentPlan);

    const layout = isHero
      ? `첫 화면 HERO입니다. 상단 소제목/배지 없이 큰 메인 타이틀을 바로 배치하고, 짧은 서브카피, 중앙 제품 비주얼, 하단 3개 핵심 카드 또는 CTA를 사용하세요.`
      : `본문 섹션입니다. 상단 소제목/배지를 넣지 마세요. HERO와 똑같은 상단-중앙-하단 3카드 반복 구조로 만들지 말고, 위 SHOT TYPE에 맞게 클로즈업/비교/흐름도/라이프스타일/인포그래픽 중 가장 적합한 구조를 선택하세요.`;

    if(PROMPT_SLIM_MODE_V13){
      const slimBrief = compactTextV13(masterBrief, PROMPT_MAX_BRIEF_V13);
      const slimCopyPlan = extractSectionCopyPlanV13(copyPlan, section, PROMPT_MAX_COPY_PLAN_V13);
      const slimSpecs = cleanPromptSpecTextV13(data.specs || analysis.spec_hint || '', PROMPT_MAX_SPECS_V13);
      const slimDedup = buildSlimCategoryAwareDedupBlockV13(section, contentPlan);
      const slimDesign = summarizeDesignBlockV13(designBlock || '', layoutBlock || '');
      const slimRefLock = buildSlimReferenceLockV13(product, analysis);
      const slimHeroLock = heroLock ? `[HERO 일관성]
앞서 만든 HERO의 제품 형태, 색상, 조명, 여백, 폰트, 카드 시스템과 같은 상세페이지처럼 이어지게 만드세요.` : '';
      const slimVariation = variation ? `[이번 섹션 톤]
${variation.name}: ${variation.desc}` : '';
      const slimContext = `상품군: ${analysis.category_group}
템플릿: ${analysis.template_type}
타겟: ${safe(data.target, analysis.target_customer)}
고객 고민: ${safe(data.pain, analysis.main_pain_point)}
핵심 가치: ${safe(data.benefits, analysis.core_value)}
플랫폼: ${platform}
톤: ${tone}`;
      const slimSpecBlock = slimSpecs ? `[확정/참고 정보 - 정제됨]
${slimSpecs}

규칙: 위에 명확한 정보만 이미지 문구로 사용하고, 미확정/도망 문구는 이미지에 넣지 마세요.` : '';
      const slimCopyBlock = slimCopyPlan ? `[이번 섹션 카피 기획서 발췌]
${slimCopyPlan}

규칙: 이 섹션의 메인/서브/카드 문구를 우선 사용하되 길면 자연스럽게 줄이세요.` : '';
      const slimBriefBlock = slimBrief ? `[마스터 브리프 핵심]
${slimBrief}` : '';
      const slimSalesCopy = buildSlimSalesCopyBlockV13(section, analysis);

      return `[상세페이지 섹션 이미지 생성 요청]
텍스트 설명 없이, 아래 기준으로 한국 이커머스 상세페이지 섹션 이미지를 생성하세요.

[현재 섹션]
${sectionTitle(section)} / 목적: ${g.goal}

${slimBriefBlock ? slimBriefBlock + '\n\n' : ''}${slimCopyBlock ? slimCopyBlock + '\n\n' : ''}${slimHeroLock ? slimHeroLock + '\n\n' : ''}${slimRefLock}

${shot}

${formula}

${slimDesign ? slimDesign + '\n\n' : ''}${buildSlimQualityRulesV13(section)}

${slimSalesCopy}

${slimDedup ? slimDedup + '\n\n' : ''}${multiBlock ? compactTextV13(multiBlock, 650) + '\n\n' : ''}${slimVariation ? slimVariation + '\n\n' : ''}${slimSpecBlock ? slimSpecBlock + '\n\n' : ''}[상품 자동 분석 결과]
${slimContext}

[SECTION - ${section}]
권장 레이아웃: ${g.layout}
카피 방향: ${g.copy}

[최종 지시]
- 제품 이미지는 첨부 원본 기준으로 유지하세요.
- 현재 섹션 역할과 한 가지 메시지에만 집중하세요.
- 확인되지 않은 수치/효과/인증/리뷰/별점/판매량/소재명은 만들지 마세요.
- HERO와 같은 상단-중앙-하단 3카드 구조를 반복하지 말고, 이 섹션의 SHOT TYPE에 맞는 구도로 만드세요.
- ⚠️ 한글 문구는 철자가 정확해야 합니다. 자모 분리·깨진 글자·오타가 보이면 실패. 자신 없으면 글자를 더 줄이고 크게 쓰세요.
- 이미지 안 글자는 최소화: 메인 1줄 + 서브 1줄 + 카드 2~3개까지. 그 이상 텍스트를 넣지 마세요.
- 비율: ${ratio}.
- 텍스트 답변 없이 이미지만 생성하세요.`;
    }

    return `${briefBlock}${copyPlanBlock}${heroLockBlock}${lock}

${shot}

${formula}

${salesCopyBlock}

${layoutBlock||''}

${designBlock||''}

${IMAGE_QUALITY_RULE_BLOCK}

${PRODUCT_INFO_INTEGRITY_BLOCK}

${multiBlock ? multiBlock + '\n\n' : ''}${variationBlock}${BANNED_COPY_RULE_BLOCK}

${specBlock ? specBlock + '\n\n' : ''}${dedupBlock ? dedupBlock + '\n\n' : ''}[상품 자동 분석 결과]
${context}

[SECTION - ${section}]
섹션 목표: ${g.goal}
권장 레이아웃: ${g.layout}
카피 방향: ${g.copy}

[제작 지시]
한국 ${platform} 상세페이지용 완성형 카드뉴스 이미지를 만들어주세요.
이 섹션은 단순 배너가 아니라 구매 설득 흐름의 일부입니다. 현재 섹션 역할과 한 가지 메시지에만 집중하세요.
${layout}
한 장 안에는 하나의 목적만 담고, 모바일에서 읽히는 큰 한글 타이포그래피를 사용하세요.
상단 소제목/배지/캡슐 라벨은 기본적으로 넣지 마세요. 이미지의 첫 문구는 메인 타이틀이어야 합니다.
카피 기획서가 제공된 경우 새 카피를 만들지 말고 해당 섹션의 메인 카피, 서브 카피, 카드 문구를 우선 사용하세요.
확인되지 않은 수치/스펙/효능/인증/리뷰수/별점/판매량/소재명/전체 사이즈 범위는 만들지 마세요.
"상세페이지 참조", "상품페이지 참고", "확인 필요", "미확인" 같은 문구는 이미지 안에 절대 넣지 마세요. 정보가 부족하면 해당 항목을 빼세요.
특정 사이즈 하나만 확인된 경우 그것을 전체 사이즈 기준처럼 쓰지 말고, 착용컷/길이감/커버 범위처럼 보이는 정보로 전환하세요.
제품 이미지는 원본 상품 사진 기준으로 유지하고, 카테고리 특성에 맞는 상세페이지 섹션처럼 구성하세요.

[카피 작성 규칙 - 손넬 와디즈 펀딩급]
- 상단 배지/소제목: 사용 금지. 섹션 역할 문구를 이미지 상단 캡슐 형태로 넣지 마세요.
- 메인 타이틀: 8~18자, 한 단어만 오렌지 강조. 정보 나열 금지, 감정/욕망을 건드리는 한 줄
  좋은 예: "오늘부터, 달라집니다", "작지만, 충분합니다"
  나쁜 예: "간편하게 사용 가능" (밋밋함)
- 서브 문구: 메인 타이틀과 이어 읽었을 때 자연스러운 한 줄. 같은 단어 반복 금지.
- 카드/라벨: 짧은 헤드 + 구체적 디테일
  좋은 예: 헤드 "단 3초" / 디테일 "꺼내서 바로 시작"
  나쁜 예: 헤드 "편리함" / 디테일 "쉽게 사용" (추상적)
- 말투: 존댓말/명사형/질문형만. 반말 평서형("-했다/-갔다/-한다") 절대 금지
- 한글 오타 없이, 한글 문장에 영단어 혼용 금지 (영문 단독 헤드라인만 허용)
- 금지어(첫인상/단정함/비즈니스 무드/깔끔한 인상/상세페이지 참조/확인 필요/미확인)는 절대 사용하지 말고, 실제로 확인된 디테일/사용상황으로 대체
- 리뷰 수, 별점, 판매량, 인증, 소재명, 사이즈 범위는 링크/사용자 입력에 명확히 있을 때만 사용
- 모든 카피는 고객이 겪는 실제 순간을 먼저 떠올리게 해야 합니다. 제품 자랑보다 구매자가 얻는 변화가 먼저 보이게 하세요.
- 한 섹션 안에서 메인 타이틀/서브/카드가 같은 말을 반복하면 실패입니다. 메인=욕구, 서브=근거, 카드=확인 포인트로 역할을 나누세요.
- 질문형은 꼭 필요할 때만 사용하고, 조건문+질문문을 억지로 붙이지 마세요. 예: "찾느라 망설인 적 있나요" 금지.
- 문장이 어색하면 의미를 유지한 채 단정형으로 고치세요. 예: "필요한 순간, 바로 꺼내기 어렵습니다".

[90점 최종 검수]
- 이 이미지를 보고 구매자가 '내 상황이다'라고 느낄 수 있어야 합니다.
- 설명문이 아니라 판매 문구처럼 자연스럽게 읽혀야 합니다.
- 확인된 사실만 사용하되, 그 사실이 고객에게 왜 좋은지까지 번역해야 합니다.
- 한글 오타, 어색한 띄어쓰기, 딱딱한 번역투가 있으면 실패입니다.
- 사용자가 선택한 디자인 무드와 결과물이 다르게 보이면 실패입니다. 무드의 색감/폰트/배치/카드 형태가 이미지에서 체감되어야 합니다.

[완성도 기준]
단순 제품컷이 아니라 실제 판매용 상세페이지 섹션처럼 완성하세요.
점 패턴/추상 도형/코너 장식/그라데이션 배경/클립아트/더미 텍스트 금지.
배경 장식은 최소화하고 제품/정보/카피의 위계를 선명하게.

비율: ${ratio}.`;
  }

  function generateDynamicPrompts({data={}, inferred=null, sectionCount='8', masterBrief='', copyPlan='', refStyle='', heroLockFromIndex=1, designMood='auto'}={}){
    // v21.8.24.66: 이번 실행의 구도 시드 — 같은 상품이라도 만들 때마다 섹션 구도/배치가 달라진다.
    _runVariantSeed = (Date.now() + Math.floor(Math.random() * 1e6)) >>> 0;
    const analysis = window.DP_PRODUCT_ANALYZER?.analyzeProductContext
      ? window.DP_PRODUCT_ANALYZER.analyzeProductContext(Object.assign({}, data, inferred||{}))
      : (inferred || {category_group:'자동분석 불가', template_type:'general_dynamic', recommended_sections:['HERO','PROBLEM','OVERVIEW','DETAIL','USAGE','BENEFIT','FAQ','CTA']});
    // v21.8.24.75: 제품명 칸이 비면 1단계 브리프에서 '공식 제품명'을 끌어와 플레이스홀더("첨부 원본 제품")가 박히던 버그 수정.
    // v21.8.24.91: 플랫폼/카테고리 꼬리표("- 물티슈/건티슈 | 쿠팡" 등)를 떼어 이미지에 깔끔한 제품명만 들어가게.
    const product = cleanProductNameV91(safe(data.product, '') || extractProductNameV75(masterBrief) || '첨부한 제품');
    const sections = pickSections(analysis, sectionCount);
    const contentPlan = buildSectionContentPlan(sections, analysis, data);
    const variation = pickVariation();
    const design = buildDesignBlock(designMood, analysis, `${data.product||''} ${data.category||''} ${analysis.category_group||''} ${analysis.product_type||''}`);
    // v21.8: 레퍼런스가 있으면 디자인 무드 대신 레퍼런스 스타일을 디자인 기준으로 (우선)
    const refBlock = refStyle ? `[레퍼런스 디자인 - 이 스타일을 최우선으로 따르세요] ⚠️
아래는 사용자가 지정한 "잘 만들어진 상세페이지"의 디자인 분석입니다.
이 톤/색감/타이포/레이아웃을 이번 상세페이지에 그대로 적용하세요. (아래 기본 디자인 무드보다 이게 우선)

${refStyle}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━` : '';
    const prompts = sections.map((section, idx) => ({
      title: sectionTitle(section),
      section,
      ratio: defaultRatio(section),
      // v21.8.24.41: 글자 오버레이용 — 섹션별 파싱된 카피(메인/서브/카드)를 함께 제공
      copy: parseSectionCopyV29(copyPlan || '', section),
      prompt: buildPrompt({
        section, product, data, analysis, variation,
        idx, total: sections.length,
        masterBrief: masterBrief || '',
        copyPlan: copyPlan || '',
        heroLock: (idx >= heroLockFromIndex && section !== 'HERO'),
        designBlock: refBlock ? (refBlock + '\n\n' + design.block) : design.block,
        layoutBlock: buildLayoutBlock(section, analysis, idx),
        contentPlan,
        refStyle: refStyle || ''
      })
    }));
    return {analysis, prompts, variation, design, hasRef: !!refStyle, contentPlan};
  }

  window.DP_DYNAMIC_PROMPTS = { generateDynamicPrompts, VARIATION_SEEDS, DESIGN_MOODS, DETAILPAGE_LAYOUT_TEMPLATES, COPY_QUALITY_RULES, COPY_QUALITY_RULES_SHORT, COPY_MESSAGE_MAP_RULES, COPY_SECTION_STRUCTURE_RULES, COPY_HOOK_RULES, validateCopyPlanV92, listPlanSectionsV92 };
})();
