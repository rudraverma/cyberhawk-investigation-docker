# CyberHawk Cracking Container — Password & Hash Cracking
# Base: dizcza/docker-hashcat:pocl — hashcat v7.1.1, Ubuntu 22.04, CPU/POCL OpenCL
FROM dizcza/docker-hashcat:pocl

LABEL maintainer="CyberHawk Consultancy"
LABEL role="cracking"
LABEL description="hashcat v7.1.1 (CPU/POCL), John the Ripper"

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    john john-data wget jq python3 python3-pip \
    && apt-get clean

RUN pip3 install --no-cache-dir hashid name-that-hash

RUN mkdir -p /workspace/wordlists \
    && wget -q "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Leaked-Databases/rockyou-75.txt" \
    -O /workspace/wordlists/rockyou-75.txt || true

VOLUME ["/workspace"]
CMD ["tail", "-f", "/dev/null"]
