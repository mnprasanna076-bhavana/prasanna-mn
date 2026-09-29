import os
import uvicorn
from app import app, find_available_port

if __name__ == "__main__":
    import webbrowser
    import threading
    import time

    preferred_port = int(os.getenv("PORT", 8000))
    port = find_available_port(preferred_port)
    host = os.getenv("HOST", "127.0.0.1")
    url = f"http://{host}:{port}"
    print("\n========================================================")
    print(f"🚀 PocketSmart AI running successfully!")
    print(f"👉 Open in browser: {url}")
    print("========================================================\n")

    def open_external_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass

    threading.Thread(target=open_external_browser, daemon=True).start()
    uvicorn.run("main:app", host=host, port=port, reload=True)
