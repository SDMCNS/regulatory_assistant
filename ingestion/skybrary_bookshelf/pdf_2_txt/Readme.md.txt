Robust PDF → Text Batch Extractor
This is intended to be used as an ingestion gate before downstream document
processing.
It deliberately distinguishes:
- PASS — extraction looks clean.
- WARN — usable text was extracted, but something deserves review.
- FAIL — extraction is sufficiently suspect that the document should not be
  treated as clean without follow-up.
Install
Basic extraction:
python -m pip install -r requirements.txt
For OCR, install Tesseract as well as the Python packages.
On Windows, if Tesseract is not on PATH:
python pdf_to_text.py .\pdfs .\text --ocr --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe"
Basic run
python pdf_to_text.py .\pdfs .\text
Recursive:
python pdf_to_text.py .\pdfs .\text --recursive
With OCR fallback:
python pdf_to_text.py .\pdfs .\text --recursive --ocr
Parallel processing:
python pdf_to_text.py .\pdfs .\text --recursive --ocr --workers 4
For a first production run I recommend --workers 1. Once the pipeline is
proven stable, increase it.
Output
The output directory contains:
text/
├── document1.txt
├── document2.txt
├── subdirectory/
│   └── document3.txt
├── _pdf_extraction_report.csv
├── _pdf_extraction_report.jsonl
├── _FOLLOW_UP.md
└── _batch_metadata.json
Every extracted document contains explicit page boundaries:
--- PAGE 1 ---

...

--- PAGE 2 ---

...
This is useful for later regulatory chunking and for tracing bad chunks back
to the source PDF.
What is checked?
Unicode
The validator counts:
- Unicode replacement character �
- Unicode unassigned characters
- control characters
- private-use characters
- surrogate characters
- suspicious formatting/control characters
A small amount produces a warning; excessive corruption produces FAIL.
Mojibake
The script looks for common broken-encoding signatures such as:
- Ã
- Â
- â€
- ðŸ
- ï¿½
These are warnings rather than automatic failures because an unusual character
sequence is not necessarily corruption.
Text density
It checks:
- total characters
- total words
- alphanumeric ratio
- empty pages
- very short pages
- pages with little/no native text
OCR
OCR is deliberately fallback, not the primary extraction method.
A page is considered for OCR if native extraction is:
- empty
- extremely short
- contains replacement characters
- contains Unicode-unassigned characters
OCR only replaces native text when it produces materially more text. This
prevents good embedded PDF text being unnecessarily replaced by lower-quality
OCR.
The report records:
- OCR pages
- OCR character count
- average OCR confidence
- OCR failures
Traceability
Every source PDF receives:
- SHA-256
- source path
- output path
- page count
- processing time
- detailed validation statistics
This means you can detect if a source PDF changes later.
Important
A WARN is not necessarily a bad document.
For example, a regulatory PDF may legitimately contain unusual symbols or a
few blank pages.
A FAIL means the document should be inspected before downstream ingestion.
The _FOLLOW_UP.md report is intended to be the human review queue.
Recommended pipeline
For your regulation project:
PDF
 ↓
PDF extraction
 ↓
Unicode / structural validation
 ↓
PASS ───────────────→ downstream ingestion
 │
 ├─ WARN → retain but review
 │
 └─ FAIL → manual/OCR/special handling
Do not feed FAIL documents into the main legal/regulatory corpus without
review.
The CSV/JSONL reports can also be consumed by a later automated ingestion
manager.