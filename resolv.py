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
    def encode_query(self, dns_name, dns_type):
        try:
            self.asked = dns.name.from_text(dns_name)
        except:
            return None

        ba = list(self.asked.to_wire())

        sz = len(ba) + DNS_HDR_LEN + 4
        pkt = bytearray(sz)

        p = DNS_HDR_LEN
        for c in ba:
            pkt[p] = c
            p = p + 1

        pkt[2] = 1  # RD=1
        pkt[5] = 1  # qcount=1

        p = len(ba) + DNS_HDR_LEN
        pkt[p] = (dns_type & 0xff00) >> 8
        pkt[p + 1] = dns_type & 0xff
        pkt[p + 3] = 1  # CLASS=IN

        return pkt

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

    def recv(self):
        while True:
            if not self.send():
                return None

            rlist, wlist, xlist = select.select([self.sock], [], [],
                                                self.expiry)
            if len(rlist) > 0:
                break
            if self.expiry > MAX_EXPIRY:
                return None

        self.reply, (addr, port) = self.sock.recvfrom(DNS_MAX_RESP)
        if self.match_id():
            return self.decode_reply()

        return None

    def __init__(self, dns_name, dns_type, servers=["8.8.8.8"]):
        self.servers = servers
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.expiry = 1
        self.question = self.encode_query(dns_name, dns_type)
        if self.question is None:
            return None

    def match_id(self):
        return (self.id is not None and self.reply[0] == self.id[0]
                and self.reply[1] == self.id[1])

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
