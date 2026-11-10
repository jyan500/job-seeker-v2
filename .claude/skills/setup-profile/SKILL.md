---
name: setup-profile
description: Build data/profile.yaml and data/criteria.yaml from the user's resume (data/resumes/Jansen_Yan_Resume.pdf), asking the user for anything the resume doesn't contain. Run once before /apply-jobs, or again to update answers.
---

# Set up the applicant profile

1. Find the resume: use `resume.dir`/`resume.default` from an existing `data/profile.yaml`, otherwise `data/resumes/Jansen_Yan_Resume.pdf`. Read it with the Read tool (for PDFs pass `pages`). If it's missing, list `data/resumes/`, tell the user what you found, ask them to put the resume there, and stop.
2. Read the schemas `data/profile.example.yaml` and `data/criteria.example.yaml`. If `data/profile.yaml` / `data/criteria.yaml` already exist, read them too and treat this as an update (keep existing answers unless the user changes them).
3. Fill everything the resume supports: contact info, links, recent roles, total years of experience (computed from role dates), skills with approximate years, education. Do not invent anything.
4. Ask the user with AskUserQuestion (batch up to 4 questions per call) for what a resume can't tell you:
   - US work authorization, and whether they need sponsorship now or in the future
   - Desired salary (a number plus how to phrase it) and the minimum salary for filtering
   - Remote/hybrid/onsite preference, target locations, willingness to relocate, start date
   - Target titles and seniority levels, and any companies to exclude
   - EEO / veteran / disability answers (offer "decline to answer" as the default)
   - Match threshold (default 70)
5. Write `data/profile.yaml` and `data/criteria.yaml` following the example schemas. Include the `resume:` block with `dir: data/resumes` and `default:` set to the resume file you read. Copy the `sheet:` block from the example as is, unless the user gives a different sheet. Keep `daily_cap: 25` unless the user asks otherwise.
6. Check that `.env` exists with `ACCOUNT_PASSWORD` set (run `python tools/accounts.py password`, but don't echo the value back). If it's not set, tell the user to copy `.env.example` to `.env` and set the password they want for job-site accounts.
7. Show the user a short summary of the profile and criteria. Point them to the files in case they want to edit by hand.
