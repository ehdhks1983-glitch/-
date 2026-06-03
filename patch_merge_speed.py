"""
patch_merge_speed.py - 이미지 합치기 탭에 속도 드롭다운 자동 부착

실행:  python patch_merge_speed.py

동작:
  1. ui_merge_tab.py의 _build_right_panel() 마지막에 부착 코드 1줄 추가
  2. 원본은 .backup_speed 로 저장
  3. 재실행 안전 (이미 패치되면 건너뜀)
"""

import re
import ast
import shutil
import sys
from pathlib import Path


TARGET_FILE = "ui_merge_tab.py"

# 부착 코드 (가장 마지막 라인, 반드시 _build_right_panel 끝에 오도록)
ATTACH_CODE = """
        # ── 🎚 속도 드롭다운 부착 (v1.1 신규, features/merge_speed.py) ──
        try:
            from features.merge_speed import attach_speed_selector
            attach_speed_selector(self)
        except Exception:
            pass
"""

MARKER = "from features.merge_speed import attach_speed_selector"


class C:
    OK = '\033[92m'
    WARN = '\033[93m'
    ERR = '\033[91m'
    END = '\033[0m'
    B = '\033[1m'


def log(m, c=""):
    print(f"{c}{m}{C.END}")


def find_build_right_panel_end(source: str):
    """
    _build_right_panel 메서드의 마지막 라인 위치(문자 index) 찾기.
    다음 def 또는 class 직전까지를 메서드 본문으로 간주.
    """
    # _build_right_panel 시작 찾기
    pat = re.compile(r"    def _build_right_panel\(self[^)]*\):")
    m = pat.search(source)
    if not m:
        return None

    start = m.end()

    # 다음 메서드(def) 또는 클래스(class) 시작점 찾기
    next_pat = re.compile(r"\n    def |\nclass ")
    m2 = next_pat.search(source, start)

    if m2:
        return m2.start()
    else:
        return len(source)


def main():
    cwd = Path.cwd()
    log(f"🔧 이미지 합치기 탭 - 속도 드롭다운 자동 부착", C.B)
    log(f"   작업 폴더: {cwd}\n")

    # features/merge_speed.py 체크
    fm = cwd / "features" / "merge_speed.py"
    if not fm.exists():
        log(f"❌ features/merge_speed.py 가 없습니다!", C.ERR)
        log(f"   먼저 merge_speed.py 를 features/ 폴더에 넣어주세요.\n", C.ERR)
        return 1

    # 대상 파일 체크
    tf = cwd / TARGET_FILE
    if not tf.exists():
        log(f"❌ {TARGET_FILE} 가 없습니다!", C.ERR)
        return 1

    source = tf.read_text(encoding="utf-8")

    # 이미 패치됨?
    if MARKER in source:
        log(f"⏭  이미 패치되어 있습니다 (건너뜀)", C.WARN)
        return 0

    # 백업
    backup = tf.with_suffix(tf.suffix + ".backup_speed")
    if not backup.exists():
        shutil.copy2(tf, backup)
        log(f"✅ 백업 생성: {backup.name}")

    # _build_right_panel 끝 찾기
    end_pos = find_build_right_panel_end(source)
    if end_pos is None:
        log(f"❌ _build_right_panel 메서드를 찾을 수 없습니다", C.ERR)
        return 1

    # 코드 삽입
    patched = source[:end_pos] + ATTACH_CODE + "\n" + source[end_pos:]

    # 문법 검증
    try:
        ast.parse(patched)
    except SyntaxError as e:
        log(f"❌ 문법 오류: {e}", C.ERR)
        log(f"   원본 유지됨", C.WARN)
        return 1

    # 저장
    tf.write_text(patched, encoding="utf-8")
    log(f"✅ {TARGET_FILE} 패치 완료", C.OK)
    log(f"")
    log(f"🎉 완료! 이제 python main.py 로 실행하면 속도 드롭다운이 보입니다.", C.OK + C.B)
    log(f"")
    log(f"📍 위치: 이미지 합치기 탭 → 우측 패널 → 반복 횟수 위", C.OK)
    log(f"📍 기본값: 1.0x (보통) = 500ms\n", C.OK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
