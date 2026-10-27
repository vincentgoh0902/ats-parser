# ats-parser

A mini ATS reader. Upload a resume PDF and see what an Applicant Tracking System
actually pulls out of it: the raw text in the order a parser reads it, the
structured fields (contact, sections, jobs, dates, skills), every link and whether
a recruiter would ever see it, and a list of problems that make parsers fail.

The goal is to match real ATS behaviour (Workday, Greenhouse, Lever, Taleo, iCIMS,
and the parsing engines behind them like Textkernel/Sovren, RChilli, Daxtra,
Affinda). It should not be smarter than they are. If a real ATS would garble
something, this tool has to garble it the same way and explain why.

## Status

Phases 1–4 done and 6 partly done: CLI, field parser, link auditor, web UI, Dockerfile
(arm64 image builds and runs at ~45 MB RAM). 30 tests pass. Next: phase 5,
calibrating against real ATSs with my real resume. Not yet added to the homelab.

Run locally:

```
uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements-dev.txt
.venv/bin/python -m app.cli resume.pdf [--engine legacy] [--check-links] [--json]
PORT=8000 .venv/bin/python -m app.main          # UI at http://localhost:8000
.venv/bin/python -m pytest -q
.venv/bin/python tests/make_fixtures.py         # regenerate test PDFs
```

## Stack

- **Backend:** Python 3.12, FastAPI, uvicorn
- **PDF engines:** `pdfminer.six` via `pdfplumber` (MIT), pure Python. All three
  readings are built from pdfplumber's character/word positions. No PyMuPDF (AGPL).
  Poppler `pdftotext` was tried and dropped: its block ordering moved right-aligned
  dates onto their own lines and pushed the education date below Skills, which is
  more pessimistic than real ATSs are on a plain single-column resume.
- **Phones:** `phonenumberslite` (same API as `phonenumbers`, minus 35 MB of
  carrier/geocoding data).
- **Frontend:** one static HTML page with vanilla JS, served by FastAPI, no build step.
  The PDF preview uses the browser's built-in viewer (object URL), so nothing is
  rendered on the server.
- **Optional:** a commercial parser API (Affinda or RChilli) behind an env var, as a
  "ground truth" comparison. Off by default.
- **Port:** `PORT` env var, default **8000**, bound to `0.0.0.0`
- **Memory:** should fit the 256 MB default. PDFs are capped at 5 MB / 10 pages and
  are processed in memory.
- **Persistent data:** none. Uploads are never written to disk or `/data`.
- **Visibility:** `private`. Could become a public showcase later; see
  "Before going public".

## How real ATSs read a PDF (the behaviour we emulate)

1. **Text layer only.** Most ATSs read the PDF's embedded text and don't run OCR.
   A scanned or image-only resume comes out empty.
2. **Content-stream order, not visual order.** Older parsers (Taleo-era) emit text
   in the order it appears in the PDF stream. Two-column layouts, sidebars and
   text boxes get interleaved or end up in the wrong place. Newer parsers rebuild
   the reading order from x/y positions, but they still struggle with columns.
3. **Glyph to Unicode mapping.** A font with no `ToUnicode` map, or with custom
   ligatures (fi, fl), produces garbage or missing letters. Icon fonts (phone, mail
   or LinkedIn glyphs) come out as junk characters.
4. **Headers and footers** are often dropped or treated as noise, so contact info
   placed there can get lost.
5. **Tables and graphics.** Table cells get flattened in odd orders. Skill bars,
   charts and logos are invisible.
6. **Sections are found by heading keywords** ("Experience", "Work History",
   "Education", "Skills"). Creative headings ("Where I've been") break
   segmentation.
7. **Links.** Parsers capture URLs that appear *as visible text*. A hyperlink
   hidden behind anchor text (the word "Portfolio" linking to a URL) lives in a
   PDF link annotation. Many ATSs drop it, and even when the parser keeps it, the
   recruiter's view of the candidate often shows plain text only.

## System design

```
                         ┌──────────────────────────────────────────────┐
  Browser                │  index.html  (upload, side-by-side view)     │
  ───────                │  [ your PDF ]  │  [ what the ATS sees ]      │
                         └───────────────┬──────────────────────────────┘
                                         │ POST /api/parse (multipart, ≤5 MB)
                                         ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ FastAPI app (one container, PORT=8000)                                     │
│                                                                            │
│  1. Intake / guard                                                         │
│     size + page cap, magic bytes "%PDF", reject encrypted, timeout         │
│                     │                                                      │
│                     ▼                                                      │
│  2. Extraction engines (all from pdfplumber chars/words, all in memory)    │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│   │ B. Smart     │ │ A. Simple    │ │ S. Raw PDF   │ │ C. Annotations   │  │
│   │ (modern)     │ │ (legacy)     │ │ order        │ │ link URIs,       │  │
│   │ column-aware │ │ straight     │ │ (stream)     │ │ anchor text,     │  │
│   │ via gutter   │ │ across page, │ │ content-     │ │ page             │  │
│   │ detection    │ │ no columns   │ │ stream order │ │                  │  │
│   └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘  │
│          ▼                ▼                ▼                  ▼            │
│  3. Layout diagnostics                                                     │
│     column detection (x-clustering) · header/footer zones · tables ·       │
│     image-only pages · fonts missing ToUnicode · icon/PUA glyphs ·         │
│     text-vs-visual order divergence score                                  │
│                     │                                                      │
│                     ▼                                                      │
│  4. Field parser (deterministic rules, ATS-like, no LLM)                   │
│     contact: name, email, phone, location, URLs                            │
│     sections: heading dictionary → Experience / Education / Skills / ...   │
│     jobs: title · company · date range (dateparser, "Present")             │
│     education: school · degree · dates     skills: list + dictionary       │
│                     │                                                      │
│                     ▼                                                      │
│  5. Link auditor                                                           │
│     visible-text URLs  vs  annotation-only URLs  vs  mismatches            │
│     optional liveness check (HEAD, SSRF-safe: public IPs only,             │
│     no redirects to private ranges, 3 s timeout, max 20 links)             │
│                     │                                                      │
│                     ▼                                                      │
│  6. Report builder → JSON                                                  │
│     raw text per engine · fields · links · issues[] (severity + fix)       │
│     · overall "parse health" score                                         │
│                                                                            │
│  (optional) 7. Commercial parser adapter ── HTTPS ──▶ Affinda / RChilli    │
│     only if PARSER_API_KEY is set; shown as a third column for comparison  │
└────────────────────────────────────────────────────────────────────────────┘
        Nothing is stored. The PDF bytes are freed when the request ends.
```

### Why several text engines

Real ATSs disagree with each other, so the tool shows a spread of readings:

- **B, Smart** (`engines/modern.py`): lines read straight across, so a right-aligned
  date stays with its job, unless `geometry.find_gutter` finds a column gutter. In
  that case each run of lines not crossing the gutter is read left column, then
  right column. A gutter that is just the border between ruled table cells doesn't count.
- **A, Simple** (`engines/legacy.py`): straight across the full page with no column
  detection. This is what position-sorting extractors (pdftotext -layout, PDFBox
  sorted by position) give cheaper ATSs. Two-column layouts interleave.
- **S, Raw PDF order** (`engines/stream.py`): content-stream order, as in Apache
  Tika's default PDF parser. Catches design-tool exports whose text boxes are
  stored out of order (`ORDER_MISMATCH`).

The field parser runs on B and A (the UI toggles between them). If B and A
differ a lot, the layout is fragile, and that is the most useful signal for the user.

### Gutter detection (`engines/geometry.py`)

For each x in the middle 70% of the page: a line is *split* if it has words on
both sides of x and none covering it, and *crossing* if a word covers it. A
gutter needs ≥5 split lines, split/(split+crossing) ≥ 0.6, and ≥8pt width.
Right-aligned dates split a few lines, but the bullet lines cross, so a single
column never qualifies.

### Why no LLM in the parse path

An LLM is far more forgiving than a real ATS. It would "fix" a broken two-column
read and hide the very problem this tool exists to show. An LLM could be added
later as a separate, clearly labelled "AI suggestions" panel, never as the parser
itself.

## Output (API contract, `POST /api/parse`)

```json
{
  "meta":   { "pages": 2, "producer": "Canva", "has_text_layer": true },
  "engines": { "modern": "raw text...", "legacy": "raw text...", "stream": "raw text..." },
  "legacy_fields": { "...": "same shape as fields, parsed from the legacy text" },
  "layout": { "gutters": {}, "order_similarity": 0.27, "stream_similarity": 1.0,
              "header_footer": [], "glyphs": {}, "tables": 0, "images": 0 },
  "fields": {
    "contact":   { "name": "...", "email": "...", "phone": "...", "location": "...", "urls": [] },
    "experience": [ { "title": "...", "company": "...", "start": "2023-06", "end": "present", "bullets": [] } ],
    "education":  [ { "school": "...", "degree": "...", "start": "...", "end": "..." } ],
    "skills":     [ "Python", "..." ],
    "unclassified": [ "text that landed in no section" ]
  },
  "links": [
    { "url": "https://...", "anchor_text": "Portfolio", "visible_in_text": false,
      "page": 1, "status": 200, "issue": "URL hidden behind anchor text" }
  ],
  "issues": [ { "severity": "high", "code": "MULTI_COLUMN", "message": "...", "fix": "..." } ],
  "score": 72
}
```

## Issue codes (first set)

| Code | Severity | Meaning |
|---|---|---|
| `NO_TEXT_LAYER` | high | Image-only page; the ATS reads nothing |
| `MULTI_COLUMN` | high | Column gutter detected; Simple and Smart readings disagree |
| `GARBLED_GLYPHS` | high | Unmapped glyphs `(cid:N)` *inside words* (a lost bullet glyph doesn't count) |
| `ORDER_MISMATCH` | medium | Raw PDF order differs from visual order (<85% alike) |
| `NO_NAME` | medium | No name-like line at the top of the Smart reading |
| `NO_EXPERIENCE` | medium | No recognised Experience heading |
| `CONTACT_IN_HEADER` | medium | Email/phone only inside the header/footer zone |
| `LINK_HIDDEN` | medium | URL only in an annotation, not visible as text |
| `LINK_MISMATCH` | medium | Visible URL text differs from the annotation target |
| `LINK_DEAD` | medium | Liveness check returned 4xx/5xx or timed out |
| `UNKNOWN_HEADING` | medium | All-caps heading not in the dictionary, or letter-spaced (`E D U C A T I O N`) |
| `TABLE_LAYOUT` | low | Content laid out in ruled tables |
| `ICON_GLYPHS` | low | Private-use (icon font) characters in the text |
| `LIGATURES` | low | ﬁ/ﬂ ligature characters, which break keyword matching |
| `DATE_FORMAT` | low | Experience entries with no recognisable date range |

The catalogue (severity + fix text) lives in `app/issues.py`. Score = 100 minus
25/10/3 per distinct high/medium/low code.

## Project layout

```
ats-parser/
├── app/
│   ├── main.py            FastAPI: /, /health, POST /api/parse (docs disabled)
│   ├── cli.py             python -m app.cli resume.pdf
│   ├── guard.py           upload validation (size, pages, %PDF, encryption)
│   ├── engines/           geometry.py, modern.py, legacy.py, stream.py, annotations.py
│   ├── diagnostics.py     columns, order, header/footer, glyphs, tables
│   ├── fields/            dates.py, sections.py, contact.py, entries.py, skills.py
│   ├── links.py           link audit + SSRF-safe liveness check
│   ├── issues.py          issue catalogue
│   ├── report.py          orchestration + score
│   └── static/            index.html, style.css, app.js (vanilla, textContent only)
├── tests/
│   ├── make_fixtures.py   generates the fixture PDFs with reportlab
│   ├── fixtures/          generated test PDFs (committed)
│   ├── fixtures/private/  my real resume (gitignored)
│   ├── test_fixtures.py   expected issues/fields per layout
│   └── test_units.py      dates, headings, SSRF guard
├── Dockerfile             python:3.12-slim multi-stage, non-root, linux/arm64
├── requirements.txt       runtime only; requirements-dev.txt adds pytest + reportlab
├── .env.example
└── README.md
```

## Plan

Phases 1–4 are done. The text below is the original plan, kept for reference.

**Phase 1: Extraction core (CLI first).**
`python -m app.cli resume.pdf` prints both engines' raw text, all link annotations
and the diagnostics. Test fixtures are generated with reportlab: single-column,
two-column, sidebar, table, header contact info, image-only, hidden links.
Done when every fixture triggers the expected issue codes.

**Phase 2: Field parser.**
Section heading dictionary, contact regexes (email, phone with
`phonenumbers`, LinkedIn/GitHub/URL), date range parsing, job and education
blocks, skills dictionary. Unit tests per fixture.

**Phase 3: Link auditor.**
Visible vs annotation-only vs mismatched links. Liveness check with SSRF guard
(resolve DNS, refuse private, loopback, link-local and CGNAT/Tailscale
100.64.0.0/10 ranges, re-check every redirect hop).

**Phase 4: Web UI + API.**
`POST /api/parse`, `GET /health`. Single page: drag-and-drop upload. The PDF sits
on the left. On the right are tabs for Parsed fields / Raw text (legacy | modern)
/ Links / Issues. Raw text lines that differ between engines are highlighted.

**Phase 5: Calibration against real ATSs.**
Run my real resume through real systems: a Workday and a Greenhouse application
"autofill from resume", plus the free demos of Affinda/RChilli. Record what each
got right and wrong in `tests/calibration.md`, then tune the heuristics until our
legacy/modern outputs bracket what the real systems did.

**Phase 6: Docker + deploy.**
`python:3.12-slim` multi-stage, non-root user. Built and tested locally
(`docker build --platform linux/arm64`, `--memory 256m`). Image ~320 MB, ~45 MB RAM.
Remaining: tell Vincent it's ready for `new-project.sh ats-parser 8000 ...`.

## Known gaps

- Parse timeout is `asyncio.wait_for` around a thread: the client gets a 504, but
  the thread runs to completion. `PARSE_CONCURRENCY` caps how many can pile up.
  Move parsing to a subprocess before going public.
- No per-IP rate limit yet.
- Two-digit years (`Jun '21`) aren't parsed. Many ATSs fail on them too, but it
  isn't flagged yet.
- Name detection is text-only (first short line of plain words). Commercial
  parsers also use font size, so `NO_NAME` may be harsher than they are.

**Phase 7 (optional):** commercial parser column, job-description keyword
match, AI suggestions panel.

## Accuracy: what to promise

No tool can reproduce every ATS exactly, because they use different, closed
parsers. What this tool promises: if it shows clean output in **both** engines
with no high-severity issues, the resume will parse well in mainstream ATSs.
Phase 5 calibration is how we check that claim. Keep the UI honest about it.

## Rules for this project

- Never store uploaded PDFs or their text: no disk, no logs, no `/data`. Log only
  sizes, timings and issue codes.
- `tests/fixtures/private/` is for my real resume and is gitignored. Never commit it.
- Liveness checks must go through the SSRF guard. The server sits on my tailnet.
- Keep the parse path deterministic, with no LLM (see above).

## Before going public

Upload cap (5 MB / 10 pages), per-IP rate limit on `/api/parse`, a parse timeout
(10 s), liveness checks rate-limited and capped, no debug mode, a privacy line in
the UI ("files are processed in memory and discarded"). README follows the
showcase template.
