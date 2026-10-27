"""Persistent local scan history.

One table is enough here: every scan stores the normalized result JSON plus a
few denormalized columns used by the history list.  Connections are opened per
operation so the GUI thread and the scanning worker can use the store freely.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..config import DB_PATH
from ..models import MediaResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    media_type   TEXT NOT NULL,
    title        TEXT NOT NULL,
    year         INTEGER,
    studio       TEXT,
    confidence   REAL NOT NULL DEFAULT 0,
    thumbnail_path TEXT,
    source_path  TEXT,
    image_hash   TEXT,
    result_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scans_created ON scans (created_at DESC);
"""


@dataclass
class ScanRecord:
    id: int
    created_at: str
    media_type: str
    title: str
    confidence: float
    thumbnail_path: str | None
    source_path: str | None
    result: MediaResult

    @property
    def created_local(self) -> datetime:
        try:
            return datetime.fromisoformat(self.created_at).astimezone()
        except ValueError:
            return datetime.now()


class HistoryStore:
    """Thin, thread-safe-by-connection wrapper around the local database."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    # ---- plumbing --------------------------------------------------------

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(_SCHEMA)
            connection.execute("PRAGMA journal_mode=WAL")

    # ---- writes ----------------------------------------------------------

    def add(
        self,
        result: MediaResult,
        thumbnail_path: str | None = None,
        source_path: str | None = None,
        image_hash: str | None = None,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scans (created_at, media_type, title, year, studio,
                                   confidence, thumbnail_path, source_path,
                                   image_hash, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    result.media_type,
                    result.title,
                    result.year,
                    result.studio,
                    result.confidence,
                    thumbnail_path,
                    source_path,
                    image_hash,
                    json.dumps(result.to_dict(), ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid or 0)

    def delete(self, scan_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM scans WHERE id = ?", (scan_id,))

    def clear(self) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM scans")

    # ---- reads -----------------------------------------------------------

    def recent(self, limit: int = 50) -> list[ScanRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM scans ORDER BY id DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        records: list[ScanRecord] = []
        for row in rows:
            record = self._to_record(row)
            if record is not None:
                records.append(record)
        return records

    def get(self, scan_id: int) -> ScanRecord | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return self._to_record(row) if row is not None else None

    def count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM scans").fetchone()
        return int(row["total"]) if row else 0

    @staticmethod
    def _to_record(row: sqlite3.Row) -> ScanRecord | None:
        try:
            payload = json.loads(row["result_json"])
            result = MediaResult.from_dict(payload)
        except (ValueError, TypeError, json.JSONDecodeError):
            # A single corrupt row should never take down the history list.
            return None
        return ScanRecord(
            id=int(row["id"]),
            created_at=str(row["created_at"]),
            media_type=str(row["media_type"]),
            title=str(row["title"]),
            confidence=float(row["confidence"] or 0),
            thumbnail_path=row["thumbnail_path"],
            source_path=row["source_path"],
            result=result,
        )
