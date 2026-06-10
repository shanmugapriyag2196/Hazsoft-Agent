#!/usr/bin/env python
import sys, io, re
from pathlib import Path
sys.path.insert(0, str(Path('.')))
from config import PDF_FOLDER
from pypdf import PdfReader

def show(file, pages=2):
    reader = PdfReader(str(PDF_FOLDER / file))
    text = ' '.join(page.extract_text() or '' for page in reader.pages[:pages])
    print(f"\n{'='*60}\n{file}\n{'='*60}")
    print(text[:1200])

show('11859.pdf')
show('10416.pdf')
show('11860.pdf')
show('201259.pdf')
