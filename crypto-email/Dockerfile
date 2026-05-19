# CyberHawk Crypto-Email Container — Cryptography + Email Forensics
# Ref: https://www.gnupg.org/
# Ref: https://veracrypt.io/en/Downloads.html
FROM ubuntu:22.04

LABEL maintainer="CyberHawk Consultancy"
LABEL role="crypto-email"
LABEL description="GPG, VeraCrypt, email forensics — emlAnalyzer, mpack, swaks, OpenSSL"

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# ── System tools ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    curl wget git \
    # GPG full suite
    gnupg2 \
    gpg-agent \
    gpgsm \
    pinentry-curses \
    # Email CLI tools (munpack is a binary inside the mpack package — not a separate pkg)
    mpack \
    mailutils \
    swaks \
    # OpenSSL
    openssl \
    # Misc
    jq \
    p7zip-full \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# ── Python email + crypto packages ───────────────────────────
RUN pip3 install --no-cache-dir \
    extract-msg \
    oletools \
    cryptography \
    pycryptodome \
    beautifulsoup4 \
    requests \
    dnspython \
    impacket \
    mail-parser \
    eml-analyzer

VOLUME ["/workspace"]

# NOTE: Requires these Docker flags for VeraCrypt mount operations:
#   --cap-add SYS_ADMIN
#   --cap-add MKNOD
#   --device=/dev/fuse:/dev/fuse

CMD ["tail", "-f", "/dev/null"]
