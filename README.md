<div align="center">

<img src="https://media.cyberhawkthreatintel.com/general/1771234479938-y9566.png" width="140" alt="CyberHawk Logo" />

# Cyber Incident Investigation Self Contained Docker build by CyberHawk Threat Intel

### AI-powered, self-hosted cyber investigation platform
**Upload evidence. Tell Claude what you want. Get a full investigation report.**

[![X](https://img.shields.io/badge/X-%40cyberhawkintel-black?logo=x&logoColor=white)](https://x.com/cyberhawkintel)
[![YouTube](https://img.shields.io/badge/YouTube-%40cyberhawkconsultancy-red?logo=youtube&logoColor=white)](https://youtube.com/@cyberhawkconsultancy)
[![YouTube](https://img.shields.io/badge/YouTube-%40cyberhawkk-red?logo=youtube&logoColor=white)](https://youtube.com/@cyberhawkk)
[![TikTok](https://img.shields.io/badge/TikTok-%40cyberhawkthreatintel-black?logo=tiktok&logoColor=white)](https://tiktok.com/@cyberhawkthreatintel)
[![Telegram](https://img.shields.io/badge/Telegram-%40cyberhawkthreatintel-26A5E4?logo=telegram&logoColor=white)](https://t.me/cyberhawkthreatintel)
[![Web App](https://img.shields.io/badge/Web%20App-app.cyberhawkthreatintel.com-22c55e?logo=globe&logoColor=white)](https://app.cyberhawkthreatintel.com)

</div>

---

## What Is CyberHawk Docker?

CyberHawk Docker is a **fully self-hosted, AI-native cyber investigation platform**. It runs as a Docker Compose stack on any Linux server and gives Claude Code (or any MCP-compatible AI) direct access to a battle-tested arsenal of cybersecurity tools, 755 structured investigation skills, and a clean web interface for evidence management.

**You don't need an Anthropic API key.** Claude Code uses your existing Pro plan via MCP.

### The investigation loop

```
Submit a URL or upload a file  (Web UI or API)
  │
  ├─► Automated pipeline runs immediately, before you do anything:
  │     • URL  → DNS/WHOIS/TLS/HTTP recon, Thug drive-by, EtherHiding blockchain-C2
  │              detect, deobfuscate + multi-stage chain-follow
  │     • File → routed by type → capa/floss/speakeasy · olevba · pdfid ·
  │              deobfuscator+sandbox · tshark · apktool · 7z-recurse
  │              + YARA + IOC aggregation + TOOLS_MANDATE.md
  │
  └─► Then you ask Claude (via MCP) to go deeper:
        "find the C2 and give me all IOCs" → Claude reads the pre-decoded
        artifacts, runs the mandated tools, and writes the structured report.
```

Everything happens inside the Docker containers. Nothing touches your host machine.

---

## Automated Investigation Pipeline

Every submission — a **URL** or an uploaded **file** — is auto-triaged the moment it arrives. The pipeline routes each evidence type to the right tool and pre-populates the case folder, so the analyst (you or Claude) starts from decoded artifacts, not raw bytes. A `TOOLS_MANDATE.md` is written into every case listing what already ran and which tools to use next.

### URL investigation

DNS / WHOIS / TLS / HTTP recon → security-header audit → **Thug** drive-by/exploit detection → **EtherHiding blockchain-C2 detection** (eth_call / smart-contract dead-drop) → automatic ABI decode, C2 payload fetch, multi-stage chain-following, and deobfuscation.

### Evidence file auto-triage — routed to the right tool

| Evidence | Tool driven automatically | Key outputs |
|---|---|---|
| **Script** `.ps1 .js .vbs .bat .hta .wsf` | deobfuscator + isolated sandbox, multi-layer decode, C2 chain-follow | `*_beautified.{ps1,js}`, `*.iocs.json`, `*.sandbox.json`, `decode_chain.md` |
| **PE / ELF** | `capa` (MITRE ATT&CK) + `floss` + `speakeasy` emulation | `capa.json`, `floss.json`, `speakeasy_output.txt` |
| **Office** `.doc .docx .xls .xlsm` | `olevba` macro extraction/decode | `olevba.txt` |
| **PDF** | `pdfid` + `pdf-parser` → embedded JS deobfuscated | `pdfid.txt`, `pdf_js_beautified.js` |
| **Archive** `.zip .7z .rar .iso` | extract (password from analyst notes) → **recurse-triage each file** | `extracted/`, per-file analysis |
| **Email** `.eml .msg` | headers + attachments → **recurse-triage each** | `email_headers.json`, `attachments/` |
| **APK** | `apktool` manifest + dangerous-permission flags | `apk_manifest.xml`, `apk_permissions.txt` |
| **PCAP** | `tshark` protocol / DNS / HTTP / TLS-SNI extraction | `pcap_dns.txt`, `pcap_http.txt`, `pcap_tls_sni.txt` |
| **All types** | YARA scan + IOC aggregation + `TOOLS_MANDATE.md` | `yara_matches.txt`, `iocs.json`, `TOOLS_MANDATE.md` |

### Deobfuscation + isolated sandbox

Obfuscated JavaScript / PowerShell is decoded through a companion **deobfuscator** service (multi-layer XOR, base-N, string-concat, pretty-printing) and, when static decoding leaves runtime-only obfuscation (`atob`+XOR+`new Function`, `TextDecoder` byte loops), the payload is **executed in a network-isolated sandbox** (`network_mode: none`, read-only, no privileges) to capture live C2 URLs, decoded inner payloads, and clipboard/ClickFix commands. Service endpoints are configurable via environment variables (see below) — nothing is hardcoded.

---

## Platform Components

### Core Stack (always running)

| Container | Role | Port |
|---|---|---|
| `cyberhawk-ui` | Web interface — evidence upload, file browser, report viewer, live terminal | `8090` |
| `cyberhawk-api` | FastAPI backend + MCP server — all tools, skill execution, file management | `3002` |

### Specialist Containers (optional — build when needed)

| Container | Role | Profile |
|---|---|---|
| `cyberhawk-sift-remnux` | Full SIFT + REMnux suite — disk images, memory dumps, malware analysis | `forensics` |
| `cyberhawk-cracking` | hashcat v7.1.1 (CPU/POCL) + John the Ripper — password and hash cracking | default |
| `cyberhawk-crypto-email` | GPG, eml-analyzer, mpack, swaks, OpenSSL — email and crypto forensics | default |
| `cyberhawk-kali` | metasploit, sqlmap, gobuster, ffuf, hydra, theharvester — pentest/OSINT | `pentest` |

All containers share a single Docker named volume (`cyberhawk-data`) mounted at `/workspace` — evidence uploaded once is accessible from every container.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Your Machine                                                        │
│                                                                      │
│  Claude Code CLI ──── MCP (port 3002) ──────────────────────────►  │
│  Browser         ──── HTTP (port 8090) ─────────────────────────►  │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │
┌──────────────────────────────────────────▼──────────────────────────┐
│  Docker Host (Linux Server)                                          │
│                                                                      │
│  ┌─────────────────────┐    ┌─────────────────────────────────────┐ │
│  │  cyberhawk-ui :8090 │    │  cyberhawk-api :3002                │ │
│  │  React 18 + Vite    │◄───│  FastAPI + uvicorn                  │ │
│  │  nginx reverse proxy│    │  MCP SSE + HTTP transport           │ │
│  │                     │    │  755 skills (read-only mount)       │ │
│  │  Pages:             │    │  Automated investigation pipeline:  │ │
│  │  • Dashboard        │    │   URL recon + EtherHiding detect    │ │
│  │  • Upload Zone      │    │   Evidence auto-triage (by type)    │ │
│  │  • Submit URL       │    │   YARA · IOC aggregation · MANDATE  │ │
│  │  • Triage File      │    │  Skill execution engine             │ │
│  │  • File Browser     │    │  Analysis tools (see below)         │ │
│  │  • Report Viewer    │    │  WebSocket PTY terminal             │ │
│  │  • MITM Live View   │    │  File management API                │ │
│  │  • Web Terminal     │    └──────────┬───────────────┬──────────┘ │
│  │  • New Investigation│               │               │            │
│  │  • Settings         │    ┌──────────▼─────────┐  ┌──▼──────────┐ │
│  └─────────────────────┘    │ Specialist         │  │ Companion   │ │
│                             │ Containers         │  │ services    │ │
│                             │ sift-remnux        │  │ (configured │ │
│                             │  (capa/floss/      │  │  via env):  │ │
│                             │   speakeasy/yara)  │  │ deobfuscator│ │
│                             │ cracking · kali    │  │  + isolated │ │
│                             │ crypto-email       │  │  sandbox    │ │
│                             └──────────┬─────────┘  └─────────────┘ │
│                                        │                            │
│  ┌─────────────────────────────────────▼──────────────────────────┐ │
│  │  Named Volume: cyberhawk-data  →  /workspace/                  │ │
│  │  ├── upload/           ← evidence drop zone                    │ │
│  │  ├── investigations/   ← structured case folders               │ │
│  │  ├── config/           ← branding, logo                        │ │
│  │  └── .agents/skills/   ← 755 skill methodologies (read-only)   │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

> The **deobfuscator** and **network-isolated sandbox** are companion services reached over the URLs in `DEOBFUSCATOR_URL` / `MITM_PROXY` (see [Environment Variables](#environment-variables)). They run as their own compose stacks, so the core platform stays lean and they can be swapped or scaled independently.

---

## Requirements

### Core Stack (cyberhawk-api + cyberhawk-ui)

| Resource | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 LTS |
| Docker | 24.x + Compose v2 | Latest stable |
| RAM | 4 GB | 8 GB |
| Disk | 10 GB free | 20 GB free |
| Ports | 8090, 3002 free | — |
| Claude Code | Pro plan CLI | — |

### With Specialist Containers (full stack)

| Container | Additional Disk | Additional RAM (active) |
|---|---|---|
| `sift-remnux` | ~8 GB | 4–8 GB |
| `cracking` | ~2 GB | 1–4 GB |
| `crypto-email` | ~600 MB | ~200 MB |
| `kali` | ~1.5 GB | ~500 MB |
| **Full stack total** | **~25 GB free recommended** | **16 GB RAM recommended** |

> **Build sequentially** — never `docker compose build` all specialist containers at once. Each one is large. Build and start them one at a time.

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/rudraverma/cyberhawk-investigation-docker.git
cd cyberhawk-investigation-docker
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env
# Add optional enrichment API keys — platform works fully without them
# ANTHROPIC_API_KEY is NOT required — Claude Code uses your Pro plan via MCP
```

### 3. Build and start core stack

```bash
docker compose up -d --build
```

First build takes 15–20 minutes (`radare2`, `volatility3`, `impacket` are large). Watch progress:

```bash
docker compose --progress plain build cyberhawk-api
```

### 4. Verify

```bash
docker compose ps
# cyberhawk-api should show (healthy)
# cyberhawk-ui should show Up
```

### 5. Open the Web UI

```
http://<server-ip>:8090
```

Go to **Settings** to customise your platform name, upload your logo, and set your organisation.

---

## Connect Claude Code (MCP)

This is how you control the platform with natural language.

**Step 1 — Add the MCP server to your Claude Code settings:**

- macOS / Linux: `~/.claude/settings.json`
- Windows: `%APPDATA%\Claude\settings.json`

```json
{
  "mcpServers": {
    "cyberhawk": {
      "type": "sse",
      "url": "http://<server-ip>:3002/sse"
    }
  }
}
```

> Current Claude Code versions also support the HTTP transport:
> ```json
> { "url": "http://<server-ip>:3002/mcp" }
> ```

**Step 2 — Restart Claude Code**

**Step 3 — Verify:** Type `/mcp` — you should see `cyberhawk` listed with 10 tools available.

---

## MCP Tools

Claude uses these automatically during investigations:

| Tool | What it does |
|---|---|
| `list_upload` | List all files in the evidence queue with MD5/SHA1/SHA256 |
| `list_cases` | List all investigation case folders |
| `list_skills` | Search 755 skills by keyword — returns name + description |
| `triage_file` | Auto-detect file type, extract strings, calculate entropy, recommend skill chain |
| `run_skill` | Load a skill's full `SKILL.md` methodology for Claude to follow step by step |
| `execute_cmd` | Run any shell command inside the container — strings, python3, yara, tshark, etc. |
| `read_file` | Read any file from `/workspace` |
| `write_file` | Write IOCs, decoded payloads, reports to a case folder |
| `hash_file` | Get MD5 / SHA1 / SHA256 of any evidence file |
| `create_case` | Create a new investigation case folder with a `notes.md` skeleton |

---

## Web UI

| Page | What you do there |
|---|---|
| **Dashboard** | Overview — recent cases, upload queue, platform status |
| **Upload Zone** | Drag-and-drop evidence files — all uploads go to `/workspace/upload/` |
| **Submit URL** | Submit a URL for automated investigation — live streaming log of every phase (recon → Thug → EtherHiding → deobfuscation) |
| **Triage File** | Kick off automated evidence triage on an uploaded file — routed to the right tool by type, live log |
| **File Browser** | Browse cases and workspace files, read reports, download artefacts |
| **Report Viewer** | Render Markdown investigation reports from case folders |
| **MITM Live View** | Watch decrypted HTTP/S traffic in real time while a URL investigation runs (companion mitmproxy) |
| **Web Terminal** | Full PTY bash shell inside the container — run tools manually |
| **New Investigation** | Create a named case folder with pre-populated `notes.md` |
| **Settings** | Platform branding, logo upload, analyst name, organisation, TLP default |

---

## Investigation Workflow

### Upload evidence

- **Web UI:** Drag files onto `http://<server-ip>:8090` → Upload Zone
- **SCP:** `scp evidence.exe user@<server-ip>:/path/to/volume/_data/upload/`
- **Terminal:** Use the built-in terminal to `cp` files into `/workspace/upload/`

### Start an investigation

Just describe what you want in Claude Code. Examples:

```
"I uploaded invoice.msg — is this a phishing email? Give me all IOCs."

"There's a suspicious .exe in the upload queue. Find the C2 server and
 decode any obfuscated strings. Create a case called mal-exe-may."

"Analyse sample.js — I think it's a RAT dropper. Give me all functions,
 decoded payloads, and network indicators in a structured report."

"Run a full memory forensics investigation on the dump in upload/
 using volatility3. Create a case and save all findings."
```

The automated pipeline has usually **already** identified the type, run the right tools, and decoded payloads before you ask. Claude then:
1. Reads `TOOLS_MANDATE.md` + `iocs.json` + the pre-decoded artifacts in the case folder
2. Runs the mandated MCP tools for anything deeper (`run_capa`, `run_floss`, `run_speakeasy`, `run_skill`, …)
3. Chains further decoding (deobfuscation → RE → C2 extraction → IOC packaging)
4. `write_file` → saves the structured report, IOCs, and timeline to the case folder

### Case folder structure

The pipeline pre-populates the case; exact files depend on evidence type. A typical layout:

```
/workspace/investigations/YYYY-MM-DD/<case-name>/
├── notes.md                 ← hashes, hypothesis, analyst
├── iocs.json                ← aggregated IOCs (URLs, IPs, domains, techniques)
├── TOOLS_MANDATE.md         ← what auto-ran + which MCP tools to use next
├── applicable_skills.json   ← skills matched for this evidence type
├── decode_chain.md          ← every deobfuscation layer, in order
├── commands.log             ← full audit trail of every command run
├── capa.json / floss.json   ← (PE/ELF) MITRE ATT&CK caps + obfuscated strings
├── *_beautified.{ps1,js}    ← (scripts) deobfuscated payloads
├── *.sandbox.json           ← (runtime-obfuscated JS) sandbox execution capture
├── yara_matches.txt         ← YARA hits
├── recon/ · page/ · scripts/ · blockchain/   ← (URL cases) per-phase evidence
└── report.md                ← final report (TLP classification header)
```

---

## 755 Cybersecurity Skills

All skills focused on CyberSecurity Incident Investigation core skills.

Each skill contains:
- `SKILL.md` — full investigation methodology, commands, checklists, and expected outputs
- `scripts/agent.py` — executable analysis script
- `references/` — API documentation, standards, workflows
- `assets/` — report templates

### Skill coverage by domain

| Domain | Skills cover |
|---|---|
| **Static Malware Analysis** | PE/ELF/APK analysis, packing detection, entropy analysis, import table review |
| **Reverse Engineering** | radare2 workflows, .NET/Go/Rust malware, Ghidra-guided disassembly |
| **Deobfuscation** | PowerShell, JavaScript, VBScript, Excel 4.0 macros, Base64 chains |
| **C2 Analysis** | Cobalt Strike beacon config extraction, DNS C2 detection, beaconing patterns |
| **Phishing Investigation** | Email header analysis, attachment triage, credential harvesting detection |
| **Network Forensics** | PCAP analysis, protocol decoding, lateral movement detection, covert channels |
| **Memory Forensics** | Volatility3 workflows, process injection detection, credential extraction from RAM |
| **Disk Forensics** | Sleuth Kit, timeline creation, deleted file recovery, browser artefacts |
| **Email Forensics** | `.msg` / `.eml` analysis, DKIM/SPF/DMARC validation, header spoofing detection |
| **OSINT** | Domain intel, passive DNS, certificate transparency, threat actor profiling |
| **Active Directory** | ACL abuse detection, Kerberoasting, BloodHound analysis, lateral movement |
| **Cloud Security** | AWS/Azure/GCP log analysis, IAM abuse, CloudTrail forensics |
| **Threat Intelligence** | IOC extraction, STIX2 packaging, YARA rule generation, Sigma rule creation |
| **Cryptography** | Hash identification, cipher analysis, GPG operations, certificate inspection |
| **Password Cracking** | hashcat workflows, John the Ripper, rule-based attacks, mask attacks |
| **Vulnerability Assessment** | CVE analysis, exploit chain tracing, CVSS scoring |
| **Incident Response** | NIST SP 800-61 workflow, triage classification, evidence preservation |

---

## Tools Inside the Core Container

### CLI tools
```
nmap  tshark  tcpdump  dnsutils  whois  netcat
file  strings  objdump  readelf  nm  exiftool  binwalk  foremost
radare2  upx  strace  ltrace  ssdeep  yara  olefile
clamav  sleuthkit  p7zip  unzip  git  curl  wget
```

### Python packages
```
# Malware / RE
yara-python  pefile  pyelftools  capstone  r2pipe  jsbeautifier

# Memory forensics
volatility3

# Network / protocol analysis
scapy  dpkt  impacket  ldap3  dnspython  python-whois  paramiko

# Office / email
oletools  extract-msg  xlmdeobfuscator  beautifulsoup4  lxml  defusedxml

# Windows artefacts
python-evtx  regipy  LnkParse3

# Threat intelligence
stix2  taxii2-client  mitreattack-python

# Crypto
cryptography  pycryptodome

# Data / reporting
pandas  pyyaml  markdown
```

---

## Specialist Containers

### sift-remnux — Disk & Memory Forensics

Based on [`digitalsleuth/sift-remnux`](https://github.com/digitalsleuth/sift-remnux) — a pre-built Ubuntu 20.04 image combining the full SIFT workstation and REMnux malware analysis suite.

**Includes:** Autopsy, Sleuth Kit, Volatility3, Plaso, RegRipper, FLOSS, YARA, and hundreds of forensics tools.

> ⚠️ Large image (~7 GB). Build separately, not in parallel.

```bash
# Build and start
docker compose build sift-remnux
docker compose --profile forensics up -d sift-remnux

# SSH into the container
ssh forensics@<server-ip> -p 2233   # default password: forensics
# ⚠️ Change the password immediately: passwd forensics
```

### cracking — Password & Hash Cracking

Based on [`dizcza/docker-hashcat:pocl`](https://hub.docker.com/r/dizcza/docker-hashcat) — hashcat v7.1.1 with CPU/POCL OpenCL, no GPU required.

**Includes:** hashcat, John the Ripper + format converters (zip2john, rar2john, keepass2john), hashid, name-that-hash, rockyou-75.txt wordlist.

```bash
docker compose build cracking && docker compose up -d cracking
```

### crypto-email — Email & Cryptography Forensics

**Includes:** GPG full suite (gnupg2, gpg-agent, gpgsm), mpack/munpack, swaks, eml-analyzer, mail-parser, extract-msg, oletools, pycryptodome, OpenSSL.

```bash
docker compose build crypto-email && docker compose up -d crypto-email
```

### kali — Pentesting & OSINT (on-demand)

Targeted tool installs only — not `kali-linux-headless`. Only tools unique to pentesting that aren't already in the core container.

**Includes:** metasploit-framework, exploitdb/searchsploit, sqlmap, nikto, gobuster, ffuf, dirb, hydra, theharvester, amass, enum4linux, smbclient.

```bash
docker compose build kali
docker compose --profile pentest up -d kali
```

---

## Environment Variables

```env
# Copy .env.example to .env — all fields are optional.
# The platform is fully functional without any of these.

# Enrichment APIs — used by skills that call external reputation services
VIRUSTOTAL_API_KEY=
ABUSEIPDB_API_KEY=
SHODAN_API_KEY=

# NOT required — Claude Code uses your Pro plan OAuth via MCP, not this key
ANTHROPIC_API_KEY=

# ── Investigation service endpoints ──────────────────────────────────────────
# The pipeline reaches these companion services. Defaults are docker service
# names; if a service runs on the host network, set the full URL with your
# host/IP here instead. Nothing is hardcoded in the source.
DEOBFUSCATOR_URL=http://cyberhawk-deobfuscator:3020/deobfuscate
MITM_PROXY=http://ch-ether-proxy:8095
ETHERHAWK_WEBHOOK_URL=http://ch-ether-api:8094/webhook/etherhiding-confirmed

# EtherHawk webhook shared secret — CHANGE THIS to a random value
ETHERHAWK_WEBHOOK_SECRET=change-me-to-a-random-secret

# UI: MITM live-view iframe URL (build-time, Vite) — leave blank to disable
VITE_MITM_URL=
```

---

## Security Notes

> **This platform is designed for self-hosted, LAN-only deployment.**

| Risk | Details |
|---|---|
| **No authentication** | The API (port 3002) and UI (port 8090) have no login. Do not expose these ports to the internet without a reverse proxy with auth (e.g. nginx + htpasswd, Cloudflare Access). |
| **Web terminal is root bash** | `/api/terminal/ws` gives full bash shell inside the container. LAN-only. |
| **CORS is open** | `allow_origins=["*"]` — intentional for LAN use. Restrict to your UI origin for any internet-facing deployment. |
| **Evidence isolation** | All uploaded files stay inside the `cyberhawk-data` Docker volume. Nothing is executed on the host. |
| **Path traversal** | All file API endpoints validate paths via `safe_path()` — escape attempts are blocked. |
| **Secrets** | All API keys injected via `.env` at runtime. Never baked into images. |
| **Skills read-only** | The `skills/` directory is bind-mounted read-only — skills cannot be modified at runtime. |

---

## Folder Structure

```
cyberhawk-docker/
├── docker-compose.yml              ← Full stack definition
├── .env.example                    ← Copy to .env, fill in API keys
├── .gitignore                      ← Secrets, evidence, branding excluded
├── DESIGN.md                       ← Full architecture and design decisions
│
├── cyberhawk-api/                  ← FastAPI backend + MCP server
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── entrypoint.sh
│   └── app/
│       ├── main.py                 ← FastAPI app, CORS, router registration
│       ├── core/workspace.py       ← Path safety, workspace constants
│       ├── defaults/branding.json  ← Default branding config
│       ├── tools/                 ← phishing_browser.py, etherhiding_detector.py
│       └── routers/
│           ├── mcp.py              ← MCP SSE + HTTP transport, all tools
│           ├── investigate.py      ← automated URL + evidence investigation pipeline
│           ├── queue.py            ← upload/investigation queue management
│           ├── files.py            ← Upload, browse, read, write, hash, delete
│           ├── skills.py           ← Skill listing and streaming execution
│           ├── config.py           ← Branding settings + logo management
│           └── terminal.py         ← WebSocket PTY (full bash in browser)
│
├── cyberhawk-ui/                   ← React 18 + Vite frontend
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── src/
│       ├── App.jsx
│       ├── components/CyberHawkUI.jsx   ← Full design system
│       └── pages/
│           ├── Dashboard.jsx
│           ├── UploadZone.jsx
│           ├── SubmitUrl.jsx        ← automated URL investigation + live log
│           ├── TriageFile.jsx       ← automated evidence triage + live log
│           ├── MitmPage.jsx         ← MITM live traffic view
│           ├── FileBrowser.jsx
│           ├── ReportViewer.jsx
│           ├── Terminal.jsx
│           ├── Settings.jsx
│           └── NewInvestigation.jsx
│
├── sift-remnux/Dockerfile          ← SIFT + REMnux specialist container
├── cracking/Dockerfile             ← hashcat + John specialist container
├── crypto-email/Dockerfile         ← GPG + email forensics specialist container
├── kali/Dockerfile                 ← Pentest tools specialist container
│
├── skills/                         ← 755 bundled skill methodologies (read-only)
│   └── <skill-name>/
│       ├── SKILL.md                ← Investigation methodology
│       ├── scripts/agent.py        ← Executable skill script
│       └── references/             ← API docs, standards, workflows
│
└── workspace/
    └── config/                     ← Branding config seed (gitignored)
```

---

## Port Reference

| Port | Service | Protocol |
|---|---|---|
| `8090` | CyberHawk Web UI | HTTP |
| `3002` | MCP + API Server | HTTP / SSE / WebSocket |
| `2233` | sift-remnux SSH | SSH (when running) |

Companion services (separate compose stacks, reached via the env-var URLs) expose their own ports — e.g. the deobfuscator on `3020` and the MITM proxy — configurable via `DEOBFUSCATOR_URL` / `MITM_PROXY`.

---

## Updating

```bash
git pull
docker compose up -d --build cyberhawk-api cyberhawk-ui
```

Workspace data (cases, uploads, branding) lives on the `cyberhawk-data` named volume — it persists across all rebuilds.

---

## Troubleshooting

**Build appears stuck**
```bash
docker compose --progress plain build cyberhawk-api
```
Normal first build: 15–20 min. `radare2`, `volatility3`, and `impacket` are the slow steps.

**API not healthy**
```bash
docker compose logs cyberhawk-api --tail 50
```

**MCP not connecting**
```bash
curl http://<server-ip>:3002/api/health   # should return {"status":"ok"}
```
Check `docker compose ps` shows `cyberhawk-api` as `(healthy)`.

**UI blank page**
```bash
docker compose logs cyberhawk-ui
```

**Specialist container out of disk**
```bash
docker system df         # check image + volume usage
docker builder prune -f  # safe — clears build cache only
```

---

## Contributing

Pull requests welcome. Please test changes with `docker compose up --build` before submitting.

If a skill references a tool not present in the core container, open an issue with the skill name and the missing binary — we'll add it to the API Dockerfile.

---

<div align="center">

## Built by CyberHawk Threat Intel

<img src="https://media.cyberhawkthreatintel.com/general/1771234479938-y9566.png" width="90" alt="CyberHawk" />

**Empowering security analysts with AI-driven investigation tools**

[🌐 Web App](https://app.cyberhawkthreatintel.com) &nbsp;·&nbsp;
[🌐 Website](https://www.cyberhawkthreatintel.com) &nbsp;·&nbsp;
[🐦 X @cyberhawkintel](https://x.com/cyberhawkintel) &nbsp;·&nbsp;
[▶️ YouTube @cyberhawkconsultancy](https://youtube.com/@cyberhawkconsultancy) &nbsp;·&nbsp;
[▶️ YouTube @cyberhawkk](https://youtube.com/@cyberhawkk) &nbsp;·&nbsp;
[📱 TikTok @cyberhawkthreatintel](https://tiktok.com/@cyberhawkthreatintel) &nbsp;·&nbsp;
[✈️ Telegram @cyberhawkthreatintel](https://t.me/cyberhawkthreatintel)

**© 2026 CyberHawk Threat Intel. All rights reserved.**

`#cyberhawkthreatintel` `#cyberhawkconsultancy` `#cyberhawkk`

> This project is provided for authorised security research, education, and defensive purposes only.
> Always obtain proper authorisation before conducting any security assessment.

</div>
