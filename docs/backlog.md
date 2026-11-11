# Backlog

Every feature in Compass started as one of these user stories. Each acceptance criterion was the spec for the pull request that closed it.

## 1. Accounts, data model and app foundation

As a busy student, I want my own private Compass account, so that my tasks and plans are mine alone and available on my laptop and phone.

**Acceptance criteria**

- [x] Sign in with email and password using Django's standard authentication (via django-allauth).
- [x] Sign-up is closed unless `SIGNUP_OPEN=1`; when `ALLOWED_EMAILS` is set, only those addresses can join.
- [x] Every new account gets default life areas: Class, TA work, STEMPower, Lab work, Personal, Jobs, YBC, Work.
- [x] All pages except sign-in and `/healthz` require sign-in; nobody can see another user's data.
- [x] `/healthz` returns 200 when the database is reachable and 503 when it isn't.
- [x] Configuration and secrets come from environment variables; the database is attached with `DATABASE_URL`; logs go to stdout; schema changes are migrations.
- [x] The layout works on phones (bottom tab bar) and desktops.
- [x] CI runs lint, a migrations check and the tests against PostgreSQL on every pull request.

## 2. Tasks and life areas

As a student juggling classes, TA work, research and clubs, I want to capture tasks and sort them by area of my life, so that nothing falls through the cracks.

**Acceptance criteria**

- [x] I can add, edit, complete, un-complete and delete a task with a title, area, due date, time estimate, priority, energy (deep focus or easy) and notes.
- [x] Adding or editing happens in a pop-up and the page updates without a full reload; it still works without JavaScript.
- [x] The Tasks page filters by area, searches title and notes, and can show done tasks.
- [x] Home shows tasks due now and coming up in the next three days; overdue tasks are marked.
- [x] In Settings I can rename areas, change their color, mark one as personal time, add new ones, and delete empty ones.
- [x] I can't see, change or use another user's tasks or areas (404 or rejected).

## 3. Day plan with a balance check

As a student with a packed schedule, I want to place tasks into the parts of my day and see whether the day actually fits, so that I stop overbooking myself.

**Acceptance criteria**

- [x] The Plan page shows any day split into Morning (8am–12pm), Midday (12–2pm), Afternoon (2–6pm) and Evening (6–11:30pm), with prev/next and a 7-day strip.
- [x] Each part shows its tasks, calendar events and a meter of time used against time available.
- [x] Adding to a part of the day opens a picker ordered by best fit (deadlines, priority, energy for that time).
- [x] A task appears at most once per day; adding it to another part moves it.
- [x] The balance check flags overbooked parts, unplanned tasks due that day or overdue, deep-focus work in the evening, three deep tasks in a row, and days with no personal time.
- [x] I can star up to three top tasks for a day; a fourth is refused with a message.
- [x] Home shows the day's balance, top 3 and plan.

## 4. Daily and weekly check-ins

As someone who plans at the end of the day, I want a short guided daily check-in and a weekly check-in, so that each day and week starts with a plan instead of a scramble.

**Acceptance criteria**

- [x] Daily check-in: close out today's planned and due tasks, carry unfinished planned tasks to the same part of tomorrow (once, never duplicated), look at tomorrow, star tomorrow's top 3, open tomorrow's plan, and finish with a one-line reflection.
- [x] Finishing records when I checked in, and the page says so.
- [x] Weekly check-in: set and save the week's goal and notes, see last week's goal, see this week's deadlines by day, add tasks area by area, reschedule overdue tasks inline, and finish the check-in.
- [x] On Sunday the weekly check-in plans the coming week.

## 5. Google Calendar import

As a student whose school events land on my Google Calendar automatically, I want Compass to show those events in my plan, so that I plan around what's already booked.

**Acceptance criteria**

- [x] I can connect Google from Settings (or sign in with Google); the connection asks for Calendar access and keeps a refresh token.
- [x] Compass copies events from every calendar I have ticked in Google Calendar (own, Canvas feeds, shared calendars) into its database, skipping cancelled and declined events and duplicate subscriptions.
- [x] Copies refresh when older than `CALENDAR_SYNC_MINUTES` or on 'Sync now'; events deleted in Google disappear on the next sync.
- [x] Busy events count toward each part of the day; events marked free are shown but not counted.
- [x] Expired access tokens refresh automatically; revoked access and Google outages show a clear message and never break a page.
- [x] Events are color-coded consistently: my calendar coral, Canvas blue, shared calendars their own color.

## 6. Planning assistant

As a busy student, I want to tell an assistant what's on my plate and have it propose a plan, so that planning takes a minute instead of twenty while I stay in control.

**Acceptance criteria**

- [x] Home has a chat with quick prompts; the model is called from the server through OpenRouter, never from the browser.
- [x] The assistant sees my open tasks, today's and tomorrow's plan, free time per part of the day and calendar events.
- [x] Replies are structured JSON: a message plus proposed changes (add/update/complete task, plan/unplan, set top 3, block time on Google Calendar).
- [x] Every proposed change is validated against my own data; anything malformed or pointing at someone else's data is dropped.
- [x] Nothing changes until I tap 'Do it'; I can untick individual changes or skip them all; a proposal can't be applied twice.
- [x] Calendar blocks are created on my own calendar in the task's area color; if Google fails, the plan is still saved and I'm told what failed.
- [x] Each user has a daily request limit (`AI_DAILY_LIMIT`); a model outage or bad reply shows a friendly message; free models fall back to `AI_FALLBACK_MODELS`.

## 7. Demo data, staging and production

As the owner of Compass, I want a repeatable way to load demo data and two public environments, so that I can try changes on staging before they reach the site I use every day.

**Acceptance criteria**

- [x] `python manage.py seed` creates or refreshes the demo account and example data, and optionally my own admin account; running it twice changes nothing extra.
- [x] Outside development, seeding refuses to run without `DEMO_PASSWORD`.
- [x] `render.yaml` defines staging (deploys on every merge to `main`) and production (deploys from the `production` branch), each with its own database.
- [x] Promoting to production is a deliberate, manual step (the 'Promote to production' workflow), which fast-forwards only.
- [x] The README explains how to run, test, deploy and reproduce the project, with screenshots.
