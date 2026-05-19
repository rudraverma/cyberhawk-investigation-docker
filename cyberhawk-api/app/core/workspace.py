import os
from pathlib import Path

WORKSPACE   = Path(os.environ.get("WORKSPACE", "/workspace"))
UPLOAD_DIR  = WORKSPACE / "upload"
CASES_DIR   = WORKSPACE / "investigations"
CONFIG_DIR  = WORKSPACE / "config"
SKILLS_DIR  = WORKSPACE / ".agents" / "skills"
BRANDING    = CONFIG_DIR / "branding.json"
LOGO_PATH   = CONFIG_DIR / "logo.png"


def safe_path(relative: str) -> Path:
    """Resolve a user-supplied relative path inside WORKSPACE; raise if it escapes."""
    resolved = (WORKSPACE / relative).resolve()
    if not str(resolved).startswith(str(WORKSPACE.resolve())):
        raise ValueError("Path traversal attempt blocked")
    return resolved
