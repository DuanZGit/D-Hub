# -*- coding: utf-8 -*-
"""Build an A4 PDF from a markdown travel guide.

Pipeline: markdown -> HTML (md_to_html.py) -> Edge headless print-to-pdf
-> QA (pdfplumber page count / size). Prints the output path on success.

Usage:
    python build_pdf.py input.md output.pdf [--title "Guide Title"]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from md_to_html import md_to_html

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/microsoft-edge",
    "/usr/bin/microsoft-edge-stable",
]
EDGE_NAMES = ["msedge", "microsoft-edge", "microsoft-edge-stable"]
PW_CACHE = os.path.expanduser("~/.cache/ms-playwright")


def find_playwright_chromium():
    """Path to Playwright-managed Chromium (this box has no Edge/Chrome)."""
    if not os.path.isdir(PW_CACHE):
        return None
    try:
        entries = sorted(os.listdir(PW_CACHE), reverse=True)
    except OSError:
        return None
    for d in entries:
        if not d.startswith("chromium-"):
            continue
        for sub in ("chrome-linux64/chrome", "chrome-linux/chrome"):
            exe = os.path.join(PW_CACHE, d, sub)
            if os.path.exists(exe):
                return exe
    return None


def print_via_playwright(html_path, pdf_path):
    """Preferred pipeline off-Windows: playwright page.pdf() (verified on this box)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    from pathlib import Path
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(Path(html_path).resolve().as_uri(), wait_until="load")
            page.pdf(path=pdf_path, format="A4", print_background=True)
            browser.close()
    except Exception as exc:  # noqa: BLE001 - fall back to CLI
        print(f"playwright pdf failed: {exc}", file=sys.stderr)
        return False
    return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1_000


def find_edge():
    for c in EDGE_CANDIDATES:
        if os.path.exists(c):
            return c
    for name in EDGE_NAMES:
        p = shutil.which(name)
        if p:
            return p
    return None


def qa_pdf(pdf_path, min_size=10_000):
    try:
        import pdfplumber
    except ImportError:
        return None
    pages = pdfplumber.open(pdf_path).pages
    return len(pages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_md")
    ap.add_argument("output_pdf")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.input_md):
        sys.exit("input markdown not found: " + args.input_md)
    out_pdf = os.path.abspath(args.output_pdf)

    workdir = tempfile.mkdtemp(prefix="trip-planner-")
    try:
        html_path = os.path.join(workdir, "guide.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(md_to_html(args.input_md, args.title))
        if not print_via_playwright(html_path, out_pdf):
            edge = find_edge() or find_playwright_chromium()
            if not edge:
                sys.exit("No PDF engine: install playwright (pw-venv) or Microsoft Edge.")
            profile = os.path.join(workdir, "edge-profile")
            cmd = [
                edge, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
                "--disable-extensions", "--no-pdf-header-footer",
                f"--user-data-dir={profile}",
                f"--print-to-pdf={out_pdf}",
                "file:///" + html_path.replace("\\", "/"),
            ]
            subprocess.run(cmd, check=False, timeout=120)
        if not os.path.exists(out_pdf) or os.path.getsize(out_pdf) < 1_000:
            sys.exit("PDF not produced; check the PDF engine invocation.")
        pages = qa_pdf(out_pdf)
        print(f"PDF written: {out_pdf}")
        if pages:
            print(f"QA ok: {pages} page(s)")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
