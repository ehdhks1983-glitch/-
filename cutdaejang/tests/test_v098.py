"""v0.98 — 🎞 구간 카드 다듬기(템포 설명·BGM 미리듣기·훅 AI) + 히스토리 동시 완료."""

import json
import threading
import urllib.request

from cutdaejang.gui import webui


def test_v098_sections_card_ui():
    html = webui._HTML
    for tok in (
        # 압축 템포 — 뭘 하는 기능인지 설명 (툴팁 + 명확한 옵션 라벨)
        "압축 템포 ⓘ", "한 장면 3.5초", "핵심 장면만 골라 압축",
        # BGM 미리듣기 — 구간·블로그·쇼핑 카드에서도
        "previewBgm(event,'secBgmSel'", "previewBgm(event,'wlBgmSel'",
        "previewBgm(event,'shopBgmSel'",
        # 훅 AI 추천 + 비우면 자동
        "function suggestSecHooks", 'id="secHookCands"', "비우면 AI가 대본을 보고",
    ):
        assert tok in html, tok


def test_sections_auto_hook_wiring():
    src = open(webui.__file__, encoding="utf-8").read()
    assert 'hook_txt in ("없음"' in src            # '없음' 입력 → 훅 없이
    assert "suggest_hooks(ctx)" in src             # 비우면 대본 기반 AI 자동
    assert "훅 제목을 AI가 지었어요" in src        # 완료 화면에 알려줌
    # 확정된 훅이 재사용 지문·렌더·재편집 모두에 쓰인다
    assert 'params["hook"] = hook_txt' in src


def test_history_shows_finished_jobs_immediately(tmp_path):
    """동시 2개가 끝나도 히스토리에 바로 보인다 — 완료 작업은 제외 목록에서 빠짐."""
    src = open(webui.__file__, encoding="utf-8").read()
    assert '"queued", "running", "awaiting_review"' in src   # 진행 중만 제외
    # 서버로 실검증: 완료 상태 메모리 잡 + 스토어 기록 → history에 나타남
    from cutdaejang.db.jobs import JobStore

    store = JobStore(tmp_path / "history.db")
    store.upsert("j-done-1", title="완료작업", mode="edit", status="ok",
                 out_mp4="", spec_json="", tts_provider="")
    store.close()
    webui._set_job("j-done-1", status="ok", title="완료작업")
    try:
        httpd = webui.create_server(str(tmp_path), port=0)
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/state", timeout=30) as r:
            st = json.loads(r.read())
        httpd.shutdown()
        assert any(h["id"] == "j-done-1" for h in st["history"]), \
            [h["id"] for h in st["history"]][:5]
    finally:
        with webui._LOCK:
            webui._JOBS.pop("j-done-1", None)


def test_jobstore_concurrent_writes_survive(tmp_path):
    """WAL+timeout — 동시 완료 2건이 같이 기록돼도 유실되지 않는다."""
    from cutdaejang.db.jobs import JobStore

    errs = []

    def worker(i):
        try:
            s = JobStore(tmp_path / "history.db")
            for k in range(20):
                s.upsert(f"job-{i}-{k}", title=f"t{i}-{k}", mode="edit",
                         status="ok", out_mp4="", spec_json="", tts_provider="")
            s.close()
        except Exception as e:  # noqa: BLE001
            errs.append(e)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert not errs, errs
    s = JobStore(tmp_path / "history.db")
    assert len(s.list(limit=100)) == 80          # 4×20 전부 기록
    s.close()


def test_done_chips_in_jobsbar():
    html = webui._HTML
    assert "'ok', 'partial', 'failed'" in html    # ✅ 완료 칩 필터
    assert "'✅'" in html
