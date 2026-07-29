"""🔌 크롬 원격 제어(CDP) — **로그인해 둔 그 창에서 직접** 페이지를 읽는다 (v1.15).

회원님 지적: "블로그 구조는 크롬을 실행해 → 로그인을 해 → 그다음에 크롤링을 해."
정확한 지적이었다. v1.12~v1.13.1은 로그인 창과 **별도의** 헤드리스 크롬을 띄우고
프로필(쿠키)만 복사했는데, 최신 크롬은 쿠키를 앱에 묶어 암호화(App-Bound
Encryption)해서 **복사한 쿠키를 다른 크롬 프로세스가 풀지 못한다.** 그래서 로그인을
해 둬도 수집 쪽은 로그아웃 상태로 페이지를 읽었다.

해결: 로그인 창을 `--remote-debugging-port=0`으로 띄우고(포트는 크롬이 프로필의
DevToolsActivePort 파일에 적어 준다), 수집할 때 **그 창에 새 탭을 열어** 페이지를
그리게 한 뒤 DOM을 가져온다. 쿠키·세션이 그 창의 것이므로 로그인 상태 그대로다.

⚠ 이건 봇 차단 우회가 아니다 — 회원님 본인의 브라우저에서, 회원님이 직접 한
로그인으로, 회원님이 넣은 주소를 여는 것뿐이다. 자동 로그인·캡차 우회는 없다.

표준 라이브러리만 쓴다(외부 패키지 금지) — CDP는 WebSocket 위의 JSON이라
필요한 최소 기능만 직접 구현했다(RFC 6455: 핸드셰이크 + 마스킹 텍스트 프레임).
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

DEVTOOLS_PORT_FILE = "DevToolsActivePort"
_LOCAL = "127.0.0.1"


def read_debug_port(profile_dir) -> int:
    """프로필 폴더의 DevToolsActivePort에서 포트 읽기 — 없으면 0 (창이 꺼져 있음)."""
    try:
        first = Path(profile_dir).joinpath(DEVTOOLS_PORT_FILE).read_text(
            encoding="utf-8", errors="replace").splitlines()[0].strip()
        return int(first)
    except (OSError, IndexError, ValueError):
        return 0


def _http_json(port: int, path: str, timeout: float = 3.0, method: str = "GET"):
    """CDP HTTP 엔드포인트 호출 — 프록시를 타지 않게 직접 opener를 만든다."""
    req = urllib.request.Request(f"http://{_LOCAL}:{port}{path}", method=method,
                                 headers={"Host": f"{_LOCAL}:{port}"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body.decode("utf-8", errors="replace")) if body else None


def is_alive(port: int, timeout: float = 2.0) -> bool:
    """그 포트에 크롬이 살아 있나 (로그인 창이 켜져 있나)."""
    if not port:
        return False
    try:
        v = _http_json(port, "/json/version", timeout=timeout)
        return bool(v and v.get("Browser"))
    except Exception:  # noqa: BLE001 — 꺼져 있으면 '없음'
        return False


class _WS:
    """최소 WebSocket 클라이언트 — CDP 한 세션에 필요한 만큼만 (텍스트 프레임)."""

    def __init__(self, url: str, timeout: float = 30.0):
        m = re.match(r"ws://([^/:]+):(\d+)(/.*)$", url)
        if not m:
            raise ValueError(f"CDP 주소를 이해하지 못했어요: {url[:80]}")
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n".encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("CDP 연결이 핸드셰이크 중에 끊겼어요")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OSError("CDP 업그레이드 실패: " + head[:60].decode("latin-1"))
        self._buf = head.split(b"\r\n\r\n", 1)[1]

    def send(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x81, 0x80 | n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, n)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _read(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OSError("CDP 연결이 끊겼어요")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self) -> str:
        """텍스트 프레임 하나 (제어 프레임은 조용히 처리, 조각난 프레임 이어붙임)."""
        data = b""
        while True:
            b0, b1 = struct.unpack("!BB", self._read(2))
            opcode, fin, ln = b0 & 0x0F, b0 & 0x80, b1 & 0x7F
            if ln == 126:
                ln = struct.unpack("!H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack("!Q", self._read(8))[0]
            body = self._read(ln) if ln else b""
            if opcode == 0x8:                       # close
                raise OSError("크롬이 CDP 연결을 닫았어요")
            if opcode == 0x9:                       # ping → pong
                self.sock.sendall(struct.pack("!BB", 0x8A, 0x80) + os.urandom(4))
                continue
            if opcode == 0xA:                       # pong
                continue
            data += body
            if fin:
                return data.decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Session:
    """CDP 명령을 주고받는 한 세션 (탭 하나 또는 브라우저)."""

    def __init__(self, ws_url: str, timeout: float = 30.0):
        self.ws = _WS(ws_url, timeout=timeout)
        self._id = 0

    def call(self, method: str, params: Optional[dict] = None,
             timeout: float = 25.0) -> dict:
        self._id += 1
        want = self._id
        self.ws.send(json.dumps({"id": want, "method": method,
                                 "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == want:
                if "error" in msg:
                    raise OSError(f"{method}: {str(msg['error'])[:120]}")
                return msg.get("result") or {}
        raise TimeoutError(f"{method} 응답이 없어요")

    def wait_event(self, name: str, timeout: float = 20.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = json.loads(self.ws.recv())
            except socket.timeout:
                break
            if msg.get("method") == name:
                return msg.get("params") or {}
        return {}

    def close(self) -> None:
        self.ws.close()


def fetch_dom(port: int, url: str, timeout: float = 45.0,
              settle_s: float = 2.5) -> Tuple[str, str]:
    """로그인 창에 **새 탭**을 열어 페이지를 그린 뒤 (HTML, 최종주소) 반환.

    끝나면 탭을 닫는다 — 회원님 화면에 탭이 쌓이지 않게. 실패하면 ("", "").
    """
    deadline = time.monotonic() + timeout
    target_id, sess = "", None
    try:
        # 새 탭 만들기 (최신 크롬은 PUT을 요구, 옛 버전은 GET도 받는다)
        info = None
        for method in ("PUT", "GET"):
            try:
                info = _http_json(port, "/json/new?" + urllib.request.quote(
                    url, safe=":/?=&%#"), timeout=8.0, method=method)
                if info and info.get("webSocketDebuggerUrl"):
                    break
            except Exception:  # noqa: BLE001 — 다음 방식으로
                info = None
        if not (info and info.get("webSocketDebuggerUrl")):
            return "", ""
        target_id = str(info.get("id") or "")
        sess = Session(str(info["webSocketDebuggerUrl"]),
                      timeout=max(5.0, deadline - time.monotonic()))
        sess.call("Page.enable")
        try:                                     # 이미 이동 중이면 그대로 기다린다
            sess.call("Page.navigate", {"url": url}, timeout=20.0)
        except OSError:
            pass
        sess.wait_event("Page.loadEventFired",
                        timeout=max(3.0, min(25.0, deadline - time.monotonic())))
        time.sleep(max(0.0, min(settle_s, deadline - time.monotonic())))  # 지연 렌더 대기
        res = sess.call(
            "Runtime.evaluate",
            {"expression": "document.documentElement.outerHTML", "returnByValue": True},
            timeout=max(3.0, min(20.0, deadline - time.monotonic())))
        html = str(((res.get("result") or {}).get("value")) or "")
        final = ""
        try:
            fr = sess.call("Runtime.evaluate",
                           {"expression": "location.href", "returnByValue": True},
                           timeout=8.0)
            final = str(((fr.get("result") or {}).get("value")) or "")
        except Exception:  # noqa: BLE001 — 주소는 없어도 진행
            pass
        return html, final or url
    except Exception:  # noqa: BLE001 — 연결·타임아웃은 헤드리스 경로로 넘어간다
        return "", ""
    finally:
        if sess is not None:
            sess.close()
        if target_id:
            try:
                _http_json(port, f"/json/close/{target_id}", timeout=5.0)
            except Exception:  # noqa: BLE001 — 탭 정리는 실패해도 무해
                pass
