#!/usr/bin/env python
"""Debug classification for 267068.pdf (Virex)."""
import sys, io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import PDF_FOLDER

from pypdf import PdfReader

pdf = PDF_FOLDER / "267068.pdf"
reader = PdfReader(str(pdf))
text = ""
for page in reader.pages[:3]:
    t = page.extract_text()
    if t:
        text += t.lower() + " "

print("=== FULL TEXT (first 2000 chars) ===")
print(text[:2000])
print("\n=== HAZARD CHECKS ===")
checks = [
    "not classified as hazardous",
    "flammable liquids, category",
    "signal word: danger",
    "skin corrosion",
    "serious eye damage",
    "causes severe",
    "hazard",
    "danger",
    "alcohol",
]
for c in checks:
    found = c in text
    idx = text.find(c)
    context = text[max(0,idx-20):idx+60] if idx >= 0 else "N/A"
    print(f"  '{c}': {found} | context: {context!r}")
