# NessWell

Daily mood logging (morning + evening), stats, and personal insights.

**Stack:** FastAPI + SQLAlchemy 2.0 + Alembic, Postgres and Auth on Supabase,
API on Render, PWA frontend on Cloudflare Pages.

## Status

- [x] Part 1: schema, migrations, auth, day logic
- [x] Part 2: check-in API, React PWA, push reminders
- [x] Part 3: stats dashboard (trend, weekdays, factors, calendar)
- [x] Part 4: insights (next-day effects, insight cards, tomorrow-morning forecast)
- [x] Part 5: recommendations, week-long experiments, personalised reminders
- [x] Part 6: Garmin sync (unofficial python-garminconnect)

## Try it locally first (no accounts, nothing deployed)

```bash
./demo.sh
```

Then open http://localhost:5173. The script starts a local database (Docker),
the real API in demo mode and the app, and fills in ~3 months of sample data with
built-in patterns (drinking hurts the next morning, workouts lift evenings, weekday
stress) plus Garmin-style metrics and a running experiment. Today's check-ins are
left for you to log.

- `./demo.sh --reset` gives fresh sample data; `./demo.sh --empty` wipes it so you
  can log from scratch.
- On your phone (same wifi), open the "On your phone" address the script prints.
  Everything works except push notifications, which need HTTPS (i.e. deployed).
- Needs Docker Desktop, Python 3.12+ and Node 18+. Already run Postgres? Set
  `DATABASE_URL` to it and Docker is skipped.
- Demo mode has no login. The API refuses to start in demo mode unless the
  database is on your own machine, so it can't be switched on by accident in
  production.

## Layout

```
backend/    FastAPI API (Python)
frontend/   React + Vite PWA
.github/workflows/reminders.yml   scheduler that triggers reminder pushes
```

## Local setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in values
alembic upgrade head
uvicorn app.main:app --reload # http://localhost:8000/docs
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env          # Supabase URL + anon key, API URL
npm run dev                   # http://localhost:5173
```

Tests need a local Postgres with a `wellness_test` database:

```bash
createdb wellness_test
pytest
```

## Supabase setup

1. Create a project at supabase.com.
2. **Database URL:** Project Settings > Database > Connection string > **Session pooler**.
   Use the pooler, not the direct connection (direct is IPv6-only).
   Change `postgresql://` to `postgresql+psycopg://`.
3. **Auth:** Authentication > Providers. Email is on by default. Google needs an
   OAuth client from Google Cloud Console.
4. Run `alembic upgrade head` against it. On Supabase the migration also adds
   row-level security and links profiles to `auth.users` (see below).

## Deploying

1. **Supabase**, as above. Under Authentication > URL Configuration, set the
   Site URL to your frontend URL and add it to the redirect URLs (email
   confirmation and Google login send people back there).
2. **Keys.** Run `python scripts/gen_vapid.py` and `python scripts/gen_garmin_key.py`
   once and put the output in the API's environment. Pick a long random
   `CRON_SECRET`. Back up `GARMIN_TOKEN_KEY`: if it's lost, everyone has to
   reconnect Garmin.
3. **API on Render.** New Web Service from the repo, root `backend`,
   build `pip install -r requirements.txt && alembic upgrade head`,
   start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Python 3.12+ is
   required (garminconnect needs it); `backend/.python-version` pins it. Add every variable
   from `.env.example`, with `ALLOWED_ORIGINS` set to the frontend URL.
4. **Frontend on Cloudflare Pages.** Root `frontend`, build `npm run build`,
   output `dist`. Set the three `VITE_` variables.
5. **Scheduler.** In GitHub, add the `API_URL` and `CRON_SECRET` Actions secrets.
   Two workflows use them: reminders every 15 minutes, Garmin sync hourly.
   The workflow pings every 15 minutes, which also stops the free Render
   instance from sleeping most of the time.
6. **On your phone**, open the site, add it to the Home Screen, open it from
   there, and turn on notifications in Settings. On iPhone this order matters:
   iOS only allows push for Home Screen apps (iOS 16.4+).

## Design notes

- **Look.** Black and white only, plus two greys for fine outlines and quiet
  fills. Light or dark follows the phone's setting; Settings > Appearance can
  override it (Match phone / Light / Dark), remembered per device. Items are rounded squares with 1px
  outlines; selected items fill solid. Charts use contrast instead of colour.
- **Type.** Cormorant Garamond (SIL Open Font License, self-hosted in
  `public/fonts/`, trimmed to Latin, 61 KB) stands in for Orpheus Pro, which is
  commercial. Orpheus Pro is first in the font stack: add licensed files plus an
  `@font-face` (instructions at the top of `styles.css`) and it takes over.
  Fine print uses the system sans for legibility at small sizes.

- **Hybrid schema.** Scores are fixed columns on `entries`. Everything else lives in
  `factors` (definitions) and `factor_values` (long format). New factors are
  new rows, not migrations. Bools are stored as 0/1, so one pandas `pivot` gives a
  numeric feature matrix.
- **Logical day.** A log before 04:00 local time counts toward the previous day
  (`app/days.py`). The timezone is stored per user in `profiles`.
- **Auth.** Supabase issues the tokens; the API only verifies them. Tokens are
  checked against the JWKS public keys by default, or HS256 if
  `SUPABASE_JWT_SECRET` is set (legacy projects).
- **Security, two layers.** The API filters every query by `user_id`. RLS in
  Postgres also blocks cross-user reads through Supabase's public Data API.
  The API connects as the table owner, so RLS doesn't apply to it. Never
  remove the `user_id` filters from API queries.
- **Reminders.** The API never runs timers (free Render sleeps). GitHub Actions
  calls `/internal/send-reminders`; each call sends what's due within a 3-hour
  window after the reminder time, records it per logical day, and skips anyone
  who has already checked in. Dead subscriptions are removed automatically.
- **Stats** (`app/stats.py`). One request returns morning, evening and
  whole-day results together so the toggle is instant; only a new date range
  refetches. Whole day = mean of whichever check-ins exist that day.
  Factor comparisons are same-day, with Welch 95% intervals, and need 5 days on
  each side before they count. Morning mood is only compared against morning
  factors, since evening ones happen later. Numeric factors split at your median.
- **Factor direction.** Each factor has optional end labels (work stress:
  Calm to Very stressed) and `higher_is` (better, worse, neutral). The labels
  show in the check-in; direction is there for recommendations (Part 5).
- **Insights** (`app/insights.py`). Next-day effects compare yesterday's
  factors with today's mood, using the same Welch method as the dashboard. The
  strongest clear results, same-day or next-day, become sentence cards.
- **Forecast.** Ridge regression predicts tomorrow morning from tonight's score,
  tonight's evening factors and whether tomorrow is a weekend. The penalty is
  picked by walk-forward validation (each day predicted only from days before
  it) and compared with guessing your running average. If it doesn't beat that
  baseline, the app shows your usual score and says nothing predicts it yet.
  The range shown is about 80%, from out-of-sample errors. Uses the last 365 days.
- **Recommendations** (`app/recommendations.py`). Only factors with a
  direction qualify, and only in the good direction, so a pattern like "alcohol
  lifts my evening" never becomes advice. Each factor's best clear effect
  (same day, or next morning) is ranked by gain in points, with percent vs the
  other days as context. Action text comes from `factors.action`, where
  `{good}` becomes the helpful side of the split ("7+", "below 3").
- **Experiments.** One at a time: aim for the action on N of the next 7 days.
  Adherence comes from what you log. At the end, days you did it are compared
  with days you didn't, and the week with the 4 weeks before. The verdict
  says plainly when a week isn't enough.
- **Personalised reminders.** Morning reminders carry the running experiment,
  a notice when one finishes, or a rotating top tip. If personalising fails,
  the plain reminder still goes out.
- **Garmin** (`app/garmin.py`). Unofficial, via python-garminconnect. The
  password is used once and never stored; OAuth tokens are Fernet-encrypted
  and re-encrypted after each sync (they refresh automatically). MFA is a
  two-step flow held in memory for 5 minutes, which assumes a single API
  instance. Synced values live in `daily_metrics` and join the analysis as
  extra factors (`source = garmin`), so stats, insights and the forecast use
  them automatically. Only steps can become a recommendation; HRV, resting
  heart rate, Body Battery, sleep score and stress are outcomes, not actions.
  Garmin's sleep hours prefill the morning check-in. If Garmin changes its
  login, first try upgrading `garminconnect`. The official Health API is the
  long-term route if this proves useful.
- **Detail layer.** Any factor can go deeper: long press it, or tap its ⋯, to
  open a sheet with structured fields plus a free-text note. Fields are defined
  per factor in `factors.detail_schema` (number, choice, multi, time), so adding
  or changing them is a data change, not a code change. Values are stored in
  `entry_details` as JSON and validated by the API against the schema. Adding
  specifics to a yes/no factor (e.g. "Run, 30 min") marks it yes. A one-line
  summary shows under the factor in the check-in. Details aren't used in the
  analysis yet; they're stored structured so insights can drill into them.
- **Early days** (`app/progress.py`, `app/tips.py`). Before personal patterns
  exist, Insights shows a "Getting to know you" box: days logged, check-in
  streak, behaviour streaks ("Worked out 3 days in a row", "4 alcohol-free
  days"), and a progress bar for each insight and the forecast. Saving a
  check-in shows milestones and streaks. Seven general tips from published
  research (each with its source) appear in Insights and rotate in morning
  reminders. A tip retires per person once they have 5+ days on each side for
  that factor, so their own data takes over. All of this is counting, not inference.
- **Forecast bar.** The forecast must beat "your running average" by at least
  10% in walk-forward testing before it's shown as a prediction. On pure noise
  the model wins by 0 to 3% through luck; on real patterns by about 40%.
- **Account deletion.** Deleting a Supabase auth user cascades to all their data.
