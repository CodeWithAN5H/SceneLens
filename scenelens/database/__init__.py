"""SQLite-backed scan history."""

from __future__ import annotations

from .db import HistoryStore, ScanRecord

__all__ = ["HistoryStore", "ScanRecord"]
