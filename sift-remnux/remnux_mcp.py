#!/usr/bin/env python3
"""
CyberHawk REMnux MCP Server
FastMCP service running inside the cyberhawk-sift-remnux container.
Exposes REMnux malware analysis tools directly to Claude Code.

Port: 3004 (streamable-http)
Endpoint: http://<server-ip>:3004/mcp

Tools: capa, FLOSS, Speakeasy, radare2, Ghidra headless, apktool/jadx,
       Volatility3, YARA, PE analysis, generic shell command.
"""

from mcp.server.fastmcp import FastMCP
import subprocess
import os
import json
import shutil

MCP_PORT = int(os.getenv("REMNUX_MCP_PORT", "3004"))
mcp = FastMCP("remnux", host="0.0.0.0", port=MCP_PORT, streamable_http_path="/mcp")

WORKSPACE = "/workspace"


def run_cmd(cmd: str, timeout: int = 120, cwd: str = WORKSPACE) -> str:
    """Run a shell command and return combined stdout+stderr."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd
        )
        out = result.stdout or ""
        err = result.stderr or ""
        if err.strip():
            out += f"\n--- STDERR ---\n{err}"
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout}s"
    except Exception as e:
        return f"ERROR: {e}"


def find_tool(name: str) -> str:
    """Return full path of a tool or empty string if not found."""
    path = shutil.which(name)
    return path or ""


# ─── PE / EXE ANALYSIS ────────────────────────────────────────────────────────

@mcp.tool()
def run_capa(file_path: str, output_format: str = "text") -> str:
    """
    Run capa on a PE/ELF binary to detect capabilities and map to MITRE ATT&CK.
    Works on packed binaries — does not require unpacking.
    file_path: absolute path inside container (e.g. /workspace/upload/sample.exe)
    output_format: 'text' (default) or 'json'
    """
    fmt = "-j" if output_format == "json" else ""
    tool = find_tool("capa")
    if not tool:
        return "ERROR: capa not found. Check REMnux installation."
    return run_cmd(f"{tool} {fmt} '{file_path}' 2>&1", timeout=180)


@mcp.tool()
def run_floss(file_path: str, min_length: int = 4) -> str:
    """
    Run FLOSS (FireEye Labs Obfuscated String Solver) to extract obfuscated,
    stack, and tight-loop strings that standard 'strings' misses.
    Works on packed/obfuscated binaries.
    file_path: absolute path inside container
    """
    tool = find_tool("floss")
    if not tool:
        return "ERROR: floss not found. Check REMnux installation."
    return run_cmd(f"{tool} --minimum-length {min_length} '{file_path}' 2>&1", timeout=180)


@mcp.tool()
def run_speakeasy(file_path: str) -> str:
    """
    Emulate a PE/shellcode using Speakeasy to observe runtime behavior without
    executing it. Captures API calls, network activity, file operations.
    Works on packed binaries — emulates the unpacking stub.
    file_path: absolute path inside container
    """
    tool = find_tool("speakeasy")
    if not tool:
        return "ERROR: speakeasy not found. Check REMnux installation."
    out_file = "/tmp/speakeasy_report.json"
    result = run_cmd(
        f"{tool} -t '{file_path}' -r -o '{out_file}' 2>&1",
        timeout=180
    )
    if os.path.exists(out_file):
        try:
            with open(out_file) as f:
                report = json.load(f)
            summary = {
                "api_calls": report.get("apis", [])[:50],
                "network": report.get("network", []),
                "files": report.get("file_access", []),
                "errors": report.get("errors", [])
            }
            result += f"\n\n--- SPEAKEASY REPORT ---\n{json.dumps(summary, indent=2)}"
        except Exception as e:
            result += f"\n(could not parse JSON report: {e})"
    return result


@mcp.tool()
def analyze_pe(file_path: str) -> str:
    """
    Full static PE analysis: file type, entropy, sections, imports,
    suspicious strings. Combines file + pefile + strings.
    file_path: absolute path inside container
    """
    out = f"=== FILE INFO ===\n{run_cmd(f'file {chr(39)}{file_path}{chr(39)}')}\n"
    out += f"\n{run_cmd(f'exiftool {chr(39)}{file_path}{chr(39)} 2>&1 | head -40')}\n"

    out += "\n=== SECTIONS + ENTROPY ===\n"
    out += run_cmd(
        f"""python3 -c "
import pefile, sys
try:
    pe = pefile.PE('{file_path}')
    for s in pe.sections:
        name = s.Name.decode(errors='replace').rstrip(chr(0))
        print(f'  {{name:12}} entropy={{s.get_entropy():.2f}}  raw={{s.SizeOfRawData:>10,}}  virt={{s.Misc_VirtualSize:>10,}}')
    print()
    print('Imports:')
    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        for e in pe.DIRECTORY_ENTRY_IMPORT:
            fns = [i.name.decode(errors='replace') for i in e.imports if i.name]
            print(f'  {{e.dll.decode(errors=chr(114)+chr(101)+chr(112)+chr(108)+chr(97)+chr(99)+chr(101))}}: {{len(fns)}} imports  {{fns[:8]}}')
    else:
        print('  [!] No import directory — likely packed')
except Exception as ex:
    print(f'pefile error: {{ex}}')
" 2>&1"""
    )

    out += "\n=== SUSPICIOUS STRINGS ===\n"
    out += run_cmd(
        f"strings -n 6 '{file_path}' | grep -iE "
        f"'(http|https|ftp|discord|token|password|steal|inject|hook|"
        f"bypass|cmd\\.exe|powershell|reg(sv|add|delete)|hkcu|hklm|"
        f"appdata|startup|\\bsend|\\brecv|socket|wget|curl|base64)' "
        f"| sort -u | head -100"
    )
    return out


# ─── APK / ANDROID ANALYSIS ───────────────────────────────────────────────────

@mcp.tool()
def analyze_apk(apk_path: str, case_name: str = "apk-analysis") -> str:
    """
    Full Android APK analysis using apktool (decompile resources/manifest)
    and jadx (Java source decompilation).
    apk_path: absolute path to APK inside container
    case_name: output subfolder name under /workspace/investigations/
    """
    out_dir = f"{WORKSPACE}/investigations/{case_name}"
    apktool_dir = f"{out_dir}/apktool"
    jadx_dir = f"{out_dir}/jadx"
    os.makedirs(out_dir, exist_ok=True)

    out = "=== APKTOOL (decompile resources + manifest) ===\n"
    apktool = find_tool("apktool")
    if apktool:
        out += run_cmd(f"{apktool} d -f '{apk_path}' -o '{apktool_dir}' 2>&1", timeout=120)
        manifest = f"{apktool_dir}/AndroidManifest.xml"
        if os.path.exists(manifest):
            out += f"\n\n--- AndroidManifest.xml ---\n{open(manifest).read()[:3000]}"
    else:
        out += "apktool not found\n"

    out += "\n\n=== JADX (Java decompilation) ===\n"
    jadx = find_tool("jadx")
    if jadx:
        out += run_cmd(
            f"{jadx} --no-res -d '{jadx_dir}' '{apk_path}' 2>&1 | tail -20",
            timeout=180
        )
        out += f"\n\nDecompiled structure:\n{run_cmd(f'find {chr(39)}{jadx_dir}{chr(39)} -name *.java | head -50')}"
    else:
        out += "jadx not found\n"

    out += f"\n\nOutput saved to: {out_dir}"
    return out


# ─── MEMORY FORENSICS ─────────────────────────────────────────────────────────

@mcp.tool()
def run_volatility(memory_image: str, plugin: str) -> str:
    """
    Run a Volatility3 plugin against a memory image.
    memory_image: absolute path to .mem/.raw/.vmem file
    plugin: Volatility3 plugin name e.g. 'windows.pslist', 'windows.netscan',
            'windows.malfind', 'windows.cmdline', 'windows.dlllist'
    """
    vol = find_tool("vol3") or find_tool("vol") or find_tool("volatility3")
    if not vol:
        return "ERROR: Volatility3 not found. Check REMnux installation."
    return run_cmd(f"{vol} -f '{memory_image}' {plugin} 2>&1 | head -300", timeout=300)


# ─── YARA ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def run_yara(rules_path: str, target_path: str, recursive: bool = False) -> str:
    """
    Scan a file or directory with YARA rules.
    rules_path: path to .yar rules file or directory
    target_path: file or directory to scan
    recursive: scan directories recursively
    """
    tool = find_tool("yara")
    if not tool:
        return "ERROR: yara not found."
    r_flag = "-r" if recursive else ""
    return run_cmd(f"{tool} {r_flag} '{rules_path}' '{target_path}' 2>&1 | head -200", timeout=120)


# ─── DISASSEMBLY / DECOMPILATION ──────────────────────────────────────────────

@mcp.tool()
def run_radare2(file_path: str, commands: str = "aaa;afl;pdf @main") -> str:
    """
    Run radare2 analysis on a binary.
    file_path: absolute path inside container
    commands: semicolon-separated r2 commands
              Examples:
                'aaa;afl' — analyze all, list functions
                'aaa;pdf @entry0' — decompile entry point
                'iz' — list strings
                'ii' — list imports
                'iS' — list sections with entropy
    """
    r2 = find_tool("r2") or find_tool("radare2")
    if not r2:
        return "ERROR: radare2 not found."
    cmds_escaped = commands.replace("'", "\\'")
    return run_cmd(f"{r2} -q -c '{cmds_escaped}' '{file_path}' 2>&1 | head -400", timeout=120)


@mcp.tool()
def ghidra_headless(file_path: str, project_name: str, no_analysis: bool = True) -> str:
    """
    Import a binary into Ghidra using analyzeHeadless.
    no_analysis=True (default): fast import only, saves immediately.
    no_analysis=False: full auto-analysis (slow for large binaries).
    Project stored at /workspace/ghidra-projects/<project_name>
    """
    project_dir = f"{WORKSPACE}/ghidra-projects"
    os.makedirs(project_dir, exist_ok=True)

    headless = ""
    for candidate in [
        "/opt/ghidra/support/analyzeHeadless",
        "/usr/share/ghidra/support/analyzeHeadless",
        "/home/remnux/tools/ghidra/support/analyzeHeadless",
    ]:
        if os.path.exists(candidate):
            headless = candidate
            break

    if not headless:
        search = run_cmd("find /opt /usr /home -name 'analyzeHeadless' 2>/dev/null | head -5")
        return f"ERROR: analyzeHeadless not found.\nSearch result:\n{search}"

    no_analyze_flag = "-noanalysis" if no_analysis else ""
    return run_cmd(
        f"{headless} '{project_dir}' '{project_name}' "
        f"-import '{file_path}' {no_analyze_flag} -overwrite 2>&1 | tail -60",
        timeout=600
    )


# ─── IOC EXTRACTION ───────────────────────────────────────────────────────────

@mcp.tool()
def extract_iocs(file_path: str) -> str:
    """
    Extract IOCs (IPs, domains, URLs, registry keys, file paths, emails)
    from a binary or text file using strings + regex patterns.
    """
    return run_cmd(
        f"""strings -n 4 '{file_path}' | python3 -c "
import sys, re
data = sys.stdin.read()
patterns = {{
    'URLs':       r'https?://[\\w./:?=&%_-]{{8,}}',
    'IPs':        r'\\b(?:\\d{{1,3}}\\.{{3}})\\d{{1,3}}\\b',
    'Domains':    r'\\b(?:[a-zA-Z0-9-]{{1,63}}\\.)+(?:com|net|org|io|ru|cn|tk|top|xyz|info|biz|pw|cc)\\b',
    'Registry':   r'(?:HKLM|HKCU|HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER)\\\\\\\\[\\\\\\\\\\\\\\\\\\\\\\\\w ]+',
    'FilePaths':  r'[A-Za-z]:\\\\\\\\[\\\\\\\\\\\\\\\\\\\\\\\\w. -]+',
    'Emails':     r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}',
}}
for label, pat in patterns.items():
    matches = list(set(re.findall(pat, data)))
    if matches:
        print(f'=== {{label}} ===')
        for m in sorted(matches)[:30]:
            print(f'  {{m}}')
" 2>&1"""
    )


# ─── GENERIC SHELL ────────────────────────────────────────────────────────────

@mcp.tool()
def run_command(command: str, timeout: int = 120) -> str:
    """
    Run any shell command inside the REMnux container.
    Full access to all REMnux tools: capa, floss, speakeasy, radare2,
    volatility3, yara, apktool, jadx, binwalk, exiftool, objdump, etc.
    /workspace/ is the shared evidence volume.
    """
    return run_cmd(command, timeout=timeout)


# ─── INFO ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def remnux_info() -> str:
    """List available REMnux tools and their versions."""
    tools = [
        "capa --version",
        "floss --version",
        "speakeasy --version 2>&1 | head -2",
        "r2 -v 2>&1 | head -1",
        "yara --version",
        "apktool --version",
        "jadx --version 2>&1 | head -1",
        "vol3 --version 2>&1 | head -1 || volatility3 --version 2>&1 | head -1",
        "python3 --version",
        "java -version 2>&1 | head -1",
    ]
    out = "=== CyberHawk REMnux MCP — Tool Inventory ===\n"
    for t in tools:
        result = run_cmd(t, timeout=10)
        out += f"  {t.split()[0]:15}: {result.splitlines()[0] if result else 'not found'}\n"

    for g in ["/opt/ghidra", "/usr/share/ghidra", "/home/remnux/tools/ghidra"]:
        if os.path.exists(g):
            out += f"  {'ghidra':15}: found at {g}\n"
            break
    else:
        out += f"  {'ghidra':15}: not found\n"

    out += f"\n/workspace contents:\n{run_cmd('ls -la /workspace/ 2>/dev/null | head -20')}"
    return out


@mcp.tool()
def run_thug(url: str, user_agent: str = "win7ie90", output_dir: str = "") -> str:
    """Run Thug honeypot client to detect drive-by exploits and malicious JavaScript."""
    tool = find_tool("thug")
    if not tool:
        return "ERROR: thug not found in PATH."
    cmd = f"{tool} -u {user_agent} -F"
    if output_dir:
        import os as _os
        _os.makedirs(output_dir, exist_ok=True)
        cmd += f" -n '{output_dir}' "
    cmd += f" '{url}' 2>&1"
    return run_cmd(cmd, timeout=120)


if __name__ == "__main__":
    print(f"[CyberHawk REMnux MCP] Starting on 0.0.0.0:{MCP_PORT}...")
    mcp.run(transport="streamable-http")
