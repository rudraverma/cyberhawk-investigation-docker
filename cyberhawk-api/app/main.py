from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import files, skills, config, mcp, terminal, investigate, queue

app = FastAPI(title="CyberHawk API", version="1.0.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router,       prefix="/api/files",       tags=["files"])
app.include_router(skills.router,      prefix="/api/skills",      tags=["skills"])
app.include_router(config.router,      prefix="/api/config",      tags=["config"])
app.include_router(terminal.router,    prefix="/api/terminal",    tags=["terminal"])
app.include_router(investigate.router, prefix="/api/investigate", tags=["investigate"])
app.include_router(queue.router,       prefix="/api/queue",       tags=["queue"])
app.include_router(mcp.router,                                    tags=["mcp"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
