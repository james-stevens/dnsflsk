#! /usr/bin/python3

import validation

import socket
import select
import os
import dns
import dns.name
import dns.message
import dns.rdatatype

DNS_HDR_LEN = 12
DNS_MAX_RESP = 4096
MAX_CLIENTS = 10
MAX_TRIES = 5


def resolv_host(server):
    if validation.is_valid_ipv4(server):
        return server
    if validation.is_valid_host(server):
        return socket.gethostbyname(server)
    return None


class Resolver:
    def __init__(self, qry):
        if not validation.is_valid_host(qry.name):
            raise ValueError("Invalid host name")

        rdtype = qry.rdtype
        if type(rdtype) != int:
            if rdtype.isdigit():
                rdtype = int(rdtype)
            else:
                rdtype = dns.rdatatype.from_text(rdtype)

        if hasattr(qry, "servers"):
            self.servers = qry.servers
        else:
            self.servers = ["8.8.8.8", "8.8.4.4"]

        for s in qry.servers:
            if not validation.is_valid_ipv4(s):
                raise ValueError("Invalid IP v4 Address for a Server")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.sock is None:
            raise OSError("Failed to open UDP client socket")

        self.expiry = 2
        self.tries = 0
        msg = dns.message.make_query(qry.name,
                                     rdtype,
                                     want_dnssec=(qry.do or qry.cd))

        self.question = bytearray(msg.to_wire())

    def send_all(self):
        ret = False
        for s in self.servers:
            try:
                sz = self.sock.sendto(self.question, (s, 53))
                ret = ret or (sz == len(self.question))
            except Exception as e:
                pass

        return ret  # True if at least one worked

    def send(self):
        if self.question is None:
            return None
        self.question[0] = 0
        self.question[1] = 0
        while self.question[0] == 0 and self.question[1] == 0:
            self.id = os.urandom(2)
            self.question[0] = self.id[0]
            self.question[1] = self.id[1]

        return self.send_all()

    def match_id(self):
        return (self.id is not None and self.reply[0] == self.id[0]
                and self.reply[1] == self.id[1])

    def recv(self):
        while True:
            self.tries = self.tries + 1

            if not self.send():
                self.sock.close()
                return None

            rlist, wlist, xlist = select.select([self.sock], [], [],
                                                self.expiry)
            if len(rlist) > 0:
                self.reply, (addr, port) = self.sock.recvfrom(DNS_MAX_RESP)
                if self.match_id():
                    ret = self.decode_reply()
                    if ret is None:
                        return None
                    ret["Responder"] = addr
                    self.sock.close()
                    return ret

            self.expiry = self.expiry + int(self.expiry / 2)
            if self.tries >= MAX_TRIES:
                self.sock.close()
                return None

        self.sock.close()
        return None

    def decode_reply(self):
        x = dns.message.from_wire(self.reply)
        if (x.flags & 0x8000) == 0:
            return None  # REPLY flag not set

        out = {}

        out["Status"] = x.rcode()
        out["RA"] = (x.flags & 0x80) != 0
        out["AD"] = (x.flags & 0x40) != 0
        out["CD"] = (x.flags & 0x20) != 0
        out["RD"] = (x.flags & 0x0100) != 0
        out["TC"] = (x.flags & 0x0200) != 0
        out["AA"] = (x.flags & 0x0400) != 0
        out["QR"] = (x.flags & 0x8000) != 0

        out["Question"] = [{
            "name": rr.name.to_text(),
            "type": rr.rdtype
        } for rr in x.question]
        out["Answer"] = [{
            "name": rr.name.to_text(),
            "data": i.to_text(),
            "type": rr.rdtype
        } for rr in x.answer for i in rr]
        out["Authority"] = [{
            "name": rr.name.to_text(),
            "data": i.to_text(),
            "type": rr.rdtype
        } for rr in x.authority for i in rr]

        return out
