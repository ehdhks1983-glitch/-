@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo ==========================================
echo   컷대장 설치 점검  (최초 1회만 실행)
echo ==========================================
echo.

rem ---------- 1) Python ----------
python --version >nul 2>nul
if errorlevel 1 (
    echo [!] Python이 설치되어 있지 않습니다. 자동 설치를 시도합니다...
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    echo.
    echo [i] Python 설치가 끝났으면 이 창을 닫고 1_설치.bat 을 "다시" 실행하세요.
    echo     자동 설치가 안 됐다면 https://www.python.org/downloads/ 에서 설치하되,
    echo     설치 화면에서 "Add python.exe to PATH"를 꼭 체크하세요.
    pause
    exit /b 1
)
for /f "delims=" %%V in ('python --version') do echo [OK] %%V

rem ---------- 2) FFmpeg - libass 포함 빌드 ----------
if exist "windows\ffmpeg\bin\ffmpeg.exe" (
    echo [OK] FFmpeg 이미 준비됨
) else (
    echo [..] FFmpeg 내려받는 중... 약 100MB, 몇 분 걸릴 수 있습니다
    powershell -NoProfile -Command "& {$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip' -OutFile (Join-Path $env:TEMP 'cutdaejang_ffmpeg.zip')}"
    if errorlevel 1 (
        echo [!] 다운로드 실패 — 인터넷 연결을 확인하세요.
        echo     수동 방법: https://www.gyan.dev/ffmpeg/builds/ 에서 release-full zip을 받아
        echo     압축을 풀고 내용물을 cutdaejang\windows\ffmpeg\ 폴더에 넣으세요.
        pause
        exit /b 1
    )
    echo [..] 압축 푸는 중...
    powershell -NoProfile -Command "& {Expand-Archive -Force (Join-Path $env:TEMP 'cutdaejang_ffmpeg.zip') (Join-Path $env:TEMP 'cutdaejang_ffmpeg')}"
    for /d %%D in ("%TEMP%\cutdaejang_ffmpeg\ffmpeg-*") do xcopy "%%D" "windows\ffmpeg\" /E /I /Y /Q >nul
    del "%TEMP%\cutdaejang_ffmpeg.zip" >nul 2>nul
)
if not exist "windows\ffmpeg\bin\ffmpeg.exe" (
    echo [!] FFmpeg 준비 실패 — 위 안내대로 수동으로 넣은 뒤 다시 실행하세요.
    pause
    exit /b 1
)

rem ---------- 3) 캡컷 draft용 pycapcut - 선택 사항 ----------
python -m pip install -q pycapcut
if errorlevel 1 echo [i] pycapcut 설치 실패 — 캡컷 draft 출력만 비활성. mp4 출력은 정상.

rem ---------- 4) 최종 진단 ----------
set "CUTDAEJANG_FFMPEG=%CD%\windows\ffmpeg\bin\ffmpeg.exe"
set "CUTDAEJANG_FFPROBE=%CD%\windows\ffmpeg\bin\ffprobe.exe"
echo.
python -m cutdaejang doctor
echo.
echo 위에 "진단 결과: 정상" 이 보이면 성공입니다. 이어서 2_UI실행.bat 을 실행하세요.
if /i not "%~1"=="auto" pause
