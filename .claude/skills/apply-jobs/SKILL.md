---
name: apply-jobs
description: Search LinkedIn, Built In, Glassdoor and Jobright for software engineer jobs matching the user's profile and apply with their resume through the Claude in Chrome browser, skipping duplicates, pausing for email verification and captchas. Optional args - max=<n> to cap this run, boards=<comma list> to limit boards.
---

# Apply to matching jobs

Arguments (optional, from `$ARGUMENTS`): `max=<n>` caps applications this run (default: whatever remains of the daily cap). `boards=linkedin,builtin,...` limits which boards run.

All helper commands are run from the project root and print JSON:
- `python tools/tracker.py ...`: dedup and the application log
- `python tools/accounts.py ...`: accounts on job sites and ATSs
- `python tools/notify.py "<title>" "<message>"`: desktop toast for the user

## 0. Preflight
1. Read `data/profile.yaml` and `data/criteria.yaml`. If either is missing, tell the user to run `/setup-profile` and stop.
   - If `criteria.yaml` has no `sheet:` block (e.g. it was created before sheet logging existed), copy the `sheet:` block from `data/criteria.example.yaml` into it, then continue.
   - Work out the resume: `<project root>/<resume.dir>/<resume.default>` (default `data/resumes/Jansen_Yan_Resume.pdf`). Check that the file exists. If it doesn't, tell the user and stop.
   - If `resume.by_title` exists, then for each job use the first entry whose `match` appears (case-insensitive) in the job title, and otherwise the default. Note the resume used in the tracker `--reason` when it isn't the default.
2. Run `python tools/tracker.py count-today`. Remaining = `daily_cap - applied_today` (and `max` if given). If remaining ≤ 0, report and stop.
3. Before the first browser action, load the `anthropic-skills:chrome-browser` skill and follow it. Work only in tabs you open yourself and never touch the user's other tabs.
4. Open each board you'll use. If LinkedIn, Glassdoor or Jobright shows a login page, run `notify.py "Login needed" "<board>"`, ask the user to sign in in that tab and reply **done**, then end your turn. Do not type the user's credentials for the job boards themselves.

## 1. Search (one board at a time; order from `criteria.boards`)
- **LinkedIn**: Jobs search for each title × location. Filters: date posted (≤ `posted_within_days`), remote/hybrid per `criteria.remote`, experience level per `seniority`. Prefer "Easy Apply" postings but don't require them. The job ID is the number in `/jobs/view/<id>`.
- **Built In** (builtin.com/jobs): search by title, apply the remote filter. The job ID is the trailing number in the job URL.
- **Glassdoor**: Jobs search with title + location, filter by date posted. The job ID is the `jobListingId` / `jl=` value.
- **Jobright** (jobright.ai): start with the recommended-jobs feed, then a keyword search. The job ID comes from the job URL. Record Jobright's match % in the reason as a hint only.

From the result list, collect for each card: source, job ID, company, title, location, URL. Skip cards that clearly fail the criteria (excluded company, wrong seniority, excluded keywords) without opening them, but still record them as `skipped` so they're not looked at again.

## 2. Dedup (before opening any posting)
`python tools/tracker.py check --source <board> --job-id <id> --company "<co>" --title "<title>"`
If `duplicate` is true, skip it. This covers the same posting seen again and the same role on another board.
Exception: if the last application to this company (per the tracker, or the Google Sheet's date for the company) was 6 months or more ago, re-applying is allowed. Within 6 months, treat it as a duplicate.
Sheet history: before opening a posting, search the Google Sheet (Ctrl+F on the company name, as in step 6b). If a row matches the same normalized key (company + title, as `tracker.py` computes it), record that history in the tracker with `python tools/tracker.py add ... --status skipped --applied-on <sheet date YYYY-MM-DD> --reason "Already in sheet: <row text> row <N>"`, or `set-status` if the record already exists. Then run `check` again so the 6-month rule applies.
If a job is set to `needs_review` during the run, leave its browser tab open with the form or posting as far as it got, and tell the user which tab it is. Do not close it or start over later.

## 3. Match
Open the posting and read the full description. Score it 0–100 against the profile and criteria:
- title/seniority fit (25), required skills overlap (30), years of experience vs. required (15), location/remote fit (15), sponsorship/clearance/other hard requirements (10), salary vs. `min_salary` when listed (5)
- Hard fails get a score of 0: sponsorship needed but not offered, a clearance requirement, an excluded company or keyword, or an onsite-only role outside the target locations.

Also work out from the posting:
- **work type**: `remote`, `hybrid` or `onsite` (in-person). Use the posting's own label first, then the description. If it's genuinely unclear, use `onsite` when a single office location is listed.
- **contract**: whether it's a contract, contract-to-hire or temporary role (`--contract`). Otherwise leave it out.
- **contract length**: only if the posting clearly states it (e.g. "6 month contract", "12-month engagement"). Pass `--contract-length "6 months"`, which also implies `--contract`. Never guess. If the posting doesn't state the length, leave this out.
- **location**: city and state (e.g. `Seattle, WA`), needed for hybrid and onsite roles.

Record it: `python tools/tracker.py add --source ... --job-id ... --company ... --title ... --location "<City, ST>" --work-type <remote|hybrid|onsite> [--contract] [--contract-length "<N months>"] --url <posting url> --score <n> --status <s> --reason "<1-line why>"`
(Add `--resume <file>` only when a non-default resume will be used.)
- score ≥ `match_threshold` → status `seen` (we'll apply)
- `match_threshold - 10` ≤ score < threshold → `needs_review`, then move on
- below that → `skipped`, then move on

If `add` returns `duplicate: true`, skip it.

## 4. Apply (score ≥ threshold)
- **Easy Apply (LinkedIn / Glassdoor)**: go through the multi-step modal. When asked, upload the resume chosen in preflight (use its absolute path), or pick it if it's already uploaded. Fill fields from `profile.yaml`.
- **External ATS** (from any board, including Jobright's "Apply" button): after landing on the employer site, run `python tools/tracker.py check --apply-url "<current url>"`. If it's a duplicate, mark this job `skipped` with reason "already applied via <existing>". Otherwise store the URL with `set-status <id> seen --apply-url "<url>"`.
- **Account required**:
  1. `python tools/accounts.py get <current url>`
  2. If `exists`: log in with the `email` and the password from `python tools/accounts.py password`.
  3. If not: `python tools/accounts.py create <current url>`, then complete sign-up with the profile email and that password. Never print the password in your messages.
  4. If the site asks to verify email: `python tools/notify.py "Verify email" "<company> - <domain>"`, tell the user which site sent the email, ask them to click it and reply **done** (or **skip**), and **end your turn**. When they reply done, reload, run `accounts.py mark-verified <domain>` and continue. If they reply skip, `set-status <id> blocked --reason "email verification"`.
- **Form answers**: use `profile.yaml`. For questions it doesn't cover:
  - If the answer can be derived honestly from the profile (e.g. "years of Python?" from skills), answer it.
  - Optional questions: leave them blank, or use "decline to answer" for EEO.
  - Required questions you can't answer truthfully: `set-status <id> needs_review --reason "unanswerable: <question>"` and move on. Never invent experience, degrees or certifications.
- **Resume upload not possible** (the file chooser can't be driven): notify the user, ask them to attach it and reply done, then end your turn.

## 5. Captchas and human checks
On reCAPTCHA, hCaptcha, a Cloudflare "verify you are human" page, or any puzzle: **never attempt to solve or bypass it.** Run `python tools/notify.py "Captcha" "<company> - <site>"`, keep the tab in front, ask the user to solve it and reply **done** (or **skip**), and end your turn. On done, check that the page moved on and continue. On skip, mark the job `blocked`.

## 6. Submit
Check the filled form once, then submit. Confirm success (a confirmation page, "application submitted", or an email-confirmation message). Then:
`python tools/tracker.py set-status <id> applied --reason "<easy apply|greenhouse|...>"`
On an error you can't fix, use `failed` with the reason.

Then log it to the Google Sheet (step 6b) right away, before starting the next job.

After each application, re-check `count-today` against the remaining budget, and stop when it's used up.

## 6b. Log to the Google Sheet
The sheet is `criteria.sheet.url` (tab `criteria.sheet.tab`). Keep one tab open on it for the whole run and reuse it.

At the start of a run, first catch up: `python tools/tracker.py unlogged` lists applied jobs that aren't in the sheet yet (for example from an interrupted run). Log those first, using the same steps.

For each applied job:
1. `python tools/tracker.py sheet-row <id>` returns:
   - `cells.A`: the company and role, e.g. `Acme (SE)`, `Acme (Full Stack - Seattle, WA)`, or for a contract `Acme (SE - Seattle, WA - +6 months)` (always purple)
   - `cells.B`: the date, `MM/DD/YYYY`
   - `cells.C.text` + `cells.C.url`: link text (Greenhouse, Lever, LinkedIn Easy Apply, Company Site, …) and the link target
   - `cells.D`: the resume, blank unless a non-default one was used
   - `cells.E`: `No Response`
   - `copy_format_from`: legend cells whose formatting goes on A and E (`null` = leave uncoloured)
   - `warnings`: check these first. If the work type is missing, set it with `set-status <id> applied --work-type ...` and re-run.

   If `already_logged_row` is set, skip it.
2. **Find the next empty row:** click the Name Box (the cell-reference box at the top left), type `A2`, press Enter, then press Ctrl+Down. That jumps to the last filled row in column A (not the sheet's last row, since Ctrl+End goes to the far edge of the used range). If Ctrl+Down stops at a blank gap, press it again until it reaches the last filled row. Read the row number shown in the Name Box. Next row N = that + 1. Take a screenshot to confirm that row N is empty in columns A–E, treating a plain (non-hyperlinked) `Link` in column C as empty. If it isn't, move down until it is. Never overwrite a non-empty cell, except plain (non-hyperlinked) `Link` text in column C, which may be overwritten with the new row's link text and hyperlink.
3. **Enter the values:** Name Box → `A<N>` → Enter. Type `cells.A`, Tab, `cells.B`, Tab, `cells.C.text`, Tab, `cells.D` (if any), Tab, `No Response`, Enter. If autocomplete suggests something different from what you typed, dismiss it (Escape before the key that moves cells), so the typed value is kept.
4. **Link column C:** Name Box → `C<N>` → Enter, press Ctrl+K, paste or type `cells.C.url` into the link field and press Enter. Check that the cell shows the link text underlined in blue. If the link dialog won't cooperate, instead enter `=HYPERLINK("<url>","<text>")` into C<N>.
5. **Colours (paste format only):**
   - If `copy_format_from.A` is set: Name Box → that cell (e.g. `H1`) → Enter, Ctrl+C, Name Box → `A<N>` → Enter, **Ctrl+Alt+V** (paste format only).
   - Name Box → `copy_format_from.E` (e.g. `I5`) → Enter, Ctrl+C, Name Box → `E<N>` → Enter, Ctrl+Alt+V.
   - Press Escape to clear the copy highlight.
6. **Verify:** screenshot row N alongside the rows above it. The text must match, the date must be right, C must be a link, A must be green/orange/blue/purple as expected and E must be magenta. Fix anything wrong (Ctrl+Z undoes).
7. `python tools/tracker.py mark-logged <id> --row <N>`

If the sheet can't be reached or edited (signed out, no permission), don't block applying: keep going, and the job stays in `unlogged` for the next run. Notify the user once.

## 7. Pacing and safety
- One job at a time. Act at a human pace, and don't open dozens of tabs. Close each job's tab when it's done.
- If a board shows a rate limit, unusual-activity warning or account restriction, stop using that board for this run, notify the user, and continue with the others.

## 8. Wrap up
Run `python tools/tracker.py report` and summarize it for the user: applied today (company and title), plus needs-review, blocked and failed jobs with their reasons and URLs so they can follow up by hand.
