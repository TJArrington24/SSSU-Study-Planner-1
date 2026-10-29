"""
AI-Powered Student Planner — Flask backend
============================================
Endpoints:
  Courses:      GET/POST /api/courses,          PUT/DELETE /api/courses/<id>
  Assessments:  GET/POST /api/assessments,      PUT/DELETE /api/assessments/<id>
  Quiz scores:  GET/POST /api/scores,           DELETE /api/scores/<id>
  Study logs:   GET/POST /api/study-logs
  Risk engine:  GET /api/risk                    -> ranked risk score per course
  Planner:      GET /api/plan?hours=20           -> generated weekly study plan
  Summary:      GET /api/summary                  -> plain-language weekly briefing

Run:
    pip install -r requirements.txt
    python app.py
Server starts on http://127.0.0.1:5000
"""

from flask import Flask, jsonify, request, g
from flask_cors import CORS
import sqlite3
import os
import math
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "planner.db")

app = Flask(__name__)
CORS(app)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT,
    credit_hours REAL NOT NULL DEFAULT 3,
    weekly_workload_hours REAL NOT NULL DEFAULT 3,
    current_grade REAL,          -- 0-100, latest known grade/average in the course
    difficulty INTEGER NOT NULL DEFAULT 3   -- 1 (easy) - 5 (hard), self-rated
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'assignment',   -- assignment | exam | quiz | project
    due_date TEXT NOT NULL,                    -- ISO date YYYY-MM-DD
    weight REAL NOT NULL DEFAULT 10             -- % of final grade
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    label TEXT NOT NULL,          -- e.g. "Quiz 1", "Midterm"
    score REAL NOT NULL,          -- percentage 0-100
    date_taken TEXT NOT NULL      -- ISO date
);

CREATE TABLE IF NOT EXISTS study_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    hours REAL NOT NULL,
    log_date TEXT NOT NULL        -- ISO date
);
"""


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def rows_to_list(rows):
    return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CRUD: Courses
# ---------------------------------------------------------------------------

@app.route("/api/courses", methods=["GET"])
def list_courses():
    db = get_db()
    rows = db.execute("SELECT * FROM courses ORDER BY id").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/courses", methods=["POST"])
def create_course():
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        """INSERT INTO courses (name, code, credit_hours, weekly_workload_hours, current_grade, difficulty)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            data.get("name"),
            data.get("code", ""),
            float(data.get("credit_hours", 3)),
            float(data.get("weekly_workload_hours", 3)),
            data.get("current_grade"),
            int(data.get("difficulty", 3)),
        ),
    )
    db.commit()
    new_row = db.execute("SELECT * FROM courses WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(new_row)), 201


@app.route("/api/courses/<int:course_id>", methods=["PUT"])
def update_course(course_id):
    data = request.get_json(force=True)
    db = get_db()
    existing = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Course not found"}), 404
    merged = {**row_to_dict(existing), **data}
    db.execute(
        """UPDATE courses SET name=?, code=?, credit_hours=?, weekly_workload_hours=?,
           current_grade=?, difficulty=? WHERE id=?""",
        (
            merged["name"], merged["code"], float(merged["credit_hours"]),
            float(merged["weekly_workload_hours"]), merged["current_grade"],
            int(merged["difficulty"]), course_id,
        ),
    )
    db.commit()
    updated = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
    return jsonify(row_to_dict(updated))


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
def delete_course(course_id):
    db = get_db()
    db.execute("DELETE FROM courses WHERE id=?", (course_id,))
    db.commit()
    return jsonify({"deleted": course_id})


# ---------------------------------------------------------------------------
# CRUD: Assessments (assignments, exams, quizzes, projects)
# ---------------------------------------------------------------------------

@app.route("/api/assessments", methods=["GET"])
def list_assessments():
    db = get_db()
    rows = db.execute(
        """SELECT a.*, c.name AS course_name FROM assessments a
           JOIN courses c ON c.id = a.course_id ORDER BY a.due_date"""
    ).fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/assessments", methods=["POST"])
def create_assessment():
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        """INSERT INTO assessments (course_id, title, type, due_date, weight)
           VALUES (?, ?, ?, ?, ?)""",
        (
            int(data["course_id"]),
            data.get("title", "Untitled"),
            data.get("type", "assignment"),
            data["due_date"],
            float(data.get("weight", 10)),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM assessments WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/assessments/<int:aid>", methods=["PUT"])
def update_assessment(aid):
    data = request.get_json(force=True)
    db = get_db()
    existing = db.execute("SELECT * FROM assessments WHERE id=?", (aid,)).fetchone()
    if not existing:
        return jsonify({"error": "Assessment not found"}), 404
    merged = {**row_to_dict(existing), **data}
    db.execute(
        """UPDATE assessments SET course_id=?, title=?, type=?, due_date=?, weight=?
           WHERE id=?""",
        (
            int(merged["course_id"]), merged["title"], merged["type"],
            merged["due_date"], float(merged["weight"]), aid,
        ),
    )
    db.commit()
    updated = db.execute("SELECT * FROM assessments WHERE id=?", (aid,)).fetchone()
    return jsonify(row_to_dict(updated))


@app.route("/api/assessments/<int:aid>", methods=["DELETE"])
def delete_assessment(aid):
    db = get_db()
    db.execute("DELETE FROM assessments WHERE id=?", (aid,))
    db.commit()
    return jsonify({"deleted": aid})


# ---------------------------------------------------------------------------
# CRUD: Scores (quiz / assignment / exam performance history)
# ---------------------------------------------------------------------------

@app.route("/api/scores", methods=["GET"])
def list_scores():
    db = get_db()
    course_id = request.args.get("course_id")
    if course_id:
        rows = db.execute(
            "SELECT * FROM scores WHERE course_id=? ORDER BY date_taken", (course_id,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM scores ORDER BY date_taken").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/scores", methods=["POST"])
def create_score():
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO scores (course_id, label, score, date_taken) VALUES (?, ?, ?, ?)",
        (
            int(data["course_id"]),
            data.get("label", "Quiz"),
            float(data["score"]),
            data.get("date_taken", date.today().isoformat()),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM scores WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/scores/<int:sid>", methods=["DELETE"])
def delete_score(sid):
    db = get_db()
    db.execute("DELETE FROM scores WHERE id=?", (sid,))
    db.commit()
    return jsonify({"deleted": sid})


# ---------------------------------------------------------------------------
# CRUD: Study logs (actual hours spent, self-reported)
# ---------------------------------------------------------------------------

@app.route("/api/study-logs", methods=["GET"])
def list_study_logs():
    db = get_db()
    rows = db.execute("SELECT * FROM study_logs ORDER BY log_date DESC").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/study-logs", methods=["POST"])
def create_study_log():
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO study_logs (course_id, hours, log_date) VALUES (?, ?, ?)",
        (
            int(data["course_id"]),
            float(data["hours"]),
            data.get("log_date", date.today().isoformat()),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM study_logs WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


# ---------------------------------------------------------------------------
# RISK ENGINE
# ---------------------------------------------------------------------------
#
# For each course we compute a 0-100 risk score from five weighted signals:
#
#   1. Grade level      (30%) — how far current grade is below a "safe" target (85)
#   2. Score trend       (25%) — is recent quiz/assignment performance declining?
#   3. Deadline urgency  (20%) — how soon is the next high-weight assessment?
#   4. Workload pressure (15%) — course workload relative to hours actually logged
#   5. Self-rated difficulty (10%) — student's own difficulty rating
#
# Every sub-score is normalized to 0-100 (100 = highest risk) then combined.
# This is intentionally transparent/rule-based rather than a black-box ML
# model, so results are explainable to the student ("why is this course
# high risk?").
# ---------------------------------------------------------------------------

WEIGHTS = {
    "grade": 0.30,
    "trend": 0.25,
    "urgency": 0.20,
    "workload": 0.15,
    "difficulty": 0.10,
}

SAFE_GRADE_TARGET = 85.0


def days_until(iso_date_str):
    try:
        d = datetime.strptime(iso_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - date.today()).days


def score_grade_component(current_grade):
    """Lower grade -> higher risk. current_grade may be None (no data yet)."""
    if current_grade is None:
        return 50.0  # neutral/unknown risk when no grade data exists
    gap = SAFE_GRADE_TARGET - current_grade
    risk = max(0.0, min(100.0, gap * (100.0 / SAFE_GRADE_TARGET)))
    return risk


def score_trend_component(scores):
    """
    Compares the average of the most recent half of scores vs the earlier half.
    A declining trend raises risk. Fewer than 2 scores -> neutral.
    """
    if len(scores) < 2:
        return 40.0
    ordered = sorted(scores, key=lambda s: s["date_taken"])
    values = [s["score"] for s in ordered]
    mid = len(values) // 2
    early = values[:mid] if mid > 0 else values[:1]
    recent = values[mid:]
    early_avg = sum(early) / len(early)
    recent_avg = sum(recent) / len(recent)
    delta = early_avg - recent_avg  # positive = declining
    # map delta of -30..+30 percentage points to risk 0..100, centered at 40
    risk = 40 + delta * 2.0
    return max(0.0, min(100.0, risk))


def score_urgency_component(assessments):
    """
    Looks at the nearest upcoming assessment weighted by its grade weight.
    Closer + higher-weight => higher urgency risk.
    """
    upcoming = []
    for a in assessments:
        d = days_until(a["due_date"])
        if d is not None and d >= 0:
            upcoming.append((d, a["weight"]))
    if not upcoming:
        return 10.0  # nothing upcoming -> low urgency
    best = None
    for d, weight in upcoming:
        # urgency contribution: closer days -> higher score, scaled by weight/100
        proximity_score = max(0.0, 100.0 - (d * 4.0))  # 0 days=100, 25+ days≈0
        contribution = proximity_score * (0.5 + weight / 100.0)
        if best is None or contribution > best:
            best = contribution
    return max(0.0, min(100.0, best))


def score_workload_component(course, logs):
    """
    Compares logged hours (last 7 days) against the course's expected weekly
    workload. Under-studying relative to workload = higher risk.
    """
    total_logged = sum(l["hours"] for l in logs)
    expected = course["weekly_workload_hours"] or 1
    ratio = total_logged / expected
    if ratio >= 1.0:
        return max(0.0, 20.0 - (ratio - 1.0) * 10.0)  # meeting/exceeding -> low risk
    return min(100.0, (1.0 - ratio) * 100.0)


def score_difficulty_component(course):
    # difficulty is 1-5 self-rated; map to 0-100
    return (course["difficulty"] - 1) / 4.0 * 100.0


def compute_risk_for_course(course, assessments, scores, logs):
    g = score_grade_component(course["current_grade"])
    t = score_trend_component(scores)
    u = score_urgency_component(assessments)
    w = score_workload_component(course, logs)
    d = score_difficulty_component(course)

    total = (
        g * WEIGHTS["grade"]
        + t * WEIGHTS["trend"]
        + u * WEIGHTS["urgency"]
        + w * WEIGHTS["workload"]
        + d * WEIGHTS["difficulty"]
    )
    total = round(max(0.0, min(100.0, total)), 1)

    if total >= 70:
        level = "High"
    elif total >= 40:
        level = "Medium"
    else:
        level = "Low"

    return {
        "course_id": course["id"],
        "course_name": course["name"],
        "risk_score": total,
        "risk_level": level,
        "components": {
            "grade_risk": round(g, 1),
            "trend_risk": round(t, 1),
            "urgency_risk": round(u, 1),
            "workload_risk": round(w, 1),
            "difficulty_risk": round(d, 1),
        },
    }


def get_recent_logs(db, course_id, days_back=7):
    rows = db.execute(
        "SELECT * FROM study_logs WHERE course_id=?", (course_id,)
    ).fetchall()
    cutoff = date.today().toordinal() - days_back
    out = []
    for r in rows:
        try:
            d = datetime.strptime(r["log_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if d.toordinal() >= cutoff:
            out.append(row_to_dict(r))
    return out


def build_risk_report():
    db = get_db()
    courses = rows_to_list(db.execute("SELECT * FROM courses").fetchall())
    report = []
    for c in courses:
        assessments = rows_to_list(
            db.execute("SELECT * FROM assessments WHERE course_id=?", (c["id"],)).fetchall()
        )
        scores = rows_to_list(
            db.execute("SELECT * FROM scores WHERE course_id=?", (c["id"],)).fetchall()
        )
        logs = get_recent_logs(db, c["id"])
        report.append(compute_risk_for_course(c, assessments, scores, logs))
    report.sort(key=lambda r: r["risk_score"], reverse=True)
    return report


@app.route("/api/risk", methods=["GET"])
def api_risk():
    return jsonify(build_risk_report())


# ---------------------------------------------------------------------------
# WEEKLY PLAN GENERATOR
# ---------------------------------------------------------------------------
#
# Allocates a student's total available weekly study hours across courses.
# Allocation weight per course = normalized blend of:
#     risk_score (60%) + deadline urgency of assessments due in next 14 days (40%)
# Then within each course, hours are split across days Mon-Sun, front-loading
# more time on courses with a closer deadline (simple greedy distribution).
# ---------------------------------------------------------------------------

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def build_weekly_plan(total_hours):
    db = get_db()
    risk_report = build_risk_report()
    if not risk_report:
        return {"total_hours": total_hours, "allocations": [], "days": {}}

    # weight = risk_score, with a floor so every course gets at least a little time
    weights = {r["course_id"]: max(r["risk_score"], 5.0) for r in risk_report}
    weight_sum = sum(weights.values())

    allocations = []
    for r in risk_report:
        course_id = r["course_id"]
        share = weights[course_id] / weight_sum
        hours = round(share * total_hours, 1)

        assessments = rows_to_list(
            db.execute(
                "SELECT * FROM assessments WHERE course_id=? ORDER BY due_date", (course_id,)
            ).fetchall()
        )
        next_due = None
        for a in assessments:
            d = days_until(a["due_date"])
            if d is not None and d >= 0:
                next_due = a
                break

        allocations.append({
            "course_id": course_id,
            "course_name": r["course_name"],
            "risk_score": r["risk_score"],
            "risk_level": r["risk_level"],
            "allocated_hours": hours,
            "next_assessment": {
                "title": next_due["title"],
                "type": next_due["type"],
                "due_date": next_due["due_date"],
                "days_left": days_until(next_due["due_date"]),
            } if next_due else None,
        })

    # Distribute each course's hours across the week.
    # Higher-risk courses get sessions spread earlier/more frequently.
    days = {day: [] for day in DAY_NAMES}
    for alloc in allocations:
        hours_left = alloc["allocated_hours"]
        if hours_left <= 0:
            continue
        # number of sessions this week, scaled by risk (more sessions if higher risk)
        if alloc["risk_score"] >= 70:
            session_count = 5
        elif alloc["risk_score"] >= 40:
            session_count = 3
        else:
            session_count = 2
        session_count = max(1, min(session_count, len(DAY_NAMES)))
        per_session = round(hours_left / session_count, 1)

        # spread across days starting Monday, evenly spaced
        step = max(1, len(DAY_NAMES) // session_count)
        placed = 0
        day_idx = 0
        while placed < session_count and day_idx < len(DAY_NAMES):
            day = DAY_NAMES[day_idx]
            days[day].append({
                "course_name": alloc["course_name"],
                "hours": per_session,
                "risk_level": alloc["risk_level"],
            })
            placed += 1
            day_idx += step

    return {
        "total_hours": total_hours,
        "allocations": allocations,
        "days": days,
    }


@app.route("/api/plan", methods=["GET"])
def api_plan():
    try:
        hours = float(request.args.get("hours", 20))
    except ValueError:
        hours = 20.0
    return jsonify(build_weekly_plan(hours))


# ---------------------------------------------------------------------------
# PLAIN-LANGUAGE WEEKLY SUMMARY
# ---------------------------------------------------------------------------

def generate_summary_text():
    report = build_risk_report()
    if not report:
        return "Add some courses to get your personalized weekly briefing."

    lines = []
    high = [r for r in report if r["risk_level"] == "High"]
    medium = [r for r in report if r["risk_level"] == "Medium"]

    if high:
        names = ", ".join(r["course_name"] for r in high)
        lines.append(f"⚠️ Priority focus this week: {names}. These courses show the highest combined risk from grades, recent performance trend, and upcoming deadlines.")
    elif medium:
        names = ", ".join(r["course_name"] for r in medium)
        lines.append(f"Keep an eye on: {names}. Risk is moderate — a bit of extra review time will help.")
    else:
        lines.append("You're in good shape across all courses this week. Keep up the consistent study habits.")

    db = get_db()
    for r in report[:3]:
        assessments = rows_to_list(
            db.execute(
                "SELECT * FROM assessments WHERE course_id=? ORDER BY due_date", (r["course_id"],)
            ).fetchall()
        )
        next_due = None
        for a in assessments:
            d = days_until(a["due_date"])
            if d is not None and d >= 0:
                next_due = a
                break
        if next_due:
            d = days_until(next_due["due_date"])
            due_phrase = "today" if d == 0 else f"in {d} day{'s' if d != 1 else ''}"
            lines.append(
                f"• {r['course_name']}: {next_due['type']} \"{next_due['title']}\" is due {due_phrase} "
                f"(risk score {r['risk_score']}/100, {r['risk_level']})."
            )
    return "\n".join(lines)


@app.route("/api/summary", methods=["GET"])
def api_summary():
    return jsonify({"summary": generate_summary_text()})


# ---------------------------------------------------------------------------
# Seed demo data (optional convenience endpoint)
# ---------------------------------------------------------------------------

@app.route("/api/seed", methods=["POST"])
def seed_demo_data():
    db = get_db()
    db.executescript("""
        DELETE FROM study_logs; DELETE FROM scores; DELETE FROM assessments; DELETE FROM courses;
    """)
    db.commit()

    from datetime import timedelta
    today = date.today()

    courses = [
        ("Data Structures & Algorithms", "CS201", 4, 8, 68, 4),
        ("Calculus II", "MATH152", 4, 6, 74, 4),
        ("Intro to Psychology", "PSY101", 3, 3, 88, 2),
        ("Organic Chemistry", "CHEM241", 4, 7, 61, 5),
    ]
    course_ids = {}
    for name, code, credits, workload, grade, diff in courses:
        cur = db.execute(
            """INSERT INTO courses (name, code, credit_hours, weekly_workload_hours, current_grade, difficulty)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, code, credits, workload, grade, diff),
        )
        course_ids[name] = cur.lastrowid

    assessments = [
        ("Data Structures & Algorithms", "Midterm Exam", "exam", today + timedelta(days=6), 25),
        ("Data Structures & Algorithms", "Assignment 4: Trees", "assignment", today + timedelta(days=2), 10),
        ("Calculus II", "Problem Set 7", "assignment", today + timedelta(days=3), 8),
        ("Calculus II", "Final Exam", "exam", today + timedelta(days=30), 35),
        ("Intro to Psychology", "Reading Quiz 5", "quiz", today + timedelta(days=4), 5),
        ("Organic Chemistry", "Lab Report 3", "assignment", today + timedelta(days=1), 12),
        ("Organic Chemistry", "Midterm Exam", "exam", today + timedelta(days=9), 30),
    ]
    for course_name, title, atype, due, weight in assessments:
        db.execute(
            "INSERT INTO assessments (course_id, title, type, due_date, weight) VALUES (?, ?, ?, ?, ?)",
            (course_ids[course_name], title, atype, due.isoformat(), weight),
        )

    scores = [
        ("Data Structures & Algorithms", [("Quiz 1", 75, -20), ("Quiz 2", 70, -12), ("Quiz 3", 62, -4)]),
        ("Calculus II", [("Quiz 1", 80, -18), ("Quiz 2", 76, -9), ("Quiz 3", 73, -3)]),
        ("Intro to Psychology", [("Quiz 1", 85, -15), ("Quiz 2", 90, -6)]),
        ("Organic Chemistry", [("Quiz 1", 66, -16), ("Quiz 2", 58, -8), ("Quiz 3", 55, -2)]),
    ]
    for course_name, quiz_list in scores:
        for label, score, offset in quiz_list:
            db.execute(
                "INSERT INTO scores (course_id, label, score, date_taken) VALUES (?, ?, ?, ?)",
                (course_ids[course_name], label, score, (today + timedelta(days=offset)).isoformat()),
            )

    logs = [
        ("Data Structures & Algorithms", 3, -2),
        ("Calculus II", 4, -1),
        ("Intro to Psychology", 3, -3),
        ("Organic Chemistry", 2, -1),
    ]
    for course_name, hours, offset in logs:
        db.execute(
            "INSERT INTO study_logs (course_id, hours, log_date) VALUES (?, ?, ?)",
            (course_ids[course_name], hours, (today + timedelta(days=offset)).isoformat()),
        )

    db.commit()
    return jsonify({"seeded": True, "courses": list(course_ids.keys())})


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
