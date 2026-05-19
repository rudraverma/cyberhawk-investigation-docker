import asyncio
import re
import subprocess
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.workspace import SKILLS_DIR, safe_path

# Only allow safe directory names — no path traversal characters
_SKILL_NAME_RE = re.compile(r'^[A-Za-z0-9_\-]{1,128}$')

def _validate_skill_name(name: str) -> None:
    if not _SKILL_NAME_RE.match(name):
        raise HTTPException(400, "Invalid skill name")

router = APIRouter()


def _read_skill_meta(skill_dir: Path) -> dict:
    skill_md = skill_dir / "SKILL.md"
    meta = {"name": skill_dir.name, "description": "", "tags": [], "domain": ""}
    if not skill_md.exists():
        return meta
    try:
        content = skill_md.read_text(errors="replace")
        # Parse YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                fm = yaml.safe_load(content[3:end])
                if isinstance(fm, dict):
                    meta["description"] = fm.get("description", "")
                    meta["tags"] = fm.get("tags", [])
                    meta["domain"] = fm.get("domain", "")
    except Exception:
        pass
    return meta


@router.get("/")
def list_skills(filter: str = None):
    if not SKILLS_DIR.exists():
        return []
    skills = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            meta = _read_skill_meta(d)
            if filter:
                needle = filter.lower()
                if (needle not in meta["name"].lower()
                        and needle not in str(meta["description"]).lower()
                        and not any(needle in t.lower() for t in meta["tags"])):
                    continue
            skills.append(meta)
    return skills


@router.get("/{skill_name}")
def get_skill(skill_name: str):
    _validate_skill_name(skill_name)
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.exists():
        return {"error": "Skill not found"}
    meta = _read_skill_meta(skill_dir)
    skill_md = skill_dir / "SKILL.md"
    meta["readme"] = skill_md.read_text(errors="replace") if skill_md.exists() else ""
    return meta


@router.websocket("/run")
async def run_skill(websocket: WebSocket):
    """
    WebSocket endpoint to stream skill execution output.
    Client sends JSON: { skill: str, evidence: str, case: str }
    Server streams stdout/stderr lines as text.
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        skill_name = data.get("skill", "")
        evidence   = data.get("evidence", "")
        case       = data.get("case", "")

        if not _SKILL_NAME_RE.match(skill_name):
            await websocket.send_text("[ERROR] Invalid skill name\n")
            await websocket.close()
            return

        skill_dir = SKILLS_DIR / skill_name
        agent_py  = skill_dir / "scripts" / "agent.py"

        if not agent_py.exists():
            await websocket.send_text(f"[ERROR] Skill '{skill_name}' not found or has no agent.py\n")
            await websocket.close()
            return

        evidence_path = safe_path(evidence) if evidence else None
        case_path     = safe_path(case)     if case     else None

        cmd = ["python3", str(agent_py)]
        if evidence_path:
            cmd += ["--evidence", str(evidence_path)]
        if case_path:
            cmd += ["--case", str(case_path)]
            case_path.mkdir(parents=True, exist_ok=True)

        await websocket.send_text(f"[CYBERHAWK] Running skill: {skill_name}\n")
        await websocket.send_text(f"[CYBERHAWK] Evidence: {evidence}\n")
        await websocket.send_text(f"[CYBERHAWK] Output: {case}\n")
        await websocket.send_text("[CYBERHAWK] " + "─" * 50 + "\n")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(skill_dir),
        )

        async for line in proc.stdout:
            await websocket.send_text(line.decode(errors="replace"))

        await proc.wait()
        await websocket.send_text(f"\n[CYBERHAWK] Skill exited with code {proc.returncode}\n")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"[ERROR] {e}\n")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
