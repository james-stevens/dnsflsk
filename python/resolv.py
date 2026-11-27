#! /usr/bin/python3
# (c) Copyright 2019-2025, James Stevens ... see LICENSE for details
# Alternative license arrangements possible, contact me for more information
""" module to resolve DNS queries into DoH JSON objects """

import argparse
import base64
import json
import os
import random
import select
import socket
import syslog

import dns
import dns.message
import dns.name
import dns.rdatatype
import misc
import validation

DNS_MAX_RESP = 4096
MAX_TRIES = 5
DNS_FLAGS = {"QR": 0x8000, "AA": 0x0400, "TC": 0x0200, "RD": 0x0100, "AD": 0x20, "CD": 0x40, "RA": 0x80}
STATUS_NAME = {
    0: ["NOERROR", "DNS Query completed successfully"],
    1: ["FORMERR", "DNS Query Format Error"],
    2: ["SERVFAIL", "Server failed to complete the DNS request"],
    3: ["NXDOMAIN", "Domain name does not exist"],
    4: ["NOTIMP", "Function not implemented"],
    5: ["REFUSED", "The server refused to answer for the query"],
    6: ["YXDOMAIN", "Name that should not exist, does exist"],
    7: ["XRRSET", "RRset that should not exist, does exist"],
    8: ["NOTAUTH", "Server not authoritative for the zone"],
    9: ["NOTZONE", "Name not in zone"]
}

BEST_ICANN_ROOT = [pfx + ".root-servers.net." for pfx in "dfjk"]


def resolv_host(server):
    """ resolve {host} to an IP if its a host name """
    if validation.is_valid_ipv4(server):
        return server
    if validation.is_valid_host(server):
        return socket.gethostbyname(server)
    return None


def decode_servers(servers):
    root_mode = False
    if servers == "icann-root" or (isinstance(servers,
                                              (list, tuple)) and len(servers) == 1 and servers[0] == "icann-root"):
        servers = os.environ.get("LOCAL_ICANN_ROOT", random.sample(BEST_ICANN_ROOT, 2))
        root_mode = True
    if isinstance(servers, list):
        return root_mode, servers
    elif isinstance(servers, str):
        return root_mode, servers.split(",")
    return False, None


class ResolvError(Exception):
    """ custom error """


class Resolver:
    """ resolve a DNS <Query> """

    def __init__(self, servers=None):
        self.root_mode = False
        self.servers = None
        if servers is None:
            with open("/etc/resolv.conf", "r") as fd:
                etc_resolv = [line.strip().split() for line in fd if line[0] != '#' and line[:11] == "nameserver "]
            self.servers = [resline[1] for resline in etc_resolv if resline[0] == "nameserver"]
        else:
            self.root_mode, self.servers = decode_servers(servers)

        if self.servers is None or not isinstance(self.servers, list):
            raise ResolvError("Failed to identify servers")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.sock is None:
            raise ResolvError("Failed to open UDP client socket")

        for each_svr in self.servers:
            if not validation.is_valid_ipv4(each_svr):
                raise ResolvError("Invalid IP v4 Address for a Server")

    def resolv(self,
               in_name,
               rdtype,
               force_tcp=False,
               flags=DNS_FLAGS["RD"],
               with_dnssec=False,
               include_raw=False,
               binary_format=False,
               servers=None):

        name = misc.utf8_to_puny(in_name)
        if not validation.is_valid_host(name):
            raise ResolvError(f"Hostname '{name}' failed validation")

        self.this_root_mode, self.this_servers = (self.root_mode,
                                                  self.servers) if servers is None else decode_servers(servers)
        self.svr_ports = [misc.get_port(svr) for svr in self.this_servers]

        self.qryid = None
        self.reply = None
        self.flags = flags
        if self.this_root_mode and self.flags & DNS_FLAGS["RD"]:
            raise ResolvError("ROOT mode requested with RD=1")

        self.force_tcp = force_tcp
        self.binary_format = binary_format
        self.include_raw = include_raw
        if with_dnssec:
            self.include_raw = True

        rdtype = int(rdtype) if isinstance(rdtype, int) else dns.rdatatype.from_text(rdtype)

        self.expiry = 1
        self.tries = 0
        msg = dns.message.make_query(name, rdtype, payload=30000, want_dnssec=with_dnssec, flags=self.flags)
        self.question = bytearray(msg.to_wire())
        return self.do_resolv()

    def send_all(self):
        """ send the query to all servers """
        ret = False
        for each_svr, each_port in self.svr_ports:
            try:
                sent_len = self.sock.sendto(self.question, (each_svr, each_port))
                ret = ret or (sent_len == len(self.question))
            except (OSError, TypeError) as err:
                syslog.syslog(f"RESOLVER: send_all - {err!s}")

        return ret  # True if at least one worked

    def send(self):
        """ send the DNS query out """
        if self.question is None:
            return None
        self.question[0] = 0
        self.question[1] = 0
        while self.question[0] == 0 and self.question[1] == 0:
            self.qryid = os.urandom(2)
            self.question[0] = self.qryid[0]
            self.question[1] = self.qryid[1]

        return self.send_all()

    def match_id(self):
        """ cehck the DNS quiery Id field matches what we asked """
        return (self.qryid is not None and self.reply[0] == self.qryid[0] and self.reply[1] == self.qryid[1])

    def do_resolv(self):
        """ look for dns UDP response and read it """
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        while self.tries < MAX_TRIES:
            if not self.send():
                self.sock.close()
                self.sock = None
                return None

            while True:
                rlist, _, _ = select.select([self.sock], [], [], self.expiry)
                if len(rlist) <= 0:
                    break

                self.reply, (rmt_addr, rmt_port) = self.sock.recvfrom(DNS_MAX_RESP)
                if self.match_id():
                    self.decoded_resp = dns.message.from_wire(self.reply)

                    if (self.decoded_resp.flags & DNS_FLAGS["TC"]) > 0 or self.force_tcp:
                        self.reply = self.ask_in_tcp(rmt_addr, rmt_port)
                        self.decoded_resp = dns.message.from_wire(self.reply)

                    if (ret := self.decode_reply()) is None:
                        return None

                    if self.binary_format:
                        return self.reply

                    ret["Responder"] = f"{rmt_addr}:{rmt_port}"
                    return ret

            self.expiry += int(self.expiry / 2) if self.expiry > 2 else 1
            self.tries += 1

        return None

    def find_port(self, addr):
        for svr, port in self.svr_ports:
            if svr == addr:
                return port
        return 53

    def ask_in_tcp(self, addr, port=53):
        sock = socket.socket()
        sock.setblocking(True)
        sock.connect((addr, port))
        sock.send(len(self.question).to_bytes(2, "big") + self.question)
        sock.settimeout(5)
        reply = b""
        target_length = None
        while target_length is None or len(reply) < target_length:
            try:
                reply = reply + sock.recv(2000)
                if target_length is None and len(reply) >= 2:
                    target_length = reply[0] * 256 + reply[1] + 2
            except TimeoutError:
                sock.close()
                return reply[2:]
            sock.settimeout(0.2)
        sock.close()
        return reply[2:]

    def json_record(self, rr, i):
        ret = {
            "name": rr.name.to_text(),
            "data": i.to_text(),
            "TTL": rr.ttl,
            "type": rr.rdtype,
            "typename": dns.rdatatype.to_text(rr.rdtype)
        }
        if self.include_raw:
            ret["rdata"] = base64.b64encode(i.to_wire()).decode("utf8")
        return ret

    def decode_reply(self):
        """ decode binary {message} in DNS format to dictionary in DoH fmt """
        if (self.decoded_resp.flags & DNS_FLAGS["QR"]) == 0:
            return None  # REPLY flag not set

        out = {}

        for flag, mask in DNS_FLAGS.items():
            out[flag] = (self.decoded_resp.flags & mask) != 0

        rcode = self.decoded_resp.rcode()
        out["Status"] = rcode
        if rcode in STATUS_NAME:
            out["Status Name"] = STATUS_NAME[rcode]

        out["Question"] = [{
            "name": rr.name.to_text(),
            "TTL": rr.ttl,
            "type": rr.rdtype,
            "typename": dns.rdatatype.to_text(rr.rdtype)
        } for rr in self.decoded_resp.question]

        out["Answer"] = [self.json_record(rr, i) for rr in self.decoded_resp.answer for i in rr]
        out["Authority"] = [self.json_record(rr, i) for rr in self.decoded_resp.authority for i in rr]
        out["Additional"] = [self.json_record(rr, i) for rr in self.decoded_resp.additional for i in rr]

        return out


def main():
    """ main """
    parser = argparse.ArgumentParser(description='This is a wrapper to test the resolver code')
    parser.add_argument("-s", "--servers", help="Resolvers to query")
    parser.add_argument("-n", "--name", default="jrcs.net", help="Name to query for")
    parser.add_argument("-t", "--rdtype", default="txt", help="RR Type to query for")
    parser.add_argument("-r", "--include-raw", default=False, help="Include raw RDATA in base64", action="store_true")
    parser.add_argument("-d", "--with_dnssec", default=False, help="With DNSSEC", action="store_true")
    parser.add_argument("-T", "--force-tcp", default=False, help="Force TCP query", action="store_true")
    parser.add_argument("-R",
                        "--no-recursion",
                        help="Make authritative, not recursive query (RD=0)",
                        action="store_true")
    args = parser.parse_args()

    res = Resolver()
    flags = 0 if args.no_recursion else DNS_FLAGS["RD"]
    print(
        json.dumps(res.resolv(args.name,
                              args.rdtype,
                              with_dnssec=args.with_dnssec,
                              include_raw=args.include_raw,
                              force_tcp=args.force_tcp,
                              servers=args.servers,
                              flags=flags),
                   indent=2))


if __name__ == "__main__":
    main()
