from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import report
from app.edit import check, model, render
from app.main import app

HERE = Path(__file__).parent
LONG = ("Designed and shipped an internal support assistant in Python and FastAPI that answers policy "
        "questions from 4,000 documents, cutting ticket handling time by 35% across three regional teams")


def rich(**overrides) -> model.Resume:
    data = {
        "contact": {"name": "Zoë Ñúñez-Müller", "email": "zoe.nunez@example-university.edu.sg",
                    "phone": "+65 9123 4567", "location": "Singapore, SG",
                    "links": ["linkedin.com/in/zoe-nunez", "github.com/zoenm"]},
        "sections": [
            {"key": "summary", "heading": "Summary", "kind": "text",
             "text": "Applied AI engineer building LLM agents and evaluation pipelines for fintech operations. " * 3},
            {"key": "experience", "heading": "Experience", "kind": "entries", "entries": [
                {"title": "Machine Learning Engineer", "org": "Fintech Asia Pte. Ltd.", "location": "Singapore, SG",
                 "dates": "Mar 2024 – Present", "bullets": [LONG + "."] * 4},
                {"title": "Software Engineering Intern", "org": "Grab", "location": "Remote",
                 "dates": "May 2023 – Aug 2023", "bullets": ["Built Kafka consumers in Go.", LONG + "."]},
                {"title": "Data Analyst", "org": "Shopee", "location": "Singapore, SG",
                 "dates": "Jan 2022 – Dec 2022", "bullets": [LONG + "."] * 6},
            ]},
            {"key": "projects", "heading": "Projects", "kind": "entries", "entries": [
                {"title": "Interview Coach | Python, LangGraph | GitHub", "dates": "Jan 2025 – Mar 2025",
                 "bullets": ["Built an AI interview coach with tool calling and evals."]}]},
            {"key": "education", "heading": "Education", "kind": "education", "schools": [
                {"school": "National University of Singapore", "location": "Singapore, SG",
                 "degree": "Bachelor of Computing in Computer Science", "dates": "Aug 2020 – May 2024",
                 "gpa": "GPA: 4.5/5.0", "details": ["Dean's List 2022"]}]},
            {"key": "skills", "heading": "Skills", "kind": "skills",
             "items": ["Python", "TypeScript", "LangGraph", "PyTorch", "PostgreSQL", "Docker", "AWS"]},
            {"key": "certifications", "heading": "Certifications", "kind": "list",
             "items": ["AWS Certified Machine Learning – Specialty (2024)"]},
            {"key": "activities", "heading": "Leadership & Activities", "kind": "list",
             "items": ["President, NUS Hackers"]},
        ],
    }
    data.update(overrides)
    return model.Resume.model_validate(data)


def roundtrip(resume: model.Resume) -> tuple[dict, model.Resume]:
    r = report.build(render.render(resume))
    return r, model.from_fields(r["fields"])


def test_fixture_roundtrips_exactly():
    original = report.build((HERE / "fixtures" / "single_column.pdf").read_bytes())
    resume = model.from_fields(original["fields"])
    r, back = roundtrip(resume)
    assert r["issues"] == []
    assert r["engines"]["modern"] == r["engines"]["legacy"]
    for key in ("contact", "experience", "education", "skills", "summary"):
        assert r["fields"][key] == original["fields"][key], key
    assert back == resume


@pytest.mark.parametrize("page_size", ["letter", "a4"])
def test_two_page_resume_roundtrips(page_size):
    resume = rich(page_size=page_size)
    jobs = resume.sections[1].entries
    jobs.append(jobs[0].model_copy(update={"title": "Research Assistant", "org": "A*STAR",
                                           "dates": "Jan 2021 – Dec 2021"}))
    r, back = roundtrip(resume)
    assert r["meta"]["pages"] == 2
    assert r["issues"] == []
    assert back.model_dump(exclude={"page_size"}) == resume.model_dump(exclude={"page_size"})


def test_wrapped_last_bullet_is_not_read_as_next_company():
    resume = rich()
    resume.sections[1].entries[0].bullets[-1] = LONG  # no full stop, wraps onto a short line
    r, _ = roundtrip(resume)
    assert [e["company"] for e in r["fields"]["experience"]] == ["Fintech Asia Pte. Ltd.", "Grab", "Shopee"]
    assert r["fields"]["experience"][0]["bullets"][-1] == LONG + "."


def test_bare_domain_written_as_link_and_unsupported_glyphs_marked():
    assert render.visible_link("zoenm.dev") == "https://zoenm.dev"
    assert render.visible_link("github.com/zoenm") == "github.com/zoenm"
    assert render.supported("Zoë 陈") == "Zoë ?"


def test_mismatches_point_at_the_field():
    resume = rich()
    resume.contact.location = "Singapore"
    resume.sections[1].entries[1].dates = "Summer of 2023"
    result = check.check(resume)
    paths = {m["path"]: m for m in result["mismatches"]}
    assert "contact.location" in paths and "City, Region" in paths["contact.location"]["hint"]
    assert "sections.1.entries.1.dates" in paths
    # The merge it causes isn't reported again as broken bullets on the job above.
    assert not any(p.startswith("sections.1.entries.0.") for p in paths)
    assert check.check(rich())["mismatches"] == []


def test_suggestions_for_backend_job():
    original = report.build((HERE / "fixtures" / "single_column.pdf").read_bytes())
    resume = model.from_fields(original["fields"])
    result = check.check(resume, (HERE / "jd" / "backend_engineer.txt").read_text())
    by_term = {s["term"]: s for s in result["suggestions"]}

    ci = by_term["CI/CD"]
    assert ci["kind"] == "implied"
    assert ci["after"] == "Wrote CI pipelines with GitHub Actions (CI/CD) and Docker."

    k8s = by_term["Kubernetes"]
    assert k8s["kind"] == "missing" and k8s["needs_confirm"]
    assert k8s["fits"][0]["path"] == "sections.0.entries.1.bullets.1"  # the Docker / GitHub Actions bullet
    assert k8s["add_to"] == "sections.2.items" and k8s["add"] == "Kubernetes"
    # A missing keyword never comes with ready-made text for a bullet.
    assert all("after" not in s for s in result["suggestions"] if s["kind"] == "missing")


def test_wording_suggestion_uses_the_jobs_term():
    result = check.check(rich(), (HERE / "jd" / "bjak_ai_engineer.txt").read_text())
    agents = next(s for s in result["suggestions"] if s["term"] == "AI Agents")
    assert agents["kind"] == "wording" and agents["path"] == "sections.0.text"
    assert "AI agents" in agents["after"] and agents["before"].count("LLM agents") == \
        agents["after"].count("LLM agents") + 1


def test_render_and_check_endpoints():
    client = TestClient(app)
    body = rich().model_dump_json()
    r = client.post("/api/render", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    r = client.post("/api/check", json={"resume": rich().model_dump(), "job_description": "Python, Kubernetes"})
    assert r.status_code == 200 and r.json()["match"]["score"] >= 0
    r = client.post("/api/render", content=b"{" + b" " * 200_000 + b"}")
    assert r.status_code == 413
    too_many = rich().model_dump()
    too_many["sections"][1]["entries"][0]["bullets"] = ["x"] * 50
    r = client.post("/api/render", json=too_many)
    assert r.status_code == 422


def test_parse_returns_editor_prefill():
    client = TestClient(app)
    pdf = (HERE / "fixtures" / "single_column.pdf").read_bytes()
    r = client.post("/api/parse", files={"file": ("r.pdf", pdf, "application/pdf")})
    resume = r.json()["resume"]
    assert resume["contact"]["name"] == "Alex Tan"
    assert [s["kind"] for s in resume["sections"]] == ["entries", "education", "skills"]


def test_skills_summary_heading_and_single_date_project():
    """Layout of a real LaTeX resume: "Skills Summary" heading, a project dated with
    one month, and its header holding the stack and link words."""
    resume = rich()
    resume.sections[2].entries[0].title = "Graph Fraud Detection | XGBoost, PyTorch Geometric, Neo4j | GitHub"
    resume.sections[2].entries[0].dates = "Oct 2026"
    resume.sections[4].heading = "Skills Summary"
    resume.sections[4].items = ["Python", "DSPy (Prompt Optimisation)", "English (Native)"]
    r, back = roundtrip(resume)
    f = r["fields"]
    assert f["skills"] == ["Python", "DSPy (Prompt Optimisation)", "English (Native)"]
    assert f["projects"][0]["date_text"] == "Oct 2026"
    assert back.sections[2].entries[0].title == resume.sections[2].entries[0].title
    assert check.check(resume)["mismatches"] == []


def test_wrapped_tail_never_reads_as_heading_or_glyph_gap():
    # "...nearing retirement age for APAC leadership" once wrapped to a lone
    # "leadership" line, which parsers take as the Leadership section.
    bullet = ("Replaced manual per-entity reporting with DAX-based KPIs for revenue per employee and workforce "
              "sustainability, flagging entities with high shares of employees nearing retirement age for APAC "
              "leadership")
    resume = rich()
    resume.sections[1].entries[2].bullets = [bullet, "Cut reporting from 2 days to ∼10 minutes."]
    r, _ = roundtrip(resume)
    assert "activities" not in [s["key"] for s in r["fields"]["sections"]][:-1]
    assert r["fields"]["experience"][2]["bullets"] == [bullet, "Cut reporting from 2 days to ~10 minutes."]
    assert check.check(resume)["mismatches"] == []


def test_split_avoids_lone_heading_line():
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from app.fields.sections import classify
    head = "Flagged entities with high shares of employees nearing retirement age for APAC"
    text = head + " leadership"
    width = stringWidth(head, render.REGULAR, 9.5) + 2
    assert simpleSplit(text, render.REGULAR, 9.5, width)[-1] == "leadership"  # the trap
    lines = render._split(text, render.REGULAR, 9.5, width, width)
    assert " ".join(lines) == text and not any(classify(l) for l in lines)
