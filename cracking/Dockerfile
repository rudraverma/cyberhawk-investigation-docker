# CyberHawk Cracking Container — Password & Hash Cracking
# Base: dizcza/docker-hashcat:pocl — hashcat v7.1.1, Ubuntu 22.04, CPU/POCL OpenCL
# Ref: https://hub.docker.com/r/dizcza/docker-hashcat
# Ref: https://github.com/dizcza/docker-hashcat (pocl branch)
FROM dizcza/docker-hashcat:pocl

LABEL maintainer="CyberHawk Consultancy"
LABEL role="cracking"
LABEL description="hashcat v7.1.1 (CPU/POCL), John the Ripper"

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# ── John the Ripper + supporting tools ───────────────────────
# apt john = format converters (zip2john, rar2john, keepass2john etc.)
# Actual cracking is done by hashcat above
RUN apt-get update && apt-get install -y --no-install-recommends \
    john \
    john-data \
    wget \
    jq \
    python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# ── Hash identifier tools ─────────────────────────────────────
RUN pip3 install --no-cache-dir \
    hashid \
    name-that-hash

# ── Wordlists ─────────────────────────────────────────────────
# rockyou-75.txt = top 75% most common passwords (~479 KB, plain text)
# Full rockyou.txt.tar.gz available at SecLists if needed
RUN mkdir -p /workspace/wordlists \
    && wget -q "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Leaked-Databases/rockyou-75.txt" \
    -O /workspace/wordlists/rockyou-75.txt || true

VOLUME ["/workspace"]

# NOTE GPU passthrough (NVIDIA) — enable in docker-compose.yml:
#   deploy.resources.reservations.devices: driver=nvidia, count=all, capabilities=[gpu]

CMD ["tail", "-f", "/dev/null"]
