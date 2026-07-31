from __future__ import annotations

import os


HOST = os.getenv("CTRLV_HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", os.getenv("CTRLV_PORT", "8765")))


def main() -> None:
    import uvicorn
    from server.app import app
    from server.desktop_capture import start_desktop_capture

    url = f"http://{HOST}:{PORT}"
    print(f"CtrlV: {url}")
    start_desktop_capture()
    uvicorn.run(app, host=HOST, port=PORT, access_log=False)


if __name__ == "__main__":
    main()
