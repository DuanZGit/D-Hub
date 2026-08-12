#!/usr/bin/env python3
"""Memory-to-Wiki semantic sync entrypoint."""
import json, os, urllib.request
base=os.getenv("DHUB_URL","http://127.0.0.1:10101")
req=urllib.request.Request(base+"/sync/trigger",data=b"{}",headers={"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(req,timeout=3600) as r: print(r.read().decode())
