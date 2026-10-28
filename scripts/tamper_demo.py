#!/usr/bin/env python3
"""
VELORA tamper demonstration script.
Demonstrates tamper-detection in the hash-chained append-only audit log.
Supports:
  --apply: Backs up the database, drops the append-only trigger, mutates one record, and recreates the trigger.
  --restore: Restores the database from backup and verifies the audit chain integrity.
"""

import argparse
import pathlib
import shutil
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402

from backend.app.audit.chain import verify_audit_chain  # noqa: E402


def apply_tamper(db_path: pathlib.Path, backup_path: pathlib.Path) -> bool:
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}", file=sys.stderr)
        return False

    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Use SQLite checkpoint and backup to ensure WAL pages are flushed cleanly
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        if not backup_path.exists():
            bck = sqlite3.connect(str(backup_path), timeout=30.0)
            conn.backup(bck)
            bck.close()
            print(f"Created untouched backup at {backup_path}")
        else:
            print(f"Preserving existing backup at {backup_path}")

        cur = conn.cursor()
        cur.execute("SELECT seq, details_json FROM audit_log ORDER BY seq DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("Error: audit_log table has no records to tamper with.", file=sys.stderr)
            return False

        target_seq = row[0]

        # 1. Temporarily drop the append-only trigger
        cur.execute("DROP TRIGGER IF EXISTS audit_no_update;")

        # 2. Mutate the details_json payload of the target record
        mutated_details = '{"tampered":true,"reason":"tamper_demonstration"}'
        cur.execute(
            "UPDATE audit_log SET details_json = ? WHERE seq = ?",
            (mutated_details, target_seq),
        )

        # 3. Recreate the append-only trigger
        cur.execute(
            """
            CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT
            RAISE(ABORT,'audit_log is append-only'); END;
            """
        )
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        print(f"Tamper applied successfully: mutated audit_log seq={target_seq}")
        return True
    except Exception as e:
        print(f"Error applying tamper: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


def restore_backup(db_path: pathlib.Path, backup_path: pathlib.Path) -> bool:
    if not backup_path.exists():
        print(f"Error: Backup file not found at {backup_path}", file=sys.stderr)
        return False

    # Connect to both and restore using SQLite backup API to ensure clean WAL handling
    dest_conn = sqlite3.connect(str(db_path), timeout=30.0)
    bck_conn = sqlite3.connect(str(backup_path), timeout=30.0)
    try:
        bck_conn.backup(dest_conn)
        dest_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        bck_conn.close()
        dest_conn.close()

    # Also clean up any lingering wal / shm files from the mutated session
    wal_file = pathlib.Path(str(db_path) + "-wal")
    shm_file = pathlib.Path(str(db_path) + "-shm")
    if wal_file.exists():
        try:
            wal_file.unlink()
        except Exception:
            pass
    if shm_file.exists():
        try:
            shm_file.unlink()
        except Exception:
            pass

    # Ensure file on disk matches backup
    shutil.copy2(backup_path, db_path)
    print(f"Restored database from {backup_path} to {db_path}")

    # Verify audit chain integrity of the restored database
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"timeout": 30})
    try:
        result = verify_audit_chain(engine)
        if result["valid"]:
            print(f"Audit chain verification PASSED (checked {result['checked']} entries, head={result['head_hash']})")
            return True
        else:
            print(f"Audit chain verification FAILED on restored DB: first_bad_seq={result['first_bad_seq']}", file=sys.stderr)
            return False
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="VELORA audit chain tamper demonstration")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Apply mutation to one audit row")
    group.add_argument("--restore", action="store_true", help="Restore database from backup")

    parser.add_argument(
        "--db-path",
        type=str,
        default=str(ROOT / "backend/data/velora.db"),
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--backup-path",
        type=str,
        default=None,
        help="Path to backup database file (default: backend/data/velora.bak.db)",
    )

    args = parser.parse_args()
    db_path = pathlib.Path(args.db_path).resolve()

    if args.backup_path:
        backup_path = pathlib.Path(args.backup_path).resolve()
    else:
        backup_path = ROOT / "backend/data/velora.bak.db"

    if args.apply:
        success = apply_tamper(db_path, backup_path)
    else:
        success = restore_backup(db_path, backup_path)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
