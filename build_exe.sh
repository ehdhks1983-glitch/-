#!/bin/bash
# 컷대장 Windows 설치 EXE 빌드 (NSIS) — v1.49 목록 99
#
# ⚠ 저장소 루트에 둔다 (installer.nsi·make_license.py와 함께 — 제품엔 안 들어감).
# 리눅스에서 makensis로 Windows 설치 파일을 만든다. 회원은 EXE를 더블클릭 →
# 사용자 폴더에 설치 + 바탕화면 바로가기. 첫 실행 때 2_UI실행.bat이 파이썬·
# FFmpeg를 알아서 준비한다.
#
# 사용: bash build_exe.sh
set -euo pipefail
command -v makensis >/dev/null || { echo "makensis가 없습니다 (apt install nsis)"; exit 1; }
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' cutdaejang/cutdaejang/__init__.py)
[ -n "$VER" ] || { echo "버전을 못 읽었습니다"; exit 1; }
OUT="${OUT:-/tmp/claude-0/-home-user--/e5db1822-2bf4-5358-8932-0f7f9efd1037/scratchpad}"
REPO="$(cd "$(dirname "$0")" && pwd)"
STAGE="$OUT/exeroot"
NAME="컷대장_v${VER}"
EXE="$OUT/컷대장_설치_v${VER}.exe"
mkdir -p "$OUT"
echo "== 컷대장 v$VER 설치 EXE 만들기 =="

# 1) 제품 스테이징 (build_zip.sh와 동일 규칙 — docs/·tests/ 제외, .bat CRLF)
echo "== 1) 스테이징 =="
rm -rf "$STAGE" && mkdir -p "$STAGE"
cd "$REPO"
git archive HEAD:cutdaejang | tar -x -C "$STAGE"
rm -rf "$STAGE/docs" "$STAGE/tests"
python3 - "$STAGE" <<'PYEOF'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for p in root.rglob("*.bat"):
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    b = b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    p.write_bytes(b)
PYEOF

# 2) 비밀·내부 파일이 스테이징에 없는지 (EXE에도 그대로 실린다)
for bad in "api_keys.json" "settings.json" "make_license.py" "installer.nsi"; do
  if find "$STAGE" -name "$bad" | grep -q .; then
    echo "  ✘ 스테이징에 $bad 포함!"; exit 1; fi
done
if [ -d "$STAGE/docs" ] || [ -d "$STAGE/tests" ]; then
  echo "  ✘ 내부 문서·시험이 스테이징에 남음!"; exit 1; fi
echo "  ✔ 비밀·내부 파일 없음"

# 3) NSIS 컴파일 — makensis argv는 UTF-8 한글을 못 받아 ASCII 임시명으로 굽고 옮긴다
echo "== 2) makensis =="
TMPEXE="$OUT/cutdaejang_setup_v${VER}.exe"
LC_ALL=C.UTF-8 makensis -INPUTCHARSET UTF8 \
  -DVERSION="$VER" -DSRCDIR="$STAGE" -DOUTFILE="$TMPEXE" \
  "$REPO/installer.nsi" | tail -6
[ -f "$TMPEXE" ] && mv -f "$TMPEXE" "$EXE"

# 4) 검증
[ -f "$EXE" ] || { echo "  ✘ EXE가 안 만들어졌습니다"; exit 1; }
file "$EXE" | grep -qi "PE32\|executable\|installer" && echo "  ✔ Windows 실행 파일"
SZ=$(du -h "$EXE" | cut -f1)
echo "== 완료: $EXE ($SZ) =="
