#! /usr/bin/python3

import resolv
import sys
import json

c = resolv.Resolver({
    "name": sys.argv[1],
    "type": int(sys.argv[2]),
    "do": True,
    "servers": ["8.8.8.8"]
})
print(json.dumps(c.recv(), indent=3))
