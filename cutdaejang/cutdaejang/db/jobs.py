"""작업 히스토리 (SQLite) — GUI 탭③의 백엔드 (기획안 §6).

spec_json을 통째로 저장해 두므로 "재생성" 시 어느 출력(A/B)으로든 재빌드할 수 있다 (§3.2).
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from pathlib import Path
from typing import List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    mode        TEXT NOT NULL DEFAULT 'review',   -- review | auto
    outputs     TEXT NOT NULL DEFAULT 'mp4',      -- 쉼표 구분: mp4,draft
    status      TEXT NOT NULL DEFAULT 'pending',
    duration_us INTEGER NOT NULL DEFAULT 0,
    spec_json   TEXT,
    out_mp4     TEXT,
    out_draft   TEXT,
    error       TEXT
);
"""


class JobStore:
    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # ⏱ timeout + WAL (v0.98) — 동시 작업 2개가 같이 끝나면 쓰기가 잠금 충돌로
        # 조용히 실패해 히스토리에 안 남던 문제 (사용자 리포트 "완료됐는데 안 보여")
        self._conn = sqlite3.connect(str(db_path), timeout=15)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=15000")
        except sqlite3.Error:
            pass                              # 오래된 sqlite여도 기본 잠금으로 동작
        self._conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(jobs)")}
        if "tts_provider" not in cols:  # v0.3: 폴백 추적용 (지시서 1-4)
            self._conn.execute("ALTER TABLE jobs ADD COLUMN tts_provider TEXT")
            self._conn.commit()
        if "params_json" not in cols:  # v0.85: 구간 대본 재편집용 입력값 보존
            self._conn.execute("ALTER TABLE jobs ADD COLUMN params_json TEXT")
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert(
        self,
        job_id: str,
        *,
        title: str = "",
        mode: str = "review",
        outputs: str = "mp4",
        status: str = "pending",
        duration_us: int = 0,
        spec_json: Optional[str] = None,
        out_mp4: Optional[str] = None,
        out_draft: Optional[str] = None,
        error: Optional[str] = None,
        tts_provider: Optional[str] = None,
        params_json: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO jobs (id, created_at, title, mode, outputs, status,
                              duration_us, spec_json, out_mp4, out_draft, error,
                              tts_provider, params_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, mode=excluded.mode, outputs=excluded.outputs,
                status=excluded.status, duration_us=excluded.duration_us,
                spec_json=COALESCE(excluded.spec_json, jobs.spec_json),
                out_mp4=COALESCE(excluded.out_mp4, jobs.out_mp4),
                out_draft=COALESCE(excluded.out_draft, jobs.out_draft),
                error=excluded.error,
                tts_provider=COALESCE(excluded.tts_provider, jobs.tts_provider),
                params_json=COALESCE(excluded.params_json, jobs.params_json)
            """,
            (
                job_id,
                _dt.datetime.now().isoformat(timespec="seconds"),
                title, mode, outputs, status, duration_us,
                spec_json, out_mp4, out_draft, error, tts_provider, params_json,
            ),
        )
        self._conn.commit()

    def get(self, job_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50) -> List[dict]:
        rows = self._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
