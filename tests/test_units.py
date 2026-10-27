import asyncio

import httpx
import pytest

from app import links, report
from app.fields import dates, sections


@pytest.mark.parametrize("text,start,end", [
    ("Engineer  Jan 2023 – Present", "2023-01", "present"),
    ("01/2021 - 03/2022", "2021-01", "2022-03"),
    ("2019–2023", "2019", "2023"),
    ("Sept. 2020 to May 2022", "2020-09", "2022-05"),
    ("Summer 2022 - Fall 2022", "2022-06", "2022-09"),
])
def test_date_ranges(text, start, end):
    _, s, e = dates.find_range(text)
    assert (s, e) == (start, end)


def test_phone_number_is_not_a_date_range():
    assert dates.find_range("call 555-2019") is None


@pytest.mark.parametrize("line,key", [
    ("EXPERIENCE", "experience"), ("Work History:", "experience"),
    ("Skills & Interests", "skills"), ("Skills Summary", "skills"), ("Where I've been", None),
])
def test_heading_classification(line, key):
    assert sections.classify(line) == key


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data", "http://100.100.100.100/",  # Tailscale CGNAT
    "http://[::1]/", "http://example.com:8080/", "ftp://example.com/",
])
def test_link_check_refuses_private_targets(url):
    async def go():
        async with httpx.AsyncClient() as client:
            return await links.check_one(client, url)
    result = asyncio.run(go())
    assert result["ok"] is None and result["note"].startswith("not checked")


def test_link_norm():
    assert links.norm("https://www.GitHub.com/you/") == links.norm("github.com/you")


def test_latex_resume_layout():
    """Shape of a common LaTeX resume: a project dated with one month whose
    header holds the stack, and a "Skills Summary" section with bracketed notes."""
    text = """Alex Tan
alex@example.com | github.com/alextan
Experience
Data Science Intern   Jul 2026 – Present
Acme Corp
• Built LLM pipelines on Databricks.
Projects
Graph Fraud Detection | XGBoost, PyTorch Geometric, Neo4j   Oct 2026
• Compared XGBoost and GNNs on 203k transactions.
Skills Summary
Languages: Python, SQL, R
LLM & GenAI: RAG, DSPy (Prompt Optimisation), Azure OpenAI
Spoken Languages: English (Native), Mandarin (Fluent)
"""
    fields, _ = report.parse_fields(text)
    assert [s["key"] for s in fields["sections"]][-2:] == ["projects", "skills"]
    project = fields["projects"][0]
    assert project["title"] == "Graph Fraud Detection" and project["date_text"] == "Oct 2026"
    assert project["location"] is None  # "Python, LangGraph"-style stacks aren't "City, Region"
    assert project["bullets"] == ["Compared XGBoost and GNNs on 203k transactions."]
    assert fields["skills"] == ["Python", "SQL", "R", "RAG", "DSPy (Prompt Optimisation)", "Azure OpenAI",
                                "English (Native)", "Mandarin (Fluent)"]
