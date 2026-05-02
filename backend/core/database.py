from __future__ import annotations

# Compatibility wrapper: runtime uses backend/database.py.
# Keep this module so inject checks that target backend/core/database.py can resolve.
from database import DB_PATH, get_db, get_db_connection, get_write_connection, init_db

__all__ = [
    "DB_PATH",
    "get_db",
    "get_db_connection",
    "get_write_connection",
    "init_db",
]
