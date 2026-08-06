#!/bin/bash
# 컷대장 배포 zip 빌드 + 검증
#
# ⚠ 이 파일은 «저장소 루트»에 둔다 (cutdaejang/ 밖).
#   ① git archive HEAD:cutdaejang 는 cutdaejang/ 안만 담으므로 배포 zip에 안 들어간다
#   ② 임시 폴더에 두면 컨테이너가 되돌아갈 때 통째로 사라진다 (이 세션에서 3번 겪었다)
#
# 사용: bash build_zip.sh
set -euo pipefail
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' cutdaejang/cutdaejang/__init__.py)
[ -n "$VER" ] || { echo "버전을 못 읽었습니다"; exit 1; }
OUT="${OUT:-/tmp/claude-0/-home-user--/e5db1822-2bf4-5358-8932-0f7f9efd1037/scratchpad}"
REPO="$(cd "$(dirname "$0")" && pwd)"
ROOT="$OUT/ziproot"
NAME="컷대장_v${VER}"
ZIP="$OUT/${NAME}_풀버전.zip"
mkdir -p "$OUT"
echo "== 컷대장 v$VER 배포본 만들기 =="

echo "== 1) git archive → 스테이징 =="
rm -rf "$ROOT" && mkdir -p "$ROOT/$NAME"
cd "$REPO"
git archive HEAD:cutdaejang | tar -x -C "$ROOT/$NAME"

echo "== 2) .bat CRLF 변환 + BOM 제거 =="
python3 - "$ROOT/$NAME" <<'EOF'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for p in root.rglob("*.bat"):
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    b = b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    p.write_bytes(b)
    print("  CRLF:", p.relative_to(root))
EOF

echo "== 3) zip 생성 =="
rm -f "$ZIP"
cd "$ROOT"
zip -qr "$ZIP" "$NAME" -x "*/__pycache__/*" -x "*.pyc" -x "*/.pytest_cache/*"

echo "== 4) 검증 =="
unzip -qt "$ZIP" >/dev/null && echo "  ✔ 무결성"
if unzip -l "$ZIP" | grep -E "api_keys\.json|settings\.json|ffmpeg\.exe"; then
  echo "  ✘ 비밀·대용량 파일 포함!" && exit 1
fi
echo "  ✔ api_keys/settings/ffmpeg 없음"

VDIR=$(mktemp -d)
unzip -q "$ZIP" -d "$VDIR"
U="$VDIR/$NAME"

grep -q "__version__ = \"$VER\"" "$U/cutdaejang/__init__.py" && echo "  ✔ __init__ 버전 $VER"
grep -q "v$VER" "$U/cutdaejang/gui/webui.py" && echo "  ✔ webui h1 버전"
ls "$U/cutdaejang/resources/fonts/" | grep -qi pretendard && echo "  ✔ Pretendard 폰트"
python3 -m compileall -q "$U" && echo "  ✔ compileall"

# 배포본 JS 문법 + 화면 무결성 (평가된 _HTML에서 추출)
python3 - "$U" <<'EOF'
import re, sys
sys.path.insert(0, sys.argv[1])
from cutdaejang.gui import webui
H = webui._apply_links(webui._HTML)
open('/tmp/ship_ui.js', 'w').write("\n".join(re.findall(r'<script>(.*?)</script>', H, re.S)))
ids = re.findall(r'\sid="([^"]+)"', H)
assert len(ids) == len(set(ids)), [i for i in set(ids) if ids.count(i) > 1]
for tag in ("div", "details", "select", "button", "textarea", "label"):
    a, b = len(re.findall(rf"<{tag}[\s>]", H)), len(re.findall(rf"</{tag}>", H))
    assert a == b, f"<{tag}> {a}/{b}"
print("  ✔ 중복 id 없음 · 태그 짝 맞음")
EOF
node --check /tmp/ship_ui.js && echo "  ✔ 배포본 JS 문법"

has()   { grep -qF -- "$2" "$U/$1" || { echo "  ✘ 없음: $2 ($1)"; exit 1; }; }
hasnt() { grep -qF -- "$2" "$U/$1" && { echo "  ✘ 남아 있음: $2 ($1)"; exit 1; }; true; }

W="cutdaejang/gui/webui.py"
S2="cutdaejang/core/script_generator.py"
A="cutdaejang/core/render_engine/ass_writer.py"
F="cutdaejang/tools/fetch_fonts.py"

# ── v1.47 (94) 자막 계속 움직임 ──
for t in "def _motion_tags(" "fscx106" "frz1.6"; do
  has "cutdaejang/core/render_engine/ass_writer.py" "$t"; done
has "cutdaejang/core/orchestrator.py" 'motion=sub.get("motion", "none")'
for t in 'id="setSubMotion"' "qd-motion" "pvPulse" "pvWiggle" "떠 있는 내내"; do
  has "$W" "$t"; done
# 실동작: 6초 두근 → \t 사슬이 끝까지 + 원위치 마감
python3 - "$U" <<'PYEOF'
import re, sys, tempfile
sys.path.insert(0, sys.argv[1])
from cutdaejang.spec import TimelineSpec, Canvas, Style, Subtitle
from cutdaejang.core.render_engine import ass_writer as aw
p = tempfile.mktemp(suffix=".ass")
aw.write_ass(TimelineSpec(canvas=Canvas(1080,1920,30), hook="제목",
             subtitles=[Subtitle(text="움직임", start_us=0, end_us=6*10**6)],
             style=Style(motion="pulse"), duration_us=6*10**6), p)
d = [l for l in open(p, encoding="utf-8").read().splitlines()
     if l.startswith("Dialogue") and ",Default," in l][0]
assert d.count("\\t(") >= 8 and "\\fscx106" in d
assert "\\fscx100\\fscy100" in d.rstrip().split("\\t(")[-1]
print("  ✔ 두근 실렌더 (배포본)")
PYEOF
echo "  ✔ v1.47 (자막 계속 움직임)"

# ── v1.46 (91·92·93) 클립 챌린지·링크 궁합·사진 추가 ──
for t in "#오늘클립챌린지" "카운팅 3조건" "뉴스·블로그·오픈톡 정보태그는 미션 제외" \
         "function renderWlGrid" "function addWlPhotos" "_wlMergePhotos" \
         "📁 사진 추가 (여러 장)" "사진을 못 가져오는 곳이에요" \
         "짧은 설명글만"; do has "$W" "$t"; done
hasnt "$W" "if(window._weblink) window._weblink.images = paths;"  # 덮어쓰기 잔재
echo "  ✔ v1.46 (클립 챌린지·링크 궁합·사진 추가)"

# ── v1.45 (88·89·90) 병기·강조 스위치·받기 허브 ──
for t in "def translate_lines(" "def finalize(" "sub_lang" "highlight_on" \
         "«강조» 표식은 번역에 방해만 된다" ; do
  has "cutdaejang/core/translator.py" "$t"; done
for t in "LANG_FONTS" "def fetch_lang(" "def lang_font_installed("; do
  has "cutdaejang/tools/fetch_fonts.py" "$t"; done
for t in "Style: Trans," "_trans_font" "trans_margin_v"; do
  has "cutdaejang/core/render_engine/ass_writer.py" "$t"; done
has "cutdaejang/core/edit_mode.py" "translator.finalize(ass_spec)"
has "cutdaejang/core/render_engine/__init__.py" "finalize(spec)"
for t in 'id="setSubLang"' 'id="setHl"' 'id="dlCard"' "⬇ 무료 자료 받기" \
         "qd-lang" "qd-hl" "maybeOfferLangFont" "/api/fetch_lang_font" \
         "refreshDlCard" "_state_lang_fonts"; do has "$W" "$t"; done
# 실동작: 병기 줄 렌더 — Trans 스타일·본문 아래·조건부
python3 - "$U" <<'PYEOF'
import re, sys, tempfile
sys.path.insert(0, sys.argv[1])
from cutdaejang.spec import TimelineSpec, Canvas, Style, Subtitle
from cutdaejang.core.render_engine import ass_writer as aw
p = tempfile.mktemp(suffix=".ass")
aw.write_ass(TimelineSpec(canvas=Canvas(1080,1920,30), hook="제목",
             subtitles=[Subtitle(text="안녕", start_us=0, end_us=10**6, trans="Hello")],
             style=Style(), duration_us=10**6), p)
t = open(p, encoding="utf-8").read()
assert "Style: Trans," in t and "Hello" in t
md = int(re.search(r"Style: Default,.*,(\d+),1$", t, re.M).group(1))
mt = int(re.search(r"Style: Trans,.*,(\d+),1$", t, re.M).group(1))
assert mt < md, "병기가 본문 아래"
print("  ✔ 병기 줄 실렌더 (배포본)")
PYEOF
echo "  ✔ v1.45 (병기·강조 스위치·받기 허브)"

# ── v1.44 (86·87) 미리보기 틀·손글씨 팝 ──
for t in '"손글씨 팝"' "line_rotate" "_line_rotate_body" 'ss.get("scale", 1.0)'; do
  has "cutdaejang/core/render_engine/ass_writer.py" "$t"; done
for t in "/api/deco_presets" "_mountPvFrame" "renderDecoPreview" "assColorToCss" \
         "pvReplay" "▶ 효과 다시" "autoFontForPreset" \
         '<option value="손글씨 팝">' "'NotoSansKR-Bold':'Noto Sans KR Bold'" \
         "'Pretendard-Bold':'Pretendard'"; do has "$W" "$t"; done
hasnt "cutdaejang/core/render_engine/ass_writer.py" 'ss.get("font"'  # 글씨체는 제안만
# 실동작: 손글씨 팝 두 줄 → 형광 두 색 + 확대 배율
python3 - "$U" <<'PYEOF'
import re, sys, tempfile
sys.path.insert(0, sys.argv[1])
from cutdaejang.spec import TimelineSpec, Canvas, Style, Subtitle
from cutdaejang.core.render_engine import ass_writer as aw
def rend(st, txt):
    p = tempfile.mktemp(suffix=".ass")
    aw.write_ass(TimelineSpec(canvas=Canvas(1080,1920,30), hook="제목",
                 subtitles=[Subtitle(text=txt, start_us=0, end_us=10**6)],
                 style=Style(sub_style=st), duration_us=10**6), p)
    return open(p, encoding="utf-8").read()
t = rend("손글씨 팝", "형광 노랑 윗줄이고요 연두색 아랫줄입니다")
assert "&H4DE9FF&" in t and "&H68F2B8&" in t, "줄마다 두 색"
fs = lambda x: int(re.search(r"Style: Default,[^,]+,(\d+)", x).group(1))
assert fs(t) > fs(rend("기본", "한 줄")), "확대"
print("  ✔ 손글씨 팝 실렌더 (배포본)")
PYEOF
echo "  ✔ v1.44 (미리보기 틀·손글씨 팝)"

# ── v1.43 (85①~⑤) 첫 설치 쉬운 모드·⚙ 문 하나·우리말 ──
for t in "_em == null ? true : !!_em" "🛠 전부 보기" 'id="topSet"' \
         "ts.classList.toggle('hidden', !!info)" \
         "'genSpeedSel', 'photoSec', 'secTempoSel', 'secBgmSel', 'secXfadeSel'" \
         "🎙 영상 속 말 받아적기" "(대본 따오기)" \
         "장면 설명 전체 복사 (통합)" "분당 목소리 호출 한도" \
         "말할 때 배경음악 줄이기"; do has "$W" "$t"; done
hasnt "$W" "🎙→📃"                      # 옛 이름 청산 (주석 포함)
hasnt "$W" "applyEasy(!!(((s || {}).ui || {}).easy_mode))"  # 옛 무조건 강제
hasnt "$W" "분당 TTS 호출 한도"
hasnt "$W" "(브루식"
hasnt "$W" "핵심 몽타주)'"              # 셀렉트 라벨 (주석은 무방)
echo "  ✔ v1.43 (첫 설치 쉬운 모드·문 하나·우리말)"

# ── v1.42 (84) AI 클립 진행 표시 ──
for t in 'id="aiClipProg"' "aiClipProgShow" "aiClipElapsed" "aiClipNote" \
         "📁 파일 위치" "aispin"; do has "$W" "$t"; done
has "cutdaejang/core/video_gen.py" "queue_position"
has "cutdaejang/core/video_gen.py" "초 지남"
echo "  ✔ v1.42 (AI 클립 진행 표시)"

# ── v1.41 (83) 자막 효과를 꾸미기 상자로 ──
for t in "function _decoEffectRow(" "_DECO_CHK" "qd-anim" "qd-fade" "qd-hookband" \
         "qd-band" "box.appendChild(_decoEffectRow());" \
         "[...src.options].forEach"; do has "$W" "$t"; done
hasnt "$W" 'id="qd-anim"'          # 분신은 class여야 한다 (id 복제 = 저장 파괴)
echo "  ✔ v1.41 (자막 효과 꾸미기)"

# ── v1.40 (82) 여러 쇼츠도 «좋은 데만» ──
for t in "def suggest_multi_highlights(" "def suggest_multi_highlights_heuristic(" \
         "def _clip_groups_sane(" "MULTI_HL_PROMPT" "등분하지 마라"; do has "$S2" "$t"; done
for t in 'mode: str = "seq"' 'if mode == "best" and subs:' "sg.suggest_multi_highlights(" \
         "splitMode" "splitCount" "applySplitMode" "핵심만 골라 여러 개" \
         "처음부터 순서대로 나누기" "지루한 부분은 버려요"; do has "$W" "$t"; done
echo "  ✔ v1.40 (여러 쇼츠 핵심 선별)"

# ── v1.39 (77) BGM 음량 맞추기 — 믹스 경로 세 곳 전부 ──
for t in "def measure_lufs(" "def bgm_gain_db(" "VOICE_LUFS"; do
  has "cutdaejang/utils/ffmpeg.py" "$t"; done
for f in "cutdaejang/core/video_editor.py" "cutdaejang/core/edit_mode.py" \
         "cutdaejang/core/render_engine/ffmpeg_composer.py"; do
  has "$f" "bgm_gain_db("; done
# ── v1.39 (78) 끊기 좋은 자리 고르기 ──
for t in "def _break_score(" "_NO_BREAK_AFTER" "_NO_BREAK_BEFORE" "_PARTICLE_END" \
         "_LINK_END" "_MOD_END"; do has "$S2" "$t"; done
hasnt "$S2" '"고", "지만"'
# ── v1.39 (79·80·81) 화면 ──
for t in "nCtrl === 1" "el.previousElementSibling" "kitPhoneRow" "kitPhone" \
         "phone_music" "Content ID" "저작자 표시가 «필요 없는» 곡" "hookStudio"; do
  has "$W" "$t"; done
hasnt "$W" "(설명란에 그대로 붙여넣기 — BGM 크레딧 포함)"
echo "  ✔ v1.39 (BGM 음량 · 자막 끊는 자리 · 상단 제목 · 안내)"

# ── v1.38 (76) 단어별 자막 + 글씨체 ──
for t in "def _word_body(" "def _word_spans(" "WORD_FADE_MS"; do has "$A" "$t"; done
for t in "def font_names(" "def check_names(" "NotoSansKR-Bold.ttf" "SCDreamBold.otf" \
         "Pretendard-Bold.otf" "Pretendard-SemiBold.otf" "SCDreamHeavy.otf" \
         "배민 한나체는 넣지 않았다"; do has "$F" "$t"; done
hasnt "$F" "Hanna"
for t in '"Pretendard-Bold": "Pretendard"' '"NanumPenScript-Regular": "Nanum Pen"' \
         '"NotoSansKR-Bold": "Noto Sans KR Bold"' '"SCDreamBold": "S-Core Dream 6 Bold"' \
         '"SCDreamHeavy": "S-Core Dream 8 Heavy"'; do has "cutdaejang/presets.py" "$t"; done
hasnt "cutdaejang/presets.py" '"Pretendard-Bold": "Pretendard Bold"'
hasnt "cutdaejang/presets.py" '"NanumPenScript-Regular": "Nanum Pen Script"'
for t in '<option value="word">' 'NotoSansKR-Bold' '약 19MB' 'd.mismatch' \
         '_ANIMS = ("none", "pop", "type", "karaoke", "word")'; do has "$W" "$t"; done
hasnt "$W" "약 8MB"
# ── v1.37 (74·75) 끌어서 구간 + 종결어미 줄 나누기 ──
for t in "function bandMake(" "function bandDrag(" "function bandPaint(" \
         "function secDur(" "function secBandsPaint(" "function initTrimBand(" \
         "trimBandBox" ".rband" "setPointerCapture" "window._secFullDur" \
         "sec-start" "sec-end" "▶ 여기부터" "⏹ 여기까지"; do has "$W" "$t"; done
for t in "def split_ko_clauses(" "def pack_ko_lines(" "_KO_ENDER_RE" \
         "chunks = pack_ko_lines(text, limit)" "말이 끝나는 곳"; do has "$S2" "$t"; done
has "cutdaejang/core/edit_mode.py" "from .script_generator import pack_ko_lines"
# ── v1.36 (72·73) · v1.35.1 (71) ──
for t in "sceneAiClip(" "sceneClipClear(" "/api/scene_clip" "kitBgmRow" "bgm_credit"; do
  has "$W" "$t"; done
hasnt "$W" "aiclip"
for t in "_is_video_span" "-stream_loop"; do
  has "cutdaejang/core/background_generator.py" "$t"
  has "cutdaejang/core/video_editor.py" "$t"; done
has "cutdaejang/config.py" "def _sanitize("
has "cutdaejang/core/stt_engine.py" "Visual C++"
echo "  ✔ v1.35~v1.39 기능 토큰"

# 🔤 별칭이 «실제로» 그 글씨를 부르는지 — 배포본에서 렌더해 확인
python3 - "$U" <<'PYEOF'
import hashlib, pathlib, subprocess, sys, tempfile
sys.path.insert(0, sys.argv[1])
from cutdaejang import presets
from cutdaejang.core.render_engine import DEFAULT_FONTS_DIR
fd = pathlib.Path(DEFAULT_FONTS_DIR)
tmp = pathlib.Path(tempfile.mkdtemp())
tpl = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 300\nWrapStyle: 2\n\n"
       "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
       "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
       "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
       "Style: S,{f},80,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,0,5,20,20,20,1\n\n"
       "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
       "Dialogue: 0,0:00:00.00,0:00:02.00,S,,0,0,0,,컷대장 가나다 ABC 123\n")
def shot(fam):
    a = tmp / "t.ass"; a.write_text(tpl.format(f=fam), encoding="utf-8"); p = tmp / "o.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=1080x300:d=0.1", "-frames:v", "1",
                    "-vf", f"subtitles=filename={a}:fontsdir={fd}", str(p)], check=True)
    return hashlib.md5(p.read_bytes()).hexdigest()
fb = shot("ZZ없는폰트ZZ"); n = 0
for stem, fam in presets.FONT_FAMILY_ALIASES.items():
    if not any((fd / (stem + e)).is_file() for e in (".ttf", ".otf")):
        continue
    assert shot(fam) != fb, f"{stem}: 별칭 {fam!r}로는 안 불린다 (기본 글씨로 그려짐)"
    n += 1
print(f"  ✔ 동봉 글씨체 {n}종이 실제 글씨를 부름 (배포본 렌더 확인)")
PYEOF

# 🎵 BGM 음량 맞추기가 배포본에서도 도는지 (77번의 핵심)
python3 - "$U" <<'PYEOF'
import pathlib, sys, tempfile
sys.path.insert(0, sys.argv[1])
from cutdaejang.utils import ffmpeg as ff
d = pathlib.Path(tempfile.mkdtemp())
outs = []
for name, vol in (("a.wav", "0dB"), ("b.wav", "-10dB")):
    p = d / name
    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
            "-i", "anoisesrc=color=pink:duration=4:sample_rate=44100",
            "-af", f"volume={vol}", str(p)])
    outs.append(ff.measure_lufs(str(p)) + ff.bgm_gain_db(str(p), -16.0))
gap = abs(outs[0] - outs[1])
assert gap < 1.0, f"배포본에서 편차 {gap:.1f}dB — 안 맞춰졌다"
print(f"  ✔ BGM 음량 맞추기 동작 (10dB 차이 → {gap:.1f}dB)")
PYEOF

# 🎬 여러 쇼츠 «핵심만»이 배포본에서도 훅을 찾는지 (82번의 핵심)
python3 - "$U" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from cutdaejang.core.script_generator import suggest_multi_highlights_heuristic as pick
F = "그리고 이어서 설명을 조금 더 드리자면 이런 부분도 있습니다"
H = {8: "그런데 여기서 진짜 놀라운 반전이 있습니다 무려 3배나 차이가 났어요?",
     21: "이 방법을 쓰면 비용이 50% 줄어듭니다 진짜일까요?",
     34: "결론은 이겁니다 딱 2가지만 기억하세요!"}
subs = [{"text": H.get(i, F), "start_us": i*4_000_000, "end_us": (i+1)*4_000_000}
        for i in range(40)]
clips = pick(subs, target_sec=30, n=3)["clips"]
found = {h for c in clips for h in H if h in c["keep"]}
assert found == set(H), f"놓친 훅: {set(H) - found}"
flat = [i for c in clips for i in c["keep"]]
assert len(flat) == len(set(flat)), "쇼츠끼리 겹쳤다"
print(f"  ✔ 여러 쇼츠 핵심 선별 동작 (훅 3개 전부 찾음 · 40줄 중 {len(flat)}줄만)")
PYEOF

rm -rf "$VDIR"
echo "== 완료: $ZIP =="
ls -lh "$ZIP"
