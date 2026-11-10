# job-seeker-v2

Claude Code is the job-application agent. It drives the user's Chrome through the Claude in Chrome extension to search LinkedIn, Built In, Glassdoor and Jobright and apply with a resume from `data/resumes/` (default `Jansen_Yan_Resume.pdf`, set in `profile.yaml: resume`; not tailored).

- `/setup-profile` builds `data/profile.yaml` and `data/criteria.yaml` from the resume.
- `/apply-jobs [max=N] [boards=...]` runs search → dedup → match → apply. To repeat it: `/loop 2h /apply-jobs`.
- `tools/tracker.py` (dedup and log), `tools/accounts.py` (site accounts; one shared password from `.env`), `tools/notify.py` (desktop toast). State lives in `data/jobs.db`.

## Rules
- Run `tracker.py check` before opening or applying to any job. Never apply to a duplicate.
- Re-applying is allowed once 6 months have passed since the last application (or since the job/company was last marked on the Google Sheet). Within 6 months, treat it as a duplicate.
- When a job we're about to apply to already appears in the Google Sheet with the same normalized key (company + title, as `tracker.py` computes it), record that history in `data/jobs.db` using the sheet's date (`--applied-on`). This keeps the 6-month check accurate.
- Any job set to `needs_review` keeps its browser tab open, with the form or posting as far as it got. Do not close the tab or redo the form later. Close only tabs for jobs that were applied, skipped or otherwise finished.
- Daily cap: `criteria.yaml: daily_cap` (25), checked with `tracker.py count-today`.
- Captcha, email verification or login → `notify.py`, ask the user to reply "done"/"skip", end the turn. Never try to solve a captcha.
- Never invent experience or answers. When a required question can't be answered truthfully, mark it `needs_review`.
- Log every application to the user's Google Sheet (`criteria.yaml: sheet`) using `tracker.py sheet-row` / `mark-logged`, as described in the apply-jobs skill step 6b. Never overwrite existing rows, except plain (non-hyperlinked) `Link` text in the sheet's column C, which may be overwritten.
- Never print `ACCOUNT_PASSWORD` in chat output.
- Tests: `python -m pytest tests`.
