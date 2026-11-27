"""Local UDP and TCP DNS server for tests. Nothing here talks to the internet."""

import socket
import threading

import dns.flags
import dns.message
import dns.rrset


class UdpProxy:
    """Stand-in for a connected UDP socket.

    CPython's socket methods are read-only, so tests wrap the real socket
    when they need to observe or divert ``sendto``. ``select`` uses ``fileno``.
    """

    def __init__(self, sock, sendto):
        self._sock = sock
        self._sendto = sendto

    def sendto(self, payload, address):
        return self._sendto(self._sock, payload, address)

    def recvfrom(self, size):
        return self._sock.recvfrom(size)

    def fileno(self):
        return self._sock.fileno()

    def close(self):
        return self._sock.close()

    def settimeout(self, value):
        return self._sock.settimeout(value)


def build_reply(wire, ip="192.0.2.10", tc=False, rcode=0, qr=True, authority=False):
    """Build a DNS response for the query in ``wire``."""
    query = dns.message.from_wire(wire)
    reply = dns.message.make_response(query)
    reply.set_rcode(rcode)
    if tc:
        reply.flags |= dns.flags.TC
    if not qr:
        reply.flags &= ~dns.flags.QR
    if rcode == 0 and query.question:
        name = query.question[0].name
        reply.answer.append(dns.rrset.from_text(name, 300, "IN", "A", ip))
        if authority:
            reply.authority.append(dns.rrset.from_text(name, 300, "IN", "NS", "ns.example.com."))
            reply.additional.append(dns.rrset.from_text("ns.example.com.", 300, "IN", "A", "192.0.2.20"))
    return reply.to_wire()


class DnsStub:
    """Answer DNS on one UDP port and the same TCP port."""

    def __init__(self):
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.port = self.udp.getsockname()[1]
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp.bind(("127.0.0.1", self.port))
        self.tcp.listen(8)
        self.udp_queries = []
        self.tcp_queries = []
        self.udp_mode = "answer"
        self.udp_handler = lambda wire: build_reply(wire, "192.0.2.10")
        self.tcp_handler = lambda wire: build_reply(wire, "192.0.2.50")
        self._stop = threading.Event()
        self._threads = [
            threading.Thread(target=self._udp_loop, name="stub-udp", daemon=True),
            threading.Thread(target=self._tcp_loop, name="stub-tcp", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    @property
    def endpoint(self):
        return f"127.0.0.1:{self.port}"

    def close(self):
        self._stop.set()
        for sock in (self.udp, self.tcp):
            try:
                sock.close()
            except OSError:
                pass
        for thread in self._threads:
            thread.join(timeout=1)

    def _udp_loop(self):
        while not self._stop.is_set():
            self.udp.settimeout(0.2)
            try:
                data, addr = self.udp.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                break
            self.udp_queries.append(data)
            if self.udp_mode == "silent":
                continue
            if self.udp_mode == "mismatch":
                good = self.udp_handler(data)
                bad = bytearray(good)
                bad[0] ^= 0xFF
                self.udp.sendto(bytes(bad), addr)
                self.udp.sendto(good, addr)
                continue
            reply = self.udp_handler(data)
            if reply is not None:
                self.udp.sendto(reply, addr)

    def _tcp_loop(self):
        while not self._stop.is_set():
            self.tcp.settimeout(0.2)
            try:
                conn, _addr = self.tcp.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(2)
                try:
                    header = self._read_exact(conn, 2)
                    if len(header) < 2:
                        continue
                    length = int.from_bytes(header, "big")
                    body = self._read_exact(conn, length)
                except (TimeoutError, OSError):
                    continue
                if len(body) < length:
                    continue
                self.tcp_queries.append(body)
                reply = self.tcp_handler(body)
                if reply is None:
                    continue
                conn.sendall(len(reply).to_bytes(2, "big") + reply)

    @staticmethod
    def _read_exact(conn, size):
        buf = b""
        while len(buf) < size:
            chunk = conn.recv(size - len(buf))
            if not chunk:
                break
            buf += chunk
        return buf
