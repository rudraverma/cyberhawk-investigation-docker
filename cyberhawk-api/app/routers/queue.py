import json
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.workspace import WORKSPACE

router = APIRouter()

QUEUE_FILE = WORKSPACE / "queue.json"
_lock = threading.Lock()


# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> dict:
    if not QUEUE_FILE.exists():
        return {"next_seq": 1, "items": []}
    try:
        return json.loads(QUEUE_FILE.read_text())
    except Exception:
        return {"next_seq": 1, "items": []}


def _save(data: dict) -> None:
    QUEUE_FILE.write_text(json.dumps(data, indent=2))


# ── Public helper (called from files.py on upload) ────────────────────────────

def queue_add(filename: str, size: int) -> int:
    """Register an uploaded file. Returns seq number. Thread-safe."""
    with _lock:
        data = _load()
        seq = data["next_seq"]
        data["next_seq"] += 1
        data["items"].append({
            "seq": seq,
            "filename": filename,
            "notes": "",
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "size": size,
            "status": "pending",
        })
        _save(data)
    return seq


def queue_remove(filename: str) -> None:
    """Remove all queue entries for a filename (called on file delete)."""
    with _lock:
        data = _load()
        data["items"] = [i for i in data["items"] if i["filename"] != filename]
        _save(data)


def queue_clear() -> None:
    """Remove all queue entries (called on clear-queue)."""
    with _lock:
        data = _load()
        data["items"] = []
        _save(data)


# ── API endpoints ─────────────────────────────────────────────────────────────

@router.get("")
def list_queue():
    with _lock:
        data = _load()
    return data["items"]


class NotesBody(BaseModel):
    notes: str


@router.patch("/{seq}/notes")
def update_notes(seq: int, body: NotesBody):
    with _lock:
        data = _load()
        for item in data["items"]:
            if item["seq"] == seq:
                item["notes"] = body.notes
                _save(data)
                return {"ok": True, "seq": seq}
    raise HTTPException(404, f"Queue item #{seq} not found")


class StatusBody(BaseModel):
    status: str


@router.patch("/{seq}/status")
def update_status(seq: int, body: StatusBody):
    with _lock:
        data = _load()
        for item in data["items"]:
            if item["seq"] == seq:
                item["status"] = body.status
                _save(data)
                return {"ok": True, "seq": seq}
    raise HTTPException(404, f"Queue item #{seq} not found")


@router.delete("/{seq}")
def remove_from_queue(seq: int):
    with _lock:
        data = _load()
        before = len(data["items"])
        data["items"] = [i for i in data["items"] if i["seq"] != seq]
        if len(data["items"]) == before:
            raise HTTPException(404, f"Queue item #{seq} not found")
        _save(data)
    return {"ok": True, "seq": seq}
