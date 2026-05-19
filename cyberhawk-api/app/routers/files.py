import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from app.core.workspace import WORKSPACE, UPLOAD_DIR, CASES_DIR, safe_path

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_file(path: Path) -> dict:
    md5, sha1, sha256 = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5.update(chunk); sha1.update(chunk); sha256.update(chunk)
    return {"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024: return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _entry(p: Path) -> dict:
    stat = p.stat()
    return {
        "name":     p.name,
        "path":     str(p.relative_to(WORKSPACE)),
        "type":     "directory" if p.is_dir() else "file",
        "size":     _fmt_size(stat.st_size) if p.is_file() else None,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


# ── Upload ────────────────────────────────────────────────────────────────────

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB hard limit per file

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    dest = UPLOAD_DIR / file.filename
    received = 0
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await file.read(65536):
            received += len(chunk)
            if received > MAX_UPLOAD_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "File exceeds 2 GB upload limit")
            await f.write(chunk)
    return {"filename": file.filename, "size": dest.stat().st_size, **_hash_file(dest)}


@router.get("/upload")
def list_upload():
    if not UPLOAD_DIR.exists():
        return []
    return [
        {**_entry(p), "hashes": _hash_file(p)}
        for p in sorted(UPLOAD_DIR.iterdir()) if p.is_file()
    ]


# ── File tree (flat listing of one directory) ─────────────────────────────────

@router.get("/tree")
def file_tree(path: str = "investigations"):
    root = safe_path(path)
    if not root.exists() or not root.is_dir():
        return []
    return [_entry(child) for child in sorted(root.iterdir())]


# ── Read / write ──────────────────────────────────────────────────────────────

@router.get("/read", response_class=PlainTextResponse)
async def read_file(path: str):
    target = safe_path(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    async with aiofiles.open(target, "r", errors="replace") as f:
        return await f.read()


class WriteBody(BaseModel):
    path:    str
    content: str

@router.post("/write")
async def write_file(body: WriteBody):
    target = safe_path(body.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target, "w") as f:
        await f.write(body.content)
    return {"ok": True, "path": body.path}


# ── Delete ────────────────────────────────────────────────────────────────────

class PathBody(BaseModel):
    path: str

@router.delete("/delete")
def delete_file(body: PathBody):
    target = safe_path(body.path)
    if not target.exists():
        raise HTTPException(404, "Not found")
    shutil.rmtree(target) if target.is_dir() else target.unlink()
    return {"ok": True}


# ── Move ──────────────────────────────────────────────────────────────────────

class MoveBody(BaseModel):
    src: str
    dst: str

@router.post("/move")
def move_file(body: MoveBody):
    src = safe_path(body.src)
    dst = safe_path(body.dst)
    if not src.exists():
        raise HTTPException(404, "Source not found")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"ok": True}


# ── Download ──────────────────────────────────────────────────────────────────

@router.get("/download")
def download_file(path: str):
    target = safe_path(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target, filename=target.name)


# ── Mkdir ─────────────────────────────────────────────────────────────────────

@router.post("/mkdir")
def make_dir(body: PathBody):
    safe_path(body.path).mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": body.path}


# ── Cases ─────────────────────────────────────────────────────────────────────

class CaseBody(BaseModel):
    name: str   # expects "YYYY-MM-DD/slug" or just "slug"

@router.post("/case")
def create_case(body: CaseBody):
    # name may be "2026-05-15/phishing-may" or just "phishing-may"
    parts = body.name.strip("/").split("/", 1)
    if len(parts) == 2 and len(parts[0]) == 10:
        date_str, slug = parts
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug     = parts[0]

    case_path = CASES_DIR / date_str / slug
    case_path.mkdir(parents=True, exist_ok=True)
    notes = case_path / "notes.md"
    if not notes.exists():
        notes.write_text(
            f"# Case: {slug}\n\nCLASSIFICATION: TLP:AMBER\n\n"
            f"**Date opened:** {date_str}\n\n## Evidence Intake\n\n## Initial Hypothesis\n"
        )
    rel = str(case_path.relative_to(WORKSPACE))
    return {"path": rel, "date": date_str, "name": slug}


@router.get("/cases")
def list_cases():
    if not CASES_DIR.exists():
        return []
    cases = []
    for date_dir in sorted(CASES_DIR.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        for case_dir in sorted(date_dir.iterdir()):
            if case_dir.is_dir():
                cases.append({
                    "name":  case_dir.name,
                    "date":  date_dir.name,
                    "path":  str(case_dir.relative_to(WORKSPACE)),
                    "files": len(list(case_dir.rglob("*"))),
                })
    return cases


# ── Hash ──────────────────────────────────────────────────────────────────────

@router.get("/hash")
def hash_file(path: str):
    target = safe_path(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    return {"path": path, "size": target.stat().st_size, **_hash_file(target)}
