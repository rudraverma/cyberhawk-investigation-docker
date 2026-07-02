#!/usr/bin/env python3
"""
Patches /root/.ghidra/.ghidra_10.4_PUBLIC/tools/CodeBrowser.tool to enable
GhidraMCPPlugin. Run AFTER Ghidra has started once (which creates the .tool file).

Usage: python3 /tool-patch.py
Returns exit code 0 on success, 1 on failure.
"""
import zipfile, io, os, sys
from xml.etree import ElementTree as ET

TOOLS_DIR = "/root/.ghidra/.ghidra_10.4_PUBLIC/tools"
TOOL_PATH = os.path.join(TOOLS_DIR, "CodeBrowser.tool")
PLUGIN_CLASS = "ghidramcp.GhidraMCPPlugin"


def find_tool():
    """Try known locations for CodeBrowser.tool; search JARs as fallback."""
    if os.path.exists(TOOL_PATH):
        print(f"[tool-patch] Found on disk: {TOOL_PATH}")
        with open(TOOL_PATH, "rb") as f:
            return f.read()

    # Not yet created — search Ghidra JARs for the default copy
    print("[tool-patch] Not on disk yet; searching Ghidra JARs...")
    for dirpath, _, files in os.walk("/ghidra"):
        for fname in files:
            if not fname.endswith(".jar"):
                continue
            jarpath = os.path.join(dirpath, fname)
            try:
                with zipfile.ZipFile(jarpath, "r") as jar:
                    for entry in jar.namelist():
                        if entry.endswith("CodeBrowser.tool"):
                            print(f"[tool-patch] Found in JAR: {jarpath} → {entry}")
                            return jar.read(entry)
            except Exception:
                pass

    return None


def patch(tool_bytes):
    """Patch tool.xml inside the .tool ZIP; return new bytes."""
    with zipfile.ZipFile(io.BytesIO(tool_bytes), "r") as zin:
        names = zin.namelist()
        print(f"[tool-patch] ZIP entries: {names}")
        if "tool.xml" not in names:
            print("[tool-patch] ERROR: tool.xml not found in ZIP")
            return None
        xml_bytes = zin.read("tool.xml")
        all_entries = {n: zin.read(n) for n in names}

    xml_str = xml_bytes.decode("utf-8")
    print("[tool-patch] ── tool.xml ────────────────────────────────────────")
    print(xml_str[:3000])
    print("[tool-patch] ────────────────────────────────────────────────────")

    root = ET.fromstring(xml_str)

    # Already patched?
    for elem in root.iter():
        if elem.get("CLASS_NAME") == PLUGIN_CLASS:
            print("[tool-patch] GhidraMCPPlugin already present — nothing to do")
            return tool_bytes

    print(f"[tool-patch] Root tag={root.tag}  attribs={dict(root.attrib)}")
    for child in root:
        print(f"[tool-patch]   <{child.tag} {dict(child.attrib)}>")

    patched = False

    # ── Strategy 1: find any <PLUGIN_PACKAGE ...> or <PACKAGE_MEMBERS ...> ──
    # Ghidra 10.x format: CLASS_NAME on the parent, MEMBER children
    for pkg in list(root.iter("PLUGIN_PACKAGE")) + list(root.iter("PACKAGE")):
        # Add a MEMBER entry identical in style to existing ones
        members = [m for m in pkg if m.get("CLASS_NAME")]
        if members:
            new_member = ET.SubElement(pkg, members[0].tag)
            new_member.attrib = dict(members[0].attrib)
            new_member.set("CLASS_NAME", PLUGIN_CLASS)
            # Copy STATUS attribute from an existing active member if present
            for m in members:
                if m.get("STATUS"):
                    new_member.set("STATUS", m.get("STATUS"))
                    break
            print(f"[tool-patch] Strategy 1: added to <{pkg.tag}> as <{members[0].tag}>")
            patched = True
            break

    # ── Strategy 2: find <ACTIVE_PLUGINS> ──
    if not patched:
        active = root.find(".//ACTIVE_PLUGINS")
        if active is not None:
            new_p = ET.SubElement(active, "PLUGIN")
            new_p.set("CLASS_NAME", PLUGIN_CLASS)
            print("[tool-patch] Strategy 2: added to <ACTIVE_PLUGINS>")
            patched = True

    # ── Strategy 3: find any element that holds CLASS_NAME children ──
    if not patched:
        for elem in root.iter():
            children_with_cls = [c for c in elem if c.get("CLASS_NAME")]
            if len(children_with_cls) >= 2:
                ref = children_with_cls[0]
                new_e = ET.SubElement(elem, ref.tag)
                new_e.set("CLASS_NAME", PLUGIN_CLASS)
                if ref.get("STATUS"):
                    new_e.set("STATUS", ref.get("STATUS"))
                print(f"[tool-patch] Strategy 3: added sibling under <{elem.tag}>")
                patched = True
                break

    # ── Strategy 4: append a top-level <PLUGINS> block ──
    if not patched:
        plugins_elem = ET.SubElement(root, "PLUGINS")
        new_p = ET.SubElement(plugins_elem, "PLUGIN")
        new_p.set("CLASS_NAME", PLUGIN_CLASS)
        print("[tool-patch] Strategy 4: appended new <PLUGINS><PLUGIN> block")
        patched = True

    new_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + ET.tostring(root, encoding="unicode")
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in all_entries.items():
            if name == "tool.xml":
                zout.writestr(name, new_xml.encode("utf-8"))
            else:
                zout.writestr(name, data)

    return buf.getvalue()


def main():
    print("[tool-patch] ── GhidraMCP tool patcher ────────────────────────────")
    tool_bytes = find_tool()
    if tool_bytes is None:
        print("[tool-patch] CodeBrowser.tool not found — Ghidra hasn't run yet")
        sys.exit(1)

    patched = patch(tool_bytes)
    if patched is None:
        print("[tool-patch] Patching failed")
        sys.exit(1)

    os.makedirs(TOOLS_DIR, exist_ok=True)
    with open(TOOL_PATH, "wb") as f:
        f.write(patched)

    print(f"[tool-patch] Wrote patched tool → {TOOL_PATH}")
    print("[tool-patch] ── Done ────────────────────────────────────────────")


if __name__ == "__main__":
    main()
