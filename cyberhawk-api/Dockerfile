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

# ── Docker CLI static binary — for Thug via docker exec into cyberhawk-sift-remnux
# (docker.io Debian package only provides dockerd, not the CLI binary)
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-26.1.3.tgz \
    | tar xz --strip-components=1 -C /usr/local/bin/ docker \
    && docker --version

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

# ── Playwright + Chromium (headless browser for dynamic analysis) ─────────────
# playwright>=1.50.0 adds Debian 13 (trixie) support; no version pin — get latest
RUN pip install playwright playwright-stealth \
    && apt-get update \
    && playwright install --with-deps chromium \
    && rm -rf /root/.cache/ms-playwright/chromium*/chrome-linux/chrome_crashpad_handler \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── App source ─────────────────────────────────────────────────────────────────
COPY app/ ./app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
