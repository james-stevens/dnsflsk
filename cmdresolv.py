#! /usr/bin/python3

import resolv
import sys
import json
import argparse

parser = argparse.ArgumentParser(description='Process some integers.')

parser.add_argument("-s",
                    '--servers',
                    help='Comma separated list of server ip addresses')

parser.add_argument("-t",
                    '--rdtype',
                    help='Record type to query (number or name), default=A')

parser.add_argument("-n", '--name', help='Name to look-up')

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

c = resolv.Resolver(args)
ret = c.recv()
if ret is None:
    print("Lookup failed")
    sys.exit(32)
else:
    print(json.dumps(ret, indent=3))
    sys.exit(ret["Status"])
