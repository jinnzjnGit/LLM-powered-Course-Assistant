"""Start the local app on the first available loopback port."""
from pathlib import Path
import socket
import subprocess
import sys


def choose_port():
    for port in range(8501, 8511):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Ports 8501-8510 are busy. Close an unused app window and retry.")


def main():
    root = Path(__file__).resolve().parents[1]
    try:
        port = choose_port()
    except RuntimeError as error:
        print(error, flush=True)
        return 1
    if port != 8501:
        print(f"Port 8501 is busy; using {port}. Existing services were not stopped.", flush=True)
    print(f"Open http://localhost:{port} and keep this window open.", flush=True)
    return subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(root / "app.py"),
        "--server.address", "127.0.0.1", "--server.port", str(port),
        "--browser.gatherUsageStats", "false",
    ], cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
