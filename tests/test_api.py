"""Flask test-client coverage. DNS stays on a local stub."""

import dns.flags
import dns.message
import dnsflsk
import pytest
import resolv
from stub_dns import DnsStub, UdpProxy, build_reply


@pytest.fixture
def stub():
    server = DnsStub()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def client(stub, monkeypatch):
    monkeypatch.setattr(dnsflsk, "dohServers", stub.endpoint)
    dnsflsk.application.config.update(TESTING=True)
    return dnsflsk.application.test_client()


def _query(client, **params):
    params.setdefault("name", "example.com")
    params.setdefault("type", "A")
    return client.get("/resolv", query_string=params)


def _redirect_port_53(monkeypatch, stub):
    """Record port 53 and deliver it to the stub. ``socket.sendto`` is read-only."""
    seen = []

    def sendto(real, payload, address):
        seen.append(address)
        host, port = address
        if port == 53:
            address = (host, stub.port)
        return real.sendto(payload, address)

    monkeypatch.setattr(dnsflsk.my_resolver, "sock", UdpProxy(dnsflsk.my_resolver.sock, sendto))
    return seen


def test_welcome_pages(client):
    assert client.get("/").get_data(as_text=True) == "Welcome to the DNS/API"
    assert "v1.0" in client.get("/dns/api/v1.0/").get_data(as_text=True)


def test_normal_query_uses_configured_servers(client, stub):
    response = _query(client)
    assert response.status_code == 200
    body = response.get_json()
    assert body["Status"] == 0
    assert body["Answer"][0]["data"] == "192.0.2.10"
    assert body["Answer"][0]["typename"] == "A"
    assert body["QR"] is True
    assert body["RD"] is True
    host, port = body["Responder"].rsplit(":", 1)
    assert host == "127.0.0.1"
    assert int(port) == stub.port
    query = dns.message.from_wire(stub.udp_queries[-1])
    assert query.question[0].name.to_text() == "example.com."
    assert query.flags & dns.flags.RD
    assert query.payload == 30000


def test_explicit_server_overrides_the_default(client, stub, monkeypatch):
    monkeypatch.setattr(dnsflsk, "dohServers", "192.0.2.9")
    response = _query(client, servers=stub.endpoint)
    assert response.status_code == 200
    assert response.get_json()["Responder"] == f"127.0.0.1:{stub.port}"
    assert stub.udp_queries


def test_omitted_type_defaults_to_address_record(client, stub):
    response = client.get("/resolv", query_string={"name": "example.com"})
    assert response.status_code == 200
    query = dns.message.from_wire(stub.udp_queries[-1])
    assert query.question[0].rdtype == 1


def test_post_form_and_numeric_type(client):
    response = client.post("/dns/api/v1.0/resolv", data={"name": "example.com", "type": "1"})
    assert response.status_code == 200
    assert response.get_json()["Answer"][0]["type"] == 1


def test_rd_and_do_flags_are_passed_through(client, stub):
    cleared = _query(client, rd="0", do="0")
    assert cleared.status_code == 200
    query = dns.message.from_wire(stub.udp_queries[-1])
    assert not (query.flags & dns.flags.RD)
    assert not (query.ednsflags & 0x8000)
    assert "rdata" not in cleared.get_json()["Answer"][0]

    secured = _query(client, rd="1", do="1")
    assert secured.status_code == 200
    query = dns.message.from_wire(stub.udp_queries[-1])
    assert query.flags & dns.flags.RD
    assert query.ednsflags & 0x8000
    body = secured.get_json()
    assert body["Answer"][0]["rdata"]
    assert body["RD"] is True


def test_cd_and_dnssec_parameters_request_dnssec_material(client, stub):
    response = _query(client, cd="1", dnssec="1")
    assert response.status_code == 200
    query = dns.message.from_wire(stub.udp_queries[-1])
    assert query.ednsflags & 0x8000
    assert response.get_json()["Answer"][0]["rdata"]


def test_truncated_udp_falls_back_to_tcp_on_the_same_port(client, stub):
    stub.udp_handler = lambda wire: build_reply(wire, "192.0.2.1", tc=True)
    response = _query(client)
    assert response.status_code == 200
    body = response.get_json()
    assert body["Answer"][0]["data"] == "192.0.2.50"
    assert body["TC"] is False
    assert body["Responder"] == f"127.0.0.1:{stub.port}"
    assert stub.tcp_queries
    tcp_query = dns.message.from_wire(stub.tcp_queries[-1])
    assert tcp_query.question[0].name.to_text() == "example.com."


def test_utf8_and_punycode_names(client, stub):
    unicode_name = _query(client, name="bücher.example")
    assert unicode_name.status_code == 200
    assert dns.message.from_wire(stub.udp_queries[-1]).question[0].name.to_text() == "xn--bcher-kva.example."

    # Bytes that are UTF-8 misread as Latin-1 are reconstructed before punycode.
    mojibake = "bücher.example".encode().decode("latin-1")
    repaired = _query(client, name=mojibake)
    assert repaired.status_code == 200
    assert dns.message.from_wire(stub.udp_queries[-1]).question[0].name.to_text() == "xn--bcher-kva.example."

    puny = _query(client, name="xn--bcher-kva.example")
    assert puny.status_code == 200
    assert dns.message.from_wire(stub.udp_queries[-1]).question[0].name.to_text() == "xn--bcher-kva.example."


def test_icann_root_with_local_ip_and_port(client, stub, monkeypatch):
    monkeypatch.setenv("LOCAL_ICANN_ROOT", stub.endpoint)
    response = _query(client, servers="icann-root", rd="0")
    assert response.status_code == 200
    body = response.get_json()
    host, port = body["Responder"].rsplit(":", 1)
    assert host == "127.0.0.1"
    assert int(port) == stub.port
    query = dns.message.from_wire(stub.udp_queries[-1])
    assert not (query.flags & dns.flags.RD)


def test_icann_root_with_local_ip_uses_port_53(client, stub, monkeypatch):
    monkeypatch.setenv("LOCAL_ICANN_ROOT", "127.0.0.1")
    seen = _redirect_port_53(monkeypatch, stub)
    response = _query(client, servers="icann-root", rd="0")
    assert response.status_code == 200
    assert ("127.0.0.1", 53) in seen
    assert response.get_json()["Answer"][0]["data"] == "192.0.2.10"


def test_icann_root_without_local_root_uses_hard_coded_letters(client, stub, monkeypatch):
    monkeypatch.delenv("LOCAL_ICANN_ROOT", raising=False)
    chosen = ["d.root-servers.net.", "k.root-servers.net."]

    def fake_sample(population, count):
        assert list(population) == resolv.BEST_ICANN_ROOT
        assert count == 2
        return list(chosen)

    looked_up = []

    def fake_lookup(host):
        looked_up.append(host)
        return "127.0.0.1"

    monkeypatch.setattr(resolv.random, "sample", fake_sample)
    monkeypatch.setattr(resolv.socket, "gethostbyname", fake_lookup)
    seen = _redirect_port_53(monkeypatch, stub)
    response = _query(client, servers="icann-root", rd="0")
    assert response.status_code == 200
    assert looked_up == chosen
    assert ("127.0.0.1", 53) in seen
    assert response.get_json()["Responder"].startswith("127.0.0.1:")


def test_http_icann_root_does_not_apply_the_resolver_rd_guard(client, stub, monkeypatch):
    """Addresses are substituted before the resolver sees ``icann-root``.

    The resolver rejects RD=1 only when it is asked for ``icann-root`` itself.
    The HTTP layer has already turned that into socket addresses, so a normal
    recursive flag still produces a query.
    """
    monkeypatch.setenv("LOCAL_ICANN_ROOT", stub.endpoint)
    response = _query(client, servers="icann-root")
    assert response.status_code == 200
    query = dns.message.from_wire(stub.udp_queries[-1])
    assert query.flags & dns.flags.RD


def test_bad_local_root_is_rejected(client, monkeypatch):
    monkeypatch.setenv("LOCAL_ICANN_ROOT", "not_a_server")
    response = _query(client, servers="icann-root", rd="0")
    assert response.status_code == 400
    assert "Bad server" in response.get_json()["error"]


def test_error_paths(client, stub, monkeypatch):
    missing = client.get("/resolv")
    assert missing.status_code == 400
    assert "missing" in missing.get_json()["error"]

    bad_name = _query(client, name="bad_host.example")
    assert bad_name.status_code == 400
    assert "not a valid FQDN" in bad_name.get_json()["error"]

    bad_type = _query(client, type="NOTATYPE")
    assert bad_type.status_code == 400
    assert "not a known RR name" in bad_type.get_json()["error"]
    assert stub.udp_queries == []

    out_of_range = _query(client, type="65535")
    assert out_of_range.status_code == 400
    assert "out of range" in out_of_range.get_json()["error"]

    zero = _query(client, type="0")
    assert zero.status_code == 400
    assert "out of range" in zero.get_json()["error"]

    bad_server = _query(client, servers="not a server")
    assert bad_server.status_code == 400
    assert "Bad server" in bad_server.get_json()["error"]

    monkeypatch.setattr(resolv.select, "select", lambda *_args, **_kwargs: ([], [], []))
    timed_out = _query(client)
    assert timed_out.status_code == 400
    assert timed_out.get_json()["error"] == "No valid answer received"


def test_binary_dns_message(client, stub):
    query = dns.message.make_query("example.com", "A", id=0x1234)
    response = client.post("/dns/api/v1.0/resolv", data=query.to_wire(), content_type="application/dns-message")
    assert response.status_code == 200
    assert response.content_type.startswith("application/dns-message")
    parsed = dns.message.from_wire(response.data)
    assert parsed.id == 0x1234
    assert parsed.answer[0][0].address == "192.0.2.10"
    assert stub.udp_queries


def test_syslog_records_the_query_and_failures_stay_json(client, monkeypatch):
    messages = []
    monkeypatch.setattr(dnsflsk, "with_syslog", True)
    monkeypatch.setattr(dnsflsk.syslog, "syslog", messages.append)
    response = _query(client)
    assert response.status_code == 200
    assert any("example.com" in item for item in messages)

    def boom(_value):
        raise TypeError("not a type")

    monkeypatch.setattr(dnsflsk.dns.rdatatype, "to_text", boom)
    failed = _query(client)
    assert failed.status_code == 400
    assert failed.get_json()["error"] == "not a type"


def test_nxdomain_status_name(client, stub):
    stub.udp_handler = lambda wire: build_reply(wire, rcode=3)
    response = _query(client)
    body = response.get_json()
    assert body["Status"] == 3
    assert body["Status Name"][0] == "NXDOMAIN"


def test_wsgi_exports_the_flask_application():
    import wsgi
    assert wsgi.application is dnsflsk.application


def test_type_attribute_missing_defaults_to_one():
    from werkzeug.datastructures import MultiDict
    query = dnsflsk.ApiQuery()
    del query.rdtype
    assert query.queryFromJson(MultiDict([("name", "example.com")])) is None
    assert query.rdtype == 1


def test_import_reads_server_and_syslog_environment():
    import importlib
    import os
    saved = {key: os.environ.get(key) for key in ("DOH_SERVERS", "DOH_SYSLOG_SERVER")}
    try:
        os.environ["DOH_SERVERS"] = "192.0.2.1,192.0.2.2"
        os.environ["DOH_SYSLOG_SERVER"] = "-"
        importlib.reload(dnsflsk)
        assert dnsflsk.dohServers == "192.0.2.1,192.0.2.2"
        assert dnsflsk.with_syslog is False

        os.environ["DOH_SYSLOG_SERVER"] = "192.0.2.9"
        importlib.reload(dnsflsk)
        assert dnsflsk.with_syslog is True
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(dnsflsk)
