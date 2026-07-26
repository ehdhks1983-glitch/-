"""컷대장 로컬 웹 UI — 브라우저에서 클릭으로 생성·검토·재생까지.

`python -m cutdaejang ui` 한 줄이면 127.0.0.1 로컬 서버가 뜨고 기본 브라우저가 열린다.
표준 라이브러리(http.server)만 사용 — 추가 설치 없음. 기획안 §6의 GUI(탭① 새 작업,
탭② 대본 검토, 탭③ 히스토리)를 웹 화면 하나로 구현한 확인용 프런트엔드다.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
import threading
import time
from collections import deque
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .. import config, presets
from ..core import background_generator, orchestrator, tts_engine
from ..core.orchestrator import JobOptions
from ..core.render_engine.ffmpeg_composer import RenderOptions
from ..core.script_generator import SCRIPT_PROVIDERS, Script
from ..core.tts_engine import GEMINI_VOICES, STYLE_INSTRUCTIONS

_JOBS: dict = {}
_LOCK = threading.Lock()
_LOCAL_VIDEOS: dict = {}  # 🎬 풀영상 미리보기 토큰 → 경로 (v0.84 — 임의 경로 GET 방지)

# 📋 작업 큐 (v0.88) — 무거운 작업(생성·편집 렌더·구간 조립)은 한 번에 하나씩.
# 여러 작업을 연달아 시작해도 앞 작업이 끝나면 자동으로 다음이 시작된다.
import queue as _queue_mod  # noqa: E402

_JOB_QUEUE: "_queue_mod.Queue" = _queue_mod.Queue()
_QUEUE_WORKER_STARTED = threading.Event()


# 🔀 동시 작업 개수 (v0.90) — 사용자 피드백 "하나 하는 동안 다른 게 멈추면 너무 느리다".
# 기본 2개 병렬, 진행·대기 바에서 1~4개로 조절 (settings.json ui.parallel_jobs).
_ACTIVE_JOBS = 0
_ACTIVE_LOCK = threading.Lock()
_PLIMIT_CACHE = {"t": 0.0, "n": 2}   # settings 파일을 0.3초마다 읽지 않도록 2초 캐시


def _parallel_limit() -> int:
    now = time.time()
    if now - _PLIMIT_CACHE["t"] > 2.0:
        try:
            n = int((config.load_settings().get("ui") or {}).get("parallel_jobs") or 2)
        except Exception:  # noqa: BLE001 — 설정을 못 읽어도 기본값으로 계속
            n = 2
        _PLIMIT_CACHE.update(t=now, n=max(1, min(4, n)))
    return _PLIMIT_CACHE["n"]


def _queue_job(job_id: str, fn, *args) -> None:
    """무거운 작업을 큐에 넣는다 — 동시 한도에 자리가 나면 자동으로 시작된다."""
    lim = _parallel_limit()
    _set_job(job_id, status="queued", stage="queued", frac=0.0,
             note=f"⏳ 대기 중 — 동시 {lim}개 한도에 자리가 나면 자동 시작 "
                  "(개수는 위 📋 진행·대기에서 조절)")
    _JOB_QUEUE.put((job_id, fn, args))


def _run_queued(job_id: str, fn, args) -> None:
    global _ACTIVE_JOBS
    try:
        _set_job(job_id, t_start=time.time())   # ⏱ 경과 시간 표시용 (v0.90)
        fn(*args)
    except Exception:  # noqa: BLE001 — 실행 스레드는 절대 죽으면 안 됨
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error(
            "큐 작업 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=["작업 실행 중 오류", traceback.format_exc()[-800:]])
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_JOBS -= 1


def _queue_worker() -> None:
    """디스패처 — 대기열에서 꺼내 동시 한도 안에서 각자 스레드로 실행 (v0.90 병렬화)."""
    global _ACTIVE_JOBS
    while True:
        job_id, fn, args = _JOB_QUEUE.get()
        try:
            cancelled = False
            while True:
                if (_get_job(job_id) or {}).get("status") == "cancelled":
                    cancelled = True          # ✕ 자리 기다리는 동안 취소됨
                    break
                with _ACTIVE_LOCK:
                    if _ACTIVE_JOBS < _parallel_limit():
                        _ACTIVE_JOBS += 1
                        break
                time.sleep(0.3)
            if cancelled:
                continue
            threading.Thread(target=_run_queued, args=(job_id, fn, args),
                             daemon=True).start()
        except Exception:  # noqa: BLE001 — 디스패처는 절대 죽으면 안 됨
            import traceback  # noqa: PLC0415

            logging.getLogger("cutdaejang").error(
                "큐 디스패치 실패 %s\n%s", job_id, traceback.format_exc())
        finally:
            _JOB_QUEUE.task_done()


def _ensure_queue_worker() -> None:
    if not _QUEUE_WORKER_STARTED.is_set():
        _QUEUE_WORKER_STARTED.set()
        threading.Thread(target=_queue_worker, daemon=True).start()

# 편집 폼에서 "기억해 두는" 세팅 키 — 경로·주제·대본·API 키 같은 작업별 입력은 제외
_EDIT_LAST_KEYS = (
    "layout", "auto_subtitle", "cut_silence", "denoise", "orig_audio",
    "bgm", "bgm_db", "hook_scale", "hook_style", "sub_style", "tone", "narr_voice", "narr_style", "narr_subs_only",
    "stt_provider", "whisper_model", "speed", "quality", "narr_fit", "transition",
    "auto_edit", "auto_multi", "auto_target_sec", "photo_sec", "wm_pos", "wm_scale",
    "tempo",  # ⚡ 빠른 템포 — 몽타주 컷 밀도 (v0.73)
    "cold_open", "hook_voice",  # 🪝 훅 팩 (v0.75)
    "filler_cut", "take_clean",  # 🧹 말 다듬기 팩 (v0.76)
)


def _attach_branding(job_id: str, mp4: str, job_dir: Path, tag: str = "") -> str:
    """설정에 인트로/아웃트로가 있으면 완성본 앞뒤에 붙인다 (v0.43).

    실패해도 작업은 성공으로 유지(원본 반환) — 브랜딩은 부가 기능이니까.
    """
    settings = config.load_settings()
    br = settings.get("branding") or {}
    intro, outro = (br.get("intro") or "").strip(), (br.get("outro") or "").strip()
    if not intro and not outro:
        return mp4
    from ..core import video_editor  # noqa: PLC0415
    try:
        _set_job(job_id, note="인트로/아웃트로 붙이는 중…")
        out = video_editor.attach_branding(
            mp4, intro, outro, str(job_dir / f"branded{tag}.mp4"))
        if out != mp4 and Path(out).is_file():
            os.replace(out, mp4)  # 파일명 유지 → 히스토리·재생 링크 그대로
            w = "🎬 인트로/아웃트로를 붙였어요"
            prev = (_get_job(job_id) or {}).get("tts_warn") or ""
            if w not in prev:
                _set_job(job_id, tts_warn=f"{prev} · {w}" if prev else w)
    except Exception as be:  # noqa: BLE001
        logging.getLogger("cutdaejang").warning("인트로/아웃트로 붙이기 실패(무시): %s", be)
        prev = (_get_job(job_id) or {}).get("tts_warn") or ""
        w = "⚠ 인트로/아웃트로 붙이기에 실패해 본편만 저장했어요 (설정의 경로·파일을 확인하세요)"
        if w not in prev:
            _set_job(job_id, tts_warn=f"{prev} · {w}" if prev else w)
    return mp4


def _set_job(job_id: str, **fields) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {"id": job_id}).update(fields)


def _get_job(job_id: str) -> Optional[dict]:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _dt_stamp() -> str:
    import datetime  # noqa: PLC0415

    return datetime.datetime.now().strftime("%H%M%S")


# 네이티브 파일 선택 창 — 사용자 PC에서 대화상자를 띄워 전체 경로를 돌려받는다.
# Windows: PowerShell(WinForms) 대화상자 — 별도 파이썬 실행이 필요 없어
#   'embedded python interpreter' 류 시작 오류 없이 안정적 (v0.74.2).
# 그 외 OS: tkinter 대화상자를 별도 프로세스로 (서버/GUI 스레드 충돌 방지).
# v0.51: 종류별(영상/그림/소리/폴더) 일반화 — 폼마다 [📁] 버튼에서 재사용.
_PICK_KINDS = ("video", "image", "images", "audio", "folder")

# Windows: PowerShell + System.Windows.Forms. @KIND@ 은 _PICK_KINDS 화이트리스트에서만
# 치환하므로 스크립트 인젝션 위험 없음. 경로는 UTF-8→base64 로 돌려받아 콘솔
# 인코딩(cp949 등)과 무관하게 한글 경로도 안전하게 복원한다.
_PS_PICK_TEMPLATE = r"""
Add-Type -AssemblyName System.Windows.Forms
$kind = '@KIND@'
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
$owner.StartPosition = 'CenterScreen'
$owner.Show()
try {
Add-Type -Namespace CDJ -Name Fg -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
[DllImport("user32.dll")] public static extern uint GetCurrentThreadId();
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
'@ -ErrorAction Stop
$fg = [CDJ.Fg]::GetForegroundWindow()
$procId = 0
$fgThread = [CDJ.Fg]::GetWindowThreadProcessId($fg, [ref]$procId)
$myThread = [CDJ.Fg]::GetCurrentThreadId()
[void][CDJ.Fg]::AttachThreadInput($myThread, $fgThread, $true)
[void][CDJ.Fg]::SetForegroundWindow($owner.Handle)
[void][CDJ.Fg]::BringWindowToTop($owner.Handle)
[void][CDJ.Fg]::AttachThreadInput($myThread, $fgThread, $false)
} catch {}
$owner.Activate()
$r = ''
if ($kind -eq 'folder') {
    $d = New-Object System.Windows.Forms.FolderBrowserDialog
    $d.Description = '폴더 선택'
    if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { $r = $d.SelectedPath }
} else {
    $d = New-Object System.Windows.Forms.OpenFileDialog
    if ($kind -eq 'images') {
        $d.Title = '사진 여러 장 선택 (Ctrl/Shift로 여러 개)'; $d.Multiselect = $true
        $d.Filter = '사진 파일|*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif|모든 파일|*.*'
    } elseif ($kind -eq 'image') {
        $d.Title = '그림 파일 선택'
        $d.Filter = '그림 파일|*.png;*.jpg;*.jpeg;*.webp;*.bmp|모든 파일|*.*'
    } elseif ($kind -eq 'audio') {
        $d.Title = '소리 파일 선택'
        $d.Filter = '소리 파일|*.mp3;*.wav;*.m4a;*.ogg;*.flac|모든 파일|*.*'
    } else {
        $d.Title = '편집할 영상 선택'
        $d.Filter = '영상 파일|*.mp4;*.mov;*.avi;*.mkv;*.webm;*.m4v;*.wmv;*.flv|모든 파일|*.*'
    }
    if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        if ($kind -eq 'images') { $r = ($d.FileNames -join ';') } else { $r = $d.FileName }
    }
}
$owner.Dispose()
[Console]::Out.Write([Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($r)))
"""

# 그 외 OS: tkinter 대화상자 (별도 파이썬 프로세스)
_PICK_FILE_CODE = r"""
import sys
import tkinter as tk
from tkinter import filedialog
kind = sys.argv[1] if len(sys.argv) > 1 else "video"
r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
if kind == "folder":
    p = filedialog.askdirectory(title="폴더 선택")
elif kind == "images":
    ps = filedialog.askopenfilenames(
        title="사진 여러 장 선택 (Ctrl/Shift로 여러 개)",
        filetypes=[("사진 파일", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("모든 파일", "*.*")])
    p = ";".join(ps or [])
elif kind == "image":
    p = filedialog.askopenfilename(
        title="그림 파일 선택",
        filetypes=[("그림 파일", "*.png *.jpg *.jpeg *.webp *.bmp"), ("모든 파일", "*.*")])
elif kind == "audio":
    p = filedialog.askopenfilename(
        title="소리 파일 선택",
        filetypes=[("소리 파일", "*.mp3 *.wav *.m4a *.ogg *.flac"), ("모든 파일", "*.*")])
else:
    p = filedialog.askopenfilename(
        title="편집할 영상 선택",
        filetypes=[("영상 파일", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.wmv *.flv"),
                   ("모든 파일", "*.*")])
r.destroy()
sys.stdout.write(p or "")
"""


def _pick_cannot_open(detail: str) -> RuntimeError:
    return RuntimeError(
        "선택 창을 열 수 없습니다. 경로를 직접 붙여넣어 주세요. "
        f"({detail})"
    )


def _pick_windows(kind: str, timeout: float) -> Optional[str]:
    """PowerShell(WinForms) 파일 대화상자. 취소=None, 실패=예외."""
    import base64  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    script = _PS_PICK_TEMPLATE.replace("@KIND@", kind)
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-EncodedCommand", enc],
            capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise _pick_cannot_open(str(e))
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()[-200:]
        raise _pick_cannot_open(err or f"exit {proc.returncode}")
    out = (proc.stdout or b"").strip()
    if not out:
        return None  # 사용자가 취소
    try:
        path = base64.b64decode(out).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return path or None


def _pick_tkinter(kind: str, timeout: float) -> Optional[str]:
    """tkinter 대화상자를 별도 파이썬 프로세스로 띄운다 (비 Windows)."""
    import subprocess  # noqa: PLC0415

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PICK_FILE_CODE, kind],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise _pick_cannot_open(str(e))
    if proc.returncode != 0:
        raise _pick_cannot_open(proc.stderr.strip()[-200:])
    return proc.stdout.strip() or None


def pick_path(kind: str = "video", timeout: float = 300.0) -> Optional[str]:
    """네이티브 선택 창을 띄우고 선택된 경로 반환. 취소=None, 사용불가=예외.

    Windows는 PowerShell(WinForms)로 — 별도 파이썬 실행이 없어 안정적.
    창이 브라우저 뒤에 열리지 않도록 SetForegroundWindow로 앞으로 끌어온다.
    그 외 OS는 tkinter를 별도 프로세스로.
    """
    if kind not in _PICK_KINDS:
        kind = "video"
    if sys.platform == "win32":
        return _pick_windows(kind, timeout)
    return _pick_tkinter(kind, timeout)


def pick_video_file(timeout: float = 300.0) -> Optional[str]:
    """(호환용) 영상 파일 선택 — 기존 테스트·호출 유지."""
    return pick_path("video", timeout)


def _stt_available() -> dict:
    """편집 모드에서 쓸 수 있는 음성인식 제공자."""
    try:
        import faster_whisper  # noqa: F401, PLC0415

        whisper = True
    except ImportError:
        whisper = False
    return {
        "whisper": whisper,
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
    }


def _env_check() -> dict:
    """UI 첫 화면에서 환경 문제를 미리 알려주기 위한 점검 (실패해도 화면은 뜨게)."""
    from ..core import render_engine  # noqa: PLC0415
    from ..utils import ffmpeg as ff  # noqa: PLC0415

    try:
        ff.ffmpeg_bin()
        ff.ffprobe_bin()
        ffmpeg_ok = True
    except ff.FFmpegError:
        ffmpeg_ok = False
    font_ok = (Path(render_engine.DEFAULT_FONTS_DIR) / "Pretendard-ExtraBold.ttf").exists()
    return {"ffmpeg": ffmpeg_ok, "font": font_ok}


def _apply_keys(params: dict) -> None:
    """UI에서 입력한 API 키를 환경변수로 반영. save_key면 파일에도 저장(선택 기능)."""
    for field, env, name in (
        ("gemini_key", "GEMINI_API_KEY", "gemini"),
        ("openai_key", "OPENAI_API_KEY", "openai"),
        ("elevenlabs_key", "ELEVENLABS_API_KEY", "elevenlabs"),
    ):
        value = (params.get(field) or "").strip()
        if value:
            os.environ[env] = value
            if params.get("save_key"):
                config.save_api_key(name, value)


def _tts_chain(params: dict, settings: dict) -> list:
    provider = params.get("tts_provider", "stub")
    if provider == "gemini":
        return list(settings["tts"]["fallback_chain"])
    if provider == "elevenlabs":  # 내 목소리 — 실패 시 기존 체인으로 폴백
        return ["elevenlabs", *settings["tts"]["fallback_chain"]]
    if provider == "sovits":      # 무료 내 목소리(로컬) — 실패 시 기존 체인으로 폴백
        return ["sovits", *settings["tts"]["fallback_chain"]]
    return [provider]


_TIMECODE_RE = __import__("re").compile(
    r"^\s*\(?\s*\d{1,2}:\d{2}\s*[-–~—]\s*\d{1,2}:\d{2}\s*\)?\s*[:.,)]?\s*")


def _parse_script_lines(text: str) -> tuple:
    """대본 줄 정리 (v0.63) — 앞머리 타임코드(0:00-0:03 등)를 떼고 목표 길이를 얻는다.

    챗지피티류가 주는 콘티 대본(줄마다 「0:03-0:06 내용」)을 그대로 붙여넣어도
    자막·목소리·장면 프롬프트에 타임코드가 새지 않게. 반환: (줄들, 마지막 초|None).
    """
    import re as _re
    lines, last_end = [], None
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        m = _TIMECODE_RE.match(s)
        if m:
            for mm, ss in _re.findall(r"(\d{1,2}):(\d{2})", m.group(0)):
                last_end = max(last_end or 0, int(mm) * 60 + int(ss))
            s = s[m.end():].strip()
        if s:
            lines.append(s)
    return lines, last_end


def _product_context(params: dict, settings: dict) -> str:
    """📇 선택한 제품 프로필 + 이번 영상 참고 메모 → AI 주입용 텍스트 (v0.64)."""
    parts = []
    name = (params.get("product") or "").strip()
    if name:
        prod = next((x for x in (settings.get("products") or [])
                     if (x.get("name") or "").strip() == name), None)
        if prod:
            lines = [f"제품명: {prod['name']}"]
            if prod.get("desc"):
                lines.append(f"한 줄 소개: {prod['desc']}")
            if prod.get("points"):
                lines.append("핵심 기능·차별점:\n" + "\n".join(
                    f"- {ln}" for ln in str(prod["points"]).splitlines() if ln.strip()))
            if prod.get("target"):
                lines.append(f"타깃: {prod['target']}")
            if prod.get("link"):
                lines.append(f"링크: {prod['link']}")
            if prod.get("tone"):
                lines.append(f"말투 톤: {prod['tone']}")
            if prod.get("avoid"):
                lines.append(f"금지 표현: {prod['avoid']}")
            parts.append("\n".join(lines))
    memo = (params.get("context_memo") or "").strip()
    if memo:
        parts.append(f"[이번 영상 참고]\n{memo}")
    return "\n\n".join(parts)[:1500]


def _font_overrides(params: dict) -> dict:
    """폼의 글씨체·기울임 선택 → settings.subtitle에 기억할 값 (v0.63, 검증 포함)."""
    out = {}
    if "sub_font" in params:
        f = str(params.get("sub_font") or "")
        if not f or f in presets.FONT_FAMILY_ALIASES:
            out["font"] = f or "Pretendard-ExtraBold"
    if "hook_font" in params:
        f = str(params.get("hook_font") or "")
        if not f or f in presets.FONT_FAMILY_ALIASES:
            out["hook_font"] = f
    if "hook_tilt" in params:
        out["hook_tilt"] = bool(params.get("hook_tilt"))
    return out


def _job_canvas(job: Optional[dict]):
    """장면 재생성·삽입 때 그 작업의 화면 형태(세로/가로)에 맞는 캔버스 (v0.61)."""
    wide = (((job or {}).get("params") or {}).get("orientation") == "wide")
    return presets.CANVAS_LANDSCAPE if wide else presets.CANVAS_SHORTS


def _job_options(params: dict, settings: Optional[dict] = None) -> JobOptions:
    settings = settings or config.load_settings()
    return JobOptions(
        outputs=("mp4",),
        auto_mode=bool(params.get("auto", True)),
        tts_chain=_tts_chain(params, settings),
        voice=params.get("voice", ""),
        tts_style=params.get("tts_style", ""),
        bgm=params.get("bgm", ""),
        hook=(params.get("hook") or "").strip(),
        hook_voice=bool(params.get("hook_voice")),  # 🎙 후킹 보이스 (v0.75)
        target_sec=int(params.get("target_sec") or 60),
        orientation=(params.get("orientation")
                     if params.get("orientation") in ("wide", "reels") else "shorts"),  # v0.61·v0.74
        sub_anim=(params.get("sub_anim")
                  if params.get("sub_anim") in ("none", "pop", "type", "karaoke") else ""),  # v0.86 테마
        pace_sec=max(0, int(params.get("pace_sec") or 0)),  # ⏱ 내 대본 길이 맞춤 (v0.63)
        render=RenderOptions(use_gpu=params.get("gpu", "auto")),
    )


def _record_history(workdir: str, result, opts: JobOptions) -> None:
    try:
        from ..db.jobs import JobStore  # noqa: PLC0415

        store = JobStore(Path(workdir) / "history.db")
        spec_json = None
        if result.spec_path and Path(result.spec_path).exists():
            spec_json = Path(result.spec_path).read_text(encoding="utf-8")
        store.upsert(
            result.job_id,
            title=result.title,
            mode="auto" if opts.auto_mode else "review",
            outputs=",".join(opts.outputs),
            status=result.status,
            duration_us=json.loads(spec_json)["duration_us"] if spec_json else 0,
            spec_json=spec_json,
            out_mp4=result.mp4.out_path if result.mp4 else None,
            error="; ".join(result.errors) or None,
            tts_provider=result.tts_provider or None,
        )
        store.close()
    except Exception:
        pass  # 히스토리 기록 실패는 UI 동작에 영향 없음


_PARAM_SECRET_KEYS = ("gemini_key", "openai_key", "eleven_key", "elevenlabs_key", "save_key")


def _record_simple_history(workdir: str, job_id: str, *, title: str, mode: str,
                           status: str, mp4: Optional[str],
                           params: Optional[dict] = None,
                           duration_us: int = 0) -> None:
    """편집·사진·블로그·구간 대본 작업도 히스토리에 남긴다 (v0.85).

    지금까지는 AI 생성만 history.db에 기록돼, 프로그램을 껐다 켜면 최근 작업이
    히스토리에서 사라졌다 (사용자 리포트). params는 재편집용 — API 키는 뺀다.
    """
    try:
        from ..db.jobs import JobStore  # noqa: PLC0415

        safe = None
        if params is not None:
            safe = {k: v for k, v in params.items() if k not in _PARAM_SECRET_KEYS}
        store = JobStore(Path(workdir) / "history.db")
        store.upsert(job_id, title=title, mode=mode, outputs="mp4", status=status,
                     duration_us=duration_us, out_mp4=mp4,
                     params_json=(json.dumps(safe, ensure_ascii=False)
                                  if safe is not None else None))
        store.close()
    except Exception:
        pass  # 히스토리 기록 실패는 UI 동작에 영향 없음


def _ai_image_setup(params: dict, settings: dict):
    """AI 배경 제공자 결정 + (미사용이면) 사유 — 완료 화면에 그대로 보여줌 (v0.40).

    v0.40부터 목소리 선택과 무관: Gemini 키만 있으면 AI 배경을 시도한다
    (기계 점검용 '테스트 톤'만 제외).
    """
    if not settings["bg"].get("ai_image"):
        return None, "설정에서 AI 배경 꺼짐"
    if not os.environ.get("GEMINI_API_KEY"):
        return None, "Gemini 키 없음"
    if params.get("tts_provider") == "stub":
        return None, "소리 점검용 목소리라 미사용"
    return background_generator.GeminiImage(
        model=settings["bg"].get("image_model")), ""


def _bg_display(image_provider, bg_skip: str, src: str) -> str:
    """완료 화면용 배경 출처 문구."""
    if src.startswith("ai_scenes:"):  # v0.45 장면별 이미지 — v0.51부터 ✍ 수동 삽입도
        return f"AI 장면 이미지 {src[10:]}장 ✨"  # (키 없이 내가 넣은 그림 포함)
    if image_provider is None:
        return f"기본 그라데이션 ({bg_skip})" if bg_skip else "기본 그라데이션"
    if src == "ai":
        return "AI 이미지 ✨"
    if src == "user":
        return "내 이미지"
    if src.startswith("ai_fail:"):
        return f"기본 그라데이션 (AI 실패: {src[8:]})"
    return "기본 그라데이션"


def _apply_bg_style(params: dict, settings: dict) -> dict:
    """생성 폼에서 고른 장면 그림체·마스코트·그림 방식을 설정에 반영(기억)하고 병합
    (v0.45/0.50/0.51)."""
    over = {}
    style = (params.get("bg_style") or "").strip()
    if style:
        over["image_style"] = style
    if "bg_character" in params:  # 빈 문자열 = 캐릭터 없음(해제)도 기억
        over["character"] = str(params.get("bg_character") or "").strip()
    if str(params.get("bg_scene_mode") or "") in ("auto", "manual", "off"):  # v0.51
        over["scene_mode"] = params["bg_scene_mode"]
    if "bg_max_imgs" in params:  # v0.51 장수 제한 (0=문장마다)
        try:
            over["max_scene_images"] = max(0, min(50, int(params.get("bg_max_imgs") or 0)))
        except (TypeError, ValueError):
            pass
    if "punch_in" in params:  # 👊 펀치인 줌 켬/끔 기억 (v0.55)
        over["punch_in"] = bool(params.get("punch_in"))
    from ..core.render_engine.ffmpeg_composer import TONE_PRESETS  # noqa: PLC0415
    if str(params.get("tone") or "") in TONE_PRESETS:  # 🎨 화면 톤 기억 (v0.56)
        over["tone"] = params["tone"]
    over_sub = {}
    from ..core.render_engine.ass_writer import HOOK_STYLES  # noqa: PLC0415
    if str(params.get("hook_style") or "") in HOOK_STYLES:  # 🪧 제목 프리셋 (v0.52)
        over_sub["hook_style"] = params["hook_style"]
    from ..core.render_engine.ass_writer import SUB_STYLES  # noqa: PLC0415
    if str(params.get("sub_style") or "") in SUB_STYLES:  # 💬 자막 프리셋 (v0.54)
        over_sub["sub_style"] = params["sub_style"]
    over_sub.update(_font_overrides(params))  # ✒ 글씨체·기울임 기억 (v0.63)
    if "info_pop" in params:  # 🔢 숫자 팝 켬/끔 기억 (v0.56)
        over_sub["info_pop"] = bool(params.get("info_pop"))
    over_sfx = {}
    if "sfx_auto" in params:  # 🔔 효과음 켬/끔 기억 (v0.53)
        over_sfx["enabled"] = bool(params.get("sfx_auto"))
    over_ui = {}
    if params.get("orientation") in ("shorts", "wide", "reels"):  # 🖥 화면 형태 기억 (v0.61·v0.74)
        over_ui["gen_orientation"] = params["orientation"]
    if "product" in params:  # 📇 마지막 제품 기억 (v0.64)
        over_ui["gen_product"] = str(params.get("product") or "")
    if params.get("target_sec"):  # ⏱ 영상 길이 기억 (v0.61)
        try:
            over_ui["gen_target_sec"] = max(10, min(900, int(params["target_sec"])))  # 최대 15분 (v0.68)
        except (TypeError, ValueError):
            pass
    if params.get("tts_provider") == "elevenlabs" and (params.get("voice") or "").strip():
        over_ui["gen_eleven_voice"] = str(params["voice"]).strip()[:80]  # 🎙 지난 성우 기억 (v0.67)
    if "hook_voice" in params:  # 🎙 후킹 보이스 선택 기억 (v0.75)
        over_ui["gen_hook_voice"] = bool(params.get("hook_voice"))
    if not over and not over_sub and not over_sfx and not over_ui:
        return settings
    save = {}
    if over and any(settings["bg"].get(k) != v for k, v in over.items()):
        save["bg"] = over
    if over_sub and any(settings["subtitle"].get(k) != v for k, v in over_sub.items()):
        save["subtitle"] = over_sub
    if over_sfx and any((settings.get("sfx") or {}).get(k) != v for k, v in over_sfx.items()):
        save["sfx"] = over_sfx
    if over_ui and any((settings.get("ui") or {}).get(k) != v for k, v in over_ui.items()):
        save["ui"] = over_ui
    if save:
        try:
            config.save_settings(save)
        except OSError:
            pass
    return config.deep_merge(settings, {"bg": over, "subtitle": over_sub, "sfx": over_sfx})


def _run_pipeline(job_id: str, script: Script, params: dict, workdir: str,
                  scene_images: Optional[list] = None) -> None:
    settings = _apply_bg_style(params, config.load_settings())
    opts = _job_options(params, settings)
    try:
        image_provider, bg_skip = _ai_image_setup(params, settings)

        result = orchestrator.run_job(
            workdir, script, opts=opts, settings=settings,
            image_provider=image_provider,
            progress_cb=lambda stage, frac: _set_job(job_id, stage=stage, frac=frac),
            status_cb=lambda msg: _set_job(job_id, note=msg),
            job_id=job_id,
            scene_images=scene_images,
        )
        bg_disp = _bg_display(image_provider, bg_skip, result.bg_source or "")
        logging.getLogger("cutdaejang").info("배경: %s", bg_disp)
        mp4_path = result.mp4.out_path if (result.mp4 and result.mp4.ok) else None
        if mp4_path and Path(mp4_path).exists():  # 🎬 인트로/아웃트로 (v0.43)
            _attach_branding(job_id, mp4_path, Path(result.job_dir))
        _set_job(
            job_id,
            status=result.status,
            stage="done",
            frac=1.0,
            note=(_get_job(job_id) or {}).get("tts_warn") or "",
            title=result.title,
            job_dir=result.job_dir,
            mp4=result.mp4.out_path if (result.mp4 and result.mp4.ok) else None,
            tts_provider=result.tts_provider,
            requested_tts=params.get("tts_provider", ""),
            bg_source=bg_disp,
            fallback_note=result.fallback_note,
            errors=result.errors,
        )
        _record_history(workdir, result, opts)
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("작업 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed", errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _edit_summary(analysis) -> str:
    return (
        f"원본 {analysis.original_us/1e6:.1f}초 → {analysis.cut_us/1e6:.1f}초 "
        f"(무음 {analysis.removed_ratio*100:.0f}% 컷, 자막 {len(analysis.subtitles)}줄, "
        f"음성인식 {analysis.stt_calls}회)"
    )


def _run_edit(job_id: str, params: dict, workdir: str) -> None:
    """1단계: 무음컷 + 자동자막 분석 → 자막 검토 대기 (Phase 1). 자막 없으면 바로 렌더."""
    try:
        _apply_keys(params)
        settings = config.load_settings()
        edit_cfg = settings["edit"]
        from ..core import edit_mode  # noqa: PLC0415
        from ..core.stt_engine import STTEngine, make_provider  # noqa: PLC0415
        from ..core.video_editor import SilenceOptions, resolve_input_video  # noqa: PLC0415

        photo_path = (params.get("photo_path") or "").strip()
        narr_file = (params.get("narr_file") or "").strip().strip('"')
        if narr_file and not Path(narr_file).is_file():
            _set_job(job_id, status="failed",
                     errors=[f"녹음 파일을 찾을 수 없습니다: {narr_file}"])
            return
        photo_imgs: list = []  # 📸 사진 목록 — 렌더 때 문장 타이밍 재배치용 (v0.79)
        if photo_path:  # 📸 사진들 → 슬라이드쇼 영상 (장수로 전체 길이 균등 분배)
            from ..core.video_editor import photos_to_video, resolve_photo_inputs  # noqa: PLC0415
            try:
                imgs = resolve_photo_inputs(photo_path)
                photo_imgs = list(imgs)
                try:
                    photo_sec = float(params.get("photo_sec") or 15)
                except (TypeError, ValueError):
                    photo_sec = 15.0
                photo_sec = max(3.0, min(180.0, photo_sec))
                if narr_file:  # 🎤 녹음이 있으면 사진 전체 길이 = 녹음 길이 (v0.58)
                    from ..utils import ffmpeg as _ff  # noqa: PLC0415
                    photo_sec = max(3.0, _ff.probe_duration_us(narr_file) / 1e6)
                _set_job(job_id, stage="cut", frac=0.0,
                         note=f"사진 {len(imgs)}장 → {photo_sec:.0f}초 영상 만드는 중…")
                (Path(workdir) / job_id).mkdir(parents=True, exist_ok=True)
                video = photos_to_video(
                    imgs, int(photo_sec * 1e6),
                    str(Path(workdir) / job_id / "slideshow.mp4"),
                    transition=(params.get("transition") or "none"))
            except Exception as ve:  # noqa: BLE001
                _set_job(job_id, status="failed", errors=[str(ve)])
                return
        else:
            try:  # 폴더를 넣으면 안의 최신 영상 자동 선택
                video = resolve_input_video(params.get("video_path") or "")
            except ValueError as ve:
                _set_job(job_id, status="failed", errors=[str(ve)])
                return

        # 사진 영상은 무음이라 음성 인식·무음 컷이 의미 없음 → 자동 비활성
        auto_subtitle = params.get("auto_subtitle", True) and not photo_path
        cut_silence = bool(params.get("cut_silence", True)) and not photo_path
        script_lines = (params.get("script") or "").splitlines()
        has_script = any(ln.strip() for ln in script_lines)
        narr_topic = "" if narr_file else (params.get("narr_topic") or "").strip()
        narr_analyze = bool(params.get("narr_analyze")) and not narr_file  # 🧠 화면 분석 대본 (v0.69)
        # 🔊 붙여넣은 대본을 AI 목소리로 읽기 (v0.78) — 주제·녹음·화면분석 내레이션이 우선
        script_tts = (has_script and bool(params.get("script_tts"))
                      and not narr_file and not narr_topic and not narr_analyze)
        stt = None
        if auto_subtitle and not has_script and not narr_topic and not narr_file and not narr_analyze:
            # 대본/내레이션(AI·녹음) 있으면 원본 영상 STT 생략
            stt_name = params.get("stt_provider") or edit_cfg["stt_provider"]
            # Whisper 모델(정확도)을 이 작업에서 고른 값으로 덮어씀
            stt_cfg = {**edit_cfg, "whisper_model": params.get("whisper_model") or edit_cfg["whisper_model"]}
            stt = STTEngine(
                make_provider(stt_name, stt_cfg),
                Path(workdir) / "cache" / "stt",
                language=params.get("language", "ko"),
            )
        logging.getLogger("cutdaejang").info(
            "편집 시작: %s (내레이션=%s, 녹음=%s, 자막만=%s, 완전자동=%s)",
            Path(video).name, bool(narr_topic), bool(narr_file),
            bool(params.get('narr_subs_only')), bool(params.get("auto_edit")))
        _set_job(job_id, status="running", stage="analyze", frac=0.0, title=Path(video).stem)
        analysis = edit_mode.analyze_video(
            video, Path(workdir) / job_id, stt,
            auto_subtitle=auto_subtitle, cut_silence=cut_silence,
            script_lines=script_lines if has_script else None,
            silence_opts=SilenceOptions(
                noise_db=edit_cfg["noise_db"], min_silence_s=edit_cfg["min_silence_s"],
                pad_s=edit_cfg["pad_s"],
            ),
            progress_cb=lambda stage, frac: _set_job(job_id, stage=stage, frac=frac),
            status_cb=lambda msg: _set_job(job_id, note=msg),
        )
        # 2줄(기본 32자) 넘는 자막은 화면을 덮음 → 여러 개의 짧은 자막으로 자동 분할
        analysis.subtitles = edit_mode.split_long_subtitles(
            analysis.subtitles, settings["subtitle"].get("wrap_chars", 16))
        denoise = params.get("denoise") or False
        # 발화 자막이 없는 영상(화면 녹화·b-roll)은 핵심 선별을 못 함 → 완전 자동 +
        # 목표 초면 영상 전체에서 고르게 조각을 뽑아 목표 길이 몽타주로 먼저 자름
        tgt_auto = int(params.get("auto_target_sec") or 0) if params.get("auto_edit") else 0
        # 🧠 무음 대본(v0.71): 요약이면 그 길이로 몽타주, 원본이면 몽타주 안 함(전체 유지)
        if narr_analyze:
            _nl_mode = params.get("narr_len") or "summary"
            tgt_auto = max(20, min(600, int(params.get("narr_target_sec") or 60))) \
                if _nl_mode == "summary" else 0
        if narr_file and params.get("auto_edit") and not photo_path:
            # 🎤 녹음 모드 완전 자동: 영상 전체에서 녹음 길이만큼 고르게 (v0.58)
            from ..utils import ffmpeg as _ff  # noqa: PLC0415
            tgt_auto = max(5, int(_ff.probe_duration_us(narr_file) / 1e6))
        # '여러 개로 나누기'면 몽타주로 미리 줄이지 않음 — 전체를 그대로 나눠야 하니까
        if (tgt_auto > 0 and not analysis.subtitles and not photo_path
                and not params.get("auto_multi")
                and analysis.cut_us > (tgt_auto + 3) * 1_000_000):
            from ..core import video_editor as ve  # noqa: PLC0415
            _set_job(job_id, stage="cut", note=f"영상 전체에서 고르게 {tgt_auto}초를 뽑는 중…")
            # ⚡ 빠른 템포(v0.73) — 조각을 더 짧게 잡아 컷을 촘촘하게 (몽타주 리듬 up)
            _piece = {"빠르게": 2_400_000, "아주 빠르게": 1_700_000}.get(
                str(params.get("tempo") or ""), 3_500_000)
            ranges = edit_mode.spread_ranges(
                analysis.cut_us, tgt_auto * 1_000_000, piece_us=_piece)
            try:  # 🎬 장면 전환에 맞춰 조각 시작점을 스냅 — 컷이 장면 중간에서 안 끊기게 (v0.44)
                if analysis.cut_us < 20 * 60 * 1_000_000:  # 아주 긴 영상은 감지 생략(시간)
                    _set_job(job_id, note="장면 전환 지점을 찾는 중…")
                    scenes = ve.detect_scene_changes(analysis.cut_video)
                    if scenes:
                        ranges = ve.shift_ranges_to_scenes(ranges, scenes, analysis.cut_us)
            except Exception:  # noqa: BLE001 — 감지 실패는 스냅 없이 진행
                pass
            analysis.cut_video = ve.cut_and_concat(
                analysis.cut_video, ranges,
                str(Path(workdir) / job_id / "auto_montage.mp4"),
                transition=(params.get("transition") or "none"))
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            analysis.cut_us = ff.probe_duration_us(analysis.cut_video)
            _set_job(job_id, tts_warn=(
                f"자막(발화)이 없어 영상 전체에서 고르게 {tgt_auto}초를 골라 담았어요"))
        review_subs = analysis.subtitles
        narr_subs_only = bool(params.get("narr_subs_only"))
        if narr_file:  # 🎤 녹음 내레이션: 자막은 녹음에서 — 대본 있으면 그 글대로 (v0.58)
            _set_job(job_id, stage="stt", note="녹음에서 자막 만드는 중…")
            n_stt = None
            if not has_script:
                try:
                    stt_name = params.get("stt_provider") or edit_cfg["stt_provider"]
                    stt_cfg = {**edit_cfg, "whisper_model":
                               params.get("whisper_model") or edit_cfg["whisper_model"]}
                    n_stt = STTEngine(make_provider(stt_name, stt_cfg),
                                      Path(workdir) / "cache" / "stt",
                                      language=params.get("language", "ko"))
                except Exception as se:  # noqa: BLE001 — STT 없이도 진행(자막만 없음)
                    logging.getLogger("cutdaejang").warning("녹음 음성 인식 준비 실패: %s", se)
            try:
                narr_subs, _rec_us = edit_mode.analyze_narration_file(
                    narr_file, Path(workdir) / job_id, n_stt,
                    script_lines=script_lines if has_script else None,
                    silence_opts=SilenceOptions(
                        noise_db=edit_cfg["noise_db"],
                        min_silence_s=edit_cfg["min_silence_s"], pad_s=edit_cfg["pad_s"]),
                    progress_cb=lambda stage, frac: _set_job(job_id, stage=stage, frac=frac))
            except Exception as ne:  # noqa: BLE001
                _set_job(job_id, status="failed", errors=[f"녹음 파일 처리 실패: {ne}"])
                return
            review_subs = edit_mode.split_long_subtitles(
                narr_subs, settings["subtitle"].get("wrap_chars", 16))
            if not review_subs:
                w = ("⚠ 녹음에서 자막을 만들지 못했어요 (음성 인식 실패/무음) — "
                     "「📝 대본 직접 넣기」에 읽은 글을 붙여넣으면 자막이 정확히 들어가요")
                _set_job(job_id, tts_warn=w)
        elif narr_topic or narr_analyze:  # AI 내레이션: 대본 생성 → 컷 길이 비례 배치
            _set_job(job_id, stage="script", note="AI 대본 작성 중…")
            want = int(params.get("auto_target_sec") or 0) if params.get("auto_edit") else 0
            target = max(15, min(600, want or int(analysis.cut_us / 1e6)))
            script = None
            if narr_analyze and os.environ.get("GEMINI_API_KEY"):
                # 🧠 무음 시연영상 등 — 화면을 직접 보고 대본을 쓴다 (v0.69)
                try:
                    from ..core import edit_mode as _em, script_generator as _sg  # noqa: PLC0415
                    # 이 시점 cut_us = (요약이면) 몽타주된 길이 / (원본이면) 전체 길이
                    dur_s = max(1.0, analysis.cut_us / 1e6)
                    nfr = max(6, min(20, round(dur_s / 20)))  # 길이 비례 6~20컷
                    n_sent = max(6, min(80, round(dur_s / 4)))  # 대본 분량을 길이에 비례 (v0.71)
                    _set_job(job_id, note=f"화면 {nfr}컷 분석해 대본({n_sent}문장 내외) 쓰는 중…")
                    frames = _em.extract_frames_b64(analysis.cut_video, n=nfr)
                    out = _sg.suggest_from_video(frames, transcript="", topic=narr_topic,
                                                 n_sentences=n_sent)
                    lines = [s for s in (out.get("script") or []) if s.strip()]
                    if lines:
                        script = Script(title="", sentences=lines)
                except Exception:
                    script = None  # 실패하면 아래 주제 기반 생성으로 폴백
            if script is None:
                topic_for_gen = narr_topic or "이 영상 내용 소개"
                try:
                    provider = SCRIPT_PROVIDERS["gemini"]() if os.environ.get("GEMINI_API_KEY") \
                        else SCRIPT_PROVIDERS["stub"]()
                    # 완전 자동 + 목표 초가 있으면 대본을 그 길이로 (영상은 뒤에서 맞춰 자름)
                    script = provider.generate(topic_for_gen, target_sec=target)
                except Exception:
                    script = SCRIPT_PROVIDERS["stub"]().generate(topic_for_gen)
            review_subs = edit_mode.align_script_to_segments(
                script.sentences, [(0, analysis.cut_us)], total_us=analysis.cut_us)
            for sub, hl in zip(review_subs, script.highlights):
                sub.highlight = hl or ""
        # 🧹 필러(추임새) 컷 (v0.76) — STT 자막 흐름 + Whisper 단어 시각이 있을 때만
        if (params.get("filler_cut") and review_subs is analysis.subtitles
                and analysis.subtitles):
            if any(getattr(s, "words", None) for s in analysis.subtitles):
                try:
                    spans = edit_mode.detect_filler_spans(analysis.subtitles)
                    if spans:
                        _set_job(job_id, stage="cut",
                                 note=f"🧹 추임새 {len(spans)}곳 잘라내는 중…")
                        cut_s = sum(b - a for a, b, *_ in spans) / 1e6
                        nv, ns = edit_mode.apply_filler_cut(
                            analysis.cut_video, analysis.subtitles, spans,
                            str(Path(workdir) / job_id / "defiller.mp4"))
                        if nv != analysis.cut_video:
                            from ..utils import ffmpeg as _ff76  # noqa: PLC0415
                            analysis.cut_video, analysis.subtitles = nv, ns
                            analysis.cut_us = _ff76.probe_duration_us(nv)
                            review_subs = analysis.subtitles
                            w = f"🧹 추임새 {len(spans)}곳({cut_s:.1f}초)을 잘라냈어요"
                            prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                            _set_job(job_id, tts_warn=f"{prev} · {w}" if prev else w)
                except Exception as fe:  # noqa: BLE001 — 실패해도 원본으로 계속
                    logging.getLogger("cutdaejang").warning("추임새 컷 실패(무시): %s", fe)
            else:
                w = ("ℹ 추임새 컷은 Whisper 자막(단어 시각)에서만 돼요 — "
                     "음성 인식을 [내장 Whisper]로 바꾸면 사용돼요")
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                if w not in prev:
                    _set_job(job_id, tts_warn=f"{prev} · {w}" if prev else w)
        # 분석 결과를 job에 저장 (2단계 렌더에서 사용)
        _set_job(
            job_id, cut_video=analysis.cut_video,
            edit_params={"layout": params.get("layout") or edit_cfg["layout"],
                         "hook": (params.get("hook") or "").strip(),
                         # 자막만 모드면 대본은 쓰되 목소리(TTS)는 넣지 않음
                         "denoise": denoise,
                         "narration": (bool(narr_topic) or narr_analyze or script_tts) and not narr_subs_only,
                         "photo_files": photo_imgs,  # 📸 문장 타이밍 재배치용 (v0.79)
                         "narr_file": narr_file,  # 🎤 녹음 내레이션 (v0.58)
                         "narr_voice": (params.get("narr_voice") or "").strip(),
                         "narr_style": (params.get("narr_style") or "").strip(),
                         "narr_fit": params.get("narr_fit") or "freeze",
                         # 원본 소리: 목소리를 얹을 때만 기본 무음 (자막만이면 유지)
                         "orig_audio": params.get("orig_audio")
                         or ("mute" if ((narr_topic or narr_analyze or script_tts)
                                        and not narr_subs_only) or narr_file
                             else "keep"),
                         "bgm": (params.get("bgm") or "").strip(),
                         "bgm_db": params.get("bgm_db"),
                         "hook_scale": params.get("hook_scale"),
                         "hook_style": params.get("hook_style") or "",  # v0.52 프리셋
                         "sub_style": params.get("sub_style") or "",    # v0.54 자막 프리셋
                         "tone": params.get("tone") or "",              # v0.56 화면 톤
                         "cold_open": bool(params.get("cold_open")),    # ⚡ 콜드오픈 (v0.75)
                         "hook_voice": bool(params.get("hook_voice")),  # 🎙 후킹 보이스 (v0.75)
                         "wm_path": (params.get("wm_path") or "").strip().strip('"'),
                         "wm_pos": params.get("wm_pos") or "tr",
                         "wm_scale": params.get("wm_scale") or 0.14},
            edit_summary=_edit_summary(analysis),
        )
        fo = _font_overrides(params)  # ✒ 글씨체·기울임 기억 (v0.63 — 편집 폼)
        if fo and any(settings["subtitle"].get(k) != v for k, v in fo.items()):
            config.save_settings({"subtitle": fo})
            settings = config.deep_merge(settings, {"subtitle": fo})
        wm_p = (params.get("wm_path") or "").strip().strip('"')
        if wm_p and Path(wm_p).is_file():  # 다음에도 쓰게 기억 (브랜딩용)
            config.save_settings({"watermark": {"path": wm_p,
                                                "pos": params.get("wm_pos") or "tr",
                                                "scale": params.get("wm_scale") or 0.14}})
        analysis.subtitles = review_subs
        if params.get("auto_edit"):  # 🤖 완전 자동: 검토 생략, (키 있으면) AI 다듬기+핵심 선별 → 렌더
            from ..core import script_generator as sg  # noqa: PLC0415

            subs_d = edit_mode.subtitles_to_dicts(analysis.subtitles)
            if subs_d and os.environ.get("GEMINI_API_KEY") and not narr_topic and not has_script and not narr_file:
                _set_job(job_id, stage="script", note="AI가 대본을 다듬는 중…")
                try:
                    lines = sg.refine_subtitles([d["text"] for d in subs_d])
                    for d, t in zip(subs_d, lines):
                        if t:
                            d["text"] = t
                except Exception:
                    pass
            # ↻ 반복(NG) 테이크 정리 (v0.76) — 같은 말 다시 하기의 앞 테이크 제거
            if (params.get("take_clean") and subs_d
                    and not narr_topic and not has_script and not narr_file):
                try:
                    drops = set(edit_mode.detect_repeat_takes(
                        [d["text"] for d in subs_d]))
                    if drops:
                        subs_d = [d for i, d in enumerate(subs_d) if i not in drops]
                        w = f"↻ 반복 말하기 {len(drops)}곳 정리 (마지막 테이크 유지)"
                        prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                        _set_job(job_id, tts_warn=f"{prev} · {w}" if prev else w)
                except Exception:  # noqa: BLE001
                    pass
            keep = None
            tgt = int(params.get("auto_target_sec") or 0)
            try:
                auto_speed = float(params.get("speed") or 1.0)
            except (TypeError, ValueError):
                auto_speed = 1.0
            multi = bool(params.get("auto_multi")) and not photo_path
            if multi and (narr_topic or narr_file or narr_analyze or script_tts):  # 내레이션은 영상 전체 기준 → 분할과 배타
                multi = False
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                w = "ℹ 내레이션과 '여러 개로 나누기'는 함께 쓸 수 없어 1개로 만들었어요"
                _set_job(job_id, tts_warn=f"{prev} · {w}" if prev else w)
            if multi and tgt > 0:  # 🎬 영상 전체를 목표 길이 단위 쇼츠 여러 개로 (v0.38)
                _do_edit_split(job_id, subs_d, (params.get("hook") or "").strip(),
                               params.get("layout") or edit_cfg["layout"],
                               analysis.cut_video, workdir, float(tgt), auto_speed,
                               params.get("quality") or "standard", denoise)
                return
            # 내레이션 대본은 이미 목표 길이로 새로 쓴 글 → 핵심 선별로 또 자르지 않음
            # (🧠 화면분석 대본도 길이를 이미 정했으므로 재차 자르지 않음 — v0.71)
            climax = -1  # ⚡ 콜드오픈 티저 후보 (v0.75)
            if subs_d and tgt > 0 and not narr_topic and not narr_file and not narr_analyze and not script_tts:
                _set_job(job_id, note=f"핵심 구간 골라 {tgt}초 쇼츠 구성 중…")
                try:
                    pick = sg.suggest_highlights(subs_d, target_sec=tgt)
                    pick_src = "AI"
                except Exception as pe:
                    logging.getLogger("cutdaejang").warning(
                        "AI 핵심 추천 무효/실패 → 후킹 점수 방식으로 대체: %s", pe)
                    pick = sg.suggest_highlights_heuristic(subs_d, target_sec=tgt)
                    pick_src = "후킹 점수"
                keep = pick["keep"]
                climax = int(pick.get("climax", -1))
                if keep:  # 어떤 구간을 골랐는지 투명하게 (로그 + 완료 화면)
                    starts = [subs_d[i].get("start_us", 0) / 1e6 for i in keep]
                    fmt = " · ".join(f"{int(x // 60)}:{int(x % 60):02d}" for x in starts)
                    msg = f"✂️ 핵심 {len(keep)}구간({pick_src}): {fmt}"
                    logging.getLogger("cutdaejang").info(
                        "%s | 사유: %s", msg, pick.get("reason", ""))
                    prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                    _set_job(job_id, tts_warn=f"{prev} · {msg}" if prev else msg)
            _do_edit_render(job_id, subs_d, (params.get("hook") or "").strip(),
                            params.get("layout") or edit_cfg["layout"],
                            analysis.cut_video, workdir, keep, auto_speed,
                            params.get("quality") or "standard", denoise,
                            climax=climax)
            return
        if analysis.subtitles:  # STT/입력 대본/내레이션 대본이 있으면 검토 화면으로
            subs_d0 = edit_mode.subtitles_to_dicts(analysis.subtitles)
            try:  # ↻ 반복 테이크 후보 표시 (v0.76) — 검토 화면 배지·원클릭 정리용
                for ri in edit_mode.detect_repeat_takes([d["text"] for d in subs_d0]):
                    subs_d0[ri]["repeat"] = True
            except Exception:  # noqa: BLE001
                pass
            _set_job(
                job_id, status="review_subtitle", stage="review", note="",
                subtitles=subs_d0,
                cut_seconds=round(analysis.cut_us / 1e6, 1),
            )
        else:
            # 자막 없음(b-roll 등) → 바로 렌더
            _do_edit_render(job_id, [], params.get("hook", ""),
                            params.get("layout") or edit_cfg["layout"],
                            analysis.cut_video, workdir, denoise=denoise)
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("편집 분석 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _apply_trim(cut_video: str, subs: list, keep, trim, job_dir: Path):
    """앞뒤 트림 (v0.41 브루식 편집) — 영상을 자르고 자막을 시프트, keep 번호 재매핑.

    trim=(시작μs, 끝μs). 끝 0은 "영상 끝까지". 범위 밖 자막은 버리고 걸친 자막은 클램프.
    반환: (새 영상, 새 자막 목록, 재매핑된 keep, 안내 문구).
    """
    try:
        t0, t1 = int(trim[0] or 0), int(trim[1] or 0)
    except (TypeError, ValueError, IndexError):
        return cut_video, subs, keep, ""
    if t0 <= 0 and t1 <= 0:
        return cut_video, subs, keep, ""
    from ..core import video_editor  # noqa: PLC0415
    from ..utils import ffmpeg as ff  # noqa: PLC0415

    dur = ff.probe_duration_us(cut_video)
    t0 = max(0, min(t0, dur))
    t1 = min(t1, dur) if t1 > 0 else dur
    if t1 <= t0 + 300_000 or (t0 <= 0 and t1 >= dur):
        return cut_video, subs, keep, ""
    job_dir.mkdir(parents=True, exist_ok=True)
    video = video_editor.cut_and_concat(cut_video, [(t0, t1)], str(job_dir / "trimmed.mp4"))
    new_subs, idx_map = [], {}
    for i, s in enumerate(subs):
        if s.end_us <= t0 or s.start_us >= t1:
            continue
        s.start_us = max(0, s.start_us - t0)
        s.end_us = min(s.end_us, t1) - t0
        if s.end_us > s.start_us:
            idx_map[i] = len(new_subs)
            new_subs.append(s)
    if keep is not None:
        keep = [idx_map[i] for i in keep if i in idx_map]
    note = f"✂️ 앞뒤 트림: {t0 / 1e6:.1f}초 ~ {t1 / 1e6:.1f}초 사용"
    return video, new_subs, keep, note


def _narr_tts_pref(ep: dict, settings: dict) -> tuple:
    """내레이션 보이스 선택 → (폴백 체인, voice) — 내레이션·후킹 보이스 공용 (v0.75)."""
    narr_voice = (ep.get("narr_voice") or "").strip()
    chain = []
    if narr_voice == "__sovits__":
        chain.append("sovits")      # 무료 내 목소리(로컬) — 실패 시 아래로 폴백
    if narr_voice == "__mine__" and os.environ.get("ELEVENLABS_API_KEY"):
        chain.append("elevenlabs")  # 내 목소리 클론 — 실패 시 아래로 폴백
    if narr_voice.startswith("el:") and os.environ.get("ELEVENLABS_API_KEY"):
        chain.append("elevenlabs")  # 🎙 일레븐랩스 성우 보이스 (v0.46)
    if os.environ.get("GEMINI_API_KEY"):
        chain.append("gemini")
    if sys.platform == "win32":
        chain.append("windows")
    chain.append("stub")
    # __mine__/__sovits__는 보이스명이 아니라서 비움 → 제공자별 기본값으로 해석
    if narr_voice.startswith("el:"):
        voice = narr_voice[3:]      # 일레븐랩스 voice_id
    else:
        voice = "" if narr_voice in ("__mine__", "__sovits__") else (
            narr_voice or settings["tts"].get("voice_gemini", ""))
    return chain, voice


def _do_edit_render(job_id: str, subtitles_dicts: list, hook: str, layout: str,
                    cut_video: str, workdir: str, keep: Optional[list] = None,
                    speed: float = 1.0, quality: str = "standard",
                    denoise=False, trim=(0, 0), climax: int = -1) -> None:
    """2단계: (수정된) 자막으로 최종 렌더. keep이 일부면 그 구간만 남겨 쇼츠로 재컷."""
    try:
        from ..core import edit_mode  # noqa: PLC0415
        from ..core.orchestrator import build_style  # noqa: PLC0415

        settings = config.load_settings()
        note = "고화질(4K) 렌더는 사양에 따라 몇 분 걸릴 수 있어요…" if quality == "ultra" else ""
        # 최종 자막을 job에 남김 → 📦 업로드 키트가 대본으로 활용 (완전 자동 포함)
        _set_job(job_id, status="running", stage="render", frac=0.0, note=note,
                 subtitles=subtitles_dicts)
        subs = edit_mode.dicts_to_subtitles(subtitles_dicts)
        cut_video, subs, keep, trim_note = _apply_trim(
            cut_video, subs, keep, trim, Path(workdir) / job_id)
        if trim_note:
            prev = (_get_job(job_id) or {}).get("tts_warn") or ""
            _set_job(job_id, tts_warn=f"{prev} · {trim_note}" if prev else trim_note)
        out = str(Path(workdir) / job_id / "edited.mp4")
        job = _get_job(job_id) or {}
        ep = job.get("edit_params") or {}
        if not ep.get("narration"):  # 검토에서 길게 고친 줄도 2줄 초과면 분할 (내레이션은 문장=클립 유지)
            subs = edit_mode.split_long_subtitles(
                subs, settings["subtitle"].get("wrap_chars", 16))
        style = build_style(settings)
        if ep.get("hook_style"):  # 🪧 상단 제목 스타일 프리셋 (v0.52)
            style.hook_style = str(ep["hook_style"])
        if ep.get("sub_style"):  # 💬 자막 프리셋 (v0.54)
            style.sub_style = str(ep["sub_style"])
        if ep.get("tone"):  # 🎨 화면 톤 (v0.56)
            style.tone = str(ep["tone"])
        if ep.get("sub_anim") in ("none", "pop", "type", "karaoke"):  # 🎬 감성 테마 (v0.86)
            style.anim = str(ep["sub_anim"])
        if ep.get("sub_pos") in ("center", "bottom"):  # 🎨 자막 위치 — 릴스 가운데 (v0.87)
            style.position = str(ep["sub_pos"])
        try:  # 상단 제목 크기 배수 (훅 스튜디오)
            style.hook_scale = float(ep.get("hook_scale") or 1.0)
        except (TypeError, ValueError):
            style.hook_scale = 1.0
        try:  # ↕ 검토 화면에서 드래그한 자막 세로 위치 (v0.49)
            if int(ep.get("margin_v") or 0):
                style.margin_v = max(60, min(1400, int(ep["margin_v"])))
        except (TypeError, ValueError):
            pass
        if ep.get("narr_style"):  # 내레이션 말투 스타일 (Gemini TTS 프롬프트에 반영)
            settings = config.deep_merge(settings, {"tts": {"style_preset": ep["narr_style"]}})
        orig_audio = ep.get("orig_audio") or "keep"
        bgm_path = None
        if ep.get("bgm"):
            b = orchestrator.resolve_bgm(ep["bgm"], settings)
            bgm_path = b.path if b else None
        try:
            bgm_db = float(ep.get("bgm_db"))
        except (TypeError, ValueError):
            bgm_db = float(settings["bgm"].get("volume_db", -16))
        # 핵심 구간만 골랐으면(전체가 아니면) 영상을 그 구간만 다시 잘라 진짜 쇼츠 길이로.
        # 내레이션보다 먼저 잘라야 목소리가 최종 타임라인 기준으로 배치된다.
        # ⚡ 콜드오픈(v0.75): 내레이션 없는 흐름에서만 — 클라이맥스 티저를 맨 앞에.
        cold_open = (bool(ep.get("cold_open")) and bool(subs)
                     and not ep.get("narration") and not ep.get("narr_file"))
        if keep is not None and 0 < len(keep) < len(subs):
            _set_job(job_id, stage="cut", frac=0.0,
                     note=f"고른 {len(keep)}개 구간만 남겨 쇼츠로 자르는 중…")
            if cold_open:
                cut_video, subs, teaser_s = edit_mode.rebuild_cold_open(
                    cut_video, subs, keep, str(Path(workdir) / job_id / "short.mp4"),
                    climax_idx=climax, transition=(ep.get("transition") or "none"),
                )
                if teaser_s > 0:
                    w3 = f"⚡ 콜드오픈: 클라이맥스 {teaser_s:.1f}초를 맨 앞 티저로 배치"
                    prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                    _set_job(job_id, tts_warn=f"{prev} · {w3}" if prev else w3)
            else:
                cut_video, subs = edit_mode.rebuild_from_keep(
                    cut_video, subs, keep, str(Path(workdir) / job_id / "short.mp4"),
                    transition=(ep.get("transition") or "none"),
                )
        elif cold_open and len(subs) >= 2:
            # 구간 선별 없이(전체 사용) 콜드오픈만 켠 경우 — 전체 본편 앞에 티저
            _set_job(job_id, stage="cut", frac=0.0,
                     note="클라이맥스 티저 배치 중… (긴 영상은 몇 분 걸릴 수 있어요 — 멈춘 게 아니에요)")
            cut_video, subs, teaser_s = edit_mode.rebuild_cold_open(
                cut_video, subs, None, str(Path(workdir) / job_id / "short.mp4"),
                climax_idx=climax, transition=(ep.get("transition") or "none"),
            )
            if teaser_s > 0:
                w3 = f"⚡ 콜드오픈: 클라이맥스 {teaser_s:.1f}초를 맨 앞 티저로 배치"
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                _set_job(job_id, tts_warn=f"{prev} · {w3}" if prev else w3)
        narration_wav = None
        narr_rec = (ep.get("narr_file") or "").strip()
        if narr_rec and Path(narr_rec).is_file():
            # 🎤 녹음 내레이션 통째 넣기 (v0.58) — TTS 없이 녹음이 그대로 목소리 트랙
            from ..core import video_editor  # noqa: PLC0415
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            cut_us = ff.probe_duration_us(cut_video)
            rec_us = ff.probe_duration_us(narr_rec)
            narr_fit = ep.get("narr_fit") or "freeze"
            narr_end_us = rec_us + 400_000  # 말 끝나고 살짝 여유
            if narr_fit in ("freeze", "loop") and narr_end_us > cut_us + 50_000:
                extra_s = (narr_end_us - cut_us) / 1e6
                _set_job(job_id, stage="cut", note="녹음 길이에 맞춰 영상을 늘리는 중…")
                cut_video = video_editor.extend_video(
                    cut_video, narr_end_us,
                    str(Path(workdir) / job_id / "narr_ext.mp4"), mode=narr_fit)
                cut_us = ff.probe_duration_us(cut_video)
                mode_ko = "마지막 장면 정지" if narr_fit == "freeze" else "영상 반복"
                w2 = f"⏱ 녹음이 영상보다 길어 {mode_ko}로 {extra_s:.1f}초 연장했어요"
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                _set_job(job_id, tts_warn=f"{prev} · {w2}" if prev else w2)
            elif cut_us > narr_end_us + 1_500_000:
                _set_job(job_id, stage="cut", note="녹음 길이에 맞춰 영상을 다듬는 중…")
                cut_video = video_editor.cut_and_concat(
                    cut_video, [(0, narr_end_us)],
                    str(Path(workdir) / job_id / "narr_fit.mp4"))
                cut_us = ff.probe_duration_us(cut_video)
            narration_wav = str(Path(workdir) / job_id / "narration.wav")
            # 영상 길이에 맞춰 뒤 무음 패드/초과 컷 (원본 소리는 렌더에서 무음/덕킹)
            ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(narr_rec),
                    "-af", f"apad,atrim=0:{cut_us / 1e6:.3f}",
                    "-ar", "44100", "-ac", "2", narration_wav])
        elif ep.get("narration") and subs:
            import re as _re  # noqa: PLC0415
            from ..core import tts_engine  # noqa: PLC0415

            def _tts_clean(t: str) -> str:  # 색 마크업·강조 표기는 TTS에서 제거
                t = _re.sub(r"\[[가-힣A-Za-z]+\]|\[/[가-힣A-Za-z]*\]", "", t)
                return (t.rsplit("|", 1)[0] if "|" in t else t).strip()

            _set_job(job_id, stage="tts", frac=0.0, note="AI 목소리 만드는 중…")
            narr_voice = ep.get("narr_voice") or ""
            chain, voice = _narr_tts_pref(ep, settings)  # 보이스 선택 → 체인 (v0.75 공용화)
            texts = [_tts_clean(s2.text) or "네" for s2 in subs]
            clips, used, note = tts_engine.synth_with_fallback(
                texts, chain, Path(workdir) / "cache" / "tts", settings,
                voice=voice,
                on_progress=lambda i, n: _set_job(job_id, stage="tts", frac=i / n),
            )
            # 고른 보이스가 반영 안 되는 폴백이면 이유를 사용자에게 알림
            want = {"__mine__": "elevenlabs", "__sovits__": "sovits"}.get(narr_voice)
            if narr_voice.startswith("el:"):
                want = "elevenlabs"
            warn = ""
            if want and used != want:
                warn = "⚠ 내 목소리 합성에 실패해 다른 목소리로 대체했어요"
            elif used in ("windows", "stub") and narr_voice not in ("", "__mine__", "__sovits__"):
                low = (note or "").lower()
                if os.environ.get("GEMINI_API_KEY") and any(
                        k in low for k in ("429", "resource_exhausted", "quota", "exceed", "한도")):
                    warn = ("⚠ 제미나이 무료 TTS 한도에 걸려 내장 음성으로 대체됐어요 — "
                            "잠시 뒤(한도 리셋 후) 같은 설정으로 다시 만들면 이미 만든 문장은 "
                            "재사용돼 이어서 완성됩니다. 문장 수를 줄이면 한도 안에 들어가요")
                elif os.environ.get("GEMINI_API_KEY"):
                    warn = "⚠ 제미나이 목소리 합성이 실패해 내장 음성으로 대체됐어요 (하단 🪵 로그 참고)"
                else:
                    warn = ("⚠ 제미나이 키가 없거나 실패해 내장 음성으로 만들었어요 — "
                            "보이스 선택은 제미나이 키가 있어야 적용됩니다")
            if warn:
                logging.getLogger("cutdaejang").warning("%s (사유: %s)", warn, (note or "")[:200])
                note = f"{note} · {warn}" if note else warn
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                _set_job(job_id, tts_warn=f"{prev} · {warn}" if prev else warn)  # 완료 화면 보존
            from ..core import video_editor  # noqa: PLC0415
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            cut_us = ff.probe_duration_us(cut_video)
            narr_fit = ep.get("narr_fit") or "freeze"
            # 목소리 실제 길이에 맞춰 자막 재배치 → 자막·목소리 싱크 보장
            subs, clips, sync_note = edit_mode.retime_narration(
                clips, subs, cut_us, Path(workdir) / job_id, fit=narr_fit)
            if sync_note:
                note = f"{note} · {sync_note}" if note else sync_note
            narr_end_us = subs[-1].end_us + 700_000 if subs else cut_us
            # 📸→🗣 사진을 문장 타이밍에 맞춰 재배치 (v0.79) — 예상 길이가 어긋나면
            # 꼬리 트림으로 뒤쪽 사진이 통째로 사라지고 내레이션과 안 맞던 문제 해결
            photo_synced = False
            photo_files = [p for p in (ep.get("photo_files") or []) if Path(p).is_file()]
            if photo_files and subs:
                try:
                    import traceback as _tb  # noqa: PLC0415

                    from ..core import background_generator as bg_gen  # noqa: PLC0415
                    from ..spec import Canvas  # noqa: PLC0415
                    _set_job(job_id, stage="cut", note="사진을 내레이션 문장 타이밍에 맞춰 배치 중…")
                    spans = video_editor.photo_sentence_spans(
                        len(photo_files), [s.start_us for s in subs], narr_end_us)
                    if spans:
                        cw, ch = (1920, 1080) if layout == "wide" else (1080, 1920)
                        synced_path = str(Path(workdir) / job_id / "photo_sync.mp4")
                        bg_gen.scene_slideshow(
                            [(photo_files[i], d) for i, d in spans], synced_path,
                            Canvas(w=cw, h=ch, fps=30))
                        cut_video = synced_path
                        cut_us = ff.probe_duration_us(cut_video)
                        photo_synced = True
                        used = len({i for i, _ in spans})
                        w3 = f"📸 사진 {used}장을 내레이션 문장 타이밍에 맞춰 배치했어요"
                        if used < len(photo_files):
                            w3 += f" (문장 수보다 많은 사진 {len(photo_files) - used}장은 뺐어요)"
                        prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                        _set_job(job_id, tts_warn=f"{prev} · {w3}" if prev else w3)
                except Exception:  # noqa: BLE001 — 실패 시 기존 늘림/트림 방식으로 계속
                    logging.getLogger("cutdaejang").warning(
                        "사진-문장 싱크 배치 실패 → 기본 방식 사용\n%s", _tb.format_exc())
            if photo_synced:
                pass  # 길이가 내레이션과 정확히 일치 — 늘림/트림 불필요
            elif narr_fit in ("freeze", "loop") and narr_end_us > cut_us + 50_000:
                # v0.42: 내레이션이 더 길면 영상을 늘려 전 문장을 담는다 (정지/반복)
                extra_s = (narr_end_us - cut_us) / 1e6
                _set_job(job_id, stage="cut", note="내레이션 길이에 맞춰 영상을 늘리는 중…")
                cut_video = video_editor.extend_video(
                    cut_video, narr_end_us,
                    str(Path(workdir) / job_id / "narr_ext.mp4"), mode=narr_fit)
                cut_us = ff.probe_duration_us(cut_video)
                mode_ko = "마지막 장면 정지" if narr_fit == "freeze" else "영상 반복"
                w2 = f"⏱ 내레이션이 길어 {mode_ko}로 {extra_s:.1f}초 연장했어요"
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                _set_job(job_id, tts_warn=f"{prev} · {w2}" if prev else w2)
            # 내레이션이 끝난 뒤 영상 꼬리가 길게 남으면 잘라 템포 유지
            elif cut_us > narr_end_us + 1_500_000:
                _set_job(job_id, stage="cut", note="내레이션 길이에 맞춰 영상을 다듬는 중…")
                cut_video = video_editor.cut_and_concat(
                    cut_video, [(0, narr_end_us)],
                    str(Path(workdir) / job_id / "narr_fit.mp4"))
                cut_us = ff.probe_duration_us(cut_video)
            narration_wav = edit_mode.build_narration_wav(
                clips, subs, cut_us, Path(workdir) / job_id / "narration.wav")
            if note:
                _set_job(job_id, note=note)
        watermark = None
        if ep.get("wm_path"):
            if Path(ep["wm_path"]).is_file():
                watermark = {"path": ep["wm_path"], "pos": ep.get("wm_pos") or "tr",
                             "scale": ep.get("wm_scale") or 0.14,
                             "opacity": settings["watermark"].get("opacity", 0.85)}
            else:
                logging.getLogger("cutdaejang").warning(
                    "워터마크 파일을 찾지 못해 없이 렌더: %s", ep["wm_path"])
        result = edit_mode.render_from_analysis(
            cut_video, subs, out, style=style,
            layout=layout, hook=hook, speed=speed, quality=quality, denoise=denoise,
            narration_wav=narration_wav,
            orig_audio=orig_audio, bgm_path=bgm_path, bgm_db=bgm_db,
            bgm_duck=bool(settings["bgm"].get("duck", True)),
            watermark=watermark,
            progress_cb=lambda f: _set_job(job_id, stage="render", frac=f),
        )
        logging.getLogger("cutdaejang").info(
            "렌더 %s: %s", "완료" if result.ok else "부분 실패", out)
        # 🎙 후킹 보이스 (v0.75) — 훅 제목을 성우가 읽는 인트로를 맨 앞에
        if ep.get("hook_voice") and (hook or "").strip() and Path(out).exists():
            try:
                from ..core import sfx as sfx_mod  # noqa: PLC0415
                from ..core import tts_engine, video_editor  # noqa: PLC0415
                from ..core.orchestrator import _hook_voice_text  # noqa: PLC0415

                hv_text = _hook_voice_text(hook)
                if hv_text:
                    _set_job(job_id, note="🎙 후킹 보이스 만드는 중…")
                    chain2, voice2 = _narr_tts_pref(ep, settings)
                    clips2, used2, _n2 = tts_engine.synth_with_fallback(
                        [hv_text], chain2, Path(workdir) / "cache" / "tts",
                        settings, voice=voice2)
                    ding = ""
                    if (settings.get("sfx") or {}).get("enabled", True):
                        try:
                            ding = sfx_mod.ensure_sfx().get("ding", "")
                        except Exception:  # noqa: BLE001
                            ding = ""
                    intro = video_editor.hook_intro_clip(
                        out, str(clips2[0]),
                        str(Path(workdir) / job_id / "hook_intro.mp4"), ding=ding,
                        gain_db=float((settings.get("sfx") or {}).get("volume_db", -13)))
                    merged = video_editor.attach_branding(
                        out, intro, "", str(Path(workdir) / job_id / "hooked.mp4"))
                    if merged != out and Path(merged).is_file():
                        os.replace(merged, out)
                        w4 = f"🎙 후킹 보이스 인트로를 앞에 붙였어요 (목소리: {used2})"
                        prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                        _set_job(job_id, tts_warn=f"{prev} · {w4}" if prev else w4)
            except Exception as hv_e:  # noqa: BLE001 — 부가 기능: 실패해도 본편 유지
                logging.getLogger("cutdaejang").warning("후킹 보이스 실패(무시): %s", hv_e)
                prev = (_get_job(job_id) or {}).get("tts_warn") or ""
                w4 = "⚠ 후킹 보이스 만들기에 실패해 본편만 저장했어요"
                if w4 not in prev:
                    _set_job(job_id, tts_warn=f"{prev} · {w4}" if prev else w4)
        if Path(out).exists():  # 🎬 인트로/아웃트로 (설정에 있으면, v0.43)
            _attach_branding(job_id, out, Path(workdir) / job_id)
        _set_job(
            job_id,
            status="ok" if result.ok else "partial" if Path(out).exists() else "failed",
            stage="done", frac=1.0,
            note=(_get_job(job_id) or {}).get("tts_warn") or "",
            job_dir=str(Path(workdir) / job_id),
            mp4=out if Path(out).exists() else None,
            errors=result.errors,
        )
        _record_simple_history(   # 📜 편집·사진·블로그 영상도 히스토리에 (v0.85)
            workdir, job_id,
            title=(_get_job(job_id) or {}).get("title") or "✂️ 내 영상 편집",
            mode="edit",
            status="ok" if result.ok else "partial" if Path(out).exists() else "failed",
            mp4=out if Path(out).exists() else None)
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("편집 렌더 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


_SPLIT_MAX = 30  # 분할 쇼츠 상한 — 초장편 영상이 수백 개 렌더로 폭주하지 않게


def _do_edit_split(job_id: str, subtitles_dicts: list, hook: str, layout: str,
                   cut_video: str, workdir: str, target_sec: float = 30.0,
                   speed: float = 1.0, quality: str = "standard",
                   denoise=False, trim=(0, 0)) -> None:
    """긴 영상을 목표 길이 단위 쇼츠 여러 개로 분할 렌더 (edited_1..N.mp4).

    자막이 있으면 자막 흐름 단위로, 없으면 시간 기준 균등 분할(v0.38 완전 자동용).
    편집 폼에서 정한 원본 소리·BGM·워터마크도 각 쇼츠에 그대로 적용된다.
    """
    try:
        from ..core import edit_mode, video_editor  # noqa: PLC0415
        from ..core.orchestrator import build_style  # noqa: PLC0415
        from ..utils import ffmpeg as ff  # noqa: PLC0415

        if layout in ("keep", "wide"):  # 📐 비율을 완료 화면에 명시 (v0.76.1·v0.77 — 혼동 방지)
            how = "원본 비율" if layout == "keep" else "가로(16:9)"
            w0 = (f"📐 {how}로 나눴어요 — 세로 쇼츠(9:16)를 원하면 편집 폼 ①에서 "
                  "[쇼츠 (세로 9:16)]을 고르고 다시 만들어 주세요")
            prev = (_get_job(job_id) or {}).get("tts_warn") or ""
            if w0 not in prev:
                _set_job(job_id, tts_warn=f"{prev} · {w0}" if prev else w0)
        settings = config.load_settings()
        subs = edit_mode.dicts_to_subtitles(subtitles_dicts)
        cut_video, subs, _, trim_note = _apply_trim(
            cut_video, subs, None, trim, Path(workdir) / job_id)
        if trim_note:
            prev = (_get_job(job_id) or {}).get("tts_warn") or ""
            _set_job(job_id, tts_warn=f"{prev} · {trim_note}" if prev else trim_note)
        groups = edit_mode.split_into_clips(subs, target_sec=target_sec)
        plan: list = [("subs", g) for g in groups]
        if not plan:  # 자막 없음 → 시간 기준 균등 분할
            total_us = ff.probe_duration_us(cut_video)
            tgt_us = max(3_000_000, int(target_sec * 1e6))
            if total_us < int(tgt_us * 1.5):
                _set_job(job_id, status="failed",
                         errors=["나눌 자막이 없고 영상도 1개당 길이보다 짧아 나눌 수 없습니다 "
                                 "(여러 개로 나누려면 영상이 목표의 1.5배 이상이어야 해요)"])
                return
            ranges = [(s, min(s + tgt_us, total_us)) for s in range(0, total_us, tgt_us)]
            if len(ranges) > 1 and (ranges[-1][1] - ranges[-1][0]) < int(tgt_us * 0.4):
                last = ranges.pop()  # 꼬리가 너무 짧으면 앞 쇼츠에 합침
                ranges[-1] = (ranges[-1][0], last[1])
            try:  # 🎬 분할 경계를 장면 전환에 스냅 — 쇼츠가 장면 중간에서 안 끊기게 (v0.44)
                if len(ranges) > 1 and total_us < 20 * 60 * 1_000_000:
                    _set_job(job_id, note="장면 전환 지점을 찾는 중…")
                    scenes = video_editor.detect_scene_changes(cut_video)
                    if scenes:
                        ranges = video_editor.snap_boundaries_to_scenes(ranges, scenes)
            except Exception:  # noqa: BLE001
                pass
            plan = [("time", r) for r in ranges]
        note_extra = ""
        if len(plan) > _SPLIT_MAX:
            note_extra = f" (앞에서부터 {_SPLIT_MAX}개까지만 — 원본이 아주 길어요)"
            plan = plan[:_SPLIT_MAX]
        # 편집 폼 소리·브랜딩 옵션을 각 쇼츠에도 동일 적용
        ep = (_get_job(job_id) or {}).get("edit_params") or {}
        orig_audio = ep.get("orig_audio") or "keep"
        bgm_path = None
        if ep.get("bgm"):
            b = orchestrator.resolve_bgm(ep["bgm"], settings)
            bgm_path = b.path if b else None
        try:
            bgm_db = float(ep.get("bgm_db"))
        except (TypeError, ValueError):
            bgm_db = float(settings["bgm"].get("volume_db", -16))
        watermark = None
        if ep.get("wm_path") and Path(ep["wm_path"]).is_file():
            watermark = {"path": ep["wm_path"], "pos": ep.get("wm_pos") or "tr",
                         "scale": ep.get("wm_scale") or 0.14,
                         "opacity": settings["watermark"].get("opacity", 0.85)}
        job_dir = Path(workdir) / job_id
        outs, errors = [], []
        style = build_style(settings)
        if ep.get("hook_style"):  # 🪧 상단 제목 스타일 프리셋 (v0.52)
            style.hook_style = str(ep["hook_style"])
        if ep.get("sub_style"):  # 💬 자막 프리셋 (v0.54)
            style.sub_style = str(ep["sub_style"])
        if ep.get("tone"):  # 🎨 화면 톤 (v0.56)
            style.tone = str(ep["tone"])
        if ep.get("sub_anim") in ("none", "pop", "type", "karaoke"):  # 🎬 감성 테마 (v0.86)
            style.anim = str(ep["sub_anim"])
        if ep.get("sub_pos") in ("center", "bottom"):  # 🎨 자막 위치 — 릴스 가운데 (v0.87)
            style.position = str(ep["sub_pos"])
        try:
            style.hook_scale = float(ep.get("hook_scale") or 1.0)
        except (TypeError, ValueError):
            style.hook_scale = 1.0
        try:  # ↕ 드래그한 자막 위치 (v0.49)
            if int(ep.get("margin_v") or 0):
                style.margin_v = max(60, min(1400, int(ep["margin_v"])))
        except (TypeError, ValueError):
            pass
        for gi, (kind, item) in enumerate(plan, 1):
            _set_job(job_id, status="running", stage="render", frac=(gi - 1) / len(plan),
                     note=f"쇼츠 {gi}/{len(plan)} 만드는 중…{note_extra}")
            try:
                if kind == "subs":
                    clip_video, clip_subs = edit_mode.rebuild_from_keep(
                        cut_video, subs, item, str(job_dir / f"short_{gi}.mp4"),
                        transition=(ep.get("transition") or "none"),
                    )
                else:  # 시간 구간 분할 (자막 없음)
                    clip_video = video_editor.cut_and_concat(
                        cut_video, [item], str(job_dir / f"short_{gi}.mp4"))
                    clip_subs = []
                out = str(job_dir / f"edited_{gi}.mp4")
                base = (gi - 1) / len(plan)
                r = edit_mode.render_from_analysis(
                    clip_video, clip_subs, out, style=style, layout=layout,
                    hook=hook, speed=speed, quality=quality, denoise=denoise,
                    orig_audio=orig_audio, bgm_path=bgm_path, bgm_db=bgm_db,
                    bgm_duck=bool(settings["bgm"].get("duck", True)),
                    watermark=watermark,
                    progress_cb=lambda f, b=base, n=len(plan): _set_job(
                        job_id, stage="render", frac=b + f / n),
                )
                if Path(out).exists():
                    _attach_branding(job_id, out, job_dir, tag=f"_{gi}")  # 🎬 각 쇼츠에도
                    outs.append(out)
                errors += r.errors
            except Exception as ce:  # 한 클립 실패해도 나머지는 계속
                errors.append(f"쇼츠 {gi} 실패: {ce}")
        _set_job(
            job_id,
            status="ok" if outs and not errors else "partial" if outs else "failed",
            stage="done", frac=1.0, job_dir=str(job_dir),
            note=f"쇼츠 {len(outs)}개 완성{note_extra}" if outs else "",
            mp4=outs[0] if outs else None, mp4s=outs, errors=errors,
        )
        _record_simple_history(   # 📜 분할 쇼츠도 히스토리에 (v0.85)
            workdir, job_id,
            title=(_get_job(job_id) or {}).get("title") or "✂️ 쇼츠 나누기",
            mode="edit",
            status="ok" if outs and not errors else "partial" if outs else "failed",
            mp4=outs[0] if outs else None)
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("분할 렌더 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _bgm_credit(bgm_name: str) -> str:
    """쓴 BGM의 저작자표시(CC BY) 문구 — 무료 음원이면 자동으로 설명란용 크레딧 생성."""
    if not bgm_name or bgm_name == "random":
        return ""
    stem = Path(bgm_name).stem
    title = stem.split("_", 1)[-1] if "_" in stem else stem
    try:
        from ..tools.fetch_bgm import TRACKS  # noqa: PLC0415

        if any(t == title for _, t in TRACKS):  # 6_무료음원_받기로 받은 Kevin MacLeod 곡
            return ("🎵 BGM\n"
                    f'"{title}" Kevin MacLeod (incompetech.com)\n'
                    "Licensed under Creative Commons: By Attribution 4.0 License\n"
                    "http://creativecommons.org/licenses/by/4.0/")
    except Exception:
        pass
    return f"🎵 BGM: {stem}"


def _kit_text(kit: dict, title: str) -> str:
    """업로드 키트를 붙여넣기 좋은 텍스트 파일로 (job 폴더에 저장)."""
    ttags = " ".join(f"#{t}" for t in kit.get("title_tags", []))
    lines = ["=" * 46, f"📦 업로드 키트 — {title or '완성 영상'}", "=" * 46, ""]
    lines += ["【유튜브】 올리기 → https://studio.youtube.com",
              "── 제목 후보 (하나 골라 복사 — 제목 옆 태그 포함) ──"]
    lines += [f"{i}. {t}" + (f" {ttags}" if ttags else "")
              for i, t in enumerate(kit.get("titles", []), 1)]
    lines += ["", "── 설명문 (설명란에 그대로 붙여넣기) ──", kit.get("description", "")]
    lines += ["", "── 태그 (태그란에 통째로 붙여넣기) ──", ", ".join(kit.get("tags", []))]
    lines += ["", "── 핵심 키워드 10 ──", " · ".join(kit.get("keywords", []))]
    lines += ["", "── 카테고리 ──",
              f"{kit.get('category', '')} — {kit.get('category_reason', '')}"]
    tk = kit.get("tiktok") or {}
    if tk.get("caption"):
        lines += ["", "【틱톡】 올리기 → https://www.tiktok.com/tiktokstudio/upload",
                  "(캡션 — 해시태그 3~5개, fyp류 금지)", tk["caption"],
                  " ".join(f"#{t}" for t in tk.get("hashtags", []))]
    ig = kit.get("instagram") or {}
    if ig.get("caption"):
        lines += ["", "【인스타그램 릴스】 올리기 → https://www.instagram.com",
                  "(첫 줄이 미리보기에 노출 · 반드시 '릴스'로 올리기 — 피드 썸네일은 위아래가 잘려 보이는 게 정상)",
                  ig["caption"], " ".join(f"#{t}" for t in ig.get("hashtags", []))]
    nc = kit.get("naver_clip") or {}
    if nc.get("title"):
        lines += ["", "【네이버 클립】 올리기 → https://clipcreators.naver.com",
                  "(검색형 제목 + 태그 10~12개)",
                  f"제목: {nc['title']}",
                  "태그: " + " ".join(f"#{t}" for t in nc.get("tags", []))]
    th = kit.get("threads") or {}
    if th.get("post"):
        lines += ["", "【스레드】 올리기 → https://www.threads.com",
                  "(짧은 반말 · 태그는 토픽 1개만 지원)", th["post"]]
        if th.get("topic"):
            lines += [f"토픽 태그: {th['topic']}"]
    lines += ["", "── 업로드 체크리스트 ──"]
    lines += [f"□ {c}" for c in kit.get("checklist", [])]
    return "\n".join(lines) + "\n"


def _reuse_prev_scenes(job_id: str, workdir: str, need: list, canvas) -> dict:
    """♻ 같은 주제의 이전 작업 scenes 그림을 찾아 필요한 장면에 복사 (v0.62, 비용 0).

    작업 폴더 이름은 "{시각}-{주제슬러그}" — 슬러그가 같은 최신 폴더에서
    scene_XX.png를 찾아 현재 캔버스로 정규화해 가져온다. 반환: {장면 i: True}.
    """
    try:
        parts = job_id.split("-", 2)
        slug = parts[2] if len(parts) > 2 and parts[2] else ""
        if not slug:
            return {}
        root = Path(workdir)
        for prev in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
            if prev.name == job_id:
                continue
            pp = prev.name.split("-", 2)
            if len(pp) < 3 or pp[2] != slug:
                continue
            src_dir = prev / "scenes"
            if not src_dir.is_dir():
                continue
            avail = {int(f.stem.split("_")[1]) - 1: f
                     for f in src_dir.glob("scene_*.png") if f.stat().st_size > 500}
            hits = {i: avail[i] for i in need if i in avail}
            if not hits:
                continue
            dest_dir = Path(workdir) / job_id / "scenes"
            dest_dir.mkdir(parents=True, exist_ok=True)
            done = {}
            for i, f in hits.items():
                try:
                    background_generator.normalize_to_canvas(
                        str(f), str(dest_dir / f"scene_{i + 1:02d}.png"), canvas)
                    done[i] = True
                except Exception:  # noqa: BLE001 — 한 장 실패는 건너뜀
                    continue
            if done:
                logging.getLogger("cutdaejang").info(
                    "♻ 이전 작업(%s) 그림 %d장 재사용", prev.name, len(done))
            return done
    except Exception:  # noqa: BLE001 — 재사용은 보너스, 실패해도 원래 흐름
        pass
    return {}


def _prepare_scenes(job_id: str, script: Script, params: dict, workdir: str) -> None:
    """🖼 장면 검토 1단계 (v0.50) — 그림을 먼저 만들어 보여주고 확정을 기다린다.

    실패하면(전부 생성 불가 등) 검토 없이 기존 파이프라인으로 안전하게 넘어간다.
    """
    try:
        settings = _apply_bg_style(params, config.load_settings())
        provider, _skip = _ai_image_setup(params, settings)
        mode = settings["bg"].get("scene_mode", "auto")
        job_dir = Path(workdir) / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "script.json").write_text(script.to_json(), encoding="utf-8")
        if provider is None and mode != "manual":
            _run_pipeline(job_id, script, params, workdir)
            return
        from .. import presets  # noqa: PLC0415

        prompts = [sp or s for sp, s in zip(script.scene_prompts, script.sentences)]
        sel = sorted(background_generator.select_scene_indices(
            len(prompts), int(settings["bg"].get("max_scene_images", 0) or 0)))
        canvas_r = (presets.CANVAS_LANDSCAPE
                    if (params or {}).get("orientation") == "wide" else presets.CANVAS_SHORTS)
        reused = _reuse_prev_scenes(job_id, workdir, sel, canvas_r)  # ♻ 같은 주제 이전 그림
        _set_job(job_id, scene_style=settings["bg"].get("image_style", "일러스트"),
                 scene_character=(settings["bg"].get("character") or "").strip() or "없음")
        if mode == "manual":
            # ✍ 내가 넣기 (v0.51) — AI 생성 없이(비용 0원) 프롬프트만 뽑아 검토로.
            # [📋 전체 복사] → 챗지피티/제미나이에서 직접 생성 → [📁]로 삽입.
            scenes = [{"i": i, "prompt": prompts[i], "ok": bool(reused.get(i)),
                       "text": script.sentences[i]} for i in sel]
            note = "✍ 내가 넣기 — 프롬프트를 복사해 그림을 만들어 넣어주세요"
            if reused:
                note = (f"♻ 같은 주제의 이전 그림 {len(reused)}장을 미리 넣어뒀어요 (비용 0원) "
                        "— 그대로 쓰거나 바꿔주세요")
            _set_job(job_id, status="review_scenes", stage="review", frac=1.0,
                     note=note, scenes=scenes)
            return
        todo = [i for i in sel if i not in reused]  # ♻ 재사용분은 다시 만들지 않음 (v0.62)
        imgs = [None] * len(prompts)
        if todo:
            imgs = background_generator.generate_scene_images(
                prompts, provider, job_dir / "scenes", canvas_r,
                style=settings["bg"].get("image_style", "일러스트"),
                character=settings["bg"].get("character", ""),
                on_note=lambda m: _set_job(job_id, note=m),
                on_progress=lambda i, n: _set_job(
                    job_id, stage="background", frac=i / max(n, 1),
                    note=f"장면 그림 {min(i + 1, n)}/{n} 만드는 중…"),
                only_indices=set(todo),
            )
        ok_map = {i: bool(imgs[i]) or bool(reused.get(i)) for i in sel}
        if not any(ok_map.values()):  # 전부 실패 → 그래도 검토 화면에서 직접 넣을 수 있게 (v0.51)
            _set_job(job_id, status="review_scenes", stage="review", frac=1.0,
                     note="장면 그림 생성이 모두 실패했어요 — 프롬프트를 복사해 직접 만들어 "
                          "넣거나, 그대로 ✅ 완성하면 기본 배경으로 만들어져요",
                     scenes=[{"i": i, "prompt": prompts[i], "ok": False,
                              "text": script.sentences[i]} for i in sel])
            return
        scenes = [{"i": i, "prompt": prompts[i], "ok": ok_map[i],
                   "text": script.sentences[i]} for i in sel]
        note = (f"♻ 같은 주제의 이전 그림 {len(reused)}장 재사용 (비용 0원) — "
                "마음에 안 들면 [🔄 다시 그리기]" if reused else "")
        _set_job(job_id, status="review_scenes", stage="review", frac=1.0, note=note,
                 scenes=scenes)
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("장면 준비 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed", errors=[str(e)])


_BGM_TASK = {"running": False, "msg": ""}  # 🎵 무료 BGM 받기 진행 상태 (v0.50.1)

_WEBLINK_TASK = {"running": False, "msg": "", "result": None, "error": ""}  # 🔗 글 가져오기 (v0.78)


def _fetch_weblink_bg(url: str, workdir: str, target_sec: int,
                      pasted_text: str = "") -> None:
    """🔗 블로그 글 수집 → (키 있으면) AI 대본 요약 — 백그라운드 싱글턴 (v0.78).

    pasted_text(v0.86 🛍 상품 정보 직접 붙여넣기)가 있으면 크롤링 없이 그 글로
    바로 대본을 만든다 — 쿠팡·스마트스토어처럼 프로그램 접근을 막는 상품
    페이지용 우회 경로 (상세설명을 복사해 붙여넣으면 됨).
    """
    import hashlib as _hl  # noqa: PLC0415

    from ..core import script_generator as sg  # noqa: PLC0415
    from ..tools import fetch_web, product_page  # noqa: PLC0415

    log = logging.getLogger("cutdaejang")
    try:
        def say(msg: str) -> None:
            _WEBLINK_TASK["msg"] = msg

        if pasted_text.strip():
            first = next((ln.strip() for ln in pasted_text.splitlines() if ln.strip()), "")
            art = {"title": first[:60] or "상품 소개",
                   "text": pasted_text.strip(),
                   "images": [], "links": ([url] if url else []),
                   "source_url": url or "",
                   "notes": ["📋 붙여넣은 상품 정보로 만들었어요 — 사진은 [🖼 상품 사진 고르기]로 넣어주세요"]}
            dest = Path(workdir) / "weblink" / "pasted"
        elif product_page.is_shop_url(url):
            # 🛒 상품 링크 자동 수집 (v0.92) — 직접 요청 → PC 브라우저 헤드리스 → 폴백 안내
            try:
                prod = product_page.collect_product(url, progress_cb=say)
            except product_page.ShopBlockedError:
                try:                             # 폴백을 바로 할 수 있게 페이지를 열어준다
                    webbrowser.open(url)
                except Exception:  # noqa: BLE001
                    pass
                raise
            dest = Path(workdir) / "weblink" / _hl.sha1(url.encode("utf-8")).hexdigest()[:8]
            say(f"상품 사진 {len(prod['images'])}장 내려받는 중…")
            local, skipped = product_page.download_images(prod["images"], dest)
            note = (f"🛒 상품 페이지에서 자동 수집했어요 ({prod['via']} 경로) — "
                    f"사진 {len(local)}장" + (f", 자잘한 그림 {skipped}장 제외" if skipped else ""))
            art = {"title": prod["title"] or "상품 소개", "text": prod["text"],
                   "images": local, "links": [url],
                   "source_url": prod.get("final_url") or url, "notes": [note]}
        else:
            norm = fetch_web.normalize_url(url)
            dest = Path(workdir) / "weblink" / _hl.sha1(norm.encode("utf-8")).hexdigest()[:8]
            art = fetch_web.fetch_article(norm, dest, progress_cb=say)
        say("대본으로 정리하는 중…")
        try:
            summ = sg.summarize_article(art["title"], art["text"], target_sec=target_sec)
            summ_src = "AI"
        except Exception as se:  # noqa: BLE001 — 키 없음·응답 오류: 원문 문장 폴백
            log.warning("글 요약 AI 실패 → 원문 문장 사용: %s", se)
            summ = sg.summarize_article_stub(art["title"], art["text"], target_sec=target_sec)
            summ_src = "원문 문장"
        notes = list(art["notes"])
        if summ_src != "AI":
            notes.append("제미나이 키가 없거나 요약에 실패해 원문 문장을 그대로 대본으로 넣었어요"
                         " — 검토 화면에서 다듬어 주세요")
        result = {
            "title": summ.get("title") or art["title"],
            "hook": summ.get("hook") or "",
            "script_lines": summ.get("sentences") or [],
            "hashtags": summ.get("hashtags") or [],
            "images": art["images"],
            # 🖼 브라우저 미리보기 주소 (v0.79) — /weblink/<해시>/<파일>
            "previews": [f"/weblink/{dest.name}/{Path(pth).name}" for pth in art["images"]],
            "links": art["links"],
            "text_excerpt": (art["text"] or "")[:2000],
            "text": art["text"],
            "source_url": art["source_url"],
            "notes": notes,
        }
        _WEBLINK_TASK.update(running=False, error="",
                             msg=f"완료 — 사진 {len(art['images'])}장 · 대본 "
                                 f"{len(result['script_lines'])}문장 ({summ_src})",
                             result=result)
    except ValueError as ve:                      # 사용자에게 그대로 보여줄 안내
        _WEBLINK_TASK.update(running=False, result=None, msg="", error=str(ve)[:300])
    except Exception as e:  # noqa: BLE001
        import traceback  # noqa: PLC0415

        log.error("웹링크 수집 실패\n%s", traceback.format_exc())
        _WEBLINK_TASK.update(running=False, result=None, msg="",
                             error=f"글 가져오기에 실패했어요: {str(e)[:200]}")


def _fetch_bgm_bg() -> None:
    """무료 BGM 14곡 다운로드 — 화면 버튼용 백그라운드 작업 (bat과 같은 일)."""
    from ..tools import fetch_bgm as fb  # noqa: PLC0415

    try:
        def progress_fetch(url, dest):
            _BGM_TASK["msg"] = f"받는 중… {dest.name}"
            return fb.fetch(url, dest)

        ok, fail = fb.main(bgm_dir=orchestrator.DEFAULT_BGM_DIR, fetch_fn=progress_fetch)
        if not ok and fail:
            msg = "받기 실패 — 인터넷 연결(방화벽)을 확인하고 다시 눌러주세요"
        else:
            msg = f"무료 BGM {len(ok)}곡 준비 완료!"
            if fail:
                msg += f" (실패 {len(fail)}곡 — 다시 누르면 그 곡만 재시도)"
        _BGM_TASK.update(running=False, msg=msg)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("cutdaejang").error("BGM 받기 실패: %s", e)
        _BGM_TASK.update(running=False, msg=f"받기 실패: {str(e)[:120]}")


def _run_sections(job_id: str, params: dict, workdir: str) -> None:
    """🎞 구간 대본 영상 (v0.80) — 구간마다 (클립, 내레이션) → 압축·낭독·자막 → 합본.

    구간 길이 = 내레이션 실제 길이. 클립이 길면 핵심 조각 몽타주(spread_ranges
    + 장면 스냅)로 압축, 짧으면 마지막 장면 정지로 연장. 구간별 렌더 후 이어붙임.
    """
    try:
        from ..core import edit_mode, tts_engine, video_editor  # noqa: PLC0415
        from ..core.orchestrator import build_style, resolve_bgm  # noqa: PLC0415
        from ..core.script_generator import Script, split_long_sentences  # noqa: PLC0415
        from ..utils import ffmpeg as ff  # noqa: PLC0415

        settings = config.load_settings()
        secs = [s for s in (params.get("sections") or [])
                if str(s.get("narration") or "").strip()]
        if not secs:
            _set_job(job_id, status="failed", errors=["구간이 없습니다 — 구간을 추가해 주세요"])
            return
        layout = params.get("layout") if params.get("layout") in ("wide", "shorts") else "wide"
        quality = params.get("quality") or "standard"
        piece_us = {"빠르게": 2_400_000, "아주 빠르게": 1_700_000}.get(
            str(params.get("tempo") or ""), 3_500_000)
        job_dir = Path(workdir) / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        style = build_style(settings)
        if params.get("hook_style"):     # 🎨 꾸미기 오버라이드 (v0.81)
            style.hook_style = str(params["hook_style"])
        if params.get("sub_style"):
            style.sub_style = str(params["sub_style"])
        if params.get("tone"):
            style.tone = str(params["tone"])
        if (params.get("sub_font") or "").strip():
            style.font = str(params["sub_font"]).strip()
        if params.get("sub_anim") in ("none", "pop", "type", "karaoke"):
            style.anim = str(params["sub_anim"])   # 🎬 감성 테마 (v0.86)
        if params.get("sub_pos") in ("center", "bottom"):
            style.position = str(params["sub_pos"])  # 🎨 자막 위치 (v0.87)
        ep_voice = {"narr_voice": (params.get("narr_voice") or "").strip(),
                    "narr_style": (params.get("narr_style") or "").strip()}
        chain, voice = _narr_tts_pref(ep_voice, settings)
        wrap = int(settings["subtitle"].get("wrap_chars", 16) or 16)
        # 🎬 풀영상 하나로 (v0.84) — 영상 1개에서 구간별 시간 범위를 잘라 쓴다
        full_video, full_us = "", 0
        if str(params.get("full_video") or "").strip():
            full_video = video_editor.resolve_input_video(str(params["full_video"]).strip())
            full_us = ff.probe_duration_us(full_video)
        # ♻ 부분 수정 (v0.85) — 이전 작업(reuse_job)과 지문이 같은 구간은 다시 만들지
        # 않고 결과를 복사. "다시 편집"에서 한 구간만 고치면 그 구간만 재제작된다.
        import hashlib as _hl  # noqa: PLC0415
        import shutil  # noqa: PLC0415
        common_fp = f"{style!r}|{layout}|{quality}|{voice}|{list(chain)}|{piece_us}"

        def _sec_fp(sec_d: dict, rng: str) -> str:
            key = json.dumps({"n": sec_d.get("narration"),
                              "v": rng or str(sec_d.get("video_path") or ""),
                              "sp": str(sec_d.get("speed") or "")},
                             ensure_ascii=False, sort_keys=True)
            return _hl.sha1((common_fp + key).encode("utf-8")).hexdigest()

        prev_meta, prev_dir = {}, None
        if str(params.get("reuse_job") or "").strip():
            prev_dir = Path(workdir) / str(params["reuse_job"]).strip()
            try:
                prev_meta = json.loads(
                    (prev_dir / "sections_meta.json").read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — 메타 없으면 전부 새로 제작
                prev_meta = {}
        fps_meta, reused = {}, 0
        n = len(secs)
        outs, out_titles, errors, notes = [], [], [], []
        for i, sec in enumerate(secs, 1):
            base = (i - 1) / n
            try:
                rng = ""
                if full_video:
                    try:
                        s_us, e_us = int(sec.get("start_us")), int(sec.get("end_us"))
                    except (TypeError, ValueError) as ve:
                        raise ValueError("풀영상에서 쓸 시간 범위가 없어요 — "
                                         "[🪄 자동으로 나누기]를 눌러주세요") from ve
                    s_us = max(0, min(s_us, full_us - 500_000))
                    e_us = max(s_us + 500_000, min(e_us, full_us))
                    rng = f"{full_video}:{s_us}-{e_us}"
                fp = _sec_fp(sec, rng)
                prev_file = (prev_dir / f"sec_{i}.mp4") if prev_dir else None
                if prev_meta.get(str(i)) == fp and prev_file and prev_file.is_file():
                    job_dir.mkdir(parents=True, exist_ok=True)
                    dst = job_dir / f"sec_{i}.mp4"
                    shutil.copy2(prev_file, dst)
                    outs.append(str(dst))
                    out_titles.append((str(sec.get("title") or "").strip() or f"구간 {i}"))
                    fps_meta[str(i)] = fp
                    reused += 1
                    _set_job(job_id, status="running", stage="render", frac=base,
                             note=f"🎞 구간 {i}/{n} — 바뀐 게 없어 이전 결과 재사용 ♻")
                    continue
                if full_video:
                    _set_job(job_id, status="running", stage="cut", frac=base,
                             note=f"🎞 구간 {i}/{n} — 풀영상 {s_us / 1e6:.0f}~{e_us / 1e6:.0f}초 잘라내는 중…")
                    video = video_editor.extract_segment(
                        full_video, s_us, e_us, str(job_dir / f"sec_{i}_src.mp4"))
                else:
                    video = video_editor.resolve_input_video(str(sec.get("video_path") or ""))
                lines = [ln.strip() for ln in str(sec["narration"]).splitlines() if ln.strip()]
                lines = split_long_sentences(  # 🛡 자막 2줄 안전장치 (v0.77 재사용)
                    Script(title="", sentences=lines), limit=max(8, wrap * 2)).sentences
                _set_job(job_id, status="running", stage="tts", frac=base,
                         note=f"🎞 구간 {i}/{n} — 목소리 만드는 중…")
                clips, _used, tnote = tts_engine.synth_with_fallback(
                    lines, list(chain), Path(workdir) / "cache" / "tts",
                    settings, voice=voice)
                if tnote and tnote not in notes:
                    notes.append(tnote)
                subs0 = edit_mode.dicts_to_subtitles(
                    [{"text": t, "start_us": 0, "end_us": 1_000} for t in lines])
                subs, clips2, _ = edit_mode.retime_narration(
                    clips, subs0, 0, job_dir, fit="freeze")  # 순차 배치 (실측 길이)
                narr_end = (subs[-1].end_us + 700_000) if subs else 1_000_000
                dur = ff.probe_duration_us(video)
                # ⏩ 구간별 배속 (v0.82) — ""=자동(몽타주) | "fit"=배속으로 길이 맞춤 | "1.5"/"2"/"3"
                sp = str(sec.get("speed") or "").strip()
                if sp:
                    if sp == "fit":
                        factor = max(1.0, min(8.0, dur / max(1, narr_end)))
                    else:
                        try:
                            factor = max(0.5, min(8.0, float(sp)))
                        except (TypeError, ValueError):
                            factor = 1.0
                    if abs(factor - 1.0) > 0.01:
                        _set_job(job_id, stage="cut", frac=base,
                                 note=f"🎞 구간 {i}/{n} — {factor:.1f}배속 적용 중…")
                        video = video_editor.speed_video(
                            video, factor, str(job_dir / f"sec_{i}_spd.mp4"))
                        dur = ff.probe_duration_us(video)
                cut = video
                if dur > narr_end + 1_000_000:      # 📹 핵심 조각 몽타주로 압축
                    _set_job(job_id, stage="cut", frac=base,
                             note=f"🎞 구간 {i}/{n} — 핵심 장면 골라 {narr_end / 1e6:.0f}초로 압축 중…")
                    ranges = edit_mode.spread_ranges(dur, narr_end, piece_us=piece_us)
                    try:                              # 장면 전환점에 스냅 (실패 무시)
                        if dur < 20 * 60 * 1_000_000:
                            scenes = video_editor.detect_scene_changes(video)
                            ranges = video_editor.shift_ranges_to_scenes(ranges, scenes, dur)
                    except Exception:  # noqa: BLE001
                        pass
                    # ✂ 몽타주 조각은 하드컷 (v0.94) — 조각마다 검은 화면을 거치는
                    # fade가 2~3초 간격 깜빡임으로 보였음 (사용자 리포트, blackdetect 확인).
                    # 장면 전환점 스냅 덕에 컷만으로도 자연스럽다.
                    cut = video_editor.cut_and_concat(
                        video, ranges, str(job_dir / f"sec_{i}_cut.mp4"), transition="none")
                elif dur < narr_end:                 # 짧으면 마지막 장면 정지로 연장
                    cut = video_editor.extend_video(
                        video, narr_end, str(job_dir / f"sec_{i}_ext.mp4"))
                cut_us = ff.probe_duration_us(cut)
                narr_wav = edit_mode.build_narration_wav(
                    clips2, subs, max(cut_us, narr_end), job_dir / f"sec_{i}_narr.wav")
                _set_job(job_id, stage="render", frac=base + 0.4 / n,
                         note=f"🎞 구간 {i}/{n} — 자막·목소리 입혀 렌더 중…")
                r = edit_mode.render_from_analysis(
                    cut, subs, str(job_dir / f"sec_{i}.mp4"), style=style, layout=layout,
                    hook="", quality=quality, narration_wav=str(narr_wav),
                    orig_audio="mute",
                    progress_cb=lambda f, b=base: _set_job(
                        job_id, frac=min(0.97, b + (0.4 + f * 0.6) / n)))
                if not r.ok:
                    raise RuntimeError("; ".join(r.errors) or "렌더 실패")
                outs.append(str(job_dir / f"sec_{i}.mp4"))
                out_titles.append((str(sec.get("title") or "").strip() or f"구간 {i}"))
                fps_meta[str(i)] = fp     # ♻ 다음 "다시 편집" 때 재사용 판별용 (v0.85)
            except Exception as se:  # noqa: BLE001 — 한 구간 실패해도 나머지는 계속
                logging.getLogger("cutdaejang").error("구간 %d 실패: %s", i, se)
                errors.append(f"구간 {i}: {str(se)[:200]}")
        if not outs:
            _set_job(job_id, status="failed", errors=errors or ["완성된 구간이 없습니다"])
            return
        try:  # ♻ 재사용 지문 저장 — 다음 "다시 편집"이 바뀐 구간만 새로 만들게
            (job_dir / "sections_meta.json").write_text(
                json.dumps(fps_meta, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        _set_job(job_id, stage="render", frac=0.97, note="🎞 구간들을 이어붙이는 중…")
        cw, ch = (1080, 1920) if layout == "shorts" else (1920, 1080)
        # 🎬 구간 전환 (v0.83 크로스페이드 → v0.85 종류 선택: 디졸브/다양하게/밀기/컷…)
        transition = str(params.get("transition") or "fade").strip() or "fade"
        sec_xfade = 0.0 if transition == "none" else 0.45
        durs = [ff.probe_duration_us(p) / 1e6 for p in outs]
        fade = video_editor.xfade_clamp(sec_xfade, durs)
        final = outs[0]
        if len(outs) > 1:
            join_clips = outs
            if fade > 0:
                # 🛡 크로스페이드가 말을 깎지 않게 (v0.94) — 겹칠 만큼을 각 구간
                # 앞뒤에 '정지 화면+무음'으로 덧대 페이드가 패딩만 소모하게 한다.
                # (기존엔 뒷구간 첫 마디가 볼륨 0에서 차오르며 끊겨 들렸음)
                join_clips = []
                for pi, p in enumerate(outs):
                    join_clips.append(video_editor.pad_video(
                        p, str(job_dir / f"sec_pad_{pi}.mp4"),
                        head_s=(fade if pi > 0 else 0.0),
                        tail_s=(fade if pi < len(outs) - 1 else 0.0)))
            final = video_editor.concat_videos(
                join_clips, str(job_dir / "sections_final.mp4"), size=(cw, ch),
                crossfade_s=fade, transition=transition)
        if (params.get("bgm") or "").strip():        # 🎵 BGM은 최종 합본에 1회 (덕킹)
            b = resolve_bgm(params["bgm"], settings)
            if b and b.path:
                _set_job(job_id, frac=0.98, note="🎵 배경음악 입히는 중…")
                try:
                    bgm_db = float(params.get("bgm_db"))
                except (TypeError, ValueError):
                    bgm_db = float(settings["bgm"].get("volume_db", -16))
                try:
                    # v0.83: 영상 재인코딩 없이 소리만 섞음 — 화질 유지·용량↓·빠름
                    final = video_editor.mix_bgm(
                        final, b.path, str(job_dir / "sections_bgm.mp4"),
                        bgm_db=bgm_db, duck=bool(settings["bgm"].get("duck", True)))
                except Exception:  # noqa: BLE001 — BGM 실패해도 본편은 산다
                    notes.append("배경음악 입히기에 실패해 없이 완성했어요")
        # ⏱ 유튜브 설명란용 타임라인 (v0.82) — 구간 실제 시작 시각 + 제목
        # v0.94: 경계마다 패딩+크로스페이드로 순길이 +fade 만큼 늘어나는 것 반영
        chap_lines, cum = [], 0.0
        for k, title_i in enumerate(out_titles):
            mm, ss = int(cum // 60), int(cum % 60)
            chap_lines.append(f"{mm:02d}:{ss:02d} {title_i}")
            cum += durs[k] + (fade if k < len(outs) - 1 else 0.0)
        total_s = ff.probe_duration_us(final) / 1e6
        msg = f"🎞 구간 {len(outs)}개 · 총 {int(total_s // 60)}분 {int(total_s % 60)}초"
        if reused:
            msg += f" · ♻ 안 바뀐 {reused}구간은 이전 결과 재사용"
        _set_job(job_id, status=("ok" if not errors else "partial"), stage="done",
                 frac=1.0, mp4=final, mp4s=[final] + (outs if len(outs) > 1 else []),
                 chapters=("\n".join(chap_lines) if len(chap_lines) > 1 else ""),
                 note="", tts_warn=" · ".join([msg] + notes + errors))
        _record_simple_history(   # 📜 재시작해도 히스토리에 남게 (v0.85)
            workdir, job_id,
            title=(_get_job(job_id) or {}).get("title") or "🎞 구간 대본 영상",
            mode="sections", status=("ok" if not errors else "partial"),
            mp4=final, params=params, duration_us=int(total_s * 1e6))
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error(
            "구간 대본 영상 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])
        _record_simple_history(
            workdir, job_id,
            title=(_get_job(job_id) or {}).get("title") or "🎞 구간 대본 영상",
            mode="sections", status="failed", mp4=None, params=params)


def _run_batch(job_id: str, items: list, params: dict, workdir: str) -> None:
    """📦 배치 (v0.42) — 주제(또는 대본 벌, v0.62) 여러 개를 순차 생성해 mp4 N개.

    항목: {"topic": str} 또는 {"script_text": str}. 한 개 실패해도 계속.
    """
    outs, errors = [], []
    total = len(items)
    try:
        _apply_keys(params)
        provider_name = params.get("script_provider", "stub")
        if provider_name == "gemini" and not os.environ.get("GEMINI_API_KEY"):
            provider_name = "stub"
        settings = _apply_bg_style(params, config.load_settings())
        opts = _job_options(params, settings)
        image_provider, _bg_skip = _ai_image_setup(params, settings)
        import re as _re  # noqa: PLC0415
        for i, item in enumerate(items):
            base = i / total
            sc_text = (item.get("script_text") or "").strip()
            if sc_text:  # 📝 대본 벌 — AI 대본 생략, 첫 줄이 제목 (v0.62)
                lines, tc_end = _parse_script_lines(sc_text)  # ⏱ 타임코드 정리 (v0.63)
                if tc_end:
                    opts = dataclasses.replace(opts, pace_sec=tc_end)
                topic = _re.sub(r"\[[가-힣A-Za-z]+\]|\[/[가-힣A-Za-z]*\]", "", lines[0])[:40]
            else:
                topic = (item.get("topic") or "").strip()
            _set_job(job_id, status="running", stage="script", frac=base,
                     note=f"📦 {i + 1}/{total}번째: {topic}")
            try:
                if sc_text:
                    from ..core.script_generator import Script  # noqa: PLC0415
                    script = Script(title=topic, sentences=lines)
                else:
                    provider = SCRIPT_PROVIDERS[provider_name]()
                    script = orchestrator.generate_script(
                        provider, topic, opts,
                        context=_product_context(params, settings))
                sub_id = orchestrator.new_job_id(topic)
                sub_dir = Path(workdir) / sub_id
                sub_dir.mkdir(parents=True, exist_ok=True)
                (sub_dir / "script.json").write_text(script.to_json(), encoding="utf-8")
                result = orchestrator.run_job(
                    workdir, script, opts=opts, settings=settings,
                    image_provider=image_provider,
                    progress_cb=lambda stage, frac, b=base: _set_job(
                        job_id, stage=stage, frac=b + frac / total),
                    status_cb=lambda msg, k=i: _set_job(
                        job_id, note=f"📦 {k + 1}/{total}번째: {msg}"),
                    job_id=sub_id,
                )
                if result.mp4 and result.mp4.ok:
                    _attach_branding(job_id, result.mp4.out_path, Path(result.job_dir))
                    outs.append(result.mp4.out_path)
                errors += [f"[{topic}] {e}" for e in result.errors]
                _record_history(workdir, result, opts)  # 개별 영상은 히스토리에서 재생
            except Exception as te:  # noqa: BLE001 — 한 주제 실패는 다음 주제로
                logging.getLogger("cutdaejang").warning("배치 항목 실패 (%s): %s", topic, te)
                errors.append(f"[{topic}] {te}")
        _set_job(
            job_id,
            status="ok" if outs and not errors else "partial" if outs else "failed",
            stage="done", frac=1.0, job_dir=workdir,
            note=f"📦 배치 완성: {len(outs)}/{total}개"
                 + (" — 일부 오류는 아래 참고" if errors and outs else ""),
            mp4=outs[0] if outs else None, mp4s=outs, errors=errors[:10],
        )
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("배치 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed",
                 errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


def _run_generate(job_id: str, params: dict, workdir: str) -> None:
    """대본 생성 → 자동 모드면 즉시 파이프라인, 검토 모드면 대기 (기획안 §1.3)."""
    try:
        _apply_keys(params)
        _set_job(job_id, status="running", stage="script", frac=0.0)
        user_script = (params.get("script_text") or "").strip()
        if user_script:  # 📝 내 대본 그대로 (v0.61) — AI 대본 생략, 비용 0
            from ..core.script_generator import Script  # noqa: PLC0415
            lines, tc_end = _parse_script_lines(user_script)  # ⏱ 타임코드 자동 정리 (v0.63)
            import re as _re  # noqa: PLC0415
            plain0 = _re.sub(r"\[[가-힣A-Za-z]+\]|\[/[가-힣A-Za-z]*\]", "", lines[0])
            script = Script(title=(params.get("topic") or "").strip() or plain0[:40],
                            sentences=lines)
            note_txt = f"내 대본 {len(lines)}줄 그대로 사용 (AI 대본 생략)"
            if tc_end:
                params = {**params, "pace_sec": tc_end}
                note_txt += f" · 타임코드 감지 → 약 {tc_end}초에 맞춤"
            elif params.get("target_sec"):
                params = {**params, "pace_sec": int(params.get("target_sec") or 0)}
            ctx = _product_context(params, config.load_settings())
            if ctx:
                _set_job(job_id, product_ctx=ctx)
            # 검토(confirm) 경로는 잡에 저장된 params로 파이프라인을 돌리므로 갱신 필수
            _set_job(job_id, note=note_txt, params=params)
            job_dir = Path(workdir) / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "script.json").write_text(script.to_json(), encoding="utf-8")
            if params.get("auto", True):
                _run_pipeline(job_id, script, params, workdir)
            else:
                _set_job(job_id, status="awaiting_review", stage="review", title=script.title,
                         script={"title": script.title, "sentences": script.sentences,
                                 "highlights": script.highlights,
                                 "background_prompt": script.background_prompt})
            return
        provider_name = params.get("script_provider", "stub")
        if provider_name == "gemini" and not os.environ.get("GEMINI_API_KEY"):
            # 키 없는 내장 음성 사용자도 실패 없이 — 템플릿 대본으로 안전 강등 (v0.40)
            provider_name = "stub"
            params = {**params, "script_provider": "stub"}
            _set_job(job_id, note="Gemini 키가 없어 템플릿 대본으로 만들어요 — 키를 넣으면 진짜 AI 대본")
        ctx = _product_context(params, config.load_settings())  # 📇 제품 정보 주입 (v0.64)
        if ctx:
            _set_job(job_id, product_ctx=ctx,
                     note=f"📇 제품 정보 반영: {(params.get('product') or '참고 메모')}")
        provider = SCRIPT_PROVIDERS[provider_name]()
        script = orchestrator.generate_script(
            provider, params["topic"], _job_options(params), context=ctx
        )
        job_dir = Path(workdir) / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "script.json").write_text(script.to_json(), encoding="utf-8")

        if params.get("auto", True):
            _run_pipeline(job_id, script, params, workdir)
        else:
            _set_job(
                job_id,
                status="awaiting_review",
                stage="review",
                title=script.title,
                script={"title": script.title, "sentences": script.sentences,
                        "highlights": script.highlights,
                        "background_prompt": script.background_prompt},
            )
    except Exception as e:
        import traceback  # noqa: PLC0415

        logging.getLogger("cutdaejang").error("작업 실패 %s\n%s", job_id, traceback.format_exc())
        _set_job(job_id, status="failed", errors=[str(e), f"[원본 오류] {traceback.format_exc()[-1500:]}"])


class _Handler(BaseHTTPRequestHandler):
    server_version = "cutdaejang-ui"

    def log_message(self, *args) -> None:  # 콘솔 소음 제거
        pass

    # ---------- 응답 헬퍼 ----------

    def _send_json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    _MAX_BODY = 16 * 1024 * 1024  # 요청 본문 상한 16MB (v0.70 — 과대 요청 방어)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > self._MAX_BODY:
            raise ValueError(f"요청 본문이 너무 큽니다 ({length} bytes > 16MB)")
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def _same_origin_ok(self) -> bool:
        """CSRF·DNS 리바인딩 방어 (v0.70): Host는 로컬호스트:포트, Origin이 있으면 일치.

        악성 웹사이트가 사용자의 127.0.0.1:포트로 POST(키 저장·삭제 등)하는 것을 차단.
        우리 화면의 fetch는 동일 출처라 Host·Origin이 자동으로 맞으므로 영향 없음.
        """
        try:
            port = self.server.server_address[1]  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return True
        host = (self.headers.get("Host") or "").strip().lower()
        ok_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if host not in ok_hosts:
            return False
        origin = (self.headers.get("Origin") or "").strip().lower()
        if origin and origin not in {f"http://{h}" for h in ok_hosts}:
            return False
        return True

    # ---------- 라우팅 ----------

    def do_GET(self) -> None:  # noqa: N802
        # 작업 id에 한글이 들어가므로 퍼센트 인코딩된 경로를 복원해야 매칭된다
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        if path == "/":
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            self._send_json(self._state())
        elif path.startswith("/video/"):
            self._serve_video(path.split("/", 2)[2])
        elif path.startswith("/localvideo/"):  # 🎬 풀영상 미리보기 (v0.84 — 등록 토큰만)
            p = _LOCAL_VIDEOS.get(path.split("/", 2)[2] or "")
            if p and Path(p).is_file():
                self._serve_file(p)
            else:
                self._send_json({"error": "등록된 영상이 없어요 — 다시 선택해 주세요"}, 404)
        elif path.startswith("/cutvideo/"):
            self._serve_cutvideo(path.split("/", 2)[2])
        elif path.startswith("/scene/"):  # 🖼 장면 검토 이미지 (v0.50): /scene/<job>/<n>
            parts = path.split("/", 3)
            job = _get_job(parts[2] if len(parts) > 2 else "")
            try:
                n = int(parts[3])
            except (IndexError, ValueError):
                n = -1
            p = (Path(self.server.workdir) / (job or {}).get("id", "") /  # type: ignore[attr-defined]
                 "scenes" / f"scene_{n + 1:02d}.png") if job and n >= 0 else None
            if p and p.is_file():
                self._serve_file(str(p))
            else:
                self._send_json({"error": "장면 이미지 없음"}, 404)
        elif path.startswith("/weblink/"):  # 🔗 가져온 글 사진 미리보기 (v0.79)
            import re as _re  # noqa: PLC0415

            m = _re.match(r"^/weblink/([0-9a-f]{8})/(img_\d{2}\.(?:jpg|jpeg|png|webp|bmp))$", path)
            p = (Path(self.server.workdir) / "weblink" / m.group(1) / m.group(2)  # type: ignore[attr-defined]
                 ) if m else None
            if p and p.is_file():
                self._serve_file(str(p))
            else:
                self._send_json({"error": "사진 없음"}, 404)
        elif path.startswith("/thumbnail/"):
            job = _get_job(path.split("/", 2)[2])
            tp = job.get("thumbnail") if job else None
            if tp and Path(tp).is_file():
                self._serve_file(tp)
            else:
                self._send_json({"error": "썸네일 없음"}, 404)
        elif path.startswith("/preview/"):
            self._serve_preview(path.split("/", 2)[2])
        elif path.startswith("/bgm/"):
            self._serve_bgm(path.split("/", 2)[2])
        elif path.startswith("/audio/"):  # 🔊 추출한 오디오 내려받기 (v0.64)
            parts = path.split("/", 3)
            job = _get_job(parts[2] if len(parts) > 2 else "")
            name = Path(parts[3]).name if len(parts) > 3 else ""
            mp4 = (job or {}).get("mp4")
            fp = (Path(mp4).parent / name) if mp4 and name.endswith(".mp3") else None
            if fp and fp.is_file():
                self._serve_file(str(fp))
            else:
                self._send_json({"error": "not found"}, 404)
        elif path.startswith("/font/"):  # 🔤 글씨체 실물 미리보기 (v0.68) — resources/fonts만
            stem = path.split("/", 2)[2]
            from ..core import render_engine as _re  # noqa: PLC0415
            from .. import presets as _pr  # noqa: PLC0415

            allowed = set(_pr.FONT_FAMILY_ALIASES.keys())  # 화이트리스트 (경로 주입 차단)
            fp = Path(_re.DEFAULT_FONTS_DIR) / (stem + ".ttf")
            if stem in allowed and fp.is_file():
                self._serve_file(str(fp))
            else:
                self._send_json({"error": "not found"}, 404)
        elif path.startswith("/sfx/"):  # 🔔 효과음 들어보기 (v0.60)
            name = path.split("/", 2)[2]
            if name not in ("pop", "whoosh", "ding"):
                self._send_json({"error": "not found"}, 404)
                return
            try:
                from ..core import sfx as sfx_mod  # noqa: PLC0415
                sp = sfx_mod.ensure_sfx().get(name)
            except Exception as e:  # noqa: BLE001 — ffmpeg 문제 등
                self._send_json({"error": f"효과음 준비 실패: {e}"}, 500)
                return
            if sp and Path(sp).is_file():
                self._serve_file(sp)
            else:
                self._send_json({"error": "not found"}, 404)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        # 🔒 동일 출처 검사 (v0.70) — 다른 웹사이트의 요청(CSRF) 차단
        if not self._same_origin_ok():
            self._send_json({"error": "허용되지 않은 출처의 요청입니다 (127.0.0.1 로컬만 허용)"}, 403)
            return
        # 전역 가드 (v0.47) — 핸들러가 예외로 죽으면 브라우저엔 'Failed to fetch'만 남는다
        # → 항상 JSON 오류로 응답하고 전체 스택은 로그에 (진단 리포트로 확인 가능)
        try:
            self._do_post_inner()
        except Exception as e:  # noqa: BLE001
            import traceback  # noqa: PLC0415

            logging.getLogger("cutdaejang").error(
                "API 처리 오류 %s\n%s", self.path, traceback.format_exc())
            msg = f"서버 내부 오류: {e} — 하단 🪵 로그 참고"
            s = str(e)
            if "429" in s and ("credit" in s.lower() or "RESOURCE_EXHAUSTED" in s
                               or "quota" in s.lower()):
                # 사용자 스크린샷: 원문 JSON이 그대로 떠서 무슨 말인지 알 수 없었음 (v0.51)
                msg = ("Gemini 한도·크레딧이 소진돼 요청이 실패했어요 — 무료 한도는 내일 "
                       "오후 4~5시쯤(한국시간) 풀리고, 유료 크레딧은 ai.studio → 결제에서 "
                       "충전할 수 있어요. ✍ 그림은 '내가 넣기' 방식이면 비용 없이 계속 가능!")
            try:
                self._send_json({"error": msg}, 500)
            except Exception:  # noqa: BLE001 — 이미 응답을 보낸 경우 등
                pass

    def _do_post_inner(self) -> None:
        path = self.path.split("?", 1)[0]
        try:
            params = self._read_json()
        except json.JSONDecodeError:
            self._send_json({"error": "잘못된 요청"}, 400)
            return

        workdir = self.server.workdir  # type: ignore[attr-defined]
        if path == "/api/generate":
            topic = (params.get("topic") or "").strip()
            has_user_script = bool((params.get("script_text") or "").strip())
            if not topic and not has_user_script:
                self._send_json({"error": "주제를 입력하세요 (대본을 직접 넣으면 주제는 생략 가능)"}, 400)
                return
            job_id = orchestrator.new_job_id(
                topic or (params.get("script_text") or "").strip().splitlines()[0][:24])
            _set_job(job_id, status="running", stage="script", frac=0.0,
                     title=topic, params=params,
                     orientation="wide" if params.get("orientation") == "wide" else "shorts")
            _queue_job(job_id, _run_generate, job_id, params, workdir)  # 📋 작업 큐 (v0.88)
            self._send_json({"job_id": job_id})
        elif path == "/api/generate_batch":
            topics = [str(t).strip() for t in (params.get("topics") or []) if str(t).strip()]
            scripts = [str(s).strip() for s in (params.get("scripts") or []) if str(s).strip()]
            if scripts:  # 📝 대본 배치 (v0.62) — 대본 여러 벌, 한 벌 = 영상 1개
                items = [{"script_text": s} for s in scripts[:20]]
                first = scripts[0].splitlines()[0][:14]
            elif topics:
                items = [{"topic": t} for t in topics[:20]]
                first = topics[0][:14]
            else:
                self._send_json({"error": "주제를 한 줄에 하나씩 입력하거나, "
                                          "대본 여러 벌을 === 로 구분해 넣으세요"}, 400)
                return
            params = {**params, "auto": True}  # 배치는 검토 없이 자동
            job_id = orchestrator.new_job_id(f"배치{len(items)}")
            _set_job(job_id, status="running", stage="script", frac=0.0,
                     title=f"📦 배치 {len(items)}개 — {first}…", params=params)
            _queue_job(job_id, _run_batch, job_id, items, params, workdir)  # 📋 작업 큐 (v0.88)
            self._send_json({"job_id": job_id, "count": len(items)})
        elif path == "/api/confirm":
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "awaiting_review":
                self._send_json({"error": "검토 대기 중인 작업이 아닙니다"}, 400)
                return
            # "문장 | 강조단어" 형식 지원 (지시서 5-1 검토 모드 강조 수정)
            sentences, highlights = [], []
            for line in params.get("sentences", []):
                line = line.strip()
                if not line:
                    continue
                text, _, hl = line.partition("|")
                sentences.append(text.strip())
                highlights.append(hl.strip())
            if not sentences:
                self._send_json({"error": "문장이 비어 있습니다"}, 400)
                return
            # 장면 프롬프트는 검토 폼에 없으니 디스크 script.json에서 복원 (v0.50)
            scene_prompts: list = []
            sj = Path(workdir) / job["id"] / "script.json"
            if sj.is_file():
                try:
                    old = Script.from_json_text(sj.read_text(encoding="utf-8"))
                    scene_prompts = old.scene_prompts
                except Exception:  # noqa: BLE001
                    pass
            script = Script(
                title=params.get("title") or job.get("title", ""),
                sentences=sentences,
                highlights=highlights,
                background_prompt=(job.get("script") or {}).get("background_prompt", ""),
                scene_prompts=scene_prompts,
            )
            settings = _apply_bg_style(job.get("params", {}), config.load_settings())
            provider, _skip = _ai_image_setup(job.get("params", {}), settings)
            # 🖼 장면 검토 (v0.50) — 키·설정이 되면 그림을 먼저 보여주고 확정받는다.
            # v0.51: ✍ 내가 넣기(manual)는 키 없이도 검토로 — 프롬프트만 뽑아 직접 삽입.
            scene_mode = settings["bg"].get("scene_mode", "auto")
            if (settings["bg"].get("scene_images", True) and scene_mode != "off"
                    and len(script.sentences) > 1
                    and (scene_mode == "manual" or provider is not None)):
                _set_job(job["id"], status="running", stage="background", frac=0.0,
                         note="장면 그림을 준비하는 중…")
                threading.Thread(
                    target=_prepare_scenes,
                    args=(job["id"], script, job.get("params", {}), workdir),
                    daemon=True,
                ).start()
            else:
                _queue_job(job["id"], _run_pipeline,
                           job["id"], script, job.get("params", {}), workdir)  # 📋 v0.88
            self._send_json({"ok": True})
        elif path == "/api/edit":
            video = (params.get("video_path") or "").strip().strip('"')
            if not video and not (params.get("photo_path") or "").strip():
                self._send_json({"error": "영상 파일(또는 사진 폴더) 경로를 입력하세요"}, 400)
                return
            if not video:
                video = "사진영상"  # 사진 모드 — 제목용
            try:  # 이 폼 세팅을 기억 → 다음 실행 때 그대로 복원 (영상만 바꿔 반복하는 자동화)
                config.save_settings({"ui": {"edit_last": {
                    k: params[k] for k in _EDIT_LAST_KEYS if k in params}}})
            except Exception:
                pass  # 세팅 기억 실패는 작업에 영향 없음
            job_id = orchestrator.new_job_id(Path(video).stem or "edit")
            _set_job(job_id, status="running", stage="analyze", frac=0.0,
                     title=Path(video).stem, params=params)
            _queue_job(job_id, _run_edit, job_id, params, workdir)  # 📋 작업 큐 (v0.88)
            self._send_json({"job_id": job_id})
        elif path == "/api/edit_render":
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_subtitle":
                self._send_json({"error": "자막 검토 중인 작업이 아닙니다"}, 400)
                return
            ep = job.get("edit_params") or {}
            if params.get("hook_scale") is not None:
                ep["hook_scale"] = params.get("hook_scale")
                _set_job(job["id"], edit_params=ep)
            if params.get("hook_style"):  # 🪧 상단 제목 스타일 프리셋 (v0.52)
                ep["hook_style"] = params.get("hook_style")
                _set_job(job["id"], edit_params=ep)
            if params.get("sub_style"):  # 💬 자막 프리셋 (v0.54)
                ep["sub_style"] = params.get("sub_style")
                _set_job(job["id"], edit_params=ep)
            if params.get("tone"):  # 🎨 화면 톤 (v0.56)
                ep["tone"] = params.get("tone")
                _set_job(job["id"], edit_params=ep)
            if params.get("sub_anim"):  # 🎬 감성 테마 자막 등장 (v0.87)
                ep["sub_anim"] = params.get("sub_anim")
                _set_job(job["id"], edit_params=ep)
            if params.get("sub_pos"):   # 🎨 자막 위치 — 릴스 가운데 (v0.87)
                ep["sub_pos"] = params.get("sub_pos")
                _set_job(job["id"], edit_params=ep)
            if params.get("margin_v"):  # ↕ 검토 화면에서 드래그한 자막 위치 (v0.49)
                ep["margin_v"] = params.get("margin_v")
                _set_job(job["id"], edit_params=ep)
            hook = params.get("hook", ep.get("hook", ""))
            keep = params.get("keep")  # 고른 구간(번호). None이면 전체 유지
            if keep is not None:
                keep = [int(i) for i in keep]
            try:
                speed = float(params.get("speed") or 1.0)
            except (TypeError, ValueError):
                speed = 1.0
            quality = params.get("quality") or "standard"
            # 잡음 제거는 편집 폼에서 정한 값(edit_params)을 따름
            denoise = ep.get("denoise") or False
            try:  # ✂️ 앞뒤 트림 (v0.41 브루식 편집)
                trim = (int(params.get("trim_start_us") or 0),
                        int(params.get("trim_end_us") or 0))
            except (TypeError, ValueError):
                trim = (0, 0)
            _queue_job(job["id"], _do_edit_render,
                       job["id"], params.get("subtitles") or [], hook,
                       ep.get("layout", "shorts"), job.get("cut_video"), workdir,
                       keep, speed, quality, denoise, trim)  # 📋 작업 큐 (v0.88)
            self._send_json({"ok": True})
        elif path == "/api/refine_subtitles":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            texts = [str((s or {}).get("text", "")) for s in (params.get("subtitles") or [])]
            if not any(t.strip() for t in texts):
                self._send_json({"error": "다듬을 자막이 없습니다"}, 400)
                return
            try:
                lines = sg.refine_subtitles(texts, context=params.get("context", ""))
                self._send_json({"lines": lines})
            except sg.ScriptError as e:
                self._send_json({"error": str(e)}, 400)
            except Exception as e:
                self._send_json({"error": f"대본 다듬기 실패: {e}"}, 500)
        elif path == "/api/suggest_highlights":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            subs = params.get("subtitles") or []
            target = int(params.get("target_sec") or 30)
            if not subs:
                self._send_json({"error": "자막이 없습니다"}, 400)
                return
            try:
                res = sg.suggest_highlights(subs, target_sec=target)
                res["ai"] = True
            except sg.ScriptError:
                res = sg.suggest_highlights_heuristic(subs, target_sec=target)  # 키 없으면 대략치
                res["ai"] = False
            except Exception as e:  # 파싱 등 실패해도 대역으로
                res = sg.suggest_highlights_heuristic(subs, target_sec=target)
                res["ai"] = False
                res["reason"] = res.get("reason", "") + f" (AI 실패: {e})"
            self._send_json(res)
        elif path == "/api/edit_split":
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_subtitle":
                self._send_json({"error": "자막 검토 중인 작업이 아닙니다"}, 400)
                return
            ep = job.get("edit_params") or {}
            if params.get("margin_v"):  # ↕ 드래그한 자막 위치는 분할 쇼츠에도 동일 적용
                ep["margin_v"] = params.get("margin_v")
                _set_job(job["id"], edit_params=ep)
            try:
                target = float(params.get("target_sec") or 30)
                speed = float(params.get("speed") or 1.0)
            except (TypeError, ValueError):
                target, speed = 30.0, 1.0
            try:
                trim = (int(params.get("trim_start_us") or 0),
                        int(params.get("trim_end_us") or 0))
            except (TypeError, ValueError):
                trim = (0, 0)
            _queue_job(job["id"], _do_edit_split,
                       job["id"], params.get("subtitles") or [],
                       params.get("hook", ep.get("hook", "")),
                       ep.get("layout", "shorts"), job.get("cut_video"), workdir,
                       target, speed, params.get("quality") or "standard",
                       ep.get("denoise") or False, trim)  # 📋 작업 큐 (v0.88)
            self._send_json({"ok": True})
        elif path == "/api/suggest_thumbnail":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            ctx = (params.get("context") or "").strip()
            if not ctx:
                self._send_json({"error": "주제/대본을 먼저 넣어주세요"}, 400)
                return
            try:
                copies = sg.suggest_thumbnail_copy(ctx)
                ai = True
            except sg.ScriptError:
                copies = sg.suggest_thumbnail_copy_stub(ctx)  # 키 없으면 템플릿
                ai = False
            self._send_json({"copies": copies, "ai": ai})
        elif path == "/api/thumbnail":
            from ..core import thumbnail as thumb  # noqa: PLC0415
            from ..core.orchestrator import build_style  # noqa: PLC0415

            job = _get_job(params.get("job_id", ""))
            bg = (params.get("bg_path") or "").strip() or (job.get("mp4") if job else None)
            if not bg or not Path(bg).is_file():
                self._send_json({"error": "배경으로 쓸 완성 영상(또는 사진)이 없습니다"}, 400)
                return
            title = (params.get("title") or "").strip()
            if not title:
                self._send_json({"error": "썸네일 제목을 입력하세요"}, 400)
                return
            out_dir = Path(job["job_dir"]) if job and job.get("job_dir") else Path(bg).parent
            out = str(out_dir / "thumbnail.png")
            preset = (params.get("preset") or "깔끔").strip()
            if params.get("ai_bg") and os.environ.get("GEMINI_API_KEY"):
                # 🖼 AI 배경 연출 (v0.48) — 집중선·스포트라이트 판. 실패하면 영상 프레임으로
                try:
                    from ..spec import Canvas  # noqa: PLC0415
                    prov = background_generator.GeminiImage(
                        model=config.load_settings()["bg"].get("image_model"))
                    bg = prov.generate(
                        (f"유튜브 썸네일 배경: {title}. 만화 집중선이나 스포트라이트처럼 "
                         "시선을 확 모으는 임팩트 연출, 중앙에 큰 글자를 올릴 여백, "
                         "채도 높고 대비 강하게. 글자·문자·로고는 절대 넣지 말 것"),
                        str(out_dir / "thumb_ai_bg.png"), Canvas(w=1280, h=720))
                except Exception as be:  # noqa: BLE001
                    logging.getLogger("cutdaejang").warning(
                        "썸네일 AI 배경 실패 → 영상 프레임 사용: %s", be)
            try:
                pos_x = float(params.get("pos_x") or 0.5)
                pos_y = float(params.get("pos_y") or 0.46)
            except (TypeError, ValueError):
                pos_x, pos_y = 0.5, 0.46
            try:
                thumb.make_thumbnail(
                    bg, title, out, highlight=params.get("highlight", ""),
                    badge=(params.get("badge") or "").strip(),
                    style=build_style(config.load_settings()),
                    preset=preset, pos_x=pos_x, pos_y=pos_y,
                )
                if job:
                    _set_job(job["id"], thumbnail=out)
                    self._send_json({"ok": True, "url": f"/thumbnail/{job['id']}", "path": out})
                else:
                    self._send_json({"ok": True, "path": out})
            except Exception as e:
                import logging  # noqa: PLC0415
                import traceback  # noqa: PLC0415
                logging.getLogger("cutdaejang").error("썸네일 실패\n%s", traceback.format_exc())
                self._send_json({"error": f"썸네일 생성 실패: {e}"}, 500)
        elif path == "/api/pick_file":
            kind = str(params.get("kind") or "video")
            try:
                # video는 기존 함수 경유 (테스트·기존 몽키패치 호환)
                picked = pick_video_file() if kind == "video" else pick_path(kind)
                self._send_json({"path": picked or "", "cancelled": picked is None})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/api/preview":
            self._preview(params)
        elif path == "/api/win_voices":
            # 🔊 이 PC의 Windows 내장 음성 목록 (v0.59) — Windows 아니면 빈 목록
            self._send_json({"voices": tts_engine.list_windows_voices(),
                             "win": sys.platform == "win32"})
        elif path == "/api/suggest_hooks":
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415

            ctx = (params.get("context") or "").strip()
            if not ctx:
                self._send_json({"error": "주제/내용을 먼저 입력하세요"}, 400)
                return
            pctx = _product_context(params, config.load_settings())
            if pctx:  # 📇 제품 차별점 기반 후킹 (v0.64)
                ctx = f"{ctx}\n{pctx}"
            try:
                hooks = sg.suggest_hooks(ctx)
            except sg.ScriptError:
                hooks = sg.suggest_hooks_stub(ctx)  # 키 없으면 템플릿
            self._send_json({"hooks": hooks})
        elif path == "/api/analyze_ai":
            # 🧠 영상 AI 분석 — 장면 캡처+자막을 Gemini에 보내 제목·훅·대본 추천
            _apply_keys(params)
            from ..core import edit_mode, script_generator as sg  # noqa: PLC0415
            job = _get_job(params.get("job_id", ""))
            video = (job or {}).get("cut_video")
            if not video or not Path(video).is_file():
                self._send_json({"error": "분석할 영상이 없습니다 — 먼저 편집을 시작하세요"}, 400)
                return
            transcript = "\n".join(
                (s.get("text") or "") for s in (job.get("subtitles") or []))[:4000]
            try:
                frames = edit_mode.extract_frames_b64(video, n=4)
                if os.environ.get("GEMINI_API_KEY"):
                    out = sg.suggest_from_video(frames, transcript)
                    out["stub"] = False
                else:
                    out = sg.suggest_from_video_stub(frames, transcript)
                    out["stub"] = True
                self._send_json(out)
            except sg.ScriptError as e:
                self._send_json({"error": str(e)}, 400)
        elif path == "/api/sovits_save":
            # GPT-SoVITS 무료 내 목소리 — 참조 녹음/대사/서버 주소 저장
            ref = (params.get("ref_audio") or "").strip().strip('"')
            txt = (params.get("ref_text") or "").strip()
            url = (params.get("url") or "").strip()
            if not ref or not Path(ref).is_file():
                self._send_json({"error": f"참조 녹음 파일을 찾을 수 없습니다: {ref or '(비어 있음)'}"}, 400)
                return
            if not txt:
                self._send_json({"error": "참조 녹음에서 말한 문장을 입력하세요 (정확할수록 품질↑)"}, 400)
                return
            merged = {"tts": {"sovits_ref_audio": ref, "sovits_ref_text": txt}}
            if url:
                merged["tts"]["sovits_url"] = url
            config.save_settings(merged)
            self._send_json({"ok": True})
        elif path == "/api/clone_voice":
            # 내 목소리 등록 (ElevenLabs 인스턴트 클론) → voice_id를 설정에 저장
            _apply_keys(params)
            fname = (params.get("file_path") or "").strip().strip('"')
            vname = (params.get("name") or "내 목소리").strip() or "내 목소리"
            try:
                vid = tts_engine.clone_voice(vname, fname)
                config.save_settings({"tts": {"voice_elevenlabs": vid,
                                              "voice_elevenlabs_name": vname}})
                self._send_json({"ok": True, "voice_id": vid, "name": vname})
            except tts_engine.TTSError as e:
                self._send_json({"error": str(e)}, 400)
        elif path == "/api/upload_kit":
            self._upload_kit(params, workdir)
        elif path == "/api/pronounce":
            from ..utils.pronounce import pronounce_ko  # noqa: PLC0415

            self._send_json({"lines": [pronounce_ko(l) for l in params.get("lines", [])]})
        elif path == "/api/eleven_voices":  # 🎙 일레븐랩스 계정 보이스 목록 (v0.46)
            self._eleven_voices(params)
        elif path == "/api/eleven_browse":  # 🇰🇷 라이브러리 한국어 성우 찾아보기 (v0.65)
            try:
                rows = tts_engine.list_shared_voices(
                    language=str(params.get("language") or "ko")[:8])
                self._send_json({"voices": rows})
            except Exception as e:
                self._send_json({"voices": [], "error": str(e)[:300]})
        elif path == "/api/eleven_fav":  # ⭐ 성우 즐겨찾기 저장/해제 (v0.67)
            vid = str(params.get("voice_id") or "").strip()[:80]
            if not vid:
                self._send_json({"error": "voice_id가 없습니다"}, 400)
                return
            favs = [str(x) for x in (config.load_settings()["tts"].get("eleven_favs") or [])]
            favs = [x for x in favs if x != vid]
            if params.get("on"):
                favs.append(vid)
            try:
                config.save_settings_replace("tts.eleven_favs", favs[-30:])
                self._send_json({"ok": True, "favs": favs[-30:]})
            except OSError as e:
                self._send_json({"error": f"저장 실패: {e}"}, 500)
        elif path == "/api/eleven_add":  # 🇰🇷 성우 내 계정에 담기 (v0.65)
            try:
                vid = tts_engine.add_shared_voice(
                    str(params.get("owner_id") or ""), str(params.get("voice_id") or ""),
                    str(params.get("name") or ""))
                type(self.server)._eleven_cache = None   # 담았으니 계정 목록 캐시 갱신
                self._send_json({"ok": True, "voice_id": vid})
            except Exception as e:
                self._send_json({"error": str(e)[:300]}, 400)
        elif path == "/api/scene_regen":  # 🖼 장면 검토 — 한 장면만 다시 (v0.50)
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_scenes":
                self._send_json({"error": "장면 검토 중인 작업이 아닙니다"}, 400)
                return
            scenes = job.get("scenes") or []
            try:
                idx = int(params.get("index"))
            except (TypeError, ValueError):
                self._send_json({"error": "장면 번호가 잘못됐습니다"}, 400)
                return
            # v0.51: 장수 제한 시 scenes는 문장 일부 — 문장 인덱스(i)로 찾는다
            scene = next((s for s in scenes if s.get("i") == idx), None)
            if scene is None:
                self._send_json({"error": "장면 번호가 잘못됐습니다"}, 400)
                return
            settings = config.load_settings()
            provider, _skip = _ai_image_setup(job.get("params", {}), settings)
            if provider is None:
                self._send_json({"error": "Gemini 키가 없어 다시 그릴 수 없습니다"}, 400)
                return
            from .. import presets  # noqa: PLC0415

            prompt = (params.get("prompt") or scene.get("prompt") or "").strip()
            scenes_dir = Path(workdir) / job["id"] / "scenes"
            ref = None
            if settings["bg"].get("character", "").strip():  # 캐릭터 일관성 참조
                for s2 in scenes:
                    if s2.get("ok") and s2["i"] != idx:
                        cand = scenes_dir / f"scene_{s2['i'] + 1:02d}.png"
                        if cand.is_file():
                            ref = str(cand)
                            break
            try:
                full = background_generator.scene_prompt_text(
                    prompt, settings["bg"].get("image_style", "일러스트"),
                    settings["bg"].get("character", ""))
                background_generator_path = provider.generate(
                    full, str(scenes_dir / f"scene_{idx + 1:02d}.png"),
                    _job_canvas(job), ref_png=ref)
                scene["prompt"], scene["ok"] = prompt, bool(background_generator_path)
                _set_job(job["id"], scenes=scenes)
                self._send_json({"ok": True})
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"다시 그리기 실패: {str(e)[:200]}"}, 500)
        elif path == "/api/scene_upload":  # ✍ 내 그림으로 장면 교체 (v0.51 — 파일 1장)
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_scenes":
                self._send_json({"error": "장면 검토 중인 작업이 아닙니다"}, 400)
                return
            src = (params.get("path") or "").strip().strip('"')
            try:
                idx = int(params.get("index"))
            except (TypeError, ValueError):
                self._send_json({"error": "장면 번호가 잘못됐습니다"}, 400)
                return
            scenes = job.get("scenes") or []
            scene = next((s for s in scenes if s.get("i") == idx), None)
            if scene is None:
                self._send_json({"error": "장면 번호가 잘못됐습니다"}, 400)
                return
            if not src or not Path(src).is_file():
                self._send_json({"error": f"그림 파일을 찾을 수 없습니다: {src or '(비어 있음)'}"}, 400)
                return
            if Path(src).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                self._send_json({"error": "그림 파일(png/jpg/webp/bmp)만 넣을 수 있어요"}, 400)
                return
            from .. import presets  # noqa: PLC0415

            dest = Path(workdir) / job["id"] / "scenes" / f"scene_{idx + 1:02d}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:  # 어떤 크기·비율이 와도 작업 캔버스에 맞게 정규화 (한쪽 채우고 넘침은 잘라냄)
                background_generator.normalize_to_canvas(src, str(dest), _job_canvas(job))
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"그림 넣기 실패: {str(e)[:200]}"}, 500)
                return
            scene["ok"] = True
            _set_job(job["id"], scenes=scenes)
            self._send_json({"ok": True})
        elif path == "/api/scene_folder":  # ✍ 폴더의 그림을 순서대로 한꺼번에 (v0.51)
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_scenes":
                self._send_json({"error": "장면 검토 중인 작업이 아닙니다"}, 400)
                return
            folder = (params.get("folder") or "").strip().strip('"')
            if not folder or not Path(folder).is_dir():
                self._send_json({"error": f"폴더를 찾을 수 없습니다: {folder or '(비어 있음)'}"}, 400)
                return
            files = sorted(
                (p for p in Path(folder).iterdir()
                 if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")),
                key=lambda p: p.name)
            if not files:
                self._send_json({"error": "폴더에 그림 파일(png/jpg/webp/bmp)이 없습니다"}, 400)
                return
            from .. import presets  # noqa: PLC0415

            scenes = job.get("scenes") or []
            scenes_dir = Path(workdir) / job["id"] / "scenes"
            scenes_dir.mkdir(parents=True, exist_ok=True)
            applied, errors = 0, []
            for scene, f in zip(scenes, files):  # 이름순 k번째 그림 → k번째 장면
                dest = scenes_dir / f"scene_{int(scene['i']) + 1:02d}.png"
                try:
                    background_generator.normalize_to_canvas(str(f), str(dest),
                                                             _job_canvas(job))
                    scene["ok"] = True
                    applied += 1
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{f.name}: {str(e)[:80]}")
            _set_job(job["id"], scenes=scenes)
            self._send_json({"ok": True, "applied": applied, "total": len(scenes),
                             "files": len(files), "errors": errors[:3]})
        elif path == "/api/confirm_scenes":  # 🖼 장면 검토 확정 → 렌더 (v0.50)
            job = _get_job(params.get("job_id", ""))
            if not job or job.get("status") != "review_scenes":
                self._send_json({"error": "장면 검토 중인 작업이 아닙니다"}, 400)
                return
            sj = Path(workdir) / job["id"] / "script.json"
            try:
                script = Script.from_json_text(sj.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                self._send_json({"error": "대본 파일을 읽을 수 없습니다"}, 500)
                return
            scenes_dir = Path(workdir) / job["id"] / "scenes"
            # 장수 제한(v0.51) 시 scenes는 문장 일부만 — 문장 인덱스(i)로 매핑하고
            # 빈 곳은 렌더에서 직전 그림으로 채워진다 (fill_scene_gaps)
            imgs = [None] * len(script.sentences)
            for s in (job.get("scenes") or []):
                idx = int(s.get("i", -1))
                p = scenes_dir / f"scene_{idx + 1:02d}.png"
                if 0 <= idx < len(imgs) and p.is_file():
                    imgs[idx] = str(p)
            _queue_job(job["id"], _run_pipeline,
                       job["id"], script, job.get("params", {}), workdir, imgs)  # 📋 v0.88
            self._send_json({"ok": True})
        elif path == "/api/settings":
            try:
                saved_to = config.save_settings(params.get("settings") or {})
                self._send_json({"ok": True, "path": saved_to})
            except OSError as e:
                self._send_json({"error": f"설정 저장 실패: {e}"}, 500)
        elif path == "/api/fetch_bgm":  # 🎵 무료 BGM 화면에서 받기 (v0.50.1)
            with _LOCK:
                if _BGM_TASK["running"]:
                    self._send_json({"ok": True, "already": True})
                    return
                _BGM_TASK.update(running=True, msg="무료 BGM 받기 시작…")
            threading.Thread(target=_fetch_bgm_bg, daemon=True).start()
            self._send_json({"ok": True})
        elif path == "/api/fetch_url":  # 🔗 블로그 글 가져오기 (v0.78) / 🛍 붙여넣기 (v0.86)
            _apply_keys(params)  # 제미나이 키 → AI 대본 요약에 사용
            url = (params.get("url") or "").strip()
            pasted = str(params.get("pasted_text") or "").strip()
            if not pasted and not url.startswith(("http://", "https://")):
                self._send_json({"error": "글 주소가 올바르지 않아요 — http로 시작하는 주소를 붙여넣어 주세요"}, 400)
                return
            if pasted and len(pasted) < 30:
                self._send_json({"error": "붙여넣은 내용이 너무 짧아요 — 상품 상세설명을 통째로 복사해 넣어주세요"}, 400)
                return
            try:
                target_sec = max(15, min(180, int(params.get("target_sec") or 45)))
            except (TypeError, ValueError):
                target_sec = 45
            with _LOCK:
                if _WEBLINK_TASK["running"]:
                    self._send_json({"ok": True, "already": True})
                    return
                _WEBLINK_TASK.update(running=True, msg="글 여는 중…", result=None, error="")
            threading.Thread(target=_fetch_weblink_bg,
                             args=(url, self.server.workdir, target_sec, pasted),
                             daemon=True).start()
            self._send_json({"ok": True})
        elif path == "/api/section_split":  # 🎞 대본 통째 → 구간 나누기 (v0.80)
            _apply_keys(params)
            from ..core import script_generator as sg  # noqa: PLC0415
            text = (params.get("script_text") or "").strip()
            if not text:
                self._send_json({"error": "대본을 먼저 붙여넣어 주세요"}, 400)
                return
            secs = []
            if os.environ.get("GEMINI_API_KEY"):
                try:
                    secs = sg.split_script_sections_ai(text)
                except Exception as e:  # noqa: BLE001 — AI 실패 → 휴리스틱
                    logging.getLogger("cutdaejang").warning("AI 구간 나누기 실패: %s", e)
            if not secs:
                secs = sg.split_script_sections(text)
            if not secs:
                self._send_json({"error": "대본에서 구간을 찾지 못했어요 — 문단(빈 줄)로 나눠 붙여넣어 보세요"}, 400)
                return
            self._send_json({"ok": True, "sections": secs})
        elif path == "/api/section_edit":  # 🎞 구간 대본 영상 (v0.80)
            secs = [s for s in (params.get("sections") or [])
                    if str((s or {}).get("narration") or "").strip()]
            if not secs:
                self._send_json({"error": "구간이 없습니다 — [➕ 구간 추가]로 구간을 만들어 주세요"}, 400)
                return
            full_mode = bool(str(params.get("full_video") or "").strip())  # 🎬 v0.84
            for si, s in enumerate(secs, 1):
                if full_mode:
                    try:
                        ok_rng = int(s.get("start_us")) < int(s.get("end_us"))
                    except (TypeError, ValueError):
                        ok_rng = False
                    if not ok_rng:
                        self._send_json({"error": f"구간 {si}의 시간 범위를 정해주세요 — "
                                         "[🪄 자동으로 나누기] 또는 [▶ 여기부터]/[⏹ 여기까지]"}, 400)
                        return
                elif not str(s.get("video_path") or "").strip():
                    self._send_json({"error": f"구간 {si}의 클립(영상)을 골라주세요"}, 400)
                    return
            _apply_keys(params)
            title = (str(secs[0].get("title") or "").strip() or "구간대본영상")[:24]
            job_id = orchestrator.new_job_id(title)
            _set_job(job_id, status="running", stage="tts", frac=0.0,
                     title=f"🎞 {title}", params=params)
            _queue_job(job_id, _run_sections, job_id, params, workdir)  # 📋 작업 큐 (v0.88)
            self._send_json({"job_id": job_id})
        elif path == "/api/job_params":  # ✏ 다시 편집 — 저장된 입력값 회수 (v0.85)
            from ..db.jobs import JobStore  # noqa: PLC0415
            try:
                store = JobStore(Path(workdir) / "history.db")
                row = store.get(str(params.get("job_id") or ""))
                store.close()
            except Exception:  # noqa: BLE001
                row = None
            pj = (row or {}).get("params_json")
            if not pj:
                self._send_json({"error": "이 작업은 다시 편집할 입력값이 저장돼 있지 않아요 "
                                 "(이 업데이트 이후에 만든 작업부터 가능해요)"}, 404)
                return
            try:
                self._send_json({"ok": True, "mode": (row or {}).get("mode") or "",
                                 "params": json.loads(pj)})
            except json.JSONDecodeError:
                self._send_json({"error": "저장된 입력값이 손상됐어요"}, 500)
        elif path == "/api/sec_draft":  # 💾 구간 작성 임시 저장 (v0.85)
            if params.get("clear"):
                config.save_settings({"ui": {"sec_draft": None}})
                self._send_json({"ok": True, "cleared": True})
            else:
                draft = params.get("draft")
                if not isinstance(draft, dict):
                    self._send_json({"error": "저장할 내용이 없어요"}, 400)
                    return
                config.save_settings({"ui": {"sec_draft": draft}})
                self._send_json({"ok": True})
        elif path == "/api/naver_keys":  # 🟢 네이버 검색 API 키 저장·확인 (v0.89)
            cid = str(params.get("client_id") or "").strip()
            csec = str(params.get("client_secret") or "").strip()
            if cid and csec:
                config.save_api_key("naver_client_id", cid)
                config.save_api_key("naver_client_secret", csec)
                os.environ["NAVER_CLIENT_ID"] = cid
                os.environ["NAVER_CLIENT_SECRET"] = csec
            self._send_json({"ok": True,
                             "has": bool(os.environ.get("NAVER_CLIENT_ID")
                                         and os.environ.get("NAVER_CLIENT_SECRET"))})
        elif path == "/api/naver_search":  # 🟢 네이버 쇼핑 상품 검색 (v0.89)
            from ..tools import naver_shop_api  # noqa: PLC0415
            try:
                items = naver_shop_api.search_shop(
                    str(params.get("keyword") or ""),
                    os.environ.get("NAVER_CLIENT_ID", ""),
                    os.environ.get("NAVER_CLIENT_SECRET", ""))
                self._send_json({"ok": True, "items": items})
            except naver_shop_api.NaverShopError as e:
                self._send_json({"error": str(e)}, 400)
        elif path == "/api/coupang_keys":  # 🛒 파트너스 API 키 저장·확인 (v0.88)
            ak = str(params.get("access") or "").strip()
            sk = str(params.get("secret") or "").strip()
            if ak and sk:
                config.save_api_key("coupang_access", ak)
                config.save_api_key("coupang_secret", sk)
                os.environ["COUPANG_ACCESS_KEY"] = ak
                os.environ["COUPANG_SECRET_KEY"] = sk
            self._send_json({"ok": True,
                             "has": bool(os.environ.get("COUPANG_ACCESS_KEY")
                                         and os.environ.get("COUPANG_SECRET_KEY"))})
        elif path == "/api/coupang_search":  # 🛒 파트너스 상품 검색 (v0.88)
            from ..tools import coupang_api  # noqa: PLC0415
            try:
                items = coupang_api.search_products(
                    str(params.get("keyword") or ""),
                    os.environ.get("COUPANG_ACCESS_KEY", ""),
                    os.environ.get("COUPANG_SECRET_KEY", ""))
                self._send_json({"ok": True, "items": items})
            except coupang_api.CoupangError as e:
                self._send_json({"error": str(e)}, 400)
        elif path == "/api/coupang_pick":  # 🛒 고른 상품 → 사진 내려받기 + 딥링크 (v0.88)
            from ..tools import coupang_api, fetch_web  # noqa: PLC0415
            import hashlib as _hl  # noqa: PLC0415
            import logging as _lg  # noqa: PLC0415 — 핸들러 안 지역 import logging과 충돌 방지 (v0.90)
            name = str(params.get("name") or "").strip()
            image = str(params.get("image") or "").strip()
            url = str(params.get("url") or "").strip()
            if not name:
                self._send_json({"error": "상품을 먼저 골라주세요"}, 400)
                return
            imgs, previews = [], []
            if image.startswith("http"):
                from ..tools import naver_shop_api  # noqa: PLC0415
                token = _hl.sha1((url or name).encode("utf-8")).hexdigest()[:8]
                dest = Path(workdir) / "weblink" / token
                dest.mkdir(parents=True, exist_ok=True)
                # 🔍 고화질 우선 (v0.90) — 492px 썸네일은 영상 배경에서 흐릿함
                # 실제로 주소가 바뀐 고화질 후보만 앞에, 원본은 폴백으로 마지막 (v0.91)
                cands = [c for c in (coupang_api.hi_res_image(image),
                                     naver_shop_api.hi_res_image(image))
                         if c and c != image] + [image]
                seen = set()
                for cand in cands:
                    if not cand or cand in seen:
                        continue
                    seen.add(cand)
                    try:
                        raw = fetch_web.fetch_bytes(cand)
                        ext = fetch_web.sniff_image_ext(raw) or "jpg"
                        p = dest / f"img_01.{ext}"
                        p.write_bytes(raw)
                        imgs = [str(p)]
                        previews = [f"/weblink/{token}/{p.name}"]
                        break
                    except Exception as ie:  # noqa: BLE001 — 다음 후보로
                        _lg.getLogger("cutdaejang").warning(
                            "상품 사진 내려받기 실패(%s): %s", cand[:60], ie)
            short = ""
            try:
                if url and "coupang" in url:  # 🟢 네이버 상품은 딥링크 대상 아님 (v0.89)
                    links = coupang_api.deeplink(
                        [url], os.environ.get("COUPANG_ACCESS_KEY", ""),
                        os.environ.get("COUPANG_SECRET_KEY", ""))
                    short = (links[0].get("short") or "") if links else ""
            except coupang_api.CoupangError:
                short = ""                    # 딥링크 실패해도 원 링크로 진행
            price = int(params.get("price") or 0)
            text = name + ("\n가격: 약 " + format(price, ",") + "원" if price else "")
            if params.get("rocket"):
                text += " · 로켓배송"
            if params.get("mall"):
                text += "\n판매처: " + str(params["mall"]).strip()
            if str(params.get("category") or "").strip():
                text += "\n분류: " + str(params["category"]).strip()
            self._send_json({"ok": True, "paste_text": text, "images": imgs,
                             "previews": previews, "link": short or url})
        elif path == "/api/shop_images":  # 📷 복사한 페이지 조각의 사진 URL들 내려받기 (v0.91)
            # 상품 페이지는 서버가 못 열어도, 사용자가 브라우저에서 복사한 조각 속
            # 이미지 주소(공개 CDN)는 그대로 받아진다 — 붙여넣기 한 번에 여러 장.
            from ..tools import product_page  # noqa: PLC0415
            import hashlib as _hl  # noqa: PLC0415
            raw_urls = [str(u).strip() for u in (params.get("urls") or [])
                        if str(u or "").strip().startswith("http")]
            uniq = list(dict.fromkeys(raw_urls))[:12]      # 순서 유지 중복 제거, 최대 12장
            if not uniq:
                self._send_json({"error": "사진 주소를 찾지 못했어요 — 상품 페이지에서 사진이 있는 부분을 드래그해 복사한 뒤 붙여넣어 주세요"}, 400)
                return
            token = _hl.sha1(("shopimgs:" + uniq[0]).encode("utf-8")).hexdigest()[:8]
            dest = Path(workdir) / "weblink" / token
            imgs, skipped = product_page.download_images(uniq, dest)  # v0.92 공용화
            previews = [f"/weblink/{token}/{Path(p).name}" for p in imgs]
            self._send_json({"ok": True, "images": imgs, "previews": previews,
                             "skipped": skipped})
        elif path == "/api/shop_upload":  # 📸 스크린샷 클립보드 붙여넣기 저장 (v0.91)
            from ..tools import fetch_web  # noqa: PLC0415
            import base64 as _b64  # noqa: PLC0415
            import hashlib as _hl  # noqa: PLC0415
            data = str(params.get("data") or "")
            if "," in data and data.startswith("data:"):
                data = data.split(",", 1)[1]   # dataURL 접두어 제거
            try:
                raw = _b64.b64decode(data or "", validate=False)
            except Exception:  # noqa: BLE001
                raw = b""
            if not raw or len(raw) > 15_000_000:
                self._send_json({"error": "이미지를 읽지 못했어요 — 스크린샷을 복사한 뒤 다시 붙여넣어 주세요"}, 400)
                return
            ext = fetch_web.sniff_image_ext(raw) or ""
            if ext not in ("jpg", "jpeg", "png", "webp", "bmp"):
                self._send_json({"error": "지원하지 않는 이미지 형식이에요 (jpg·png·webp·bmp)"}, 400)
                return
            token = _hl.sha1(b"shoppaste:" + raw[:256] + str(len(raw)).encode()).hexdigest()[:8]
            dest = Path(workdir) / "weblink" / token
            dest.mkdir(parents=True, exist_ok=True)
            p = dest / f"img_01.{ext}"
            p.write_bytes(raw)
            self._send_json({"ok": True, "images": [str(p)],
                             "previews": [f"/weblink/{token}/{p.name}"]})
        elif path == "/api/reg_video":  # 🎬 풀영상 등록 → 미리보기 토큰 (v0.84)
            from ..core import video_editor  # noqa: PLC0415
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            try:
                video = video_editor.resolve_input_video(str(params.get("path") or ""))
            except ValueError as e:
                self._send_json({"error": str(e)}, 400)
                return
            import hashlib as _hl  # noqa: PLC0415
            token = _hl.sha1(video.encode("utf-8")).hexdigest()[:12]
            _LOCAL_VIDEOS[token] = video
            self._send_json({"ok": True, "token": token, "path": video,
                             "duration_s": round(ff.probe_duration_us(video) / 1e6, 1)})
        elif path == "/api/suggest_ranges":  # 🪄 풀영상 구간 자동 제안 (v0.84)
            from ..core import video_editor  # noqa: PLC0415
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            try:
                video = video_editor.resolve_input_video(str(params.get("video_path") or ""))
            except ValueError as e:
                self._send_json({"error": str(e)}, 400)
                return
            total = ff.probe_duration_us(video)
            weights = [max(1.0, float(w or 1)) for w in (params.get("weights") or [])]
            if not weights:
                self._send_json({"error": "구간이 없어요 — 먼저 구간을 만들어 주세요"}, 400)
                return
            scenes = []
            if total < 20 * 60 * 1_000_000:      # 긴 영상은 장면 감지 생략 (시간)
                try:
                    scenes = video_editor.detect_scene_changes(video)
                except Exception:  # noqa: BLE001 — 스냅은 보너스, 실패해도 비율 분할
                    pass
            ranges = video_editor.partition_by_weights(total, weights, scenes)
            self._send_json({"ok": True, "total_us": total,
                             "ranges": [[s, e] for s, e in ranges],
                             "snapped": bool(scenes)})
        elif path == "/api/cancel_queued":  # 📋 대기 중 작업 취소 (v0.88)
            job = _get_job(str(params.get("job_id") or "")) or {}
            if job.get("status") != "queued":
                self._send_json({"error": "대기 중인 작업만 취소할 수 있어요 (진행 중인 작업은 끝까지 갑니다)"}, 400)
                return
            _set_job(job["id"], status="cancelled", stage="cancelled",
                     note="✕ 취소됨 — 시작 전에 대기열에서 뺐어요")
            self._send_json({"ok": True})
        elif path == "/api/parallel":  # 🔀 동시 작업 개수 조절 (v0.90)
            try:
                n = max(1, min(4, int(params.get("n") or 2)))
            except (TypeError, ValueError):
                self._send_json({"error": "1~4 사이 숫자를 골라주세요"}, 400)
                return
            config.save_settings({"ui": {"parallel_jobs": n}})
            _PLIMIT_CACHE.update(t=time.time(), n=n)   # 대기 중 작업에 즉시 반영
            self._send_json({"ok": True, "n": n})
        elif path == "/api/shrink":  # 📦 업로드용 용량 줄이기 (v0.83)
            job_id = str(params.get("job_id") or "")
            job = _get_job(job_id) or {}
            src = job.get("mp4") or ""
            if not src or not Path(src).is_file():
                self._send_json({"error": "완성된 영상 파일을 찾을 수 없어요 — 영상을 먼저 완성해 주세요"}, 400)
                return
            if job.get("shrink_status") == "running":
                self._send_json({"ok": True})   # 이미 진행 중 — 그대로 기다리면 됨
                return
            out = str(Path(src).with_name(Path(src).stem + "_업로드용.mp4"))
            _set_job(job_id, shrink_status="running", shrink_out="", shrink_error="")

            def _shrink_bg(jid=job_id, s=src, o=out):
                from ..core import video_editor  # noqa: PLC0415
                try:
                    before = os.path.getsize(s) / 1048576
                    video_editor.shrink_video(s, o)
                    after = os.path.getsize(o) / 1048576
                    _set_job(jid, shrink_status="done", shrink_out=o,
                             shrink_before_mb=round(before, 1),
                             shrink_after_mb=round(after, 1))
                except Exception as e:  # noqa: BLE001
                    logging.getLogger("cutdaejang").error("용량 줄이기 실패: %s", e)
                    _set_job(jid, shrink_status="failed", shrink_error=str(e)[:300])

            threading.Thread(target=_shrink_bg, daemon=True).start()
            self._send_json({"ok": True})
        elif path == "/api/template":  # 📋 편집 세팅 템플릿 (v0.43)
            name = (params.get("name") or "").strip()[:40]
            if not name:
                self._send_json({"error": "템플릿 이름을 입력하세요"}, 400)
                return
            tpls = dict((config.load_settings().get("ui") or {}).get("templates") or {})
            if params.get("op") == "delete":
                tpls.pop(name, None)
            else:
                data = params.get("params") or {}
                if len(tpls) >= 20 and name not in tpls:
                    self._send_json({"error": "템플릿은 20개까지예요 — 안 쓰는 것을 지워주세요"}, 400)
                    return
                tpls[name] = {k: data[k] for k in _EDIT_LAST_KEYS if k in data}
            try:
                config.save_settings_replace("ui.templates", tpls)
                self._send_json({"ok": True, "templates": tpls})
            except OSError as e:
                self._send_json({"error": f"템플릿 저장 실패: {e}"}, 500)
        elif path == "/api/keys":
            if params.get("action") == "clear":
                config.clear_api_keys()
                self._send_json({"ok": True})
            elif params.get("action") == "save":  # 🔑 API 연동 화면에서 저장 (v0.63)
                _apply_keys({**params, "save_key": True})
                out = {"ok": True,
                       "gemini": bool(os.environ.get("GEMINI_API_KEY")),
                       "elevenlabs": bool(os.environ.get("ELEVENLABS_API_KEY"))}
                if (params.get("elevenlabs_key") or "").strip():
                    # 저장 즉시 실제 목록 조회로 키 검증 — 결과를 그대로 알림 (v0.64.1)
                    type(self.server)._eleven_cache = None
                    try:
                        voices = tts_engine.list_elevenlabs_voices()
                        type(self.server)._eleven_cache = (time.time(), voices)
                        out["eleven_check"] = {"ok": True, "count": len(voices)}
                    except Exception as e:
                        out["eleven_check"] = {"ok": False, "error": str(e)[:300]}
                self._send_json(out)
            else:
                self._send_json({"error": "지원하지 않는 동작"}, 400)
        elif path == "/api/products":  # 📇 내 제품 프로필 (v0.64)
            act = params.get("action") or "list"
            prods = list(config.load_settings().get("products") or [])
            if act == "save":
                item = params.get("item") or {}
                name = (item.get("name") or "").strip()[:40]
                if not name:
                    self._send_json({"error": "제품 이름을 입력하세요"}, 400)
                    return
                clean = {k: str(item.get(k) or "").strip()[:500]
                         for k in ("name", "desc", "points", "target", "tone", "link", "avoid")}
                clean["name"] = name
                prods = [x for x in prods if (x.get("name") or "") != name] + [clean]
                if len(prods) > 20:
                    self._send_json({"error": "제품은 20개까지예요 — 안 쓰는 것을 지워주세요"}, 400)
                    return
                config.save_settings_replace("products", prods)
            elif act == "delete":
                name = (params.get("name") or "").strip()
                prods = [x for x in prods if (x.get("name") or "") != name]
                config.save_settings_replace("products", prods)
            self._send_json({"ok": True, "products": prods})
        elif path == "/api/product_summarize":  # 붙여넣은 소개글 → 프로필 초안 (v0.64)
            _apply_keys(params)
            raw = (params.get("text") or "").strip()
            if not raw:
                self._send_json({"error": "제품 소개 글을 붙여넣어 주세요"}, 400)
                return
            from ..core import script_generator as sg  # noqa: PLC0415
            try:
                if not os.environ.get("GEMINI_API_KEY"):
                    raise sg.ScriptError("no key")
                out = sg.summarize_product(raw)
            except Exception:  # noqa: BLE001 — 키 없음/실패 → 앞부분 잘라 초안
                lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
                out = {"name": (lines[0] if lines else "")[:40],
                       "desc": (lines[1] if len(lines) > 1 else "")[:120],
                       "points": "\n".join(lines[2:6]), "target": "", "tone": "", "link": ""}
            self._send_json({"ok": True, "item": out})
        elif path == "/api/extract_audio":  # 🔊 완성 영상에서 오디오 추출 (v0.64)
            job = _get_job(params.get("job_id", ""))
            mp4 = (job or {}).get("mp4")
            if not mp4 or not Path(mp4).is_file():
                self._send_json({"error": "완성된 영상이 없습니다"}, 400)
                return
            kind = params.get("kind") or "mix"
            job_dir = Path(mp4).parent
            from ..utils import ffmpeg as ff  # noqa: PLC0415
            try:
                if kind == "voice":  # 목소리만 — 렌더 중간 산출물(BGM·원본 소리 없음)
                    # 생성 모드는 job_dir/render/, 편집 모드는 job_dir에 남는다
                    cands = [job_dir / "render" / "voice_sfx.m4a",
                             job_dir / "render" / "voice_full.m4a",
                             job_dir / "voice_sfx.m4a", job_dir / "voice_full.m4a",
                             job_dir / "narration.wav"]
                    src = next((c for c in cands if c.is_file()), None)
                    if src is None:
                        self._send_json({"error": "목소리 트랙 파일을 찾을 수 없어요 — "
                                                  "[전체 소리]로 저장해 주세요"}, 404)
                        return
                    dest = job_dir / "목소리만.mp3"
                    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(src),
                            "-codec:a", "libmp3lame", "-q:a", "2", str(dest)])
                else:
                    dest = job_dir / "소리(전체).mp3"
                    ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-i", str(mp4), "-vn",
                            "-codec:a", "libmp3lame", "-q:a", "2", str(dest)])
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"오디오 추출 실패: {str(e)[:200]}"}, 500)
                return
            self._send_json({"ok": True, "path": str(dest),
                             "url": f"/audio/{(job or {}).get('id', '')}/{dest.name}"})
        elif path == "/api/fetch_fonts":  # ⬇ 무료 글씨체 받기 (v0.63 — BGM 받기 패턴)
            from ..tools import fetch_fonts as ffonts  # noqa: PLC0415
            try:
                r = ffonts.fetch_all()
                self._send_json({"ok": True, "got": r["got"], "skip": r["skip"],
                                 "fail": r["fail"], "fonts": ffonts.installed()})
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"글씨체 받기 실패: {str(e)[:200]}"}, 500)
        elif path == "/api/regenerate":
            self._regenerate(params, workdir)
        elif path == "/api/diagnostic":
            self._diagnostic(workdir)
        elif path == "/api/open_folder":
            self._open_folder(params, workdir)
        else:
            self._send_json({"error": "not found"}, 404)

    # ---------- 재생성 (히스토리 → 저장된 spec 재렌더) ----------

    def _regenerate(self, params: dict, workdir: str) -> None:
        from ..db.jobs import JobStore  # noqa: PLC0415
        from ..spec import TimelineSpec  # noqa: PLC0415

        store = JobStore(Path(workdir) / "history.db")
        row = store.get(params.get("job_id", ""))
        store.close()
        if not row or not row["spec_json"]:
            self._send_json({"error": "재생성할 spec이 없습니다"}, 404)
            return
        spec = TimelineSpec.from_json(row["spec_json"])
        missing = spec.missing_files()
        if missing:
            self._send_json(
                {"error": "원본 소재 파일이 삭제되어 재생성 불가: " + ", ".join(missing[:3])}, 409
            )
            return

        new_id = f"{row['id']}-r{_dt_stamp()}"
        title = row["title"] or row["id"]
        _set_job(new_id, status="running", stage="render", frac=0.0, title=f"{title} (재생성)")

        def run():
            try:
                from ..core import render_engine  # noqa: PLC0415
                from ..core.orchestrator import safe_filename  # noqa: PLC0415

                job_dir = Path(workdir) / new_id
                result = render_engine.render(
                    spec, job_dir / "render",
                    out_path=str(job_dir / f"{safe_filename(title)}.mp4"),
                    progress_cb=lambda f: _set_job(new_id, stage="render", frac=f),
                )
                _set_job(
                    new_id,
                    status="ok" if result.ok else "failed",
                    stage="done", frac=1.0, job_dir=str(job_dir),
                    mp4=result.out_path if result.ok else None,
                    errors=[] if result.ok else result.errors,
                )
                try:
                    store2 = JobStore(Path(workdir) / "history.db")
                    store2.upsert(
                        new_id, title=f"{title} (재생성)", mode=row["mode"],
                        outputs="mp4", status="ok" if result.ok else "failed",
                        duration_us=spec.duration_us, spec_json=row["spec_json"],
                        out_mp4=result.out_path if result.ok else None,
                        tts_provider=row["tts_provider"],
                    )
                    store2.close()
                except Exception:
                    pass
            except Exception as e:
                _set_job(new_id, status="failed", errors=[str(e)])

        _queue_job(new_id, run)  # 📋 작업 큐 (v0.88) — 재생성도 순차
        self._send_json({"job_id": new_id})

    # ---------- 📦 업로드 키트 (v0.39) — 유튜브 제목·태그·설명 일괄 생성 ----------

    def _upload_kit(self, params: dict, workdir: str) -> None:
        _apply_keys(params)
        from ..core import edit_mode, script_generator as sg  # noqa: PLC0415
        from ..utils import ffmpeg as ff  # noqa: PLC0415

        job_id = params.get("job_id", "")
        job = _get_job(job_id) or {}
        title = job.get("title") or ""
        mp4 = job.get("mp4")
        if not (mp4 and Path(mp4).exists()):  # 서버를 껐다 켜도 히스토리 영상이면 가능
            mp4 = self._video_path(job_id)
        if not mp4:
            self._send_json({"error": "완성 영상을 찾을 수 없습니다 — 먼저 영상을 완성하세요"}, 400)
            return
        jp = job.get("params") or {}
        ep = job.get("edit_params") or {}
        hook = (ep.get("hook") or jp.get("hook") or "").strip()
        # 대본: 검토 자막(메모리) → job 폴더 script.json → 없으면 장면 캡처만으로
        transcript = "\n".join(
            (s.get("text") or "") for s in (job.get("subtitles") or []))
        if not transcript.strip():
            sj = Path(workdir) / job_id / "script.json"
            if sj.is_file():
                try:
                    # sentences는 [{"text",...}] 형식 — 문자열 join하면 크래시 (완전 자동
                    # 생성 영상의 키트가 여기로 옴. v0.47에서 발견·수정한 잠복 버그)
                    raw_sents = json.loads(sj.read_text(encoding="utf-8")).get("sentences", [])
                    transcript = "\n".join(
                        (s.get("text", "") if isinstance(s, dict) else str(s))
                        for s in raw_sents)
                except (OSError, json.JSONDecodeError, AttributeError, TypeError):
                    pass
        if not title:
            try:
                from ..db.jobs import JobStore  # noqa: PLC0415

                store = JobStore(Path(workdir) / "history.db")
                row = store.get(job_id)
                store.close()
                if row:
                    title = row["title"] or ""
            except Exception:
                pass
        try:
            dur_s = int(ff.probe_duration_us(mp4) / 1e6)
            w, h = ff.probe_video_size(mp4)
        except Exception:
            dur_s, w, h = 0, 1080, 1920
        is_shorts = h > w and dur_s <= 180
        channel = config.load_settings().get("channel") or {}
        try:
            frames = edit_mode.extract_frames_b64(mp4, n=4)
        except Exception:
            frames = []
        stub = False
        try:
            if os.environ.get("GEMINI_API_KEY"):
                kit = sg.suggest_upload_kit(
                    frames, transcript, duration_s=dur_s, is_shorts=is_shorts,
                    hook=hook or title, channel=channel)
            else:
                kit = sg.suggest_upload_kit_stub(transcript, hook or title,
                                                 is_shorts=is_shorts)
                stub = True
        except sg.ScriptError as e:
            logging.getLogger("cutdaejang").warning("업로드 키트 AI 실패 → 예시로 대체: %s", e)
            kit = sg.suggest_upload_kit_stub(transcript, hook or title,
                                             is_shorts=is_shorts)
            stub = True
        # BGM 크레딧 자동 삽입 — 어떤 곡을 썼는지 컷대장이 아니까 (CC BY 표기 의무)
        credit = _bgm_credit((ep.get("bgm") or jp.get("bgm") or "").strip())
        if credit:
            kit["description"] = (kit.get("description", "").rstrip() + "\n\n" + credit)
        # 업로드 체크리스트 (계산으로 확실한 것들)
        checks = []
        if is_shorts:
            checks.append(f"세로 {dur_s}초 영상 → 올리면 쇼츠로 자동 인식돼요 (#Shorts 표기 불필요)")
            checks.append("인스타는 '릴스'로 올리기 — 9:16로 딱 맞아요. 프로필·피드 썸네일이 "
                          "위아래 잘려 보이는 건 정상(4:5 미리보기)이고, 릴스로 재생하면 다 나와요")
        else:
            checks.append(f"가로/롱폼({dur_s}초) → 노출을 위해 썸네일을 꼭 넣으세요")
        checks.append("썸네일: " + ("만들어 둠 ✓" if job.get("thumbnail")
                                  else "아직 없음 — 완료 화면 [🖼️ 썸네일 만들기] (쇼츠는 선택, 롱폼은 권장)"))
        if credit:
            checks.append("BGM 크레딧이 설명문 끝에 자동 포함됐어요 (무료 음원 표기 의무)")
        checks.append("태그는 유튜브 스튜디오 [세부정보 → 태그]에 통째로 붙여넣기 (쉼표 그대로)")
        checks.append("틱톡·인스타·네이버 클립·스레드 문구는 아래 접힌 칸에서 복사 "
                      + ("(같은 영상 그대로 재업로드 OK)" if is_shorts
                         else "(세로 플랫폼엔 세로로 만든 편집본과 함께 쓰세요)"))
        kit["checklist"] = checks
        kit["is_shorts"] = is_shorts
        # 파일로도 저장 — 업로드할 때 열어서 복붙
        out_dir = Path(job["job_dir"]) if job.get("job_dir") else Path(mp4).parent
        kit_path = ""
        try:
            p = out_dir / "업로드킷.txt"
            p.write_text(_kit_text(kit, title), encoding="utf-8")
            kit_path = str(p.resolve())
        except OSError:
            pass
        logging.getLogger("cutdaejang").info(
            "업로드 키트 생성: %s (AI=%s, 쇼츠=%s)", title or job_id, not stub, is_shorts)
        self._send_json({"kit": kit, "stub": stub, "path": kit_path})

    # ---------- 진단 리포트 / 폴더 열기 ----------

    def _diagnostic(self, workdir: str) -> None:
        import datetime as dt  # noqa: PLC0415
        import platform  # noqa: PLC0415
        import subprocess  # noqa: PLC0415

        from .. import __version__  # noqa: PLC0415
        from ..utils import ffmpeg as ff  # noqa: PLC0415

        lines = [
            "=" * 60,
            f"컷대장 진단 리포트  {dt.datetime.now().isoformat(timespec='seconds')}",
            f"버전: v{__version__} / Python {platform.python_version()} / {platform.platform()}",
            "=" * 60,
            "",
            "── 환경 ──",
        ]
        try:
            ver = subprocess.run([ff.ffmpeg_bin(), "-version"], capture_output=True, timeout=15)
            lines.append("ffmpeg: " + ver.stdout.decode("utf-8", "replace").splitlines()[0])
        except Exception as e:
            lines.append(f"ffmpeg: ✘ {e}")
        env = _env_check()
        lines.append(f"libass 폰트 동봉: {'OK' if env['font'] else '없음'}")
        lines += ["", "── 최근 로그 (하단 🪵 패널과 동일) ──", *list(_LOG_BUF)[-150:]]
        try:
            lines.append(f"GPU 인코딩(nvenc): {'사용가능' if ff.nvenc_available() else '미감지(libx264)'}")
        except Exception as e:
            lines.append(f"GPU 감지 오류: {e}")
        for name, on in self._state()["keys"].items():
            lines.append(f"{name} 키: {'설정됨' if on else '없음'}")
        lines.append(f"음성인식 사용가능: {_stt_available()}")

        lines.append("")
        lines.append("── 설정(settings.json) ──")
        try:
            lines.append(json.dumps(config.load_settings(), ensure_ascii=False, indent=2))
        except Exception as e:
            lines.append(f"설정 로드 오류: {e}")

        lines.append("")
        lines.append("── 최근 작업 8건 ──")
        for r in self._state()["history"][:8]:
            lines.append(f"{r['created_at']}  [{r['status']}] {r['title']} (목소리: {r['tts_provider'] or '-'})")

        # 진행 중/방금 끝난 작업의 전체 오류(자르지 않음) + 파라미터(키 제외)
        with _LOCK:
            recent = list(_JOBS.values())[-5:]
        for j in recent:
            if j.get("errors") or j.get("status") == "failed":
                lines.append("")
                lines.append(f"── 작업 상세 ({j['id']}, 상태={j.get('status')}) ──")
                p = dict(j.get("params") or {})
                for k in ("gemini_key", "openai_key"):
                    if p.get(k):
                        p[k] = "***"
                if p:
                    lines.append("입력: " + json.dumps(p, ensure_ascii=False))
                for e in (j.get("errors") or []):
                    lines.append(str(e))  # 전체 (원본 오류·stderr 꼬리 포함)

        log_file = Path(workdir) / "logs" / "cutdaejang.log"
        if log_file.exists():
            lines.append("")
            lines.append("── 로그 (마지막 200줄, 전체 오류 추적 포함) ──")
            lines += log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]

        out = Path(workdir) / f"진단리포트_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        text = "\n".join(lines)
        out.write_text(text, encoding="utf-8")
        # v0.44.1: 파일 경로만 alert로 주면 못 찾음 → 내용을 화면에도 그대로 보여줌
        self._send_json({"path": str(out.resolve()), "text": text})

    def _open_folder(self, params: dict, workdir: str) -> None:
        job = _get_job(params.get("job_id", ""))
        target = Path(job["job_dir"]) if job and job.get("job_dir") else Path(workdir)
        if not target.is_dir():
            self._send_json({"error": "폴더 없음"}, 404)
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(target))  # noqa: S606
            else:
                import subprocess  # noqa: PLC0415

                subprocess.Popen(["xdg-open", str(target)])
            self._send_json({"ok": True, "path": str(target)})
        except Exception as e:
            self._send_json({"error": str(e), "path": str(target)}, 500)

    # ---------- 목소리 미리듣기 (지시서 PATCH 6) ----------

    def _eleven_voices(self, params: Optional[dict] = None) -> None:
        """내 ElevenLabs 계정 보이스 목록 — 10분 캐시 (v0.46 성우 보이스 선택)."""
        favs = [str(x) for x in (config.load_settings()["tts"].get("eleven_favs") or [])]
        if not os.environ.get("ELEVENLABS_API_KEY"):
            self._send_json({"voices": [], "no_key": True, "favs": favs})
            return
        if (params or {}).get("refresh"):  # 🔄 다시 불러오기 — 캐시 버리고 새로 (v0.64.1)
            type(self.server)._eleven_cache = None
        now = time.time()
        cache = getattr(type(self.server), "_eleven_cache", None)
        if cache and now - cache[0] < 600:
            self._send_json({"voices": cache[1], "favs": favs})
            return
        try:
            voices = tts_engine.list_elevenlabs_voices()
            type(self.server)._eleven_cache = (now, voices)
            self._send_json({"voices": voices, "favs": favs})
        except Exception as e:  # 키 거부·네트워크 문제 — 사유를 화면까지 (v0.64.1)
            self._send_json({"voices": [], "error": str(e)[:300], "favs": favs})

    def _preview(self, params: dict) -> None:
        _apply_keys(params)
        settings = config.load_settings()
        if params.get("tts_style"):
            settings = config.deep_merge(
                settings, {"tts": {"style_preset": params["tts_style"]}}
            )
        if params.get("tts_provider") == "windows" and params.get("voice"):
            # 내장 음성 보이스는 voice 인자가 아니라 제공자 설정으로 (v0.59)
            settings = config.deep_merge(
                settings, {"tts": {"windows_voice": params["voice"]}})
        try:
            provider = tts_engine.make_provider(params.get("tts_provider", "stub"), settings)
            engine = tts_engine.TTSEngine(
                provider,
                Path(self.server.workdir) / "cache" / "tts",  # type: ignore[attr-defined]
                settings=settings,
            )
            path = engine.synth_sentence(
                params.get("text") or "안녕하세요, 컷대장 목소리 미리듣기입니다.",
                voice=params.get("voice", ""),
            )
            self._send_json({"url": f"/preview/{path.name}"})
        except tts_engine.TTSError as e:
            self._send_json({"error": str(e)}, 400)

    def _serve_bgm(self, name: str) -> None:
        """BGM 미리듣기 — resources/bgm 폴더 안 음원 파일만 서빙."""
        safe = Path(name).name
        p = orchestrator.DEFAULT_BGM_DIR / safe
        if (safe != name or not p.is_file()
                or p.suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}):
            self._send_json({"error": "not found"}, 404)
            return
        self._serve_file(str(p))

    def _serve_preview(self, name: str) -> None:
        if not (name.endswith(".wav") and name[:-4].isalnum()):  # 캐시 해시 파일만
            self._send_json({"error": "not found"}, 404)
            return
        path = Path(self.server.workdir) / "cache" / "tts" / name  # type: ignore[attr-defined]
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- 상태 ----------

    def _state_fonts(self) -> list:
        try:
            from ..tools import fetch_fonts as ffonts  # noqa: PLC0415
            return ffonts.installed()
        except Exception:  # noqa: BLE001
            return []

    def _state(self) -> dict:
        with _LOCK:
            jobs = [dict(j) for j in _JOBS.values()]
        for j in jobs:
            j.pop("params", None)  # API 키 등 입력값은 화면으로 돌려보내지 않음
        jobs.sort(key=lambda j: j["id"], reverse=True)

        history = []
        try:
            from ..db.jobs import JobStore  # noqa: PLC0415

            store = JobStore(Path(self.server.workdir) / "history.db")  # type: ignore[attr-defined]
            active_ids = {j["id"] for j in jobs}
            history = [
                {
                    "id": r["id"], "title": r["title"], "mode": r["mode"],
                    "status": r["status"], "created_at": r["created_at"],
                    "has_mp4": bool(r["out_mp4"] and Path(r["out_mp4"]).exists()),
                    "has_spec": bool(r["spec_json"]),
                    "has_params": bool(r.get("params_json")),  # ✏ 다시 편집 가능 (v0.85)
                    "tts_provider": r["tts_provider"] or "",
                }
                for r in store.list(limit=30)
                if r["id"] not in active_ids
            ]
            store.close()
        except Exception:
            pass
        return {
            "jobs": jobs,
            "history": history,
            "fonts": self._state_fonts(),
            "keys": {
                "gemini": bool(os.environ.get("GEMINI_API_KEY")),
                "openai": bool(os.environ.get("OPENAI_API_KEY")),
                "elevenlabs": bool(os.environ.get("ELEVENLABS_API_KEY")),
                "coupang": bool(os.environ.get("COUPANG_ACCESS_KEY")
                                and os.environ.get("COUPANG_SECRET_KEY")),  # 🛒 v0.88
                "naver": bool(os.environ.get("NAVER_CLIENT_ID")
                              and os.environ.get("NAVER_CLIENT_SECRET")),   # 🟢 v0.89
            },
            "platform": sys.platform,
            "env": _env_check(),
            "settings": config.load_settings(),
            "bgm_files": sorted(
                p.name
                for p in orchestrator.DEFAULT_BGM_DIR.glob("*")
                if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
            ),
            "voices": GEMINI_VOICES,
            "styles": list(STYLE_INSTRUCTIONS),
            "stt_available": _stt_available(),
            "bgm_fetch": dict(_BGM_TASK),
            "weblink_fetch": dict(_WEBLINK_TASK),  # 🔗 글 가져오기 진행/결과 (v0.78)
            "logs": list(_LOG_BUF)[-120:],
        }

    # ---------- 영상 서빙 (Range 지원 — 브라우저 탐색바용) ----------

    def _video_path(self, job_id: str) -> Optional[str]:
        job = _get_job(job_id)
        if job and job.get("mp4") and Path(job["mp4"]).exists():
            return job["mp4"]
        try:
            from ..db.jobs import JobStore  # noqa: PLC0415

            store = JobStore(Path(self.server.workdir) / "history.db")  # type: ignore[attr-defined]
            row = store.get(job_id)
            store.close()
            if row and row["out_mp4"] and Path(row["out_mp4"]).exists():
                return row["out_mp4"]
        except Exception:
            pass
        return None

    def _serve_cutvideo(self, job_id: str) -> None:
        """자막 검토 중 참고 재생용 컷 영상(자막 없는 상태)."""
        job = _get_job(job_id)
        path = job.get("cut_video") if job else None
        if not path or not Path(path).is_file():
            self._send_json({"error": "컷 영상 없음"}, 404)
            return
        self._serve_file(path)

    def _serve_video(self, job_id: str) -> None:
        path = self._video_path(job_id)
        if not path:
            self._send_json({"error": "영상 없음"}, 404)
            return
        self._serve_file(path)

    def _serve_file(self, path: str) -> None:
        size = os.path.getsize(path)
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            try:
                raw_start, _, raw_end = range_header[6:].partition("-")
                start = int(raw_start) if raw_start else 0
                end = int(raw_end) if raw_end else size - 1
                end = min(end, size - 1)
            except ValueError:
                start, end = 0, size - 1
        length = end - start + 1

        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".mp3": "audio/mpeg", ".wav": "audio/wav",
                 ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".flac": "audio/flac",
                 ".ttf": "font/ttf", ".otf": "font/otf",  # 🔤 글씨체 미리보기 (v0.68)
                 }.get(Path(path).suffix.lower(), "video/mp4")
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)


_LOG_BUF: deque = deque(maxlen=400)  # 🪵 UI 하단 로그 패널용 링버퍼


class _UILogHandler(logging.Handler):
    def emit(self, record):  # noqa: D102
        try:
            _LOG_BUF.append(
                f"{time.strftime('%H:%M:%S')} [{record.levelname[0]}] {record.getMessage()}")
        except Exception:  # noqa: BLE001
            pass


def _attach_ui_log() -> None:
    lg = logging.getLogger("cutdaejang")
    if not any(isinstance(h, _UILogHandler) for h in lg.handlers):
        lg.addHandler(_UILogHandler())
    if lg.level in (logging.NOTSET, logging.WARNING):
        lg.setLevel(logging.INFO)


def create_server(workdir: str, port: int = 7860) -> ThreadingHTTPServer:
    Path(workdir).mkdir(parents=True, exist_ok=True)
    _attach_ui_log()
    for msg in config.migrate_settings():  # 구버전 설정 1회 승격 (v0.50.1)
        logging.getLogger("cutdaejang").info("설정 업데이트: %s", msg)
    _ensure_queue_worker()   # 📋 작업 큐 워커 (v0.88) — 무거운 작업 순차 실행
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    httpd.workdir = str(workdir)  # type: ignore[attr-defined]
    return httpd


def _setup_file_logging(workdir: str) -> None:
    import logging  # noqa: PLC0415

    log_dir = Path(workdir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "cutdaejang.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("cutdaejang")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def serve(workdir: str = "jobs", port: int = 7860, open_browser: bool = True) -> int:
    loaded = config.load_api_keys_into_env()
    if loaded:
        print(f"저장된 API 키 로드: {', '.join(loaded)}")
    _setup_file_logging(workdir)
    httpd = None
    for candidate in range(port, port + 10):  # 이전 서버가 켜져 있어도 다음 포트로
        try:
            httpd = create_server(workdir, candidate)
            break
        except OSError:
            continue
    if httpd is None:
        print(f"[!] {port}~{port + 9} 포트를 모두 사용 중입니다. 켜져 있는 컷대장 창을 닫아주세요.")
        return 1
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"컷대장 UI: {url}   (끝내려면 Ctrl+C — 이 창을 닫으면 UI도 꺼집니다)")
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


# ─────────────────────────── 화면 (단일 페이지) ───────────────────────────

_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>컷대장</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
         background:#0f1117; color:#e8eaf0; }
  .wrap { max-width:860px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:22px; margin:0 0 4px; } h1 small{ color:#8b93a7; font-size:13px; font-weight:400; }
  .card { background:#171a23; border:1px solid #262b3a; border-radius:12px;
          padding:18px; margin-top:16px; }
  label { display:block; font-size:13px; color:#aab2c5; margin:12px 0 4px; }
  input[type=text], input[type=password], input[type=number], select, textarea {
    width:100%; padding:10px 12px; border-radius:8px; border:1px solid #2c3347;
    background:#0f1117; color:#e8eaf0; font-size:14px; }
  textarea { min-height:140px; line-height:1.7; }
  .row { display:flex; gap:12px; flex-wrap:wrap; } .row > div { flex:1; min-width:180px; }
  .toggle { display:flex; gap:8px; margin-top:6px; }
  .toggle label { flex:1; margin:0; text-align:center; padding:10px; border-radius:8px;
    border:1px solid #2c3347; cursor:pointer; color:#aab2c5; font-size:14px; }
  .toggle input { display:none; }
  .toggle input:checked + span { color:#fff; }
  .toggle label:has(input:checked) { background:#243052; border-color:#4266d5; color:#fff; }
  .chk { display:flex; align-items:center; gap:8px; margin-top:12px; font-size:14px; color:#cdd3e0; }
  button { padding:12px 18px; border-radius:9px; border:0; background:#4266d5; color:#fff;
           font-size:15px; font-weight:700; cursor:pointer; width:100%; margin-top:16px; }
  button:disabled { background:#2c3347; color:#6b7387; cursor:default; }
  button.ghost { background:transparent; border:1px solid #2c3347; width:auto; padding:8px 14px;
                 font-size:13px; font-weight:400; margin:0; }
  .bar { height:10px; background:#0f1117; border-radius:6px; overflow:hidden; margin-top:8px; }
  .bar > div { height:100%; background:linear-gradient(90deg,#4266d5,#7a5cf0); width:0%; transition:width .4s; }
  .stage { font-size:13px; color:#8b93a7; margin-top:8px; }
  video { width:100%; max-width:320px; border-radius:12px; margin-top:12px; background:#000; display:block; }
  .err { color:#ff7b8a; font-size:13px; white-space:pre-wrap; margin-top:8px; }
  .ok-badge { color:#5dd39e; } .fail-badge { color:#ff7b8a; }
  table { width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }
  th, td { text-align:left; padding:8px 6px; border-bottom:1px solid #232838; color:#cdd3e0; }
  th { color:#8b93a7; font-weight:400; }
  .hint { font-size:12px; color:#6b7387; margin-top:4px; }
  .banner { background:#3a1520; border:1px solid #ff7b8a; color:#ffb3bd; border-radius:10px;
            padding:12px 14px; margin-top:14px; font-size:13px; }
  .hookcands { display:flex; flex-direction:column; gap:6px; margin-top:8px; }
  .hookcands button { width:100%; text-align:left; background:#12305a; border:1px solid #2c4a7a;
    color:#dfe7f5; border-radius:8px; padding:9px 12px; font-size:14px; cursor:pointer; margin:0; }
  .hookcands button:hover { background:#183c72; }
  .subrow-active { background:#243052; box-shadow:0 0 0 1px #4266d5 inset; }
  .subrow-active input { border-color:#4266d5; }
  /* 자막 검토: 영상 플레이어를 위에 고정(sticky) — 스크롤해도 항상 보임 */
  .playbar { position:sticky; top:0; z-index:6; background:#171a23; padding:8px 0 10px;
             border-bottom:1px solid #262b3a; margin-bottom:8px; }
  .playbar video { max-width:200px; margin:0; }
  .playrow { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:8px; }
  .playrow button { margin:0; }
  .pbtn { width:auto; padding:8px 14px; font-size:14px; }
  .playrow select { width:auto; padding:6px 8px; }
  .subrowbtns button { padding:6px 9px; font-size:12px; }
  .subList-scroll { max-height:46vh; overflow-y:auto; padding-right:4px; }
  .shortsbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:10px;
               padding:8px 10px; border:1px dashed #3a4157; border-radius:10px; }
  .shortsbar button { margin:0; }
  .keepchk { width:18px; height:18px; margin-top:8px; flex:none; cursor:pointer; accent-color:#4266d5; }
  .subrow.dropped { opacity:0.4; }
  .subrow.dropped input[type=text] { text-decoration:line-through; }
  .hidden { display:none !important; }
  code { background:#0f1117; padding:2px 6px; border-radius:4px; font-size:12px; }
  /* v0.36 초보자 UI — 첫 화면 카드·단계 번호·접는 옵션 그룹 */
  .topbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .topbar h1 { flex:1; min-width:240px; }
  .topbar button { width:auto; margin:0; }
  .home-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(216px,1fr));
                gap:12px; margin-top:14px; }
  .modecard { background:#171a23; border:1px solid #2c3347; border-radius:14px;
              padding:22px 14px; text-align:center; cursor:pointer; margin:0; font-weight:400; }
  .modecard:hover { border-color:#4266d5; background:#1a2030; }
  .modecard .mc-emoji { font-size:34px; display:block; }
  .modecard .mc-title { font-size:16px; font-weight:800; display:block; margin-top:8px; color:#fff; }
  .modecard .mc-desc { font-size:12px; color:#8b93a7; display:block; margin-top:6px; line-height:1.5; }
  .backrow { display:flex; align-items:center; gap:10px; }
  .backrow b { font-size:16px; }
  .backrow button { margin:0; }
  .stepnum { display:inline-flex; width:22px; height:22px; border-radius:50%; background:#4266d5;
             color:#fff; font-size:13px; font-weight:700; align-items:center; justify-content:center;
             margin-right:7px; flex:none; }
  .steplabel { display:flex; align-items:center; flex-wrap:wrap; font-size:14px; color:#e8eaf0;
               font-weight:700; margin:18px 0 6px; }
  .steplabel .hint { font-weight:400; margin-left:8px; margin-top:0; }
  details.opt { border:1px solid #262b3a; border-radius:10px; padding:0 12px; margin-top:8px;
                background:#141722; }
  details.opt > summary { cursor:pointer; padding:11px 0; font-size:14px; color:#cdd3e0;
                          list-style:none; }
  details.opt > summary::-webkit-details-marker { display:none; }
  details.opt > summary::before { content:'▸  '; color:#6b7387; }
  details.opt[open] > summary::before { content:'▾  '; }
  details.opt[open] { padding-bottom:12px; }
  .guide { background:#14233c; border:1px solid #2c4a7a; color:#cfe0ff; border-radius:10px;
           padding:12px 14px; margin-top:14px; font-size:13px; line-height:1.7; }
  .guide a { color:#8ab4ff; }
  /* ── v0.60 꾸미기 시각화: 견본 칩·미니 데모·톤 스와치 ── */
  .stylechips { display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
  .stylechip { background:#0d0f14; border:1.5px solid #2c3350; border-radius:10px;
    padding:9px 14px; cursor:pointer; font-weight:800; font-size:15px; line-height:1.2; }
  .stylechip:hover { border-color:#4266d5; }
  .stylechip.sel { border-color:#5b7cfa; box-shadow:0 0 0 2px rgba(91,124,250,.28); }
  .fx-demo { display:inline-flex; width:64px; height:38px; border-radius:6px; flex:none;
    background:linear-gradient(135deg,#31406e,#7a4a76 60%,#b8875a);
    align-items:center; justify-content:center; overflow:hidden; }
  .fx-demo b { color:#fff; font-size:12.5px; text-shadow:0 1px 2px #000; }
  .punch-demo b { animation:punchD 1.8s ease-in-out infinite; }
  @keyframes punchD { 0%,55%,100% { transform:scale(1); } 30% { transform:scale(1.28); } }
  .pop-demo b { animation:popD 2.2s ease-out infinite; color:#ffd400; font-weight:900; font-size:14px; }
  @keyframes popD { 0%,12% { transform:scale(0); opacity:0; } 22% { transform:scale(1.4); opacity:1; }
    32% { transform:scale(1); } 74% { opacity:1; transform:scale(1); } 88%,100% { opacity:0; } }
  .tonerow { display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
  .tonecard { cursor:pointer; text-align:center; border:1.5px solid #2c3350; border-radius:10px;
    padding:5px 6px 4px; background:#0d0f14; }
  .tonecard:hover { border-color:#4266d5; }
  .tonecard.sel { border-color:#5b7cfa; box-shadow:0 0 0 2px rgba(91,124,250,.28); }
  .tonecard .sw { width:76px; height:44px; border-radius:6px;
    background:linear-gradient(135deg,#4a6fd4 0%,#c76a93 55%,#e8b45a 100%); }
  .tonecard span { display:block; font-size:11px; color:#aeb6c8; margin-top:4px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1>컷대장 <small>유튜브 영상 자동 제작 (v0.94.0)</small></h1>
    <div id="jobsBar" class="hidden" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;flex:1 1 100%;order:9;margin:6px 0 2px;padding:8px 10px;border:1px dashed #3a4157;border-radius:10px">
      <span class="hint" style="white-space:nowrap">📋 진행·대기</span>
      <select id="parallelSel" onchange="setParallel(event)" title="동시에 몇 개까지 같이 만들지 — 여러 작업을 걸어두고 병렬로 진행돼요. PC가 버벅이면 낮추세요" style="font-size:12px;padding:2px 6px">
        <option value="1">동시 1개 (순서대로)</option>
        <option value="2">동시 2개 (추천)</option>
        <option value="3">동시 3개</option>
        <option value="4">동시 4개 (고사양)</option>
      </select>
    </div>
    <button class="ghost" onclick="toggleProductCard()">📇 내 제품</button>
    <button class="ghost" onclick="toggleApiCard()">🔑 API 연동</button>
    <button class="ghost" onclick="toggleSettings()">⚙ 설정</button>
  </div>
  <div class="banner hidden" id="envBanner"></div>

  <div class="card" id="homeCard">
    <div style="font-size:17px;font-weight:800">무엇을 만들까요?</div>
    <div class="hint" style="margin-top:4px">카드를 누르면 시작돼요. 꼭 필요한 것만 물어보고, 나머지는 컷대장이 알아서 합니다.</div>
    <div class="home-cards">
      <button class="modecard" onclick="openMode('gen')">
        <span class="mc-emoji">🤖</span><span class="mc-title">AI 영상 만들기</span>
        <span class="mc-desc">주제 한 줄만 쓰면<br>대본·목소리·자막·배경까지 자동</span>
      </button>
      <button class="modecard" onclick="openMode('edit')">
        <span class="mc-emoji">✂️</span><span class="mc-title">내 영상 편집</span>
        <span class="mc-desc">내 영상을 넣으면 무음 컷·자막을<br>자동으로, 쇼츠로도 줄여줘요</span>
      </button>
      <button class="modecard" onclick="openMode('photo')">
        <span class="mc-emoji">📸</span><span class="mc-title">사진으로 영상</span>
        <span class="mc-desc">사진 몇 장이면<br>내레이션 넣은 영상 완성</span>
      </button>
      <button class="modecard" onclick="openMode('weblink')">
        <span class="mc-emoji">🔗</span><span class="mc-title">블로그 글로 만들기</span>
        <span class="mc-desc">내 블로그 글 주소만 넣으면<br>사진+내레이션 홍보 영상</span>
      </button>
      <button class="modecard" onclick="openMode('sections')">
        <span class="mc-emoji">🎞</span><span class="mc-title">구간 대본 영상</span>
        <span class="mc-desc">대본 구간마다 클립을 넣으면<br>압축·내레이션·이어붙이기 자동</span>
      </button>
      <button class="modecard" onclick="openMode('shop')">
        <span class="mc-emoji">🛒</span><span class="mc-title">쇼핑 상품 영상</span>
        <span class="mc-desc">쿠팡 파트너스 · 네이버 쇼핑커넥트<br>상품 검색 → 홍보 영상 자동</span>
      </button>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px">
      <button class="ghost" onclick="openVoice(event)">🎤 내 목소리 등록</button>
      <span class="hint">녹음 파일 하나로 <b>나만의 AI 목소리</b>를 만들어 내레이션에 쓸 수 있어요</span>
      <b class="hint" id="homeVoiceState" style="color:#5dd39e"></b>
    </div>
    <div class="guide hidden" id="startGuide">💡 <b>처음 오셨나요? — 준비물 1개 (1분)</b><br>
      AI 대본·자막·좋은 목소리는 <b>무료 Gemini 키</b>가 있어야 해요.
      <a href="https://aistudio.google.com/apikey" target="_blank">여기서 무료 발급</a>받고,
      만들기를 시작할 때 나오는 창에 붙여넣으면 끝 — 한 번 넣으면 저장돼서 다시 안 물어봐요.</div>
  </div>

  <div class="card hidden" id="editCard">
    <div class="backrow">
      <button class="ghost" onclick="showHome(event)">← 처음으로</button>
      <b id="editTitleLabel">✂️ 내 영상 편집</b>
    </div>

    <div class="chk" style="gap:8px;flex-wrap:wrap">
      <span class="hint">📋 내 세팅 템플릿</span>
      <select id="tplSel" style="width:auto;padding:6px 8px" onchange="applyTemplate()">
        <option value="">템플릿…</option>
      </select>
      <button class="ghost" style="padding:5px 10px" onclick="saveTemplate(event)">💾 지금 세팅을 템플릿으로</button>
      <button class="ghost" style="padding:5px 10px" onclick="deleteTemplate(event)" title="고른 템플릿 삭제">🗑</button>
      <span class="hint">— 꾸미기·완성 방식을 이름으로 저장해두고 언제든 한 번에 불러와요</span>
    </div>

    <div id="videoBlock">
      <div class="steplabel"><span class="stepnum">1</span>편집할 영상 고르기</div>
      <div style="display:flex; gap:8px">
        <input type="text" id="editVideo" style="flex:1" placeholder="[📁 영상 선택] 버튼을 누르거나, 영상 파일 경로를 붙여넣기">
        <button class="ghost" style="white-space:nowrap" onclick="pickFile(event)">📁 영상 선택</button>
      </div>
      <div class="hint">버튼을 누르면 파일 탐색기가 열려요. 폴더 경로를 넣으면 그 안의 최신 영상을 씁니다.</div>
    </div>

    <div id="photoBlock" class="hidden">
      <div class="steplabel"><span class="stepnum">1</span>사진 고르기</div>
      <div class="hint" style="margin-bottom:6px">💡 블로그 글에서 사진·대본을 가져오려면 첫 화면의 <b>[🔗 블로그 글로 만들기]</b>를 쓰세요.</div>
      <div style="display:flex;gap:8px">
        <input type="text" id="photoPath" style="flex:1" placeholder="사진 파일들(세미콜론 구분) 또는 폴더 경로">
        <button class="ghost" style="white-space:nowrap" onclick="pickInto(event,'photoPath','images')">🖼 사진 고르기 (여러 장)</button>
        <button class="ghost" style="white-space:nowrap" onclick="pickInto(event,'photoPath','folder')">📁 폴더째</button>
      </div>
      <div class="hint">[🖼 사진 고르기]에서 Ctrl/Shift로 여러 장을 한 번에 — 고른 순서(입력칸의 세미콜론 순서)대로 들어가요. 폴더를 고르면 안의 사진 전부(이름순). 가로 사진도 블러 배경으로 세로 쇼츠에 자연스럽게 들어갑니다.</div>
      <div class="chk" style="gap:8px">
        <span>영상 전체 길이</span>
        <input type="number" id="photoSec" value="15" min="3" max="180" style="width:80px;padding:6px">
        <span class="hint">초 — 예) 사진 5장 + 15초 = 한 장당 3초씩</span>
      </div>
    </div>

    <div class="steplabel"><span class="stepnum">2</span>어떻게 완성할까요?</div>
    <div class="toggle">
      <label><input type="radio" name="editFinish" value="review" checked onchange="onFinishChange()"><span>✋ 자막 확인 후 완성 (추천)</span></label>
      <label><input type="radio" name="editFinish" value="auto" onchange="onFinishChange()"><span>🤖 완전 자동 (끝까지 알아서)</span></label>
    </div>
    <div class="hint" id="finishHint">중간에 자막을 확인하는 화면이 한 번 나와요 — 오타만 고치고 [완성]을 누르면 됩니다.</div>
    <div id="autoOptRow" class="hidden">
      <div class="chk" style="gap:8px;margin-top:6px">
        <span>만들기</span>
        <select id="autoMultiSel" style="width:auto;padding:6px 8px" onchange="onAutoMultiChange()">
          <option value="one" selected>쇼츠 1개 — 핵심 장면만 뽑아서</option>
          <option value="multi">여러 개로 나누기 — 영상 전체를 쇼츠 여러 개로</option>
        </select>
        <span class="hint" id="autoMultiHint"></span>
      </div>
      <div class="chk" style="gap:8px">
        <span id="autoLenLabel">완성 길이</span>
        <select id="autoTargetPreset" style="width:auto;padding:6px 8px" onchange="applyTargetPreset()">
          <option value="30" selected>쇼츠 30초 — 핵심만 자동 선별</option>
          <option value="60">쇼츠 60초</option>
          <option value="0">원본 길이 그대로</option>
          <option value="custom">직접 입력…</option>
        </select>
        <input type="number" id="autoTargetSec" value="30" min="0" max="90" style="width:64px;padding:6px" class="hidden">
        <span class="hint">· 재생 속도</span>
        <select id="editSpeedSel" style="width:auto;padding:6px 8px">
          <option value="1">1배</option>
          <option value="1.25">1.25배</option>
          <option value="1.5">1.5배</option>
          <option value="2">2배</option>
        </select>
        <span class="hint">· ⚡ 빠른 템포</span>
        <select id="editTempoSel" style="width:auto;padding:6px 8px"
                title="자막(발화) 없는 영상을 자동 몽타주할 때 컷을 얼마나 촘촘히 자를지 — 인스타 릴스처럼 빠른 편집 리듬">
          <option value="">기본</option>
          <option value="빠르게">빠르게 (컷 촘촘)</option>
          <option value="아주 빠르게">아주 빠르게</option>
        </select>
        <span class="hint">· 화질</span>
        <select id="autoQualitySel" style="width:auto;padding:6px 8px">
          <option value="draft">빠름 (초안)</option>
          <option value="standard" selected>표준 (1080p)</option>
          <option value="high">고화질</option>
          <option value="ultra">초고화질 (4K)</option>
        </select>
      </div>
      <div class="hint" style="margin-top:4px">💾 여기서 정한 세팅은 자동으로 기억돼요 — 다음부터는 영상만 바꿔 넣고 [만들기 시작]만 누르면 같은 방식으로 만들어집니다.</div>
    </div>

    <div class="steplabel" style="margin-top:20px"><span class="stepnum">3</span>꾸미기 <span class="hint">— 전부 선택사항. 필요한 줄만 눌러서 펼치세요</span></div>

    <details class="opt" id="optDirect">
      <summary>🪄 자동 연출·말 다듬기 <span class="hint">— 첫 3초 티저 · 추임새 컷 · 반복 정리</span></summary>
      <div class="chk" style="gap:8px;margin-top:6px">
        <label class="chk" style="cursor:pointer" title="가장 궁금한 순간 2~3초를 맨 앞에 잠깐 보여주고 본편 시작 — 첫 3초 이탈을 막는 편집 공식">
          <input type="checkbox" id="editColdOpen"> ⚡ 첫 3초 티저 (콜드오픈)</label>
        <span class="hint">— 하이라이트를 맨 앞에 슬쩍 보여주고 시작해요 (내레이션과는 함께 안 돼요)</span>
      </div>
      <div class="chk" style="gap:8px;margin-top:6px">
        <label class="chk" style="cursor:pointer" title='말 사이에 홀로 나온 "어", "음", "그니까" 같은 추임새를 영상에서 자동으로 잘라냅니다 (내장 Whisper 자막일 때)'>
          <input type="checkbox" id="editFillerCut"> 🧹 추임새("어·음") 자동 컷</label>
        <label class="chk" style="cursor:pointer" title="같은 말을 연달아 다시 말한 NG 테이크를 감지해 마지막 테이크만 남깁니다 (검토 화면에서는 ↻ 배지로 표시)">
          <input type="checkbox" id="editTakeClean"> ↻ 반복 말하기(NG) 정리</label>
        <span class="hint">— 촬영 후 가편집을 자동으로 (Whisper 자막 추천)</span>
      </div>
    </details>

    <details class="opt" id="optHook">
      <summary>🪝 상단 제목 넣기 <span class="hint">— 화면 위에 크게 박히는 한 줄 (AI 추천·색·글씨 스타일)</span></summary>
      <div style="display:flex;gap:6px;margin-top:4px">
        <input type="text" id="editHookTopic" style="flex:1" placeholder="① 주제 키워드 입력 (예: 블로그 자동화) → AI 추천을 받거나, 아래에 직접 쓰세요">
        <button class="ghost" style="white-space:nowrap" onclick="suggestHooks(event,'editHookTopic','editHook')">✨ AI 제목 추천</button>
      </div>
      <div id="editHookCands" class="hookcands"></div>
      <textarea id="editHook" style="min-height:56px;margin-top:6px" oninput="renderHookPreview()" placeholder="② 제목 확정 — 추천을 누르면 여기 채워져요 / 직접 써도 됩니다 (줄바꿈은 Enter)"></textarea>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px" id="hookStudio">
        <span class="hint">색: <b>드래그로 선택</b>하거나 단어에 커서 두고 →</span>
        <span id="hookColorChips"></span>
        <button class="ghost" style="padding:4px 8px" onclick="clearHookMarkup(event,'editHook')">색 지우기</button>
        <span class="hint" style="margin-left:6px">· 크기</span>
        <select id="hookSizeSel" style="width:auto;padding:4px 8px" onchange="renderHookPreview()">
          <option value="0.85">작게</option>
          <option value="1" selected>기본</option>
          <option value="1.2">크게</option>
          <option value="1.4">아주 크게</option>
        </select>
        <span class="hint">· 글씨 스타일</span>
        <select id="hookStyleSel" style="width:auto;padding:4px 8px" onchange="renderHookPreview()">
          <option value="기본" selected>기본 (흰 글자+띠)</option>
          <option value="예능 노랑">예능 노랑 (노랑+검정 테두리)</option>
          <option value="화이트 박스">화이트 박스 (흰 띠+검정 글자)</option>
          <option value="네온">네온 (민트 글로우)</option>
          <option value="다색 팝">다색 팝 (문장마다 색+흰테두리)</option>
          <option value="블랙 박스">블랙 박스 (검은 띠+흰 글자)</option>
        </select>
        <span style="margin-left:6px">글씨체</span>
        <select id="editHookFontSel" class="fontsel" style="width:auto;padding:4px 8px" onchange="renderHookPreview()">
          <option value="">기본 (프리텐다드)</option>
          <option value="BlackHanSans-Regular">블랙한산스 — 임팩트 굵은</option>
          <option value="Jua-Regular">주아 — 둥근 포근</option>
          <option value="DoHyeon-Regular">도현 — 각진 고딕</option>
          <option value="Gugi-Regular">구기 — 레트로</option>
          <option value="NanumPenScript-Regular">나눔손글씨 펜 — 손글씨</option>
        </select>
        <label style="display:flex;gap:5px;align-items:center;cursor:pointer">
          <input type="checkbox" id="editHookTiltChk"> 비스듬히</label>
      </div>
      <div id="hookPreview" style="margin-top:6px;border-radius:10px;background:#14161c;border:1px solid #2c3350;padding:18px 10px;text-align:center;display:none"></div>
      <div class="hint">숫자는 자동으로 노랗게 강조돼요. 직접 표시하려면 <b>| 단어</b>(강조)나 <b>[노랑]글자[/]</b>(색)도 됩니다.</div>
      <label class="chk" style="margin-top:6px;cursor:pointer" title="영상 맨 앞에서 성우가 이 제목을 읽어주고 시작 — 전문 채널 같은 오프닝">
        <input type="checkbox" id="editHookVoice"> 🎙 후킹 보이스 <span class="hint">— 이 제목을 성우(위 내레이션 목소리)가 읽으며 시작해요</span></label>
    </details>

    <details class="opt" id="optNarr">
      <summary>🎙️ 내레이션 (해설 목소리) <span class="hint">— AI가 대본 쓰고 읽거나, 내가 녹음한 파일을 통째로</span></summary>
      <div class="chk" style="gap:14px;margin-top:4px;flex-wrap:wrap">
        <label style="display:flex;gap:6px;align-items:center;cursor:pointer">
          <input type="radio" name="narrMode" value="ai" checked onchange="onNarrModeChange()"> ✍ AI가 대본 쓰고 읽기</label>
        <label style="display:flex;gap:6px;align-items:center;cursor:pointer">
          <input type="radio" name="narrMode" value="file" onchange="onNarrModeChange()"> 🎤 내가 녹음한 파일 넣기</label>
      </div>
      <div id="narrFileBox" class="hidden">
        <div style="display:flex;gap:6px;margin-top:6px">
          <input type="text" id="narrFile" placeholder="녹음 파일 (mp3 · m4a · wav · aac …) — 폰 녹음 파일 그대로 OK" style="flex:1">
          <button class="ghost" style="white-space:nowrap" onclick="pickInto(event,'narrFile','audio')">🎵 녹음 파일 고르기</button>
        </div>
        <div class="hint">녹음이 <b>영상 목소리로 통째로</b> 들어가요 (원본 소리는 자동 무음, 아래 🎵 소리에서 변경 가능).
          자막은 녹음을 음성 인식해 자동으로 만들고, 읽은 글을 「📝 대본 직접 넣기」에 붙여넣으면 <b>그 글자 그대로</b> 자막이 돼 더 정확해요.
          영상·사진 길이는 녹음 길이에 자동으로 맞춰집니다.</div>
      </div>
      <div id="narrAiBox">
      <input type="text" id="narrTopic" oninput="onNarrTopicInput()" placeholder="영상 주제/내용 입력 (예: 동네 라멘 맛집 소개) — 비우면 사용 안 함">
      <div class="chk" style="margin-top:6px">
        <input type="checkbox" id="narrAnalyzeChk" onchange="onNarrTopicInput()">
        <span>🧠 <b>화면을 보고 대본 자동 작성</b> (무음·시연 영상용) — AI가 영상 장면을 분석해 위 주제에 맞춰 대본을 써요 <span class="hint">(제미나이 키 필요)</span></span>
      </div>
      <div id="narrAnalyzeLenBox" class="hidden" style="margin:6px 0 2px 22px;padding:8px 10px;border:1px solid #2c3350;border-radius:8px">
        <div class="chk" style="gap:14px;flex-wrap:wrap">
          <label style="display:flex;gap:5px;align-items:center;cursor:pointer">
            <input type="radio" name="narrLen" value="summary" checked onchange="onNarrLenChange()"> ✂ 요약(짧게)</label>
          <span id="narrLenSecBox">
            길이 <select id="narrLenSec" style="width:auto;padding:4px 8px">
              <option value="30">약 30초</option>
              <option value="60" selected>약 1분</option>
              <option value="120">약 2분</option>
              <option value="180">약 3분</option>
            </select>
          </span>
          <label style="display:flex;gap:5px;align-items:center;cursor:pointer">
            <input type="radio" name="narrLen" value="full" onchange="onNarrLenChange()"> 📼 원본 길이 그대로(전체 내레이션)</label>
        </div>
        <div class="hint" id="narrLenHint" style="margin-top:4px">긴 영상을 짧게 요약해요 — 8분 영상도 고른 길이로 추립니다. (원본 길이는 문장·목소리 합성이 많아 시간·API를 더 써요)</div>
      </div>
      <div class="row" style="margin-top:8px">
        <div>
          <label>목소리(보이스)</label>
          <select id="narrVoiceSel" onchange="updateFavBtns()"></select>
        </div>
        <div>
          <label>말투 스타일</label>
          <select id="narrStyleSel"></select>
        </div>
        <div style="display:flex;align-items:flex-end;gap:6px">
          <button class="ghost" style="margin-bottom:1px" onclick="previewNarrVoice(event)">🔊 미리듣기</button>
          <button class="ghost" id="narrFavBtn" style="margin-bottom:1px" title="이 일레븐랩스 성우를 즐겨찾기 — 목록 맨 위 고정" onclick="toggleElevenFav(event,'narr')">☆</button>
          <button class="ghost" style="margin-bottom:1px" title="일레븐랩스 성우 목록 새로고침" onclick="loadElevenVoices(true);return false">🔄</button>
        </div>
      </div>
      <div class="hint" id="narrElevenState"></div>
      <details id="narrBrowse" class="opt" ontoggle="onNarrBrowse(this)">
        <summary>🇰🇷 한국어 성우 담기 <span class="hint">— 여기서 듣고 ➕ 담기 (담기 무료 · 제작 사용은 Starter부터)</span></summary>
        <div class="hint" id="narrBrowseState" style="margin-top:6px"></div>
        <div id="narrBrowseList" style="max-height:300px;overflow-y:auto;margin-top:6px"></div>
      </details>
      <div class="chk" style="margin-top:6px">
        <input type="checkbox" id="narrSubsOnly" onchange="onNarrTopicInput()">
        <span>🔇 목소리는 빼고 <b>자막만</b> 넣기 (AI가 쓴 대본을 하단 자막으로만)</span>
      </div>
      </div>
      <div class="chk" style="gap:8px">
        <span class="hint">내레이션(녹음)이 영상보다 길면</span>
        <select id="narrFitSel" style="width:auto;padding:6px 8px">
          <option value="freeze" selected>⏸ 마지막 장면 정지로 늘려 다 담기 (추천)</option>
          <option value="loop">🔁 영상을 처음부터 반복해 다 담기</option>
          <option value="drop">✂ 말 속도 올리고 뒷문장 생략 (예전 방식)</option>
        </select>
      </div>
      <div class="hint">넣으면 AI가 대본을 쓰고 목소리(제미나이 키 권장, 없으면 내장 음성)를 입혀요. 보이스·말투는 제미나이 키가 있을 때 적용(내장 음성은 목소리 고정). 대본은 검토 화면에서 수정 가능.</div>
      <div class="chk" style="gap:8px">
        <span class="hint">내 목소리로 읽게 하고 싶다면 →</span>
        <button class="ghost" style="padding:5px 10px" onclick="openVoice(event)">🎤 내 목소리 등록</button>
        <b class="hint" id="myVoiceStateNarr"></b>
      </div>
    </details>

    <details class="opt" id="optSound">
      <summary>🎵 소리·배경음악 <span class="hint">— 원본 소리 조절 · BGM 넣기 · 잡음 제거</span></summary>
      <div class="chk" style="gap:8px;margin-top:4px">
        <span>🔈 원본 소리</span>
        <select id="origAudioSel" style="width:auto;padding:6px 8px" onchange="window._origTouched=true">
          <option value="keep">그대로</option>
          <option value="low">작게 (배경으로)</option>
          <option value="mute">무음 (소리 제거)</option>
        </select>
        <span class="hint">영상 속 말소리·소음을 뺄 때 '무음' — AI 내레이션을 넣으면 자동으로 무음이 돼요</span>
      </div>
      <div class="chk" style="gap:8px">
        <span>🎵 배경음악</span>
        <select id="bgmEditSel" style="width:auto;max-width:220px;padding:6px 8px">
          <option value="">없음</option>
        </select>
        <select id="bgmVolSel" style="width:auto;padding:6px 8px">
          <option value="-20">은은하게</option>
          <option value="-14" selected>중간</option>
          <option value="-9">크게</option>
        </select>
        <button class="ghost" style="padding:6px 10px" onclick="previewBgm(event,'bgmEditSel','bgmVolSel')">▶ 미리듣기</button>
        <span class="hint">영상 길이만큼 반복+페이드. <b>windows\\6_무료음원_받기.bat</b>로 유명 무료 BGM 14곡 자동 채우기</span>
      </div>
      <div class="chk" style="gap:8px">
        <span>🔇 잡음 제거</span>
        <select id="denoiseSel" style="width:auto;padding:6px 8px">
          <option value="">끔</option>
          <option value="low">약하게</option>
          <option value="mid">중간 (권장)</option>
          <option value="high">강하게</option>
        </select>
        <span class="hint">배경 잡음·히스·웅웅거림 줄이기 (목소리는 살림)</span>
      </div>
    </details>

    <details class="opt" id="optFx">
      <summary>🎬 전환 효과 <span class="hint">— 장면·사진이 바뀔 때 부드럽게</span></summary>
      <div class="chk" style="gap:8px;margin-top:4px">
        <span>장면이 바뀔 때</span>
        <select id="transSel" style="width:auto;padding:6px 8px">
          <option value="none" selected>그냥 컷 (기본)</option>
          <option value="fade">페이드 — 살짝 어두워졌다 밝아지며</option>
        </select>
      </div>
      <div class="hint">사진 슬라이드, 핵심 구간·몽타주·여러 쇼츠로 나눌 때 구간 경계에 적용돼요.
        영상 길이와 자막 싱크는 그대로 유지됩니다. (무음 컷 경계에는 넣지 않아요 — 말 흐름 유지)</div>
      <div class="hint">🎞 인트로/아웃트로는 ⚙ 설정 → 「내 채널 정보·브랜딩」에 파일을 넣으면 모든 완성 영상에 자동으로 붙어요.</div>
    </details>

    <details class="opt" id="optWm">
      <summary>🏷️ 워터마크(로고) <span class="hint">— 내 채널 로고를 화면 구석에</span></summary>
      <div class="chk" style="gap:8px;margin-top:4px">
        <input type="text" id="wmPath" style="flex:1;min-width:180px;padding:6px 8px" placeholder="로고 이미지 경로 (투명 PNG 권장) — 비우면 없음">
        <select id="wmPos" style="width:auto;padding:6px 8px">
          <option value="tr">우상단</option>
          <option value="tl">좌상단</option>
          <option value="br">우하단</option>
          <option value="bl">좌하단</option>
        </select>
        <select id="wmScale" style="width:auto;padding:6px 8px">
          <option value="0.10">작게</option>
          <option value="0.14" selected>중간</option>
          <option value="0.20">크게</option>
        </select>
      </div>
      <div class="hint">한 번 넣으면 기억돼요. 쇼츠 UI 안전영역을 피해 배치됩니다.</div>
    </details>

    <details class="opt" id="optScript">
      <summary>📝 대본 직접 넣기 <span class="hint">— 써둔 대본이 있으면 음성 인식 없이 그대로 자막으로</span></summary>
      <textarea id="editScript" oninput="onScriptInput()" style="min-height:64px"
        placeholder="대본이 있으면 여기 붙여넣기 (한 줄 = 자막 한 줄)&#10;예)&#10;오늘은 라멘 맛집을 소개합니다&#10;가격은 육천구백원이에요&#10;&#10;비우면 영상 소리에서 자동으로 자막을 인식합니다"></textarea>
      <div class="hint" id="scriptHint">붙여넣으면 <b>음성 인식을 건너뛰고</b> 이 대본을 영상 타이밍에 맞춰 자막으로 넣어요 (오인식·비용 없음). 내레이션 없는 영상에도 쓸 수 있어요.</div>
      <label class="chk" style="gap:8px">
        <input type="checkbox" id="scriptTtsChk">
        <span>🔊 <b>이 대본을 AI 목소리로 읽어주기</b> <span class="hint">— 사진 영상·무음 영상에 내레이션을 입혀요. 목소리는 🎙️ AI 내레이션의 보이스 선택을 따라요 (주제 입력·녹음 내레이션과 함께는 안 돼요)</span></span>
      </label>
    </details>

    <details class="opt" id="optAdv">
      <summary>⚙️ 세부 설정 <span class="hint">— 화면 비율 · 자동 자막/무음 컷 · 음성 인식 엔진</span></summary>
      <div class="chk" style="gap:8px;flex-wrap:wrap;margin-top:6px">
        <span>🎨 감성 테마</span>
        <select id="editThemeSel" style="width:auto;padding:6px 8px" onchange="applyTheme('edit')">
          <option value="">직접 고르기</option>
          <option value="insta">📸 인스타 감성</option>
          <option value="tiktok">🎵 틱톡 감성</option>
          <option value="youtube">▶ 유튜브 예능</option>
          <option value="cinema">🎬 시네마틱</option>
        </select>
        <span class="hint">— 자막 스타일·색감·등장·위치를 한 번에 (틱톡은 말하는 단어가 차오르는 하이라이트)</span>
      </div>
      <div style="margin-top:6px">
        <span>💬 자막 글씨 스타일 <span class="hint">— 보이는 그대로 들어가요 (강조색 자동 조정, 기억됨)</span></span>
        <select id="editSubStyleSel" class="hidden">
          <option value="기본" selected>기본 (흰 글자+검정 테두리)</option>
          <option value="예능 노랑">예능 노랑 (노랑+검정 테두리)</option>
          <option value="말풍선 띠">말풍선 띠 (흰 띠+검정 글자)</option>
          <option value="네온">네온 (민트 글로우)</option>
          <option value="다색 팝">다색 팝 (문장마다 색+흰테두리)</option>
          <option value="블랙 박스">블랙 박스 (검은 띠+흰 글자)</option>
        </select>
        <div class="stylechips" data-for="editSubStyleSel">
          <div class="stylechip sel" data-v="기본" onclick="pickStyleChip('editSubStyleSel','기본',event)"
               style="color:#fff;text-shadow:-1.5px -1.5px 0 #000,1.5px -1.5px 0 #000,-1.5px 1.5px 0 #000,1.5px 1.5px 0 #000,0 2px 3px #000">기본 자막</div>
          <div class="stylechip" data-v="예능 노랑" onclick="pickStyleChip('editSubStyleSel','예능 노랑',event)"
               style="color:#ffd400;text-shadow:-1.5px -1.5px 0 #000,1.5px -1.5px 0 #000,-1.5px 1.5px 0 #000,1.5px 1.5px 0 #000,0 2px 3px #000">예능 노랑</div>
          <div class="stylechip" data-v="말풍선 띠" onclick="pickStyleChip('editSubStyleSel','말풍선 띠',event)"
               style="background:#f4f5f8;color:#15161c;border-radius:999px">말풍선 띠</div>
          <div class="stylechip" data-v="네온" onclick="pickStyleChip('editSubStyleSel','네온',event)"
               style="color:#7dffd4;text-shadow:0 0 8px rgba(125,255,212,.95),0 0 18px rgba(125,255,212,.55)">네온 글로우</div>
          <div class="stylechip" data-v="다색 팝" onclick="pickStyleChip('editSubStyleSel','다색 팝',event)"
               style="text-shadow:-1.5px -1.5px 0 #fff,1.5px -1.5px 0 #fff,-1.5px 1.5px 0 #fff,1.5px 1.5px 0 #fff,0 2px 4px #000"><span style="color:#FF3B30">다색</span> <span style="color:#31E1C4">팝</span></div>
          <div class="stylechip" data-v="블랙 박스" onclick="pickStyleChip('editSubStyleSel','블랙 박스',event)"
               style="background:#121212;color:#fff;border-radius:6px">블랙 박스 <span style="color:#FFD400">강조</span></div>
        </div>
      </div>
      <div class="chk" style="gap:8px;margin-top:6px">
        <span>글씨체</span>
        <select id="editSubFontSel" class="fontsel" style="width:auto;padding:4px 8px" onchange="renderSubFontPrev('editSubFontSel','editSubFontPrev')">
          <option value="">기본 (프리텐다드)</option>
          <option value="BlackHanSans-Regular">블랙한산스 — 임팩트 굵은</option>
          <option value="Jua-Regular">주아 — 둥근 포근</option>
          <option value="DoHyeon-Regular">도현 — 각진 고딕</option>
          <option value="Gugi-Regular">구기 — 레트로</option>
          <option value="NanumPenScript-Regular">나눔손글씨 펜 — 손글씨</option>
        </select>
        <span class="hint">본문 자막 글씨체 (기억됨)</span>
      </div>
      <div id="editSubFontPrev" style="margin-top:6px;padding:10px 12px;border-radius:10px;background:#14161c;border:1px solid #2c3350;font-size:26px;font-weight:800;text-align:center">가나다 라마바 ABC 12 — 자막 미리보기</div>
      <div style="margin-top:8px">
        <span>🎨 화면 톤(색보정) <span class="hint">— 같은 장면이 이렇게 달라져요 (자막·제목 글자는 원색 유지)</span></span>
        <select id="editToneSel" class="hidden">
          <option value="기본" selected>기본 (보정 없음)</option>
          <option value="시네마틱">시네마틱 (영화 느낌 틸·오렌지)</option>
          <option value="화사">화사 (밝고 쨍한 브이로그)</option>
          <option value="선명">선명 (대비·채도·샤픈 업)</option>
          <option value="흑백">흑백 (드라마틱)</option>
        </select>
        <div class="tonerow" data-for="editToneSel"><div class="tonecard sel" data-v="기본" onclick="pickToneCard('editToneSel','기본',event)"
               title="기본"><div class="sw" style="filter:none"></div><span>기본</span></div><div class="tonecard" data-v="시네마틱" onclick="pickToneCard('editToneSel','시네마틱',event)"
               title="시네마틱"><div class="sw" style="filter:sepia(.30) saturate(1.35) contrast(1.08) hue-rotate(-8deg)"></div><span>시네마틱</span></div><div class="tonecard" data-v="화사" onclick="pickToneCard('editToneSel','화사',event)"
               title="화사"><div class="sw" style="filter:brightness(1.16) saturate(1.18)"></div><span>화사</span></div><div class="tonecard" data-v="선명" onclick="pickToneCard('editToneSel','선명',event)"
               title="선명"><div class="sw" style="filter:contrast(1.3) saturate(1.4)"></div><span>선명</span></div><div class="tonecard" data-v="흑백" onclick="pickToneCard('editToneSel','흑백',event)"
               title="흑백"><div class="sw" style="filter:grayscale(1) contrast(1.1)"></div><span>흑백</span></div></div>
      </div>
      <div class="row" style="margin-top:4px">
        <div>
          <label>출력 형태</label>
          <div class="toggle">
            <label><input type="radio" name="editLayout" value="shorts" checked><span>쇼츠 (세로 9:16)</span></label>
            <label><input type="radio" name="editLayout" value="wide"><span>가로 (16:9)</span></label>
            <label><input type="radio" name="editLayout" value="keep"><span>원본 비율 유지</span></label>
          </div>
          <span class="hint hidden" id="layoutAutoHint"></span>
        </div>
        <div>
          <label>음성 인식 엔진</label>
          <select id="sttSel"></select>
          <div class="hint" id="sttHint"></div>
          <div id="whisperModelRow" class="hidden" style="margin-top:6px">
            <label style="margin-top:0">정확도(Whisper 모델)</label>
            <select id="whisperModelSel">
              <option value="tiny">tiny — 가장 빠름·정확도 낮음</option>
              <option value="base">base — 빠름</option>
              <option value="small" selected>small — 기본(권장)</option>
              <option value="medium">medium — 느림·정확도↑</option>
              <option value="large-v3">large-v3 — 가장 느림·최고 정확도</option>
            </select>
            <div class="hint">클수록 정확하지만 느리고, 첫 사용 시 모델 다운로드가 큽니다.</div>
          </div>
        </div>
      </div>
      <div class="chk" style="margin-top:10px">
        <input type="checkbox" id="autoSubChk" checked onchange="toggleAutoSub()">
        <span>자동 자막 만들기 (말한 내용을 자막으로) — <b>내레이션 없는 영상은 체크 해제</b></span>
      </div>
      <div class="chk">
        <input type="checkbox" id="cutSilenceChk" checked>
        <span>무음(빈) 구간 자동 컷 — 끄면 원본 길이 그대로</span>
      </div>
      <div id="editKeyRow" class="hidden">
        <label>Gemini API 키 <span class="hint">(<a href="https://aistudio.google.com/apikey" target="_blank" style="color:#7a9bff">무료 발급</a>)</span></label>
        <input type="password" id="editGeminiKey" placeholder="AIza...">
      </div>
    </details>

    <div class="hint" style="margin-top:14px">그냥 [만들기 시작]만 눌러도 충분해요 — 빈(무음) 구간을 잘라내고, 말한 내용을 자막으로 붙이고, 가로 영상은 세로 쇼츠로 자동 배치합니다.</div>
    <div style="display:flex;gap:8px">
      <button id="editBtn" style="flex:1" onclick="startEditSafe()">✂️ 만들기 시작</button>
      <button class="ghost" style="white-space:nowrap" onclick="resetEditForm(event)" title="편집 폼의 모든 입력을 기본값으로 되돌립니다">↺ 초기화</button>
    </div>
  </div>

  <div class="card hidden" id="voiceCard">
    <div class="backrow">
      <button class="ghost" onclick="closeVoice(event)">← 돌아가기</button>
      <b>🎤 내 목소리 등록 <span class="hint" id="myVoiceState"></span></b>
    </div>
    <div class="hint" style="margin-top:10px;font-size:13px;color:#cdd3e0">
      내 목소리를 녹음한 파일로 <b>"나만의 AI 목소리"</b>를 만들어요. 한 번 등록하면
      🤖 AI 영상 만들기의 목소리와 🎙️ AI 내레이션의 보이스 목록에 <b>「🎤 내 목소리」</b>가 생기고,
      그걸 고르면 AI가 쓴 대본을 <b>내 목소리로</b> 읽어줍니다. 두 가지 방법 중 하나만 하면 돼요.
    </div>

    <div style="margin-top:12px;padding:10px 12px;border:1px solid #2c3350;border-radius:10px">
      <b style="font-size:14px">방법 A — 무료 · 내 PC에서 (GPT-SoVITS)</b>
      <span class="hint">5~10초 녹음이면 시작. 프로그램을 켜두면 무제한 무료. 설치법은 카페가이드 Q12</span>
      <div class="row" style="margin-top:6px">
        <div>
          <label>참조 녹음 (5~10초, 깨끗하게)</label>
          <div style="display:flex;gap:6px">
            <input type="text" id="sovitsRef" style="flex:1" placeholder="예) C:\\Users\\me\\참조녹음.wav">
            <button class="ghost" style="white-space:nowrap;padding:6px 10px" onclick="pickInto(event,'sovitsRef','audio')">📁</button>
          </div>
        </div>
        <div>
          <label>그 녹음에서 말한 문장</label>
          <input type="text" id="sovitsRefText" placeholder="예) 안녕하세요 곰대리입니다 오늘도 좋은 하루 보내세요">
        </div>
        <div style="display:flex;align-items:flex-end;gap:6px">
          <button class="ghost" style="margin-bottom:1px" onclick="saveSovits(event)">등록(저장)</button>
          <button class="ghost" style="margin-bottom:1px" onclick="previewMyVoice(event,'sovits')">🔊 미리듣기</button>
        </div>
      </div>
      <div class="hint">GPT-SoVITS 통합패키지의 API 서버(api_v2, 127.0.0.1:9880)를 켜두면 학습 없이(zero-shot) 바로 내 목소리가 나와요. 더 똑같이 만들고 싶으면 GPT-SoVITS에서 한 번만 학습하면 됩니다.</div>
    </div>

    <div style="margin-top:10px;padding:10px 12px;border:1px solid #2c3350;border-radius:10px">
      <b style="font-size:14px">방법 B — 유료 · 간편 (ElevenLabs, 월 $6)</b>
      <span class="hint">설치 없이 인터넷만 있으면 됨. 품질 안정적</span>
      <div class="row" style="margin-top:6px">
        <div>
          <label>녹음 파일 (1~3분 낭독, mp3/wav/m4a)</label>
          <div style="display:flex;gap:6px">
            <input type="text" id="cloneFile" style="flex:1" placeholder="예) C:\\Users\\me\\내녹음.mp3">
            <button class="ghost" style="white-space:nowrap;padding:6px 10px" onclick="pickInto(event,'cloneFile','audio')">📁</button>
          </div>
        </div>
        <div>
          <label>ElevenLabs API 키</label>
          <input type="password" id="elevenKey" placeholder="elevenlabs.io 발급 키">
        </div>
        <div style="display:flex;align-items:flex-end;gap:6px">
          <button class="ghost" style="margin-bottom:1px" onclick="cloneVoice(event)">등록</button>
          <button class="ghost" style="margin-bottom:1px" onclick="previewMyVoice(event,'elevenlabs')">🔊 미리듣기</button>
        </div>
      </div>
      <div class="hint">조용한 곳에서 또박또박 1~3분 읽은 녹음이면 충분해요. 한 번 등록하면 저장됩니다. ⚠ 클로닝은 ElevenLabs <b>유료 구독(Starter, 월 $6)</b>부터 지원.</div>
      <div class="hint" style="margin-top:6px;line-height:1.7">🧭 <b>처음이라면 이 순서대로</b>:<br>
        ① <a href="https://elevenlabs.io" target="_blank" style="color:#7a9bff">elevenlabs.io</a> 가입 → 오른쪽 위 내 계정 → <b>Subscription</b>에서 Starter(월 $6) 구독<br>
        ② <a href="https://elevenlabs.io/app/settings/api-keys" target="_blank" style="color:#7a9bff">API Keys 페이지</a>에서 <b>Create API Key</b> → 복사해 위의 「ElevenLabs API 키」 칸에 붙여넣기<br>
        ③ [📁]로 내 녹음 파일 선택 → <b>[등록]</b> → 🔊 미리듣기로 확인 (녹음 없이 <b>성우 목소리</b>만 쓰려면 ①②만 하면 돼요 —
        <a href="https://elevenlabs.io/app/voice-library" target="_blank" style="color:#7a9bff">Voice Library</a>에서 마음에 드는 보이스를 Add하면 컷대장 목록에 나타납니다)</div>
    </div>

    <div class="guide" style="margin-top:10px">📌 <b>등록 후 사용법</b> — 영상 만들 때 목소리(보이스)에서 「🎤 내 목소리」만 고르면 끝!<br>
      · 🤖 AI 영상 만들기 → ② 목소리 고르기에 「🎤 내 목소리」 버튼이 생겨요<br>
      · ✂️ 내 영상 편집 / 📸 사진으로 영상 → ③ 꾸미기 → 🎙️ AI 내레이션의 보이스 맨 위에 생겨요<br>
      · 방법 A는 만들 때 GPT-SoVITS 서버가 켜져 있어야 하고, 꺼져 있으면 자동으로 다른 목소리로 대체돼요</div>
    <div class="hint" style="margin-top:8px">⚠ 어떤 방식이든 꼭 <b>본인 목소리</b>만 등록하세요 (타인 목소리 무단 클로닝 금지).</div>
  </div>

  <div class="card hidden" id="formCard">
    <div class="backrow">
      <button class="ghost" onclick="showHome(event)">← 처음으로</button>
      <b>🤖 AI 영상 만들기</b>
    </div>

    <div class="steplabel"><span class="stepnum">1</span>영상 주제 쓰기</div>
    <input type="text" id="topic" placeholder="예) 하루 10분 정리 습관" value="하루 10분 정리 습관">
    <div class="hint">이 주제로 AI가 대본을 쓰고 자막·배경·목소리까지 자동으로 만듭니다.</div>
    <div class="chk" style="gap:8px">
      <input type="checkbox" id="batchChk" onchange="onBatchChange()">
      <span>📦 <b>여러 개 한 번에(배치)</b> — 주제를 여러 줄 넣으면 줄 수만큼 영상이 나와요</span>
    </div>
    <textarea id="topicBatch" class="hidden" style="min-height:96px" placeholder="한 줄 = 영상 1개 (최대 20개)&#10;예)&#10;하루 10분 정리 습관&#10;아침 루틴 꿀팁 3가지&#10;퇴근 후 부업 시작하는 법"></textarea>
    <div class="hint hidden" id="batchHint">배치는 검토 없이 자동으로 연속 완성돼요. 고른 목소리·배경음악·설정이 전부 똑같이 적용됩니다.
      대본으로 만들려면 아래 「📝 대본 직접 넣기」에 대본 여러 벌을 <b>=== 줄로 구분</b>해 넣으세요 (한 벌 = 영상 1개).</div>
    <div class="chk" style="gap:8px;flex-wrap:wrap;margin-top:8px">
      <span>📇 제품</span>
      <select id="genProductSel" style="width:auto;min-width:150px" onchange="onGenProductChange()">
        <option value="">없음 (일반 주제)</option>
      </select>
      <button class="ghost" style="padding:4px 10px;font-size:12.5px" onclick="toggleProductCard()">📇 관리</button>
      <span class="hint">제품을 고르면 등록한 사실만 근거로 대본·훅·키트를 써요</span>
    </div>
    <details class="opt" style="margin-top:6px">
      <summary>📎 이번 영상 참고 메모 <span class="hint">— 이번 편에만 쓸 추가 정보 (선택)</span></summary>
      <textarea id="genContext" style="min-height:72px" placeholder="예) 이번 편은 신기능 '자동 자막' 위주로. 이벤트: 7월 말까지 30% 할인"></textarea>
    </details>
    <div class="chk" style="gap:10px;flex-wrap:wrap;margin-top:8px">
      <span>화면</span>
      <div class="toggle" style="margin:0">
        <label><input type="radio" name="genOrient" value="shorts" checked><span>📱 세로 쇼츠 (9:16)</span></label>
        <label><input type="radio" name="genOrient" value="reels"><span>📲 인스타·틱톡 (9:16 특화)</span></label>
        <label><input type="radio" name="genOrient" value="wide"><span>🖥 가로 롱폼 (16:9)</span></label>
      </div>
      <div class="hint" style="margin-top:2px">📲 <b>인스타·틱톡</b>을 고르면 자막이 <b>화면 중앙 + 타이핑</b>으로 등장하고 <b>다색 팝</b> 스타일이 자동 적용돼요 (릴스·틱톡 감성). 자막 스타일을 직접 고르면 그게 우선.</div>
      <span style="margin-left:6px">길이</span>
      <select id="genLenSel" style="width:auto;padding:6px 8px" onchange="onGenLenChange()">
        <option value="30">약 30초</option>
        <option value="45">약 45초</option>
        <option value="60" selected>약 1분 (기본)</option>
        <option value="90">약 1분 30초</option>
        <option value="120">약 2분</option>
        <option value="180">약 3분</option>
        <option value="300">약 5분</option>
        <option value="custom">직접 입력…</option>
      </select>
      <span id="genLenCustomBox" class="hidden" style="margin-left:4px">
        <input type="number" id="genLenCustomMin" min="1" max="15" step="0.5" value="7"
               style="width:64px;padding:6px 8px"> 분
      </span>
      <span class="hint">길이는 AI 대본 분량 기준(말 속도에 따라 조금 달라져요) — 대본을 직접 넣으면 그 분량대로</span>
      <div class="hint" style="margin-top:4px">💡 기본을 5분까지만 둔 이유: 더 길면 AI 대본이 반복·빈약해지고, 문장마다 목소리(TTS)를 만들어 시간·비용이 커져요. 더 필요하면 [직접 입력]으로 최대 15분까지 — 이땐 대본을 직접 넣는 걸 권장해요.</div>
    </div>
    <details class="opt" style="margin-top:8px">
      <summary>📝 대본 직접 넣기 <span class="hint">— 써둔 대본이 있으면 AI 대본 대신 그대로 (한 줄 = 자막 하나)</span></summary>
      <textarea id="genScript" style="min-height:110px" placeholder="한 줄이 자막 한 개가 돼요. 비워두면 주제로 AI가 대본을 씁니다.&#10;[노랑]강조할 말[/노랑] 처럼 색을 직접 칠할 수도 있어요 (색: 노랑·빨강·초록·파랑·주황·분홍·하늘·민트·보라).&#10;줄이 많을수록 목소리 합성(TTS)도 그만큼 늘어나요."></textarea>
      <div class="hint">넣으면 영상 길이는 대본 분량대로(위 길이 설정은 무시), 주제는 제목·훅에만 쓰여요.
        「📦 배치」와 함께 쓰면 <b>=== 줄로 구분한 대본 한 벌마다 영상 1개</b>가 나와요 (첫 줄이 제목).</div>
    </details>

    <div class="steplabel"><span class="stepnum">2</span>목소리 고르기</div>
    <div class="toggle">
      <label><input type="radio" name="prov" value="gemini" checked><span>🌟 AI 성우 (추천)</span></label>
      <label id="provWinLabel" class="hidden"><input type="radio" name="prov" value="windows" id="provWin"><span>내장 음성 (무료)</span></label>
      <label id="provMineLabel" class="hidden"><input type="radio" name="prov" value="elevenlabs" id="provMine"><span>🎤 내 목소리</span></label>
      <label id="provElevenLabel"><input type="radio" name="prov" value="eleven_voice" id="provEleven" onclick="checkElevenProv(event)"><span>🎙 일레븐랩스 성우</span></label>
      <label id="provSovitsLabel" class="hidden"><input type="radio" name="prov" value="sovits" id="provSovits"><span>🎤 내 목소리 (무료·내 PC)</span></label>
    </div>
    <div class="hint">여기서는 <b>목소리만</b> 골라요 — 대본·자막·배경은 뭘 고르든 컷대장이 알아서 만듭니다.</div>
    <div class="chk" style="gap:8px">
      <span class="hint">내 목소리(녹음으로 만든 AI 목소리)로 만들고 싶다면 →</span>
      <button class="ghost" style="padding:5px 10px" onclick="openVoice(event)">🎤 내 목소리 등록</button>
    </div>

    <div id="keyRow" class="hidden">
      <label>Gemini API 키 <span class="hint">(<a href="https://aistudio.google.com/apikey" target="_blank" style="color:#7a9bff">무료 발급</a>)</span></label>
      <input type="password" id="geminiKey" placeholder="AIza...">
      <div class="chk" style="margin-top:8px">
        <input type="checkbox" id="saveKeyChk" checked>
        <span>이 PC에 저장 (다음부터 입력 생략 — 파일로 저장되니 공용 PC에서는 해제)</span>
      </div>
    </div>
    <div id="keySaved" class="hidden hint" style="margin-top:8px">
      🔑 저장된 Gemini 키 사용 중 — <a href="#" onclick="clearKeys(event)" style="color:#ff9aa6">키 삭제</a>
    </div>

    <div id="geminiOpts" class="hidden">
      <div class="row">
        <div>
          <label>보이스</label>
          <select id="voiceSel"></select>
        </div>
        <div>
          <label>말투 스타일</label>
          <select id="styleSel"></select>
        </div>
        <div style="display:flex;align-items:flex-end">
          <button class="ghost" style="margin-bottom:1px" onclick="previewVoice(event)">🔊 미리듣기</button>
        </div>
      </div>
    </div>

    <div id="elevenOpts" class="hidden">
      <div class="row">
        <div>
          <label>일레븐랩스 보이스 <span class="hint">— 내 계정에 담긴 보이스 그대로</span></label>
          <select id="elevenVoiceSel" onchange="updateFavBtns()"></select>
        </div>
        <div style="display:flex;align-items:flex-end;gap:6px">
          <button class="ghost" style="margin-bottom:1px" onclick="previewElevenVoice(event)">🔊 미리듣기</button>
          <button class="ghost" id="elevenFavBtn" style="margin-bottom:1px" title="이 성우를 즐겨찾기 — 목록 맨 위 고정, 다음에도 기억" onclick="toggleElevenFav(event,'gen')">☆ 즐겨찾기</button>
          <button class="ghost" style="margin-bottom:1px" onclick="loadElevenVoices(true);return false">🔄 다시 불러오기</button>
        </div>
      </div>
      <div class="hint" id="elevenListState"></div>
      <details id="elevenBrowse" class="opt" ontoggle="onElevenBrowse(this)">
        <summary>🇰🇷 한국어 성우 담기 <span class="hint">— 여기서 듣고 ➕ 담기 (담기 무료 · 제작 사용은 Starter부터)</span></summary>
        <div class="hint" id="elevenBrowseState" style="margin-top:6px"></div>
        <div id="elevenBrowseList" style="max-height:300px;overflow-y:auto;margin-top:6px"></div>
      </details>
      <div class="hint">글자 수 과금 — 60초 쇼츠 1편 ≈ 300자. 클론 보이스·직접 담은 보이스도 위 목록에 같이 나와요.</div>
    </div>

    <div class="steplabel" style="margin-top:20px"><span class="stepnum">3</span>꾸미기 <span class="hint">— 전부 선택사항. 필요한 줄만 눌러서 펼치세요</span></div>

    <details class="opt">
      <summary>🪝 상단 제목 넣기 <span class="hint">— 비우면 AI가 만든 제목이 자동으로 크게 들어가요</span></summary>
      <button class="ghost" style="margin-top:4px" onclick="suggestHooks(event,'topic','genHook')">✨ AI 제목 추천받기 <span class="hint">(위의 주제로 추천)</span></button>
      <div id="genHookCands" class="hookcands"></div>
      <textarea id="genHook" style="min-height:52px;margin-top:6px" oninput="renderGenHookPreview()" placeholder="추천을 누르면 여기 채워져요 / 직접 쓰려면 여기에 · 비워두면 AI 제목 자동 (줄바꿈 Enter)"></textarea>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px">
        <span class="hint">색: <b>드래그로 선택</b>하거나 단어에 커서 두고 →</span>
        <span id="genHookColorChips"></span>
        <button class="ghost" style="padding:4px 8px" onclick="clearHookMarkup(event,'genHook')">색 지우기</button>
        <span class="hint" style="margin-left:6px">· 글씨 스타일</span>
        <select id="genHookStyleSel" style="width:auto;padding:4px 8px" onchange="renderGenHookPreview()">
          <option value="기본" selected>기본 (흰 글자+띠)</option>
          <option value="예능 노랑">예능 노랑 (노랑+검정 테두리)</option>
          <option value="화이트 박스">화이트 박스 (흰 띠+검정 글자)</option>
          <option value="네온">네온 (민트 글로우)</option>
          <option value="다색 팝">다색 팝 (문장마다 색+흰테두리)</option>
          <option value="블랙 박스">블랙 박스 (검은 띠+흰 글자)</option>
        </select>
      </div>
      <div class="chk" style="gap:8px;flex-wrap:wrap;margin-top:6px">
        <span>글씨체</span>
        <select id="genHookFontSel" class="fontsel" style="width:auto;padding:4px 8px" onchange="renderGenHookPreview()">
          <option value="">기본 (프리텐다드)</option>
          <option value="BlackHanSans-Regular">블랙한산스 — 임팩트 굵은</option>
          <option value="Jua-Regular">주아 — 둥근 포근</option>
          <option value="DoHyeon-Regular">도현 — 각진 고딕</option>
          <option value="Gugi-Regular">구기 — 레트로</option>
          <option value="NanumPenScript-Regular">나눔손글씨 펜 — 손글씨</option>
        </select>
        <label style="display:flex;gap:5px;align-items:center;cursor:pointer">
          <input type="checkbox" id="genHookTiltChk"> 비스듬히 (예능 자막st)</label>
        <button class="ghost" id="fontFetchBtn" style="padding:4px 10px;font-size:12.5px"
                onclick="fetchFonts(event)"
                title="Google Fonts의 무료(OFL) 한글 글씨체 5종을 받아옵니다 (약 8MB) — 영상·상업용 사용 가능">⬇ 무료 글씨체 받기</button>
      </div>
      <div id="genHookPreview" style="margin-top:6px;border-radius:10px;background:#14161c;border:1px solid #2c3350;padding:18px 10px;text-align:center;display:none"></div>
      <label class="chk" style="margin-top:6px;cursor:pointer" title="영상 맨 앞에서 성우가 제목을 읽어주고 시작 — 전문 채널 같은 오프닝">
        <input type="checkbox" id="genHookVoice"> 🎙 후킹 보이스 <span class="hint">— 제목을 성우(고른 목소리)가 읽으며 시작해요 (비우면 AI 제목을 읽음)</span></label>
    </details>

    <details class="opt">
      <summary>💬 자막 글씨 스타일 <span class="hint">— 본문 자막의 글씨 느낌 고르기</span></summary>
      <select id="genSubStyleSel" class="hidden">
        <option value="기본" selected>기본 (흰 글자+검정 테두리)</option>
        <option value="예능 노랑">예능 노랑 (노랑+검정 테두리)</option>
        <option value="말풍선 띠">말풍선 띠 (흰 띠+검정 글자)</option>
        <option value="네온">네온 (민트 글로우)</option>
          <option value="다색 팝">다색 팝 (문장마다 색+흰테두리)</option>
          <option value="블랙 박스">블랙 박스 (검은 띠+흰 글자)</option>
      </select>
      <div class="stylechips" data-for="genSubStyleSel">
          <div class="stylechip sel" data-v="기본" onclick="pickStyleChip('genSubStyleSel','기본',event)"
               style="color:#fff;text-shadow:-1.5px -1.5px 0 #000,1.5px -1.5px 0 #000,-1.5px 1.5px 0 #000,1.5px 1.5px 0 #000,0 2px 3px #000">기본 자막</div>
          <div class="stylechip" data-v="예능 노랑" onclick="pickStyleChip('genSubStyleSel','예능 노랑',event)"
               style="color:#ffd400;text-shadow:-1.5px -1.5px 0 #000,1.5px -1.5px 0 #000,-1.5px 1.5px 0 #000,1.5px 1.5px 0 #000,0 2px 3px #000">예능 노랑</div>
          <div class="stylechip" data-v="말풍선 띠" onclick="pickStyleChip('genSubStyleSel','말풍선 띠',event)"
               style="background:#f4f5f8;color:#15161c;border-radius:999px">말풍선 띠</div>
          <div class="stylechip" data-v="네온" onclick="pickStyleChip('genSubStyleSel','네온',event)"
               style="color:#7dffd4;text-shadow:0 0 8px rgba(125,255,212,.95),0 0 18px rgba(125,255,212,.55)">네온 글로우</div>
          <div class="stylechip" data-v="다색 팝" onclick="pickStyleChip('genSubStyleSel','다색 팝',event)"
               style="text-shadow:-1.5px -1.5px 0 #fff,1.5px -1.5px 0 #fff,-1.5px 1.5px 0 #fff,1.5px 1.5px 0 #fff,0 2px 4px #000"><span style="color:#FF3B30">다색</span> <span style="color:#31E1C4">팝</span></div>
          <div class="stylechip" data-v="블랙 박스" onclick="pickStyleChip('genSubStyleSel','블랙 박스',event)"
               style="background:#121212;color:#fff;border-radius:6px">블랙 박스 <span style="color:#FFD400">강조</span></div>
        </div>
      <div class="chk" style="gap:8px;margin-top:6px">
        <span>글씨체</span>
        <select id="genSubFontSel" class="fontsel" style="width:auto;padding:4px 8px" onchange="renderSubFontPrev('genSubFontSel','genSubFontPrev')">
          <option value="">기본 (프리텐다드)</option>
          <option value="BlackHanSans-Regular">블랙한산스 — 임팩트 굵은</option>
          <option value="Jua-Regular">주아 — 둥근 포근</option>
          <option value="DoHyeon-Regular">도현 — 각진 고딕</option>
          <option value="Gugi-Regular">구기 — 레트로</option>
          <option value="NanumPenScript-Regular">나눔손글씨 펜 — 손글씨</option>
        </select>
        <span class="hint">본문 자막 글씨체 — [⬇ 무료 글씨체 받기]는 상단 제목 그룹에</span>
      </div>
      <div id="genSubFontPrev" style="margin-top:6px;padding:10px 12px;border-radius:10px;background:#14161c;border:1px solid #2c3350;font-size:26px;font-weight:800;text-align:center">가나다 라마바 ABC 12 — 자막 미리보기</div>
      <div class="hint">위 미리보기가 실제 자막 글씨예요 (받은 글씨체만 보여요) — 강조색은 스타일에 맞게 자동, 한 번 고르면 기억</div>
    </details>

    <details class="opt">
      <summary>🎬 자동 연출 <span class="hint">— 감성 테마·효과음·줌·숫자 팝·색감 (전부 자동, 여기서 켜고 끔)</span></summary>
      <div class="chk" style="gap:8px;flex-wrap:wrap">
        <span>🎨 <b>감성 테마</b></span>
        <select id="genThemeSel" style="width:auto;padding:6px 8px" onchange="applyTheme('gen')">
          <option value="">직접 고르기</option>
          <option value="insta">📸 인스타 감성 (타자기 자막+타닥+화사, 자막 가운데)</option>
          <option value="tiktok">🎵 틱톡 감성 (단어 하이라이트+블랙 박스+쨍한 색)</option>
          <option value="youtube">▶ 유튜브 예능 (노랑 자막 팝+선명)</option>
          <option value="cinema">🎬 시네마틱 (차분한 영화 색감)</option>
        </select>
        <span class="hint" id="genThemeHint">— 한 번에 그 느낌으로 (자막 스타일·색감·자막 등장을 묶어 세팅)</span>
      </div>
      <div class="chk" style="gap:8px;flex-wrap:wrap">
        <input type="checkbox" id="genSfxChk" checked>
        <span>🔔 <b>효과음 자동</b> — 눌러서 들어보세요 →</span>
        <button class="ghost" style="padding:4px 10px;font-size:12.5px" onclick="playSfx(event,'pop')">▶ 뿅 (강조)</button>
        <button class="ghost" style="padding:4px 10px;font-size:12.5px" onclick="playSfx(event,'whoosh')">▶ 휙 (장면 전환)</button>
        <button class="ghost" style="padding:4px 10px;font-size:12.5px" onclick="playSfx(event,'ding')">▶ 띠링 (제목 등장)</button>
      </div>
      <div class="chk" style="gap:10px">
        <input type="checkbox" id="genPunchChk" checked>
        <span class="fx-demo punch-demo"><b>화면 쿵!</b></span>
        <span>👊 <b>펀치인 줌</b> — 강조 문장에서 옆 미리보기처럼 살짝 확대됐다 복귀 (자막은 고정)</span>
      </div>
      <div class="chk" style="gap:10px">
        <input type="checkbox" id="genInfoChk" checked>
        <span class="fx-demo pop-demo"><b>50%</b></span>
        <span>🔢 <b>숫자 인포 팝</b> — 강조 문장 속 숫자(3가지·10분·50%)가 옆처럼 크게 뿅!</span>
      </div>
      <div style="margin-top:8px">
        <span>🎨 화면 톤(색보정) <span class="hint">— 같은 장면이 이렇게 달라져요 (자막·제목 글자는 원색 유지)</span></span>
        <select id="genToneSel" class="hidden">
          <option value="기본" selected>기본 (보정 없음)</option>
          <option value="시네마틱">시네마틱 (영화 느낌 틸·오렌지)</option>
          <option value="화사">화사 (밝고 쨍한 브이로그)</option>
          <option value="선명">선명 (대비·채도·샤픈 업)</option>
          <option value="흑백">흑백 (드라마틱)</option>
        </select>
        <div class="tonerow" data-for="genToneSel"><div class="tonecard sel" data-v="기본" onclick="pickToneCard('genToneSel','기본',event)"
               title="기본"><div class="sw" style="filter:none"></div><span>기본</span></div><div class="tonecard" data-v="시네마틱" onclick="pickToneCard('genToneSel','시네마틱',event)"
               title="시네마틱"><div class="sw" style="filter:sepia(.30) saturate(1.35) contrast(1.08) hue-rotate(-8deg)"></div><span>시네마틱</span></div><div class="tonecard" data-v="화사" onclick="pickToneCard('genToneSel','화사',event)"
               title="화사"><div class="sw" style="filter:brightness(1.16) saturate(1.18)"></div><span>화사</span></div><div class="tonecard" data-v="선명" onclick="pickToneCard('genToneSel','선명',event)"
               title="선명"><div class="sw" style="filter:contrast(1.3) saturate(1.4)"></div><span>선명</span></div><div class="tonecard" data-v="흑백" onclick="pickToneCard('genToneSel','흑백',event)"
               title="흑백"><div class="sw" style="filter:grayscale(1) contrast(1.1)"></div><span>흑백</span></div></div>
      </div>
    </details>

    <details class="opt">
      <summary>🎵 배경음악 <span class="hint">— 영상에 깔릴 음악 고르기</span></summary>
      <div style="display:flex;gap:6px;margin-top:4px">
        <select id="bgmSel" style="flex:1"><option value="">없음</option></select>
        <button class="ghost" style="white-space:nowrap" onclick="previewBgm(event,'bgmSel',null)">▶ 미리듣기</button>
        <button class="ghost" id="bgmFetchBtn" style="white-space:nowrap" onclick="fetchBgm(event)"
                title="유튜버들이 가장 많이 쓰는 무료 BGM 14곡(Kevin MacLeod, CC BY)을 resources/bgm 폴더에 자동으로 받아옵니다 (약 40MB)">⬇ 무료 BGM 받기</button>
      </div>
      <div class="hint"><b>windows\\6_무료음원_받기.bat</b>로 유명 무료 BGM 자동 채우기. 저작권 확인된 음원만 사용하세요.</div>
    </details>

    <details class="opt">
      <summary>🖼 AI 배경 그림 <span class="hint">— 문장마다 장면 그림이 넘어가요 (Gemini 키)</span></summary>
      <div class="chk" style="gap:8px;margin-top:4px">
        <span>그림체</span>
        <select id="genBgStyle" style="width:auto;padding:6px 8px">
          <option value="일러스트" selected>일러스트 (기본)</option>
          <option value="실사풍">실사풍</option>
          <option value="3D">3D</option>
          <option value="수채화">수채화</option>
          <option value="네온">네온</option>
          <option value="미니멀">미니멀</option>
          <option value="웹툰">웹툰</option>
          <option value="지브리풍">지브리풍</option>
          <option value="유화">유화</option>
          <option value="동화">동화</option>
          <option value="흑백">흑백</option>
          <option value="픽셀아트">픽셀아트</option>
        </select>
        <span class="hint">전 장면에 같은 그림체로 통일돼요</span>
      </div>
      <div class="chk" style="gap:8px;flex-wrap:wrap">
        <span>마스코트</span>
        <select id="genCharSel" style="width:auto;padding:6px 8px" onchange="onGenCharChange()">
          <option value="" selected>없음</option>
          <option value="해골">☠️ 해골 캐릭터 (경제·지식 채널 감성)</option>
          <option value="고양이">🐱 고양이</option>
          <option value="곰돌이">🐻 곰돌이</option>
          <option value="직장인">🧑‍💼 직장인</option>
          <option value="스틱맨">✏️ 스틱맨</option>
          <option value="custom">✍ 직접 쓰기</option>
        </select>
        <input type="text" id="genCharCustom" class="hidden" style="flex:1;min-width:180px;padding:6px 8px"
               placeholder="예) 파란 모자를 쓴 유머러스한 해골">
        <span class="hint">모든 장면에 같은 캐릭터가 등장 (첫 그림을 참조로 일관성 유지)</span>
      </div>
      <div class="chk" style="gap:8px;flex-wrap:wrap">
        <span>그림 만들기</span>
        <select id="genSceneMode" style="width:auto;padding:6px 8px">
          <option value="auto" selected>🤖 자동 — AI가 장면마다 생성</option>
          <option value="manual">✍ 내가 넣기 — 프롬프트만 뽑기 (AI 비용 0원)</option>
          <option value="off">⛔ 그림 없이 (기본 배경)</option>
        </select>
        <span>최대 장수</span>
        <input type="number" id="genMaxImg" min="0" max="50" value="0" style="width:74px;padding:6px 8px">
        <span class="hint">0=문장마다 1장 · 예) 19문장에 10 → 10장만 (비용 절감)</span>
      </div>
      <div class="hint">✍ 내가 넣기 = 프롬프트만 뽑아 챗지피티/제미나이에서 직접 생성해 넣는 방식 (이미지 비용 0원, 「검토」로 진행)</div>
      <div class="hint hidden" id="aiBgOffWarn" style="color:#e8b34b">⚠ 지금 ⚙ 설정에서 <b>AI 배경이 꺼져 있어</b> 장면 그림·마스코트가 적용되지 않아요.
        <button class="ghost" style="padding:3px 10px;margin-left:6px" onclick="enableAiBg(event)">지금 켜기</button></div>
      <div class="hint">문장(장면)마다 AI 그림이 말 타이밍에 맞춰 넘어갑니다 — 키 없으면 기본 그라데이션.</div>
    </details>

    <details class="opt">
      <summary>⚙️ 세부 설정 <span class="hint">— 완성 전에 대본을 확인하고 싶다면</span></summary>
      <div class="chk" style="gap:8px">
        <label style="display:flex;gap:6px;align-items:center;margin:0"><input type="radio" name="prov" value="stub"><span>🔊 소리 점검용 목소리 (삐- 테스트 — 기계 확인할 때만)</span></label>
      </div>
      <label style="margin-top:4px">완성 방식</label>
      <div class="toggle">
        <label><input type="radio" name="mode" value="auto" checked><span>자동 (한 번에 완성)</span></label>
        <label><input type="radio" name="mode" value="review"><span>검토 (대본 확인 후)</span></label>
      </div>
    </details>

    <div class="hint" style="margin-top:14px">주제와 목소리만 고르고 [생성 시작]을 누르면 끝 — 완성까지 보통 몇 분 걸려요.</div>
    <div class="hidden" id="prodBadge" style="margin-top:12px;background:#12305a;border:1px solid #4266d5;border-radius:10px;padding:10px 12px;font-size:13.5px;color:#dfe7f5;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <span>📇 <b id="prodBadgeName"></b> 제품 정보로 만들어져요 — 일반 주제로 만들려면 끄세요</span>
      <button class="ghost" style="padding:4px 10px;font-size:12.5px;border-color:#4266d5" onclick="clearGenProduct(event)">✕ 제품 끄기</button>
    </div>
    <div style="display:flex;gap:8px">
      <button id="goBtn" style="flex:1" onclick="generateSafe()">🎬 생성 시작</button>
      <button class="ghost" style="white-space:nowrap" onclick="resetGenForm(event)" title="생성 폼의 입력을 기본값으로 되돌립니다">↺ 초기화</button>
    </div>
  </div>

  <div class="card hidden" id="weblinkCard">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <button class="ghost" onclick="showHome(event)">← 처음으로</button>
      <b>🔗 블로그 글로 만들기</b>
    </div>
    <div class="hint">내가 쓴 블로그 글(상품 소개·후기) 주소를 넣으면 글 속 <b>사진</b>과 <b>대본</b>을 가져와
      AI 목소리 내레이션 영상으로 만들어요. ⚠ 쿠팡·네이버쇼핑 <b>상품 페이지</b> 주소는 쇼핑몰이 막아서 안 돼요
      — 꼭 <b>상품을 소개한 블로그 글</b> 주소를 넣어주세요 (네이버 블로그 권장).</div>
    <div class="steplabel"><span class="stepnum">1</span>블로그 글 주소</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <input type="text" id="weblinkUrl" style="flex:1;min-width:220px" placeholder="예) https://blog.naver.com/아이디/글번호">
      <button class="ghost" style="white-space:nowrap;border-color:#4266d5" id="weblinkBtn" onclick="loadWeblink(event)">🔗 글 가져오기</button>
    </div>
    <div class="hint" id="weblinkHint"></div>
    <details class="opt" id="wlPasteBox">
      <summary>🛍 쇼핑 링크(쿠팡·스마트스토어)일 때 — 상품 정보 직접 붙여넣기</summary>
      <div class="hint" style="margin-top:4px">상품 페이지는 프로그램 접근을 막아 자동 수집이 안 돼요.
        대신: ① 상품 페이지의 <b>상세설명 글을 드래그·복사</b>해 아래에 붙여넣고 ② 상품 사진을
        PC에 저장해 [🖼 상품 사진 고르기]로 넣어주세요. 링크는 위 칸에 그대로 두면 출처로 저장돼요.</div>
      <div class="hint" style="margin-top:6px;color:#7fd18a">💡 쿠팡 파트너스·네이버 쇼핑커넥트 상품은 홈의
        <b>[🛒 쇼핑 상품 영상]</b> 카드가 더 편해요 — 상품 검색으로 이름·가격·사진·링크가 자동으로 채워집니다.</div>
      <textarea id="wlPasteText" style="min-height:110px;margin-top:6px" placeholder="상품 상세설명·특징·후기 등을 통째로 붙여넣으세요 — AI가 홍보 대본으로 정리해요"></textarea>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
        <button class="ghost" onclick="pickWlPhotos(event)">🖼 상품 사진 고르기 (여러 장)</button>
        <span class="hint" id="wlPhotoCnt" style="align-self:center"></span>
        <button class="ghost" style="border-color:#4266d5" onclick="loadWeblinkPasted(event)">🤖 이 내용으로 대본 만들기</button>
      </div>
    </details>
    <div id="wlPreview" class="hidden">
      <div class="steplabel"><span class="stepnum">2</span>사진 확인 <span class="hint">— 체크를 끄면 그 사진은 영상에서 빠져요 (순서 = 문장 순서)</span></div>
      <div id="wlGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:8px"></div>
      <div class="steplabel"><span class="stepnum">3</span>대본 확인 <span class="hint">— 한 줄 = 자막 한 줄 = 사진 한 장 타이밍. AI 목소리가 읽어요</span></div>
      <textarea id="wlScript" style="min-height:110px"></textarea>
      <div class="chk" style="gap:8px"><span>훅 제목</span><input type="text" id="wlHook" style="flex:1" placeholder="영상 상단에 크게 붙는 제목"></div>
      <div class="chk" style="gap:8px">
        <span>목소리</span>
        <select id="wlVoiceSel" style="width:auto;min-width:200px"></select>
        <span class="hint">— 🎙 AI 내레이션과 같은 목록 (제미나이 키가 있어야 적용)</span>
      </div>
      <details class="opt" id="wlDecoBox">
        <summary>🎨 꾸미기 <span class="hint">— 감성 테마·자막·제목 스타일·화면 톤 (안 바꾸면 기억된 설정 그대로)</span></summary>
        <div class="chk" style="gap:10px;flex-wrap:wrap">
          <span>🎨 감성 테마</span>
          <select id="wlThemeSel" style="width:auto" onchange="applyTheme('wl')">
            <option value="">직접 고르기</option>
            <option value="insta">📸 인스타 감성</option>
            <option value="tiktok">🎵 틱톡 감성</option>
            <option value="youtube">▶ 유튜브 예능</option>
            <option value="cinema">🎬 시네마틱</option>
          </select>
          <span>자막 스타일</span><select id="wlSubStyleSel" style="width:auto"></select>
          <span>제목 스타일</span><select id="wlHookStyleSel" style="width:auto"></select>
          <span>자막 글씨체</span><select id="wlSubFontSel" style="width:auto;max-width:180px"></select>
          <span>화면 톤</span><select id="wlToneSel" style="width:auto"></select>
        </div>
      </details>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button id="wlGoBtn" style="flex:1;min-width:200px" onclick="startWeblinkSafe()">🎬 영상 만들기</button>
        <button class="ghost" id="weblinkProdBtn" onclick="saveWeblinkProduct(event)" title="가져온 글에서 제품 정보를 AI로 정리해 「📇 내 제품 정보」에 저장 — 글 속 제휴 링크도 자동으로 넣어줘요">📇 제품 프로필 저장</button>
      </div>
      <div class="hint">만들면 자막 검토 화면이 나와요 — 확인 후 [완성]을 누르면 <b>사진이 문장 타이밍에 맞춰</b> 넘어갑니다.</div>
    </div>
  </div>

  <div class="card hidden" id="sectionCard">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <button class="ghost" onclick="showHome(event)">← 처음으로</button>
      <b>🎞 구간 대본 영상</b>
    </div>
    <div class="hint">촬영 대본의 구간(장면)마다 화면녹화 클립을 넣으면: 클립을 <b>내레이션 길이에 맞게
      핵심 장면만 남기고 압축</b>하고, 내레이션을 AI 목소리로 읽고, 자막을 넣어 <b>순서대로 이어붙인</b>
      완성 영상 1개를 만들어요. 구간 길이는 대본의 시간표가 아니라 <b>말을 실제로 읽은 길이</b>를 따라요 (말 안 잘림).</div>
    <details class="opt" id="secScriptBox">
      <summary>📝 대본 통째로 붙여넣기 <span class="hint">— 구간과 내레이션을 자동으로 나눠 아래에 채워드려요</span></summary>
      <textarea id="secScriptText" style="min-height:140px" placeholder="촬영 대본을 통째로 붙여넣으세요.&#10;[말] 표시가 있는 대본이면 그대로 인식하고, 일반 글이면 문단 단위로 나눠요."></textarea>
      <button class="ghost" style="margin-top:6px" id="secSplitBtn" onclick="splitSections(event)">✂️ 구간 자동 나누기</button>
    </details>
    <div class="steplabel" style="margin-top:10px"><span class="stepnum">1</span>영상 넣는 방식</div>
    <div class="chk" style="gap:10px;flex-wrap:wrap">
      <div class="toggle" style="margin:0">
        <label><input type="radio" name="secSrcMode" value="full" checked onchange="applySecMode()"><span>🎥 풀영상 하나로 <span class="hint">(길게 찍고 구간만 고르기 — 추천)</span></span></label>
        <label><input type="radio" name="secSrcMode" value="clips" onchange="applySecMode()"><span>🎬 구간마다 클립 따로</span></label>
      </div>
    </div>
    <div id="secFullBox" style="margin-top:8px;padding:10px;border:1px dashed #3a4157;border-radius:10px">
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <input type="text" id="secFullPath" placeholder="전체 시연을 처음부터 끝까지 담은 풀영상 파일 경로" style="flex:1;min-width:200px" onchange="loadFullVideo()">
        <button class="ghost" style="white-space:nowrap" onclick="pickFullVideo(event)">🎥 풀영상 선택</button>
        <button class="ghost" style="white-space:nowrap" onclick="suggestSecRanges(event)" title="내레이션 분량 비율로 나누고, 화면이 확 바뀌는 지점(장면 전환)에 경계를 맞춰요">🪄 자동으로 나누기</button>
      </div>
      <video id="secPlayer" controls playsinline class="hidden" style="margin-top:8px;max-height:280px"></video>
      <div class="hint" id="secFullDur" style="margin-top:4px">영상을 고르면 여기서 바로 재생하며 구간을 정할 수 있어요.
        [🪄 자동으로 나누기]가 구간별 시간을 채워주고, 재생 중 각 구간의 [▶ 여기부터]/[⏹ 여기까지]로 손볼 수 있어요.
        (미리보기가 안 떠도 만들기는 됩니다 — 일부 폰 영상 형식은 브라우저가 재생만 못 해요)</div>
    </div>
    <div class="steplabel" style="margin-top:10px"><span class="stepnum">2</span>구간 만들기 <span class="hint">— 행 순서대로 이어붙어요. 구간마다 읽을 내레이션 + (클립 또는 풀영상 범위)</span></div>
    <div id="secRows"></div>
    <button class="ghost" style="margin-top:8px" onclick="addSectionRow()">➕ 구간 추가</button>
    <div class="hint" id="secTotal" style="margin-top:6px"></div>
    <div class="steplabel" style="margin-top:12px"><span class="stepnum">3</span>공통 설정</div>
    <div class="chk" style="gap:10px;flex-wrap:wrap">
      <span>화면</span>
      <div class="toggle" style="margin:0">
        <label><input type="radio" name="secLayout" value="wide" checked><span>🖥 가로 (16:9)</span></label>
        <label><input type="radio" name="secLayout" value="shorts"><span>📱 세로 쇼츠 (9:16)</span></label>
      </div>
      <span style="margin-left:6px">목소리</span>
      <select id="secVoiceSel" style="width:auto;min-width:180px"></select>
      <span style="margin-left:6px">압축 템포</span>
      <select id="secTempoSel" style="width:auto;padding:6px 8px">
        <option value="">보통 (3.5초 조각)</option>
        <option value="빠르게">빠르게 (2.4초 조각)</option>
        <option value="아주 빠르게">아주 빠르게 (1.7초 조각)</option>
      </select>
      <span style="margin-left:6px">배경음악</span>
      <select id="secBgmSel" style="width:auto;min-width:140px"><option value="">없음</option></select>
      <span style="margin-left:6px">구간 전환</span>
      <select id="secXfadeSel" style="width:auto;padding:6px 8px" title="구간과 구간이 이어지는 방식">
        <option value="">스르륵 (디졸브)</option>
        <option value="varied">🎲 다양하게 (구간마다 다른 효과)</option>
        <option value="slideleft">밀어내기</option>
        <option value="wipeleft">닦아내기</option>
        <option value="circleopen">원형 열기</option>
        <option value="smoothleft">부드러운 밀기</option>
        <option value="fadeblack">암전 (어두워졌다 밝게)</option>
        <option value="none">컷 (전환 없음)</option>
      </select>
    </div>
    <details class="opt" id="secDecoBox">
      <summary>🎨 꾸미기 <span class="hint">— 자막·제목 스타일·화면 톤 (안 바꾸면 기억된 설정 그대로)</span></summary>
      <div class="chk" style="gap:10px;flex-wrap:wrap">
        <span>🎨 감성 테마</span>
        <select id="secThemeSel" style="width:auto" onchange="applyTheme('sec')">
          <option value="">직접 고르기</option>
          <option value="insta">📸 인스타 감성</option>
          <option value="tiktok">🎵 틱톡 감성</option>
          <option value="youtube">▶ 유튜브 예능</option>
          <option value="cinema">🎬 시네마틱</option>
        </select>
        <span>자막 스타일</span><select id="secSubStyleSel" style="width:auto"></select>
        <span>제목 스타일</span><select id="secHookStyleSel" style="width:auto"></select>
        <span>자막 글씨체</span><select id="secSubFontSel" style="width:auto;max-width:180px"></select>
        <span>화면 톤</span><select id="secToneSel" style="width:auto"></select>
      </div>
    </details>
    <div class="hint hidden" id="secDraftHint" style="margin-top:6px;color:#7fd18a">💾 지난 임시 저장을 불러왔어요 — 이어서 작성하시면 돼요. 새로 시작하려면 [🗑 임시 저장 지우기]</div>
    <div style="display:flex;gap:8px;margin-top:4px;flex-wrap:wrap">
      <button id="secGoBtn" style="flex:1;min-width:180px" onclick="startSectionsSafe()">🎬 영상 만들기</button>
      <button class="ghost" onclick="saveSecDraft(event)" title="지금 작성 중인 구간·내레이션·설정을 저장해 두고, 나중에 이 카드를 열면 이어서 작성할 수 있어요">💾 임시 저장</button>
      <button class="ghost" onclick="clearSecDraft(event)" title="저장해 둔 임시 저장을 지워요">🗑</button>
    </div>
    <div class="hint">구간이 많으면 시간이 걸려요 (구간당 보통 1~2분). 진행 상황에 구간 번호가 표시됩니다.
      완성 후 히스토리의 [✏ 다시 편집]으로 불러오면 <b>바뀐 구간만 다시 만들어</b> 빨라요.</div>
  </div>

  <div id="shopCard" class="hidden">
    <div style="display:flex;align-items:center;gap:8px">
      <button class="ghost" onclick="showHome()">← 처음으로</button>
      <h2 style="margin:0">🛒 쇼핑 상품 영상 <span class="hint">— 쿠팡 파트너스 · 네이버 쇼핑커넥트</span></h2>
    </div>
    <div class="hint">상품을 검색해 고르면 이름·가격·대표 사진이 자동으로 채워지고,
      AI가 홍보 대본을 써서 <b>사진+내레이션 영상</b>으로 완성해요. 수익 링크는 영상 설명란에 붙여넣으면 됩니다.</div>
    <div class="steplabel" style="margin-top:10px"><span class="stepnum">1</span>상품 고르기 <span class="hint">— 두 방법 중 편한 쪽 (검색 또는 직접 붙여넣기)</span></div>
    <details class="opt" open>
      <summary>🛒 쿠팡 파트너스 <span class="hint" id="cpKeyState">— API 키를 저장하면 상품 검색·파트너스 링크 자동</span></summary>
      <details class="opt" id="cpKeyBox" style="margin-top:4px">
        <summary>🔑 파트너스 API 키 <span class="hint">— 쿠팡 파트너스 → 도구 → Open API에서 발급</span></summary>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
          <input type="password" id="cpAccess" placeholder="Access Key" style="flex:1;min-width:140px">
          <input type="password" id="cpSecret" placeholder="Secret Key" style="flex:1;min-width:140px">
          <button class="ghost" onclick="saveCoupangKeys(event)">저장</button>
        </div>
      </details>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
        <input type="text" id="cpKeyword" placeholder="상품 검색어 (예: 무선 선풍기)" style="flex:1;min-width:160px">
        <button class="ghost" onclick="coupangSearch(event)">🛒 상품 검색</button>
      </div>
      <div id="cpResults" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-top:8px"></div>
    </details>
    <details class="opt">
      <summary>🟢 네이버 쇼핑커넥트 <span class="hint" id="nvKeyState">— 무료 검색 API 키를 저장하면 상품 검색 자동</span></summary>
      <details class="opt" id="nvKeyBox" style="margin-top:4px">
        <summary>🔑 네이버 검색 API 키 <span class="hint">— developers.naver.com에서 앱 등록(무료) 후 발급</span></summary>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
          <input type="password" id="nvClientId" placeholder="Client ID" style="flex:1;min-width:140px">
          <input type="password" id="nvClientSecret" placeholder="Client Secret" style="flex:1;min-width:140px">
          <button class="ghost" onclick="saveNaverKeys(event)">저장</button>
        </div>
      </details>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
        <input type="text" id="nvKeyword" placeholder="상품 검색어 (예: 무선 선풍기)" style="flex:1;min-width:160px">
        <button class="ghost" onclick="naverSearch(event)">🟢 상품 검색</button>
      </div>
      <div id="nvResults" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-top:8px"></div>
      <div class="hint" style="margin-top:4px">쇼핑커넥트 수익 링크는 커넥트 대시보드에서 만들어 아래 「내 수익 링크」에 붙여넣어 주세요 (API로는 발급이 안 돼요)</div>
    </details>
    <div class="steplabel" style="margin-top:10px"><span class="stepnum">2</span>상품 정보 확인 <span class="hint">— 자동으로 채워져요. 상세설명을 덧붙이면 대본이 풍부해져요</span></div>
    <textarea id="shopPasteText" style="min-height:100px" placeholder="상품 이름·특징·후기 등 — 위에서 상품을 고르면 자동으로 채워지고, 상품 페이지의 상세설명을 복사해 덧붙일 수 있어요"></textarea>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
      <button class="ghost" onclick="pickShopPhotos(event)">🖼 상품 사진 고르기 (여러 장)</button>
      <button class="ghost" onclick="clearShopPhotos(event)" title="지금까지 모은 상품 사진을 전부 비우고 처음부터 다시">🗑 사진 비우기</button>
      <span class="hint" id="shopPhotoCnt" style="align-self:center"></span>
    </div>
    <div id="shopPhotoPrev" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px"></div>
    <div class="hint" style="margin-top:4px">📋 <b>사진 한꺼번에 넣기</b> — 상품 페이지에서 사진 있는 부분을 마우스로 드래그해 복사(Ctrl+C)한 뒤 이 화면에 붙여넣기(Ctrl+V)하면 사진 여러 장이 자동으로 들어와요. 스크린샷(Win+Shift+S)을 바로 붙여넣어도 됩니다</div>
    <div class="chk" style="gap:8px;margin-top:6px">
      <span style="white-space:nowrap">🔗 내 수익 링크</span>
      <input type="text" id="shopLinkInput" style="flex:1" placeholder="상품 링크를 붙여넣고 아래 [🤖 대본 만들기]를 누르면 사진·설명 자동 수집 (파트너스·쇼핑커넥트 링크도 이 칸)">
    </div>
    <button class="ghost" style="margin-top:8px;border-color:#4266d5" onclick="makeShopScript(event)" title="상세설명이 비어 있어도 링크가 있으면 상품 페이지에서 사진·설명을 자동으로 수집해요 (안 되면 페이지 복사→붙여넣기 안내)">🤖 이 상품으로 대본 만들기</button>
    <div id="shopPreview" class="hidden">
      <div class="steplabel" style="margin-top:10px"><span class="stepnum">3</span>대본 확인 <span class="hint">— 한 줄 = 자막 한 줄. AI 목소리가 읽어요</span></div>
      <textarea id="shopScript" style="min-height:110px"></textarea>
      <div class="chk" style="gap:8px"><span>훅 제목</span><input type="text" id="shopHook" style="flex:1" placeholder="영상 상단에 크게 붙는 제목"></div>
      <div class="chk" style="gap:10px;flex-wrap:wrap;margin-top:4px">
        <span>목소리</span><select id="shopVoiceSel" style="width:auto;min-width:180px"></select>
        <span>배경음악</span><select id="shopBgmSel" style="width:auto;min-width:140px"><option value="">없음</option></select>
      </div>
      <details class="opt" id="shopDecoBox">
        <summary>🎨 꾸미기 <span class="hint">— 감성 테마·자막·제목 스타일·화면 톤</span></summary>
        <div class="chk" style="gap:10px;flex-wrap:wrap">
          <span>🎨 감성 테마</span>
          <select id="shopThemeSel" style="width:auto" onchange="applyTheme('shop')">
            <option value="">직접 고르기</option>
            <option value="insta">📸 인스타 감성</option>
            <option value="tiktok">🎵 틱톡 감성</option>
            <option value="youtube">▶ 유튜브 예능</option>
            <option value="cinema">🎬 시네마틱</option>
          </select>
          <span>자막 스타일</span><select id="shopSubStyleSel" style="width:auto"></select>
          <span>제목 스타일</span><select id="shopHookStyleSel" style="width:auto"></select>
          <span>자막 글씨체</span><select id="shopSubFontSel" style="width:auto;max-width:180px"></select>
          <span>화면 톤</span><select id="shopToneSel" style="width:auto"></select>
        </div>
      </details>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button id="shopGoBtn" style="flex:1" onclick="startShopSafe()">🎬 영상 만들기</button>
      </div>
      <div class="hint">완성되면 [📦 업로드 키트]로 제목·태그·설명을 만들고, 위의 수익 링크를 설명란에 붙여넣으세요.</div>
    </div>
  </div>

  <div class="card hidden" id="statusCard">
    <div id="statusTitle" style="font-weight:700"></div>
    <div class="bar"><div id="barFill"></div></div>
    <div class="stage" id="stageText"></div>
    <div class="stage" id="noteText" style="color:#e8b34b"></div>

    <div id="reviewBox" class="hidden">
      <label>제목</label>
      <input type="text" id="rvTitle">
      <label>대본 (한 줄 = 자막 한 줄 = TTS 한 문장 · 강조 단어는 <code>문장 | 단어</code>)</label>
      <textarea id="rvSentences"></textarea>
      <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
        <button class="ghost" onclick="pronounceLines(event)">한글 발음으로 변환 (숫자·영어)</button>
        <span class="hint">예: 2026년→이천이십육년, AI→에이아이 — TTS 오독 방지</span>
      </div>
      <button onclick="confirmScript()">이 대본으로 계속</button>
    </div>

    <div id="sceneBox" class="hidden">
      <div style="font-weight:700">🖼 장면 그림 확인 <span class="hint">— 문장마다 이 그림이 배경으로 들어가요</span>
        <span class="hint" id="sceneMeta" style="font-weight:400;margin-left:8px"></span></div>
      <div class="hint" style="margin-top:4px">마음에 안 드는 장면은 <b>묘사를 고치고 [🔄 다시 그리기]</b>, 또는 <b>[📁 내 그림]</b>으로 직접 만든 그림을 넣어도 돼요 → 다 되면 맨 아래 <b>[✅ 이 그림들로 완성]</b></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
        <button class="ghost" onclick="copyScenePrompts(event)" title="장면별 프롬프트를 「N번 장면 → 묘사」 통합 형식으로 복사 — 챗지피티/제미나이에 붙여넣어 한 번에 생성">📋 프롬프트 전체 복사 (통합)</button>
        <button class="ghost" onclick="importSceneFolder(event)" title="직접 만든 그림들을 폴더에 담아두면 이름순으로 1번 장면부터 차례로 들어갑니다">📁 그림 폴더에서 한꺼번에 넣기</button>
      </div>
      <textarea id="sceneAllText" class="hidden" readonly
                style="margin-top:8px;min-height:180px;font-size:12.5px;line-height:1.55"
                title="복사된 내용 — 여기서 드래그해 직접 복사해도 됩니다"></textarea>
      <div id="sceneGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-top:10px"></div>
      <button style="margin-top:12px" onclick="confirmScenes()">✅ 이 그림들로 영상 완성</button>
    </div>

    <div id="subEditBox" class="hidden">
      <div style="font-weight:700;margin-bottom:4px">✏️ 자막 확인하고 완성하기</div>
      <div class="hint" style="font-size:13px;color:#cdd3e0">① 아래 자막에서 <b>틀린 글자만 고치세요</b> (칸을 누르면 영상이 멈춰요) → ② 쇼츠로 줄이려면 ✂️ 줄에서 구간을 고르거나 [✨ AI 핵심 추천] → ③ 맨 아래 <b>[✅ 완성]</b> 버튼</div>
      <div class="hint">각 줄 <b>▶</b>=듣기 · <b>✂</b>=줄 나누기 · <b>🗑</b>=<b>자막+영상 구간 통째 삭제</b>(브루식 — 체크박스 다시 켜면 복구) · <b>✕</b>=자막만 삭제(영상 유지) · <b>스페이스바</b>=재생/정지 · 💛 강조 <b>| 단어</b>, 색 <b>[노랑]글자[/]</b></div>
      <div class="playbar">
        <div id="playerWrap" style="position:relative;line-height:0">
          <video id="cutPlayer" controls playsinline style="width:100%"></video>
          <div id="subPosBar" title="드래그해서 자막 위치를 옮기세요"
               style="position:absolute;left:6%;right:6%;height:34px;bottom:25%;cursor:ns-resize;border:2px dashed rgba(255,217,64,.85);border-radius:8px;background:rgba(255,217,64,.10);display:flex;align-items:center;justify-content:center;touch-action:none;user-select:none;z-index:5">
            <span style="font-size:12px;color:#ffd940;background:rgba(0,0,0,.55);padding:1px 8px;border-radius:6px;line-height:1.4">↕ 자막 위치</span>
          </div>
        </div>
        <div class="playrow">
          <button class="ghost pbtn" id="playToggle" onclick="togglePlay(event)">▶ 재생</button>
          <span class="hint" id="playClock" style="min-width:64px">0:00</span>
          <span class="hint">배속</span>
          <select id="playRate" onchange="setPlayRate()">
            <option value="0.75">0.75×</option>
            <option value="1" selected>1×</option>
            <option value="1.25">1.25×</option>
            <option value="1.5">1.5×</option>
            <option value="2">2×</option>
          </select>
          <span class="hint">← 스페이스바로 정지</span>
        </div>
      </div>
      <div class="shortsbar">
        <b style="font-size:13px">✂️ 앞뒤 트림</b>
        <span class="hint">영상을 원하는 지점에 멈춘 뒤</span>
        <button class="ghost" onclick="setTrimStart(event)">⏮ 여기부터 시작</button>
        <button class="ghost" onclick="setTrimEnd(event)">⏭ 여기서 끝</button>
        <span class="hint" id="trimInfo" style="color:#7a9bff;font-weight:700">전체 사용</span>
        <button class="ghost" onclick="clearTrim(event)">해제</button>
      </div>
      <div class="shortsbar">
        <b style="font-size:13px">✂️ 쇼츠로 줄이기</b>
        <span class="hint">넣을 핵심 구간만 <b>체크 ☑</b> (나머지는 잘려요)</span>
        <span class="hint" id="keepInfo" style="color:#7a9bff;font-weight:700">전체</span>
        <button class="ghost" onclick="selectAll(true,event)">전체 선택</button>
        <button class="ghost" onclick="selectAll(false,event)">전체 해제</button>
        <span style="flex:1;min-width:6px"></span>
        <span class="hint">목표</span>
        <input type="number" id="hlTarget" value="30" min="5" max="90" style="width:54px;padding:6px">
        <span class="hint">초</span>
        <button class="ghost" onclick="aiHighlights(event)" title="AI가 핵심 구간을 골라 체크해줍니다">✨ AI 핵심 추천</button>
        <button class="ghost" onclick="renderSplit(event)" title="전체를 목표 길이 단위로 잘라 쇼츠 여러 개로 저장">🎬 여러 쇼츠로 나누기</button>
        <button class="ghost" id="cleanRepeatsBtn" style="display:none;color:#f0a020" onclick="cleanRepeats(event)" title="↻ 표시된 반복(NG) 테이크를 지우고 마지막 테이크만 남깁니다 (영상도 함께 컷)">↻ 반복 정리</button>
      </div>
      <div class="hint" id="hlReason" style="margin-top:4px"></div>
      <div id="subList" class="subList-scroll" style="margin-top:10px"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
        <button class="ghost" onclick="refineSubs(event)" title="발음 오인식을 문맥에 맞게 자연스럽게 자동 교정 (제미나이 키 필요)">🪄 AI로 대본 다듬기</button>
        <button class="ghost" onclick="addSubRow(event)">+ 자막 줄 추가</button>
      </div>
      <details class="opt" style="margin-top:8px">
        <summary>🧰 더 많은 도구 <span class="hint">— AI 영상 분석 · 대본 저장 · 일괄 붙여넣기 · 발음 변환</span></summary>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
          <button class="ghost" onclick="analyzeAI(event)" title="장면 캡처+자막을 AI가 보고 제목·훅·대본을 추천 (제미나이 키 권장)">🧠 AI 영상 분석 (제목·대본)</button>
          <button class="ghost" onclick="pronounceSubs(event)">숫자·영어 → 한글 발음</button>
          <button class="ghost" onclick="toggleBulk(event)">📋 대본 일괄 붙여넣기</button>
          <button class="ghost" onclick="downloadScript(event,'txt')">📥 대본 저장(.txt)</button>
          <button class="ghost" onclick="downloadScript(event,'srt')">📥 자막 저장(.srt)</button>
        </div>
      </details>
      <div id="aiAnalyzeBox" class="hidden" style="margin-top:8px;padding:10px 12px;border:1px solid #2c3350;border-radius:10px">
        <div class="hint" id="aiSummary" style="margin-bottom:6px"></div>
        <b style="font-size:13px">🪝 상단 훅 추천 (클릭하면 채워져요)</b>
        <div id="aiHooks" class="hookcands"></div>
        <b style="font-size:13px">📌 유튜브 제목 추천</b>
        <div id="aiTitles" class="hint" style="white-space:pre-line;margin:4px 0 8px"></div>
        <b style="font-size:13px">📝 추천 내레이션 대본</b>
        <textarea id="aiScript" readonly style="min-height:84px;margin-top:4px"></textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
          <button class="ghost" onclick="applyAiScript(event)">이 대본으로 자막 텍스트 교체</button>
          <button class="ghost" onclick="copyAiScript(event)">📋 복사</button>
          <span class="hint" id="aiTags"></span>
        </div>
      </div>
      <div id="bulkBox" class="hidden" style="margin-top:8px">
        <textarea id="bulkText" style="min-height:90px" placeholder="대본을 한 줄에 한 자막씩 붙여넣고 아래 버튼을 누르면, 위 자막들의 텍스트가 순서대로 교체됩니다 (타이밍은 유지). 줄이 더 많으면 뒤에 추가돼요."></textarea>
        <button class="ghost" onclick="applyBulk(event)">이 대본으로 자막 텍스트 교체</button>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px">
        <span class="hint">⏩ 저장 속도 <span style="color:#8b93a7">(완성 영상에 적용 · 자막도 같이 빨라짐)</span></span>
        <select id="outSpeed" style="width:auto;padding:6px 8px">
          <option value="1">1배 (원본)</option>
          <option value="1.25">1.25배</option>
          <option value="1.5">1.5배</option>
          <option value="2">2배</option>
        </select>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px">
        <span class="hint">🎞️ 화질</span>
        <select id="outQuality" style="width:auto;padding:6px 8px" onchange="qualityHint()">
          <option value="draft">빠름 (초안·가장 빠름)</option>
          <option value="standard" selected>표준 (1080p)</option>
          <option value="high">고화질 (1080p · 선명·저압축)</option>
          <option value="ultra">초고화질 (4K 업스케일 · 유튜브 노출↑ · 느림)</option>
        </select>
        <span class="hint" id="qualityHint"></span>
      </div>
      <button id="renderBtn" onclick="renderEdited()">✅ 이 자막으로 완성</button>
    </div>

    <div id="doneBox" class="hidden">
      <div style="font-weight:800;font-size:16px;margin-top:8px">🎉 영상 완성!</div>
      <div class="stage" id="providerBadge"></div>
      <video id="player" controls playsinline></video>
      <div class="stage" id="outPaths"></div>
      <div id="chaptersBox" class="hidden" style="margin-top:10px;padding:10px 12px;border:1px dashed #3a4157;border-radius:10px">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <b style="font-size:13px">⏱ 구간 타임라인</b>
          <span class="hint">— 유튜브 설명란에 그대로 붙여넣으면 영상에 챕터(구간 이동 바)가 생겨요</span>
          <button class="ghost" style="padding:2px 8px" onclick="copyChapters(event)">📋 복사</button>
          <button class="ghost" style="padding:2px 8px" onclick="reEditSections(currentJob)" title="이 영상의 구간·내레이션을 폼으로 불러와 일부만 고쳐 다시 만들어요 — 바뀐 구간만 재제작돼 빨라요">✏ 다시 편집</button>
        </div>
        <pre id="chaptersText" style="margin:6px 0 0;white-space:pre-wrap;font-size:13px;color:#c8cede;font-family:inherit"></pre>
      </div>
      <button class="ghost" style="margin-top:10px" onclick="openFolder(event)">📂 폴더 열기</button>
      <button class="ghost" style="margin-top:10px" onclick="sendDoneToEdit(event,'shorts')" title="완성된 이 영상을 편집 카드로 보내 세로 쇼츠(9:16)로 다시 만들어요 — 핵심만 남겨 60초 쇼츠 여러 개로 나누는 완전 자동을 추천으로 맞춰둬요">📱 쇼츠로 만들기</button>
      <button class="ghost" style="margin-top:10px" onclick="sendDoneToEdit(event,'keep')" title="완성된 이 영상을 편집 카드로 보내 자르고 다듬어요 — 자막·훅·BGM·배속을 다시 설정할 수 있어요">✂ 이 영상 편집</button>
      <button class="ghost" style="margin-top:10px" onclick="shrinkVideo(event)" title="용량이 커서 업로드가 안 될 때 — 화질 거의 그대로 파일 크기를 크게 줄인 업로드용 mp4를 하나 더 만들어요 (원본은 그대로)">📦 용량 줄이기 (업로드용)</button>
      <button class="ghost" style="margin-top:10px" onclick="extractAudio(event,'mix')" title="완성 영상의 소리(목소리+BGM+효과음)를 mp3로 저장">🔊 소리 저장(mp3)</button>
      <button class="ghost" style="margin-top:10px" onclick="extractAudio(event,'voice')" title="BGM·원본 소리 없이 내레이션 목소리만 mp3로 저장 — 다른 편집기·팟캐스트에 재사용">🎙 목소리만(mp3)</button>
      <button class="ghost" style="margin-top:10px" onclick="toggleKit(event)">📦 업로드 키트 (제목·태그·설명 자동)</button>
      <button class="ghost" style="margin-top:10px" onclick="toggleThumb(event)">🖼️ 유튜브 썸네일 만들기 (16:9)</button>
      <div class="hint" style="margin-top:10px;padding:8px 12px;border:1px dashed #3a4157;border-radius:10px">🎯 <b>다음엔 이것도 해보세요</b> —
        ① [🖼️ 썸네일 만들기]로 업로드용 썸네일까지 30초 ·
        ② [📦 업로드 키트]로 제목·태그·설명 복사 ·
        ③ 세부 설정을 「검토」로 하면 대본과 장면 그림을 확인·수정하고 완성할 수 있어요</div>
      <div id="kitBox" class="hidden" style="margin-top:10px;padding:10px 12px;border:1px dashed #3a4157;border-radius:10px">
        <div style="font-weight:700;font-size:14px">📦 업로드 키트 <span class="hint">— 유튜브 · 틱톡 · 인스타 · 네이버 클립 · 스레드</span></div>
        <div class="hint" id="kitStatus" style="margin-top:4px"></div>
        <div id="kitBody" class="hidden">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <b style="font-size:13px">📌 제목 후보 <span class="hint">(클릭하면 제목+옆 태그까지 통째로 복사돼요)</span></b>
            <a href="https://studio.youtube.com" target="_blank" rel="noopener" class="ghost" style="padding:2px 8px;text-decoration:none;margin-left:auto">↗ 유튜브 스튜디오 열기</a>
          </div>
          <div id="kitTitles" class="hookcands"></div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:10px">
            <b style="font-size:13px">📝 설명문</b>
            <span class="hint">(설명란에 그대로 붙여넣기 — BGM 크레딧 포함)</span>
            <button class="ghost" style="padding:2px 8px" onclick="copyKit(event,'kitDesc')">📋 복사</button>
          </div>
          <textarea id="kitDesc" style="min-height:120px;margin-top:4px"></textarea>
          <div style="display:flex;align-items:center;gap:8px;margin-top:8px">
            <b style="font-size:13px">🏷️ 태그</b>
            <span class="hint">(태그란에 통째로 붙여넣기)</span>
            <button class="ghost" style="padding:2px 8px" onclick="copyKit(event,'kitTags')">📋 복사</button>
          </div>
          <textarea id="kitTags" style="min-height:48px;margin-top:4px"></textarea>
          <div class="hint" id="kitKeywords" style="margin-top:8px"></div>
          <div class="hint" id="kitCategory" style="margin-top:4px"></div>

          <details class="opt" style="margin-top:10px">
            <summary>🎵 틱톡 <span class="hint">— 캡션+해시태그 (150자·태그 3~5개)</span>
              <button class="ghost" style="padding:2px 8px" onclick="copyKit(event,'kitTiktok')">📋 복사</button>
              <a href="https://www.tiktok.com/tiktokstudio/upload" target="_blank" rel="noopener" class="ghost" style="padding:2px 8px;text-decoration:none" onclick="event.stopPropagation()">↗ 틱톡 열기</a></summary>
            <textarea id="kitTiktok" style="min-height:72px;margin-top:4px"></textarea>
          </details>
          <details class="opt">
            <summary>📸 인스타그램 릴스 <span class="hint">— 첫 줄이 미리보기에 노출</span>
              <button class="ghost" style="padding:2px 8px" onclick="copyKit(event,'kitInsta')">📋 복사</button>
              <a href="https://www.instagram.com" target="_blank" rel="noopener" class="ghost" style="padding:2px 8px;text-decoration:none" onclick="event.stopPropagation()">↗ 인스타 열기</a></summary>
            <textarea id="kitInsta" style="min-height:88px;margin-top:4px"></textarea>
            <div class="hint" style="margin-top:4px">📐 반드시 <b>'릴스'</b>로 올리세요. 영상은 9:16(1080×1920)로 딱 맞아요 —
              프로필·피드 <b>썸네일이 위아래로 잘려 보이는 건 정상</b>(인스타가 4:5로 미리보기 crop). 릴스로 재생하면 제목까지 다 나와요.</div>
          </details>
          <details class="opt">
            <summary>🟢 네이버 클립 <span class="hint">— 제목·태그 각각 복사 + 카테고리 추천</span>
              <a href="https://clipcreators.naver.com" target="_blank" rel="noopener" class="ghost" style="padding:2px 8px;text-decoration:none" onclick="event.stopPropagation()">↗ 클립 열기</a></summary>
            <div class="chk" style="gap:8px;margin-top:4px"><b style="font-size:13px">제목</b>
              <button class="ghost" style="padding:2px 8px" onclick="copyKit(event,'kitNaverTitle')">📋 복사</button>
              <span class="hint">— 제목란에 그대로 (라벨 없이 붙어요)</span></div>
            <input type="text" id="kitNaverTitle" style="margin-top:2px">
            <div class="chk" style="gap:8px;margin-top:6px"><b style="font-size:13px">태그</b>
              <button class="ghost" style="padding:2px 8px" onclick="copyKit(event,'kitNaverTags')">📋 복사</button>
              <span class="hint">— 쉼표로 구분돼 태그란에 그대로</span></div>
            <textarea id="kitNaverTags" style="min-height:48px;margin-top:2px"></textarea>
            <div class="hint" id="kitNaverCat" style="margin-top:6px"></div>
          </details>
          <details class="opt">
            <summary>🧵 스레드 <span class="hint">— 짧은 반말 + 토픽 태그 1개만</span>
              <button class="ghost" style="padding:2px 8px" onclick="copyKit(event,'kitThreads')">📋 복사</button>
              <a href="https://www.threads.com" target="_blank" rel="noopener" class="ghost" style="padding:2px 8px;text-decoration:none" onclick="event.stopPropagation()">↗ 스레드 열기</a></summary>
            <textarea id="kitThreads" style="min-height:64px;margin-top:4px"></textarea>
          </details>

          <div class="hint" id="kitChecklist" style="white-space:pre-line;margin-top:8px;color:#cdd3e0"></div>
          <div class="hint" id="kitPath" style="margin-top:8px"></div>
          <button class="ghost" style="margin-top:8px" onclick="makeKit(event)">🔄 다시 만들기</button>
        </div>
      </div>
      <div id="thumbBox" class="hidden" style="margin-top:10px;padding:10px;border:1px dashed #3a4157;border-radius:10px">
        <label style="margin-top:0">썸네일 제목 <span class="hint">— 짧고 강하게. 줄바꿈 Enter. 강조는 <b>| 단어</b></span></label>
        <textarea id="thumbTitle" style="min-height:52px" placeholder="예) 사진만 넣으면&#10;홍보글이 뚝딱! | 뚝딱!"></textarea>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
          <input type="text" id="thumbTopic" style="flex:1;min-width:160px" placeholder="주제/키워드 (예: 블로그 홍보글 자동화)">
          <button class="ghost" style="white-space:nowrap" onclick="suggestThumb(event)">✨ AI 카피 추천</button>
        </div>
        <div id="thumbCands" class="hookcands"></div>
        <div class="chk" style="gap:8px;margin-top:6px;flex-wrap:wrap">
          <span>스타일</span>
          <select id="thumbStyleSel" style="width:auto;padding:6px 8px">
            <option value="임팩트" selected>💥 임팩트 — 노랑 입체+기울임 (추천)</option>
            <option value="포인트">🎨 포인트 — 줄마다 색 교차</option>
            <option value="입체3D">🧱 입체 3D — 빨강 돌출 기둥</option>
            <option value="깔끔">⬜ 깔끔 — 반투명 띠 (기존)</option>
          </select>
          <input type="checkbox" id="thumbAiBg">
          <span class="hint">🖼 AI 배경 연출 — 집중선·스포트라이트 판을 AI가 그림 (Gemini 키)</span>
        </div>
        <div class="row" style="margin-top:6px">
          <div>
            <label style="margin-top:0">우상단 배지 <span class="hint">(선택 · 초록 라벨)</span></label>
            <input type="text" id="thumbBadge" placeholder="예) ✅ 자동 발행  /  직접 쓴 글 아닙니다">
          </div>
          <div>
            <label style="margin-top:0">배경 사진 <span class="hint">(선택 · 비우면 완성 영상 장면)</span></label>
            <input type="text" id="thumbBg" placeholder="내 사진 경로 붙여넣기 (png/jpg)">
          </div>
        </div>
        <button id="thumbMakeBtn" onclick="makeThumb(event)">이 제목으로 썸네일 만들기</button>
        <div id="thumbResult" class="hidden" style="margin-top:10px">
          <img id="thumbImg" style="width:100%;border-radius:10px;border:1px solid #262b3a" alt="썸네일">
          <div class="hint" id="thumbPath" style="margin-top:6px"></div>
        </div>
      </div>
    </div>
    <div class="err hidden" id="errBox"></div>
    <details class="hidden" id="rawErr" style="margin-top:8px">
      <summary class="hint" style="cursor:pointer">자세히 (원본 오류)</summary>
      <pre class="err" id="rawErrText" style="overflow-x:auto"></pre>
    </details>
    <button class="ghost" style="margin-top:14px" onclick="resetForm()">🏠 처음으로 (새 작업)</button>
  </div>

  <div class="card">
    <div style="font-weight:700">히스토리</div>
    <table id="histTable"><thead>
      <tr><th>시각</th><th>제목</th><th>목소리</th><th>상태</th><th></th></tr>
    </thead><tbody></tbody></table>
  </div>

  <div class="card hidden" id="productCard">
    <div class="backrow"><b>📇 내 제품 정보</b> <span class="hint">— 등록해 두면 AI가 이 사실만 근거로 대본·훅·키트를 써요 (지어내기 방지)</span></div>
    <div class="chk" style="gap:8px;margin-top:8px">
      <span>제품 고르기</span>
      <select id="prodSel" style="width:auto;min-width:180px" onchange="fillProductForm()"></select>
      <button class="ghost" style="padding:5px 10px" onclick="newProduct(event)">➕ 새 제품</button>
      <button class="ghost" style="padding:5px 10px;color:#ff9aa6" onclick="deleteProduct(event)">🗑 삭제</button>
    </div>
    <div class="row" style="margin-top:8px">
      <div><label>제품명 *</label><input type="text" id="prodName" placeholder="예) 곰대리 GIF 움짤 제작기"></div>
      <div><label>한 줄 소개</label><input type="text" id="prodDesc" placeholder="예) 클릭 3번으로 움짤을 만들어주는 프로그램"></div>
    </div>
    <label style="margin-top:8px">핵심 기능·차별점 <span class="hint">(줄당 1개, 3~5줄 — 대본의 근거가 돼요)</span></label>
    <textarea id="prodPoints" style="min-height:84px" placeholder="영상에서 원하는 구간만 골라 움짤로&#10;글자·스티커 넣기 지원&#10;결과물 용량 자동 최적화"></textarea>
    <div class="row" style="margin-top:8px">
      <div><label>타깃</label><input type="text" id="prodTarget" placeholder="예) 블로그·카페 운영자"></div>
      <div><label>말투 톤</label><input type="text" id="prodTone" placeholder="예) 친근한 / 전문적인"></div>
    </div>
    <div class="row" style="margin-top:8px">
      <div><label>링크</label><input type="text" id="prodLink" placeholder="예) https://..."></div>
      <div><label>금지 표현</label><input type="text" id="prodAvoid" placeholder="예) 무료라고 하지 말 것"></div>
    </div>
    <button style="margin-top:10px" onclick="saveProduct(event)">💾 저장</button>
    <details class="opt" style="margin-top:10px">
      <summary>✨ 붙여넣고 AI로 정리 <span class="hint">— 제품 소개 페이지 글을 통째로 붙여넣으면 위 칸을 자동으로 채워요 (Gemini 키)</span></summary>
      <textarea id="prodRaw" style="min-height:110px" placeholder="제품 소개 글 붙여넣기…"></textarea>
      <button class="ghost" style="margin-top:6px" onclick="summarizeProduct(event)">✨ AI로 정리해 채우기</button>
    </details>
    <button style="margin-top:12px" class="ghost" onclick="toggleProductCard()">닫기</button>
  </div>

  <div class="card hidden" id="apiCard">
    <div class="backrow"><b>🔑 API 연동</b> <span class="hint">— 키는 이 PC의 설정 파일에만 저장돼요 (외부 전송 없음)</span></div>
    <div style="border:1px solid #2c3350;border-radius:12px;padding:12px;margin-top:10px">
      <div style="display:flex;align-items:center;gap:8px;font-weight:700">🌟 Gemini (구글)
        <span class="hint" id="apiGeminiState" style="font-weight:400"></span></div>
      <div class="hint" style="margin-top:4px">쓰이는 곳: AI 대본 · AI 성우 목소리 · 장면 그림 · 영상 분석 · 업로드 키트
        — <a href="https://aistudio.google.com/apikey" target="_blank" style="color:#7a9bff">무료 발급 (aistudio.google.com)</a></div>
      <div style="display:flex;gap:6px;margin-top:8px">
        <input type="password" id="apiGeminiKey" placeholder="AIza... (붙여넣기)" style="flex:1">
        <button class="ghost" style="white-space:nowrap" onclick="saveApiKey(event,'gemini')">저장</button>
      </div>
    </div>
    <div style="border:1px solid #2c3350;border-radius:12px;padding:12px;margin-top:10px">
      <div style="display:flex;align-items:center;gap:8px;font-weight:700">🎙 ElevenLabs (일레븐랩스)
        <span class="hint" id="apiElevenState" style="font-weight:400"></span></div>
      <div class="hint" style="margin-top:4px">쓰이는 곳: 성우 보이스 목록 · 내 목소리 클로닝
        — <a href="https://elevenlabs.io" target="_blank" style="color:#7a9bff">elevenlabs.io (유료 구독)</a></div>
      <div style="display:flex;gap:6px;margin-top:8px">
        <input type="password" id="apiElevenKey" placeholder="일레븐랩스 API 키" style="flex:1">
        <button class="ghost" style="white-space:nowrap" onclick="saveApiKey(event,'elevenlabs')">저장</button>
      </div>
    </div>
    <div style="border:1px solid #2c3350;border-radius:12px;padding:12px;margin-top:10px">
      <div style="font-weight:700">🎤 GPT-SoVITS (무료 내 목소리 · 내 PC)</div>
      <div class="hint" style="margin-top:4px">키가 아니라 내 PC 프로그램 연결이에요 — 등록은
        <button class="ghost" style="padding:3px 10px" onclick="openVoice(event)">🎤 내 목소리 등록</button> 화면에서</div>
    </div>
    <div class="chk" style="gap:8px;margin-top:12px">
      <button class="ghost" style="color:#ff9aa6" onclick="clearAllKeys(event)">🔒 저장된 키 모두 삭제</button>
      <span class="hint">공용 PC였다면 쓰고 나서 지워주세요</span>
    </div>
    <button style="margin-top:12px" class="ghost" onclick="toggleApiCard()">닫기</button>
  </div>

  <div class="card hidden" id="settingsCard">
    <div style="font-weight:700">⚙ 설정 <span class="hint">— 필요한 묶음만 펼쳐서 바꾸세요 (저장하면 다음 작업부터 적용)</span></div>

    <details class="opt">
      <summary>📝 자막·제목 스타일 <span class="hint">— 크기 · 띠 · 강조 색 · 줄바꿈</span></summary>
      <div class="row" style="margin-top:4px">
        <div><label>자막 크기(px)</label><input type="number" id="setFontSize" min="40" max="120"></div>
        <div><label>외곽선 두께</label><input type="number" id="setOutline" min="0" max="8"></div>
        <div><label>자막 세로 여백</label><input type="number" id="setMarginV" min="100" max="800" step="10"></div>
        <div><label>한 줄 최대 글자수 <span class="hint">(넘으면 2줄, 0=끔)</span></label><input type="number" id="setWrapChars" min="0" max="40"></div>
      </div>
      <div class="row">
        <div><label>강조 색</label><input type="color" id="setHlColor" style="height:40px;padding:4px"></div>
      </div>
      <div class="chk"><input type="checkbox" id="setFade"><span>자막 등장 페이드</span></div>
      <div class="chk" style="gap:8px"><span>자막 등장 애니메이션</span>
        <select id="setSubAnim" style="width:auto;padding:6px 8px">
          <option value="none">없음</option>
          <option value="pop">팝 — 살짝 커지며 등장 (쇼츠 감성)</option>
          <option value="type">타이핑 — 글자가 하나씩 (인스타·틱톡 감성)</option>
          <option value="karaoke">카라오케 — 말하는 단어가 차오름 (편집·Whisper 자막)</option>
        </select></div>
      <div class="chk"><input type="checkbox" id="setHookBand"><span>상단 제목 배경 띠 (유튜브 썸네일 스타일 · 글자 뒤 어두운 띠)</span></div>
      <div class="chk"><input type="checkbox" id="setBand"><span>자막에도 배경 띠 (하단 자막 뒤에도 어두운 띠)</span></div>
    </details>

    <details class="opt">
      <summary>🎬 배경·모션 <span class="hint">— AI 영상 만들기의 배경 (줌 · AI 배경 이미지)</span></summary>
      <div class="row" style="margin-top:4px">
        <div><label>배경 모션</label>
          <select id="setMotion">
            <option value="zoom_in">줌인 (기본)</option>
            <option value="zoom_out">줌아웃</option>
            <option value="off">없음</option>
          </select></div>
        <div><label>줌 정도 (0.02~0.2)</label><input type="number" id="setMotionAmt" min="0.02" max="0.2" step="0.01"></div>
      </div>
      <div class="chk"><input type="checkbox" id="setAiImage"><span>AI 배경 이미지 생성 (Gemini · 키 없으면 자동 생략 — v0.45부터 기본 켬)</span></div>
      <div class="chk"><input type="checkbox" id="setSceneImg"><span>🖼 문장(장면)마다 새 이미지 — 말 타이밍에 맞춰 그림이 넘어가요 (끄면 1장+줌)</span></div>
      <div class="hint" style="margin:2px 0 0 26px">🤖 AI 영상 만들기 전용 (내 영상 편집·사진은 원본이 배경). Gemini 키가 있으면
        어떤 목소리를 골라도 적용돼요 (소리 점검용만 제외). 그림체는 만들기 폼의 「🖼 AI 배경 그림」에서.
        <b>실제로 어떤 배경이 쓰였는지는 완성 화면의 「🖼️ 배경: …」 표시로 확인</b> —
        AI 장면 이미지 N장 ✨ / AI 이미지 ✨ / 기본 그라데이션(사유)로 알려줍니다.</div>
    </details>

    <details class="opt">
      <summary>🔊 소리·목소리 <span class="hint">— BGM 볼륨 · 덕킹 · 문장 간격 · TTS 한도</span></summary>
      <div class="row" style="margin-top:4px">
        <div><label>BGM 볼륨(dB)</label><input type="number" id="setBgmVol" min="-40" max="0"></div>
        <div><label>문장 간격(ms)</label><input type="number" id="setGap" min="0" max="1000" step="10"></div>
        <div><label>분당 TTS 호출 한도</label><input type="number" id="setRpm" min="1" max="60"></div>
      </div>
      <div class="chk"><input type="checkbox" id="setDuck"><span>BGM 덕킹 (음성 나올 때 자동 감쇠 — 기본 켬, v0.44부터 편집·사진 영상에도 적용)</span></div>
      <div class="chk" style="gap:8px;flex-wrap:wrap"><span>내장 음성 목소리</span>
        <select id="setWinVoice" style="width:auto;max-width:330px;padding:6px 8px">
          <option value="">자동 (한국어 첫 번째)</option>
        </select>
        <button class="ghost" style="padding:5px 10px" onclick="previewWinVoice(event)">🔊 미리듣기</button>
        <span class="hint" id="winVoiceHint">이 PC에 설치된 Windows 음성 중 선택 — 목소리 추가는 Windows 설정 → 시간 및 언어 → 음성</span></div>
      <div class="chk" style="gap:8px"><span>내장 음성 말 속도</span>
        <select id="setWinRate" style="width:auto;padding:6px 8px">
          <option value="-2">느리게</option>
          <option value="0">보통 (기본)</option>
          <option value="2">살짝 빠르게 (추천)</option>
          <option value="4">빠르게</option>
        </select>
        <span class="hint">내장 음성(키 없이 쓰는 목소리·폴백)에 적용 — 제미나이/일레븐 보이스와는 별개</span></div>
    </details>

    <details class="opt">
      <summary>📦 내 채널 정보·브랜딩 <span class="hint">— 업로드 키트 문구 톤 + 인트로/아웃트로 (선택)</span></summary>
      <div class="row" style="margin-top:4px">
        <div><label>채널명</label><input type="text" id="setChName" placeholder="예) 곰대리의 자동화"></div>
        <div><label>채널 주제</label><input type="text" id="setChTopic" placeholder="예) 블로그·유튜브 자동화 꿀팁"></div>
        <div><label>타깃 시청자</label><input type="text" id="setChAudience" placeholder="예) 부업 시작하는 3040 직장인"></div>
      </div>
      <div class="row" style="margin-top:6px">
        <div><label>🎞 인트로 파일 <span class="hint">(영상 또는 사진 — 사진은 2.5초)</span></label>
          <input type="text" id="setIntroPath" placeholder="예) C:\\내채널\\인트로.mp4 — 비우면 없음"></div>
        <div><label>🎞 아웃트로 파일</label>
          <input type="text" id="setOutroPath" placeholder="예) C:\\내채널\\구독요청.mp4 — 비우면 없음"></div>
      </div>
      <div class="hint">넣으면 <b>모든 완성 영상</b>(AI 생성·편집·사진·배치·여러 쇼츠) 앞뒤에 자동으로 붙어요.
        해상도가 달라도 본편 크기에 맞춰줍니다. 파일이 없으면 조용히 건너뛰어요.</div>
    </details>

    <button onclick="saveSettings()">설정 저장</button>
  </div>

  <details id="logPanel" style="margin-top:16px">
    <summary class="hint" style="cursor:pointer">🪵 작업 로그 — 오류가 나면 펼쳐서 <b>[📋 복사]</b> 후 붙여넣어 주세요 <button class="ghost" style="padding:2px 8px;margin-left:6px" onclick="copyLogs(event)">📋 복사</button></summary>
    <pre id="logBox" style="max-height:260px;overflow:auto;background:#0d0f14;border:1px solid #2c3350;border-radius:8px;padding:10px;font-size:12px;line-height:1.55;white-space:pre-wrap;margin-top:8px">(아직 로그 없음)</pre>
  </details>
  <div style="text-align:center;margin-top:12px">
    <button class="ghost" onclick="diagnostic(event)">🩺 진단 리포트 보기 (문의할 때 [📋 복사]해서 붙여넣기)</button>
  </div>
  <details id="diagPanel" class="hidden" style="margin-top:8px">
    <summary class="hint" style="cursor:pointer">🩺 진단 리포트
      <button class="ghost" style="padding:2px 8px;margin-left:6px" onclick="copyDiag(event)">📋 복사</button>
      <button class="ghost" style="padding:2px 8px" onclick="openDiagFolder(event)">📂 저장 폴더 열기</button>
      <span class="hint" id="diagPath"></span></summary>
    <pre id="diagBox" style="max-height:340px;overflow:auto;background:#0d0f14;border:1px solid #2c3350;border-radius:8px;padding:10px;font-size:12px;line-height:1.55;white-space:pre-wrap;margin-top:8px"></pre>
  </details>
</div>

<script>
let currentJob = null, timer = null;
const $ = id => document.getElementById(id);
// 🔒 XSS 방어 (v0.70) — 제목·AI응답·경로 등 신뢰할 수 없는 값을 innerHTML에 넣기 전 이스케이프
const escHtml = s => String(s==null?'':s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const STAGE_KO = {queued:'⏳ 대기 중 (동시 한도에 자리가 나면 자동 시작)', cancelled:'✕ 취소됨',
                  script:'대본 생성', tts:'목소리 합성(TTS)', background:'배경 준비',
                  timeline:'타임라인 계산', render:'영상 렌더링',
                  review:'대본 검토 대기', done:'완료',
                  analyze:'무음 구간 분석', cut:'무음 잘라내기', stt:'음성 인식(자막 만들기)'};

document.querySelectorAll('input[name=prov]').forEach(r => r.onchange = () => {
  const isGemini = pick('prov') === 'gemini';
  $('keyRow').classList.toggle('hidden', !isGemini || window._hasGeminiKey);
  $('geminiOpts').classList.toggle('hidden', !isGemini);
  $('elevenOpts').classList.toggle('hidden', pick('prov') !== 'eleven_voice');
});

// ── 🎙 일레븐랩스 성우 보이스 (v0.46) — 내 계정 보이스 자동 불러오기 ──
async function loadElevenVoices(force){
  if(window._elevenLoaded && !force) return;
  window._elevenLoaded = true;
  const st = $('elevenListState'), st2 = $('narrElevenState');  // 제작 폼 + 내레이션 박스(편집·사진)
  if(st) st.textContent = '⏳ 일레븐랩스에서 목록 불러오는 중...';
  if(st2) st2.textContent = '⏳ 일레븐랩스 성우 불러오는 중...';
  try{
    const body = force ? JSON.stringify({refresh:true}) : '{}';
    const data = await (await fetch('/api/eleven_voices', {method:'POST', body})).json();
    const voices = data.voices || [];
    if(!voices.length){
      // 왜 비었는지 이유를 그대로 보여준다 (v0.64.1) — 조용한 빈 칸 금지
      if(st){
        if(data.no_key) st.textContent = '⬜ 키 미등록 — 첫 화면 「🔑 API 연동」에서 ElevenLabs 키를 저장한 뒤 🔄 다시 불러오기를 누르세요';
        else if(data.error) st.textContent = '⚠ 불러오기 실패: ' + data.error + ' → elevenlabs.io의 API Keys에서 권한 기본값 그대로 새 키를 만들어 다시 저장해 보세요';
        else st.textContent = '⚠ 계정에 보이스가 하나도 없어요 — elevenlabs.io의 Voices에서 담아주세요';
      }
      if(st2){
        if(data.no_key) st2.textContent = '일레븐랩스 키를 연동하면 성우 목소리가 여기에도 추가돼요 — 첫 화면 「🔑 API 연동」';
        else if(data.error) st2.textContent = '⚠ 일레븐랩스 목록 실패: ' + data.error;
        else st2.textContent = '';
      }
      return;
    }
    window._elevenData = voices;                       // ⭐ 즐겨찾기 렌더용 캐시 (v0.67)
    window._elevenFavs = data.favs || [];
    renderElevenLists();
    // 기억된 내레이션 보이스가 일레븐랩스면 목록이 채워진 지금 복원
    if(window._wantNarrVoice && [...$('narrVoiceSel').options].some(o => o.value === window._wantNarrVoice)){
      $('narrVoiceSel').value = window._wantNarrVoice;
      window._wantNarrVoice = '';
    }
    // 🤖 지난번 제작에 쓴 성우 복원 (v0.67 — 목록이 채워진 뒤에만 가능)
    const sel = $('elevenVoiceSel');
    if(window._wantGenElevenVoice){
      if([...sel.options].some(o => o.value === window._wantGenElevenVoice))
        sel.value = window._wantGenElevenVoice;
      window._wantGenElevenVoice = '';
    }
    // 🇰🇷 방금 담은 성우가 있으면 바로 선택 (v0.65) — 내레이션 목록에도 (v0.66)
    if(window._wantElevenVoice){
      if([...sel.options].some(o => o.value === window._wantElevenVoice))
        sel.value = window._wantElevenVoice;
      const nv2 = $('narrVoiceSel'), wantNv = 'el:' + window._wantElevenVoice;
      if(nv2 && [...nv2.options].some(o => o.value === wantNv)) nv2.value = wantNv;
      window._wantElevenVoice = '';
    }
    updateFavBtns();
    if(st) st.textContent = '✅ 성우 ' + voices.length + '명 — ★ 즐겨찾기는 맨 위로, (담은 성우)는 Starter부터 재생돼요';
    if(st2) st2.textContent = '🎙 일레븐랩스 성우 ' + voices.length + '명이 보이스 목록에 들어와 있어요 — ★는 즐겨찾기';
  } catch(e){
    window._elevenLoaded = false;
    if(st) st.textContent = '⚠ 서버와 통신 실패 — 컷대장 콘솔 창이 켜져 있는지 확인하고 🔄 다시 불러오기를 눌러주세요';
    if(st2) st2.textContent = '⚠ 서버와 통신 실패 — 🔄 를 눌러주세요';
  }
}

// ── ⭐ 성우 즐겨찾기 (v0.67) — ★는 맨 위, 저장돼서 다음에도 유지 ──
function renderElevenLists(){
  const voices = window._elevenData || [], favs = window._elevenFavs || [];
  const sel = $('elevenVoiceSel'), nv = $('narrVoiceSel');
  if(!voices.length || !sel) return;
  const rank = v => favs.includes(v.voice_id) ? 0 : (v.category === 'premade' ? 1 : 2);
  const sorted = [...voices].sort((a, b) => rank(a) - rank(b)
    || favs.indexOf(a.voice_id) - favs.indexOf(b.voice_id));
  const keepSel = sel.value, keepNv = nv ? nv.value : '';
  sel.innerHTML = '';
  if(nv) [...nv.options].filter(o => o.value.indexOf('el:') === 0).forEach(o => o.remove());
  for(const v of sorted){
    const star = favs.includes(v.voice_id) ? '★ ' : '';
    const tag = v.category === 'cloned' ? ' (내 클론)'
              : (v.category !== 'premade' ? ' (담은 성우)' : '');
    sel.add(new Option(star + v.name + tag, v.voice_id));
    if(nv) nv.add(new Option('🎙 ' + star + v.name + tag + ' (일레븐랩스)', 'el:' + v.voice_id));
  }
  if(keepSel && [...sel.options].some(o => o.value === keepSel)) sel.value = keepSel;
  if(nv && keepNv && [...nv.options].some(o => o.value === keepNv)) nv.value = keepNv;
}
function updateFavBtns(){
  const favs = window._elevenFavs || [];
  const b1 = $('elevenFavBtn'), b2 = $('narrFavBtn');
  if(b1){
    const v = ($('elevenVoiceSel')||{}).value || '';
    b1.textContent = favs.includes(v) ? '★ 즐겨찾기됨' : '☆ 즐겨찾기';
  }
  if(b2){
    const nvv = ($('narrVoiceSel')||{}).value || '';
    b2.textContent = (nvv.indexOf('el:') === 0 && favs.includes(nvv.slice(3))) ? '★' : '☆';
  }
}
async function toggleElevenFav(ev, which){
  ev.preventDefault();
  const raw = which === 'narr' ? (($('narrVoiceSel')||{}).value || '') : (($('elevenVoiceSel')||{}).value || '');
  const vid = which === 'narr' ? (raw.indexOf('el:') === 0 ? raw.slice(3) : '') : raw;
  if(!vid){ alert('일레븐랩스 성우를 고른 상태에서 ★를 눌러주세요'); return; }
  const favs = window._elevenFavs || [];
  const on = !favs.includes(vid);
  try{
    const d = await (await fetch('/api/eleven_fav', {method:'POST',
      body: JSON.stringify({voice_id: vid, on})})).json();
    if(d.error){ alert(d.error); return; }
    window._elevenFavs = d.favs || [];
    renderElevenLists();
    updateFavBtns();
  } catch(e){ alert('서버 통신 실패 — 다시 시도해주세요'); }
}

// ── 🇰🇷 한국어 성우 담기 (v0.65) — 라이브러리 목록·미리듣기·➕ 담기 ──
// v0.66: 제작·편집·사진 어디서든 같은 패널 — 렌더러 공용 + 목록 1회 캐시
function onElevenBrowse(el){ return browseEleven(el, 'elevenBrowseState', 'elevenBrowseList'); }
function onNarrBrowse(el){ return browseEleven(el, 'narrBrowseState', 'narrBrowseList'); }
async function browseEleven(el, stId, listId){
  const st = $(stId), list = $(listId);
  if(!el.open || !st || !list || list.dataset.loaded === '1') return;
  st.textContent = '⏳ 한국어 성우 목록 불러오는 중...';
  let rows = window._elevenBrowseRows;
  if(!rows){
    try{
      const data = await (await fetch('/api/eleven_browse', {method:'POST', body:'{}'})).json();
      rows = data.voices || [];
      if(!rows.length){
        st.textContent = data.error
          ? '⚠ 못 불러왔어요: ' + data.error
          : '⚠ 지금은 라이브러리 응답이 비어 있어요 — 잠시 후 다시 열어보세요';
        return;
      }
      window._elevenBrowseRows = rows;
    } catch(e){
      st.textContent = '⚠ 서버 통신 실패 — 접었다 다시 열어보세요';
      return;
    }
  }
  list.dataset.loaded = '1';
  st.textContent = '▶ 듣고 [➕ 담기] — 담기는 무료예요. 단, 담은 성우로 영상 제작은 Starter(월 $6)부터 — 무료 플랜은 기본 성우(영어 이름)나 ⭐ AI 성우로 만들 수 있어요';
  list.innerHTML = '';
  for(const v of rows){
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid #232838';
      const play = document.createElement('button');
      play.className = 'ghost'; play.textContent = '▶';
      play.onclick = (e) => { e.preventDefault(); playBrowsePreview(v.preview_url, play); };
      const info = document.createElement('div');
      info.style.cssText = 'flex:1;min-width:0';
      const nm = document.createElement('div'); nm.textContent = v.name; nm.style.fontWeight = '700';
      const ds = document.createElement('div'); ds.className = 'hint';
      ds.textContent = v.desc || '';
      info.appendChild(nm); info.appendChild(ds);
      const add = document.createElement('button');
      add.className = 'ghost'; add.textContent = '➕ 담기';
      add.onclick = (e) => { e.preventDefault(); addBrowseVoice(v, add); };
      row.appendChild(play); row.appendChild(info); row.appendChild(add);
      list.appendChild(row);
  }
}
function playBrowsePreview(url, btn){
  if(window._browseAudio){
    window._browseAudio.pause();
    if(window._browseBtn) window._browseBtn.textContent = '▶';
    const same = window._browseBtn === btn;
    window._browseAudio = null; window._browseBtn = null;
    if(same) return;                       // 같은 버튼 다시 누르면 정지만
  }
  if(!url){ alert('이 성우는 미리듣기 샘플이 없어요 — 담은 뒤 위의 🔊 미리듣기로 들어보세요'); return; }
  const a = new Audio(url);
  a.onended = () => { btn.textContent = '▶'; window._browseAudio = null; window._browseBtn = null; };
  a.onerror = () => { btn.textContent = '▶'; };
  a.play(); btn.textContent = '⏹';
  window._browseAudio = a; window._browseBtn = btn;
}
async function addBrowseVoice(v, btn){
  btn.disabled = true; btn.textContent = '담는 중...';
  try{
    const d = await (await fetch('/api/eleven_add', {method:'POST', body: JSON.stringify(
      {owner_id: v.owner_id, voice_id: v.voice_id, name: v.name})})).json();
    if(d.error){ btn.disabled = false; btn.textContent = '➕ 담기'; alert('⚠ ' + d.error); return; }
    btn.textContent = '✅ 담김';
    window._wantElevenVoice = d.voice_id || v.voice_id;   // 채워지면 자동 선택
    loadElevenVoices(true);
  } catch(e){
    btn.disabled = false; btn.textContent = '➕ 담기';
    alert('서버 통신 실패 — 다시 시도해주세요');
  }
}

async function previewElevenVoice(ev){
  ev.preventDefault();
  const btn = ev.target;
  btn.disabled = true; btn.textContent = '합성 중...';
  try{
    const res = await fetch('/api/preview', {method:'POST', body: JSON.stringify({
      tts_provider: 'elevenlabs', voice: $('elevenVoiceSel').value,
    })});
    const data = await res.json();
    if(data.error){ alert(data.error); } else { new Audio(data.url).play(); }
  } finally { btn.disabled = false; btn.textContent = '🔊 미리듣기'; }
}

function pick(name){ return document.querySelector(`input[name=${name}]:checked`).value; }

// ── 첫 화면(홈) ↔ 만들기 폼 전환 (v0.36 초보자 UI) ──
function openMode(kind){
  window._view = kind;                       // 'gen'|'edit'|'photo'|'weblink'|'sections'|'shop'
  $('homeCard').classList.add('hidden');
  $('voiceCard').classList.add('hidden');
  $('weblinkCard').classList.toggle('hidden', kind !== 'weblink');  // 🔗 전용 탭 (v0.79)
  $('sectionCard').classList.toggle('hidden', kind !== 'sections'); // 🎞 구간 대본 (v0.80)
  $('shopCard').classList.toggle('hidden', kind !== 'shop');        // 🛒 쇼핑 상품 (v0.89)
  $('formCard').classList.toggle('hidden', kind !== 'gen');
  $('editCard').classList.toggle('hidden', kind === 'gen' || kind === 'weblink' || kind === 'sections' || kind === 'shop');
  if(kind === 'weblink'){ initWeblinkCard(); return; }
  if(kind === 'sections'){ initSectionCard(); return; }
  if(kind === 'shop'){ initShopCard(); return; }
  if(kind !== 'gen'){
    window._editKind = kind;
    $('videoBlock').classList.toggle('hidden', kind === 'photo');
    $('photoBlock').classList.toggle('hidden', kind !== 'photo');
    // 사진 모드엔 음성 인식·무음 컷이 없음 → 세부 설정을 숨겨 화면 단순화
    $('optAdv').classList.toggle('hidden', kind === 'photo');
    $('editTitleLabel').textContent = kind === 'photo' ? '📸 사진으로 영상 만들기' : '✂️ 내 영상 편집';
    if(!window._sttFilled) loadStt();
  }
}
function showHome(ev){
  if(ev) ev.preventDefault();
  window._view = 'home';
  $('homeCard').classList.remove('hidden');
  $('formCard').classList.add('hidden');
  $('editCard').classList.add('hidden');
  $('voiceCard').classList.add('hidden');
  $('weblinkCard').classList.add('hidden');
  $('sectionCard').classList.add('hidden');
  $('shopCard').classList.add('hidden');
}
// ── 🎤 내 목소리 등록 전용 화면 (v0.37) — 어디서 열었든 [← 돌아가기]로 복귀 ──
function openVoice(ev){
  if(ev) ev.preventDefault();
  window._voiceReturn = window._view || 'home';
  $('homeCard').classList.add('hidden');
  $('formCard').classList.add('hidden');
  $('editCard').classList.add('hidden');
  $('weblinkCard').classList.add('hidden');
  $('sectionCard').classList.add('hidden');
  $('shopCard').classList.add('hidden');
  $('voiceCard').classList.remove('hidden');
  window._view = 'voice';
}
function closeVoice(ev){
  if(ev) ev.preventDefault();
  $('voiceCard').classList.add('hidden');
  const r = window._voiceReturn;
  if(r === 'gen' || r === 'edit' || r === 'photo' || r === 'weblink' || r === 'sections') openMode(r); else showHome();
}
function markMyVoice(){
  for(const id of ['myVoiceState', 'myVoiceStateNarr', 'homeVoiceState']){
    const el = $(id); if(el) el.textContent = '✅ 등록됨';
  }
}
async function previewMyVoice(ev, prov){
  ev.preventDefault();
  if(prov === 'sovits' && !$('sovitsRef').value.trim()){
    alert('먼저 참조 녹음과 문장을 넣고 [등록(저장)]을 눌러주세요'); return;
  }
  if(prov === 'elevenlabs' && !window._hasElevenKey && !$('elevenKey').value.trim()){
    alert('먼저 녹음 파일과 ElevenLabs 키를 넣고 [등록]을 눌러주세요'); return;
  }
  const btn = ev.target; const old = btn.textContent;
  btn.disabled = true; btn.textContent = '합성 중...';
  try{
    const body = {tts_provider: prov, text: '안녕하세요, 내 목소리 미리듣기입니다.'};
    if(prov === 'elevenlabs' && $('elevenKey').value.trim()){
      body.elevenlabs_key = $('elevenKey').value.trim(); body.save_key = true;
    }
    const data = await (await fetch('/api/preview', {method:'POST', body: JSON.stringify(body)})).json();
    if(data.error){ alert(data.error); } else { new Audio(data.url).play(); }
  } finally { btn.disabled = false; btn.textContent = old; }
}
function onFinishChange(){
  const auto = pick('editFinish') === 'auto';
  $('autoOptRow').classList.toggle('hidden', !auto);
  $('finishHint').textContent = auto
    ? '검토 없이 끝까지 자동으로 만들어요. Gemini 키가 있으면 AI가 자막을 다듬고 핵심 구간까지 골라줍니다.'
    : '중간에 자막을 확인하는 화면이 한 번 나와요 — 오타만 고치고 [완성]을 누르면 됩니다.';
}
function applyTargetPreset(){
  const p = $('autoTargetPreset').value;
  const n = $('autoTargetSec');
  n.classList.toggle('hidden', p !== 'custom');
  if(p !== 'custom') n.value = p;
  ensureShortsLayout();
}
function ensureShortsLayout(){
  // 📐 쇼츠 모드(길이 목표 있음)인데 '원본 비율 유지'가 기억돼 있으면 세로로 자동 전환 (v0.76.1)
  // — "쇼츠로 나눴는데 가로로 나와요" 방지. 사용자가 다시 원본 비율을 고르면 그대로 둔다.
  if((($('autoTargetPreset')||{}).value) === '0') return;
  const keep = document.querySelector('input[name=editLayout][value=keep]');
  const sh = document.querySelector('input[name=editLayout][value=shorts]');
  const h = $('layoutAutoHint');
  if(keep && keep.checked && sh){
    sh.checked = true;
    if(h){ h.textContent = '📐 쇼츠 모드라 세로(9:16)로 자동 선택했어요 — 원본 비율을 원하면 위에서 다시 고르세요'; h.classList.remove('hidden'); }
  }
}
function onAutoMultiChange(){
  const multi = $('autoMultiSel').value === 'multi';
  $('autoLenLabel').textContent = multi ? '쇼츠 1개당 길이' : '완성 길이';
  $('autoMultiHint').textContent = multi
    ? '예) 10분 영상 ÷ 60초 = 약 10개 (edited_1.mp4, edited_2.mp4 …)' : '';
  const p = $('autoTargetPreset');
  if(multi && p.value === '0'){ p.value = '60'; applyTargetPreset(); }  // 나누기엔 길이 필수
  ensureShortsLayout();
}
// 지난번 편집 세팅 복원 (v0.38) — 경로·주제·대본만 빼고 전부 이어받아 "영상만 바꿔 반복"
function applyEditLast(el){
  if(!el || !Object.keys(el).length) return;
  const set = (id, v) => { const e = $(id); if(e && v !== undefined && v !== null) e.value = String(v); };
  const chk = (id, v) => { const e = $(id); if(e && v !== undefined && v !== null) e.checked = !!v; };
  set('editSpeedSel', el.speed); set('editTempoSel', el.tempo||''); set('autoQualitySel', el.quality);
  set('denoiseSel', el.denoise); set('origAudioSel', el.orig_audio);
  if(el.orig_audio && el.orig_audio !== 'keep') window._origTouched = true;  // 복원값 보호
  set('bgmEditSel', el.bgm); set('bgmVolSel', el.bgm_db);
  set('hookSizeSel', el.hook_scale); set('hookStyleSel', el.hook_style); set('editSubStyleSel', el.sub_style); set('editToneSel', el.tone); set('photoSec', el.photo_sec);
  syncDecorChips();
  set('narrStyleSel', el.narr_style); chk('narrSubsOnly', el.narr_subs_only);
  set('narrFitSel', el.narr_fit); set('transSel', el.transition);
  if(el.narr_voice && [...$('narrVoiceSel').options].some(o => o.value === el.narr_voice))
    $('narrVoiceSel').value = el.narr_voice;
  else if((el.narr_voice || '').startsWith('el:'))
    window._wantNarrVoice = el.narr_voice;   // 일레븐랩스 목록은 늦게 채워짐 → 로드 후 복원
  chk('autoSubChk', el.auto_subtitle); chk('cutSilenceChk', el.cut_silence);
  chk('editColdOpen', el.cold_open); chk('editHookVoice', el.hook_voice);  // 🪝 훅 팩 (v0.75)
  chk('editFillerCut', el.filler_cut); chk('editTakeClean', el.take_clean);  // 🧹 말 다듬기 (v0.76)
  set('whisperModelSel', el.whisper_model);
  window._wantStt = el.stt_provider || '';   // STT 목록은 늦게 채워짐 → loadStt에서 적용
  const lay = document.querySelector('input[name=editLayout][value="' + (el.layout || 'shorts') + '"]');
  if(lay) lay.checked = true;
  const fin = document.querySelector('input[name=editFinish][value="' + (el.auto_edit ? 'auto' : 'review') + '"]');
  if(fin) fin.checked = true;
  if($('autoMultiSel')) $('autoMultiSel').value = el.auto_multi ? 'multi' : 'one';
  const t = String(el.auto_target_sec !== undefined && el.auto_target_sec !== null ? el.auto_target_sec : 30);
  $('autoTargetPreset').value = ['30','60','0'].includes(t) ? t : 'custom';
  applyTargetPreset();
  if($('autoTargetPreset').value === 'custom') $('autoTargetSec').value = t;
  onFinishChange(); onAutoMultiChange(); toggleAutoSub();
}

const STT_KO = {whisper:'내장 Whisper (무료·오프라인)', gemini:'Gemini (내 키)', openai:'OpenAI (내 키)'};
async function loadStt(){
  const av = (await (await fetch('/api/state')).json()).stt_available || {};
  const sel = $('sttSel'); sel.innerHTML = '';
  // 사용 가능한 것 우선, 없으면 안내
  const order = ['whisper','gemini','openai'];
  let any = false;
  for(const k of order){ if(av[k]){ sel.add(new Option(STT_KO[k], k)); any = true; } }
  if(!any){
    sel.add(new Option('Gemini (키 입력 필요)', 'gemini'));
  }
  // 지난번 세팅 복원 — 목록에 있는 값이면 그대로
  if(window._wantStt && [...sel.options].some(o => o.value === window._wantStt))
    sel.value = window._wantStt;
  window._sttFilled = true;
  updateSttHint();
  sel.onchange = updateSttHint;
}
function updateSttHint(){
  const v = $('sttSel').value;
  $('editKeyRow').classList.toggle('hidden', v !== 'gemini' || window._hasGeminiKey);
  if($('whisperModelRow')) $('whisperModelRow').classList.toggle('hidden', v !== 'whisper');
  $('sttHint').textContent = v === 'whisper'
    ? '최초 1회 모델 다운로드(수십 MB). 이후 무료·오프라인.'
    : v === 'gemini' ? '내 Gemini 키 사용. 구간마다 호출돼 조금 걸릴 수 있어요.'
    : '내 OpenAI 키 사용.';
}

const PASTE_TIP = '\\n\\n창이 안 보이면: 탐색기에서 영상 파일을 Shift+우클릭 → "경로로 복사" → 아래 칸에 붙여넣으세요.';
async function pickFile(ev){
  ev.preventDefault();
  const btn = ev.target;
  btn.disabled = true; btn.textContent = '창 여는 중…';
  // 창이 브라우저 뒤에 떠서 안 보일 때 대비 안내
  const hint = setTimeout(()=>{ btn.textContent = '작업표시줄 확인 ↓'; }, 2500);
  try{
    const data = await (await fetch('/api/pick_file', {method:'POST', body:'{}'})).json();
    if(data.error){ alert(data.error + PASTE_TIP); }
    else if(data.path){ $('editVideo').value = data.path; }
    // 취소면 그대로 둠
  } catch(e){ alert('파일 선택 창을 열 수 없습니다: ' + e + PASTE_TIP); }
  finally { clearTimeout(hint); btn.disabled = false; btn.textContent = '📁 영상 선택'; }
}

// 종류별 선택 창을 열어 입력칸에 채움 (v0.51 — 폴더/그림/소리)
async function pickInto(ev, targetId, kind){
  ev.preventDefault();
  const btn = ev.target; btn.disabled = true;
  const label = btn.textContent;
  const hint = setTimeout(()=>{ btn.textContent = '작업표시줄 확인 ↓'; }, 2500);
  try{
    const data = await (await fetch('/api/pick_file', {method:'POST',
      body: JSON.stringify({kind: kind || 'video'})})).json();
    if(data.error){ alert(data.error + PASTE_TIP); }
    else if(data.path){ $(targetId).value = data.path; }
  } catch(e){ alert('선택 창을 열 수 없습니다: ' + e + PASTE_TIP); }
  finally { clearTimeout(hint); btn.disabled = false; btn.textContent = label; }
}

function toggleAutoSub(){
  // 자막 끄면 음성인식 관련 항목 숨김
  const on = $('autoSubChk').checked;
  $('sttSel').closest('div').style.opacity = on ? '1' : '0.4';
  $('sttSel').disabled = !on;
}
function onScriptInput(){
  // 대본을 붙여넣으면 음성 인식은 생략됨을 표시
  const has = ($('editScript').value || '').trim().length > 0;
  $('sttSel').closest('div').style.opacity = has ? '0.4' : ($('autoSubChk').checked ? '1' : '0.4');
  $('sttSel').disabled = has || !$('autoSubChk').checked;
  $('scriptHint').innerHTML = has
    ? '✅ <b>이 대본을 사용</b>합니다 — 음성 인식은 건너뜁니다. (다음 화면에서 타이밍·줄을 다듬을 수 있어요)'
    : '붙여넣으면 <b>음성 인식을 건너뛰고</b> 이 대본을 영상 타이밍에 맞춰 자막으로 넣어요 (오인식·비용 없음). 내레이션 없는 영상에도 쓸 수 있어요.';
}

function onNarrModeChange(){
  const file = (document.querySelector("input[name='narrMode'][value='file']")||{}).checked;
  $('narrAiBox').classList.toggle('hidden', !!file);
  $('narrFileBox').classList.toggle('hidden', !file);
}

async function startEdit(){
  const kind = window._editKind || 'edit';
  const video = kind === 'photo' ? '' : $('editVideo').value.trim();
  const photos = kind === 'photo' ? (($('photoPath')||{}).value||'').trim() : '';
  if(kind === 'photo' && !photos){ alert('사진 폴더(또는 사진 파일들) 경로를 넣어주세요'); return; }
  if(kind !== 'photo' && !video){ alert('편집할 영상을 먼저 골라주세요 — [📁 영상 선택] 버튼을 눌러보세요'); return; }
  if(pick('editFinish') === 'auto' && ($('autoMultiSel')||{}).value === 'multi'
     && !(+$('autoTargetSec').value)){
    alert('여러 개로 나누려면 쇼츠 1개당 길이를 정해주세요 (예: 60초)'); return;
  }
  const nv = ($('narrVoiceSel')||{}).value||'';
  const narrFileMode = !!(document.querySelector("input[name='narrMode'][value='file']")||{}).checked;
  const narrFileVal = narrFileMode ? (($('narrFile')||{}).value||'').trim() : '';
  if(narrFileMode && !narrFileVal){
    alert('🎤 녹음 파일을 골라주세요 — [🎵 녹음 파일 고르기] 버튼을 눌러보세요'); return;
  }
  let editKey = $('editGeminiKey').value;
  // 내레이션 보이스는 제미나이 키가 있어야 적용 — 없으면 여기서 물어봐 저장
  const subsOnly = ($('narrSubsOnly')||{}).checked;
  const wantAnalyze = !narrFileMode && !!(($('narrAnalyzeChk')||{}).checked);
  const wantScriptTts = !narrFileMode && !!(($('scriptTtsChk')||{}).checked)
    && !!(($('editScript')||{}).value||'').trim();   // 🔊 대본 읽어주기 (v0.78)
  if(!narrFileMode && ((($('narrTopic')||{}).value||'').trim() || wantAnalyze || wantScriptTts) && !window._hasGeminiKey && !editKey){
    editKey = ensureGeminiKey();   // 대본 품질(+목소리)에 필요 — 화면 분석은 키 필수
    if(wantAnalyze && !editKey){ alert('🧠 화면 보고 대본 자동은 제미나이 키가 꼭 필요해요 (무료 발급: aistudio.google.com/apikey)'); return; }
    if(!editKey && !subsOnly && nv && nv !== '__mine__' && nv !== '__sovits__'
       && !confirm('제미나이 키가 없으면 보이스 선택 없이 내장 음성으로 만들어져요.\\n그래도 진행할까요?')) return;
  }
  const body = {
    video_path: video, layout: pick('editLayout'), hook: $('editHook').value,
    auto_subtitle: $('autoSubChk').checked, cut_silence: $('cutSilenceChk').checked,
    photo_path: photos, photo_sec: +(($('photoSec')||{}).value)||15,
    hook_scale: +(($('hookSizeSel')||{}).value)||1,
    hook_style: (($('hookStyleSel')||{}).value)||'기본',
    hook_font: (($('editHookFontSel')||{}).value)||'',
    hook_tilt: !!(($('editHookTiltChk')||{}).checked),
    sub_font: (($('editSubFontSel')||{}).value)||'',
    sub_style: (($('editSubStyleSel')||{}).value)||'기본',
    tone: (($('editToneSel')||{}).value)||'기본',
    denoise: $('denoiseSel').value,
    narr_topic: narrFileMode ? '' : (($('narrTopic')||{}).value||''),
    narr_analyze: !narrFileMode && !!(($('narrAnalyzeChk')||{}).checked),  // 🧠 화면 분석 대본 (v0.69)
    narr_len: (document.querySelector("input[name=narrLen]:checked")||{}).value || 'summary',  // v0.71
    narr_target_sec: +(($('narrLenSec')||{}).value) || 60,                 // v0.71 요약 길이
    narr_file: narrFileVal,
    narr_subs_only: (($('narrSubsOnly')||{}).checked)||false,
    narr_voice: nv, narr_style: ($('narrStyleSel')||{}).value||'',
    narr_fit: (($('narrFitSel')||{}).value)||'freeze',
    transition: (($('transSel')||{}).value)||'none',
    orig_audio: $('origAudioSel').value,
    bgm: $('bgmEditSel').value, bgm_db: +$('bgmVolSel').value,
    wm_path: ($('wmPath')||{}).value||'', wm_pos: ($('wmPos')||{}).value||'tr',
    wm_scale: +(($('wmScale')||{}).value)||0.14,
    speed: +$('editSpeedSel').value || 1,
    tempo: (($('editTempoSel')||{}).value)||'',   // ⚡ 빠른 템포 — 몽타주 컷 밀도 (v0.73)
    quality: (($('autoQualitySel')||{}).value)||'standard',
    cold_open: !!(($('editColdOpen')||{}).checked),   // ⚡ 첫 3초 티저 (v0.75)
    hook_voice: !!(($('editHookVoice')||{}).checked), // 🎙 후킹 보이스 (v0.75)
    filler_cut: !!(($('editFillerCut')||{}).checked), // 🧹 추임새 컷 (v0.76)
    take_clean: !!(($('editTakeClean')||{}).checked), // ↻ 반복 정리 (v0.76)
    auto_edit: pick('editFinish') === 'auto', auto_target_sec: +$('autoTargetSec').value||0,
    auto_multi: (($('autoMultiSel')||{}).value) === 'multi',
    script: $('editScript').value,
    script_tts: !!(($('scriptTtsChk')||{}).checked),  // 🔊 붙여넣은 대본을 목소리로 (v0.78)
    stt_provider: $('sttSel').value, whisper_model: ($('whisperModelSel')||{}).value || 'small',
    gemini_key: editKey, save_key: true,
  };
  const res = await fetch('/api/edit', {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'edit';
  window._subLoaded = false;
  window._kitLoaded = false;
  $('kitBox').classList.add('hidden'); $('kitBody').classList.add('hidden');
  $('editBtn').disabled = true;
  $('editCard').classList.add('hidden');   // 진행 화면에 집중 (🏠 처음으로 로 복귀)
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('subEditBox').classList.add('hidden');
  $('rawErr').classList.add('hidden'); $('noteText').textContent='';
  poll();
  timer = setInterval(poll, 900);
}

// ── 훅 제목 AI 추천 (v0.8) ──
async function suggestHooks(ev, topicId, targetId){
  ev.preventDefault();
  const ctx = ($(topicId).value || '').trim();
  if(!ctx){ alert('주제/키워드를 먼저 입력하세요'); return; }
  const btn = ev.target.closest('button') || ev.target;  // 버튼 안 힌트 클릭도 안전
  btn.disabled = true; const old = btn.textContent; btn.textContent = '추천 중…';
  const cands = $(targetId + 'Cands'); cands.innerHTML = '';
  try {
    const key = ensureGeminiKey();
    const data = await (await fetch('/api/suggest_hooks', {method:'POST',
      body: JSON.stringify({context: ctx, gemini_key: key, save_key: true,
        product: (($('genProductSel')||{}).value)||'',
        context_memo: (($('genContext')||{}).value)||''})})).json();
    if(data.error){ alert(data.error); return; }
    (data.hooks || []).forEach(h => {
      const b = document.createElement('button');
      b.textContent = h;
      b.onclick = (e) => { e.preventDefault(); $(targetId).value = h; cands.innerHTML='';
        if(targetId === 'genHook') renderGenHookPreview(); else if(targetId === 'editHook') renderHookPreview(); };
      cands.appendChild(b);
    });
    if(!(data.hooks||[]).length) cands.innerHTML = '<span class="hint">추천 결과가 없습니다. 키워드를 바꿔보세요.</span>';
  } finally { btn.disabled = false; btn.textContent = old; }
}

// ── 자막 검토·수정 (Phase 1) ──
function fmtTime(us){ const s=us/1e6; const m=Math.floor(s/60); return m+':'+(s%60).toFixed(1).padStart(4,'0'); }
function renderSubRows(){
  const box = $('subList'); box.innerHTML='';
  (window._subs||[]).forEach((sub, i) => {
    const row = document.createElement('div');
    const dropped = sub.keep===false;
    row.className='subrow subrowbtns'+(dropped?' dropped':''); row.id='subrow'+i;
    row.style.cssText='display:flex;gap:5px;align-items:flex-start;margin-bottom:6px;padding:3px;border-radius:8px';
    // 🔎 인식 신뢰도 낮은 줄 = 붉은 점선 밑줄 / ↻ 반복 테이크 후보 = 배지 (v0.76)
    const lowConf = (sub.conf !== undefined && sub.conf < 0.45);
    const confStyle = lowConf ? 'border-bottom:2px dashed #e5484d;' : '';
    const repBadge = sub.repeat
      ? `<span title="앞뒤로 거의 같은 말이 또 있어요 — 반복(NG) 테이크로 보여요. [↻ 반복 정리]를 누르면 마지막 테이크만 남아요" style="padding-top:8px;color:#f0a020;font-weight:700">↻</span>`
      : '';
    row.innerHTML =
      `<input type="checkbox" class="keepchk" ${dropped?'':'checked'} title="이 구간을 쇼츠에 넣기" onchange="window._subs[${i}].keep=this.checked; renderSubRows(); updateKeepInfo()">`+
      repBadge+
      `<button class="ghost" title="이 줄부터 재생" onclick="seekCut(${sub.start_us})">▶</button>`+
      `<span class="hint" style="min-width:50px;padding-top:9px;cursor:pointer" title="이 지점 재생" onclick="seekCut(${sub.start_us})">${fmtTime(sub.start_us)}</span>`+
      `<input type="text" style="flex:1;${confStyle}" ${lowConf?'title="음성 인식이 불확실한 줄이에요 — 한번 확인해 주세요"':''} value="${escHtml(sub.text||'')}" onfocus="pauseCut()" oninput="window._subs[${i}].text=this.value">`+
      `<button class="ghost" title="위 줄과 합치기" onclick="mergeSub(${i})" ${i===0?'disabled':''}>⬆</button>`+
      `<button class="ghost" title="이 줄을 둘로 나누기" onclick="splitSub(${i})">✂</button>`+
      `<button class="ghost" title="자막+영상 구간 통째 삭제 (브루식 — 체크박스로 복구)" onclick="dropSeg(${i})">🗑</button>`+
      `<button class="ghost" title="자막만 삭제 (영상은 유지)" onclick="delSub(${i})">✕</button>`;
    box.appendChild(row);
  });
  updateKeepInfo();
}
// ── 쇼츠 핵심 추출: 고른 구간만 남기기 (v0.10) ──
function updateKeepInfo(){
  const info=$('keepInfo'); if(!info) return;
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  const kept=subs.filter(s=>s.keep!==false);
  const dur=kept.reduce((a,s)=>a+(s.end_us-s.start_us),0)/1e6;
  const btn=$('renderBtn');
  if(!subs.length){ info.textContent='자막 없음'; if(btn) btn.textContent='✅ 자막 없이 완성'; return; }
  if(kept.length===subs.length){
    info.textContent='전체 '+dur.toFixed(1)+'초';
    if(btn) btn.textContent='✅ 이 자막으로 완성 (전체)';
  } else {
    info.textContent='선택 '+kept.length+'/'+subs.length+'줄 · 약 '+dur.toFixed(1)+'초';
    if(btn) btn.textContent='✂️ 선택 구간만 쇼츠로 완성 (약 '+Math.round(dur)+'초)';
  }
}
function selectAll(on, ev){ if(ev)ev.preventDefault(); (window._subs||[]).forEach(s=>s.keep=on); renderSubRows(); }
function cleanRepeats(ev){  // ↻ 반복(NG) 테이크 원클릭 정리 (v0.76) — 마지막 테이크만 유지
  if(ev)ev.preventDefault();
  let n=0;
  (window._subs||[]).forEach(s=>{ if(s.repeat && s.keep!==false){ s.keep=false; n++; } });
  renderSubRows();
  const b=$('cleanRepeatsBtn'); if(b) b.style.display='none';
  if(n) alert('반복(NG) 테이크 '+n+'곳을 뺐어요 — 마지막 테이크만 남습니다.\\n잘못 골랐으면 그 줄 체크박스를 다시 켜면 복구돼요.');
}
async function aiHighlights(ev){
  if(ev)ev.preventDefault();
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  if(!subs.length){ alert('먼저 자막이 있어야 핵심을 고를 수 있어요'); return; }
  const target=parseInt($('hlTarget').value||'30');
  const key=ensureGeminiKey();  // 키 없으면 붙여넣기 창(취소하면 대략 추천으로 진행)
  const btn=ev.target; btn.disabled=true; const old=btn.textContent; btn.textContent='고르는 중…';
  try{
    const data=await (await fetch('/api/suggest_highlights',{method:'POST',
      body:JSON.stringify({subtitles:subs, target_sec:target, gemini_key:key, save_key:true})})).json();
    if(data.error){ alert(data.error); return; }
    const keep=new Set(data.keep||[]);
    let fi=0;
    (window._subs||[]).forEach(s=>{ if(!(s.text||'').trim()) return; s.keep=keep.has(fi); fi++; });
    renderSubRows();
    if(data.ai) window._hasGeminiKey=true;
    const r=$('hlReason'); if(r) r.textContent=(data.ai?'✨ AI 추천: ':'ℹ 대략 추천(제미나이 키 넣으면 문맥으로 골라요): ')+(data.reason||'');
  } finally { btn.disabled=false; btn.textContent=old; }
}
// 제미나이 키 확보 — 저장된 키 없으면 그 자리에서 붙여넣기 (PC에 저장 → 다음부턴 안 물음)
function ensureGeminiKey(){
  if(window._hasGeminiKey) return '';
  const k=(($('editGeminiKey')||{}).value||'') || (($('geminiKey')||{}).value||'');
  if(k.trim()) return k.trim();
  const v=prompt('제미나이(Gemini) API 키를 붙여넣어 주세요.\\n\\n· 무료 발급: aistudio.google.com/apikey\\n· 이 PC에 저장돼 다음부터는 묻지 않아요');
  return (v||'').trim();
}

// AI로 자막(대본) 다듬기 — 발음 오인식을 문맥 기반으로 자연스럽게 교정
// ── 훅 제목 스튜디오 (v0.31) — 색 칩·크기·실시간 미리보기 ──
const HOOK_COLORS = {'노랑':'#FFD400','빨강':'#FF3B30','초록':'#34C759','파랑':'#0A84FF',
  '주황':'#FF9500','분홍':'#FF375F','하늘':'#5AC8FA','민트':'#31E1C4','보라':'#BF5AF2','흰':'#FFFFFF'};

function initHookChips(){
  // v0.52: 편집 폼(editHook)과 생성 폼(genHook) 양쪽에 같은 색 칩
  for(const [boxId, taId] of [['hookColorChips','editHook'], ['genHookColorChips','genHook']]){
    const box = $(boxId);
    if(!box || box.childElementCount) continue;
    for(const name in HOOK_COLORS){
      const b = document.createElement('button');
      b.className = 'ghost'; b.textContent = name;
      b.style.cssText = 'padding:3px 8px;border-color:' + HOOK_COLORS[name] + ';color:' + HOOK_COLORS[name] + (name==='흰' ? ';color:#fff' : '');
      b.onclick = (e) => wrapHookColor(e, name, taId);
      box.appendChild(b);
    }
  }
}

function wrapHookColor(ev, name, taId){
  ev.preventDefault();
  const ta = $(taId || 'editHook');
  let s = ta.selectionStart, e = ta.selectionEnd;
  const v = ta.value;
  if(!v.trim()){ alert('먼저 상단 제목을 입력하세요'); ta.focus(); return; }
  if(s === e){
    // 드래그 없이도: 커서가 놓인 단어를 자동 선택 (공백·줄바꿈 경계)
    const isSp = (ch) => ch === ' ' || ch === String.fromCharCode(10) || ch === String.fromCharCode(9);
    if(s > 0 && (s >= v.length || isSp(v[s]))) s--;           // 단어 끝에 커서
    while(s > 0 && !isSp(v[s-1]) && v[s-1] !== ']') s--;
    e = s;
    while(e < v.length && !isSp(v[e]) && v[e] !== '[') e++;
    if(s === e){ alert('색을 입힐 단어에 커서를 두거나 드래그로 선택하세요'); ta.focus(); return; }
  }
  let mid = v.slice(s, e);
  const tagRe = new RegExp('[[](?:[가-힣A-Za-z]+|/[가-힣A-Za-z]*)]', 'g');
  const already = new RegExp('^[[]' + name + ']').test(mid) || (
    v.slice(Math.max(0, s - name.length - 2), s) === '[' + name + ']');
  mid = mid.replace(tagRe, '');                               // 선택 안 기존 색 제거(중첩 방지)
  let before = v.slice(0, s), after = v.slice(e);
  // 선택 바로 앞뒤의 여닫는 태그도 정리 ([노랑]단어[/] 전체를 다시 칠할 때)
  before = before.replace(new RegExp('[[][가-힣A-Za-z]+]$'), '');
  after = after.replace(new RegExp('^[[]/[가-힣A-Za-z]*]'), '');
  // 같은 색을 다시 누르면 해제(토글), 다른 색이면 교체
  ta.value = already ? (before + mid + after)
                     : (before + '[' + name + ']' + mid + '[/]' + after);
  ta.focus();
  if(ta.id === 'genHook') renderGenHookPreview(); else renderHookPreview();
}

function clearHookMarkup(ev, taId){
  ev.preventDefault();
  const ta = $(taId || 'editHook');
  const re1 = new RegExp('[[](?:[가-힣A-Za-z]+|/[가-힣A-Za-z]*)]', 'g');
  ta.value = ta.value.replace(re1, '');
  if(ta.id === 'genHook') renderGenHookPreview(); else renderHookPreview();
}

function hookLineHtml(line){
  const esc = (x) => x.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  let rest = line, out = '', hasMarkup = false;
  const tagRe = new RegExp('[[]([가-힣A-Za-z]+)]');
  while(rest){
    const m = rest.match(tagRe);
    const name = m ? m[1] : null;
    const col = name && (HOOK_COLORS[name] || HOOK_COLORS[name.replace(/색$/,'')]);
    if(!m || !col){
      if(m && m.index !== undefined){ out += esc(rest.slice(0, m.index + m[0].length)); rest = rest.slice(m.index + m[0].length); continue; }
      out += esc(rest); break;
    }
    hasMarkup = true;
    out += esc(rest.slice(0, m.index));
    rest = rest.slice(m.index + m[0].length);
    const close = rest.search(new RegExp('[[]/[가-힣A-Za-z]*]'));
    const next = rest.search(tagRe);
    let end = rest.length;
    if(close >= 0 && (next < 0 || close <= next)) end = close;
    else if(next >= 0) end = next;
    out += '<span style="color:' + col + '">' + esc(rest.slice(0, end)) + '</span>';
    rest = (close >= 0 && close === end) ? rest.slice(end).replace(new RegExp('^[[]/[가-힣A-Za-z]*]'), '') : rest.slice(end);
  }
  if(!hasMarkup){
    // 마크업 없으면: | 단어 강조 → 없으면 숫자 자동 강조 (렌더와 같은 규칙)
    const bar = line.lastIndexOf('|');
    if(bar > 0){
      const word = line.slice(bar + 1).trim();
      const body = line.slice(0, bar).trim();
      out = esc(body).split(esc(word)).join('<span style="color:#FFD400">' + esc(word) + '</span>');
    } else {
      out = esc(line).replace(new RegExp('([0-9]+[가-힣%]*)', 'g'), '<span style="color:#FFD400">$1</span>');
    }
  }
  return out;
}

// 🪧 제목 스타일 프리셋의 화면 미리보기 근사값 (실제 렌더는 ass_writer.HOOK_STYLES)
const HOOK_STYLE_CSS = {
  '기본':      'background:rgba(10,10,14,.72);color:#fff',
  '예능 노랑':  'background:transparent;color:#FFD400;text-shadow:-2px -2px 0 #101010,2px -2px 0 #101010,-2px 2px 0 #101010,2px 2px 0 #101010,0 3px 0 #101010',
  '화이트 박스': 'background:#F2F2F2;color:#141414',
  '네온':      'background:transparent;color:#9CFFF0;text-shadow:0 0 8px #17E0C4,0 0 16px #0FB5A0',
  // v0.73 프리셋도 미리보기 반영 (v0.74)
  '다색 팝':    'background:transparent;color:#FF3B30;text-shadow:-2px -2px 0 #fff,2px -2px 0 #fff,-2px 2px 0 #fff,2px 2px 0 #fff,0 3px 4px rgba(0,0,0,.5)',
  '블랙 박스':  'background:#121212;color:#fff',
};
// 💬 본문 자막 스타일 실물 미리보기 (v0.74) — 고르면 어떤 효과인지 바로 보이게
const SUB_STYLE_CSS = {
  '기본':      'color:#fff;text-shadow:-1.5px -1.5px 0 #000,1.5px -1.5px 0 #000,-1.5px 1.5px 0 #000,1.5px 1.5px 0 #000,0 2px 3px #000',
  '예능 노랑':  'color:#FFE14D;text-shadow:-2px -2px 0 #101010,2px -2px 0 #101010,-2px 2px 0 #101010,2px 2px 0 #101010',
  '말풍선 띠':  'background:#F5F5F5;color:#141414;padding:4px 12px;border-radius:8px',
  '네온':      'color:#9CFFF0;text-shadow:0 0 8px #17E0C4,0 0 16px #0FB5A0',
  '블랙 박스':  'background:#121212;color:#fff;padding:4px 12px;border-radius:6px',
};
const POP_PALETTE_CSS = ['#FF3B30','#31E1C4','#FFD400','#FF7A00','#5AC8FA','#FF375F'];
function subStylePreviewInto(prevId, styleName, fontId){
  const box = $(prevId); if(!box) return;
  const fam = 'font-family:' + fontFamilyOf(fontId) + ';';
  const sample = '이렇게 자막이 나와요';
  if(styleName === '다색 팝'){  // 단어마다 색이 바뀌는 걸 그대로 보여줌
    const outline = 'text-shadow:-2px -2px 0 #fff,2px -2px 0 #fff,-2px 2px 0 #fff,2px 2px 0 #fff,0 3px 4px rgba(0,0,0,.5)';
    const inner = sample.split(' ').map((w,i) =>
      '<span style="color:' + POP_PALETTE_CSS[i%POP_PALETTE_CSS.length] + ';' + outline + '">' + escHtml(w) + '</span>').join(' ');
    box.innerHTML = '<span style="' + fam + 'font-weight:800;font-size:24px">' + inner + '</span>';
  } else {
    const css = SUB_STYLE_CSS[styleName] || SUB_STYLE_CSS['기본'];
    box.innerHTML = '<span style="' + fam + 'font-weight:800;font-size:24px;' + css + '">' + escHtml(sample) + '</span>';
  }
}

// ── 🔤 글씨체 실물 미리보기 (v0.68) — 받은 폰트를 브라우저에 등록해 화면에 그대로 ──
const FONT_FAMILY_MAP = {
  'Pretendard-ExtraBold':'Pretendard ExtraBold', 'BlackHanSans-Regular':'Black Han Sans',
  'Jua-Regular':'Jua', 'DoHyeon-Regular':'Do Hyeon', 'Gugi-Regular':'Gugi',
  'NanumPenScript-Regular':'Nanum Pen Script',
};
function injectFontFaces(installed){
  const have = new Set(['Pretendard-ExtraBold'].concat(installed || []));
  let css = '';
  have.forEach(stem => {
    const fam = FONT_FAMILY_MAP[stem]; if(!fam) return;
    css += "@font-face{font-family:'" + fam + "';src:url('/font/" + stem +
           "') format('truetype');font-display:swap;}";
  });
  let el = $('dynFontFaces');
  if(!el){ el = document.createElement('style'); el.id = 'dynFontFaces'; document.head.appendChild(el); }
  el.textContent = css;
}
function fontFamilyOf(stem){
  return "'" + (FONT_FAMILY_MAP[stem] || 'Pretendard ExtraBold') + "', sans-serif";
}
function renderSubFontPrev(selId, prevId){
  const sel = $(selId); if(!$(prevId)) return;
  // v0.74: 글씨체 + 자막 스타일을 함께 반영 — 고르면 어떤 효과인지 실물로 보임
  const styleSelId = prevId === 'editSubFontPrev' ? 'editSubStyleSel'
                   : prevId === 'genSubFontPrev' ? 'genSubStyleSel' : '';
  const styleName = styleSelId ? ((($(styleSelId)||{}).value) || '기본') : '기본';
  subStylePreviewInto(prevId, styleName, sel ? sel.value : '');
}

function hookPreviewInto(taId, boxId, scale, styleName, fontId){
  initHookChips();
  const box = $(boxId);
  const raw = $(taId).value.trim();
  if(!raw){ box.style.display = 'none'; return; }
  const px = Math.round(24 * (scale || 1));
  const css = HOOK_STYLE_CSS[styleName] || HOOK_STYLE_CSS['기본'];
  const fam = 'font-family:' + fontFamilyOf(fontId) + ';';
  box.style.display = 'block';
  box.innerHTML = raw.split(new RegExp('[' + String.fromCharCode(10,13) + ']+')).map(l =>
    '<div style="display:inline-block;padding:4px 12px;margin:2px 0;' +
    'font-weight:800;font-size:' + px + 'px;line-height:1.35;letter-spacing:-0.5px;' + fam + css + '">' +
    hookLineHtml(l) + '</div>').join('<br>');
}

// ── v0.60 꾸미기 시각화: 견본 칩·톤 스와치·효과음 듣기 ──
function pickStyleChip(selId, val, ev){
  if(ev) ev.preventDefault();
  const sel = $(selId); if(!sel) return;
  sel.value = val;
  syncStyleChips(selId);
  // v0.74: 스타일 바꾸면 실물 미리보기도 즉시 갱신
  if(selId === 'editSubStyleSel') renderSubFontPrev('editSubFontSel','editSubFontPrev');
  else if(selId === 'genSubStyleSel') renderSubFontPrev('genSubFontSel','genSubFontPrev');
}
function syncStyleChips(selId){
  const sel = $(selId); if(!sel) return;
  document.querySelectorAll(".stylechips[data-for='" + selId + "'] .stylechip")
    .forEach(c => c.classList.toggle('sel', c.dataset.v === sel.value));
}
function pickToneCard(selId, val, ev){
  if(ev) ev.preventDefault();
  const sel = $(selId); if(!sel) return;
  sel.value = val;
  syncToneCards(selId);
}
function syncToneCards(selId){
  const sel = $(selId); if(!sel) return;
  document.querySelectorAll(".tonerow[data-for='" + selId + "'] .tonecard")
    .forEach(c => c.classList.toggle('sel', c.dataset.v === sel.value));
}
function syncDecorChips(){  // 프로그램이 select 값을 바꾼 뒤 화면 동기화 (복원·초기화·템플릿)
  ['genSubStyleSel', 'editSubStyleSel'].forEach(syncStyleChips);
  ['genToneSel', 'editToneSel'].forEach(syncToneCards);
}
function playSfx(ev, name){
  if(ev) ev.preventDefault();
  const a = new Audio('/sfx/' + name);
  a.onerror = () => alert('효과음 재생 실패 — FFmpeg 설치를 확인해 주세요 (1_설치.bat)');
  a.play().catch(() => {});
}

function renderHookPreview(){
  hookPreviewInto('editHook', 'hookPreview', +(($('hookSizeSel')||{}).value) || 1,
                  (($('hookStyleSel')||{}).value) || '기본', (($('editHookFontSel')||{}).value) || '');
}

function renderGenHookPreview(){
  hookPreviewInto('genHook', 'genHookPreview', 1, (($('genHookStyleSel')||{}).value) || '기본',
                  (($('genHookFontSel')||{}).value) || '');
}

async function analyzeAI(ev){
  ev.preventDefault();
  const btn = ev.target; const oldTxt = btn.textContent;
  const key = ensureGeminiKey();
  btn.disabled = true; btn.textContent = '🧠 분석 중…(장면 캡처+AI)';
  try{
    const data = await (await fetch('/api/analyze_ai', {method:'POST', body: JSON.stringify({
      job_id: currentJob, gemini_key: key, save_key: true,
    })})).json();
    if(data.error){ alert(data.error); return; }
    if(key) window._hasGeminiKey = true;
    $('aiAnalyzeBox').classList.remove('hidden');
    $('aiSummary').textContent = (data.stub ? '⚠ 제미나이 키가 없어 예시 추천입니다 — 키를 넣으면 영상 내용 기반으로 추천돼요. ' : '') + (data.summary || '');
    const hooks = $('aiHooks'); hooks.innerHTML = '';
    (data.hooks || []).forEach(h => {
      const b = document.createElement('button');
      b.textContent = h;
      b.onclick = (e) => { e.preventDefault(); $('editHook').value = h; };
      hooks.appendChild(b);
    });
    $('aiTitles').textContent = (data.titles || []).map((t2,i) => (i+1) + '. ' + t2).join('\\n');
    $('aiScript').value = (data.script || []).join('\\n');
    $('aiTags').textContent = (data.hashtags || []).map(h => '#' + h.replace(/^#/, '')).join(' ');
  } finally { btn.disabled = false; btn.textContent = oldTxt; }
}

function applyAiScript(ev){
  ev.preventDefault();
  const lines = $('aiScript').value.split('\\n').map(s => s.trim()).filter(Boolean);
  if(!lines.length){ alert('추천 대본이 없습니다'); return; }
  if(!confirm('자막 텍스트를 추천 대본으로 교체할까요? (타이밍은 유지, 줄이 더 많으면 뒤에 추가)')) return;
  $('bulkText').value = lines.join('\\n');
  applyBulk(ev);
}

async function copyAiScript(ev){
  ev.preventDefault();
  try{ await navigator.clipboard.writeText($('aiScript').value); ev.target.textContent = '✓ 복사됨'; }
  catch(e){ alert('복사 실패 — 직접 드래그해서 복사하세요'); }
}

async function refineSubs(ev){
  if(ev)ev.preventDefault();
  const idxs=[]; (window._subs||[]).forEach((s,i)=>{ if((s.text||'').trim()) idxs.push(i); });
  if(!idxs.length){ alert('다듬을 자막이 없습니다'); return; }
  if(!confirm(idxs.length+'줄을 AI가 문맥에 맞게 자연스럽게 고칩니다. 계속할까요?\\n(제미나이 키가 필요해요)')) return;
  const key=ensureGeminiKey();
  if(!key && !window._hasGeminiKey){ alert('제미나이 키가 있어야 쓸 수 있어요. (무료 발급: aistudio.google.com/apikey)'); return; }
  const btn=ev.target; btn.disabled=true; const old=btn.textContent; btn.textContent='다듬는 중…';
  try{
    const subs=idxs.map(i=>({text:window._subs[i].text}));
    const data=await (await fetch('/api/refine_subtitles',{method:'POST',
      body:JSON.stringify({subtitles:subs, context:$('editHook').value||'', gemini_key:key, save_key:true})})).json();
    if(data.error){ alert(data.error); return; }
    window._hasGeminiKey=true;
    (data.lines||[]).forEach((t,k)=>{ if(idxs[k]!=null && t) window._subs[idxs[k]].text=t; });
    renderSubRows();
    const r=$('hlReason'); if(r) r.textContent='🪄 AI가 대본을 다듬었어요. 어색한 부분은 직접 더 고치세요.';
  } finally { btn.disabled=false; btn.textContent=old; }
}
// ── ↕ 자막 위치 드래그 (v0.49) — 노란 점선 상자를 끌면 그 높이로 자막이 들어감 ──
function initSubPosBar(){
  const bar=$('subPosBar'), wrap=$('playerWrap');
  if(!bar || !wrap || bar._init) return;
  bar._init=true;
  let drag=false;
  bar.addEventListener('pointerdown', e=>{ e.preventDefault(); drag=true; bar.setPointerCapture(e.pointerId); });
  bar.addEventListener('pointermove', e=>{
    if(!drag) return;
    const r=wrap.getBoundingClientRect();
    let frac=(r.bottom-e.clientY)/r.height;         // 아래에서부터의 비율
    frac=Math.max(0.05, Math.min(0.72, frac));
    bar.style.bottom=(frac*100)+'%';
    window._subMarginV=Math.round(frac*1920);       // 쇼츠 캔버스(1920) 기준 px
    bar.firstElementChild.textContent='↕ 자막 위치 — 아래에서 '+Math.round(frac*100)+'%';
  });
  const up=()=>{ drag=false; };
  bar.addEventListener('pointerup', up); bar.addEventListener('pointercancel', up);
}
function resetSubPosBar(defMv){
  window._subMarginV=0;                              // 0 = 설정 기본값 그대로
  const bar=$('subPosBar');
  if(!bar) return;
  bar.style.bottom=(Math.max(0.05, Math.min(0.72, (defMv||480)/1920))*100)+'%';
  bar.firstElementChild.textContent='↕ 자막 위치';
  initSubPosBar();
}

function seekCut(us){ const p=$('cutPlayer'); p.currentTime=us/1e6; p.play(); }
function fmtClock(sec){ const m=Math.floor(sec/60), s=Math.floor(sec%60); return m+':'+String(s).padStart(2,'0'); }
function togglePlay(ev){ if(ev&&ev.preventDefault)ev.preventDefault(); const p=$('cutPlayer'); if(!p||!p.src) return; if(p.paused) p.play(); else p.pause(); }
function pauseCut(){ const p=$('cutPlayer'); if(p && !p.paused) p.pause(); }  // 자막 편집 시작하면 자동 정지
function setPlayRate(){ const p=$('cutPlayer'); if(p) p.playbackRate=parseFloat($('playRate').value||'1'); }
function qualityHint(){
  const v=($('outQuality')||{}).value, h=$('qualityHint'); if(!h) return;
  h.textContent = v==='ultra' ? '유튜브가 더 좋은 코덱으로 처리 → 체감 화질↑ (원본 화소는 안 늘어요)'
    : v==='high' ? '압축을 덜 해 더 또렷하게 (파일 조금 커짐)' : '';
}
function splitSub(i){
  const s=window._subs, cur=s[i]; if(!cur) return;
  const mid=Math.round((cur.start_us+cur.end_us)/2);
  const words=(cur.text||'').trim().split(/\\s+/).filter(Boolean);
  const half=Math.ceil(words.length/2);
  s.splice(i,1,
    {text:words.slice(0,half).join(' '), start_us:cur.start_us, end_us:mid},
    {text:words.slice(half).join(' '), start_us:mid, end_us:cur.end_us});
  renderSubRows();
}
function fmtSrtTime(us){
  const ms=Math.floor(us/1000), h=Math.floor(ms/3600000), m=Math.floor(ms%3600000/60000),
        sec=Math.floor(ms%60000/1000), mm=ms%1000;
  const p=(n,w)=>String(n).padStart(w,'0');
  return p(h,2)+':'+p(m,2)+':'+p(sec,2)+','+p(mm,3);
}
// 검토 중인 전체 대본을 파일로 다운로드 (수정한 내용 그대로)
function downloadScript(ev, kind){
  if(ev)ev.preventDefault();
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  if(!subs.length){ alert('저장할 대본이 없습니다'); return; }
  const clean=t=>t.replace(/\\[[가-힣A-Za-z]+\\]|\\[\\/[가-힣A-Za-z]*\\]/g,'').replace(/\\s*\\|[^|]*$/,'').trim();
  let content, name;
  if(kind==='srt'){
    content=subs.map((s,i)=>(i+1)+'\\n'+fmtSrtTime(s.start_us)+' --> '+fmtSrtTime(s.end_us)+'\\n'+clean(s.text)+'\\n').join('\\n');
    name='대본.srt';
  } else {
    content=subs.map(s=>clean(s.text)).join('\\n');
    name='대본.txt';
  }
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob(['\\ufeff'+content],{type:'text/plain;charset=utf-8'}));
  a.download=name; a.click(); URL.revokeObjectURL(a.href);
}
function toggleBulk(ev){ if(ev)ev.preventDefault(); $('bulkBox').classList.toggle('hidden'); }
function applyBulk(ev){
  if(ev)ev.preventDefault();
  const lines=($('bulkText').value||'').split('\\n').map(l=>l.trim()).filter(Boolean);
  if(!lines.length){ alert('붙여넣을 대본을 입력하세요'); return; }
  const s=window._subs;
  lines.forEach((t,i)=>{
    if(s[i]) s[i].text=t;
    else { const last=s.length?s[s.length-1].end_us:0; s.push({text:t, start_us:last, end_us:last+1800000}); }
  });
  renderSubRows(); $('bulkBox').classList.add('hidden');
}
// 재생 위치 따라 현재 말하는 자막 줄 하이라이트 (+ 화면 밖이면 스크롤) + 시계 갱신
function hlActiveSub(){
  const p=$('cutPlayer'); if(!p) return;
  const clk=$('playClock'); if(clk) clk.textContent=fmtClock(p.currentTime);
  const us=p.currentTime*1e6;
  let active=-1;
  (window._subs||[]).forEach((s,i)=>{ if(us>=s.start_us && us<s.end_us) active=i; });
  const box=$('subList');
  document.querySelectorAll('.subrow').forEach((r,i)=>{
    const on=(i===active);
    r.classList.toggle('subrow-active', on);
    if(on && box){  // 목록 스크롤 영역 안에서만 가운데로 (전체 페이지는 안 움직임)
      const rb=box.getBoundingClientRect(), rr=r.getBoundingClientRect();
      if(rr.top<rb.top+6 || rr.bottom>rb.bottom-6) r.scrollIntoView({block:'center', behavior:'smooth'});
    }
  });
}
function mergeSub(i){
  if(i<=0) return;
  const s=window._subs;
  s[i-1].text=(s[i-1].text+' '+s[i].text).trim();
  s[i-1].end_us=s[i].end_us;
  s.splice(i,1); renderSubRows();
}
function delSub(i){ window._subs.splice(i,1); renderSubRows(); }
function dropSeg(i){  // 브루식: 자막 줄과 그 영상 구간을 함께 삭제 (keep 해제 = 렌더 때 잘림)
  const s=window._subs[i]; if(!s) return;
  s.keep=false; renderSubRows(); updateKeepInfo();
}
// ── ✂️ 앞뒤 트림 (v0.41) — 재생 위치를 시작/끝점으로 ──
function setTrimStart(ev){
  ev.preventDefault();
  const p=$('cutPlayer');
  if(!p || !p.src){ alert('먼저 영상을 재생해 원하는 위치에 멈춰주세요'); return; }
  const us=Math.round(p.currentTime*1e6);
  if(window._trimEnd && us >= window._trimEnd){ alert('시작점은 끝점보다 앞이어야 해요'); return; }
  window._trimStart=us; applyTrimMarks();
}
function setTrimEnd(ev){
  ev.preventDefault();
  const p=$('cutPlayer');
  if(!p || !p.src){ alert('먼저 영상을 재생해 원하는 위치에 멈춰주세요'); return; }
  const us=Math.round(p.currentTime*1e6);
  if(us <= (window._trimStart||0)){ alert('끝점은 시작점보다 뒤여야 해요'); return; }
  window._trimEnd=us; applyTrimMarks();
}
function clearTrim(ev){
  if(ev)ev.preventDefault();
  window._trimStart=0; window._trimEnd=0;
  (window._subs||[]).forEach(s=>{ if(s._trimDrop){ s.keep=true; delete s._trimDrop; } });
  renderSubRows(); updateTrimInfo();
}
function applyTrimMarks(){
  // 트림 범위 밖 자막 줄은 자동으로 체크 해제(영상도 잘림을 눈으로 보여줌), 범위 복귀 시 복구
  const t0=window._trimStart||0, t1=window._trimEnd||0;
  (window._subs||[]).forEach(s=>{
    const out=(t0 && s.end_us<=t0) || (t1 && s.start_us>=t1);
    if(out){ if(s.keep!==false){ s.keep=false; s._trimDrop=true; } }
    else if(s._trimDrop){ s.keep=true; delete s._trimDrop; }
  });
  renderSubRows(); updateTrimInfo();
}
function updateTrimInfo(){
  const el=$('trimInfo'); if(!el) return;
  const t0=window._trimStart||0, t1=window._trimEnd||0;
  el.textContent=(!t0 && !t1) ? '전체 사용' : '사용: '+fmtTime(t0)+' ~ '+(t1?fmtTime(t1):'끝');
}
function addSubRow(ev){
  ev.preventDefault();
  const s=window._subs, last=s.length?s[s.length-1].end_us:0;
  s.push({text:'', start_us:last, end_us:last+1500000}); renderSubRows();
}
async function pronounceSubs(ev){
  ev.preventDefault();
  const res=await fetch('/api/pronounce',{method:'POST',body:JSON.stringify({lines:window._subs.map(s=>s.text)})});
  const data=await res.json();
  if(data.lines){ data.lines.forEach((t,i)=>{ if(window._subs[i]) window._subs[i].text=t; }); renderSubRows(); }
}
// 전체를 목표 길이 단위로 잘라 쇼츠 여러 개 생성
async function renderSplit(ev){
  if(ev)ev.preventDefault();
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  if(subs.length<2){ alert('나눌 자막이 부족합니다 (2개 이상 필요)'); return; }
  const target=parseInt($('hlTarget').value||'30');
  if(!confirm('전체를 약 '+target+'초 단위 쇼츠 여러 개로 나눠 저장합니다. 계속할까요?')) return;
  const speed=parseFloat(($('outSpeed')||{}).value||'1');
  const quality=($('outQuality')||{}).value||'standard';
  const res=await fetch('/api/edit_split',{method:'POST',body:JSON.stringify(
    {job_id:currentJob, subtitles:subs, target_sec:target, hook:$('editHook').value, speed, quality, trim_start_us:Math.round(window._trimStart||0), trim_end_us:Math.round(window._trimEnd||0), margin_v:window._subMarginV||0})});
  const data=await res.json();
  if(data.error){ alert(data.error); return; }
  $('subEditBox').classList.add('hidden');
  if(!timer) timer=setInterval(poll,900);
  poll();
}

async function renderEdited(){
  const subs=(window._subs||[]).filter(s=>(s.text||'').trim());
  const keepIdx=[]; subs.forEach((s,i)=>{ if(s.keep!==false) keepIdx.push(i); });
  if(subs.length && !keepIdx.length){ alert('쇼츠에 넣을 구간을 하나 이상 ☑ 체크하세요'); return; }
  // 전체 선택(또는 자막 없음)이면 재컷 안 함(null), 일부만이면 그 구간만 남김
  const keep=(!subs.length || keepIdx.length===subs.length) ? null : keepIdx;
  const speed=parseFloat(($('outSpeed')||{}).value || '1');
  const quality=($('outQuality')||{}).value || 'standard';
  const res=await fetch('/api/edit_render',{method:'POST',body:JSON.stringify({job_id:currentJob, subtitles:subs, hook:$('editHook').value, keep, speed, quality, hook_scale:+(($('hookSizeSel')||{}).value)||1, hook_style:(($('hookStyleSel')||{}).value)||'기본', sub_style:(($('editSubStyleSel')||{}).value)||'기본', tone:(($('editToneSel')||{}).value)||'기본', sub_anim:(window._themeAnim||{}).edit||'', sub_pos:(window._themePos||{}).edit||'', trim_start_us:Math.round(window._trimStart||0), trim_end_us:Math.round(window._trimEnd||0), margin_v:window._subMarginV||0})});
  const data=await res.json();
  if(data.error){ alert(data.error); return; }
  $('subEditBox').classList.add('hidden');
  if(!timer) timer=setInterval(poll,900);
  poll();
}

function onBatchChange(){
  const on = $('batchChk').checked;
  $('topicBatch').classList.toggle('hidden', !on);
  $('batchHint').classList.toggle('hidden', !on);
  $('topic').classList.toggle('hidden', on);
}

// ⚠ 버튼 무반응 방지 (v0.78) — 화면 동작 중 오류·조용한 중단을 상단 배너로 보여준다
// (알림창이 브라우저에서 차단돼 있어도 배너는 항상 보임)
function uiBanner(msg){
  try{
    const b = $('envBanner');
    if(b){ b.textContent = msg; b.classList.remove('hidden');
           b.scrollIntoView({behavior:'smooth', block:'center'}); }
  }catch(_e){}
}
function reportUiError(where, e){
  const raw = String((e && (e.message || e)) || '알 수 없는 오류');
  let msg = '⚠ ' + where + ' 중 화면 오류: ' + raw;
  if(/fetch|network/i.test(raw)) msg += ' — 컷대장 서버(검은 창)가 꺼져 있지 않은지 확인하고, 창을 닫았다면 windows\\2_UI실행.bat 로 다시 켜주세요';
  else msg += ' — 새로고침(F5) 후에도 반복되면 🩺 진단 리포트를 저장해 올려주세요';
  uiBanner(msg);
  try{ console.error('[컷대장]', where, e); }catch(_e){}
}
async function generateSafe(){ try{ await generate(); }catch(e){ reportUiError('생성 시작', e); } }
async function startEditSafe(){ try{ await startEdit(); }catch(e){ reportUiError('만들기 시작', e); } }

async function generate(){
  const prov = pick('prov');
  if(prov === 'eleven_voice' && !(($('elevenVoiceSel')||{}).value)){
    alert('일레븐랩스 보이스 목록을 아직 못 불러왔어요 — 잠시 후 다시 시도하거나 키를 확인하세요'); return;
  }
  if(prov === 'gemini' && !window._hasGeminiKey && !($('geminiKey').value||'').trim()){
    const k = ensureGeminiKey();   // 무료 발급 안내 포함 프롬프트 (1회 저장)
    if(k){ $('geminiKey').value = k; }
    else if(!confirm('Gemini 키 없이 만들면 내장 음성·기본 배경으로 완성돼요.' + String.fromCharCode(10) + '키 없이 계속할까요?')){
      // 입력·확인창이 취소(또는 브라우저에서 차단)되면 왜 안 시작됐는지 보여준다 (v0.78)
      uiBanner('ℹ 생성을 시작하지 않았어요 — 제미나이 키 입력(또는 "키 없이 계속" 확인)이 취소됐어요. ⚙ 설정에서 키를 저장해 두면 다시 묻지 않아요.');
      return;
    }
  }
  let autoMode = pick('mode') === 'auto';
  const sceneMode = (($('genSceneMode')||{}).value)||'auto';
  if(sceneMode === 'manual' && autoMode && !(($('batchChk')||{}).checked)){
    // ✍ 내가 넣기는 그림을 직접 넣는 단계가 필요 → 검토 방식으로 자동 전환 (v0.51)
    alert('✍ 내가 넣기는 「검토」 방식으로 진행돼요 — 대본 확정 후 프롬프트가 나옵니다.');
    autoMode = false;
    const rv = document.querySelector("input[name='mode'][value='review']");
    if(rv) rv.checked = true;
  }
  const body = {
    topic: $('topic').value, auto: autoMode,
    // v0.40: 대본은 목소리와 무관 — 키만 있으면 AI 대본 (테스트 톤만 템플릿, 키 없으면 서버가 안전 강등)
    script_provider: prov === 'stub' ? 'stub' : 'gemini',
    tts_provider: prov === 'eleven_voice' ? 'elevenlabs' : prov,   // 🎙 성우도 같은 제공자
    voice: prov === 'gemini' ? $('voiceSel').value
         : prov === 'eleven_voice' ? $('elevenVoiceSel').value : '',
    tts_style: prov === 'gemini' ? $('styleSel').value : '',
    bgm: $('bgmSel').value, hook: $('genHook').value,
    hook_voice: !!(($('genHookVoice')||{}).checked),  // 🎙 후킹 보이스 (v0.75)
    bg_style: (($('genBgStyle')||{}).value)||'',
    bg_character: (($('genCharSel')||{}).value) === 'custom'
      ? ((($('genCharCustom')||{}).value)||'').trim()
      : ((($('genCharSel')||{}).value)||''),
    bg_scene_mode: sceneMode,                                   // v0.51 그림 방식
    hook_style: (($('genHookStyleSel')||{}).value)||'기본',        // v0.52 제목 프리셋
    hook_font: (($('genHookFontSel')||{}).value)||'',              // v0.63 제목 글씨체
    hook_tilt: !!(($('genHookTiltChk')||{}).checked),              // v0.63 비스듬히
    sub_font: (($('genSubFontSel')||{}).value)||'',                // v0.63 자막 글씨체
    product: (($('genProductSel')||{}).value)||'',                 // 📇 제품 프로필 (v0.64)
    context_memo: (($('genContext')||{}).value)||'',               // 📎 이번 영상 참고 (v0.64)
    orientation: pick('genOrient') || 'shorts',                    // v0.61 화면 형태
    target_sec: genTargetSec(),                                    // v0.61 영상 길이 (직접 입력 v0.68)
    script_text: (($('genScript')||{}).value)||'',                 // v0.61 내 대본
    sub_style: (($('genSubStyleSel')||{}).value)||'기본',          // v0.54 자막 프리셋
    sub_anim: (window._themeAnim||{}).gen || '',                  // 🎨 감성 테마 자막 등장 (v0.86)
    sfx_auto: !!(($('genSfxChk')||{}).checked),                    // v0.53 효과음
    punch_in: !!(($('genPunchChk')||{}).checked),                  // v0.55 펀치 줌
    tone: (($('genToneSel')||{}).value)||'기본',                    // v0.56 화면 톤
    info_pop: !!(($('genInfoChk')||{}).checked),                   // v0.56 숫자 팝
    bg_max_imgs: Math.max(0, +((($('genMaxImg')||{}).value)||0)), // v0.51 장수 제한
    gemini_key: $('geminiKey').value,
    save_key: $('saveKeyChk').checked,
  };
  window._scenesLoaded = false;
  $('sceneBox').classList.add('hidden');
  let endpoint = '/api/generate';
  if(($('batchChk')||{}).checked){
    const NL = String.fromCharCode(10);
    const rawScript = (($('genScript')||{}).value||'');
    const topics = ($('topicBatch').value||'').split(NL).map(t=>t.trim()).filter(Boolean);
    if(rawScript.trim()){
      // 📝 대본 배치 (v0.62) — === 줄로 구분한 대본 여러 벌, 한 벌 = 영상 1개
      if(topics.length){
        alert('배치는 「주제 여러 줄」이나 「대본 여러 벌」 중 하나만 넣어주세요' + NL +
              '— 대본으로 만들려면 주제 배치 칸을 비워주세요.'); return;
      }
      const blocks = []; let cur = [];
      rawScript.split(NL).forEach(ln => {
        const s = ln.trim();
        if(s.length >= 3 && s.split('').every(c => c === '=')){
          if(cur.join(NL).trim()) blocks.push(cur.join(NL).trim());
          cur = [];
        } else cur.push(ln);
      });
      if(cur.join(NL).trim()) blocks.push(cur.join(NL).trim());
      if(!blocks.length){ alert('대본이 비어 있어요'); return; }
      if(blocks.length === 1 && !confirm('구분선(===)이 없어 대본 1벌 = 영상 1개로 만들어요.' + NL +
          '여러 개를 만들려면 대본 사이에 === 줄을 넣으세요. 1개로 진행할까요?')) return;
      if(blocks.length > 20){ alert('한 번에 최대 20개까지 가능해요 (지금 ' + blocks.length + '벌)'); return; }
      if(blocks.length > 1 && !confirm(blocks.length + '개 영상을 대본대로 연속으로 만듭니다 (AI 대본 없이). 시작할까요?')) return;
      body.scripts = blocks;
      body.script_text = '';
      endpoint = '/api/generate_batch';
    } else {
      if(!topics.length){ alert('주제를 한 줄에 하나씩 입력하거나, 「📝 대본 직접 넣기」에 대본 여러 벌을 === 로 구분해 넣으세요'); return; }
      if(topics.length > 20){ alert('한 번에 최대 20개까지 가능해요 (지금 ' + topics.length + '개)'); return; }
      if(!confirm(topics.length + '개 영상을 연속으로 만듭니다. 시간이 꽤 걸려요 — 시작할까요?')) return;
      body.topics = topics;
      endpoint = '/api/generate_batch';
    }
  }
  const res = await fetch(endpoint, {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'gen';
  window._kitLoaded = false;
  $('kitBox').classList.add('hidden'); $('kitBody').classList.add('hidden');
  $('goBtn').disabled = true;
  $('formCard').classList.add('hidden');   // 진행 화면에 집중 (🏠 처음으로 로 복귀)
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('rawErr').classList.add('hidden'); $('noteText').textContent='';
  poll();
  timer = setInterval(poll, 900);
}

async function previewVoice(ev){
  ev.preventDefault();
  const btn = ev.target;
  btn.disabled = true; btn.textContent = '합성 중...';
  try{
    const res = await fetch('/api/preview', {method:'POST', body: JSON.stringify({
      tts_provider: pick('prov'), voice: $('voiceSel').value,
      tts_style: $('styleSel').value, gemini_key: $('geminiKey').value,
    })});
    const data = await res.json();
    if(data.error){ alert(data.error); } else { new Audio(data.url).play(); }
  } finally { btn.disabled = false; btn.textContent = '🔊 미리듣기'; }
}

// ── 편집 모드 내레이션 (v0.26) ──
function onNarrTopicInput(){
  // 🧠 화면분석 켜면 길이 옵션 노출 (v0.71)
  const box = $('narrAnalyzeLenBox');
  if(box) box.classList.toggle('hidden', !(($('narrAnalyzeChk')||{}).checked));
  // AI '목소리'를 얹을 때만 원본 자동 무음 (자막만 모드는 원본 소리 유지)
  if(window._origTouched) return;
  const voiceOn = ($('narrTopic').value.trim() || (($('narrAnalyzeChk')||{}).checked))
                  && !(($('narrSubsOnly')||{}).checked);
  $('origAudioSel').value = voiceOn ? 'mute' : 'keep';
}
function onNarrLenChange(){  // 요약이면 길이 선택 보이기, 원본이면 숨기기 (v0.71)
  const full = (document.querySelector("input[name=narrLen]:checked")||{}).value === 'full';
  const sb = $('narrLenSecBox'); if(sb) sb.style.display = full ? 'none' : '';
  const h = $('narrLenHint');
  if(h) h.textContent = full
    ? '원본 8분이면 결과도 8분 — 화면 진행에 맞춰 처음부터 끝까지 내레이션을 깔아요 (문장·목소리 합성이 많아 시간·API를 더 써요).'
    : '긴 영상을 고른 길이로 요약해요 — 8분 영상도 전체에서 고르게 추립니다.';
}

async function loadWinVoices(saved){
  const sel = $('setWinVoice'); if(!sel) return;
  sel.innerHTML = '<option value="">자동 (한국어 첫 번째)</option>';
  let voices = [], isWin = false;
  try {
    const d = await (await fetch('/api/win_voices', {method:'POST', body:'{}'})).json();
    voices = d.voices || []; isWin = !!d.win;
  } catch(e) { /* 목록 실패해도 저장값은 유지 */ }
  voices.forEach(v => {
    const o = document.createElement('option');
    o.value = v.name;
    const g = v.gender === 'Female' ? '여' : v.gender === 'Male' ? '남' : '';
    o.textContent = v.name.replace(/^Microsoft /, '') + ' (' + v.culture + (g ? ' · ' + g : '') + ')';
    sel.appendChild(o);
  });
  if(saved && ![...sel.options].some(o => o.value === saved)){
    const o = document.createElement('option');
    o.value = saved; o.textContent = saved + ' (저장됨)';
    sel.appendChild(o);
  }
  sel.value = saved || '';
  const hint = $('winVoiceHint');
  if(hint && !isWin) hint.textContent = 'Windows에서 실행하면 이 PC의 음성 목록이 떠요 (지금은 미리보기 불가)';
}

async function previewWinVoice(ev){
  ev.preventDefault();
  const btn = ev.target;
  btn.disabled = true; const oldTxt = btn.textContent; btn.textContent = '합성 중...';
  try{
    const res = await fetch('/api/preview', {method:'POST', body: JSON.stringify({
      tts_provider: 'windows', voice: $('setWinVoice').value,
      text: '안녕하세요, 컷대장 내장 음성 미리듣기입니다.',
    })});
    const data = await res.json();
    if(data.error){ alert(data.error); } else { new Audio(data.url).play(); }
  } finally { btn.disabled = false; btn.textContent = oldTxt; }
}

async function previewNarrVoice(ev){
  ev.preventDefault();
  const v = $('narrVoiceSel').value;
  let prov = window._hasGeminiKey ? 'gemini' : (window._isWin ? 'windows' : 'stub');
  let key = '';
  if(v === '__mine__') prov = 'elevenlabs';
  else if(v === '__sovits__') prov = 'sovits';
  else if(v.startsWith('el:')) prov = 'elevenlabs';   // 🎙 일레븐랩스 성우 (v0.46)
  else {
    key = ensureGeminiKey();   // 보이스는 제미나이 키가 있어야 적용됨 — 없으면 물어봄
    if(key || window._hasGeminiKey) prov = 'gemini';
    else if(!confirm('제미나이 키가 없으면 보이스 선택이 적용되지 않아요 (내장 음성 하나로 고정).\\n키 없이 내장 음성으로 들어볼까요?')) return;
  }
  const btn = ev.target;
  btn.disabled = true; btn.textContent = '합성 중...';
  try{
    const res = await fetch('/api/preview', {method:'POST', body: JSON.stringify({
      tts_provider: prov,
      voice: (v === '__mine__' || v === '__sovits__') ? ''
           : (v.startsWith('el:') ? v.slice(3) : v),
      tts_style: $('narrStyleSel').value, gemini_key: key, save_key: true,
    })});
    const data = await res.json();
    if(data.error){ alert(data.error); } else { if(key) window._hasGeminiKey = true; new Audio(data.url).play(); }
  } finally { btn.disabled = false; btn.textContent = '🔊 미리듣기'; }
}

function previewBgm(ev, selId, volSelId){
  ev.preventDefault();
  const btn = ev.target;
  // 재생 중이면 정지 (토글)
  if(window._bgmAudio){
    window._bgmAudio.pause(); window._bgmAudio = null;
    if(window._bgmBtn) window._bgmBtn.textContent = '▶ 미리듣기';
    if(window._bgmBtn === btn) return;   // 같은 버튼 = 정지만
  }
  let name = $(selId).value;
  if(!name){ alert('먼저 배경음악을 선택하세요 (없음 상태)'); return; }
  if(name === 'random'){
    const files = window._bgmFiles || [];
    if(!files.length){ alert('resources/bgm 폴더에 음원이 없습니다 — [⬇ 무료 BGM 받기] 버튼을 눌러보세요 (배경음악 그룹)'); return; }
    name = files[Math.floor(Math.random() * files.length)];
  }
  const a = new Audio('/bgm/' + encodeURIComponent(name));
  // 실제 믹스 볼륨 느낌으로 미리듣기 (목소리=1.0 대비)
  const db = volSelId ? +$(volSelId).value : -14;
  a.volume = Math.min(1, Math.pow(10, db / 20) * 2);
  a.onended = () => { if(window._bgmBtn) window._bgmBtn.textContent = '▶ 미리듣기'; window._bgmAudio = null; };
  a.onerror = () => alert('음원을 재생할 수 없습니다: ' + name);
  a.play();
  window._bgmAudio = a; window._bgmBtn = btn;
  btn.textContent = '⏹ 정지';
}

async function cloneVoice(ev){
  ev.preventDefault();
  const file = $('cloneFile').value.trim();
  if(!file){ alert('녹음 파일 경로를 입력하세요 (1~3분 낭독 녹음)'); return; }
  const key = $('elevenKey').value.trim();
  if(!key && !window._hasElevenKey){ alert('ElevenLabs API 키를 입력하세요 (elevenlabs.io에서 발급, 클로닝은 Starter 이상)'); return; }
  const btn = ev.target; btn.disabled = true; btn.textContent = '등록 중…(최대 1분)';
  try{
    const data = await (await fetch('/api/clone_voice', {method:'POST', body: JSON.stringify({
      file_path: file, name: '내 목소리', elevenlabs_key: key, save_key: true,
    })})).json();
    if(data.error){ alert(data.error); return; }
    window._hasElevenKey = true;
    addMyVoiceOption(data.name || '내 목소리');
    $('narrVoiceSel').value = '__mine__';
    alert('✅ 내 목소리 등록 완료!\\n\\n옆의 🔊 미리듣기로 확인해보세요.\\n이제 영상 만들 때 목소리에서 「🎤 내 목소리」를 고르면 됩니다.');
  } finally { btn.disabled = false; btn.textContent = '등록'; }
}

async function saveSovits(ev){
  ev.preventDefault();
  const ref = $('sovitsRef').value.trim(), txt = $('sovitsRefText').value.trim();
  if(!ref){ alert('참조 녹음 파일 경로를 입력하세요 (5~10초 낭독)'); return; }
  if(!txt){ alert('참조 녹음에서 말한 문장을 입력하세요'); return; }
  const btn = ev.target; btn.disabled = true; btn.textContent = '저장 중…';
  try{
    const data = await (await fetch('/api/sovits_save', {method:'POST', body: JSON.stringify({
      ref_audio: ref, ref_text: txt,
    })})).json();
    if(data.error){ alert(data.error); return; }
    addSovitsOption();
    $('narrVoiceSel').value = '__sovits__';
    alert('✅ 등록 완료!\\n\\nGPT-SoVITS API 서버(127.0.0.1:9880)를 켜둔 상태에서 옆의 🔊 미리듣기로 확인해보세요.\\n이제 영상 만들 때 목소리에서 「🎤 내 목소리 (무료·내 PC)」를 고르면 됩니다.');
  } finally { btn.disabled = false; btn.textContent = '저장'; }
}

function addSovitsOption(){
  if(![...$('narrVoiceSel').options].some(o => o.value === '__sovits__'))
    $('narrVoiceSel').add(new Option('🎤 내 목소리 (무료·내 PC)', '__sovits__'), 0);
  $('provSovitsLabel').classList.remove('hidden');
  markMyVoice();
}

function addMyVoiceOption(name){
  if(![...$('narrVoiceSel').options].some(o => o.value === '__mine__'))
    $('narrVoiceSel').add(new Option('🎤 내 목소리 (' + name + ')', '__mine__'), 0);
  $('provMineLabel').classList.remove('hidden');
  markMyVoice();
}

function showErrors(errs){
  const raw = (errs||[]).filter(e => e.startsWith('[원본 오류]'));
  const main = (errs||[]).filter(e => !e.startsWith('[원본 오류]'));
  if(main.length){ $('errBox').classList.remove('hidden'); $('errBox').textContent = main.join('\\n'); }
  $('rawErr').classList.toggle('hidden', raw.length === 0);
  $('rawErrText').textContent = raw.join('\\n');
}

async function clearKeys(ev){
  ev.preventDefault();
  if(!confirm('저장된 API 키를 삭제할까요?')) return;
  await fetch('/api/keys', {method:'POST', body: JSON.stringify({action:'clear'})});
  window._hasGeminiKey = false;
  $('keySaved').classList.add('hidden');
  poll();
}

async function pronounceLines(ev){
  ev.preventDefault();
  const res = await fetch('/api/pronounce', {method:'POST', body: JSON.stringify({
    lines: $('rvSentences').value.split('\\n'),
  })});
  const data = await res.json();
  if(data.lines) $('rvSentences').value = data.lines.join('\\n');
}

async function openFolder(ev){
  ev.preventDefault();
  const res = await fetch('/api/open_folder', {method:'POST', body: JSON.stringify({job_id: currentJob})});
  const data = await res.json();
  if(data.error) alert('폴더를 열 수 없습니다: ' + (data.path || data.error));
}

// ── 유튜브 썸네일 만들기 (16:9) ──
function toggleThumb(ev){
  if(ev)ev.preventDefault();
  const box=$('thumbBox'); box.classList.toggle('hidden');
  if(!box.classList.contains('hidden')){
    if(!$('thumbTitle').value) $('thumbTitle').value = ($('editHook')&&$('editHook').value) || ($('topic')&&$('topic').value) || '';
    if(!$('thumbTopic').value) $('thumbTopic').value = ($('editHookTopic')&&$('editHookTopic').value) || ($('topic')&&$('topic').value) || '';
  }
}
async function suggestThumb(ev){
  if(ev)ev.preventDefault();
  const ctx=($('thumbTopic').value||'').trim() || ($('thumbTitle').value||'').trim();
  if(!ctx){ alert('주제/키워드를 먼저 입력하세요'); return; }
  const key=ensureGeminiKey();
  const btn=ev.target; btn.disabled=true; const old=btn.textContent; btn.textContent='추천 중…';
  const cands=$('thumbCands'); cands.innerHTML='';
  try{
    const data=await (await fetch('/api/suggest_thumbnail',{method:'POST',
      body:JSON.stringify({context:ctx, gemini_key:key, save_key:true})})).json();
    if(data.error){ alert(data.error); return; }
    (data.copies||[]).forEach(c=>{
      const b=document.createElement('button');
      b.textContent=(c.title||'').replace(/\\n/g,' / ')+(c.highlight?('  ✨'+c.highlight):'');
      b.onclick=(e)=>{ e.preventDefault(); $('thumbTitle').value = c.highlight ? (c.title+' | '+c.highlight) : c.title; cands.innerHTML=''; };
      cands.appendChild(b);
    });
    if(!(data.copies||[]).length) cands.innerHTML='<span class="hint">추천 결과가 없습니다.</span>';
  } finally { btn.disabled=false; btn.textContent=old; }
}
async function makeThumb(ev){
  if(ev)ev.preventDefault();
  const title=($('thumbTitle').value||'').trim();
  if(!title){ alert('썸네일 제목을 입력하세요'); return; }
  // 클릭 이동 재생성처럼 ev 없이 불려도 동작 (v0.49)
  const btn=(ev&&ev.target)||$('thumbMakeBtn'); btn.disabled=true; const old=btn.textContent; btn.textContent='만드는 중…';
  try{
    const tp=window._thumbPos||[0.5,0.46];
    const data=await (await fetch('/api/thumbnail',{method:'POST',
      body:JSON.stringify({job_id:currentJob, title,
        badge:($('thumbBadge')||{}).value||'', bg_path:($('thumbBg')||{}).value||'',
        preset:(($('thumbStyleSel')||{}).value)||'임팩트',
        ai_bg:(($('thumbAiBg')||{}).checked)||false,
        pos_x:tp[0], pos_y:tp[1]})})).json();
    if(data.error){ alert(data.error); return; }
    $('thumbImg').src=(data.url||'')+'?t='+Date.now();
    $('thumbPath').textContent='저장됨: '+(data.path||'')+'  ·  💡 썸네일을 클릭하면 그 자리로 글자가 이동해요';
    $('thumbResult').classList.remove('hidden');
    initThumbPos();
  } finally { btn.disabled=false; btn.textContent=old; }
}

// ── 🖱 썸네일 글자 위치 — 결과 이미지를 클릭(드래그)하면 그 자리로 재생성 (v0.49) ──
function initThumbPos(){
  const img=$('thumbImg');
  if(!img || img._posInit) return;
  img._posInit=true;
  img.style.cursor='crosshair';
  let down=false;
  img.addEventListener('pointerdown', e=>{ e.preventDefault(); down=true; });
  img.addEventListener('pointerup', e=>{
    if(!down) return; down=false;
    if((($('thumbStyleSel')||{}).value)==='깔끔'){ alert('글자 위치 이동은 임팩트·포인트·입체3D 스타일에서 돼요'); return; }
    const r=img.getBoundingClientRect();
    window._thumbPos=[(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height];
    makeThumb();   // 새 위치로 다시 렌더 (버튼과 동일 경로)
  });
}

// ── 📦 유튜브 업로드 키트 (v0.39) — 제목·태그·설명·카테고리 원클릭 생성 ──
function toggleKit(ev){
  if(ev)ev.preventDefault();
  const box = $('kitBox'); box.classList.toggle('hidden');
  if(!box.classList.contains('hidden') && !window._kitLoaded) makeKit(ev);
}
async function makeKit(ev){
  if(ev)ev.preventDefault();
  const key = ensureGeminiKey();  // 키가 있어야 영상 내용 기반 (없으면 예시 문구)
  $('kitStatus').textContent = '🧠 영상 장면과 대본을 읽고 업로드 문구를 만드는 중… (10~20초)';
  $('kitBody').classList.add('hidden');
  try{
    const data = await (await fetch('/api/upload_kit', {method:'POST',
      body: JSON.stringify({job_id: currentJob, gemini_key: key, save_key: true})})).json();
    if(data.error){ $('kitStatus').textContent = '⚠ ' + data.error; return; }
    if(key) window._hasGeminiKey = true;
    window._kitLoaded = true;
    renderKit(data);
  } catch(e){ $('kitStatus').textContent = '⚠ 생성 실패: ' + e; }
}
function renderKit(data){
  const kit = data.kit || {};
  $('kitStatus').textContent = data.stub
    ? '⚠ 제미나이 키가 없어 예시 문구입니다 — 키를 넣으면 영상 내용으로 만들어져요.'
    : '✅ 완성! 항목마다 복사해서 유튜브 스튜디오에 붙여넣으세요.';
  const tb = $('kitTitles'); tb.innerHTML = '';
  // v0.47: 제목 옆에 붙는 해시태그 2~3개 — 유튜브 관행대로 "제목 #태그 #태그"를 통째 복사
  const ttags = (kit.title_tags || []).map(t => '#' + t).join(' ');
  (kit.titles || []).forEach(t => {
    const full = ttags ? (t + ' ' + ttags) : t;
    const b = document.createElement('button');
    b.textContent = full;
    b.onclick = async (e) => {
      e.preventDefault();
      try{ await navigator.clipboard.writeText(full); b.textContent = '✓ 복사됨 — ' + full; }
      catch(err){ alert('복사 실패 — 드래그해서 복사하세요'); }
    };
    tb.appendChild(b);
  });
  $('kitDesc').value = kit.description || '';
  $('kitTags').value = (kit.tags || []).join(', ');
  // v0.47: 플랫폼별 섹션 (틱톡·인스타·네이버 클립·스레드)
  const NL = String.fromCharCode(10);
  const hash = a => (a || []).map(t => '#' + t).join(' ');
  const tk = kit.tiktok || {};
  $('kitTiktok').value = tk.caption ? (tk.caption + NL + NL + hash(tk.hashtags)) : '';
  const ig = kit.instagram || {};
  $('kitInsta').value = ig.caption ? (ig.caption + NL + NL + hash(ig.hashtags)) : '';
  // 🟢 네이버 클립 (v0.87) — "제목:"/"태그:" 라벨 없이 각 입력란에 그대로 붙는 형식
  const nc = kit.naver_clip || {};
  if($('kitNaverTitle')) $('kitNaverTitle').value = nc.title || '';
  if($('kitNaverTags')) $('kitNaverTags').value = (nc.tags || []).join(', ');
  if($('kitNaverCat')) $('kitNaverCat').innerHTML = nc.category1
    ? ('📂 카테고리 추천: <b>1차 — ' + escHtml(nc.category1) + '</b> · <b>2차 — ' +
       escHtml(nc.category2 || '자유 선택') + '</b> <span class="hint">(업로드 화면에서 가장 비슷한 항목을 고르세요)</span>')
    : '';
  const th = kit.threads || {};
  $('kitThreads').value = th.post
    ? (th.post + (th.topic ? (NL + NL + th.topic) : '')) : '';   // 토픽은 맨 아랫줄 (라벨 없음)
  $('kitKeywords').innerHTML = '<b>🔑 키워드 10:</b> ' + escHtml((kit.keywords || []).join(' · '));
  $('kitCategory').innerHTML = '<b>📂 카테고리:</b> ' + escHtml(kit.category || '') +
    (kit.category_reason ? (' — ' + escHtml(kit.category_reason)) : '');
  $('kitChecklist').textContent = (kit.checklist || []).map(c => '□ ' + c)
    .join(String.fromCharCode(10));
  $('kitPath').textContent = data.path
    ? ('💾 저장됨: ' + data.path + ' — 업로드할 때 이 파일을 열어 복붙해도 돼요') : '';
  $('kitBody').classList.remove('hidden');
}
async function copyKit(ev, id){
  ev.preventDefault(); ev.stopPropagation();   // summary 안 버튼 — 접힘 토글 방지
  try{
    await navigator.clipboard.writeText($(id).value);
    const btn = ev.target; btn.textContent = '✓ 복사됨';
    setTimeout(() => { btn.textContent = '📋 복사'; }, 1500);
  } catch(e){ alert('복사 실패 — 직접 드래그해서 복사하세요'); }
}
function kitHist(id){
  playHist(id);                       // 진행 카드 + 플레이어 표시
  currentJob = id; window._jobMode = 'gen';
  window._kitLoaded = false;
  $('kitBox').classList.remove('hidden');
  makeKit();
}

async function diagnostic(ev){
  ev.preventDefault();
  const btn = ev.target; const old = btn.textContent;
  btn.disabled = true; btn.textContent = '진단 정보 모으는 중…';
  try{
    const data = await (await fetch('/api/diagnostic', {method:'POST', body:'{}'})).json();
    $('diagBox').textContent = data.text || '(내용 없음)';
    $('diagPath').textContent = ' — 파일로도 저장됨: ' + data.path;
    const p = $('diagPanel');
    p.classList.remove('hidden'); p.open = true;
    p.scrollIntoView({behavior:'smooth', block:'start'});
  } catch(e){ alert('진단 리포트 생성 실패: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

async function copyDiag(ev){
  ev.preventDefault(); ev.stopPropagation();
  try{
    await navigator.clipboard.writeText($('diagBox').textContent);
    ev.target.textContent = '✓ 복사됨';
    setTimeout(() => { ev.target.textContent = '📋 복사'; }, 1500);
  } catch(e){ alert('복사 실패 — 내용을 드래그해서 복사하세요'); }
}

async function openDiagFolder(ev){
  ev.preventDefault(); ev.stopPropagation();
  const data = await (await fetch('/api/open_folder', {method:'POST', body:'{}'})).json();
  if(data.error) alert('폴더 열기 실패: ' + data.error + String.fromCharCode(10) + '경로: ' + (data.path || ''));
}

function toggleSettings(){ $('settingsCard').classList.toggle('hidden'); }

// ── 📇 내 제품 프로필 (v0.64) ──
function toggleProductCard(){
  $('productCard').classList.toggle('hidden');
  if(!$('productCard').classList.contains('hidden')) loadProducts();
}
async function loadProducts(keep){
  const d = await (await fetch('/api/products', {method:'POST', body: JSON.stringify({action:'list'})})).json();
  window._products = d.products || [];
  const sel = $('prodSel'); if(sel){
    sel.innerHTML = '';
    window._products.forEach(x => sel.add(new Option(x.name, x.name)));
    sel.add(new Option('➕ 새 제품…', ''));
    if(keep && [...sel.options].some(o => o.value === keep)) sel.value = keep;
    fillProductForm();
  }
  const gsel = $('genProductSel'); if(gsel){
    const cur = gsel.value;
    gsel.innerHTML = '<option value="">없음 (일반 주제)</option>';
    window._products.forEach(x => gsel.add(new Option('📇 ' + x.name, x.name)));
    if([...gsel.options].some(o => o.value === cur)) gsel.value = cur;
    updateProductBadge();
  }
}
// 📇 제품 배지 — 제품이 골라져 있으면 [생성 시작] 바로 위에 크게 표시 (v0.77 혼동 방지)
function updateProductBadge(){
  const badge = $('prodBadge'); if(!badge) return;
  const v = (($('genProductSel')||{}).value)||'';
  if($('prodBadgeName')) $('prodBadgeName').textContent = v;
  badge.classList.toggle('hidden', !v);
}
function onGenProductChange(){
  updateProductBadge();
  // 고른 값을 즉시 저장 — "없음"도 저장해서 다음에 옛 제품이 조용히 되살아나지 않게 (v0.77)
  fetch('/api/settings', {method:'POST', body: JSON.stringify({settings:{ui:{
    gen_product: (($('genProductSel')||{}).value)||''}}})}).catch(() => {});
}
function clearGenProduct(ev){
  if(ev) ev.preventDefault();
  const gsel = $('genProductSel'); if(gsel) gsel.value = '';
  onGenProductChange();
}
function fillProductForm(){
  const x = (window._products || []).find(v => v.name === (($('prodSel')||{}).value)) || {};
  $('prodName').value = x.name || ''; $('prodDesc').value = x.desc || '';
  $('prodPoints').value = x.points || ''; $('prodTarget').value = x.target || '';
  $('prodTone').value = x.tone || ''; $('prodLink').value = x.link || '';
  $('prodAvoid').value = x.avoid || '';
}
function newProduct(ev){ ev.preventDefault(); const s = $('prodSel'); if(s) s.value = ''; fillProductForm(); $('prodName').focus(); }
async function saveProduct(ev){
  ev.preventDefault();
  const item = {name: $('prodName').value, desc: $('prodDesc').value,
    points: $('prodPoints').value, target: $('prodTarget').value,
    tone: $('prodTone').value, link: $('prodLink').value, avoid: $('prodAvoid').value};
  const d = await (await fetch('/api/products', {method:'POST',
    body: JSON.stringify({action:'save', item})})).json();
  if(d.error){ alert(d.error); return; }
  await loadProducts(item.name.trim());
  alert('저장했어요 — 영상 만들 때 「📇 제품」에서 고르면 이 정보만 근거로 대본을 써요');
}
async function deleteProduct(ev){
  ev.preventDefault();
  const name = ($('prodSel')||{}).value;
  if(!name){ alert('삭제할 제품을 먼저 골라주세요'); return; }
  if(!confirm('「' + name + '」 프로필을 삭제할까요?')) return;
  await fetch('/api/products', {method:'POST', body: JSON.stringify({action:'delete', name})});
  await loadProducts();
}
async function summarizeProduct(ev){
  ev.preventDefault();
  const btn = ev.target; btn.disabled = true; const old = btn.textContent; btn.textContent = '정리 중…';
  try {
    const key = ensureGeminiKey();
    const d = await (await fetch('/api/product_summarize', {method:'POST',
      body: JSON.stringify({text: $('prodRaw').value, gemini_key: key, save_key: true})})).json();
    if(d.error){ alert(d.error); return; }
    const it = d.item || {};
    $('prodName').value = it.name || $('prodName').value;
    $('prodDesc').value = it.desc || ''; $('prodPoints').value = it.points || '';
    $('prodTarget').value = it.target || ''; $('prodTone').value = it.tone || '';
    $('prodLink').value = it.link || '';
    alert('채웠어요 — 내용 확인하고 [💾 저장]을 눌러주세요');
  } finally { btn.disabled = false; btn.textContent = old; }
}

// ── 🔊 오디오 추출 (v0.64) ──
async function extractAudio(ev, kind){
  ev.preventDefault();
  const btn = ev.target; btn.disabled = true; const old = btn.textContent; btn.textContent = '추출 중…';
  try {
    const d = await (await fetch('/api/extract_audio', {method:'POST',
      body: JSON.stringify({job_id: currentJob, kind})})).json();
    if(d.error){ alert(d.error); return; }
    const a = document.createElement('a');
    a.href = d.url; a.download = '';
    document.body.appendChild(a); a.click(); a.remove();
    alert('저장했어요!' + String.fromCharCode(10) + '영상 폴더에도 있어요: ' + d.path);
  } finally { btn.disabled = false; btn.textContent = old; }
}

// ── 🔑 API 연동 화면 (v0.63) ──
function toggleApiCard(){
  $('apiCard').classList.toggle('hidden');
  refreshApiStates();
}
function refreshApiStates(){
  const g = $('apiGeminiState'), e = $('apiElevenState');
  if(g) g.textContent = window._hasGeminiKey ? '✅ 연결됨' : '⬜ 미등록';
  if(e) e.textContent = window._hasElevenKey ? '🔑 키 저장됨 · 확인 중...' : '⬜ 미등록';
  // 일레븐랩스는 "저장됨"과 "실제로 됨"이 달라서, 열 때마다 진짜로 확인 (v0.64.1)
  if(e && window._hasElevenKey){
    fetch('/api/eleven_voices', {method:'POST', body:'{}'}).then(r => r.json()).then(d => {
      const n = (d.voices || []).length;
      if(n) e.textContent = '✅ 연결됨 · 성우 ' + n + '명';
      else if(d.error) e.textContent = '⚠ 키가 동작하지 않아요 — 권한 기본값으로 새 키를 저장하세요';
      else e.textContent = '🔑 키 저장됨 · 계정에 보이스 없음';
    }).catch(() => { e.textContent = '🔑 키 저장됨'; });
  }
}
async function saveApiKey(ev, which){
  ev.preventDefault();
  const val = (which === 'gemini' ? $('apiGeminiKey').value : $('apiElevenKey').value).trim();
  if(!val){ alert('키를 붙여넣은 뒤 [저장]을 눌러주세요'); return; }
  const body = {action:'save'};
  if(which === 'gemini') body.gemini_key = val; else body.elevenlabs_key = val;
  const d = await (await fetch('/api/keys', {method:'POST', body: JSON.stringify(body)})).json();
  if(d.error){ alert(d.error); return; }
  window._hasGeminiKey = !!d.gemini; window._hasElevenKey = !!d.elevenlabs;
  if(which === 'gemini') $('apiGeminiKey').value = ''; else $('apiElevenKey').value = '';
  refreshApiStates();
  if(which === 'elevenlabs' && d.eleven_check){
    // 저장 즉시 서버가 실제 조회로 검사한 결과 (v0.64.1) — 되는 척 금지
    if(d.eleven_check.ok){
      alert('✅ 키 확인 완료! 계정에서 성우 ' + d.eleven_check.count + '명이 보여요. 영상 만들기의 「🎙 일레븐랩스 성우」 목록이 바로 채워집니다.');
      loadElevenVoices(true);
    } else {
      alert('❌ 키는 저장했지만 일레븐랩스가 거부했어요: ' + d.eleven_check.error + ' — elevenlabs.io의 API Keys에서 권한을 제한하지 말고(기본값 그대로) 새 키를 만들어 다시 저장해 주세요.');
    }
    return;
  }
  alert('저장했어요 — 이제 이 키가 필요한 기능이 모두 켜집니다');
}
async function clearAllKeys(ev){
  ev.preventDefault();
  if(!confirm('저장된 API 키를 모두 삭제할까요? (다음 사용 때 다시 입력)')) return;
  await fetch('/api/keys', {method:'POST', body: JSON.stringify({action:'clear'})});
  window._hasGeminiKey = false; window._hasElevenKey = false;
  refreshApiStates();
}

// ── ⏱ 영상 길이 직접 입력 (v0.68) ──
function onGenLenChange(){
  const custom = (($('genLenSel')||{}).value) === 'custom';
  const box = $('genLenCustomBox');
  if(box) box.classList.toggle('hidden', !custom);
}
function genTargetSec(){
  const sel = ($('genLenSel')||{}).value;
  if(sel === 'custom'){
    let m = parseFloat(($('genLenCustomMin')||{}).value) || 7;
    m = Math.max(1, Math.min(15, m));       // 1~15분 (백엔드도 같은 상한)
    return Math.round(m * 60);
  }
  return (+sel) || 60;
}

// ── ⬇ 무료 글씨체 (v0.63) ──
function fillFontSels(installed){
  const have = new Set(installed || []);
  document.querySelectorAll('select.fontsel option').forEach(o => {
    if(!o.value) return;  // 기본(프리텐다드)은 항상 가능
    const base = o.textContent.replace(' — 받기 필요', '');
    o.disabled = !have.has(o.value);
    o.textContent = o.disabled ? base + ' — 받기 필요' : base;
  });
  injectFontFaces(installed);                       // 🔤 받은 글씨체를 미리보기용으로 등록 (v0.68)
  renderSubFontPrev('genSubFontSel', 'genSubFontPrev');
  renderSubFontPrev('editSubFontSel', 'editSubFontPrev');
  renderGenHookPreview(); renderHookPreview();
}
async function fetchFonts(ev){
  ev.preventDefault();
  const btn = ev.target;
  btn.disabled = true; const old = btn.textContent; btn.textContent = '받는 중… (약 8MB)';
  try {
    const d = await (await fetch('/api/fetch_fonts', {method:'POST', body:'{}'})).json();
    if(d.error){ alert(d.error); return; }
    fillFontSels(d.fonts || []);
    let msg = '무료 글씨체 준비 완료! 이제 글씨체 목록에서 고를 수 있어요.';
    if((d.fail || []).length) msg += String.fromCharCode(10) + '실패: ' + d.fail.join(', ') + ' — 인터넷 확인 후 다시';
    alert(msg);
  } finally { btn.disabled = false; btn.textContent = old; }
}

function resetEditForm(ev){
  ev.preventDefault();
  if(!confirm('편집 폼의 모든 입력을 기본값으로 되돌릴까요?\\n(기억된 편집 세팅도 기본값으로 — 저장된 키·내 목소리는 그대로)')) return;
  const set = (id, v) => { const el = $(id); if(el) el.value = v; };
  const chk = (id, v) => { const el = $(id); if(el) el.checked = v; };
  set('editVideo',''); set('photoPath',''); set('photoSec',15);
  set('editHook',''); set('hookSizeSel','1'); set('editHookTopic','');
  const hc = $('editHookCands'); if(hc) hc.innerHTML='';
  set('narrTopic',''); chk('narrSubsOnly',false); set('narrStyleSel','정보형'); set('narrFitSel','freeze');
  set('transSel','none');
  const nv = $('narrVoiceSel'); if(nv && nv.options.length) nv.selectedIndex = 0;
  set('editScript',''); chk('autoSubChk',true); chk('cutSilenceChk',true);
  set('denoiseSel',''); window._origTouched = false; set('origAudioSel','keep');
  set('bgmEditSel',''); set('bgmVolSel','-14');
  set('wmPath',''); set('wmPos','tr'); set('wmScale','0.14');
  const rf = document.querySelector('input[name=editFinish][value=review]'); if(rf) rf.checked = true;
  set('autoTargetPreset','30'); set('autoTargetSec',30); set('editSpeedSel','1'); set('editTempoSel','');
  set('autoMultiSel','one'); set('autoQualitySel','standard');
  chk('editColdOpen',false); chk('editHookVoice',false);  // 🪝 훅 팩 (v0.75)
  chk('editFillerCut',false); chk('editTakeClean',false);  // 🧹 말 다듬기 (v0.76)
  set('weblinkUrl',''); chk('scriptTtsChk',false); window._weblink = null;  // 🔗 링크 채우기 (v0.78)
  const wpb = $('weblinkProdBtn'); if(wpb) wpb.classList.add('hidden');
  onFinishChange(); applyTargetPreset(); onAutoMultiChange();
  const st = $('sttSel'); if(st && st.options.length) st.selectedIndex = 0;
  set('whisperModelSel','small'); window._wantStt = '';
  renderHookPreview(); onNarrTopicInput();
  if(typeof toggleAutoSub === 'function') toggleAutoSub();
  // 기억된 편집 세팅도 기본값으로 덮어써 저장 (다음 실행에 옛 세팅이 되살아나지 않게)
  fetch('/api/settings', {method:'POST', body: JSON.stringify({settings:{ui:{edit_last:{
    layout:'shorts', auto_subtitle:true, cut_silence:true, denoise:'', orig_audio:'keep',
    bgm:'', bgm_db:-14, hook_scale:1, hook_style:'기본', sub_style:'기본', tone:'기본', narr_voice:'', narr_style:'', narr_subs_only:false,
    stt_provider:'', whisper_model:'small', speed:1, quality:'standard', transition:'none',
    auto_edit:false, auto_multi:false, auto_target_sec:30, photo_sec:15,
    cold_open:false, hook_voice:false, filler_cut:false, take_clean:false,
    wm_pos:'tr', wm_scale:0.14}}}})}).catch(()=>{});
}

function resetGenForm(ev){
  ev.preventDefault();
  if(!confirm('생성 폼의 입력을 기본값으로 되돌릴까요?')) return;
  const set = (id, v) => { const el = $(id); if(el) el.value = v; };
  set('topic','하루 10분 정리 습관'); set('genHook','');
  set('genHookStyleSel','기본'); set('genSubStyleSel','기본'); const gp=$('genHookPreview'); if(gp) gp.style.display='none';
  const ors=document.querySelector("input[name=genOrient][value=shorts]"); if(ors) ors.checked=true;
  set('genLenSel','60'); set('genScript','');
  const bc = $('batchChk'); if(bc){ bc.checked = false; } set('topicBatch',''); onBatchChange();
  const hc = $('genHookCands'); if(hc) hc.innerHTML='';
  set('bgmSel',''); set('voiceSel', ($('voiceSel').options[0]||{}).value || '');
  set('styleSel', ($('styleSel').options[0]||{}).value || '');
  set('genBgStyle','일러스트');
  set('genCharSel',''); set('genCharCustom',''); onGenCharChange();
  set('genSceneMode','auto'); set('genMaxImg','0');   // v0.51 그림 방식·장수
  if($('genSfxChk')) $('genSfxChk').checked = true;    // v0.53 효과음
  if($('genPunchChk')) $('genPunchChk').checked = true; // v0.55 펀치 줌
  set('genToneSel','기본'); if($('genInfoChk')) $('genInfoChk').checked = true; // v0.56
  if($('genProductSel')){ $('genProductSel').value = ''; onGenProductChange(); } // 📇 제품 끄기 + 즉시 저장 (v0.77)
  set('genContext','');
  syncDecorChips();
}

function updateLogs(lines){
  const box = $('logBox');
  if(!box || !lines) return;
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  box.textContent = (lines.length ? lines.join(String.fromCharCode(10)) : '(아직 로그 없음)');
  if(atBottom) box.scrollTop = box.scrollHeight;
}

async function copyLogs(ev){
  ev.preventDefault(); ev.stopPropagation();
  try{ await navigator.clipboard.writeText($('logBox').textContent); ev.target.textContent = '✓ 복사됨'; }
  catch(e){ alert('복사 실패 — 로그를 드래그해서 복사하세요'); }
}

function fillSettings(s){
  $('setFontSize').value = s.subtitle.font_size;
  $('setOutline').value = s.subtitle.outline;
  $('setMarginV').value = s.subtitle.margin_v;
  $('setWrapChars').value = s.subtitle.wrap_chars != null ? s.subtitle.wrap_chars : 16;
  $('setSubAnim').value = s.subtitle.anim || 'none';
  $('setFade').checked = !!s.subtitle.fade;
  $('setHookBand').checked = s.subtitle.hook_band !== false;
  $('setBand').checked = !!s.subtitle.band;
  $('setHlColor').value = s.subtitle.highlight_color;
  $('setMotion').value = s.bg.motion;
  $('setMotionAmt').value = s.bg.motion_amount;
  $('setAiImage').checked = !!s.bg.ai_image;
  $('setSceneImg').checked = s.bg.scene_images !== false;
  $('setBgmVol').value = s.bgm.volume_db;
  $('setDuck').checked = !!s.bgm.duck;
  $('setGap').value = s.audio.gap_ms;
  $('setRpm').value = s.tts.rpm_limit;
  const wr = String(s.tts.windows_rate != null ? s.tts.windows_rate : 0);
  $('setWinRate').value = ['-2','0','2','4'].includes(wr) ? wr : '0';
  loadWinVoices(s.tts.windows_voice || '');
  const ch = s.channel || {};
  $('setChName').value = ch.name || '';
  $('setChTopic').value = ch.topic || '';
  $('setChAudience').value = ch.audience || '';
  const br = s.branding || {};
  $('setIntroPath').value = br.intro || '';
  $('setOutroPath').value = br.outro || '';
  window._templates = ((s.ui || {}).templates) || {};
  refreshTplSel('');
}

// ── 📋 편집 세팅 템플릿 (v0.43) ──
function refreshTplSel(cur){
  const sel = $('tplSel'); if(!sel) return;
  sel.innerHTML = '';
  sel.add(new Option('템플릿…', ''));
  Object.keys(window._templates || {}).forEach(nm => sel.add(new Option(nm, nm)));
  sel.value = (cur && (window._templates || {})[cur]) ? cur : '';
}

function collectTplParams(){
  return {
    layout: pick('editLayout'), auto_subtitle: $('autoSubChk').checked,
    cut_silence: $('cutSilenceChk').checked, denoise: $('denoiseSel').value,
    orig_audio: $('origAudioSel').value, bgm: $('bgmEditSel').value,
    bgm_db: +$('bgmVolSel').value, hook_scale: +(($('hookSizeSel')||{}).value)||1,
    hook_style: (($('hookStyleSel')||{}).value)||'기본',
    sub_style: (($('editSubStyleSel')||{}).value)||'기본',
    tone: (($('editToneSel')||{}).value)||'기본',
    narr_voice: (($('narrVoiceSel')||{}).value)||'', narr_style: (($('narrStyleSel')||{}).value)||'',
    narr_subs_only: (($('narrSubsOnly')||{}).checked)||false,
    narr_fit: (($('narrFitSel')||{}).value)||'freeze',
    transition: (($('transSel')||{}).value)||'none',
    stt_provider: $('sttSel').value||'', whisper_model: (($('whisperModelSel')||{}).value)||'small',
    speed: +$('editSpeedSel').value||1, tempo: (($('editTempoSel')||{}).value)||'',
    quality: (($('autoQualitySel')||{}).value)||'standard',
    cold_open: !!(($('editColdOpen')||{}).checked),   // ⚡ 콜드오픈 (v0.75)
    hook_voice: !!(($('editHookVoice')||{}).checked), // 🎙 후킹 보이스 (v0.75)
    filler_cut: !!(($('editFillerCut')||{}).checked), take_clean: !!(($('editTakeClean')||{}).checked),  // 🧹 (v0.76)
    auto_edit: pick('editFinish')==='auto', auto_multi: (($('autoMultiSel')||{}).value)==='multi',
    auto_target_sec: +$('autoTargetSec').value||0, photo_sec: +(($('photoSec')||{}).value)||15,
    wm_pos: (($('wmPos')||{}).value)||'tr', wm_scale: +(($('wmScale')||{}).value)||0.14,
  };
}

async function saveTemplate(ev){
  ev.preventDefault();
  const n = (prompt('템플릿 이름 (예: 요리 쇼츠, 브이로그 톤)', $('tplSel').value || '') || '').trim();
  if(!n) return;
  const data = await (await fetch('/api/template', {method:'POST',
    body: JSON.stringify({name: n, params: collectTplParams()})})).json();
  if(data.error){ alert(data.error); return; }
  window._templates = data.templates || {};
  refreshTplSel(n);
  alert('저장했어요! 다음부터 목록에서 「' + n + '」을 고르면 이 세팅이 한 번에 적용됩니다.');
}

async function deleteTemplate(ev){
  ev.preventDefault();
  const n = $('tplSel').value;
  if(!n){ alert('지울 템플릿을 먼저 목록에서 고르세요'); return; }
  if(!confirm('템플릿 「' + n + '」을 지울까요?')) return;
  const data = await (await fetch('/api/template', {method:'POST',
    body: JSON.stringify({op:'delete', name: n})})).json();
  if(data.error){ alert(data.error); return; }
  window._templates = data.templates || {};
  refreshTplSel('');
}

function applyTemplate(){
  const n = $('tplSel').value;
  const t = (window._templates || {})[n];
  if(!n || !t) return;
  applyEditLast(t);
}

async function saveSettings(){
  const body = {settings: {
    subtitle: {font_size: +$('setFontSize').value, outline: +$('setOutline').value,
               margin_v: +$('setMarginV').value, fade: $('setFade').checked,
               highlight_color: $('setHlColor').value.toUpperCase(),
               hook_band: $('setHookBand').checked, band: $('setBand').checked,
               wrap_chars: +$('setWrapChars').value, anim: $('setSubAnim').value},
    bg: {motion: $('setMotion').value, motion_amount: +$('setMotionAmt').value,
         ai_image: $('setAiImage').checked, scene_images: $('setSceneImg').checked},
    bgm: {volume_db: +$('setBgmVol').value, duck: $('setDuck').checked},
    audio: {gap_ms: +$('setGap').value},
    tts: {rpm_limit: +$('setRpm').value, windows_rate: +$('setWinRate').value,
          windows_voice: $('setWinVoice').value},
    channel: {name: $('setChName').value.trim(), topic: $('setChTopic').value.trim(),
              audience: $('setChAudience').value.trim()},
    branding: {intro: $('setIntroPath').value.trim(), outro: $('setOutroPath').value.trim()},
  }};
  const data = await (await fetch('/api/settings', {method:'POST', body: JSON.stringify(body)})).json();
  alert(data.ok ? '저장했습니다. 다음 작업부터 적용됩니다.' : ('저장 실패: ' + data.error));
}

async function regen(id){
  const res = await fetch('/api/regenerate', {method:'POST', body: JSON.stringify({job_id: id})});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'gen';
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('reviewBox').classList.add('hidden');
  if(!timer) timer = setInterval(poll, 900);
}

async function confirmScript(){
  await fetch('/api/confirm', {method:'POST', body: JSON.stringify({
    job_id: currentJob, title: $('rvTitle').value,
    sentences: $('rvSentences').value.split('\\n'),
  })});
  $('reviewBox').classList.add('hidden');
  window._scenesLoaded = false;
  timer = timer || setInterval(poll, 900);
}

// ── 🖼 장면 그림 검토 (v0.50/0.51) — 그리드 렌더·재생성·내 그림 삽입·확정 ──
function renderScenes(job){
  const grid = $('sceneGrid'); grid.innerHTML = '';
  window._lastScenes = job.scenes || [];
  window._jobOrient = job.orientation || 'shorts';  // v0.61 복사 문구용
  const sm = $('sceneMeta');
  if(sm) sm.textContent = '(그림체: ' + (job.scene_style || '일러스트') +
    ' · 마스코트: ' + (job.scene_character || '없음') + ' — 폼 「AI 배경 그림」에서 변경)';
  (job.scenes || []).forEach((s, k) => {
    const cell = document.createElement('div');
    cell.style.cssText = 'border:1px solid #2c3350;border-radius:12px;padding:10px;background:#12141c;display:flex;flex-direction:column;gap:6px'
      + (s.ok ? '' : ';border-style:dashed');
    const head = document.createElement('div');
    head.style.cssText = 'display:flex;align-items:center;gap:8px;font-weight:700';
    head.innerHTML = '<span style="background:#22283f;border-radius:8px;padding:2px 10px">장면 ' + (k + 1) + '</span>'
      + '<span class="hint" style="font-weight:400">' + (s.ok ? '🟢 그림 있음' : '⬜ 그림 없음') + '</span>';
    cell.appendChild(head);
    if(s.ok){  // 그림이 있을 때만 이미지 — 없으면 깨진 아이콘 대신 프롬프트에 집중
      const img = document.createElement('img');
      img.style.cssText = 'width:100%;border-radius:8px;aspect-ratio:9/16;object-fit:cover;background:#0d0f14';
      img.src = '/scene/' + encodeURIComponent(job.id) + '/' + s.i + '?t=' + Date.now();
      img.alt = '장면 ' + (k + 1);
      cell.appendChild(img);
    }
    const cap = document.createElement('div');
    cap.style.cssText = 'font-size:12.5px;color:#cdd3e0;line-height:1.45';
    cap.textContent = '💬 ' + (s.text || '');
    const lab = document.createElement('div');
    lab.className = 'hint';
    lab.textContent = '그림 묘사 (프롬프트) — 고쳐도 돼요';
    const ta = document.createElement('textarea');
    ta.style.cssText = 'min-height:96px;font-size:12.5px;line-height:1.5';
    ta.value = s.prompt || '';
    ta.id = 'scnP' + s.i;
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap';
    const btn = document.createElement('button');
    btn.className = 'ghost';
    btn.style.cssText = 'padding:5px 10px;font-size:12px';
    btn.textContent = '🔄 ' + (s.ok ? '다시 그리기' : 'AI로 그리기');
    btn.onclick = (e) => regenScene(e, s.i);
    const up = document.createElement('button');
    up.className = 'ghost';
    up.style.cssText = 'padding:5px 10px;font-size:12px';
    up.textContent = '📁 내 그림';
    up.title = '직접 만든 그림 파일을 이 장면에 넣기 (자동으로 쇼츠 크기에 맞춰져요)';
    up.onclick = (e) => sceneUpload(e, s.i);
    row.append(btn, up);
    cell.append(cap, lab, ta, row);
    grid.appendChild(cell);
  });
  $('sceneBox').classList.remove('hidden');
}

async function refreshScenes(){
  const state = await (await fetch('/api/state')).json();
  const job = (state.jobs || []).find(j => j.id === currentJob);
  if(job && job.scenes) renderScenes(job);
}

// 📋 번호별 프롬프트 + 그림체·마스코트 지시문을 한 번에 복사 (v0.51 — 챗지피티/제미나이용)
async function copyScenePrompts(ev){
  ev.preventDefault();
  const scenes = window._lastScenes || [];
  if(!scenes.length){ alert('장면이 없습니다'); return; }
  const style = (($('genBgStyle')||{}).value)||'일러스트';
  const ch = (($('genCharSel')||{}).value) === 'custom'
    ? ((($('genCharCustom')||{}).value)||'').trim() : ((($('genCharSel')||{}).value)||'');
  const ratio = (window._jobOrient === 'wide') ? '가로(16:9)' : '세로(9:16)';
  const lines = [
    '아래 번호마다 유튜브용 ' + ratio + ' 이미지를 1장씩 만들어줘. 총 ' + scenes.length + '장.',
    '모든 장면은 같은 그림체(' + style + ' 느낌)로 통일하고, 글자는 넣지 말고, 화면 아래 1/3은 자막이 올라갈 수 있게 단순하게.',
  ];
  if(ch) lines.push('주인공 캐릭터: ' + ch + ' — 모든 장면에 같은 모습·같은 그림체로 등장.');
  lines.push('');
  scenes.forEach((s, k) => {  // 「N번 장면 → 프롬프트」 통합 블록 (v0.57.2 사용자 요청 형식)
    const p = (($('scnP' + s.i)||{}).value) || s.prompt || s.text || '';
    lines.push((k + 1) + '번 장면');
    lines.push(p);
    lines.push('');
  });
  const text = lines.join(String.fromCharCode(10));
  const box = $('sceneAllText');
  if(box){ box.value = text; box.classList.remove('hidden'); }
  try { await navigator.clipboard.writeText(text); }
  catch(e){ alert('자동 복사가 안 돼요 — 아래 상자의 내용을 드래그해 복사하세요'); return; }
  alert('복사 완료! (아래 상자에서도 볼 수 있어요)' + String.fromCharCode(10) +
        '챗지피티/제미나이에 붙여넣어 그림을 만들고, 한 폴더에 저장한 뒤' + String.fromCharCode(10) +
        '[📁 그림 폴더에서 한꺼번에 넣기]를 누르세요 (이름순으로 1번부터 들어가요).');
}

// 📁 폴더의 그림을 이름순으로 1번 장면부터 (v0.51)
async function importSceneFolder(ev){
  ev.preventDefault();
  const pk = await (await fetch('/api/pick_file', {method:'POST',
    body: JSON.stringify({kind:'folder'})})).json();
  if(pk.error){ alert(pk.error); return; }
  if(!pk.path) return;  // 취소
  const data = await (await fetch('/api/scene_folder', {method:'POST',
    body: JSON.stringify({job_id: currentJob, folder: pk.path})})).json();
  if(data.error){ alert(data.error); return; }
  await refreshScenes();
  let msg = '그림 ' + data.applied + '/' + data.total + '개 장면에 넣었어요';
  if(data.files < data.total) msg += ' (폴더에 그림이 ' + data.files + '개뿐 — 나머지 장면은 직전 그림 유지)';
  if((data.errors||[]).length) msg += String.fromCharCode(10) + '실패: ' + data.errors.join(', ');
  alert(msg);
}

// 📁 이 장면에 내 그림 1장 (v0.51)
async function sceneUpload(ev, i){
  ev.preventDefault();
  const pk = await (await fetch('/api/pick_file', {method:'POST',
    body: JSON.stringify({kind:'image'})})).json();
  if(pk.error){ alert(pk.error); return; }
  if(!pk.path) return;
  const data = await (await fetch('/api/scene_upload', {method:'POST',
    body: JSON.stringify({job_id: currentJob, index: i, path: pk.path})})).json();
  if(data.error){ alert(data.error); return; }
  await refreshScenes();
}

// 🎙 일레븐랩스 라디오 — 키가 없으면 등록 화면으로 안내 (v0.51 상시 노출)
function checkElevenProv(ev){
  if(window._hasElevenKey) return;
  ev.target.checked = false;
  const stub = document.querySelector("input[name='prov'][value='stub']");
  if(stub) stub.checked = true;
  if(confirm('일레븐랩스 성우를 쓰려면 키 등록이 필요해요 (elevenlabs.io 가입 → 키 발급).' +
             String.fromCharCode(10) + '등록 화면으로 갈까요?')) openVoice(ev);
}

async function regenScene(ev, i){
  ev.preventDefault();
  const btn = ev.target; const old = btn.textContent;
  btn.disabled = true; btn.textContent = '그리는 중… (10초 안팎)';
  try{
    const data = await (await fetch('/api/scene_regen', {method:'POST',
      body: JSON.stringify({job_id: currentJob, index: i, prompt: $('scnP' + i).value})})).json();
    if(data.error){ alert(data.error); return; }
    const img = btn.parentElement.querySelector('img');
    img.src = '/scene/' + encodeURIComponent(currentJob) + '/' + i + '?t=' + Date.now();
    btn.textContent = '🔄 다시 그리기';
  } finally { btn.disabled = false; if(btn.textContent.includes('중')) btn.textContent = old; }
}

async function confirmScenes(){
  const okN = (window._lastScenes || []).filter(s => s.ok).length;  // v0.51 안내
  if(!okN && !confirm('그림이 하나도 없어요 — 이대로 완성하면 기본 그라데이션 배경으로 만들어져요.' +
                      String.fromCharCode(10) + '계속할까요?')) return;
  const data = await (await fetch('/api/confirm_scenes', {method:'POST',
    body: JSON.stringify({job_id: currentJob})})).json();
  if(data.error){ alert(data.error); return; }
  $('sceneBox').classList.add('hidden');
  timer = timer || setInterval(poll, 900);
}

function onGenCharChange(){
  $('genCharCustom').classList.toggle('hidden', $('genCharSel').value !== 'custom');
}

// '으로/로' 조사 — 받침 있으면 '으로', 없거나 ㄹ받침·비한글이면 '로' ("내장 음성으로")
function josaRo(w){
  const c = (w || '').charCodeAt((w || '').length - 1);
  if(c < 0xAC00 || c > 0xD7A3) return w + '로';
  const jong = (c - 0xAC00) % 28;
  return w + ((jong === 0 || jong === 8) ? '로' : '으로');
}

// ── ⚠ AI 배경 꺼짐 경고 — 구버전 설정 파일로 장면 그림이 안 나오던 사용자용 (v0.50.1) ──
async function enableAiBg(ev){
  ev.preventDefault();
  await fetch('/api/settings', {method:'POST', body: JSON.stringify({settings:{bg:{ai_image:true}}})});
  $('aiBgOffWarn').classList.add('hidden');
  if(window._settings && window._settings.bg) window._settings.bg.ai_image = true;
  if($('setAiImage')) $('setAiImage').checked = true;
}

// ── 🎵 무료 BGM 화면에서 받기 (v0.50.1) — bat 없이 버튼 하나로 ──
function refillBgmLists(files){
  for(const id of ['bgmSel','bgmEditSel']){
    const sel = $(id); if(!sel) continue;
    const cur = sel.value;
    sel.innerHTML = '';
    sel.add(new Option('없음', ''));
    if(files.length) sel.add(new Option('랜덤', 'random'));
    for(const f of files) sel.add(new Option(f, f));
    if([...sel.options].some(o => o.value === cur)) sel.value = cur;
  }
  window._bgmFiles = files;
}

async function fetchBgm(ev){
  ev.preventDefault();
  const btn = $('bgmFetchBtn'); btn.disabled = true;
  btn.textContent = '받는 중… (1~3분)';
  try{
    await fetch('/api/fetch_bgm', {method:'POST', body:'{}'});
    while(true){
      await new Promise(s => setTimeout(s, 2000));
      const st = await (await fetch('/api/state')).json();
      const t = st.bgm_fetch || {};
      if(t.running){ btn.textContent = t.msg || '받는 중…'; continue; }
      refillBgmLists(st.bgm_files || []);
      alert((t.msg || '무료 BGM 받기 완료') + '\\n크레딧 문구는 resources/bgm 폴더의 txt 파일에 — 영상 설명란에 붙여넣으세요.');
      break;
    }
  } catch(e){ alert('받기 중 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = '⬇ 무료 BGM 받기'; }
}

// ── 🎨 감성 테마 (v0.86 → v0.87 틱톡·자막 위치) — 스타일·색감·등장·위치를 한 번에 ──
const THEMES = {
  insta:   {sub_style: '다색 팝', tone: '화사', anim: 'type', pos: 'center'},
  tiktok:  {sub_style: '블랙 박스', tone: '선명', anim: 'karaoke', pos: 'center'},
  youtube: {sub_style: '예능 노랑', tone: '선명', anim: 'pop', pos: ''},
  cinema:  {sub_style: '기본', tone: '시네마틱', anim: 'none', pos: ''},
};
window._themeAnim = window._themeAnim || {};
window._themePos = window._themePos || {};
function applyTheme(prefix){
  const sel = $(prefix + 'ThemeSel'); if(!sel) return;
  const t = THEMES[sel.value];
  window._themeAnim[prefix] = t ? t.anim : '';
  window._themePos[prefix] = t ? (t.pos || '') : '';
  if(!t) return;
  const map = {gen: ['genSubStyleSel', 'genToneSel'],
               wl: ['wlSubStyleSel', 'wlToneSel'],
               sec: ['secSubStyleSel', 'secToneSel'],
               shop: ['shopSubStyleSel', 'shopToneSel'],
               edit: ['editSubStyleSel', 'editToneSel']}[prefix] || [];
  const set = function(id, v){ const el = $(id);
    if(el && v && [...el.options].some(o => o.value === v)) el.value = v; };
  set(map[0], t.sub_style); set(map[1], t.tone);
  if(prefix === 'gen'){
    if(typeof syncDecorChips === 'function') syncDecorChips();
    if(t.pos === 'center'){   // 인스타·틱톡 감성 → 화면 형태도 릴스(자막 가운데)로
      const r = document.querySelector("input[name=genOrient][value='reels']");
      if(r && !r.checked) r.checked = true;
    }
  }
}

// ── 🛍 쇼핑 링크 감지 (v0.86) — 상품 페이지는 봇 차단 → 붙여넣기 안내 ──
const SHOP_HOST_RE = /coupang\\.com|coupa\\.ng|smartstore\\.naver\\.com|shopping\\.naver\\.com|brand\\.naver\\.com|11st\\.co\\.kr|gmarket\\.co\\.kr|auction\\.co\\.kr/i;

// ── 🛒 쿠팡 파트너스 API (v0.88) — 상품 검색으로 붙여넣기 자동 채우기 ──
async function saveCoupangKeys(ev){
  ev.preventDefault();
  const ak = (($('cpAccess')||{}).value || '').trim();
  const sk = (($('cpSecret')||{}).value || '').trim();
  if(!ak || !sk){ alert('Access Key와 Secret Key를 모두 붙여넣어 주세요'); return; }
  const d = await (await fetch('/api/coupang_keys', {method:'POST',
    body: JSON.stringify({access: ak, secret: sk})})).json();
  if(d.error){ alert(d.error); return; }
  window._hasCoupangKey = !!d.has;
  $('cpAccess').value = ''; $('cpSecret').value = '';
  $('cpKeyState').textContent = '✅ 키 저장됨 — 이제 상품을 검색해 보세요';
  alert('저장했어요 — 상품 검색으로 이름·가격·사진·파트너스 링크를 자동으로 채울 수 있어요');
}

function shopUrlGuard(inpId){
  // 🔗 검색창에 상품 '링크'를 붙여넣는 실수 방지 (v0.90) — 쿠팡·네이버 API는
  // 키워드 검색만 지원해서 링크를 넣으면 엉뚱한 인기 상품들이 나온다.
  const inp = $(inpId); if(!inp) return null;
  const kw = (inp.value || '').trim();
  if(/^https?:/i.test(kw) || kw.indexOf('www.') === 0){
    const link = $('shopLinkInput');
    if(link && !link.value.trim()){ link.value = kw; }
    inp.value = '';
    alert('붙여넣은 링크는 아래 [수익 링크]칸에 옮겨뒀어요!' + String.fromCharCode(10) +
          '그대로 [🤖 이 상품으로 대본 만들기]를 누르면 링크에서 사진·설명을 자동 수집해요.' + String.fromCharCode(10) +
          '(이 검색창은 상품 "이름" 검색용이에요 — 예: 무선 물걸레 청소기)');
    return null;
  }
  return kw;
}

async function coupangSearch(ev){
  ev.preventDefault();
  const kw = shopUrlGuard('cpKeyword');
  if(kw === null) return;
  if(!kw){ alert('검색어를 입력해 주세요 (예: 무선 선풍기)'); return; }
  if(!window._hasCoupangKey){
    const kb = $('cpKeyBox'); if(kb) kb.open = true;
    alert('먼저 파트너스 API 키를 저장해 주세요 — 쿠팡 파트너스 → 도구 → Open API에서 발급'); return;
  }
  const btn = ev.target; btn.disabled = true; const old = btn.textContent;
  btn.textContent = '검색 중…';
  try{
    const d = await (await fetch('/api/coupang_search', {method:'POST',
      body: JSON.stringify({keyword: kw})})).json();
    if(d.error){ alert(d.error); return; }
    const grid = $('cpResults'); grid.innerHTML = '';
    (d.items || []).forEach(function(it){
      const card = document.createElement('div');
      card.style.cssText = 'border:1px solid #2c3347;border-radius:10px;padding:8px;cursor:pointer;background:#14161c';
      card.innerHTML = (it.image ? '<img src="' + escHtml(it.image) + '" style="width:100%;height:96px;object-fit:contain;border-radius:6px;background:#fff">' : '') +
        '<div style="font-size:12px;margin-top:6px;line-height:1.3;max-height:48px;overflow:hidden">' + escHtml(it.name) + '</div>' +
        '<div class="hint" style="margin-top:2px">' + (it.price ? (Number(it.price).toLocaleString() + '원') : '') +
        (it.rocket ? ' 🚀' : '') + '</div>';
      card.title = '이 상품으로 채우기';
      card.onclick = function(){ coupangPick(it, card); };
      grid.appendChild(card);
    });
    if(!(d.items || []).length) alert('검색 결과가 없어요 — 다른 검색어로 시도해 보세요');
  } catch(e){ alert('상품 검색 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

async function coupangPick(it, card){       // 🛒 쇼핑 카드 공용 상품 채우기 (v0.89)
  if(card){ card.style.borderColor = '#4266d5'; }
  try{
    const d = await (await fetch('/api/coupang_pick', {method:'POST',
      body: JSON.stringify(it)})).json();
    if(d.error){ alert(d.error); return; }
    if(d.paste_text){
      const ta = $('shopPasteText');
      ta.value = d.paste_text + '\\n\\n[▼ 이 아래에 상품 페이지의 상세설명·특징·후기를 복사해 붙여넣어 주세요 — 많이 붙일수록 대본이 좋아져요]\\n';
      ta.focus();
      try{ ta.setSelectionRange(ta.value.length, ta.value.length); }catch(_e){}
    }
    if((d.images || []).length){
      window._shopPhotos = d.images.slice();           // 새 상품 = 사진 새로 시작
      window._shopPrev = (d.previews || []).slice();
      renderShopPhotoPrev();
      $('shopPhotoCnt').textContent = '📷 대표사진 1장(고화질) 자동 저장됨 — 상품 페이지를 복사해 붙여넣으면(Ctrl+V) 사진이 한꺼번에 더 들어와요';
    }
    if(d.link){ $('shopLinkInput').value = d.link; }   // 파트너스 추적 링크
    uiBanner('🛒 기본 정보를 채웠어요 (쿠팡·네이버 API는 대표사진 1장·이름·가격·분류까지만 제공) — ' +
             '① 상품 페이지의 상세설명을 복사해 덧붙이고 ② 사진을 몇 장 더 넣은 뒤 [🤖 대본 만들기]를 누르세요' +
             (d.link && d.link.indexOf('coupang') >= 0 ? ' (파트너스 링크 자동 ✓)' : ''));
  } catch(e){ alert('상품 채우기 오류: ' + e); }
}

// ── 🟢 네이버 쇼핑커넥트 (v0.89) — 검색 API로 상품 정보 ──
async function saveNaverKeys(ev){
  ev.preventDefault();
  const cid = (($('nvClientId')||{}).value || '').trim();
  const cs = (($('nvClientSecret')||{}).value || '').trim();
  if(!cid || !cs){ alert('Client ID와 Client Secret을 모두 붙여넣어 주세요'); return; }
  const d = await (await fetch('/api/naver_keys', {method:'POST',
    body: JSON.stringify({client_id: cid, client_secret: cs})})).json();
  if(d.error){ alert(d.error); return; }
  window._hasNaverKey = !!d.has;
  $('nvClientId').value = ''; $('nvClientSecret').value = '';
  $('nvKeyState').textContent = '✅ 키 저장됨 — 상품을 검색해 보세요';
  alert('저장했어요 — 이제 네이버 쇼핑 상품을 검색할 수 있어요');
}

async function naverSearch(ev){
  ev.preventDefault();
  const kw = shopUrlGuard('nvKeyword');
  if(kw === null) return;
  if(!kw){ alert('검색어를 입력해 주세요 (예: 무선 선풍기)'); return; }
  if(!window._hasNaverKey){
    const kb = $('nvKeyBox'); if(kb) kb.open = true;
    alert('먼저 네이버 검색 API 키를 저장해 주세요 — developers.naver.com에서 앱 등록(무료) 후 발급'); return;
  }
  const btn = ev.target; btn.disabled = true; const old = btn.textContent;
  btn.textContent = '검색 중…';
  try{
    const d = await (await fetch('/api/naver_search', {method:'POST',
      body: JSON.stringify({keyword: kw})})).json();
    if(d.error){ alert(d.error); return; }
    const grid = $('nvResults'); grid.innerHTML = '';
    (d.items || []).forEach(function(it){
      const card = document.createElement('div');
      card.style.cssText = 'border:1px solid #2c3347;border-radius:10px;padding:8px;cursor:pointer;background:#14161c';
      card.innerHTML = (it.image ? '<img src="' + escHtml(it.image) + '" style="width:100%;height:96px;object-fit:contain;border-radius:6px;background:#fff">' : '') +
        '<div style="font-size:12px;margin-top:6px;line-height:1.3;max-height:48px;overflow:hidden">' + escHtml(it.name) + '</div>' +
        '<div class="hint" style="margin-top:2px">' + (it.price ? (Number(it.price).toLocaleString() + '원~') : '') +
        (it.mall ? (' · ' + escHtml(it.mall)) : '') + '</div>';
      card.title = '이 상품으로 채우기';
      card.onclick = function(){ coupangPick(it, card); };   // 채우기 로직 공용 (딥링크는 쿠팡만)
      grid.appendChild(card);
    });
    if(!(d.items || []).length) alert('검색 결과가 없어요 — 다른 검색어로 시도해 보세요');
  } catch(e){ alert('상품 검색 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

// ── 🛒 쇼핑 카드 공통 (v0.89) — 사진·대본·시작 ──
async function pickShopPhotos(ev){
  ev.preventDefault();
  const btn = ev.target; btn.disabled = true;
  try{
    const data = await (await fetch('/api/pick_file', {method:'POST',
      body: JSON.stringify({kind: 'images'})})).json();
    if(data.error){ alert(data.error + PASTE_TIP); return; }
    const paths = (data.path || '').split(';').filter(Boolean);
    if(paths.length){ addShopPhotos(paths, []); }
  } catch(e){ alert('선택 창을 열 수 없습니다: ' + e + PASTE_TIP); }
  finally { btn.disabled = false; }
}

// ── 📷 사진 대량 가져오기 (v0.91) — 페이지 복사·붙여넣기 + 스크린샷 붙여넣기 ──
// 상품 페이지는 서버가 못 열어도(봇 차단), 사용자가 브라우저에서 복사한 조각의
// 이미지 주소는 공개 CDN이라 그대로 받아진다 — Ctrl+C → Ctrl+V 한 번에 여러 장.
function renderShopPhotoPrev(){
  const box = $('shopPhotoPrev'); if(!box) return;
  box.innerHTML = (window._shopPrev || []).map(function(u){
    return '<img src="' + escHtml(u) + '" style="width:64px;height:64px;object-fit:cover;border-radius:8px;border:1px solid #2c3347">';
  }).join('');
}
function addShopPhotos(paths, previews){
  window._shopPhotos = window._shopPhotos || [];
  window._shopPrev = window._shopPrev || [];
  (paths || []).forEach(function(p, i){
    if(window._shopPhotos.indexOf(p) >= 0) return;
    window._shopPhotos.push(p);
    if((previews || [])[i]) window._shopPrev.push(previews[i]);
  });
  $('shopPhotoCnt').textContent = '📷 사진 ' + window._shopPhotos.length + '장 준비됨';
  renderShopPhotoPrev();
}
function clearShopPhotos(ev){
  if(ev) ev.preventDefault();
  window._shopPhotos = []; window._shopPrev = [];
  $('shopPhotoCnt').textContent = '';
  renderShopPhotoPrev();
  uiBanner('🗑 상품 사진을 비웠어요 — 다시 붙여넣거나 [🖼 상품 사진 고르기]로 넣어주세요');
}
function extractImgUrls(html){
  const out = [], seen = {};
  const re = /<img[^>]+?(?:src|data-src|data-original)=["']([^"']+)["']/gi;
  let m;
  while((m = re.exec(html)) !== null){
    let u = m[1];
    if(u.indexOf('//') === 0) u = 'https:' + u;
    if(u.indexOf('http') !== 0) continue;          // data: 등 제외
    if(seen[u]) continue;
    seen[u] = 1; out.push(u);
    if(out.length >= 12) break;
  }
  return out;
}
async function fetchShopImages(urls){
  uiBanner('📷 붙여넣은 조각에서 사진 ' + urls.length + '장을 가져오는 중…');
  try{
    const d = await (await fetch('/api/shop_images', {method:'POST',
      body: JSON.stringify({urls})})).json();
    if(d.error){ uiBanner('📷 ' + d.error); return; }
    addShopPhotos(d.images, d.previews);
    uiBanner('📷 사진 ' + (d.images || []).length + '장을 가져왔어요' +
             (d.skipped ? ' (아이콘 같은 자잘한 그림 ' + d.skipped + '장은 뺐어요)' : '') +
             ' — 아래 미리보기 확인, 잘못 들어갔으면 [🗑 사진 비우기]');
  } catch(e){ uiBanner('📷 사진 가져오기 오류: ' + e); }
}
function uploadPastedImage(file){
  if(!file) return;
  const rd = new FileReader();
  rd.onload = async function(){
    try{
      const d = await (await fetch('/api/shop_upload', {method:'POST',
        body: JSON.stringify({data: rd.result})})).json();
      if(d.error){ uiBanner('📸 ' + d.error); return; }
      addShopPhotos(d.images, d.previews);
      uiBanner('📸 스크린샷을 상품 사진으로 넣었어요 — 지금 ' + (window._shopPhotos || []).length + '장');
    } catch(e){ uiBanner('📸 스크린샷 업로드 오류: ' + e); }
  };
  rd.readAsDataURL(file);
}
function shopPasteHandler(e){
  const cd = e.clipboardData; if(!cd) return;
  const items = cd.items || [];
  const files = [];
  for(let i = 0; i < items.length; i++){
    if(items[i].kind === 'file' && (items[i].type || '').indexOf('image/') === 0)
      files.push(items[i].getAsFile());
  }
  if(files.length){ e.preventDefault(); files.forEach(uploadPastedImage); return; }
  const html = cd.getData('text/html') || '';
  if(html && html.toLowerCase().indexOf('<img') >= 0){
    const urls = extractImgUrls(html);
    if(urls.length) fetchShopImages(urls);   // 글자는 평소처럼 붙고, 사진은 덤으로
  }
}
document.addEventListener('paste', function(e){
  const sc = $('shopCard');
  if(sc && !sc.classList.contains('hidden')) shopPasteHandler(e);
});

async function makeShopScript(ev){
  ev.preventDefault();
  const text = (($('shopPasteText')||{}).value || '').trim();
  const link = (($('shopLinkInput')||{}).value||'').trim();
  const linkOnly = text.length < 20 && !!link && SHOP_HOST_RE.test(link);   // 🔗 링크 자동 수집 (v0.92)
  if(text.length < 20 && !linkOnly){
    alert('상품 정보가 아직 없어요 — 상품 링크를 「내 수익 링크」칸에 붙여넣거나, 위에서 상품을 고르거나, 상세설명을 붙여넣어 주세요'); return;
  }
  const btn = ev.target; btn.disabled = true; const old = btn.textContent;
  btn.textContent = linkOnly ? '링크에서 자동 수집 중…' : 'AI가 대본으로 정리하는 중…';
  try{
    const key = ensureGeminiKey();
    const d = await (await fetch('/api/fetch_url', {method:'POST',
      body: JSON.stringify({pasted_text: linkOnly ? '' : text, url: link,
                            target_sec: 45, gemini_key: key, save_key: true})})).json();
    if(d.error){ alert(d.error); return; }
    while(true){
      await new Promise(s => setTimeout(s, 1500));
      const st = await (await fetch('/api/state')).json();
      const t = st.weblink_fetch || {};
      if(t.running){ btn.textContent = (t.msg || '정리 중…').slice(0, 22); continue; }
      if(t.error){ alert(t.error); break; }
      const r = t.result || {};
      $('shopScript').value = (r.script_lines || []).join('\\n');
      $('shopHook').value = r.hook || r.title || '';
      $('shopPreview').classList.remove('hidden');
      if((r.images || []).length){                       // 🛒 수집된 상품 사진 (v0.92)
        window._shopPhotos = r.images.slice();
        window._shopPrev = (r.previews || []).slice();
        renderShopPhotoPrev();
        $('shopPhotoCnt').textContent = '📷 상품 사진 ' + r.images.length + '장 자동 수집됨';
      }
      if(linkOnly && r.text){                            // 수집한 설명을 눈으로 확인·보강
        $('shopPasteText').value = r.text;
      }
      const note = ((r.notes || [])[0]) || '';
      if(note) uiBanner(note);
      else if(!(window._shopPhotos || []).length)
        uiBanner('🖼 대본 준비 완료 — [🖼 상품 사진 고르기]로 사진을 넣으면 [🎬 영상 만들기]가 가능해요');
      break;
    }
  } catch(e){ alert('대본 만들기 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

function initShopCard(){
  const nv = $('narrVoiceSel'), sv = $('shopVoiceSel');
  if(nv && sv && nv.options.length && sv.options.length !== nv.options.length){
    const cur = sv.value;
    sv.innerHTML = nv.innerHTML;
    sv.value = [...sv.options].some(o => o.value === cur) && cur ? cur : nv.value;
  }
  const bg = $('bgmEditSel'), sb = $('shopBgmSel');
  if(bg && sb && bg.options.length && sb.options.length !== bg.options.length){
    const cur = sb.value;
    sb.innerHTML = bg.innerHTML;
    sb.value = [...sb.options].some(o => o.value === cur) ? cur : '';
  }
  cloneSelect('editSubStyleSel', 'shopSubStyleSel');
  cloneSelect('hookStyleSel', 'shopHookStyleSel');
  cloneSelect('editSubFontSel', 'shopSubFontSel');
  cloneSelect('editToneSel', 'shopToneSel');
}

async function startShop(){
  const imgs = window._shopPhotos || [];
  if(!imgs.length){ alert('상품 사진을 1장 이상 넣어주세요 — [🖼 상품 사진 고르기]'); return; }
  const NL = String.fromCharCode(10);
  const lines = ($('shopScript').value || '').split(NL).map(s => s.trim()).filter(Boolean);
  if(!lines.length){ alert('대본이 비어 있어요 — [🤖 이 상품으로 대본 만들기]를 먼저 눌러주세요'); return; }
  let key = '';
  if(!window._hasGeminiKey) key = ensureGeminiKey();
  const body = {
    photo_path: imgs.join(';'),
    photo_sec: Math.max(10, Math.min(180, Math.round(lines.length * 4))),
    layout: 'shorts', quality: 'standard',
    script: lines.join(NL), script_tts: true,
    hook: ($('shopHook')||{}).value || '',
    narr_voice: ($('shopVoiceSel')||{}).value || '',
    auto_subtitle: false, cut_silence: false,
    bgm: ($('shopBgmSel')||{}).value || '',
    sub_style: ($('shopSubStyleSel')||{}).value || '',
    hook_style: ($('shopHookStyleSel')||{}).value || '',
    sub_font: ($('shopSubFontSel')||{}).value || '',
    tone: ($('shopToneSel')||{}).value || '',
    sub_anim: (window._themeAnim||{}).shop || '',
    sub_pos: (window._themePos||{}).shop || '',
    gemini_key: key, save_key: true,
  };
  const res = await fetch('/api/edit', {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'edit';
  window._subLoaded = false; window._kitLoaded = false;
  $('kitBox').classList.add('hidden'); $('kitBody').classList.add('hidden');
  $('shopCard').classList.add('hidden');
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('subEditBox').classList.add('hidden');
  $('rawErr').classList.add('hidden'); $('noteText').textContent = '';
  poll();
  timer = setInterval(poll, 900);
}
async function startShopSafe(){ try{ await startShop(); }catch(e){ reportUiError('영상 만들기', e); } }

async function pickWlPhotos(ev){
  ev.preventDefault();
  const btn = ev.target; btn.disabled = true;
  try{
    const data = await (await fetch('/api/pick_file', {method:'POST',
      body: JSON.stringify({kind: 'images'})})).json();
    if(data.error){ alert(data.error + PASTE_TIP); return; }
    const paths = (data.path || '').split(';').filter(Boolean);
    if(paths.length){
      window._wlLocalPhotos = paths;
      $('wlPhotoCnt').textContent = '📷 사진 ' + paths.length + '장 선택됨';
      if(window._weblink) window._weblink.images = paths;
    }
  } catch(e){ alert('선택 창을 열 수 없습니다: ' + e + PASTE_TIP); }
  finally { btn.disabled = false; }
}

async function loadWeblinkPasted(ev){
  ev.preventDefault();
  const text = (($('wlPasteText')||{}).value || '').trim();
  if(text.length < 30){ alert('상품 상세설명을 통째로 복사해 붙여넣어 주세요 (30자 이상)'); return; }
  const btn = ev.target; btn.disabled = true; const old = btn.textContent;
  btn.textContent = 'AI가 대본으로 정리하는 중…';
  try{
    const key = ensureGeminiKey();
    const d = await (await fetch('/api/fetch_url', {method:'POST',
      body: JSON.stringify({pasted_text: text, url: (($('weblinkUrl')||{}).value||'').trim(),
                            target_sec: 45, gemini_key: key, save_key: true})})).json();
    if(d.error){ alert(d.error); return; }
    while(true){
      await new Promise(s => setTimeout(s, 1500));
      const st = await (await fetch('/api/state')).json();
      const t = st.weblink_fetch || {};
      if(t.running){ btn.textContent = (t.msg || '정리 중…').slice(0, 22); continue; }
      if(t.error){ alert(t.error); break; }
      window._weblink = t.result || {};
      if((window._wlLocalPhotos || []).length) window._weblink.images = window._wlLocalPhotos;
      applyWeblink(window._weblink);
      if(!(window._wlLocalPhotos || []).length)
        uiBanner('🖼 대본은 준비됐어요 — [🖼 상품 사진 고르기]로 사진을 넣으면 [🎬 영상 만들기]를 누를 수 있어요');
      break;
    }
  } catch(e){ alert('대본 만들기 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

// ── 🔗 블로그 글로 사진 영상 채우기 (v0.78) ──
async function loadWeblink(ev){
  ev.preventDefault();
  const url = (($('weblinkUrl')||{}).value||'').trim();
  if(!url){ alert('블로그 글 주소를 먼저 붙여넣어 주세요'); return; }
  if(SHOP_HOST_RE.test(url)){          // 🛍 상품 페이지 → 전용 쇼핑 카드로 안내 (v0.89)
    if(confirm('쇼핑몰 상품 링크네요! 상품 영상은 [🛒 쇼핑 상품 영상] 카드가 더 편해요 — 링크에서 사진·설명을 자동 수집해요 (v0.92).\\n지금 이동할까요?')){
      openMode('shop');
      if($('shopLinkInput') && !$('shopLinkInput').value) $('shopLinkInput').value = url;
      uiBanner('🛒 링크를 넣어뒀어요 — [🤖 이 상품으로 대본 만들기]를 누르면 사진·설명을 자동 수집해요');
    } else {
      const pb = $('wlPasteBox'); if(pb) pb.open = true;
      uiBanner('🛍 여기 블로그 카드에서는 상품 페이지 자동 수집을 지원하지 않아요 — 아래 붙여넣기에 상세설명을 복사해 넣거나, [🛒 쇼핑 상품 영상] 카드를 이용해 주세요.');
    }
    return;
  }
  const btn = $('weblinkBtn'); btn.disabled = true; const old = btn.textContent;
  btn.textContent = '가져오는 중…';
  try{
    const key = ensureGeminiKey();  // 대본 요약용 — 없으면 원문 문장으로 폴백
    const d = await (await fetch('/api/fetch_url', {method:'POST',
      body: JSON.stringify({url, target_sec: 45, gemini_key: key, save_key: true})})).json();
    if(d.error){ alert(d.error); return; }
    while(true){
      await new Promise(s => setTimeout(s, 1500));
      const st = await (await fetch('/api/state')).json();
      const t = st.weblink_fetch || {};
      if(t.running){ btn.textContent = (t.msg || '가져오는 중…').slice(0, 22); continue; }
      if(t.error){ alert(t.error); break; }
      window._weblink = t.result || {};
      applyWeblink(window._weblink);
      break;
    }
  } catch(e){ alert('가져오기 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

// 🎨 카드용 셀렉트 복제 — 편집 폼의 옵션·기억값을 그대로 (v0.81)
function cloneSelect(srcId, dstId){
  const s = $(srcId), d = $(dstId);
  if(!s || !d || !s.options.length) return;
  const cur = d.value;
  if(d.options.length !== s.options.length) d.innerHTML = s.innerHTML;
  d.value = ([...d.options].some(o => o.value === cur) && cur) ? cur : s.value;
}

function initWeblinkCard(){
  // 목소리 목록: 🎙 내레이션 셀렉트와 동일하게 (상태 로드 때 채워짐)
  const nv = $('narrVoiceSel'), wl = $('wlVoiceSel');
  if(nv && wl && nv.options.length && wl.options.length !== nv.options.length){
    const cur = wl.value;
    wl.innerHTML = nv.innerHTML;
    wl.value = [...wl.options].some(o => o.value === cur) && cur ? cur : nv.value;
  }
  // 🎨 꾸미기 — 편집 폼의 스타일 옵션·기억값 복제 (v0.81)
  cloneSelect('editSubStyleSel', 'wlSubStyleSel');
  cloneSelect('hookStyleSel', 'wlHookStyleSel');
  cloneSelect('editSubFontSel', 'wlSubFontSel');
  cloneSelect('editToneSel', 'wlToneSel');
}

function applyWeblink(r){
  const imgs = r.images || [], lines = r.script_lines || [];
  // 🖼 사진 미리보기 그리드 — 체크 해제 = 영상에서 제외 (v0.79)
  const grid = $('wlGrid');
  if(grid){
    grid.innerHTML = '';
    (r.previews || []).forEach((u, i) => {
      const lab = document.createElement('label');
      lab.style.cssText = 'display:block;cursor:pointer;background:#0f1117;border:1px solid #2c3347;border-radius:10px;padding:6px';
      const img = document.createElement('img');
      img.src = u; img.loading = 'lazy';
      img.style.cssText = 'width:100%;height:110px;object-fit:cover;border-radius:6px;display:block';
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:6px;margin-top:5px;font-size:12px;color:#cdd3e0';
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = true; cb.dataset.i = i;
      row.appendChild(cb); row.appendChild(document.createTextNode((i + 1) + '번'));
      lab.appendChild(img); lab.appendChild(row);
      grid.appendChild(lab);
    });
  }
  if($('wlScript')) $('wlScript').value = lines.join('\\n');
  if($('wlHook')) $('wlHook').value = r.hook || r.title || '';
  const pv = $('wlPreview'); if(pv) pv.classList.remove('hidden');
  const h = $('weblinkHint');
  if(h){
    let msg = '✅ <b>사진 ' + imgs.length + '장 · 대본 ' + lines.length + '문장</b>을 가져왔어요 — 아래에서 확인하고 [🎬 영상 만들기]를 누르세요.';
    if((r.links||[]).length) msg += ' 🛒 글에서 상품 링크도 찾았어요 — [📇 제품 프로필 저장]을 누르면 기억해 둬요.';
    (r.notes||[]).forEach(n => { msg += '<br>ℹ ' + n; });
    h.innerHTML = msg;
  }
  const pb = $('weblinkProdBtn'); if(pb) pb.classList.remove('hidden');
}

async function startWeblink(){
  const r = window._weblink || {};
  const all = r.images || [];
  const imgs = all.filter((_, i) => {
    const c = document.querySelector('#wlGrid input[data-i="' + i + '"]');
    return !c || c.checked;
  });
  if(!imgs.length){ alert('사진을 1장 이상 남겨주세요'); return; }
  const NL = String.fromCharCode(10);
  const lines = ($('wlScript').value || '').split(NL).map(s => s.trim()).filter(Boolean);
  if(!lines.length){ alert('대본이 비어 있어요 — 한 줄에 한 문장씩 넣어주세요'); return; }
  let key = '';
  if(!window._hasGeminiKey) key = ensureGeminiKey();  // 보이스 적용용 (없어도 내장 음성으로 진행)
  const body = {
    photo_path: imgs.join(';'),
    photo_sec: Math.max(10, Math.min(180, Math.round(lines.length * 4))),
    layout: 'shorts', quality: 'standard',
    script: lines.join(NL), script_tts: true,      // 🔊 대본을 목소리로
    hook: ($('wlHook')||{}).value || '',
    narr_voice: ($('wlVoiceSel')||{}).value || '',
    auto_subtitle: false, cut_silence: false,
    bgm: ($('bgmEditSel')||{}).value || '',        // 편집 폼에서 고른 BGM 있으면 같이
    sub_style: ($('wlSubStyleSel')||{}).value || '',   // 🎨 꾸미기 (v0.81)
    hook_style: ($('wlHookStyleSel')||{}).value || '',
    sub_font: ($('wlSubFontSel')||{}).value || '',
    tone: ($('wlToneSel')||{}).value || '',
    sub_anim: (window._themeAnim||{}).wl || '',        // 🎨 감성 테마 자막 등장 (v0.86)
    sub_pos: (window._themePos||{}).wl || '',          // 🎨 자막 위치 — 인스타·틱톡 가운데 (v0.87)
    gemini_key: key, save_key: true,
  };
  const res = await fetch('/api/edit', {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._jobMode = 'edit';
  window._subLoaded = false;
  window._kitLoaded = false;
  $('kitBox').classList.add('hidden'); $('kitBody').classList.add('hidden');
  $('weblinkCard').classList.add('hidden');   // 진행 화면에 집중
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('subEditBox').classList.add('hidden');
  $('rawErr').classList.add('hidden'); $('noteText').textContent='';
  poll();
  timer = setInterval(poll, 900);
}
async function startWeblinkSafe(){ try{ await startWeblink(); }catch(e){ reportUiError('영상 만들기', e); } }

// ── 🎞 구간 대본 영상 (v0.80) ──
function initSectionCard(){
  const nv = $('narrVoiceSel'), sv = $('secVoiceSel');
  if(nv && sv && nv.options.length && sv.options.length !== nv.options.length){
    const cur = sv.value;
    sv.innerHTML = nv.innerHTML;
    sv.value = [...sv.options].some(o => o.value === cur) && cur ? cur : nv.value;
  }
  const bg = $('bgmEditSel'), sb = $('secBgmSel');
  if(bg && sb && bg.options.length && sb.options.length !== bg.options.length){
    const cur = sb.value;
    sb.innerHTML = bg.innerHTML;
    sb.value = [...sb.options].some(o => o.value === cur) ? cur : '';
  }
  // 🎨 꾸미기 — 편집 폼의 스타일 옵션·기억값 복제 (v0.81)
  cloneSelect('editSubStyleSel', 'secSubStyleSel');
  cloneSelect('hookStyleSel', 'secHookStyleSel');
  cloneSelect('editSubFontSel', 'secSubFontSel');
  cloneSelect('editToneSel', 'secToneSel');
  if($('secRows') && !$('secRows').children.length) addSectionRow();
  // 💾 임시 저장 자동 복원 (v0.85) — 비어 있을 때만, 한 번만
  const draft = ((window._settings || {}).ui || {}).sec_draft;
  if(draft && !window._secDraftLoaded && $('secRows')){
    const rs = $('secRows').children;
    const empty = !rs.length ||
      (rs.length === 1 && !(((rs[0].querySelector('.sec-narr')||{}).value || '').trim()));
    if(empty){
      fillSectionsForm(draft);
      window._secDraftLoaded = true;
      const h = $('secDraftHint'); if(h) h.classList.remove('hidden');
    }
  }
  applySecMode();
}

function addSectionRow(title, narration){
  const rows = $('secRows'); if(!rows) return;
  const div = document.createElement('div');
  div.className = 'secrow';
  div.style.cssText = 'border:1px solid #2c3347;border-radius:10px;padding:10px;margin-top:8px;background:#171a23';
  const head = document.createElement('div');
  head.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap';
  const num = document.createElement('b');
  num.className = 'sec-num'; num.style.cssText = 'color:#8b93a7;white-space:nowrap';
  const ti = document.createElement('input');
  ti.type = 'text'; ti.className = 'sec-title'; ti.placeholder = '구간 제목 (선택 — 타임라인에 표시)';
  ti.style.cssText = 'flex:1;min-width:140px'; ti.value = title || '';
  const tm = document.createElement('span');           // ⏱ 예상 시간 (v0.82)
  tm.className = 'sec-time hint'; tm.style.cssText = 'white-space:nowrap;color:#7fd18a';
  const del = document.createElement('button');
  del.className = 'ghost'; del.textContent = '✕'; del.title = '이 구간 삭제';
  del.style.cssText = 'padding:4px 10px';
  del.onclick = function(ev){ ev.preventDefault(); div.remove(); renumberSections(); };
  head.appendChild(num); head.appendChild(ti); head.appendChild(tm); head.appendChild(del);
  const vrow = document.createElement('div');
  vrow.className = 'sec-cliprow';
  vrow.style.cssText = 'display:flex;gap:8px;margin-top:6px;flex-wrap:wrap';
  const vi = document.createElement('input');
  vi.type = 'text'; vi.className = 'sec-video';
  vi.placeholder = '이 구간에 쓸 영상(화면녹화) 파일 경로';
  vi.style.cssText = 'flex:1;min-width:180px';
  const pick = document.createElement('button');
  pick.className = 'ghost'; pick.textContent = '🎬 클립 선택';
  pick.style.cssText = 'white-space:nowrap';
  pick.onclick = function(ev){ pickSectionVideo(ev, vi); };
  const sp = document.createElement('select');         // ⏩ 구간별 배속 (v0.82)
  sp.className = 'sec-speed'; sp.style.cssText = 'width:auto;padding:6px 8px';
  sp.title = '클립이 내레이션보다 길 때 줄이는 방법 — 몽타주는 핵심 장면만 잘라 붙이고, 배속은 안 자르고 빨리 감아요';
  [['', '컷: 자동 (핵심 몽타주)'], ['fit', '⏩ 배속으로 통째로 맞춤 (안 잘림)'],
   ['1.5', '⏩ 1.5배속'], ['2', '⏩ 2배속'], ['3', '⏩ 3배속']
  ].forEach(function(o){ sp.add(new Option(o[1], o[0])); });
  vrow.appendChild(vi); vrow.appendChild(pick); vrow.appendChild(sp);
  // 🎥 풀영상 모드: 이 구간이 풀영상의 몇 초~몇 초인지 (v0.84)
  const rrow = document.createElement('div');
  rrow.className = 'sec-rangebox';
  rrow.style.cssText = 'display:none;gap:6px;margin-top:6px;align-items:center;flex-wrap:wrap';
  const rl = document.createElement('span');
  rl.className = 'hint'; rl.textContent = '풀영상에서';
  const si = document.createElement('input');
  si.type = 'text'; si.className = 'sec-start'; si.placeholder = '시작 0:00';
  si.style.cssText = 'width:82px';
  const dash = document.createElement('span'); dash.textContent = '~';
  const ei = document.createElement('input');
  ei.type = 'text'; ei.className = 'sec-end'; ei.placeholder = '끝 0:20';
  ei.style.cssText = 'width:82px';
  const bs = document.createElement('button');
  bs.className = 'ghost'; bs.textContent = '▶ 여기부터'; bs.style.cssText = 'padding:4px 8px';
  bs.title = '위 플레이어의 현재 위치를 이 구간의 시작으로';
  bs.onclick = function(ev){ ev.preventDefault(); si.value = fmtMMSS((($('secPlayer')||{}).currentTime)||0); };
  const be = document.createElement('button');
  be.className = 'ghost'; be.textContent = '⏹ 여기까지'; be.style.cssText = 'padding:4px 8px';
  be.title = '위 플레이어의 현재 위치를 이 구간의 끝으로';
  be.onclick = function(ev){ ev.preventDefault(); ei.value = fmtMMSS((($('secPlayer')||{}).currentTime)||0); };
  const bp = document.createElement('button');
  bp.className = 'ghost'; bp.textContent = '👁 이 구간 재생'; bp.style.cssText = 'padding:4px 8px';
  bp.onclick = function(ev){
    ev.preventDefault();
    const p = $('secPlayer'); if(!p || !p.src){ alert('먼저 [🎥 풀영상 선택]으로 영상을 골라주세요'); return; }
    const s = parseMMSS(si.value), e = parseMMSS(ei.value);
    if(s == null){ alert('시작 시간을 먼저 넣어주세요 (예: 1:20)'); return; }
    p.currentTime = s; window._secStopAt = (e != null && e > s) ? e : null; p.play();
  };
  // 자동 배속(핵심 몽타주) 셀렉트는 두 모드 공용 — 범위 줄에도 같이 보임
  rrow.appendChild(rl); rrow.appendChild(si); rrow.appendChild(dash); rrow.appendChild(ei);
  rrow.appendChild(bs); rrow.appendChild(be); rrow.appendChild(bp);
  const na = document.createElement('textarea');
  na.className = 'sec-narr';
  na.placeholder = '이 구간에서 읽을 내레이션 — 한 줄 = 자막 한 줄. 이 길이만큼 구간이 만들어져요';
  na.style.cssText = 'min-height:64px;margin-top:6px'; na.value = narration || '';
  na.oninput = updateSectionTimes;
  div.appendChild(head); div.appendChild(vrow); div.appendChild(rrow); div.appendChild(na);
  rows.appendChild(div);
  renumberSections();
  applySecMode();
  return div;
}

// 🎥 영상 넣는 방식 전환 (v0.84) — 풀영상 하나 vs 구간마다 클립
function applySecMode(){
  const full = (pick('secSrcMode') || 'full') === 'full';
  const fb = $('secFullBox'); if(fb) fb.classList.toggle('hidden', !full);
  [...(($('secRows')||{}).children || [])].forEach(function(d){
    const c = d.querySelector('.sec-cliprow');
    const r = d.querySelector('.sec-rangebox');
    if(c) c.style.display = full ? 'none' : 'flex';
    if(r) r.style.display = full ? 'flex' : 'none';
    if(full && r && c){                      // 배속 셀렉트를 보이는 줄로 옮김
      const spSel = d.querySelector('.sec-speed');
      if(spSel && spSel.parentElement !== r) r.appendChild(spSel);
    } else if(!full && c){
      const spSel = d.querySelector('.sec-speed');
      if(spSel && spSel.parentElement !== c) c.appendChild(spSel);
    }
  });
}

function parseMMSS(v){
  v = String(v || '').trim(); if(!v) return null;
  const m = v.match(/^(?:(\\d+):)?(\\d+(?:\\.\\d+)?)$/);
  if(!m) return null;
  return (m[1] ? parseInt(m[1], 10) * 60 : 0) + parseFloat(m[2]);
}

async function pickFullVideo(ev){
  ev.preventDefault();
  const btn = ev.target; btn.disabled = true; const label = btn.textContent;
  try{
    const data = await (await fetch('/api/pick_file', {method:'POST',
      body: JSON.stringify({kind: 'video'})})).json();
    if(data.error){ alert(data.error + PASTE_TIP); }
    else if(data.path){ $('secFullPath').value = data.path; await loadFullVideo(); }
  } catch(e){ alert('선택 창을 열 수 없습니다: ' + e + PASTE_TIP); }
  finally { btn.disabled = false; btn.textContent = label; }
}

async function loadFullVideo(){
  const vp = ($('secFullPath')||{}).value.trim(); if(!vp) return;
  try{
    const d = await (await fetch('/api/reg_video', {method:'POST',
      body: JSON.stringify({path: vp})})).json();
    if(d.error){ alert(d.error); return; }
    $('secFullPath').value = d.path;
    const p = $('secPlayer');
    p.src = '/localvideo/' + d.token + '?t=' + Date.now();
    p.classList.remove('hidden');
    if(!window._secStopHooked){
      window._secStopHooked = true;         // 👁 구간 재생 — 끝 시각에서 자동 정지
      p.addEventListener('timeupdate', function(){
        if(window._secStopAt != null && p.currentTime >= window._secStopAt){
          p.pause(); window._secStopAt = null;
        }
      });
    }
    $('secFullDur').textContent = '⏱ 풀영상 길이 ' + fmtMMSS(d.duration_s) +
      ' — [🪄 자동으로 나누기]를 누르면 구간별 시간이 채워져요. 재생하며 [▶ 여기부터]/[⏹ 여기까지]로 손보세요.';
  } catch(e){ alert('영상 불러오기 오류: ' + e); }
}

// 💾 구간 작성 임시 저장 (v0.85) — 피곤할 때 저장해 두고 다음에 이어서
function collectSecDraft(){
  return {
    src_mode: pick('secSrcMode') || 'full',
    full_video: (($('secFullPath')||{}).value || '').trim(),
    layout: pick('secLayout') || 'wide',
    narr_voice: (($('secVoiceSel')||{}).value || ''),
    tempo: (($('secTempoSel')||{}).value || ''),
    bgm: (($('secBgmSel')||{}).value || ''),
    transition: (($('secXfadeSel')||{}).value || ''),
    sub_style: (($('secSubStyleSel')||{}).value || ''),
    hook_style: (($('secHookStyleSel')||{}).value || ''),
    sub_font: (($('secSubFontSel')||{}).value || ''),
    tone: (($('secToneSel')||{}).value || ''),
    sections: [...(($('secRows')||{}).children || [])].map(d => ({
      title: (d.querySelector('.sec-title')||{}).value || '',
      narration: (d.querySelector('.sec-narr')||{}).value || '',
      video_path: ((d.querySelector('.sec-video')||{}).value || '').trim(),
      speed: (d.querySelector('.sec-speed')||{}).value || '',
      start: ((d.querySelector('.sec-start')||{}).value || '').trim(),
      end: ((d.querySelector('.sec-end')||{}).value || '').trim(),
    })),
  };
}

async function saveSecDraft(ev){
  ev.preventDefault();
  const btn = ev.target;
  try{
    const draft = collectSecDraft();
    const d = await (await fetch('/api/sec_draft', {method:'POST',
      body: JSON.stringify({draft})})).json();
    if(d.error){ alert(d.error); return; }
    if(window._settings){ (window._settings.ui = window._settings.ui || {}).sec_draft = draft; }
    btn.textContent = '✓ 저장됨';
    setTimeout(() => { btn.textContent = '💾 임시 저장'; }, 1500);
  } catch(e){ alert('임시 저장 오류: ' + e); }
}

async function clearSecDraft(ev){
  ev.preventDefault();
  try{
    await (await fetch('/api/sec_draft', {method:'POST', body: JSON.stringify({clear: true})})).json();
    if(window._settings && window._settings.ui) window._settings.ui.sec_draft = null;
    window._secDraftLoaded = false;
    const h = $('secDraftHint'); if(h) h.classList.add('hidden');
    ev.target.textContent = '✓'; setTimeout(() => { ev.target.textContent = '🗑'; }, 1200);
  } catch(e){ alert('지우기 오류: ' + e); }
}

// ✏ 폼 채우기 — 임시 저장(문자 시간) / 다시 편집(㎲ 시간) 양쪽 지원 (v0.85)
function fillSectionsForm(d){
  d = d || {};
  const rows = $('secRows'); if(!rows) return;
  const mode = d.src_mode || (d.full_video ? 'full' : 'clips');
  const mr = document.querySelector('input[name="secSrcMode"][value="' + mode + '"]');
  if(mr) mr.checked = true;
  if($('secFullPath')){
    $('secFullPath').value = d.full_video || '';
    if(d.full_video) loadFullVideo();
  }
  const lr = document.querySelector('input[name="secLayout"][value="' + (d.layout || 'wide') + '"]');
  if(lr) lr.checked = true;
  const setSel = function(id, v){
    const el = $(id);
    if(el && v != null && v !== '' && [...el.options].some(o => o.value === String(v))) el.value = String(v);
  };
  setSel('secVoiceSel', d.narr_voice); setSel('secTempoSel', d.tempo);
  setSel('secBgmSel', d.bgm); setSel('secXfadeSel', d.transition);
  setSel('secSubStyleSel', d.sub_style); setSel('secHookStyleSel', d.hook_style);
  setSel('secSubFontSel', d.sub_font); setSel('secToneSel', d.tone);
  rows.innerHTML = '';
  (d.sections || []).forEach(function(s){
    const div = addSectionRow(s.title || '', s.narration || '');
    if(!div) return;
    const set = function(cls, v){ const el = div.querySelector(cls); if(el && v != null && v !== '') el.value = v; };
    set('.sec-video', s.video_path);
    set('.sec-speed', s.speed);
    set('.sec-start', s.start_us != null ? fmtMMSS(s.start_us / 1e6) : (s.start || ''));
    set('.sec-end', s.end_us != null ? fmtMMSS(s.end_us / 1e6) : (s.end || ''));
  });
  if(!(d.sections || []).length) addSectionRow();
  applySecMode(); updateSectionTimes();
}

// ✏ 완성한 구간 영상을 폼으로 불러와 일부만 고쳐 다시 만들기 (v0.85)
async function reEditSections(id){
  if(!id){ alert('불러올 작업이 없어요'); return; }
  try{
    const d = await (await fetch('/api/job_params', {method:'POST',
      body: JSON.stringify({job_id: id})})).json();
    if(d.error){ alert(d.error); return; }
    showHome(); openMode('sections');
    fillSectionsForm(d.params || {});
    window._secReuseJob = id;
    uiBanner('✏ 이전 작업을 불러왔어요 — 고칠 구간만 수정하고 [🎬 영상 만들기]를 누르세요. 바뀐 구간만 다시 만들어 훨씬 빨라요 ♻');
  } catch(e){ alert('다시 편집 불러오기 오류: ' + e); }
}

// 🪄 내레이션 분량 비율 + 장면 전환점 스냅으로 구간 시간 자동 채우기 (v0.84)
async function suggestSecRanges(ev, silent){
  if(ev) ev.preventDefault();
  const vp = ($('secFullPath')||{}).value.trim();
  if(!vp){ if(!silent) alert('먼저 [🎥 풀영상 선택]으로 영상을 골라주세요'); return false; }
  const rows = [...(($('secRows')||{}).children || [])];
  if(!rows.length){ if(!silent) alert('구간이 없어요 — [➕ 구간 추가] 또는 대본 자동 나누기를 먼저 해주세요'); return false; }
  const btn = ev ? ev.target : null; if(btn){ btn.disabled = true; }
  try{
    const weights = rows.map(function(d){
      return Math.max(1, (((d.querySelector('.sec-narr')||{}).value || '').replace(/\\s/g, '').length));
    });
    const d = await (await fetch('/api/suggest_ranges', {method:'POST',
      body: JSON.stringify({video_path: vp, weights})})).json();
    if(d.error){ if(!silent) alert(d.error); return false; }
    (d.ranges || []).forEach(function(r, i){
      const row = rows[i]; if(!row) return;
      const si2 = row.querySelector('.sec-start'), ei2 = row.querySelector('.sec-end');
      if(si2) si2.value = fmtMMSS(r[0] / 1e6);
      if(ei2) ei2.value = fmtMMSS(r[1] / 1e6);
    });
    if(!silent) alert('🪄 구간 ' + (d.ranges || []).length + '개의 시간을 채웠어요' +
      (d.snapped ? ' (화면이 바뀌는 지점에 맞춤)' : '') +
      '\\n어긋난 구간은 재생하면서 [▶ 여기부터]/[⏹ 여기까지]로 고치면 돼요');
    return true;
  } catch(e){ if(!silent) alert('자동 나누기 오류: ' + e); return false; }
  finally { if(btn) btn.disabled = false; }
}

function renumberSections(){
  const rows = $('secRows'); if(!rows) return;
  [...rows.children].forEach((d, i) => {
    const n = d.querySelector('.sec-num'); if(n) n.textContent = '구간 ' + (i + 1);
  });
  updateSectionTimes();
}

function fmtMMSS(s){
  s = Math.max(0, Math.round(s));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

// ⏱ 대본처럼 "몇 초부터 몇 초" — 내레이션 글자수로 구간 시간 실시간 예측 (v0.82)
function updateSectionTimes(){
  const rows = [...(($('secRows')||{}).children || [])];
  let cum = 0;
  rows.forEach(function(d){
    const el = d.querySelector('.sec-time'); if(!el) return;
    const txt = ((d.querySelector('.sec-narr')||{}).value || '');
    const lines = txt.split('\\n').filter(function(t){ return t.trim(); });
    const chars = lines.join('').replace(/\\s/g, '').length;
    if(!chars){ el.textContent = ''; return; }
    const est = Math.max(2, chars / 5.5 + lines.length * 0.35 + 0.7);  // 한국어 낭독 ≈ 초당 5.5자
    el.textContent = '⏱ 예상 ' + fmtMMSS(cum) + ' ~ ' + fmtMMSS(cum + est);
    cum += est;
  });
  const tot = $('secTotal');
  if(tot) tot.textContent = cum
    ? ('⏱ 전체 예상: 약 ' + fmtMMSS(cum) + ' — 실제 읽은 길이에 따라 조금 달라져요. 완성되면 유튜브 설명란용 실제 타임라인을 드려요.')
    : '';
}

async function pickSectionVideo(ev, input){
  ev.preventDefault();
  const btn = ev.target; btn.disabled = true; const label = btn.textContent;
  try{
    const data = await (await fetch('/api/pick_file', {method:'POST',
      body: JSON.stringify({kind: 'video'})})).json();
    if(data.error){ alert(data.error + PASTE_TIP); }
    else if(data.path){ input.value = data.path; }
  } catch(e){ alert('선택 창을 열 수 없습니다: ' + e + PASTE_TIP); }
  finally { btn.disabled = false; btn.textContent = label; }
}

async function splitSections(ev){
  ev.preventDefault();
  const text = (($('secScriptText')||{}).value||'').trim();
  if(!text){ alert('대본을 먼저 붙여넣어 주세요'); return; }
  const btn = $('secSplitBtn'); btn.disabled = true; const old = btn.textContent;
  btn.textContent = '나누는 중…';
  try{
    const key = ensureGeminiKey();  // 형식 자유 대본은 AI가 더 잘 나눔 (없으면 규칙 기반)
    const d = await (await fetch('/api/section_split', {method:'POST',
      body: JSON.stringify({script_text: text, gemini_key: key, save_key: true})})).json();
    if(d.error){ alert(d.error); return; }
    const rows = $('secRows'); rows.innerHTML = '';
    (d.sections || []).forEach(s => addSectionRow(s.title || '', s.narration || ''));
    alert('✂️ 구간 ' + (d.sections || []).length + '개로 나눴어요 — 이제 구간마다 [🎬 클립 선택]으로 영상을 넣어주세요');
  } catch(e){ alert('구간 나누기 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

async function startSections(){
  const full = (pick('secSrcMode') || 'full') === 'full';        // 🎥 v0.84
  const fullPath = full ? (($('secFullPath')||{}).value || '').trim() : '';
  if(full && !fullPath){ alert('[🎥 풀영상 선택]으로 영상을 골라주세요 — 구간마다 클립을 따로 넣으려면 위에서 [🎬 구간마다 클립 따로]를 고르세요'); return; }
  const collect = function(){
    return [...(($('secRows')||{}).children || [])].map(d => {
      const s = parseMMSS(((d.querySelector('.sec-start')||{}).value || ''));
      const e = parseMMSS(((d.querySelector('.sec-end')||{}).value || ''));
      return {
        title: (d.querySelector('.sec-title')||{}).value || '',
        video_path: ((d.querySelector('.sec-video')||{}).value || '').trim(),
        narration: (d.querySelector('.sec-narr')||{}).value || '',
        speed: (d.querySelector('.sec-speed')||{}).value || '',  // ⏩ 구간별 배속 (v0.82)
        start_us: s != null ? Math.round(s * 1e6) : null,
        end_us: e != null ? Math.round(e * 1e6) : null,
      };
    }).filter(s => s.narration.trim());
  };
  let sections = collect();
  if(!sections.length){ alert('구간이 없어요 — [➕ 구간 추가]로 구간을 만들고 내레이션을 넣어주세요'); return; }
  if(full){
    const missing = sections.some(s => s.start_us == null || s.end_us == null || s.end_us <= s.start_us);
    if(missing){                     // 시간이 빈 구간이 있으면 자동 제안으로 채우고 진행
      if(!(await suggestSecRanges(null, true))){
        alert('구간 시간이 비어 있어요 — [🪄 자동으로 나누기]를 먼저 눌러주세요'); return;
      }
      sections = collect();
    }
  } else {
    for(let i = 0; i < sections.length; i++){
      if(!sections[i].video_path){ alert('구간 ' + (i + 1) + '의 클립(영상)을 골라주세요'); return; }
    }
  }
  let key = '';
  if(!window._hasGeminiKey) key = ensureGeminiKey();  // 보이스 적용용 (없어도 내장 음성)
  const body = {
    sections,
    full_video: fullPath,                    // 🎥 풀영상 하나로 (v0.84 — 빈 값이면 클립 모드)
    transition: ($('secXfadeSel')||{}).value || '',   // 🎬 구간 전환 종류 (v0.85)
    reuse_job: window._secReuseJob || '',             // ♻ 바뀐 구간만 재제작 (v0.85)
    layout: pick('secLayout') || 'wide',
    quality: 'standard',
    narr_voice: ($('secVoiceSel')||{}).value || '',
    tempo: ($('secTempoSel')||{}).value || '',
    bgm: ($('secBgmSel')||{}).value || '',
    sub_anim: (window._themeAnim||{}).sec || '',       // 🎨 감성 테마 자막 등장 (v0.86)
    sub_pos: (window._themePos||{}).sec || '',         // 🎨 자막 위치 — 인스타·틱톡 가운데 (v0.87)
    sub_style: ($('secSubStyleSel')||{}).value || '',  // 🎨 꾸미기 (v0.81)
    hook_style: ($('secHookStyleSel')||{}).value || '',
    sub_font: ($('secSubFontSel')||{}).value || '',
    tone: ($('secToneSel')||{}).value || '',
    gemini_key: key, save_key: true,
  };
  const res = await fetch('/api/section_edit', {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  window._secReuseJob = data.job_id;   // ♻ 다음 "다시 편집"은 방금 작업 기준으로 이어짐
  window._jobMode = 'edit';
  window._subLoaded = false;
  window._kitLoaded = false;
  $('kitBox').classList.add('hidden'); $('kitBody').classList.add('hidden');
  $('sectionCard').classList.add('hidden');
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  $('subEditBox').classList.add('hidden');
  $('rawErr').classList.add('hidden'); $('noteText').textContent='';
  poll();
  timer = setInterval(poll, 900);
}
async function startSectionsSafe(){ try{ await startSections(); }catch(e){ reportUiError('영상 만들기', e); } }

// ⏱ 타임라인 복사 (v0.82) — 유튜브 설명란에 붙여넣으면 챕터가 생겨요
async function copyChapters(ev){
  ev.preventDefault();
  try{
    await navigator.clipboard.writeText(($('chaptersText')||{}).textContent || '');
    const btn = ev.target; btn.textContent = '✓ 복사됨';
    setTimeout(() => { btn.textContent = '📋 복사'; }, 1500);
  } catch(e){ alert('복사 실패 — 직접 드래그해서 복사하세요'); }
}

// 📦 업로드용 용량 줄이기 (v0.83) — 화질 거의 그대로 파일 크기 대폭 축소
// ── 📱 완성 영상 → 쇼츠·편집 보내기 (v0.90) — "16:9로 만들었는데 쇼츠도 바로" ──
function sendDoneToEdit(ev, layout){
  if(ev) ev.preventDefault();
  const job = window._lastDoneJob || {};
  const mp4 = ((job.mp4s && job.mp4s.length) ? job.mp4s[0] : job.mp4) || '';
  if(!mp4){
    alert('완성된 영상 경로를 찾지 못했어요 — [📂 폴더 열기]에서 mp4를 확인하고, 편집 카드의 [📁 영상 선택]으로 직접 골라주세요');
    return;
  }
  openMode('edit');
  window.scrollTo(0, 0);
  $('editVideo').value = mp4;
  const r = document.querySelector("input[name=editLayout][value='" + layout + "']");
  if(r) r.checked = true;
  if(layout === 'shorts'){
    // 긴 가로 영상 → 쇼츠: 완전 자동(핵심만) + 60초 여러 개 나누기를 추천 기본으로
    const auto = document.querySelector("input[name=editFinish][value='auto']");
    if(auto && !auto.checked){ auto.checked = true; try{ onFinishChange(); }catch(_e){} }
    if($('autoMultiSel')) $('autoMultiSel').value = 'multi';
    if($('autoTargetSec') && !(+($('autoTargetSec').value))) $('autoTargetSec').value = 60;
    uiBanner('📱 완성 영상을 쇼츠로! — 세로(9:16) + 완전 자동(핵심만 남겨 60초 쇼츠 여러 개)로 맞춰뒀어요. 원하면 바꾸고 아래 [시작]을 누르세요');
  } else {
    uiBanner('✂ 완성 영상을 편집 카드로 불러왔어요 — 자르기·자막·훅·BGM을 설정하고 [시작]을 누르세요');
  }
}

async function shrinkVideo(ev){
  ev.preventDefault();
  if(!currentJob){ alert('완성된 작업이 없어요'); return; }
  const btn = ev.target; btn.disabled = true; const old = btn.textContent;
  btn.textContent = '📦 줄이는 중… (긴 영상은 몇 분 걸려요)';
  try{
    const d = await (await fetch('/api/shrink', {method:'POST',
      body: JSON.stringify({job_id: currentJob})})).json();
    if(d.error){ alert(d.error); return; }
    for(let i = 0; i < 1800; i++){                  // 최대 1시간 대기 (2초 간격)
      await new Promise(r => setTimeout(r, 2000));
      const st = await (await fetch('/api/state')).json();
      const job = (st.jobs || []).find(j => j.id === currentJob) || {};
      if(job.shrink_status === 'done'){
        $('outPaths').innerHTML += '<br>📦 업로드용: ' + escHtml(job.shrink_out || '') +
          ' <span class="hint">(' + job.shrink_before_mb + ' MB → ' + job.shrink_after_mb + ' MB)</span>';
        alert('📦 업로드용 파일 완성!\\n' + job.shrink_before_mb + ' MB → ' + job.shrink_after_mb +
              ' MB\\n[📂 폴더 열기]를 눌러 이름 끝에 _업로드용 이 붙은 mp4를 올리세요');
        return;
      }
      if(job.shrink_status === 'failed'){
        alert('용량 줄이기 실패: ' + (job.shrink_error || '알 수 없는 오류')); return;
      }
    }
    alert('시간이 오래 걸리고 있어요 — [📂 폴더 열기]에서 _업로드용.mp4가 생겼는지 확인해 주세요');
  } catch(e){ alert('용량 줄이기 오류: ' + e); }
  finally{ btn.disabled = false; btn.textContent = old; }
}

async function saveWeblinkProduct(ev){
  ev.preventDefault();
  const r = window._weblink || {};
  const rawText = r.text || r.text_excerpt || '';
  if(!rawText){ alert('먼저 [🔗 글 가져오기]로 글을 불러와 주세요'); return; }
  const btn = $('weblinkProdBtn'); btn.disabled = true; const old = btn.textContent;
  btn.textContent = '📇 정리 중…';
  try{
    const key = ensureGeminiKey();
    const d = await (await fetch('/api/product_summarize', {method:'POST',
      body: JSON.stringify({text: (r.title ? r.title + '\\n' : '') + rawText,
                            gemini_key: key, save_key: true})})).json();
    if(d.error){ alert(d.error); return; }
    const item = d.item || {};
    if(!(item.name||'').trim()) item.name = (r.title || '새 제품').slice(0, 40);
    if(!(item.link||'').trim() && (r.links||[]).length) item.link = r.links[0];  // 🛒 제휴 링크 자동
    const sv = await (await fetch('/api/products', {method:'POST',
      body: JSON.stringify({action:'save', item})})).json();
    if(sv.error){ alert(sv.error); return; }
    await loadProducts(item.name);
    alert('📇 「' + item.name + '」 제품 프로필로 저장했어요!\\n🤖 AI 영상 만들기의 「📇 제품」에서 고르면 이 사실만 근거로 대본을 씁니다.');
  } catch(e){ alert('저장 오류: ' + e); }
  finally { btn.disabled = false; btn.textContent = old; }
}

async function poll(){
  const state = await (await fetch('/api/state')).json();
  window._hasGeminiKey = state.keys.gemini;
  window._hasCoupangKey = !!(state.keys || {}).coupang;   // 🛒 파트너스 (v0.88)
  if(window._hasCoupangKey && $('cpKeyState') && !window._cpStateSet){
    window._cpStateSet = true;
    $('cpKeyState').textContent = '— ✅ 키 저장됨, 상품을 검색해 보세요';
  }
  window._hasNaverKey = !!(state.keys || {}).naver;       // 🟢 쇼핑커넥트 (v0.89)
  if(window._hasNaverKey && $('nvKeyState') && !window._nvStateSet){
    window._nvStateSet = true;
    $('nvKeyState').textContent = '— ✅ 키 저장됨, 상품을 검색해 보세요';
  }

  window._isWin = (state.platform || '').startsWith('win');
  window._hasElevenKey = !!(state.keys && state.keys.elevenlabs);
  if(window._hasElevenKey){
    $('provElevenLabel').classList.remove('hidden');   // 🎙 성우 보이스 (키 있을 때만)
    loadElevenVoices();
  }
  if(window._isWin){
    $('provWinLabel').classList.remove('hidden');
  }
  if(!window._optsFilled){
    window._optsFilled = true;
    for(const v of state.voices || []){ $('voiceSel').add(new Option(v, v)); $('narrVoiceSel').add(new Option(v, v)); }
    for(const s of state.styles || []){ $('styleSel').add(new Option(s, s)); $('narrStyleSel').add(new Option(s, s)); }
    window._bgmFiles = state.bgm_files || [];
    if((state.bgm_files || []).length){
      $('bgmSel').add(new Option('랜덤', 'random'));
      $('bgmEditSel').add(new Option('랜덤', 'random'));
      for(const f of state.bgm_files){ $('bgmSel').add(new Option(f, f)); $('bgmEditSel').add(new Option(f, f)); }
    }
    if(state.settings) fillSettings(state.settings);
    window._settings = state.settings || {};
    // v0.45: 마지막에 쓴 장면 그림체 복원
    const bgst = ((state.settings || {}).bg || {}).image_style;
    if(bgst && $('genBgStyle') && [...$('genBgStyle').options].some(o => o.value === bgst))
      $('genBgStyle').value = bgst;
    // v0.50: 마스코트 캐릭터 복원 (프리셋 키면 선택, 아니면 직접 쓰기로)
    const bgc = ((state.settings || {}).bg || {}).character || '';
    if(bgc && $('genCharSel')){
      if([...$('genCharSel').options].some(o => o.value === bgc)) $('genCharSel').value = bgc;
      else { $('genCharSel').value = 'custom'; $('genCharCustom').value = bgc; }
      onGenCharChange();
    }
    // v0.54: 자막 글씨 스타일 복원 (생성 폼)
    const sst = ((state.settings || {}).subtitle || {}).sub_style || '기본';
    if($('genSubStyleSel')) $('genSubStyleSel').value = sst;
    // v0.56: 화면 톤·숫자 팝 복원 (생성 폼)
    if($('genToneSel')) $('genToneSel').value = ((state.settings || {}).bg || {}).tone || '기본';
    syncDecorChips();
    if($('genInfoChk')) $('genInfoChk').checked = (((state.settings || {}).subtitle || {}).info_pop !== false);
    // v0.55: 펀치인 줌 체크 복원
    if($('genPunchChk')) $('genPunchChk').checked = (((state.settings || {}).bg || {}).punch_in !== false);
    // v0.53: 효과음 체크 복원
    if($('genSfxChk')) $('genSfxChk').checked = (((state.settings || {}).sfx || {}).enabled !== false);
    // v0.52: 상단 제목 글씨 스타일 복원 (생성 폼)
    const hks = ((state.settings || {}).subtitle || {}).hook_style || '기본';
    if($('genHookStyleSel')) $('genHookStyleSel').value = hks;
    // v0.64: 제품 목록 채우기 + 마지막 선택 복원
    window._products = (state.settings || {}).products || [];
    const gsel = $('genProductSel');
    if(gsel){
      gsel.innerHTML = '<option value="">없음 (일반 주제)</option>';
      window._products.forEach(x => gsel.add(new Option('📇 ' + x.name, x.name)));
      const lastP = ((state.settings || {}).ui || {}).gen_product || '';
      if(lastP && [...gsel.options].some(o => o.value === lastP)) gsel.value = lastP;
      updateProductBadge();  // 복원된 제품을 배지로 크게 알림 (v0.77)
    }
    // v0.63: 글씨체·기울임 복원 + 설치 목록 반영
    fillFontSels(state.fonts || []);
    const subF = ((state.settings || {}).subtitle || {}).font || '';
    const hkF = ((state.settings || {}).subtitle || {}).hook_font || '';
    const tiltV = !!((state.settings || {}).subtitle || {}).hook_tilt;
    ['genSubFontSel', 'editSubFontSel'].forEach(id => {
      const el = $(id); if(el) el.value = (subF === 'Pretendard-ExtraBold') ? '' : subF; });
    ['genHookFontSel', 'editHookFontSel'].forEach(id => { const el = $(id); if(el) el.value = hkF; });
    ['genHookTiltChk', 'editHookTiltChk'].forEach(id => { const el = $(id); if(el) el.checked = tiltV; });
    // v0.61: 화면 형태·영상 길이 복원
    const gor = ((state.settings || {}).ui || {}).gen_orientation;
    if(gor){ const r = document.querySelector("input[name=genOrient][value='" + gor + "']"); if(r) r.checked = true; }
    const glen = ((state.settings || {}).ui || {}).gen_target_sec;
    if(glen && $('genLenSel')){
      if([...$('genLenSel').options].some(o => +o.value === +glen)){
        $('genLenSel').value = String(glen);
      } else {                                  // 프리셋에 없는 값 → 직접 입력으로 복원 (v0.68)
        $('genLenSel').value = 'custom';
        if($('genLenCustomMin')) $('genLenCustomMin').value = String(Math.round(glen / 60 * 10) / 10);
      }
      onGenLenChange();
    }
    // 🎙 지난 제작에 쓴 일레븐랩스 성우 — 목록이 채워지면 자동 선택 (v0.67)
    window._wantGenElevenVoice = ((state.settings || {}).ui || {}).gen_eleven_voice || '';
    // 🎙 후킹 보이스 선택 복원 (v0.75)
    if($('genHookVoice')) $('genHookVoice').checked = !!((state.settings || {}).ui || {}).gen_hook_voice;
    // v0.51: 그림 방식·최대 장수 복원
    const scm = ((state.settings || {}).bg || {}).scene_mode || 'auto';
    if($('genSceneMode')) $('genSceneMode').value = scm;
    const mxi = ((state.settings || {}).bg || {}).max_scene_images || 0;
    if($('genMaxImg')) $('genMaxImg').value = String(mxi);
    initHookChips();
    const mv = ((state.settings || {}).tts || {});
    if(mv.voice_elevenlabs) addMyVoiceOption(mv.voice_elevenlabs_name || '내 목소리');
    const wms = ((state.settings || {}).watermark || {});
    if(wms.path){ $('wmPath').value = wms.path; $('wmPos').value = wms.pos || 'tr';
                  $('wmScale').value = String(wms.scale || 0.14); }
    if(mv.sovits_ref_audio){
      addSovitsOption();
      $('sovitsRef').value = mv.sovits_ref_audio;
      $('sovitsRefText').value = mv.sovits_ref_text || '';
    }
    // 지난번 편집 세팅 복원 — 내 목소리 옵션이 추가된 뒤에 (보이스 복원 가능하도록)
    applyEditLast(((state.settings || {}).ui || {}).edit_last || {});
  }
  $('keySaved').classList.toggle('hidden', !state.keys.gemini);
  $('startGuide').classList.toggle('hidden', !!state.keys.gemini);  // 처음 사용자 안내
  // ⚠ 설정에서 AI 배경이 꺼져 있으면 생성 폼에 경고 + 켜기 버튼 (v0.50.1)
  $('aiBgOffWarn').classList.toggle('hidden', !!(((state.settings || {}).bg || {}).ai_image));
  const env = state.env || {};
  const problems = [];
  if(env.ffmpeg === false) problems.push('⚠ FFmpeg가 없습니다 — windows 폴더의 1_설치.bat 을 먼저 실행한 뒤 이 화면을 새로고침하세요.');
  if(env.font === false) problems.push('⚠ 자막 폰트가 없습니다 — zip을 다시 풀어주세요 (resources/fonts 폴더).');
  $('envBanner').classList.toggle('hidden', problems.length === 0);
  $('envBanner').textContent = problems.join('  ');

  renderHistory(state.history);
  updateLogs(state.logs);
  renderJobsBar(state.jobs || []);   // 📋 진행·대기 목록 (v0.88)
  syncParallelSel(state);            // 🔀 동시 개수 셀렉트 동기화 (v0.90)
  // 🎙 쇼핑 카드 목소리·BGM — 목록이 늦게 로드돼도 계속 동기화 (v0.93 버그 수정:
  // 카드를 목록 로드 전에 열면 목소리가 빈 채로 남던 문제. initShopCard는 멱등)
  if(window._view === 'shop') initShopCard();
  if(!currentJob) return;
  const job = state.jobs.find(j => j.id === currentJob);
  if(!job) return;
  if(job.status === 'cancelled'){
    clearInterval(timer); timer = null;
    $('stageText').textContent = '✕ 취소됨 — 대기열에서 뺐어요';
    $('goBtn').disabled = false; $('editBtn').disabled = false;
    return;
  }

  $('statusTitle').textContent = job.title || job.id;
  const frac = job.frac || 0;
  $('barFill').style.width = (job.status==='ok'||job.status==='partial' ? 100 : Math.round(frac*100)) + '%';
  let elaTxt = '';                     // ⏱ 오래 걸릴 때 최소한 경과라도 보이게 (v0.90)
  if(job.status === 'running' && job.t_start){
    const es = Math.max(0, Math.floor(Date.now() / 1000 - job.t_start));
    if(es >= 60) elaTxt = ' · ⏱ ' + Math.floor(es / 60) + '분 경과';
  }
  $('stageText').textContent = (STAGE_KO[job.stage] || job.stage || '') +
      (job.status==='running' && job.stage!=='review' ? ` — ${Math.round(frac*100)}%` : '') + elaTxt;
  let note = job.status === 'running' ? (job.note || '') : '';
  // 렌더 초반 0%가 '멈춤'으로 보이지 않도록 안내 (배경 줌은 시간이 걸림)
  if(job.status==='running' && job.stage==='render' && frac < 0.02)
    note = note || '영상 렌더링 준비 중… 배경 줌 효과는 사양에 따라 1~5분 걸릴 수 있어요. 검은 창을 닫지 마세요.';
  $('noteText').textContent = note;

  if(job.status === 'awaiting_review' && job.script){
    clearInterval(timer); timer = null;
    $('reviewBox').classList.remove('hidden');
    if(!$('rvTitle').value) $('rvTitle').value = job.script.title;
    if(!$('rvSentences').value){
      const hls = job.script.highlights || [];
      $('rvSentences').value = job.script.sentences
        .map((t, i) => hls[i] ? `${t} | ${hls[i]}` : t).join('\\n');
    }
  }
  if(job.status === 'review_scenes' && !window._scenesLoaded){   // 🖼 장면 검토 (v0.50)
    clearInterval(timer); timer = null;
    window._scenesLoaded = true;
    renderScenes(job);
  }
  if(job.status === 'review_subtitle' && !window._subLoaded){
    clearInterval(timer); timer = null;
    window._subLoaded = true;
    window._trimStart = 0; window._trimEnd = 0;
    if($('trimInfo')) $('trimInfo').textContent = '전체 사용';
    resetSubPosBar(((window._settings||{}).subtitle||{}).margin_v);  // ↕ 자막 위치 (v0.49)
    // 강조 단어가 있으면 "문장 | 단어" 형태로 보여줘 그 자리에서 수정 가능
    window._subs = (job.subtitles || []).map(s => ({
      text: s.highlight ? (s.text + ' | ' + s.highlight) : s.text,
      start_us: s.start_us, end_us: s.end_us,
      words: s.words || [], conf: (s.conf === undefined ? 1 : s.conf),
      repeat: !!s.repeat,   // ↻ 반복 테이크 후보 (v0.76)
    }));
    // ↻ 반복 감지 안내 + [반복 정리] 버튼 표시
    const repN = window._subs.filter(s => s.repeat).length;
    const repBtn = $('cleanRepeatsBtn');
    if(repBtn) repBtn.style.display = repN ? '' : 'none';
    if(repBtn) repBtn.textContent = '↻ 반복 정리 (' + repN + '곳)';
    $('subEditBox').classList.remove('hidden');
    $('bulkBox').classList.add('hidden'); $('bulkText').value='';
    const cp=$('cutPlayer');
    cp.src = '/cutvideo/' + job.id + '?t=' + Date.now();
    cp.ontimeupdate = hlActiveSub;  // 재생 위치 따라 자막 하이라이트 + 시계
    cp.onplay = () => { $('playToggle').textContent='⏸ 정지'; };
    cp.onpause = () => { $('playToggle').textContent='▶ 재생'; };
    cp.playbackRate = parseFloat(($('playRate')||{}).value || '1');
    if($('hlReason')) $('hlReason').textContent='';
    renderSubRows();
    $('noteText').textContent = job.edit_summary || '';
  }
  const provKo = {gemini:'Gemini', openai:'OpenAI', windows:'Windows 내장 음성', stub:'소리 점검용'};
  if(job.status === 'ok' || job.status === 'partial'){
    clearInterval(timer); timer = null;
    // 완료 화면에도 안내(트림·핵심 구간·TTS 경고)를 남김 — 진행 중에만 보이던 문제 수정 (v0.41)
    $('noteText').textContent = job.note || '';
    $('stageText').innerHTML = job.status === 'ok'
      ? '<span class="ok-badge">✔ 완료 — 자가검증 통과</span>'
      : '<span class="fail-badge">부분 완료</span>';
    let badge = job.tts_provider ? '목소리: ' + (provKo[job.tts_provider] || job.tts_provider) : '';
    if(job.requested_tts && job.tts_provider && job.requested_tts !== job.tts_provider)
      badge = '⚠ ' + josaRo(provKo[job.tts_provider] || job.tts_provider) + ' 대체 생성됨 (원래 선택: ' + (provKo[job.requested_tts] || job.requested_tts) + ')';
    if(job.edit_summary) badge = '✂️ ' + job.edit_summary;  // 편집 모드 요약
    if(job.bg_source) badge = (badge ? badge + '  ·  ' : '') + '🖼️ 배경: ' + job.bg_source;
    $('providerBadge').textContent = badge;
    if(job.mp4){
      window._lastDoneJob = job;     // 📱 쇼츠로 만들기·✂ 편집 보내기용 (v0.90)
      $('doneBox').classList.remove('hidden');
      $('player').src = '/video/' + job.id + '?t=' + Date.now() + '#t=0.1';
      if(job.mp4s && job.mp4s.length > 1){
        const isSec = !!job.chapters;   // 🎞 구간 합본 작업 — 쇼츠 아님 (v0.94 라벨 정리)
        $('outPaths').innerHTML = (isSec
            ? '🎬 완성 파일 ' + job.mp4s.length + '개 (1번이 최종 합본, 나머지는 구간별 파일):<br>'
            : '🎬 쇼츠 ' + job.mp4s.length + '개 완성:<br>') +
          job.mp4s.map((p,i)=>('  '+(i+1)+') '+escHtml(p))).join('<br>') +
          '<br><span class="hint">' + (isSec
            ? '(위 플레이어가 최종 합본이에요. 업로드는 1번 파일 하나면 됩니다)'
            : '(위 플레이어는 1번 쇼츠. 나머지는 [📂 폴더 열기]에서 확인)') + '</span>';
      } else {
        $('outPaths').textContent = 'mp4: ' + job.mp4;
      }
      // ⏱ 구간 타임라인 (v0.82) — 유튜브 설명란용 챕터 텍스트
      const chp = job.chapters || '';
      $('chaptersBox').classList.toggle('hidden', !chp);
      $('chaptersText').textContent = chp;
    }
    showErrors(job.errors);
    $('goBtn').disabled = false; $('editBtn').disabled = false;
  }
  if(job.status === 'failed'){
    clearInterval(timer); timer = null;
    $('stageText').innerHTML = '<span class="fail-badge">✘ 실패</span>';
    if(!(job.errors || []).length) $('errBox').textContent = '알 수 없는 오류';
    showErrors(job.errors);
    $('errBox').classList.remove('hidden');
    $('goBtn').disabled = false; $('editBtn').disabled = false;
  }
}

const PROV_KO = {gemini:'Gemini', openai:'OpenAI', windows:'내장', stub:'톤'};
// ── 🔀 동시 작업 개수 (v0.90) — "하나 하는 동안 다른 게 멈추면 느리다" ──
async function setParallel(ev){
  const n = +ev.target.value || 2;
  try{
    const d = await (await fetch('/api/parallel', {method:'POST', body: JSON.stringify({n})})).json();
    if(d.error){ alert(d.error); return; }
    uiBanner('🔀 이제 동시에 ' + d.n + '개까지 같이 만들어요' +
             (d.n === 1 ? ' (순서대로 하나씩)' : ' — PC가 버벅이면 1~2개로 낮추세요'));
  } catch(e){ alert('설정 저장 실패: ' + e); }
}
function syncParallelSel(state){
  const ps = $('parallelSel');
  if(!ps || document.activeElement === ps) return;   // 고르는 중엔 건드리지 않음
  const n = (((state.settings || {}).ui) || {}).parallel_jobs || 2;
  if(+ps.value !== +n) ps.value = String(n);
}
// ── 📋 작업 큐 — 진행·대기 목록 칩 (v0.88) ──
function renderJobsBar(jobs){
  const bar = $('jobsBar'); if(!bar) return;
  const act = (jobs || []).filter(j =>
    ['queued', 'running', 'review_subtitle', 'review_scenes'].includes(j.status));
  bar.classList.toggle('hidden', act.length === 0);
  [...bar.querySelectorAll('.jobchip')].forEach(c => c.remove());
  act.slice(0, 6).forEach(j => {
    const chip = document.createElement('span');
    chip.className = 'jobchip';
    chip.style.cssText = 'display:inline-flex;gap:6px;align-items:center;padding:4px 10px;' +
      'border:1px solid ' + (j.id === currentJob ? '#4266d5' : '#2c3347') +
      ';border-radius:999px;background:#171a23;cursor:pointer;font-size:12.5px';
    const ico = j.status === 'queued' ? '⏳'
      : j.status === 'running' ? '▶' : '📝';
    const pct = j.status === 'running' ? (' ' + Math.round((j.frac || 0) * 100) + '%') : '';
    let ela = '';                       // ⏱ 경과 시간 (v0.90)
    if(j.status === 'running' && j.t_start){
      const s = Math.max(0, Math.floor(Date.now() / 1000 - j.t_start));
      if(s >= 60) ela = ' · ' + Math.floor(s / 60) + '분';
    }
    chip.textContent = ico + ' ' + ((j.title || j.id).slice(0, 16)) + pct + ela;
    chip.title = (j.title || j.id) + ' — 눌러서 이 작업 화면 보기';
    chip.onclick = function(){ watchJob(j.id); };
    if(j.status === 'queued'){
      const x = document.createElement('b');
      x.textContent = '✕'; x.title = '대기 취소';
      x.style.cssText = 'color:#e46a6a;cursor:pointer';
      x.onclick = function(ev){ ev.stopPropagation(); cancelQueued(j.id); };
      chip.appendChild(x);
    }
    bar.appendChild(chip);
  });
}

function watchJob(id){
  currentJob = id;
  window._subLoaded = false; window._kitLoaded = false;
  ['formCard', 'editCard', 'weblinkCard', 'sectionCard', 'shopCard'].forEach(c => {
    const el = $(c); if(el) el.classList.add('hidden');
  });
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.add('hidden'); $('errBox').classList.add('hidden');
  if(!timer) timer = setInterval(poll, 900);
  poll();
}

async function cancelQueued(id){
  try{
    const d = await (await fetch('/api/cancel_queued', {method:'POST',
      body: JSON.stringify({job_id: id})})).json();
    if(d.error) alert(d.error);
  } catch(e){ alert('취소 오류: ' + e); }
}

function renderHistory(rows){
  const tb = $('histTable').querySelector('tbody');
  tb.innerHTML = '';
  for(const r of rows || []){
    const tr = document.createElement('tr');
    const btns = [
      r.has_mp4 ? `<button class="ghost" onclick="playHist('${r.id}')">▶ 재생</button>` : '',
      r.has_mp4 ? `<button class="ghost" onclick="kitHist('${r.id}')" title="유튜브 업로드 문구(제목·태그·설명) 만들기">📦 업로드 키트</button>` : '',
      r.has_spec ? `<button class="ghost" onclick="regen('${r.id}')" title="저장된 설계로 mp4 재렌더">♻ 재생성</button>` : '',
      (r.has_params && r.mode === 'sections')
        ? `<button class="ghost" onclick="reEditSections('${r.id}')" title="구간·내레이션을 폼으로 불러와 일부만 고쳐 다시 만들기 — 바뀐 구간만 재제작">✏ 다시 편집</button>` : '',
    ].join(' ');
    tr.innerHTML = `<td>${escHtml((r.created_at||'').replace('T',' ').slice(5,16))}</td>
      <td>${escHtml(r.title||r.id)}</td><td>${escHtml(PROV_KO[r.tts_provider]||'-')}</td>
      <td>${r.status==='ok'?'<span class="ok-badge">완료</span>':r.status}</td>
      <td style="white-space:nowrap">${btns}</td>`;
    tb.appendChild(tr);
  }
}

function playHist(id){
  $('statusCard').classList.remove('hidden');
  $('doneBox').classList.remove('hidden');
  $('statusTitle').textContent = '히스토리 재생';
  $('stageText').textContent = '';
  $('player').src = '/video/' + id + '?t=' + Date.now() + '#t=0.1';
}

function resetForm(){
  currentJob = null; if(timer){clearInterval(timer); timer=null;}
  window._subLoaded = false; window._subs = [];
  $('statusCard').classList.add('hidden');
  $('reviewBox').classList.add('hidden');
  $('subEditBox').classList.add('hidden');
  $('rvTitle').value = ''; $('rvSentences').value = '';
  $('noteText').textContent = ''; $('providerBadge').textContent = '';
  $('errBox').classList.add('hidden'); $('rawErr').classList.add('hidden');
  if($('thumbBox')){ $('thumbBox').classList.add('hidden'); $('thumbResult').classList.add('hidden');
    $('thumbTitle').value=''; $('thumbCands').innerHTML=''; }
  window._kitLoaded = false;
  if($('kitBox')){ $('kitBox').classList.add('hidden'); $('kitBody').classList.add('hidden'); }
  $('goBtn').disabled = false; $('editBtn').disabled = false;
  showHome();
}

// 스페이스바 = 재생/정지 (자막 검토 화면에서만, 입력창 포커스 땐 제외 — 브루식 단축키)
document.addEventListener('keydown', (e) => {
  if(e.code !== 'Space' && e.key !== ' ') return;
  const t = e.target, tag = (t.tagName || '').toLowerCase();
  if(tag==='input' || tag==='textarea' || tag==='select' || t.isContentEditable) return;
  const box = $('subEditBox');
  if(!box || box.classList.contains('hidden')) return;
  e.preventDefault(); togglePlay();
});

injectFontFaces([]);  // 🔤 번들 프리텐다드 즉시 등록 — 받은 글씨체는 poll의 fillFontSels가 추가 (v0.68)
poll(); setInterval(()=>{ if(!currentJob) poll(); }, 5000);
</script>
</body>
</html>
"""
