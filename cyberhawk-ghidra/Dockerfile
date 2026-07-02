# ── CyberHawk GhidraMCP — bethington/ghidra-mcp v5.12.0 ─────────────────────
# Headless server: no GUI, no Xvfb, no plugin activation required.
# Java 21 headless server (port 8089) + Python MCP bridge (port 8081 SSE).
#
# Build time: ~10-15 min (downloads Ghidra 12.1 + Maven build once)
# Subsequent builds use Docker layer cache.

# ── Stage 1: Build headless JAR ───────────────────────────────────────────────
FROM eclipse-temurin:21-jdk AS builder

ARG GHIDRA_VERSION=12.1
ARG GHIDRA_DATE=20260513

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget unzip maven git \
    && rm -rf /var/lib/apt/lists/*

# Download Ghidra 12.1
WORKDIR /opt
RUN wget -q --no-check-certificate \
    "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_DATE}.zip" \
    -O ghidra.zip \
    && unzip -q ghidra.zip \
    && rm ghidra.zip \
    && mv ghidra_* ghidra \
    && echo "Ghidra $(cat /opt/ghidra/Ghidra/application.properties | grep application.version) installed"

ENV GHIDRA_HOME=/opt/ghidra

# Install Ghidra JARs into Maven local repository
RUN mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/Generic/lib/Generic.jar        -DgroupId=ghidra -DartifactId=Generic        -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/SoftwareModeling/lib/SoftwareModeling.jar -DgroupId=ghidra -DartifactId=SoftwareModeling -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/Project/lib/Project.jar        -DgroupId=ghidra -DartifactId=Project        -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/Docking/lib/Docking.jar        -DgroupId=ghidra -DartifactId=Docking        -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/Utility/lib/Utility.jar        -DgroupId=ghidra -DartifactId=Utility        -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/Gui/lib/Gui.jar                -DgroupId=ghidra -DartifactId=Gui            -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/FileSystem/lib/FileSystem.jar  -DgroupId=ghidra -DartifactId=FileSystem      -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/Help/lib/Help.jar              -DgroupId=ghidra -DartifactId=Help            -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Features/Base/lib/Base.jar               -DgroupId=ghidra -DartifactId=Base            -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Features/Decompiler/lib/Decompiler.jar   -DgroupId=ghidra -DartifactId=Decompiler      -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/DB/lib/DB.jar                  -DgroupId=ghidra -DartifactId=DB              -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Framework/Emulation/lib/Emulation.jar    -DgroupId=ghidra -DartifactId=Emulation       -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Debug/Debugger-api/lib/Debugger-api.jar  -DgroupId=ghidra -DartifactId=Debugger-api    -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Debug/Framework-TraceModeling/lib/Framework-TraceModeling.jar -DgroupId=ghidra -DartifactId=Framework-TraceModeling -Dversion=${GHIDRA_VERSION} -Dpackaging=jar && \
    mvn -q install:install-file -Dfile=/opt/ghidra/Ghidra/Debug/Debugger-rmi-trace/lib/Debugger-rmi-trace.jar -DgroupId=ghidra -DartifactId=Debugger-rmi-trace -Dversion=${GHIDRA_VERSION} -Dpackaging=jar

# Clone bethington/ghidra-mcp and build the headless server JAR
WORKDIR /build
RUN git clone --depth 1 https://github.com/bethington/ghidra-mcp . \
    && mvn clean package -P headless -DskipTests -q \
    && echo "Built: $(ls target/GhidraMCP-*.jar)"

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl \
    && rm -rf /var/lib/apt/lists/*

# Python MCP bridge dependencies
ENV PIP_BREAK_SYSTEM_PACKAGES=1
RUN pip3 install --no-cache-dir "mcp[cli]>=1.2.0" "requests>=2.31,<3" "httpx>=0.27"

# Copy Ghidra 12.1 from builder
COPY --from=builder /opt/ghidra /opt/ghidra
ENV GHIDRA_HOME=/opt/ghidra

# Copy headless server JAR
RUN mkdir -p /app
COPY --from=builder /build/target/GhidraMCP-*.jar /app/GhidraMCP.jar

# Download bridge + requirements from the same release tag
RUN curl -sL "https://github.com/bethington/ghidra-mcp/releases/download/v5.12.0/bridge_mcp_ghidra.py" \
        -o /app/bridge_mcp_ghidra.py \
    && curl -sL "https://github.com/bethington/ghidra-mcp/releases/download/v5.12.0/requirements.txt" \
        -o /tmp/bridge_requirements.txt \
    && pip3 install --no-cache-dir -r /tmp/bridge_requirements.txt \
    && rm /tmp/bridge_requirements.txt

# Workspace directories (shared via cyberhawk-data volume)
RUN mkdir -p /workspace/ghidra-projects /workspace/ghidra-symbols /data /projects

# Scripts
COPY entrypoint.sh /entrypoint.sh
COPY load_binary.sh /load_binary.sh
RUN chmod +x /entrypoint.sh /load_binary.sh

# Defaults — override via docker-compose environment:
ENV GHIDRA_MCP_PORT=8089
ENV GHIDRA_MCP_URL=http://127.0.0.1:8089
ENV MCP_BRIDGE_PORT=8081
ENV JAVA_OPTS="-Xmx4g -XX:+UseG1GC"

EXPOSE 8081 8089

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -sf http://localhost:8089/check_connection || exit 1

ENTRYPOINT ["/entrypoint.sh"]
