# CyberHawk Kali Container — Pentesting + Network + OSINT
# Ref: https://www.kali.org/docs/containers/using-kali-docker-images/
# DESIGN NOTE: kali-linux-headless (400+ tools, ~5GB) is deliberately NOT used.
# Only tools unique vs cyberhawk-api core are installed (~1.5GB total).
# Core already provides: nmap, tshark, scapy, impacket, dnspython, curl, wget
FROM kalilinux/kali-rolling

LABEL maintainer="CyberHawk Consultancy"
LABEL role="kali"
LABEL description="Pentesting + OSINT — targeted tool installs, not kali-linux-headless"

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# ── Step 1: Exploitation frameworks ──────────────────────────
# No --no-install-recommends — kali packages declare deps as Recommends
RUN apt-get update && apt-get install -y \
    metasploit-framework \
    exploitdb \
    && rm -rf /var/lib/apt/lists/*

# ── Step 2: Web scanning + fuzzing ───────────────────────────
RUN apt-get update && apt-get install -y \
    sqlmap \
    nikto \
    gobuster \
    ffuf \
    dirb \
    && rm -rf /var/lib/apt/lists/*

# ── Step 3: Password attacks + OSINT + network recon ─────────
RUN apt-get update && apt-get install -y \
    hydra \
    theharvester \
    amass \
    enum4linux \
    smbclient \
    tshark \
    wireshark-common \
    && rm -rf /var/lib/apt/lists/*

# ── Step 4: Python OSINT packages ────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    shodan \
    censys \
    dnspython \
    requests \
    beautifulsoup4 \
    scapy

VOLUME ["/workspace"]
CMD ["tail", "-f", "/dev/null"]
