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
- Never apply in an excluded industry (`criteria.yaml: excluded_industries`: adult content, cannabis, gambling, crypto). Judge by what the company does, not its stack: read the posting's About section or the company page before applying, and skip with reason `excluded industry: <which>`. Add the company to `excluded_companies` so other boards skip it too.
- Time zone: the user is Pacific (`criteria.yaml: timezone`). Skip remote jobs that require Eastern/Central (or any non-Pacific) time zone residence or hours, with reason `time zone: requires <zone>`. Remote jobs open to Pacific or any US zone are fine. Check the posting and any application question like "do you live in the Eastern or Central time zone?" before filling a form.
- The user is a U.S. citizen (`profile.yaml: work_authorization.us_citizen`). Do not skip jobs for "US citizen only" or "USC/GC holders only" requirements, and answer citizenship questions "Yes". Clearance requirements (`clearance required`, TS/SCI) are still hard fails.
- Daily cap: `criteria.yaml: daily_cap` (25), checked with `tracker.py count-today`.
- Captcha, email verification or login → `notify.py`, ask the user to reply "done"/"skip", end the turn. Never try to solve a captcha.
- Verification code box on an application form (a code sent to the user's email or phone before submit): fill in everything else, keep the tab open, set the job to `needs_review` (reason "verification code required") and tell the user which tab it is. The user retrieves the code and submits by hand. After they confirm, set it to `applied` and log it to the sheet like any other. This is separate from account-signup email verification above.
- Required "I agree" checkboxes for terms or privacy statements: ask the user before ticking them.
- Never invent experience or answers. When a required question can't be answered truthfully, mark it `needs_review`.
- Log every application to the user's Google Sheet (`criteria.yaml: sheet`) using `tracker.py sheet-row` / `mark-logged`, as described in the apply-jobs skill step 6b. Never overwrite existing rows, except plain (non-hyperlinked) `Link` text in the sheet's column C, which may be overwritten.
- Never print `ACCOUNT_PASSWORD` in chat output.
- Tests: `python -m pytest tests`.
