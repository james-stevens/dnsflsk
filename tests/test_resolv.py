"""Direct tests of the resolver, including branches the HTTP layer does not reach."""

import json
import sys

import dns.flags
import dns.message
import pytest
import resolv
from resolv import DNS_FLAGS, Resolver, ResolvError
from stub_dns import DnsStub, UdpProxy, build_reply


@pytest.fixture
def stub():
    server = DnsStub()
    try:
        yield server
    finally:
        server.close()


def test_init_reads_resolv_conf_and_rejects_bad_servers():
    resolver = Resolver()
    try:
        assert resolver.servers
        assert all("." in item for item in resolver.servers)
    finally:
        resolver.sock.close()

    with pytest.raises(ResolvError, match="Failed to identify servers"):
        Resolver(servers=123)
    with pytest.raises(ResolvError, match="Invalid IP"):
        Resolver(servers="not-an-ip")


def test_init_rejects_a_missing_socket(monkeypatch):
    monkeypatch.setattr(resolv.socket, "socket", lambda *_args, **_kwargs: None)
    with pytest.raises(ResolvError, match="UDP client socket"):
        Resolver(servers="127.0.0.1")


def test_root_mode_rejects_recursion_and_queries_when_rd_is_clear(monkeypatch, stub):
    monkeypatch.setenv("LOCAL_ICANN_ROOT", stub.endpoint)
    resolver = Resolver(servers="8.8.8.8")
    try:
        with pytest.raises(ResolvError, match="ROOT mode requested with RD=1"):
            resolver.resolv("example.com", "A", servers="icann-root", flags=DNS_FLAGS["RD"])
        assert stub.udp_queries == []

        answer = resolver.resolv("example.com", "A", servers=["icann-root"], flags=0)
        assert answer["Answer"][0]["data"] == "192.0.2.10"
        assert answer["Responder"].endswith(f":{stub.port}")
    finally:
        if resolver.sock is not None:
            resolver.sock.close()


def test_query_round_trip_flags_raw_and_tcp(stub):
    resolver = Resolver(servers="8.8.8.8")
    try:
        plain = resolver.resolv("example.com", 1, servers=stub.endpoint, flags=DNS_FLAGS["RD"])
        assert plain["Status"] == 0
        assert plain["Status Name"][0] == "NOERROR"
        assert "rdata" not in plain["Answer"][0]
        query = dns.message.from_wire(stub.udp_queries[-1])
        assert query.flags & dns.flags.RD
        assert query.payload == 30000
        assert not (query.ednsflags & 0x8000)

        rich = resolver.resolv("example.com.",
                               "A",
                               servers=stub.endpoint,
                               include_raw=True,
                               with_dnssec=True,
                               force_tcp=True,
                               flags=0)
        assert rich["Answer"][0]["data"] == "192.0.2.50"
        assert rich["Answer"][0]["rdata"]
        tcp_query = dns.message.from_wire(stub.tcp_queries[-1])
        assert tcp_query.ednsflags & 0x8000
        assert not (tcp_query.flags & dns.flags.RD)
        host, port = rich["Responder"].rsplit(":", 1)
        assert host == "127.0.0.1"
        assert int(port) == stub.port
    finally:
        resolver.sock.close()


def test_truncated_udp_retries_tcp_on_the_same_port(stub):
    stub.udp_handler = lambda wire: build_reply(wire, "192.0.2.1", tc=True)
    resolver = Resolver(servers="127.0.0.1")
    try:
        answer = resolver.resolv("example.com", "TXT", servers=stub.endpoint)
        assert answer["Answer"][0]["data"] == "192.0.2.50"
        assert answer["TC"] is False
        assert stub.tcp_queries
        assert answer["Responder"] == f"127.0.0.1:{stub.port}"
    finally:
        resolver.sock.close()


def test_identifier_mismatch_then_match(stub):
    stub.udp_mode = "mismatch"
    resolver = Resolver(servers="127.0.0.1")
    try:
        answer = resolver.resolv("example.com", "A", servers=stub.endpoint)
        assert answer["Answer"][0]["data"] == "192.0.2.10"
    finally:
        resolver.sock.close()


def test_response_without_qr_is_rejected(stub):
    stub.udp_handler = lambda wire: build_reply(wire, qr=False)
    resolver = Resolver(servers="127.0.0.1")
    try:
        assert resolver.resolv("example.com", "A", servers=stub.endpoint) is None
    finally:
        resolver.sock.close()


def test_timeout_returns_none(monkeypatch, stub):
    monkeypatch.setattr(resolv.select, "select", lambda *_args, **_kwargs: ([], [], []))
    resolver = Resolver(servers="127.0.0.1")
    try:
        assert resolver.resolv("example.com", "A", servers=stub.endpoint) is None
    finally:
        resolver.sock.close()


def test_send_failure_closes_the_socket(monkeypatch):
    resolver = Resolver(servers="127.0.0.1")
    messages = []
    monkeypatch.setattr(resolv.syslog, "syslog", messages.append)

    def explode(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr(resolver, "sock", UdpProxy(resolver.sock, lambda real, payload, address: explode()))
    assert resolver.resolv("example.com", "A", servers="127.0.0.1") is None
    assert resolver.sock is None
    assert any("network down" in item for item in messages)


def test_recreates_socket_and_rejects_a_bad_name(stub):
    resolver = Resolver(servers="127.0.0.1")
    resolver.sock.close()
    resolver.sock = None
    answer = resolver.resolv("example.com", "A", servers=stub.endpoint)
    assert answer["Answer"][0]["data"] == "192.0.2.10"
    resolver.sock.close()

    resolver = Resolver(servers="127.0.0.1")
    try:
        with pytest.raises(ResolvError, match="failed validation"):
            resolver.resolv("bad_host", "A", servers="127.0.0.1")
    finally:
        resolver.sock.close()


def test_send_skips_an_all_zero_identifier(monkeypatch, stub):
    resolver = Resolver(servers="127.0.0.1")
    try:
        resolver.question = bytearray(dns.message.make_query("example.com", "A").to_wire())
        resolver.question[0] = 0
        resolver.question[1] = 0
        resolver.svr_ports = [("127.0.0.1", stub.port)]
        drawn = [b"\x00\x00", b"\x12\x34"]
        monkeypatch.setattr(resolv.os, "urandom", lambda _n: drawn.pop(0))
        assert resolver.send() is True
        assert bytes(resolver.question[:2]) == b"\x12\x34"
        resolver.question = None
        assert resolver.send() is None
    finally:
        resolver.sock.close()


def test_match_id_and_find_port():
    resolver = Resolver(servers="127.0.0.1")
    try:
        resolver.qryid = None
        resolver.reply = b"\x00\x01rest"
        assert resolver.match_id() is False
        resolver.qryid = b"\x00\x01"
        resolver.reply = b"\x00\x02rest"
        assert resolver.match_id() is False
        resolver.reply = b"\x00\x01rest"
        assert resolver.match_id() is True
        resolver.svr_ports = [("127.0.0.1", 5300), ("192.0.2.9", 53)]
        assert resolver.find_port("127.0.0.1") == 5300
        assert resolver.find_port("192.0.2.8") == 53
    finally:
        resolver.sock.close()


def test_tcp_read_timeout_and_short_reads(monkeypatch):
    resolver = Resolver(servers="127.0.0.1")
    try:
        resolver.question = b"\x00\x01" + b"\x00" * 10

        class TimingOut:

            def setblocking(self, _flag):
                pass

            def connect(self, _addr):
                pass

            def send(self, data):
                return len(data)

            def settimeout(self, _value):
                pass

            def recv(self, _size):
                raise TimeoutError("slow")

            def close(self):
                self.closed = True

        sock = TimingOut()
        monkeypatch.setattr(resolv.socket, "socket", lambda *_a, **_k: sock)
        assert resolver.ask_in_tcp("127.0.0.1", 53) == b""
        assert sock.closed is True

        # The first two bytes are a length. Deliver less than that, then the rest.
        message = b"abcdefghij"
        framed = (len(message)).to_bytes(2, "big") + message
        pieces = [framed[:1], framed[1:4], framed[4:]]

        class Framed:

            def setblocking(self, _flag):
                pass

            def connect(self, _addr):
                pass

            def send(self, data):
                return len(data)

            def settimeout(self, _value):
                pass

            def recv(self, _size):
                return pieces.pop(0)

            def close(self):
                pass

        monkeypatch.setattr(resolv.socket, "socket", lambda *_a, **_k: Framed())
        assert resolver.ask_in_tcp("127.0.0.1", 5300) == message
    finally:
        resolver.sock.close()


def test_unknown_rcode_and_authority(stub):
    stub.udp_handler = lambda wire: build_reply(wire, rcode=11)
    resolver = Resolver(servers="127.0.0.1")
    try:
        odd = resolver.resolv("example.com", "A", servers=stub.endpoint)
        assert odd["Status"] == 11
        assert "Status Name" not in odd

        stub.udp_handler = lambda wire: build_reply(wire, authority=True, ip="192.0.2.10")
        full = resolver.resolv("example.com", "A", servers=stub.endpoint, include_raw=True)
        assert full["Authority"][0]["typename"] == "NS"
        assert any(item["data"] == "192.0.2.20" for item in full["Additional"])
        assert full["Answer"][0]["rdata"]
    finally:
        resolver.sock.close()


def test_command_line_wrapper(monkeypatch, stub, capsys):
    monkeypatch.setattr(sys, "argv", ["resolv.py", "-n", "example.com", "-s", stub.endpoint, "-t", "A"])
    resolv.main()
    first = json.loads(capsys.readouterr().out)
    assert first["Answer"][0]["data"] == "192.0.2.10"
    assert first["RD"] is True

    monkeypatch.setattr(sys, "argv",
                        ["resolv.py", "-n", "example.com", "-s", stub.endpoint, "-t", "A", "-R", "-r", "-d", "-T"])
    resolv.main()
    second = json.loads(capsys.readouterr().out)
    assert second["Answer"][0]["data"] == "192.0.2.50"
    assert second["RD"] is False
    assert second["Answer"][0]["rdata"]
    query = dns.message.from_wire(stub.tcp_queries[-1])
    assert query.ednsflags & 0x8000
