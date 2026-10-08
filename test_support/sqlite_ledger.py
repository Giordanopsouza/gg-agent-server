"""One temporary SQLite file per case, shared by every ledger instance."""

from contextlib import contextmanager
from pathlib import Path

from gg.runtime.ledger import TaskLedger
from gg.runtime.sqlite_db import SQLiteDB, initialize


_path: Path | None = None
_databases: list[SQLiteDB] = []


@contextmanager
def isolated_test_ledger(path: Path):
    global _path
    if _path is not None:
        raise RuntimeError("test ledger already configured")
    initialize(path)
    _path = path
    try:
        yield path
    finally:
        clean_test_ledger()


def new_ledger() -> TaskLedger:
    if _path is None:
        raise RuntimeError("use the isolated_test_ledger fixture")
    db = SQLiteDB(_path)
    _databases.append(db)
    return TaskLedger(db)


def clean_test_ledger() -> None:
    global _path
    for db in _databases:
        db.close()
    _databases.clear()
    _path = None
