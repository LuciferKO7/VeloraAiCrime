import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import require_role
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_EVAL_KINDS = {
    "parser",
    "verifier",
    "lexicon",
    "convergence",
    "bias_audit",
    "end_to_end",
}


class CreateEvalRunRequest(BaseModel):
    kind: str = Field(..., description="Evaluation kind: parser, verifier, lexicon, convergence, bias_audit, end_to_end")
    config: dict[str, Any] | None = Field(default=None, description="Optional evaluation configuration dictionary")
    metrics: dict[str, Any] = Field(..., description="Evaluation outcome metrics dictionary (precision, recall, f1, etc.)")


# ==============================================================================
# Model Registry Routes (§7, §12 Step B10)
# ==============================================================================
@router.get("/models")
def list_models(
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    """
    List registered AI models and versions in the model registry (§7, §9, §12 Step B10).
    Requires admin or supervisor role.
    """
    rows = conn.execute(
        text(
            """
            SELECT id, name, role, version, source, license, checksum,
                   metrics_json, is_active, registered_at
            FROM model_registry
            ORDER BY registered_at DESC
            """
        )
    ).mappings().fetchall()

    results = []
    for r in rows:
        item = dict(r)
        try:
            item["metrics"] = json.loads(item["metrics_json"])
        except Exception:
            item["metrics"] = {}
        item["is_active"] = bool(item["is_active"])
        results.append(item)
    return results


@router.post("/models/{model_id}/activate", status_code=status.HTTP_200_OK)
def activate_model(
    model_id: str,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin")),
):
    """
    Exclusively activates a model for its role (§8.0, §12 Step B12).
    Requires admin role. Deactivates other models for the same role and audits the action.
    """
    from backend.app.services.registry_sync import activate_model_exclusive

    return activate_model_exclusive(conn, model_id, current_user)


# ==============================================================================
# Eval Runs Routes (§7, §12 Step B10)
# ==============================================================================
@router.post("/eval-runs", status_code=status.HTTP_201_CREATED)
def create_eval_run(
    payload: CreateEvalRunRequest,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin")),
):
    """
    Record an evaluation run with metrics and config (§7, §12 Step B10).
    Requires admin role.
    """
    kind = payload.kind.strip().lower()
    if kind not in VALID_EVAL_KINDS:
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid evaluation kind '{payload.kind}'. Must be one of {sorted(VALID_EVAL_KINDS)}",
            details={"allowed_kinds": sorted(VALID_EVAL_KINDS)},
            status_code=422,
        )

    if not isinstance(payload.metrics, dict):
        raise AppError(
            "VALIDATION_ERROR",
            "Field 'metrics' must be a valid dictionary of evaluation metrics.",
            status_code=422,
        )

    run_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    config_dict = payload.config or {}
    config_json = json.dumps(config_dict, sort_keys=True, separators=(",", ":"))
    metrics_json = json.dumps(payload.metrics, sort_keys=True, separators=(",", ":"))

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO eval_runs (
                    id, kind, config_json, metrics_json, created_by, created_at
                )
                VALUES (:id, :kind, :config_json, :metrics_json, :created_by, :created_at)
                """
            ),
            {
                "id": run_id,
                "kind": kind,
                "config_json": config_json,
                "metrics_json": metrics_json,
                "created_by": current_user["id"],
                "created_at": now_iso,
            },
        )
        write_audit_entry(
            conn,
            action="admin.eval_run",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="eval_run",
            resource_id=run_id,
            details={
                "kind": kind,
                "config": config_dict,
                "metrics_summary": {k: payload.metrics[k] for k in list(payload.metrics.keys())[:5]},
            },
        )

    return {
        "id": run_id,
        "kind": kind,
        "config": config_dict,
        "config_json": config_json,
        "metrics": payload.metrics,
        "metrics_json": metrics_json,
        "created_by": current_user["id"],
        "created_at": now_iso,
    }


@router.get("/eval-runs")
def list_eval_runs(
    kind: str | None = Query(None, description="Optional filter by eval run kind"),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin", "supervisor", "auditor")),
):
    """
    List evaluation runs, optionally filtered by kind (§7, §12 Step B10).
    Accessible to admin, supervisor, and auditor.
    """
    if kind is not None:
        kind_clean = kind.strip().lower()
        if kind_clean not in VALID_EVAL_KINDS:
            raise AppError(
                "VALIDATION_ERROR",
                f"Invalid evaluation kind '{kind}'. Must be one of {sorted(VALID_EVAL_KINDS)}",
                status_code=422,
            )
        rows = conn.execute(
            text(
                """
                SELECT id, kind, config_json, metrics_json, created_by, created_at
                FROM eval_runs
                WHERE kind = :kind
                ORDER BY created_at DESC
                """
            ),
            {"kind": kind_clean},
        ).mappings().fetchall()
    else:
        rows = conn.execute(
            text(
                """
                SELECT id, kind, config_json, metrics_json, created_by, created_at
                FROM eval_runs
                ORDER BY created_at DESC
                """
            )
        ).mappings().fetchall()

    results = []
    for r in rows:
        item = dict(r)
        try:
            item["config"] = json.loads(item["config_json"])
        except Exception:
            item["config"] = {}
        try:
            item["metrics"] = json.loads(item["metrics_json"])
        except Exception:
            item["metrics"] = {}
        results.append(item)
    return results


@router.get("/eval-runs/{run_id}")
def get_eval_run(
    run_id: str,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin", "supervisor", "auditor")),
):
    """
    Retrieve single evaluation run by ID with detailed metrics and configuration (§7, §12 Step B10).
    """
    row = conn.execute(
        text(
            """
            SELECT id, kind, config_json, metrics_json, created_by, created_at
            FROM eval_runs
            WHERE id = :id
            """
        ),
        {"id": run_id},
    ).mappings().fetchone()

    if not row:
        raise AppError("NOT_FOUND", f"Evaluation run '{run_id}' not found", status_code=404)

    item = dict(row)
    try:
        item["config"] = json.loads(item["config_json"])
    except Exception:
        item["config"] = {}
    try:
        item["metrics"] = json.loads(item["metrics_json"])
    except Exception:
        item["metrics"] = {}
    return item
