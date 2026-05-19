"""
CyberHawk MCP Server — HTTP + SSE transport.

Claude Code connects via:  { "type": "sse", "url": "http://<host>:3002/sse" }

Investigation flow:
  1. Claude calls list_upload  → finds the evidence file
  2. Claude calls triage_file  → file type, strings, hashes, recommended skill chain
  3. Claude calls run_skill    → loads the SKILL.md methodology to follow
  4. Claude calls execute_cmd  → runs analysis tools inside the container
  5. Claude calls write_file   → saves IOCs, decoded payloads, report
  6. Repeat steps 3-5 chaining skills until investigation is complete
"""
import asyncio
import hashlib
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.workspace import WORKSPACE, UPLOAD_DIR, CASES_DIR, SKILLS_DIR, safe_path

router = APIRouter()
_sessions: dict[str, asyncio.Queue] = {}


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_cases",
        "description": "List all investigation cases in the workspace.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_upload",
        "description": "List files waiting in upload/ with name, size, MD5, SHA1, SHA256.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_skills",
        "description": "Search the 755 installed cybersecurity skills by keyword. Returns name + description.",
        "inputSchema": {
            "type": "object",
            "properties": {"filter": {"type": "string", "description": "Keyword to filter by (e.g. 'malware', 'phishing', 'c2', 'powershell')"}},
            "required": [],
        },
    },
    {
        "name": "run_skill",
        "description": (
            "Load a skill's full SKILL.md methodology so you can execute it step by step. "
            "Read the skill, understand the workflow and commands, then use execute_cmd to run each step. "
            "Chain multiple skills in sequence for a complete investigation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Exact skill folder name from list_skills"},
            },
            "required": ["skill_name"],
        },
    },
    {
        "name": "triage_file",
        "description": (
            "Auto-triage an evidence file: detects file type, extracts strings, calculates hashes, "
            "runs exiftool/binwalk where applicable. Returns a triage report and a recommended "
            "ordered list of skills to chain for a full investigation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to /workspace, e.g. upload/sample.exe"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "execute_cmd",
        "description": (
            "Run a shell command inside the Docker container with /workspace as cwd. "
            "Use this to execute analysis steps from skill methodologies: "
            "strings, file, exiftool, binwalk, python3, base64, xxd, yara, clamscan, etc. "
            "stdout and stderr are returned. Timeout 120s."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run, e.g. 'strings -n 8 upload/sample.exe | grep -E \"http|cmd|powershell\"'"},
                "cwd":     {"type": "string", "description": "Optional working directory relative to /workspace (default: /workspace)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read any text file from the workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relative to /workspace"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the workspace (creates parent dirs). Use to save IOCs, decoded payloads, reports.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Path relative to /workspace, e.g. investigations/2026-05-15/case-name/iocs.md"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "hash_file",
        "description": "Get MD5, SHA1, SHA256 of a file.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "create_case",
        "description": "Create a new investigation case folder with a notes.md skeleton.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short case name, e.g. malware-invoice-may"},
                "date": {"type": "string", "description": "YYYY-MM-DD (defaults to today)"},
            },
            "required": ["name"],
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(path: Path) -> dict:
    md5, sha1, sha256 = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5.update(chunk); sha1.update(chunk); sha256.update(chunk)
    return {"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}


async def _run(cmd: str, cwd: str = None, timeout: int = 120) -> str:
    work_dir = str(WORKSPACE) if not cwd else str((WORKSPACE / cwd).resolve())
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=work_dir,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out.decode(errors="replace")
    except asyncio.TimeoutError:
        proc.kill()
        return f"[TIMEOUT after {timeout}s]"


# ── Triage logic ──────────────────────────────────────────────────────────────

# Maps file characteristics → ordered skill chain to recommend
SKILL_CHAINS = {
    "pe":        ["performing-static-malware-analysis-with-pe-studio",
                  "extracting-iocs-from-malware-samples",
                  "analyzing-command-and-control-communication",
                  "reverse-engineering-malware-with-ghidra",
                  "analyzing-network-traffic-of-malware"],
    "elf":       ["analyzing-linux-elf-malware",
                  "extracting-iocs-from-malware-samples",
                  "analyzing-command-and-control-communication"],
    "pdf":       ["analyzing-pdf-malware-with-pdfid",
                  "extracting-iocs-from-malware-samples"],
    "office":    ["analyzing-macro-malware-in-office-documents",
                  "extracting-iocs-from-malware-samples",
                  "deobfuscating-powershell-obfuscated-malware"],
    "powershell":["deobfuscating-powershell-obfuscated-malware",
                  "extracting-iocs-from-malware-samples",
                  "analyzing-command-and-control-communication"],
    "javascript":["deobfuscating-javascript-malware",
                  "extracting-iocs-from-malware-samples",
                  "analyzing-command-and-control-communication",
                  "performing-malware-ioc-extraction"],
    "email":     ["analyzing-email-headers-for-phishing-investigation",
                  "investigating-phishing-email-incident",
                  "extracting-iocs-from-malware-samples"],
    "apk":       ["analyzing-android-malware-with-apktool",
                  "reverse-engineering-android-malware-with-jadx",
                  "extracting-iocs-from-malware-samples"],
    "dotnet":    ["reverse-engineering-dotnet-malware-with-dnspy",
                  "extracting-iocs-from-malware-samples",
                  "analyzing-command-and-control-communication"],
    "pcap":      ["analyzing-network-traffic-with-wireshark",
                  "hunting-for-command-and-control-beaconing",
                  "detecting-command-and-control-over-dns"],
    "script":    ["extracting-iocs-from-malware-samples",
                  "analyzing-command-and-control-communication"],
    "default":   ["extracting-iocs-from-malware-samples",
                  "performing-malware-ioc-extraction",
                  "analyzing-command-and-control-communication"],
}

def _recommend_skills(file_output: str, filename: str, strings_sample: str) -> list[str]:
    combined = (file_output + filename + strings_sample).lower()
    if "pe32" in combined or "portable executable" in combined or filename.endswith((".exe", ".dll", ".sys")):
        key = "pe"
    elif "elf" in combined or filename.endswith((".elf", ".so")):
        key = "elf"
    elif ".net" in combined or "cil" in combined or "msil" in combined:
        key = "dotnet"
    elif "pdf" in combined or filename.endswith(".pdf"):
        key = "pdf"
    elif filename.endswith((".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".docm", ".ppt", ".pptx")):
        key = "office"
    elif filename.endswith((".ps1", ".psm1")):
        key = "powershell"
    elif filename.endswith((".js", ".jse", ".vbs", ".vbe", ".hta")):
        key = "javascript"
    elif filename.endswith((".msg", ".eml")):
        key = "email"
    elif filename.endswith(".apk"):
        key = "apk"
    elif filename.endswith((".pcap", ".pcapng", ".cap")):
        key = "pcap"
    elif "powershell" in combined or "invoke-expression" in combined:
        key = "powershell"
    elif "script" in combined or "javascript" in combined:
        key = "javascript"
    else:
        key = "default"
    return SKILL_CHAINS[key]


# ── Tool execution ────────────────────────────────────────────────────────────

async def _call_tool(name: str, args: dict) -> str:
    from datetime import date as dt

    # ── list_cases ────────────────────────────────────────────────────────────
    if name == "list_cases":
        cases = []
        if CASES_DIR.exists():
            for d in sorted(CASES_DIR.iterdir(), reverse=True):
                if d.is_dir():
                    for c in sorted(d.iterdir()):
                        if c.is_dir():
                            cases.append({"name": c.name, "date": d.name,
                                          "path": str(c.relative_to(WORKSPACE))})
        return json.dumps(cases, indent=2)

    # ── list_upload ───────────────────────────────────────────────────────────
    if name == "list_upload":
        files = []
        if UPLOAD_DIR.exists():
            for p in sorted(UPLOAD_DIR.iterdir()):
                if p.is_file():
                    files.append({"name": p.name, "size": p.stat().st_size, **_hash(p)})
        return json.dumps(files, indent=2)

    # ── list_skills ───────────────────────────────────────────────────────────
    if name == "list_skills":
        import yaml
        filt = args.get("filter", "").lower()
        skills = []
        if SKILLS_DIR.exists():
            for d in sorted(SKILLS_DIR.iterdir()):
                sm = d / "SKILL.md"
                if d.is_dir() and sm.exists():
                    try:
                        txt = sm.read_text(errors="replace")
                        desc = ""
                        if txt.startswith("---"):
                            end = txt.find("---", 3)
                            if end > 0:
                                fm = yaml.safe_load(txt[3:end]) or {}
                                desc = str(fm.get("description", ""))
                        if filt and filt not in d.name.lower() and filt not in desc.lower():
                            continue
                        skills.append({"name": d.name, "description": desc[:150]})
                    except Exception:
                        skills.append({"name": d.name, "description": ""})
        return json.dumps(skills, indent=2)

    # ── run_skill ─────────────────────────────────────────────────────────────
    if name == "run_skill":
        skill_dir = SKILLS_DIR / args["skill_name"]
        skill_md  = skill_dir / "SKILL.md"
        if not skill_dir.exists():
            close = [d.name for d in SKILLS_DIR.iterdir()
                     if args["skill_name"].split("-")[0] in d.name][:5]
            return f"Skill '{args['skill_name']}' not found. Similar: {close}"
        if not skill_md.exists():
            return f"SKILL.md not found in '{args['skill_name']}'."
        return skill_md.read_text(errors="replace")

    # ── triage_file ───────────────────────────────────────────────────────────
    if name == "triage_file":
        target = safe_path(args["path"])
        if not target.is_file():
            return "Error: file not found"

        filename = target.name
        size     = target.stat().st_size
        hashes   = _hash(target)

        # file type
        file_out  = await _run(f"file -b {str(target)!r}")
        # strings (first 200 interesting ones)
        str_out   = await _run(
            f"strings -n 6 {str(target)!r} | grep -E "
            f"'(http|ftp|https|cmd|powershell|eval|base64|exec|socket|connect|download|"
            f"wget|curl|invoke|bypass|hidden|\\\\x[0-9a-f]{{2}})' | head -200"
        )
        # exiftool
        exif_out  = await _run(f"exiftool {str(target)!r} 2>/dev/null | head -40")
        # entropy check via python
        entropy_out = await _run(
            f"python3 -c \""
            f"import math, collections; d=open('{str(target)}','rb').read(); "
            f"c=collections.Counter(d); "
            f"e=-sum((v/len(d))*math.log2(v/len(d)) for v in c.values() if v); "
            f"print(f'Entropy: {{e:.2f}}/8.00 — {{\\\"HIGH (likely packed/encrypted)\\\" if e>7 else \\\"NORMAL\\\"}}')\""
        )

        # recommend skill chain
        chain = _recommend_skills(file_out, filename, str_out)
        # filter to only skills that exist on disk
        chain = [s for s in chain if (SKILLS_DIR / s).exists()]

        report = f"""# Triage Report: {filename}

## File Info
- **Name:** {filename}
- **Size:** {size:,} bytes
- **Type:** {file_out.strip()}
- **{entropy_out.strip()}**

## Hashes
- MD5:    {hashes['md5']}
- SHA1:   {hashes['sha1']}
- SHA256: {hashes['sha256']}

## Exiftool
```
{exif_out.strip()}
```

## Suspicious Strings (grep)
```
{str_out.strip() or '(none matched)'}
```

## Recommended Skill Chain
Run these skills in order for a complete investigation:
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(chain))}

Use run_skill(<name>) to load each skill's full methodology, then execute_cmd to run the analysis steps.
"""
        return report

    # ── execute_cmd ───────────────────────────────────────────────────────────
    if name == "execute_cmd":
        cmd = args["command"]
        cwd = args.get("cwd")
        # Block obviously destructive commands
        blocked = ["rm -rf /", "mkfs", "> /dev/sd", "dd if="]
        for b in blocked:
            if b in cmd:
                return f"Blocked: command contains '{b}'"
        output = await _run(cmd, cwd=cwd, timeout=120)
        return output or "(no output)"

    # ── read_file ─────────────────────────────────────────────────────────────
    if name == "read_file":
        target = safe_path(args["path"])
        if not target.is_file():
            return "Error: file not found"
        return target.read_text(errors="replace")

    # ── write_file ────────────────────────────────────────────────────────────
    if name == "write_file":
        target = safe_path(args["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args["content"])
        return f"Written: {args['path']}"

    # ── hash_file ─────────────────────────────────────────────────────────────
    if name == "hash_file":
        target = safe_path(args["path"])
        if not target.is_file():
            return "Error: file not found"
        return json.dumps({"path": args["path"], "size": target.stat().st_size, **_hash(target)}, indent=2)

    # ── create_case ───────────────────────────────────────────────────────────
    if name == "create_case":
        d = args.get("date") or dt.today().isoformat()
        case_path = CASES_DIR / d / args["name"]
        case_path.mkdir(parents=True, exist_ok=True)
        notes = case_path / "notes.md"
        if not notes.exists():
            notes.write_text(
                f"# Case: {args['name']}\n\nCLASSIFICATION: TLP:AMBER\n\n"
                f"**Date opened:** {d}\n\n## Evidence Intake\n\n## Initial Hypothesis\n"
            )
        return f"Created: {str(case_path.relative_to(WORKSPACE))}"

    return f"Unknown tool: {name}"


# ── HTTP streamable transport (MCP 2025-03-26 — current standard) ────────────

@router.post("/mcp")
async def mcp_http(request: Request):
    """Single-endpoint HTTP transport — used by current Claude Code versions."""
    body   = await request.json()
    method = body.get("method", "")
    req_id = body.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cyberhawk", "version": "2.0.0"},
            },
        }
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = body["params"]["name"]
        tool_args = body["params"].get("arguments", {})
        try:
            result = await _call_tool(tool_name, tool_args)
        except Exception as e:
            result = f"Error: {e}"
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": result}]},
        }
    elif method == "notifications/initialized":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    else:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


# ── SSE transport (legacy — kept for backwards compatibility) ──────────────────

async def _sse_stream(session_id: str):
    q = _sessions[session_id]
    yield f"event: endpoint\ndata: {json.dumps({'uri': f'/messages?sessionId={session_id}'})}\n\n"
    while True:
        try:
            msg = await asyncio.wait_for(q.get(), timeout=25)
            if msg is None:
                break
            yield f"data: {json.dumps(msg)}\n\n"
        except asyncio.TimeoutError:
            yield ": ping\n\n"


@router.get("/sse")
async def sse_connect(request: Request):
    session_id = str(uuid.uuid4())
    _sessions[session_id] = asyncio.Queue()
    return StreamingResponse(
        _sse_stream(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/messages")
async def mcp_messages(request: Request, sessionId: str):
    body   = await request.json()
    q      = _sessions.get(sessionId)
    method = body.get("method", "")
    req_id = body.get("id")

    if method == "initialize":
        response = {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cyberhawk", "version": "2.0.0"},
            },
        }
    elif method == "tools/list":
        response = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = body["params"]["name"]
        tool_args = body["params"].get("arguments", {})
        try:
            result = await _call_tool(tool_name, tool_args)
        except Exception as e:
            result = f"Error: {e}"
        response = {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": result}]},
        }
    elif method == "notifications/initialized":
        return {"ok": True}
    else:
        response = {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    if q:
        await q.put(response)
    return {"ok": True}
