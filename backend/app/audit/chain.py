import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from backend.app.db.session import get_engine

AUDIT_ACTIONS: frozenset[str] = frozenset(
    {
        "auth.login",
        "auth.login_failed",
        "auth.logout",
        "access.denied",
        "user.create",
        "user.update",
        "case.create",
        "case.view",
        "case.update",
        "case.access_grant",
        "case.access_revoke",
        "witness.create",
        "session.create",
        "session.view",
        "session.complete",
        "statement.create",
        "speech.transcribe",
        "attributes.update",
        "round.generate",
        "round.evolve",
        "round.edit",
        "round.transform",
        "feedback.create",
        "image.view",
        "session.finalize",
        "export.create",
        "export.download",
        "match.search",
        "scene.extract",
        "scene.update",
        "scene.view",
        "consensus.view",
        "audit.view",
        "audit.verify",
        "audit.export",
        "glossary.review",
        "admin.model_activate",
        "admin.eval_run",
        "gallery.add",
    }
)

GENESIS_PREV_HASH: str = "0" * 64


def get_iso_timestamp() -> str:
    now = datetime.now(UTC)
    # §5: YYYY-MM-DDTHH:MM:SS.sssZ
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def compute_canonical(payload: dict[str, Any]) -> str:
    """
    Exact canonical serialization per Section 5:
    json.dumps({
        ts, user_id, username, role, action, resource_type, resource_id,
        case_id, purpose, ip, status_code, details
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_entry_hash(prev_hash: str, canonical: str) -> str:
    """
    Exact formula per Section 5:
    entry_hash = SHA256_hex( prev_hash + "|" + canonical )
    """
    return hashlib.sha256((prev_hash + "|" + canonical).encode("utf-8")).hexdigest()


def write_audit_entry(
    engine: Engine | None = None,
    *,
    action: str,
    user_id: str | None = None,
    username: str | None = None,
    role: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    case_id: str | None = None,
    purpose: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    status_code: int | None = None,
    details: dict[str, Any] | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """
    Writes one hash-chained audit record.
    Uses SQLite BEGIN IMMEDIATE to serialize audit writes.
    Allocates contiguous sequence numbers and links to the preceding entry's hash.
    """
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"Unknown audit action: '{action}'. Action must be one of {sorted(AUDIT_ACTIONS)}")

    if ts is None:
        ts = get_iso_timestamp()

    if details is None:
        details_dict = {}
    elif isinstance(details, str):
        details_dict = json.loads(details)
    else:
        details_dict = details

    details_json = json.dumps(details_dict, separators=(",", ":"), ensure_ascii=False)

    canonical_dict = {
        "action": action,
        "case_id": case_id,
        "details": details_dict,
        "ip": ip,
        "purpose": purpose,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "role": role,
        "status_code": status_code,
        "ts": ts,
        "user_id": user_id,
        "username": username,
    }
    canonical = compute_canonical(canonical_dict)

    def _insert_entry(c: Connection) -> dict[str, Any]:
        row = c.execute(
            text("SELECT seq, entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1")
        ).fetchone()

        if row is None:
            seq = 1
            prev_hash = GENESIS_PREV_HASH
        else:
            seq = row[0] + 1
            prev_hash = row[1]

        entry_hash = compute_entry_hash(prev_hash, canonical)

        c.execute(
            text(
                """
                INSERT INTO audit_log (
                    seq, ts, user_id, username, role, action,
                    resource_type, resource_id, case_id, purpose,
                    ip, user_agent, status_code, details_json,
                    prev_hash, entry_hash
                ) VALUES (
                    :seq, :ts, :user_id, :username, :role, :action,
                    :resource_type, :resource_id, :case_id, :purpose,
                    :ip, :user_agent, :status_code, :details_json,
                    :prev_hash, :entry_hash
                )
                """
            ),
            {
                "seq": seq,
                "ts": ts,
                "user_id": user_id,
                "username": username,
                "role": role,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "case_id": case_id,
                "purpose": purpose,
                "ip": ip,
                "user_agent": user_agent,
                "status_code": status_code,
                "details_json": details_json,
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            },
        )
        return {
            "seq": seq,
            "ts": ts,
            "user_id": user_id,
            "username": username,
            "role": role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "case_id": case_id,
            "purpose": purpose,
            "ip": ip,
            "user_agent": user_agent,
            "status_code": status_code,
            "details": details_dict,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
        }

    if isinstance(engine, Connection):
        res = _insert_entry(engine)
        if not engine.info.get("in_atomic_mutation"):
            # Standalone write on connection (e.g. read view or access.denied) -> commit immediately
            engine.commit()
        return res
    else:
        # engine is an Engine or None (e.g. parallel worker threads, error handlers)
        target_engine = engine or get_engine()
        with target_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("BEGIN IMMEDIATE"))
            try:
                res = _insert_entry(conn)
                conn.execute(text("COMMIT"))
                return res
            except Exception:
                conn.execute(text("ROLLBACK"))
                raise


def verify_audit_chain(engine: Engine | None = None) -> dict[str, Any]:
    """
    Verifies the entire audit chain from genesis to the current head.
    Recomputes hashes from canonical stored fields.
    Verifies sequence continuity, genesis hash, each prev_hash, and each entry_hash.
    Returns: {"valid": bool, "checked": int, "first_bad_seq": int | None, "head_hash": str | None}
    """
    if hasattr(engine, "engine"):
        target_engine = engine.engine
    else:
        target_engine = engine or get_engine()

    with target_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT seq, ts, user_id, username, role, action,
                       resource_type, resource_id, case_id, purpose,
                       ip, user_agent, status_code, details_json,
                       prev_hash, entry_hash
                FROM audit_log
                ORDER BY seq ASC
                """
            )
        ).mappings().fetchall()

    if not rows:
        return {
            "valid": True,
            "checked": 0,
            "first_bad_seq": None,
            "head_hash": None,
        }

    expected_prev_hash = GENESIS_PREV_HASH
    head_hash = None

    for idx, row in enumerate(rows):
        expected_seq = idx + 1
        current_seq = row["seq"]

        # Check contiguous sequence
        if current_seq != expected_seq:
            return {
                "valid": False,
                "checked": idx,
                "first_bad_seq": current_seq,
                "head_hash": head_hash,
            }

        # Check prev_hash links to prior entry's hash (or genesis)
        if row["prev_hash"] != expected_prev_hash:
            return {
                "valid": False,
                "checked": idx,
                "first_bad_seq": current_seq,
                "head_hash": head_hash,
            }

        # Parse details
        try:
            details_dict = json.loads(row["details_json"])
        except Exception:
            return {
                "valid": False,
                "checked": idx,
                "first_bad_seq": current_seq,
                "head_hash": head_hash,
            }

        canonical_dict = {
            "action": row["action"],
            "case_id": row["case_id"],
            "details": details_dict,
            "ip": row["ip"],
            "purpose": row["purpose"],
            "resource_id": row["resource_id"],
            "resource_type": row["resource_type"],
            "role": row["role"],
            "status_code": row["status_code"],
            "ts": row["ts"],
            "user_id": row["user_id"],
            "username": row["username"],
        }
        canonical = compute_canonical(canonical_dict)
        expected_hash = compute_entry_hash(expected_prev_hash, canonical)

        # Check entry_hash matches recomputed hash
        if row["entry_hash"] != expected_hash:
            return {
                "valid": False,
                "checked": idx,
                "first_bad_seq": current_seq,
                "head_hash": head_hash,
            }

        expected_prev_hash = row["entry_hash"]
        head_hash = row["entry_hash"]

    return {
        "valid": True,
        "checked": len(rows),
        "first_bad_seq": None,
        "head_hash": head_hash,
    }
