"""
REST API for patient records.

Kept as a standalone APIRouter so `ws_server.py` mounts it in two lines and the
realtime frame path is not touched. REST for records, WebSocket for frames: CRUD
wants request/response semantics, and mixing patient administration into the hot
socket loop would put database latency in the way of video.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import get_db
from .repository import Repository

router = APIRouter(prefix="/api", tags=["records"])


def _repo() -> Repository:
    return Repository(get_db())


# ================================================================= schemas ====

class PatientIn(BaseModel):
    full_name: str = Field(..., min_length=1)
    date_of_birth: Optional[str] = None
    sex: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class PatientPatch(BaseModel):
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    sex: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    archived: Optional[int] = None


class AssignIn(BaseModel):
    condition_id: int
    clinician_id: Optional[int] = None
    notes: Optional[str] = None


class SessionIn(BaseModel):
    patient_id: int
    notes: Optional[str] = None


class ReportedIn(BaseModel):
    pain_score: Optional[int] = Field(None, ge=0, le=10)
    exertion_score: Optional[int] = Field(None, ge=0, le=20)
    comment: Optional[str] = None


# ================================================================ patients ====

@router.get("/patients")
def list_patients(search: Optional[str] = None,
                  include_archived: bool = False) -> List[Dict[str, Any]]:
    return _repo().list_patients(search=search, include_archived=include_archived)


@router.post("/patients", status_code=201)
def create_patient(body: PatientIn) -> Dict[str, Any]:
    try:
        return _repo().create_patient(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/patients/{patient_id}")
def get_patient(patient_id: int) -> Dict[str, Any]:
    patient = _repo().get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="patient not found")
    return patient


@router.patch("/patients/{patient_id}")
def update_patient(patient_id: int, body: PatientPatch) -> Dict[str, Any]:
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = _repo().update_patient(patient_id, **fields)
    if not updated:
        raise HTTPException(status_code=404, detail="patient not found")
    return updated


# ============================================================== catalogue ====

@router.get("/conditions")
def list_conditions() -> List[Dict[str, Any]]:
    return _repo().list_conditions()


@router.get("/conditions/{condition_id}/protocol")
def condition_protocol(condition_id: int) -> List[Dict[str, Any]]:
    repo = _repo()
    if not repo.get_condition(condition_id):
        raise HTTPException(status_code=404, detail="condition not found")
    return repo.protocol_for_condition(condition_id)


# ============================================================ assignments ====

@router.post("/patients/{patient_id}/assign", status_code=201)
def assign(patient_id: int, body: AssignIn) -> Dict[str, Any]:
    repo = _repo()
    if not repo.get_patient(patient_id):
        raise HTTPException(status_code=404, detail="patient not found")
    if not repo.get_condition(body.condition_id):
        raise HTTPException(status_code=404, detail="condition not found")
    repo.assign_condition(patient_id, body.condition_id,
                          clinician_id=body.clinician_id, notes=body.notes)
    return repo.todays_plan(patient_id)


@router.get("/patients/{patient_id}/plan")
def todays_plan(patient_id: int) -> Dict[str, Any]:
    try:
        return _repo().todays_plan(patient_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# =============================================================== sessions ====

@router.post("/sessions", status_code=201)
def start_session(body: SessionIn) -> Dict[str, Any]:
    repo = _repo()
    if not repo.get_patient(body.patient_id):
        raise HTTPException(status_code=404, detail="patient not found")
    return repo.start_session(body.patient_id, notes=body.notes)


@router.post("/sessions/{session_id}/end")
def end_session(session_id: int, notes: Optional[str] = None) -> Dict[str, Any]:
    ended = _repo().end_session(session_id, notes=notes)
    if not ended:
        raise HTTPException(status_code=404, detail="session not found")
    return ended


@router.get("/sessions/{session_id}")
def get_session(session_id: int) -> Dict[str, Any]:
    repo = _repo()
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {**session, "results": repo.results_for_session(session_id)}


@router.get("/patients/{patient_id}/sessions")
def list_sessions(patient_id: int) -> List[Dict[str, Any]]:
    return _repo().list_sessions(patient_id)


@router.post("/results/{result_id}/reported")
def save_reported(result_id: int, body: ReportedIn) -> Dict[str, Any]:
    _repo().save_patient_reported(result_id, **body.model_dump())
    return {"ok": True, "result_id": result_id}


# =============================================================== progress ====

@router.get("/patients/{patient_id}/progress")
def progress(patient_id: int) -> Dict[str, Any]:
    try:
        return _repo().progress_summary(patient_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/patients/{patient_id}/report")
def build_report(patient_id: int,
                 output_dir: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Renders the doctor's PDF and returns where it was written."""
    from .report import build_progress_report
    try:
        path = build_progress_report(_repo(), patient_id, output_dir=output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "path": path, "filename": os.path.basename(path)}


# ================================================================= health ====

@router.get("/health")
def health() -> Dict[str, Any]:
    db = get_db()
    return {"ok": True, "database": db.path, "counts": db.table_counts()}
