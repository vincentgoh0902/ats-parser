"""Match a parsed resume against a job description and score the fit.

Everything is literal keyword matching with aliases and light stemming, the
way most ATS searches work. Character spans are returned for both texts so
the UI can highlight a term in the resume and point at it in the job ad.
"""

import re
from datetime import date

from app.fields import sections
from app.match import jd as jdparse
from app.match import phrases
from app.match.taxonomy import IMPLIES, SKILLS

WEIGHTS = {"required": 55, "preferred": 15, "title": 10, "years": 10, "education": 10}
BANDS = [(80, "strong", "Strong match"), (65, "good", "Good match"),
         (50, "partial", "Partial match"), (0, "weak", "Weak match")]
# Where a keyword shows up on the resume decides how much credit it earns: a
# skill used in a job bullet is better evidence than one listed under Skills.
EVIDENCE_SECTIONS = {"experience", "projects", "activities", "summary"}
CREDIT_EVIDENCE, CREDIT_LISTED, CREDIT_PARTIAL = 1.0, 0.85, 0.5
TITLE_NOISE = {"senior", "sr", "junior", "jr", "lead", "staff", "principal", "i", "ii", "iii", "iv",
               "intern", "internship", "trainee", "graduate", "associate", "entry", "level", "head",
               "chief", "of", "the", "and", "for", "in", "with", "remote", "hybrid", "contract"}
TITLE_LEMMA = {"scientist": "science", "engineer": "engineering", "analyst": "analytic",
               "analysis": "analytic", "analytics": "analytic", "developer": "development",
               "programmer": "development", "researcher": "research", "designer": "design",
               "ml": "machine", "ai": "artificial"}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#]*")
# Job ad lines whose keywords never count: perks, company blurb, "this role is not for".
SKIP_KINDS = {"ignore", "exclude", "heading"}


# ---------------------------------------------------------------- helpers

def _resume_lines(text: str) -> list[tuple[int, int, str]]:
    """(start, end, section key) for every line of the resume text."""
    out, current, pos = [], "top", 0
    for raw in text.split("\n"):
        start, end = pos, pos + len(raw)
        pos = end + 1
        key = sections.classify(raw.strip())
        if key:
            current = key
            out.append((start, end, "heading"))
        else:
            out.append((start, end, current))
    return out


def _section_at(lines, offset: int) -> str:
    for start, end, key in lines:
        if start <= offset <= end:
            return key
    return "top"


def _variant(s: str) -> str:
    v = re.sub(r"[\s\-.]", "", s.lower())
    return v[:-1] if v.endswith("s") and len(v) > 3 else v


def _most_common(values) -> str:
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get)


def _parse_month(value: str | None, end: bool) -> tuple[int, int] | None:
    today = date.today()
    if value == "present":
        return today.year, today.month
    if not value:
        return None
    if len(value) == 4:
        return int(value), 12 if end else 1
    y, m = value.split("-")
    return int(y), int(m)


def _experience_months(experience: list[dict]) -> int:
    """Total months covered by job date ranges, with overlaps merged."""
    today = date.today()
    spans = []
    for e in experience:
        s, f = _parse_month(e.get("start"), False), _parse_month(e.get("end"), True)
        if not s or not f:
            continue
        a, b = s[0] * 12 + s[1] - 1, min(f[0] * 12 + f[1] - 1, today.year * 12 + today.month - 1)
        if b >= a:
            spans.append((a, b + 1))
    total, last_end = 0, None
    for a, b in sorted(spans):
        if last_end is not None and a < last_end:
            a = last_end
        if b > a:
            total += b - a
            last_end = b if last_end is None else max(last_end, b)
    return total


def _title_tokens(title: str) -> set[str]:
    out = set()
    for tok in TOKEN_RE.findall(title.lower()):
        if tok in TITLE_NOISE:
            continue
        out.add(TITLE_LEMMA.get(tok, phrases.stem(tok)))
    return out


def _degree_level(text: str) -> int:
    low = text.lower()
    levels = [lvl for lvl, _, pattern in jdparse.DEGREE_LEVELS if re.search(pattern, low)]
    if re.search(r"bachelor of|\bb\.?\s?s\.?\b|\bbs\b", low):
        levels.append(2)
    return max(levels) if levels else 0


def _fields_in(text: str) -> list[str]:
    low = text.lower()
    found = [f for f in jdparse.FIELDS if f in low]
    return [f for f in found if not any(f != g and f in g for g in found)]


# ---------------------------------------------------------------- matching

def _jd_skill_terms(jd: dict) -> list[dict]:
    text = jd["text"]
    usable = [(s, e, k) for s, e, k, _ in jd["lines"] if k not in SKIP_KINDS]
    terms = []
    for skill in SKILLS:
        occurrences = []
        for s, e, kind in usable:
            for m in skill.finditer(text[s:e]):
                occurrences.append((s + m.start(), s + m.end(), kind, m.group(0)))
        if occurrences:
            terms.append({"skill": skill, "occurrences": occurrences})
    # "GitHub" inside "GitHub Actions", "Spring" inside "Spring Boot": the longer one wins.
    for t in terms:
        t["occurrences"] = [o for o in t["occurrences"] if not any(
            other is not t and other_o[0] <= o[0] and o[1] <= other_o[1] and other_o[1] - other_o[0] > o[1] - o[0]
            for other in terms for other_o in other["occurrences"])]
    return [t for t in terms if t["occurrences"]]


def _importance(kinds: set[str]) -> str:
    if kinds & {"required", "general"}:
        return "required"
    if kinds & {"responsibilities", "intro"}:
        return "responsibility"
    return "preferred"


def _weight(importance: str, count: int, kind: str) -> float:
    w = {"required": 1.0, "responsibility": 0.8, "preferred": 1.0}[importance]
    w *= 1.4 if count >= 3 else 1.2 if count == 2 else 1.0
    if kind == "soft":
        w *= 0.4
    elif kind == "phrase":
        w *= 0.4
    return round(w, 2)


def _match_skill(term: dict, resume_text: str, resume_lines) -> dict:
    skill = term["skill"]
    spans = [(m.start(), m.end(), m.group(0)) for m in skill.finditer(resume_text)]
    where = sorted({_section_at(resume_lines, s) for s, _, _ in spans} - {"heading"})
    jd_variants = {_variant(o[3]) for o in term["occurrences"]}
    resume_variants = {_variant(v) for _, _, v in spans}
    implied_by = []
    if not spans:
        status, credit = "missing", 0.0
        by_name = {sk.name: sk for sk in SKILLS}
        for name in IMPLIES.get(skill.name, []):
            hits = [(m.start(), m.end(), m.group(0)) for m in by_name[name].finditer(resume_text)]
            if hits:
                implied_by.append(name)
                spans += hits
        if implied_by:
            status, credit = "partial", CREDIT_PARTIAL
            where = sorted({_section_at(resume_lines, s) for s, _, _ in spans} - {"heading"})
    elif set(where) & EVIDENCE_SECTIONS:
        status, credit = "matched", CREDIT_EVIDENCE
    else:
        status, credit = "matched", CREDIT_LISTED
    return {
        "status": status, "credit": credit, "where": where,
        "resume_spans": [[s, e] for s, e, _ in spans],
        "resume_wording": sorted({v for _, _, v in spans}),
        "wording_differs": bool(spans) and not implied_by and not (jd_variants & resume_variants),
        "implied_by": implied_by,
    }


def _match_phrase(key_stems: list[str], resume_text: str, resume_lines) -> dict:
    toks = [(phrases.stem(m.group(0)), m.start(), m.end()) for m in TOKEN_RE.finditer(resume_text)]
    n = len(key_stems)
    exact = [[toks[i][1], toks[i + n - 1][2]] for i in range(len(toks) - n + 1)
             if [t[0] for t in toks[i:i + n]] == key_stems]
    if exact:
        where = sorted({_section_at(resume_lines, s) for s, _ in exact} - {"heading"})
        credit = CREDIT_EVIDENCE if set(where) & EVIDENCE_SECTIONS else CREDIT_LISTED
        return {"status": "matched", "credit": credit, "where": where, "resume_spans": exact}
    # Partial: every word of the phrase appears in one resume line.
    for start, end, key in resume_lines:
        line_toks = [t for t in toks if start <= t[1] < end]
        stems = {t[0] for t in line_toks}
        if n > 1 and set(key_stems) <= stems:
            spans = [[t[1], t[2]] for t in line_toks if t[0] in key_stems]
            return {"status": "partial", "credit": CREDIT_PARTIAL, "where": [key], "resume_spans": spans}
    return {"status": "missing", "credit": 0.0, "where": [], "resume_spans": []}


def match(jd_text: str, report: dict) -> dict:
    jd = jdparse.parse(jd_text)
    resume_text = report["engines"]["modern"]
    fields = report["fields"]
    resume_lines = _resume_lines(resume_text)
    terms = []

    # Known skills.
    for t in _jd_skill_terms(jd):
        kinds = {o[2] for o in t["occurrences"]}
        importance = _importance(kinds)
        kind = "soft" if t["skill"].category == "soft" else "skill"
        m = _match_skill(t, resume_text, resume_lines)
        terms.append({
            "term": t["skill"].name, "label": _most_common(o[3] for o in t["occurrences"]), "kind": kind, "category": t["skill"].category,
            "importance": importance, "weight": _weight(importance, len(t["occurrences"]), kind),
            "jd_spans": [[o[0], o[1]] for o in t["occurrences"]],
            "jd_wording": sorted({o[3] for o in t["occurrences"]}), **m,
        })

    # Other key phrases from the requirement and responsibility lines.
    title_span = []
    if jd["title"]:
        i = jd["text"].find(jd["title"])
        if i >= 0:
            title_span = [(i, i + len(jd["title"]))]
    # The title, years and degree lines are scored on their own; keep phrases out of them.
    scored_lines = [sp for sp in title_span]
    for info in (jd["years"], jd["degree"]):
        if info:
            scored_lines.append(tuple(info["span"]))

    def on_scored_line(s, e):
        return any(a < e and s < b for a, b in scored_lines)

    # Phrases skip the intro too: before the first heading is usually the company pitch.
    usable = [(s, e, k) for s, e, k, _ in jd["lines"]
              if k not in SKIP_KINDS | {"intro"} and not on_scored_line(s, e)]
    jd_skill_spans = [tuple(sp) for t in terms for sp in t["jd_spans"]]
    phrase_text = "\n".join(jd["text"][s:e] for s, e, _ in usable)
    company_words = set(jd["company"].split()) if jd["company"] else set()
    for p in phrases.extract(phrase_text, limit=25, extra_stop=company_words):
        spans, kinds = [], set()
        pattern = re.compile(r"(?<!\w)" + r"(?:['’]s)?[\s\-]+".join(map(re.escape, p["phrase"].split())) + r"(?!\w)", re.I)
        for s, e, kind in usable:
            for mm in pattern.finditer(jd["text"], s, e):
                spans.append([mm.start(), mm.end()])
                kinds.add(kind)
        overlapping = any(a < y and x < b for a, b in spans for x, y in jd_skill_spans)
        if not spans or overlapping:
            continue
        importance = _importance(kinds)
        m = _match_phrase(p["key"].split(), resume_text, resume_lines)
        terms.append({
            "term": p["phrase"], "label": p["phrase"], "kind": "phrase", "category": "phrase", "importance": importance,
            "weight": _weight(importance, len(spans), "phrase"), "jd_spans": spans,
            "jd_wording": [p["phrase"]], "wording_differs": False, "resume_wording": [], **m,
        })
        if sum(t["kind"] == "phrase" for t in terms) >= 8:
            break

    terms.sort(key=lambda t: (-t["weight"], t["term"].lower()))
    for i, t in enumerate(terms):
        t["id"] = f"t{i}"

    components = {}

    def bucket(names):
        ts = [t for t in terms if t["importance"] in names]
        if not ts:
            return None
        total = sum(t["weight"] for t in ts)
        got = sum(t["weight"] * t["credit"] for t in ts)
        found = sum(t["status"] != "missing" for t in ts)
        return {"score": got / total, "detail": f"{found} of {len(ts)} found"}

    components["required"] = bucket({"required", "responsibility"})
    components["preferred"] = bucket({"preferred"})

    # Job title.
    title_info = None
    if jd["title"]:
        want = _title_tokens(jd["title"])
        best, best_title = 0.0, None
        for e in fields["experience"]:
            if e.get("title") and want:
                overlap = len(want & _title_tokens(e["title"])) / len(want)
                if overlap > best:
                    best, best_title = overlap, e["title"]
        spans = []
        if best_title:
            spans = [[m.start(), m.end()] for m in re.finditer(re.escape(best_title), resume_text)]
        title_info = {"job_title": jd["title"], "closest": best_title, "overlap": round(best, 2),
                      "jd_spans": [list(s) for s in title_span], "resume_spans": spans}
        if want:
            components["title"] = {"score": best, "detail": f"closest: {best_title}" if best_title
                                   else "no similar title on the resume"}

    # Years of experience.
    years_info = None
    if jd["years"]:
        need = jd["years"]["years"]
        have = round(_experience_months(fields["experience"]) / 12, 1)
        years_info = {"required": need, "have": have, "jd_spans": [jd["years"]["span"]],
                      "text": jd["years"]["text"]}
        components["years"] = {"score": min(1.0, have / need),
                               "detail": f"about {have:g} of {need}+ years (dated jobs, internships included)"}

    # Education.
    edu_info = None
    if jd["degree"]:
        want = jd["degree"]
        today = (date.today().year, date.today().month)
        best_level, best_fields, in_progress = 0, [], False
        for e in fields["education"]:
            text = " ".join(filter(None, [e.get("degree"), e.get("school")]))
            level = _degree_level(text)
            if level >= best_level:
                best_level, best_fields = level, _fields_in(" ".join(filter(None, [e.get("degree")])))
                end = _parse_month(e.get("end"), True)
                in_progress = bool(end and end > today)
        if best_level >= want["level"]:
            score = 0.6 if in_progress else 0.7
        elif best_level == want["level"] - 1:
            score = 0.3
        else:
            score = 0.0
        if best_level:
            if not want["fields"] or set(best_fields) & set(want["fields"]):
                score += 0.3
            elif want["related_ok"] and set(best_fields) & jdparse.STEM:
                score += 0.25
        edu_info = {"required": want["label"], "fields": want["fields"], "have_level": best_level,
                    "have_fields": best_fields, "in_progress": in_progress, "jd_spans": [want["span"]]}
        components["education"] = {
            "score": score,
            "detail": ("degree in progress" if in_progress else "degree found") if best_level
            else "no degree found on the resume"}

    active = {k: v for k, v in components.items() if v is not None}
    total_weight = sum(WEIGHTS[k] for k in active)
    score = round(sum(WEIGHTS[k] * v["score"] for k, v in active.items()) / total_weight * 100) \
        if total_weight else 0
    band = next(b for b in BANDS if score >= b[0])

    labels = {"required": "Required skills", "preferred": "Preferred skills", "title": "Job title",
              "years": "Years of experience", "education": "Education"}
    breakdown = [{"key": k, "label": labels[k], "weight": round(WEIGHTS[k] / total_weight * 100),
                  "score": round(v["score"], 2), "detail": v["detail"]} for k, v in active.items()]

    return {
        "score": score, "band": band[1], "band_label": band[2],
        "breakdown": breakdown,
        "terms": terms,
        "title": title_info, "years": years_info, "education": edu_info,
        "suggestions": _suggestions(terms, title_info, years_info, edu_info, report),
        "jd_text": jd["text"],
        "jd_sections": [[s, e, k] for s, e, k, _ in jd["lines"]],
        "resume_text": resume_text,
    }


def _suggestions(terms, title, years, edu, report) -> list[dict]:
    out = []
    high = [i for i in report["issues"] if i["severity"] == "high"]
    if high:
        out.append({"kind": "layout", "text": f"Fix the layout problem first ({high[0]['code']}): an ATS "
                    "may not read these keywords in the right place at all."})
    missing_req = [t for t in terms if t["status"] == "missing" and t["importance"] != "preferred"
                   and t["kind"] != "phrase"]
    for t in missing_req[:6]:
        out.append({"kind": "missing", "term": t["id"], "text": f"Add “{t['term']}” if you've used it. "
                    "The job asks for it and your resume doesn't mention it."})
    for t in terms:
        if t["status"] == "partial" and t.get("implied_by"):
            out.append({"kind": "implied", "term": t["id"], "text":
                        f"You list {', '.join(t['implied_by'])} but never write “{t['term']}”. An ATS "
                        f"search for “{t['term']}” won't find you, so write it out."})
    for t in terms:
        if t["status"] == "matched" and t["wording_differs"] and t["kind"] == "skill":
            out.append({"kind": "wording", "term": t["id"], "text":
                        f"The job says “{t['jd_wording'][0]}”, your resume says “{t['resume_wording'][0]}”. "
                        "Use the job's wording somewhere, since some ATSs match exact terms only."})
    for t in terms:
        if (t["status"] == "matched" and t["kind"] == "skill" and t["importance"] != "preferred"
                and not set(t["where"]) & EVIDENCE_SECTIONS):
            out.append({"kind": "evidence", "term": t["id"], "text":
                        f"“{t['term']}” only appears in your skills list. Mention it in a bullet that "
                        "shows where you used it."})
    if years and years["have"] < years["required"]:
        out.append({"kind": "years", "text": f"The job asks for {years['required']}+ years; your dated jobs "
                    f"add up to about {years['have']:g}. If you have more (part-time, freelance, research), "
                    "list it with dates."})
    if title and title["overlap"] < 0.5:
        out.append({"kind": "title", "text": f"None of your job titles is close to “{title['job_title']}”. "
                    "If your work fits, use that wording in your summary."})
    if edu and not edu["have_level"]:
        out.append({"kind": "education", "text": f"The job asks for a {edu['required']} degree and none "
                    "was parsed from your resume. Check the Education section reads correctly."})
    missing_pref = [t for t in terms if t["status"] == "missing" and t["importance"] == "preferred"
                    and t["kind"] != "phrase"]
    if missing_pref:
        names = ", ".join(f"“{t['term']}”" for t in missing_pref[:5])
        out.append({"kind": "preferred", "text": f"Nice-to-haves you don't mention: {names}."})
    return out
