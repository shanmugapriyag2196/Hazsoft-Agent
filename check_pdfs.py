#!/usr/bin/env python
"""Read specific PDFs to verify classification."""
from pathlib import Path
import sys, io

sys.path.insert(0, str(Path(__file__).parent))
from config import PDF_FOLDER

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit(1)

check_files = [
    "267068.pdf",   # Virex disinfectant - got Hazardous-Alcohol (wrong)
    "15587.pdf",    # RBC Lysing Agent - got Others-Oxygen (wrong)
    "267394.pdf",   # Norepinephrine - got Hazardous-Oxygen (wrong)
    "201259.pdf",   # pH Indicator - got Hazardous-Oxygen (wrong)
    "284554.pdf",   # Liquichek immunoassay - got Non-Hazardous-Cleaning (wrong)
    "291286.pdf",   # Liquichek Diabetes - got Non-Hazardous-Cleaning (wrong)
]

for name in check_files:
    pdf = PDF_FOLDER / name
    reader = PdfReader(str(pdf))
    text = ""
    for page in reader.pages[:2]:
        t = page.extract_text()
        if t:
            text += t
    print(f"\n{'='*60}")
    print(f"FILE: {name}")
    print(f"{'='*60}")
    print(text[:1500])
    print("...")
