"""Run every stage on one PDF and build the report."""

import io

import pdfplumber

from app import diagnostics, guard, links
from app.engines import annotations, legacy, modern, stream
from app.fields import contact, entries, sections, skills
from app.issues import SEVERITY_ORDER, issue

PENALTY = {"high": 25, "medium": 10, "low": 3}


def parse_fields(text: str) -> tuple[dict, list[dict]]:
    """Structured fields from one engine's text, plus field-level issues."""
    lines = [l for l in text.splitlines() if l.strip()]
    name = contact.find_name(lines)
    secs, heading_problems = sections.split(lines, name=name)
    by_key: dict[str, list[str]] = {}
    for s in secs:
        by_key.setdefault(s["key"], []).extend(s["lines"])

    experience, undated = entries.extract(by_key.get("experience", []), "experience")
    issues = []
    # With no text at all, NO_TEXT_LAYER already says why nothing was found.
    if lines and not name:
        issues.append(issue("NO_NAME",
            f"No name found at the top. The text starts with '{lines[0][:50]}'."))
    if lines and "experience" not in by_key:
        issues.append(issue("NO_EXPERIENCE", "No Experience section heading was recognised."))
    elif lines and not experience:
        issues.append(issue("DATE_FORMAT",
            "The Experience section has no dates the parser recognised, so no jobs were found."))
    elif undated:
        issues.append(issue("DATE_FORMAT",
            f"Text at the start of Experience has no date: '{undated[0][:60]}'."))
    education, _ = entries.extract(by_key.get("education", []), "education")

    for p in heading_problems:
        if p["kind"] == "letter_spaced":
            issues.append(issue("UNKNOWN_HEADING",
                f"'{p['heading']}' is spaced out letter by letter. Many ATSs read it as "
                f"single letters and miss the {p['would_be'].title()} section.", heading=p["heading"]))
        else:
            issues.append(issue("UNKNOWN_HEADING",
                f"'{p['heading']}' looks like a heading but isn't one the parser knows, so its "
                f"content was filed under the previous section.", heading=p["heading"]))

    projects, _ = entries.extract(by_key.get("projects", []), "projects")
    skill_lines = by_key.get("skills", [])
    fields = {
        "contact": contact.extract(by_key.get("top", [])[:12] or lines[:12], text),
        "sections": [{"key": s["key"], "heading": s["heading"], "lines": len(s["lines"])}
                     for s in secs if s["key"] != "top" or s["lines"]],
        "summary": " ".join(by_key.get("summary", [])) or None,
        "experience": experience,
        "education": education,
        "projects": projects if projects else by_key.get("projects", []),
        "skills": skills.from_section(skill_lines),
        "skills_detected": skills.detect(text),
        "other_sections": {k: v for k, v in by_key.items()
                           if k not in ("top", "summary", "experience", "education",
                                        "projects", "skills")},
    }
    return fields, issues


def _contact_in_header(fields: dict, header_texts: list[str], full_text: str) -> list[dict]:
    found = []
    header = "\n".join(header_texts)
    body = full_text
    for h in header_texts:
        body = body.replace(h, "")
    for label in ("email", "phone"):
        value = fields["contact"].get(label)
        if value and value in header and value not in body:
            found.append(issue("CONTACT_IN_HEADER",
                f"Your {label} ({value}) is only in the page header/footer.", field=label))
    return found


def score(issues: list[dict]) -> int:
    worst = {}
    for i in issues:
        worst[i["code"]] = min(worst.get(i["code"], 2), SEVERITY_ORDER[i["severity"]])
    sev = {v: k for k, v in SEVERITY_ORDER.items()}
    return max(0, 100 - sum(PENALTY[sev[s]] for s in worst.values()))


def build(data: bytes) -> dict:
    """The full report, without link liveness (see add_liveness)."""
    pages = guard.check(data)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages_by_engine = {
            "modern": modern.extract(pdf),
            "legacy": legacy.extract(pdf),
            "stream": stream.extract(pdf),
        }
        annots = annotations.extract(pdf)
        layout, issues = diagnostics.run(pdf, pages_by_engine)
        meta = {
            "pages": pages,
            "producer": pdf.metadata.get("Producer"),
            "creator": pdf.metadata.get("Creator"),
            "has_text_layer": layout["glyphs"]["total"] > 0,
        }

    texts = {k: "\n\n".join(v) for k, v in pages_by_engine.items()}
    modern_text, legacy_text = texts["modern"], texts["legacy"]
    fields, field_issues = parse_fields(modern_text)
    legacy_fields, _ = parse_fields(legacy_text)
    link_list, link_issues = links.audit(annots, fields["contact"]["urls"], modern_text)
    issues += field_issues + link_issues
    issues += _contact_in_header(fields, layout["header_footer"], modern_text)
    issues.sort(key=lambda i: SEVERITY_ORDER[i["severity"]])

    return {
        "meta": meta,
        "engines": texts,
        "fields": fields,
        "legacy_fields": legacy_fields,
        "layout": layout,
        "links": link_list,
        "issues": issues,
        "score": score(issues),
    }


async def add_liveness(report: dict) -> dict:
    dead = await links.check_liveness(report["links"])
    report["issues"] = sorted(report["issues"] + dead, key=lambda i: SEVERITY_ORDER[i["severity"]])
    report["score"] = score(report["issues"])
    return report
