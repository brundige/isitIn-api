"""User-submitted river suggestions."""

from fastapi import APIRouter, HTTPException

from Backend import db
from Backend.API.schemas import RiverRequestPayload

router = APIRouter(prefix="/river-requests", tags=["river-requests"])


@router.post("", status_code=201)
def submit(req: RiverRequestPayload):
    if not req.river_name.strip():
        raise HTTPException(status_code=422, detail="river_name is required")
    entry = db.add_river_request(
        river_name=req.river_name.strip(),
        location=req.location.strip(),
        gauge_id=req.gauge_id.strip(),
        notes=req.notes.strip(),
    )
    return {"status": "received", "river_name": entry["river_name"]}


@router.get("")
def list_all():
    return db.list_river_requests()
