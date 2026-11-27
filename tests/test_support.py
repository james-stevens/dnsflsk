"""Unit tests for helpers that do not open sockets."""

import runpy
import sys
from pathlib import Path

import misc
import pytest
import resolv
import validation

ROOT = Path(__file__).resolve().parents[1]


def test_get_port_variants():
    assert misc.get_port("192.0.2.1") == ("192.0.2.1", 53)
    assert misc.get_port("192.0.2.1:5300") == ("192.0.2.1", 5300)
    assert misc.get_port("192.0.2.1:0") == ("192.0.2.1:0", 53)
    assert misc.get_port("192.0.2.1:65536") == ("192.0.2.1:65536", 53)
    assert misc.get_port("192.0.2.1:abc") == ("192.0.2.1:abc", 53)
    assert misc.get_port("192.0.2.1:53:1") == ("192.0.2.1:53:1", 53)


def test_punycode_and_unicode_names():
    assert misc.utf8_to_puny(".") == "."
    assert misc.puny_to_utf8(".") == "."
    assert misc.utf8_to_puny("example.com") == "example.com"
    assert misc.utf8_to_puny("bücher.example") == "xn--bcher-kva.example"
    assert misc.puny_to_utf8("xn--bcher-kva.example") == "bücher.example"
    # idna rejects this label and the codec fallback accepts it.
    assert misc.utf8_to_puny("xn--") == "xn--"
    # Both encoders reject an over-long label.
    assert misc.utf8_to_puny("a" * 70) is None
    # idna rejects the label; the codec fallback still returns it.
    assert misc.puny_to_utf8("....") == "...."
    # idna and the codec both reject a truncated A-label.
    assert misc.puny_to_utf8("xn--") is None


def test_host_and_address_validation():
    assert validation.is_valid_host(None) is False
    assert validation.is_valid_host(".") is True
    assert validation.is_valid_host("example.com") is True
    assert validation.is_valid_host("example.com.") is True
    assert validation.is_valid_host("d.root-servers.net.") is True
    assert validation.is_valid_host("bad_host.example") is False
    assert validation.is_valid_host("-bad.example") is False

    assert validation.is_valid_ipv4(None) is False
    assert validation.is_valid_ipv4("127.0.0.1") is True
    assert validation.is_valid_ipv4("127.1") is False
    assert validation.is_valid_ipv4("256.1.1.1") is False
    assert validation.is_valid_ipv4("not-an-ip") is False

    assert validation.is_valid_server(None) is False
    assert validation.is_valid_server("192.0.2.1") is True
    assert validation.is_valid_server("example.com") is True
    assert validation.is_valid_server("bad_host") is False


def test_ipv4_without_inet_pton(monkeypatch):

    def missing(*_args, **_kwargs):
        raise AttributeError("inet_pton")

    monkeypatch.setattr(validation.socket, "inet_pton", missing)
    assert validation.is_valid_ipv4("127.0.0.1") is True
    # inet_aton accepts this shorthand; the dot-count check rejects it.
    assert validation.is_valid_ipv4("127.1") is False

    def broken_aton(_address):
        raise OSError("aton")

    monkeypatch.setattr(validation.socket, "inet_aton", broken_aton)
    assert validation.is_valid_ipv4("127.0.0.1") is False


def test_decode_servers_shapes(monkeypatch):
    monkeypatch.delenv("LOCAL_ICANN_ROOT", raising=False)
    root_mode, servers = resolv.decode_servers("8.8.8.8,8.8.4.4")
    assert root_mode is False
    assert servers == ["8.8.8.8", "8.8.4.4"]

    root_mode, servers = resolv.decode_servers(["192.0.2.1"])
    assert root_mode is False
    assert servers == ["192.0.2.1"]

    assert resolv.decode_servers(None) == (False, None)
    assert resolv.decode_servers(5) == (False, None)


def test_decode_servers_icann_root_uses_environment_or_hard_coded_roots(monkeypatch):
    monkeypatch.setenv("LOCAL_ICANN_ROOT", "192.0.2.8,192.0.2.9:5300")
    root_mode, servers = resolv.decode_servers("icann-root")
    assert root_mode is True
    assert servers == ["192.0.2.8", "192.0.2.9:5300"]

    root_mode, servers = resolv.decode_servers(["icann-root"])
    assert root_mode is True
    assert servers == ["192.0.2.8", "192.0.2.9:5300"]

    monkeypatch.delenv("LOCAL_ICANN_ROOT", raising=False)
    root_mode, servers = resolv.decode_servers("icann-root")
    assert root_mode is True
    assert len(servers) == 2
    assert set(servers).issubset(set(resolv.BEST_ICANN_ROOT))
    assert [item[0] for item in resolv.BEST_ICANN_ROOT] == list("dfjk")


def test_module_entry_points(monkeypatch, capsys):
    import flask
    monkeypatch.setattr(flask.Flask, "run", lambda self, *_args, **_kwargs: None)

    monkeypatch.setattr(sys, "argv", ["misc.py", "192.0.2.1:53"])
    runpy.run_path(str(ROOT / "python" / "misc.py"), run_name="__main__")
    assert capsys.readouterr().out.strip() == "('192.0.2.1', 53)"

    monkeypatch.setattr(sys, "argv", ["validation.py"])
    runpy.run_path(str(ROOT / "python" / "validation.py"), run_name="__main__")
    assert "www.gstatic.com." in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["resolv.py", "-h"])
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(str(ROOT / "python" / "resolv.py"), run_name="__main__")
    assert caught.value.code == 0

    runpy.run_path(str(ROOT / "python" / "wsgi.py"), run_name="__main__")
    runpy.run_path(str(ROOT / "python" / "dnsflsk.py"), run_name="__main__")


def test_resolv_host(monkeypatch):
    monkeypatch.setattr(resolv.socket, "gethostbyname", lambda host: "192.0.2.8")
    assert resolv.resolv_host("192.0.2.9") == "192.0.2.9"
    assert resolv.resolv_host("example.com") == "192.0.2.8"
    assert resolv.resolv_host("bad_host") is None
