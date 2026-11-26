#! /usr/bin/python3
# (c) Copyright 2019-2026, James Stevens ... see LICENSE for details
# Alternative license arrangements possible, contact me for more information
""" Support functions for domains """

import idna
import sys


def get_port(server):
    if server.find(":") < 0:
        return server, 53
    a = server.split(":")
    if len(a) == 2 and a[1].isdigit():
        port = int(a[1])
        if port < 1 or port > 65535:
            return server, 53
        return a[0], port
    return server, 53


def puny_to_utf8(name):
    if name == ".":
        return "."

    try:
        idn = idna.decode(name)
        return idn
    except idna.IDNAError:
        try:
            idn = name.encode("utf-8").decode("idna")
            return idn
        except UnicodeError:
            return None
    return None


def utf8_to_puny(utf8):
    if utf8 == ".":
        return "."

    try:
        puny = idna.encode(utf8)
        return puny.decode("utf-8")
    except idna.IDNAError:
        try:
            puny = utf8.encode("idna")
            return puny.decode("utf-8")
        except UnicodeError:
            return None
    return None


if __name__ == "__main__":
    print(get_port(sys.argv[1]))
