#! /usr/bin/python3
# (c) Copyright 2019-2020, James Stevens ... see LICENSE for details
# Alternative license arrangements possible, contact me for more information

import re
import socket


def is_valid_host(host):
    if host is None:
        return False
    return re.match(
        r'^(?!.{255}|.{253}[^.])([a-z0-9](?:[-a-z-0-9]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?[.]?$',
        host, re.IGNORECASE) is not None


def is_valid_ipv4(address):
    if address is None:
        return False

    try:
        socket.inet_pton(socket.AF_INET, address)
    except AttributeError:  # no inet_pton here, sorry
        try:
            socket.inet_aton(address)
        except socket.error:
            return False
        return address.count('.') == 3
    except socket.error:  # not a valid address
        return False

    return True


# for testing
if __name__ == "__main__":
    for host in ["A_A", "www.gstatic.com.", "m.files.bbci.co.uk."]:
        print(host, is_valid_host(host))
