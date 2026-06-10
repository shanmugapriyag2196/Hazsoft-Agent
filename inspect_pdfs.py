#!/usr/bin/env python
"""Read and dump first 3 pages of each PDF to understand content."""
from pathlib import Path
import sys
from config import PDF_FOLDER

sys.path.insert(0, str(Path(__file__).parent))

try:
    from pypdf import PdfReader
except ImportError:
    print("Install pypdf first")
    sys.exit(1)

pdfs = sorted(PDF_FOLDER.glob("*.pdf"))
print(f"Total PDFs: {len(pdfs)}\n")
for pdf in pdfs:
    reader = PdfReader(str(pdf))
    text = ""
    for i, page in enumerate(reader.pages[:3]):
        t = page.extract_text()
        if t:
            text += t
    print(f"{'='*80}")
    print(f"FILE: {pdf.name}")
    print(f"SIZE: {pdf.stat().st_size} bytes")
    print(f"{'='*80}")
    print(text[:800])
    print("\n")
