"""Generate the test resumes in tests/fixtures/. Run: python tests/make_fixtures.py

Every fixture is the same fictional person laid out a different way, so a
test can check that the layout, and nothing else, changes what gets parsed.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

OUT = Path(__file__).parent / "fixtures"
W, H = LETTER

NAME = "Alex Tan"
EMAIL = "alex.tan@example.com"
PHONE = "+1 415 555 0132"
JOBS = [
    ("Software Engineer", "Acme Corp", "San Francisco, CA", "Jan 2023 – Present",
     ["Built a payments API in Python and FastAPI serving 2M requests a day.",
      "Cut p95 latency 40% by moving hot paths to Redis."]),
    ("Software Engineering Intern", "Globex", "Remote", "Jun 2022 – Aug 2022",
     ["Shipped a React dashboard used by 300 internal analysts.",
      "Wrote CI pipelines with GitHub Actions and Docker."]),
]
SCHOOL = ("University of California, Berkeley", "B.S. Computer Science", "Aug 2018 – May 2022")
SKILLS = "Python, TypeScript, React, FastAPI, PostgreSQL, Docker, AWS"


class Writer:
    """Draws lines top-down in one column."""

    def __init__(self, c, x, right, y=H - 60):
        self.c, self.x, self.right, self.y = c, x, right, y

    def line(self, text, size=10, font="Helvetica", right_text=None, gap=14, link=None):
        """link=(url, substring of text to make clickable)"""
        self.c.setFont(font, size)
        self.c.drawString(self.x, self.y, text)
        if link:
            url, part = link
            x0 = self.x + self.c.stringWidth(text[:text.index(part)], font, size)
            x1 = x0 + self.c.stringWidth(part, font, size)
            self.c.linkURL(url, (x0, self.y - 2, x1, self.y + size), relative=0)
        if right_text:
            self.c.drawRightString(self.right, self.y, right_text)
        self.y -= gap

    def heading(self, text):
        self.y -= 6
        self.line(text, size=12, font="Helvetica-Bold", gap=16)

    def jobs(self):
        for title, company, loc, dates, bullets in JOBS:
            self.line(f"{title} — {company}", font="Helvetica-Bold", right_text=dates)
            self.line(loc, size=9)
            for b in bullets:
                self.line(f"• {b}", size=9)
            self.y -= 4

    def education(self):
        school, degree, dates = SCHOOL
        self.line(school, font="Helvetica-Bold", right_text=dates)
        self.line(f"{degree}, GPA: 3.8/4.0", size=9)


def single_column(c):
    w = Writer(c, 54, W - 54)
    w.line(NAME, size=20, font="Helvetica-Bold", gap=22)
    w.line(f"{EMAIL} | {PHONE} | San Francisco, CA | github.com/alextan", size=9,
           link=("https://github.com/alextan", "github.com/alextan"))
    w.heading("EXPERIENCE")
    w.jobs()
    w.heading("EDUCATION")
    w.education()
    w.heading("SKILLS")
    w.line(SKILLS, size=9)


def two_column(c):
    side = Writer(c, 40, 180, y=H - 120)
    side.heading("CONTACT")
    for t in (EMAIL, PHONE, "San Francisco, CA", "github.com/alextan"):
        side.line(t, size=8)
    side.heading("SKILLS")
    for s in SKILLS.split(", "):
        side.line(s, size=9)
    side.heading("EDUCATION")
    side.line("UC Berkeley", size=9)
    side.line("B.S. Computer Science", size=8)
    side.line("Aug 2018 – May 2022", size=8)
    main = Writer(c, 220, W - 40)
    main.line(NAME, size=22, font="Helvetica-Bold", gap=26)
    main.line("Backend engineer who likes fast, boring, reliable systems.", size=9, gap=20)
    main.heading("EXPERIENCE")
    main.jobs()


def hidden_links(c):
    w = Writer(c, 54, W - 54)
    w.line(NAME, size=20, font="Helvetica-Bold", gap=22)
    c.setFont("Helvetica", 9)
    x = 54
    for label, url in (("Email", f"mailto:{EMAIL}"), ("LinkedIn", "https://www.linkedin.com/in/alextan"),
                       ("Portfolio", "https://alextan.dev"), ("github.com/alextan", "https://github.com/someone-else")):
        c.drawString(x, w.y, label)
        width = c.stringWidth(label, "Helvetica", 9)
        c.linkURL(url, (x, w.y - 2, x + width, w.y + 9), relative=0)
        x += width + 18
    w.y -= 14
    w.heading("EXPERIENCE")
    w.jobs()
    w.heading("EDUCATION")
    w.education()


def header_contact(c):
    for page in range(2):
        c.setFont("Helvetica", 8)
        c.drawString(54, H - 30, f"{NAME} | {EMAIL} | {PHONE}")
        c.drawRightString(W - 54, 30, f"Page {page + 1}")
        w = Writer(c, 54, W - 54, y=H - 80)
        if page == 0:
            w.line(NAME, size=20, font="Helvetica-Bold", gap=22)
            w.heading("EXPERIENCE")
            w.jobs()
        else:
            w.heading("EDUCATION")
            w.education()
        c.showPage()


def unknown_heading(c):
    w = Writer(c, 54, W - 54)
    w.line(NAME, size=20, font="Helvetica-Bold", gap=22)
    w.line(f"{EMAIL} | {PHONE}", size=9)
    w.heading("WHERE I'VE WORKED")
    w.jobs()
    w.heading("E D U C A T I O N")
    w.education()


def image_only(c):
    img = Image.new("RGB", (1275, 1650), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=36)
    y = 100
    for t in (NAME, EMAIL, "EXPERIENCE", "Software Engineer — Acme Corp  Jan 2023 – Present"):
        d.text((100, y), t, fill="black", font=font)
        y += 60
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    c.drawImage(ImageReader(io.BytesIO(buf.getvalue())), 0, 0, W, H)


def table_layout(path):
    doc = SimpleDocTemplate(str(path), pagesize=LETTER)
    rows = [["Name", NAME], ["Email", EMAIL], ["Phone", PHONE],
            ["Experience", "Software Engineer, Acme Corp, Jan 2023 – Present"],
            ["Education", "B.S. Computer Science, UC Berkeley"], ["Skills", SKILLS]]
    t = Table(rows, colWidths=[90, 380])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    doc.build([t])


def main():
    OUT.mkdir(exist_ok=True)
    for name, draw in [("single_column", single_column), ("two_column", two_column),
                       ("hidden_links", hidden_links), ("header_contact", header_contact),
                       ("unknown_heading", unknown_heading), ("image_only", image_only)]:
        c = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=LETTER)
        c.setTitle(name)
        draw(c)
        c.save()
    table_layout(OUT / "table_layout.pdf")
    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
