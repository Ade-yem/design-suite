"""
routers/drawings.py
===================
Drawings router to support the Drafting Agent.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, status
from dependencies import require_design_complete, get_project
from schemas.jobs import JobStatus
from storage.job_store import job_store
from typing import Any

router = APIRouter()

# Stub stores
_drawings_store: dict[str, Any] = {}

class DrawingCommandSet: pass # Stub model if needed

@router.post("/{project_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_drawings(
    project_id: str,
    background_tasks: BackgroundTasks,
    project=Depends(require_design_complete)
):
    job_id = job_store.create("drawings", project_id=project_id)
    # Stub generation logic; ideally handled by agent, but if router triggers:
    job_store.mark_complete(job_id)
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/drawings/{project_id}/status/{job_id}",
        "message": "Drawing generation in progress."
    }

@router.get("/{project_id}")
async def list_drawings(project_id: str):
    return _drawings_store.get(project_id, [])

@router.get("/{project_id}/member/{member_id}")
async def get_drawing(project_id: str, member_id: str):
    drawings = _drawings_store.get(project_id, [])
    for d in drawings:
        if d.get("member_id") == member_id:
            return d
    return {}

@router.post("/{project_id}/member/{member_id}/regenerate")
async def regenerate_drawing(project_id: str, member_id: str):
    return {"status": "regenerated"}

@router.put("/{project_id}/confirm")
async def confirm_drawings(project_id: str, payload: dict, project=Depends(get_project)):
    return {"status": "confirmed"}

@router.get("/{project_id}/layers")
async def get_layers(project_id: str):
    return {"layers": [], "bounds": {"width": 1000, "height": 1000}}

@router.get("/{project_id}/status/{job_id}", response_model=JobStatus)
async def get_drawing_status(project_id: str, job_id: str):
    return job_store.get_or_404(job_id)
