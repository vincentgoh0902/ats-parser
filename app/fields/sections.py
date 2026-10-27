"""Split resume text into sections by heading keywords, the way ATSs do."""

import re

from app.fields.dates import find_range

HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "about", "about me", "objective",
                "career objective", "career summary", "professional profile", "personal statement"],
    "experience": ["experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "relevant experience", "career history",
                   "internships", "internship experience", "research experience",
                   "industry experience", "work and leadership experience"],
    "education": ["education", "academic background", "education and training", "academics",
                  "academic qualifications", "qualifications", "education background"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "skills and tools",
               "technologies", "tech stack", "core competencies", "competencies", "tools",
               "skills and interests", "skills and certifications", "technical proficiencies",
               "languages and tools", "skills and technologies"],
    "projects": ["projects", "personal projects", "academic projects", "selected projects",
                 "side projects", "key projects", "technical projects", "project experience"],
    "certifications": ["certifications", "certificates", "licenses and certifications",
                       "certifications and awards", "courses", "relevant coursework", "coursework"],
    "awards": ["awards", "honors", "honours", "achievements", "awards and honors",
               "awards and honours", "awards and achievements", "honors and awards"],
    "activities": ["leadership", "leadership experience", "activities", "extracurricular activities",
                   "extracurriculars", "volunteering", "volunteer experience",
                   "co curricular activities", "cocurricular activities", "community involvement",
                   "leadership and activities"],
    "publications": ["publications", "research", "papers"],
    "languages": ["languages", "spoken languages"],
    "interests": ["interests", "hobbies", "hobbies and interests"],
    "links": ["links", "online presence", "portfolio"],
    "contact": ["contact", "contact information", "contact details"],
    "references": ["references", "referees"],
}
ALIASES = {alias: key for key, aliases in HEADINGS.items() for alias in aliases}


def normalize(line: str) -> str:
    s = line.lower().replace("&", " and ")
    s = re.sub(r"[^a-z ]+", " ", s)
    return " ".join(s.split())


def _letter_spaced(line: str) -> str | None:
    """'E X P E R I E N C E' -> 'EXPERIENCE'."""
    if re.fullmatch(r"(?:[A-Za-z&] ){3,}[A-Za-z]", line.strip()):
        return line.replace(" ", "")
    return None


def classify(line: str) -> str | None:
    s = line.strip()
    if not s or len(s) > 45:
        return None
    return ALIASES.get(normalize(s))


def looks_like_heading(line: str) -> bool:
    """An ALL-CAPS short line with no digits: probably meant as a heading."""
    s = line.strip().rstrip(":")
    letters = [c for c in s if c.isalpha()]
    return (len(letters) >= 4 and s.upper() == s and not re.search(r"\d", s)
            and len(s.split()) <= 4 and re.fullmatch(r"[A-Z &/,'’-]+", s) is not None)


def split(lines: list[str], name: str | None = None) -> tuple[list[dict], list[dict]]:
    """Return (sections, heading problems).

    Each section is {"key", "heading", "lines"}. Text before the first heading
    goes in a section with key "top" (name and contact block, usually).
    """
    sections = [{"key": "top", "heading": None, "lines": []}]
    problems = []
    lines = [l.strip() for l in lines if l.strip()]
    for i, line in enumerate(lines):
        key = classify(line)
        if key:
            sections.append({"key": key, "heading": line, "lines": []})
            continue
        spaced = _letter_spaced(line)
        if spaced and classify(spaced):
            problems.append({"heading": line, "kind": "letter_spaced", "would_be": classify(spaced)})
        elif sections[-1]["key"] != "skills" and _unknown_heading(
                line, lines[i + 1] if i + 1 < len(lines) else "", name, past_top=i >= 2,
                in_entries=sections[-1]["key"] in ENTRY_SECTIONS):
            problems.append({"heading": line, "kind": "unknown"})
        sections[-1]["lines"].append(line)
    return sections, problems


ENTRY_SECTIONS = {"experience", "education", "projects", "activities"}


def _unknown_heading(line: str, next_line: str, name: str | None, past_top: bool,
                     in_entries: bool) -> bool:
    # Inside Experience, an all-caps line followed by dates is a company name.
    if in_entries and find_range(next_line):
        return False
    return past_top and looks_like_heading(line) and line != (name or "").strip()
