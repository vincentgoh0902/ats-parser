"""python -m app.cli resume.pdf [--jd job.txt] [--json] [--check-links] [--engine legacy|modern]"""

import argparse
import asyncio
import json
import sys

from app import report
from app.guard import RejectedUpload
from app.match import matcher


def _print(r: dict, engine: str) -> None:
    fields = r["fields"] if engine == "modern" else r["legacy_fields"]
    print(f"Parse health: {r['score']}/100   pages={r['meta']['pages']}   "
          f"producer={r['meta']['producer']}")
    print(f"\n=== Raw text ({engine} engine) ===\n{r['engines'][engine]}")
    c = fields["contact"]
    print("\n=== Contact ===")
    for k in ("name", "email", "phone", "location"):
        print(f"  {k:9} {c[k]}")
    for u in c["urls"]:
        print(f"  url       {u}")
    print("\n=== Sections ===")
    for s in fields["sections"]:
        print(f"  {s['key']:15} {s['heading'] or '(top of page)'}  [{s['lines']} lines]")
    print("\n=== Experience ===")
    for e in fields["experience"]:
        print(f"  {e['title']} | {e['company']} | {e['location']} | {e['start']} → {e['end']}"
              f"  ({len(e['bullets'])} bullets)")
    print("\n=== Education ===")
    for e in fields["education"]:
        print(f"  {e['school']} | {e['degree']} | {e['start']} → {e['end']} | {e['gpa']}")
    print(f"\n=== Skills (section) ===\n  {', '.join(fields['skills'])}")
    print(f"=== Skills (taxonomy hits) ===\n  {', '.join(fields['skills_detected'])}")
    print("\n=== Links ===")
    for l in r["links"]:
        check = l.get("check")
        status = f"  [{check['status'] or check['note']}]" if check else ""
        print(f"  {'click' if l['clickable'] else 'text '} {'seen  ' if l['visible_in_text'] else 'HIDDEN'}"
              f"  {l['url']}  anchor='{l['anchor_text']}'{status}")
    print("\n=== Issues ===")
    for i in r["issues"]:
        print(f"  [{i['severity']:6}] {i['code']}: {i['message']}\n           fix: {i['fix']}")
    if not r["issues"]:
        print("  none")


def _print_match(m: dict) -> None:
    print(f"\n=== Job match: {m['score']}/100 ({m['band_label']}) ===")
    for b in m["breakdown"]:
        print(f"  {b['label']:20} {b['score']:>4.0%}  (weight {b['weight']}%)  {b['detail']}")
    for imp in ("required", "responsibility", "preferred"):
        ts = [t for t in m["terms"] if t["importance"] == imp]
        if not ts:
            continue
        print(f"\n  {imp}:")
        for t in ts:
            mark = {"matched": "✓", "partial": "~", "missing": "✗"}[t["status"]]
            where = f"  [{', '.join(t['where'])}]" if t["where"] else ""
            label = t["label"] if t["label"] == t["term"] else f"{t['label']} → {t['term']}"
            print(f"    {mark} {label} ({t['kind']}, w={t['weight']}){where}")
    print("\n  Suggestions:")
    for s in m["suggestions"]:
        print(f"    - {s['text']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="See what an ATS parses from a resume PDF.")
    ap.add_argument("pdf")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-links", action="store_true")
    ap.add_argument("--engine", choices=("modern", "legacy"), default="modern")
    ap.add_argument("--jd", help="text file with a job description to match against")
    args = ap.parse_args()
    with open(args.pdf, "rb") as f:
        data = f.read()
    try:
        r = report.build(data)
    except RejectedUpload as e:
        print(f"Rejected: {e}", file=sys.stderr)
        return 1
    if args.check_links:
        r = asyncio.run(report.add_liveness(r))
    if args.jd:
        with open(args.jd, encoding="utf-8") as f:
            r["match"] = matcher.match(f.read(), r)
    if args.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        _print(r, args.engine)
        if args.jd:
            _print_match(r["match"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
