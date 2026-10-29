# AI-Powered Student Planner

A full-stack prototype that tracks courses, deadlines, and quiz/grade performance, then:

1. **Scores risk per course** using a transparent, explainable formula (not a black-box model) combining grade level, performance trend, deadline urgency, workload pressure, and self-rated difficulty.
2. **Generates a weekly study plan** that allocates your available study hours across courses in proportion to risk, and spreads sessions across the week.
3. **Writes a plain-language weekly briefing** summarizing what to prioritize.

## Project structure

```
ai-student-planner/
├── backend/
│   ├── app.py            Flask API + risk engine + planner (SQLite storage)
│   └── requirements.txt
└── frontend/
    ├── index.html         Single-page app (Dashboard / Courses / Assessments / Scores / Plan)
    ├── style.css
    └── app.js             Talks to the Flask API at http://127.0.0.1:5000
```

## Running it

**1. Backend**

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

This starts the API on `http://127.0.0.1:5000` and creates `planner.db` (SQLite) automatically on first run.

**2. Frontend**

The frontend is static — no build step. Just open it:

```bash
cd frontend
python -m http.server 8000
```

Then visit `http://127.0.0.1:8000` in your browser. (Opening `index.html` directly as a `file://` URL also works in most browsers since the app only talks to the API via `fetch`.)

**3. Try it**

Click **"Load demo data"** in the top bar to seed four sample courses with realistic deadlines, declining quiz trends, and study logs — this is the fastest way to see the risk engine and planner in action. Then explore the Dashboard and Weekly Plan tabs.

## How the risk score works

Each course gets a 0–100 risk score from five weighted signals:

| Signal | Weight | Logic |
|---|---|---|
| Grade level | 30% | How far the current grade is below an 85% "safe" target |
| Performance trend | 25% | Comparing recent quiz/assignment scores to earlier ones — a decline raises risk |
| Deadline urgency | 20% | How soon the next assessment is, weighted by how much it counts toward the final grade |
| Workload pressure | 15% | Hours actually logged this week vs. the course's expected weekly workload |
| Self-rated difficulty | 10% | Student's own 1–5 difficulty rating |

Score ≥ 70 = **High** risk, ≥ 40 = **Medium**, below that = **Low**. The formula and weights live in `backend/app.py` (`WEIGHTS`, `compute_risk_for_course`) — tune them there.

This is intentionally rule-based rather than an ML model trained on data you don't have yet: it's explainable ("why is this course high-risk?" has a real answer), works with zero historical data, and is a clean foundation to swap in a trained classifier later once you're logging real outcomes.

## How the weekly plan works

1. Each course's share of your total weekly hours is proportional to its risk score (with a floor so no course gets zero time).
2. Within a course's allocated hours, the number of study *sessions* per week scales with risk (5 sessions/week if High risk, 3 if Medium, 2 if Low), spread across the 7 days.

See `build_weekly_plan()` in `backend/app.py`.

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/courses` | List / create courses |
| PUT/DELETE | `/api/courses/<id>` | Update / delete a course |
| GET/POST | `/api/assessments` | List / create assignments, exams, quizzes |
| PUT/DELETE | `/api/assessments/<id>` | Update / delete an assessment |
| GET/POST | `/api/scores` | List / log quiz or assignment scores |
| DELETE | `/api/scores/<id>` | Delete a score |
| GET/POST | `/api/study-logs` | List / log actual study hours |
| GET | `/api/risk` | Ranked risk score per course |
| GET | `/api/plan?hours=20` | Generated weekly plan for N available hours |
| GET | `/api/summary` | Plain-language weekly briefing |
| POST | `/api/seed` | Replace all data with demo data |

## Extending this

- **Real ML risk model**: once you have real historical outcomes (did students who looked "high risk" actually underperform?), swap `compute_risk_for_course` for a trained classifier (scikit-learn logistic regression / gradient boosting) fed the same five signals as features — the API contract (`/api/risk`) doesn't need to change.
- **LLM-generated briefings**: replace `generate_summary_text()` with a call to an LLM API, passing the risk report + upcoming assessments as context, for a more natural-sounding weekly message.
- **Auth + multi-user**: add a `users` table and a `user_id` foreign key on `courses`; the current version is single-user (one shared `planner.db`).
- **Calendar sync**: import deadlines from Google Calendar / Canvas via their APIs instead of manual entry.
