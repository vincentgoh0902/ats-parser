"""Job description parsing: sections, title, years and degree requirements."""

import re

from app.fields.entries import TITLE_WORDS

MAX_JD_CHARS = 20_000

# Which part of the job ad a line belongs to decides how much its keywords weigh.
HEADINGS = {
    "required": ["requirements", "qualifications", "minimum qualifications", "basic qualifications",
                 "required qualifications", "what you ll need", "what you need", "must have",
                 "must haves", "what we re looking for", "what we are looking for", "about you",
                 "you have", "you ll have", "who you are", "skills", "required skills",
                 "key requirements", "requirements and qualifications", "your profile",
                 "skills and experience", "experience", "job requirements", "the ideal candidate",
                 "what we look for", "what we re looking for in you", "the bar", "what you bring",
                 "what it takes", "you bring", "your background"],
    "preferred": ["preferred qualifications", "preferred", "nice to have", "nice to haves",
                  "bonus", "bonus points", "good to have", "desired", "desirable",
                  "preferred skills", "pluses", "extra credit", "it s a plus if"],
    "responsibilities": ["responsibilities", "what you ll do", "what you will do", "the role",
                         "your role", "key responsibilities", "job description", "job descriptions", "duties",
                         "job responsibilities", "job scope", "role and responsibilities",
                         "day to day", "in this role you will", "role overview", "about the role",
                         "what you ll be doing", "your responsibilities", "the job", "what you will build",
                         "what you ll build", "what you will work on", "what you ll work on",
                         "the opportunity", "your mission"],
    "ignore": ["about us", "about the company", "who we are", "benefits", "perks",
               "what we offer", "compensation", "salary", "why join us", "our values",
               "equal opportunity", "eeo", "diversity", "how to apply", "location",
               "perks and benefits", "life at", "our culture", "work location", "language", "languages",
               "interview process", "hiring process", "our hiring process", "application process",
               "next steps", "how we hire", "our mission", "the company", "company overview"],
    # Who the company does NOT want. Nothing here is a keyword to add.
    "exclude": ["this role is not for", "this role isn t for", "who this role is not for",
                "this is not for you if", "this job is not for", "not a fit if", "you won t enjoy this if",
                "who should not apply", "this isn t for you if", "red flags"],
    # LinkedIn's wrapper heading: changes nothing.
    "general": ["about the job"],
}
_ALIASES = {a: k for k, aliases in HEADINGS.items() for a in aliases}
ABOUT_COMPANY = re.compile(r"^about\s+(?!the\s+(?:role|job|team|position)\b|you\b|this\b|\d)"
                           r"[\w&.'’-]+(?:\s[\w&.'’-]+){0,3}:?$", re.I)
NOT_FOR = re.compile(r"\b(?:not for|not a fit|isn t for|should not apply|won t enjoy)\b")
# Who may apply, not what they need to know: "Singaporeans and PRs only", "no visa sponsorship".
ELIGIBILITY = re.compile(r"\b(?:citizens?(?:hip)?|permanent residents?|PRs only|work pass(?:es)?|work permits?|"
                         r"employment pass|visa sponsorship|right to work|authori[sz]ed to work|"
                         r"work authori[sz]ation|security clearance)\b", re.I)
# "Model development: Design, train..." starts with a label, a mini heading.
INLINE_LABEL = re.compile(r"^\s*(?:[-•*·]\s*)?[A-Z][\w/&+-]*(?:\s+[\w/&+-]+){0,3}:\s+")
# A heading glued onto the next sentence when copied from a job board: "The RoleWe are...".
GLUED = re.compile(r"(?<=[A-Za-z])(?=[A-Z][a-z])")

PREFERRED_CUE = re.compile(r"\b(?:preferred|nice to have|an? (?:strong |big |huge |definite )?plus|bonus|ideally|"
                           r"desirable|good to have)\b", re.I)
REQUIRED_CUE = re.compile(r"\b(?:required|must|mandatory|essential)\b", re.I)

YEARS_RE = re.compile(
    r"(?P<n>\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?\+?\s*(?:years?|yrs?)\b(?P<rest>[^.\n]{0,60})", re.I)
# Abbreviations need word boundaries and a degree-like context: "ms" ends
# "teams" and "200 ms" is a latency, neither is a Master's.
DEGREE_LEVELS = [  # (level, label, pattern)
    (4, "PhD", r"\bph\.?\s?d\b|\bdoctorate\b|\bdoctoral\b"),
    (3, "Master's", r"\bmaster'?s?\b(?!\s+(?:of\s+)?(?:data|records|copy|schedule|branch|list|plan|file))|"
                    r"\bm\.\s?sc?\.?|\bms\s+(?:in|degree)\b|\bmsc\b|\bm\.?eng\b|\bmba\b|\bgraduate degree\b"),
    (2, "Bachelor's", r"\bbachelor'?s?\b|\bb\.\s?sc?\.?|\bbs\s+(?:in|degree)\b|\bbsc\b|\bb\.a\.|"
                      r"\bb\.?eng\b|\bb\.?tech\b|\bundergraduate degree\b|\buniversity degree\b"),
    (1, "Diploma", r"\bdiploma\b|\bassociate'?s? degree\b"),
]
FIELDS = ["computer science", "data science", "statistics", "mathematics", "applied mathematics",
          "computer engineering", "software engineering", "electrical engineering", "engineering",
          "physics", "economics", "information systems", "information technology", "business analytics",
          "analytics", "operations research", "finance", "business"]
STEM = {"computer science", "data science", "statistics", "mathematics", "applied mathematics",
        "computer engineering", "software engineering", "electrical engineering", "engineering",
        "physics", "information systems", "information technology", "operations research",
        "analytics", "business analytics"}


def _norm_heading(line: str) -> str:
    s = line.lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"[^a-z ]+", " ", s)
    return " ".join(s.split())


def heading_kind(line: str) -> str | None:
    s = line.strip()
    # "- Experience with Django" is a requirement, not an "Experience" heading.
    if not s or len(s) > 60 or re.match(r"[-–•*·▪●◦]\s", s):
        return None
    norm = _norm_heading(s)
    if norm in _ALIASES:
        return _ALIASES[norm]
    # "About BJAK", "About Acme Corp": the company blurb.
    if ABOUT_COMPANY.match(s):
        return "ignore"
    if NOT_FOR.search(norm):
        return "exclude"
    # "Requirements:" or "Preferred Qualifications (nice to have)"
    if s.endswith(":") or len(s.split()) <= 5:
        for alias, kind in _ALIASES.items():
            if norm.startswith(alias + " ") and len(norm) - len(alias) < 25:
                return kind
    return None


def split_glued_headings(text: str) -> str:
    """Put a line break between a heading and the sentence glued onto it
    ("LocationThis role is remote"). Only when the part before is a known
    heading, so "TypeScript" or "JavaScript" are never split."""
    out = []
    for line in text.split("\n"):
        for m in GLUED.finditer(line[:45]):
            head = line[:m.start()]
            if heading_kind(head) and not re.search(r"[.:;!?]", head):
                line = head + "\n" + line[m.start():]
                break
        out.append(line)
    return "\n".join(out)


def lines_with_kind(text: str) -> list[tuple[int, int, str, str]]:
    """Every line as (start, end, kind, line text). Kind comes from the heading
    above it, overridden by cues on the line itself ("... is a plus").
    Lines before the first heading are "intro" once the ad has headings: often
    a company pitch, so they only count for known skills, at a lower weight."""
    out, current, pos = [], "general", 0
    has_headings = any(heading_kind(raw) not in (None, "general") for raw in text.split("\n"))
    if has_headings:
        current = "intro"
    for raw in text.split("\n"):
        start, end = pos, pos + len(raw)
        pos = end + 1
        kind = heading_kind(raw)
        if kind:
            if kind != "general":
                current = kind
            out.append((start, end, "heading", raw))
            continue
        line_kind = current
        if ELIGIBILITY.search(raw):
            line_kind = "ignore"
        elif current not in ("ignore", "exclude"):
            if PREFERRED_CUE.search(raw):
                line_kind = "preferred"
            elif REQUIRED_CUE.search(raw) and current in ("general", "intro"):
                line_kind = "required"
        out.append((start, end, line_kind, raw))
    return out


AS_A_TITLE = re.compile(r"\bAs an? ((?:[A-Z][\w/&+.-]*\s?){1,5}?)(?:,|\s+you\b)")


def detect_title(text: str) -> str | None:
    found = _title_line(text)
    if found:
        return found
    # "As an AI Engineer, you will..."
    for m in AS_A_TITLE.finditer(text[:3000]):
        if TITLE_WORDS.search(m.group(1)):
            return m.group(1).strip()
    return None


def _title_line(text: str) -> str | None:
    for raw in text.split("\n")[:8]:
        line = re.sub(r"^\s*(?:job\s+title|position|role)\s*[:\-–]\s*", "", raw, flags=re.I).strip()
        line = re.split(r"\s+[|–—-]\s+|\s*\(", line)[0].strip()
        if line and len(line.split()) <= 8 and TITLE_WORDS.search(line) and not line.endswith("."):
            return line
    return None


def years_required(lines) -> dict | None:
    """The largest 'N+ years' of experience asked for. Required lines win over
    preferred ones; a 'preferred' 5 years doesn't override a required 2."""
    candidates = []
    for start, end, kind, line in lines:
        if kind in ("ignore", "exclude", "heading"):
            continue
        for m in YEARS_RE.finditer(line):
            n = int(m.group("n"))
            if 0 < n <= 15 and re.search(r"experience|working|professional|industry", line, re.I):
                candidates.append({"years": n, "text": m.group(0).strip(), "kind": kind,
                                   "span": [start + m.start(), start + m.end()]})
    if not candidates:
        return None
    required = [c for c in candidates if c["kind"] != "preferred"]
    return max(required or candidates, key=lambda c: c["years"])


def degree_required(lines) -> dict | None:
    """Lowest degree level mentioned ('Bachelor's or Master's' means Bachelor's)."""
    found = None
    for start, end, kind, line in lines:
        if kind in ("ignore", "exclude", "heading"):
            continue
        low = line.lower()
        levels = [(lvl, label) for lvl, label, pattern in DEGREE_LEVELS if re.search(pattern, low)]
        if not levels and re.search(r"\bdegree\b", low):
            levels = [(2, "Bachelor's")]  # "a degree in ..." usually means a bachelor's
        if not levels:
            continue
        level, label = min(levels)
        if found is None or level < found["level"]:
            fields = [f for f in FIELDS if f in low]
            fields = [f for f in fields if not any(f != g and f in g for g in fields)]
            found = {"level": level, "label": label, "fields": fields,
                     "related_ok": bool(re.search(r"related|equivalent|similar|quantitative", low)),
                     "kind": kind, "span": [start, end]}
    return found


def detect_company(lines) -> str | None:
    """The name in an "About Acme" heading, so it isn't reported as a keyword."""
    for _, _, kind, line in lines:
        m = ABOUT_COMPANY.match(line.strip())
        if kind == "heading" and m:
            return line.strip()[6:].strip(" :")
    return None


def parse(text: str) -> dict:
    text = split_glued_headings(text.replace("\r\n", "\n").replace("\r", "\n")[:MAX_JD_CHARS])
    lines = lines_with_kind(text)
    return {
        "text": text,
        "lines": lines,
        "title": detect_title(text),
        "years": years_required(lines),
        "degree": degree_required(lines),
        "company": detect_company(lines),
    }
