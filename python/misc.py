#! /usr/bin/python3
# (c) Copyright 2019-2026, James Stevens ... see LICENSE for details
# Alternative license arrangements possible, contact me for more information
""" Support functions for domains """

import idna


def puny_to_utf8(name):
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
