// v21.8.24.51: 프롬프트 스타일 '템플릿' 저장/불러오기/삭제 (추가 기능 — 입력값 저장/복원만).
// 기존 프롬프트 생성(prompt_short_dynamic.js)·이미지 생성/완료감지(content.js) 로직과 완전히 무관.
// 별도 storage 키를 사용하며, 기존 설정 저장(STORE_KEY)에는 손대지 않는다.
(function () {
  'use strict';

  const TEMPLATE_STORE_KEY = 'dp_director_templates_v1';
  const SECTION_ID = 'dp-template-section';
  const MOUNT_POLL_INTERVAL_MS = 1000;
  const MOUNT_DEBOUNCE_MS = 300;

  // 저장 대상: '재사용 가능한 스타일 설정'만. 상품명/링크/스펙 등 상품별 정보는 절대 포함하지 않는다.
  const STYLE_SELECT_FIELDS = [
    { key: 'mood', elId: 'dp-mood' },
    { key: 'tone', elId: 'dp-tone' },
    { key: 'sections', elId: 'dp-sections' },
    { key: 'platform', elId: 'dp-platform' },
    { key: 'ratio', elId: 'dp-ratio' },
    { key: 'quality', elId: 'dp-quality' }
  ];

  // ===== storage 계층 (별도 키) =====
  function loadStore() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get([TEMPLATE_STORE_KEY], (r) => {
          const raw = r && r[TEMPLATE_STORE_KEY];
          resolve(raw && Array.isArray(raw.templates) ? raw.templates : []);
        });
      } catch (_) { resolve([]); }
    });
  }
  function saveStore(templates) {
    return new Promise((resolve) => {
      try { chrome.storage.local.set({ [TEMPLATE_STORE_KEY]: { templates } }, () => resolve(true)); }
      catch (_) { resolve(false); }
    });
  }

  // ===== 현재 스타일 읽기 / 적용 =====
  function readCurrentStyle() {
    const style = {};
    STYLE_SELECT_FIELDS.forEach((f) => {
      const el = document.getElementById(f.elId);
      style[f.key] = el ? String(el.value || '') : '';
    });
    // refStyle: content.js가 노출한 안전 훅으로만 접근(없으면 빈 값)
    try {
      style.refStyle = (window.DP_REF_STYLE && typeof window.DP_REF_STYLE.get === 'function')
        ? String(window.DP_REF_STYLE.get() || '') : '';
    } catch (_) { style.refStyle = ''; }
    return style;
  }
  function applyStyle(template) {
    if (!template) return;
    STYLE_SELECT_FIELDS.forEach((f) => {
      const el = document.getElementById(f.elId);
      if (!el) return;
      const val = typeof template[f.key] === 'string' ? template[f.key] : '';
      if (!val) return; // 빈 값은 기존 설정을 덮어쓰지 않는다
      const optionExists = Array.from(el.options || []).some((o) => o.value === val) || el.value === val;
      if (!optionExists) return; // 해당 옵션이 없으면 무시(안전)
      el.value = val;
      el.dispatchEvent(new Event('change', { bubbles: true })); // 기존 onchange/save 자연 발동
    });
    if (typeof template.refStyle === 'string' && template.refStyle) {
      try {
        if (window.DP_REF_STYLE && typeof window.DP_REF_STYLE.set === 'function') {
          window.DP_REF_STYLE.set(template.refStyle);
        }
      } catch (_) { /* 훅 없으면 조용히 무시 */ }
    }
  }

  // ===== 데이터 API =====
  async function listTemplates() { return await loadStore(); }
  async function saveTemplate(name) {
    const trimmed = String(name || '').trim();
    if (!trimmed) return { ok: false, error: '템플릿 이름을 입력하세요.' };
    const templates = await loadStore();
    const entry = Object.assign({ name: trimmed }, readCurrentStyle(), { savedAt: Date.now() });
    const idx = templates.findIndex((t) => t && t.name === trimmed);
    const overwrite = idx >= 0;
    if (overwrite) templates[idx] = entry; else templates.push(entry);
    await saveStore(templates);
    return { ok: true, overwrite, count: templates.length };
  }
  async function getTemplate(name) {
    const templates = await loadStore();
    return templates.find((t) => t && t.name === String(name)) || null;
  }
  async function deleteTemplate(name) {
    const templates = await loadStore();
    const before = templates.length;
    const next = templates.filter((t) => t && t.name !== String(name));
    await saveStore(next);
    return { ok: true, removed: before - next.length };
  }

  window.DP_TEMPLATES = {
    listTemplates, saveTemplate, getTemplate, deleteTemplate,
    readCurrentStyle, applyStyle, STYLE_SELECT_FIELDS, TEMPLATE_STORE_KEY
  };

  // ===== UI =====
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }
  function logToPanel(msg) {
    try {
      const box = document.getElementById('dp-log');
      if (box) {
        const line = `[${new Date().toLocaleTimeString()}] ${msg}`;
        const prev = (box.textContent || '').split('\n').filter((l) => l && !l.startsWith('상품을 준비하고'));
        prev.push(line);
        box.textContent = prev.slice(-50).join('\n');
        box.scrollTop = box.scrollHeight;
        return;
      }
    } catch (_) { /* fall through */ }
    console.log('[DP_TEMPLATES]', msg);
  }

  function buildSectionHtml() {
    return `<div id="${SECTION_ID}" style="margin-top:14px">
      <label style="font-weight:bold">📁 템플릿 (스타일 설정 저장/불러오기)</label>
      <div class="dp-help" style="margin-top:2px">자주 쓰는 무드·톤·섹션 개수·플랫폼·비율(+레퍼런스 톤)을 이름으로 저장해, 다음 상품에서 골라 불러옵니다. (상품명·링크는 저장하지 않습니다)</div>
      <div class="dp-footer2" style="margin-top:6px">
        <input id="dp-template-name" type="text" placeholder="템플릿 이름 (예: 하이엔드 블랙)" style="flex:1;min-width:120px;padding:6px;border-radius:6px;border:1px solid #555;background:#222;color:#eee">
        <button class="dp-btn purple" id="dp-template-save">현재 스타일 저장</button>
      </div>
      <div class="dp-footer2" style="margin-top:6px">
        <select id="dp-template-list" style="flex:1;min-width:120px;padding:6px;border-radius:6px;border:1px solid #555;background:#222;color:#eee"><option value="">저장된 템플릿 선택…</option></select>
        <button class="dp-btn green" id="dp-template-load">불러오기</button>
        <button class="dp-btn danger" id="dp-template-delete">삭제</button>
      </div>
    </div>`;
  }

  async function refreshDropdown() {
    const sel = document.getElementById('dp-template-list');
    if (!sel) return;
    const current = sel.value;
    const templates = (await listTemplates()).slice().sort((a, b) => (b.savedAt || 0) - (a.savedAt || 0));
    sel.innerHTML = `<option value="">저장된 템플릿 선택…</option>` +
      templates.map((t) => `<option value="${esc(t.name)}">${esc(t.name)}</option>`).join('');
    if (current && Array.from(sel.options).some((o) => o.value === current)) sel.value = current;
  }

  function bindSection() {
    const nameInput = document.getElementById('dp-template-name');
    const listSel = document.getElementById('dp-template-list');
    const saveBtn = document.getElementById('dp-template-save');
    const loadBtn = document.getElementById('dp-template-load');
    const delBtn = document.getElementById('dp-template-delete');

    if (saveBtn) saveBtn.onclick = async () => {
      const result = await saveTemplate(nameInput ? nameInput.value : '');
      if (!result.ok) { logToPanel('⚠️ 템플릿 저장 실패: ' + (result.error || '')); return; }
      if (nameInput) nameInput.value = '';
      await refreshDropdown();
      logToPanel(`✅ 템플릿 저장 완료 (${result.overwrite ? '덮어쓰기' : '신규'}, 총 ${result.count}개)`);
    };
    if (loadBtn) loadBtn.onclick = async () => {
      const name = listSel ? listSel.value : '';
      if (!name) { logToPanel('⚠️ 불러올 템플릿을 선택하세요.'); return; }
      const template = await getTemplate(name);
      if (!template) { logToPanel('⚠️ 템플릿을 찾을 수 없습니다.'); return; }
      applyStyle(template);
      logToPanel(`✅ 템플릿 "${name}" 불러오기 완료. 이제 [프롬프트 생성]/[자동 생성]을 누르세요.`);
    };
    if (delBtn) delBtn.onclick = async () => {
      const name = listSel ? listSel.value : '';
      if (!name) { logToPanel('⚠️ 삭제할 템플릿을 선택하세요.'); return; }
      const result = await deleteTemplate(name);
      await refreshDropdown();
      logToPanel(result.removed ? `🗑 템플릿 "${name}" 삭제 완료.` : '⚠️ 삭제할 항목이 없습니다.');
    };
  }

  // 고급 영역(#dp-advanced)의 '레퍼런스 학습' 섹션 바로 위에 삽입(없으면 맨 앞).
  function findReferenceBlock(advanced) {
    let found = null;
    advanced.querySelectorAll('div').forEach((d) => {
      if (found) return;
      if (d.parentNode !== advanced) return;
      const label = d.querySelector(':scope > label');
      if (label && /레퍼런스 학습/.test(label.textContent || '')) found = d;
    });
    return found;
  }
  function mountIfReady() {
    const advanced = document.getElementById('dp-advanced');
    if (!advanced) return false;
    if (document.getElementById(SECTION_ID)) return true; // 이미 마운트됨
    const wrapper = document.createElement('div');
    wrapper.innerHTML = buildSectionHtml();
    const node = wrapper.firstElementChild;
    const refBlock = findReferenceBlock(advanced);
    if (refBlock) advanced.insertBefore(node, refBlock);
    else advanced.insertBefore(node, advanced.firstChild);
    bindSection();
    refreshDropdown();
    return true;
  }

  let mountScheduled = false;
  function scheduleMount() {
    if (mountScheduled) return;
    mountScheduled = true;
    setTimeout(() => { mountScheduled = false; mountIfReady(); }, MOUNT_DEBOUNCE_MS);
  }
  function init() {
    mountIfReady(); // 패널이 이미 있으면 즉시 마운트
    // ⚠️ 패널은 [접기] 시 DOM에서 제거되고 다시 열면 재생성된다(content.js collapse/injectPanel).
    // 따라서 관찰자를 끊지 않고 유지해, 패널이 새로 그려질 때마다 템플릿 섹션을 다시 붙인다.
    try {
      const observer = new MutationObserver(scheduleMount);
      observer.observe(document.documentElement, { childList: true, subtree: true });
    } catch (_) { /* 관찰 불가 시 폴링만 사용 */ }
    // 안전 폴백: 가벼운 주기 점검(섹션이 있으면 즉시 반환). 패널 재생성도 1초 내 복구.
    setInterval(mountIfReady, MOUNT_POLL_INTERVAL_MS);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
