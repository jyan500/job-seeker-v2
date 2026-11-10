import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tracker  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBS_DB", str(tmp_path / "jobs.db"))


def run(capsys, *argv):
    assert tracker.main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def test_normalization():
    assert tracker.norm_company("Acme, Inc.") == "acme"
    assert tracker.norm_company("Acme Corporation") == "acme"
    assert tracker.norm_title("Sr. Software Engineer (Remote)") == "senior software engineer"
    assert tracker.norm_title("Senior Software Engineer - Remote, US") == "senior software engineer"
    assert tracker.norm_title("Software Engineer II") == "software engineer 2"
    assert tracker.norm_key("Acme Inc", "Sr SWE") == tracker.norm_key("ACME", "Senior Software Engineer")


def test_canon_url():
    assert tracker.canon_url("https://Boards.Greenhouse.io/acme/jobs/123/?gh_src=linkedin") == \
        "https://boards.greenhouse.io/acme/jobs/123"


def test_cross_board_duplicate(capsys):
    r = run(capsys, "add", "--source", "linkedin", "--job-id", "111", "--company", "Acme, Inc.",
            "--title", "Sr. Software Engineer", "--location", "Remote")
    assert r["added"]
    r = run(capsys, "check", "--source", "builtin", "--job-id", "999", "--company", "Acme",
            "--title", "Senior Software Engineer", "--location", "New York, NY")
    assert r["duplicate"] and r["match_reason"] == "same company + title"
    r = run(capsys, "add", "--source", "builtin", "--job-id", "999", "--company", "Acme",
            "--title", "Senior Software Engineer")
    assert not r["added"]


def test_same_source_id_duplicate(capsys):
    run(capsys, "add", "--source", "linkedin", "--job-id", "42", "--company", "A", "--title", "Engineer")
    r = run(capsys, "check", "--source", "linkedin", "--job-id", "42")
    assert r["duplicate"] and r["match_reason"] == "same source job id"


def test_apply_url_duplicate(capsys):
    run(capsys, "add", "--source", "jobright", "--company", "Foo", "--title", "Backend Engineer",
        "--apply-url", "https://jobs.lever.co/foo/abc?lever-source=jobright")
    r = run(capsys, "check", "--apply-url", "https://jobs.lever.co/foo/abc/")
    assert r["duplicate"] and r["match_reason"] == "same apply url"


def test_short_title():
    assert tracker.short_title("Senior Software Engineer") == "SE"
    assert tracker.short_title("Full-Stack Engineer") == "Full Stack"
    assert tracker.short_title("Sr. Frontend Developer") == "Frontend"
    assert tracker.short_title("Front End Engineer II") == "Frontend"
    assert tracker.short_title("Backend Engineer, Payments") == "Backend"


def test_site_label():
    assert tracker.site_label("linkedin", "https://linkedin.com/jobs/view/1", None) == "LinkedIn Easy Apply"
    assert tracker.site_label("glassdoor", "u", None) == "Glassdoor Easy Apply"
    assert tracker.site_label("builtin", "u", "https://boards.greenhouse.io/acme/jobs/1") == "Greenhouse"
    assert tracker.site_label("jobright", "u", "https://acme.wd5.myworkdayjobs.com/x") == "Workday"
    assert tracker.site_label("linkedin", "u", "https://careers.acme.com/1") == "Company Site"


def _job(**kw):
    base = dict(id=1, source="builtin", company="Acme", title="Software Engineer", location="Seattle, WA",
                url="https://builtin.com/job/1", apply_url="https://jobs.lever.co/acme/1",
                applied_at="2026-11-09 14:00:00", work_type="remote", is_contract=0,
                site_label=None, resume_file=None, sheet_row=None)
    base.update(kw)
    return base


def test_sheet_row_remote():
    r = tracker.build_sheet_row(_job())
    assert r["cells"]["A"] == "Acme (SE)"
    assert r["cells"]["B"] == "11/09/2026"
    assert r["cells"]["C"] == {"text": "Lever", "url": "https://jobs.lever.co/acme/1"}
    assert r["cells"]["D"] == ""
    assert r["cells"]["E"] == "No Response"
    assert r["copy_format_from"] == {"A": "H1", "E": "I5"}


def test_sheet_row_hybrid_onsite_contract():
    r = tracker.build_sheet_row(_job(work_type="hybrid", title="Full Stack Engineer"))
    assert r["cells"]["A"] == "Acme (Full Stack - Seattle, WA)"
    assert r["copy_format_from"]["A"] == "H2"
    assert tracker.build_sheet_row(_job(work_type="onsite"))["copy_format_from"]["A"] == "H3"
    assert tracker.build_sheet_row(_job(work_type="remote", is_contract=1))["copy_format_from"]["A"] == "H4"
    r = tracker.build_sheet_row(_job(work_type=None))
    assert r["copy_format_from"]["A"] is None and r["warnings"]


def test_contract_length():
    assert tracker.norm_contract_length("6 month contract") == "+6 months"
    assert tracker.norm_contract_length("12-month") == "+12 months"
    assert tracker.norm_contract_length("+3 months") == "+3 months"
    assert tracker.norm_contract_length("1 year") == "+1 year"
    assert tracker.norm_contract_length(None) is None

    remote = tracker.build_sheet_row(_job(is_contract=1, contract_length="+6 months"))
    assert remote["cells"]["A"] == "Acme (SE - +6 months)"
    assert remote["copy_format_from"]["A"] == "H4"
    hybrid = tracker.build_sheet_row(_job(work_type="hybrid", is_contract=1, contract_length="+12 months"))
    assert hybrid["cells"]["A"] == "Acme (SE - Seattle, WA - +12 months)"
    assert hybrid["copy_format_from"]["A"] == "H4"
    no_len = tracker.build_sheet_row(_job(work_type="onsite", is_contract=1))
    assert no_len["cells"]["A"] == "Acme (SE - Seattle, WA)"
    assert no_len["copy_format_from"]["A"] == "H4"


def test_contract_length_cli(capsys):
    a = run(capsys, "add", "--source", "builtin", "--job-id", "8", "--company", "Acme",
            "--title", "Software Engineer", "--work-type", "remote", "--contract-length", "6-month")
    run(capsys, "set-status", str(a["id"]), "applied")
    r = run(capsys, "sheet-row", str(a["id"]))
    assert r["cells"]["A"] == "Acme (SE - +6 months)" and r["copy_format_from"]["A"] == "H4"


def test_sheet_logging_flow(capsys):
    a = run(capsys, "add", "--source", "linkedin", "--job-id", "5", "--company", "Acme",
            "--title", "Frontend Engineer", "--location", "Austin, TX", "--work-type", "onsite")
    assert "error" in run(capsys, "sheet-row", str(a["id"]))  # not applied yet
    run(capsys, "set-status", str(a["id"]), "applied")
    r = run(capsys, "sheet-row", str(a["id"]))
    assert r["cells"]["A"] == "Acme (Frontend - Austin, TX)"
    assert r["cells"]["C"]["text"] == "LinkedIn Easy Apply"
    assert len(run(capsys, "unlogged")["rows"]) == 1
    run(capsys, "mark-logged", str(a["id"]), "--row", "1802")
    assert run(capsys, "unlogged")["rows"] == []


def test_count_today_and_report(capsys):
    a = run(capsys, "add", "--source", "linkedin", "--job-id", "1", "--company", "A", "--title", "SWE")
    run(capsys, "add", "--source", "linkedin", "--job-id", "2", "--company", "B", "--title", "SWE",
        "--status", "needs_review", "--reason", "borderline")
    assert run(capsys, "count-today")["applied_today"] == 0
    run(capsys, "set-status", str(a["id"]), "applied", "--reason", "Easy Apply")
    assert run(capsys, "count-today")["applied_today"] == 1
    rep = run(capsys, "report")
    assert rep["counts"]["applied"] == 1 and rep["counts"]["needs_review"] == 1
    assert rep["needs_attention"][0]["company"] == "B"
