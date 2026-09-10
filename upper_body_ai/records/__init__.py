"""
Patient records for Therayu.

A self-contained layer that sits DOWNSTREAM of the clinical engine. It reads the
angles and telemetry the engine already produces and stores them against a
patient, a condition and a day. It imports nothing from `metrics`, `inference`
or `src`, so it cannot change what the engine measures.
"""

from .db import Database, get_db, reset_db_singleton, utc_now, DEFAULT_DB_PATH
from .repository import Repository
from .session_recorder import SessionRecorder
from .seed import seed, load_seed_file

__all__ = [
    "Database", "get_db", "reset_db_singleton", "utc_now", "DEFAULT_DB_PATH",
    "Repository", "SessionRecorder", "seed", "load_seed_file",
]
