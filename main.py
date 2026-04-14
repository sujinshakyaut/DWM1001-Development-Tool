import asyncio
import threading
import time
import tkinter as tk

import requests
import uvicorn

from gui import DWM1001App


def _run_api():
    """Runs the FastAPI/uvicorn server in a background daemon thread."""
    asyncio.run(
        uvicorn.Server(
            uvicorn.Config(
                "ble_api:app",
                host="127.0.0.1",
                port=8000,
                log_level="error",
            )
        ).serve()
    )


def _wait_for_api(timeout: float = 10.0) -> bool:
    """Polls GET /status until uvicorn is ready, or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get("http://127.0.0.1:8000/status", timeout=0.5)
            return True
        except Exception:
            time.sleep(0.25)
    return False


if __name__ == "__main__":
    # 1. Start FastAPI server in a background daemon thread
    api_thread = threading.Thread(target=_run_api, daemon=True, name="ble-api-thread")
    api_thread.start()

    # 2. Wait until the server is accepting connections
    if not _wait_for_api():
        print("ERROR: API server failed to start within 10 seconds.")
        raise SystemExit(1)

    # 3. Launch Tkinter on the main thread (blocks until window is closed)
    root = tk.Tk()
    DWM1001App(root)
    root.mainloop()

    # api_thread is daemon=True so it exits automatically when mainloop returns
