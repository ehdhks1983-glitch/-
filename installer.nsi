; 컷대장 Windows 설치 파일 (NSIS) — v1.49 목록 99
; 저장소 루트에 둔다 (제품 zip 제외). build_exe.sh가 makensis로 부른다.
; 전달 define: SRCDIR(스테이징 폴더), VERSION, OUTFILE
Unicode true
!include "MUI2.nsh"

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef SRCDIR
  !error "SRCDIR(스테이징 폴더)를 -D로 넘겨주세요"
!endif
!ifndef OUTFILE
  !define OUTFILE "컷대장_설치.exe"
!endif

Name "컷대장 ${VERSION}"
OutFile "${OUTFILE}"
; 관리자 권한 없이 — 사용자 폴더에 설치 (백신·권한 마찰 최소화)
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\컷대장"
InstallDirRegKey HKCU "Software\컷대장" "InstallDir"
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\windows\2_UI실행.bat"
!define MUI_FINISHPAGE_RUN_TEXT "지금 컷대장 실행 (처음엔 파이썬·FFmpeg 준비로 몇 분 걸릴 수 있어요)"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "English"

Section "컷대장 (필수)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${SRCDIR}\*.*"

  ; 바탕화면 + 시작메뉴 바로가기 → 서버+화면 실행 배치
  CreateShortcut "$DESKTOP\컷대장.lnk" "$INSTDIR\windows\2_UI실행.bat" "" \
    "$SYSDIR\shell32.dll" 137 SW_SHOWMINIMIZED "" "컷대장 — 유튜브 영상 자동 제작"
  CreateDirectory "$SMPROGRAMS\컷대장"
  CreateShortcut "$SMPROGRAMS\컷대장\컷대장.lnk" "$INSTDIR\windows\2_UI실행.bat" "" \
    "$SYSDIR\shell32.dll" 137 SW_SHOWMINIMIZED "" "컷대장 — 유튜브 영상 자동 제작"
  CreateShortcut "$SMPROGRAMS\컷대장\실행가이드.lnk" "$INSTDIR\실행가이드.md"
  CreateShortcut "$SMPROGRAMS\컷대장\컷대장 제거.lnk" "$INSTDIR\uninstall.exe"

  ; 언인스톨러 + 프로그램 추가/제거 등록
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\컷대장" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\컷대장" \
    "DisplayName" "컷대장 (유튜브 영상 자동 제작)"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\컷대장" \
    "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\컷대장" \
    "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\컷대장" \
    "DisplayIcon" "$SYSDIR\shell32.dll,137"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\컷대장" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\컷대장" \
    "NoRepair" 1
SectionEnd

Section "Uninstall"
  ; ⚠ 회원 작업물·설정은 남긴다 — windows\jobs, settings.json, api_keys.json은
  ;    지우지 않는다 (프로그램 파일만 제거). 통째로 지우려면 폴더를 직접 삭제.
  Delete "$DESKTOP\컷대장.lnk"
  RMDir /r "$SMPROGRAMS\컷대장"
  RMDir /r "$INSTDIR\cutdaejang"
  RMDir /r "$INSTDIR\windows\python"
  Delete "$INSTDIR\windows\*.bat"
  Delete "$INSTDIR\실행가이드.md"
  RMDir /r "$INSTDIR\판매문서"
  Delete "$INSTDIR\업데이트.bat"
  Delete "$INSTDIR\uninstall.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\컷대장"
  DeleteRegKey HKCU "Software\컷대장"
  ; 남은 폴더가 비면 정리 (작업물이 있으면 남는다)
  RMDir "$INSTDIR\windows"
  RMDir "$INSTDIR"
SectionEnd
