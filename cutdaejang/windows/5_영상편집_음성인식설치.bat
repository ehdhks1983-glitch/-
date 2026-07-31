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
echo.
echo [OK] 설치 완료! 편집 화면의 음성인식에서 "내장 Whisper"를 고를 수 있습니다.
echo      (처음 자막 만들 때 모델을 한 번 자동 다운로드합니다)
pause
