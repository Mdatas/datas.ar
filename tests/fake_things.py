"""Stand-ins for hardware and network devices, small enough to read: an MQTT broker, a
Modbus device, a serial board. They speak the real protocols over real sockets, so the
tests exercise the same code a real device would."""

from __future__ import annotations

import os
import socket
import struct
import threading


class Server:
    """A TCP server on 127.0.0.1 with one thread per connection."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.open = True
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while self.open:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._safe, args=(conn,), daemon=True).start()

    def _safe(self, conn: socket.socket) -> None:
        try:
            self.handle(conn)
        except (OSError, struct.error, IndexError):
            pass
        finally:
            conn.close()

    def handle(self, conn: socket.socket) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def close(self) -> None:
        self.open = False
        self.sock.close()


def exactly(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise OSError("closed")
        buf += chunk
    return buf


class Broker(Server):
    """MQTT 3.1.1, the parts a client needs: connect, subscribe, publish (kept messages too)."""

    def __init__(self, password: str | None = None) -> None:
        self.password = password
        self.subs: list[tuple[socket.socket, str]] = []
        self.retained: dict[str, bytes] = {}
        self.seen: list[tuple[str, bytes]] = []
        self.lock = threading.Lock()
        super().__init__()

    @staticmethod
    def _packet(conn: socket.socket) -> tuple[int, int, bytes]:
        first = exactly(conn, 1)[0]
        length, shift = 0, 0
        while True:
            b = exactly(conn, 1)[0]
            length |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        return first >> 4, first & 0x0F, exactly(conn, length) if length else b""

    @staticmethod
    def _text(data: bytes, at: int) -> tuple[str, int]:
        n = struct.unpack(">H", data[at : at + 2])[0]
        return data[at + 2 : at + 2 + n].decode(), at + 2 + n

    @staticmethod
    def matches(pattern: str, topic: str) -> bool:
        p, t = pattern.split("/"), topic.split("/")
        for i, part in enumerate(p):
            if part == "#":
                return True
            if i >= len(t) or (part != "+" and part != t[i]):
                return False
        return len(p) == len(t)

    @staticmethod
    def _publish(topic: str, payload: bytes, retain: bool = False) -> bytes:
        body = struct.pack(">H", len(topic)) + topic.encode() + payload
        assert len(body) < 128
        return bytes([0x30 | (1 if retain else 0), len(body)]) + body

    def handle(self, conn: socket.socket) -> None:
        while True:
            kind, flags, data = self._packet(conn)
            if kind == 1:  # CONNECT
                _proto, at = self._text(data, 0)
                connect_flags = data[at + 1]
                at += 4
                _client, at = self._text(data, at)
                password = None
                if connect_flags & 0x80:
                    _user, at = self._text(data, at)
                if connect_flags & 0x40:
                    password, at = self._text(data, at)
                ok = self.password is None or password == self.password
                conn.sendall(bytes([0x20, 0x02, 0x00, 0x00 if ok else 0x05]))
                if not ok:
                    return
            elif kind == 8:  # SUBSCRIBE
                pid = data[:2]
                topic, _ = self._text(data, 2)
                with self.lock:
                    self.subs.append((conn, topic))
                    kept = [(t, p) for t, p in self.retained.items() if self.matches(topic, t)]
                conn.sendall(bytes([0x90, 0x03]) + pid + b"\x00")
                for t, p in kept:
                    conn.sendall(self._publish(t, p, True))
            elif kind == 3:  # PUBLISH
                topic, at = self._text(data, 0)
                qos = (flags >> 1) & 3
                if qos:
                    conn.sendall(bytes([0x40, 0x02]) + data[at : at + 2])
                    at += 2
                payload = data[at:]
                with self.lock:
                    self.seen.append((topic, payload))
                    if flags & 1:
                        self.retained[topic] = payload
                    targets = [c for c, pat in self.subs if self.matches(pat, topic)]
                for c in targets:
                    try:
                        c.sendall(self._publish(topic, payload))
                    except OSError:
                        pass
            elif kind == 12:  # PINGREQ
                conn.sendall(bytes([0xD0, 0x00]))
            elif kind == 14:  # DISCONNECT
                return


class ModbusDevice(Server):
    """Modbus TCP over a small memory: holding registers and coils; reads of input registers
    and discrete inputs see the same values."""

    def __init__(self) -> None:
        self.registers = {i: 0 for i in range(100)}
        self.coils = {i: 0 for i in range(100)}
        super().__init__()

    def handle(self, conn: socket.socket) -> None:
        while True:
            tid, proto, length, unit = struct.unpack(">HHHB", exactly(conn, 7))
            pdu = exactly(conn, length - 1)
            out = self.answer(pdu)
            conn.sendall(struct.pack(">HHHB", tid, proto, len(out) + 1, unit) + out)

    def answer(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        try:
            if fc in (3, 4):
                addr, n = struct.unpack(">HH", pdu[1:5])
                vals = [self.registers[a] for a in range(addr, addr + n)]
                return bytes([fc, 2 * n]) + struct.pack(f">{n}H", *vals)
            if fc in (1, 2):
                addr, n = struct.unpack(">HH", pdu[1:5])
                bits = [self.coils[a] for a in range(addr, addr + n)]
                packed = bytearray((n + 7) // 8)
                for i, b in enumerate(bits):
                    if b:
                        packed[i // 8] |= 1 << (i % 8)
                return bytes([fc, len(packed)]) + bytes(packed)
            if fc == 6:
                addr, val = struct.unpack(">HH", pdu[1:5])
                if addr not in self.registers:
                    raise KeyError(addr)
                self.registers[addr] = val
                return pdu[:5]
            if fc == 5:
                addr, val = struct.unpack(">HH", pdu[1:5])
                if addr not in self.coils:
                    raise KeyError(addr)
                self.coils[addr] = 1 if val == 0xFF00 else 0
                return pdu[:5]
            if fc == 16:
                addr, n, _nbytes = struct.unpack(">HHB", pdu[1:6])
                vals = struct.unpack(f">{n}H", pdu[6 : 6 + 2 * n])
                for i, v in enumerate(vals):
                    if addr + i not in self.registers:
                        raise KeyError(addr + i)
                    self.registers[addr + i] = v
                return pdu[:5]
            if fc == 15:
                addr, n, _nbytes = struct.unpack(">HHB", pdu[1:6])
                for i in range(n):
                    if addr + i not in self.coils:
                        raise KeyError(addr + i)
                    self.coils[addr + i] = (pdu[6 + i // 8] >> (i % 8)) & 1
                return pdu[:5]
            return bytes([fc | 0x80, 1])  # illegal function
        except KeyError:
            return bytes([fc | 0x80, 2])  # illegal data address


class Board:
    """A board on a serial port (a pseudo-terminal): says READY while it waits, then answers
    each line — like an Arduino sketch that reads commands. POSIX only."""

    def __init__(self) -> None:
        import pty
        import tty

        self.master, slave = pty.openpty()
        tty.setraw(slave)
        self.port = os.ttyname(slave)
        self._slave = slave
        self.got: list[str] = []
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._greet, daemon=True).start()

    def _greet(self) -> None:
        import time

        while not self.got:
            try:
                os.write(self.master, b"READY v1\r\n")
            except OSError:
                return
            time.sleep(0.1)

    def _run(self) -> None:
        buf = b""
        while True:
            try:
                data = os.read(self.master, 256)
            except OSError:
                return
            if not data:
                return
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = line.decode("utf-8", "replace").strip()
                self.got.append(cmd)
                if cmd == "LED ON":
                    os.write(self.master, b"OK led=1\r\n")
                elif cmd == "TEMP?":
                    os.write(self.master, b"TEMP 21.5\r\n")
                else:
                    os.write(self.master, b"ERR unknown\r\n")

    def close(self) -> None:
        for fd in (self.master, self._slave):
            try:
                os.close(fd)
            except OSError:
                pass
