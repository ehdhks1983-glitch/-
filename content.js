(() => {
  if (window.__DP_DIRECTOR_V20_10__) { window.dispatchEvent(new CustomEvent('DP_TOGGLE_PANEL_LOCAL')); return; }
  window.__DP_DIRECTOR_V20_10__ = true;

  const STORE_KEY = 'dp_director_v20_10_data';
  const RESULT_KEY = 'dp_director_v20_10_last_result';
  const state = { images: [], isWide: false, lastResult: '', advancedOpen: false, inferred: null, shortImagePrompts: [], currentShortImageIndex: 0, chatFilesUploaded: false, attachmentVerified: false, masterBrief: '', copyPlan: '', refStyle: '', autoRunActive: false, autoRunStop: false, wizardActive: false, wizardPhase: 'idle', attachDebug: [], sectionStatus: [], lastProductSig: '', briefSig: '', planSig: '', collectedImages: [], autoQa: false, textOverlay: false, lastDesignLabel: '' };

  chrome.runtime?.onMessage?.addListener((msg) => { if (msg?.type === 'DP_TOGGLE_PANEL') togglePanel(); });
  window.addEventListener('DP_TOGGLE_PANEL_LOCAL', togglePanel);

  function $(id){ return document.getElementById(id); }
  function esc(v=''){ return String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
  // v21.8.24.39: 원문이 외국어(중국어/일본어/영어)인지 판별 → 한국어 번역·현지화 지시에 사용
  function looksForeign(t){
    t=String(t||'');
    if(/[぀-ヿ]/.test(t)) return true; // 일본어 히라가나/가타카나
    const cjk=(t.match(/[㐀-鿿]/g)||[]).length; // CJK 한자
    const han=(t.match(/[가-힣]/g)||[]).length;
    if(cjk>=2 && cjk>=han) return true; // 한자 우세(중국어)
    const latin=(t.match(/[A-Za-z]/g)||[]).length;
    if(latin>=25 && han<3) return true; // 영어 위주
    return false;
  }
  function foreignLocalizeBlock(product, specs){
    if(!looksForeign(`${product||''} ${specs||''}`)) return '';
    return `\n[현지화 필수 - 외국어 원문]\n원문 상품정보가 외국어(중국어/영어/일본어)입니다. 공식 제품명과 모든 카피를 자연스러운 한국어로 번역·현지화하세요. 직역·번역투·외국어 단어·중국어 흔적을 남기지 말고, 한국 고객이 쓰는 표현으로 바꾸세요.\n`;
  }
  function log(msg){
    const el=$('dp-log'); if(!el) return;
    const line = `[${new Date().toLocaleTimeString()}] ${msg}`;
    // v21.8.12: 누적 표시 (최근 50줄 유지). 이전엔 textContent로 덮어써서 마지막 1줄만 보였음.
    const prev = (el.textContent||'').split('\n').filter(l=>l && !l.startsWith('상품을 준비하고'));
    prev.push(line);
    const recent = prev.slice(-50);
    el.textContent = recent.join('\n');
    el.scrollTop = el.scrollHeight; // 자동 스크롤
    console.log('[DP]', line);  // 콘솔에도 동시 출력
  }
  function attachLog(msg){
    const line = `[${new Date().toLocaleTimeString()}] ${msg}`;
    state.attachDebug = [...(state.attachDebug||[]), line].slice(-80);
    const el = $('dp-attach-debug-log');
    if(el) el.textContent = state.attachDebug.join('\n') || '첨부 시도 전입니다.';
    console.log('[DP_ATTACH]', msg);
  }
  function clearAttachLog(){ state.attachDebug=[]; const el=$('dp-attach-debug-log'); if(el) el.textContent='첨부 로그를 지웠습니다.'; }
  async function copyAttachLog(){ try{ await navigator.clipboard.writeText((state.attachDebug||[]).join('\n')); log('첨부 디버그 로그를 복사했습니다.'); }catch(e){ log('첨부 로그 복사 실패: '+(e?.message||e)); } }
  function describeEl(el){ if(!el) return '없음'; const parts=[el.tagName?.toLowerCase()||'node']; if(el.id) parts.push('#'+el.id); const dt=el.getAttribute?.('data-testid'); if(dt) parts.push(`[data-testid="${dt}"]`); const al=el.getAttribute?.('aria-label'); if(al) parts.push(`[aria-label="${al.slice(0,40)}"]`); const ac=el.getAttribute?.('accept'); if(ac) parts.push(`[accept="${ac}"]`); return parts.join(''); }
  function setBusy(busy){ ['dp-auto','dp-generate','dp-insert','dp-copy','dp-sample','dp-clear','dp-infer','dp-extract-images','dp-make-image','dp-next-image','dp-upload-chatgpt','dp-check-attach','dp-fetch-link','dp-build-short-prompts','dp-make-short-image','dp-next-short-image','dp-build-brief','dp-save-brief','dp-clear-brief','dp-build-plan','dp-save-plan','dp-clear-plan','dp-build-ref','dp-save-ref','dp-clear-ref','dp-collect-images','dp-merge-jpg','dp-merge-pdf'].forEach(id=>{ const el=$(id); if(el) el.disabled=busy; }); }

  function injectPanel(){
    if ($('dp-director-panel')) return;
    const panel=document.createElement('div'); panel.id='dp-director-panel';
    panel.innerHTML=`
      <div class="dp-head">
        <div><div class="dp-title">AI 상세페이지 디렉터</div><div class="dp-sub">v21.8.24.103 · FAQ 전카테고리 수정</div></div>
        <div class="dp-head-actions"><button class="dp-btn danger" id="dp-clear" style="padding:5px 9px">🔄 전체 초기화</button><button class="dp-btn secondary" id="dp-save">저장</button><button class="dp-btn secondary" id="dp-close">접기</button></div>
      </div>
      <div class="dp-body">
        <!-- ===== 초보자 영역: 이것만 보면 됨 ===== -->
        <div class="dp-section">
          <h3>① 상품 준비</h3>
          <div class="dp-help">원본 상품 사진을 ChatGPT 입력창(+버튼)에 첨부하고, 아래에 상품명이나 링크를 넣으세요.</div>
          <div style="height:8px"></div>
          <div class="dp-grid">
            ${field('product','상품명','예: 디노트 저항밴드 / 홈엔모어 구두약')}
            ${field('link','상품 링크(선택)','쿠팡/스마트스토어/와디즈 링크')}
          </div>
          <div class="dp-field dp-full" style="margin-top:8px">
            <div style="display:flex;gap:8px;align-items:center">
              <button class="dp-btn purple" id="dp-fetch-link" type="button">🔗 링크에서 상품정보 자동 채우기</button>
              <span id="dp-fetch-status" class="dp-help" style="margin:0"></span>
            </div>
            <div id="dp-fetch-result" class="dp-output small" style="display:none;margin-top:8px"></div>
          </div>
          <div class="dp-field dp-full" style="margin-top:8px">
            <label>중요정보 직접 입력 / 스크린샷 기준 보정값 (선택 · 최우선 반영)</label>
            <textarea id="dp-manualFacts" rows="5" placeholder="예:&#10;색상 옵션: 화이트블랙&#10;현재 선택된 사이즈: 2XL&#10;사이즈 옵션 후보: M, L, XL&#10;소재: 확인 필요&#10;제조국: 확인 필요"></textarea>
            <div class="dp-help">쿠팡 옵션/스펙이 틀리면 여기에 직접 적어주세요. 이 값이 자동 크롤링보다 우선 적용됩니다.</div>
          </div>
          <div class="dp-field dp-full" style="margin-top:8px">
            <label>패널 미리보기용 이미지 (선택)</label>
            <input id="dp-image-files" type="file" accept="image/*" multiple>
            <div id="dp-upload-status" class="dp-help">선택하면 자동 제작 시 ChatGPT에 자동 첨부됩니다. 안 되면 ChatGPT +버튼으로 직접 첨부하세요.</div>
            <label style="display:block;margin-top:6px"><input type="checkbox" id="dp-images-attached"> ChatGPT에 원본 이미지를 이미 첨부했습니다</label>
          </div>
          <div id="dp-preview" class="dp-preview-list"></div>
        </div>

        <div class="dp-section">
          <h3>② 디자인 (선택)</h3>
          <div class="dp-help">그냥 두면 상품에 맞게 자동으로 정해집니다.</div>
          <div style="height:8px"></div>
          <div class="dp-grid">
            ${selectMood()}
            ${selectSections()}
          </div>
          <div style="margin-top:12px;padding:10px;border:1px solid #3f3f46;border-radius:8px">
            <label style="font-weight:bold;font-size:12px;color:#d4d4d8">🎨 카피할 디자인 (선택 · 퀄리티↑)</label>
            <div class="dp-help" style="margin-top:2px">마음에 드는 상세페이지를 ChatGPT 입력창(+)에 <b>첨부</b>한 뒤 [이 디자인 분석]을 누르면, 그 색·타이포·레이아웃·구조를 그대로 따라 만듭니다. (디자인 무드보다 우선)</div>
            <div id="dp-ref-style-status" class="dp-output small" style="margin-top:6px"></div>
            <div class="dp-footer2" style="margin-top:6px">
              <button class="dp-btn purple" id="dp-build-ref" type="button">🎨 이 디자인 분석해서 적용</button>
              <button class="dp-btn secondary" id="dp-clear-ref" type="button">초기화</button>
            </div>
            <textarea id="dp-ref-paste" rows="2" placeholder="또는 특징을 직접: 블랙 배경+블루 포인트, 큰 헤드라인, 카드형, 여백 넓게…" style="width:100%;margin-top:6px;padding:6px;border-radius:6px;border:1px solid #555;background:#222;color:#eee;font-size:12px;box-sizing:border-box"></textarea>
            <div class="dp-footer2" style="margin-top:6px"><button class="dp-btn secondary" id="dp-apply-ref-text" type="button">텍스트로 적용</button></div>
          </div>
        </div>

        <div class="dp-section" style="text-align:center">
          <h3>③ 자동 제작</h3>
          <div class="dp-help">아래 버튼 하나면 제품분석 → 카피기획 → 이미지 제작까지 자동으로 끝납니다.</div>
          <div style="height:10px"></div>
          <button class="dp-btn green" id="dp-magic-wizard" style="font-size:16px;padding:14px;width:100%;font-weight:bold">✨ 상세페이지 자동 만들기</button>
          <div class="dp-help" style="margin-top:8px">진행 상황은 아래 로그에 단계별로 표시됩니다. 다시 누르면 중단됩니다.</div>
        </div>

        <div class="dp-section">
          <h3>📊 섹션 진행 현황</h3>
          <label style="display:block;margin-bottom:6px;font-size:12px"><input type="checkbox" id="dp-auto-qa"> 각 섹션 생성 후 자동 검수·재생성(1회) · 기본 꺼짐, 필요할 때만</label>
          <label style="display:block;margin-bottom:6px;font-size:12px"><input type="checkbox" id="dp-text-overlay"> 🅰️ 글자 직접 입히기(AI 글자가 깨질 때만 켜기 · 기본 꺼짐). 평소엔 GPT가 한글·폰트까지 직접 그립니다</label>
          <label style="display:block;margin-bottom:6px;font-size:12px"><input type="checkbox" id="dp-wizard-bundle"> 📦 원클릭(✨ 만들기) 끝나면 자동으로 묶음 내보내기(이미지+움짤 군데군데) · 켜면 버튼 한 번으로 완성</label>
          <label style="display:block;margin-bottom:6px;font-size:12px"><input type="checkbox" id="dp-show-price"> 💲 가격/금액을 이미지에 표기 (기본 꺼짐 — 평소엔 상세페이지에 가격이 안 들어갑니다)</label>
          <div id="dp-section-progress" class="dp-output small">아직 진행 내역이 없습니다. 자동 제작 또는 프롬프트 생성을 시작하면 섹션별 상태가 표시됩니다.</div>
          <div class="dp-footer2" style="margin-top:6px">
            <button class="dp-btn secondary" id="dp-retry-failed" type="button">⟳ 실패 섹션만 다시 생성</button>
          </div>
        </div>

        <div id="dp-fixpanel"></div>

        <div class="dp-section">
          <h3>④ 결과 이미지 합치기</h3>
          <div class="dp-help">ChatGPT가 생성한 섹션 이미지들을 위→아래 순서로 모아 한 장(JPG) 또는 PDF로 저장합니다. 이미지 제작이 끝난 뒤 누르세요.</div>
          <div id="dp-merge-status" class="dp-output small" style="margin-top:8px">아직 수집하지 않았습니다. [생성 이미지 수집]을 눌러 몇 장이 잡히는지 확인하세요.</div>
          <div id="dp-merge-list" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px"></div>
          <div class="dp-footer2" style="margin-top:8px">
            <button class="dp-btn secondary" id="dp-collect-images" type="button">🔍 생성 이미지 수집</button>
            <button class="dp-btn green" id="dp-merge-jpg" type="button">🧵 세로 1장 JPG</button>
            <button class="dp-btn purple" id="dp-merge-pdf" type="button">📄 PDF로 저장</button>
          </div>
        </div>

        <div class="dp-section">
          <!-- v21.8.24.71: 정지컷 모션 GIF/영상 (상단/중간/하단용) -->
            <div style="margin:6px 0 12px;padding:10px;border:1px solid #3f3f46;border-radius:8px">
              <label style="font-weight:bold;font-size:12px;color:#d4d4d8">🎞️ 움짤(GIF/영상) 만들기 — 스마트스토어식</label>
              <div class="dp-help" style="margin:4px 0 8px">④에서 [생성 이미지 수집] 후, 움짤로 만들 컷들을 ✔ 선택하고 아래 버튼을 누르면 <b>컷마다 1개씩 움짤</b>이 만들어집니다(각 컷은 자기 섹션의 2단계 카피로 애니메이션). 스마트스토어처럼 페이지 중간중간 끼워 넣으세요.</div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 10px;margin-bottom:8px">
                <label style="font-size:11px;color:#a1a1aa">스타일
                  <select id="dp-gif-style" style="width:100%;margin-top:2px"><option value="element" selected>요소 애니메이션 · 카피/카드 등장</option><option value="simple">심플 · 줌/팬/샤인</option></select>
                </label>
                <label style="font-size:11px;color:#a1a1aa">포맷
                  <select id="dp-gif-format" style="width:100%;margin-top:2px"><option value="gif" selected>GIF · 이미지칸 자동재생</option><option value="webm">영상(webm) · 고화질/동영상 슬롯</option></select>
                </label>
                <label style="font-size:11px;color:#a1a1aa">크기(가로)
                  <select id="dp-gif-width" style="width:100%;margin-top:2px"><option value="480">480px</option><option value="600" selected>600px</option><option value="720">720px</option></select>
                </label>
                <label style="font-size:11px;color:#a1a1aa">길이
                  <select id="dp-gif-secs" style="width:100%;margin-top:2px"><option value="1.5">1.5초</option><option value="2" selected>2초</option><option value="3">3초</option></select>
                </label>
                <label style="font-size:11px;color:#a1a1aa">부드러움(GIF 프레임)
                  <select id="dp-gif-frames" style="width:100%;margin-top:2px"><option value="15">15프레임</option><option value="20" selected>20프레임</option><option value="30">30프레임</option></select>
                </label>
              </div>
              <button class="dp-btn green" id="dp-gif-batch" type="button" style="width:100%">🎬 선택한 컷들 움짤로 만들기 (컷마다 1개)</button>
              <div style="border-top:1px solid #3f3f46;margin:10px 0 8px;padding-top:8px">
                <div class="dp-help" style="margin-bottom:6px">또는 ⬇️ <b>상세페이지 전체를 한 묶음으로</b> — 군데군데 자동으로 움짤이 섞인 파일들이 <b>순서대로(detail_01~)</b> 나옵니다. 그 순서 그대로 상세페이지에 업로드하세요.</div>
                <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
                  <label style="font-size:11px;color:#a1a1aa">움짤 빈도(군데군데)</label>
                  <select id="dp-bundle-freq" style="font-size:11px"><option value="low">적게(핵심만)</option><option value="mid" selected>보통(추천)</option><option value="high">많이</option></select>
                </div>
                <button class="dp-btn purple" id="dp-bundle-export" type="button" style="width:100%">📦 상세페이지 묶음 내보내기 (이미지+움짤)</button>
              </div>
              <img id="dp-gif-preview" alt="미리보기" style="display:none;max-width:200px;margin-top:8px;border-radius:6px;border:1px solid #52525b">
              <video id="dp-gif-vpreview" controls loop muted playsinline style="display:none;max-width:200px;margin-top:8px;border-radius:6px;border:1px solid #52525b"></video>
            </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <label style="font-weight:bold;font-size:12px;color:#d4d4d8">진행 로그</label>
          <button class="dp-btn secondary" id="dp-clear-log" style="padding:4px 8px;font-size:11px">로그 지우기</button>
        </div>
        <div id="dp-log" class="dp-log">상품을 준비하고 [✨ 상세페이지 자동 만들기]를 누르세요.</div>

        <div class="dp-section" id="dp-attach-debug-section">
          <h3>📎 첨부 디버그 로그</h3>
          <div class="dp-help">이미지가 ChatGPT 입력창에 안 들어갈 때, 아래 로그를 보면 어느 단계에서 실패했는지 확인할 수 있습니다.</div>
          <div id="dp-attach-debug-log" class="dp-output small" style="white-space:pre-wrap;max-height:180px;overflow:auto;margin-top:6px">첨부 시도 전입니다.</div>
          <div class="dp-footer2" style="margin-top:6px">
            <button class="dp-btn secondary" id="dp-copy-attach-log" type="button">로그 복사</button>
            <button class="dp-btn secondary" id="dp-clear-attach-log" type="button">로그 지우기</button>
          </div>
        </div>

        <div class="dp-section">
          <h3>🩺 DOM 자가진단</h3>
          <div class="dp-help">ChatGPT UI가 바뀌어 자동화(입력/전송/첨부/완료감지)가 안 될 때, 어떤 요소를 못 찾는지 점검합니다.</div>
          <div id="dp-diag-output" class="dp-output small" style="margin-top:6px">[🩺 DOM 진단 실행]을 누르세요.</div>
          <div class="dp-footer2" style="margin-top:6px">
            <button class="dp-btn secondary" id="dp-run-diag" type="button">🩺 DOM 진단 실행</button>
          </div>
        </div>

        </div>
      <div class="dp-footer">
        <button class="dp-btn secondary" id="dp-width" type="button">↔ 패널 폭 변경</button>
        <button class="dp-btn secondary" id="dp-save2" type="button">💾 입력 저장</button>
      </div>`;
    document.body.appendChild(panel); bind(); loadSaved(); renderMasterBriefStatus(); renderCopyPlanStatus(); renderRefStyleStatus(); updateWizardButton(); renderSectionProgress(); renderStatusDash(); try{ window.DP_FIX_PANEL && window.DP_FIX_PANEL.mount(); }catch(_){} log('패널을 열었습니다.');
    // v21.8.13: 모듈 로드 상태 자가 점검 + 누락 시 경고
    const moduleStatus = {
      analyzer: !!window.DP_PRODUCT_ANALYZER,
      generator: !!window.DP_DYNAMIC_PROMPTS
    };
    if(!moduleStatus.analyzer || !moduleStatus.generator){
      log('⚠️ 모듈 로드 누락 감지: ' + (moduleStatus.analyzer?'':'분석기 없음 ') + (moduleStatus.generator?'':'생성기 없음') + ' → ChatGPT 페이지를 새로고침(F5)해주세요.');
    } else {
      log('✅ 모듈 로드 정상 (분석기/생성기 OK)');
    }
  }

  function field(id,label,ph){ return `<div class="dp-field"><label>${label}</label><input id="dp-${id}" placeholder="${esc(ph)}"></div>`; }
  function area(id,label,ph){ return `<div class="dp-field dp-full"><label>${label}</label><textarea id="dp-${id}" placeholder="${esc(ph)}"></textarea></div>`; }
  function selectTone(){ return `<div class="dp-field"><label>톤</label><select id="dp-tone"><option>전환 중심</option><option>감성</option><option>프리미엄</option><option>가성비</option><option>전문가형</option></select></div>`; }

  // v20.3: 플랫폼/비율 선택 - 플랫폼 따라 비율 자동 변경
  function selectPlatform(){
    return `<div class="dp-field"><label>판매 플랫폼</label><select id="dp-platform">
      <option value="스마트스토어">스마트스토어 (상세 세로)</option>
      <option value="쿠팡">쿠팡 (상세 세로)</option>
      <option value="와디즈">와디즈 (세로 긴 형)</option>
      <option value="인스타">인스타그램 (세로 4:5)</option>
      <option value="자사몰">자사몰/홈페이지 (세로)</option>
      <option value="11번가">11번가 (상세 세로)</option>
      <option value="기타">기타</option>
    </select></div>`;
  }

  function selectRatio(){
    return `<div class="dp-field"><label>이미지 비율</label><select id="dp-ratio">
      <option value="auto">자동 (권장: 전 섹션 4:5 세로)</option>
      <option value="4:5">4:5 세로형 (권장)</option>
      <option value="9:16">9:16 세로 (쿠팡/와디즈 상세)</option>
      <option value="2:3">2:3 세로형</option>
    </select></div>`;
  }

  // v20.4: 섹션 개수 선택
  function selectSections(){
    return `<div class="dp-field"><label>섹션 개수</label><select id="dp-sections">
      <option value="5">5개 (간단형)</option>
      <option value="6">6개</option>
      <option value="7">7개</option>
      <option value="8" selected>8개 (표준 - 권장)</option>
      <option value="10">10개</option>
      <option value="12">12개 (풀세트)</option>
    </select></div>`;
  }

  // v21.4: 디자인 무드 선택 (색감/폰트/분위기 다양화)
  function selectMood(){
    return `<div class="dp-field"><label>디자인 무드</label><select id="dp-mood">
      <option value="auto" selected>자동 (상품군별 추천)</option>
      <option value="orange_minimal">오렌지 미니멀</option>
      <option value="dark_premium">다크 프리미엄</option>
      <option value="soft_neutral">감성 뉴트럴</option>
      <option value="vivid_pop">비비드 팝</option>
      <option value="magazine">매거진 에디토리얼</option>
      <option value="fresh_clean">프레시 클린</option>
      <option value="feminine_soft">여성감성 소프트</option>
      <option value="sporty_active">스포티 액티브</option>
      <option value="clean_white">클린 화이트</option>
      <option value="modern_lifestyle">모던 라이프스타일</option>
      <option value="highend_brand">하이엔드 브랜드형</option>
      <option value="practical_info">실용 정보형</option>
      <option value="gift_premium">선물 고급 패키지형</option>
      <option value="tech_dashboard">테크 대시보드형</option>
      <option value="warm_natural">웜 내추럴</option>
      <option value="trendy_mz">트렌디 MZ형</option>
      <option value="trust_blue">신뢰 블루 정보형</option>
      <option value="bold_conversion">강한 전환형</option>
      <option value="baby_clean">프리미엄 베이비 클린형</option>
    </select>
    <div style="display:flex;gap:8px;margin-top:6px;align-items:center">
      <canvas id="dp-mood-preview" width="150" height="98" style="border-radius:6px;border:1px solid #555;flex:0 0 auto"></canvas>
      <button class="dp-btn secondary" id="dp-mood-gallery-btn" type="button" style="font-size:11px;padding:5px 8px">🎨 전체 무드 그림으로 보기</button>
    </div>
    <div id="dp-mood-gallery" style="display:none;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px"></div>
    </div>`;
  }
  // v21.8.24.83: 무드가 글씨로만 보여 감이 안 와서, 각 무드를 '미니 목업 그림'으로 미리보기.
  const DP_MOOD_PREVIEW = {
    auto:            {bg:'#e9e9ec', accent:'#8a8a90', accent2:'', text:'#555', dark:false, label:'자동(상품군별)'},
    orange_minimal:  {bg:'#ffffff', accent:'#FF6B1A', accent2:'', text:'#111111', dark:false, label:'오렌지 미니멀'},
    dark_premium:    {bg:'#1C1C1E', accent:'#C9A24B', accent2:'', text:'#ffffff', dark:true,  label:'다크 프리미엄'},
    soft_neutral:    {bg:'#F3EDE3', accent:'#CC9999', accent2:'', text:'#5C4A3A', dark:false, label:'감성 뉴트럴'},
    vivid_pop:       {bg:'#ffffff', accent:'#2563EB', accent2:'#FACC15', text:'#111111', dark:false, label:'비비드 팝'},
    magazine:        {bg:'#FAFAF7', accent:'#B91C1C', accent2:'', text:'#111111', dark:false, label:'매거진 에디토리얼'},
    fresh_clean:     {bg:'#F0F9FF', accent:'#14B8A6', accent2:'', text:'#1E293B', dark:false, label:'프레시 클린'},
    feminine_soft:   {bg:'#F7EDE9', accent:'#CC8FA0', accent2:'', text:'#5C4A44', dark:false, label:'여성감성 소프트'},
    sporty_active:   {bg:'#ffffff', accent:'#FF6A00', accent2:'#111111', text:'#111111', dark:false, label:'스포티 액티브'},
    clean_white:     {bg:'#ffffff', accent:'#38BDF8', accent2:'', text:'#334155', dark:false, label:'클린 화이트'},
    modern_lifestyle:{bg:'#F2F2EF', accent:'#1E3A5F', accent2:'', text:'#2B2B2B', dark:false, label:'모던 라이프스타일'},
    highend_brand:   {bg:'#F6F3EE', accent:'#B08D57', accent2:'', text:'#1A1A1A', dark:false, label:'하이엔드 브랜드형'},
    practical_info:  {bg:'#ffffff', accent:'#2563EB', accent2:'#9aa0a6', text:'#333333', dark:false, label:'실용 정보형'},
    gift_premium:    {bg:'#F3EDE0', accent:'#7B2D3A', accent2:'#B08D57', text:'#2A2A2A', dark:false, label:'선물 고급 패키지형'},
    tech_dashboard:  {bg:'#13182B', accent:'#06B6D4', accent2:'#8B5CF6', text:'#ffffff', dark:true,  label:'테크 대시보드형'},
    warm_natural:    {bg:'#EFE7D8', accent:'#9CA891', accent2:'', text:'#4A3F35', dark:false, label:'웜 내추럴'},
    trendy_mz:       {bg:'#F3EEFB', accent:'#EC4899', accent2:'#2563EB', text:'#111111', dark:false, label:'트렌디 MZ형'},
    trust_blue:      {bg:'#ffffff', accent:'#1D4ED8', accent2:'', text:'#1E293B', dark:false, label:'신뢰 블루 정보형'},
    bold_conversion: {bg:'#ffffff', accent:'#FF3B30', accent2:'#111111', text:'#111111', dark:false, label:'강한 전환형'},
    baby_clean:      {bg:'#FBF7F0', accent:'#8FB8DE', accent2:'#D9C7A8', text:'#5A5A5A', dark:false, label:'프리미엄 베이비 클린형'}
  };
  // 미니 상세페이지 섹션 목업을 그린다(배경+헤드라인 2줄+액센트 바+제품 자리+칩 3개)
  function drawMoodSwatch(canvas, key){
    if(!canvas || !canvas.getContext) return;
    const m = DP_MOOD_PREVIEW[key] || DP_MOOD_PREVIEW.auto;
    const W=canvas.width, H=canvas.height, ctx=canvas.getContext('2d');
    ctx.clearRect(0,0,W,H);
    ctx.fillStyle=m.bg; ctx.fillRect(0,0,W,H);
    const padX=Math.round(W*0.09);
    // 헤드라인 2줄
    ctx.fillStyle=m.text;
    ctx.fillRect(padX, Math.round(H*0.13), Math.round(W*0.64), Math.round(H*0.085));
    ctx.fillRect(padX, Math.round(H*0.26), Math.round(W*0.44), Math.round(H*0.085));
    // 액센트 바
    ctx.fillStyle=m.accent;
    ctx.fillRect(padX, Math.round(H*0.40), Math.round(W*0.18), Math.round(H*0.05));
    if(m.accent2){ ctx.fillStyle=m.accent2; ctx.fillRect(padX+Math.round(W*0.21), Math.round(H*0.40), Math.round(W*0.10), Math.round(H*0.05)); }
    // 제품 자리(회색 박스)
    ctx.fillStyle = m.dark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.10)';
    ctx.fillRect(padX, Math.round(H*0.52), W-padX*2, Math.round(H*0.22));
    // 칩 3개
    const chipY=Math.round(H*0.80), chipH=Math.round(H*0.12), chipW=Math.round((W-padX*2-2*6)/3);
    for(let i=0;i<3;i++){
      const cx=padX+i*(chipW+6);
      ctx.fillStyle = m.dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.06)';
      _roundRectPath(ctx,cx,chipY,chipW,chipH,Math.round(chipH*0.4)); ctx.fill();
      ctx.fillStyle=m.accent; ctx.beginPath(); ctx.arc(cx+Math.round(chipW*0.18), chipY+chipH/2, Math.max(2,Math.round(chipH*0.22)),0,Math.PI*2); ctx.fill();
    }
  }
  function _roundRectPath(ctx,x,y,w,h,r){ r=Math.min(r,w/2,h/2); ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r); ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath(); }
  function toggleMoodGallery(){
    const box=$('dp-mood-gallery'); if(!box) return;
    const open = box.style.display!=='grid';
    if(!open){ box.style.display='none'; return; }
    box.style.display='grid';
    box.innerHTML='';
    Object.keys(DP_MOOD_PREVIEW).forEach(key=>{
      const m=DP_MOOD_PREVIEW[key];
      const cell=document.createElement('div');
      cell.style.cssText='cursor:pointer;text-align:center;border:2px solid '+(($('dp-mood')?.value===key)?'#22c55e':'transparent')+';border-radius:8px;padding:3px';
      const cv=document.createElement('canvas'); cv.width=120; cv.height=78; cv.style.cssText='width:100%;border-radius:6px;border:1px solid #444';
      cell.appendChild(cv);
      const lb=document.createElement('div'); lb.textContent=m.label; lb.style.cssText='font-size:10px;color:#cbd5e1;margin-top:2px;line-height:1.2'; cell.appendChild(lb);
      cell.onclick=()=>{ const sel=$('dp-mood'); if(sel){ sel.value=key; sel.dispatchEvent(new Event('change',{bubbles:true})); } drawMoodSwatch($('dp-mood-preview'),key); toggleMoodGallery(); toggleMoodGallery(); };
      box.appendChild(cell);
      drawMoodSwatch(cv,key);
    });
  }

  // v21.8.24.27: 생성 안정성 프리셋(고급) — 한 번에 속도/안전 균형을 고른다
  function selectQualityPreset(){
    return `<div class="dp-field"><label>생성 안정성 (고급)</label><select id="dp-quality">
      <option value="fast">빠름 (속도 우선)</option>
      <option value="balanced" selected>표준 (권장)</option>
      <option value="safe">안전 (조기전송 최소화)</option>
    </select></div>`;
  }
  function renderStatusDash(){
    const box=$('dp-status-dash'); if(!box) return;
    const prod=($('dp-product')?.value||'').trim();
    const mood=($('dp-mood')?.value||'auto');
    const qual=($('dp-quality')?.value||'balanced');
    const mark=(b)=>b?'✅':'⏳';
    const qlabel={fast:'빠름',balanced:'표준',safe:'안전'}[qual]||qual;
    const moodLabel=(mood&&mood!=='auto')?('선택('+mood+')'):'자동';
    box.textContent =
      `상품: ${prod?prod.slice(0,32):'미입력'}  |  원본이미지: ${state.images.length}장\n`+
      `제품진단 ${mark(!!state.masterBrief)}   카피기획 ${mark(!!state.copyPlan)}   섹션프롬프트 ${state.shortImagePrompts?.length||0}개   레퍼런스 ${state.refStyle?'🎨':'없음'}\n`+
      `무드: ${moodLabel}  |  안정성: ${qlabel}  |  글자: ${$('dp-text-overlay')?.checked?'직접 입힘(추천)':'AI가 그림'}  |  자동검수: ${$('dp-auto-qa')?.checked?'ON':'OFF'}`;
  }

  // 플랫폼별 추천 비율 매핑 (auto일 때 사용)
  function getPlatformRatio(platform, sectionTitle){
    // v21.8.24.49: 상세페이지=세로 스크롤 전용. 정사각(1:1)·가로(3:2) 제거하고 HERO 포함 전 섹션 4:5(세로)로 통일(권장).
    // 다른 세로 비율(9:16 등)이 필요하면 '이미지 비율' 드롭다운에서 직접 고르면 그 값이 우선합니다.
    return '4:5';
  }

  function bind(){
    if($('dp-close')) $('dp-close').onclick=collapse;
    if($('dp-save')) $('dp-save').onclick=save;
    if($('dp-save2')) $('dp-save2').onclick=save;
    if($('dp-sample')) $('dp-sample').onclick=sample;
    if($('dp-advanced-toggle')) $('dp-advanced-toggle').onclick=toggleAdvanced;
    if($('dp-open-advanced')) $('dp-open-advanced').onclick=toggleAdvanced;
    if($('dp-infer')) $('dp-infer').onclick=()=>{ runLocalInference(true); };
    if($('dp-build-short-prompts')) $('dp-build-short-prompts').onclick=()=>{ buildShortImagePrompts(true); };
    if($('dp-make-short-image')) $('dp-make-short-image').onclick=()=>{ createShortImageByIndex(0); };
    if($('dp-next-short-image')) $('dp-next-short-image').onclick=()=>{ createShortImageByIndex(state.currentShortImageIndex + 1); };
    if($('dp-clear')) $('dp-clear').onclick=clearAll;
    if($('dp-width')) $('dp-width').onclick=()=>{ state.isWide=!state.isWide; $('dp-director-panel').classList.toggle('dp-wide',state.isWide); };
    $('dp-image-files').onchange=handleImageFiles; if($('dp-upload-chatgpt')) $('dp-upload-chatgpt').onclick=uploadSelectedImagesToChatGPT; if($('dp-check-attach')) $('dp-check-attach').onclick=checkAttachmentStatus;
    if($('dp-fetch-link')) $('dp-fetch-link').onclick=fetchProductLink;
    if($('dp-build-brief')) $('dp-build-brief').onclick=buildMasterBrief;
    if($('dp-save-brief')) $('dp-save-brief').onclick=saveMasterBriefManual;
    if($('dp-clear-brief')) $('dp-clear-brief').onclick=clearMasterBrief;
    if($('dp-build-plan')) $('dp-build-plan').onclick=buildCopyPlan;
    if($('dp-save-plan')) $('dp-save-plan').onclick=saveCopyPlanManual;
    if($('dp-clear-plan')) $('dp-clear-plan').onclick=clearCopyPlan;
    if($('dp-magic-wizard')) $('dp-magic-wizard').onclick=runMagicWizard;
    if($('dp-clear-log')) $('dp-clear-log').onclick=()=>{ const el=$('dp-log'); if(el) el.textContent='로그를 지웠습니다.'; };
    if($('dp-build-ref')) $('dp-build-ref').onclick=analyzeReference;
    if($('dp-save-ref')) $('dp-save-ref').onclick=saveRefStyleManual;
    if($('dp-clear-ref')) $('dp-clear-ref').onclick=clearRefStyle;
    if($('dp-apply-ref-text')) $('dp-apply-ref-text').onclick=applyRefStyleFromText;
    if($('dp-auto-run-all')) $('dp-auto-run-all').onclick=()=>{ if(state.autoRunActive) stopAutoRun(); else autoRunAllSections(); };
    if($('dp-copy-attach-log')) $('dp-copy-attach-log').onclick=copyAttachLog;
    if($('dp-clear-attach-log')) $('dp-clear-attach-log').onclick=clearAttachLog;
    if($('dp-collect-images')) $('dp-collect-images').onclick=previewCollectImages;
    if($('dp-merge-jpg')) $('dp-merge-jpg').onclick=()=>mergeSectionImages('jpg');
    if($('dp-merge-pdf')) $('dp-merge-pdf').onclick=()=>mergeSectionImages('pdf');
    if($('dp-gif-batch')) $('dp-gif-batch').onclick=makeClipsBatch;
    if($('dp-bundle-export')) $('dp-bundle-export').onclick=exportDetailBundle;
    if($('dp-retry-failed')) $('dp-retry-failed').onclick=retryFailedSections;
    if($('dp-run-diag')) $('dp-run-diag').onclick=runDomDiagnostics;
    if($('dp-quality')) $('dp-quality').onchange=()=>{ applyTimingPreset($('dp-quality').value); renderStatusDash(); save(); const L={fast:'빠름',balanced:'표준',safe:'안전'}; log('생성 안정성: '+(L[$('dp-quality').value]||$('dp-quality').value)+' 적용'); };
    if($('dp-auto-qa')) $('dp-auto-qa').onchange=()=>{ renderStatusDash(); save(); };
    if($('dp-text-overlay')) $('dp-text-overlay').onchange=()=>{ renderStatusDash(); save(); };
    if($('dp-show-price')) $('dp-show-price').onchange=()=>{ save(); };
    ['dp-product','dp-mood'].forEach(id=>{ const el=$(id); if(el) el.addEventListener('input', renderStatusDash); });
    // v21.8.24.83: 무드 그림 미리보기
    if($('dp-mood')){ $('dp-mood').addEventListener('change', ()=>drawMoodSwatch($('dp-mood-preview'), $('dp-mood').value)); drawMoodSwatch($('dp-mood-preview'), $('dp-mood').value); }
    if($('dp-mood-gallery-btn')) $('dp-mood-gallery-btn').onclick=toggleMoodGallery;
  }

  function basicIds(){ return ['product','link','platform','tone','ratio','sections','mood','quality']; }
  function advancedIds(){ return ['category','price','target','benefits','pain','specs','manualFacts','reviews','competitor']; }
  function ids(){ return [...basicIds(), ...advancedIds()]; }
  function getData(){
    const d={};
    ids().forEach(k=>d[k]=($('dp-'+k)?.value||'').trim());
    d.specs = mergeManualFactsWithSpecs(d.manualFacts, d.specs);
    d.imagesAttached=!!(state.attachmentVerified || isComposerLikelyHasAttachments()); d.imageNames=state.images.map(i=>i.name); d.inferred=state.inferred; d.advancedOpen=state.advancedOpen; d.masterBrief=state.masterBrief; d.copyPlan=state.copyPlan; d.refStyle=state.refStyle; d.lastProductSig=state.lastProductSig; d.briefSig=state.briefSig; d.planSig=state.planSig; d.autoQa=!!$('dp-auto-qa')?.checked; d.textOverlay=!!$('dp-text-overlay')?.checked; d.wizardBundle=!!$('dp-wizard-bundle')?.checked; d.showPrice=!!$('dp-show-price')?.checked;
    // v21.8.24.92: 새로고침/탭 종료 후 '이어서 생성'을 위해 섹션 프롬프트·진행상태도 저장
    d.shortImagePrompts=state.shortImagePrompts||[]; d.sectionStatus=state.sectionStatus||[]; return d;
  }
  function setData(d={}){ ids().forEach(k=>{ if($('dp-'+k)) $('dp-'+k).value=d[k]||''; }); state.attachmentVerified=false; if($('dp-images-attached')) $('dp-images-attached').checked=false; state.inferred=d.inferred||null; state.advancedOpen=!!d.advancedOpen; state.masterBrief=d.masterBrief||''; state.copyPlan=d.copyPlan||'';
    // v21.8.24.102: 과거 버그로 '[이미지 답변]' 같은 껍데기가 레퍼런스로 저장된 경우 복원 시 정리
    state.refStyle=(d.refStyle && isUsableRefStyle(d.refStyle)) ? d.refStyle : '';
    if(d.refStyle && !state.refStyle) log('🧹 이전에 저장된 레퍼런스가 빈 껍데기("[이미지 답변]" 등)라 초기화했습니다. 다시 분석하거나 [텍스트로 적용]을 사용하세요.'); state.lastProductSig=d.lastProductSig||''; state.briefSig=d.briefSig||''; state.planSig=d.planSig||''; if($('dp-auto-qa')) $('dp-auto-qa').checked=!!d.autoQa; if($('dp-text-overlay')) $('dp-text-overlay').checked=!!d.textOverlay; if($('dp-wizard-bundle')) $('dp-wizard-bundle').checked=!!d.wizardBundle; if($('dp-show-price')) $('dp-show-price').checked=!!d.showPrice;
    // v21.8.24.92: 진행상태 복원 — 'running'은 죽은 세션이므로 'pending'으로 정규화 후 미완료가 있으면 이어서 생성 안내
    if(Array.isArray(d.shortImagePrompts) && d.shortImagePrompts.length){
      state.shortImagePrompts = d.shortImagePrompts;
      state.sectionStatus = (Array.isArray(d.sectionStatus)?d.sectionStatus:[]).map(s => s==='running' ? 'pending' : s);
      const left = state.sectionStatus.filter(s => s==='pending' || s==='failed').length;
      if(left > 0) setTimeout(()=>{ log(`🔁 지난 작업 복원: 섹션 ${state.shortImagePrompts.length}개 중 ${left}개 미완료 — [⟳ 실패 섹션만 다시 생성]을 누르면 이어서 만듭니다.`); renderSectionProgress(); }, 800);
    }
    const _q=$('dp-quality'); if(_q){ if(!_q.value) _q.value='balanced'; applyTimingPreset(_q.value); } applyAdvancedState(); renderInference(); renderMasterBriefStatus(); renderCopyPlanStatus(); renderRefStyleStatus(); renderStatusDash(); try{ drawMoodSwatch($('dp-mood-preview'), $('dp-mood')?.value||'auto'); }catch(_){} }
  // v21.8.24.24: 상품 동일성 시그니처. 링크(URL)가 가장 안정적이며, 없으면 상품명으로 판별.
  function productSignature(d){
    const link=String(d?.link||'').trim().toLowerCase().replace(/[#?].*$/,'');
    if(link) return 'L:'+link;
    const name=String(d?.product||'').replace(/\[[^\]]*\]/g,'').replace(/\s+/g,' ').trim().toLowerCase().slice(0,60);
    return name ? 'N:'+name : '';
  }
  // 새 상품이 감지되면 이전 제품의 진단/카피/자동추정/파생필드를 초기화해 오염을 막는다.
  function clearStaleForNewProduct(reason){
    const cleared=[];
    if(state.masterBrief){ state.masterBrief=''; cleared.push('제품진단'); }
    if(state.copyPlan){ state.copyPlan=''; cleared.push('카피기획'); }
    state.briefSig=''; state.planSig='';
    state.shortImagePrompts=[]; state.sectionStatus=[]; state.currentShortImageIndex=0; state.collectedImages=[]; if($('dp-merge-list')) $('dp-merge-list').innerHTML='';
    ['category','target','benefits','pain','specs'].forEach(k=>{ const el=$('dp-'+k); if(el && el.value.trim()){ el.value=''; cleared.push(k); } });
    state.inferred=null;
    renderMasterBriefStatus(); renderCopyPlanStatus(); renderInference(); renderShortPromptStatus(); renderSectionProgress();
    if(cleared.length) log(`🔄 새 상품 감지(${reason}) → 이전 제품 정보 초기화: ${cleared.join(', ')}`);
  }
  function save(){ chrome.storage.local.set({[STORE_KEY]:getData(),[RESULT_KEY]:state.lastResult}); log('입력값을 저장했습니다.'); }
  function loadSaved(){ chrome.storage.local.get([STORE_KEY,RESULT_KEY], r=>{ if(r?.[STORE_KEY]) setData(r[STORE_KEY]); if(r?.[RESULT_KEY]) state.lastResult=r[RESULT_KEY]||''; }); }
  // v21.8.24.51: (plumbing) 템플릿 모듈이 레퍼런스/스타일 가이드 텍스트를 읽고 쓰기 위한 안전 훅.
  // 상태 저장·복원만 담당하며, 프롬프트 생성·이미지 생성·완료감지 로직과는 무관.
  window.DP_REF_STYLE = { get: () => state.refStyle || '', set: (v) => { state.refStyle = String(v || ''); save(); renderRefStyleStatus(); } };
  // v21.8.24.57: '증상 기반 고치기' 패널(fix_panel.js)이 호출하는 최소 훅. 기존 생성/완료감지 함수 본문은 건드리지 않고 참조만 노출.
  window.DP_FIX_HOOKS = {
    log,
    getState: () => state,
    rebuildPrompts: (showLog=false) => buildShortImagePrompts(showLog),
    regenAll: () => autoRunAllSections(),
    regenOneSection: (i) => runSection(i, (state.shortImagePrompts||[]).length),
    ensureImagesAttached: () => ensureImagesAttached(),
    tryOpenImageMode: () => tryOpenImageMode(),
    rebuildCopyPlan: (directive='') => buildCopyPlan(directive),
    rebuildMasterBrief: () => buildMasterBrief(),
    openAdvanced: () => { state.advancedOpen = true; applyAdvancedState(); save(); },
    setMood: (v) => { const el = $('dp-mood'); if(el){ el.value = String(v||'auto'); } },
    setSectionStatus: (i, st) => setSectionStatus(i, st),
    renderProgress: () => { renderSectionProgress(); renderShortPromptStatus(); }
  };

  function toggleAdvanced(){ state.advancedOpen=!state.advancedOpen; applyAdvancedState(); save(); }
  function applyAdvancedState(){ const box=$('dp-advanced'); const btn=$('dp-advanced-toggle'); if(box) box.style.display=state.advancedOpen?'block':'none'; if(btn) btn.textContent=state.advancedOpen?'⚙️ 단계별 수동 제어 / 고급 설정 접기':'⚙️ 단계별 수동 제어 / 고급 설정 열기'; }

  function sample(){
    setData({product:'브라운 퀼팅 컴포트 체어',link:'',platform:'스마트스토어',tone:'감성',category:'',price:'',target:'',benefits:'',pain:'',specs:'',reviews:'',competitor:'',manualFacts:'',imagesAttached:false});
    runLocalInference(true);
    log('최소 샘플 값을 입력하고 AI 추정을 실행했습니다.');
  }

  function handleImageFiles(e){
    const files=Array.from(e.target.files||[]).slice(0,8);
    state.images.forEach(i=>URL.revokeObjectURL(i.url));
    state.images=files.map((file,idx)=>({file,name:file.name,url:URL.createObjectURL(file),idx:idx+1}));
    state.chatFilesUploaded=false;
    state.attachmentVerified=false;
    clearAttachLog();
    attachLog(`[준비] 패널 이미지 선택: ${state.images.length}개${state.images.length?' · '+state.images.map(x=>x.name).join(', '):''}`);
    if($('dp-images-attached')) $('dp-images-attached').checked=false;
    const status=$('dp-upload-status');
    if(status) status.textContent=state.images.length ? `선택 이미지 ${state.images.length}장. 자동 제작 시 ChatGPT 입력창에 자동 첨부를 시도합니다.` : '선택하면 자동 제작 시 ChatGPT에 자동 첨부됩니다. 안 되면 ChatGPT +버튼으로 직접 첨부하세요.';
    renderPreview(); save();
    log(`이미지 목록 ${state.images.length}장을 추가했습니다. 자동 제작 시 ChatGPT 입력창 첨부를 다시 확인합니다.`);
  }
  function renderPreview(){
    const box=$('dp-preview'); if(!box)return;
    box.innerHTML=state.images.map((img,i)=>`<div class="dp-image-card"><img class="dp-thumb" src="${img.url}"><div class="dp-image-info"><b>이미지 ${i+1}${img.srcUrl?' · 링크':''}</b><div>${esc(img.name)}</div></div><button class="dp-btn danger dp-img-del" data-idx="${i}" style="padding:4px 8px;font-size:11px;margin-left:auto">✕</button></div>`).join('');
    box.querySelectorAll('.dp-img-del').forEach(b=>b.onclick=()=>removeImage(parseInt(b.dataset.idx,10)));
    renderStatusDash();
  }
  function removeImage(i){
    const img=state.images[i]; if(!img) return;
    try{ URL.revokeObjectURL(img.url); }catch(_){}
    state.images.splice(i,1);
    state.attachmentVerified=false;
    if($('dp-images-attached')) $('dp-images-attached').checked=false;
    renderPreview(); save();
    log(`이미지 ${i+1}장을 목록에서 제거했습니다.`);
  }
  // v21.8.24.25: 링크에서 받은 상품 이미지를 원본 참고용으로 추가(→ 자동 제작 시 ChatGPT에 자동 첨부)
  // v21.8.24.48: 받아온 바이트가 진짜 이미지인지 매직바이트로 판별(서비스워커와 동일 기준).
  // 비이미지를 image/jpeg로 위장 첨부해 "링크/파일"로 깨지던 문제를 막는다.
  async function sniffImageMimeFromBlobV48(blob){
    try{
      const bytes=new Uint8Array(await blob.slice(0,256).arrayBuffer());
      if(bytes.length<4) return '';
      const b=bytes;
      if(b[0]===0xFF && b[1]===0xD8 && b[2]===0xFF) return 'image/jpeg';
      if(b[0]===0x89 && b[1]===0x50 && b[2]===0x4E && b[3]===0x47) return 'image/png';
      if(b[0]===0x47 && b[1]===0x49 && b[2]===0x46 && b[3]===0x38) return 'image/gif';
      if(b[0]===0x42 && b[1]===0x4D) return 'image/bmp';
      if(b.length>=12 && b[0]===0x52 && b[1]===0x49 && b[2]===0x46 && b[3]===0x46 &&
         b[8]===0x57 && b[9]===0x45 && b[10]===0x42 && b[11]===0x50) return 'image/webp';
      let head=''; for(let i=0;i<bytes.length;i++) head+=String.fromCharCode(bytes[i]);
      if(/<svg[\s>]/i.test(head)) return 'image/svg+xml';
      return '';
    }catch(_){ return ''; }
  }
  // 매직바이트 통과 + (래스터는) 실제 디코딩(naturalWidth>0)까지 확인한 것만 반환.
  async function verifyDecodableImageV48(blob){
    const mime=await sniffImageMimeFromBlobV48(blob);
    if(!mime) return null;
    if(mime==='image/svg+xml') return { blob, mime };
    const ok=await new Promise(res=>{
      const u=URL.createObjectURL(blob); const im=new Image();
      im.onload=()=>{ URL.revokeObjectURL(u); res(im.naturalWidth>0 && im.naturalHeight>0); };
      im.onerror=()=>{ URL.revokeObjectURL(u); res(false); };
      im.src=u;
    });
    return ok ? { blob, mime } : null;
  }

  async function importLinkImageAsReference(imgUrl){
    if(!imgUrl) return false;
    if(state.images.some(i=>i.srcUrl===imgUrl)) return true;
    if(state.images.length>=10){ log('⚠️ 원본 이미지는 최대 10장까지입니다. 불필요한 이미지를 ✕로 제거 후 추가하세요.'); return false; }
    log('🖼 링크 상품 이미지를 가져오는 중...');
    const durl=await getImageDataURL(imgUrl);
    if(!durl){ log('⚠️ 링크 이미지를 가져오지 못했습니다(이미지가 아니거나 차단/CORS 가능). 필요하면 ChatGPT에 직접 첨부하세요.'); return false; }
    try{
      const rawBlob=await (await fetch(durl)).blob();
      if(rawBlob.size<256){ log('⚠️ 유효한 이미지가 아닙니다(파일이 너무 작음).'); return false; }
      // v21.8.24.48: 강제 jpeg 변환 제거. 실제로 열리는 이미지일 때만 첨부, 아니면 건너뛴다.
      const verified=await verifyDecodableImageV48(rawBlob);
      if(!verified){ log('⚠️ 이미지가 아니거나 열 수 없는 파일이라 건너뜁니다(링크가 실제 이미지가 아닐 수 있음). 필요하면 ChatGPT에 직접 첨부하세요.'); return false; }
      const blob=verified.blob;
      const type=verified.mime;
      const ext=((type.split('/')[1])||'jpg').replace('jpeg','jpg').replace('svg+xml','svg');
      const name='링크상품_'+Date.now()+'.'+ext;
      const file=new File([blob], name, {type});
      const url=URL.createObjectURL(blob);
      state.images.push({file,name,url,srcUrl:imgUrl});
      state.attachmentVerified=false;
      if($('dp-images-attached')) $('dp-images-attached').checked=false;
      renderPreview(); save();
      log('✅ 링크 상품 이미지를 원본으로 추가했습니다. [상세페이지 자동 만들기] 시 ChatGPT에 자동 첨부됩니다.');
      return true;
    }catch(e){ log('링크 이미지 처리 오류: '+(e?.message||e)); return false; }
  }

  function runLocalInference(fillFields=false){
    const d=getData();
    let analysis = null;
    try{
      analysis = window.DP_PRODUCT_ANALYZER?.analyzeProductContext
        ? window.DP_PRODUCT_ANALYZER.analyzeProductContext(d)
        : null;
    }catch(e){ console.warn('product analyzer failed', e); }

    let category='확인 필요', target='확인 필요', benefits='확인 필요', pain='확인 필요', specs='확인 필요', competitor='확인 필요';
    if(analysis){
      category = analysis.category_group || analysis.product_type || '확인 필요';
      target = analysis.target_customer || '확인 필요';
      benefits = analysis.core_value || '확인 필요';
      pain = analysis.main_pain_point || '확인 필요';
      specs = analysis.spec_hint || '확인 필요';
      competitor = analysis.competitor_hint || '확인 필요';
    } else {
      const p=(d.product||'').toLowerCase();
      const link=d.link||'';
      if(/체어|의자|chair|퀼팅|브라운/.test(p)){
        category='가구/사무용 의자';
        target='홈오피스 사용자, 재택근무자, 매장 상담 공간을 꾸미는 소상공인';
        benefits='브라운 컬러, 퀼팅 디테일, 팔걸이, 따뜻한 홈오피스 분위기';
        pain='일반 사무의자는 너무 투박하고 방 분위기와 잘 어울리지 않음';
        specs='정확한 소재, 사이즈, 내하중, 높이조절 여부, 조립 여부 확인 필요';
        competitor='일반 블랙 사무의자는 사무실 느낌이 강하고 인테리어 포인트가 약함';
      } else if(/노트북|laptop|컴퓨터|pc/.test(p)){
        category='디지털/노트북 또는 자동화 장비';
        target='온라인 업무 자동화가 필요한 사장님, 블로그/SNS 운영자, 소상공인';
        benefits='업무 자동화, 반복 작업 시간 절약, 노트북 기반 사용 편의성';
        pain='홍보/블로그/SNS 작업을 매일 직접 하기 번거로움';
        specs='CPU, RAM, 저장공간, 운영체제, 설치 프로그램, A/S 조건 확인 필요';
        competitor='일반 노트북은 자동화 세팅이 없고 사용자가 직접 세팅해야 함';
      } else if(/저항밴드|저항 밴드|밴드|resistance|튜빙|홈트|운동밴드|운동 밴드/.test(p)){
        category='스포츠/홈트레이닝 소도구';
        target='집에서 간단히 운동하려는 홈트 사용자, 초보 운동자, 공간 부담 없이 근력운동을 원하는 사용자';
        benefits='휴대성, 공간 절약, 다양한 동작 활용, 강도별 사용 가능 여부 확인 필요';
        pain='운동기구는 부피가 크고 사용법이 어렵거나 꾸준히 하기 부담스러움';
        specs='구성품, 밴드 강도, 소재, 길이, 손잡이/앵커 포함 여부, 보관 파우치 여부 확인 필요';
        competitor='일반 저가 밴드는 구성 설명이 부족하거나 강도/사용법/내구성 신뢰 요소가 약할 수 있음';
      } else if(link){
        category='상품 링크 기반 확인 필요';
        target='상품 링크와 원본 이미지를 바탕으로 AI가 추정 필요';
        benefits='상품 링크와 이미지에서 확인 가능한 장점 추정 필요';
        pain='고객 고민은 상품 카테고리 확인 후 추정 필요';
        specs='링크/이미지 확인 필요';
        competitor='경쟁상품 특징은 카테고리 확인 후 추정 필요';
      }
    }

    state.inferred={
      category,target,benefits,pain,specs,competitor,price:'확인 필요',reviews:'확인 필요',
      product_type: analysis?.product_type || category,
      category_group: analysis?.category_group || category,
      template_type: analysis?.template_type || 'general',
      recommended_sections: analysis?.recommended_sections || [],
      confidence: analysis?.confidence || 0
    };
    if(fillFields){
      if(!$('dp-category').value) $('dp-category').value=category;
      if(!$('dp-target').value) $('dp-target').value=target;
      if(!$('dp-benefits').value) $('dp-benefits').value=benefits;
      if(!$('dp-pain').value) $('dp-pain').value=pain;
      if(!$('dp-specs').value) $('dp-specs').value=specs;
      if(!$('dp-competitor').value) $('dp-competitor').value=competitor;
      if(!$('dp-price').value) $('dp-price').value='확인 필요';
      if(!$('dp-reviews').value) $('dp-reviews').value='확인 필요';
    }
    renderInference(); save();
    log(`상품 자동 분석 완료: ${state.inferred.category_group} / ${state.inferred.template_type}`);
  }

    function renderInference(){
    const box=$('dp-infer-box'); if(!box) return;
    if(!state.inferred){ box.textContent='[AI 자동 추정]을 누르면 카테고리, 타겟, 장점, 고객 고민 등을 먼저 채워줍니다.'; return; }
    const x=state.inferred;
    box.textContent=`상품군: ${x.category_group||x.category}\n템플릿: ${x.template_type||'general'}\n추천 섹션: ${(x.recommended_sections||[]).join(' → ')||'기본'}\n신뢰도: ${x.confidence||0}%\n\n타겟 고객: ${x.target}\n핵심 장점: ${x.benefits}\n고객 고민: ${x.pain}\n상품 스펙: ${x.specs}\n경쟁상품 특징: ${x.competitor}\n\n※ 상품명/링크/원본 이미지 첨부 여부 기반 자동 분석입니다. 실제 상세페이지에서는 원본 이미지와 확인된 스펙을 우선합니다.`;
  }

  async function setPromptText(text){ const el=findInput(); if(!el) return false; el.focus(); if(el.tagName==='TEXTAREA'){ el.value=text; el.dispatchEvent(new Event('input',{bubbles:true})); } else { el.innerHTML=''; el.textContent=text; el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text})); } await sleep(150); return true; }
  function findInput(){ const selectors=['#prompt-textarea','textarea[data-testid="prompt-textarea"]','textarea','div[contenteditable="true"][data-testid="prompt-textarea"]','div[contenteditable="true"]']; for(const s of selectors){ const el=document.querySelector(s); if(el) return el; } return null; }
  function getPromptInputText(input=findInput()){
    if(!input) return '';
    if(input.tagName==='TEXTAREA') return input.value || '';
    return (input.innerText || input.textContent || '').trim();
  }

  function userMessageCount(){
    return document.querySelectorAll('[data-message-author-role="user"]').length;
  }

  function getButtonSignalText(btn){
    if(!btn) return '';
    const attrs=[];
    ['aria-label','data-testid','title','name','type','class'].forEach(k=>{
      try{ const v=btn.getAttribute?.(k); if(v) attrs.push(v); }catch(_){ }
    });
    try{
      const imgAlt=[...btn.querySelectorAll?.('img[alt],svg[aria-label],span[aria-label]')||[]]
        .map(x=>x.getAttribute('alt')||x.getAttribute('aria-label')||'')
        .filter(Boolean);
      attrs.push(...imgAlt);
    }catch(_){ }
    return ((btn.innerText||btn.textContent||'')+' '+attrs.join(' ')).toLowerCase();
  }

  function isWrongSendButtonTarget(btn){
    if(!btn) return true;
    const panel=$('dp-director-panel');
    if(panel && panel.contains(btn)) return true;
    const txt=getButtonSignalText(btn);
    // v21.8.5: 전송 버튼 오클릭 방지. vidIQ/확장/도구/이미지/마이크/첨부 버튼은 절대 클릭하지 않음.
    return /vidiq|확장|extension|extensions|이미지 만들기|글쓰기|편집|필요한 항목 찾기|항목 찾기|search|검색|browse|web|웹|attach|첨부|upload|파일|image|이미지|photo|사진|paperclip|clip|plus|\+|mic|microphone|마이크|voice|음성|stop|중지|cancel|취소|menu|더보기|model|모델|tool|도구|canvas|캔버스|apps|앱|connector|connect|연결/.test(txt);
  }

  function clickElementLikeUser(el){
    if(!el) return false;
    try{
      el.scrollIntoView({block:'nearest', inline:'nearest'});
      const r=el.getBoundingClientRect();
      const x=r.left+r.width/2, y=r.top+r.height/2;
      ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type=>{
        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0}));
      });
      return true;
    }catch(e){
      try{ el.click(); return true; }catch(_){ return false; }
    }
  }

  function isOfficialSendButton(btn){
    const txt=getButtonSignalText(btn);
    const dt=(btn.getAttribute?.('data-testid')||'').toLowerCase();
    const aria=(btn.getAttribute?.('aria-label')||'').toLowerCase();
    return /send-button|send_message|composer-submit|submit/.test(dt) || /send|전송|보내기/.test(aria) || /^submit$/i.test(btn.getAttribute?.('type')||'');
  }

  function isDarkButton(btn){
    try{
      const bg=getComputedStyle(btn).backgroundColor||'';
      const m=bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
      if(!m) return false;
      const [r,g,b]=m.slice(1,4).map(Number);
      return r<80 && g<80 && b<80;
    }catch(_){ return false; }
  }

  function isLikelyUnlabeledSendButton(btn, root, input){
    if(!btn || !root || isWrongSendButtonTarget(btn)) return false;
    if(isOfficialSendButton(btn)) return true;
    const txt=(btn.innerText||btn.textContent||'').trim();
    const aria=(btn.getAttribute?.('aria-label')||'').trim();
    const dt=(btn.getAttribute?.('data-testid')||'').trim();
    // 라벨이 있는 버튼은 대부분 도구 버튼이므로, 공식 send 신호가 없으면 제외.
    if(txt || aria || dt) return false;
    const r=btn.getBoundingClientRect();
    const base=(root||input).getBoundingClientRect();
    if(r.width<24 || r.height<24 || r.width>72 || r.height>72) return false;
    const centerX=r.left+r.width/2;
    const centerY=r.top+r.height/2;
    const nearRight=centerX > base.right - 90;
    const nearBottom=centerY > base.bottom - 90;
    const hasSvg=!!btn.querySelector('svg');
    // 현재 ChatGPT 전송 버튼은 입력창 오른쪽 아래의 검은 원형/사각 버튼.
    return nearRight && nearBottom && hasSvg && isDarkButton(btn);
  }

  function getSendButtonCandidates(){
    const panel=$('dp-director-panel');
    const input=findInput();
    const root=input ? (input.closest('form') || input.closest('[data-testid*="composer"]') || input.closest('[class*="composer"]') || input.parentElement?.parentElement?.parentElement || input.parentElement) : null;
    const all=[];
    const add=(b)=>{
      if(!b || (panel && panel.contains(b)) || !isVisible(b) || b.disabled || b.getAttribute('aria-disabled')==='true') return;
      if(isWrongSendButtonTarget(b)) return;
      if(isOfficialSendButton(b) || isLikelyUnlabeledSendButton(b, root, input)) all.push(b);
    };
    // 공식 send 버튼 우선. (현재 ChatGPT UI 변형 대응: data-testid/aria-label 다양화)
    [...document.querySelectorAll('button[data-testid="send-button"],button#composer-submit-button,button[data-testid*="send"],button[id*="composer-submit"],button[aria-label="프롬프트 보내기"],button[aria-label="Send prompt"],button[aria-label*="Send"],button[aria-label*="send"],button[aria-label*="전송"],button[aria-label*="보내기"],button[aria-label*="프롬프트"],button[aria-label*="메시지 보내기" i]')].forEach(add);
    // 그 다음 composer 내부에서만 엄격 후보 탐색.
    if(root){
      [...root.querySelectorAll('button,[role="button"]')].forEach(add);
    }
    const unique=[...new Set(all)];
    const base=(root||input)?.getBoundingClientRect?.();
    unique.sort((a,b)=>{
      if(isOfficialSendButton(a) && !isOfficialSendButton(b)) return -1;
      if(!isOfficialSendButton(a) && isOfficialSendButton(b)) return 1;
      const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect();
      if(base){
        const as=Math.abs((ar.left+ar.width/2)-base.right)*1.5 + Math.abs((ar.top+ar.height/2)-base.bottom);
        const bs=Math.abs((br.left+br.width/2)-base.right)*1.5 + Math.abs((br.top+br.height/2)-base.bottom);
        return as-bs;
      }
      return 0;
    });
    return unique.slice(0,3);
  }

  async function verifySendStarted(beforeInputText='', beforeUserCount=0, beforeAssistantText=''){
    for(let i=0;i<14;i++){
      await sleep(250);
      const nowInput=getPromptInputText();
      const nowUser=userMessageCount();
      const nowAssistant=getLastAssistantText();
      if(isGenerating()) return true;
      if(beforeInputText && !nowInput) return true;
      if(beforeInputText && nowInput.length < Math.min(20, beforeInputText.length*0.2)) return true;
      if(nowUser > beforeUserCount) return true;
      if(beforeAssistantText && nowAssistant && nowAssistant !== beforeAssistantText) return true;
    }
    return false;
  }

  // v21.8.24.47: 전송 버튼을 못 찾을 때 입력창에서 Enter로 전송(ChatGPT 기본 동작). 버튼 감지 실패 우회.
  async function pressEnterToSend(input){
    if(!input) return false;
    try{
      input.focus();
      const opts={bubbles:true,cancelable:true,key:'Enter',code:'Enter',keyCode:13,which:13};
      ['keydown','keypress','keyup'].forEach(type=>{ try{ input.dispatchEvent(new KeyboardEvent(type,opts)); }catch(_){ } });
      return true;
    }catch(_){ return false; }
  }
  async function clickSendButton(beforeAssistantText=''){
    const input=findInput();
    const beforeInputText=getPromptInputText(input);
    const beforeUserCount=userMessageCount();
    const beforeText=beforeAssistantText || getLastAssistantText();
    const candidates=getSendButtonCandidates();
    // 1) 안전 후보 버튼 클릭(오클릭 방지 필터 통과한 것만)
    for(let i=0;i<candidates.length;i++){
      const btn=candidates[i];
      if(isWrongSendButtonTarget(btn)) continue;
      if(clickElementLikeUser(btn)){
        if(await verifySendStarted(beforeInputText,beforeUserCount,beforeText)) return true;
      }
    }
    // 2) 버튼 실패/없음 → 입력창 Enter 전송 폴백(현재 ChatGPT UI에서 버튼 셀렉터가 안 맞아도 전송됨)
    if(input){
      log('전송 버튼 자동탐지 실패 → 입력창 Enter 전송으로 시도합니다.');
      await pressEnterToSend(input);
      if(await verifySendStarted(beforeInputText,beforeUserCount,beforeText)) return true;
      await sleep(500);
      await pressEnterToSend(input);
      if(await verifySendStarted(beforeInputText,beforeUserCount,beforeText)) return true;
    }
    log('⚠️ 전송 실패: 버튼·Enter 모두 전송 확인 안 됨. 입력창 오른쪽 아래 화살표를 직접 눌러주세요.');
    return false;
  }
  // v21.8.11: 생성 상태 기반으로 재작성. 이미지 답변(텍스트 거의 없는 경우)도 정확히 감지.
  async function waitForNewAssistantText(before='', timeout=300000){
    const start = Date.now();
    let last = '';
    let phase = 'wait_start';  // wait_start → generating → finished
    let stoppedStable = 0;
    let assistantNodeCountAtStart = countAssistantNodes();

    while(Date.now() - start < timeout){
      await sleep(1000);
      const gen = isGenerating();
      const cur = getLastAssistantText();
      const newAssistantNode = countAssistantNodes() > assistantNodeCountAtStart;

      // 1) 생성 시작 대기 (정지 버튼 등장 또는 새 assistant 노드 등장)
      if(phase === 'wait_start'){
        if(gen || newAssistantNode){
          phase = 'generating';
          log('[답변 대기] ChatGPT 생성 시작 감지');
        } else if(Date.now()-start > 15000){
          // 15초 동안 생성 시작 신호 없음 - 그래도 답변이 있으면 통과(빠르게 끝난 경우)
          if(cur && cur !== before) return cur;
        }
        continue;
      }

      // 2) 생성 중 → 생성 끝(정지 버튼 사라짐) 감지
      if(phase === 'generating'){
        if(cur && cur !== last){ last = cur; }
        if(!gen){
          // 정지 버튼 사라짐 = 생성 끝. 단, 1.5초 안정화 대기 (깜빡임 방지)
          stoppedStable++;
          if(stoppedStable >= 2){
            log('[답변 대기] ChatGPT 생성 완료');
            // 텍스트가 있으면 텍스트 반환, 없으면(이미지만) 빈 문자열이 아닌 placeholder 반환
            const final = getLastAssistantText();
            return final || '[이미지 답변]';
          }
        } else {
          stoppedStable = 0;
        }
        continue;
      }
    }
    log('[답변 대기] 타임아웃');
    return last || '[타임아웃]';
  }
  // v21.8.24.16: ChatGPT DOM 감지값 — UI 변경 시 이 블록만 수정 (제8원칙: 셀렉터 하드코딩 금지)
  const CGPT_DETECT = {
    // 생성 중 신호: Stop(중지) 버튼/스트리밍 표시가 있으면 ChatGPT가 아직 응답/이미지 생성 중
    generating: [
      'button[data-testid="stop-button"]',
      '[data-testid="stop-button"]',
      'button[aria-label*="Stop" i]',
      'button[aria-label*="중지"]',
      'button[aria-label*="스트리밍 중지"]',
      'button[aria-label*="생성 중지"]',
      'button[aria-label*="Stop generating" i]',
      'button[aria-label*="Stop streaming" i]',
      '.result-streaming'
    ],
    // 생성된 이미지 시그니처: id(_r_xxx_)는 매번 바뀌므로 제외. 클래스/위치/blob src로 감지
    generatedImage: [
      'img.w-full[class*="top-0"]',
      'img[class*="absolute"][class*="w-full"]',
      'img[src^="blob:"]'
    ],
    idleStableTicks: 4,       // 생성신호 없음이 연속 4초 = idle 판정
    nextSendGuardMs: 40000,   // 다음 프롬프트 전송 전 idle 대기 최대 시간(타임아웃 시 어차피 전송하므로 과하게 길 필요 없음)
    postDoneCooldownMs: 5000  // 한 섹션 완료 후 다음 전송 전 안정화 쿨다운
  };
  // v21.8.24.27: 생성 안정성 타이밍을 한 곳에서 관리(고급: 프리셋으로 조절). waitForImageAnswerDone가 참조.
  const DP_TIMING = { imgStableTicks: 12, imgMinActiveMs: 25000, genGoneTicks: 6, minWaitMs: 45000, cooldownMs: 5000, idleStableTicks: 4, nextSendGuardMs: 40000 };
  const DP_TIMING_PRESETS = {
    // v21.8.24.61: nextSendGuardMs(전송 전 idle 대기 타임아웃)를 프리셋에 편입 — 이전엔 프리셋과 무관하게 120초 고정이라 '빠름'도 안 빨라졌음.
    fast:     { imgStableTicks: 8,  imgMinActiveMs: 16000, genGoneTicks: 4, minWaitMs: 30000, cooldownMs: 3000,  idleStableTicks: 3, nextSendGuardMs: 25000 },
    balanced: { imgStableTicks: 12, imgMinActiveMs: 25000, genGoneTicks: 6, minWaitMs: 45000, cooldownMs: 5000,  idleStableTicks: 4, nextSendGuardMs: 40000 },
    safe:     { imgStableTicks: 16, imgMinActiveMs: 35000, genGoneTicks: 8, minWaitMs: 55000, cooldownMs: 12000, idleStableTicks: 7, nextSendGuardMs: 90000 }
  };
  function applyTimingPreset(name){
    const p = DP_TIMING_PRESETS[name] || DP_TIMING_PRESETS.balanced;
    Object.assign(DP_TIMING, p);
    CGPT_DETECT.idleStableTicks = p.idleStableTicks;
    CGPT_DETECT.postDoneCooldownMs = p.cooldownMs;
    if(p.nextSendGuardMs) CGPT_DETECT.nextSendGuardMs = p.nextSendGuardMs;
  }
  function cgptQueryAll(selList, root){ root = root || document; const out = []; (selList || []).forEach(function(s){ try{ root.querySelectorAll(s).forEach(function(el){ out.push(el); }); }catch(_){} }); return out; }
  function cgptHasAny(selList, root){ root = root || document; return (selList || []).some(function(s){ try{ return !!root.querySelector(s); }catch(_){ return false; } }); }

  function countAssistantNodes(){
    return document.querySelectorAll('[data-message-author-role="assistant"]').length;
  }
  function getAssistantNodes(){
    const nodes=[...document.querySelectorAll('[data-message-author-role="assistant"]')];
    if(nodes.length) return nodes;
    return [...document.querySelectorAll('.markdown.prose, article')];
  }
  function countAssistantImageLikeNodes(){
    // v21.8.24.14: assistant 노드 한정 제거 → 대화영역 전체에서 생성 이미지 신호로 감지
    // (생성 이미지가 assistant 컨테이너 밖에 렌더되거나 동적 id를 쓰는 케이스 대응)
    const root = document.querySelector('main') || document.body;
    const seen = new Set();
    let count = 0;
    const candidates = cgptQueryAll(CGPT_DETECT.generatedImage, root);
    root.querySelectorAll('img, picture, canvas').forEach(el => candidates.push(el));
    candidates.forEach(el => {
      if(seen.has(el)) return;
      const cls = (el.getAttribute && el.getAttribute('class')) || '';
      const src = (el.getAttribute && el.getAttribute('src')) || '';
      const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
      const w = el.naturalWidth || (rect ? rect.width : 0) || 0;
      const h = el.naturalHeight || (rect ? rect.height : 0) || 0;
      const isGenSig = /\bw-full\b/.test(cls) && (/\babsolute\b/.test(cls) || /\btop-0\b/.test(cls));
      const isBlobImg = src.indexOf('blob:') === 0; // 생성 이미지는 blob: URL (data:는 아이콘이라 제외)
      const bigEnough = (w >= 200 || h >= 200) || el.tagName === 'CANVAS';
      // 아이콘/아바타 같은 작은 요소는 제외하고, 실제 생성 이미지 후보만 센다.
      if(isGenSig || isBlobImg || bigEnough){ seen.add(el); count++; }
    });
    return count;
  }
  function getLatestGeneratedImage(){
    // 대화영역에서 가장 마지막(최신) 생성 이미지 후보 반환
    const root = document.querySelector('main') || document.body;
    const imgs = [];
    cgptQueryAll(CGPT_DETECT.generatedImage, root).forEach(el => imgs.push(el));
    root.querySelectorAll('img').forEach(el => {
      const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
      const w = el.naturalWidth || (rect ? rect.width : 0) || 0;
      const h = el.naturalHeight || (rect ? rect.height : 0) || 0;
      if(w >= 200 || h >= 200) imgs.push(el);
    });
    return imgs.length ? imgs[imgs.length - 1] : null;
  }
  function imageSig(el){
    // 이미지의 src + 로드완료여부 + 실제 픽셀크기 → 내용이 바뀌면 시그니처도 바뀜
    if(!el) return '';
    const src = (el.getAttribute && el.getAttribute('src')) || el.currentSrc || '';
    const complete = el.complete ? '1' : '0';
    const w = el.naturalWidth || 0, h = el.naturalHeight || 0;
    return src + '|' + complete + '|' + w + 'x' + h;
  }
  async function waitForImageAnswerDone(before='', timeout=300000){
    const start = Date.now();
    const beforeAssistantCount=countAssistantNodes();
    const beforeImageCount=countAssistantImageLikeNodes();
    // v21.8.24.64: 직전 섹션 이미지를 '이번 새 이미지'로 오인해 조기 완료하던 버그 수정용 기준선.
    const beforeLastSig=imageSig(getLatestGeneratedImage());
    // v21.8.24.27: 안정성 프리셋(고급 설정)에서 조절 가능한 타이밍 값 사용
    const minWaitMs = DP_TIMING.minWaitMs;       // 이미지 감지 실패 시 블라인드 최소 대기
    const IMG_STABLE_TICKS = DP_TIMING.imgStableTicks;   // 최신 이미지가 N초 연속 '동일'해야 완료로 인정
    const IMG_MIN_ACTIVE_MS = DP_TIMING.imgMinActiveMs;  // 생성 시작 후 최소 N초는 완료 판정 금지
    const GEN_GONE_TICKS = DP_TIMING.genGoneTicks;       // 생성신호가 연속 N초 사라져야 완료 인정
    let phase='wait_start';
    let imageSeen=false;
    let genEverSeen=false;   // 실제 생성 사이클을 한 번이라도 관측했는가(이전 섹션 정지 이미지 오판 방지)
    let genGoneTicks=0;      // 생성신호가 사라진 뒤 연속 경과 틱
    let stableTicks=0;
    let lastImageCount=beforeImageCount;
    let lastImageSig='';
    let imgStableTicks=0;
    let startedAt=0;
    let lastText='';

    while(Date.now() - start < timeout){
      await sleep(1000);
      const gen=isGenerating();
      const cur=getLastAssistantText();
      const assistantCount=countAssistantNodes();
      const imageCount=countAssistantImageLikeNodes();
      const newAssistantNode=assistantCount > beforeAssistantCount;
      const newImage=imageCount > beforeImageCount;
      // v21.8.24.64: '이미지 생성 중' 플레이스홀더가 떠 있으면 정지버튼이 잠깐 사라져도 아직 생성 중으로 간주.
      const genPlaceholder=/이미지\s*생성\s*중|이미지를?\s*(만들고|생성하고)|creating image|generating image/i.test(cur||'');
      const genNow=gen||genPlaceholder;

      // 생성신호 관측 추적: 한 번이라도 gen이 떠야 진짜 생성으로 인정, 사라진 뒤 연속 틱을 센다.
      if(genNow){ genEverSeen=true; genGoneTicks=0; } else { genGoneTicks++; }

      if(phase === 'wait_start'){
        if(genNow || newAssistantNode || newImage || (cur && cur !== before)){
          phase='generating';
          startedAt=Date.now();
          log('[답변 대기] ChatGPT 이미지 생성 시작 감지');
        } else if(Date.now()-start > 20000){
          // 시작 신호가 늦는 경우에도 곧바로 완료 처리하지 않고 계속 대기한다.
          startedAt=startedAt || Date.now();
          phase='generating';
          log('[답변 대기] 이미지 생성 시작 신호 지연 → 실제 이미지 완료 대기');
        }
        continue;
      }

      if(cur && cur !== lastText){ lastText=cur; }

      // (A) 최신 이미지 내용 안정도: 미리보기→선명 전환이 끝나야 시그니처가 멈춤
      const latestImg=getLatestGeneratedImage();
      const sig = imageSig(latestImg);
      // v21.8.24.64: 시작 기준선(beforeLastSig)과 다른 = 이번 섹션에서 새로 생성된 이미지일 때만 imageSeen 인정.
      // (이전 섹션 이미지가 blob/안정 상태로 남아 있어도 새 이미지로 오인하지 않는다.)
      const isNewLatest = !!sig && sig !== beforeLastSig;
      if(newImage || isNewLatest) imageSeen=true;
      if(sig){
        if(sig === lastImageSig) imgStableTicks++;
        else { imgStableTicks = 0; lastImageSig = sig; }
      } else { imgStableTicks = 0; }
      // 완료 안정 틱은 '새 이미지'에 대해서만 유효 — 아직 직전 이미지(기준선)와 같으면 완료에 쓰지 않는다.
      const stableOnNew = isNewLatest && imgStableTicks >= IMG_STABLE_TICKS;

      // (B) 이미지 감지 실패 대비용: 개수 안정도(아래 블라인드 fallback에서만 사용)
      if(imageCount === lastImageCount) stableTicks++;
      else { stableTicks=0; lastImageCount=imageCount; }

      const elapsedFromStart = Date.now() - (startedAt || start);
      const genSettled = !genNow && genGoneTicks >= GEN_GONE_TICKS; // 생성신호가 충분히 오래 사라짐

      // 정상 완료: 실제 생성 관측됨 + 이번 섹션의 새 이미지 떴음 + 생성신호 충분히 사라짐 + 새 이미지가 오래 '그대로' + 최소 시간 경과
      if(genEverSeen && imageSeen && genSettled && stableOnNew && elapsedFromStart >= IMG_MIN_ACTIVE_MS){
        log('[답변 대기] ChatGPT 이미지 생성 완료');
        return getLastAssistantText() || '[이미지 답변]';
      }

      // 블라인드 fallback 1: 생성은 관측됐는데 이미지 DOM을 못 잡은 경우(UI 변경 대비)
      if(genEverSeen && !imageSeen && genSettled && elapsedFromStart >= minWaitMs && stableTicks >= 10){
        log('[답변 대기] 이미지 결과 DOM 직접 감지 실패 → 생성 종료/안정화 후 완료로 처리');
        return getLastAssistantText() || '[이미지 답변]';
      }

      // 블라인드 fallback 2: 생성신호 자체를 끝내 못 잡은 경우(셀렉터 불일치)만, 매우 보수적으로 — 단 '새 이미지'가 안정됐을 때만
      if(!genEverSeen && elapsedFromStart >= minWaitMs && stableOnNew && stableTicks >= 10){
        log('[답변 대기] 생성신호 미감지 → 이미지/개수 안정화 기준으로 완료 처리');
        return getLastAssistantText() || '[이미지 답변]';
      }
    }
    log('[답변 대기] 이미지 생성 타임아웃');
    return getLastAssistantText() || '[타임아웃]';
  }
  function isGenerating(){ return cgptHasAny(CGPT_DETECT.generating); }
  async function waitUntilChatIdle(timeout){
    // v21.8.24.14: 다음 프롬프트를 보내기 전, ChatGPT가 완전히 멈출 때까지 대기.
    // 생성 신호(Stop 버튼)가 없는 상태가 연속으로 유지돼야 idle로 판정 → 생성 중 전송 방지.
    timeout = timeout || CGPT_DETECT.nextSendGuardMs;
    const start = Date.now();
    let idleTicks = 0;
    while(Date.now() - start < timeout){
      if(!isGenerating()) idleTicks++; else idleTicks = 0;
      if(idleTicks >= CGPT_DETECT.idleStableTicks) return true;
      await sleep(1000);
    }
    log('[안정화] ChatGPT가 계속 응답 중 → 대기 타임아웃, 다음 단계 진행');
    return false;
  }
  function getLastAssistantText(){ const nodes=getAssistantNodes(); if(!nodes.length) return ''; const txt=nodes[nodes.length-1].innerText?.trim()||''; return txt; }

  // v21.8.24.16: 구버전 결과탭 UI(dp-tabs/dp-result/dp-image-prompt-status) 제거에 따라
  // 더 이상 호출되지 않던 결과 파서/렌더 함수(renderTabs/setResult/renderResult/extractByTag/
  // extractSection/extractAndShowImagePrompts/parseImagePrompts/renderImagePromptStatus)를 정리했습니다.
  // 섹션별 이미지 프롬프트는 buildShortImagePrompts() 경로만 사용합니다.

  function buildShortImagePrompts(showLog=true){
    const d=getData();
    if(!state.inferred) runLocalInference(false);

    let result = null;
    try{
      result = window.DP_DYNAMIC_PROMPTS?.generateDynamicPrompts
        ? window.DP_DYNAMIC_PROMPTS.generateDynamicPrompts({
            data: d,
            inferred: state.inferred,
            getPlatformRatio,
            sectionCount: (d.sections||'8').trim(),
            masterBrief: state.masterBrief || '',
            copyPlan: state.copyPlan || '',
            refStyle: state.refStyle || '',
            heroLockFromIndex: 1,
            designMood: (d.mood||'auto').trim()
          })
        : null;
    }catch(e){
      console.error('dynamic prompt generator failed', e);
      result = null;
    }

    if(!result || !Array.isArray(result.prompts) || !result.prompts.length){
      log('동적 프롬프트 생성기가 로드되지 않아 기본 프롬프트 생성을 중단했습니다.');
      state.shortImagePrompts=[];
      renderShortPromptStatus();
      return [];
    }

    state.inferred = Object.assign({}, state.inferred||{}, result.analysis||{});
    const userRatio = (d.ratio||'auto').trim();
    const platform = (d.platform||'').trim();
    result.prompts.forEach(p=>{
      let targetRatio = p.ratio || '4:5';
      if(userRatio && userRatio !== 'auto'){
        targetRatio = userRatio;
      } else if(platform){
        targetRatio = getPlatformRatio(platform, p.title);
      }
      p.prompt = String(p.prompt||'').replace(/비율:?\s*[0-9]+:[0-9]+\s*\./g, `비율 ${targetRatio}.`);
      p.ratio = targetRatio;
    });

    state.shortImagePrompts=result.prompts;
    state.lastDesignLabel=result.design?.label||'';
    state.currentShortImageIndex=0;
    initSectionStatus();
    renderInference();
    renderShortPromptStatus();
    const ratioInfo = userRatio==='auto' ? `플랫폼 자동 (${platform||'기본'})` : userRatio;
    const briefInfo = state.masterBrief ? '✅브리프' : '브리프없음';
    const planInfo = state.copyPlan ? '✅기획서' : '';
    const refInfo = result.hasRef ? '🎨레퍼런스' : '';
    const toneInfo = result.variation?.name ? `톤:${result.variation.name}` : '';
    const userMoodPicked = (d.mood||'auto').trim() !== 'auto';
    const moodInfo = result.hasRef ? '무드:레퍼런스우선' : (result.design?.label ? `${userMoodPicked?'사용자선택 무드강제':'자동무드'}:${result.design.label}` : '');
    const involveInfo = result.analysis?.involvement==='low' ? '관여도:저관여(사회적증거형)' : '관여도:고관여(스토리형)';
    if(showLog) log(`v21.8 프롬프트 ${result.prompts.length}개 · ${result.analysis?.category_group||'자동'} · ${involveInfo} · ${moodInfo} · ${refInfo} · ${briefInfo} · ${planInfo} · ${toneInfo} · 비율: ${ratioInfo}`);
    return result.prompts;
  }

  function renderShortPromptStatus(){
    renderStatusDash();
    const box=$('dp-short-prompt-status');
    if(!box) return;
    if(!state.shortImagePrompts?.length){
      box.textContent='아직 섹션별 프롬프트가 없습니다. [섹션별 프롬프트 생성]을 누르세요.';
      return;
    }
    box.textContent=state.shortImagePrompts.map((x,i)=>`${i+1}. ${x.title}\n${x.ratio}\n${x.prompt.slice(0,360)}${x.prompt.length>360?'...':''}`).join('\n\n');
  }

  // v21.1: 이미지 자동 첨부 - 첨부 안 돼있으면 자동으로 ChatGPT에 첨부 (버튼 수동 클릭 불필요)
  async function ensureImagesAttached(){
    // 패널에 선택된 이미지가 없으면 첨부할 게 없음 (사용자가 ChatGPT에 직접 올렸을 수 있음 → 통과)
    if(!state.images.length){
      attachLog('[첨부 0/7] 패널 선택 이미지 없음 → 첨부 단계 생략');
      return true;
    }

    const manualChecked = !!$('dp-images-attached')?.checked;
    if(manualChecked){
      state.attachmentVerified = true;
      attachLog('[첨부 0/7] 사용자가 "ChatGPT에 원본 이미지를 이미 첨부했습니다"를 체크함 → 자동 첨부 생략');
      return true;
    }

    // v21.8.3: 기존 첨부 감지 오판 방지.
    // 체크박스가 꺼져 있고 패널 이미지가 있으면 무조건 자동 첨부를 시도한다.
    // 이전 버전은 입력창 주변 아이콘/이전 이미지/확장 아이콘을 첨부로 오인해 실제 첨부를 건너뛰는 문제가 있었다.
    if(state.attachmentVerified){
      attachLog('[첨부 0/7] 이번 세션에서 이미 ChatGPT 입력창 첨부 확인됨 → 자동 첨부 생략');
      return true;
    }

    clearAttachLog();
    attachLog(`[첨부 1/7] 패널 선택 이미지: ${state.images.length}개 · ${state.images.map(x=>x.name).join(', ')}`);
    log('📎 선택한 원본 이미지를 ChatGPT 입력창에 자동 첨부 중...');

    try{
      const files=state.images.map(x=>x.file).filter(Boolean);
      attachLog(`[첨부 2/7] File 객체 확인: ${files.length}/${state.images.length}개`);
      if(files.length !== state.images.length){
        attachLog('[첨부 실패] 패널 미리보기는 있지만 실제 File 객체가 부족합니다. 이미지를 다시 선택하세요.');
        return false;
      }

      const ok=await attachFilesToComposer(files);
      attachLog(`[첨부 6/7] 파일 주입/붙여넣기 시도 결과: ${ok?'성공 신호':'실패 신호'}`);
      if(!ok){
        state.chatFilesUploaded=false; state.attachmentVerified=false;
        if($('dp-images-attached')) $('dp-images-attached').checked=false;
        const status=$('dp-upload-status');
        if(status) status.textContent='자동 첨부 실패: ChatGPT 입력창 + 버튼 → 사진 및 파일 추가로 직접 첨부해 주세요.';
        log('⚠️ 자동 첨부 실패. 패널 이미지는 선택되어 있지만 ChatGPT 입력창에는 아직 올라가지 않았습니다. 아래 첨부 디버그 로그를 확인하세요.');
        attachLog('[첨부 실패] 자동 첨부 함수가 성공 신호를 반환하지 못했습니다.');
        return false;
      }

      const verified=await waitForAttachmentVerification(state.images.map(x=>x.name), 15000);
      state.chatFilesUploaded=verified; state.attachmentVerified=verified;
      if($('dp-images-attached')) $('dp-images-attached').checked=verified;
      const status=$('dp-upload-status');
      if(status) status.textContent=verified?'첨부 확인 완료: ChatGPT 입력창에 원본 이미지가 감지되었습니다.':'첨부 확인 실패: ChatGPT 입력창에 이미지 썸네일이 보이는지 확인해 주세요.';
      if(verified){ attachLog('[첨부 7/7] ChatGPT 입력창 첨부 썸네일 확인: 성공'); log('✅ 원본 이미지 자동 첨부 완료'); return true; }
      // v21.8.24.45: 파일 주입은 성공했는데 썸네일만 자동 감지 실패한 경우 → 흐름을 막지 않고 진행한다.
      // (ChatGPT UI 변경으로 썸네일 위치를 못 찾는 경우가 많아, 차단하면 자동제작이 통째로 멈춤)
      state.chatFilesUploaded=true; state.attachmentVerified=true;
      if($('dp-images-attached')) $('dp-images-attached').checked=true;
      if(status) status.textContent='첨부 주입 완료(썸네일 자동확인은 실패). ChatGPT 입력창에 이미지가 보이는지 확인하고, 안 보이면 +버튼으로 직접 올려주세요.';
      attachLog('[첨부 7/7] 썸네일 자동 감지 실패했지만 파일 주입은 성공 → 진행(감지기 한계 가능).');
      log('⚠️ 첨부 썸네일 자동확인엔 실패했지만 파일 주입은 성공해 계속 진행합니다. (이미지가 안 올라갔다면 ChatGPT +버튼으로 직접 첨부 후 다시 실행하세요)');
      return true;
    }catch(e){ attachLog('[첨부 오류] '+(e?.message||e)); log('자동 첨부 오류: '+(e?.message||e)); return false; }
  }

  function buildImageGenerationRequest(item, idx=0, total=0){
    const raw = String(item?.prompt || '').trim();
    // v21.8.24.54: 머리글·[규칙]에 이미 '이미지만 생성'과 '비율'이 있어 꼬리말 중복 제거(프롬프트 길이 축소).
    return `${raw}

(${idx+1}${total?`/${total}`:''}번째 섹션)`;
  }

  async function createShortImageByIndex(idx){
    if(!state.shortImagePrompts?.length) buildShortImagePrompts(false);
    if(!state.shortImagePrompts.length){ log('짧은 이미지 프롬프트가 없습니다.'); return; }
    if(idx>=state.shortImagePrompts.length){ log('짧은 이미지 프롬프트를 모두 사용했습니다.'); return; }
    setBusy(true);
    try{
      const item=state.shortImagePrompts[idx];
      // v21.1: 첨부 안 돼있으면 자동 첨부 (버튼 수동 클릭 불필요). 첫 섹션에서만 첨부 필요
      const attached = await ensureImagesAttached();
      if(!attached){
        log('⚠️ 이미지 첨부 실패로 섹션 이미지 생성을 중단했습니다. 아래 첨부 디버그 로그를 확인하세요.');
        return;
      }
      state.currentShortImageIndex=idx;
      // v21.8.10: 모드 시도만, 실패해도 진행
      const modeOk=await tryOpenImageMode();
      if(modeOk) log('[이미지 모드] 활성화 성공');
      else log('[이미지 모드] 활성화 실패 - 프롬프트로 이미지 생성 진행');
      const imageRequest=buildImageGenerationRequest(item, idx, state.shortImagePrompts.length);
      const ok=await setPromptText(imageRequest);
      if(!ok){ await navigator.clipboard.writeText(imageRequest); log('입력창을 찾지 못해 이미지 생성 요청을 복사했습니다.'); return; }
      await sleep(300);
      const sent=await clickSendButton();
      if(sent) log(`${idx+1}번 섹션 이미지 생성 요청을 ${modeOk?'이미지 만들기 모드에':'입력창에'} 넣고 전송했습니다.`);
      else log(`${idx+1}번 섹션 이미지 생성 요청은 입력창에 준비됐지만 전송이 확인되지 않았습니다. 검은 화살표를 직접 눌러주세요.`);
    }catch(e){
      console.error(e);
      log('섹션 이미지 만들기 실행 중 오류: '+(e?.message||e));
    }finally{
      setBusy(false);
    }
  }

  // ===== v21.0 이식: 마스터 브리프 (STAGE 0) =====
  async function buildMasterBrief(){
    const d=getData();
    const product=(d.product||'').trim() || '첨부한 원본 제품';
    const tone=(d.tone||'전환 중심').trim();
    const benefits=(d.benefits||'').trim();
    const target=(d.target||'').trim();
    const category=(d.category||'').trim();
    const price=(d.price||'').trim();
    const specs=(d.specs||'').trim();
    const specInstruction=buildSpecInstructionBlock(specs);
    if(state.images.length && !(state.attachmentVerified || $('dp-images-attached')?.checked)){
      attachLog('[진행 중단] 1단계 제품진단 실행 전 자동첨부 확인 또는 사용자의 직접 첨부 체크가 없습니다.');
      log('⚠️ 원본 이미지 첨부 확인 안 됨. [상세페이지 자동 만들기]로 자동첨부를 시도하거나, ChatGPT에 직접 첨부 후 체크박스를 켜주세요.');
      return;
    }
    const platform=(d.platform||'').trim();
    const pain=(d.pain||'').trim();
    const briefPrompt = foreignLocalizeBlock(product, specs) + `[상세페이지 제작 1단계 - 제품 진단 및 구매의도 기준 확정]
당신은 한국 이커머스 상세페이지 기획 전문가입니다.

지금부터 첨부한 원본 제품 사진, 상품명, 링크 정보, 사용자가 입력한 정보를 바탕으로 앞으로 만들 상세페이지 전체의 기준을 확정합니다.
절대 단순히 제품 외형이나 스펙만 요약하지 마세요.
상세페이지는 제품 설명서가 아니라 구매 설득 구조입니다.

아래 입력 정보를 기준으로 분석하세요.

상품명:
${product}

카테고리:
${category || '확인 필요'}

판매 플랫폼:
${platform || '확인 필요'}

타겟 고객:
${target || '확인 필요'}

핵심 장점:
${benefits || '확인 필요'}

고객 고민:
${pain || '확인 필요'}

가격대:
${price || '확인 필요'}
${ $('dp-show-price')?.checked ? '' : '\n[가격 표기 금지 - 중요] 가격·금액·할인율·판매가·쿠폰가를 이미지 안 카피(메인/서브/카드/CTA 포함)에 절대 넣지 마세요. 위 가격은 내부 참고용일 뿐, 이미지에는 표기하지 않습니다.\n' }

확인된 스펙/구성:
${specInstruction || '확인 필요'}

첨부 이미지:
원본 제품 사진 또는 기존 상세페이지 이미지

────────────────────
[제품 동일성 - 최우선]
────────────────────
- 이 상세페이지의 진짜 제품은 위 "상품명"과 "확인된 스펙/구성"입니다. 반드시 이것을 기준으로 분석하세요.
- 만약 타겟/장점/고민 등 다른 입력값이 상품명과 명백히 다른 품목(예: 상품명은 'A'인데 다른 칸은 전혀 다른 'B' 제품)을 가리키면, 그 상충 정보는 잔재로 보고 무시한 뒤 "상품명"과 "확인된 스펙"만 따르세요.
- 절대로 상품명과 다른 제품으로 기준을 바꾸지 마세요. 첨부 원본 사진과 상품명이 우선입니다.

────────────────────
[분석 원칙]
────────────────────
1. 원본 제품 사진에서 확인되는 정보와 사용자가 입력한 정보만 확정 정보로 사용하세요.
2. 확인되지 않은 소재, 성능, 인증, 수치, 효과, 구성품은 절대 지어내지 마세요.
3. 상품을 스펙 중심으로 해석하지 말고, 고객이 이 제품을 왜 사는지 중심으로 해석하세요.
4. 고객은 제품 자체를 사는 것이 아니라, 제품이 해결해주는 상황과 결과를 삽니다.
5. 이후 모든 이미지 섹션에서 제품의 색상, 형태, 소재, 구성품, 패키지, 로고, 비율이 일관되게 유지되도록 기준을 잡으세요.
6. 원본 사진에 없는 구성품, 액세서리, 인증마크, 로고, 수상 배지는 추가하지 마세요.
7. 기존 상세페이지나 공급처 이미지는 참고 자료일 뿐입니다. 문구와 레이아웃을 그대로 복사하지 마세요.

────────────────────
[상품군별 해석 기준]
────────────────────
디지털/가전:
CPU, 메모리, 저장공간, 무게 자랑이 아니라 업무, 학습, 콘텐츠 제작, 쇼핑몰 운영, 반복 작업을 더 수월하게 만드는 제품으로 해석하세요. 스펙은 설득의 근거로만 사용합니다.

의류/패션:
색상, 소재, 핏 나열이 아니라 어떤 상황에서 입고, 어떤 고민을 줄이고, 어떤 인상을 만드는지 중심으로 해석하세요.

생활/주방/수납:
크기, 재질 나열이 아니라 정리, 시간 절약, 위생, 공간 문제 해결 중심으로 해석하세요.

뷰티/잡화:
성분, 구성 자랑이 아니라 사용 장면, 루틴, 휴대성, 선물감, 관리 고민 해결 중심으로 해석하세요.

운동/홈트:
강도, 구성품 나열이 아니라 운동을 시작하기 쉬운지, 공간 부담이 적은지, 사용법이 이해되는지 중심으로 해석하세요.

가구/인테리어:
사이즈, 소재 나열이 아니라 공간 분위기, 사용 장면, 배치 후 변화 중심으로 해석하세요.

식품:
원재료, 용량 나열이 아니라 언제 먹고 싶은지, 어떤 상황에서 선택되는지, 선물/간식/식사 대체 등 구매 맥락 중심으로 해석하세요.

────────────────────
[출력 형식 - 반드시 유지]
────────────────────
[상세페이지 기준 확정]

1. 공식 제품명:
상세페이지 전체에서 사용할 제품명 1개

2. 제품 형태 정의:
원본 사진 기준으로 색상, 형태, 구성품, 패키지, 눈에 띄는 디테일을 정리

3. 확인 가능한 스펙:
사용자 입력 또는 원본 자료에서 확인된 스펙만 정리
모르면 "확인 필요"

4. 제품 사실성 잠금:
이미지 생성 시 절대 바꾸면 안 되는 색상, 형태, 소재, 구성품, 로고, 패키지 요소

5. 타겟 고객 한 줄 정의:
이 제품을 가장 살 가능성이 높은 고객을 구체적으로 정의

6. 고객의 실제 구매 상황:
고객이 어떤 순간에 이 제품을 필요로 하는지 설명

7. 고객의 핵심 고민:
구매 전 고객이 느끼는 불편, 걱정, 망설임

8. 구매 버튼을 누르게 만드는 이유:
고객이 이 제품을 선택해야 하는 가장 강한 이유

9. 핵심 셀링포인트 3가지:
각 항목은 아래 형식으로 작성
- 셀링포인트:
- 고객 효익:
- 이미지로 보여줄 방법:
- 근거:

10. 상세페이지 첫 화면에서 반드시 말해야 할 메시지:
HERO 섹션의 방향이 될 한 줄

11. 피해야 할 방향:
스펙 자랑, 과장 표현, 제품 왜곡, 미확인 정보 등 주의점

12. 추천 상세페이지 흐름:
이 제품에 가장 적합한 섹션 흐름을 8개 기준으로 제안

이 결과는 이후 모든 상세페이지 이미지의 기준이 됩니다.
설명문이 아니라 실제 판매 상세페이지 제작 기준으로 작성하세요.`;
    setBusy(true);
    try{
      const beforeText = getLastAssistantText();
      const ok = await setPromptText(briefPrompt);
      if(!ok){ await navigator.clipboard.writeText(briefPrompt); log('입력창을 못 찾아 브리프 프롬프트를 복사했습니다. 직접 붙여넣어 주세요.'); return; }
      // v21.8.15: 제품진단은 이미지 첨부 직후 첫 전송이라 전송 버튼이 늦게 활성화될 수 있음.
      // 공통 clickSendButton()은 다른 자동화 흐름에 영향이 있어 건드리지 않고, 제품진단 단계에서만 준비 대기 + 재시도 처리.
      let sent = false;
      for(let attempt=1; attempt<=3; attempt++){
        for(let wait=0; wait<30; wait++){
          const inputText = getPromptInputText();
          const candidates = getSendButtonCandidates();
          if(inputText && inputText.length > 20 && candidates.length){ break; }
          await sleep(500);
        }
        sent = await clickSendButton(beforeText);
        if(sent) break;
        if(isGenerating()) { sent = true; break; }
        if(attempt < 3){
          log(`⚠️ 제품 진단 전송 확인 실패 → 입력창/첨부 안정화 대기 후 재시도 (${attempt}/3)`);
          if(!getPromptInputText()){ await setPromptText(briefPrompt); }
          await sleep(1500);
        }
      }
      if(!sent){ log('전송 버튼을 못 눌렀습니다. 입력창 오른쪽 아래 검은 화살표를 직접 눌러주세요.'); return; }
      log('📋 1단계 제품 진단 요청 전송 확인 완료. ChatGPT 답변 대기 중...');
      const answer = await waitForNewAssistantText(beforeText, 120000);
      if(answer && answer !== beforeText){
        state.masterBrief = answer; state.briefSig = productSignature(getData()); save(); renderMasterBriefStatus();
        log('✅ 마스터 브리프 확정 완료. 이제 [섹션별 프롬프트 생성]을 누르면 이 기준이 모든 섹션에 적용됩니다.');
      } else {
        if(!saveLatestMasterBriefIfExists('브리프 대기 실패 후 최근 답변')){
          log('⚠️ 브리프 답변 감지 실패. [최근 답변을 브리프로] 버튼을 쓰거나 다시 시도하세요.');
        }
      }
    }catch(e){ console.error(e); log('마스터 브리프 생성 오류: '+(e?.message||e)); }
    finally{ setBusy(false); }
  }
  function saveMasterBriefManual(){
    const t = getLastAssistantText();
    if(t){ state.masterBrief = t; state.briefSig = productSignature(getData()); save(); renderMasterBriefStatus(); log('✅ 최근 ChatGPT 답변을 마스터 브리프로 저장했습니다.'); }
    else { log('⚠️ 최근 ChatGPT 답변을 찾지 못했습니다.'); }
  }

  function isLikelyMasterBriefText(t){
    t=String(t||'');
    if(t.length<120) return false;
    const hasBriefTitle=/상세페이지\s*기준|기준\s*확정|마스터\s*브리프|공식\s*제품명/i.test(t);
    const hasBriefFields=/제품\s*형태|확인\s*가능한\s*스펙|브랜드\s*톤|셀링포인트|타겟\s*고객/i.test(t);
    const isCopyPlan=isLikelyCopyPlanText(t);
    return hasBriefTitle && hasBriefFields && !isCopyPlan;
  }

  function isLikelyCopyPlanText(t){
    t=String(t||'');
    if(t.length<250) return false;
    const hasSections=/\[?섹션\s*1\b|섹션\s*1\s*-|섹션\s*1\s*[–—]/i.test(t);
    const hasCopyFields=/핵심\s*메시지|메인\s*카피|서브\s*카피|근거\/포인트|카피\s*공식/i.test(t);
    const hasPlanTitle=/카피\s*기획서|섹션별\s*카피|상세페이지\s*8개\s*섹션/i.test(t);
    return hasSections && hasCopyFields && hasPlanTitle;
  }

  function getAssistantTextsNewestFirst(){
    const panel=$('dp-director-panel');
    const nodes=[...document.querySelectorAll('[data-message-author-role="assistant"]')]
      .filter(n=>!panel || !panel.contains(n));
    const texts=nodes.map(n=>(n.innerText||n.textContent||'').trim())
      .filter(t=>t && t.length>80);
    if(texts.length) return texts.reverse();

    // fallback: 일부 UI에서 role 속성이 없을 때만 article을 후순위로 검사
    return [...document.querySelectorAll('article')]
      .filter(n=>!panel || !panel.contains(n))
      .map(n=>(n.innerText||n.textContent||'').trim())
      .filter(t=>t && t.length>80)
      .reverse();
  }

  function findLatestAssistantTextByMatcher(matcher, debugLabel){
    const candidates=getAssistantTextsNewestFirst();
    if(debugLabel) log(`[${debugLabel}] assistant 답변 ${candidates.length}개 스캔`);
    for(let i=0;i<candidates.length;i++){
      const t=candidates[i];
      const ok=matcher(t);
      if(debugLabel){
        log(`[${debugLabel}] ${i+1}번 답변(${t.length}자): ${ok?'감지 성공':'형식 불일치'}`);
      }
      if(ok) return t;
    }
    const last=getLastAssistantText();
    if(last && matcher(last)){
      if(debugLabel) log(`[${debugLabel}] 마지막 답변에서 감지`);
      return last;
    }
    return '';
  }

  function saveLatestMasterBriefIfExists(reason='최근 답변'){
    const t=findLatestAssistantTextByMatcher(isLikelyMasterBriefText);
    if(t){
      if(state.masterBrief !== t){
        state.masterBrief=t; state.briefSig = productSignature(getData()); save(); renderMasterBriefStatus();
        log(`✅ ${reason}에서 마스터 브리프를 감지해 저장했습니다.`);
      }
      return true;
    }
    return !!state.masterBrief;
  }

  function saveLatestCopyPlanIfExists(reason='최근 답변', verbose=false){
    const t=findLatestAssistantTextByMatcher(isLikelyCopyPlanText, verbose ? '카피감지' : null);
    if(t){
      if(state.copyPlan !== t){
        state.copyPlan=t; state.planSig = productSignature(getData()); save(); renderCopyPlanStatus();
        log(`[카피저장] copyPlan 저장 완료 (${reason})`);
      }
      return true;
    }
    return !!state.copyPlan;
  }

  function restoreWizardStateFromLatestAnswer(){
    const savedCopy=saveLatestCopyPlanIfExists('화면의 최근 답변');
    const savedBrief=savedCopy ? false : saveLatestMasterBriefIfExists('화면의 최근 답변');
    return savedCopy || savedBrief;
  }
  function clearMasterBrief(){ state.masterBrief=''; save(); renderMasterBriefStatus(); log('마스터 브리프를 초기화했습니다.'); }
  function renderMasterBriefStatus(){
    renderStatusDash();
    const box = $('dp-master-brief-status');
    if(!box) return;
    if(state.masterBrief){
      const preview = state.masterBrief.slice(0, 200);
      box.innerHTML = `<div style="color:#4ade80;font-weight:bold;margin-bottom:4px">✅ 마스터 브리프 적용 중</div><div style="color:#aaa;font-size:11px;line-height:1.5">${esc(preview)}${state.masterBrief.length>200?'...':''}</div>`;
    } else {
      box.innerHTML = `<div style="color:#888">아직 마스터 브리프가 없습니다. [1단계: 제품 진단]을 누르면 제품명/스펙/톤을 확정해 모든 섹션에 일관 적용합니다. (선택, 강력 권장)</div>`;
    }
  }

  // ===== v21.5: 2단계 카피 기획서 (섹션별 메시지/카피를 먼저 전략적으로 확정) =====
  // 손넬 방식: 바로 이미지 만들지 말고, ChatGPT에게 "각 섹션에 무슨 카피를 쓸지" 기획서를 먼저 받음
  // v21.8.24.92: 카피 저장 직후 코드가 직접 검증(중복 헤드라인/포인트, 금지어, 길이, 도망문구) →
  // 위반이 있으면 위반 목록을 지시문으로 넣어 '자동 재기획 1회'. wasReplan 가드로 무한루프 방지.
  async function lintCopyPlanAndAutoReplan(wasReplan){
    try{
      const V = window.DP_DYNAMIC_PROMPTS && window.DP_DYNAMIC_PROMPTS.validateCopyPlanV92;
      if(!V || !state.copyPlan) return;
      const _pd = (typeof getData === 'function') ? getData() : {};
      const v = V(state.copyPlan, (_pd.product || ''));
      if(v.ok){ log(`🧪 카피 자동 검증 통과 (섹션 ${v.sections}개 · 중복/금지어/길이 OK)`); return; }
      log(`🧪 카피 자동 검증: ${v.violations.length}건 발견`);
      v.violations.slice(0, 6).forEach(x => log('  · ' + x));
      if(v.violations.length > 6) log(`  · …외 ${v.violations.length - 6}건`);
      if(wasReplan){ log('⚠️ 자동 재기획 후에도 일부 위반이 남았습니다 — 그대로 진행합니다(이미지 단계 검수가 한 번 더 거릅니다).'); return; }
      log('🔁 위반 사항을 지시문으로 넣어 자동 재기획 1회 실행...');
      await buildCopyPlan('직전 기획서에서 아래 문제만 정확히 고치고, 나머지는 유지한 채 같은 출력 형식으로 전체 기획서를 다시 작성하세요:\n- ' + v.violations.join('\n- '));
    }catch(e){ console.warn('카피 린트 오류', e); }
  }

  async function buildCopyPlan(directive=''){
    if(typeof directive !== 'string') directive = ''; // 이벤트 객체 등 비문자 유입 방어
    const d=getData();
    const product=(d.product||'').trim() || '첨부한 원본 제품';
    const tone=(d.tone||'전환 중심').trim();
    const target=(d.target||'').trim();
    const pain=(d.pain||'').trim();
    const benefits=(d.benefits||'').trim();
    const specs=(d.specs||'').trim();
    const specInstruction=buildSpecInstructionBlock(specs);
    const sections=(d.sections||'8').trim();
    if(state.images.length && !(state.attachmentVerified || $('dp-images-attached')?.checked)){
      attachLog('[진행 중단] 1단계 제품진단 실행 전 자동첨부 확인 또는 사용자의 직접 첨부 체크가 없습니다.');
      log('⚠️ 원본 이미지 첨부 확인 안 됨. [상세페이지 자동 만들기]로 자동첨부를 시도하거나, ChatGPT에 직접 첨부 후 체크박스를 켜주세요.');
      return;
    }
    const briefRef = state.masterBrief ? `\n[1단계에서 확정한 제품 기준 - 반드시 반영]\n${state.masterBrief}\n` : '';
    const planPrompt = foreignLocalizeBlock((d.product||''), specs) + `[상세페이지 제작 2단계 - 섹션별 구매전환 카피 기획서]
당신은 한국 이커머스 상위 1% 상세페이지 카피 전략가입니다.

지금부터 이미지를 만들기 전에, 이 상품의 상세페이지 각 섹션에 들어갈 이미지 안 문구를 먼저 기획합니다.
목표는 예쁜 문장이 아니라 구매자가 상세페이지를 보며 갖는 질문에 순서대로 답하는 것입니다.${directive ? `\n\n⚠️[이번 재기획 강조 지시 - 최우선]\n${directive}` : ''}

절대 스펙 나열형 카피를 만들지 마세요.
고객은 숫자, 소재, 구성품 자체를 사는 것이 아니라 그 제품으로 해결되는 상황과 결과를 삽니다.

────────────────────
[1단계 제품 기준]
────────────────────
${state.masterBrief ? state.masterBrief : '아직 1단계 마스터 브리프가 없습니다. 사용자 입력과 확인된 스펙만 기준으로 기획하세요.'}

────────────────────
[사용자 입력]
────────────────────
상품명:
${product}

카테고리:
${(d.category || state.inferred?.category_group || state.inferred?.category || '확인 필요')}

판매 플랫폼:
${(d.platform || '쿠팡')}

타겟:
${target || state.inferred?.target || '확인 필요'}

고객 고민:
${pain || state.inferred?.pain || '확인 필요'}

핵심 장점:
${benefits || state.inferred?.benefits || '확인 필요'}

확인된 스펙/구성:
${specs || state.inferred?.specs || '확인 필요'}

톤:
${tone}

섹션 개수:
${sections}

────────────────────
[출력 개수 규칙 - 매우 중요]
────────────────────
1. 섹션 개수가 ${sections}개라면 반드시 ${sections}개 섹션만 작성하세요.
2. 요청된 개수보다 많이 쓰거나 적게 쓰지 마세요.
3. 5컷이면 HERO → PROBLEM → SOLUTION → DETAIL/TRUST → CTA 흐름을 우선 추천하세요.
4. 6컷이면 HERO → PROBLEM → SOLUTION → USP → DETAIL/TRUST → CTA 흐름을 우선 추천하세요.
5. 8컷이면 HERO → PROBLEM → SOLUTION → USP → BENEFIT/SCENE → DETAIL → TRUST/FAQ → CTA 흐름을 우선 추천하세요.
6. 사용자가 입력한 섹션 수와 상품 특성을 기준으로 가장 설득력 있는 흐름을 구성하세요.

${(window.DP_DYNAMIC_PROMPTS && window.DP_DYNAMIC_PROMPTS.COPY_TONE_RULES) ? window.DP_DYNAMIC_PROMPTS.COPY_TONE_RULES + '\n\n' : ''}${(window.DP_DYNAMIC_PROMPTS && window.DP_DYNAMIC_PROMPTS.COPY_BESTSELLER_RULES) ? window.DP_DYNAMIC_PROMPTS.COPY_BESTSELLER_RULES + '\n\n' : ''}${(window.DP_DYNAMIC_PROMPTS && window.DP_DYNAMIC_PROMPTS.COPY_MESSAGE_MAP_RULES) ? window.DP_DYNAMIC_PROMPTS.COPY_MESSAGE_MAP_RULES + '\n\n' : ''}${(window.DP_DYNAMIC_PROMPTS && window.DP_DYNAMIC_PROMPTS.COPY_SECTION_STRUCTURE_RULES) ? window.DP_DYNAMIC_PROMPTS.COPY_SECTION_STRUCTURE_RULES + '\n\n' : ''}${(window.DP_DYNAMIC_PROMPTS && window.DP_DYNAMIC_PROMPTS.COPY_HOOK_RULES) ? window.DP_DYNAMIC_PROMPTS.COPY_HOOK_RULES + '\n\n' : ''}${(window.DP_DYNAMIC_PROMPTS && window.DP_DYNAMIC_PROMPTS.COPY_QUALITY_RULES) ? window.DP_DYNAMIC_PROMPTS.COPY_QUALITY_RULES + '\n\n' : ''}────────────────────
[카피 작성 최우선 원칙]
────────────────────
1. 각 섹션은 서로 다른 구매자 질문에 답해야 합니다.
2. 같은 메시지를 반복하지 마세요.
3. 스펙은 주인공이 아니라 설득의 근거입니다.
4. 스펙·수치를 '여러 개 나열'하지 마세요. 단, 이 상품군의 대표 수치 하나(예: 우산 "126cm 대형"·"8K 방풍")가 확인됐다면 HERO/USP 헤드라인의 후크로 키워도 됩니다(한 섹션 = 한 숫자).
5. 메인 카피는 고객이 얻는 결과, 줄어드는 고민, 시작 가능한 일을 보여줘야 합니다.
6. 모든 카피는 모바일에서 3초 안에 읽히는 짧은 문장이어야 합니다.
7. 확인되지 않은 효능, 인증, 수치, 후기, 구성품은 절대 만들지 마세요.
8. 과장 광고처럼 보이는 표현은 피하세요.
9. 제품을 좋아 보이게 하는 것보다 “왜 이 제품이어야 하는지”가 보여야 합니다.
10. 이미지 안 문구로 그대로 들어갈 수 있게 짧고 강하게 작성하세요.
11. 리뷰 수, 별점, 판매량, 인증, 수상, 소재명, 전체 사이즈 범위는 사용자 입력/링크/원본 이미지에서 명확히 확인된 경우에만 사용하세요.
12. 특정 사이즈나 옵션 하나만 확인된 경우 그것을 전체 사이즈 기준처럼 단정하지 마세요.
13. "상세페이지 참조", "상세페이지 정보 참조", "상품페이지 참고", "판매 페이지 확인", "확인 필요", "미확인" 같은 문구는 이미지 안 카피로 절대 작성하지 마세요.
14. 정보가 부족한 항목은 억지로 채우지 말고, 확인 가능한 착용컷/형태/색상/라인/구성/사용 상황 중심으로 바꾸세요.
15. [브릿지 카피] 각 섹션의 마지막 문구(서브 또는 카드)는 다음 섹션으로 자연스럽게 이어지는 '다리'가 되게 하세요. 단절형("우리 제품이 답입니다")이 아니라 연결형으로(예: "지금 ○○ 신호를 보내고 있습니다" → 다음 섹션의 근거로 이어짐). 섹션을 따로따로 끝내지 마세요.
16. [카테고리 핵심 속성 필수] 이 상품군에서 고객이 가장 궁금해하는 핵심 속성은 반드시 포함하세요(화장품=텍스처·사용감, 의류=핏·소재, 식품=맛·식감, 잡화/케이스=수납·휴대감, 디지털/무형=구성·결과). 이 핵심 속성이 통째로 빠지면 실패입니다.

────────────────────
[저품질 카피 금지]
────────────────────
아래 표현은 메인 카피, 서브 카피, 카드 헤드에서 단독으로 사용하지 마세요.

금지어:
깔끔한, 고급스러운, 편리한, 효율적인, 스마트한, 프리미엄, 완벽한, 최고의, 강력한, 선택 포인트, 구매 기준, 확인 스펙, 숫자로 보는, 한눈에, 시작점, 운영 환경, 기준으로 확인

추가 금지어:
AI 마케팅용, 구성 안내, 대표 제품 소개, 고를 땐, 스펙으로 확인, 필요한 근거만 정리, 망설임보다 확인이 먼저, 상세페이지 참조, 상세페이지 정보 참조, 상품페이지 참고, 판매 페이지 확인, 확인 필요, 미확인

진부어(클리셰) 금지 — 이미지 생성 단계와 통일:
첫인상, 단정함, 비즈니스 무드, 깔끔한 인상, 다양한 활용, 편안한 사용감, 데일리 아이템, 추천템, 만족도 높은 제품, 부담 없이 사용, 활용도 높은
→ 위 표현 대신 실제 장면으로 바꾸세요. 예: "꺼내는 순간", "전달의 순간", "정돈된 형태", "업무 자리", "출근 가방 속".

대체 방향:
- 실제 사용 상황
- 고객이 느끼는 불편
- 구매 후 달라지는 장면
- 확인된 제품 디테일
- 고객이 망설이는 이유를 해소하는 문장

나쁜 예:
"강력한 성능"
"깔끔한 디자인"
"확인된 스펙"
"스마트한 선택"
"숫자로 보는 구매 기준"
"16GB와 512GB가 맞는지 보세요"

좋은 예:
"여러 창을 켜도 작업 흐름 그대로"
"여름 외출 전, 팔 타는 걱정부터 줄이세요"
"꺼내고, 걸고, 바로 운동하세요"
"작은 가방에도 부담 없는 수납감"
"홍보가 밀릴 때, 작업 순서부터 잡으세요"

────────────────────
[상품 정보 무결성 규칙]
────────────────────
1. 확인되지 않은 리뷰 수, 별점, 판매량, 인증, 수상, 소재명, 전체 사이즈 범위는 절대 쓰지 마세요.
2. "상세페이지 참조", "상세페이지 정보 참조", "상품페이지 참고", "확인 필요", "미확인"은 실제 이미지 문구로 쓰면 실패입니다.
3. 상품 정보가 부족하면 그 항목을 빼고, 원본 사진에서 보이는 착용컷, 핏, 색상, 라인, 구성, 사용 상황 중심으로 바꾸세요.
4. 특정 옵션 하나만 확인되면 전체 옵션처럼 단정하지 말고, 필요한 경우 해당 옵션은 내부 근거로만 사용하세요.
5. 사이즈/소재/후기/별점/옵션은 링크 또는 사용자 입력에 명확히 있을 때만 카드 문구로 사용하세요.

────────────────────
[섹션별 역할]
────────────────────
HERO:
고객이 왜 멈춰서 봐야 하는지 1초 안에 보여주세요.
메인 카피는 기능 설명("걸어두기 쉬운 우산", "간편한 OO")이 아니라 욕구·이득·호기심을 건드리는 '한 방'이어야 합니다.
좋은 예: "비 올 때마다 걸 곳이 없었다면", "우산도 걸어두는 시대". 나쁜 예: "걸어두기 쉬운 우산"(밋밋한 기능 설명).
상품명·스펙명·모델명을 메인 카피로 쓰지 말고, 고객이 달라지는 순간/장면을 크게 던지세요.

PROBLEM:
바디는 'WHY 흐름'으로 시작하세요 — 다짜고짜 장점 나열 금지.
① 고객이 속으로 던지는 질문/고민 한 줄(예: "아무거나 사도 괜찮을까?") → ② 그 불편이 생기는 원인 → ③ "그래서 이 제품으로 해결"로 자연스럽게 잇기.
사양 설명이 아니라 생활/업무/착용/사용 상황의 막힘을 고객 언어로 보여주세요.

SOLUTION:
이 제품이 그 불편을 어떻게 줄여주는지 말하세요.
“그래서 이 제품이 필요하다”는 전환점이 되어야 합니다.

USP:
비슷한 제품과 다른 이유를 보여주세요.
흔한 장점이 아니라 선택 이유로 바꿔야 합니다.

BENEFIT / SCENE:
구매 후 고객이 얻게 되는 장면을 보여주세요.
제품이 있는 일상을 상상하게 만드세요.

DETAIL:
소재, 구성, 기능, 마감, 스펙은 고객 효익으로 번역하세요.
단순 나열 금지.
확인된 수치와 구성은 이 섹션에서만 보조 근거로 사용하세요.

TRUST / FAQ:
구매 전 '진짜 망설임'을 해소하세요.
★당연한 질문 금지: 보면 바로 아는 것("고리 손잡이인가요?", "접히나요?", "색상이 있나요?")을 Q로 쓰지 마세요. 후킹 0입니다.
실제 구매 직전 불안을 Q로 잡으세요: 내구성("자주 접었다 펴도 괜찮나요?"), 사용 한계("바람 부는 날도 쓸 만한가요?"), 관리/세척, 휴대성("가방에 넣으면 부담되나요?"), 배송/교환, 실패 경험("싸구려처럼 금방 망가지지 않나요?").
A는 확인된 사실 범위 안에서 짧고 안심되게(과장·보장·미확인 수치 금지). Q→A 2~3개.

CTA:
누구에게 맞는지, 지금 무엇을 시작할 수 있는지 행동으로 연결하세요.
체크리스트나 정보 요약으로 끝내지 마세요.

────────────────────
[카피 공식]
────────────────────
각 섹션에는 아래 공식 중 하나를 적용하세요.

PAS:
문제 → 불편 증폭 → 해결 실마리

BAB:
현재 상태 → 바뀐 모습 → 제품이 연결하는 다리

FAB:
특징 → 장점 → 고객 효익

Comparison:
일반 선택의 어려움 → 이 제품의 선택 이유

Risk Reversal:
구매 전 불안 → 확인 정보 → 안심

CTA:
대상 고객 → 얻는 결과 → 행동 유도

────────────────────
[이미지 안 문구 길이 제한 - 짧을수록 좋음]
────────────────────
※ 매우 중요: AI 이미지 모델은 한글 글자가 많을수록 철자가 깨지고 오타가 납니다.
이미지 안 글자는 "최소한"으로, 짧고 굵게. 긴 문장·작은 글자·빽빽한 텍스트는 절대 금지.

상단 배지/소제목:
최종 이미지에는 사용하지 않습니다. 내부 섹션 구분용으로만 참고하세요.

메인 카피:
6~16자 (한 줄, 핵심 한 마디)

서브 카피:
14~26자 (한 줄)

카드 헤드:
3~8자 (단어 위주)

카드 설명:
6~16자 (짧은 한 줄, 길면 줄이기)

카드 개수:
2~3개 (꼭 필요할 때만. 적을수록 글자 깨짐이 줄어 퀄리티가 올라갑니다)

한 문장에 쉼표 2개 이상 금지.
한 섹션에 메시지 1개만 담으세요.
메인 카피와 서브 카피를 이어 읽었을 때 문맥이 자연스러워야 합니다.
같은 단어를 메인 카피와 서브 카피에서 반복하지 마세요.
명사형 조각 문구만 나열하지 말고, 구매자가 바로 이해하는 자연스러운 말로 작성하세요.
줄바꿈은 의미 단위로 자연스럽게(단어 중간에서 끊지 않기).

────────────────────
[출력 형식 - 반드시 유지]
────────────────────
맨 위 제목은 반드시 아래처럼 작성하세요.

[상세페이지 카피 기획서]

각 섹션은 반드시 아래 형식으로 작성하세요.

[섹션 N - 섹션역할]

· 배정 포인트:
0단계 메시지 지도에서 이 섹션에 배정한 강점 포인트 1개(다른 섹션과 겹치지 않게). 이 섹션 카피는 이 포인트만 다룬다.

· 구매자 질문:
이 섹션이 답해야 할 고객의 속질문 1개

· 핵심 메시지:
이 섹션에서 전달할 단 하나의 메시지

· 섹션 역할 메모:
이미지에 넣지 않는 내부 참고용 문구 5~12자

· 메인 카피:
6~16자, 실제 이미지 제목으로 사용. ★기능 설명·추상어·딱딱한 어미 금지, 구매자 생활 장면으로(위 [후킹·자연스러움] 규칙 적용)

· 서브 카피:
14~30자, 기능 설명 말고 사용 장면을 구체화

· 이미지 안 카드 카피: ★위 [섹션별 카피 구조]를 따라 '섹션 유형에 맞는 형식'으로(모든 섹션을 카드 3개로 만들지 말 것)
  - 카드형 섹션(USP/BENEFIT/DETAIL 등): 헤드 3~8자 / 설명 6~16자, 2~3개
  - 비카드형 섹션(PROBLEM=공감 문장 / SOLUTION=동사형 스텝 / FAQ=Q&A): 그 형식으로 2~3줄
  - HERO=포인트 2개, CTA=0~2개 (적게). 카드가 안 맞으면 맨 앞에 "카드 없음" 표기 후 대체 형식 작성

· 근거/포인트:
원본 사진, 사용자 입력, 스펙, 브리프에서 확인되는 구체 근거 2~3개
없으면 내부 판단용으로만 "확인 부족"이라고 적고, 이미지 안 카피에는 넣지 마세요.

· 이미지 연출 방향:
제품 단독샷, 사용 장면, 비교컷, 클로즈업, 구성품, FAQ 등 어떤 이미지로 보여줄지

· 카피 공식:
PAS, BAB, FAB, 비교, FAQ, 리스크 해소, CTA 중 선택

────────────────────
[최종 자체 검수]
────────────────────
작성 후 스스로 아래 기준으로 검수하세요.
단, 검수표는 출력하지 마세요.
검수 결과 문제가 있으면 카피를 수정한 뒤 최종 [상세페이지 카피 기획서]만 출력하세요.

1. HERO가 스펙 자랑이 아니라 구매 이유를 말하는가?
2. PROBLEM이 실제 고객 불편을 말하는가?
3. SOLUTION이 제품의 역할을 명확히 말하는가?
4. USP가 흔한 장점이 아니라 선택 이유가 되었는가?
5. DETAIL이 스펙 나열이 아니라 고객 효익으로 번역되었는가?
6. FAQ/TRUST가 구매 전 불안을 줄이는가?
7. CTA가 행동으로 이어지는가?
8. 모든 메인 카피가 서로 다르게 시작하는가? (비슷한 헤드라인 2개 이상이면 다시 쓰기)
8-1. ★각 섹션이 '서로 다른 포인트'를 다루는가? 같은 포인트(예: 고리)가 두 섹션에 중복되지 않았는가?
8-2. ★제품의 '대표 효과'(구두약=광택/복원, 화장품=발색 등)가 '효과 중심'으로 한 섹션에 들어갔는가? (단순 "챙기세요/보관하세요"가 아니라 제품이 뭘 해주는지가 보이는가)
8-3. ★'사용 타이밍·보관'(출근 전·현관·신발장에 두고 꺼내쓰기 등) 메시지가 2개 섹션 이상 차지하지 않았는가? (그러면 효과 섹션으로 교체)
8-4. ★두 섹션이 '거의 같은 말'(표현만 다른 같은 메시지)이 아닌가?
9. 추상어 대신 실제 사용 상황이 들어갔는가?
10. 확인되지 않은 정보가 들어가지 않았는가?
11. "상세페이지 참조", "확인 필요", "미확인" 같은 도망 문구가 이미지 카피에 들어가지 않았는가?
12. 특정 옵션 하나를 전체 사이즈/옵션처럼 단정하지 않았는가?
13. 각 섹션 끝 카피가 다음 섹션으로 이어지는 브릿지가 되는가? (섹션이 따로 끊기지 않는가)
14. 이 상품군의 핵심 속성(텍스처/핏/맛/수납/구성 등)이 통째로 빠지지 않았는가?
15. ★각 문구가 한국 사람이 한 번 읽고 바로 이해되는 자연스러운 말인가? (소리 내어 읽었을 때 어색하면 고치기)
16. ★대상에 안 맞는 단어를 쓰지 않았는가? (예: 명함에 '섞다' → '뒤섞이다/구겨지다/흐트러지다/찾기 힘들다'로 교체)

이 기획서의 메인 카피, 서브 카피, 이미지 안 카드 카피는 이후 이미지 생성 단계에서 그대로 사용됩니다.
섹션 역할 메모는 내부 구분용이며 실제 이미지 상단 소제목/배지로 넣지 않습니다.
메인 카피와 서브 카피는 이어 읽었을 때 자연스러워야 하며, 같은 단어를 한 문단 안에서 반복하지 마세요.
짧더라도 조각난 단어 나열이 아니라 실제 사람이 쓴 판매 문장처럼 작성하세요.
설명문이 아니라 실제 판매용 이미지 카피 기준으로 작성하세요.`
    setBusy(true);
    try{
      const beforeText = getLastAssistantText();
      const ok = await setPromptText(planPrompt);
      if(!ok){ await navigator.clipboard.writeText(planPrompt); log('입력창을 못 찾아 기획서 프롬프트를 복사했습니다. 직접 붙여넣어 주세요.'); return; }
      await sleep(400);
      const sent = await clickSendButton(beforeText);
      if(!sent){ log('전송 버튼을 못 눌렀습니다. 입력창 오른쪽 아래 검은 화살표를 직접 눌러주세요.'); return; }
      log('📝 2단계 카피 기획서 요청 전송 확인 완료. ChatGPT 답변 대기 중...');
      const answer = await waitForNewAssistantText(beforeText, 150000);
      if(answer && answer !== beforeText){
        state.copyPlan = answer; state.planSig = productSignature(getData()); save(); renderCopyPlanStatus();
        log('✅ 카피 기획서 확정 완료. 이제 [섹션별 프롬프트 생성]을 누르면 이 카피가 이미지에 반영됩니다.');
        await lintCopyPlanAndAutoReplan(!!directive);
      } else {
        if(saveLatestCopyPlanIfExists('카피기획 대기 실패 후 최근 답변')){
          await lintCopyPlanAndAutoReplan(!!directive);
        } else {
          log('⚠️ 기획서 답변 감지 실패. [최근 답변을 기획서로] 버튼을 쓰거나 다시 시도하세요.');
        }
      }
    }catch(e){ console.error(e); log('카피 기획서 생성 오류: '+(e?.message||e)); }
    finally{ setBusy(false); }
  }
  function saveCopyPlanManual(){
    const t = getLastAssistantText();
    if(t){ state.copyPlan = t; state.planSig = productSignature(getData()); save(); renderCopyPlanStatus(); log('✅ 최근 ChatGPT 답변을 카피 기획서로 저장했습니다.'); }
    else { log('⚠️ 최근 ChatGPT 답변을 찾지 못했습니다.'); }
  }
  function clearCopyPlan(){ state.copyPlan=''; save(); renderCopyPlanStatus(); log('카피 기획서를 초기화했습니다.'); }
  function renderCopyPlanStatus(){
    renderStatusDash();
    const box = $('dp-copy-plan-status');
    if(!box) return;
    if(state.copyPlan){
      const preview = state.copyPlan.slice(0, 200);
      box.innerHTML = `<div style="color:#4ade80;font-weight:bold;margin-bottom:4px">✅ 카피 기획서 적용 중</div><div style="color:#aaa;font-size:11px;line-height:1.5">${esc(preview)}${state.copyPlan.length>200?'...':''}</div>`;
    } else {
      box.innerHTML = `<div style="color:#888">아직 카피 기획서가 없습니다. [2단계: 카피 기획]을 누르면 섹션별 카피를 먼저 전략적으로 설계해 이미지에 반영합니다. (선택, 내용 알참 +++)</div>`;
    }
  }

  // ===== v21.8: 레퍼런스 학습 - 잘된 상세페이지 이미지의 디자인 톤을 분석해 따라가기 =====
  // 사용법: ChatGPT에 참고할 상세페이지 이미지를 첨부 → 분석 → 그 스타일을 우리 상품에 적용
  // v21.8.24.102: '[이미지 답변]'(텍스트 미감지 placeholder)·빈 답·너무 짧은 답이 레퍼런스로 저장돼
  // "적용 중"이라 뜨는데 실제 내용은 없던 버그 수정. 디자인 분석다운 텍스트인지 검사 후에만 저장한다.
  function isUsableRefStyle(t){
    const x = String(t || '').trim();
    if(!x) return false;
    if(/^\[이미지 답변\]$/.test(x)) return false;
    if(x.length < 40) return false;                      // 분석이라기엔 너무 짧음
    if(/이미지를 만들|생성했|만들어 드렸|여기 이미지|이미지가 완성/.test(x.slice(0, 120))) return false; // 분석이 아니라 이미지 생성 답변
    return true;
  }
  async function analyzeReference(){
    if(!(state.attachmentVerified || isComposerLikelyHasAttachments())){
      log('⚠️ 먼저 ChatGPT 입력창에 "참고할 상세페이지 이미지"를 첨부하세요. (잘 나온 상세페이지/와디즈 베스트 등)');
      return;
    }
    const refPrompt = `[레퍼런스 디자인 분석]
지금 첨부한 이미지는 내가 참고하고 싶은 "잘 만들어진 상세페이지/카드뉴스" 예시입니다.
이 이미지를 상품이 아니라 "디자인 레퍼런스"로 보고, 아래 항목을 분석해줘.
(이 이미지 속 제품이 뭔지는 중요하지 않고, 오직 디자인 스타일만 분석)

1. 전체 무드: (예: 미니멀/럭셔리/감성/팝/매거진 등 한 줄)
2. 색상 팔레트: (배경색, 포인트색, 텍스트색 - 구체적으로)
3. 타이포그래피: (폰트 느낌, 메인/서브 크기·굵기 대비, 정렬 - 세리프/산세리프)
4. 레이아웃 특징: (요소 배치, 여백 활용, 그리드, 카드 스타일)
5. 사진/이미지 처리: (제품 촬영 각도, 배경, 그림자, 보정 톤)
6. 섹션 구성·배치 순서: (이 페이지가 어떤 설득 흐름인지 — 예: 후킹→문제제기→공감→해결책→스펙→비포애프터→사회적증거→FAQ→CTA 중 무엇을 어떤 순서로 썼는지)
7. 카피 톤: (말투·후킹 방식 — 질문형/단정형, 짧고 강한지/감성적인지)
8. 이 스타일+구조를 한 문장으로 요약: (다른 상품에도 그대로 적용할 수 있게)

분석만 하고, 이미지를 새로 만들지는 마. 이 분석이 앞으로 내 상품 상세페이지의 디자인·구조 기준이 된다.`;
    setBusy(true);
    try{
      const beforeText = getLastAssistantText();
      const ok = await setPromptText(refPrompt);
      if(!ok){ await navigator.clipboard.writeText(refPrompt); log('입력창을 못 찾아 레퍼런스 분석 프롬프트를 복사했습니다.'); return; }
      await sleep(400);
      const sent = await clickSendButton(beforeText);
      if(!sent){ log('전송 버튼을 못 눌렀습니다. 입력창 오른쪽 아래 검은 화살표를 직접 눌러주세요.'); return; }
      log('🎨 레퍼런스 디자인 분석 요청 전송 확인 완료. ChatGPT 답변 대기 중...');
      const answer = await waitForNewAssistantText(beforeText, 120000);
      if(answer && answer !== beforeText && isUsableRefStyle(answer)){
        state.refStyle = answer; save(); renderRefStyleStatus();
        log('✅ 레퍼런스 스타일 분석 완료. 이제 [섹션별 프롬프트 생성] 시 이 디자인 톤을 따라갑니다.');
        log('💡 팁: 레퍼런스를 쓰면 [디자인 무드]보다 레퍼런스가 우선 적용됩니다.');
      } else if(answer && !isUsableRefStyle(answer)){
        // placeholder/이미지 생성 답변은 저장하지 않는다 — 빈 레퍼런스가 '적용 중'으로 뜨는 것 방지
        log('⚠️ ChatGPT 답변에서 디자인 분석 텍스트를 읽지 못했습니다("[이미지 답변]" 등). 레퍼런스를 저장하지 않았습니다.');
        log('   → ChatGPT 답변이 글로 완성된 뒤 다시 누르거나, 아래 칸에 특징을 직접 적고 [텍스트로 적용]을 눌러주세요.');
      } else {
        log('⚠️ 레퍼런스 분석 답변 감지 실패. [최근 답변을 레퍼런스로] 버튼을 쓰거나 다시 시도하세요.');
      }
    }catch(e){ console.error(e); log('레퍼런스 분석 오류: '+(e?.message||e)); }
    finally{ setBusy(false); }
  }
  function saveRefStyleManual(){
    const t = getLastAssistantText();
    if(t && isUsableRefStyle(t)){ state.refStyle = t; save(); renderRefStyleStatus(); log('✅ 최근 ChatGPT 답변을 레퍼런스 스타일로 저장했습니다.'); }
    else if(t){ log('⚠️ 최근 답변이 디자인 분석 텍스트가 아닙니다("[이미지 답변]"/이미지 생성 답변 등) — 저장하지 않았습니다.'); }
    else { log('⚠️ 최근 ChatGPT 답변을 찾지 못했습니다.'); }
  }
  function clearRefStyle(){ state.refStyle=''; const pe=$('dp-ref-paste'); if(pe) pe.value=''; save(); renderRefStyleStatus(); log('레퍼런스 스타일을 초기화했습니다. (디자인 무드로 복귀)'); }
  // v21.8.24.55: 패널에 직접 붙여넣은 벤치마크 텍스트를 레퍼런스로 적용(ChatGPT 첨부·분석 없이).
  function applyRefStyleFromText(){
    const el = $('dp-ref-paste');
    const t = (el?.value || '').trim();
    if(!t){ log('⚠️ 붙여넣은 레퍼런스 텍스트가 비어 있습니다.'); return; }
    state.refStyle = t; save(); renderRefStyleStatus();
    log('✅ 붙여넣은 텍스트를 레퍼런스 스타일로 적용했습니다. (디자인 무드보다 우선, 템플릿 저장 시 함께 보관)');
  }
  function renderRefStyleStatus(){
    renderStatusDash();
    // v21.8.24.55: 붙여넣기 칸을 현재 레퍼런스와 동기화(입력 중일 때는 건드리지 않음)
    const paste = $('dp-ref-paste');
    if(paste && document.activeElement !== paste) paste.value = state.refStyle || '';
    const box = $('dp-ref-style-status');
    if(!box) return;
    if(state.refStyle){
      const preview = state.refStyle.slice(0, 200);
      box.innerHTML = `<div style="color:#4ade80;font-weight:bold;margin-bottom:4px">✅ 레퍼런스 스타일 적용 중 (디자인 무드보다 우선)</div><div style="color:#aaa;font-size:11px;line-height:1.5">${esc(preview)}${state.refStyle.length>200?'...':''}</div>`;
    } else {
      box.innerHTML = `<div style="color:#888">레퍼런스 없음. 잘 나온 상세페이지를 ChatGPT에 첨부하고 [레퍼런스 분석]을 누르면 그 톤을 따라갑니다. (선택, 퀄리티 ↑↑)</div>`;
    }
  }

  // ===== v21.0 이식: 전체 섹션 자동 순차 생성 =====
  async function autoRunAllSections(){
    if(state.autoRunActive){ log('이미 자동 순차 생성이 진행 중입니다.'); return; }
    if(!state.shortImagePrompts?.length) buildShortImagePrompts(false);
    if(!state.shortImagePrompts.length){ log('먼저 [섹션별 프롬프트 생성]을 눌러주세요.'); return; }
    // v21.1: 첨부 자동 처리 (수동 버튼 불필요)
    const attached = await ensureImagesAttached();
    if(!attached){
      log('⚠️ 이미지 첨부 실패로 전체 섹션 자동 생성을 중단했습니다. 아래 첨부 디버그 로그를 확인하세요.');
      return;
    }
    const total = state.shortImagePrompts.length;
    state.autoRunActive = true; state.autoRunStop = false; updateAutoRunButton();
    log(`🚀 자동 순차 생성 시작: ${total}개 섹션. 멈추려면 [자동 생성 중지]를 누르세요.`);
    // v21.8.24.65: 백그라운드 진행 가능 여부 안내
    log(_timerWorkerOk
      ? '⏱ 백그라운드 타이머(Web Worker) 활성 — 다른 탭으로 가거나 창을 가려도 계속 진행됩니다. (탭을 닫거나 ChatGPT를 새로고침하면 중단)'
      : '⚠️ 백그라운드 타이머 사용 불가(페이지 보안정책) — 이 탭을 보이게 두세요(최소화/숨기면 느려질 수 있음).');
    // v21.8.10: 이미지 만들기 모드는 시도만 하고 실패해도 진행. 프롬프트에 "이미지 생성" 명시돼있어 모드 없이도 ChatGPT가 이미지 그림.
    const modeOk = await tryOpenImageMode();
    if(modeOk){
      log('[이미지 모드] 활성화 성공');
    } else {
      log('[이미지 모드] 활성화 실패 - 프롬프트에 이미지 생성 지시 있으므로 그대로 진행합니다');
    }
    for(let i=0; i<total; i++){
      if(state.autoRunStop){ log(`⏸ 자동 순차 생성 중단됨 (${i}/${total} 완료)`); break; }
      await runSection(i, total);
      if(state.autoRunStop){ log(`⏸ ${i+1}번 완료 후 중단됨`); break; }
    }
    state.autoRunActive = false; state.autoRunStop = false; updateAutoRunButton();
    const failedCount = (state.sectionStatus||[]).filter(s=>s==='failed').length;
    log(failedCount ? `🎉 자동 순차 생성 종료 (실패 ${failedCount}개 → [⟳ 실패 섹션만 다시 생성] 사용 가능)` : `🎉 자동 순차 생성 종료`);
  }

  // v21.8.24.19: 한 섹션 생성 단위 (autoRunAllSections / retryFailedSections 공용). 성공 여부 반환.
  async function runSection(i, total){
    const item = state.shortImagePrompts[i];
    if(!item) return false;
    state.currentShortImageIndex = i;
    setSectionStatus(i, 'running');
    log(`[${i+1}/${total}] "${item.title}" 생성 시작...`);
    // v21.8.24.74: 매 섹션 전송 직전 '이미지 만들기' 모드를 보장한다. 한 번 켜도 생성 후 칩이 풀리면
    // 다음 섹션이 일반 텍스트로 나가 퀄리티가 떨어지므로, 비활성일 때마다 다시 켠다.
    if(!isImageModeActive()){
      const modeOk = await tryOpenImageMode();
      log(modeOk ? `[${i+1}] '이미지 만들기' 모드 ON` : `[${i+1}] 이미지 모드 활성 실패 — 프롬프트로 진행(퀄리티 차이 가능)`);
    }
    const beforeText = getLastAssistantText();
    const imageRequest = buildImageGenerationRequest(item, i, total);
    const ok = await setPromptText(imageRequest);
    if(!ok){ log(`❌ [${i+1}] 입력창을 찾지 못했습니다.`); setSectionStatus(i, 'failed'); return false; }
    await waitUntilChatIdle(); // 이전 이미지가 완전히 끝나기 전에는 전송하지 않음
    if(isGenerating()){ log(`[${i+1}/${total}] 아직 생성 마무리 중 → 추가 대기`); await waitUntilChatIdle(); }
    await sleep(800);
    const sent = await clickSendButton(beforeText);
    if(!sent){ log(`❌ [${i+1}] 전송 버튼을 누르지 못했습니다.`); setSectionStatus(i, 'failed'); return false; }
    log(`[${i+1}/${total}] ChatGPT 이미지 생성 완료 대기 중... (최대 5분)`);
    const newText = await waitForImageAnswerDone(beforeText, 300000);
    const done = !!(newText && newText !== '[타임아웃]');
    if(done) log(`✅ [${i+1}/${total}] "${item.title}" 생성 완료`);
    else log(`⚠️ [${i+1}] 답변 타임아웃.`);
    // v21.8.24.19: 자동 검수 → 필요 시 1회 재생성
    if(done && !state.autoRunStop && !!$('dp-auto-qa')?.checked){
      await runQaRegenerate(i, total);
    }
    setSectionStatus(i, done ? 'done' : 'failed');
    await sleep(CGPT_DETECT.postDoneCooldownMs); // 완료 후 안정화 쿨다운(다음 전송 침범 방지)
    // v21.8.24.61: 여기서의 idle 재확인은 다음 섹션 전송 직전 waitUntilChatIdle와 중복이라 제거(섹션당 idle 대기 1회 절감).
    return done;
  }

  // v21.8.24.19: 실패/대기 상태 섹션만 다시 생성
  async function retryFailedSections(){
    if(state.autoRunActive){ log('자동 생성 진행 중에는 사용할 수 없습니다.'); return; }
    const ps = state.shortImagePrompts || [];
    if(!ps.length){ log('먼저 [프롬프트 생성] 또는 [자동 만들기]를 실행하세요.'); return; }
    const targets = ps.map((_, i) => i).filter(i => state.sectionStatus[i] === 'failed' || state.sectionStatus[i] === 'pending');
    if(!targets.length){ log('실패/대기 상태인 섹션이 없습니다. 모두 완료되었습니다.'); return; }
    const attached = await ensureImagesAttached();
    if(!attached){ log('⚠️ 이미지 첨부 실패로 재생성을 중단했습니다.'); return; }
    state.autoRunActive = true; state.autoRunStop = false; updateAutoRunButton();
    log(`⟳ 실패/대기 섹션 ${targets.length}개 재생성 시작`);
    await tryOpenImageMode();
    const total = ps.length;
    for(const i of targets){
      if(state.autoRunStop){ log('⏸ 재생성 중단됨'); break; }
      await runSection(i, total);
    }
    state.autoRunActive = false; state.autoRunStop = false; updateAutoRunButton();
    const left = (state.sectionStatus||[]).filter(s=>s==='failed').length;
    log(left ? `⟳ 재생성 종료 (아직 실패 ${left}개)` : `⟳ 재생성 종료 (모든 섹션 완료 ✅)`);
  }

  // v21.8.24.19: 생성 직후 ChatGPT 스스로 검수 → 문제 있으면 같은 비율로 수정본 1회 재생성
  async function runQaRegenerate(i, total){
    try{
      const item = state.shortImagePrompts[i];
      const ratio = item?.ratio || '4:5';
      const qaPrompt = `방금 생성한 위 이미지를 스스로 점검하세요. 아래 항목 중 하나라도 문제가 있으면 같은 비율(${ratio})로 "수정본 이미지"를 다시 생성하고, 모두 통과면 텍스트로 "검수 통과"라고만 답하세요. (설명 나열 금지)
점검 항목:
1) ⚠️ 한글 철자 깨짐·자모 분리·이상한 글자·오타·어색한 띄어쓰기·번역투 (가장 중요 — 하나라도 있으면 무조건 재생성)
2) 글자가 너무 많거나 작아 빽빽한가 → 그렇다면 글자를 줄이고 크게 다시
3) 첨부 원본 제품과 형태/색상/구성 불일치, 또는 원본에 없는 로고·구성품·인증·리뷰·별점 추가
4) 금지어 사용(첫인상, 단정함, 비즈니스 무드, 깔끔한 인상, 상세페이지 참조, 확인 필요, 미확인)
5) 확인되지 않은 수치·스펙·효능 표기
문제가 있으면 텍스트 설명 없이 수정본 이미지만 다시 생성하세요. 특히 한글이 깨졌으면 글자 수를 줄여서 다시 그리세요.`;
      const beforeText = getLastAssistantText();
      const ok = await setPromptText(qaPrompt);
      if(!ok) return;
      await waitUntilChatIdle();
      await sleep(500);
      const sent = await clickSendButton(beforeText);
      if(!sent){ log(`[${i+1}/${total}] 검수 요청 전송 실패 → 건너뜀`); return; }
      log(`[${i+1}/${total}] 🔎 자동 검수 요청 → 응답 대기`);
      // 검수는 "통과" 텍스트 또는 수정본 이미지 둘 다 가능 → 텍스트 기반 종료 감지 사용
      await waitForNewAssistantText(beforeText, 180000);
      await waitUntilChatIdle();
    }catch(e){ log(`검수 단계 오류(건너뜀): ${e?.message||e}`); }
  }

  // v21.8.24.19: 섹션 진행 현황 표시
  function initSectionStatus(){ state.sectionStatus = (state.shortImagePrompts || []).map(() => 'pending'); renderSectionProgress(); }
  function setSectionStatus(i, st){ if(!Array.isArray(state.sectionStatus)) state.sectionStatus=[]; state.sectionStatus[i] = st; renderSectionProgress(); }
  function renderSectionProgress(){
    const box = $('dp-section-progress'); if(!box) return;
    const ps = state.shortImagePrompts || [];
    if(!ps.length){ box.textContent = '아직 진행 내역이 없습니다. 자동 제작 또는 프롬프트 생성을 시작하면 섹션별 상태가 표시됩니다.'; return; }
    const label = { pending:'⏳ 대기', running:'🟢 생성중', done:'✅ 완료', failed:'❌ 실패' };
    const done = (state.sectionStatus||[]).filter(s=>s==='done').length;
    const busy = state.autoRunActive;
    // v21.8.24.78: 섹션별 '이 섹션만 다시 생성' 버튼 복구(이전엔 텍스트만 떠서 단계별 재생성이 안 보였음).
    box.innerHTML = `<div style="margin-bottom:6px;font-weight:bold">진행: ${done}/${ps.length} 완료${busy?' · 생성 중…':''}</div>` +
      ps.map((p, i) => {
        const st = state.sectionStatus[i] || 'pending';
        return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid #2a2a2e">
          <span style="flex:1;font-size:12px">${i+1}. ${esc(p.title)} — ${label[st]}</span>
          <button class="dp-btn secondary dp-regen-one" data-i="${i}" ${busy?'disabled':''} style="padding:3px 9px;font-size:11px;white-space:nowrap">🔄 이 섹션만</button>
        </div>`;
      }).join('');
    box.querySelectorAll('.dp-regen-one').forEach(b=>{ b.onclick=()=>regenerateSingleSection(parseInt(b.dataset.i,10)); });
  }
  // v21.8.24.78: 한 섹션만 단독 재생성(단계별 재생성). 첨부·이미지모드 보장 후 그 섹션만 다시 생성.
  async function regenerateSingleSection(i){
    const ps = state.shortImagePrompts || [];
    if(!ps[i]){ log('재생성할 섹션이 없습니다. 먼저 [프롬프트 생성]/[자동 제작]을 실행하세요.'); return; }
    if(state.autoRunActive){ log('자동 생성 중에는 개별 재생성을 할 수 없습니다. 끝나거나 중단 후 사용하세요.'); return; }
    const attached = await ensureImagesAttached();
    if(!attached){ log('⚠️ 이미지 첨부 실패로 재생성을 중단했습니다.'); return; }
    state.autoRunActive = true; state.autoRunStop = false; updateAutoRunButton();
    log(`🔄 [${i+1}/${ps.length}] "${ps[i].title}" 이 섹션만 다시 생성`);
    try{ await runSection(i, ps.length); }
    catch(e){ log('재생성 오류: '+(e?.message||e)); }
    finally{ state.autoRunActive = false; state.autoRunStop = false; updateAutoRunButton(); renderSectionProgress(); }
  }

  // v21.8.24.19: ChatGPT DOM 자가진단 — UI 변경으로 자동화가 깨지는 지점을 한눈에 점검
  function runDomDiagnostics(){
    try{
      const mark = (b) => b ? '✅' : '❌';
      const lines = [];
      const input = findInput();
      lines.push(`${mark(!!input)} 입력창(findInput): ${input ? describeEl(input) : '못 찾음'}`);
      const root = getComposerRootStrict();
      lines.push(`${mark(!!root)} composer 루트: ${root ? describeEl(root) : '못 찾음'}`);
      const fileInput = findChatGPTFileInput();
      lines.push(`${mark(!!fileInput)} 파일 input(첨부용): ${fileInput ? describeEl(fileInput) : '못 찾음'}`);
      const menuBtn = findComposerMenuButton();
      lines.push(`${mark(!!menuBtn)} +/첨부 메뉴 버튼: ${menuBtn ? describeEl(menuBtn) : '못 찾음'}`);
      const sendCands = getSendButtonCandidates();
      // v21.8.24.90: 전송 버튼은 입력칸에 글자가 있을 때만 활성/표시됨. 빈 입력창이면 0개가 정상이라 오해 방지.
      const sendExists = !!document.querySelector('button[data-testid="send-button"],button#composer-submit-button,button[aria-label*="보내기"],button[aria-label*="프롬프트"],button[aria-label*="Send" i]');
      const inputEmpty = !((getPromptInputText()||'').trim());
      if(sendCands.length > 0) lines.push(`✅ 전송 버튼 후보: ${sendCands.length}개 · ${describeEl(sendCands[0])}`);
      else if(sendExists) lines.push(`✅ 전송 버튼 있음(현재 비활성 — 입력창에 글자가 있으면 활성화됨)`);
      else if(inputEmpty) lines.push(`ℹ️ 전송 버튼: 입력칸이 비어 숨겨진 상태(정상 — 글자를 입력하면 나타납니다). 자동 제작은 프롬프트를 먼저 넣은 뒤 누르므로 영향 없음`);
      else lines.push(`❌ 전송 버튼 후보: 0개 (UI 변경 의심)`);
      const stopHits = (CGPT_DETECT.generating || []).filter(s => { try{ return !!document.querySelector(s); }catch(_){ return false; } });
      lines.push(`ℹ️ 생성중 신호(isGenerating): ${isGenerating() ? '예(생성 중)' : '아니오(대기)'} · 현재 매칭 셀렉터 ${stopHits.length}개`);
      const genImgs = collectGeneratedSectionImages();
      lines.push(`ℹ️ 현재 감지된 생성 이미지 후보: ${genImgs.length}장`);
      const assistantNodes = countAssistantNodes();
      lines.push(`ℹ️ assistant 메시지 노드: ${assistantNodes}개`);
      const sendOk = sendCands.length > 0 || sendExists || inputEmpty;
      const core = !!input && sendOk;
      const verdict = core
        ? (sendCands.length>0 || sendExists
            ? '\n\n판정: 핵심 자동화 요소(입력창+전송버튼) 정상 ✅'
            : '\n\n판정: ✅ 정상으로 보입니다. (전송 버튼은 입력칸에 글자가 있을 때만 나타나므로, 지금 0개는 빈 입력창이라 그런 것일 뿐 — 자동 제작은 글자를 먼저 넣고 전송합니다.)')
        : '\n\n판정: ⚠️ 입력창 또는 전송버튼을 못 찾았습니다. 새 ChatGPT 대화 탭에서 다시 시도하거나, ChatGPT UI가 바뀐 것일 수 있습니다. 이 진단 내용을 캡처해 전달하면 셀렉터를 맞출 수 있습니다.';
      const out = $('dp-diag-output');
      if(out) out.textContent = lines.join('\n') + verdict;
      log('🩺 DOM 자가진단 완료');
    }catch(e){ const out=$('dp-diag-output'); if(out) out.textContent='진단 오류: '+(e?.message||e); log('DOM 진단 오류: '+(e?.message||e)); }
  }
  function stopAutoRun(){
    if(!state.autoRunActive){ log('자동 생성이 실행 중이 아닙니다.'); return; }
    state.autoRunStop = true; log('⏸ 중단 요청됨. 현재 섹션 완료 후 멈춥니다.');
  }
  function updateAutoRunButton(){
    const btn = $('dp-auto-run-all');
    if(!btn) return;
    if(state.autoRunActive){ btn.textContent='⏸ 자동 생성 중지'; btn.classList.remove('green'); btn.classList.add('danger'); }
    else { btn.textContent='🚀 전체 섹션 자동 생성'; btn.classList.remove('danger'); btn.classList.add('green'); }
  }

  // ===== v21.6: 초보자 원클릭 마법사 - 1단계→2단계→생성을 전자동 =====
  // 사진+상품명만 있으면 버튼 하나로 끝까지 자동 실행
  async function runMagicWizard(){
    if(state.wizardActive){ stopWizard(); return; }
    const d = getData();
    // 최소 조건 체크: 상품명 또는 첨부 이미지 중 하나는 필요
    const hasProduct = !!(d.product||'').trim();
    const hasImage = state.images.length > 0;
    if(!hasProduct && !hasImage){
      log('⚠️ 상품명을 입력하거나 원본 이미지를 첨부해주세요. (둘 중 하나는 필요)');
      return;
    }

    // v21.8.24.24: 저장된 진단/카피 기획이 "지금 상품"과 다른 제품 것이면 재사용 금지 → 초기화 후 새로 생성.
    const curSig = productSignature(d);
    if(curSig){
      if(state.masterBrief && state.briefSig && state.briefSig !== curSig){ state.masterBrief=''; state.briefSig=''; log('🔄 저장된 제품진단이 다른 상품 기준이라 초기화합니다.'); }
      if(state.copyPlan && state.planSig && state.planSig !== curSig){ state.copyPlan=''; state.planSig=''; log('🔄 저장된 카피기획이 다른 상품 기준이라 초기화합니다.'); }
      if(!state.lastProductSig) state.lastProductSig = curSig;
      renderMasterBriefStatus(); renderCopyPlanStatus();
    }

    state.wizardActive = true;
    state.autoRunStop = false;
    updateWizardButton();
    setBusy(true);

    try{
      log('━━━━━━━━━━━━━━━━━━━━━━━');
      log('✨ 원클릭 자동 제작 시작! 5단계로 진행됩니다.');
      log('중간에 멈추려면 [✨ 만들기] 버튼을 다시 누르세요.');
      log('━━━━━━━━━━━━━━━━━━━━━━━');

      // v21.8.7: 사용자가 중간에 수동 전송한 뒤 다시 누른 경우, 화면의 최근 답변을 먼저 저장해 이어서 진행
      restoreWizardStateFromLatestAnswer();

      // --- 1/5: 이미지 자동 첨부 ---
      state.wizardPhase = 'attaching';
      if(hasImage){
        log('【흐름 1/5】 원본 이미지 ChatGPT에 첨부 중...');
        const attached = await ensureImagesAttached();
        if(!attached){
          log('⛔ 이미지 자동 첨부가 확인되지 않아 자동 제작을 중단했습니다. 아래 첨부 디버그 로그를 확인하고, ChatGPT +버튼으로 직접 첨부한 뒤 다시 실행하세요.');
          throw new Error('ATTACH_FAIL');
        }
        log('[흐름] 이미지 첨부 완료');
      } else {
        log('【흐름 1/5】 첨부할 이미지 없음 → 텍스트 기반으로 진행');
      }
      if(state.autoRunStop){ throw new Error('STOP'); }

      // --- 2/5: AI 상품 분석 (로컬) ---
      state.wizardPhase = 'analyzing';
      log('【흐름 2/5】 상품 정보 자동 분석 중...');
      runLocalInference(false);
      log('[흐름] 제품분석 완료');
      await sleep(500);
      if(state.autoRunStop){ throw new Error('STOP'); }

      // --- 3/5: 1단계 제품 진단 (마스터 브리프) ---
      state.wizardPhase = 'brief';
      restoreWizardStateFromLatestAnswer();
      if(state.copyPlan){
        log('【흐름 3/5】 카피 기획서가 이미 저장되어 있어 제품 진단/카피기획 재요청을 건너뜁니다.');
      }else if(state.masterBrief){
        log('【흐름 3/5】 저장된 제품 진단 기준을 사용합니다.');
        log('[흐름] 제품진단 저장 완료');
      }else{
        log('【흐름 3/5】 제품 진단 중... (ChatGPT가 제품을 분석합니다, 최대 2분)');
        setBusy(false); // buildMasterBrief 내부에서 setBusy 쓰므로 잠시 해제
        await buildMasterBrief();
        setBusy(true);
        saveLatestMasterBriefIfExists('제품진단 완료 후 최근 답변');
        if(state.autoRunStop){ throw new Error('STOP'); }
        if(state.masterBrief){
          log('[흐름] 제품진단 저장 완료');
        } else {
          log('⚠️ 제품 진단 답변을 못 받았지만 계속 진행합니다.');
        }
      }

      // --- 4/5: 2단계 카피 기획 ---
      state.wizardPhase = 'copyplan';
      restoreWizardStateFromLatestAnswer();
      if(state.copyPlan){
        log('【흐름 4/5】 저장된 카피 기획서를 사용합니다. 바로 이미지 제작 단계로 넘어갑니다.');
        log('[흐름] 카피기획 저장 완료');
      }else{
        log('【흐름 4/5】 카피 기획 중... (섹션별 카피를 설계합니다, 최대 2분)');
        setBusy(false);
        await buildCopyPlan();
        setBusy(true);
        // v21.8.9: 카피기획 답변 감지 로그 강화
        const beforePlan = state.copyPlan;
        saveLatestCopyPlanIfExists('카피기획 완료 후 최근 답변', true); // verbose=true
        if(state.copyPlan && state.copyPlan !== beforePlan){
          log('[흐름] 카피기획 저장 완료');
        } else if(state.copyPlan){
          log('[카피감지] 기존 카피기획서 유지');
          log('[흐름] 카피기획 저장 완료');
        } else {
          log('[카피감지] 카피기획서 감지 실패 - 답변이 형식에 안 맞거나 아직 미완성');
        }
        if(state.autoRunStop){ throw new Error('STOP'); }
        if(!state.copyPlan){
          log('⚠️ 카피 기획 답변을 못 받았지만 계속 진행합니다.');
        }
      }

      // --- 5/5: 프롬프트 생성 + 전체 이미지 자동 생성 ---
      log('【흐름 5/5】 섹션별 프롬프트 생성 + 이미지 자동 제작 시작...');
      buildShortImagePrompts(true);
      const promptCount = state.shortImagePrompts?.length || 0;
      log(`[흐름] 이미지 프롬프트 ${promptCount}개 생성 완료`);
      // v21.8.13: 프롬프트 0개면 모듈 로드 실패 → 중단 (이전엔 "🎉 완료" 잘못 표시했음)
      if(promptCount === 0){
        log('⛔ 프롬프트가 0개입니다. 동적 프롬프트 생성기 모듈이 로드되지 않았을 가능성이 큽니다.');
        log('→ ChatGPT 페이지를 새로고침(F5)한 뒤 다시 [✨ 만들기]를 눌러주세요.');
        throw new Error('PROMPT_GEN_FAIL');
      }
      await sleep(800);
      if(state.autoRunStop){ throw new Error('STOP'); }

      // v21.8.9: wizardActive를 풀지 않고 유지 → autoRunAllSections 완료까지 [중지] 버튼 노출
      // setBusy만 해제 (개별 버튼 활성화 필요)
      setBusy(false);
      state.wizardPhase = 'generating';
      await autoRunAllSections(); // 내부에서 섹션별 이미지 순차 생성

      // v21.8.24.81: 원클릭에 '묶음 내보내기'까지 포함(옵션). 켜져 있으면 생성→수집→이미지+움짤 묶음을 자동으로.
      if(!state.autoRunStop && $('dp-wizard-bundle')?.checked){
        state.wizardPhase = 'bundling';
        log('【마무리】 생성된 컷 자동 수집 → 이미지+움짤 묶음 내보내기...');
        await sleep(1500); // 마지막 이미지 DOM 안정화
        previewCollectImages();
        await sleep(500);
        if((state.collectedImages||[]).some(x=>x.checked)){
          await exportDetailBundle();
        } else {
          log('⚠️ 수집된 컷이 없어 묶음 내보내기를 건너뜁니다. ④에서 [생성 이미지 수집] 후 [📦 묶음 내보내기]를 눌러주세요.');
        }
      }

      state.wizardPhase = 'done';
      log('━━━━━━━━━━━━━━━━━━━━━━━');
      log($('dp-wizard-bundle')?.checked ? '🎉 원클릭 완성! 다운로드된 detail_01~ 파일을 순서대로 상세페이지에 업로드하세요.' : '🎉 원클릭 자동 제작 완료! ChatGPT에서 생성된 이미지들을 확인하세요.');
      log('━━━━━━━━━━━━━━━━━━━━━━━');

    }catch(e){
      if(e?.message === 'STOP'){
        log('⏸ 자동 제작이 중단되었습니다.');
        state.wizardPhase = 'stopped';
      }else if(e?.message === 'ATTACH_FAIL'){
        attachLog('[자동 제작 중단] 이미지 첨부 실패로 1단계 이후 진행하지 않았습니다.');
        state.wizardPhase = 'attach_fail';
      }else if(e?.message === 'COPYPLAN_NOT_FOUND'){
        log('⛔ 카피 기획서가 저장되지 않아 중단했습니다.');
        state.wizardPhase = 'copyplan_fail';
      }else if(e?.message === 'PROMPT_GEN_FAIL'){
        state.wizardPhase = 'prompt_gen_fail';
      }else{
        console.error(e);
        log('자동 제작 중 오류: '+(e?.message||e));
        state.wizardPhase = 'error';
      }
    }finally{
      state.wizardActive = false;
      state.autoRunStop = false;
      updateWizardButton();
      setBusy(false);
    }
  }

  function stopWizard(){
    state.autoRunStop = true;
    log('⏸ 중단 요청됨. 현재 단계 완료 후 멈춥니다.');
  }

  function updateWizardButton(){
    const btn = $('dp-magic-wizard');
    if(!btn) return;
    if(state.wizardActive){
      btn.textContent = '⏸ 자동 제작 중지';
      btn.classList.remove('green'); btn.classList.add('danger');
    }else{
      btn.textContent = '✨ 상세페이지 자동 만들기';
      btn.classList.remove('danger'); btn.classList.add('green');
    }
  }

  async function uploadSelectedImagesToChatGPT(){
    if(!state.images.length){ log('패널에서 먼저 원본 이미지를 선택하세요.'); return false; }
    setBusy(true);
    try{
      const ok=await attachFilesToComposer(state.images.map(x=>x.file).filter(Boolean));
      const verified= ok ? await waitForAttachmentVerification(state.images.map(x=>x.name), 10000) : false;
      state.chatFilesUploaded=verified;
      state.attachmentVerified=verified;
      if($('dp-images-attached')) $('dp-images-attached').checked=verified;
      const status=$('dp-upload-status');
      if(status) status.textContent=verified?'첨부 확인 완료: ChatGPT 입력창 위에 원본 이미지가 연결된 것으로 감지되었습니다.':'자동 첨부가 확인되지 않았습니다. ChatGPT + 버튼 → 사진 및 파일 추가로 직접 첨부한 뒤 [첨부 상태 확인]을 누르세요.';
      log(verified?'선택 이미지가 ChatGPT 대화창 첨부로 확인되었습니다.':'자동 첨부 확인 실패. 패널 이미지가 아니라 ChatGPT 입력창 썸네일이 보여야 합니다.');
      save();
      return verified;
    }catch(e){ console.error(e); log('이미지 첨부 중 오류: '+(e?.message||e)); return false; }
    finally{ setBusy(false); }
  }

  async function checkAttachmentStatus(){
    const verified=await waitForAttachmentVerification(state.images.map(x=>x.name), 1500);
    state.attachmentVerified=verified;
    state.chatFilesUploaded=verified;
    if($('dp-images-attached')) $('dp-images-attached').checked=verified;
    const status=$('dp-upload-status');
    if(status) status.textContent=verified?'첨부 확인 완료: ChatGPT 입력창에서 원본 이미지/파일 첨부가 감지되었습니다.':'첨부 미확인: 패널 미리보기만으로는 부족합니다. ChatGPT 입력창 + 버튼으로 원본 이미지를 직접 첨부해 주세요.';
    log(verified?'원본 이미지 첨부 상태를 확인했습니다.':'원본 이미지 첨부가 확인되지 않았습니다.');
    save();
    return verified;
  }

  async function attachFilesToComposer(files){
    const fileList=(files||[]).filter(Boolean);
    if(!fileList.length){ attachLog('[첨부 중단] 전달받은 파일이 0개입니다.'); return false; }

    const root=getComposerRootStrict();
    attachLog(`[첨부 3/7] ChatGPT composer 탐색: ${root?'성공 · '+describeEl(root):'실패'}`);
    if(!root){
      attachLog('[첨부 실패] ChatGPT 입력창/composer를 찾지 못했습니다. 새 ChatGPT 대화 탭에서 다시 시도하세요.');
      return false;
    }

    // v21.8.2: 1차 - 현재 ChatGPT composer 주변 file input에 직접 주입
    let input=findChatGPTFileInput();
    attachLog(`[첨부 4/7] file input 1차 탐색: ${input?'성공 · '+describeEl(input):'실패'}`);
    if(input){
      const ok=await setFilesToInput(input, fileList, '1차 composer file input');
      if(ok) return true;
    }

    // 2차 - 입력창 주변 +/첨부 버튼을 눌러 file input/menu를 열고 다시 주입
    const menuBtn=findComposerMenuButton();
    attachLog(`[첨부 4-2/7] +/첨부 버튼 탐색: ${menuBtn?'성공 · '+describeEl(menuBtn):'실패'}`);
    if(menuBtn){
      try{ menuBtn.click(); attachLog('[첨부 4-3/7] +/첨부 버튼 클릭 완료'); }
      catch(e){ attachLog('[첨부 4-3/7] +/첨부 버튼 클릭 오류: '+(e?.message||e)); }
      await sleep(700);
      input=findChatGPTFileInput();
      attachLog(`[첨부 5/7] 버튼 클릭 후 file input 재탐색: ${input?'성공 · '+describeEl(input):'실패'}`);
      if(input){
        const ok=await setFilesToInput(input, fileList, '2차 버튼 클릭 후 file input');
        if(ok) return true;
      }

      const menuClicked = clickMenuItemByText(['사진 및 파일 추가','사진 및 파일 업로드','사진 및 파일','파일 추가','파일 업로드','Upload from computer','Add photos and files','Attach files','Upload files']);
      attachLog(`[첨부 5-2/7] 메뉴 항목 클릭: ${menuClicked?'성공':'실패'}`);
      await sleep(900);
      input=findChatGPTFileInput();
      attachLog(`[첨부 5-3/7] 메뉴 클릭 후 file input 재탐색: ${input?'성공 · '+describeEl(input):'실패'}`);
      if(input){
        const ok=await setFilesToInput(input, fileList, '3차 메뉴 클릭 후 file input');
        if(ok) return true;
      }
    }

    // 3차 - 붙여넣기 이벤트 fallback. ChatGPT UI 변경으로 input 접근이 막힐 때 대비.
    attachLog('[첨부 5-4/7] file input 직접 주입 실패 → paste 이벤트 fallback 시도');
    return await pasteFilesToComposer(fileList);
  }

  async function setFilesToInput(input, files, label='file input'){
    try{
      if(!input){ attachLog(`[첨부 실패] ${label}: input 없음`); return false; }
      const dt=new DataTransfer();
      files.forEach(file=>dt.items.add(file));
      attachLog(`[첨부 5-주입] ${label}: DataTransfer 생성 ${dt.files.length}개`);
      input.files=dt.files;
      ['focus','input','change'].forEach(type=>input.dispatchEvent(new Event(type,{bubbles:true,cancelable:true})));
      input.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,inputType:'insertFromPaste',data:null}));
      await sleep(1800);
      const immediate = isComposerLikelyHasAttachments(files.length);
      attachLog(`[첨부 5-확인] ${label}: 주입 직후 composer 첨부 감지 ${immediate?'성공':'미확인'}`);
      // 즉시 감지가 안 되어도 ChatGPT가 늦게 렌더링할 수 있으므로 주입 자체가 성공했으면 true 반환, 최종 검증은 waitForAttachmentVerification에서 처리
      return true;
    }catch(e){ attachLog(`[첨부 오류] ${label}: ${e?.name||'Error'} · ${e?.message||e}`); console.warn('file attach failed', e); return false; }
  }

  async function pasteFilesToComposer(files){
    const input=findInput();
    if(!input){ attachLog('[첨부 fallback] paste 실패: 입력창을 찾지 못함'); return false; }
    try{
      input.focus();
      const dt=new DataTransfer();
      files.forEach(file=>dt.items.add(file));
      const ev=new Event('paste',{bubbles:true,cancelable:true});
      Object.defineProperty(ev,'clipboardData',{value:dt});
      input.dispatchEvent(ev);
      attachLog(`[첨부 fallback] paste 이벤트 발행: ${dt.files.length}개`);
      await sleep(2200);
      const ok=isComposerLikelyHasAttachments(files.length);
      attachLog(`[첨부 fallback] paste 후 composer 첨부 감지: ${ok?'성공':'실패'}`);
      return ok;
    }catch(e){ attachLog('[첨부 fallback 오류] '+(e?.message||e)); console.warn('paste attach failed', e); return false; }
  }

  function findChatGPTFileInput(){
    const panel=$('dp-director-panel');
    const isPanelInput=(i)=>panel && panel.contains(i);
    const isFile=(i)=>i && i.type==='file' && !isPanelInput(i);
    const root=getComposerRootStrict();

    // composer 내부/근처 input 우선. 숨김 input도 실제 업로드 대상일 수 있어 visible 조건을 걸지 않음.
    const local=root ? [...root.querySelectorAll('input[type="file"]')].filter(isFile) : [];
    const localImage=local.find(i=>/image|png|jpg|jpeg|webp|gif|\*/i.test(i.accept||''));
    if(localImage || local[0]) return localImage || local[0];

    const all=[...document.querySelectorAll('input[type="file"]')].filter(isFile);
    const imageInput=all.find(i=>/image|png|jpg|jpeg|webp|gif|\*/i.test(i.accept||''));
    return imageInput || all[0] || null;
  }

  function getComposerRootStrict(){
    const input=findInput();
    if(!input) return null;
    return input.closest('form') || input.closest('[data-testid*="composer"]') || input.closest('[class*="composer"]') || input.parentElement?.parentElement?.parentElement || input.parentElement || null;
  }

  function composerRoot(){
    return getComposerRootStrict() || document.body;
  }

  function getComposerAttachmentSearchRoot(){
    const root=getComposerRootStrict();
    if(!root) return null;
    // ChatGPT 첨부 썸네일은 form 바로 안이 아니라 입력창 주변 wrapper에 렌더링되는 경우가 있어
    // 입력창 기준 가까운 조상 몇 단계까지만 탐색한다. 패널/본문 전체는 절대 보지 않는다.
    let cur=root;
    for(let i=0;i<5 && cur?.parentElement;i++) cur=cur.parentElement; // v21.8.24.45: 탐색 범위 확대(썸네일이 더 상위 wrapper에 렌더되는 케이스 대응)
    return cur || root;
  }

  function getComposerAttachmentCandidates(){
    const panel=$('dp-director-panel');
    const scope=getComposerAttachmentSearchRoot();
    if(!scope) return [];

    const inPanel=(el)=>panel && panel.contains(el);
    const visibleSizeOk=(el)=>{
      if(!isVisible(el)) return false;
      const r=el.getBoundingClientRect();
      // vidIQ/마이크/툴 아이콘 같은 작은 아이콘 오판 방지
      if(r.width < 34 || r.height < 34) return false;
      // 실제 입력창 주변 영역만 허용. 이전 답변 본문 이미지 오판 방지
      if(r.top < window.innerHeight * 0.18) return false;
      if(r.left > window.innerWidth * 0.9) return false;
      return true;
    };

    const imgCandidates=[...scope.querySelectorAll('img')]
      .filter(el=>!inPanel(el))
      .filter(visibleSizeOk)
      .filter(el=>{
        const src=el.getAttribute('src')||'';
        const alt=el.getAttribute('alt')||'';
        return /^blob:|^data:/i.test(src) || /첨부|업로드|image|file|preview|thumbnail|사진|파일/i.test(alt);
      });

    const cardSelectors=[
      '[data-testid*="attachment"]','[data-testid*="upload"]','[data-testid*="preview"]',
      '[class*="attachment"]','[class*="upload"]','[class*="preview"]','[class*="file"]'
    ].join(',');

    const cardCandidates=[...scope.querySelectorAll(cardSelectors)]
      .filter(el=>!inPanel(el))
      .filter(isVisible)
      .filter(el=>{
        const r=el.getBoundingClientRect();
        if(r.width < 40 || r.height < 40) return false;
        if(r.top < window.innerHeight * 0.18) return false;
        // 단순 파일/이미지 버튼은 제외하고, 내부에 이미지나 제거 버튼이 있는 카드형 요소만 허용
        const hasThumb=!!el.querySelector('img,canvas,video');
        const hasRemove=!!el.querySelector('button[aria-label*="삭제"],button[aria-label*="Remove"],button[aria-label*="remove"],button[aria-label*="닫기"],button[aria-label*="Close"]');
        return hasThumb || hasRemove;
      });

    const merged=[];
    [...imgCandidates, ...cardCandidates].forEach(el=>{
      if(!merged.some(x=>x===el || x.contains(el) || el.contains(x))) merged.push(el);
    });
    return merged;
  }

  function isComposerLikelyHasAttachments(expectedCount=1){
    const candidates=getComposerAttachmentCandidates();
    const needed=Math.max(1, Math.min(Number(expectedCount)||1, 3));
    return candidates.length >= needed;
  }

  async function waitForAttachmentVerification(names=[], timeout=8000){
    const start=Date.now();
    const expected=Math.max(1, Math.min((names||[]).length || state.images.length || 1, 3));
    attachLog(`[첨부 검증] ChatGPT 입력창 첨부 썸네일 확인 시작 (${Math.round(timeout/1000)}초 · 최소 ${expected}개 감지 필요)`);
    let checks=0;
    while(Date.now()-start<timeout){
      checks++;
      const candidates=getComposerAttachmentCandidates();
      if(candidates.length >= expected){
        attachLog(`[첨부 검증] 성공 (${checks}회차 · 후보 ${candidates.length}개)`);
        return true;
      }
      if(checks===1 || checks%4===0) attachLog(`[첨부 검증] 대기 중 (${checks}회차 · 후보 ${candidates.length}개)`);
      await sleep(500);
    }
    const finalCandidates=getComposerAttachmentCandidates();
    attachLog(`[첨부 검증] 실패 (${checks}회 확인 · 최종 후보 ${finalCandidates.length}개). 패널 미리보기/아이콘/이전 답변 이미지는 제외하고 ChatGPT 입력창 주변 첨부 카드만 검사했습니다.`);
    return false;
  }

  async function tryOpenImageMode(){
    try{
      if(isImageModeActive()) return true;

      // 1) 입력창에 이미 '이미지 만들기' 버튼이 노출돼 있으면 바로 클릭
      const directBtn=findVisibleImageModeButton();
      if(directBtn){
        clickElementLikeUser(directBtn);
        for(let i=0;i<6;i++){ await sleep(250); if(isImageModeActive()) return true; }
      }

      // 2) '+' 메뉴 열고 → '이미지 만들기' 항목 클릭 (메뉴가 뜰 때까지 대기, 최대 2회 재시도)
      for(let attempt=0; attempt<2; attempt++){
        const menuBtn=findComposerMenuButton();
        if(menuBtn) clickElementLikeUser(menuBtn);
        // 메뉴(팝오버)가 실제로 열릴 때까지 대기
        for(let i=0;i<8;i++){
          await sleep(150);
          if(document.querySelector('[role="menu"],[data-radix-popper-content-wrapper],[role="listbox"],[data-radix-menu-content]')) break;
        }
        await sleep(150);
        const clicked=clickImageModeMenuItem() || clickExactComposerText(['이미지 만들기','Create image','Image generation']);
        if(clicked){
          for(let i=0;i<12;i++){ await sleep(250); if(isImageModeActive()) return true; }
        }
        if(isImageModeActive()) return true;
        await sleep(300);
      }
      return isImageModeActive();
    }catch(e){ console.warn(e); return false; }
  }

  function getImageModeSearchRoot(){
    const root=getComposerRootStrict();
    if(!root) return null;
    let cur=root;
    for(let i=0;i<2 && cur?.parentElement;i++) cur=cur.parentElement;
    return cur || root;
  }

  function findVisibleImageModeButton(){
    const panel=$('dp-director-panel');
    const scope=getImageModeSearchRoot() || getComposerRootStrict() || document.body;
    const candidates=[...scope.querySelectorAll('button,[role="button"],[role="option"]')]
      .filter(el=>isVisible(el) && (!panel || !panel.contains(el)));
    return candidates.find(el=>{
      const txt=(el.innerText||el.textContent||'').trim();
      const r=el.getBoundingClientRect();
      return /^(이미지 만들기|Create image|Image generation)$/i.test(txt) && r.top > window.innerHeight*0.45;
    }) || null;
  }

  function clickExactComposerText(words){
    const panel=$('dp-director-panel');
    const scope=getImageModeSearchRoot() || document.body;
    const nodes=[...scope.querySelectorAll('button,[role="menuitem"],[role="option"],div,span')]
      .filter(el=>isVisible(el) && (!panel || !panel.contains(el)));
    const hit=nodes.find(el=>{
      const txt=(el.innerText||el.textContent||'').trim();
      if(!txt || txt.length>60) return false;
      const r=el.getBoundingClientRect();
      return r.top > window.innerHeight*0.35 && words.some(w=>txt===w);
    });
    if(!hit) return false;
    return clickElementLikeUser(hit);
  }

  // v21.8.24.59: '+' 메뉴가 위로 펼쳐져도(스크린샷처럼) 잡히도록, 열린 팝오버/메뉴 내부에서 항목을 찾는다(y좌표 의존 제거).
  function clickImageModeMenuItem(){
    const panel=$('dp-director-panel');
    const words=['이미지 만들기','Create image','Image generation','이미지 생성'];
    const menus=[...document.querySelectorAll('[role="menu"],[role="listbox"],[data-radix-popper-content-wrapper],[data-radix-menu-content]')]
      .filter(isVisible).filter(m=>!panel || !panel.contains(m));
    const pools=menus.length ? menus : [document.body];
    for(const scope of pools){
      const items=[...scope.querySelectorAll('[role="menuitem"],[role="option"],button,div,span')]
        .filter(el=>isVisible(el) && (!panel || !panel.contains(el)));
      const hit=items.find(n=>{
        const t=(n.innerText||n.textContent||'').trim();
        return t && t.length<=40 && words.some(w=>t===w);
      });
      if(hit) return clickElementLikeUser(hit);
    }
    return false;
  }

  // v21.8.24.59: 이미지 모드가 켜지면 입력창에 도구 칩('이미지')이 남는다. 이를 활성 신호로 인정해야
  // 성공 후 isImageModeActive가 false로 오판→메뉴를 또 눌러 모드가 꺼지는 문제를 막는다.
  function hasActiveImageChip(){
    const panel=$('dp-director-panel');
    const root=getComposerRootStrict();
    if(!root) return false;
    return [...root.querySelectorAll('button,[role="button"]')]
      .filter(el=>isVisible(el) && (!panel || !panel.contains(el)))
      .filter(el=>!el.closest('[role="menu"],[role="listbox"],[data-radix-popper-content-wrapper]'))
      .some(el=>/^(이미지|Image)$/.test((el.innerText||el.textContent||'').trim()));
  }
  function isImageModeActive(){
    if(hasActiveImageChip()) return true;
    const panel=$('dp-director-panel');
    const scope=getImageModeSearchRoot() || getComposerRootStrict() || document.body;
    const nodes=[...scope.querySelectorAll('button,[role="button"],[role="option"],[data-state]')]
      .filter(el=>isVisible(el) && (!panel || !panel.contains(el)))
      // v21.8.10: 메뉴 내부 항목은 제외 (메뉴에 보이는 "이미지 만들기"를 모드 활성으로 오판하던 버그 수정)
      .filter(el=>{
        const inMenu = el.closest('[role="menu"], [role="listbox"], [data-radix-popper-content-wrapper], [data-state="open"][role="menu"]');
        if(el.getAttribute('role')==='menuitem') return false;
        return !inMenu;
      });
    return nodes.some(el=>{
      const txt=(el.innerText||el.textContent||'').trim();
      if(!/^(이미지 만들기|Create image|Image generation)$/i.test(txt)) return false;
      const r=el.getBoundingClientRect();
      if(r.top < window.innerHeight*0.4) return false;
      // v21.8.10: 실제 활성 신호가 있을 때만 true (||fallback 제거 - 텍스트만 보고 활성으로 판단하던 버그)
      const stateSignal=((el.getAttribute('aria-pressed')||'')+' '+(el.getAttribute('aria-selected')||'')+' '+(el.getAttribute('data-state')||'')+' '+(String(el.className||''))).toLowerCase();
      return /true|selected|active|checked|current|on/.test(stateSignal);
    });
  }

  function findComposerMenuButton(){
    const panel=$('dp-director-panel');
    const root=getComposerRootStrict();
    const candidates=[];
    const collect=(scope)=>{
      if(!scope) return;
      candidates.push(...[...scope.querySelectorAll('button,[role="button"]')]
        .filter(b=>isVisible(b) && (!panel || !panel.contains(b))));
    };
    collect(root);
    if(!candidates.length){
      const input=findInput();
      const inputRect=input?.getBoundingClientRect();
      const buttons=[...document.querySelectorAll('button,[role="button"]')]
        .filter(b=>isVisible(b) && (!panel || !panel.contains(b)))
        .filter(b=>{
          const r=b.getBoundingClientRect();
          if(inputRect){
            return r.top>inputRect.top-80 && r.bottom<inputRect.bottom+100 && r.left<inputRect.left+180;
          }
          return r.top>window.innerHeight*0.55;
        });
      candidates.push(...buttons);
    }
    const scored=candidates.map(b=>{
      const txt=((b.getAttribute('aria-label')||'')+' '+(b.title||'')+' '+(b.innerText||'')+' '+(b.getAttribute('data-testid')||'')).trim();
      let score=0;
      if(/첨부|파일|사진|upload|attach|add|추가|plus|\+/i.test(txt)) score+=10;
      if((b.innerText||'').trim()==='+') score+=8;
      const r=b.getBoundingClientRect();
      score += Math.max(0, 300-r.left)/100; // 입력창 왼쪽의 + 버튼 선호
      return {b,score,txt};
    }).filter(x=>!/send|전송|mic|마이크|voice|음성|stop|중지/i.test(x.txt));
    scored.sort((a,b)=>b.score-a.score);
    return scored[0]?.b || null;
  }

  function clickMenuItemByText(words){
    const panel=$('dp-director-panel');
    const forbiddenZones=[...document.querySelectorAll('nav,aside,[class*="sidebar"],[class*="Sidebar"],[data-testid*="history"],[class*="conversation"]')];
    const inForbidden=(node)=>forbiddenZones.some(z=>z.contains(node));
    const all=[...document.querySelectorAll('button,[role="menuitem"],[role="option"],div,span')]
      .filter(isVisible)
      .filter(n=>!panel || !panel.contains(n))
      .filter(n=>!inForbidden(n));
    const menuish=all.filter(n=>{
      const r=n.getBoundingClientRect();
      const txt=(n.innerText||n.textContent||'').trim();
      if(!txt || txt.length>90) return false;
      return r.top > window.innerHeight*0.25;
    });
    const exact=menuish.find(n=>words.some(w=>(n.innerText||n.textContent||'').trim()===w));
    if(exact){ exact.click(); return true; }
    const includes=menuish.find(n=>words.some(w=>(n.innerText||n.textContent||'').includes(w)));
    if(includes){ includes.click(); return true; }
    return false;
  }
  function isVisible(el){ const r=el.getBoundingClientRect(); return r.width>0 && r.height>0 && r.bottom>0 && r.top<window.innerHeight; }


  // v21.8.24.65: 백그라운드 탭(다른 탭/최소화)에서 setTimeout이 분당 1회 수준으로 throttling되어
  // 자동 생성 루프가 멈추던 문제 수정. Web Worker 타이머는 백그라운드 throttling이 거의 없어서,
  // sleep을 워커로 구동하면 화면을 안 봐도 섹션이 계속 진행된다. 워커 생성 실패(CSP 등) 시 기존 setTimeout으로 자동 폴백.
  const _timerWorker = (function(){
    try{
      const src = 'self.onmessage=function(e){var d=e.data;setTimeout(function(){self.postMessage(d.id);}, d.ms);};';
      const url = URL.createObjectURL(new Blob([src], {type:'application/javascript'}));
      const w = new Worker(url);
      return w;
    }catch(_){ return null; }
  })();
  const _timerCbs = new Map();
  let _timerSeq = 0;
  let _timerWorkerOk = !!_timerWorker;
  if(_timerWorker){
    _timerWorker.onmessage = (e)=>{ const cb=_timerCbs.get(e.data); if(cb){ _timerCbs.delete(e.data); cb(); } };
    _timerWorker.onerror = ()=>{ _timerWorkerOk = false; }; // 워커 에러 시 이후 호출은 setTimeout 폴백
  }
  function sleep(ms){
    return new Promise(r=>{
      if(_timerWorkerOk){
        const id = ++_timerSeq;
        _timerCbs.set(id, r);
        try{ _timerWorker.postMessage({id, ms}); }
        catch(_){ _timerCbs.delete(id); _timerWorkerOk=false; setTimeout(r, ms); }
      } else {
        setTimeout(r, ms);
      }
    });
  }

  // ===== v21.8.24.18: 생성 섹션 이미지 합치기 (긴 JPG 1장 / PDF) =====
  function setMergeStatus(msg){ const el=$('dp-merge-status'); if(el) el.textContent=msg; log(msg); }
  function tsName(){ const d=new Date(); const p=n=>String(n).padStart(2,'0'); return `${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`; }
  function downloadBlob(blob, filename){
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a'); a.href=url; a.download=filename; a.style.display='none';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 5000);
  }
  function blobToDataURL(blob){ return new Promise((res,rej)=>{ const r=new FileReader(); r.onload=()=>res(r.result); r.onerror=rej; r.readAsDataURL(blob); }); }
  function loadImage(src){ return new Promise((res,rej)=>{ const img=new Image(); img.onload=()=>res(img); img.onerror=()=>rej(new Error('이미지 로드 실패')); img.src=src; }); }
  function dataUrlToBytes(durl){ const b64=String(durl||'').split(',')[1]||''; const bin=atob(b64); const u=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i); return u; }

  // 대화에서 생성된 섹션 이미지를 위→아래 순서로 수집 (아바타/아이콘/첨부썸네일 제외)
  function collectGeneratedSectionImages(){
    const root=document.querySelector('main')||document.body;
    const panel=$('dp-director-panel');
    // v21.8.24.30: 사용자가 '상세페이지 제작용으로 첨부한 원본'은 user 메시지 버블에 뜨므로 제외.
    // 생성 이미지는 assistant 영역/플로팅 양쪽에 뜰 수 있어 user 버블만 배제하고 전체에서 모은다.
    const pool=[...root.querySelectorAll('img')];
    const seen=new Set(); const out=[];
    pool.forEach(img=>{
      if(panel && panel.contains(img)) return;
      if(img.closest && img.closest('[data-message-author-role="user"]')) return; // 첨부 원본 제외
      const src=img.currentSrc||img.getAttribute('src')||'';
      if(!src || seen.has(src)) return;
      const rect=img.getBoundingClientRect ? img.getBoundingClientRect() : {width:0,height:0};
      const w=img.naturalWidth || rect.width || 0;
      const h=img.naturalHeight || rect.height || 0;
      if(w<256 || h<256) return; // 아이콘/아바타/작은 미리보기 제외
      if(/avatar|profile|emoji|favicon|spinner|sprite|icon|logo/i.test(src)) return;
      seen.add(src); out.push({src,w,h});
    });
    return out;
  }

  async function getImageDataURL(src){
    if(/^data:/i.test(src)) return src;
    if(/^blob:/i.test(src)){
      try{ const b=await (await fetch(src)).blob(); return await blobToDataURL(b); }catch(_){ return ''; }
    }
    // http(s) (oaiusercontent 등): canvas 오염 방지 위해 background가 host 권한으로 받아온다
    try{
      const resp=await chrome.runtime.sendMessage({ type:'DP_FETCH_IMAGE', url:src });
      if(resp?.ok && resp.dataUrl) return resp.dataUrl;
    }catch(_){}
    // 마지막 fallback: 직접 fetch (CORS 허용 시)
    try{ const b=await (await fetch(src)).blob(); return await blobToDataURL(b); }catch(_){ return ''; }
  }

  function previewCollectImages(){
    const items=collectGeneratedSectionImages();
    state.collectedImages=items.map(it=>({src:it.src, checked:true}));
    renderMergeList();
    if(items.length) setMergeStatus(`생성 이미지 ${items.length}장 감지. 합칠 이미지를 ✔로 선택(원본/불필요한 건 해제)한 뒤 [세로 1장 JPG]/[PDF]를 누르세요.`);
    else setMergeStatus('생성 이미지를 찾지 못했습니다. 섹션 이미지를 먼저 생성한 뒤 다시 누르세요.');
  }
  // v21.8.24.30: 수집된 이미지를 썸네일+체크박스로 보여줘 합칠 대상을 직접 선택(원본/불필요 제외)
  function renderMergeList(){
    const box=$('dp-merge-list'); if(!box) return;
    const list=state.collectedImages||[];
    if(!list.length){ box.innerHTML=''; return; }
    box.innerHTML=`<div class="dp-help" style="width:100%;margin-bottom:2px">합칠 이미지 선택 (순서대로 ${list.length}장)</div>`+
      list.map((it,i)=>`<label style="position:relative;cursor:pointer;display:inline-block"><img src="${it.src}" referrerpolicy="no-referrer" style="width:58px;height:58px;object-fit:cover;border-radius:6px;border:2px solid ${it.checked?'#059669':'#666'};opacity:${it.checked?'1':'0.35'}"><input type="checkbox" data-i="${i}" ${it.checked?'checked':''} style="position:absolute;top:3px;left:3px"><span style="position:absolute;bottom:1px;right:3px;font-size:10px;color:#fff;text-shadow:0 0 3px #000">${i+1}</span></label>`).join('');
    box.querySelectorAll('input[type=checkbox]').forEach(c=>c.onchange=()=>{ const i=+c.dataset.i; if(state.collectedImages[i]) state.collectedImages[i].checked=c.checked; renderMergeList(); });
  }

  async function loadCollectedImages(){
    if(!state.collectedImages || !state.collectedImages.length){
      state.collectedImages=collectGeneratedSectionImages().map(it=>({src:it.src, checked:true}));
      renderMergeList();
    }
    const items=(state.collectedImages||[]).filter(x=>x.checked);
    if(!items.length) return [];
    const loaded=[];
    for(let i=0;i<items.length;i++){
      setMergeStatus(`이미지 불러오는 중 ${i+1}/${items.length}...`);
      const durl=await getImageDataURL(items[i].src);
      if(!durl) continue;
      try{ loaded.push(await loadImage(durl)); }catch(_){}
    }
    return loaded;
  }

  // 섹션당 1페이지 PDF를 외부 라이브러리 없이 직접 생성 (JPEG=DCTDecode 임베드)
  function buildPdf(pages){
    const parts=[]; let len=0; const enc=new TextEncoder();
    const push=(u8)=>{ parts.push(u8); len+=u8.length; };
    const pushStr=(s)=>push(enc.encode(s));
    const offsets=[];
    const startObj=(n)=>{ offsets[n]=len; pushStr(`${n} 0 obj\n`); };
    const endObj=()=>pushStr('endobj\n');
    pushStr('%PDF-1.4\n');
    push(new Uint8Array([0x25,0xE2,0xE3,0xCF,0xD3,0x0A])); // 바이너리 마커
    const n=pages.length;
    const pageIds=[]; for(let i=0;i<n;i++) pageIds.push(5+i*3);
    startObj(1); pushStr('<< /Type /Catalog /Pages 2 0 R >>\n'); endObj();
    startObj(2); pushStr(`<< /Type /Pages /Kids [${pageIds.map(id=>id+' 0 R').join(' ')}] /Count ${n} >>\n`); endObj();
    for(let i=0;i<n;i++){
      const pg=pages[i];
      const imageId=3+i*3, contentId=4+i*3, pageId=5+i*3;
      startObj(imageId);
      pushStr(`<< /Type /XObject /Subtype /Image /Width ${pg.w} /Height ${pg.h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${pg.bytes.length} >>\nstream\n`);
      push(pg.bytes); pushStr('\nendstream\n'); endObj();
      const content=`q ${pg.w} 0 0 ${pg.h} 0 0 cm /Im0 Do Q\n`;
      const cb=enc.encode(content);
      startObj(contentId);
      pushStr(`<< /Length ${cb.length} >>\nstream\n`); push(cb); pushStr('endstream\n'); endObj();
      startObj(pageId);
      pushStr(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pg.w} ${pg.h}] /Resources << /XObject << /Im0 ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>\n`); endObj();
    }
    const xrefStart=len;
    const total=2+n*3;
    pushStr(`xref\n0 ${total+1}\n0000000000 65535 f \n`);
    for(let i=1;i<=total;i++) pushStr(String(offsets[i]||0).padStart(10,'0')+' 00000 n \n');
    pushStr(`trailer\n<< /Size ${total+1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`);
    const out=new Uint8Array(len); let o=0; parts.forEach(p=>{ out.set(p,o); o+=p.length; });
    return out;
  }

  // ===== v21.8.24.70/71: 정지컷 모션 GIF/영상 (줌·팬·샤인) =====
  // 출력비율(4:5)로 커버-핏한 기준 소스 박스
  function _motionBox(img, W, H){
    const srcAR=img.width/img.height, dstAR=W/H;
    let bw,bh; if(srcAR>dstAR){ bh=img.height; bw=Math.round(bh*dstAR); } else { bw=img.width; bh=Math.round(bw/dstAR); }
    return {bw, bh};
  }
  // 진행도 p(0~1, 선형)로 한 프레임을 캔버스에 그린다. GIF·영상이 같은 모션을 공유.
  function drawMotionFrame(ctx, img, p, opt, W, H, bw, bh){
    const e=p<0.5?2*p*p:1-Math.pow(-2*p+2,2)/2; // easeInOut
    const zoom=opt.zoom?(1+0.14*e):1.0;
    const sw=bw/zoom, sh=bh/zoom;
    const slackX=Math.max(0,img.width-sw), slackY=Math.max(0,img.height-sh);
    const sx=slackX*(opt.pan?(0.18+0.64*e):0.5), sy=slackY*0.5;
    ctx.clearRect(0,0,W,H);
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, W, H);
    if(opt.shine){
      const pos=(-0.35+1.7*p)*W, w=W*0.16;
      const grad=ctx.createLinearGradient(pos-w,0,pos+w,H*0.25);
      grad.addColorStop(0,'rgba(255,255,255,0)');
      grad.addColorStop(0.5,'rgba(255,255,255,0.26)');
      grad.addColorStop(1,'rgba(255,255,255,0)');
      ctx.save(); ctx.globalCompositeOperation='lighter'; ctx.fillStyle=grad; ctx.fillRect(0,0,W,H); ctx.restore();
    }
  }
  // ----- v21.8.24.72: 요소 애니메이션 (카피·카드 순차 등장) -----
  function _ease(p){ return p<0.5?2*p*p:1-Math.pow(-2*p+2,2)/2; }
  function _reveal(p, start, dur){ if(p<=start) return 0; if(p>=start+dur) return 1; return _ease((p-start)/dur); }
  function _rr(ctx,x,y,w,h,r){ r=Math.min(r,w/2,h/2); ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r); ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath(); }
  // A: { copy:{main,sub,cards}, accent, isHero }  — 배경은 살짝 줌, 그 위에 카피/카드가 시간차로 등장
  function drawElementFrame(ctx, img, p, A, W, H, bw, bh){
    const e=_ease(p), zoom=1+0.06*e, sw=bw/zoom, sh=bh/zoom;
    const slackX=Math.max(0,img.width-sw), slackY=Math.max(0,img.height-sh);
    ctx.clearRect(0,0,W,H);
    ctx.drawImage(img, slackX*0.5, slackY*0.5, sw, sh, 0,0,W,H);
    const padX=Math.round(W*0.07), accent=A.accent, copy=A.copy;
    // 헤드라인 영역
    const headR=_reveal(p,0.08,0.22);
    if(headR>0 && copy.main){
      const bandH=Math.round(H*0.34);
      const g=ctx.createLinearGradient(0,0,0,bandH);
      g.addColorStop(0,'rgba(255,255,255,0.96)'); g.addColorStop(0.6,'rgba(255,255,255,0.9)'); g.addColorStop(1,'rgba(255,255,255,0)');
      ctx.save(); ctx.globalAlpha=Math.min(1,headR*1.3); ctx.fillStyle=g; ctx.fillRect(0,0,W,bandH); ctx.restore();
      const hSize=Math.round(W*(A.isHero?0.082:0.066));
      ctx.save(); ctx.globalAlpha=headR; ctx.translate(0,(1-headR)*Math.round(H*0.04));
      ctx.textBaseline='top'; ctx.textAlign='left';
      ctx.font=`800 ${hSize}px ${DP_KR_FONT}`; ctx.fillStyle='#191919';
      let y=Math.round(H*0.06);
      const mainLines=wrapTextLines(ctx,copy.main,W-padX*2,2);
      mainLines.forEach(ln=>{ ctx.fillText(ln,padX,y); y+=Math.round(hSize*1.16); });
      ctx.fillStyle=accent; ctx.fillRect(padX,y+Math.round(hSize*0.06),Math.round(W*0.11),Math.max(4,Math.round(hSize*0.1)));
      ctx.restore();
      if(copy.sub){
        const subR=_reveal(p,0.30,0.16);
        if(subR>0){
          const sSize=Math.round(W*0.036);
          const subY=Math.round(H*0.06)+mainLines.length*Math.round(hSize*1.16)+Math.round(hSize*0.55);
          ctx.save(); ctx.globalAlpha=subR; ctx.textBaseline='top'; ctx.textAlign='left';
          ctx.font=`500 ${sSize}px ${DP_KR_FONT}`; ctx.fillStyle='#3a3a3a';
          let y2=subY; wrapTextLines(ctx,copy.sub,W-padX*2,2).forEach(ln=>{ ctx.fillText(ln,padX,y2); y2+=Math.round(sSize*1.3); });
          ctx.restore();
        }
      }
    }
    // 하단 카드 순차 등장
    const cards=(copy.cards||[]).slice(0,3);
    if(cards.length){
      const cardW=W-padX*2, cardH=Math.round(H*0.105), gap=Math.round(H*0.022);
      const totalH=cards.length*cardH+(cards.length-1)*gap;
      let cy=H-Math.round(H*0.06)-totalH;
      for(let i=0;i<cards.length;i++){
        const c=cards[i], cr=_reveal(p,0.46+i*0.13,0.14);
        if(cr>0){
          const sc=0.86+0.14*cr, cx=padX, drawY=cy+(1-cr)*Math.round(H*0.02);
          ctx.save(); ctx.globalAlpha=cr;
          ctx.translate(cx+cardW/2,drawY+cardH/2); ctx.scale(sc,sc); ctx.translate(-(cx+cardW/2),-(drawY+cardH/2));
          ctx.fillStyle='rgba(255,255,255,0.95)'; _rr(ctx,cx,drawY,cardW,cardH,Math.round(cardH*0.22)); ctx.fill();
          ctx.fillStyle=accent; const dotR=Math.round(cardH*0.15); ctx.beginPath(); ctx.arc(cx+Math.round(cardW*0.065),drawY+cardH/2,dotR,0,Math.PI*2); ctx.fill();
          const tx=cx+Math.round(cardW*0.13), hS=Math.round(cardH*0.30), dS=Math.round(cardH*0.22);
          ctx.textBaseline='middle'; ctx.textAlign='left';
          ctx.fillStyle='#1a1a1a'; ctx.font=`700 ${hS}px ${DP_KR_FONT}`;
          ctx.fillText(String(c.head||'').slice(0,18), tx, c.desc?drawY+cardH*0.36:drawY+cardH*0.5);
          if(c.desc){ ctx.fillStyle='#5a5a5a'; ctx.font=`400 ${dS}px ${DP_KR_FONT}`; ctx.fillText(String(c.desc).slice(0,30), tx, drawY+cardH*0.68); }
          ctx.restore();
        }
        cy+=cardH+gap;
      }
    }
  }
  // 위치별 2단계 카피 자동 선택
  function getCopyForPosition(position){
    const ps=state.shortImagePrompts||[];
    if(!ps.length) return null;
    const find=(names)=>ps.find(p=>names.indexOf(p.section)>=0);
    let sec;
    if(position==='top') sec=find(['HERO'])||ps[0];
    else if(position==='bottom') sec=find(['CTA'])||ps[ps.length-1];
    else sec=find(['BENEFIT','FEATURE','OVERVIEW','SOLUTION','POINT','USAGE'])||ps[Math.floor(ps.length/2)]||ps[0];
    return (sec && sec.copy && sec.copy.main) ? {copy:sec.copy, section:sec.section} : null;
  }

  // ----- 범용 프레임/녹화: 매 프레임을 그리는 drawFn(ctx,p)를 받는다 -----
  function framesFromDrawer(drawFn, W, H, N){
    N=Math.max(2,N|0);
    const cvs=document.createElement('canvas'); cvs.width=W; cvs.height=H;
    const ctx=cvs.getContext('2d',{willReadFrequently:true});
    const frames=[];
    for(let i=0;i<N;i++){ drawFn(ctx, i/(N-1)); frames.push({data:ctx.getImageData(0,0,W,H).data, width:W, height:H}); }
    return frames;
  }
  async function webmFromDrawer(drawFn, W, H, secs){
    if(typeof MediaRecorder==='undefined') throw new Error('이 브라우저는 영상 녹화(MediaRecorder)를 지원하지 않습니다.');
    const cvs=document.createElement('canvas'); cvs.width=W; cvs.height=H;
    if(!cvs.captureStream) throw new Error('이 브라우저는 캔버스 녹화를 지원하지 않습니다.');
    const ctx=cvs.getContext('2d');
    const stream=cvs.captureStream(30);
    let mime='video/webm;codecs=vp9';
    if(!(MediaRecorder.isTypeSupported&&MediaRecorder.isTypeSupported(mime))) mime=(MediaRecorder.isTypeSupported&&MediaRecorder.isTypeSupported('video/webm;codecs=vp8'))?'video/webm;codecs=vp8':'video/webm';
    const rec=new MediaRecorder(stream,{mimeType:mime, videoBitsPerSecond:8000000});
    const chunks=[]; rec.ondataavailable=ev=>{ if(ev.data&&ev.data.size) chunks.push(ev.data); };
    const stopped=new Promise(r=>{ rec.onstop=r; });
    drawFn(ctx,0); rec.start();
    const dur=Math.max(500,secs*1000), start=performance.now();
    await new Promise(res=>{ function tick(now){ const p=Math.min(1,(now-start)/dur); drawFn(ctx,p); if(p<1) requestAnimationFrame(tick); else res(); } requestAnimationFrame(tick); });
    await sleep(150); rec.stop(); await stopped;
    return new Blob(chunks,{type:'video/webm'});
  }

  // 한 컷 → 움짤 Blob (요소 애니메이션: copyObj 있으면 / 없으면 심플 모션)
  async function buildClipBlob(img, copyObj, fmt, W, H, N, secs, style){
    const {bw,bh}=_motionBox(img,W,H);
    let drawFn;
    if(style==='element' && copyObj){
      const A={ copy:copyObj.copy, accent:overlayAccent(state.lastDesignLabel||''), isHero:copyObj.section==='HERO' };
      drawFn=(ctx,p)=>drawElementFrame(ctx, img, p, A, W, H, bw, bh);
    } else {
      drawFn=(ctx,p)=>drawMotionFrame(ctx, img, p, {zoom:true,pan:true,shine:true}, W, H, bw, bh);
    }
    if(fmt==='webm'){ return {blob:await webmFromDrawer(drawFn, W, H, secs), ext:'webm'}; }
    if(!window.DP_GIF) throw new Error('GIF 인코더 미로드 — 확장을 새로고침하세요.');
    const frames=framesFromDrawer(drawFn, W, H, N);
    const bytes=window.DP_GIF.fromFrames(frames, {delayMs:Math.max(40,Math.round(secs*1000/frames.length)), loop:0});
    return {blob:new Blob([bytes],{type:'image/gif'}), ext:'gif'};
  }

  // v21.8.24.80: '군데군데' 움짤로 만들 위치를 자동 선택(HERO는 항상 + 빈도에 따라 간격)
  function pickGifIndices(n, freq){
    const set=new Set();
    if(n<=0) return set;
    set.add(0); // 첫 컷(HERO/후킹)은 항상 움짤
    const step = freq==='high' ? 2 : (freq==='low' ? 4 : 3);
    for(let i=step; i<n; i+=step) set.add(i);
    // 마지막(CTA)도 움짤로 마무리 임팩트(보통/많이일 때)
    if(freq!=='low' && n>2) set.add(n-1);
    return set;
  }
  // v21.8.24.80: 상세페이지 '완성' 묶음 — ✔ 수집 컷을 순서대로, 일부는 움짤(GIF)로 자동 변환해 한 번에 내보낸다.
  // 결과: detail_01_HERO.jpg, detail_02_PROBLEM.gif ... (순서대로 상세페이지에 업로드)
  async function exportDetailBundle(){
    let list=state.collectedImages||[];
    if(!list.length){ list=collectGeneratedSectionImages().map(it=>({src:it.src,checked:true})); state.collectedImages=list; renderMergeList(); }
    const items=list.map((x,k)=>({src:x.src, k, checked:x.checked})).filter(x=>x.checked);
    if(!items.length){ setMergeStatus('내보낼 컷이 없습니다. ④ [생성 이미지 수집] 후 컷을 ✔ 선택하세요.'); return; }
    if(!window.DP_GIF){ setMergeStatus('GIF 인코더 미로드 — 확장을 새로고침하세요.'); return; }
    const ps=state.shortImagePrompts||[];
    const freq=$('dp-bundle-freq')?.value||'mid';
    const style=$('dp-gif-style')?.value||'element';
    const W=parseInt($('dp-gif-width')?.value||'600',10), H=Math.round(W*5/4);
    const N=parseInt($('dp-gif-frames')?.value||'20',10), secs=parseFloat($('dp-gif-secs')?.value||'2');
    const gifSet=pickGifIndices(items.length, freq);
    const imgPrev=$('dp-gif-preview'), vidPrev=$('dp-gif-vpreview');
    try{
      setBusy(true);
      let out=0, gifCount=0;
      const zipEntries=[];
      for(let pos=0; pos<items.length; pos++){
        const it=items[pos]; const sec=ps[it.k];
        const secName=(sec && sec.section) || ('컷'+(it.k+1));
        const isGif=gifSet.has(pos);
        setMergeStatus(`묶음 만드는 중 ${pos+1}/${items.length} (${secName}, ${isGif?'움짤':'이미지'})...`);
        const durl=await getImageDataURL(it.src); if(!durl) continue;
        const img=await loadImage(durl);
        await sleep(10);
        let blob, ext;
        if(isGif){
          const copyObj=(sec && sec.copy && sec.copy.main)?{copy:sec.copy, section:sec.section}:null;
          const r=await buildClipBlob(img, copyObj, 'gif', W, H, N, secs, style);
          blob=r.blob; ext=r.ext; gifCount++;
          if(imgPrev && blob){ const u=URL.createObjectURL(blob); imgPrev.src=u; imgPrev.style.display='block'; if(vidPrev) vidPrev.style.display='none'; setTimeout(()=>URL.revokeObjectURL(u),120000); }
        } else {
          const nw=img.naturalWidth||img.width||1080, nh=img.naturalHeight||img.height||1350;
          const JW=1080, JH=Math.max(1,Math.round(nh*(JW/nw)));
          const c=document.createElement('canvas'); c.width=JW; c.height=JH;
          const cx=c.getContext('2d'); cx.fillStyle='#fff'; cx.fillRect(0,0,JW,JH); cx.drawImage(img,0,0,JW,JH);
          blob=await new Promise(r=>c.toBlob(r,'image/jpeg',0.92)); ext='jpg';
        }
        if(blob && blob.size){
          zipEntries.push({ name: `detail_${String(pos+1).padStart(2,'0')}_${secName}.${ext}`, blob });
          out++;
        }
      }
      // v21.8.24.92: 파일 N개 연속 다운로드(차단/순서 섞임/저장 꼬임) 대신 ZIP 1개로 묶어 내보냄.
      if(zipEntries.length && window.DP_ZIP){
        setMergeStatus(`ZIP으로 묶는 중... (${zipEntries.length}개 파일)`);
        const files=[]; for(const e of zipEntries){ files.push({ name:e.name, bytes:new Uint8Array(await e.blob.arrayBuffer()) }); }
        const zipBytes = window.DP_ZIP.make(files);
        downloadBlob(new Blob([zipBytes], {type:'application/zip'}), `detail_pack_${tsName()}.zip`);
        setMergeStatus(`✅ detail_pack.zip 1개로 내보냄 (컷 ${out}개 · 움짤 ${gifCount}개 군데군데). 압축 풀면 detail_01~ 순서 그대로 업로드하면 됩니다.`);
      } else if(zipEntries.length){
        for(const e of zipEntries){ downloadBlob(e.blob, e.name); await sleep(500); }
        setMergeStatus(`✅ 상세페이지 묶음 ${out}개 내보냄 (움짤 ${gifCount}개 군데군데 포함). detail_01~ 순서 그대로 업로드하세요.`);
      } else {
        setMergeStatus('내보낼 결과가 없습니다(이미지 접근 실패 가능). 다시 시도해 주세요.');
      }
    }catch(e){
      setMergeStatus('묶음 내보내기 실패: '+(e&&e.message||e));
    }finally{ setBusy(false); }
  }

  // 스마트스토어식: ✔ 선택한 섹션 컷들을 각각(컷마다) 움짤로 만든다. 각 컷은 같은 순서의 2단계 카피와 짝지음.
  async function makeClipsBatch(){
    const fmt=$('dp-gif-format')?.value || 'gif';
    const style=$('dp-gif-style')?.value || 'element';
    const list=state.collectedImages||[];
    let idxs=list.map((x,k)=>x.checked?k:-1).filter(k=>k>=0);
    // 수집이 없으면 첨부 원본 1장으로라도
    if(!idxs.length && !(state.images[0])){ setMergeStatus('움짤로 만들 컷이 없습니다. ④에서 [생성 이미지 수집] 후 컷을 ✔ 선택하세요.'); return; }
    const ps=state.shortImagePrompts||[];
    if(style==='element' && !ps.length) log('2단계 카피가 없어 심플(줌·팬) 모션으로 만듭니다. 카피가 살아 움직이게 하려면 2단계 카피기획을 먼저 하세요.');
    if(list.length && ps.length && list.length!==ps.length) log(`⚠️ 수집 ${list.length}장 ≠ 섹션 ${ps.length}개. 카피가 컷과 어긋날 수 있으니 수집에서 원본/실패컷을 빼고 섹션 순서대로 두세요.`);
    const W=parseInt($('dp-gif-width')?.value||'600',10), H=Math.round(W*5/4);
    const N=parseInt($('dp-gif-frames')?.value||'20',10), secs=parseFloat($('dp-gif-secs')?.value||'2');
    const imgPrev=$('dp-gif-preview'), vidPrev=$('dp-gif-vpreview');
    const sources = idxs.length ? idxs.map(k=>({src:list[k].src, k})) : [{src:state.images[0].url, k:0}];
    try{
      setBusy(true);
      let done=0;
      const zipEntries=[];
      for(let n=0;n<sources.length;n++){
        const {src,k}=sources[n];
        const sec=ps[k];
        const copyObj=(sec && sec.copy && sec.copy.main)?{copy:sec.copy, section:sec.section}:null;
        const secName=(sec && sec.section) || ('컷'+(k+1));
        setMergeStatus(`움짤 만드는 중... ${n+1}/${sources.length} (${secName}, ${fmt==='webm'?'영상':'GIF'})`);
        const durl=await getImageDataURL(src); if(!durl){ continue; }
        const img=await loadImage(durl);
        await sleep(15);
        const {blob,ext}=await buildClipBlob(img, copyObj, fmt, W, H, N, secs, style);
        if(blob && blob.size){
          const url=URL.createObjectURL(blob);
          if(ext==='webm' && vidPrev){ vidPrev.src=url; vidPrev.style.display='block'; if(imgPrev) imgPrev.style.display='none'; vidPrev.play&&vidPrev.play().catch(()=>{}); }
          else if(imgPrev){ imgPrev.src=url; imgPrev.style.display='block'; if(vidPrev) vidPrev.style.display='none'; }
          setTimeout(()=>URL.revokeObjectURL(url), 120000);
          zipEntries.push({ name:`detail_${String(n+1).padStart(2,'0')}_${secName}.${ext}`, blob });
          done++;
        }
      }
      // v21.8.24.92: 움짤들도 ZIP 1개로 묶어 내보냄(다중 다운로드 차단 회피).
      if(zipEntries.length && window.DP_ZIP){
        setMergeStatus(`ZIP으로 묶는 중... (${zipEntries.length}개)`);
        const files=[]; for(const e of zipEntries){ files.push({ name:e.name, bytes:new Uint8Array(await e.blob.arrayBuffer()) }); }
        downloadBlob(new Blob([window.DP_ZIP.make(files)], {type:'application/zip'}), `detail_clips_${tsName()}.zip`);
        setMergeStatus(`✅ 움짤 ${done}개를 detail_clips.zip 1개로 내보냈습니다(${fmt==='webm'?'영상':'GIF'}). 압축 풀어 순서대로 끼워 넣으세요.`);
      } else {
        for(const e of zipEntries){ downloadBlob(e.blob, e.name); await sleep(500); }
        setMergeStatus(`✅ 움짤 ${done}개 생성 완료(${fmt==='webm'?'영상':'GIF'}). 파일명 detail_01~ 순서 = 섹션 순서.`);
      }
    }catch(e){
      setMergeStatus('움짤 생성 실패: '+(e&&e.message||e));
    }finally{ setBusy(false); }
  }

  // ===== v21.8.24.41: 글자 오버레이 엔진 (비주얼은 AI, 헤드라인은 시스템 한글폰트로 직접 렌더) =====
  const DP_KR_FONT = "Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', AppleGothic, system-ui, sans-serif";
  function overlayAccent(label){
    const map={'다크 프리미엄':'#C9A24B','강한 전환형':'#FF3B30','비비드 팝':'#2563EB','오렌지 미니멀':'#FF6B1A','프레시 클린':'#14B8A6','트렌디 MZ형':'#EC4899','신뢰 블루 정보형':'#1D4ED8','테크 대시보드형':'#06B6D4','하이엔드 브랜드형':'#B08D57','매거진 에디토리얼':'#B91C1C','모던 라이프스타일':'#1E3A5F','여성감성 소프트':'#CC9999','감성 뉴트럴':'#C36A4D','웜 내추럴':'#9CA891','스포티 액티브':'#FF6A00','클린 화이트':'#2563EB'};
    return map[label] || '#FF6B1A';
  }
  function wrapTextLines(ctx, text, maxW, maxLines){
    const chars=String(text||'').split(''); const lines=[]; let cur='';
    for(const ch of chars){
      const test=cur+ch;
      if(ctx.measureText(test).width>maxW && cur){ lines.push(cur); cur=ch; if(lines.length>=(maxLines||2)) break; }
      else cur=test;
    }
    if(cur && lines.length<(maxLines||2)) lines.push(cur);
    return lines;
  }
  function drawTextOverlay(ctx, W, H, copy, isHero, accent){
    if(!copy || !copy.main) return;
    const bandH=Math.round(H*(isHero?0.36:0.30));
    const g=ctx.createLinearGradient(0,0,0,bandH);
    g.addColorStop(0,'rgba(255,255,255,0.97)'); g.addColorStop(0.62,'rgba(255,255,255,0.92)'); g.addColorStop(1,'rgba(255,255,255,0)');
    ctx.fillStyle=g; ctx.fillRect(0,0,W,bandH);
    const padX=Math.round(W*0.07); let y=Math.round(H*0.055);
    const hSize=Math.round(W*(isHero?0.082:0.064));
    ctx.textBaseline='top'; ctx.textAlign='left';
    ctx.font=`800 ${hSize}px ${DP_KR_FONT}`; ctx.fillStyle='#191919';
    wrapTextLines(ctx, copy.main, W-padX*2, 2).forEach(ln=>{ ctx.fillText(ln,padX,y); y+=Math.round(hSize*1.16); });
    ctx.fillStyle=accent; ctx.fillRect(padX, y+Math.round(hSize*0.10), Math.round(W*0.11), Math.max(4,Math.round(hSize*0.11)));
    y+=Math.round(hSize*0.5);
    if(copy.sub){
      const sSize=Math.round(W*0.035);
      ctx.font=`500 ${sSize}px ${DP_KR_FONT}`; ctx.fillStyle='#454545';
      y+=Math.round(sSize*0.5);
      wrapTextLines(ctx, copy.sub, W-padX*2, 2).forEach(ln=>{ ctx.fillText(ln,padX,y); y+=Math.round(sSize*1.3); });
    }
  }
  function compositeOverlay(img, copy, isHero, accent, targetW){
    const nw=img.naturalWidth||img.width||targetW, nh=img.naturalHeight||img.height||targetW;
    const W=targetW, H=Math.max(1,Math.round(nh*(targetW/nw)));
    const c=document.createElement('canvas'); c.width=W; c.height=H;
    const ctx=c.getContext('2d'); ctx.fillStyle='#fff'; ctx.fillRect(0,0,W,H);
    ctx.drawImage(img,0,0,W,H);
    try{ drawTextOverlay(ctx,W,H,copy,isHero,accent); }catch(_){}
    return c;
  }
  // 오버레이 모드일 때 수집 이미지에 섹션 카피를 입혀 캔버스 배열로 반환(아니면 원본 그대로)
  function prepareRenderImages(imgs, targetW){
    const overlayOn = !!$('dp-text-overlay')?.checked;
    if(!overlayOn) return imgs;
    const accent = overlayAccent(state.lastDesignLabel||'');
    const ps = state.shortImagePrompts||[];
    if(ps.length && imgs.length !== ps.length){
      log(`⚠️ 수집 이미지 ${imgs.length}장 ≠ 섹션 ${ps.length}개. 글자가 섹션과 어긋날 수 있으니, 수집에서 원본/실패 컷을 빼고 섹션 순서대로 ${ps.length}장만 선택하세요.`);
    }
    let applied=0;
    const out = imgs.map((im,j)=>{
      const sec = ps[j];
      const copy = sec && sec.copy;
      const isHero = (sec && sec.section==='HERO') || j===0;
      if(copy && copy.main){ applied++; return compositeOverlay(im, copy, isHero, accent, targetW); }
      return im;
    });
    if(applied) log(`🅰️ 글자 오버레이 적용: ${applied}개 섹션에 헤드라인 직접 입힘`);
    else log('🅰️ 글자 오버레이 ON이지만 카피 매핑이 없어(2단계 카피기획 필요) 원본 그대로 합칩니다.');
    return out;
  }

  async function mergeSectionImages(format){
    setBusy(true);
    try{
      const loaded=await loadCollectedImages();
      if(!loaded.length){ setMergeStatus('합칠 이미지를 찾지 못했습니다. 먼저 섹션 이미지를 생성하세요.'); return; }

      if(format==='jpg'){
        const targetW=1080;
        const imgs=prepareRenderImages(loaded, targetW);
        const rows=imgs.map(im=>{ const nw=im.naturalWidth||im.width||targetW; const nh=im.naturalHeight||im.height||1; const h=Math.max(1,Math.round(nh*(targetW/nw))); return {im,h}; });
        // v21.8.24.84: v79 크로스페이드(destination-in 2회)가 임시 캔버스를 통째로 투명화시켜 2번째 이후 컷이 안 그려지던 버그 수정.
        // → 투명 처리 없이 단순 적층(모든 컷을 직접 그림)으로 되돌림. 확실히 작동.
        const sumH=rows.reduce((a,r)=>a+r.h,0);
        const MAX_SIDE=32760;
        const scale=sumH>MAX_SIDE ? MAX_SIDE/sumH : 1;
        const cw=Math.max(1,Math.round(targetW*scale));
        const ch=Math.max(1,Math.round(sumH*scale));
        const canvas=document.createElement('canvas'); canvas.width=cw; canvas.height=ch;
        const ctx=canvas.getContext('2d'); ctx.fillStyle='#ffffff'; ctx.fillRect(0,0,cw,ch);
        let y=0;
        rows.forEach(({im,h})=>{ const dh=Math.max(1,Math.round(h*scale)); ctx.drawImage(im,0,y,cw,dh); y+=dh; });
        const blob=await new Promise(res=>canvas.toBlob(res,'image/jpeg',0.92));
        if(!blob){ setMergeStatus('JPG 생성 실패(이미지가 보호되어 캔버스를 읽지 못했을 수 있음).'); return; }
        downloadBlob(blob, `detailpage_merged_${tsName()}.jpg`);
        setMergeStatus(`✅ ${imgs.length}장을 세로로 이어붙여 JPG로 저장했습니다. (폭 ${cw}px)`);
      } else {
        const pages=[];
        // v21.8.24.30: 모든 페이지 폭을 동일하게 통일(가로 사이즈가 제각각이던 문제 해결)
        const PDF_W=1000;
        const imgs=prepareRenderImages(loaded, PDF_W);
        for(let i=0;i<imgs.length;i++){
          setMergeStatus(`PDF 페이지 만드는 중 ${i+1}/${imgs.length}...`);
          const im=imgs[i];
          const nw=im.naturalWidth||im.width||PDF_W, nh=im.naturalHeight||im.height||PDF_W;
          const w=PDF_W;
          const h=Math.max(1,Math.round(nh*(PDF_W/nw)));
          const c=document.createElement('canvas'); c.width=w; c.height=h;
          const cx=c.getContext('2d'); cx.fillStyle='#ffffff'; cx.fillRect(0,0,w,h); cx.drawImage(im,0,0,w,h);
          let durl; try{ durl=c.toDataURL('image/jpeg',0.92); }catch(e){ setMergeStatus('PDF 생성 실패(이미지 보호로 캔버스를 읽지 못함).'); return; }
          pages.push({ bytes:dataUrlToBytes(durl), w, h });
        }
        const pdf=buildPdf(pages);
        downloadBlob(new Blob([pdf],{type:'application/pdf'}), `detailpage_${tsName()}.pdf`);
        setMergeStatus(`✅ ${pages.length}장을 PDF(섹션당 1페이지)로 저장했습니다.`);
      }
    }catch(e){ console.error(e); setMergeStatus('합치기 오류: '+(e?.message||e)); }
    finally{ setBusy(false); }
  }


  function manualFactKey(line=''){
    const key=String(line||'').split(/[:：]/)[0].replace(/\s+/g,' ').trim();
    if(/색상\s*옵션|현재\s*선택된\s*색상|색상계열|^색상$|^컬러$/i.test(key)) return 'color';
    if(/사이즈\s*옵션|현재\s*선택된\s*사이즈|^사이즈$/i.test(key)) return 'size';
    if(/소재|재질|겉감|안감|혼용률/i.test(key)) return 'material';
    if(/제조국|원산지/i.test(key)) return 'origin';
    if(/치수|크기|가로|세로|폭|높이|무게|중량/i.test(key)) return 'dimension';
    if(/구성|구성품|수량|개수/i.test(key)) return 'components';
    if(/세탁|취급주의/i.test(key)) return 'care';
    return key || '';
  }

  function mergeManualFactsWithSpecs(manual='', specs=''){
    const manualLines=String(manual||'').split(/\n+/).map(x=>x.trim()).filter(Boolean);
    const specLines=String(specs||'').split(/\n+/).map(x=>x.trim()).filter(Boolean);
    if(!manualLines.length) return specLines.join('\n');
    const manualKeys=new Set(manualLines.map(manualFactKey).filter(Boolean));
    const keptSpecs=specLines.filter(line=>{
      const key=manualFactKey(line);
      if(!key) return true;
      return !manualKeys.has(key);
    });
    const out=['[사용자 직접 확인 정보 - 자동수집보다 우선]', ...manualLines];
    if(keptSpecs.length) out.push('', '[자동 수집 참고 정보]', ...keptSpecs);
    return out.join('\n').trim();
  }

  function normalizeFetchedPrice(raw){
    const digits = String(raw || '').replace(/[^\d]/g, '');
    return digits ? Number(digits).toLocaleString('ko-KR') + '원' : '';
  }

  function buildFetchedSpecText(data){
    const lines=[];
    // v21.8.24.2: 제품진단에는 페이지 전체 설명이 아니라 정제된 사실 요약만 전달한다.
    if(data?.factSummary) lines.push('[링크에서 확인된 사실 요약]\n'+String(data.factSummary).trim());
    else if(data?.specs) lines.push('[링크에서 확인된 스펙]\n'+String(data.specs).trim());
    return lines.join('\n\n').trim();
  }

  function buildSpecInstructionBlock(specs){
    const s=String(specs||'').trim();
    if(!s || /^확인\s*필요$/i.test(s)) return '';
    return `\n[사용자 직접 확인 정보 + 링크/상세정보 - 사용자 입력값 최우선 반영]\n${s}\n\n규칙:\n- 위에 명시된 소재/사이즈/색상/구성품/수납/옵션만 확인된 정보로 봅니다.\n- 위에 없는 소재, 전체 사이즈 범위, 리뷰 수, 별점, 판매량, 인증, 수상 정보는 절대 만들지 마세요.\n- 특정 옵션 하나만 확인된 경우 그것을 전체 옵션처럼 단정하지 마세요.\n- \"확인 필요\", \"상세페이지 참조\", \"상품페이지 참고\", \"미확인\" 같은 도망 문구는 이미지 안 문구로 쓰지 말고, 정보가 부족한 항목은 카피에서 제외하세요.\n`;
  }

  const DP_BANNED_COPY_NOTICE = `\n[카피 금지어/대체 규칙 - 반드시 준수]\n아래 표현은 이미지 안 문구와 카피 기획서에서 사용하지 마세요.\n금지: \"첫인상\", \"단정함\", \"비즈니스 무드\", \"깔끔한 인상\"\n대체 방향:\n- 첫인상 → 꺼내는 순간 / 전달의 순간 / 손끝의 완성도\n- 단정함 → 정돈된 형태 / 차분한 균형 / 절제된 디자인\n- 비즈니스 무드 → 업무 자리 / 미팅 자리 / 상담 자리\n- 깔끔한 인상 → 흐트러짐 없는 보관 / 정리된 전달감 / 정돈된 사용감\n추상적인 분위기 말보다 링크에서 확인된 스펙, 제품 디테일, 실제 사용 상황을 우선 사용하세요.\n`;

  function applyFetchedText(el, value, label, filled){
    if (!el || !value) return;
    el.value = String(value).trim();
    el.dispatchEvent(new Event('input', { bubbles: true }));
    filled.push(label);
  }

  // v20.9: 상품 링크 분석 - fetch 실패/403 시 background 탭 보조 분석

  function normalizeProductUrlInput(raw){
    const value = String(raw || '').trim();
    if (!value) return '';
    if (/^\/\//.test(value)) return 'https:' + value;
    if (/^\/vp\/products\//i.test(value)) return 'https://www.coupang.com' + value;
    if (/^vp\/products\//i.test(value)) return 'https://www.coupang.com/' + value;
    return value;
  }

  async function fetchProductLink(){
    const linkInput = $('dp-link');
    const rawUrl = (linkInput?.value || '').trim();
    const url = normalizeProductUrlInput(rawUrl);
    const statusEl = $('dp-fetch-status');
    const resultEl = $('dp-fetch-result');
    if (!url) {
      if (statusEl) statusEl.textContent = '⚠️ 상품 링크를 먼저 입력하세요.';
      log('상품 링크를 먼저 입력하세요.');
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      if (statusEl) statusEl.textContent = '⚠️ https:// 로 시작하거나 /vp/products/... 형태의 쿠팡 링크를 입력하세요.';
      log('상품 링크 형식이 올바르지 않습니다.');
      return;
    }
    if (linkInput && linkInput.value !== url) linkInput.value = url;

    setBusy(true);
    if (statusEl) statusEl.textContent = '⏳ 페이지 분석 중... 403이면 브라우저 탭 보조 분석을 자동 시도합니다.';
    if (resultEl) { resultEl.style.display='none'; resultEl.textContent=''; }
    log(`상품 링크 분석 시작: ${url.slice(0,80)}`);

    try {
      const response = await chrome.runtime.sendMessage({ type: 'DP_FETCH_PRODUCT_PAGE', url });
      if (!response?.ok) {
        const reason = response?.error || '알 수 없는 오류';
        // v21.8.24.96: 크롤링 실패(403/차단/시간초과)여도 막다른 끝이 되지 않게 안내한다.
        //   링크 자동수집은 보조 수단일 뿐이라, 상품명만 직접 입력하고 참고 이미지를 올리면 그대로 제작을 진행할 수 있다.
        const is403 = /403|차단|응답 오류|시간 초과|찾지 못/i.test(reason);
        if (statusEl) {
          statusEl.innerHTML = is403
            ? `⚠️ 자동 수집 실패: ${esc(reason)}<br><span style="color:#8ab4ff">쇼핑몰이 외부 분석을 막은 경우입니다. <b>상품명·가격을 직접 입력</b>하고 <b>참고 이미지를 올리면</b> 그대로 제작을 진행할 수 있어요.</span>`
            : `❌ 실패: ${esc(reason)}`;
        }
        log(`링크 분석 실패(수동 진행 가능): ${reason}`);
        return;
      }

      const data = response.data || {};
      const filled = [];
      const priceLabel = normalizeFetchedPrice(data.price);
      const methodLabel = response.method === 'tab_fallback' ? '브라우저 탭 보조 분석' : response.method === 'fetch+page_observation' ? '링크 분석 + 상품페이지 자동 관찰' : response.method === 'fetch_partial_timeout' ? '부분 분석(탭 시간 초과)' : '메타 fetch 분석';

      // v21.8.24.24: 직전 분석과 다른 상품이면 이전 제품의 진단/카피/추정/스펙을 먼저 초기화(품목 섞임 방지)
      const newSig = 'L:' + String(url).trim().toLowerCase().replace(/[#?].*$/, '');
      if (state.lastProductSig && state.lastProductSig !== newSig) {
        clearStaleForNewProduct('링크 변경');
      }
      state.lastProductSig = newSig;

      applyFetchedText($('dp-product'), data.title ? data.title.slice(0, 90) : '', '상품명', filled);
      if (priceLabel) applyFetchedText($('dp-price'), priceLabel, '가격', filled);

      const platformSel = $('dp-platform');
      if (platformSel && data.source) {
        const sourceMap = { '쿠팡':'쿠팡', '스마트스토어':'스마트스토어', '와디즈':'와디즈', '11번가':'11번가', 'G마켓':'기타', '옥션':'기타', 'SSG':'기타', '기타':'기타' };
        const targetVal = sourceMap[data.source] || '기타';
        const opt = Array.from(platformSel.options).find(o => o.value === targetVal);
        if (opt) { platformSel.value = targetVal; filled.push('플랫폼'); }
      }

      const fetchedSpecText = buildFetchedSpecText(data);
      // v21.8.24.24: 자동 채우기는 새 상품의 스펙으로 덮어쓴다(이전 상품 스펙 잔존 방지). 수동 보정값은 별도 칸(manualFacts)에서 보호됨.
      if (fetchedSpecText && $('dp-specs')) {
        $('dp-specs').value = fetchedSpecText;
        $('dp-specs').dispatchEvent(new Event('input', { bubbles: true }));
        filled.push(data.specs ? '상세 스펙' : '상품 설명');
      }

      if (resultEl) {
        resultEl.style.display = 'block';
        resultEl.innerHTML = '';
        const box = document.createElement('div');
        box.style.cssText = 'display:flex;gap:12px;align-items:flex-start';
        if (data.image) {
          const img = document.createElement('img');
          img.referrerPolicy = 'no-referrer';
          img.src = data.image;
          img.style.cssText = 'width:80px;height:80px;object-fit:cover;border-radius:8px;border:1px solid #444;flex-shrink:0;background:#111';
          img.onerror = ()=>{ img.style.display='none'; };
          box.appendChild(img);
        }
        const info = document.createElement('div');
        info.style.cssText = 'flex:1;font-size:12px;line-height:1.5';
        info.innerHTML = `
          <div><b>출처:</b> ${esc(data.source||'알 수 없음')} · ${esc(methodLabel)}</div>
          <div><b>상품명:</b> ${esc(data.title||'(없음)')}</div>
          <div><b>가격:</b> ${priceLabel || '(없음)'}</div>
          ${data.specs ? `<div style="margin-top:4px;color:#aaa;white-space:pre-line"><b>스펙:</b> ${esc(data.specs.slice(0,260))}${data.specs.length>260?'...':''}</div>` : ''}
          ${data.description ? `<div style="margin-top:4px;color:#aaa"><b>설명:</b> ${esc(data.description.slice(0,140))}${data.description.length>140?'...':''}</div>` : ''}
          ${data.factSummary ? `<div style="margin-top:4px;color:#c8f7c5;white-space:pre-line"><b>정제 요약:</b> ${esc(data.factSummary.slice(0,320))}${data.factSummary.length>320?'...':''}</div>` : ''}
          ${data.collectionStatus ? `<div style="margin-top:6px;color:#9dd7ff"><b>확인됨:</b> ${esc((data.collectionStatus.confirmed||[]).join(', ')||'없음')}</div><div style="margin-top:2px;color:#ffb4b4"><b>부족함:</b> ${esc((data.collectionStatus.missing||[]).join(', ')||'없음')}</div>` : ''}
          ${response.warning ? `<div style="margin-top:6px;color:#ffd580"><b>경고:</b> ${esc(response.warning)}</div>` : ''}
          <div style="margin-top:6px;color:#8ab4ff">※ 쇼핑몰이 차단하면 일부 정보는 비어 있을 수 있습니다.</div>
        `;
        box.appendChild(info);
        // v21.8.24.26: 링크에서 찾은 상품 이미지 여러 장을 갤러리로 표시 → 클릭/전부 추가
        const gallery = (Array.isArray(data.images) && data.images.length) ? data.images.slice(0, 12) : (data.image ? [data.image] : []);
        if (gallery.length) {
          const gal = document.createElement('div');
          gal.style.cssText = 'margin-top:8px';
          const cap = document.createElement('div');
          cap.className = 'dp-help';
          cap.style.cssText = 'margin-bottom:4px';
          cap.textContent = `링크에서 찾은 상품 이미지 ${gallery.length}장 — 썸네일을 누르면 원본으로 추가됩니다`;
          gal.appendChild(cap);
          const grid = document.createElement('div');
          grid.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px';
          gallery.forEach(u => {
            const im = document.createElement('img');
            im.src = u; im.referrerPolicy = 'no-referrer'; im.title = '클릭하면 원본 이미지로 추가';
            im.style.cssText = 'width:52px;height:52px;object-fit:cover;border-radius:6px;border:1px solid #444;cursor:pointer;background:#111';
            im.onclick = () => importLinkImageAsReference(u);
            im.onerror = () => { im.style.display = 'none'; };
            grid.appendChild(im);
          });
          gal.appendChild(grid);
          const allBtn = document.createElement('button');
          allBtn.className = 'dp-btn green'; allBtn.type = 'button';
          allBtn.style.cssText = 'font-size:12px;padding:6px 10px;margin-top:6px';
          const addN = Math.min(gallery.length, 10);
          allBtn.textContent = `🖼 이미지 ${addN}장 모두 원본으로 추가`;
          allBtn.onclick = async () => { for (const u of gallery.slice(0, 10)) { await importLinkImageAsReference(u); } };
          gal.appendChild(allBtn);
          box.appendChild(gal);
        }
        resultEl.appendChild(box);
      }

      // v21.8.24.25: "링크 하나로" 편의 — 사용자가 올린 이미지가 없으면 링크 대표 이미지를 자동으로 원본에 추가
      if (data.image && !state.images.length) {
        importLinkImageAsReference(data.image);
      }

      if (statusEl) statusEl.textContent = filled.length ? `✅ 적용 완료(${methodLabel}): ${filled.join(', ')}` : `✅ 분석 완료(${methodLabel}). 적용 가능한 값이 부족합니다.`;
      log(`링크 분석 완료(${methodLabel}). 적용: ${filled.join(', ') || '없음'}`);
      if (response.warning) log(`링크 분석 경고: ${response.warning}`);
      if (data.collectionStatus) {
        const confirmed = (data.collectionStatus.confirmed || []).join(', ') || '없음';
        const missing = (data.collectionStatus.missing || []).join(', ') || '없음';
        log(`상품페이지 관찰 결과 - 확인됨: ${confirmed}`);
        if (data.pageObservation?.optionGroups?.length) {
          const optionSummary = data.pageObservation.optionGroups
            .slice(0, 4)
            .map(g => `${g.name || '옵션'}=${(g.values || []).slice(0, 12).join('/')}`)
            .join(' · ');
          if (optionSummary) log(`상품페이지 옵션 후보: ${optionSummary}`);
        }
        if (typeof data.pageObservation?.detailImageCount === 'number') {
          log(`상품페이지 상세 이미지 후보: ${data.pageObservation.detailImageCount}장 감지`);
        }
        if (missing && missing !== '없음') log(`상품페이지 관찰 결과 - 부족함: ${missing}`);
      }
      save();
    } catch (e) {
      if (statusEl) statusEl.textContent = `❌ 오류: ${e?.message||e}`;
      log(`링크 분석 오류: ${e?.message||e}`);
    } finally {
      setBusy(false);
    }
  }

  function clearAll(){
    ids().forEach(k=>{ if($('dp-'+k)) $('dp-'+k).value=''; });
    state.attachmentVerified=false; state.chatFilesUploaded=false;
    clearAttachLog();
    if($('dp-images-attached')) $('dp-images-attached').checked=false;
    state.images.forEach(i=>URL.revokeObjectURL(i.url)); state.images=[];
    state.inferred=null;
    state.shortImagePrompts=[]; state.currentShortImageIndex=0; state.sectionStatus=[]; state.collectedImages=[];
    if($('dp-merge-list')) $('dp-merge-list').innerHTML='';
    state.masterBrief=''; state.copyPlan=''; state.refStyle='';
    state.lastProductSig=''; state.briefSig=''; state.planSig='';
    renderPreview(); renderInference(); renderShortPromptStatus(); renderSectionProgress(); renderMasterBriefStatus(); renderCopyPlanStatus(); renderRefStyleStatus();
    state.lastResult='';
    // v20.7: 링크 분석 결과도 리셋
    if($('dp-fetch-status')) $('dp-fetch-status').textContent='';
    if($('dp-fetch-result')) { $('dp-fetch-result').style.display='none'; $('dp-fetch-result').textContent=''; }
    chrome.storage.local.remove([STORE_KEY,RESULT_KEY]);
    log('입력값과 결과를 초기화했습니다.');
  }
  function collapse(){ const p=$('dp-director-panel'); if(p) p.remove(); if(!$('dp-mini-tab')){ const b=document.createElement('button'); b.id='dp-mini-tab'; b.textContent='AI 상세페이지'; b.onclick=()=>{b.remove();injectPanel();}; document.body.appendChild(b); } }
  function togglePanel(){ if($('dp-director-panel')) collapse(); else { const mini=$('dp-mini-tab'); if(mini) mini.remove(); injectPanel(); } }
  injectPanel();
})();
