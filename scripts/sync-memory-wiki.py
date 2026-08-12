#!/usr/bin/env python3
"""Memory-to-Wiki semantic sync entrypoint."""

import os
import urllib.request

base = os.getenv("DHUB_URL", "http://127.0.0.1:10101")
headers = {"Content-Type": "application/json"}
if os.getenv("DHUB_API_KEY"):
    headers["Authorization"] = f"Bearer {os.environ['DHUB_API_KEY']}"
request = urllib.request.Request(
    base + "/sync/trigger", data=b"{}", headers=headers, method="POST"
)
with urllib.request.urlopen(request, timeout=3600) as response:
    print(response.read().decode())
