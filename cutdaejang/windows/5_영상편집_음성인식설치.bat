@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
echo ==========================================
echo   내 영상 편집 - 무료 오프라인 음성인식(Whisper) 설치
echo ==========================================
echo.
echo 이건 선택 설치입니다. Gemini 키가 있으면 안 해도 편집 기능이 됩니다.
echo 무료로 오프라인 자막을 원하면 설치하세요. (수백 MB, 몇 분 소요)
echo.
call "windows\find_python.bat"
if not defined PY (
    echo [!] Python을 찾지 못했습니다 — windows\1_설치.bat 을 먼저 실행하세요.
    pause
    exit /b 1
)
"%PY%" -m pip install -U faster-whisper
if errorlevel 1 (
    echo.
    echo [!] 설치 실패 - 인터넷 연결을 확인하거나, 편집 시 음성인식을 Gemini로 선택하세요.
    pause
    exit /b 1
)
rem ---------- 진짜로 «불러와지는지» 확인 (v1.35.1, 목록 71) ----------
rem ⚠ 예전에는 pip이 성공하면 그걸로 끝이라고 알렸다. 그런데 회원님이 파일을
rem    주신 테스트 PC에서, 설치는 됐는데 ctranslate2.dll을 못 불러와
rem    FileNotFoundError가 났고 프로그램 전체가 안 되는 것처럼 보였다.
rem    그래서 여기서 한 번 «실제로» 불러본다.
echo.
echo [..] 실제로 불러와지는지 확인 중...
"%PY%" -c "import faster_whisper" >nul 2>&1
if not errorlevel 1 goto :ok

echo.
echo [!] 설치는 됐는데 «불러오지»를 못했습니다.
echo     대개 Microsoft Visual C++ 재배포 패키지가 없어서입니다 (윈도우 공용 부품).
echo.
set /p VCYN=지금 자동으로 받아서 설치할까요? (약 25MB) [Y/N]
if /i not "%VCYN%"=="Y" goto :skipvc
echo [..] 내려받는 중...
curl -L --fail --progress-bar -o "%TEMP%\cutdaejang_vcredist.exe" "https://aka.ms/vs/17/release/vc_redist.x64.exe"
if errorlevel 1 (
    powershell -NoProfile -Command "& {$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile (Join-Path $env:TEMP 'cutdaejang_vcredist.exe')}"
)
if not exist "%TEMP%\cutdaejang_vcredist.exe" (
    echo [!] 내려받기 실패 — 아래 주소에서 직접 받아 설치해 주세요:
    echo     https://aka.ms/vs/17/release/vc_redist.x64.exe
    goto :skipvc
)
echo [..] 설치 중... 창이 뜨면 "예"를 눌러주세요.
"%TEMP%\cutdaejang_vcredist.exe" /install /passive /norestart
del "%TEMP%\cutdaejang_vcredist.exe" >nul 2>nul
echo [..] 다시 확인 중...
"%PY%" -c "import faster_whisper" >nul 2>&1
if not errorlevel 1 goto :ok

:skipvc
echo.
echo ------------------------------------------------------------
echo  무료 Whisper는 이 PC에서 아직 못 씁니다. 하지만 걱정 마세요 —
echo  컷대장의 나머지 기능은 "전부 그대로" 됩니다.
echo.
echo   - 편집 화면의 [음성 인식 엔진]을 "Gemini"로 고르면 자막이 만들어집니다
echo   - 사진 영상/AI 영상/블로그 영상은 음성인식이 아예 필요 없습니다
echo.
echo  그래도 무료 Whisper를 쓰고 싶으시면:
echo   1^) https://aka.ms/vs/17/release/vc_redist.x64.exe 를 받아 설치
echo   2^) PC를 다시 켠 뒤 이 배치를 한 번 더 실행
echo ------------------------------------------------------------
pause
exit /b 0

:ok
echo.
echo [OK] 설치 완료! 편집 화면의 음성인식에서 "내장 Whisper"를 고를 수 있습니다.
echo      (처음 자막 만들 때 모델을 한 번 자동 다운로드합니다)
pause
