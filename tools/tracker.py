"""Job dedup + application log. All commands print JSON.

Usage examples:
  python tools/tracker.py check --source linkedin --job-id 123 --company "Acme Inc" --title "Sr. Software Engineer"
  python tools/tracker.py add --source linkedin --job-id 123 --company "Acme" --title "Senior Software Engineer" \
      --location "Remote" --url https://... --score 82 --status seen
  python tools/tracker.py set-status 7 applied --reason "Easy Apply"
  python tools/tracker.py count-today
  python tools/tracker.py report [--since 2026-11-01]
  python tools/tracker.py list --status needs_review
  python tools/tracker.py sheet-row 7          # what to type into the Google Sheet for job 7
  python tools/tracker.py mark-logged 7 --row 1802
  python tools/tracker.py unlogged             # applied jobs not yet in the sheet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, __import__("os").path.dirname(__file__))
from db import DATA_DIR, connect  # noqa: E402

STATUSES = ("seen", "applied", "skipped", "needs_review", "blocked", "failed")
WORK_TYPES = ("remote", "hybrid", "onsite")

# Legend cells in the user's sheet whose formatting (fill colour) is copied
# onto new rows. Overridable via criteria.yaml -> sheet.format_cells.
DEFAULT_FORMAT_CELLS = {
    "remote": "H1", "hybrid": "H2", "onsite": "H3", "contract": "H4", "no_response": "I5",
}
ATS_LABELS = [
    ("greenhouse.io", "Greenhouse"), ("lever.co", "Lever"), ("ashbyhq.com", "Ashby"),
    ("myworkdayjobs.com", "Workday"), ("workday.com", "Workday"),
    ("smartrecruiters.com", "SmartRecruiters"), ("icims.com", "iCIMS"),
    ("jobvite.com", "Jobvite"), ("bamboohr.com", "BambooHR"), ("workable.com", "Workable"),
    ("rippling.com", "Rippling"), ("dover.com", "Dover"), ("wellfound.com", "Wellfound"),
]
BOARD_NAMES = {"linkedin": "LinkedIn", "glassdoor": "Glassdoor", "builtin": "Built In", "jobright": "Jobright"}

COMPANY_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "co", "company", "plc", "gmbh", "lp", "llp",
}
TITLE_ABBREVIATIONS = {
    "sr": "senior", "jr": "junior", "swe": "software engineer",
    "sde": "software development engineer", "eng": "engineer",
    "engr": "engineer", "dev": "developer", "mgr": "manager",
    "i": "1", "ii": "2", "iii": "3", "iv": "4",
}


def _words(text: str) -> list[str]:
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text.lower())  # drop "(Remote)" etc.
    text = text.replace("&", " and ")
    return re.findall(r"[a-z0-9+#]+", text)


def norm_company(company: str) -> str:
    words = _words(company)
    while words and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def norm_title(title: str) -> str:
    # Drop trailing location/team qualifiers like "Software Engineer - Remote, US"
    title = re.split(r"\s[-–—|]\s", title)[0]
    words: list[str] = []
    for w in _words(title):
        words.extend(TITLE_ABBREVIATIONS.get(w, w).split())
    return " ".join(words)


def norm_key(company: str, title: str) -> str:
    """Cross-board identity of a role. Location is intentionally excluded:
    boards format it inconsistently, and the same role in several cities
    should only be applied to once."""
    return f"{norm_company(company)}|{norm_title(title)}"


def canon_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), path, "", ""))


def short_title(title: str) -> str:
    """The user's shorthand for a role: SE, Full Stack, Frontend, Backend, Mobile."""
    t = norm_title(title)
    if re.search(r"full ?stack", t):
        return "Full Stack"
    if re.search(r"front ?end", t):
        return "Frontend"
    if re.search(r"back ?end", t):
        return "Backend"
    if re.search(r"\b(mobile|ios|android)\b", t):
        return "Mobile"
    return "SE"


def site_label(source: str, url: str | None, apply_url: str | None) -> str:
    """Link text for the sheet's Site column."""
    host = urlsplit(apply_url).netloc.lower() if apply_url else ""
    for needle, label in ATS_LABELS:
        if needle in host:
            return label
    if not apply_url and source in ("linkedin", "glassdoor"):
        return f"{BOARD_NAMES[source]} Easy Apply"
    if apply_url:
        return "Company Site"
    return BOARD_NAMES.get(source, source.title())


def norm_contract_length(text: str | None) -> str | None:
    """'6 month contract' / '6-month' / '+6 months' / '1 year' -> '+6 months' / '+1 year'."""
    if not text:
        return None
    m = re.search(r"(\d+)\s*-?\s*(month|mo|year|yr|week|wk)s?\b", text.lower())
    if not m:
        return text.strip() or None
    n = int(m.group(1))
    unit = {"mo": "month", "yr": "year", "wk": "week"}.get(m.group(2), m.group(2))
    return f"+{n} {unit}{'s' if n != 1 else ''}"


def load_sheet_config() -> dict:
    path = DATA_DIR / "criteria.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("sheet") or {}
    except Exception:
        return {}


def build_sheet_row(job: dict, format_cells: dict | None = None) -> dict:
    fmt = {**DEFAULT_FORMAT_CELLS, **(format_cells or {})}
    work_type = job.get("work_type")
    parts = [short_title(job["title"])]
    if work_type in ("hybrid", "onsite") and job.get("location"):
        parts.append(job["location"])
    if job.get("is_contract") and job.get("contract_length"):
        parts.append(job["contract_length"])
    a_text = f"{job['company']} ({' - '.join(parts)})"

    applied = job.get("applied_at") or job.get("first_seen") or date.today().isoformat()
    b_date = date.fromisoformat(str(applied)[:10]).strftime("%m/%d/%Y")

    link_url = job.get("apply_url") or job.get("url")
    link_text = job.get("site_label") or site_label(job["source"], job.get("url"), job.get("apply_url"))

    if job.get("is_contract"):
        a_format = fmt["contract"]
    elif work_type in WORK_TYPES:
        a_format = fmt[work_type]
    else:
        a_format = None

    warnings = []
    if a_format is None:
        warnings.append("work_type unknown - column A left uncoloured; set it with set-status --work-type")
    if not link_url:
        warnings.append("no URL recorded - Site column will be plain text")

    return {
        "id": job["id"],
        "cells": {
            "A": a_text,
            "B": b_date,
            "C": {"text": link_text, "url": link_url},
            "D": job.get("resume_file") or "",
            "E": "No Response",
        },
        "copy_format_from": {"A": a_format, "E": fmt["no_response"]},
        "already_logged_row": job.get("sheet_row"),
        "warnings": warnings,
    }


def _row(r) -> dict | None:
    return dict(r) if r is not None else None


def find_duplicate(conn, *, source=None, job_id=None, company=None, title=None, apply_url=None):
    if source and job_id:
        r = conn.execute(
            "SELECT * FROM jobs WHERE source=? AND source_job_id=?", (source, str(job_id))
        ).fetchone()
        if r:
            return r, "same source job id"
    if company and title:
        r = conn.execute(
            "SELECT * FROM jobs WHERE norm_key=? ORDER BY id LIMIT 1",
            (norm_key(company, title),),
        ).fetchone()
        if r:
            return r, "same company + title"
    cu = canon_url(apply_url)
    if cu:
        r = conn.execute("SELECT * FROM jobs WHERE apply_url=? LIMIT 1", (cu,)).fetchone()
        if r:
            return r, "same apply url"
    return None, None


def cmd_check(args, conn):
    r, why = find_duplicate(
        conn, source=args.source, job_id=args.job_id, company=args.company,
        title=args.title, apply_url=args.apply_url,
    )
    return {
        "duplicate": r is not None,
        "match_reason": why,
        "existing": _row(r),
        "norm_key": norm_key(args.company, args.title) if args.company and args.title else None,
    }


def cmd_add(args, conn):
    r, why = find_duplicate(
        conn, source=args.source, job_id=args.job_id, company=args.company,
        title=args.title, apply_url=args.apply_url,
    )
    if r is not None:
        return {"added": False, "duplicate": True, "match_reason": why, "existing": _row(r)}
    cur = conn.execute(
        """INSERT INTO jobs (source, source_job_id, url, apply_url, company, title,
                             location, norm_key, match_score, status, reason,
                             work_type, is_contract, contract_length, site_label, resume_file, applied_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, CASE WHEN ?='applied' THEN datetime('now','localtime') END)""",
        (
            args.source, str(args.job_id) if args.job_id else None, args.url,
            canon_url(args.apply_url), args.company, args.title, args.location,
            norm_key(args.company, args.title), args.score, args.status, args.reason,
            args.work_type, int(bool(args.contract or args.contract_length)),
            norm_contract_length(args.contract_length), args.site_label, args.resume,
            args.status,
        ),
    )
    conn.commit()
    return {"added": True, "id": cur.lastrowid}


def cmd_set_status(args, conn):
    sets = ["status=?", "reason=COALESCE(?, reason)"]
    params: list = [args.status, args.reason]
    if args.status == "applied":
        sets.append("applied_at=COALESCE(applied_at, datetime('now','localtime'))")
    if args.apply_url:
        sets.append("apply_url=?")
        params.append(canon_url(args.apply_url))
    if args.score is not None:
        sets.append("match_score=?")
        params.append(args.score)
    for col, val in (("work_type", args.work_type), ("location", args.location),
                     ("site_label", args.site_label), ("resume_file", args.resume)):
        if val is not None:
            sets.append(f"{col}=?")
            params.append(val)
    if args.contract_length is not None:
        sets.append("contract_length=?")
        params.append(norm_contract_length(args.contract_length))
        if args.contract is None:
            args.contract = True
    if args.contract is not None:
        sets.append("is_contract=?")
        params.append(int(args.contract))
    params.append(args.id)
    cur = conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    if cur.rowcount == 0:
        return {"updated": False, "error": f"no job with id {args.id}"}
    return {"updated": True, "job": _row(conn.execute("SELECT * FROM jobs WHERE id=?", (args.id,)).fetchone())}


def count_applied_on(conn, day: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status='applied' AND date(applied_at)=?", (day,)
    ).fetchone()[0]


def cmd_count_today(args, conn):
    return {"date": date.today().isoformat(), "applied_today": count_applied_on(conn, date.today().isoformat())}


def cmd_report(args, conn):
    since = args.since or date.today().isoformat()
    counts = {s: 0 for s in STATUSES}
    for r in conn.execute(
        "SELECT status, COUNT(*) n FROM jobs WHERE date(COALESCE(applied_at, first_seen))>=? GROUP BY status",
        (since,),
    ):
        counts[r["status"]] = r["n"]
    applied = [
        _row(r) for r in conn.execute(
            "SELECT id, source, company, title, match_score, applied_at FROM jobs "
            "WHERE status='applied' AND date(applied_at)>=? ORDER BY applied_at", (since,))
    ]
    attention = [
        _row(r) for r in conn.execute(
            "SELECT id, source, company, title, status, reason, url FROM jobs "
            "WHERE status IN ('needs_review','blocked','failed') AND date(first_seen)>=? ORDER BY id", (since,))
    ]
    return {"since": since, "counts": counts, "applied": applied, "needs_attention": attention}


def _get_job(conn, job_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def cmd_sheet_row(args, conn):
    job = _get_job(conn, args.id)
    if not job:
        return {"error": f"no job with id {args.id}"}
    if job["status"] != "applied":
        return {"error": f"job {args.id} has status {job['status']!r}; only applied jobs are logged"}
    return build_sheet_row(job, load_sheet_config().get("format_cells"))


def cmd_mark_logged(args, conn):
    cur = conn.execute("UPDATE jobs SET sheet_row=? WHERE id=?", (args.row, args.id))
    conn.commit()
    return {"updated": cur.rowcount > 0, "id": args.id, "sheet_row": args.row}


def cmd_unlogged(args, conn):
    fmt = load_sheet_config().get("format_cells")
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status='applied' AND sheet_row IS NULL ORDER BY applied_at, id"
    ).fetchall()
    return {"rows": [build_sheet_row(dict(r), fmt) for r in rows]}


def cmd_list(args, conn):
    q, params = "SELECT * FROM jobs", []
    if args.status:
        q += " WHERE status=?"
        params.append(args.status)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)
    return {"jobs": [_row(r) for r in conn.execute(q, params)]}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def job_args(sp, required: bool):
        sp.add_argument("--source", required=required, help="linkedin|glassdoor|builtin|jobright|ats")
        sp.add_argument("--job-id")
        sp.add_argument("--company", required=required)
        sp.add_argument("--title", required=required)
        sp.add_argument("--location")
        sp.add_argument("--apply-url")

    def detail_args(sp):
        sp.add_argument("--work-type", choices=WORK_TYPES)
        sp.add_argument("--contract", action=argparse.BooleanOptionalAction, default=None)
        sp.add_argument("--contract-length", help='only if the posting states it, e.g. "6 months" (implies --contract)')
        sp.add_argument("--site-label", help='override link text, e.g. "Company Site"')
        sp.add_argument("--resume", help="resume file name, only if not the default")

    sp = sub.add_parser("check"); job_args(sp, required=False); sp.set_defaults(fn=cmd_check)
    sp = sub.add_parser("add"); job_args(sp, required=True); detail_args(sp)
    sp.add_argument("--url"); sp.add_argument("--score", type=int)
    sp.add_argument("--status", choices=STATUSES, default="seen"); sp.add_argument("--reason")
    sp.set_defaults(fn=cmd_add)

    sp = sub.add_parser("set-status")
    sp.add_argument("id", type=int); sp.add_argument("status", choices=STATUSES)
    sp.add_argument("--reason"); sp.add_argument("--apply-url"); sp.add_argument("--score", type=int)
    sp.add_argument("--location"); detail_args(sp)
    sp.set_defaults(fn=cmd_set_status)

    sp = sub.add_parser("sheet-row"); sp.add_argument("id", type=int); sp.set_defaults(fn=cmd_sheet_row)
    sp = sub.add_parser("mark-logged"); sp.add_argument("id", type=int)
    sp.add_argument("--row", type=int, required=True); sp.set_defaults(fn=cmd_mark_logged)
    sp = sub.add_parser("unlogged"); sp.set_defaults(fn=cmd_unlogged)

    sp = sub.add_parser("count-today"); sp.set_defaults(fn=cmd_count_today)
    sp = sub.add_parser("report"); sp.add_argument("--since"); sp.set_defaults(fn=cmd_report)
    sp = sub.add_parser("list"); sp.add_argument("--status", choices=STATUSES)
    sp.add_argument("--limit", type=int, default=50); sp.set_defaults(fn=cmd_list)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    with connect() as conn:
        result = args.fn(args, conn)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
