from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def backup_database(source_path: Path, destination_path: Path) -> None:
    source_uri = f"file:{source_path}?mode=ro"
    with (
        closing(sqlite3.connect(source_uri, uri=True, timeout=20)) as source,
        closing(sqlite3.connect(destination_path, timeout=20)) as destination,
    ):
        source.backup(destination)
        integrity_result = destination.execute("PRAGMA integrity_check").fetchone()
    if integrity_result != ("ok",):
        raise RuntimeError(f"SQLite backup integrity check failed: {integrity_result!r}")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: backup_sqlite.py SOURCE DESTINATION", file=sys.stderr)
        return 2
    backup_database(Path(sys.argv[1]), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
