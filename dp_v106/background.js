importScripts('link_parser.js');

// v21.8.24.8: Chrome message channel 보호용 강제 제한값
// 탭 보조 분석이 오래 걸리면 응답 채널이 닫히므로, 반드시 부분 응답을 먼저 반환한다.
const DP_FETCH_TIMEOUT_MS = 12000;
const DP_PAGE_OBSERVATION_TIMEOUT_MS = 38000;
const DP_TAB_LOAD_TIMEOUT_MS = 11000;
// v21.8.24.8: 쿠팡 탭 중복 열림 방지. 링크 분석은 한 번에 하나만 실행한다.
let DP_PRODUCT_FETCH_LOCK = false;
const DP_TEMP_PRODUCT_TABS = new Set();

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'DP_TOGGLE_PANEL' });
  } catch (e) {
    try {
      await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ['styles.css'] });
      // v21.8.24.107: 동적 주입 목록을 manifest content_scripts와 1:1 동일하게 유지.
      // (v21.8.13에서 한 번 고쳤지만 이후 추가된 gif_encoder/zip_store/template_store/fix_panel이
      //  빠져 있어, 이 경로로 주입되면 움짤·ZIP 내보내기·템플릿·고치기 패널이 동작하지 않던 문제 수정.)
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['product_analyzer.js', 'prompt_short_dynamic.js', 'gif_encoder.js', 'zip_store.js', 'content.js', 'template_store.js', 'fix_panel.js']
      });
    } catch (err) {
      console.error('AI 상세페이지 디렉터 주입 실패:', err);
    }
  }
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type !== 'DP_FETCH_PRODUCT_PAGE') return;
  if (DP_PRODUCT_FETCH_LOCK) {
    sendResponse({ ok: false, error: '이미 상품 링크 분석이 진행 중입니다. 잠시 후 다시 눌러주세요.' });
    return;
  }
  DP_PRODUCT_FETCH_LOCK = true;
  (async () => {
    try {
      const inputUrl = String(msg.url || '').trim();
      const normalizedUrl = normalizeProductUrl(inputUrl);
      if (!normalizedUrl.ok) {
        sendResponse({ ok: false, error: normalizedUrl.error });
        return;
      }

      const direct = await withTimeout(
        fetchProductHtml(normalizedUrl.url),
        DP_FETCH_TIMEOUT_MS,
        { ok: false, status: 0, timeout: true, error: '상품 HTML 직접 분석 시간 초과' }
      );
      if (direct.ok) {
        let merged = direct.data || {};
        let method = 'fetch';
        let warning = '';

        // v21.8.24.4: 탭 보조 분석은 오래 걸려도 메시지 채널을 닫지 않도록 강제 타임아웃을 둔다.
        if (shouldTryPageObservation(normalizedUrl.url, merged)) {
          const observed = await withTimeout(
            fetchProductViaTemporaryTab(normalizedUrl.url, merged),
            DP_PAGE_OBSERVATION_TIMEOUT_MS,
            { ok: false, timeout: true, error: '탭 보조 분석 시간 초과' }
          );
          if (observed.ok) {
            merged = mergeProductData(merged, observed.data || {});
            method = 'fetch+page_observation';
          } else if (observed.timeout) {
            await closeTemporaryProductTabs();
            merged = ensureFallbackFactData(merged);
            method = 'fetch_partial_timeout';
            warning = '쿠팡 탭 보조 분석 시간 초과 → 상품명/가격/플랫폼 중심으로 부분 적용했습니다. 옵션/상세스펙은 수동 확인이 필요할 수 있습니다.';
          }
        }

        sendResponse({ ok: true, data: merged, finalUrl: direct.finalUrl, method, warning });
        return;
      }

      // v20.9: 쿠팡/네이버 등 403 또는 동적 페이지는 실제 탭 로드 후 DOM에서 메타를 읽는 방식으로 1회 보조 시도
      const shouldTryTab = direct.status === 403 || direct.status === 401 || direct.status === 429 || /차단|동적|상품 정보를 찾지 못/i.test(direct.error || '');
      if (shouldTryTab) {
        const tabResult = await withTimeout(
          fetchProductViaTemporaryTab(normalizedUrl.url),
          DP_PAGE_OBSERVATION_TIMEOUT_MS,
          { ok: false, timeout: true, error: '탭 보조 분석 시간 초과' }
        );
        if (tabResult.ok) {
          sendResponse({ ok: true, data: tabResult.data, finalUrl: tabResult.finalUrl, method: 'tab_fallback', warning: direct.error });
          return;
        }
        if (tabResult.timeout) {
          await closeTemporaryProductTabs();
          sendResponse({ ok: false, error: `${direct.error} / 탭 보조 분석 시간 초과: 상품명·가격도 충분히 확보하지 못했습니다. 수동 입력을 권장합니다.` });
          return;
        }
        sendResponse({ ok: false, error: `${direct.error} / 탭 보조 분석도 실패: ${tabResult.error}` });
        return;
      }

      sendResponse({ ok: false, error: direct.error || '상품 링크 분석에 실패했습니다.' });
    } catch (e) {
      console.error('[DP] 상품 링크 분석 실패:', e);
      sendResponse({ ok: false, error: String(e?.message || e) });
    } finally {
      DP_PRODUCT_FETCH_LOCK = false;
    }
  })();
  return true;
});

// v21.8.24.48: 받아온 바이트의 매직바이트로 실제 이미지 형식을 판별한다.
// CDN/서버가 content-type을 잘못 줘도(또는 HTML/리다이렉트/트래킹 픽셀을 줘도)
// 실제 그림이 아닌 바이트를 image/jpeg로 위장해 첨부하던 문제("링크/파일"로 깨짐)를 막기 위함.
function sniffImageMimeFromBytes(bytes) {
  if (!bytes || bytes.length < 4) return '';
  const b = bytes;
  if (b[0] === 0xFF && b[1] === 0xD8 && b[2] === 0xFF) return 'image/jpeg';
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4E && b[3] === 0x47) return 'image/png';
  if (b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x38) return 'image/gif';
  if (b[0] === 0x42 && b[1] === 0x4D) return 'image/bmp';
  if (b.length >= 12 && b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 &&
      b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50) return 'image/webp';
  // SVG/XML 등 텍스트 기반 벡터 이미지는 앞부분에서 <svg 태그를 탐지
  let head = '';
  for (let i = 0; i < Math.min(bytes.length, 256); i++) head += String.fromCharCode(bytes[i]);
  if (/<svg[\s>]/i.test(head)) return 'image/svg+xml';
  return '';
}

// v21.8.24.18: 생성 이미지 합치기용. 콘텐츠 스크립트가 canvas 오염 없이 픽셀을 읽도록
// 크로스오리진 이미지(oaiusercontent 등)를 서비스워커가 host 권한으로 받아 dataURL로 돌려준다.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type !== 'DP_FETCH_IMAGE') return;
  (async () => {
    try {
      const url = String(msg.url || '').trim();
      if (!url) { sendResponse({ ok: false, error: '이미지 URL 없음' }); return; }
      const res = await fetch(url, { credentials: 'omit', redirect: 'follow' });
      if (!res.ok) { sendResponse({ ok: false, error: `이미지 응답 오류 ${res.status}` }); return; }
      const buf = new Uint8Array(await res.arrayBuffer());
      // v21.8.24.48: 헤더가 아니라 실제 바이트로 형식 판별. 이미지가 아니면 거부(첨부 단계에서 건너뜀).
      const headerCt = String(res.headers.get('content-type') || '');
      const sniffed = sniffImageMimeFromBytes(buf);
      const mime = sniffed || (/^image\//i.test(headerCt) ? headerCt.split(';')[0].trim() : '');
      if (!mime) {
        sendResponse({ ok: false, notImage: true, error: '이미지가 아닌 응답(HTML/리다이렉트/추적 픽셀 등)' });
        return;
      }
      let bin = '';
      const CHUNK = 0x8000;
      for (let i = 0; i < buf.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, buf.subarray(i, i + CHUNK));
      }
      sendResponse({ ok: true, dataUrl: `data:${mime};base64,${btoa(bin)}`, mime });
    } catch (e) {
      sendResponse({ ok: false, error: String(e?.message || e) });
    }
  })();
  return true;
});

function normalizeProductUrl(raw) {
  const value = String(raw || '').trim();
  if (!value) return { ok: false, error: '상품 링크를 입력하세요.' };
  if (/^\/\//.test(value)) return { ok: true, url: 'https:' + value };
  if (/^\/vp\/products\//i.test(value)) return { ok: true, url: 'https://www.coupang.com' + value };
  if (/^vp\/products\//i.test(value)) return { ok: true, url: 'https://www.coupang.com/' + value };
  if (/^https?:\/\//i.test(value)) return { ok: true, url: value };
  return { ok: false, error: '유효한 URL이 아닙니다. https:// 로 시작하거나 /vp/products/... 형태의 쿠팡 링크를 입력하세요.' };
}

// v21.8.24.23: 도매꾹 등 EUC-KR/CP949 페이지의 한글 깨짐 방지. 헤더/메타에서 charset을 찾아 알맞게 디코딩.
function decodeHtmlBuffer(buf, contentType) {
  const bytes = new Uint8Array(buf);
  let charset = '';
  const mh = /charset=["']?\s*([\w-]+)/i.exec(String(contentType || ''));
  if (mh) charset = mh[1].toLowerCase();
  if (!charset) {
    // 앞부분을 latin1로 가볍게 읽어 <meta charset> 또는 content-type meta를 탐지
    const head = new TextDecoder('utf-8', { fatal: false }).decode(bytes.subarray(0, 4096));
    const mm = /<meta[^>]+charset=["']?\s*([\w-]+)/i.exec(head) || /<meta[^>]+content=["'][^"']*charset=\s*([\w-]+)/i.exec(head);
    if (mm) charset = mm[1].toLowerCase();
  }
  const isKorLegacy = /euc-?kr|ks_c_5601|cp949|x-windows-949|windows-949/.test(charset);
  try {
    if (isKorLegacy) return new TextDecoder('euc-kr').decode(bytes);
    return new TextDecoder(charset || 'utf-8', { fatal: false }).decode(bytes);
  } catch (_) {
    try { return new TextDecoder('euc-kr').decode(bytes); } catch (_2) {
      return new TextDecoder('utf-8', { fatal: false }).decode(bytes);
    }
  }
}

async function fetchProductHtml(url) {
  try {
    const res = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'
      },
      // v21.8.24.96: 'omit'→'include'. 사용자가 이미 쿠팡에 접속/로그인했다면 브라우저가 보유한
      // 세션/봇차단 쿠키(Akamai _abck·bm_sz 등)가 함께 전송돼 403을 통과할 확률이 크게 오른다.
      credentials: 'include',
      redirect: 'follow'
    });

    if (!res.ok) {
      return { ok: false, status: res.status, error: `페이지 응답 오류 (${res.status}). 쇼핑몰이 외부 분석 요청을 차단했을 수 있습니다.` };
    }

    const contentType = res.headers.get('content-type') || '';
    const buf = await res.arrayBuffer();
    const html = decodeHtmlBuffer(buf, contentType);
    if (!/html|text/i.test(contentType) && !/<html|<meta|<script/i.test(html)) {
      return { ok: false, status: 0, error: '상품 HTML을 읽지 못했습니다. 링크가 이미지/파일 또는 차단 페이지일 수 있습니다.' };
    }

    const parsed = DPLinkParser.parseProductMeta(html, res.url || url);
    if (!parsed.title && !parsed.image && !parsed.price) {
      return { ok: false, status: 0, error: '상품 정보를 찾지 못했습니다. 로그인/봇 차단/동적 페이지일 수 있어 수동 입력이 필요합니다.' };
    }

    return { ok: true, data: parsed, finalUrl: res.url || url };
  } catch (e) {
    return { ok: false, status: 0, error: String(e?.message || e) };
  }
}

async function fetchProductViaTemporaryTab(url, existingData = null) {
  let tabId = null;
  try {
    // v21.8.24.96: active:false→true. 숨김(백그라운드) 탭은 타이머가 throttle돼 쿠팡 Akamai
    // 봇차단 JS 챌린지(쿠키 생성)가 제때 끝나지 않아 차단 페이지를 받던 문제가 컸다.
    // 보이는 탭으로 잠깐 열어 챌린지를 통과시키고, 분석이 끝나면 자동으로 닫는다(원래 탭으로 포커스 복귀).
    const tab = await chrome.tabs.create({ url, active: true });
    tabId = tab.id;
    if (tabId) DP_TEMP_PRODUCT_TABS.add(tabId);
    await waitForTabComplete(tabId, DP_TAB_LOAD_TIMEOUT_MS);
    await sleep(900);


    // v21.8.24.4: 응답 안정성 우선. 전체 예열 스크롤은 제거하고 상단 구매/옵션 영역만 관찰한다.
    try {
      await chrome.scripting.executeScript({ target: { tabId }, func: () => { window.scrollTo(0, 0); } });
      await sleep(220);
    } catch (_) {}

    const injected = await chrome.scripting.executeScript({
      target: { tabId },
      func: async () => {
        const clean = (v = '') => String(v || '').replace(/\s+/g, ' ').trim();
        const toText = (el) => clean(el?.innerText || el?.textContent || '');
        const sleep = (ms) => new Promise(r => setTimeout(r, ms));
        const uniqPush = (arr, value, max = 12) => {
          const v = clean(value);
          if (!v || arr.includes(v)) return;
          if (arr.length < max) arr.push(v);
        };
        const visible = (el) => {
          if (!el) return false;
          const st = window.getComputedStyle(el);
          if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        };
        const pickFirst = (sels) => {
          for (const sel of sels) {
            const el = document.querySelector(sel);
            const txt = toText(el);
            if (txt) return txt;
          }
          return '';
        };
        const normalizeSizeToken = (txt = '') => {
          const t = clean(txt).toUpperCase().replace(/XXL/g, '2XL').replace(/ONE SIZE/g, 'FREE').replace(/프리/g, 'FREE');
          if (/^(XS|S|M|L|XL|2XL|3XL|4XL|5XL|FREE)$/.test(t)) return t;
          if (/^(44|55|66|77|88|90|95|100|105|110)$/.test(t)) return t;
          return '';
        };
        const isSizeValue = (txt) => !!normalizeSizeToken(txt);
        const isPriceLike = (txt = '') => /\d[\d,]{2,}\s*원|할인|판매자로켓|로켓배송|무료배송|도착\s*보장|내일|오늘|배송/i.test(clean(txt));
        const isPolicyText = (txt = '') => /의류\/잡화\/수입명품|계절상품\/식품\/화장품|반품|교환|환불|취소|택\(TAG\)|라벨의\s*멸실|상품의\s*사용|상품의\s*훼손|구성품\s*누락|알러지|붉은\s*반점|가려움|따가움|단순변심/i.test(clean(txt));
        const extractSizeValues = (txt = '') => {
          const out = [];
          String(txt || '')
            .replace(/XXL/gi, '2XL')
            .split(/\n|\r|,|\/|\||·|ㆍ|\s+/)
            .map(clean)
            .forEach(part => {
              const token = normalizeSizeToken(part);
              if (token && !out.includes(token)) out.push(token);
            });
          return out;
        };
        const firstLineSizeValue = (el) => {
          const raw = String(el?.innerText || el?.textContent || '');
          const lines = raw.split(/\n+/).map(clean).filter(Boolean);
          if (!lines.length) return '';
          const firstToken = normalizeSizeToken(lines[0]);
          if (firstToken) return firstToken;
          const m = clean(lines.join(' ')).match(/^(XS|S|M|L|XL|XXL|2XL|3XL|4XL|5XL|FREE|프리|44|55|66|77|88|90|95|100|105|110)(?=\s|$)/i);
          return m ? normalizeSizeToken(m[1]) : '';
        };
        const hasColorWord = (txt) => /블랙|화이트|아이보리|베이지|네이비|핑크|레드|옐로|오렌지|그린|블루|그레이|카키|브라운|퍼플|검정|흰색/.test(txt);
        const normalizeOptionLabel = (txt) => {
          const t = clean(txt).replace(/품절|일시품절|선택|옵션|사이즈|색상|컬러|\/|-/g, ' ').replace(/\s+/g, ' ').trim();
          return normalizeSizeToken(t) || t || clean(txt);
        };
        // v21.8.24.96: 주문폼의 연락처(휴대전화 앞자리) select가 상품 '옵션 후보'로 오수집되던 문제 차단용
        const isPhoneLike = (name = '', value = '') => {
          const n = clean(name).toLowerCase();
          const v = clean(value);
          if (/consumer_mobile|mobile|phone|tel|연락처|전화|휴대|핸드폰|fax|email|이메일/i.test(n)) return true;
          if (/^(010|011|016|017|018|019|050\d?|02|0\d{2,3})$/.test(v)) return true; // 전화 앞자리 토큰
          return false;
        };
        const isNoiseOptionValue = (value, groupName = '') => {
          const v = clean(value);
          const g = clean(groupName).toLowerCase();
          if (!v) return true;
          if (/^component$/i.test(g)) return true;
          if (isPhoneLike(g, v)) return true;
          if (/전체\/패션의류|패션의류 잡화|뷰티\/출산|주방용품|홈인테리어|가전디지털|도서 음반 DVD|자동차용품/.test(v)) return true;
          if (/추천상품|함께 본 상품|다른 고객|광고|카테고리|랭킹|로켓|쿠팡홈|장바구니|바로구매/.test(v)) return true;
          if (/[,.，]/.test(v) && v.length > 12) return true;
          if (/여성용|남성용|래쉬가드|레쉬가드|수영복|상의|하의|팬츠|원피스|브랜드|상품명/.test(v) && v.length > 12) return true;
          return false;
        };
        const optionGroupNameFor = (name, value) => {
          const n = clean(name);
          const v = clean(value);
          if (isSizeValue(v)) return '사이즈 옵션 후보';
          if (hasColorWord(v) && !/계열/.test(v)) return '색상 옵션 후보';
          if (/색상계열/.test(n) || /색상계열/.test(v)) return '색상계열';
          return n || '옵션';
        };

        const optionGroups = [];
        const optionGroupKey = (name = '') => {
          const n = clean(name);
          if (/현재 선택된 사이즈/.test(n)) return 'current-size';
          if (/사이즈 옵션 후보/.test(n)) return 'size-candidates';
          if (/현재 선택된 색상/.test(n)) return 'current-color';
          if (/색상 옵션 후보/.test(n)) return 'color-candidates';
          if (/색상계열/.test(n)) return 'color-family';
          return n || '옵션';
        };
        const getOrCreateGroup = (name) => {
          const groupName = clean(name || '옵션');
          const key = optionGroupKey(groupName);
          let group = optionGroups.find(g => optionGroupKey(g.name) === key);
          if (!group) {
            group = { name: groupName, values: [] };
            optionGroups.push(group);
          }
          return group;
        };
        const addOptionValue = (name, value, max = 18) => {
          let raw = clean(value);
          let v = normalizeOptionLabel(raw);
          let groupName = optionGroupNameFor(name, v);
          if (/사이즈|size/i.test(groupName) || /사이즈|size/i.test(name)) {
            const sizes = extractSizeValues(raw);
            if (!sizes.length) return;
            v = sizes[0];
            groupName = /현재 선택된 사이즈/.test(name) ? '현재 선택된 사이즈' : '사이즈 옵션 후보';
          }
          if (!v || v.length > 22) return;
          if (isNoiseOptionValue(v, groupName)) return;
          if (/색상 옵션 후보|현재 선택된 색상/.test(groupName) && (v.length > 12 || /계열/.test(v) || isPriceLike(v))) return;
          if (/사이즈 옵션 후보|현재 선택된 사이즈/.test(groupName) && !isSizeValue(v)) return;
          const group = getOrCreateGroup(groupName);
          uniqPush(group.values, v, max);
        };
        const collectSelectedOptionTexts = () => {
          [...document.querySelectorAll('div,button,[role="button"],[class*="option"],[class*="select"],[class*="dropdown"]')].forEach(el => {
            if (!visible(el)) return;
            const raw = String(el.innerText || el.textContent || '');
            const compact = clean(raw);
            if (!compact || compact.length > 80) return;
            const sizeMatch = raw.match(/사이즈\s*(?:[:：]|\n|\r|\s)+\s*(XS|S|M|L|XL|XXL|2XL|3XL|4XL|5XL|FREE|프리|44|55|66|77|88|90|95|100|105|110)/i);
            if (sizeMatch) addOptionValue('현재 선택된 사이즈', sizeMatch[1]);
            const colorMatch = raw.match(/색상\s*[:：]?\s*([가-힣A-Za-z0-9]{2,12})/i);
            if (colorMatch && hasColorWord(colorMatch[1]) && !/계열/.test(colorMatch[1])) addOptionValue('현재 선택된 색상', colorMatch[1]);
          });
        };

        const collectCoupangDropdownSizeBlocks = () => {
          const selectors = [
            '[role="option"]', '[role="listbox"] li', '[aria-selected]',
            '[class*="prod-option"] li', '[class*="prod-option"] button', '[class*="prod-option"] a',
            '[class*="dropdown"] li', '[class*="dropdown"] button', '[class*="select"] li'
          ];
          const seen = new Set();
          selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
              if (!visible(el) || seen.has(el)) return;
              seen.add(el);
              const raw = String(el.innerText || el.textContent || '');
              const txt = clean(raw);
              if (!txt || txt.length > 160) return;
              const firstSize = firstLineSizeValue(el);
              if (firstSize) {
                addOptionValue('사이즈 옵션 후보', firstSize);
                return;
              }
              // 쿠팡 드롭다운 옵션 블록은 "M / 25,700원 / 내일 도착" 형태다. 첫 줄이 사이즈가 아니면 가격/배송 블록은 버린다.
              if (isPriceLike(txt) || isPolicyText(txt)) return;
            });
          });
        };

        const collectVisibleOptionTexts = (source = '화면') => {
          collectSelectedOptionTexts();
          collectCoupangDropdownSizeBlocks();

          document.querySelectorAll('select').forEach(sel => {
            const name = sel.getAttribute('name') || sel.getAttribute('aria-label') || sel.id || '옵션';
            const values = [...sel.options].map(o => clean(o.textContent)).filter(v => v && !/선택|고르/i.test(v));
            if (/^component$/i.test(name) || values.join('/').length > 120) return;
            // v21.8.24.96: 휴대전화 앞자리/연락처/이메일 도메인 select는 상품 옵션이 아니므로 통째로 건너뛴다.
            if (isPhoneLike(name) || values.some(v => isPhoneLike(name, v))) return;
            values.forEach(v => addOptionValue(name, v));
          });

          const optionSelectors = [
            '[role="option"]', '[role="listbox"] li', '[aria-selected]',
            '[class*="prod-option"] li', '[class*="prod-option"] button', '[class*="prod-option"] span',
            '[class*="option"] li', '[class*="option"] button', '[class*="option"] span',
            '[class*="select"] li', '[class*="select"] button', '[class*="select"] span',
            '[class*="dropdown"] li', '[class*="dropdown"] button', '[class*="dropdown"] span'
          ];
          const seen = new Set();
          optionSelectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
              if (!visible(el)) return;
              if (seen.has(el)) return;
              seen.add(el);
              const raw = String(el.innerText || el.textContent || '');
              const txt = clean(raw);
              if (!txt || txt.length > 80) return;
              const firstSize = firstLineSizeValue(el);
              if (firstSize) { addOptionValue('사이즈 옵션 후보', firstSize); return; }
              if (isPriceLike(txt) || isPolicyText(txt)) return;
              const context = toText(el.closest('[class*="option"],[id*="option"],[class*="select"],[id*="select"],[class*="dropdown"],[id*="dropdown"],ul,li,section,div') || el.parentElement || el);
              const optionContext = /사이즈|색상|컬러|옵션|선택|XL|FREE|프리|화이트|블랙/.test(context + ' ' + txt);
              if (!optionContext && !isSizeValue(txt) && !hasColorWord(txt)) return;
              if (isNoiseOptionValue(txt, context)) return;
              if (isSizeValue(txt)) addOptionValue('사이즈 옵션 후보', txt);
              if (hasColorWord(txt) && !/계열/.test(txt)) addOptionValue('색상 옵션 후보', txt);
            });
          });
        };

        const openOptionDropdowns = async () => {
          const candidates = [];
          const addCandidate = (el) => {
            if (!el || candidates.includes(el) || !visible(el)) return;
            const txt = toText(el);
            const aria = clean(el.getAttribute?.('aria-label') || '');
            const cls = clean(el.className || '');
            const parentTxt = toText(el.closest?.('div,section,li,label') || el.parentElement || el);
            const hay = `${txt} ${aria} ${cls} ${parentTxt}`;
            if (!/사이즈|색상|컬러|옵션|선택|dropdown|select|prod-option|구매옵션/i.test(hay)) return;
            const r = el.getBoundingClientRect();
            if (r.width < 20 || r.height < 16) return;
            candidates.push(el);
          };

          document.querySelectorAll('select, button, [role="button"], [aria-haspopup], [class*="option"], [class*="select"], [class*="dropdown"], .prod-option-dropdown, .prod-option__dropdown, .dropdown, .selectbox').forEach(addCandidate);
          [...document.querySelectorAll('div,span,a,label')].forEach(el => {
            const txt = toText(el);
            if (/^(사이즈|색상|컬러|옵션)$/.test(txt) || /사이즈\s*(XS|S|M|L|XL|2XL|3XL|4XL|FREE|프리|\d{2,3})/i.test(txt)) {
              addCandidate(el.closest('div,button,[role="button"],label') || el);
              addCandidate(el.parentElement);
              addCandidate(el.nextElementSibling);
            }
          });

          collectVisibleOptionTexts('초기');
          for (const el of candidates.slice(0, 4)) {
            try {
              el.scrollIntoView({ block: 'center', inline: 'center' });
              await sleep(180);
              el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
              el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
              el.click();
              await sleep(260);
              collectVisibleOptionTexts('클릭후');
              document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
              await sleep(80);
            } catch (_) {}
          }
        };

        // v21.8.24.96: 동적 갤러리 로드 대기. 쿠팡 등은 메인 상품 이미지가 lazy-load라
        // 탭이 'complete'여도 갤러리 img가 아직 안 떠 빈 DOM/오수집이 되던 문제를 줄인다.
        // 상품 갤러리/상세 이미지가 1장이라도 뜨면 즉시 진행, 없으면 최대 ~3.5초만 폴링한다.
        const waitForGallery = async () => {
          const sel = '.prod-image img, [class*="prod-image"] img, [class*="ProductImage"] img, [class*="product-image"] img, #productDetail img, [class*="product-detail"] img';
          for (let i = 0; i < 14; i++) {
            const ready = [...document.querySelectorAll(sel)].some(im =>
              (im.naturalWidth || 0) >= 200 || /vendor_inventory|retail-product|coupangcdn|image\./i.test(im.currentSrc || im.src || ''));
            if (ready) return;
            await sleep(250);
          }
        };
        await waitForGallery();

        // v21.8.24.8: 안정성 우선. 쿠팡 드롭다운을 억지로 열지 않는다.
        // 자동 수집은 현재 화면에 보이는 기본 정보만 읽고, 전체 색상/사이즈 옵션은 사용자 수동 보정을 우선한다.
        collectVisibleOptionTexts('상단표시정보만');
        window.scrollTo(0, 0);
        await sleep(80);

        const title = pickFirst(['h1', '[class*="prod-buy-header"] h2', '[class*="ProductHeader"] h1', '[data-testid*="title"]']) || document.title || '';

        const priceCandidates = [];
        document.querySelectorAll('strong,em,span,div').forEach(el => {
          if (!visible(el)) return;
          const txt = toText(el);
          if (!txt || txt.length > 30) return;
          if (/\d[\d,]{2,}\s*원/.test(txt)) uniqPush(priceCandidates, txt, 10);
        });

        const details = [];
        const unknownFields = [];
        const isUnknownValue = (value) => /상품\s*상세|상세페이지\s*참조|판매자\s*문의|업체\s*제공|확인\s*필요|미확인|참조|별도표기/i.test(clean(value));
        const addUnknown = (field) => uniqPush(unknownFields, clean(field), 18);
        const addDetail = (k, v) => {
          const key = clean(k).replace(/[：:]+$/, '');
          const val = clean(v);
          if (!key || !val || val.length > 140) return;
          const line = `${key}: ${val}`;
          if (isPolicyText(line)) return;
          if (/장바구니|바로구매|혜택보기|공유하기|카테고리|추천상품|함께 본 상품|반품|교환|환불/i.test(val)) return;
          if (/사이즈/i.test(key)) {
            const sizes = extractSizeValues(val);
            if (!sizes.length) return;
            const target = sizes.length === 1 ? '현재 선택된 사이즈' : '사이즈 옵션 후보';
            sizes.forEach(size => addOptionValue(target, size));
            return;
          }
          if (/소재|재질|제품 소재|제조국|세탁|취급주의|구성|구성품|수량/i.test(key) && isUnknownValue(val)) { addUnknown(key); return; }
          if (isUnknownValue(val)) return;
          if (isPriceLike(val) && !/가격|판매가/.test(key)) return;
          if (/자외선|UV|속건|냉감|고탄력|방수|발수/i.test(val) && !/상품정보|필수|상세|고시|table/i.test(key)) return;
          uniqPush(details, line, 38);
        };

        document.querySelectorAll('table tr').forEach(tr => {
          const th = toText(tr.querySelector('th'));
          const td = toText(tr.querySelector('td'));
          if (th && td) addDetail(th, td);
        });

        [...document.querySelectorAll('dt')].forEach(dt => {
          const dd = dt.nextElementSibling;
          const th = toText(dt);
          const td = toText(dd);
          if (th && td) addDetail(th, td);
        });

        const bodyText = clean(document.body?.innerText || '');
        const labels = ['사이즈', '옵션', '색상', '컬러', '색상계열', '소재', '재질', '구성', '구성품', '품명', '모델명', '제조국', '원산지', '세탁', '주의사항', '상품번호'];
        labels.forEach(label => {
          const re = new RegExp(label + '\\s*[:：]?\\s*([^\\n]{1,100})', 'i');
          const m = bodyText.match(re);
          if (m) addDetail(label, m[1]);
        });

        // 쿠팡 bullet 정보처럼 한 줄 단위로 보이는 기본 정보도 후보로 추가한다.
        bodyText.split(/\s*•\s*|\n/).forEach(line => {
          const t = clean(line);
          if (/^(색상계열|사이즈|상품번호|색상|구성|소재|제조국)\s*[:：]/.test(t)) {
            const idx = t.search(/[:：]/);
            addDetail(t.slice(0, idx), t.slice(idx + 1));
          }
        });

        // 선택값과 후보값은 절대 합치지 않는다. 쿠팡 드롭다운 가격/배송 문구는 여기서도 2차 제거한다.
        optionGroups.forEach(g => {
          g.values = [...new Set((g.values || []).map(v => clean(v)).filter(Boolean))]
            .filter(v => {
              if (/사이즈/.test(g.name)) return isSizeValue(v);
              if (/색상/.test(g.name)) return hasColorWord(v) && !isPriceLike(v) && !/계열/.test(v);
              return !isPriceLike(v) && !isPolicyText(v);
            })
            .slice(0, 18);
        });
        const currentSizes = new Set(optionGroups.filter(g => /현재 선택된 사이즈/.test(g.name)).flatMap(g => g.values || []));
        optionGroups.forEach(g => {
          if (/사이즈 옵션 후보/.test(g.name) && currentSizes.size) {
            g.values = (g.values || []).filter(v => !currentSizes.has(v));
          }
        });
        for (let i = optionGroups.length - 1; i >= 0; i--) {
          if (!optionGroups[i].values.length) optionGroups.splice(i, 1);
        }

        const reviewSummary = [];
        [/별점\s*([0-5](?:\.\d)?)/i, /평점\s*([0-5](?:\.\d)?)/i, /리뷰\s*([0-9,]+)개/i, /상품평\s*([0-9,]+)개/i, /\(([0-9,]+)\)\s*한\s*달간/i, /한\s*달간\s*[0-9,]+명\s*이상\s*구매/i].forEach(re => {
          const m = bodyText.match(re);
          if (m) uniqPush(reviewSummary, m[0], 8);
        });

        return {
          html: document.documentElement ? document.documentElement.outerHTML : '',
          title,
          url: location.href,
          bodyText: bodyText.slice(0, 9000),
          priceCandidates,
          details,
          optionGroups,
          reviewSummary,
          imageCount: document.images ? document.images.length : 0,
          detailImageCount: (() => {
            // v21.8.24.96: 상세 컨테이너 안의 이미지는 쿠팡 CDN이 아니어도(도매꾹 등) 크기 기준으로 센다.
            // 컨테이너가 없으면(쿠팡 외 일부) 페이지 전체 + 쿠팡 CDN 패턴으로만 제한해 추천/광고 과대집계를 막는다.
            const roots = [...document.querySelectorAll('#productDetail, #product-detail, [id*="productDetail"], [class*="product-detail"], [class*="ProductDetail"], [class*="goods_detail"], [class*="goodsDetail"], [class*="detail-content"], [class*="item-detail"]')];
            const inRoot = roots.length > 0;
            const imgs = (inRoot ? roots.flatMap(root => [...root.querySelectorAll('img')]) : [...document.images])
              .filter(img => {
                const src = img.src || '';
                const r = img.getBoundingClientRect();
                if (/sprite|icon|logo|badge|avatar|profile|review/i.test(src)) return false;
                if (!/^https?:/i.test(src)) return false;
                if (!inRoot && !/vendor_inventory|retail-product|product-detail|image\.coupangcdn\.com/i.test(src)) return false;
                if (r.width && r.width < 120) return false;
                if (r.height && r.height < 80) return false;
                return true;
              });
            return new Set(imgs.map(img => img.currentSrc || img.src)).size;
          })(),
          unknownFields,
          heroImage: (document.querySelector('.prod-image__detail, [class*="prod-image"] img, [class*="ProductImage"] img, [class*="product-image"] img') || document.querySelector('img'))?.src || '',
          // v21.8.24.30: 상품 갤러리 이미지 여러 장 수집. 백그라운드(숨김) 탭은 lazy-load라
          // naturalWidth/레이아웃 크기가 0인 경우가 많아, src뿐 아니라 data-src/srcset 등 지연로딩 속성까지 읽고
          // 크기 정보가 없으면(=아직 미로딩) src 패턴으로 허용한다.
          // v21.8.24.96: "함께 본 상품/추천/광고/베스트" 영역의 다른 제품 이미지가 섞이던 문제 수정.
          //   ① 상품 갤러리/상세 컨테이너를 먼저 스캔(추천 영역이 원천적으로 포함되지 않음)
          //   ② 부족하면 페이지 전체로 보강하되, 추천/광고 영역은 클래스 + 영역 제목 텍스트로 모두 배제
          images: (() => {
            const out = []; const seen = new Set();
            const isBad = (u) => /sprite|icon|logo|badge|avatar|profile|btn|button|banner|sns|facebook|kakao|emoji|blank|loading|spinner|qr|1x1|pixel|delivery|rocket|grade|star_|review|ad_|\/ads?\/|adimg|coupack|\.svg(\?|$)/i.test(u);
            const norm = (s) => String(s || '').split('?')[0];
            // 추천/함께 본 상품/광고/베스트/랭킹/비교/유사 영역 — 클래스 기준
            const BAD_CTX = 'nav,header,footer,aside,[class*="header"],[class*="footer"],[class*="gnb"],[class*="lnb"],[class*="banner"],[class*="recommend"],[class*="relate"],[class*="related"],[class*="viewtogether"],[class*="view-together"],[class*="together"],[class*="best"],[class*="rank"],[class*="compare"],[class*="comparison"],[class*="carousel"],[class*="product-ad"],[class*="adsense"],[class*="advertise"],[class*="promotion"],[class*="cross-sell"],[class*="similar"],[class*="popular"],[class*="reco"],[class*="md-"]';
            // 영역 제목 텍스트 기준(클래스명이 난독화된 동적 컴포넌트 대응)
            const BAD_TEXT = /함께\s*본|함께\s*둘러본|이\s*상품과\s*함께|추천\s*상품|관련\s*상품|다른\s*고객|비슷한\s*상품|이런\s*상품|광고|베스트|랭킹|순위|많이\s*본|인기\s*상품|함께\s*구매/;
            const SKIP_TAG = /^(BODY|MAIN|ARTICLE|HTML|FORM)$/;
            const inBad = (el) => {
              if (el.closest && el.closest(BAD_CTX)) return true;
              // 영역 '자기 제목'만 얕게(깊이≤2) 검사한다. body까지 올라가면 페이지 어딘가의 추천 제목이
              // 모든 이미지에 잘못 적용되므로, body/main/article 등 큰 래퍼는 건너뛴다.
              let sec = el.parentElement; let hops = 0;
              while (sec && hops < 4) {
                if (sec.tagName && !SKIP_TAG.test(sec.tagName) && sec.querySelectorAll) {
                  const heads = sec.querySelectorAll('h1,h2,h3,h4,strong,[class*="title"],[class*="Title"]');
                  for (const h of heads) {
                    let depth = 0, p = h;
                    while (p && p !== sec) { p = p.parentElement; depth++; }
                    if (depth > 2) continue; // 하위 다른 섹션의 제목이 새지 않게
                    const ht = String(h.innerText || h.textContent || '').replace(/\s+/g, ' ').trim();
                    if (ht && ht.length < 40 && BAD_TEXT.test(ht)) return true;
                  }
                }
                sec = sec.parentElement; hops++;
              }
              return false;
            };
            const pushU = (u, hasSize, sizeOk) => {
              if (!u) return;
              u = String(u).trim().split(/\s+/)[0]; // srcset 첫 URL
              if (u.indexOf('//') === 0) u = 'https:' + u;
              if (!/^https?:\/\//.test(u) || isBad(u)) return;
              if (hasSize && !sizeOk) return;            // 크기 정보가 있으면 작은 건 제외
              const key = norm(u);
              if (seen.has(key)) return; seen.add(key);
              out.push(u);
            };
            const collectFrom = (els) => {
              els.forEach(el => {
                if (inBad(el)) return;
                const nw = el.naturalWidth || 0;
                const hasSize = nw > 0;
                const sizeOk = nw >= 200;
                // 1) 실제 표시 src (크기 정보 있으면 200 이상만)
                pushU(el.currentSrc || el.getAttribute('src'), hasSize, sizeOk);
                // 2) 지연로딩 속성 (크기 미확정 → 패턴만 통과하면 허용)
                ['data-src', 'data-original', 'data-lazy', 'data-lazy-src', 'data-srcset', 'srcset'].forEach(attr => {
                  pushU(el.getAttribute && el.getAttribute(attr), false, true);
                });
              });
            };
            // ① 상품 갤러리/상세 컨테이너 우선 (이 영역엔 추천/함께 본 상품이 들어오지 않음)
            const GALLERY = '.prod-image,.prod-image__items,[class*="prod-image"],[class*="ProductImage"],[class*="product-image"],[class*="image-gallery"],#productDetail,#product-detail,[id*="productDetail"],[class*="product-detail"],[class*="ProductDetail"],[class*="prod-detail"],.vendor-item,[class*="detail-content"]';
            const roots = [...document.querySelectorAll(GALLERY)].filter(r => !inBad(r));
            roots.forEach(root => collectFrom([...root.querySelectorAll('img, source')]));
            // ② 갤러리에서 충분히 못 모았으면 페이지 전체로 보강(추천/광고 영역 제외는 유지)
            if (out.length < 3) collectFrom([...document.querySelectorAll('img, source')]);
            return out.slice(0, 15);
          })()
        };
      }
    });

    const page = injected?.[0]?.result || {};
    const html = String(page.html || '');
    if (!html || html.length < 500) return { ok: false, error: '탭에서 상품 HTML을 충분히 읽지 못했습니다.' };

    const parsed = DPLinkParser.parseProductMeta(html, page.url || url);
    if (!parsed.title && page.title) parsed.title = String(page.title).trim();
    if (!parsed.source) parsed.source = DPLinkParser.detectSource(page.url || url);
    if (!parsed.image && page.heroImage) parsed.image = page.heroImage;
    // v21.8.24.26: 갤러리 이미지 여러 장 병합(파서가 찾은 메타 이미지 + 페이지에서 수집한 이미지)
    {
      const merged = [];
      const pushUniq = (u) => { const v = String(u || '').trim(); if (v && !merged.includes(v)) merged.push(v); };
      (parsed.images || []).forEach(pushUniq);
      if (parsed.image) pushUniq(parsed.image);
      (page.images || []).forEach(pushUniq);
      parsed.images = merged.slice(0, 12);
      if (!parsed.image && parsed.images[0]) parsed.image = parsed.images[0];
    }

    const observedSpecs = [];
    (page.optionGroups || []).forEach(group => {
      const values = Array.isArray(group?.values) ? group.values.filter(Boolean).join(', ') : '';
      if (values) observedSpecs.push(`${group.name || '옵션'}: ${values}`);
    });
    (page.details || []).forEach(line => {
      if (line && !observedSpecs.includes(line)) observedSpecs.push(line);
    });
    // v21.8.24.8: 확인 필요 항목은 스펙 줄로 직접 넣지 않고 collectionStatus/factSummary의 미확정 정보로만 표시한다.
    if (page.reviewSummary?.length) observedSpecs.push(`리뷰/구매 요약: ${page.reviewSummary.join(' / ')}`);
    if (page.detailImageCount) observedSpecs.push(`상세 이미지 후보: ${page.detailImageCount}장 감지`);

    parsed.specs = mergeSpecBlocks(existingData?.specs || parsed.specs || '', observedSpecs.join('\n'));
    // v21.8.24.3: 쿠팡 메타 설명은 리뷰/추천 광고 문구가 섞일 수 있어 제품진단에는 쓰지 않는다.
    parsed.description = sanitizeProductDescription(pickBetterDescription(existingData?.description || '', parsed.description || ''));
    parsed.price = parsed.price || pickDigits((page.priceCandidates || [])[0] || '');
    parsed.collectionStatus = buildCollectionStatus(parsed.specs || '', parsed.description || '', page.reviewSummary || []);
    parsed.factSummary = buildFactSummary(parsed, page);
    parsed.pageObservation = {
      optionGroups: page.optionGroups || [],
      detailsCount: (page.details || []).length,
      reviewSummary: page.reviewSummary || [],
      imageCount: page.imageCount || 0,
      detailImageCount: page.detailImageCount || 0,
      unknownFields: page.unknownFields || []
    };

    if (!parsed.title && !parsed.image && !parsed.price) {
      // v21.8.24.96: 봇차단/보안확인 페이지인지 구분해 사용자가 바로 조치할 수 있게 안내한다.
      const bt = String(page.bodyText || '') + ' ' + String(page.title || '');
      const blocked = /Access\s*Denied|Pardon\s*the\s*interruption|보안\s*문자|로봇이\s*아닙니다|자동\s*입력\s*방지|비정상적인\s*접근|일시적으로\s*차단|접근이\s*제한|캡차|captcha|cloudflare|를\s*확인하고\s*있습니다/i.test(bt);
      if (blocked) {
        return { ok: false, blocked: true, error: '쿠팡이 봇차단(보안 확인) 페이지를 띄웠습니다. 브라우저에서 쿠팡에 한 번 접속/로그인한 뒤 다시 시도하거나, 이미지 첨부 + 상품명 직접 입력으로 진행하세요.' };
      }
      return { ok: false, error: '탭 분석에서도 상품명/이미지/가격을 찾지 못했습니다.' };
    }
    return { ok: true, data: parsed, finalUrl: page.url || url };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  } finally {
    if (tabId) {
      try { await chrome.tabs.remove(tabId); } catch (_) {}
      try { DP_TEMP_PRODUCT_TABS.delete(tabId); } catch (_) {}
    }
  }
}

async function closeTemporaryProductTabs() {
  const ids = Array.from(DP_TEMP_PRODUCT_TABS);
  DP_TEMP_PRODUCT_TABS.clear();
  await Promise.all(ids.map(async id => {
    try { await chrome.tabs.remove(id); } catch (_) {}
  }));
}


function withTimeout(promise, ms, fallback) {
  let timer = null;
  return Promise.race([
    promise,
    new Promise(resolve => {
      timer = setTimeout(() => resolve(fallback), ms);
    })
  ]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

function ensureFallbackFactData(data = {}) {
  const safe = { ...data };
  safe.collectionStatus = safe.collectionStatus || {
    confirmed: ['상품명', '가격', '플랫폼'].filter(k => {
      if (k === '상품명') return !!safe.title;
      if (k === '가격') return !!safe.price;
      if (k === '플랫폼') return !!safe.source;
      return true;
    }),
    missing: ['옵션/사이즈', '소재', '정확한 구성 수량', '리뷰/별점', '상세 설명', '제조국', '세탁방법/취급주의']
  };
  if (!safe.factSummary) {
    const lines = [];
    if (safe.title) lines.push(`상품명: ${safe.title}`);
    if (safe.source) lines.push(`판매 플랫폼: ${safe.source}`);
    if (safe.price) lines.push(`가격: ${DPLinkParser.formatPriceLabel ? DPLinkParser.formatPriceLabel(safe.price) : safe.price}`);
    lines.push('[미확정 정보] 옵션/사이즈, 소재, 정확한 구성 수량, 제조국, 세탁방법/취급주의');
    safe.factSummary = lines.join('\n');
  }
  return safe;
}

function shouldTryPageObservation(url, data) {
  const source = String(data?.source || DPLinkParser.detectSource(url) || '');
  return /쿠팡|스마트스토어|도매꾹|와디즈|11번가|G마켓|옥션|SSG|1688|타오바오|티몰|알리익스프레스|알리바바|VVIC|아마존재팬|라쿠텐/.test(source);
}


function normalizeSizeTokenForSpec(txt = '') {
  const t = String(txt || '').replace(/\s+/g, ' ').trim().toUpperCase().replace(/XXL/g, '2XL').replace(/ONE SIZE/g, 'FREE').replace(/프리/g, 'FREE');
  if (/^(XS|S|M|L|XL|2XL|3XL|4XL|5XL|FREE|44|55|66|77|88|90|95|100|105|110)$/.test(t)) return t;
  return '';
}

function extractSizeValuesFromSpec(txt = '') {
  const out = [];
  String(txt || '').replace(/XXL/gi, '2XL').split(/\n|\r|,|\/|\||·|ㆍ|\s+/).forEach(part => {
    const token = normalizeSizeTokenForSpec(part);
    if (token && !out.includes(token)) out.push(token);
  });
  return out;
}

function isPriceLikeSpec(txt = '') {
  return /\d[\d,]{2,}\s*원|할인|판매자로켓|로켓배송|무료배송|도착\s*보장|내일|오늘|배송/i.test(String(txt || ''));
}

function isPolicySpecText(txt = '') {
  return /의류\/잡화\/수입명품|계절상품\/식품\/화장품|CD\s*\/\s*DVD\s*\/\s*GAME\s*\/\s*BOOK|복제가\s*가능한\s*상품|포장\s*등을\s*훼손|반품|교환|환불|취소|택\(TAG\)|라벨의\s*멸실|상품의\s*사용|상품의\s*훼손|구성품\s*누락|알러지|붉은\s*반점|가려움|따가움|단순변심|상호\s*\/\s*대표자|대표자|e-?mail|이메일|구매안전\s*서비스|서비스\s*가입사실|본\s*판매자는\s*고객님의\s*안전거래|통신판매업|사업자등록번호|판매자\s*정보|고객센터|전자상거래|소비자\s*보호/i.test(String(txt || ''));
}

function sanitizeProductDescription(desc = '') {
  const d = String(desc || '').replace(/\s+/g, ' ').trim();
  if (!d) return '';
  if (/현재\s*별점|리뷰\s*[0-9,]+개|더\s*저렴하고\s*다양한|제품들을\s*확인|추천|광고|쿠팡에서/i.test(d)) return '';
  if (isPolicySpecText(d)) return '';
  return d.length > 220 ? d.slice(0, 220) : d;
}

function isUnknownSpecValue(line = '') {
  const value = String(line || '').split(/[:：]/).slice(1).join(':').trim();
  return /상품\s*상세|상세페이지\s*참조|판매자\s*문의|업체\s*제공|확인\s*필요|미확인|참조|별도표기/i.test(value);
}

function isConfirmedMaterialLine(line = '') {
  const m = String(line || '').replace(/\s+/g, ' ').trim().match(/^(제품\s*소재|소재|재질|겉감|안감|혼용률)\s*[:：]\s*(.{1,120})$/i);
  if (!m) return false;
  const value = m[2].trim();
  if (!value || isUnknownSpecValue(`${m[1]}: ${value}`) || isPolicySpecText(value) || isPriceLikeSpec(value)) return false;
  // 실제 소재명으로 볼 수 있는 표현만 확정 처리. "상품 상세페이지 참조"나 정책 문구는 소재 확정으로 승격하지 않는다.
  return /폴리|폴리에스터|폴리우레탄|스판|스판덱스|나일론|면|코튼|레이온|아크릴|울|모|마|린넨|실리콘|고무|합성섬유|엘라스틴|nylon|poly|cotton|span|spandex|rayon|acrylic|linen/i.test(value);
}

function isNoiseSpecLine(line = '') {
  const t = String(line || '').replace(/\s+/g, ' ').trim();
  if (!t) return true;
  if (/component\s*=|component\s*:/i.test(t)) return true;
  if (isPolicySpecText(t)) return true;
  if (/전체\/패션의류|패션의류 잡화|뷰티\/출산|주방용품|생활용품|홈인테리어|가전디지털|도서 음반 DVD|자동차용품/.test(t)) return true;
  if (/추천상품|함께 본 상품|다른 고객|광고|랭킹|카테고리|쿠팡홈|장바구니|바로구매/i.test(t)) return true;
  if (/^사이즈\s*[:：]/.test(t) && isPriceLikeSpec(t) && !extractSizeValuesFromSpec(t.split(/[:：]/).slice(1).join(':')).length) return true;
  if (/^사이즈\s*[:：]\s*\d[\d,]*(?:원)?/i.test(t)) return true;
  if (/배송방법|묶음배송|교환|반품|환불|취소|상호\s*\/\s*대표자|e-?mail|이메일|구매안전\s*서비스|사업자등록번호|통신판매업|CD\s*\/\s*DVD\s*\/\s*GAME\s*\/\s*BOOK/.test(t)) return true;
  if (/(래쉬가드|레쉬가드|수영복|여성용|남성용).*,/.test(t) && !/상품명|품명/.test(t)) return true;
  if (/자외선|UV|속건|냉감|고탄력|방수|발수/i.test(t) && !/확인 필요|상품정보|필수|고시|상세/i.test(t)) return true;
  // v21.8.24.23: 도매꾹 등에서 실측된 UI/광고/도망값 잡음 제거
  if (/흥정하기|최소구매수량|총\s*상품금액|쿠폰적용|관심상품|파트너프로그램|공유하기|렌즈\s*검색|신규가입|혜정하기|미술도구|수납용품|로켓그로스|사회공헌/.test(t)) return true;
  if (/별도표기/.test(t)) return true;                                  // "상세정보 별도표기" 류 도망값
  if (/^(품명|모델명|품명\s*및\s*모델명)\s*[:：]\s*(상품명|상세정보|별도표기)/.test(t)) return true; // 라벨=값 오인
  if (/^수량\s*[:：]\s*(0\s*개|단가|\(?개\)?|\d{1,2}\s*개)?\s*$/.test(t)) return true; // 의미 없는 수량
  if (/^수량\s*[:：]\s*단가/.test(t)) return true;
  if (/^무게\s*[:：]\s*[\dxX]+\s*[\/xX]\s*[\d.]+\s*$/.test(t)) return true; // 포장 치수 잡음(20x40 / 0.2)
  if (/^총\s*상품금액|^공급사명\s*[:：]/.test(t)) return true;
  // v21.8.24.25: 도매꾹 등에서 실측된 연락처/사업자/주문 UI 잡음 제거
  if (/consumer_mobile|^mobile|tel\b|phone|휴대전화|전화번호|문의번호|연락처|고객센터|^010[\d ,]/i.test(t)) return true;
  if (/사업자구분|사업장소재지|사업자등록|통신판매|대표자|판매자명|공급사명|간이과세|일반과세/.test(t)) return true;
  if (/수령지|배송지|주소직접입력|주소록|품절확인|이미지무료다운로드|추가\s*이미지|관심상품등록|장바구니|바로구매|찜하기/.test(t)) return true;
  if (/[:：]\s*(내용없음|없음|-|없슴)\s*$/.test(t)) return true;          // 빈 값
  if (/^무게\s*[:：]\s*\/?\s*$/.test(t)) return true;                       // "무게: /" 빈값
  return false;
}


function normalizeSpecLine(line = '') {
  const cleaned = String(line || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return '';
  const m = cleaned.match(/^([^:：]{1,28})[:：]\s*(.{1,160})$/);
  if (!m) return cleaned;
  const key = m[1].trim();
  let value = m[2].trim();
  if (isPolicySpecText(`${key}: ${value}`)) return '';
  if (/^(상호\s*\/\s*대표자|상호|대표자|e-?mail|이메일|구매안전\s*서비스|통신판매업|사업자등록번호|판매자\s*정보|CD\s*\/\s*DVD\s*\/\s*GAME\s*\/\s*BOOK)$/i.test(key)) return '';
  // v21.8.24.23: 값이 라벨명("상품명")이거나 도망 문구면 버림
  if (/^(상품명|상세정보|별도표기|단가)$/.test(value)) return '';
  // 원산지/제조국 값의 구분자(_)를 표준화해 중복 라인 통합
  if (/원산지|제조국/.test(key)) value = value.replace(/_/g, ' / ').replace(/\s*\/\s*/g, ' / ').trim();
  // 색상/컬러는 실제 색상명만 인정(예: "컬러: 미술도구수납용품" 제거)
  if (/^(색상|컬러)$/.test(key) && !/블랙|화이트|아이보리|베이지|네이비|핑크|레드|옐로|오렌지|그린|블루|그레이|카키|브라운|퍼플|검정|흰색|그레이|회색|남색|연두|민트|와인|버건디|골드|실버/.test(value)) return '';
  if (/색상계열/.test(key) && /블랙/.test(value)) return '색상계열: 블랙계열';
  if (/현재 선택된 사이즈|사이즈 옵션 후보|^사이즈$/.test(key)) {
    const sizes = extractSizeValuesFromSpec(value);
    if (!sizes.length) return '';
    if (/현재 선택된 사이즈/.test(key) || /^사이즈$/.test(key)) return `현재 선택된 사이즈: ${sizes[0]}`;
    return `사이즈 옵션 후보: ${sizes.join(', ')}`;
  }
  if (isPolicySpecText(`${key}: ${value}`)) return '';
  if (isPriceLikeSpec(value) && !/가격|판매가/.test(key)) return '';
  return `${key}: ${value}`;
}


function mergeSpecBlocks(a = '', b = '') {
  const lines = [];
  const seen = new Set();
  String(a || '').split(/\n+/).concat(String(b || '').split(/\n+/)).forEach(line => {
    const cleaned = normalizeSpecLine(line);
    if (!cleaned || isNoiseSpecLine(cleaned) || seen.has(cleaned)) return;
    seen.add(cleaned);
    lines.push(cleaned);
  });

  const currentSizes = new Set();
  lines.forEach(line => {
    if (/^현재 선택된 사이즈\s*[:：]/.test(line)) {
      extractSizeValuesFromSpec(line.split(/[:：]/).slice(1).join(':')).forEach(v => currentSizes.add(v));
    }
  });
  const normalizedLines = lines.map(line => {
    if (/^사이즈 옵션 후보\s*[:：]/.test(line) && currentSizes.size) {
      const values = extractSizeValuesFromSpec(line.split(/[:：]/).slice(1).join(':')).filter(v => !currentSizes.has(v));
      return values.length ? `사이즈 옵션 후보: ${values.join(', ')}` : '';
    }
    return line;
  }).filter(Boolean);

  return normalizedLines.slice(0, 28).join('\n');
}


function pickBetterDescription(existing = '', parsed = '', body = '') {
  const candidates = [existing, parsed, body].map(v => String(v || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
  return candidates.sort((a, b) => b.length - a.length)[0] || '';
}

function pickDigits(text = '') {
  const digits = String(text || '').replace(/[^\d]/g, '');
  return digits || '';
}

function buildCollectionStatus(specs = '', description = '', reviewSummary = []) {
  const lines = String(specs || '').split(/\n+/).map(normalizeSpecLine).filter(Boolean).filter(line => !isNoiseSpecLine(line));
  const hasConfirmedLine = (re) => lines.some(line => re.test(line) && !isUnknownSpecValue(line));
  const hasUnknownLine = (re) => lines.some(line => re.test(line) && isUnknownSpecValue(line));
  const confirmed = ['상품명', '가격', '플랫폼'];
  const missing = [];

  if (hasConfirmedLine(/현재 선택된 사이즈|사이즈 옵션 후보|현재 선택된 색상|색상 옵션 후보|색상계열|색상|컬러/i)) confirmed.push('옵션/사이즈');
  else missing.push('옵션/사이즈');

  if (lines.some(isConfirmedMaterialLine)) confirmed.push('소재');
  else missing.push('소재');

  if (hasConfirmedLine(/^구성품|^구성 내용|^수량|^개수/i)) confirmed.push('구성');
  else missing.push('정확한 구성 수량');

  // 쿠팡 메타/본문에서 별점·리뷰가 광고문구로 섞이는 경우가 많아 상세페이지 카피 기준으로는 기본 미확정 처리한다.
  missing.push('리뷰/별점');

  if (sanitizeProductDescription(description).length > 40) confirmed.push('상세 설명');
  else missing.push('상세 설명');

  if (hasUnknownLine(/제조국|원산지/i) || !hasConfirmedLine(/제조국|원산지/i)) missing.push('제조국');
  if (hasUnknownLine(/세탁|취급주의/i) || !hasConfirmedLine(/세탁|취급주의/i)) missing.push('세탁방법/취급주의');
  return { confirmed: [...new Set(confirmed)], missing: [...new Set(missing)] };
}


function buildFactSummary(parsed = {}, page = {}) {
  const lines = [];
  if (parsed.title) lines.push(`상품명: ${parsed.title}`);
  if (parsed.source) lines.push(`판매 플랫폼: ${parsed.source}`);
  if (parsed.price) lines.push(`가격: ${DPLinkParser.formatPriceLabel ? DPLinkParser.formatPriceLabel(parsed.price) : parsed.price}`);
  String(parsed.specs || '').split(/\n+/).forEach(line => {
    const cleaned = normalizeSpecLine(line);
    if (!cleaned || isNoiseSpecLine(cleaned) || isUnknownSpecValue(cleaned)) return;
    if (/상세 이미지 후보|리뷰\/구매 요약/.test(cleaned)) return;
    lines.push(cleaned);
  });
  const missing = parsed.collectionStatus?.missing || [];
  if (missing.length) lines.push(`[미확정 정보] ${missing.join(', ')}`);
  return lines.slice(0, 24).join('\n');
}

function mergeProductData(base = {}, observed = {}) {
  return {
    ...base,
    ...observed,
    title: observed.title || base.title || '',
    image: observed.image || base.image || '',
    images: (() => { const m = []; const p = (u) => { const v = String(u || '').trim(); if (v && !m.includes(v)) m.push(v); }; (base.images || []).forEach(p); (observed.images || []).forEach(p); return m.slice(0, 12); })(),
    price: observed.price || base.price || '',
    source: observed.source || base.source || '',
    description: pickBetterDescription(base.description || '', observed.description || ''),
    specs: mergeSpecBlocks(base.specs || '', observed.specs || ''),
    collectionStatus: observed.collectionStatus || base.collectionStatus || null,
    factSummary: observed.factSummary || base.factSummary || '',
    pageObservation: observed.pageObservation || base.pageObservation || null
  };
}

function waitForTabComplete(tabId, timeout = 15000) {
  return new Promise((resolve) => {
    const started = Date.now();
    const done = () => {
      try { chrome.tabs.onUpdated.removeListener(listener); } catch (_) {}
      resolve();
    };
    const timer = setInterval(() => {
      if (Date.now() - started > timeout) {
        clearInterval(timer);
        done();
      }
    }, 500);
    const listener = (id, info) => {
      if (id === tabId && info.status === 'complete') {
        clearInterval(timer);
        done();
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
