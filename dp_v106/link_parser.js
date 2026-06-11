// AI 상세페이지 디렉터 v20.8
// 상품 링크 분석 전용 파서. background.js에서 importScripts로 로드됩니다.
(function(global){
  const SOURCE_RULES = [
    [/coupang\.com/i, '쿠팡'],
    [/smartstore\.naver\.com|brand\.naver\.com|shopping\.naver\.com|search\.shopping\.naver\.com/i, '스마트스토어'],
    [/domeggook\.com|ddokdaily\.com/i, '도매꾹'],
    [/1688\.com/i, '1688'],
    [/taobao\.com/i, '타오바오'],
    [/tmall\.com/i, '티몰'],
    [/aliexpress\.(com|kr)/i, '알리익스프레스'],
    [/alibaba\.com/i, '알리바바'],
    [/vvic\.com/i, 'VVIC'],
    [/amazon\.co\.jp/i, '아마존재팬'],
    [/rakuten\.co\.jp/i, '라쿠텐'],
    [/wadiz\.kr/i, '와디즈'],
    [/11st\.co\.kr/i, '11번가'],
    [/gmarket\.co\.kr/i, 'G마켓'],
    [/auction\.co\.kr/i, '옥션'],
    [/ssg\.com/i, 'SSG']
  ];

  function parseProductMeta(html, url) {
    const out = { title: '', image: '', price: '', description: '', source: '', specs: '' };
    out.source = detectSource(url);

    out.title = firstMeta(html, ['og:title', 'twitter:title', 'title']) || '';
    out.image = firstMeta(html, ['og:image', 'twitter:image', 'image']) || '';
    out.description = firstMeta(html, ['og:description', 'twitter:description', 'description']) || '';
    out.price = firstMeta(html, ['product:price:amount', 'og:price:amount', 'twitter:data1']) || '';

    const ld = parseJsonLd(html);
    if (ld) {
      if (!out.title && ld.title) out.title = ld.title;
      if (!out.description && ld.description) out.description = ld.description;
      if (!out.image && ld.image) out.image = ld.image;
      if (!out.price && ld.price) out.price = ld.price;
    }

    const next = parseNextData(html);
    if (next) {
      if (!out.title && next.title) out.title = next.title;
      if (!out.description && next.description) out.description = next.description;
      if (!out.image && next.image) out.image = next.image;
      if (!out.price && next.price) out.price = next.price;
    }

    // v21.8.24.22: 구조화 상태 JSON 우선 추출 (네이버 __PRELOADED_STATE__ / 쿠팡 __PRELOADED_STATE__ /
    // Apollo / Nuxt 등). 화면 텍스트 추정보다 정확하다. 비어있는 항목만 채운다.
    if (!out.title || !out.price || !out.image || !out.description) {
      const state = parseInlineStateJson(html, [
        'window.__PRELOADED_STATE__', '__PRELOADED_STATE__',
        'window.__APOLLO_STATE__', '__APOLLO_STATE__',
        'window.__INITIAL_STATE__', '__INITIAL_STATE__',
        'window.__NEXT_DATA__', 'window.__NUXT__',
        // 해외(타오바오/티몰/1688/알리) 인라인 데이터 변수
        'window.runParams', 'g_page_config', 'window.__INIT_DATA__', '__INIT_DATA__',
        'window.__GLOBAL_DATA__', 'window.__PAGE_DATA__', 'window.iDataObj'
      ]);
      const picked = state ? deepPickFromObject(state) : null;
      if (picked) {
        if (!out.title && picked.title) out.title = picked.title;
        if (!out.description && picked.description) out.description = picked.description;
        if (!out.image && picked.image) out.image = picked.image;
        if (!out.price && picked.price) out.price = picked.price;
      }
    }

    // 모든 정확한 소스가 실패했을 때만 페이지 <title> 태그를 최후 폴백으로 사용
    if (!out.title) out.title = extractTitleTag(html);

    out.title = cleanText(out.title);
    out.description = cleanText(out.description);
    out.price = normalizePriceRaw(out.price);
    out.image = absolutizeUrl(cleanText(out.image), url);
    out.images = collectMetaImages(html, url, out.image);
    out.specs = extractProductSpecs(html);
    return out;
  }

  // v21.8.24.26: 메타/JSON-LD에서 여러 상품 이미지 수집(아이콘/배지 제외, 대표 이미지 우선)
  function collectMetaImages(html, url, primary) {
    const list = [];
    const push = (u) => {
      const a = absolutizeUrl(cleanText(u), url);
      if (!a || list.includes(a)) return;
      if (/sprite|icon|logo|badge|avatar|emoji|blank|spinner|qr|\.svg(\?|$)/i.test(a)) return;
      list.push(a);
    };
    if (primary) push(primary);
    (html.match(/<meta\b[^>]*>/gi) || []).forEach(tag => {
      const attrs = parseAttrs(tag);
      const prop = String(attrs.property || attrs.name || attrs.itemprop || '').toLowerCase();
      if (/^(og:image|og:image:url|og:image:secure_url|twitter:image|twitter:image:src|image)$/.test(prop) && attrs.content) push(attrs.content);
    });
    const ld = parseJsonLd(html);
    if (ld && ld.image) { if (Array.isArray(ld.image)) ld.image.forEach(push); else push(ld.image); }
    return list.slice(0, 12);
  }

  function extractProductSpecs(html) {
    const specs = [];
    const seen = new Set();
    const normalizeSizeToken = (txt = '') => {
      const t = cleanText(txt).toUpperCase().replace(/XXL/g, '2XL').replace(/ONE SIZE/g, 'FREE').replace(/프리/g, 'FREE');
      if (/^(XS|S|M|L|XL|2XL|3XL|4XL|5XL|FREE|44|55|66|77|88|90|95|100|105|110)$/.test(t)) return t;
      return '';
    };
    const extractSizes = (txt = '') => {
      const out = [];
      String(txt || '').replace(/XXL/gi, '2XL').split(/\n|\r|,|\/|\||·|ㆍ|\s+/).forEach(part => {
        const token = normalizeSizeToken(part);
        if (token && !out.includes(token)) out.push(token);
      });
      return out;
    };
    const isPolicyText = (txt = '') => /의류\/잡화\/수입명품|계절상품\/식품\/화장품|CD\s*\/\s*DVD\s*\/\s*GAME\s*\/\s*BOOK|복제가\s*가능한\s*상품|포장\s*등을\s*훼손|반품|교환|환불|취소|택\(TAG\)|라벨의\s*멸실|상품의\s*사용|상품의\s*훼손|구성품\s*누락|알러지|붉은\s*반점|가려움|따가움|단순변심|상호\s*\/\s*대표자|대표자|e-?mail|이메일|구매안전\s*서비스|서비스\s*가입사실|본\s*판매자는\s*고객님의\s*안전거래|통신판매업|사업자등록번호|판매자\s*정보|고객센터|전자상거래|소비자\s*보호/i.test(cleanText(txt));
    const isPriceLike = (txt = '') => /\d[\d,]{2,}\s*원|할인|판매자로켓|로켓배송|무료배송|도착\s*보장|내일|오늘|배송/i.test(cleanText(txt));
    const add = (label, value) => {
      label = cleanText(label).replace(/[\[\]{}]/g, '').trim();
      value = cleanText(value).replace(/^[：:\-\s]+/, '').trim();
      if (!label || !value) return;
      if (value.length < 1 || value.length > 90) return;
      if (/^(상호\s*\/\s*대표자|상호|대표자|e-?mail|이메일|구매안전\s*서비스|통신판매업|사업자등록번호|판매자\s*정보|CD\s*\/\s*DVD\s*\/\s*GAME\s*\/\s*BOOK)$/i.test(label)) return;
      const line = `${label}: ${value}`;
      // v21.8.24.3: 쿠팡 가격/배송/반품 안내와 사이즈 오인값은 확정 스펙으로 쓰지 않는다.
      if (isPolicyText(line)) return;
      if (/확인\s*필요|상품\s*상세|상세페이지\s*참조|상품상세|판매자\s*문의|구매|배송|리뷰|문의|광고|쿠팡|로그인|장바구니/i.test(value)) return;
      if (/전체\/패션의류|패션의류 잡화|홈인테리어|가전디지털|추천상품|함께 본 상품|다른 고객/i.test(value)) return;
      if (/자외선|UV|속건|냉감|고탄력|방수|발수/i.test(value)) return;
      if (/사이즈/i.test(label)) {
        const sizes = extractSizes(value);
        if (!sizes.length) return;
        value = sizes.join(', ');
      } else if (isPriceLike(value) && !/가격|판매가/i.test(label)) {
        return;
      }
      const key = `${label}:${value}`;
      if (seen.has(key)) return;
      seen.add(key);
      specs.push(`${label}: ${value}`);
    };

    const labels = [
      '사이즈','크기','제품 크기','상품 크기','가로','세로','높이','두께','무게','중량',
      '소재','재질','제품 소재','겉감','안감','메탈','스테인리스','인조가죽',
      '구성품','구성','구성 내용','수량','개수','색상','컬러','색상계열','옵션','옵션명',
      '수납','수납 매수','수납수','명함 수납','카드 수납','품명','모델명','품명 및 모델명','제조국','원산지'
    ];
    const labelAlt = labels.map(escapeReg).join('|');

    const visible = htmlToPlainText(html);
    const pairRe = new RegExp(`(${labelAlt})\\s*(?:[:：]|\\n|\\r|\\t| {2,})\\s*([^\\n\\r|]{1,90})`, 'gi');
    let m;
    while ((m = pairRe.exec(visible)) !== null) add(m[1], m[2]);

    const decoded = decodeEntity(html);
    for (const label of labels) {
      const l = escapeReg(label);
      const patterns = [
        new RegExp(`"(?:attributeTypeName|attributeName|name|key|title|label)"\\s*:\\s*"${l}"[\\s\\S]{0,260}?"(?:attributeValueName|attributeValue|value|content|text)"\\s*:\\s*"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"`, 'i'),
        new RegExp(`"${l}"\\s*:\\s*"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"`, 'i')
      ];
      for (const re of patterns) {
        const mm = decoded.match(re);
        if (mm) add(label, mm[1].replace(/\\"/g, '"'));
      }
    }

    return specs.slice(0, 18).join('\n');
  }

  function htmlToPlainText(html) {
    return decodeEntity(String(html || ''))
      .replace(/<script\b[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style\b[\s\S]*?<\/style>/gi, ' ')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|li|tr|th|td|dt|dd|section|article|table|h\d)>/gi, '\n')
      .replace(/<[^>]+>/g, ' ')
      .replace(/[ \t]+/g, ' ')
      .replace(/\n\s+/g, '\n')
      .replace(/\n{2,}/g, '\n')
      .trim();
  }

  function detectSource(url='') {
    const found = SOURCE_RULES.find(([re]) => re.test(url));
    return found ? found[1] : '기타';
  }

  function firstMeta(html, keys) {
    for (const key of keys) {
      const v = findMetaContent(html, key);
      if (v) return decodeEntity(v);
    }
    return '';
  }

  function findMetaContent(html, key) {
    const metas = html.match(/<meta\b[^>]*>/gi) || [];
    const keyLower = String(key).toLowerCase();
    for (const tag of metas) {
      const attrs = parseAttrs(tag);
      const prop = String(attrs.property || attrs.name || attrs.itemprop || '').toLowerCase();
      if (prop === keyLower && attrs.content) return attrs.content;
    }
    return '';
  }

  function parseAttrs(tag) {
    const attrs = {};
    tag.replace(/([:\w-]+)\s*=\s*(["'])(.*?)\2/gs, (_, name, q, value) => {
      attrs[name.toLowerCase()] = value;
      return '';
    });
    return attrs;
  }

  function extractTitleTag(html) {
    const m = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    return m ? decodeEntity(m[1]) : '';
  }

  function parseJsonLd(html) {
    const blocks = html.match(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>[\s\S]*?<\/script>/gi) || [];
    for (const block of blocks) {
      const raw = block.replace(/<script\b[^>]*>/i, '').replace(/<\/script>/i, '').trim();
      try {
        const parsed = JSON.parse(raw);
        const found = findProductLike(parsed);
        if (found) return found;
      } catch (_) {}
    }
    return null;
  }

  function findProductLike(node) {
    const stack = Array.isArray(node) ? [...node] : [node];
    while (stack.length) {
      const cur = stack.shift();
      if (!cur || typeof cur !== 'object') continue;
      const type = cur['@type'];
      const isProduct = type === 'Product' || (Array.isArray(type) && type.includes('Product')) || cur.offers || cur.price;
      if (isProduct) {
        const offers = Array.isArray(cur.offers) ? cur.offers[0] : cur.offers;
        return {
          title: cur.name || cur.headline || '',
          description: cur.description || '',
          image: Array.isArray(cur.image) ? cur.image[0] : (cur.image || cur.thumbnailUrl || ''),
          price: offers?.price || offers?.lowPrice || cur.price || ''
        };
      }
      if (Array.isArray(cur['@graph'])) stack.push(...cur['@graph']);
      for (const v of Object.values(cur)) {
        if (v && typeof v === 'object') stack.push(v);
      }
    }
    return null;
  }

  function parseNextData(html) {
    const m = html.match(/<script\b[^>]*id=["']__NEXT_DATA__["'][^>]*>([\s\S]*?)<\/script>/i);
    if (!m) return null;
    try {
      const obj = JSON.parse(m[1]);
      const text = JSON.stringify(obj);
      const title = pickString(text, ['productName','name','title']);
      const image = pickString(text, ['representativeImageUrl','imageUrl','thumbnailUrl','image']);
      const price = pickNumberOrString(text, ['salePrice','discountedSalePrice','price','finalPrice']);
      const description = pickString(text, ['description','subTitle']);
      return { title, image, price, description };
    } catch (_) { return null; }
  }

  function pickString(jsonText, keys) {
    for (const key of keys) {
      const re = new RegExp('"' + escapeReg(key) + '"\\s*:\\s*"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"', 'i');
      const m = jsonText.match(re);
      if (m) return decodeEntity(m[1].replace(/\\"/g, '"'));
    }
    return '';
  }

  function pickNumberOrString(jsonText, keys) {
    for (const key of keys) {
      const re = new RegExp('"' + escapeReg(key) + '"\\s*:\\s*("?)([0-9,.]+)\\1', 'i');
      const m = jsonText.match(re);
      if (m) return m[2];
    }
    return '';
  }

  // v21.8.24.22: 페이지 내 상태 JSON(`var = {...}` 또는 `<script id=...>{...}`) 추출
  function parseInlineStateJson(html, varNames) {
    const s = String(html || '');
    for (const name of varNames) {
      // 1) script#id 형태 (__NEXT_DATA__ 등)
      if (/^window\.__NEXT_DATA__$/.test(name) || name === '__NEXT_DATA__') {
        const m = s.match(/<script\b[^>]*id=["']__NEXT_DATA__["'][^>]*>([\s\S]*?)<\/script>/i);
        if (m) { try { return JSON.parse(m[1]); } catch (_) {} }
        continue;
      }
      // 2) 변수 할당 형태: window.__PRELOADED_STATE__ = {...};
      const re = new RegExp(escapeReg(name) + '\\s*=\\s*(\\{)');
      const m = re.exec(s);
      if (!m) continue;
      const start = m.index + m[0].length - 1; // '{' 위치
      const json = sliceBalancedBraces(s, start);
      if (json) {
        try { return JSON.parse(json); } catch (_) {
          // Nuxt 등은 함수형(JSON 아님)일 수 있음 → 건너뜀
        }
      }
    }
    return null;
  }

  // 문자열 인식 균형 중괄호 슬라이스: start('{')부터 짝이 맞는 '}'까지
  function sliceBalancedBraces(s, start) {
    let depth = 0, inStr = false, esc = false, q = '';
    for (let i = start; i < s.length; i++) {
      const c = s[i];
      if (inStr) {
        if (esc) esc = false;
        else if (c === '\\') esc = true;
        else if (c === q) inStr = false;
        continue;
      }
      if (c === '"' || c === "'") { inStr = true; q = c; continue; }
      if (c === '{') depth++;
      else if (c === '}') { depth--; if (depth === 0) return s.slice(start, i + 1); }
      // 안전장치: 과도하게 길면 중단
      if (i - start > 4000000) return '';
    }
    return '';
  }

  // 파싱된 상태 객체에서 상품명/가격/이미지/설명을 BFS로 탐색 (키 이름 기반)
  function deepPickFromObject(root) {
    const out = { title: '', image: '', price: '', description: '' };
    const nameKeys = ['productname', 'itemname', 'prodnm', 'goodsname', 'name', 'title', 'headline'];
    const priceKeys = ['discountedsaleprice', 'saleprice', 'finalprice', 'sellprice', 'dcprice', 'price', 'lowprice'];
    const imgKeys = ['representativeimageurl', 'mainimageurl', 'thumbnailurl', 'imageurl', 'mainimage', 'imgurl', 'image'];
    const descKeys = ['description', 'subtitle', 'detailcontent', 'summary'];
    const queue = [root];
    let guard = 0;
    while (queue.length && guard < 300000) {
      guard++;
      const cur = queue.shift();
      if (!cur || typeof cur !== 'object') continue;
      for (const k in cur) {
        const v = cur[k];
        if (v && typeof v === 'object') { queue.push(v); continue; }
        if (v == null) continue;
        const kl = String(k).toLowerCase();
        const sv = String(v).trim();
        if (!sv) continue;
        if (!out.title && nameKeys.includes(kl) && typeof v === 'string' && sv.length > 1 && sv.length < 160) out.title = sv;
        if (!out.price && priceKeys.includes(kl)) {
          const digits = sv.replace(/[^\d]/g, '');
          if (digits && Number(digits) > 0 && digits.length <= 9) out.price = digits;
        }
        if (!out.image && imgKeys.includes(kl) && /^(https?:)?\/\//i.test(sv) && /\.(jpg|jpeg|png|webp|gif)/i.test(sv)) out.image = sv;
        if (!out.description && descKeys.includes(kl) && typeof v === 'string' && sv.length > 5 && sv.length < 600) out.description = sv;
      }
    }
    return out;
  }

  function escapeReg(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function normalizePriceRaw(raw) {
    const digits = String(raw || '').replace(/[^\d]/g, '');
    return digits || '';
  }

  function formatPriceLabel(raw) {
    const digits = normalizePriceRaw(raw);
    return digits ? Number(digits).toLocaleString('ko-KR') + '원' : '';
  }

  function cleanText(s) {
    return decodeEntity(String(s || ''))
      .replace(/\s+/g, ' ')
      .replace(/^쿠팡!\s*\|\s*/i, '')
      .trim();
  }

  function absolutizeUrl(src, base) {
    if (!src) return '';
    try { return new URL(src, base).href; } catch (_) { return src; }
  }

  // v21.8.24.107: 수치 문자참조 디코딩을 fromCharCode → 코드포인트 기반으로 교체.
  // BMP 밖 문자(이모지 등, U+10000 이상)가 깨지던 문제 수정. 유효 범위 밖 값은 무시한다.
  function decodeNumericRef(n) {
    return (Number.isFinite(n) && n >= 0 && n <= 0x10FFFF) ? String.fromCodePoint(n) : '';
  }
  function decodeEntity(s) {
    if (!s) return '';
    return String(s)
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;|&apos;/g, "'")
      .replace(/&#x([0-9a-f]+);/gi, (_, h) => decodeNumericRef(parseInt(h, 16)))
      .replace(/&#(\d+);/g, (_, n) => decodeNumericRef(parseInt(n, 10)));
  }

  // v21.8.24.39: 해외(외국어) 소스 판별 — 번역/현지화 필요 여부 판단에 사용
  const FOREIGN_SOURCES = ['1688', '타오바오', '티몰', '알리익스프레스', '알리바바', 'VVIC', '아마존재팬', '라쿠텐'];
  function isForeignSource(srcOrUrl) {
    const v = String(srcOrUrl || '');
    if (FOREIGN_SOURCES.indexOf(v) >= 0) return true;
    return FOREIGN_SOURCES.indexOf(detectSource(v)) >= 0;
  }

  global.DPLinkParser = { parseProductMeta, formatPriceLabel, normalizePriceRaw, detectSource, isForeignSource };
})(typeof self !== 'undefined' ? self : window);
