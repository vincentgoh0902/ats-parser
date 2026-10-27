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

Planning. No code yet.

## Stack

- **Backend:** Python 3.12, FastAPI, uvicorn
- **PDF engines:** `pdfminer.six` (via `pdfplumber`, MIT) and poppler `pdftotext`
  (`poppler-utils` apt package, arm64 OK). No PyMuPDF, because AGPL.
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
│  2. Extraction engines (run in parallel, all in memory)                    │
│   ┌────────────────────┐ ┌─────────────────────┐ ┌──────────────────────┐  │
│   │ A. "Legacy ATS"    │ │ B. "Modern ATS"     │ │ C. Annotations       │  │
│   │ pdfminer, stream   │ │ pdftotext + layout  │ │ pdfplumber           │  │
│   │ order, no layout   │ │ analysis (reading   │ │ link annots (URI),   │  │
│   │ analysis           │ │ order by x/y)       │ │ anchor text, page    │  │
│   └─────────┬──────────┘ └──────────┬──────────┘ └──────────┬───────────┘  │
│             │   chars + fonts + bboxes (pdfplumber)          │              │
│             ▼                       ▼                        ▼              │
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

### Why two text engines

Real ATSs disagree with each other. Engine A shows the worst case (a stream-order
parser like old Taleo or iCIMS). Engine B shows what a decent modern parser
produces. If A and B differ a lot, the layout is fragile, and that is the most
useful signal for the user. The field parser runs on B, with a toggle to run it on A.

### Why no LLM in the parse path

An LLM is far more forgiving than a real ATS. It would "fix" a broken two-column
read and hide the very problem this tool exists to show. An LLM could be added
later as a separate, clearly labelled "AI suggestions" panel, never as the parser
itself.

## Output (API contract, `POST /api/parse`)

```json
{
  "meta":   { "pages": 2, "producer": "Canva", "has_text_layer": true },
  "engines": { "legacy": "raw text...", "modern": "raw text..." },
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
| `MULTI_COLUMN` | high | Columns detected and engines A/B disagree on order |
| `GARBLED_GLYPHS` | high | Font without ToUnicode map, or many replacement/PUA chars |
| `CONTACT_IN_HEADER` | medium | Email/phone only inside the header/footer zone |
| `LINK_HIDDEN` | medium | URL only in an annotation, not visible as text |
| `LINK_MISMATCH` | medium | Visible URL text differs from the annotation target |
| `LINK_DEAD` | medium | Liveness check returned 4xx/5xx or timed out |
| `UNKNOWN_HEADING` | medium | Section heading not in the dictionary |
| `TABLE_LAYOUT` | low | Content laid out in tables |
| `ICON_GLYPHS` | low | Icon-font characters in the text |
| `DATE_FORMAT` | low | Dates that couldn't be parsed |

## Project layout (planned)

```
ats-parser/
├── app/
│   ├── main.py            FastAPI routes, static files, /health
│   ├── guard.py           upload validation
│   ├── engines/           legacy.py, modern.py, annotations.py
│   ├── diagnostics.py     columns, header/footer, fonts, tables
│   ├── fields/            contact.py, sections.py, experience.py, education.py, skills.py
│   ├── links.py           link audit + SSRF-safe liveness check
│   ├── report.py          issues + score
│   ├── adapters/          commercial parser (optional)
│   └── static/index.html
├── tests/
│   ├── fixtures/          generated test PDFs (committed)
│   └── fixtures/private/  my real resume (gitignored)
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Plan

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
`python:3.12-slim` multi-stage, `apt-get install poppler-utils`, non-root user.
Build and test locally with `docker build`, push, then tell Vincent it's ready
for `new-project.sh ats-parser 8000 ...`.

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
