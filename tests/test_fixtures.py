"""Each fixture is the same resume in a different layout. The layout, and only
the layout, should decide which issues fire."""

from pathlib import Path

import pytest

from app import report

FIXTURES = Path(__file__).parent / "fixtures"


def build(name):
    return report.build((FIXTURES / f"{name}.pdf").read_bytes())


def codes(r):
    return {i["code"] for i in r["issues"]}


def test_single_column_is_clean():
    r = build("single_column")
    assert codes(r) == set()
    assert r["score"] == 100
    f = r["fields"]
    assert f["contact"]["name"] == "Alex Tan"
    assert f["contact"]["email"] == "alex.tan@example.com"
    assert f["contact"]["phone"] == "+1 415 555 0132"
    assert f["contact"]["location"] == "San Francisco, CA"
    jobs = [(e["title"], e["company"], e["start"], e["end"]) for e in f["experience"]]
    assert jobs == [("Software Engineer", "Acme Corp", "2023-01", "present"),
                    ("Software Engineering Intern", "Globex", "2022-06", "2022-08")]
    assert all(len(e["bullets"]) == 2 for e in f["experience"])
    edu = f["education"][0]
    assert edu["school"] == "University of California, Berkeley"
    assert edu["degree"] == "B.S. Computer Science"
    assert edu["gpa"] == "GPA: 3.8/4.0"
    assert "PostgreSQL" in f["skills"]
    assert r["links"][0]["visible_in_text"] is True


def test_two_column_breaks_simple_parser_only():
    r = build("two_column")
    assert "MULTI_COLUMN" in codes(r)
    # The smart parser keeps the jobs intact...
    assert [e["company"] for e in r["fields"]["experience"]] == ["Acme Corp", "Globex"]
    # ...while the simple parser interleaves the sidebar into them, the CONTACT
    # heading lands inside Experience, and no jobs survive.
    assert r["layout"]["order_similarity"] < 0.6
    assert "+1 415 555 0132   (cid:127) Built a payments API" in r["engines"]["legacy"]
    assert r["legacy_fields"]["experience"] == []


def test_hidden_and_mismatched_links():
    r = build("hidden_links")
    by_url = {l["url"]: l for l in r["links"]}
    assert by_url["https://alextan.dev"]["issue"] == "LINK_HIDDEN"
    assert by_url["https://www.linkedin.com/in/alextan"]["issue"] == "LINK_HIDDEN"
    assert by_url["mailto:alex.tan@example.com"]["issue"] == "LINK_HIDDEN"
    assert by_url["https://github.com/someone-else"]["issue"] == "LINK_MISMATCH"
    assert by_url["https://alextan.dev"]["anchor_text"] == "Portfolio"


def test_padded_link_rectangles_dont_pick_up_the_name_above():
    r = build("latex_header")
    by_url = {l["url"]: l for l in r["links"]}
    li = by_url["https://www.linkedin.com/in/goh-kai-swee-vincent/"]
    assert li["anchor_text"] == "linkedin.com/in/goh-kai-swee-vincent"
    assert li["issue"] is None
    assert by_url["https://github.com/vincentgoh0902"]["anchor_text"] == "github.com/vincentgoh0902"
    assert "LINK_MISMATCH" not in codes(r)


def test_contact_in_repeated_header():
    r = build("header_contact")
    assert {i["field"] for i in r["issues"] if i["code"] == "CONTACT_IN_HEADER"} == {"email", "phone"}


def test_unknown_and_letter_spaced_headings():
    r = build("unknown_heading")
    headings = {i["heading"] for i in r["issues"] if i["code"] == "UNKNOWN_HEADING"}
    assert headings == {"WHERE I'VE WORKED", "E D U C A T I O N"}
    assert "NO_EXPERIENCE" in codes(r)


def test_image_only_has_no_text():
    r = build("image_only")
    assert codes(r) == {"NO_TEXT_LAYER"}
    assert r["meta"]["has_text_layer"] is False


def test_table_is_not_mistaken_for_columns():
    r = build("table_layout")
    assert "TABLE_LAYOUT" in codes(r)
    assert "MULTI_COLUMN" not in codes(r)
    assert r["engines"]["modern"].startswith("Name   Alex Tan")


@pytest.mark.parametrize("data,msg", [
    (b"", "empty"), (b"hello", "not a PDF"), (b"%PDF-1.4 garbage", "could not be opened"),
])
def test_rejects_bad_uploads(data, msg):
    from app.guard import RejectedUpload
    with pytest.raises(RejectedUpload, match=msg):
        report.build(data)
