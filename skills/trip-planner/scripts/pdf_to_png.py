"""Render PDF pages to PNG for visual QA (replaces pdftoppm on boxes without poppler).

Usage:
    ~/pw-venv/bin/python pdf_to_png.py input.pdf out_prefix [--scale 2]
Writes <out_prefix>_p1.png, _p2.png, ... and prints the page count.
"""
import argparse
import sys

try:
    import pypdfium2 as pdfium
except ImportError:
    sys.exit("pypdfium2 missing; run: ~/pw-venv/bin/pip install pypdfium2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_pdf")
    ap.add_argument("out_prefix")
    ap.add_argument("--scale", type=float, default=2.0)
    args = ap.parse_args()

    pdf = pdfium.PdfDocument(args.input_pdf)
    for i in range(len(pdf)):
        out = f"{args.out_prefix}_p{i + 1}.png"
        pdf[i].render(scale=args.scale).to_pil().save(out)
        print(f"page {i + 1} -> {out}")
    print(f"total {len(pdf)} page(s)")


if __name__ == "__main__":
    main()
