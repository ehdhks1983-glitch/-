// fix_panel.js — v21.8.24.57
// '증상 기반 고치기' 패널: 초보자가 쉬운 말로 '뭐가 문제인지'만 고르면,
// 봇이 뒤에서 기존 고급 기능/생성 함수를 호출해 재생성한다.
// 설계 원칙:
//  - 생성/완료감지 엔진은 새로 만들지 않는다. content.js가 노출한 window.DP_FIX_HOOKS(기존 함수 참조)만 호출.
//  - 증상→동작 매핑, 무드 선택지는 아래 CONFIG 한 곳에서만 관리(하드코딩 흩뿌림 금지).
(function () {
  'use strict';

  // ===== 상수(매직넘버/문자열 금지: 의미 있는 이름으로 관리) =====
  const CONTAINER_ID = 'dp-fixpanel';
  const FIX_BTN_CLASS = 'dp-fix-btn';
  const MOUNTED_MARK = 'data-fix';      // 마운트 완료 표식(중복 렌더 방지)
  const MOUNT_POLL_INTERVAL_MS = 1000;  // 패널 재생성 대비 가벼운 주기 점검
  const COMPARE_SECTION_RE = /COMPARISON|BEFORE_AFTER/i;

  // 증상1: buildCopyPlan에 넘기는 '강한 pain-point 톤' 방향(랜덤 재생성이 아니라 방향을 강제)
  const STRONG_PAIN_DIRECTIVE =
    '카피를 지금보다 확실히 더 강하게: 각 섹션 메인 문구는 고객이 실제로 겪는 불편·손해·답답함(pain point)을 먼저 정면으로 콕 찌르는 공감형으로 시작하고, ' +
    '그 다음에 해결을 약속하는 구조로. 밋밋한 설명·기능 나열 금지, 소비자가 실제 쓰는 말로 더 구체적이고 감정이 실리게. 단, 과장·허위·미확인 수치는 금지.';

  // ===== CONFIG: 증상 → 동작 매핑(한 곳 관리) =====
  // kind: 'global'(전체 재생성) | 'mood'(무드 고르고 전체 재생성) | 'info'(정보 수정) | 'dedupe'(중복정리+해당 섹션) | 'pick'(섹션 골라 1개)
  const FIX_SYMPTOMS = [
    { id: 'copy',       label: '카피가 밋밋해요',     hint: '더 강한 고민·공감(pain) 톤으로 카피를 다시 기획 → 전체 재생성', kind: 'global', action: 'copyStrengthen' },
    { id: 'similar',    label: '이미지가 다 비슷해요', hint: '섹션마다 다른 구도로 다시 배치 → 전체 재생성',                 kind: 'global', action: 'diversify' },
    { id: 'mood',       label: '색·분위기가 안 맞아요', hint: '원하는 무드를 고르면 그 톤으로 전체 재생성',                  kind: 'mood' },
    { id: 'info',       label: '제품 정보가 틀려요',   hint: '세부 정보를 열어 직접 고치거나, 제품 진단을 다시 실행',        kind: 'info' },
    { id: 'dupcompare', label: '비교가 두 번 나와요',  hint: '중복된 비교 섹션을 1개로 정리 → 그 섹션만 다시 생성',          kind: 'dedupe' },
    { id: 'onecut',     label: '이 컷만 별로예요',     hint: '고칠 섹션을 골라 그 하나만 다시 생성',                        kind: 'pick' }
  ];

  // ===== CONFIG: 무드 선택지(기존 dp-mood value에 매핑) =====
  const MOOD_CHOICES = [
    { value: 'clean_white',    label: '크림·화이트 (밝고 깔끔)' },
    { value: 'dark_premium',   label: '다크 프리미엄 (고급·강렬)' },
    { value: 'soft_neutral',   label: '감성 뉴트럴 (부드러운)' },
    { value: 'tech_dashboard', label: '테크 (정보·기능형)' },
    { value: 'vivid_pop',      label: '비비드 팝 (쨍한 컬러)' },
    { value: 'warm_natural',   label: '웜 내추럴 (따뜻한)' }
  ];

  function hooks() { return window.DP_FIX_HOOKS || null; }
  function log(msg) { const h = hooks(); if (h && h.log) h.log(msg); else console.log('[fix]', msg); }

  // 패널 내 버튼 전부 비활성/활성 (중복 실행 방지)
  function setFixBusy(busy) {
    const root = document.getElementById(CONTAINER_ID);
    if (!root) return;
    root.querySelectorAll('.' + FIX_BTN_CLASS).forEach(function (b) { b.disabled = busy; });
  }

  function isBusy() {
    const h = hooks(); if (!h) return true;
    const st = h.getState ? h.getState() : {};
    return !!(st.autoRunActive || st.regenBusy);
  }

  function hasPrompts() {
    const h = hooks(); if (!h || !h.getState) return false;
    const st = h.getState();
    return !!(st.shortImagePrompts && st.shortImagePrompts.length);
  }

  // ===== 공용 실행 래퍼 =====
  async function runGlobal(label, beforeFn) {
    const h = hooks(); if (!h) return;
    if (isBusy()) { log('⏳ 이미 생성/재생성이 진행 중입니다. 끝난 뒤 다시 시도하세요.'); return; }
    if (!hasPrompts()) { log('먼저 [✨ 상세페이지 자동 만들기]로 섹션을 생성하세요.'); return; }
    const st = h.getState();
    st.regenBusy = true; setFixBusy(true);
    try {
      log('🔧 ' + label);
      if (beforeFn) await beforeFn();
      await h.regenAll();
      log('🔧 완료: ' + label + ' (※ 완벽 강제가 아니라 방향 조정입니다. 결과가 아쉬우면 한 번 더 누르세요.)');
    } catch (e) {
      log('재생성 중 오류: ' + (e && e.message || e));
    } finally {
      st.regenBusy = false; setFixBusy(false);
    }
  }

  async function runSingle(idx) {
    const h = hooks(); if (!h) return;
    if (isBusy()) { log('⏳ 이미 생성/재생성이 진행 중입니다. 끝난 뒤 다시 시도하세요.'); return; }
    const st = h.getState();
    const ps = st.shortImagePrompts || [];
    if (!ps.length) { log('먼저 섹션을 생성하세요.'); return; }
    if (idx < 0 || idx >= ps.length) { log('섹션 번호가 올바르지 않습니다.'); return; }
    st.regenBusy = true; setFixBusy(true);
    try {
      log('🔧 ' + (idx + 1) + '번 "' + (ps[idx].title || '') + '" 섹션만 다시 생성 중…');
      const attached = await h.ensureImagesAttached();
      if (!attached) { log('⚠️ 이미지 첨부 확인 실패로 중단했습니다.'); return; }
      await h.tryOpenImageMode();
      await h.regenOneSection(idx);
      log('✅ ' + (idx + 1) + '번 섹션 재생성 요청 완료.');
    } catch (e) {
      log('단일 섹션 재생성 오류: ' + (e && e.message || e));
    } finally {
      st.regenBusy = false; setFixBusy(false);
    }
  }

  // ===== 증상별 동작 =====
  const ACTIONS = {
    copyStrengthen: function () {
      const h = hooks();
      return runGlobal('카피를 더 강한 고민·공감 톤으로 다시 기획 → 전체 재생성', async function () {
        log('②단계 카피 기획서를 더 강한 pain-point 방향으로 다시 만드는 중…');
        await h.rebuildCopyPlan(STRONG_PAIN_DIRECTIVE);
        h.rebuildPrompts(false);
      });
    },
    diversify: function () {
      const h = hooks();
      return runGlobal('섹션마다 다른 구도로 다시 배치 → 전체 재생성', async function () {
        // 프롬프트 재빌드 시 엔진이 구도(variation/shot)를 새로 회전시킨다.
        h.rebuildPrompts(false);
        log('구도를 새로 배치했습니다(섹션마다 다른 앵글·레이아웃).');
      });
    },
    mood: function (root) { toggleSub(root, 'mood'); },
    info: function (root) { toggleSub(root, 'info'); },
    dedupe: function () {
      const h = hooks();
      if (isBusy()) { log('⏳ 진행 중입니다. 끝난 뒤 다시 시도하세요.'); return; }
      if (!hasPrompts()) { log('먼저 섹션을 생성하세요.'); return; }
      const st = h.getState();
      const ps = st.shortImagePrompts || [];
      const compares = ps.map(function (p, i) { return { i: i, sec: String(p.section || '') }; })
                         .filter(function (o) { return COMPARE_SECTION_RE.test(o.sec); });
      if (compares.length <= 1) { log('🔧 중복된 비교 섹션이 없습니다. (정리할 것 없음)'); return; }
      const keep = compares[0].i;
      const removeIdx = compares.slice(1).map(function (o) { return o.i; }).sort(function (a, b) { return b - a; });
      removeIdx.forEach(function (i) {
        ps.splice(i, 1);
        if (Array.isArray(st.sectionStatus)) st.sectionStatus.splice(i, 1);
      });
      if (h.renderProgress) h.renderProgress();
      log('🔧 중복 비교 섹션 ' + removeIdx.length + '개를 목록에서 정리했습니다(1개만 유지). ' +
          '※ 이미 ChatGPT 대화에 올라간 중복 이미지는 자동으로 지울 수 없어요 — 화면에서 직접 삭제해 주세요.');
      // keep 인덱스는 제거 대상(모두 keep보다 뒤)보다 앞이라 그대로 유지됨.
      runSingle(keep);
    },
    pick: function (root) { toggleSub(root, 'pick'); },
    productReanalyze: function () {
      const h = hooks();
      return runGlobal('제품 진단(1단계)을 다시 실행 → 전체 재생성', async function () {
        log('①단계 제품 진단을 다시 실행하는 중…');
        await h.rebuildMasterBrief();
        h.rebuildPrompts(false);
      });
    },
    openDetails: function () {
      const h = hooks();
      h.openAdvanced();
      log('🔧 세부 정보(고급) 영역을 열었습니다. 카테고리·가격·타겟·스펙 등을 고친 뒤, ' +
          '"이미지가 다 비슷해요"나 "이 컷만 별로예요"로 재생성하거나 [✨ 자동 만들기]를 다시 누르세요.');
    }
  };

  // 서브 영역(무드 칩 / 섹션 선택 / 정보 수정) 토글
  function toggleSub(root, which) {
    ['mood', 'info', 'pick'].forEach(function (k) {
      const el = root.querySelector('[data-sub="' + k + '"]');
      if (el) el.style.display = (k === which && el.style.display !== 'block') ? 'block' : (k === which ? 'none' : 'none');
    });
    if (which === 'pick') refreshSectionPicker(root);
  }

  function refreshSectionPicker(root) {
    const sel = root.querySelector('#dp-fix-section-select');
    if (!sel) return;
    const h = hooks(); const st = h && h.getState ? h.getState() : {};
    const ps = (st.shortImagePrompts) || [];
    sel.innerHTML = ps.length
      ? ps.map(function (p, i) { return '<option value="' + i + '">' + (i + 1) + '. ' + escapeHtml(p.title || p.section || ('섹션 ' + (i + 1))) + '</option>'; }).join('')
      : '<option value="">아직 생성된 섹션이 없습니다</option>';
  }

  function escapeHtml(v) {
    return String(v).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[c];
    });
  }

  // ===== 렌더 =====
  function render(root) {
    const btnRows = FIX_SYMPTOMS.map(function (s) {
      return '<button type="button" class="dp-btn secondary ' + FIX_BTN_CLASS + '" data-sym="' + s.id + '" ' +
             'style="display:block;width:100%;text-align:left;margin:4px 0;white-space:normal;line-height:1.4">' +
             '<b>' + escapeHtml(s.label) + '</b><br><span style="font-size:11px;color:#9ca3af">' + escapeHtml(s.hint) + '</span>' +
             '</button>';
    }).join('');

    const moodChips = MOOD_CHOICES.map(function (m) {
      return '<button type="button" class="dp-btn purple ' + FIX_BTN_CLASS + '" data-mood="' + m.value + '" ' +
             'style="margin:3px">' + escapeHtml(m.label) + '</button>';
    }).join('');

    root.innerHTML =
      '<div class="dp-section">' +
        '<h3>🔧 맘에 안 드는 부분 고치기</h3>' +
        '<div class="dp-help">결과가 아쉬울 때, 어디가 문제인지만 고르면 알맞게 다시 만들어요. (전체 자동 생성이 끝난 뒤 사용)</div>' +
        '<div data-fix="buttons" style="margin-top:8px">' + btnRows + '</div>' +
        // 무드 선택 서브
        '<div data-sub="mood" style="display:none;margin-top:8px;padding:8px;border:1px solid #3f3f46;border-radius:8px">' +
          '<div style="font-size:12px;margin-bottom:4px">원하는 색·분위기를 고르세요 → 그 무드로 전체 재생성합니다.</div>' +
          '<div>' + moodChips + '</div>' +
        '</div>' +
        // 섹션 선택 서브
        '<div data-sub="pick" style="display:none;margin-top:8px;padding:8px;border:1px solid #3f3f46;border-radius:8px">' +
          '<div style="font-size:12px;margin-bottom:4px">고칠 섹션을 고르세요 → 그 한 컷만 다시 생성합니다.</div>' +
          '<select id="dp-fix-section-select" style="width:100%;padding:6px;border-radius:6px;border:1px solid #555;background:#222;color:#eee;font-size:12px"></select>' +
          '<div class="dp-footer2" style="margin-top:6px">' +
            '<button type="button" class="dp-btn green ' + FIX_BTN_CLASS + '" id="dp-fix-regen-one">이 섹션만 다시 생성</button>' +
          '</div>' +
        '</div>' +
        // 정보 수정 서브
        '<div data-sub="info" style="display:none;margin-top:8px;padding:8px;border:1px solid #3f3f46;border-radius:8px">' +
          '<div style="font-size:12px;margin-bottom:6px">제품 정보가 틀렸나요? 둘 중 하나를 고르세요.</div>' +
          '<div class="dp-footer2">' +
            '<button type="button" class="dp-btn secondary ' + FIX_BTN_CLASS + '" id="dp-fix-open-details">세부 정보 열어 직접 고치기</button>' +
            '<button type="button" class="dp-btn purple ' + FIX_BTN_CLASS + '" id="dp-fix-reanalyze">제품 진단 다시 실행 → 재생성</button>' +
          '</div>' +
        '</div>' +
      '</div>';

    bindEvents(root);
  }

  function bindEvents(root) {
    // 증상 버튼
    root.querySelectorAll('[data-sym]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const sym = FIX_SYMPTOMS.find(function (s) { return s.id === btn.getAttribute('data-sym'); });
        if (!sym) return;
        if (sym.kind === 'global') {
          if (sym.action === 'copyStrengthen') ACTIONS.copyStrengthen();
          else if (sym.action === 'diversify') ACTIONS.diversify();
        } else if (sym.kind === 'mood') ACTIONS.mood(root);
        else if (sym.kind === 'info') ACTIONS.info(root);
        else if (sym.kind === 'dedupe') ACTIONS.dedupe();
        else if (sym.kind === 'pick') ACTIONS.pick(root);
      });
    });
    // 무드 칩
    root.querySelectorAll('[data-mood]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        const v = chip.getAttribute('data-mood');
        const m = MOOD_CHOICES.find(function (x) { return x.value === v; });
        runGlobal('"' + (m ? m.label : v) + '" 무드로 전체 재생성', async function () {
          const h = hooks(); h.setMood(v); h.rebuildPrompts(false);
          log('무드를 "' + (m ? m.label : v) + '"(으)로 바꿔 다시 배치했습니다.');
        });
      });
    });
    // 섹션 단일 재생성
    const one = root.querySelector('#dp-fix-regen-one');
    if (one) one.addEventListener('click', function () {
      const sel = root.querySelector('#dp-fix-section-select');
      const idx = sel && sel.value !== '' ? parseInt(sel.value, 10) : -1;
      runSingle(idx);
    });
    // 정보 수정
    const od = root.querySelector('#dp-fix-open-details');
    if (od) od.addEventListener('click', function () { ACTIONS.openDetails(); });
    const ra = root.querySelector('#dp-fix-reanalyze');
    if (ra) ra.addEventListener('click', function () { ACTIONS.productReanalyze(); });
  }

  // ===== 마운트(재주입 대비 idempotent) =====
  function mount() {
    const root = document.getElementById(CONTAINER_ID);
    if (!root) return false;                                   // 패널 아직 없음
    if (!window.DP_FIX_HOOKS) return false;                    // content.js 훅 준비 전
    if (root.querySelector('[' + MOUNTED_MARK + '="buttons"]')) return true; // 이미 마운트됨
    render(root);
    return true;
  }

  window.DP_FIX_PANEL = { mount: mount, CONFIG: { FIX_SYMPTOMS: FIX_SYMPTOMS, MOOD_CHOICES: MOOD_CHOICES } };

  // template_store.js와 동일한 견고한 부트스트랩:
  // 패널은 [접기] 시 제거되고 다시 열면 재생성되므로, 관찰자+폴링을 유지해 그때마다 다시 붙인다.
  function init() {
    try { mount(); } catch (_) {}
    try {
      const observer = new MutationObserver(function () { try { mount(); } catch (_) {} });
      observer.observe(document.documentElement, { childList: true, subtree: true });
    } catch (_) { /* 관찰 불가 시 폴링만 사용 */ }
    setInterval(function () { try { mount(); } catch (_) {} }, MOUNT_POLL_INTERVAL_MS);
  }
  // readyState에 의존하지 않는다: 즉시 mount 시도 + 관찰자 + 폴링이 준비되는 즉시 자동으로 붙인다.
  init();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
})();
