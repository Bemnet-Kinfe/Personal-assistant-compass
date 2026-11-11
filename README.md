# Compass

A personal planning assistant for a busy student life: tasks in every area of your life, a day plan that shows whether the day actually fits, and short daily and weekly check-ins.


## What it does

- **Accounts.** Email and password sign-in, closed to strangers unless you open sign-up. Every account starts with life areas: Class, TA work, STEMPower, Lab work, Personal, Jobs, YBC and Work.
- **Tasks and areas.** Add tasks in a pop-up with a due date, time estimate, priority and energy level. Filter by area, search, rename and recolor areas.
- **Day plan.** Put tasks into the morning, midday, afternoon and evening. A meter shows how full each part is, and a balance check flags overbooking, forgotten deadlines, late-night deep work and days with no personal time. Star a top 3.

## How it's built

| Piece | Choice |
|---|---|
| Framework | Django 5.1 |
| Database | PostgreSQL (SQLite works for quick local runs) |
| Accounts | Django auth via django-allauth (email + password, optional Google) |
| Interface | Server-rendered templates, [htmx](https://htmx.org) for updates without page reloads, hand-written responsive CSS |
| Hosting | Any 12-factor host |
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


