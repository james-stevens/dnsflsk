#! /usr/bin/python3
# (c) Copyright 2019-2025, James Stevens ... see LICENSE for details
# Alternative license arrangements possible, contact me for more information
""" module to resolve DNS queries into DoH JSON objects """

import socket
import select
import argparse
import os
import base64
import json
import dns
import dns.name
import dns.message
import dns.rdatatype
import syslog

import validation

DNS_MAX_RESP = 4096
MAX_TRIES = 5
DNS_FLAGS = {
    "QR": 0x8000,
    "AA": 0x0400,
    "TC": 0x0200,
    "RD": 0x0100,
    "AD": 0x20,
    "CD": 0x40,
    "RA": 0x80
}
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


def resolv_host(server):
    """ resolve {host} to an IP if its a host name """
    if validation.is_valid_ipv4(server):
        return server
    if validation.is_valid_host(server):
        return socket.gethostbyname(server)
    return None


class ResolvError(Exception):
    """ custom error """


class Resolver:
    """ resolve a DNS <Query> """

    def __init__(self, servers=None):
        self.servers = None
        if servers is None:
            with open("/etc/resolv.conf", "r") as fd:
                etc_resolv = [
                    line.strip().split() for line in fd.readlines()
                    if line[0] != '#' and line[:11] == "nameserver "
                ]
            self.servers = [
                resline[1] for resline in etc_resolv
                if resline[0] == "nameserver"
            ]
        else:
            if servers is not None:
                if isinstance(servers, list):
                    self.servers = servers
                elif isinstance(servers, str):
                    self.servers = servers.split(",")

        if self.servers is None or not isinstance(self.servers, list):
            raise ResolvError("Failed to identify servers")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.sock is None:
            raise ResolvError("Failed to open UDP client socket")

        for each_svr in self.servers:
            if not validation.is_valid_ipv4(each_svr):
                raise ResolvError("Invalid IP v4 Address for a Server")

    def resolv(self,
               name,
               rdtype,
               force_tcp=False,
               flags=DNS_FLAGS["RD"],
               with_dnssec=False,
               include_raw=False,
               binary_format=False,
               servers=None):
        if not validation.is_valid_host(name):
            raise ResolvError(f"Hostname '{name}' failed validation")

        if servers is not None:
            self.this_servers = servers
        else:
            self.this_servers = self.servers

        self.qryid = None
        self.reply = None
        self.flags = flags
        self.force_tcp = force_tcp
        self.include_raw = include_raw
        if with_dnssec:
            self.include_raw = True

        if not validation.is_valid_host(name):
            raise ResolvError(f"Hostname '{name}' failed validation")

        rdtype = int(rdtype) if isinstance(
            rdtype, int) else dns.rdatatype.from_text(rdtype)

        self.expiry = 1
        self.tries = 0
        msg = dns.message.make_query(name,
                                     rdtype,
                                     payload=30000,
                                     want_dnssec=with_dnssec,
                                     flags=self.flags)
        self.question = bytearray(msg.to_wire())
        return self.do_resolv()

    def send_all(self):
        """ send the query to all servers """
        ret = False
        for each_svr in self.this_servers:
            try:
                sent_len = self.sock.sendto(self.question, (each_svr, 53))
                ret = ret or (sent_len == len(self.question))
            # pylint: disable=broad-except
            except Exception as err:
                syslog.syslog(f"RESOLVER: send_all - {str(err)}")

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
        return (self.qryid is not None and self.reply[0] == self.qryid[0]
                and self.reply[1] == self.qryid[1])

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

                self.reply, (addr, _) = self.sock.recvfrom(DNS_MAX_RESP)
                if self.match_id():
                    self.decoded_resp = dns.message.from_wire(self.reply)

                    if (self.decoded_resp.flags
                            & DNS_FLAGS["TC"]) > 0 or self.force_tcp:
                        self.reply = self.ask_in_tcp(addr)
                        self.decoded_resp = dns.message.from_wire(self.reply)

                    if (ret := self.decode_reply()) is None:
                        return None

                    ret["Responder"] = addr
                    return ret

            self.expiry += int(self.expiry / 2) if self.expiry > 2 else 1
            self.tries += 1

        return None

    def ask_in_tcp(self, addr):
        sock = socket.socket()
        sock.setblocking(True)
        sock.connect((addr, 53))
        sock.send(len(self.question).to_bytes(2, "big") + self.question)
        sock.settimeout(5)
        reply = bytes()
        target_length = None
        while target_length is None or len(reply) < target_length:
            try:
                reply = reply + sock.recv(2000)
                if target_length is None and len(reply) >= 2:
                    target_length = reply[0] * 256 + reply[1] + 2
            except socket.timeout:
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

        for flag in DNS_FLAGS:
            out[flag] = (self.decoded_resp.flags & DNS_FLAGS[flag]) != 0

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

        out["Answer"] = [
            self.json_record(rr, i) for rr in self.decoded_resp.answer
            for i in rr
        ]
        out["Authority"] = [
            self.json_record(rr, i) for rr in self.decoded_resp.authority
            for i in rr
        ]
        out["Additional"] = [
            self.json_record(rr, i) for rr in self.decoded_resp.additional
            for i in rr
        ]

        return out


def main():
    """ main """
    parser = argparse.ArgumentParser(
        description='This is a wrapper to test the resolver code')
    parser.add_argument("-s", "--servers", help="Resolvers to query")
    parser.add_argument("-n",
                        "--name",
                        default="jrcs.net",
                        help="Name to query for")
    parser.add_argument("-t",
                        "--rdtype",
                        default="txt",
                        help="RR Type to query for")
    parser.add_argument("-r",
                        "--include-raw",
                        default=False,
                        help="Include raw RDATA in base64",
                        action="store_true")
    parser.add_argument("-d",
                        "--with_dnssec",
                        default=False,
                        help="With DNSSEC",
                        action="store_true")
    parser.add_argument("-T",
                        "--force-tcp",
                        default=False,
                        help="Force TCP query",
                        action="store_true")
    parser.add_argument("-R",
                        "--no-recursion",
                        help="Make authritative, not recursive query (RD=0)",
                        action="store_true")
    args = parser.parse_args()

    if not validation.is_valid_host(args.name):
        print(f"ERROR: '{args.name}' is an invalid host name")
    else:
        res = Resolver()
        flags = 0 if args.no_recursion else DNS_FLAGS["RD"]
        servers = args.servers.split(",") if args.servers else None
        print(
            json.dumps(res.resolv(args.name,
                                  args.rdtype,
                                  with_dnssec=args.with_dnssec,
                                  include_raw=args.include_raw,
                                  force_tcp=args.force_tcp,
                                  servers=servers,
                                  flags=flags),
                       indent=2))


if __name__ == "__main__":
    main()
