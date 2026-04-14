import asyncio
import threading
import time
import tkinter as tk

import requests
import uvicorn

from gui import DWM1001App


def _run_api():
    asyncio.run(
        uvicorn.Server(
            uvicorn.Config(
                "api:app",
                host="127.0.0.1",
                port=8000,
                log_level="error",
            )
        ).serve()
    )


def _wait_for_api(timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get("http://127.0.0.1:8000/status", timeout=0.5)
            return True
        except Exception:
            time.sleep(0.25)
    return False


if __name__ == "__main__":
    api_thread = threading.Thread(target=_run_api, daemon=True, name="ble-api-thread")
    api_thread.start()

    if not _wait_for_api():
        print("ERROR: API server failed to start within 10 seconds.")
        raise SystemExit(1)

    root = tk.Tk()
    DWM1001App(root)
    root.mainloop()

