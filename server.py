"""
Bidirectional WebSocket server for the dashboard.

Python → Browser: push_state() sends game snapshots to all connected clients
Browser → Python: read_command() reads button clicks from the browser

Uses:
  - asyncio.Queue for Python→Browser (broadcaster coroutine)
  - threading.Queue for Browser→Python (readable from any thread without asyncio)
"""
import asyncio
import json
import queue as _tqueue
import sys
import threading
import time
from typing import Optional

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import websockets
from websockets.server import WebSocketServerProtocol

_clients:     set  = set()
_loop:        Optional[asyncio.AbstractEventLoop] = None
_out_queue:   Optional[asyncio.Queue] = None   # Python → Browser (asyncio)
_in_queue:    _tqueue.Queue = _tqueue.Queue()  # Browser → Python (threading)
_last_snap:   Optional[str] = None
_pending:     Optional[dict] = None

async def _handler(ws: WebSocketServerProtocol):
    _clients.add(ws)
    try:
        if _last_snap:
            await ws.send(_last_snap)
        async for message in ws:
            _in_queue.put_nowait(message)   # thread-safe, no await needed
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        _clients.discard(ws)


async def _broadcaster():
    global _last_snap
    while True:
        snap_json = await _out_queue.get()
        _last_snap = snap_json
        dead = set()
        for ws in list(_clients):
            try:
                await ws.send(snap_json)
            except Exception:
                dead.add(ws)
        _clients.difference_update(dead)


async def _watchdog():
    """Re-broadcast only when state actually changed, or for late-joining clients."""
    await asyncio.sleep(0.5)
    last_hash = None
    while True:
        if _pending is not None:
            snap_json = json.dumps(_pending, ensure_ascii=False, separators=(",", ":"))
            h = hash(snap_json)
            if h != last_hash or not _clients:
                # State changed or new client waiting
                if _clients or last_hash is None:
                    await _out_queue.put(snap_json)
                last_hash = h
        await asyncio.sleep(5.0)   # check every 5s, only send if changed


async def _serve(host: str, port: int):
    global _out_queue
    _out_queue = asyncio.Queue()
    asyncio.create_task(_broadcaster())
    asyncio.create_task(_watchdog())
    async with websockets.serve(_handler, host, port):
        sys.stderr.write(f"[ws] listening on ws://{host}:{port}\n")
        await asyncio.Future()


def _thread_main(host: str, port: int):
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_serve(host, port))
    except Exception as e:
        sys.stderr.write(f"[ws] error: {e}\n")


# ── Public API ────────────────────────────────────────────────
def start(host: str = "localhost", port: int = 8765) -> bool:
    try:
        import websockets as _check  # noqa
    except ImportError:
        return False
    t = threading.Thread(target=_thread_main, args=(host, port), daemon=True)
    t.start()
    time.sleep(0.5)
    return True


def push_state(snapshot: dict) -> None:
    global _pending
    _pending = snapshot
    if _loop is None or _out_queue is None:
        return
    snap_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    asyncio.run_coroutine_threadsafe(_out_queue.put(snap_json), _loop)


def read_command(timeout: float = 0.0) -> Optional[dict]:
    """
    Read next command from browser. Non-blocking by default (timeout=0.0).
    Returns None immediately if nothing waiting.
    Pass timeout>0 to block briefly.
    """
    try:
        block = timeout > 0
        raw = _in_queue.get(block=block, timeout=timeout if block else None)
        return json.loads(raw)
    except Exception:
        return None
