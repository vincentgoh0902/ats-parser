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
