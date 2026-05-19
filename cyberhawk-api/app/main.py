from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import files, skills, config, mcp, terminal

app = FastAPI(title="CyberHawk API", version="1.0.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    # Wildcard is intentional — this API is designed for self-hosted LAN/localhost use.
    # If you expose port 3002 to the internet, restrict this to your UI origin:
    #   allow_origins=["http://<server-ip>:8090"]
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router,    prefix="/api/files",    tags=["files"])
app.include_router(skills.router,   prefix="/api/skills",   tags=["skills"])
app.include_router(config.router,   prefix="/api/config",   tags=["config"])
app.include_router(terminal.router, prefix="/api/terminal", tags=["terminal"])
app.include_router(mcp.router,                              tags=["mcp"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
