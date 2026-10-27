"""The editable resume: what the editor form holds and /api/render accepts.

It mirrors the parsed `fields`, but as an ordered list of sections so the user's
section order survives. Limits keep a render cheap: a resume over these sizes
isn't one a recruiter would read anyway.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.fields.entries import BULLET_RE
from app.fields.sections import HEADINGS

SHORT, LINE, PARA = 120, 400, 2000
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏ -‮﻿]")


def _clean(value: str) -> str:
    """No control or invisible characters, no line breaks, single spaces."""
    return " ".join(CONTROL_RE.sub("", value or "").split())


class Clean(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def clean_strings(cls, v):
        if isinstance(v, str):
            return _clean(v)
        if isinstance(v, list):
            return [x for x in (_clean(i) if isinstance(i, str) else i for i in v) if x != ""]
        return v


class Contact(Clean):
    name: str = Field("", max_length=SHORT)
    email: str = Field("", max_length=SHORT)
    phone: str = Field("", max_length=40)
    location: str = Field("", max_length=SHORT)
    links: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("links")
    @classmethod
    def link_length(cls, v):
        return [link[:SHORT] for link in v]


class Entry(Clean):
    """A job, project or activity. `title` and `org` share the first line."""
    title: str = Field("", max_length=SHORT)
    org: str = Field("", max_length=SHORT)
    location: str = Field("", max_length=SHORT)
    dates: str = Field("", max_length=60)
    bullets: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("bullets")
    @classmethod
    def bullet_length(cls, v):
        return [b[:LINE] for b in v]


class School(Clean):
    school: str = Field("", max_length=SHORT)
    degree: str = Field("", max_length=SHORT)
    location: str = Field("", max_length=SHORT)
    dates: str = Field("", max_length=60)
    gpa: str = Field("", max_length=30)
    details: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("details")
    @classmethod
    def detail_length(cls, v):
        return [d[:LINE] for d in v]


class Section(Clean):
    key: str = Field(max_length=30)
    heading: str = Field(max_length=60)
    kind: Literal["text", "entries", "education", "skills", "list"]
    text: str = Field("", max_length=PARA)
    entries: list[Entry] = Field(default_factory=list, max_length=12)
    schools: list[School] = Field(default_factory=list, max_length=6)
    items: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("items")
    @classmethod
    def item_length(cls, v):
        return [i[:LINE] for i in v]


class Resume(BaseModel):
    contact: Contact = Field(default_factory=Contact)
    sections: list[Section] = Field(default_factory=list, max_length=12)
    page_size: Literal["letter", "a4"] = "letter"


# Headings we write: the first alias of each key is the plain, standard one.
STANDARD_HEADING = {key: aliases[0].title() for key, aliases in HEADINGS.items()}
STANDARD_HEADING.update({"summary": "Summary", "activities": "Leadership & Activities"})
ENTRY_KEYS = {"experience", "projects", "activities"}


def _entry(e: dict) -> dict:
    return {"title": e.get("title") or "", "org": e.get("company") or "",
            "location": e.get("location") or "", "dates": e.get("date_text") or "",
            "bullets": e.get("bullets") or []}


def _plain(lines: list[str]) -> list[str]:
    return [BULLET_RE.sub("", l).strip() for l in lines if BULLET_RE.sub("", l).strip()]


def from_fields(fields: dict) -> Resume:
    """Prefill the editor from what the parser read. Section order follows the resume."""
    c = fields["contact"]
    contact = Contact(name=c.get("name") or "", email=c.get("email") or "", phone=c.get("phone") or "",
                      location=c.get("location") or "", links=c.get("urls") or [])
    sections, seen = [], set()
    order = [s["key"] for s in fields["sections"] if s["key"] != "top"]
    for key in order:
        if key in seen:
            continue
        seen.add(key)
        heading = STANDARD_HEADING.get(key, key.title())
        if key == "summary" and fields.get("summary"):
            sections.append(Section(key=key, heading=heading, kind="text", text=fields["summary"]))
        elif key == "experience":
            sections.append(Section(key=key, heading=heading, kind="entries",
                                    entries=[_entry(e) for e in fields["experience"]]))
        elif key == "projects":
            p = fields["projects"]
            if p and isinstance(p[0], dict):
                # Keep the whole project header ("Name | stack | links") as the title.
                entries = [{**_entry(e), "title": e.get("header") or e.get("title") or "", "org": ""} for e in p]
                sections.append(Section(key=key, heading=heading, kind="entries", entries=entries))
            else:
                sections.append(Section(key=key, heading=heading, kind="list", items=_plain(p)))
        elif key == "education":
            sections.append(Section(key=key, heading=heading, kind="education", schools=[
                {"school": e.get("school") or "", "degree": e.get("degree") or "",
                 "location": e.get("location") or "", "dates": e.get("date_text") or "",
                 "gpa": e.get("gpa") or "", "details": e.get("details") or []}
                for e in fields["education"]]))
        elif key == "skills":
            sections.append(Section(key=key, heading=heading, kind="skills", items=fields["skills"]))
        elif key in fields.get("other_sections", {}) and key not in ("contact", "links"):
            sections.append(Section(key=key, heading=heading, kind="list",
                                    items=_plain(fields["other_sections"][key])))
    return Resume(contact=contact, sections=sections)
