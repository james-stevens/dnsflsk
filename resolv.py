#! /usr/bin/python3

import socket
import select
import os
import dns
import dns.name
import dns.message

DNS_HDR_LEN = 12
DNS_MAX_RESP = 4096
MAX_CLIENTS = 10
MAX_EXPIRY = 30


class Resolver:
    def __init__(self, qry):
        self.servers = qry["servers"]
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.expiry = 1
        self.question = bytearray(
            dns.message.make_query(qry["name"],
                                   qry["type"],
                                   want_dnssec=qry["do"]).to_wire())
        if self.question is None:
            return None

    def send_all(self):
        ret = False
        for s in self.servers:
            sz = self.sock.sendto(self.question, (s, 53))
            ret = ret or (sz == len(self.question))
        return ret

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
            if not self.send():
                return None

            rlist, wlist, xlist = select.select([self.sock], [], [],
                                                self.expiry)
            if len(rlist) > 0:
                break
            self.expiry = self.expiry + self.expiry
            if self.expiry > MAX_EXPIRY:
                return None

        self.reply, (addr, port) = self.sock.recvfrom(DNS_MAX_RESP)
        if self.match_id():
            return self.decode_reply()

        return None

    def decode_reply(self):
        x = dns.message.from_wire(self.reply)
        out = {}

        out["Status"] = x.rcode()
        out["RA"] = (x.flags & 0x80) != 0
        out["AD"] = (x.flags & 0x40) != 0
        out["CD"] = (x.flags & 0x20) != 0
        out["RD"] = (x.flags & 0x0100) != 0
        out["TC"] = (x.flags & 0x0200) != 0

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
