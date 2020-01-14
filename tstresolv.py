#! /usr/bin/python3

import resolv
import sys
import json

c = resolv.Resolver(sys.argv[1],int(sys.argv[2]),servers=["192.168.1.20"])
print(json.dumps(c.recv(),indent=3))
