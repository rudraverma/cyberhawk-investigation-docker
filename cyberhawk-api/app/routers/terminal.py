import asyncio
import os
import pty
import select
import termios
import struct
import fcntl

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

WORKSPACE = os.environ.get("WORKSPACE", "/workspace")


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket):
    """
    Full PTY-backed web terminal over WebSocket.
    Client sends: { "type": "input", "data": "<keys>" }
                  { "type": "resize", "cols": N, "rows": N }
    Server sends raw terminal output as text.
    """
    await websocket.accept()

    master_fd, slave_fd = pty.openpty()

    proc = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "--login",
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=WORKSPACE,
        env={**os.environ, "TERM": "xterm-256color", "HOME": "/root"},
    )
    os.close(slave_fd)

    loop = asyncio.get_event_loop()

    async def read_pty():
        while True:
            try:
                r, _, _ = select.select([master_fd], [], [], 0.04)
                if r:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                await asyncio.sleep(0.02)
            except OSError:
                break

    reader = asyncio.ensure_future(read_pty())

    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "input":
                os.write(master_fd, msg["data"].encode())
            elif msg.get("type") == "resize":
                cols = msg.get("cols", 80)
                rows = msg.get("rows", 24)
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ,
                            struct.pack("HHHH", rows, cols, 0, 0))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        reader.cancel()
        try:
            proc.terminate()
            await proc.wait()
        except Exception:
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
