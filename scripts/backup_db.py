#!/usr/bin/env python3
"""
Database Backup Script (§12 Step B12).

Performs a safe, online SQLite backup using sqlite3.Connection.backup()
without locking or tearing the live WAL database.

Usage:
    python scripts/backup_db.py [--output PATH] [--db-path PATH]
"""

import argparse
import logging
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("velora.backup")


def get_default_source_path() -> Path:
    """Resolve default SQLite source path from settings or backend storage."""
    try:
        from backend.app.core.config import settings

        url = settings.DATABASE_URL
        if url.startswith("sqlite:///"):
            clean_path = url[len("sqlite:///") :]
            return Path(clean_path).resolve()
    except Exception:
        pass

    # Fallback to local default locations
    local_data = Path("backend/data/velora.db").resolve()
    if local_data.exists():
        return local_data
    local_storage = Path("backend/storage/velora.db").resolve()
    return local_storage


def backup_database(src_path: Path | str, dst_path: Path | str) -> Path:
    """
    Performs online SQLite backup from src_path to dst_path using SQLite backup API.

    Raises FileNotFoundError if src_path does not exist.
    Raises ValueError if dst_path resolves to the same file as src_path.
    """
    src = Path(src_path).resolve()
    dst = Path(dst_path).resolve()

    if not src.exists():
        raise FileNotFoundError(f"Source database file '{src}' does not exist.")

    if src == dst:
        raise ValueError(f"Cannot overwrite source database with backup ('{src}' == '{dst}').")

    # Ensure destination directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Starting safe online backup: %s -> %s", src, dst)
    start_time = datetime.now(UTC)

    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))

    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100, progress=None)
    finally:
        dst_conn.close()
        src_conn.close()

    elapsed = (datetime.now(UTC) - start_time).total_seconds()
    size_bytes = dst.stat().st_size
    logger.info(
        "Backup completed successfully in %.2fs: %s (%d bytes)",
        elapsed,
        dst,
        size_bytes,
    )
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description="VELORA Safe Online SQLite Database Backup")
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to source SQLite database file (defaults to configured DATABASE_URL)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to output backup file (defaults to backend/storage/backups/velora_backup_<timestamp>.db)",
    )

    args = parser.parse_args()

    # Determine source path
    if args.db_path:
        src = Path(args.db_path).resolve()
    else:
        src = get_default_source_path()

    # Determine destination path
    if args.output:
        dst = Path(args.output).resolve()
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_dir = Path("backend/storage/backups").resolve()
        dst = backup_dir / f"velora_backup_{timestamp}.db"

    try:
        backup_database(src, dst)
        return 0
    except Exception as exc:
        logger.error("Database backup failed: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
