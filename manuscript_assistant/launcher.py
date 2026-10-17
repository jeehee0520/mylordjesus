"""Starts the app on this computer only and opens it in the default browser.

Used by run_windows.bat and run_mac_linux.sh. The server listens on 127.0.0.1,
so other computers on the network cannot reach it (and no firewall prompt appears).
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent


def free_port(start: int = 8501, tries: int = 50) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"{start}~{start + tries - 1} 사이에 사용할 수 있는 포트가 없습니다.")


def wait_until_ready(url: str, proc: subprocess.Popen, timeout: float = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{url}/_stcore/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    if sys.version_info < (3, 10):
        print(f"Python 3.10 이상이 필요합니다 (현재 {sys.version.split()[0]}).")
        return 1
    port = free_port()
    url = f"http://localhost:{port}"
    cmd = [sys.executable, "-m", "streamlit", "run", str(HERE / "app.py"),
           "--server.port", str(port), "--server.address", "127.0.0.1", "--server.headless", "true"]
    print("투고 양식 도우미를 시작하는 중입니다…")
    proc = subprocess.Popen(cmd, cwd=HERE)
    if not wait_until_ready(url, proc):
        code = proc.poll()
        if code is None:
            proc.terminate()
        print("\n앱을 시작하지 못했습니다. 위에 나온 오류 메시지를 확인해 주세요.")
        return 1
    print(f"\n브라우저에서 앱을 엽니다: {url}")
    print("브라우저가 열리지 않으면 위 주소를 직접 입력하세요.")
    print("이 창을 닫으면 앱이 종료됩니다.\n")
    webbrowser.open(url)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
