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
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

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
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO jobs (id, created_at, title, mode, outputs, status,
                              duration_us, spec_json, out_mp4, out_draft, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, mode=excluded.mode, outputs=excluded.outputs,
                status=excluded.status, duration_us=excluded.duration_us,
                spec_json=COALESCE(excluded.spec_json, jobs.spec_json),
                out_mp4=COALESCE(excluded.out_mp4, jobs.out_mp4),
                out_draft=COALESCE(excluded.out_draft, jobs.out_draft),
                error=excluded.error
            """,
            (
                job_id,
                _dt.datetime.now().isoformat(timespec="seconds"),
                title, mode, outputs, status, duration_us,
                spec_json, out_mp4, out_draft, error,
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
