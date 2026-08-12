#!/usr/bin/env python3
"""Memory-to-Wiki semantic sync entrypoint."""

import os
import urllib.request

base = os.getenv("DHUB_URL", "http://127.0.0.1:10101")
headers = {"Content-Type": "application/json"}
admin_key = os.getenv("DHUB_ADMIN_KEY") or os.getenv("DHUB_API_KEY")
if admin_key:
    headers["Authorization"] = f"Bearer {admin_key}"
request = urllib.request.Request(
    base + "/sync/trigger", data=b"{}", headers=headers, method="POST"
)
with urllib.request.urlopen(request, timeout=3600) as response:
    print(response.read().decode())
