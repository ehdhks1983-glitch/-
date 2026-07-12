@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
if exist "windows\ffmpeg\bin\ffmpeg.exe" (
    set "CUTDAEJANG_FFMPEG=%CD%\windows\ffmpeg\bin\ffmpeg.exe"
    set "CUTDAEJANG_FFPROBE=%CD%\windows\ffmpeg\bin\ffprobe.exe"
)
set "DRAFTS=%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft"
if not exist "%DRAFTS%" (
    echo [?] 기본 경로에서 캡컷 Drafts 폴더를 찾지 못했습니다.
    echo     캡컷을 한 번이라도 실행한 PC여야 합니다.
    set /p DRAFTS=Drafts 폴더 전체 경로를 붙여넣고 Enter:
)
echo 데모 쇼츠를 mp4 + 캡컷 draft 로 생성합니다...
python -m cutdaejang demo --workdir windows\jobs --outputs mp4,draft --drafts-dir "%DRAFTS%"
echo.
echo 캡컷을 열어 cutdaejang_ 으로 시작하는 프로젝트가 정상으로 열리는지 확인하세요.
echo 세부 확인 항목: docs\CAPCUT_CHECKLIST.md
pause
