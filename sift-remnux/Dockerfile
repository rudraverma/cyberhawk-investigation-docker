# CyberHawk SIFT-REMnux Container — Digital Forensics + Malware Analysis
# Uses digitalsleuth/sift-remnux pre-built image (Ubuntu 20.04)
# which installs full SIFT + REMnux toolsets via CAST installer
# Ref: https://github.com/digitalsleuth/sift-remnux
# Ref: https://docs.remnux.org/install-distro/remnux-as-a-container
FROM digitalsleuth/sift-remnux:latest

LABEL maintainer="CyberHawk Consultancy"
LABEL role="sift-remnux"
LABEL description="Full SIFT + REMnux forensics suite — disk, memory, log, malware analysis"

ENV DEBIAN_FRONTEND=noninteractive

# ── Extra packages on top of base image ──────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# ── Extra Python packages not in base REMnux ─────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    construct \
    dpkt \
    impacket \
    || pip3 install --no-cache-dir \
    construct \
    dpkt \
    impacket

# ── Workspace setup ───────────────────────────────────────────
# Grant forensics user access to shared workspace volume
RUN mkdir -p /workspace && chown -R forensics:forensics /workspace

WORKDIR /workspace

# NOTE: Requires these Docker flags for forensic mount operations:
#   --cap-add SYS_ADMIN
#   --cap-add MKNOD
#   --device=/dev/fuse:/dev/fuse
# SSH available on port 22 (mapped to host port 33)
# Default user: forensics / password: forensics
# To use interactively: docker exec -it cyberhawk-sift-remnux bash

CMD ["tail", "-f", "/dev/null"]
