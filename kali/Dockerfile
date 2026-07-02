# CyberHawk Kali Container — Pentesting + Network + OSINT
FROM kalilinux/kali-rolling

LABEL maintainer="CyberHawk Consultancy"
LABEL role="kali"
LABEL description="Pentesting + OSINT — targeted tool installs"

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

RUN apt-get update && apt-get install -y metasploit-framework exploitdb && apt-get clean
RUN apt-get update && apt-get install -y sqlmap nikto gobuster ffuf dirb && apt-get clean
RUN apt-get update && apt-get install -y hydra theharvester amass enum4linux smbclient tshark wireshark-common && apt-get clean

RUN pip3 install --no-cache-dir --break-system-packages \
    shodan censys dnspython requests beautifulsoup4 scapy

VOLUME ["/workspace"]
CMD ["tail", "-f", "/dev/null"]
