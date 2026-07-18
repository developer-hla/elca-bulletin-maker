"""Past-runs endpoints for the web adapter."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from bulletin_maker.core import past_runs

router = APIRouter(prefix="/api/runs")


@router.get("")
def list_runs():
    return {"success": True, "runs": past_runs.list_past_runs()}


@router.post("")
def save_run(payload: dict):
    run_id = past_runs.save_past_run(
        payload.get("form_data", {}), payload.get("metadata", {}))
    return {"success": True, "id": run_id}


@router.get("/{run_id}")
def get_run(run_id: str):
    run = past_runs.get_past_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={
            "error": "Run not found.", "error_type": "validation"})
    return {"success": True,
            "form_data": run.get("form_data", {}),
            "metadata": run.get("metadata", {})}


@router.delete("/{run_id}")
def delete_run(run_id: str):
    if not past_runs.delete_past_run(run_id):
        raise HTTPException(status_code=404, detail={
            "error": "Run not found.", "error_type": "validation"})
    return {"success": True}
