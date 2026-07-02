# CyberHawk Docker — Architecture & Design

## Overview

CyberHawk is a self-contained cyber investigation platform running as a Docker Compose stack. It provides an isolated environment for static malware analysis, phishing investigation, IOC extraction, and threat intelligence operations using 755 pre-built cybersecurity skills.

---

## Container Stack

### v1 — Core Only (current running state)

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host Machine                             │
│                                                                 │
│   Claude Code CLI (Pro plan, OAuth) ── MCP ──► :3002           │
│   Browser ──────────────────────────────────► :8090            │
└────────────────────────────┬──────────────────────┬────────────┘
                             │                      │
              ┌──────────────▼──────┐   ┌───────────▼────────────┐
              │  cyberhawk-ui       │   │  cyberhawk-api          │
              │                     │   │                          │
              │  nginx:alpine       │◄──│  python:3.12-slim        │
              │  React SPA          │   │  FastAPI + uvicorn       │
              │  CyberHawk branding │   │  Skill runner            │
              │  Port 80→host:8090  │   │  File manager            │
              │                     │   │  MCP server              │
              │  Pages:             │   │  Web terminal (pty)      │
              │  - Dashboard        │   │  All analysis tools      │
              │  - Upload Zone      │   │  Port 8000→host:3002     │
              │  - File Browser     │   │                          │
              │  - Report Viewer    │   │  Analysis tools:         │
              │  - Web Terminal     │   │  dig, whois, file        │
              │  - New Case         │   │  strings, exiftool       │
              │  - Settings         │   │  oletools, extract-msg   │
              └─────────────────────┘   │  yara, binwalk, clamav  │
                                        └──────────┬──────────────┘
                                                   │
                             ┌─────────────────────▼──────────────┐
                             │       Docker Named Volume           │
                             │       cyberhawk-data                │
                             │                                      │
                             │  /workspace/                         │
                             │    upload/        ← evidence         │
                             │    investigations/ ← cases           │
                             │    config/        ← branding         │
                             │    .agents/skills/ ← 755 skills      │
                             └──────────────────────────────────────┘
```

### v2 — Multi-Container Bundle (new specialist containers added)

```
Host: <your-server>
Project root: ~/cyberhawk-docker/   (or wherever you clone this repo)
Build command: cd ~/cyberhawk-docker && docker compose build
Run command:   cd ~/cyberhawk-docker && docker compose up -d

┌───────────────────────────────────────────────────────────────────┐
│  cyberhawk-net (Docker bridge network)                            │
│                                                                   │
│  cyberhawk-ui    ── port 8090 → host                             │
│  cyberhawk-api   ── port 3002 → host (MCP entry point)           │
│                                                                   │
│  cyberhawk-remnux     (malware analysis — REMnux base)           │
│  cyberhawk-sift       (disk/memory forensics — Ubuntu 22.04)     │
│  cyberhawk-kali       (pentest/network/OSINT — kali-rolling)     │
│  cyberhawk-cracking   (hashcat + John — GPU-ready)               │
│  cyberhawk-crypto-email (GPG + VeraCrypt + email tools)          │
│                                                                   │
│  All containers mount: cyberhawk-data:/workspace                 │
└───────────────────────────────────────────────────────────────────┘
```

| Container | Base Image | Key Tools |
|---|---|---|
| `cyberhawk-api` | python:3.12-slim | MCP server, FastAPI, all core analysis tools, 755 skills, **Playwright + Chromium headless browser** (`/app/app/tools/phishing_browser.py`) |
| `cyberhawk-ui` | nginx:alpine | React SPA, CyberHawk branding |
| `cyberhawk-sift-remnux` | digitalsleuth/sift-remnux:latest | Full SIFT + REMnux suite — disk, memory, malware analysis (on-demand profile) |
| `cyberhawk-cracking` | dizcza/docker-hashcat:pocl | hashcat v7.1.1 (CPU/POCL), John the Ripper, wordlists |
| `cyberhawk-crypto-email` | ubuntu:22.04 | GPG, mpack, swaks, eml-analyzer, OpenSSL |
| `cyberhawk-kali` | kalilinux/kali-rolling | metasploit, sqlmap, gobuster, ffuf, hydra, theharvester (profile: `pentest`) |
| `cyberhawk-ghidra` | eclipse-temurin:21-jre | **bethington/ghidra-mcp v5.12.0** — Ghidra 12.1 + fully headless Java server (port 8089 internal) + Python MCP bridge. **183 tools** via streamable-http on host port **8083**. Profile: `reverse-eng`. |
| *(host service)* | Ubuntu host | **Server MCP** — FastMCP Python service, port 3003, systemd. 13 tools: docker_logs, docker_exec, run_command, run_sudo, docker_ps, docker_restart, docker_build_and_start, read_file, write_file, list_files, systemctl_status, server_info. Install: `/opt/cyberhawk-server-mcp/`. |

---

## Port Assignments

| Port | Service | Notes |
|------|---------|-------|
| 8090 | cyberhawk-ui | Web interface |
| 3002 | cyberhawk-api MCP | Claude Code connects here (streamable-http) |
| 8000 | cyberhawk-api (internal) | FastAPI uvicorn inside container |
| 3003 | Server MCP (host service) | Claude Code connects here — runs on Ubuntu host, NOT in Docker |
| 8083 | cyberhawk-ghidra MCP bridge | Claude Code connects here for RE tools (streamable-http). Maps to container port 8081. |
| 8089 | cyberhawk-ghidra Java server | Internal only (127.0.0.1) — Ghidra headless REST API, never exposed to host |
| 2233 | cyberhawk-sift-remnux SSH | `ssh forensics@<server>:2233` |

> **Ghidra session note:** After any ghidra container restart, the MCP session IDs are invalidated.
> Claude Code MUST be restarted to create fresh sessions — otherwise all ghidra tool calls return `Session not found`.

---

## Security Model

| Threat | Mitigation |
|--------|-----------|
| Malware escaping to host | Named volume isolates from host filesystem; files never executed in api container |
| Malware calling home | Static analysis only by default; no sandbox network egress |
| API secrets in image | All secrets injected at runtime via .env; never baked into image |
| UI exposed to internet | Binds to 0.0.0.0 by default — add Cloudflare tunnel or nginx auth for external access |
| Skills running untrusted code | Subprocess execution with timeout; container cgroup limits apply |

---

## Claude Code MCP Integration

Claude Code (Pro plan) runs on the analyst's local machine and connects to three MCP servers via streamable-http. No API key is required — authentication uses the existing Pro plan OAuth session.

```
Analyst terminal (local)
  └── claude (Pro plan)
        ├── MCP: cyberhawk  → http://<SERVER_IP>:3002/mcp  (cyberhawk-api Docker container)
        │     └── evidence analysis, skills, file ops, triage
        ├── MCP: server     → http://<SERVER_IP>:3003/mcp  (Ubuntu HOST — systemd service)
        │     └── docker_logs, docker_exec, run_command, host filesystem, server_info
        └── MCP: ghidra     → http://<SERVER_IP>:8083/mcp  (cyberhawk-ghidra Docker container)
              └── import_file, decompile_function, list_functions, search_memory, debugger_*
```

`.mcp.json` (at repo root):
```json
{
  "mcpServers": {
    "cyberhawk": { "type": "http", "url": "http://<SERVER_IP>:3002/mcp" },
    "server":    { "type": "http", "url": "http://<SERVER_IP>:3003/mcp" },
    "ghidra":    { "type": "http", "url": "http://<SERVER_IP>:8083/mcp" }
  }
}
```

MCP tools exposed:

| Tool | Input | Output |
|------|-------|--------|
| list_cases | — | Array of case objects |
| list_upload | — | Array of file objects with hashes |
| list_skills | filter (optional) | Array of skill names + descriptions |
| run_skill | skill_name, evidence_path, case_path | Skill output text |
| read_file | path | File contents |
| write_file | path, content | Success/error |
| hash_file | path | MD5, SHA1, SHA256 |
| create_case | name | Created case path |

---

## Branding System

All UI text and visual identity is driven by `/workspace/config/branding.json`. The React frontend fetches this file at startup and applies it globally. No rebuild required to change branding.

Configurable fields: platform name, hero title, subtitle, tagline, status label, welcome message, footer, analyst name, organisation, TLP default, logo (file upload or remote URL).

---

## Skill Execution

Skills (Python scripts in `/workspace/.agents/skills/`) are executed as subprocesses by the API. Output is streamed back to the UI via WebSocket. Each skill receives:
- `--evidence`: path to the evidence file
- `--case`: path to the case output folder
- `--config`: path to branding.json (for analyst name / org)

Skills write their output files directly to the case folder.

---

## Investigation Folder Structure

```
/workspace/investigations/YYYY-MM-DD/<case-name>/
├── notes.md        ← opened first: date, evidence, hypothesis
├── iocs.md         ← IOC table with confidence levels
├── timeline.md     ← chronological event log
├── report.md       ← final report (CLASSIFICATION header)
├── decoded/        ← deobfuscated payloads
└── rules/          ← YARA / Sigma rules
```

---

## Deployment

```bash
git clone <repo>
cd cyberhawk-docker
cp -r /path/to/skills/* skills/
cp .env.example .env
docker compose up -d
```

Access UI at `http://<server-ip>:8090`. Add MCP server to Claude Code settings. Investigate.

---

## Change Log

| Date | Change |
|---|---|
| 2026-05-19 | Added v2 multi-container bundle: remnux, sift, kali, cracking, crypto-email Dockerfiles + updated docker-compose.yml. All new containers share `cyberhawk-data` volume. |
| 2026-05-27 | Added Playwright + Chromium headless browser to `cyberhawk-api`. New investigation tool: `/app/tools/phishing_browser.py`. Bypasses fingerprint gates. |
| 2026-05-27 | **GhidraMCP v2 — complete rewrite.** Replaced LaurieWired GhidraMCP v1.4 (required GUI/Xvfb, plugin activation broken) with **bethington/ghidra-mcp v5.12.0** (100% headless). Multi-stage Dockerfile: eclipse-temurin:21-jdk builder downloads Ghidra 12.1, Maven builds headless JAR (`com.xebyte.headless.GhidraMCPHeadlessServer`); eclipse-temurin:21-jre runtime runs Java server on `127.0.0.1:8089` + Python bridge on port 8081. Host port mapping: 8083→8081. 183 MCP tools registered. Transport: streamable-http. Root cause of original failure: `--bind 0.0.0.0` without `GHIDRA_MCP_AUTH_TOKEN` → fix: changed to `--bind 127.0.0.1`. |
| 2026-05-27 | **Server MCP — NEW service on Ubuntu host.** FastMCP Python app (`cyberhawk_server_mcp.py`) running as systemd service on the Ubuntu host at port 3003. Installed at `/opt/cyberhawk-server-mcp/venv/`. Solves fundamental limitation that `cyberhawk-api` has no Docker socket access (cannot run docker logs/exec/ps). 13 tools covering full host + Docker management. `.mcp.json` updated with third entry. Deployment: `docker cp` from staging + `python3 -m venv` + `pip install mcp[cli]>=1.2.0` + `systemctl enable --now`. |
