import asyncio
import json
import os
import re
import socket
import ssl
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import dns.resolver
import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.workspace import WORKSPACE, CASES_DIR, UPLOAD_DIR

router = APIRouter()

# ── In-memory task store ──────────────────────────────────────────────────────
_tasks: dict[str, dict] = {}


def _log(task_id: str, msg: str, level: str = "info") -> None:
    if task_id in _tasks:
        _tasks[task_id]["logs"].append(
            {"msg": msg, "level": level, "ts": datetime.now().isoformat()}
        )


def _defang(s: str) -> str:
    return s.replace("http", "hxxp").replace(".", "[.]")


def _run(cmd: list[str], timeout: int = 15) -> tuple[str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return "", str(e)




def _run_and_log(cmd: list[str], cmd_log: Path, timeout: int = 15) -> tuple[str, str]:
    """Run a subprocess command, capture output, AND append full output to commands.log."""
    from datetime import datetime as _dt
    import shlex as _shlex
    stdout, stderr = _run(cmd, timeout)
    try:
        with open(cmd_log, "a", encoding="utf-8") as lf:
            lf.write(f"\n{'='*70}\n")
            lf.write(f"[{_dt.now().isoformat()}] CMD: {_shlex.join(cmd)}\n")
            lf.write(f"STDOUT:\n{stdout or '(empty)'}\n")
            if stderr:
                lf.write(f"STDERR:\n{stderr}\n")
    except Exception:
        pass
    return stdout, stderr


def _save_fetch(data: str | bytes, dest: Path, cmd_log: Path, label: str = "") -> None:
    """Save fetched content (HTML, JSON, binary) to case folder and log the action."""
    from datetime import datetime as _dt
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        dest.write_bytes(data)
    else:
        dest.write_text(data, encoding="utf-8", errors="replace")
    try:
        with open(cmd_log, "a", encoding="utf-8") as lf:
            lf.write(f"\n{'='*70}\n")
            lf.write(f"[{_dt.now().isoformat()}] SAVED: {dest.name}  ({len(data):,} bytes)")
            if label:
                lf.write(f"  [{label}]")
            lf.write("\n")
    except Exception:
        pass


# ── MANDATORY: deobfuscate every payload via :3020 immediately on receipt ─────
# Rule: raw file saved first, then beautified file via cyberhawk-deobfuscator.
# Every step logged to decode_chain.md. No exceptions.
async def _sandbox_execute_js(code: str, timeout_s: int = 10) -> dict:
    """Execute JS in the network-isolated cyberhawk-sandbox (network:none, read_only,
    cap_drop:ALL) via docker exec. Captures fetch/XHR URLs, new Function/eval bodies,
    clipboard writes, and eth_calls that static deobfuscation cannot reach.
    Returns the capture dict, or {} on any failure (never raises)."""
    import os as _os
    _sb = _os.getenv("SANDBOX_CONTAINER", "cyberhawk-sandbox")
    _payload = json.dumps({"code": code, "timeout_ms": min(timeout_s, 10) * 1000})
    try:
        _proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", _sb, "node", "/sandbox/runner.js",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _out, _err = await asyncio.wait_for(
            _proc.communicate(input=_payload.encode("utf-8")), timeout=timeout_s + 20)
        if _out:
            return json.loads(_out.decode("utf-8", errors="replace"))
    except Exception:
        pass
    return {}


async def _deobfuscate_and_save(
    code: str,
    dest_beautified: Path,
    cmd_log: Path,
    decode_chain_path: Path,
    label: str,
    technique: str = "auto-detect",
    raw_dest: Path | None = None,
) -> str:
    """Save raw payload, POST to deobfuscator:3020, save beautified output, append to decode_chain.md."""
    from datetime import datetime as _dt
    DEOBFUSCATOR = os.getenv("DEOBFUSCATOR_URL", "http://cyberhawk-deobfuscator:3020/deobfuscate")
    dest_beautified.parent.mkdir(parents=True, exist_ok=True)

    if raw_dest:
        _save_fetch(code, raw_dest, cmd_log, f"{label} (raw)")

    result_code = code
    _dd = {}
    try:
        async with httpx.AsyncClient(timeout=60) as _hc:
            _dr = await _hc.post(DEOBFUSCATOR, json={"code": code, "label": label})
            if _dr.status_code == 200:
                _dd = _dr.json()
                result_code = (
                    _dd.get("beautified") or _dd.get("result") or
                    _dd.get("code") or _dd.get("deobfuscated") or code
                )
    except Exception:
        pass

    # Honor the detected language for the extension (PowerShell payloads -> .ps1)
    if _dd.get("language") == "powershell" and dest_beautified.suffix == ".js":
        dest_beautified = dest_beautified.with_suffix(".ps1")

    _save_fetch(result_code, dest_beautified, cmd_log, f"{label} (beautified via :3020)")

    # Persist the IOCs the deobfuscator extracted (URLs, IPs, techniques). Previously discarded.
    _iocs = _dd.get("iocs")
    if _iocs:
        _iocs_path = dest_beautified.parent / (dest_beautified.name + ".iocs.json")
        _save_fetch(json.dumps(_iocs, indent=2), _iocs_path, cmd_log, f"{label} extracted IOCs")

    try:
        with open(decode_chain_path, "a", encoding="utf-8") as _dc:
            _dc.write(
                f"\n## {label}\n"
                f"- **Timestamp:** {_dt.now().isoformat()}\n"
                f"- **Technique:** {technique}\n"
                f"- **Input:** {raw_dest.name if raw_dest else 'inline'} ({len(code):,} bytes)\n"
                f"- **Output:** {dest_beautified.name} ({len(result_code):,} bytes)\n"
                f"- **Tool:** cyberhawk-deobfuscator POST http://cyberhawk-deobfuscator:3020/deobfuscate\n"
            )
    except Exception:
        pass

    # ── Sandbox escalation: static beautify left runtime-only obfuscation ────────
    # Execute the ORIGINAL payload in the isolated cyberhawk-sandbox to unwrap
    # atob+XOR+new Function layers and capture C2 URLs / clipboard commands / eth_calls.
    if _dd.get("needs_sandbox"):
        try:
            _sbres = await _sandbox_execute_js(code)
        except Exception:
            _sbres = {}
        if _sbres:
            _save_fetch(json.dumps(_sbres, indent=2),
                        dest_beautified.parent / (dest_beautified.name + ".sandbox.json"),
                        cmd_log, f"{label} sandbox execution")
            _cc = _sbres.get("captured_code") or []
            if _cc:
                _save_fetch("\n\n// ---- next captured block ----\n\n".join(_cc),
                            dest_beautified.parent / (dest_beautified.stem + "_sandbox_decoded.js"),
                            cmd_log, f"{label} sandbox-decoded inner payload")
            _extra = []
            for _nr in (_sbres.get("network_requests") or []):
                _u = _nr.get("url") if isinstance(_nr, dict) else _nr
                if _u:
                    _extra.append(str(_u))
            for _cl in (_sbres.get("clipboard") or []):
                _extra.append("// clipboard-write: " + str(_cl))
            if _extra:
                result_code = result_code + "\n\n/* ---- sandbox-captured (dynamic execution) ---- */\n" + "\n".join(_extra)

    return result_code


# ── Submit URL ────────────────────────────────────────────────────────────────

class UrlBody(BaseModel):
    url: str
    case_name: str = ""
    case_type: str = "Phishing"
    tlp: str = "TLP:AMBER"
    analyst: str = ""


@router.post("/url")
async def submit_url(body: UrlBody):
    raw = body.url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw

    parsed = urlparse(raw)
    domain = (parsed.netloc or parsed.path.split("/")[0]).split(":")[0]

    today = datetime.now().strftime("%Y-%m-%d")
    slug = body.case_name.strip() or re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)[:60]

    # Ensure unique task id if slug already exists
    base_id = f"{today}-{slug}"
    task_id = base_id
    counter = 1
    while task_id in _tasks and _tasks[task_id]["status"] == "running":
        task_id = f"{base_id}-{counter}"
        counter += 1

    case_path = CASES_DIR / today / slug
    case_path.mkdir(parents=True, exist_ok=True)

    _tasks[task_id] = {
        "status": "running",
        "logs": [],
        "case_path": str(case_path.relative_to(WORKSPACE)),
        "url": raw,
        "domain": domain,
    }

    # Write initial notes stub immediately
    (case_path / "notes.md").write_text(
        f"# URL Investigation — {raw}\n\n"
        f"**Submitted:** {datetime.now().isoformat()}\n"
        f"**TLP:** {body.tlp}\n"
        f"**Type:** {body.case_type}\n"
        f"**Analyst:** {body.analyst or 'AUTO'}\n\n"
        f"_Investigation in progress..._\n"
    )

    asyncio.create_task(_investigate(task_id, raw, domain, case_path, body))
    return {
        "ok": True,
        "task_id": task_id,
        "case_path": str(case_path.relative_to(WORKSPACE)),
    }


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/url/{task_id}/stream")
async def stream_task(task_id: str):
    async def gen():
        pointer = 0
        while True:
            task = _tasks.get(task_id)
            if task:
                new_logs = task["logs"][pointer:]
                for entry in new_logs:
                    yield f"data: {json.dumps(entry)}\n\n"
                pointer += len(new_logs)
                if task["status"] != "running":
                    yield (
                        f'data: {json.dumps({"type": "done", "status": task["status"], "case_path": task["case_path"]})}\n\n'
                    )
                    break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/url/{task_id}/status")
def task_status(task_id: str):
    t = _tasks.get(task_id)
    if not t:
        return {"ok": False, "error": "Task not found"}
    return {"ok": True, **{k: v for k, v in t.items() if k != "logs"}, "log_count": len(t["logs"])}


# ── Investigation engine ──────────────────────────────────────────────────────





def _extract_next_stage_urls(code: str, current_domain: str = "") -> list:
    """
    Parse a decoded payload (JS or PS) for next-stage download URLs.
    Looks for: PS iex(irm), DownloadString, JS fetch/XHR, explicit URL vars.
    Returns deduplicated list of candidate URLs.
    """
    found = []

    # PS: iex(irm URL) — grab non-whitespace token, strip any surrounding quotes
    for m in re.finditer(r'(?:irm|iwr)\s+(\S+)', code, re.IGNORECASE):
        u = m.group(1).strip("'\"")
        if not u.startswith("http"):
            u = "https://" + u
        found.append(u)

    # PS: DownloadString('URL') or DownloadFile('URL')
    for m in re.finditer(r'(?:DownloadString|DownloadFile)\s*\((\S+)\)', code, re.IGNORECASE):
        u = m.group(1).strip("'\"")
        if not u.startswith("http"):
            u = "https://" + u
        found.append(u)

    # JS/PS: any https:// URL not matching known RPC/CDN noise
    rpc_skip = ("polygon", "infura", "alchemy", "tatum", "ankr", "tenderly", "cloudflare-eth",
                "publicnode", "qrpc.io", "blastapi", "gateway.tenderly", "bsc-dataseed",
                "jquery", "bootstrap", "googleapis", "cdn.", "ajax.", "fontawesome")
    for m in re.finditer(r'https?://[\w./:?=&%#~-]{12,200}', code):
        u = m.group(0).rstrip(".,;)'\"")
        if not any(skip in u.lower() for skip in rpc_skip):
            found.append(u)

    # Deduplicate preserving order
    seen = set()
    result = []
    for u in found:
        u = u.strip()
        if u and u not in seen:
            seen.add(u)
            result.append(u)
    return result


async def _investigate(task_id: str, url: str, domain: str, case_path: Path, body: UrlBody):
    def log(msg: str, level: str = "info"):
        _log(task_id, msg, level)

    artifacts: dict = {}
    verdict_flags: list[str] = []
    page_html = ""
    ips: list[str] = []

    try:
        log(f"[+] Target: {_defang(url)}")
        log(f"[+] Domain: {_defang(domain)}")
        log(f"[+] Case:   investigations/{case_path.relative_to(WORKSPACE)}")
        cmd_log = case_path / "commands.log"
        cmd_log.write_text(f"# Command Log — URL Investigation\n# Target: {url}\n# Started: {datetime.now().isoformat()}\n\n")

        # decode_chain.md — records every obfuscation layer decoded during investigation
        decode_chain = case_path / "decode_chain.md"
        decode_chain.write_text(
            f"# Decode Chain \u2014 {url}\n"
            f"# Case: {case_path.name} | Started: {datetime.now().isoformat()}\n"
            f"# Every payload decode step is appended below in order.\n"
            f"# Format per step: label, timestamp, technique, input file, output file, tool used.\n\n"
        )

        # ── Case folder subdirectory layout ───────────────────────────────────────────
        # recon/      → DNS, WHOIS, TLS, HTTP headers, port scan
        # page/       → raw HTML, page source, page analysis
        # scripts/    → external scripts + inline injection script
        # blockchain/ → Phase 5.6 EtherHiding evidence (when detected)
        recon_dir = case_path / "recon"
        page_dir  = case_path / "page"
        recon_dir.mkdir(exist_ok=True)
        page_dir.mkdir(exist_ok=True)




        # ── Phase 0: Skills Inventory (MANDATORY) ────────────────────────
        log("", "sep")
        log("[ PHASE 0 ]  SKILLS INVENTORY", "phase")
        log("[!] MANDATORY: Skills checked BEFORE investigation starts", "warn")

        SKILL_MAP = {
            "phishing":  ["phishing", "email", "certificate", "phish"],
            "malware":   ["malware", "pe", "elf", "rootkit", "binary", "cobalt", "beacon", "packer"],
            "c2":        ["command-and-control", "cobalt", "beacon", "c2", "cs-profile"],
            "apt":       ["apt", "campaign", "attribution", "mitre", "kill-chain"],
            "web":       ["web", "sql", "xss", "ssrf", "browser", "api"],
            "network":   ["network", "pcap", "dns", "firewall", "logs"],
            "cloud":     ["cloud", "azure", "aws", "gcp", "kubernetes"],
            "mobile":    ["android", "ios", "apk", "mobile"],
            "memory":    ["memory", "volatility", "heap", "process"],
        }
        DEFAULT_KW = ["phishing", "web", "certificate", "dns", "email"]

        case_lower = (body.case_type or "phishing").lower()
        keywords: list[str] = []
        for k, kw_list in SKILL_MAP.items():
            if k in case_lower or any(kw in case_lower for kw in kw_list):
                keywords.extend(kw_list)
        if not keywords:
            keywords = DEFAULT_KW
        keywords = list(dict.fromkeys(keywords))

        from app.core.workspace import SKILLS_DIR
        applicable: list[str] = []
        try:
            if SKILLS_DIR.exists():
                all_skills = sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir())
                log(f"[+] Skills library: {len(all_skills)} skills available")
                applicable = [s for s in all_skills if any(kw in s for kw in keywords)]
                if applicable:
                    log(f"[+] Applicable for [{body.case_type}]: {len(applicable)} skill(s) matched", "skill")
                    for sk in applicable[:20]:
                        log(f"    ▸ {sk}", "skill")
                    if len(applicable) > 20:
                        log(f"    ... and {len(applicable) - 20} more", "skill")
                else:
                    log("  No keyword-matched skills - general methodology applies", "warn")
            else:
                log("  Skills directory not mounted - skipping library check", "warn")
        except Exception as _e:
            log(f"  Skills check error: {_e}", "error")

        (case_path / "applicable_skills.json").write_text(
            __import__("json").dumps(
                {"case_type": body.case_type, "keywords": keywords, "applicable": applicable},
                indent=2,
            )
        )
        log("[+] applicable_skills.json saved")

        # ── Phase 1: DNS Enumeration ──────────────────────────────────────
        log("", "sep")
        log("[ PHASE 1 ]  DNS ENUMERATION", "phase")
        dns_data: dict[str, list[str]] = {}

        for rtype in ("A", "AAAA", "MX", "TXT", "NS", "CNAME"):
            try:
                answers = dns.resolver.resolve(domain, rtype, lifetime=8)
                records = [str(r) for r in answers]
                dns_data[rtype] = records
                for r in records:
                    log(f"  {rtype:<6}  {_defang(r)}", "dns")
            except Exception:
                dns_data[rtype] = []

        ips = dns_data.get("A", [])
        (recon_dir / "dns_records.json").write_text(json.dumps(dns_data, indent=2))
        log(f"[+] recon/dns_records.json saved  ({sum(len(v) for v in dns_data.values())} records)")
        if ips:
            log(f"[+] Resolved IPs: {', '.join(ips)}")
        artifacts["dns"] = dns_data

        # ── Phase 2: WHOIS ────────────────────────────────────────────────
        log("", "sep")
        log("[ PHASE 2 ]  WHOIS LOOKUP", "phase")
        whois_out, _ = _run_and_log(["whois", domain], cmd_log, timeout=20)
        whois_fields: dict = {}
        if whois_out:
            (recon_dir / "whois.txt").write_text(whois_out)
            log(f"[+] recon/whois.txt saved  ({len(whois_out):,} chars)")
            for pattern, key in [
                (r"Registrar:\s*(.+)",               "Registrar"),
                (r"Creation Date:\s*(.+)",            "Created"),
                (r"Updated Date:\s*(.+)",             "Updated"),
                (r"Registry Expiry Date:\s*(.+)",     "Expires"),
                (r"Registrant Organization:\s*(.+)",  "Org"),
                (r"Registrant Country:\s*(.+)",       "Country"),
                (r"Name Server:\s*(.+)",              "NS"),
            ]:
                m = re.search(pattern, whois_out, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    whois_fields[key] = val
                    log(f"  {key}: {_defang(val)}", "whois")
        else:
            log("  WHOIS returned no data", "warn")
        artifacts["whois"] = whois_fields

        # ── Phase 3: HTTP Analysis ────────────────────────────────────────
        log("", "sep")
        log("[ PHASE 3 ]  HTTP ANALYSIS", "phase")
        http_data: dict = {"status": None, "headers": {}, "redirects": [], "final_url": url}

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=20, verify=False,
                proxy=os.getenv("MITM_PROXY"),
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
            ) as client:
                resp = await client.get(url)
                http_data["status"] = resp.status_code
                http_data["final_url"] = str(resp.url)
                http_data["headers"] = dict(resp.headers)
                http_data["redirects"] = [str(r.url) for r in resp.history]
                page_html = resp.text
                _save_fetch(page_html, page_dir / "raw_page.html", cmd_log, "HTTP fetch")

            log(f"  Status:    {http_data['status']}")
            if http_data["redirects"]:
                log(f"  Redirects: {len(http_data['redirects'])} hop(s)", "warn")
                for r in http_data["redirects"]:
                    log(f"    → {_defang(r)}", "redirect")
            log(f"  Final URL: {_defang(http_data['final_url'])}")

            # Security headers audit
            present_h  = [h for h in resp.headers if h.lower() in ("content-security-policy", "x-frame-options", "strict-transport-security", "x-content-type-options", "referrer-policy", "permissions-policy")]
            sec_names  = {"content-security-policy", "x-frame-options", "strict-transport-security", "x-content-type-options", "referrer-policy"}
            missing_h  = [h for h in sec_names if h not in {k.lower() for k in resp.headers}]
            if present_h:
                log(f"  Sec headers present: {', '.join(present_h)}", "good")
            if missing_h:
                log(f"  Missing sec headers: {', '.join(missing_h)}", "warn")

            server = resp.headers.get("server", "")
            x_powered = resp.headers.get("x-powered-by", "")
            if server:
                log(f"  Server: {server}", "info")
            if x_powered:
                log(f"  X-Powered-By: {x_powered}", "warn")

            (recon_dir / "http_response.json").write_text(json.dumps({
                "status":    http_data["status"],
                "final_url": http_data["final_url"],
                "redirects": http_data["redirects"],
                "headers":   http_data["headers"],
            }, indent=2))
            log(f"[+] recon/http_response.json saved")
            artifacts["http"] = http_data

        except Exception as e:
            log(f"  HTTP request failed: {e}", "error")

        # ── Phase 3.5: Thug — Exploit / Drive-by Detection ───────────────
        log("", "sep")
        log("[ PHASE 3.5 ]  THUG — EXPLOIT / DRIVE-BY DETECTION", "phase")
        try:
            _remnux = os.getenv("REMNUX_CONTAINER", "cyberhawk-sift-remnux")
            _thug_dir = case_path / "thug"
            _thug_dir.mkdir(exist_ok=True)
            _case_rel = str(case_path.relative_to(WORKSPACE))
            _thug_log_dir = f"/workspace/{_case_rel}/thug"
            _thug_cmd = [
                "docker", "exec", _remnux,
                "bash", "-c",
                f"thug -u win7ie90 -F -n '{_thug_log_dir}' '{url}' 2>&1"
            ]
            log(f"  Running Thug against {_defang(url)} ...")
            _loop = asyncio.get_event_loop()
            thug_out, _ = await _loop.run_in_executor(
                None, lambda: _run_and_log(_thug_cmd, cmd_log, timeout=120)
            )
            if thug_out:
                (_thug_dir / "thug_stdout.txt").write_text(thug_out)
                log(f"  [+] thug/thug_stdout.txt saved  ({len(thug_out):,} chars)")
                _exploit_found = bool(re.search(r"Exploit|CVE-\d{4}|shellcode|payload", thug_out, re.IGNORECASE))
                if _exploit_found:
                    log("  [!!!] EXPLOIT OR SHELLCODE DETECTED in Thug output!", "critical")
                    verdict_flags.append("EXPLOIT_DETECTED")
                else:
                    log("  No exploits detected by Thug", "good")
            else:
                log("  Thug produced no output", "warn")
        except FileNotFoundError:
            log("  docker CLI not available — Thug skipped", "warn")
        except Exception as _te:
            log(f"  Thug error: {_te}", "warn")

        # ── Phase 4: TLS Certificate ──────────────────────────────────────
        log("", "sep")
        log("[ PHASE 4 ]  TLS / SSL CERTIFICATE", "phase")
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            loop = asyncio.get_event_loop()
            def _get_cert():
                with socket.create_connection((domain, 443), timeout=10) as raw_sock:
                    with ctx.wrap_socket(raw_sock, server_hostname=domain) as s:
                        return s.getpeercert()
            cert = await loop.run_in_executor(None, _get_cert)

            cert_data = {
                "subject": dict(x[0] for x in cert.get("subject", [])),
                "issuer":  dict(x[0] for x in cert.get("issuer", [])),
                "not_before": cert.get("notBefore", ""),
                "not_after":  cert.get("notAfter", ""),
                "san": [v for t, v in cert.get("subjectAltName", []) if t == "DNS"],
                "version": cert.get("version", ""),
            }
            log(f"  Subject:    {cert_data['subject'].get('commonName', 'N/A')}")
            log(f"  Issuer:     {cert_data['issuer'].get('organizationName', 'N/A')}")
            log(f"  Valid from: {cert_data['not_before']}")
            log(f"  Expires:    {cert_data['not_after']}")
            if cert_data["san"]:
                log(f"  SANs ({len(cert_data['san'])}): {', '.join(_defang(s) for s in cert_data['san'][:6])}")
            (recon_dir / "tls_cert.json").write_text(json.dumps(cert_data, indent=2))
            log(f"[+] recon/tls_cert.json saved")
            artifacts["tls"] = cert_data
        except Exception as e:
            log(f"  TLS check skipped: {e}", "warn")

        # ── Phase 5: Page Content Analysis ───────────────────────────────
        log("", "sep")
        log("[ PHASE 5 ]  PAGE CONTENT ANALYSIS", "phase")
        iocs: dict = {"ips": [], "urls": [], "domains": [], "emails": []}
        page_meta: dict = {}

        if page_html:
            (page_dir / "page_source.html").write_text(page_html)
            log(f"[+] page/page_source.html saved  ({len(page_html):,} bytes)")

            soup = BeautifulSoup(page_html, "lxml")

            title    = (soup.title.string or "").strip() if soup.title else ""
            meta_d   = next((t.get("content", "") for t in soup.find_all("meta") if t.get("name", "").lower() == "description"), "")
            scripts  = [t.get("src", "") for t in soup.find_all("script") if t.get("src")]
            ext_scr  = [s for s in scripts if s.startswith("http")]
            iframes  = [t.get("src", "") for t in soup.find_all("iframe") if t.get("src")]
            forms    = soup.find_all("form")
            links    = [t.get("href", "") for t in soup.find_all("a") if t.get("href", "").startswith("http")]

            log(f"  Title:    {title or '(none)'}")
            if meta_d:
                log(f"  Desc:     {meta_d[:120]}")
            log(f"  Scripts:  {len(scripts)} total, {len(ext_scr)} external")
            log(f"  Iframes:  {len(iframes)}")
            log(f"  Forms:    {len(forms)}")
            log(f"  Ext links:{len(links)}")

            for s in ext_scr[:6]:
                log(f"  ⚠ EXT SCRIPT: {_defang(s)}", "warn")
            for iframe in iframes[:3]:
                log(f"  ⚠ IFRAME: {_defang(iframe)}", "warn")
            for f in forms:
                act = f.get("action", "")
                if act:
                    log(f"  ⚠ FORM ACTION: {_defang(act)}", "warn")

            # IOC extraction
            ip_pat = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
            for ip in set(ip_pat.findall(page_html)):
                octets = ip.split(".")
                if not any(ip.startswith(p) for p in ("127.", "0.", "192.168.", "10.", "172.1", "172.2", "172.3")) and all(int(o) < 256 for o in octets):
                    iocs["ips"].append(ip)

            url_pat = re.compile(r'https?://[^\s\'"<>]{6,200}')
            seen_urls: set = set()
            for u in url_pat.findall(page_html):
                u = u.rstrip(".,;)")
                if u not in seen_urls:
                    seen_urls.add(u)
                    iocs["urls"].append(u)
                if len(iocs["urls"]) >= 40:
                    break

            dom_pat = re.compile(
                r'\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|co|uk|gov|mil|edu|de|ru|cn|xyz|online|info|biz|app|dev)\b',
                re.IGNORECASE,
            )
            for d in set(dom_pat.findall(page_html)):
                if d.lower() != domain.lower() and not d.lower().endswith(f".{domain.lower()}"):
                    iocs["domains"].append(d)
                if len(iocs["domains"]) >= 40:
                    break

            email_pat = re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b')
            iocs["emails"] = list(set(email_pat.findall(page_html)))[:20]

            if iocs["ips"]:
                log(f"  IOC IPs:     {', '.join(iocs['ips'][:5])}", "ioc")
            if iocs["emails"]:
                log(f"  IOC emails:  {', '.join(iocs['emails'][:3])}", "ioc")

            page_meta = {
                "title": title, "meta_description": meta_d,
                "script_count": len(scripts), "external_scripts": ext_scr,
                "iframe_count": len(iframes), "form_count": len(forms),
                "external_links": links[:20],
            }
            (page_dir / "page_analysis.json").write_text(json.dumps(page_meta, indent=2))
            (case_path / "iocs.json").write_text(json.dumps(iocs, indent=2))
            log(f"[+] page/page_analysis.json saved")
            log(f"[+] iocs.json saved  ({sum(len(v) for v in iocs.values())} total IOCs)")
            artifacts["iocs"]      = iocs
            artifacts["page_meta"] = page_meta

        # ── Phase 5.5: Blockchain C2 (EtherHiding) Detection ────────────
        log("", "sep")
        log("[ PHASE 5.5 ]  BLOCKCHAIN C2 / ETHERHIDING DETECTION", "phase")
        try:
            import subprocess as _sp, sys as _sys
            _detector = "/app/app/tools/etherhiding_detector.py"
            _result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _sp.run(
                    [_sys.executable, _detector,
                     "--url", url,
                     "--case", str(case_path),
                     "--webhook-url", os.getenv("ETHERHAWK_WEBHOOK_URL", "http://ch-ether-api:8094/webhook/etherhiding-confirmed"),
                     "--webhook-secret", os.getenv("ETHERHAWK_WEBHOOK_SECRET", ""),
                     "--timeout", "35"],
                    capture_output=True, text=True, timeout=60
                )
            )
            if _result.returncode == 1:
                log("  [!!!] ETHERHIDING DETECTED — eth_call / blockchain C2 found!", "critical")
                log("  [+]  etherhiding_signal.json written", "warn")
                log("  [+]  EtherHawk investigation triggered", "warn")
                artifacts["etherhiding"] = True
            elif _result.returncode == 0:
                log("  [+] No EtherHiding indicators")
            else:
                log(f"  [!] detector error (rc={_result.returncode}): {_result.stderr[:200]}", "warn")
            if _result.stdout.strip():
                _save_fetch(_result.stdout, case_path / "etherhiding_detector.log", cmd_log, "detector stdout")
        except Exception as _e:
            log(f"  [!] Phase 5.5 error: {_e}", "warn")

        # ── Phase 5.5b: EtherHiding grep fallback — runs if CDP hook missed ──────────────────
        # Catches cases where Thug JS engine fails (e.g. TextDecoder not defined) and the
        # CDP hook never fires. Greps Thug output + page source for EtherHiding signatures.
        if not artifacts.get("etherhiding"):
            log("  [5.5b] CDP miss — grep fallback: scanning Thug output + page source...", "info")
            _fb_sigs = {
                "eth_call": False, "text_decoder": False, "new_function": False,
                "xor_array": False, "b64_xor": False, "contract": "", "func_selector": "",
            }
            _fb_sources = []
            _thug_log   = case_path / "thug" / "thug_stdout.txt"
            _pagesrc    = page_dir / "page_source.html"
            if _thug_log.exists():
                _fb_sources.append(("thug_stdout.txt", _thug_log.read_text(errors="replace")))
            if _pagesrc.exists():
                _fb_sources.append(("page_source.html", _pagesrc.read_text(errors="replace")))

            for _fsrc_name, _fsrc_text in _fb_sources:
                if re.search(r"\beth_call\b", _fsrc_text):
                    _fb_sigs["eth_call"] = True
                if re.search(r"new\s+TextDecoder", _fsrc_text):
                    _fb_sigs["text_decoder"] = True
                if re.search(r"new\s+Function\s*\(", _fsrc_text):
                    _fb_sigs["new_function"] = True
                if re.search(r"bxor\b|\[([\d,\s]{40,})\]", _fsrc_text):
                    _fb_sigs["xor_array"] = True
                if re.search(r"atob\s*\(|btoa\s*\(", _fsrc_text) and re.search(r"bxor|xor|\^", _fsrc_text, re.I):
                    _fb_sigs["b64_xor"] = True
                _cm = re.search(r"0x([0-9a-fA-F]{40})", _fsrc_text)
                if _cm and not _fb_sigs["contract"]:
                    _fb_sigs["contract"] = "0x" + _cm.group(1)
                _fm = re.search(r'["\'](0x[0-9a-fA-F]{8})["\'"]', _fsrc_text)
                if _fm and not _fb_sigs["func_selector"]:
                    _fb_sigs["func_selector"] = _fm.group(1)

            _hit_count = sum(1 for k, v in _fb_sigs.items() if v and k not in ("contract", "func_selector"))
            if _fb_sigs["eth_call"] or _hit_count >= 2:
                log(f"  [!!!] ETHERHIDING GREP FALLBACK HIT — eth_call={_fb_sigs['eth_call']}, xor={_fb_sigs['xor_array']}, TextDecoder={_fb_sigs['text_decoder']}, b64xor={_fb_sigs['b64_xor']}", "critical")
                _signal_path = case_path / "etherhiding_signal.json"
                if not _signal_path.exists():
                    _synthetic = {
                        "detected_by": "grep_fallback_phase_5.5b",
                        "eth_calls": [],
                        "contract": _fb_sigs.get("contract", ""),
                        "func_selector": _fb_sigs.get("func_selector", ""),
                        "rpc_url": "",
                        "signatures": _fb_sigs,
                        "note": "CDP hook missed — likely TextDecoder/new Function pattern in injection prevented Thug execution. Signatures confirmed via grep of Thug stdout + page source.",
                    }
                    _save_fetch(json.dumps(_synthetic, indent=2), _signal_path, cmd_log, "synthetic etherhiding_signal.json (grep fallback 5.5b)")
                    log("  [+] etherhiding_signal.json (synthetic) written — Phase 5.6 will proceed", "critical")
                artifacts["etherhiding"] = True
            else:
                log(f"  [+] Grep fallback: no EtherHiding signatures ({len(_fb_sources)} source(s) scanned)", "info")

        # ── Phase 5.6: EtherHiding Deep Analysis (analyzing-etherhiding-blockchain-c2 skill) ──
        if artifacts.get("etherhiding"):
            log("", "sep")
            log("[ PHASE 5.6 ]  ETHERHIDING DEEP ANALYSIS — SKILL: analyzing-etherhiding-blockchain-c2", "phase")
            log("  Automating: page grep, script fetch, RPC replay, ABI decode, IOC extract", "info")
            try:
                import base64 as _b64

                # Create blockchain/ subfolder for all Phase 5.6 evidence
                blockchain_dir = case_path / "blockchain"
                blockchain_dir.mkdir(exist_ok=True)

                _signal_path = case_path / "etherhiding_signal.json"
                _signal     = json.loads(_signal_path.read_text()) if _signal_path.exists() else {}
                _contract   = _signal.get("contract", "")
                _rpc_url    = _signal.get("rpc_url", "")
                _eth_calls  = _signal.get("eth_calls", [])

                # ── Skill Phase 2: grep page_source.html for injection signatures ──
                log("  [2/6] Scanning page_source.html for injection signatures...", "info")
                _html_path = page_dir / "page_source.html"
                if _html_path.exists():
                    _html = _html_path.read_text(errors="replace")
                    _sig_hits = {
                        "eth_call":             bool(re.search(r"eth_call", _html)),
                        "contract_address":     bool(re.search(r"0x[a-fA-F0-9]{40}", _html)),
                        "rpc_providers":        re.findall(r"publicnode|infura\.io|cloudflare-eth|alchemy|ankr\.com|sepolia|base\.org|bsc-dataseed|bnbchain", _html),
                        "eval_atob":            bool(re.search(r"eval\s*\(.*?atob\(", _html, re.DOTALL)),
                        "sync_xhr_false":       bool(re.search(r'\.open\("GET".*?(?:false|!1)', _html, re.DOTALL)),
                        "createElement_script": bool(re.search(r"createElement.*?script", _html, re.DOTALL)),
                        "obfuscated_hex":       bool(re.search(r"_0x[a-z0-9]{4,}", _html)),
                        "clickfix_patterns":    bool(re.search(r"handleCmdCheck|Win\+R|Ctrl\+V|clipboard|powershell", _html, re.I)),
                        "web3_references":      bool(re.search(r"\bweb3\b|\bethers\.js\b", _html, re.I)),
                    }
                    _save_fetch(json.dumps(_sig_hits, indent=2), blockchain_dir / "injection_signatures.json", cmd_log, "skill phase 2")
                    _active = [k for k, v in _sig_hits.items() if v]
                    log(f"  [+] Signatures: {', '.join(_active) or 'none'}", "warn" if _active else "info")

                    # Extract full inline <script> block containing eth_call
                    _eth_blocks = re.findall(
                        r'<script[^>]*>((?:(?!</script>)[\s\S])*?eth_call(?:(?!</script>)[\s\S])*?)</script>',
                        _html, re.IGNORECASE
                    )
                    if _eth_blocks:
                        _raw_inj = max(_eth_blocks, key=len).strip()
                        _inj_hdr = (
                            "# injection_script_raw.js\n"
                            f"# Case: {case_path.name}\n"
                            "# Source: inline <script> block extracted from page_source.html\n"
                            "# Contains: eth_call blockchain C2 lookup + payload loader code\n"
                            "# See injection-code.md for the annotated/beautified version (generated by Claude in Step B)\n\n"
                        )
                        _inj_scripts_dir = case_path / "scripts"
                        _inj_scripts_dir.mkdir(exist_ok=True)
                        _save_fetch(_inj_hdr + _raw_inj, _inj_scripts_dir / "injection_script_raw.js", cmd_log, "inline injection script (raw)")
                        log(f"  [+] scripts/injection_script_raw.js — {len(_raw_inj)} chars (eth_call inline script extracted)", "critical")
                    else:
                        log("  [!] No inline <script> with eth_call found — injection likely in external script", "info")
                else:
                    log("  [!] page_source.html not found — skipping signature scan", "warn")

                # ── Skill Phase 3: fetch every external script ──
                log("  [3/6] Fetching external scripts...", "info")
                _ext_scripts = (artifacts.get("page_meta") or {}).get("external_scripts", [])
                _scripts_dir = case_path / "scripts"
                _scripts_dir.mkdir(exist_ok=True)
                _script_results = []

                async def _fetch_script(su: str) -> dict:
                    try:
                        async with httpx.AsyncClient(follow_redirects=True, timeout=12, proxy=os.getenv("MITM_PROXY")) as _hc:
                            _sr = await _hc.get(su, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
                            })
                            _body = _sr.text
                            _sname = re.sub(r"[^a-zA-Z0-9._-]", "_", su.split("/")[-1].split("?")[0])[:60] or "script"
                            if not _sname.endswith(".js"):
                                _sname += ".js"
                            _save_fetch(_body, _scripts_dir / _sname, cmd_log, f"ext script: {su}")
                            _ind = (
                                _body.count("eth_call") + _body.count("web3") + _body.count("_0x") +
                                _body.count("handleCmdCheck") +
                                int(bool(re.search(r"0x[a-fA-F0-9]{40}", _body))) +
                                int(bool(re.search(r"eval\s*\(.*?atob\(", _body, re.DOTALL)))
                            )
                            return {"url": su, "size": len(_body), "eth_indicators": _ind, "saved": _sname}
                    except Exception as _sex:
                        return {"url": su, "error": str(_sex)}

                if _ext_scripts:
                    _script_results = list(await asyncio.gather(*[_fetch_script(s) for s in _ext_scripts[:10]]))
                    _save_fetch(json.dumps(_script_results, indent=2), blockchain_dir / "external_scripts_analysis.json", cmd_log, "script fetch summary")
                    for _srr in _script_results:
                        _ind = _srr.get("eth_indicators", 0)
                        log(f"  Script: {_srr['url'][:70]}  eth_indicators={_ind}",
                            "critical" if _ind > 3 else ("warn" if _ind > 0 else "info"))
                else:
                    log("  No external scripts in page_analysis.json", "info")

                # ── Skill Phase 4/5: direct RPC replay → ABI decode → C2 URL extract ──
                log("  [4/6] Replaying eth_call to blockchain (direct RPC)...", "info")
                _rpc_responses = []
                for _call in _eth_calls[:3]:
                    _ru     = _call.get("url", _rpc_url)
                    _params = _call.get("params", [])
                    if _ru and _params:
                        try:
                            async with httpx.AsyncClient(timeout=15, proxy=os.getenv("MITM_PROXY")) as _hc:
                                _rr = await _hc.post(_ru,
                                    json={"jsonrpc": "2.0", "method": "eth_call", "params": _params, "id": 1},
                                    headers={"Content-Type": "application/json"})
                                _rpc_responses.append({"request": {"url": _ru, "params": _params}, "response": _rr.json()})
                        except Exception as _rpe:
                            _rpc_responses.append({"request": {"url": _ru}, "error": str(_rpe)})

                _payload_js = ""
                _c2_urls: list[str] = []

                if _rpc_responses:
                    _save_fetch(json.dumps(_rpc_responses, indent=2), blockchain_dir / "blockchain_rpc_response.json", cmd_log, "skill phase 4 — RPC replay")
                    log(f"  [+] blockchain/blockchain_rpc_response.json — {len(_rpc_responses)} call(s) replayed", "warn")

                    _first_hex = (_rpc_responses[0].get("response") or {}).get("result", "")
                    if _first_hex and _first_hex not in ("0x", "0x0", "", None):
                        try:
                            _raw     = _first_hex[2:]
                            _str_len = int(_raw[64:128], 16)
                            _str_hex = _raw[128: 128 + _str_len * 2]
                            _utf8    = bytes.fromhex(_str_hex).decode("utf-8", errors="replace")
                            try:
                                _payload_js = _b64.b64decode(_utf8 + "==").decode("utf-8", errors="replace")
                            except Exception:
                                _payload_js = _utf8
                            _save_fetch(_payload_js, blockchain_dir / "blockchain_decoded_payload.js", cmd_log, "ABI decoded payload")
                            log(f"  [+] blockchain/blockchain_decoded_payload.js — {len(_payload_js)} chars", "critical")
                            log(f"  [>] Preview: {_payload_js[:120].replace(chr(10), ' ')}", "critical")

                            # MANDATORY: beautify immediately via deobfuscator — no exceptions
                            await _deobfuscate_and_save(
                                code=_payload_js,
                                dest_beautified=blockchain_dir / "blockchain_decoded_payload_beautified.js",
                                cmd_log=cmd_log,
                                decode_chain_path=decode_chain,
                                label="Stage-1: blockchain decoded payload",
                                technique="ABI-decode (hex→UTF-8) + base64",
                            )
                            log("  [+] blockchain/blockchain_decoded_payload_beautified.js written", "critical")

                            _n_match = re.search(r'var n\s*=\s*\[([^\]]+)\]', _payload_js)
                            if _n_match:
                                for _b64u in re.findall(r'"([A-Za-z0-9+/=]{10,})"', _n_match.group(1)):
                                    try:
                                        _c2_urls.append(_b64.b64decode(_b64u + "==").decode("utf-8", errors="replace"))
                                    except Exception:
                                        pass
                            _c2_urls += re.findall(r"https?://[^\s'\"<>]{10,200}", _payload_js)
                            _c2_urls = list(dict.fromkeys(_c2_urls))

                            if _c2_urls:
                                _save_fetch(json.dumps({"c2_urls": _c2_urls}, indent=2), blockchain_dir / "c2_urls_extracted.json", cmd_log, "C2 URLs from blockchain payload")
                                for _cu in _c2_urls[:5]:
                                    log(f"  [C2] {_defang(_cu)}", "critical")

                            # MANDATORY: auto-fetch each C2 URL, save raw + beautified immediately
                            # Then parse each beautified payload for next-stage URLs and chain-fetch up to stage 6.
                            log("  [5.6-C] Auto-fetching C2 payload chain and deobfuscating via :3020...", "info")
                            _chain_urls: list[str] = list(_c2_urls[:3])  # start with blockchain-extracted URLs
                            _fetched_urls: set = set()
                            _stage_num = 2

                            while _chain_urls and _stage_num <= 6:
                                _cu = _chain_urls.pop(0)
                                if _cu in _fetched_urls:
                                    continue
                                _fetched_urls.add(_cu)
                                try:
                                    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as _chc:
                                        _cres = await _chc.get(
                                            _cu,
                                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"}
                                        )
                                        _c2_raw = _cres.text

                                    # Detect file type for naming
                                    _is_ps = bool(re.search(r"bxor|iex\s*\(|\$\w+\s*=|\[char\]|DownloadString", _c2_raw, re.I))
                                    _ext = "ps1" if _is_ps else "js"
                                    _raw_name  = f"c2_stage{_stage_num}_raw.{_ext}"
                                    _beau_name = f"c2_stage{_stage_num}_beautified.{_ext}"

                                    _beautified = await _deobfuscate_and_save(
                                        code=_c2_raw,
                                        dest_beautified=case_path / _beau_name,
                                        cmd_log=cmd_log,
                                        decode_chain_path=decode_chain,
                                        label=f"Stage-{_stage_num}: C2 payload from {_defang(_cu)}",
                                        technique="auto-detect (deobfuscator:3020 — JS+PS engine)",
                                        raw_dest=case_path / _raw_name,
                                    )
                                    log(f"  [+] {_raw_name} ({len(_c2_raw):,} bytes) + {_beau_name} saved", "critical")

                                    # Parse beautified output for next-stage URLs and add to chain
                                    _next_urls = _extract_next_stage_urls(_beautified, domain)
                                    _rpc_skip = ("polygon", "infura", "alchemy", "tatum", "ankr", "tenderly",
                                                 "publicnode", "qrpc", "blastapi", "gateway", "bsc-dataseed",
                                                 "jquery", "bootstrap", "googleapis", "cdn.", "ajax.", "fontawesome")
                                    for _nu in _next_urls:
                                        if _nu not in _fetched_urls and not any(s in _nu.lower() for s in _rpc_skip):
                                            _chain_urls.append(_nu)
                                            log(f"  [>] Stage-{_stage_num} references next URL: {_defang(_nu)}", "warn")

                                    _stage_num += 1
                                except Exception as _cfe:
                                    log(f"  [!] C2 auto-fetch failed for stage {_stage_num} ({_defang(_cu)}): {_cfe}", "warn")
                                    _stage_num += 1
                        except Exception as _de:
                            log(f"  [!] ABI decode failed: {_de}", "warn")
                    else:
                        log("  [!] RPC returned empty — contract may have no active payload", "warn")

                # ── Write CLAUDE_MANDATE.md — mandatory next steps for analyst ──
                log("  [5/6] Writing CLAUDE_MANDATE.md...", "info")
                _mandate = (
                    "# ⚠️ CLAUDE MANDATE — EtherHiding Detection — MANDATORY STEPS\n\n"
                    f"**Auto-generated by pipeline — {datetime.now().isoformat()}**\n"
                    "**ALL steps below are mandatory. Case CANNOT be closed without completing Steps A–H.**\n\n"
                    "---\n\n"
                    "## Detection Summary\n"
                    "| Field | Value |\n|---|---|\n"
                    f"| Contract | `{_contract or 'unknown'}` |\n"
                    f"| RPC URL | `{_rpc_url or 'unknown'}` |\n"
                    f"| eth_calls captured | {len(_eth_calls)} |\n"
                    f"| C2 URLs decoded | {len(_c2_urls)} |\n\n"
                    "## MANDATORY FIRST ACTION — READ THE SKILL\n\n"
                    "```\nSkill: analyzing-etherhiding-blockchain-c2\n"
                    "Path:  /workspace/.agents/skills/analyzing-etherhiding-blockchain-c2/SKILL.md\n```\n\n"
                    "**Invoke Skill('etherhiding-investigate') BEFORE any manual action. Non-negotiable.**\n\n"
                    "---\n\n"
                    "## Automated Outputs Already Written (do NOT re-run)\n\n"
                    "| File | Contents |\n|---|---|\n"
                    "| `etherhiding_signal.json` | Contract address, RPC URL, raw eth_calls |\n"
                    "| `captured_evals.json` | eval() / atob() hook captures from browser |\n"
                    "| `etherhiding_signal.json` | Contract address, RPC URL, raw eth_calls (root) |\n"
                    "| `captured_evals.json` | eval() / atob() hook captures from browser (root) |\n"
                    "| `blockchain/injection_signatures.json` | Grep scan of page/page_source.html |\n"
                    "| `blockchain/external_scripts_analysis.json` | All external scripts + eth_indicator scores |\n"
                    "| `blockchain/blockchain_rpc_response.json` | Raw eth_call responses from direct RPC replay |\n"
                    "| `blockchain/blockchain_decoded_payload.js` | ABI-decoded + base64-decoded blockchain payload |\n"
                    "| `blockchain/c2_urls_extracted.json` | C2 URLs extracted from decoded payload |\n"
                    "| `scripts/injection_script_raw.js` | Raw inline <script> eth_call block from page HTML |\n"
                    "| `scripts/` | Every external script saved individually |\n"
                    "| `page/page_source.html` | Full page HTML (used for grep/analysis) |\n\n"
                    "---\n\n"
                    "## MANDATORY REMAINING STEPS\n\n"
                    "### Step A — Read ALL automated outputs\n"
                    "Read every file listed above. Do not skip any.\n\n"
                    "### Step B — Injection script analysis + generate injection-code.md (MANDATORY)\n"
                    "1. Read `scripts/injection_script_raw.js` (pipeline-extracted inline script) if it exists.\n"
                    "   OR identify the injection script from `scripts/` (external injection) if not.\n"
                    "2. Write `injection-code.md` to the case folder with this EXACT structure:\n"
                    "   - SECTION 1: `## Raw Injected Script` — full raw script in a code block (unchanged)\n"
                    "   - SECTION 2: `## What This Code Does — Annotated` — beautified, block-by-block,\n"
                    "     each block followed by `// ANALYST NOTE: [plain English explanation]`\n"
                    "   - SECTION 3: `## Key Indicators` — every C2 domain, contract address, RPC endpoint,\n"
                    "     obfuscation method, anti-analysis technique, cookie/localStorage key found\n"
                    "3. Read every file in `scripts/`. Note which have eth_indicators > 0.\n"
                    "4. Document all findings in notes.md.\n\n"
                    "### Step C — Review auto-fetched C2 payloads (pipeline already ran this)\n"
                    "The pipeline AUTOMATICALLY fetched each C2 URL, saved raw + beautified, and logged to decode_chain.md.\n"
                    "Files already written by pipeline:\n"
                    "- `c2_stage2_raw.js` + `c2_stage2_beautified.js`\n"
                    "- `c2_stage3_raw.js` + `c2_stage3_beautified.js` (if C2 returned a next stage)\n"
                    "- PowerShell C2 stages are saved as `c2_stageN_beautified.ps1` (auto-detected, not .js)\n"
                    "- `<stage>.iocs.json` — URLs/IPs/techniques the deobfuscator already extracted for that stage\n"
                    "- `<stage>.sandbox.json` + `<stage>_sandbox_decoded.js` — for JS with runtime-only obfuscation\n"
                    "  (atob+XOR+new Function), the isolated sandbox ALREADY executed it and captured the decoded\n"
                    "  inner payload, live C2 fetch/XHR URLs, and clipboard writes — do NOT re-run these manually\n"
                    "- `decode_chain.md` — full record of every decode step, input/output file, key, and tool\n\n"
                    "Your job for Step C:\n"
                    "1. Read `decode_chain.md` first — understand every layer already decoded\n"
                    "2. Read each `c2_stageN_beautified.js` — analyze what the decoded payload does\n"
                    "3. If a beautified file still contains XOR/base64 the deobfuscator did not unwrap:\n"
                    "   a. Extract the encoded array or base64 string\n"
                    "   b. Decode with Python (docker exec) — save decoded output\n"
                    "   c. POST result to http://cyberhawk-deobfuscator:3020/deobfuscate for beautification\n"
                    "   d. Save as `c2_stageN_decoded_final.js`\n"
                    "   e. Append the step to `decode_chain.md` (label, technique, key, input→output)\n"
                    "4. Continue until you reach human-readable code with no further encoding layers\n"
                    "5. Identify malware family from final payload (IOC patterns, API calls, C2 protocol)\n\n"
                    "### Step D — Test ClickFix C2 endpoint (SKILL Phase 8)\n"
                    "Probe: `GET <c2_host>/index.php?callback=handleCmdCheck_<TIMESTAMP>&id=test`\n"
                    "If `\"executed\":true` — C2 is ACTIVE. Save response as `c2_active_command.json`.\n\n"
                    "### Step E — Kill chain documentation (SKILL Phase 10)\n"
                    "Write full kill chain table to notes.md (Stages 1–5).\n\n"
                    "### Step F — IOC classification (SKILL Phase 11)\n"
                    "Victim domain → `domain`, to_ids=FALSE\n"
                    "C2 payload server → `domain`, to_ids=TRUE\n"
                    "Contract address → `text`, to_ids=FALSE\n\n"
                    "### Step G — MISP push and publish (SKILL Phase 12, MANDATORY)\n"
                    "1. Create MISP event, add IOCs, tag tlp:amber\n"
                    "2. **PUBLISH** via `mcp__misp-mcp__misp_publish_event` — do NOT leave as draft\n"
                    "3. Write MISP event ID to top of iocs.json\n\n"
                    "### Step H — Write report.md (SKILL Phase 13)\n"
                    "Full incident report. ALL IOCs defanged. No HTML unless Rudra explicitly asks.\n\n"
                    "---\n\n"
                    "## ARTIFACT STANDARDS — MANDATORY FOR ALL FILES IN CASE FOLDER\n\n"
                    "Every file saved to the case folder MUST follow these rules:\n"
                    "- **Header comment at top**: what the file is, where it came from, what it contains\n"
                    "- **Fetched code files**: raw content on top -> `---` separator -> beautified version below\n"
                    "- **Decoded/deobfuscated files**: Approach section at top -> raw input -> decoded output\n"
                    "- **Descriptive filenames**: `<source>_raw.js`, `<source>_decoded.js`, `injection-code.md`\n"
                    "- **Self-documenting**: readable cold, no session context needed — no suspense for the reader\n\n"
                    "---\n\n"
                    "## ENFORCEMENT — ZERO TOLERANCE\n\n"
                    "Claude is NOT permitted to:\n"
                    "- Close this case without completing Steps A–H\n"
                    "- Skip MISP publish (Step G) for any reason\n"
                    "- Write report.md without first completing Steps B–F\n"
                    "- Summarise findings without completing all steps\n\n"
                    "**There is NO ROOM for deviation from this pipeline. — Set by Rudra Verma, CyberHawk TI**\n"
                )
                _save_fetch(_mandate, case_path / "CLAUDE_MANDATE.md", cmd_log, "CLAUDE_MANDATE.md")
                log("  [!!!] CLAUDE_MANDATE.md written — Steps A–H mandatory before case closure", "critical")
                log("  [6/6] Phase 5.6 complete — skill auto-analysis done", "info")

            except Exception as _e56:
                log(f"  [!] Phase 5.6 error: {_e56}", "warn")

        # ── Phase 6: Port Scan ────────────────────────────────────────────
        log("", "sep")
        log("[ PHASE 6 ]  PORT SCAN (top-20 fast scan)", "phase")
        if ips:
            loop = asyncio.get_event_loop()
            nmap_out, _ = await loop.run_in_executor(
                None, lambda: _run_and_log(["nmap", "-F", "--top-ports", "20", "-T4", "--open", ips[0]], cmd_log, timeout=45)
            )
            if nmap_out:
                (recon_dir / "portscan.txt").write_text(nmap_out)
                open_ports = re.findall(r"(\d+/(?:tcp|udp))\s+open\s+(\S+)", nmap_out)
                if open_ports:
                    for port, svc in open_ports:
                        log(f"  OPEN  {port:<15} {svc}", "port")
                else:
                    log("  No open ports found in top-20 scan")
                log(f"[+] recon/portscan.txt saved")
            else:
                log("  nmap returned no output", "warn")
        else:
            log("  Skipped — no resolved IP", "warn")

        # ── Phase 7: Write report ─────────────────────────────────────────
        log("", "sep")
        log("[ PHASE 7 ]  WRITING INVESTIGATION REPORT", "phase")
        notes = _build_notes(url, domain, body, artifacts, page_meta, iocs, ips)
        (case_path / "notes.md").write_text(notes)
        log(f"[+] notes.md written")

        log("", "sep")
        log(f"[✓] Investigation complete — {case_path.relative_to(WORKSPACE)}", "done")
        _tasks[task_id]["status"] = "complete"

    except Exception as exc:
        import traceback
        _log(task_id, f"[!] Unexpected error: {exc}", "error")
        _log(task_id, traceback.format_exc(), "error")
        _tasks[task_id]["status"] = "error"


def _build_notes(url, domain, body, artifacts, page_meta, iocs, ips):
    def df(s):
        return s.replace("http", "hxxp").replace(".", "[.]")

    dns  = artifacts.get("dns",   {})
    http = artifacts.get("http",  {})
    tls  = artifacts.get("tls",   {})
    wh   = artifacts.get("whois", {})
    ts   = datetime.now().isoformat()

    lines = [
        f"# URL Investigation — {df(url)}",
        f"",
        f"**CLASSIFICATION: {body.tlp}** — Authorised analysis only",
        f"",
        "## Metadata",
        f"| Field | Value |",
        f"|---|---|",
        f"| Target | `{df(url)}` |",
        f"| Domain | `{df(domain)}` |",
        f"| Investigated | {ts} |",
        f"| Type | {body.case_type} |",
        f"| Analyst | {body.analyst or 'AUTO'} |",
        f"| TLP | {body.tlp} |",
        "",
        "## DNS Records",
    ]
    for rtype, records in dns.items():
        if records:
            lines.append(f"- **{rtype}:** {', '.join(df(r) for r in records)}")
    if ips:
        lines.append(f"\n**Resolved IPs:** {', '.join(ips)}")

    if wh:
        lines += ["", "## WHOIS"]
        for k, v in wh.items():
            lines.append(f"- **{k}:** {df(v)}")

    if http:
        lines += [
            "", "## HTTP Analysis",
            f"- **Status:** {http.get('status')}",
            f"- **Final URL:** `{df(str(http.get('final_url', url)))}`",
        ]
        if http.get("redirects"):
            chain = " → ".join(df(r) for r in http["redirects"])
            lines.append(f"- **Redirect chain:** {chain}")
        srv = http.get("headers", {}).get("server", "")
        if srv:
            lines.append(f"- **Server:** {srv}")

    if tls:
        lines += [
            "", "## TLS Certificate",
            f"- **Subject:** {tls.get('subject', {}).get('commonName', 'N/A')}",
            f"- **Issuer:** {tls.get('issuer', {}).get('organizationName', 'N/A')}",
            f"- **Valid until:** {tls.get('not_after', 'N/A')}",
        ]
        if tls.get("san"):
            lines.append(f"- **SANs:** {', '.join(df(s) for s in tls['san'][:10])}")

    if page_meta:
        lines += [
            "", "## Page Content",
            f"- **Title:** {page_meta.get('title', 'N/A')}",
            f"- **Description:** {(page_meta.get('meta_description') or 'N/A')[:200]}",
            f"- **Scripts:** {page_meta.get('script_count', 0)} total ({len(page_meta.get('external_scripts', []))} external)",
            f"- **Iframes:** {page_meta.get('iframe_count', 0)}",
            f"- **Forms:** {page_meta.get('form_count', 0)}",
        ]
        ext = page_meta.get("external_scripts", [])
        if ext:
            lines.append("- **External scripts:**")
            for s in ext[:8]:
                lines.append(f"  - `{df(s)}`")

    if any(iocs.values()):
        lines += ["", "## Extracted IOCs"]
        for ioc_type, vals in iocs.items():
            if vals:
                lines.append(f"\n**{ioc_type.upper()} ({len(vals)}):**")
                for v in vals[:15]:
                    lines.append(f"- `{df(v)}`")

    lines += [
        "",
        "## Key Findings",
        "_Populate as investigation progresses._",
        "",
        "## MITRE ATT&CK",
        "_Map observed techniques here._",
        "",
        "## Analyst Notes",
        "_Add observations, hypothesis updates, and next steps here._",
        "",
        "## Case Folder Structure",
        "```",
        "case-slug/",
        "├── notes.md               # analyst working notes",
        "├── report.md              # final incident report",
        "├── iocs.json              # machine-readable IOCs",
        "├── CLAUDE_MANDATE.md      # mandatory steps (EtherHiding only)",
        "├── commands.log           # full command audit trail",
        "├── applicable_skills.json # skills matched",
        "├── recon/                 # DNS, WHOIS, TLS, HTTP headers, port scan",
        "├── page/                  # raw HTML, page source, page analysis",
        "├── scripts/               # external + inline injection scripts",
        "└── blockchain/            # EtherHiding evidence (Phase 5.6 only)",
        "```",
        "",
        "## Artifacts",
        "| File | Description |",
        "|---|---|",
        "| `recon/dns_records.json` | A / AAAA / MX / TXT / NS / CNAME records |",
        "| `recon/whois.txt` | Raw WHOIS registration data |",
        "| `recon/http_response.json` | Status, headers, redirect chain |",
        "| `recon/tls_cert.json` | Certificate subject, issuer, SANs, expiry |",
        "| `recon/portscan.txt` | nmap top-20 port scan result |",
        "| `page/raw_page.html` | Raw HTTP response HTML |",
        "| `page/page_source.html` | Full page HTML (used for grep/injection scan) |",
        "| `page/page_analysis.json` | Title, scripts, iframes, forms, links |",
        "| `iocs.json` | Extracted IPs, URLs, domains, emails |",
        "| `iocs.json` | Extracted IPs, URLs, domains, emails |",
        "| `scripts/` | External scripts + injection_script_raw.js (EtherHiding) |",
        "| `blockchain/` | EtherHiding: RPC responses, decoded payloads, C2 URLs |",
    ]
    return "\n".join(lines) + "\n"


# ═══════════════════════════════════════════════════════════════════════════════
# EVIDENCE FILE INVESTIGATION
# Auto-triggered on every upload. Phase 0 skills check runs FIRST, always.
# ═══════════════════════════════════════════════════════════════════════════════

class EvidenceBody(BaseModel):
    filename: str           # filename in /workspace/upload/
    case_name: str = ""
    case_type: str = "General"
    tlp: str = "TLP:AMBER"
    analyst: str = ""
    notes: str = ""         # analyst notes from upload queue (password, incident ref, context)


# ── File type → skill keyword mapping ────────────────────────────────────────

_EXT_SKILLS: dict[str, list[str]] = {
    # Email
    ".eml": ["email", "phishing", "header", "attachment"],
    ".msg": ["email", "phishing", "header", "outlook"],
    ".mbox": ["email", "phishing", "header"],
    # Executables
    ".exe": ["pe", "malware", "binary", "reverse", "packer", "loader", "dropper", "rootkit"],
    ".dll": ["pe", "malware", "binary", "injection", "hooking"],
    ".sys": ["pe", "rootkit", "driver", "kernel"],
    ".scr": ["pe", "malware"],
    # Scripts
    ".ps1": ["powershell", "script", "malware", "obfuscation"],
    ".vbs": ["vbs", "script", "malware", "macro"],
    ".js":  ["javascript", "script", "malware", "obfuscation"],
    ".py":  ["script", "malware", "python"],
    ".bat": ["script", "malware", "batch"],
    ".sh":  ["script", "malware", "shell"],
    # Office / documents
    ".doc":  ["office", "macro", "maldoc", "vba", "phishing"],
    ".docx": ["office", "macro", "maldoc", "oxml", "phishing"],
    ".xls":  ["office", "macro", "maldoc", "vba"],
    ".xlsx": ["office", "macro", "maldoc", "oxml"],
    ".xlsm": ["office", "macro", "maldoc", "vba"],
    ".ppt":  ["office", "macro", "maldoc"],
    ".pptx": ["office", "macro", "maldoc"],
    ".pdf":  ["pdf", "malware", "javascript", "phishing", "embedded"],
    ".rtf":  ["rtf", "maldoc", "exploit"],
    # Shortcuts / LNK
    ".lnk":  ["lnk", "shortcut", "persistence", "malware"],
    ".url":  ["lnk", "shortcut", "phishing"],
    # Archives
    ".zip":  ["archive", "malware", "phishing"],
    ".rar":  ["archive", "malware"],
    ".7z":   ["archive", "malware"],
    ".iso":  ["iso", "malware", "initial-access"],
    ".img":  ["iso", "malware", "initial-access"],
    # Network captures
    ".pcap":   ["pcap", "network", "traffic", "c2", "dns", "exfiltration"],
    ".pcapng": ["pcap", "network", "traffic", "c2"],
    ".cap":    ["pcap", "network", "traffic"],
    # Memory
    ".vmem": ["memory", "volatility", "forensics"],
    ".mem":  ["memory", "volatility", "forensics"],
    ".raw":  ["memory", "forensics"],
    ".dmp":  ["memory", "crash", "forensics"],
    # Android
    ".apk": ["android", "apk", "mobile", "malware"],
    # Linux
    ".elf": ["elf", "linux", "malware", "binary", "rootkit"],
    # Generic
    ".log":  ["logs", "forensics", "timeline"],
    ".evtx": ["eventlog", "forensics", "windows", "timeline"],
    ".reg":  ["registry", "persistence", "forensics"],
}

_MIME_SKILLS: dict[str, list[str]] = {
    "application/x-dosexec":      ["pe", "malware", "binary", "reverse"],
    "application/pdf":            ["pdf", "malware", "phishing"],
    "text/x-shellscript":         ["script", "malware", "shell"],
    "application/zip":            ["archive", "malware"],
    "application/x-rar":          ["archive", "malware"],
    "application/vnd.ms-excel":   ["office", "macro", "maldoc"],
    "application/vnd.ms-word":    ["office", "macro", "maldoc"],
    "message/rfc822":             ["email", "phishing", "header"],
    "application/vnd.tcpdump.pcap": ["pcap", "network", "traffic"],
    "application/x-pcapng":       ["pcap", "network", "traffic"],
    "application/x-7z-compressed": ["archive", "malware"],
    "application/x-iso9660-image": ["iso", "malware"],
    "application/x-elf":          ["elf", "linux", "malware"],
    "application/x-shockwave-flash": ["flash", "exploit"],
}


def _evidence_keywords(filename: str, mime: str, case_type: str) -> list[str]:
    """Derive skill keywords from filename extension + MIME + case type."""
    ext = Path(filename).suffix.lower()
    kw: list[str] = []
    kw.extend(_EXT_SKILLS.get(ext, []))
    for mime_prefix, skills in _MIME_SKILLS.items():
        if mime.startswith(mime_prefix):
            kw.extend(skills)
    # Layer in case type keywords
    ct = case_type.lower()
    extra_map = {
        "phishing": ["phishing", "email", "certificate"],
        "malware":  ["malware", "pe", "elf", "rootkit", "reverse"],
        "ransomware": ["ransomware", "malware", "encryption", "pe"],
        "network":  ["network", "pcap", "dns", "c2"],
        "forensics": ["forensics", "timeline", "artifact"],
        "memory":   ["memory", "volatility"],
        "apt":      ["apt", "campaign", "attribution"],
        "web":      ["web", "sql", "xss", "ssrf"],
    }
    for k, v in extra_map.items():
        if k in ct:
            kw.extend(v)
    if not kw:
        kw = ["malware", "forensics", "triage", "binary", "script"]
    return list(dict.fromkeys(kw))


@router.post("/evidence")
async def investigate_evidence(body: EvidenceBody):
    filename = Path(body.filename).name  # sanitise
    src_file = UPLOAD_DIR / filename
    if not src_file.exists():
        from fastapi import HTTPException
        raise HTTPException(404, f"File not found in upload queue: {filename}")

    today = datetime.now().strftime("%Y-%m-%d")
    stem  = re.sub(r"[^a-z0-9]+", "-", filename.lower()).strip("-")[:50]
    slug  = (re.sub(r"[^a-z0-9\-]", "", (body.case_name or stem)))[:60]

    base_id = f"ev-{today}-{slug}"
    task_id = base_id
    counter = 1
    while task_id in _tasks and _tasks[task_id]["status"] == "running":
        task_id = f"{base_id}-{counter}"
        counter += 1

    case_path = CASES_DIR / today / slug
    case_path.mkdir(parents=True, exist_ok=True)

    # Copy evidence into case
    dest_file = case_path / filename
    import shutil as _shutil
    _shutil.copy2(str(src_file), str(dest_file))

    _tasks[task_id] = {
        "status": "running",
        "logs": [],
        "case_path": str(case_path.relative_to(WORKSPACE)),
        "filename": filename,
        "type": "evidence",
    }

    analyst_block = (
        f"\n## Analyst Notes\n\n{body.notes}\n"
        if body.notes.strip() else ""
    )
    (case_path / "notes.md").write_text(
        f"# Evidence Triage — {filename}\n\n"
        f"**Submitted:** {datetime.now().isoformat()}\n"
        f"**TLP:** {body.tlp}\n"
        f"**Type:** {body.case_type}\n"
        f"**Analyst:** {body.analyst or 'AUTO'}\n"
        + analyst_block +
        "\n_Triage in progress..._\n"
    )

    asyncio.create_task(_triage_evidence(task_id, dest_file, body, case_path))
    return {
        "ok": True,
        "task_id": task_id,
        "case_path": str(case_path.relative_to(WORKSPACE)),
    }


@router.get("/evidence/{task_id}/stream")
async def stream_evidence(task_id: str):
    async def gen():
        pointer = 0
        while True:
            task = _tasks.get(task_id)
            if task:
                new_logs = task["logs"][pointer:]
                for entry in new_logs:
                    yield f"data: {json.dumps(entry)}\n\n"
                pointer += len(new_logs)
                if task["status"] != "running":
                    yield (
                        f'data: {json.dumps({"type": "done", "status": task["status"], "case_path": task.get("case_path", "")})}'
                        '\n\n'
                    )
                    break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/evidence/{task_id}/status")
def evidence_status(task_id: str):
    t = _tasks.get(task_id)
    if not t:
        return {"ok": False, "error": "Task not found"}
    return {"ok": True, **{k: v for k, v in t.items() if k != "logs"}, "log_count": len(t["logs"])}


# ── Evidence triage engine ────────────────────────────────────────────────────

async def _yara_scan(file_path, case_path, cmd_log, loop, log):
    """YARA scan via the REMnux master rule index. Saves matches; best-effort."""
    try:
        _rel = str(case_path.relative_to(WORKSPACE))
    except Exception:
        _rel = case_path.name
    _rp = f"/workspace/{_rel}/{file_path.name}"
    RX = os.getenv("REMNUX_CONTAINER", "cyberhawk-sift-remnux")
    try:
        out, _ = await loop.run_in_executor(None, lambda: _run_and_log(
            ["docker", "exec", RX, "yara", "-w", "/usr/local/yara-rules/index.yar", _rp],
            cmd_log, timeout=120))
        matches = [ln.split()[0] for ln in out.splitlines() if ln.strip() and " " in ln]
        if matches:
            (case_path / "yara_matches.txt").write_text(out)
            log(f"  [YARA] {len(matches)} match(es): {', '.join(matches[:8])}", "warn")
            log("[+] yara_matches.txt saved")
        else:
            log("  [YARA] no rule matches", "info")
        return matches
    except Exception as _e:
        log(f"  YARA error: {_e}", "warn")
        return []


def _aggregate_iocs(case_path, log):
    """Merge CURATED IOC files into one iocs.json. Only pulls from deobfuscator *.iocs.json,
    c2_urls_extracted.json, and script_iocs.json — NOT strings_iocs.json (which stores raw
    grep lines, e.g. .NET version numbers that look like IPs)."""
    import re as _re
    _ipre = _re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    def _clean_ip(s):
        m = _ipre.search(str(s))
        if not m:
            return None
        ip = m.group(0)
        octs = ip.split(".")
        if any(int(o) > 255 for o in octs):
            return None
        if octs[1:] == ["0", "0", "0"]:          # x.0.0.0 -> version/network noise
            return None
        if ip.startswith(("127.", "0.", "255.")):
            return None
        return ip

    def _allow(n):
        return n.endswith(".iocs.json") or n in ("c2_urls_extracted.json", "script_iocs.json")

    agg = {"urls": [], "ips": [], "domains": [], "techniques": [], "sources": []}
    for jf in sorted(case_path.glob("*.json")):
        if jf.name == "iocs.json" or not _allow(jf.name):
            continue
        try:
            d = json.loads(jf.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        touched = False
        for x in (d.get("urls") or []) + (d.get("c2_urls") or []):
            if isinstance(x, str) and x.startswith("http") and x not in agg["urls"]:
                agg["urls"].append(x); touched = True
        for x in (d.get("ips") or []):
            ip = _clean_ip(x)
            if ip and ip not in agg["ips"]:
                agg["ips"].append(ip); touched = True
        for x in (d.get("domains") or []):
            if isinstance(x, str) and x and x not in agg["domains"]:
                agg["domains"].append(x); touched = True
        for x in (d.get("techniques") or []):
            if isinstance(x, str) and x and x not in agg["techniques"]:
                agg["techniques"].append(x); touched = True
        if touched:
            agg["sources"].append(jf.name)
    agg = {k: v for k, v in agg.items() if v}
    (case_path / "iocs.json").write_text(json.dumps(agg, indent=2))
    n = sum(len(v) for k, v in agg.items() if k != "sources" and isinstance(v, list))
    log(f"[+] iocs.json — aggregated {n} IOC(s) from {len(agg.get('sources', []))} source(s)", "ioc")
    return agg



def _write_tools_mandate(case_path, file_path, produced, log):
    """Write TOOLS_MANDATE.md: what auto-ran + which MCP tools Claude MUST use next (no ad-hoc scripts)."""
    lines = [
        f"# TOOLS MANDATE - {file_path.name}",
        "",
        "**Auto-generated by the evidence pipeline. Read before ANY manual analysis.**",
        "",
        "## Already produced automatically (do NOT re-run or re-script these)",
    ]
    for pn in produced:
        lines.append(f"- `{pn}`")
    lines += [
        "",
        "## For deeper analysis use these tools - NEVER write ad-hoc scripts",
        "",
        "| Goal | Use this (NOT a custom script) |",
        "|---|---|",
        "| Skills methodology | `mcp__cyberhawk__list_skills` then `mcp__cyberhawk__run_skill` |",
        "| PE/ELF capability map | `mcp__remnux__run_capa` |",
        "| Obfuscated strings | `mcp__remnux__run_floss` |",
        "| PE emulation (API/net) | `mcp__remnux__run_speakeasy` |",
        "| Disassembly | `mcp__remnux__run_radare2` |",
        "| APK decompile | `mcp__remnux__analyze_apk` |",
        "| Memory forensics | `mcp__remnux__run_volatility` |",
        "| YARA scan | `mcp__remnux__run_yara` |",
        "| IOC extraction | `mcp__remnux__extract_iocs` |",
        "| Deobfuscate JS/PS | `POST http://cyberhawk-deobfuscator:3020/deobfuscate` (sandbox auto-escalates) |",
        "| Shell in RE box | `mcp__remnux__run_command` |",
        "",
        "## Mandatory next steps",
        "1. Read `notes.md`, `iocs.json`, and every artifact listed above.",
        "2. Run the matched skills in `applicable_skills.json` - non-negotiable.",
        "3. Use the MCP tools above for deeper work. Do NOT reimplement them as Python/bash.",
        "4. Push IOCs to MISP + publish, then write `report.md`.",
        "",
        "**Rule: analyze WITH the linked tools, not by improvising scripts. - Set by Rudra Verma.**",
        "",
    ]
    (case_path / "TOOLS_MANDATE.md").write_text("\n".join(lines))
    log("[+] TOOLS_MANDATE.md written", "critical")


async def _remnux_binary_analysis(file_path, case_path, cmd_log, loop, log, kind="PE"):
    """Drive REMnux capa (MITRE ATT&CK) + FLOSS (obfuscated strings) + Speakeasy (PE emulation)
    on a binary living in the shared /workspace volume. Best-effort: each tool is independent
    and failures are logged, never fatal."""
    try:
        _rel = str(case_path.relative_to(WORKSPACE))
    except Exception:
        _rel = case_path.name
    _rp = f"/workspace/{_rel}/{file_path.name}"
    RX = os.getenv("REMNUX_CONTAINER", "cyberhawk-sift-remnux")

    try:
        log(f"  [{kind}] REMnux capa (MITRE ATT&CK capability map)...", "skill")
        _capa, _ = await loop.run_in_executor(None, lambda: _run_and_log(
            ["docker", "exec", RX, "capa", "-j", _rp], cmd_log, timeout=300))
        if _capa.strip().startswith("{"):
            (case_path / "capa.json").write_text(_capa)
            try:
                _rules = list((json.loads(_capa).get("rules") or {}).keys())
                log(f"  [{kind}] capa: {len(_rules)} capabilities matched", "warn" if _rules else "info")
                for _r in _rules[:12]:
                    log(f"      - {_r}", "warn")
            except Exception:
                pass
            log("[+] capa.json saved")
        elif _capa.strip():
            (case_path / "capa.txt").write_text(_capa)
            log("[+] capa.txt saved")
    except Exception as _e:
        log(f"  capa error: {_e}", "warn")

    try:
        log(f"  [{kind}] REMnux FLOSS (deobfuscated/stack strings)...", "skill")
        _floss, _ = await loop.run_in_executor(None, lambda: _run_and_log(
            ["docker", "exec", RX, "floss", "--quiet", "-j", _rp], cmd_log, timeout=300))
        if _floss.strip().startswith("{"):
            (case_path / "floss.json").write_text(_floss)
            log("[+] floss.json saved")
        elif _floss.strip():
            (case_path / "floss.txt").write_text(_floss)
            log("[+] floss.txt saved")
    except Exception as _e:
        log(f"  floss error: {_e}", "warn")

    if kind == "PE":
        try:
            log(f"  [{kind}] REMnux Speakeasy (emulation — API/network capture)...", "skill")
            _spk, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                ["docker", "exec", RX, "speakeasy", "-t", _rp], cmd_log, timeout=180))
            if _spk.strip():
                (case_path / "speakeasy_output.txt").write_text(_spk)
                log("[+] speakeasy_output.txt saved")
        except Exception as _e:
            log(f"  speakeasy error: {_e}", "warn")


def _first2(fpath):
    try:
        with open(fpath, "rb") as _fh:
            return _fh.read(2)
    except Exception:
        return b""


async def _analyze_extracted_file(fpath, case_path, cmd_log, loop, log, tag="extracted"):
    """Dispatch ONE extracted/attached file to the right analyzer. Does NOT re-enter
    archives (prevents infinite recursion). Best-effort per file."""
    e = fpath.suffix.lower()
    try:
        if e in (".ps1", ".vbs", ".js", ".jse", ".bat", ".cmd", ".hta", ".wsf", ".wsh", ".vbe"):
            log(f"  [{tag}] script {fpath.name} -> deobfuscator + sandbox", "skill")
            await _deobfuscate_and_save(
                code=fpath.read_text(errors="replace"), cmd_log=cmd_log,
                dest_beautified=case_path / f"{fpath.stem}_beautified.js",
                decode_chain_path=(case_path / "decode_chain.md"),
                label=f"{tag}: {fpath.name}",
                technique="deobfuscator :3020 + sandbox")
        elif e in (".exe", ".dll", ".sys", ".scr") or _first2(fpath) == b"MZ":
            log(f"  [{tag}] PE {fpath.name} -> REMnux capa/floss/speakeasy", "skill")
            await _remnux_binary_analysis(fpath, case_path, cmd_log, loop, log, kind="PE")
        elif e in (".doc", ".docx", ".docm", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".rtf"):
            log(f"  [{tag}] office {fpath.name} -> olevba", "skill")
            _ov, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                ["olevba", "--decode", str(fpath)], cmd_log, timeout=90))
            if _ov.strip():
                (case_path / f"{fpath.stem}_olevba.txt").write_text(_ov)
        else:
            log(f"  [{tag}] {fpath.name} ({e or 'no-ext'}) saved — no auto-module", "info")
    except Exception as _e:
        log(f"  [{tag}] analyze error {fpath.name}: {_e}", "warn")


async def _triage_evidence(task_id: str, file_path: Path, body: EvidenceBody, case_path: Path):
    def log(msg: str, level: str = "info"):
        _log(task_id, msg, level)

    loop = asyncio.get_event_loop()

    try:
        log(f"[+] File:     {file_path.name}")
        log(f"[+] Case:     investigations/{case_path.relative_to(WORKSPACE)}")
        cmd_log = case_path / "commands.log"
        cmd_log.write_text(f"# Command Log — Evidence Triage\n# File: {file_path.name}\n# Started: {datetime.now().isoformat()}\n\n")

        # ── Phase 0: Skills Inventory (MANDATORY — runs before EVERYTHING) ────
        log("", "sep")
        log("[ PHASE 0 ]  SKILLS INVENTORY", "phase")
        log("[!] MANDATORY: Skills checked BEFORE investigation starts", "warn")

        # Detect MIME type first so skills mapping is accurate
        mime_type = "application/octet-stream"
        try:
            import magic as _magic
            mime_type = _magic.from_file(str(file_path), mime=True)
            log(f"[+] Quick MIME probe: {mime_type}")
        except Exception:
            pass

        keywords = _evidence_keywords(file_path.name, mime_type, body.case_type)
        log(f"[+] Evidence type: {body.case_type} | Extension: {file_path.suffix.lower()} | MIME: {mime_type}")
        log(f"[+] Skill keywords: {', '.join(keywords[:10])}")

        from app.core.workspace import SKILLS_DIR
        applicable: list[str] = []
        try:
            if SKILLS_DIR.exists():
                all_skills = sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir())
                log(f"[+] Skills library: {len(all_skills)} skills available")
                applicable = [s for s in all_skills if any(kw in s for kw in keywords)]
                if applicable:
                    log(f"[+] Applicable skills: {len(applicable)} matched for this evidence type", "skill")
                    for sk in applicable[:25]:
                        log(f"    ▸ {sk}", "skill")
                    if len(applicable) > 25:
                        log(f"    ... and {len(applicable) - 25} more", "skill")
                else:
                    log("  No keyword-matched skills — applying general triage methodology", "warn")
            else:
                log("  Skills directory not mounted", "warn")
        except Exception as _e:
            log(f"  Skills check error: {_e}", "error")

        (case_path / "applicable_skills.json").write_text(
            json.dumps({"filename": file_path.name, "mime": mime_type, "case_type": body.case_type,
                        "keywords": keywords, "applicable": applicable}, indent=2)
        )
        log("[+] applicable_skills.json saved")

        # ── Phase 1: File Identification ──────────────────────────────────────
        log("", "sep")
        log("[ PHASE 1 ]  FILE IDENTIFICATION", "phase")

        fsize = file_path.stat().st_size
        log(f"  Size:      {fsize:,} bytes ({fsize/1024:.1f} KB)")
        log(f"  Extension: {file_path.suffix.lower() or '(none)'}")

        # Full file magic description
        file_out, _ = _run_and_log(["file", "-b", str(file_path)], cmd_log)
        log(f"  Type:      {file_out[:200]}")

        # MIME
        log(f"  MIME:      {mime_type}")

        # Magic bytes (first 16)
        with open(file_path, "rb") as fh:
            magic_bytes = fh.read(16).hex()
        log(f"  Magic:     {magic_bytes[:32]}...")

        # Entropy estimation (sample)
        try:
            import math
            with open(file_path, "rb") as fh:
                data = fh.read(min(65536, fsize))
            counts = [0] * 256
            for b in data:
                counts[b] += 1
            n = len(data)
            entropy = -sum((c/n) * math.log2(c/n) for c in counts if c)
            level_str = "HIGH (packed/encrypted)" if entropy > 7.0 else "MEDIUM" if entropy > 5.5 else "LOW (plaintext)"
            log(f"  Entropy:   {entropy:.2f} / 8.0 — {level_str}",
                "warn" if entropy > 7.0 else "good" if entropy < 5.5 else "info")
        except Exception as _e:
            log(f"  Entropy:   calc failed: {_e}", "warn")

        # ── Phase 2: Cryptographic Hashes ─────────────────────────────────────
        log("", "sep")
        log("[ PHASE 2 ]  HASHING", "phase")

        import hashlib
        md5_, sha1_, sha256_ = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                md5_.update(chunk); sha1_.update(chunk); sha256_.update(chunk)
        hashes = {"md5": md5_.hexdigest(), "sha1": sha1_.hexdigest(), "sha256": sha256_.hexdigest()}
        log(f"  MD5:    {hashes['md5']}")
        log(f"  SHA1:   {hashes['sha1']}")
        log(f"  SHA256: {hashes['sha256']}")
        (case_path / "hashes.json").write_text(json.dumps(hashes, indent=2))
        log("[+] hashes.json saved")

        # ── Phase 3: ExifTool Metadata ─────────────────────────────────────────
        log("", "sep")
        log("[ PHASE 3 ]  METADATA EXTRACTION", "phase")
        exif_out, _ = _run_and_log(["exiftool", "-j", str(file_path)], cmd_log, timeout=20)
        if exif_out:
            try:
                exif_data = json.loads(exif_out)
                (case_path / "metadata.json").write_text(json.dumps(exif_data, indent=2))
                meta = exif_data[0] if exif_data else {}
                for key in ("FileType", "MIMEType", "Author", "Creator", "Producer",
                            "CreateDate", "ModifyDate", "Software", "Title", "Subject",
                            "LastModifiedBy", "Company", "CodePage"):
                    if key in meta and meta[key]:
                        log(f"  {key}: {meta[key]}", "info")
                log(f"[+] metadata.json saved  ({len(exif_data[0]) if exif_data else 0} fields)")
            except Exception:
                log("  exiftool returned non-JSON output", "warn")
        else:
            log("  No metadata extracted", "warn")

        # ── Phase 4: Type-Specific Analysis ───────────────────────────────────
        log("", "sep")
        log("[ PHASE 4 ]  TYPE-SPECIFIC ANALYSIS", "phase")

        ext = file_path.suffix.lower()

        # PE analysis
        if "PE" in file_out or ext in (".exe", ".dll", ".sys", ".scr"):
            log("  [PE] Windows executable detected", "skill")
            try:
                import pefile as _pe
                pe = _pe.PE(str(file_path), fast_load=True)
                pe.parse_data_directories(
                    directories=[_pe.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                 _pe.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
                )
                # Compile time
                ts = pe.FILE_HEADER.TimeDateStamp
                from datetime import datetime as _dt
                comp_time = _dt.utcfromtimestamp(ts).isoformat() if ts else "N/A"
                log(f"  [PE] Compile time:  {comp_time}")

                # Sections
                for sec in pe.sections:
                    name = sec.Name.decode(errors="replace").rstrip("\x00")
                    log(f"  [PE] Section {name:<10} VA={hex(sec.VirtualAddress)}  sz={sec.SizeOfRawData:,}  entropy={sec.get_entropy():.2f}")

                # Imports
                susp_imports = ["VirtualAlloc", "WriteProcessMemory", "CreateRemoteThread",
                                "NtUnmapViewOfSection", "SetWindowsHookEx", "ShellExecute",
                                "URLDownloadToFile", "WinExec", "CreateProcess", "RegSetValue"]
                found_susp = []
                if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
                    dll_count = len(pe.DIRECTORY_ENTRY_IMPORT)
                    log(f"  [PE] Import DLLs: {dll_count}")
                    for entry in pe.DIRECTORY_ENTRY_IMPORT:
                        for imp in entry.imports:
                            if imp.name:
                                iname = imp.name.decode(errors="replace")
                                if iname in susp_imports:
                                    found_susp.append(iname)
                if found_susp:
                    log(f"  [PE] Suspicious imports: {', '.join(found_susp)}", "warn")

                pe_data = {"compile_time": comp_time,
                           "suspicious_imports": found_susp,
                           "sections": [{"name": s.Name.decode(errors="replace").rstrip("\x00"),
                                         "entropy": round(s.get_entropy(), 2),
                                         "size": s.SizeOfRawData} for s in pe.sections]}
                (case_path / "pe_analysis.json").write_text(json.dumps(pe_data, indent=2))
                log("[+] pe_analysis.json saved")
            except Exception as _e:
                log(f"  PE parse error: {_e}", "warn")

            # REMnux deep RE — capa (ATT&CK) + FLOSS + Speakeasy
            await _remnux_binary_analysis(file_path, case_path, cmd_log, loop, log, kind="PE")

        # ELF / Linux binary
        elif ext in (".elf", ".so", ".o") or "ELF " in file_out:
            log("  [ELF] Linux binary detected", "skill")
            await _remnux_binary_analysis(file_path, case_path, cmd_log, loop, log, kind="ELF")

        # Archive — extract (password from analyst notes) then recurse-triage contents
        elif ext in (".zip", ".7z", ".rar", ".iso", ".img", ".cab", ".gz", ".tar"):
            log(f"  [ARCHIVE] {ext.upper()} — extracting + recursing", "skill")
            try:
                _pw = ""
                _m = re.search(r'(?:pass(?:word)?|pwd|pw)\s*[:=]?\s*([^\s,;]+)', body.notes or "", re.I)
                if _m:
                    _pw = _m.group(1)
                    log(f"  [ARCHIVE] using password from analyst notes", "info")
                _exdir = case_path / "extracted"
                _exdir.mkdir(exist_ok=True)
                _7z = ["7z", "x", "-y", f"-o{_exdir}"] + ([f"-p{_pw}"] if _pw else ["-p"]) + [str(file_path)]
                _xo, _ = await loop.run_in_executor(None, lambda: _run_and_log(_7z, cmd_log, timeout=120))
                _files = [p for p in _exdir.rglob("*") if p.is_file()]
                log(f"  [ARCHIVE] extracted {len(_files)} file(s)", "warn" if _files else "info")
                for _ef in _files[:25]:
                    await _analyze_extracted_file(_ef, case_path, cmd_log, loop, log, tag="archived")
            except Exception as _e:
                log(f"  Archive error: {_e}", "warn")

        # APK — apktool manifest + permissions (jadx heavy, skipped in auto pass)
        elif ext == ".apk":
            log("  [APK] Android package — apktool manifest + permissions", "skill")
            try:
                _rel = str(case_path.relative_to(WORKSPACE))
                _rp = f"/workspace/{_rel}/{file_path.name}"
                _out = f"/workspace/{_rel}/apktool_out"
                RX = os.getenv("REMNUX_CONTAINER", "cyberhawk-sift-remnux")
                await loop.run_in_executor(None, lambda: _run_and_log(
                    ["docker", "exec", RX, "apktool", "d", "-f", "-o", _out, _rp], cmd_log, timeout=180))
                _man = case_path / "apktool_out" / "AndroidManifest.xml"
                if _man.exists():
                    _mx = _man.read_text(errors="replace")
                    (case_path / "apk_manifest.xml").write_text(_mx)
                    _perms = sorted(set(re.findall(r'android\.permission\.[A-Z_]+', _mx)))
                    (case_path / "apk_permissions.txt").write_text("\n".join(_perms))
                    _dang = [p for p in _perms if any(d in p for d in ("SMS", "CALL", "CONTACTS", "LOCATION", "RECORD_AUDIO", "CAMERA", "ACCESSIBILITY", "SYSTEM_ALERT", "READ_PHONE"))]
                    log(f"  [APK] {len(_perms)} permissions, {len(_dang)} dangerous: {', '.join(p.split('.')[-1] for p in _dang[:8])}", "warn" if _dang else "info")
                    log("[+] apk_manifest.xml + apk_permissions.txt saved")
                else:
                    log("  [APK] apktool produced no manifest", "warn")
            except Exception as _e:
                log(f"  APK error: {_e}", "warn")

        # PCAP — tshark protocol hierarchy + DNS + HTTP + TLS SNI
        elif ext in (".pcap", ".pcapng", ".cap"):
            log("  [PCAP] Network capture — tshark protocol/DNS/HTTP/TLS extraction", "skill")
            try:
                _proto, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                    ["tshark", "-r", str(file_path), "-q", "-z", "io,phs"], cmd_log, timeout=60))
                if _proto.strip():
                    (case_path / "pcap_protocols.txt").write_text(_proto)
                    log("[+] pcap_protocols.txt saved")
                _dns, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                    ["tshark", "-r", str(file_path), "-Y", "dns.flags.response==0", "-T", "fields", "-e", "dns.qry.name"], cmd_log, timeout=60))
                _dnsq = sorted(set(d for d in _dns.splitlines() if d.strip()))
                if _dnsq:
                    (case_path / "pcap_dns.txt").write_text("\n".join(_dnsq))
                    log(f"  [PCAP] {len(_dnsq)} unique DNS queries", "warn")
                _http, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                    ["tshark", "-r", str(file_path), "-Y", "http.request", "-T", "fields", "-e", "http.host", "-e", "http.request.uri"], cmd_log, timeout=60))
                if _http.strip():
                    (case_path / "pcap_http.txt").write_text(_http)
                    log(f"  [PCAP] {_http.count(chr(10))} HTTP requests", "warn")
                _sni, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                    ["tshark", "-r", str(file_path), "-Y", "tls.handshake.type==1", "-T", "fields", "-e", "tls.handshake.extensions_server_name"], cmd_log, timeout=60))
                _snis = sorted(set(s for s in _sni.splitlines() if s.strip()))
                if _snis:
                    (case_path / "pcap_tls_sni.txt").write_text("\n".join(_snis))
                    log(f"  [PCAP] {len(_snis)} unique TLS SNI hosts", "warn")
                # persist DNS + SNI as IOC domains for aggregation
                _pdoms = sorted(set(_dnsq + _snis))
                if _pdoms:
                    (case_path / "pcap.iocs.json").write_text(json.dumps({"domains": _pdoms}, indent=2))
            except Exception as _e:
                log(f"  PCAP error: {_e}", "warn")

        # Email
        elif ext in (".eml", ".msg") or "RFC 822" in file_out or "SMTP mail" in file_out:
            log("  [EMAIL] Email message detected", "skill")
            try:
                import email as _email
                with open(file_path, "rb") as fh:
                    msg = _email.message_from_bytes(fh.read())
                email_fields = {}
                for hdr in ("From", "To", "Subject", "Date", "Reply-To",
                            "X-Originating-IP", "X-Mailer", "Message-ID",
                            "DKIM-Signature", "Received-SPF", "Authentication-Results"):
                    val = msg.get(hdr, "")
                    if val:
                        email_fields[hdr] = val
                        log(f"  [{hdr}] {str(val)[:120]}", "info")
                (case_path / "email_headers.json").write_text(json.dumps(email_fields, indent=2))
                log("[+] email_headers.json saved")
                # URLs in body
                _body_urls = []
                for _part in msg.walk():
                    if _part.get_content_type() in ("text/plain", "text/html"):
                        try:
                            _pl = _part.get_payload(decode=True)
                            if _pl:
                                _body_urls += re.findall(r'https?://[^\s"\'<>]{10,300}', _pl.decode(errors="replace"))
                        except Exception:
                            pass
                _body_urls = list(dict.fromkeys(_body_urls))
                if _body_urls:
                    (case_path / "email.iocs.json").write_text(json.dumps({"urls": _body_urls}, indent=2))
                    log(f"  [EMAIL] {len(_body_urls)} URL(s) in body", "warn")
                # Attachments — save + recurse-triage each
                _adir = case_path / "attachments"
                _atts = []
                for _part in msg.walk():
                    _fn = _part.get_filename()
                    if not _fn:
                        continue
                    try:
                        _data = _part.get_payload(decode=True)
                        if _data:
                            _adir.mkdir(exist_ok=True)
                            _safe = re.sub(r'[^A-Za-z0-9._-]', '_', _fn)[:80]
                            _ap = _adir / _safe
                            _ap.write_bytes(_data)
                            _atts.append(_safe)
                    except Exception:
                        pass
                if _atts:
                    log(f"  [EMAIL] {len(_atts)} attachment(s): {', '.join(_atts)}", "warn")
                    for _an in _atts[:15]:
                        await _analyze_extracted_file(_adir / _an, case_path, cmd_log, loop, log, tag="attachment")
            except Exception as _e:
                log(f"  Email parse error: {_e}", "warn")

        # Office documents — olevba macro analysis (--decode deobfuscates VBA)
        elif ext in (".doc", ".docx", ".docm", ".xls", ".xlsx", ".xlsm", ".xlsb", ".ppt", ".pptx", ".pptm", ".rtf"):
            log(f"  [OFFICE] {ext.upper()} document — olevba macro analysis", "skill")
            try:
                _ov, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                    ["olevba", "--decode", str(file_path)], cmd_log, timeout=90))
                if _ov.strip():
                    (case_path / "olevba.txt").write_text(_ov)
                    _susp = _ov.count("SUSPICIOUS")
                    _hasmacro = ("VBA MACRO" in _ov) or ("AutoExec" in _ov)
                    log(f"  [OFFICE] macros: {'YES' if _hasmacro else 'none'}  suspicious-keywords: {_susp}",
                        "warn" if (_susp or _hasmacro) else "info")
                    log("[+] olevba.txt saved")
                else:
                    log("  [OFFICE] olevba produced no output", "info")
            except Exception as _e:
                log(f"  olevba error: {_e}", "warn")

        # PDF — pdfid (structure) + pdf-parser (JS) -> deobfuscate embedded JS
        elif ext == ".pdf":
            log("  [PDF] document — pdfid + pdf-parser (JS/OpenAction/Launch)", "skill")
            try:
                _rel = str(case_path.relative_to(WORKSPACE))
                _rp = f"/workspace/{_rel}/{file_path.name}"
                RX = os.getenv("REMNUX_CONTAINER", "cyberhawk-sift-remnux")
                _pid, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                    ["docker", "exec", RX, "pdfid.py", _rp], cmd_log, timeout=60))
                if _pid.strip():
                    (case_path / "pdfid.txt").write_text(_pid)
                    _risky = []
                    for _k in ("/JavaScript", "/JS", "/OpenAction", "/AA", "/Launch", "/EmbeddedFile"):
                        for _ln in _pid.splitlines():
                            if _ln.strip().startswith(_k):
                                try:
                                    if int(_ln.split()[-1]) > 0:
                                        _risky.append(_k)
                                except Exception:
                                    pass
                    log(f"  [PDF] risky markers: {', '.join(_risky) or 'none'}", "warn" if _risky else "info")
                    log("[+] pdfid.txt saved")
                _js, _ = await loop.run_in_executor(None, lambda: _run_and_log(
                    ["docker", "exec", RX, "pdf-parser.py", "--search", "javascript", "--raw", _rp],
                    cmd_log, timeout=60))
                if _js and ("/JS" in _js or "eval" in _js or "app." in _js or "unescape" in _js):
                    (case_path / "pdf_javascript.txt").write_text(_js)
                    log("[+] pdf_javascript.txt saved", "warn")
                    await _deobfuscate_and_save(
                        code=_js, cmd_log=cmd_log,
                        dest_beautified=case_path / "pdf_js_beautified.js",
                        decode_chain_path=(case_path / "decode_chain.md"),
                        label=f"PDF embedded JS: {file_path.name}",
                        technique="pdf-parser extract -> deobfuscator :3020",
                    )
            except Exception as _e:
                log(f"  PDF analysis error: {_e}", "warn")

        # Scripts (obfuscatable) — full deobfuscation + sandbox (SAME engine as URL chain)
        elif ext in (".ps1", ".vbs", ".js", ".jse", ".bat", ".cmd", ".hta", ".wsf", ".wsh", ".vbe"):
            log(f"  [SCRIPT] {ext.upper()} script detected — routing to deobfuscator :3020 + sandbox", "skill")
            try:
                _raw = file_path.read_text(errors="replace")
                _beau = await _deobfuscate_and_save(
                    code=_raw,
                    dest_beautified=case_path / f"{file_path.stem}_beautified.js",  # -> .ps1 if PS detected
                    cmd_log=cmd_log,
                    decode_chain_path=(case_path / "decode_chain.md"),
                    label=f"Uploaded script: {file_path.name}",
                    technique="auto-detect (deobfuscator:3020 JS+PS engine, sandbox on runtime obfuscation)",
                    raw_dest=case_path / f"{file_path.stem}_raw{ext}",
                )
                log(f"  [+] beautified + .iocs.json written (sandbox.json too if runtime-obfuscated)", "critical")
                # Chain-follow any C2 URLs the deobfuscator/sandbox surfaced
                _next = _extract_next_stage_urls(_beau, "")
                if _next:
                    (case_path / "c2_urls_extracted.json").write_text(json.dumps({"c2_urls": _next}, indent=2))
                    log(f"  [>] {len(_next)} next-stage C2 URL(s) surfaced from decoded payload:", "warn")
                    for _u in _next[:5]:
                        log(f"      {_defang(_u)}", "critical")
            except Exception as _e:
                log(f"  Script deobfuscation error: {_e}", "warn")

        # Plain scripts (.sh/.py) — full-file IOC scan (deobfuscator is JS/PS focused)
        elif ext in (".sh", ".py", ".pl", ".rb"):
            log(f"  [SCRIPT] {ext.upper()} script detected — full-file IOC scan", "skill")
            try:
                content = file_path.read_text(errors="replace")
                urls = list(dict.fromkeys(re.findall(r'https?://[^\s\'"<>]+', content)))
                ips  = list(dict.fromkeys(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', content)))
                b64  = re.findall(r'[A-Za-z0-9+/]{40,}={0,2}', content)
                log(f"  URLs: {len(urls)}  IPs: {len(ips)}  B64 blobs: {len(b64)}", "warn" if b64 else "info")
                for u in urls[:8]:
                    log(f"    URL: {_defang(u)}", "ioc")
                (case_path / "script_iocs.json").write_text(json.dumps({"urls": urls, "ips": ips, "b64_blobs": len(b64)}, indent=2))
                log("[+] script_iocs.json saved")
            except Exception as _e:
                log(f"  Script analysis error: {_e}", "warn")

        else:
            log(f"  General triage — no type-specific module for {ext or 'unknown'}")

        # ── Phase 5: Strings Extraction ───────────────────────────────────────
        log("", "sep")
        log("[ PHASE 5 ]  STRINGS EXTRACTION", "phase")

        # Only run strings on binary files or if > 100 bytes
        if fsize > 100:
            strings_out, _ = await loop.run_in_executor(None,
                lambda: _run_and_log(["strings", "-n", "8", str(file_path)], cmd_log, timeout=20))
            if strings_out:
                all_strings = strings_out.split("\n")
                log(f"  Strings extracted: {len(all_strings):,}")

                # Filter for interesting patterns
                url_strings   = [s for s in all_strings if re.search(r'https?://', s)]
                ip_strings    = [s for s in all_strings if re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', s)]
                reg_strings   = [s for s in all_strings if re.search(r'HKEY_|HKLM|HKCU|SOFTWARE\\', s)]
                cmd_strings   = [s for s in all_strings if re.search(r'cmd\.exe|powershell|wscript|cscript', s, re.I)]

                if url_strings:
                    log(f"  URLs in strings ({len(url_strings)}):", "warn")
                    for s in url_strings[:6]:
                        log(f"    {_defang(s)}", "ioc")
                if ip_strings:
                    log(f"  IPs in strings ({len(ip_strings)}):", "warn")
                    for s in ip_strings[:4]:
                        log(f"    {_defang(s)}", "ioc")
                if reg_strings:
                    log(f"  Registry refs ({len(reg_strings)}): {reg_strings[0][:80]}", "warn")
                if cmd_strings:
                    log(f"  CMD/PS refs ({len(cmd_strings)}): {cmd_strings[0][:80]}", "warn")

                iocs_s = {"urls": url_strings, "ips": ip_strings,
                          "registry": reg_strings, "cmdline": cmd_strings}
                (case_path / "strings_iocs.json").write_text(json.dumps(iocs_s, indent=2))
                (case_path / "strings.txt").write_text(strings_out[:500000])
                log("[+] strings.txt + strings_iocs.json saved")

        # ── Phase 5.5: YARA scan (every evidence type) ────────────────────────
        log("", "sep")
        log("[ PHASE 5.5 ]  YARA SCAN", "phase")
        await _yara_scan(file_path, case_path, cmd_log, loop, log)

        # ── Phase 5.6: Aggregate IOCs + Tools Mandate ─────────────────────────
        log("", "sep")
        log("[ PHASE 5.6 ]  IOC AGGREGATION + TOOLS MANDATE", "phase")
        _aggregate_iocs(case_path, log)
        _produced = sorted(p.name for p in case_path.iterdir() if p.is_file())
        _write_tools_mandate(case_path, file_path, _produced, log)

        # ── Phase 6: Write Triage Report ──────────────────────────────────────
        log("", "sep")
        log("[ PHASE 6 ]  TRIAGE REPORT", "phase")

        report = _build_triage_report(file_path, hashes, mime_type, file_out,
                                       applicable, keywords, body)
        (case_path / "notes.md").write_text(report)
        log("[+] notes.md (triage report) written")
        log(f"[+] Case complete: investigations/{case_path.relative_to(WORKSPACE)}", "done")

        _tasks[task_id]["status"] = "complete"

    except Exception as exc:
        import traceback
        log(f"[FATAL] {exc}", "error")
        log(traceback.format_exc(), "error")
        _tasks[task_id]["status"] = "error"


def _build_triage_report(file_path: Path, hashes: dict, mime: str, file_type: str,
                          applicable: list, keywords: list, body: EvidenceBody) -> str:
    ts = datetime.now().isoformat()
    lines = [
        f"# Evidence Triage — {file_path.name}",
        f"",
        f"**CLASSIFICATION: {body.tlp}** — Authorised analysis only",
        f"",
        "## Metadata",
        f"| Field | Value |",
        f"|---|---|",
        f"| Filename | `{file_path.name}` |",
        f"| Size | {file_path.stat().st_size:,} bytes |",
        f"| MIME | `{mime}` |",
        f"| File type | {file_type[:120]} |",
        f"| Triaged | {ts} |",
        f"| Analyst | {body.analyst or 'AUTO'} |",
        f"| TLP | {body.tlp} |",
        f"",
        "## Hashes",
        f"| Algorithm | Hash |",
        f"|---|---|",
        f"| MD5 | `{hashes['md5']}` |",
        f"| SHA1 | `{hashes['sha1']}` |",
        f"| SHA256 | `{hashes['sha256']}` |",
        f"",
        "## Applicable Skills",
        f"_{len(applicable)} skills matched for this evidence type_",
        f"",
    ]
    for sk in applicable[:30]:
        lines.append(f"- `{sk}`")
    lines += [
        f"",
        "## Key Findings",
        "_Populate as investigation progresses._",
        f"",
        "## MITRE ATT&CK",
        "_Map observed techniques here._",
        f"",
        "## Analyst Notes",
        "_Add observations, hypothesis updates, and next steps here._",
        f"",
        "## Artifacts",
        "| File | Description |",
        "|---|---|",
        "| `hashes.json` | MD5 / SHA1 / SHA256 |",
        "| `metadata.json` | ExifTool metadata dump |",
        "| `applicable_skills.json` | Skills matched for this evidence type |",
        "| `strings.txt` | Extracted strings |",
        "| `strings_iocs.json` | URLs / IPs / registry refs in strings |",
    ]
    return "\n".join(lines) + "\n"
