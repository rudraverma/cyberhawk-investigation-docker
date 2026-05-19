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
| `cyberhawk-api` | python:3.12-slim | MCP server, FastAPI, all core analysis tools, 755 skills |
| `cyberhawk-ui` | nginx:alpine | React SPA, CyberHawk branding |
| `cyberhawk-sift-remnux` | digitalsleuth/sift-remnux:latest | Full SIFT + REMnux suite — disk, memory, malware analysis (on-demand profile) |
| `cyberhawk-cracking` | dizcza/docker-hashcat:pocl | hashcat v7.1.1 (CPU/POCL), John the Ripper, wordlists |
| `cyberhawk-crypto-email` | ubuntu:22.04 | GPG, mpack, swaks, eml-analyzer, OpenSSL |
| `cyberhawk-kali` | kalilinux/kali-rolling | metasploit, sqlmap, gobuster, ffuf, hydra, theharvester (pentest profile) |

---

## Port Assignments

| Port | Service | Notes |
|------|---------|-------|
| 8090 | cyberhawk-ui | Web interface |
| 3002 | cyberhawk-api MCP | Claude Code connects here |
| 8000 | cyberhawk-api (internal) | nginx proxies /api/* here |

Ports 8090 and 3002 must be free on the host. All other communication is internal to the Docker network.

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

Claude Code (Pro plan) runs on the analyst's local machine and connects to the Docker container via MCP over HTTP+SSE. No API key is required — authentication uses the existing Pro plan OAuth session.

```
Analyst terminal (local)
  └── claude (Pro plan)
        └── MCP tool call
              └── HTTP SSE → server:3002/sse
                    └── cyberhawk-api
                          └── runs skill / reads file / writes result
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
