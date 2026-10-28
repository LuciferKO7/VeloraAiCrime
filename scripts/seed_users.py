#!/usr/bin/env python3
"""
Seed initial users for each role (admin, supervisor, investigator, artist, auditor).
Uses passwords from SEED_PASSWORD_* environment variables.
Refuses to run (exits non-zero) if any SEED_PASSWORD_* is empty.
Passwords stored as Argon2 hashes.
"""
import argparse
import os
import pathlib
import sqlite3
import sys
import uuid
from datetime import UTC, datetime

from argon2 import PasswordHasher

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Load .env if present
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, rest = line.partition("=")
            k = k.strip()
            v = rest.split("#", 1)[0].strip()
            if k and k not in os.environ:
                os.environ[k] = v

ROLES = ["admin", "supervisor", "investigator", "artist", "auditor"]


def get_db_file_path(db_url: str = None) -> pathlib.Path:
    if db_url and db_url.startswith("sqlite:///"):
        p = db_url.replace("sqlite:///", "")
        return pathlib.Path(p).resolve()
    return (ROOT / "backend" / "data" / "velora.db").resolve()


def seed_users(db_path: pathlib.Path = None) -> bool:
    passwords = {}
    missing = []
    for role in ROLES:
        env_key = f"SEED_PASSWORD_{role.upper()}"
        pwd = os.getenv(env_key, "").strip()
        if not pwd:
            missing.append(env_key)
        passwords[role] = pwd

    if missing:
        print(f"Error: Refusing to run because seed passwords are missing or empty: {', '.join(missing)}", file=sys.stderr)
        return False

    ph = PasswordHasher()
    target_path = db_path or get_db_file_path()
    if not target_path.exists():
        print(f"Error: Database {target_path} does not exist. Run init_db.py first.", file=sys.stderr)
        return False

    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    now_iso = datetime.now(UTC).isoformat()

    for role in ROLES:
        username = role
        full_name = f"Default {role.capitalize()}"
        pwd = passwords[role]
        pwd_hash = ph.hash(pwd)

        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, is_active = 1, failed_logins = 0, locked_until = NULL
                WHERE username = ?
                """,
                (pwd_hash, username)
            )
            print(f"Updated user: {username}")
        else:
            user_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO users (id, username, full_name, role, password_hash, is_active, failed_logins, locked_until, created_at)
                VALUES (?, ?, ?, ?, ?, 1, 0, NULL, ?)
                """,
                (user_id, username, full_name, role, pwd_hash, now_iso)
            )
            print(f"Created user: {username}")

    conn.commit()
    conn.close()
    return True


def main():
    parser = argparse.ArgumentParser(description="Seed initial users")
    parser.add_argument("--db-path", type=str, help="Custom SQLite db file path", default=None)
    args = parser.parse_args()

    db_path = pathlib.Path(args.db_path).resolve() if args.db_path else None
    if not seed_users(db_path):
        sys.exit(1)
    print("User seeding complete.")


if __name__ == "__main__":
    main()
