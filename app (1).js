const API_BASE = "http://127.0.0.1:5000/api";

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPut(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PUT ${path} failed: ${res.status}`);
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status}`);
  return res.json();
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v);
  });
  children.forEach((c) => node.appendChild(c));
  return node;
}

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "dashboard") loadDashboard();
    if (btn.dataset.tab === "plan") loadPlan();
  });
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

async function loadDashboard() {
  const [summary, risks] = await Promise.all([
    apiGet("/summary"),
    apiGet("/risk"),
  ]);

  document.getElementById("summaryText").textContent = summary.summary;

  const list = document.getElementById("riskList");
  list.innerHTML = "";
  if (risks.length === 0) {
    list.appendChild(el("div", { class: "empty-state", text: "No courses yet. Add one in the Courses tab, or load demo data." }));
    return;
  }
  risks.forEach((r) => {
    const row = el("div", { class: `risk-row ${r.risk_level}` });
    row.appendChild(el("span", { class: "name", text: r.course_name }));
    const track = el("div", { class: "risk-bar-track" });
    track.appendChild(el("div", { class: `risk-bar-fill ${r.risk_level}`, style: `width:${r.risk_score}%` }));
    row.appendChild(track);
    row.appendChild(el("span", { class: "score", text: `${r.risk_score}/100` }));
    row.appendChild(el("span", { class: "badge", text: r.risk_level }));
    list.appendChild(row);
  });
}

// ---------------------------------------------------------------------------
// Courses
// ---------------------------------------------------------------------------

let coursesCache = [];

async function loadCourses() {
  coursesCache = await apiGet("/courses");
  renderCoursesTable();
  populateCourseDropdowns();
}

function renderCoursesTable() {
  const body = document.getElementById("coursesTableBody");
  body.innerHTML = "";
  if (coursesCache.length === 0) {
    body.appendChild(el("tr", {}, [el("td", { colspan: "7", class: "empty-state", text: "No courses added yet." })]));
    return;
  }
  coursesCache.forEach((c) => {
    const tr = el("tr");
    tr.appendChild(el("td", { text: c.name }));
    tr.appendChild(el("td", { text: c.code || "—" }));
    tr.appendChild(el("td", { text: c.credit_hours }));
    tr.appendChild(el("td", { text: c.weekly_workload_hours }));
    tr.appendChild(el("td", { text: c.current_grade != null ? `${c.current_grade}%` : "—" }));
    tr.appendChild(el("td", { text: c.difficulty }));
    const actions = el("td");
    const editBtn = el("button", { class: "btn btn-ghost", style: "padding:4px 10px;font-size:0.78rem;margin-right:6px", text: "Edit" });
    editBtn.addEventListener("click", () => startEditCourse(c));
    const delBtn = el("button", { class: "btn btn-danger", text: "Delete" });
    delBtn.addEventListener("click", async () => {
      if (confirm(`Delete "${c.name}"? This also removes its assessments and scores.`)) {
        await apiDelete(`/courses/${c.id}`);
        await loadCourses();
      }
    });
    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    tr.appendChild(actions);
    body.appendChild(tr);
  });
}

function startEditCourse(c) {
  document.getElementById("courseId").value = c.id;
  document.getElementById("courseName").value = c.name;
  document.getElementById("courseCode").value = c.code || "";
  document.getElementById("courseCredits").value = c.credit_hours;
  document.getElementById("courseWorkload").value = c.weekly_workload_hours;
  document.getElementById("courseGrade").value = c.current_grade != null ? c.current_grade : "";
  document.getElementById("courseDifficulty").value = c.difficulty;
  document.getElementById("cancelCourseEdit").style.display = "inline-block";
  document.querySelector('[data-tab="courses"]').click();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.getElementById("cancelCourseEdit").addEventListener("click", () => {
  document.getElementById("courseForm").reset();
  document.getElementById("courseId").value = "";
  document.getElementById("cancelCourseEdit").style.display = "none";
});

document.getElementById("courseForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("courseId").value;
  const payload = {
    name: document.getElementById("courseName").value.trim(),
    code: document.getElementById("courseCode").value.trim(),
    credit_hours: parseFloat(document.getElementById("courseCredits").value),
    weekly_workload_hours: parseFloat(document.getElementById("courseWorkload").value),
    current_grade: document.getElementById("courseGrade").value === "" ? null : parseFloat(document.getElementById("courseGrade").value),
    difficulty: parseInt(document.getElementById("courseDifficulty").value, 10),
  };
  if (id) {
    await apiPut(`/courses/${id}`, payload);
  } else {
    await apiPost("/courses", payload);
  }
  document.getElementById("courseForm").reset();
  document.getElementById("courseId").value = "";
  document.getElementById("cancelCourseEdit").style.display = "none";
  await loadCourses();
});

function populateCourseDropdowns() {
  const selects = ["assessmentCourse", "scoreCourse", "logCourse"];
  selects.forEach((id) => {
    const select = document.getElementById(id);
    const prevValue = select.value;
    select.innerHTML = "";
    coursesCache.forEach((c) => {
      select.appendChild(el("option", { value: c.id, text: c.name }));
    });
    if (prevValue) select.value = prevValue;
  });
}

// ---------------------------------------------------------------------------
// Assessments
// ---------------------------------------------------------------------------

async function loadAssessments() {
  const assessments = await apiGet("/assessments");
  const body = document.getElementById("assessmentsTableBody");
  body.innerHTML = "";
  if (assessments.length === 0) {
    body.appendChild(el("tr", {}, [el("td", { colspan: "6", class: "empty-state", text: "No assessments added yet." })]));
    return;
  }
  assessments.forEach((a) => {
    const tr = el("tr");
    tr.appendChild(el("td", { text: a.course_name }));
    tr.appendChild(el("td", { text: a.title }));
    tr.appendChild(el("td", { text: a.type }));
    tr.appendChild(el("td", { text: a.due_date }));
    tr.appendChild(el("td", { text: `${a.weight}%` }));
    const actions = el("td");
    const delBtn = el("button", { class: "btn btn-danger", text: "Delete" });
    delBtn.addEventListener("click", async () => {
      await apiDelete(`/assessments/${a.id}`);
      await loadAssessments();
    });
    actions.appendChild(delBtn);
    tr.appendChild(actions);
    body.appendChild(tr);
  });
}

document.getElementById("assessmentForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    course_id: parseInt(document.getElementById("assessmentCourse").value, 10),
    title: document.getElementById("assessmentTitle").value.trim(),
    type: document.getElementById("assessmentType").value,
    due_date: document.getElementById("assessmentDue").value,
    weight: parseFloat(document.getElementById("assessmentWeight").value),
  };
  await apiPost("/assessments", payload);
  document.getElementById("assessmentForm").reset();
  document.getElementById("assessmentWeight").value = 10;
  await loadAssessments();
});

// ---------------------------------------------------------------------------
// Scores + Study logs
// ---------------------------------------------------------------------------

async function loadScores() {
  const scores = await apiGet("/scores");
  const courseMap = Object.fromEntries(coursesCache.map((c) => [c.id, c.name]));
  const body = document.getElementById("scoresTableBody");
  body.innerHTML = "";
  if (scores.length === 0) {
    body.appendChild(el("tr", {}, [el("td", { colspan: "5", class: "empty-state", text: "No scores logged yet." })]));
    return;
  }
  scores.forEach((s) => {
    const tr = el("tr");
    tr.appendChild(el("td", { text: courseMap[s.course_id] || `#${s.course_id}` }));
    tr.appendChild(el("td", { text: s.label }));
    tr.appendChild(el("td", { text: `${s.score}%` }));
    tr.appendChild(el("td", { text: s.date_taken }));
    const actions = el("td");
    const delBtn = el("button", { class: "btn btn-danger", text: "Delete" });
    delBtn.addEventListener("click", async () => {
      await apiDelete(`/scores/${s.id}`);
      await loadScores();
    });
    actions.appendChild(delBtn);
    tr.appendChild(actions);
    body.appendChild(tr);
  });
}

document.getElementById("scoreForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    course_id: parseInt(document.getElementById("scoreCourse").value, 10),
    label: document.getElementById("scoreLabel").value.trim(),
    score: parseFloat(document.getElementById("scoreValue").value),
    date_taken: document.getElementById("scoreDate").value,
  };
  await apiPost("/scores", payload);
  document.getElementById("scoreForm").reset();
  document.getElementById("scoreDate").value = todayISO();
  await loadScores();
});

document.getElementById("logForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    course_id: parseInt(document.getElementById("logCourse").value, 10),
    hours: parseFloat(document.getElementById("logHours").value),
    log_date: document.getElementById("logDate").value,
  };
  await apiPost("/study-logs", payload);
  document.getElementById("logForm").reset();
  document.getElementById("logDate").value = todayISO();
  alert("Study hours logged.");
});

// ---------------------------------------------------------------------------
// Weekly plan
// ---------------------------------------------------------------------------

async function loadPlan() {
  const hours = parseFloat(document.getElementById("totalHoursInput").value) || 20;
  const plan = await apiGet(`/plan?hours=${hours}`);

  const allocList = document.getElementById("allocationList");
  allocList.innerHTML = "";
  if (plan.allocations.length === 0) {
    allocList.appendChild(el("div", { class: "empty-state", text: "Add courses to generate a plan." }));
  } else {
    plan.allocations.forEach((a) => {
      const row = el("div", { class: `allocation-row ${a.risk_level}` });
      const top = el("div", { class: "row-top" });
      top.appendChild(el("span", { class: "name", text: a.course_name }));
      top.appendChild(el("span", { class: "hours", text: `${a.allocated_hours} hrs` }));
      row.appendChild(top);
      let metaText = `Risk: ${a.risk_score}/100 (${a.risk_level})`;
      if (a.next_assessment) {
        metaText += ` · Next: ${a.next_assessment.type} "${a.next_assessment.title}" due in ${a.next_assessment.days_left} day(s)`;
      }
      row.appendChild(el("div", { class: "meta", text: metaText }));
      allocList.appendChild(row);
    });
  }

  const weekGrid = document.getElementById("weekGrid");
  weekGrid.innerHTML = "";
  Object.entries(plan.days || {}).forEach(([day, sessions]) => {
    const col = el("div", { class: "day-col" });
    col.appendChild(el("h3", { text: day }));
    if (sessions.length === 0) {
      col.appendChild(el("div", { class: "empty-state", style: "font-size:0.78rem;padding:4px 0", text: "—" }));
    } else {
      sessions.forEach((s) => {
        const chip = el("div", { class: "session-chip" });
        chip.appendChild(el("div", { text: s.course_name }));
        chip.appendChild(el("span", { class: "chip-hours", text: `${s.hours} hrs` }));
        col.appendChild(chip);
      });
    }
    weekGrid.appendChild(col);
  });
}

document.getElementById("totalHoursInput").addEventListener("change", () => {
  if (document.getElementById("tab-plan").classList.contains("active")) loadPlan();
});

// ---------------------------------------------------------------------------
// Seed demo data
// ---------------------------------------------------------------------------

document.getElementById("seedBtn").addEventListener("click", async () => {
  if (!confirm("This will replace all current data with demo courses, assessments, and scores. Continue?")) return;
  await apiPost("/seed", {});
  await refreshAll();
  alert("Demo data loaded.");
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function refreshAll() {
  await loadCourses();
  await Promise.all([loadAssessments(), loadScores(), loadDashboard()]);
  if (document.getElementById("tab-plan").classList.contains("active")) await loadPlan();
}

document.getElementById("scoreDate").value = todayISO();
document.getElementById("logDate").value = todayISO();

refreshAll().catch((err) => {
  console.error(err);
  document.getElementById("summaryText").textContent =
    "Could not reach the backend. Make sure the Flask server is running on http://127.0.0.1:5000 (see README).";
});
