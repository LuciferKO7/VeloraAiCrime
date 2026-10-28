#!/usr/bin/env python3
"""
Initialize the Velora SQLite database idempotently.
Executes contracts/schema.sql followed by contracts/migrations/*.sql in order.
Tracks applied files in an internal _migrations table.
"""
import argparse
import pathlib
import sqlite3
import sys
from datetime import UTC, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent


def get_db_file_path(db_url: str = None) -> pathlib.Path:
    if db_url and db_url.startswith("sqlite:///"):
        p = db_url.replace("sqlite:///", "")
        return pathlib.Path(p).resolve()
    return (ROOT / "backend" / "data" / "velora.db").resolve()


def init_db(db_path: pathlib.Path = None) -> bool:
    target_path = db_path or get_db_file_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA journal_mode = WAL;")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    cursor.execute("SELECT name FROM _migrations")
    applied = {row[0] for row in cursor.fetchall()}

    schema_file = ROOT / "contracts" / "schema.sql"
    if "schema.sql" not in applied:
        if schema_file.exists():
            sql = schema_file.read_text(encoding="utf-8")
            cursor.executescript(sql)
            now_iso = datetime.now(UTC).isoformat()
            cursor.execute("INSERT INTO _migrations (name, applied_at) VALUES (?, ?)", ("schema.sql", now_iso))
            conn.commit()
            print(f"Applied baseline: {schema_file.name}")
        else:
            print(f"Error: {schema_file} not found", file=sys.stderr)
            conn.close()
            return False
    else:
        print("Baseline schema.sql already applied.")

    migrations_dir = ROOT / "contracts" / "migrations"
    if migrations_dir.exists():
        migration_files = sorted(migrations_dir.glob("*.sql"))
        for mfile in migration_files:
            if mfile.name not in applied:
                sql = mfile.read_text(encoding="utf-8")
                cursor.executescript(sql)
                now_iso = datetime.now(UTC).isoformat()
                cursor.execute("INSERT INTO _migrations (name, applied_at) VALUES (?, ?)", (mfile.name, now_iso))
                conn.commit()
                print(f"Applied migration: {mfile.name}")

    conn.close()
    return True


def main():
    parser = argparse.ArgumentParser(description="Initialize Velora database")
    parser.add_argument("--db-path", type=str, help="Custom SQLite db file path", default=None)
    args = parser.parse_args()

    db_path = pathlib.Path(args.db_path).resolve() if args.db_path else None
    success = init_db(db_path)
    if not success:
        sys.exit(1)
    print("Database initialization complete.")


if __name__ == "__main__":
    main()
