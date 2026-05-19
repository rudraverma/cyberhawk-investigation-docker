import json
import shutil

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.workspace import BRANDING, LOGO_PATH, CONFIG_DIR

router = APIRouter()


@router.get("/branding")
async def get_branding():
    if not BRANDING.exists():
        return _defaults()
    async with aiofiles.open(BRANDING, "r") as f:
        return json.loads(await f.read())


@router.put("/branding")
async def update_branding(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(BRANDING, "w") as f:
        await f.write(json.dumps(data, indent=2))
    return {"ok": True}


MAX_LOGO_BYTES = 5 * 1024 * 1024  # 5 MB — logos should never be larger

@router.post("/logo")
async def upload_logo(file: UploadFile = File(...)):
    allowed = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in allowed:
        raise HTTPException(400, "Unsupported image type")
    dest = CONFIG_DIR / f"logo{suffix}"
    received = 0
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await file.read(65536):
            received += len(chunk)
            if received > MAX_LOGO_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "Logo exceeds 5 MB limit")
            await f.write(chunk)
    # Update branding to use override
    branding = await get_branding()
    branding["logoOverride"] = True
    branding["logoFile"] = f"logo{suffix}"
    await update_branding(branding)
    return {"ok": True, "file": f"logo{suffix}"}


@router.get("/logo")
def serve_logo():
    for ext in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
        candidate = CONFIG_DIR / f"logo{ext}"
        if candidate.exists():
            return FileResponse(candidate)
    raise HTTPException(404, "No custom logo uploaded")


@router.delete("/logo")
async def reset_logo():
    for ext in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
        candidate = CONFIG_DIR / f"logo{ext}"
        if candidate.exists():
            candidate.unlink()
    branding = await get_branding()
    branding["logoOverride"] = False
    branding.pop("logoFile", None)
    await update_branding(branding)
    return {"ok": True}


def _defaults() -> dict:
    return {
        "platformName": "CyberHawk",
        "heroTitle": "THREAT INTEL PLATFORM",
        "heroSubtitle": "Developed In-House",
        "tagline": "HUNT. ANALYSE. REPORT",
        "statusLabel": "LIVE",
        "welcomeMessage": "",
        "footerText": "CyberHawk Threat Intel",
        "analystName": "",
        "organisation": "CyberHawk",
        "tlpDefault": "TLP:AMBER",
        "logoUrl": "https://media.cyberhawkthreatintel.com/general/1771234479938-y9566.png",
        "logoOverride": False,
    }
