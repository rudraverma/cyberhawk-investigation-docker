FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV WORKSPACE=/workspace

# ── System analysis tools (all verified in Debian trixie) ─────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Network
    dnsutils whois curl wget netcat-openbsd nmap tcpdump tshark \
    # File identification & carving
    file binutils exiftool binwalk foremost scalpel \
    # Malware utilities
    ssdeep upx-ucl strace ltrace \
    # Archive extraction
    p7zip-full unzip \
    # Disk forensics
    sleuthkit \
    # AV
    clamav clamav-freshclam \
    # Build & system
    git procps build-essential libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# ── Radare2 — installed from official GitHub release (not in Debian trixie apt)
RUN curl -Ls https://github.com/radareorg/radare2/releases/download/5.9.4/radare2_5.9.4_amd64.deb \
    -o /tmp/r2.deb \
    && dpkg -i /tmp/r2.deb \
    && rm /tmp/r2.deb

# ── Python dependencies ────────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# ── App source ─────────────────────────────────────────────────────────────────
COPY app/ ./app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
