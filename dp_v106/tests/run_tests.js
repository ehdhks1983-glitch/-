#!/usr/bin/env node
// 가상 테스트 러너 — 크롬 없이 Node(vm)로 확장 모듈을 직접 로드/실행해 검증한다.
// 사용: node tests/run_tests.js [그룹...]   그룹: syntax inject analyzer prompts manifest parser gifzip
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { spawnSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');

const groupsArg = process.argv.slice(2);
const runGroup = (g) => groupsArg.length === 0 || groupsArg.includes(g);

let passed = 0, failed = 0;
const failures = [];
function test(name, fn) {
  try { fn(); passed++; console.log('  ✅ ' + name); }
  catch (e) { failed++; failures.push({ name, msg: e.message }); console.log('  ❌ ' + name + ' — ' + e.message); }
}
function assert(cond, msg) { if (!cond) throw new Error(msg || '검증 실패'); }
function group(title) { console.log('\n■ ' + title); }

// ---- vm 컨텍스트에서 확장 스크립트 로드 (window/self 공유) ----
function loadScripts(files) {
  const w = {};
  const noop = () => 0;
  const ctx = {
    window: w, self: w, console,
    URL, TextEncoder, TextDecoder,
    setTimeout: noop, setInterval: noop, clearTimeout: noop, clearInterval: noop,
    navigator: { userAgent: 'test' },
    chrome: { storage: { local: { get: (_k, cb) => cb && cb({}), set: (_o, cb) => cb && cb() } }, runtime: {} }
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  for (const f of files) vm.runInContext(read(f), ctx, { filename: f });
  return w;
}

// ============================================================
if (runGroup('syntax')) {
  group('T0. 전체 JS 구문 검사 (node --check)');
  const jsFiles = fs.readdirSync(ROOT).filter((f) => f.endsWith('.js'));
  for (const f of jsFiles) {
    test('구문 OK: ' + f, () => {
      const r = spawnSync(process.execPath, ['--check', path.join(ROOT, f)], { encoding: 'utf8' });
      assert(r.status === 0, (r.stderr || '').split('\n')[0]);
    });
  }
}

// ============================================================
if (runGroup('inject')) {
  group('T1. manifest ↔ background 동적 주입 일관성 (Fix 1)');
  const manifest = JSON.parse(read('manifest.json'));
  const manifestJs = manifest.content_scripts[0].js;
  const bg = read('background.js');

  test('background.js의 executeScript files 목록 == manifest content_scripts 목록(순서 포함)', () => {
    const fileArrays = [...bg.matchAll(/files:\s*\[([^\]]*)\]/g)].map((m) =>
      [...m[1].matchAll(/['"]([^'"]+)['"]/g)].map((x) => x[1])
    );
    const jsArrays = fileArrays.filter((a) => a.some((f) => f.endsWith('.js')));
    assert(jsArrays.length === 1, 'JS 주입 files 배열이 1개여야 함 (발견: ' + jsArrays.length + ')');
    const injected = jsArrays[0];
    assert(JSON.stringify(injected) === JSON.stringify(manifestJs),
      '불일치 — manifest: [' + manifestJs.join(', ') + '] / 주입: [' + injected.join(', ') + ']');
  });
  test('styles.css insertCSS 주입 존재', () => {
    assert(/insertCSS\([\s\S]{0,120}?styles\.css/.test(bg), 'insertCSS styles.css 누락');
  });
  test('주입 대상 파일이 모두 실제 존재', () => {
    for (const f of manifestJs.concat(manifest.content_scripts[0].css, [manifest.background.service_worker])) {
      assert(fs.existsSync(path.join(ROOT, f)), '파일 없음: ' + f);
    }
  });
}

// ============================================================
if (runGroup('analyzer')) {
  group('T2. 상품 분류기 (product_analyzer.js) — 분류 + 일반화된 폴백 카피 (Fix 2)');
  const w = loadScripts(['product_analyzer.js']);
  const az = (data) => w.DP_PRODUCT_ANALYZER.analyzeProductContext(data);

  test('티셔츠 → fashion_clothing 분류', () => {
    assert(az({ product: '남성 오버핏 반팔 티셔츠' }).key === 'fashion_clothing');
  });
  test('티셔츠 폴백 타겟에 물놀이 전용 문구 없음', () => {
    const r = az({ product: '남성 오버핏 반팔 티셔츠' });
    const t = r.target_customer + ' ' + r.main_pain_point + ' ' + r.core_value;
    assert(!/워터파크|수영장|물놀이|래쉬가드/.test(t), '물놀이 전용 폴백 잔존: ' + t);
  });
  test('래쉬가드 → 여전히 fashion_clothing 분류(회귀 없음)', () => {
    assert(az({ product: '여성 래쉬가드 세트' }).key === 'fashion_clothing');
  });
  test('명함지갑 → fashion_accessory 분류', () => {
    assert(az({ product: '소가죽 명함지갑' }).key === 'fashion_accessory');
  });
  test('에코백 폴백 카피에 명함 전용 문구 없음', () => {
    const r = az({ product: '캔버스 에코백 보조가방' });
    assert(r.key === 'fashion_accessory', '분류: ' + r.key);
    const t = r.target_customer + ' ' + r.main_pain_point + ' ' + r.core_value + ' ' + r.competitor_hint;
    assert(!/명함/.test(t), '명함 전용 폴백 잔존: ' + t);
  });
  test('신발 경계 — 운동화→footwear, 구두약→shoe_care, 클리너→케어계열(footwear 아님)', () => {
    assert(az({ product: '남성 런닝화 운동화' }).key === 'footwear', '운동화 분류 오류');
    assert(az({ product: '구두약 광택 세트' }).key === 'shoe_care', '구두약 분류 오류');
    const cleaner = az({ product: '신발 클리너 세트' }).key;
    assert(['shoe_care', 'living'].includes(cleaner), '클리너 분류: ' + cleaner);
  });
  test('노트북 모델명(그램) → digital (사양형 인식 유지)', () => {
    assert(az({ product: 'LG 그램 16인치 노트북 인텔 코어울트라' }).key === 'digital');
  });
  test('사용자 입력 타겟이 폴백을 덮어씀', () => {
    const r = az({ product: '반팔 티셔츠', target: '20대 대학생' });
    assert(r.target_customer === '20대 대학생');
  });
}

// ============================================================
if (runGroup('prompts')) {
  group('T3. 프롬프트 엔진 (prompt_short_dynamic.js) — 카테고리 전략 일반화 (Fix 2)');
  const w = loadScripts(['product_analyzer.js', 'prompt_short_dynamic.js']);
  const gen = (product) => w.DP_DYNAMIC_PROMPTS.generateDynamicPrompts({ data: { product } });
  const allText = (r) => r.prompts.map((p) => p.prompt).join('\n');

  test('티셔츠 이미지 프롬프트(전 섹션)에 워터파크/래쉬가드 전략 미주입', () => {
    const r = gen('남성 오버핏 반팔 티셔츠');
    assert(r.analysis.key === 'fashion_clothing', '분류: ' + r.analysis.key);
    assert(r.prompts.length >= 6, '섹션 수 부족: ' + r.prompts.length);
    const t = allText(r);
    assert(!/워터파크|수영장|래쉬가드|바캉스/.test(t), '물놀이 전략 문구가 프롬프트에 주입됨');
  });
  test('에코백 이미지 프롬프트(전 섹션)에 명함지갑 전략 미주입', () => {
    const r = gen('캔버스 에코백 보조가방');
    const t = allText(r);
    assert(!/명함/.test(t), '명함 전용 문구가 프롬프트에 주입됨');
  });
  test('명함지갑 상품은 정상적으로 상품명이 프롬프트에 포함(파이프라인 관통)', () => {
    const t = allText(gen('소가죽 명함지갑'));
    assert(/명함지갑/.test(t), '상품명이 프롬프트에 없음');
  });
  test('프롬프트에 제품 1:1 재현 기준(v106 충실도) 포함', () => {
    const t = allText(gen('소가죽 명함지갑'));
    assert(/제품 재현 기준|1:1/.test(t), '충실도 규칙 누락');
  });
  test('parseConceptOptionsV106 — 기획안 5종 파싱', () => {
    const sample = [1, 2, 3, 4, 5].map((n) =>
      `[기획안 ${n}]\n- 컨셉명: 컨셉${n}\n- 핵심 상황: 상황${n}\n- 메인 메시지: 메시지${n}\n- 연출 방향: 연출${n}`
    ).join('\n');
    const list = w.DP_DYNAMIC_PROMPTS.parseConceptOptionsV106(sample);
    assert(list.length === 5, '파싱 개수: ' + list.length);
    assert(list[2].name === '컨셉3' && list[2].situation === '상황3' && list[2].message === '메시지3' && list[2].direction === '연출3',
      '3번 기획안 필드 불일치: ' + JSON.stringify(list[2]));
  });
  test('validateCopyPlanV92 — 정상 동작(스모크)', () => {
    const v = w.DP_DYNAMIC_PROMPTS.validateCopyPlanV92('아무 내용 없음', '테스트상품');
    assert(v && typeof v === 'object', '검증기 반환값 이상');
  });
}

// ============================================================
if (runGroup('manifest')) {
  group('T4. manifest 규격 (Fix 3)');
  const manifest = JSON.parse(read('manifest.json'));
  test('description ≤ 132자 (웹스토어/규격 한도)', () => {
    const len = [...manifest.description].length;
    assert(len <= 132, '현재 ' + len + '자');
  });
  test('name ≤ 45자', () => {
    assert([...manifest.name].length <= 45, '현재 ' + [...manifest.name].length + '자');
  });
  test('version 형식(숫자.숫자…) 유효', () => {
    assert(/^\d+(\.\d+){0,3}$/.test(manifest.version), 'version: ' + manifest.version);
  });
  test('CHANGELOG.md 존재(변경 이력 분리 보존)', () => {
    assert(fs.existsSync(path.join(ROOT, 'CHANGELOG.md')), 'CHANGELOG.md 없음');
  });
}

// ============================================================
if (runGroup('parser')) {
  group('T5. 링크 파서 (link_parser.js) — 메타 추출 + 엔티티 디코딩 (Fix 4)');
  const w = loadScripts(['link_parser.js']);
  const P = w.DPLinkParser;

  test('og 메타 기본 추출 + 가격 정규화', () => {
    const html = '<head><meta property="og:title" content="테스트 상품"><meta property="og:image" content="/img/a.jpg">' +
      '<meta property="product:price:amount" content="12,900"></head>';
    const r = P.parseProductMeta(html, 'https://smartstore.naver.com/x/1');
    assert(r.title === '테스트 상품', 'title: ' + r.title);
    assert(r.price === '12900', 'price: ' + r.price);
    assert(r.image === 'https://smartstore.naver.com/img/a.jpg', 'image: ' + r.image);
    assert(r.source === '스마트스토어', 'source: ' + r.source);
  });
  test('HTML 엔티티 — 기본(&amp;) + 한글 수치참조(&#54620;)', () => {
    const html = '<meta property="og:title" content="A &amp; B &#54620;정판">';
    const r = P.parseProductMeta(html, 'https://www.coupang.com/vp/products/1');
    assert(r.title === 'A & B 한정판', 'title: ' + r.title);
  });
  test('BMP 밖 문자(이모지) 수치참조 — &#x1F600; / &#128525; 가 깨지지 않음', () => {
    const html = '<meta property="og:title" content="한정판 &#x1F600; 굿즈 &#128525;">';
    const r = P.parseProductMeta(html, 'https://www.coupang.com/vp/products/1');
    assert(r.title.includes('😀') && r.title.includes('😍'), 'title: ' + r.title);
  });
  test('비정상 코드포인트(&#x110000;)는 안전 처리(예외 없음)', () => {
    const html = '<meta property="og:title" content="X &#x110000; Y">';
    const r = P.parseProductMeta(html, 'https://www.coupang.com/vp/products/1');
    assert(typeof r.title === 'string' && r.title.includes('X') && r.title.includes('Y'), 'title: ' + r.title);
  });
  test('소스 감지 + 해외 소스 판별', () => {
    assert(P.detectSource('https://www.coupang.com/vp/products/123') === '쿠팡');
    assert(P.isForeignSource('https://item.taobao.com/item.htm?id=1') === true);
    assert(P.isForeignSource('https://smartstore.naver.com/a/b') === false);
  });
  test('JSON-LD Product 추출', () => {
    const html = '<script type="application/ld+json">{"@type":"Product","name":"LD상품","offers":{"price":"5500"},"image":"https://cdn.x.com/i.jpg"}</' + 'script>';
    const r = P.parseProductMeta(html, 'https://www.ssg.com/item/1');
    assert(r.title === 'LD상품' && r.price === '5500', JSON.stringify(r));
  });
}

// ============================================================
if (runGroup('gifzip')) {
  group('T6. GIF/ZIP 인코더 무결성 (회귀 가드)');
  const w = loadScripts(['gif_encoder.js', 'zip_store.js']);

  test('GIF89a 인코딩 — 헤더/루프확장/트레일러 바이트 검증', () => {
    const mk = (c) => ({ width: 8, height: 8, data: new Uint8Array(8 * 8 * 4).fill(c) });
    const gif = w.DP_GIF.fromFrames([mk(40), mk(200)], { delayMs: 100, loop: 0 });
    const head = String.fromCharCode(...gif.slice(0, 6));
    assert(head === 'GIF89a', '헤더: ' + head);
    assert(gif[gif.length - 1] === 0x3B, '트레일러(0x3B) 누락');
    // NETSCAPE2.0 루프 블록은 글로벌 색상표(768B) 뒤에 위치 — 전체 버퍼에서 탐색
    const whole = Buffer.from(gif).toString('latin1');
    assert(whole.includes('NETSCAPE2.0'), '루프 확장 누락');
  });
  test('ZIP store 모드 — 시그니처/엔트리수/CRC 검증', () => {
    const enc = new TextEncoder();
    const zip = w.DP_ZIP.make([
      { name: 'a.txt', bytes: enc.encode('hello') },
      { name: '한글이름.txt', bytes: enc.encode('world') }
    ]);
    assert(zip[0] === 0x50 && zip[1] === 0x4B && zip[2] === 3 && zip[3] === 4, '로컬 헤더 시그니처 이상');
    // EOCD 탐색
    let eocd = -1;
    for (let i = zip.length - 22; i >= 0; i--) {
      if (zip[i] === 0x50 && zip[i + 1] === 0x4B && zip[i + 2] === 5 && zip[i + 3] === 6) { eocd = i; break; }
    }
    assert(eocd >= 0, 'EOCD 없음');
    const count = zip[eocd + 10] | (zip[eocd + 11] << 8);
    assert(count === 2, '엔트리 수: ' + count);
    assert(w.DP_ZIP._crc32(enc.encode('hello')) === 0x3610A686, 'CRC32("hello") 불일치');
  });
}

// ============================================================
console.log('\n──────────────────────────────');
console.log('결과: ' + passed + '개 통과, ' + failed + '개 실패');
if (failures.length) {
  console.log('실패 목록:');
  failures.forEach((f) => console.log('  ✗ ' + f.name + ' — ' + f.msg));
}
process.exit(failed ? 1 : 0);
