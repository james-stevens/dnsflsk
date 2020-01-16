#! /usr/bin/python3

import re
import socket

is_valid_host_re = re.compile(r'^([0-9a-z][-\w]*[0-9a-z]\.)+[a-z0-9\-]{2,15}$')


def is_valid_host(host):
    return is_valid_host_re.match(host) is not None


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
