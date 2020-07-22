#! /usr/bin/python3
# (c) Copyright 2019-2020, James Stevens ... see LICENSE for details
# Alternative license arrangements possible, contact me for more information

import resolv

import socket
import sys
import json
import argparse
import validation

dohServers = "8.8.8.8,8.8.4.4"
if "DOH_SERVERS" in os.environ:
    dohServers = os.environ["DOH_SERVERS"]

parser = argparse.ArgumentParser(description='Process some integers.')

parser.add_argument("-s",
                    '--servers',
                    default=dohServers,
                    help='Comma separated list of server ip addresses')

parser.add_argument("-t",
                    '--rdtype',
                    default=1,
                    help='Record type to query (number or name), default=A')

parser.add_argument("-n", '--name', required=True, help='Name to look-up')

parser.add_argument("-d",
                    '--do',
                    help='Set DO bit',
                    action="store_true",
                    default=False)

parser.add_argument("-c",
                    '--cd',
                    help='Same as --do',
                    action="store_true",
                    default=False)

args = parser.parse_args()

args.servers = args.servers.split(",")
args.servers = [resolv.resolv_host(s) for s in args.servers]

res = resolv.Resolver(args)

ret = res.recv()
if ret is None:
    print("Lookup failed")
    sys.exit(32)
else:
    print(json.dumps(ret, indent=3))
    sys.exit(ret["Status"])
