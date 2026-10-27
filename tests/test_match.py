from pathlib import Path

import pytest

from app import report
from app.match import jd, matcher
from app.match.taxonomy import SKILLS

HERE = Path(__file__).parent
BY_NAME = {s.name: s for s in SKILLS}


@pytest.fixture(scope="module")
def resume():
    return report.build((HERE / "fixtures" / "single_column.pdf").read_bytes())


def run(resume, name):
    return matcher.match((HERE / "jd" / f"{name}.txt").read_text(), resume)


def terms(m):
    return {t["term"]: t for t in m["terms"]}


@pytest.mark.parametrize("skill,text,hits", [
    ("C", "C, C++ and C#; C-level; CI/CD", ["C"]),
    ("R", "R&D team; R or Python", ["R"]),
    ("JavaScript", "Node.js and JS", ["JS"]),
    ("Go", "Go, Golang, go to market", ["Go", "Golang"]),
    ("Spring", "Spring Boot; Spring 2024", ["Spring"]),
    ("PostgreSQL", "Postgres 15", ["Postgres"]),
    ("A/B Testing", "ran A/B tests", ["A/B tests"]),
])
def test_taxonomy_edge_cases(skill, text, hits):
    assert [m.group(0) for m in BY_NAME[skill].finditer(text)] == hits


def test_jd_sections_title_years_degree():
    parsed = jd.parse((HERE / "jd" / "data_scientist.txt").read_text())
    assert parsed["title"] == "Data Scientist"
    assert parsed["years"]["years"] == 3
    assert parsed["degree"]["label"] == "Bachelor's"
    assert parsed["degree"]["fields"] == ["computer science", "statistics"]
    kinds = {line.strip(): k for _, _, k, line in parsed["lines"]}
    assert kinds["- Kubernetes, Terraform"] == "preferred"
    assert kinds["- Strong Python and SQL skills"] == "required"
    assert kinds["We're a fintech company helping 2 million people save. Great benefits including "
                 "health insurance and a Python-themed hackathon."] == "ignore"


def test_backend_job_scores_backend_resume(resume):
    m = run(resume, "backend_engineer")
    t = terms(m)
    assert 55 <= m["score"] <= 75
    assert t["Python"]["status"] == "matched" and "experience" in t["Python"]["where"]
    assert t["Django"]["status"] == "missing"
    assert t["Apache Kafka"]["importance"] == "preferred"
    assert "GitHub" not in t  # only inside "GitHub Actions"
    assert t["CI/CD"]["status"] == "partial" and t["CI/CD"]["implied_by"] == ["GitHub Actions"]
    assert m["years"]["required"] == 5
    title = next(b for b in m["breakdown"] if b["key"] == "title")
    assert title["score"] == pytest.approx(2 / 3, abs=0.01)


def test_data_job_scores_backend_resume_low(resume):
    m = run(resume, "data_scientist")
    t = terms(m)
    assert m["score"] < 40
    assert t["PostgreSQL"]["wording_differs"] is True  # job says Postgres
    assert t["SQL"]["status"] == "partial"
    # Benefits text ("Python-themed hackathon") isn't a requirement.
    assert all(sp[0] > m["jd_text"].index("What you'll do") for sp in t["Python"]["jd_spans"])
    kinds = {s["kind"] for s in m["suggestions"]}
    assert {"missing", "implied", "wording", "title", "preferred"} <= kinds


def test_spans_point_at_the_right_text(resume):
    m = run(resume, "backend_engineer")
    for t in m["terms"]:
        for s, e in t["jd_spans"]:
            assert m["jd_text"][s:e].strip()
        for s, e in t["resume_spans"]:
            assert m["resume_text"][s:e].strip()
    py = terms(m)["Python"]
    assert {m["resume_text"][s:e] for s, e in py["resume_spans"]} == {"Python"}


def test_experience_months_merges_overlaps():
    jobs = [{"start": "2020-01", "end": "2020-12"}, {"start": "2020-06", "end": "2021-06"},
            {"start": "2019", "end": "2019"}]
    assert matcher._experience_months(jobs) == 12 + 6 + 12


def test_glued_headings_and_not_for_section():
    # Copied from LinkedIn: headings run into the next sentence ("The RoleWe are...").
    parsed = jd.parse((HERE / "jd" / "bjak_ai_engineer.txt").read_text())
    kinds = {line.strip(): k for _, _, k, line in parsed["lines"]}
    assert parsed["company"] == "BJAK"
    for heading in ("About BJAK", "The Role", "What You Will Build", "What We Look For",
                    "This Role Is Not For", "The Bar", "Location", "Language", "Interview Process"):
        assert kinds[heading] == "heading"
    assert kinds["People who only want research projects with no production ownership."] == "exclude"
    language = next(k for line, k in kinds.items() if line.startswith("English is our main"))
    assert language == "ignore"
    fintech = next(k for line, k in kinds.items() if line.startswith("Fintech, banking"))
    assert fintech == "preferred"  # "is a strong plus"


def test_ai_engineer_job_terms(resume):
    t = terms(run(resume, "bjak_ai_engineer"))
    for skill in ("AI Agents", "Tool Calling", "LLM Evaluation", "Guardrails", "KYC", "CRM",
                  "Retrieval-Augmented Generation", "Workflow Automation", "Python", "TypeScript"):
        assert skill in t, skill
    # Company blurb, "not for" list, logistics and bare constraint words aren't keywords.
    labels = " | ".join(t).lower()
    for bad in ("believe people", "research projects", "ownership", "communication", "cybersecurity",
                "s ai neobank", "bjak", "ai strategy", "real technology", "similar practical",
                "turn manual", "around real"):
        assert bad not in labels, bad
    assert t["Fintech"]["importance"] == "preferred"


@pytest.mark.parametrize("text,hits", [
    ("Built evaluations for our LLM agents", ["evaluations"]),
    ("Ran quarterly performance evaluations", []),
    ("Wrote LLM evals", ["LLM evals"]),
])
def test_context_only_aliases(text, hits):
    assert [m.group(0) for m in BY_NAME["LLM Evaluation"].finditer(text)] == hits


def test_bullet_starting_with_heading_word_is_not_a_heading():
    parsed = jd.parse("Requirements\n- Experience with Django\n- Skills in SQL\nNice to have\n• Kafka")
    kinds = [k for _, _, k, _ in parsed["lines"]]
    assert kinds == ["heading", "required", "required", "heading", "preferred"]


@pytest.mark.parametrize("text,label", [
    ("Work closely with backend and mobile teams", None),   # "ms" in "teams"
    ("p95 latency under 200 ms", None),
    ("Familiar with webmaster tools and master data management", None),
    ("MS in Computer Science or related field", "Master's"),
    ("B.Sc. in Mathematics", "Bachelor's"),
    ("Bachelor's or Master's degree in Statistics", "Bachelor's"),
    ("MBA preferred", "Master's"),
])
def test_degree_patterns(text, label):
    found = jd.parse("Requirements\n" + text)["degree"]
    assert (found and found["label"]) == label


def test_medtech_job_ad():
    # e2i Talent Link ad: eligibility line, "Job Descriptions" heading, "Label: duty" lines.
    parsed = jd.parse((HERE / "jd" / "medtech_ai_engineer.txt").read_text())
    assert parsed["title"] == "AI Engineer"  # from "As an AI Engineer, you will..."
    assert parsed["degree"] is None
    kinds = {line.strip()[:20]: k for _, _, k, line in parsed["lines"]}
    assert kinds["Talent Link by e2i i"] == "ignore"  # "Singaporeans and PRs only"
    assert kinds["Job Descriptions"] == "heading"


def test_medtech_job_terms(resume):
    t = terms(run(resume, "medtech_ai_engineer"))
    for skill in ("Small Language Models", "Edge AI", "Model Quantization", "Model Compression",
                  "AWS", "GCP", "CI/CD", "Retrieval-Augmented Generation", "Technical Documentation",
                  "Medical Device Software"):
        assert skill in t, skill
    labels = " | ".join(t).lower()
    for bad in ("permanent residents", "bring small", "constrained clinical", "contribute technical",
                "release models", "model development", "pipeline maintenance", "edge deployment:"):
        assert bad not in labels, bad
