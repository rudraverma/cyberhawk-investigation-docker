# CyberHawk Crypto-Email Container — Cryptography + Email Forensics
FROM ubuntu:22.04

LABEL maintainer="CyberHawk Consultancy"
LABEL role="crypto-email"
LABEL description="GPG, email forensics — emlAnalyzer, mpack, swaks, OpenSSL"

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl wget git gnupg2 gpg-agent gpgsm pinentry-curses \
    mpack mailutils swaks openssl jq p7zip-full unzip \
    && apt-get clean

RUN pip3 install --no-cache-dir \
    extract-msg oletools cryptography pycryptodome beautifulsoup4 \
    requests dnspython impacket mail-parser eml-analyzer

VOLUME ["/workspace"]
CMD ["tail", "-f", "/dev/null"]
