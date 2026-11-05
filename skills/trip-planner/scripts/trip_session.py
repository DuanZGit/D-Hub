"""Load site cookies exported by the cookie-getter userscript into Playwright.

Usage:
    ~/pw-venv/bin/python trip_session.py --cookies ~/.secrets/trip_ctrip.json \
        --domain .ctrip.com --url https://hotels.ctrip.com/ --shot /tmp/ctrip.png

Accepts either the userscript's JSON format (name/value/domain/path/httpOnly/...)
or the raw "Cookie 请求头" string (name=value; name=value), in which case
--domain is required. Keeps a persistent profile per --site so later runs reuse
the session.
"""
import argparse
import json
import os
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright missing; run with ~/pw-venv/bin/python")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def parse_cookies(path, domain):
    raw = Path(path).read_text(encoding="utf-8").strip()
    if raw.startswith(("[", "{")):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            sys.exit(f"cookie file is not valid JSON ({path}): {exc}")
        items = data if isinstance(data, list) else data.get("cookies", [])
        out = []
        for c in items:
            if not c.get("name"):
                continue
            ck = {"name": c["name"], "value": c.get("value") or "",
                  "domain": c.get("domain") or domain, "path": c.get("path") or "/"}
            if c.get("expirationDate"):
                ck["expires"] = float(c["expirationDate"])
            if c.get("secure"):
                ck["secure"] = True
            if c.get("httpOnly"):
                ck["httpOnly"] = True
            if c.get("sameSite") in ("Strict", "Lax", "None"):
                ck["sameSite"] = c["sameSite"]
            out.append(ck)
        return out
    # raw header string: split on ';' but only before a token that looks like name=
    pairs, out = [], []
    for part in raw.replace("\n", "; ").split(";"):
        part = part.strip()
        if "=" in part:
            pairs.append(part)
    for p in pairs:
        name, _, value = p.partition("=")
        if name.strip():
            out.append({"name": name.strip(), "value": value,
                        "domain": domain, "path": "/"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookies", required=True)
    ap.add_argument("--domain", required=True, help="e.g. .ctrip.com (used when file has no domain)")
    ap.add_argument("--url", required=True)
    ap.add_argument("--site", default="default", help="persistent profile name")
    ap.add_argument("--shot", default=None)
    ap.add_argument("--ua", default=UA)
    ap.add_argument("--keep-open", type=float, default=0.0,
                    help="seconds to wait before closing (lets dynamic content settle)")
    args = ap.parse_args()

    cookies = parse_cookies(args.cookies, args.domain)
    if not cookies:
        sys.exit("no cookies parsed from " + args.cookies)
    profile = os.path.expanduser(f"~/.cache/trip-planner/profile-{args.site}")
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError as exc:
        sys.exit(f"cannot create profile dir {profile}: {exc}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, headless=True, user_agent=args.ua,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 1000}, locale="zh-CN",
            timezone_id="Asia/Shanghai")
        ctx.add_cookies(cookies)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        resp = page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        if args.keep_open:
            page.wait_for_timeout(args.keep_open * 1000)
        print(f"cookies loaded: {len(cookies)}")
        print(f"http status: {resp.status if resp else 'n/a'}")
        print(f"title: {page.title()}")
        print(f"url: {page.url}")
        if args.shot:
            page.screenshot(path=args.shot, full_page=False)
            print(f"screenshot: {args.shot}")
        ctx.close()


if __name__ == "__main__":
    main()
