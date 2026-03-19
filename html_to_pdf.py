"""Standalone script: reads HTML from stdin, writes PDF to stdout."""
import sys
from playwright.sync_api import sync_playwright

html = sys.stdin.buffer.read().decode("utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content(html, wait_until="networkidle")
    pdf_bytes = page.pdf(
        format="Letter",
        print_background=True,
        margin={"top": "0.4in", "bottom": "0.4in", "left": "0.5in", "right": "0.5in"},
    )
    browser.close()

sys.stdout.buffer.write(pdf_bytes)
