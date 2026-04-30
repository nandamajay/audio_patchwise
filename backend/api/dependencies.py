from __future__ import annotations

import os

from knowledge.sqlite_store import SQLiteStore
from session.session_manager import SessionManager
from submission.submission_engine import SubmissionEngine


sqlite_store = SQLiteStore(db_path=os.getenv("SQLITE_DB_PATH", "./data/sqlite/patchwise.db"))
session_manager = SessionManager(sqlite_store)
engine = SubmissionEngine(dict(os.environ), session_manager)
