"""Check an edited resume: render it, read it back like an ATS, compare.

Instead of a separate set of lint rules, the rendered PDF goes through the same
parser as an upload. Any field that doesn't come back as written is reported at
its place in the form. With a job ad, the match runs on the rendered PDF and its
terms become suggestions tied to specific bullets.

Suggestions never write new claims. A wording swap or an "(SQL)" after
"PostgreSQL" only restates what the bullet already says; a missing keyword only
points at the bullets where it would fit, and "add to Skills" is offered once the
user confirms they have used it (the UI asks).
"""

import re

from app import report
from app.edit import render
from app.edit.model import Resume
from app.fields.contact import EMAIL_RE
from app.match import matcher, phrases
from app.match.taxonomy import IMPLIES, SKILLS

BY_NAME = {s.name: s for s in SKILLS}
IMPLIED_BY = {}  # "PostgreSQL" -> ["SQL"]
for general, specifics in IMPLIES.items():
    for s in specifics:
        IMPLIED_BY.setdefault(s, []).append(general)

HINTS = {
    "name": "Use 2–4 plain words on the first line, e.g. “Alex Tan”.",
    "email": "Check the email address for typos or spaces.",
    "phone": "Write the full number with country code, e.g. “+65 9123 4567”.",
    "location": "Parsers look for “City, Region”, e.g. “Singapore, SG” or “Austin, TX”.",
    "links": "Write links in full, e.g. “https://yourname.dev”.",
    "dates": "Parsers can't read this date, so this entry gets merged into the one above. "
             "Use “Mon YYYY – Mon YYYY” or “Mon YYYY – Present”, e.g. “Jan 2023 – Present”.",
    "entry": "A job needs a date range to be read as its own job.",
    "title": "Put a job-title word in the title (Engineer, Analyst, Intern…) so it isn't read as the company.",
    "org": "The company didn't come back as written. Keep it short, without dates or locations.",
    "school": "Include a school word (University, College, Institute…) in the school name.",
    "degree": "Start with the degree type, e.g. “Bachelor of Science in …” or “B.S. …”.",
    "bullets": "This bullet didn't come back as one bullet. Very short lines or dates inside a bullet can split it.",
    "items": "This section didn't come back as written.",
    "text": "The summary didn't come back as written.",
}


def _norm(s) -> str:
    """Compare as the PDF writes it: look-alikes for missing glyphs ("∼" -> "~")."""
    text = render.supported(str(s or ""))
    return " ".join(text.lower().replace("–", "-").replace("—", "-").split()).rstrip(".")


def _texts(resume: Resume):
    """Every editable text the matcher can see, with its path in the form."""
    for i, s in enumerate(resume.sections):
        if s.kind == "text":
            yield f"sections.{i}.text", s.text, s.key
        for j, e in enumerate(s.entries):
            for k, b in enumerate(e.bullets):
                yield f"sections.{i}.entries.{j}.bullets.{k}", b, s.key
        for j, e in enumerate(s.schools):
            for k, d in enumerate(e.details):
                yield f"sections.{i}.schools.{j}.details.{k}", d, s.key
        if s.kind == "list":
            for k, item in enumerate(s.items):
                yield f"sections.{i}.items.{k}", item, s.key


def _skills_path(resume: Resume) -> str | None:
    i = next((i for i, s in enumerate(resume.sections) if s.kind == "skills"), None)
    return None if i is None else f"sections.{i}.items"


# ---------------------------------------------------------------- read-back

def mismatches(resume: Resume, fields: dict) -> list[dict]:
    """Fields an ATS would read differently from what the user wrote."""
    out = []

    def add(path, hint_key, wrote, read):
        out.append({"path": path, "wrote": wrote, "read": read or "", "hint": HINTS[hint_key]})

    c, got = resume.contact, fields["contact"]
    for key in ("name", "email", "phone", "location"):
        if getattr(c, key) and _norm(getattr(c, key)) != _norm(got.get(key)):
            add(f"contact.{key}", key, getattr(c, key), got.get(key))
    read_urls = {_norm(u).removeprefix("https://").removeprefix("http://") for u in got.get("urls", [])}
    for k, link in enumerate(c.links):
        if EMAIL_RE.fullmatch(link):
            continue
        if _norm(link).removeprefix("https://").removeprefix("http://") not in read_urls:
            add(f"contact.links.{k}", "links", link, "")

    for i, s in enumerate(resume.sections):
        if s.kind == "entries":
            parsed = fields["experience"] if s.key == "experience" else fields.get("projects") \
                if s.key == "projects" else None
            if parsed is None:
                # Other dated sections (activities) aren't split into entries by the parser.
                continue
            parsed = [p for p in parsed if isinstance(p, dict)]
            undated = {j for j, e in enumerate(s.entries)
                       if not any(_norm(p.get("date_text")) == _norm(e.dates) and e.dates for p in parsed)}
            for j, e in enumerate(s.entries):
                base = f"sections.{i}.entries.{j}"
                p = next((p for p in parsed if _norm(p.get("date_text")) == _norm(e.dates)
                          and e.dates), None)
                if not p:
                    add(f"{base}.dates", "dates" if e.dates else "entry", e.dates, "")
                    continue
                parsed.remove(p)
                # An unreadable date merges the next entry into this one; that's
                # reported on the date, not as broken bullets here.
                if j + 1 in undated:
                    continue
                # ATSs have no fields for a project's header, so only jobs are compared.
                header_fields = (("title", "title"), ("org", "company"), ("location", "location")) \
                    if s.key == "experience" else ()
                for field, got_key in header_fields:
                    if getattr(e, field) and _norm(getattr(e, field)) != _norm(p.get(got_key)):
                        add(f"{base}.{field}", field if field != "location" else "location",
                            getattr(e, field), p.get(got_key))
                got_b = [_norm(b) for b in p.get("bullets", [])]
                for k, b in enumerate(e.bullets):
                    if _norm(b) not in got_b:
                        add(f"{base}.bullets.{k}", "bullets", b, "")
        elif s.kind == "education":
            parsed = list(fields["education"])
            for j, e in enumerate(s.schools):
                base = f"sections.{i}.schools.{j}"
                p = next((p for p in parsed if _norm(p.get("date_text")) == _norm(e.dates) and e.dates), None)
                if not p:
                    if e.dates:
                        add(f"{base}.dates", "dates", e.dates, "")
                    continue
                parsed.remove(p)
                for field in ("school", "degree", "location"):
                    if getattr(e, field) and _norm(getattr(e, field)) != _norm(p.get(field)):
                        add(f"{base}.{field}", field, getattr(e, field), p.get(field))
        elif s.kind == "skills":
            got_items = {_norm(x) for x in fields["skills"]}
            for k, item in enumerate(s.items):
                if _norm(item) not in got_items:
                    add(f"sections.{i}.items.{k}", "items", item, "")
        elif s.kind == "text" and s.key == "summary":
            if _norm(s.text) != _norm(fields.get("summary")):
                add(f"sections.{i}.text", "text", s.text, fields.get("summary"))
    return out


# ---------------------------------------------------------------- suggestions

def _stems(text: str) -> set[str]:
    return {phrases.stem(t) for t in re.findall(r"[A-Za-z][A-Za-z0-9+#]*", text)
            if not phrases.is_stop(t) and len(t) > 2}


def _words(text: str) -> dict[str, str]:
    """Stem -> the word as written, for the content words of a text."""
    return {phrases.stem(t): t for t in re.findall(r"[A-Za-z][A-Za-z0-9+#]*", text)
            if not phrases.is_stop(t) and len(t) > 2}


def _jd_context(term: dict, jd_text: str, keyword_stems: set[str]) -> set[str]:
    """Words from the job ad lines the term came from, minus the words of
    every keyword: "KYC, CRM, document handling" says nothing about where KYC
    fits, so a bullet mentioning documents isn't a match for it."""
    words = set()
    for s, e in term["jd_spans"]:
        start = jd_text.rfind("\n", 0, s) + 1
        end = jd_text.find("\n", e)
        words |= _stems(jd_text[start:end if end >= 0 else None])
    return words - keyword_stems


def _related(name: str) -> tuple[list, list]:
    """Skills whose presence in a bullet makes it a good home for `name`:
    close ones (one implies the other) and same-category ones."""
    skill = BY_NAME.get(name)
    if not skill:
        return [], []
    close = {n for n in (*IMPLIES.get(name, []), *IMPLIED_BY.get(name, [])) if n in BY_NAME}
    same = [s for s in SKILLS if s.category == skill.category and s is not skill and s.name not in close
            and skill.category not in ("soft", "language")]
    return [BY_NAME[n] for n in close], same


HOME_KEYS = {"experience", "projects", "activities"}
BROAD = {"ml", "practice", "domain", "soft", "automation"}
# Words every tech job ad and resume share; overlap on them says nothing.
FIT_IGNORE = {phrases.stem(w) for w in ("based", "product", "products", "pipeline", "pipelines", "test", "tests",
              "system", "systems", "model", "models", "data", "tool", "tools", "user", "users", "team",
              "teams", "service", "services", "platform", "application", "applications", "feature", "features",
              "power", "integrating", "work", "working", "built", "building")}


def best_fit(term: dict, resume: Resume, jd_text: str, keyword_stems: set[str] = frozenset(),
             limit: int = 2) -> list[dict]:
    """Bullets from jobs, projects and activities that best fit a keyword:
    words shared with the job ad line it came from, and related skills."""
    context = _jd_context(term, jd_text, keyword_stems | _stems(term["term"]))
    close, same = _related(term["term"])
    scored = []
    for path, text, key in _texts(resume):
        if key not in HOME_KEYS or ".text" in path:
            continue
        written = _words(text)
        shared = sorted(written[st] for st in (written.keys() & context) - FIT_IGNORE)
        near = [s.name for s in close if s.search(text)]
        kin = [s.name for s in same if s.search(text)]
        score = len(shared) + 2 * len(near) + min(len(kin), 2)
        # Shared words alone need to be more than one: "pipelines" in both says little.
        # In a broad category a same-category skill alone is weak ("3D Vision"
        # next to an LLM bullet); in a narrow one (cloud, web) it's a fair hint.
        broad = BY_NAME[term["term"]].category in BROAD if term["term"] in BY_NAME else True
        if near or (kin and (shared or not broad)) or len(shared) >= 2:
            why = []
            if near or kin:
                why.append("mentions " + ", ".join((near + kin)[:3]))
            if shared:
                why.append("shares “" + "”, “".join(shared[:4]) + "” with the job ad")
            scored.append({"path": path, "score": score, "why": "; ".join(why)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def suggestions(resume: Resume, match: dict, jd_text: str) -> list[dict]:
    out = []
    skills_path = _skills_path(resume)
    keyword_stems = set()
    for t in match["terms"]:
        for w in [t["term"], *t["jd_wording"]]:
            keyword_stems |= _stems(w)
    for t in match["terms"]:
        skill = BY_NAME.get(t["term"]) if t["kind"] != "phrase" else None
        base = {"term": t["term"], "label": t["label"], "importance": t["importance"]}

        if skill and t["status"] == "matched" and t["wording_differs"]:
            want = t["jd_wording"][0]
            for path, text, _ in _texts(resume):
                hits = [m for m in skill.finditer(text) if _norm(m.group(0)) != _norm(want)]
                if hits:
                    m = hits[0]
                    out.append({**base, "kind": "wording", "path": path, "before": text,
                                "after": text[:m.start()] + want + text[m.end():],
                                "text": f"The job says “{want}”; this says “{m.group(0)}”. Use the job's wording."})
                    break

        elif skill and t["status"] == "partial" and t.get("implied_by"):
            for name in t["implied_by"]:
                done = False
                for path, text, _ in _texts(resume):
                    m = BY_NAME[name].search(text)
                    if m:
                        out.append({**base, "kind": "implied", "path": path, "before": text,
                                    "after": text[:m.end()] + f" ({t['term']})" + text[m.end():],
                                    "text": f"You use {m.group(0)}, which is {t['term']}. Say so, so a "
                                            f"search for “{t['term']}” finds it."})
                        done = True
                        break
                if done:
                    break

        elif skill and t["status"] == "matched" and t["where"] == ["skills"]:
            fits = best_fit(t, resume, jd_text, keyword_stems, limit=1)
            if fits:
                out.append({**base, "kind": "evidence", "path": fits[0]["path"], "why": fits[0]["why"],
                            "text": f"“{t['term']}” is only in your Skills list. If you used it here, "
                                    "say how in this bullet."})

        elif t["status"] == "missing" and t["kind"] != "phrase":
            fits = best_fit(t, resume, jd_text, keyword_stems)
            item = {**base, "kind": "missing", "needs_confirm": True, "fits": fits,
                    "text": f"The job asks for “{t['label']}”. Only add it if you have really used it."}
            if skills_path and skill:
                item["add_to"] = skills_path
                item["add"] = t["term"]
            out.append(item)
    return out


# ---------------------------------------------------------------- entry point

def check(resume: Resume, jd_text: str = "") -> dict:
    pdf = render.render(resume)
    result = report.build(pdf)
    out = {
        "pages": result["meta"]["pages"],
        "issues": result["issues"],
        "parse_score": result["score"],
        "mismatches": mismatches(resume, result["fields"]),
        "match": None,
        "suggestions": [],
    }
    if jd_text.strip():
        m = matcher.match(jd_text, result)
        out["match"] = {k: m[k] for k in ("score", "band", "band_label", "breakdown")}
        out["suggestions"] = suggestions(resume, m, jd_text)
    return out
