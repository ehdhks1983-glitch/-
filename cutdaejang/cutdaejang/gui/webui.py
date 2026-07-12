"""컷대장 로컬 웹 UI — 브라우저에서 클릭으로 생성·검토·재생까지.

`python -m cutdaejang ui` 한 줄이면 127.0.0.1 로컬 서버가 뜨고 기본 브라우저가 열린다.
표준 라이브러리(http.server)만 사용 — 추가 설치 없음. 기획안 §6의 GUI(탭① 새 작업,
탭② 대본 검토, 탭③ 히스토리)를 웹 화면 하나로 구현한 확인용 프런트엔드다.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .. import config
from ..core import background_generator, orchestrator, tts_engine
from ..core.orchestrator import JobOptions
from ..core.render_engine.ffmpeg_composer import RenderOptions
from ..core.script_generator import SCRIPT_PROVIDERS, Script
from ..core.tts_engine import GEMINI_VOICES, STYLE_INSTRUCTIONS

_JOBS: dict = {}
_LOCK = threading.Lock()


def _set_job(job_id: str, **fields) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {"id": job_id}).update(fields)


def _get_job(job_id: str) -> Optional[dict]:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


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


def default_drafts_dir() -> str:
    """Windows 표준 CapCut Drafts 경로 자동 감지 (없으면 빈 문자열)."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        if p.is_dir():
            return str(p)
    return ""


def _apply_keys(params: dict) -> None:
    """UI에서 입력한 API 키를 이 프로세스 환경변수로만 반영 (디스크 저장 없음)."""
    for field, env in (("gemini_key", "GEMINI_API_KEY"), ("openai_key", "OPENAI_API_KEY")):
        value = (params.get(field) or "").strip()
        if value:
            os.environ[env] = value


def _tts_chain(params: dict, settings: dict) -> list:
    provider = params.get("tts_provider", "stub")
    if provider == "gemini":
        return list(settings["tts"]["fallback_chain"])
    return [provider]


def _job_options(params: dict, settings: Optional[dict] = None) -> JobOptions:
    settings = settings or config.load_settings()
    outputs = ["mp4"]
    if params.get("draft"):
        outputs.append("draft")
    return JobOptions(
        outputs=tuple(outputs),
        auto_mode=bool(params.get("auto", True)),
        tts_chain=_tts_chain(params, settings),
        voice=params.get("voice", ""),
        tts_style=params.get("tts_style", ""),
        bgm=params.get("bgm", ""),
        target_sec=int(params.get("target_sec") or 60),
        drafts_dir=(params.get("drafts_dir") or "").strip() or None,
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
            out_draft=result.draft_path or None,
            error="; ".join(result.errors) or None,
            tts_provider=result.tts_provider or None,
        )
        store.close()
    except Exception:
        pass  # 히스토리 기록 실패는 UI 동작에 영향 없음


def _run_pipeline(job_id: str, script: Script, params: dict, workdir: str) -> None:
    settings = config.load_settings()
    opts = _job_options(params, settings)
    try:
        image_provider = None
        if os.environ.get("GEMINI_API_KEY") and params.get("script_provider") == "gemini":
            image_provider = background_generator.GeminiImage()

        result = orchestrator.run_job(
            workdir, script, opts=opts, settings=settings,
            image_provider=image_provider,
            progress_cb=lambda stage, frac: _set_job(job_id, stage=stage, frac=frac),
            status_cb=lambda msg: _set_job(job_id, note=msg),
            job_id=job_id,
        )
        _set_job(
            job_id,
            status=result.status,
            stage="done",
            frac=1.0,
            note="",
            title=result.title,
            job_dir=result.job_dir,
            mp4=result.mp4.out_path if (result.mp4 and result.mp4.ok) else None,
            draft=result.draft_path or None,
            tts_provider=result.tts_provider,
            requested_tts=params.get("tts_provider", ""),
            fallback_note=result.fallback_note,
            errors=result.errors,
        )
        _record_history(workdir, result, opts)
    except Exception as e:
        _set_job(job_id, status="failed", errors=[str(e)])


def _run_generate(job_id: str, params: dict, workdir: str) -> None:
    """대본 생성 → 자동 모드면 즉시 파이프라인, 검토 모드면 대기 (기획안 §1.3)."""
    try:
        _apply_keys(params)
        _set_job(job_id, status="running", stage="script", frac=0.0)
        provider = SCRIPT_PROVIDERS[params.get("script_provider", "stub")]()
        script = orchestrator.generate_script(
            provider, params["topic"], _job_options(params)
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
        _set_job(job_id, status="failed", errors=[str(e)])


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

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

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
        elif path.startswith("/preview/"):
            self._serve_preview(path.split("/", 2)[2])
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            params = self._read_json()
        except json.JSONDecodeError:
            self._send_json({"error": "잘못된 요청"}, 400)
            return

        workdir = self.server.workdir  # type: ignore[attr-defined]
        if path == "/api/generate":
            topic = (params.get("topic") or "").strip()
            if not topic:
                self._send_json({"error": "주제를 입력하세요"}, 400)
                return
            job_id = orchestrator.new_job_id(topic)
            _set_job(job_id, status="running", stage="script", frac=0.0,
                     title=topic, params=params)
            threading.Thread(
                target=_run_generate, args=(job_id, params, workdir), daemon=True
            ).start()
            self._send_json({"job_id": job_id})
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
            script = Script(
                title=params.get("title") or job.get("title", ""),
                sentences=sentences,
                highlights=highlights,
                background_prompt=(job.get("script") or {}).get("background_prompt", ""),
            )
            _set_job(job["id"], status="running", stage="tts", frac=0.0)
            threading.Thread(
                target=_run_pipeline,
                args=(job["id"], script, job.get("params", {}), workdir),
                daemon=True,
            ).start()
            self._send_json({"ok": True})
        elif path == "/api/preview":
            self._preview(params)
        else:
            self._send_json({"error": "not found"}, 404)

    # ---------- 목소리 미리듣기 (지시서 PATCH 6) ----------

    def _preview(self, params: dict) -> None:
        _apply_keys(params)
        settings = config.load_settings()
        if params.get("tts_style"):
            settings = config.deep_merge(
                settings, {"tts": {"style_preset": params["tts_style"]}}
            )
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
                    "draft": r["out_draft"] or "",
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
            "drafts_dir": default_drafts_dir(),
            "keys": {
                "gemini": bool(os.environ.get("GEMINI_API_KEY")),
                "openai": bool(os.environ.get("OPENAI_API_KEY")),
            },
            "platform": sys.platform,
            "env": _env_check(),
            "bgm_files": sorted(
                p.name
                for p in orchestrator.DEFAULT_BGM_DIR.glob("*")
                if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
            ),
            "voices": GEMINI_VOICES,
            "styles": list(STYLE_INSTRUCTIONS),
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

    def _serve_video(self, job_id: str) -> None:
        path = self._video_path(job_id)
        if not path:
            self._send_json({"error": "영상 없음"}, 404)
            return
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

        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", "video/mp4")
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


def create_server(workdir: str, port: int = 7860) -> ThreadingHTTPServer:
    Path(workdir).mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    httpd.workdir = str(workdir)  # type: ignore[attr-defined]
    return httpd


def serve(workdir: str = "jobs", port: int = 7860, open_browser: bool = True) -> int:
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
  .hidden { display:none !important; }
  code { background:#0f1117; padding:2px 6px; border-radius:4px; font-size:12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>컷대장 <small>쇼츠 자동 조립 — 확인용 UI (v0.3)</small></h1>
  <div class="banner hidden" id="envBanner"></div>

  <div class="card" id="formCard">
    <label>쇼츠 주제</label>
    <input type="text" id="topic" placeholder="예) 하루 10분 정리 습관" value="하루 10분 정리 습관">

    <div class="row">
      <div>
        <label>모드</label>
        <div class="toggle">
          <label><input type="radio" name="mode" value="auto" checked><span>자동 (한 번에 완성)</span></label>
          <label><input type="radio" name="mode" value="review"><span>검토 (대본 확인 후)</span></label>
        </div>
      </div>
      <div>
        <label>목소리</label>
        <div class="toggle">
          <label id="provWinLabel" class="hidden"><input type="radio" name="prov" value="windows" id="provWin"><span>내장 음성 (무료)</span></label>
          <label><input type="radio" name="prov" value="gemini"><span>Gemini (실전 품질)</span></label>
          <label><input type="radio" name="prov" value="stub" checked><span>테스트 톤</span></label>
        </div>
        <div class="hint">내장 음성 = Windows 한국어 음성(키·인터넷 불필요) · Gemini = 성우급 + <b>진짜 대본 생성</b> · 테스트 톤 = "삐-" 소리(기계 점검용)</div>
      </div>
    </div>

    <div id="keyRow" class="hidden">
      <label>Gemini API 키 <span class="hint">(이 PC의 메모리에만 유지, 저장 안 함 — <a href="https://aistudio.google.com/apikey" target="_blank" style="color:#7a9bff">발급</a>)</span></label>
      <input type="password" id="geminiKey" placeholder="AIza...">
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

    <div class="row">
      <div>
        <label>배경음악 (BGM)</label>
        <select id="bgmSel"><option value="">없음</option></select>
        <div class="hint">resources/bgm 폴더에 음원을 넣으면 목록에 나타납니다. 저작권 확인된 음원만 사용하세요.</div>
      </div>
    </div>

    <div class="chk">
      <input type="checkbox" id="draftChk">
      <span>캡컷 draft도 생성 (출력 A — 캡컷 설치 PC)</span>
    </div>
    <div id="draftRow" class="hidden">
      <label>캡컷 Drafts 폴더</label>
      <input type="text" id="draftsDir" placeholder="자동 감지 실패 시 직접 입력">
    </div>

    <button id="goBtn" onclick="generate()">생성 시작</button>
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
      <button onclick="confirmScript()">이 대본으로 계속</button>
    </div>

    <div id="doneBox" class="hidden">
      <div class="stage" id="providerBadge"></div>
      <video id="player" controls playsinline></video>
      <div class="stage" id="outPaths"></div>
    </div>
    <div class="err hidden" id="errBox"></div>
    <details class="hidden" id="rawErr" style="margin-top:8px">
      <summary class="hint" style="cursor:pointer">자세히 (원본 오류)</summary>
      <pre class="err" id="rawErrText" style="overflow-x:auto"></pre>
    </details>
    <button class="ghost" style="margin-top:14px" onclick="resetForm()">+ 새 작업</button>
  </div>

  <div class="card">
    <div style="font-weight:700">히스토리</div>
    <table id="histTable"><thead>
      <tr><th>시각</th><th>제목</th><th>모드</th><th>상태</th><th></th></tr>
    </thead><tbody></tbody></table>
  </div>
</div>

<script>
let currentJob = null, timer = null;
const $ = id => document.getElementById(id);
const STAGE_KO = {script:'대본 생성', tts:'목소리 합성(TTS)', background:'배경 준비',
                  timeline:'타임라인 계산', render:'영상 렌더링', draft:'캡컷 draft 조립',
                  review:'대본 검토 대기', done:'완료'};

document.querySelectorAll('input[name=prov]').forEach(r => r.onchange = () => {
  const isGemini = pick('prov') === 'gemini';
  $('keyRow').classList.toggle('hidden', !isGemini || window._hasGeminiKey);
  $('geminiOpts').classList.toggle('hidden', !isGemini);
});
$('draftChk').onchange = () => $('draftRow').classList.toggle('hidden', !$('draftChk').checked);

function pick(name){ return document.querySelector(`input[name=${name}]:checked`).value; }

async function generate(){
  const prov = pick('prov');
  const body = {
    topic: $('topic').value, auto: pick('mode') === 'auto',
    script_provider: prov === 'gemini' ? 'gemini' : 'stub',  // 진짜 대본은 Gemini만
    tts_provider: prov,
    voice: prov === 'gemini' ? $('voiceSel').value : '',
    tts_style: prov === 'gemini' ? $('styleSel').value : '',
    bgm: $('bgmSel').value,
    gemini_key: $('geminiKey').value,
    draft: $('draftChk').checked, drafts_dir: $('draftsDir').value,
  };
  const res = await fetch('/api/generate', {method:'POST', body: JSON.stringify(body)});
  const data = await res.json();
  if(data.error){ alert(data.error); return; }
  currentJob = data.job_id;
  $('goBtn').disabled = true;
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

function showErrors(errs){
  const raw = (errs||[]).filter(e => e.startsWith('[원본 오류]'));
  const main = (errs||[]).filter(e => !e.startsWith('[원본 오류]'));
  if(main.length){ $('errBox').classList.remove('hidden'); $('errBox').textContent = main.join('\\n'); }
  $('rawErr').classList.toggle('hidden', raw.length === 0);
  $('rawErrText').textContent = raw.join('\\n');
}

async function confirmScript(){
  await fetch('/api/confirm', {method:'POST', body: JSON.stringify({
    job_id: currentJob, title: $('rvTitle').value,
    sentences: $('rvSentences').value.split('\\n'),
  })});
  $('reviewBox').classList.add('hidden');
  timer = timer || setInterval(poll, 900);
}

async function poll(){
  const state = await (await fetch('/api/state')).json();
  window._hasGeminiKey = state.keys.gemini;
  if(!$('draftsDir').value && state.drafts_dir) $('draftsDir').value = state.drafts_dir;

  if((state.platform || '').startsWith('win')){
    $('provWinLabel').classList.remove('hidden');
    if(!window._defaultSet){ window._defaultSet = true; $('provWin').checked = true; }
  }
  if(!window._optsFilled){
    window._optsFilled = true;
    for(const v of state.voices || []) $('voiceSel').add(new Option(v, v));
    for(const s of state.styles || []) $('styleSel').add(new Option(s, s));
    if((state.bgm_files || []).length){
      $('bgmSel').add(new Option('랜덤', 'random'));
      for(const f of state.bgm_files) $('bgmSel').add(new Option(f, f));
    }
  }
  const env = state.env || {};
  const problems = [];
  if(env.ffmpeg === false) problems.push('⚠ FFmpeg가 없습니다 — windows 폴더의 1_설치.bat 을 먼저 실행한 뒤 이 화면을 새로고침하세요.');
  if(env.font === false) problems.push('⚠ 자막 폰트가 없습니다 — zip을 다시 풀어주세요 (resources/fonts 폴더).');
  $('envBanner').classList.toggle('hidden', problems.length === 0);
  $('envBanner').textContent = problems.join('  ');

  renderHistory(state.history);
  if(!currentJob) return;
  const job = state.jobs.find(j => j.id === currentJob);
  if(!job) return;

  $('statusTitle').textContent = job.title || job.id;
  const frac = job.frac || 0;
  $('barFill').style.width = (job.status==='ok'||job.status==='partial' ? 100 : Math.round(frac*100)) + '%';
  $('stageText').textContent = (STAGE_KO[job.stage] || job.stage || '') +
      (job.status==='running' && job.stage!=='review' ? ` — ${Math.round(frac*100)}%` : '');
  $('noteText').textContent = job.status === 'running' ? (job.note || '') : '';

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
  const provKo = {gemini:'Gemini', openai:'OpenAI', windows:'Windows 내장 음성', stub:'테스트 톤'};
  if(job.status === 'ok' || job.status === 'partial'){
    clearInterval(timer); timer = null;
    $('stageText').innerHTML = job.status === 'ok'
      ? '<span class="ok-badge">✔ 완료 — 자가검증 통과</span>'
      : '<span class="fail-badge">부분 완료</span>';
    let badge = job.tts_provider ? '목소리: ' + (provKo[job.tts_provider] || job.tts_provider) : '';
    if(job.requested_tts && job.tts_provider && job.requested_tts !== job.tts_provider)
      badge = '⚠ ' + (provKo[job.tts_provider] || job.tts_provider) + '로 대체 생성됨 (원래 선택: ' + (provKo[job.requested_tts] || job.requested_tts) + ')';
    $('providerBadge').textContent = badge;
    if(job.mp4){
      $('doneBox').classList.remove('hidden');
      $('player').src = '/video/' + job.id + '?t=' + Date.now() + '#t=0.1';
      $('outPaths').textContent = 'mp4: ' + job.mp4 + (job.draft ? '  |  draft: ' + job.draft : '');
    }
    showErrors(job.errors);
    $('goBtn').disabled = false;
  }
  if(job.status === 'failed'){
    clearInterval(timer); timer = null;
    $('stageText').innerHTML = '<span class="fail-badge">✘ 실패</span>';
    if(!(job.errors || []).length) $('errBox').textContent = '알 수 없는 오류';
    showErrors(job.errors);
    $('errBox').classList.remove('hidden');
    $('goBtn').disabled = false;
  }
}

function renderHistory(rows){
  const tb = $('histTable').querySelector('tbody');
  tb.innerHTML = '';
  for(const r of rows || []){
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${(r.created_at||'').replace('T',' ').slice(5,16)}</td>
      <td>${r.title||r.id}</td><td>${r.mode==='auto'?'자동':'검토'}</td>
      <td>${r.status==='ok'?'<span class="ok-badge">완료</span>':r.status}</td>
      <td>${r.has_mp4?`<button class="ghost" onclick="playHist('${r.id}')">▶ 재생</button>`:''}</td>`;
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
  $('statusCard').classList.add('hidden');
  $('reviewBox').classList.add('hidden');
  $('rvTitle').value = ''; $('rvSentences').value = '';
  $('noteText').textContent = ''; $('providerBadge').textContent = '';
  $('errBox').classList.add('hidden'); $('rawErr').classList.add('hidden');
  $('goBtn').disabled = false;
}

poll(); setInterval(()=>{ if(!currentJob) poll(); }, 5000);
</script>
</body>
</html>
"""
