# Compass

A personal planning assistant for a busy student life: tasks in every area of your life, a day plan that shows whether the day actually fits, and short daily and weekly check-ins.

| Home | Plan (phone) | Daily check-in |
|---|---|---|
| ![Home](docs/screenshots/home.png) | ![Plan on a phone](docs/screenshots/plan-phone.png) | ![Daily check-in](docs/screenshots/daily.png) |

## What it does

- **Accounts.** Email and password sign-in, closed to strangers unless you open sign-up. Every account starts with life areas: Class, TA work, STEMPower, Lab work, Personal, Jobs, YBC and Work.
- **Tasks and areas.** Add tasks in a pop-up with a due date, time estimate, priority and energy level. Filter by area, search, rename and recolor areas.
- **Day plan.** Put tasks into the morning, midday, afternoon and evening. A meter shows how full each part is, and a balance check flags overbooking, forgotten deadlines, late-night deep work and days with no personal time. Star a top 3.
- **Daily and weekly check-ins.** Close out the day, carry over what didn't happen, star tomorrow's top 3. Each week, set a goal, review deadlines and reschedule anything overdue.
- **Google Calendar.** Events from every calendar you have ticked (including Canvas feeds and shared calendars) show up in your plan and count against your free time.
- **Assistant.** Ask it to plan your day or week. It replies with a checklist of proposed changes, such as adding tasks, placing them, setting a top 3 or blocking time on Google Calendar. Nothing happens until you tap **Do it**.

## How it's built

| Piece | Choice |
|---|---|
| Framework | Django 5.1 |
| Database | PostgreSQL (SQLite works for quick local runs) |
| Accounts | Django auth via django-allauth (email + password, optional Google) |
| Interface | Server-rendered templates, [htmx](https://htmx.org) for updates without page reloads, hand-written responsive CSS |
| AI | OpenRouter, called only from the server |
| Hosting | Any 12-factor host; `render.yaml` sets up staging and production on Render |
| CI | GitHub Actions: ruff, a migrations check and the tests on PostgreSQL |

```
config/            settings (all from environment variables), URLs, WSGI
planner/
  models.py        areas, tasks, day plans, check-ins, calendar events, chat, AI usage
  views/           one module per feature: common (home, health), tasks, plan, checkins, calendar, assistant
  services/        the logic behind the views: days (balance check), gcal (Google Calendar), ai + assistant
  templates/       pages and htmx partials
  tests/           one test module per feature; Google and the AI are always mocked
```

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # then edit it
set -a; source .env; set +a
python manage.py migrate
python manage.py seed           # demo account: demo@compass.app / the DEMO_PASSWORD you set (compass-demo-2026 in DEBUG)
python manage.py createsuperuser   # or set OWNER_EMAIL / OWNER_PASSWORD before seeding
python manage.py runserver
```

## Tests and lint

```bash
ruff check .
python manage.py test
```

The tests never call Google or the AI: both are mocked. CI runs them against PostgreSQL 16 on every pull request.

## Configuration

Everything is an environment variable; see [`.env.example`](.env.example).

| Variable | What it does |
|---|---|
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Standard Django settings |
| `DATABASE_URL` | The database, for example `postgresql://user:pass@host/db` |
| `ENVIRONMENT` | `development`, `staging` or `production` (staging shows a badge) |
| `SIGNUP_OPEN`, `ALLOWED_EMAILS` | Who may create an account |
| `TIME_ZONE` | Your time zone, default `America/New_York` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in and Calendar access |
| `CALENDAR_SYNC_MINUTES` | How long a calendar copy stays fresh (default 10) |
| `OPENROUTER_API_KEY`, `AI_MODEL`, `AI_FALLBACK_MODELS` | The assistant's model and backups |
| `AI_DAILY_LIMIT` | Assistant requests per person per day (default 45) |
| `DEMO_EMAIL`, `DEMO_PASSWORD`, `OWNER_EMAIL`, `OWNER_PASSWORD` | Accounts created by `manage.py seed` |

## Connecting Google Calendar

1. In [Google Cloud Console](https://console.cloud.google.com), create a project and enable the **Google Calendar API**.
2. Under **Google Auth Platform**, set up the consent screen (audience **External**), add the scopes `.../auth/calendar.readonly` and `.../auth/calendar.events`, and **Publish** the app. In testing mode, Google signs you out every 7 days.
3. Create an OAuth client (**Web application**) with the redirect URI `https://YOUR-SITE/accounts/google/login/callback/`. Add `http://localhost:8000/accounts/google/login/callback/` for local use.
4. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then use **Settings → Connect Google Calendar**.

If your school's Google Workspace blocks outside apps, share your school calendar with a personal Gmail account and connect that one instead.

## Staging and production

`render.yaml` is a Render Blueprint with two public services, each with its own database:

| Environment | Service | Deploys when |
|---|---|---|
| Staging | `compass-staging` | every merge to `main` |
| Production | `compass` | you run **Actions → Promote to production**, which fast-forwards `production` to `main` |

To set it up: create two databases (for example two branches of a [Neon](https://neon.tech) project), then choose **New → Blueprint** in Render, pick this repo, and fill in each service's `DATABASE_URL`, `DEMO_PASSWORD` and the optional keys. Every deploy runs `build.sh`: install, collect static files, migrate and seed.

## How Compass was built

Each feature arrived as its own pull request that closes a user story, with a description of what it adds and how it was tested. Reading them in order is the quickest way to understand, or rebuild, the app. See [docs/backlog.md](docs/backlog.md) for every story and its acceptance criteria.
