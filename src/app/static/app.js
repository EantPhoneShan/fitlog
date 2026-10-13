// FitLog front end: plain JavaScript, no framework. Talks to the Python API under /api.

const $ = (sel) => document.querySelector(sel);
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const NUM_FIELDS = ["weight", "waist", "protein", "water", "steps", "sleep"];
const TOKEN_KEY = "fitlog-token";
const USER_KEY = "fitlog-user"; // last known profile, so the app can still open offline

const state = { date: isoDate(new Date()), user: null, summary: null, range: 30, view: "today" };

// ---------- helpers ----------
function isoDate(d) {
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}
function shiftDate(iso, days) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + days);
  return isoDate(d);
}
function prettyDate(iso) {
  const today = isoDate(new Date());
  if (iso === today) return "Today";
  if (iso === shiftDate(today, -1)) return "Yesterday";
  const d = new Date(iso + "T12:00:00");
  return `${DAYS[d.getDay()]}, ${d.getDate()} ${d.toLocaleString("en", { month: "short" })}`;
}
// Anything a user typed goes through esc() before it is put into the page
function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const isRest = (name) => (name || "").trim().toLowerCase() === "rest";

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 2000);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(path, { ...options, headers });
  } catch {
    const err = new Error("Can't reach FitLog. Check your internet.");
    err.offline = true;
    throw err;
  }
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    logout();
    throw new Error("Please log in again");
  }
  if (res.status === 404 && (!options.method || options.method === "GET")) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || "Something went wrong";
    throw new Error(msg);
  }
  return body;
}

// ---------- AUTH ----------
let authMode = "login";

function showAuth() {
  $("#app").hidden = true;
  $("#auth").hidden = false;
  setAuthMode(authMode);
  api("/api/config").then((c) => ($("#codeField").dataset.required = c.signup_code_required ? "1" : "")).catch(() => {});
}

function setAuthMode(mode) {
  authMode = mode;
  const signup = mode === "signup";
  document.querySelectorAll(".auth-seg button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  document.querySelectorAll("#auth .signup-only").forEach((el) => (el.hidden = !signup));
  $("#codeField").hidden = !(signup && $("#codeField").dataset.required);
  const form = $("#authForm");
  form.elements.name.required = signup;
  form.elements.password.autocomplete = signup ? "new-password" : "current-password";
  $("#authSubmit").textContent = signup ? "Create account" : "Log in";
  $("#authError").textContent = "";
}

document.querySelectorAll(".auth-seg button").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.mode)));

$("#authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target.elements;
  const btn = $("#authSubmit");
  btn.disabled = true;
  $("#authError").textContent = "";
  try {
    const body = authMode === "signup"
      ? { name: f.name.value, email: f.email.value, password: f.password.value, code: f.code.value || null }
      : { email: f.email.value, password: f.password.value };
    const res = await api(`/api/auth/${authMode}`, { method: "POST", body: JSON.stringify(body) });
    localStorage.setItem(TOKEN_KEY, res.token);
    rememberUser(res.user);
    e.target.reset();
    showApp();
    if (authMode === "signup") toast(`Welcome, ${res.user.name}! Your plan is ready to edit.`);
  } catch (err) {
    $("#authError").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

function rememberUser(user) {
  state.user = user;
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  state.user = null;
  authMode = "login";
  showAuth();
}

function showApp() {
  $("#auth").hidden = true;
  $("#app").hidden = false;
  buildWorkoutOptions();
  show("today");
}

// ---------- TODAY ----------
async function loadToday() {
  $("#dateLabel").textContent = prettyDate(state.date);
  $("#dateInput").value = state.date;
  state.summary = await api(`/api/summary?day=${state.date}`);
  renderToday();
}

function buildWorkoutOptions() {
  const names = [...new Set(state.user.settings.split.map((d) => d.name).filter((n) => !isRest(n)))];
  const options = ["", ...names, "Cardio", "Rest", "Skipped"];
  $("#workoutSelect").innerHTML = options
    .map((n) => `<option value="${esc(n)}">${n ? esc(n) : "Not logged"}</option>`).join("");
}

function renderToday() {
  const s = state.summary;
  const entry = s.entry || {};
  const w = s.workout;
  const rest = isRest(w.name);
  const weekday = DAYS[new Date(state.date + "T12:00:00").getDay()];

  $("#hello").innerHTML = `Hi <b>${esc(s.name)}</b>, here's ${state.date === isoDate(new Date()) ? "today" : prettyDate(state.date)}.`;
  $("#workoutDay").textContent = `${weekday} · ${rest ? "recovery" : "today's session"}`;
  $("#workoutName").textContent = rest ? "Rest day" : `${w.name} day`;
  $("#workoutMins").textContent = rest ? "Recover" : `${w.exercises.length} exercises`;
  $("#workoutList").innerHTML = w.exercises.map((e) => `<li>${esc(e)}</li>`).join("");

  $("#workoutChips").innerHTML = rest ? "" : `
    <button class="chip ${entry.workout === w.name ? "on" : ""}" data-set="${esc(w.name)}">&#10003; Done</button>
    <button class="chip off ${entry.workout === "Skipped" ? "on" : ""}" data-set="Skipped">Skipped</button>`;

  const fmt = (v, digits = 1) => (v == null ? "–" : v.toFixed(digits));
  $("#sAvg").textContent = fmt(s.weight_avg_7d);
  const ch = $("#sChange");
  ch.textContent = s.weekly_change == null ? "–" : (s.weekly_change > 0 ? "+" : "") + s.weekly_change.toFixed(2);
  ch.className = "stat-val " + (s.weekly_change == null ? "" : s.weekly_change <= -0.2 ? "good" : "warn");
  $("#sStreak").textContent = s.streak;
  $("#sSessions").textContent = s.sessions_this_week;
  $("#advice").textContent = s.advice;

  fillForm(entry);
  renderRings();
  $("#saved").textContent = s.entry ? "Saved" : "Nothing logged yet";
}

function fillForm(entry) {
  const select = $("#workoutSelect");
  if (entry.workout && ![...select.options].some((o) => o.value === entry.workout)) {
    select.insertAdjacentHTML("beforeend", `<option value="${esc(entry.workout)}">${esc(entry.workout)}</option>`);
  }
  for (const el of $("#dayForm").elements) {
    if (el.name) el.value = entry[el.name] ?? "";
  }
}

function readForm() {
  const data = {};
  for (const el of $("#dayForm").elements) {
    if (!el.name) continue;
    const v = el.value.trim();
    if (v === "") continue;
    data[el.name] = NUM_FIELDS.includes(el.name) ? Number(v) : v;
  }
  return data;
}

const RINGS = [
  { key: "protein", label: "Protein", unit: "g", color: "var(--lime)", add: 25, addLabel: "+25 g" },
  { key: "water", label: "Water", unit: "L", color: "var(--blue)", add: 0.5, addLabel: "+0.5 L" },
  { key: "steps", label: "Steps", unit: "", color: "var(--orange)", add: 1000, addLabel: "+1k" },
  { key: "sleep", label: "Sleep", unit: "h", color: "var(--violet)", add: 0.5, addLabel: "+30 min" },
];

function renderRings() {
  const data = readForm();
  const targets = state.summary.targets;
  const C = 2 * Math.PI * 30;
  const k = (n) => (n >= 1000 ? +(n / 1000).toFixed(1) + "k" : n);
  $("#rings").innerHTML = RINGS.map((r) => {
    const value = data[r.key] || 0;
    const pct = targets[r.key] ? Math.min(value / targets[r.key], 1) : 0;
    const shown = r.key === "steps" ? k(value) : value;
    const goal = r.key === "steps" ? k(targets.steps) : `${targets[r.key]} ${r.unit}`;
    return `
      <div class="ring">
        <div class="ring-wrap">
          <svg viewBox="0 0 72 72">
            <circle class="track" cx="36" cy="36" r="30"/>
            <circle class="bar" cx="36" cy="36" r="30" stroke="${r.color}"
              stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"/>
          </svg>
          <span class="ring-val">${shown}</span>
        </div>
        <span class="ring-lbl">${r.label}<br>of ${goal}</span>
        <button type="button" class="ring-add" data-add="${r.key}" data-amount="${r.add}">${r.addLabel}</button>
      </div>`;
  }).join("");
}

let saveTimer;
function scheduleSave() {
  $("#saved").textContent = "Saving…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 700);
}

async function save() {
  clearTimeout(saveTimer);
  try {
    await api(`/api/days/${state.date}`, { method: "PUT", body: JSON.stringify(readForm()) });
    state.summary = await api(`/api/summary?day=${state.date}`);
    renderToday();
    $("#saved").textContent = "Saved ✓";
    return true;
  } catch (err) {
    $("#saved").textContent = "Not saved";
    toast(err.message);
    return false;
  }
}

// ---------- HISTORY ----------
async function loadHistory() {
  const end = isoDate(new Date());
  const start = shiftDate(end, -(state.range - 1));
  const days = await api(`/api/days?start=${shiftDate(start, -6)}&end=${end}`);
  renderChart(days, start, end);
  renderHistoryList(days.filter((d) => d.date >= start).reverse());
}

function renderChart(days, start, end) {
  const chart = $("#chart");
  const byDate = Object.fromEntries(days.map((d) => [d.date, d]));
  const points = [];
  for (let d = start, i = 0; d <= end; d = shiftDate(d, 1), i++) {
    const window = [];
    for (let k = 0; k < 7; k++) {
      const w = byDate[shiftDate(d, -k)]?.weight;
      if (w) window.push(w);
    }
    points.push({
      i, date: d,
      weight: byDate[d]?.weight ?? null,
      avg: window.length ? window.reduce((a, b) => a + b, 0) / window.length : null,
    });
  }
  const weights = points.flatMap((p) => [p.weight, p.avg]).filter((v) => v != null);
  if (weights.length < 2) {
    chart.innerHTML = `<div class="empty">Log your weight on a few mornings<br>and your trend line shows up here.</div>`;
    return;
  }
  const W = Math.max(chart.clientWidth, 280), H = 220, pad = { l: 34, r: 8, t: 10, b: 24 };
  const min = Math.floor(Math.min(...weights) - 0.5), max = Math.ceil(Math.max(...weights) + 0.5);
  const x = (i) => pad.l + (i / Math.max(points.length - 1, 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - min) / (max - min)) * (H - pad.t - pad.b);

  const ticks = [];
  const step = Math.max(1, Math.round((max - min) / 4));
  for (let v = min; v <= max; v += step) ticks.push(v);
  const grid = ticks.map((v) => `<line class="gridline" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text x="0" y="${y(v) + 4}">${v}</text>`).join("");
  const avgPts = points.filter((p) => p.avg != null);
  const avgPath = avgPts.map((p, k) => `${k ? "L" : "M"}${x(p.i)},${y(p.avg)}`).join(" ");
  const area = avgPts.length ? `${avgPath} L${x(avgPts.at(-1).i)},${H - pad.b} L${x(avgPts[0].i)},${H - pad.b} Z` : "";
  const dots = points.filter((p) => p.weight != null)
    .map((p) => `<circle cx="${x(p.i)}" cy="${y(p.weight)}" r="3.5" fill="var(--blue)"><title>${p.date}: ${p.weight} kg</title></circle>`).join("");
  const labels = [points[0], points[Math.floor(points.length / 2)], points.at(-1)]
    .map((p, k) => `<text x="${x(p.i)}" y="${H - 4}" text-anchor="${["start", "middle", "end"][k]}">${prettyDate(p.date)}</text>`).join("");

  chart.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}">
      <defs><linearGradient id="fade" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="#c8f560" stop-opacity=".25"/><stop offset="1" stop-color="#c8f560" stop-opacity="0"/>
      </linearGradient></defs>
      ${grid}
      <path d="${area}" fill="url(#fade)"/>
      <path d="${avgPath}" fill="none" stroke="var(--lime)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
      ${dots}${labels}
    </svg>`;
}

function renderHistoryList(days) {
  const list = $("#historyList");
  if (!days.length) {
    list.innerHTML = `<div class="card empty" style="height:120px">No entries in this range yet.</div>`;
    return;
  }
  list.innerHTML = days.map((d) => {
    const dt = new Date(d.date + "T12:00:00");
    const bits = [
      d.weight != null && `<span><b>${d.weight}</b> kg</span>`,
      d.protein != null && `<span><b>${d.protein}</b> g protein</span>`,
      d.water != null && `<span><b>${d.water}</b> L</span>`,
      d.steps != null && `<span><b>${d.steps.toLocaleString()}</b> steps</span>`,
      d.sleep != null && `<span><b>${d.sleep}</b> h sleep</span>`,
    ].filter(Boolean).join("");
    const trained = d.workout && !["Rest", "Skipped"].includes(d.workout);
    return `
      <button class="hrow" data-date="${d.date}">
        <span class="hdate">${dt.getDate()} ${dt.toLocaleString("en", { month: "short" })}<small>${DAYS[dt.getDay()]}</small></span>
        <span class="hmeta">${bits || "<span>Notes only</span>"}</span>
        ${d.workout ? `<span class="tag ${trained ? "done" : ""}">${esc(d.workout)}</span>` : "<span></span>"}
      </button>`;
  }).join("");
}

// ---------- PLAN ----------
async function loadPlan() {
  const p = await api("/api/plan");
  const t = p.targets;
  $("#targets").innerHTML = [
    [t.calories.toLocaleString(), "kcal"], [t.protein, "g protein"], [t.water + " L", "water"],
    [t.steps >= 1000 ? +(t.steps / 1000).toFixed(1) + "k" : t.steps, "steps"], [t.sleep + " h", "sleep"],
  ].map(([v, l]) => `<div class="target"><b>${v}</b><span>${l}</span></div>`).join("");

  const todayIdx = (new Date(state.date + "T12:00:00").getDay() + 6) % 7;
  $("#split").innerHTML = p.split.map((s, i) => `
    <div class="srow ${i === todayIdx ? "today" : ""}">
      <span class="d">${s.day}</span><span class="n">${esc(s.name)}</span><span class="e">${s.exercises.map(esc).join(" · ")}</span>
    </div>`).join("");

  const total = p.menu.reduce((a, m) => a + m.protein, 0);
  $("#menu").innerHTML = p.menu.length
    ? p.menu.map((m) => `<div class="mrow"><div><b>${esc(m.meal)}</b>${esc(m.food)}</div><span class="p">${m.protein} g</span></div>`).join("")
      + `<div class="mrow"><b>Total</b><span class="p">≈ ${total} g protein</span></div>`
    : `<p class="muted">No meals yet. Tap Edit plan to add some.</p>`;
  $("#rules").innerHTML = p.rules.map((r) => `<li>${esc(r)}</li>`).join("");
  setPlanEditing(false);
}

function setPlanEditing(on) {
  $("#planView").hidden = on;
  $("#planEdit").hidden = !on;
  $("#editPlan").hidden = on;
  if (on) fillPlanEditor();
}

function mealRow(m = { meal: "", food: "", protein: 0 }) {
  return `<div class="mealrow">
    <input name="meal" placeholder="Meal" maxlength="30" value="${esc(m.meal)}" required>
    <input name="food" placeholder="What you eat" maxlength="200" value="${esc(m.food)}">
    <input name="mprotein" type="number" min="0" max="200" placeholder="g" value="${m.protein}" aria-label="Protein grams">
    <button type="button" class="icon-btn" data-remove aria-label="Remove meal">&times;</button>
  </div>`;
}

function fillPlanEditor() {
  const s = state.user.settings;
  for (const [k, v] of Object.entries(s.targets)) $(`#targetInputs [name=${k}]`).value = v;
  $("#splitInputs").innerHTML = s.split.map((d, i) => `
    <div class="sday">
      <b>${WEEK[i]}</b>
      <input name="dname" maxlength="30" value="${esc(d.name)}" required aria-label="${WEEK[i]} name">
      <textarea name="dex" rows="${Math.max(2, d.exercises.length + 1)}" aria-label="${WEEK[i]} exercises">${esc(d.exercises.join("\n"))}</textarea>
    </div>`).join("");
  $("#menuInputs").innerHTML = s.menu.map(mealRow).join("");
}

function readPlanEditor() {
  const targets = {};
  for (const el of $("#targetInputs").querySelectorAll("input")) targets[el.name] = Number(el.value);
  const split = [...$("#splitInputs").querySelectorAll(".sday")].map((row) => ({
    name: row.querySelector("[name=dname]").value.trim(),
    exercises: row.querySelector("[name=dex]").value.split("\n").map((l) => l.trim()).filter(Boolean),
  }));
  const menu = [...$("#menuInputs").querySelectorAll(".mealrow")].map((row) => ({
    meal: row.querySelector("[name=meal]").value.trim(),
    food: row.querySelector("[name=food]").value.trim(),
    protein: Number(row.querySelector("[name=mprotein]").value) || 0,
  }));
  return { targets, split, menu };
}

$("#editPlan").addEventListener("click", () => setPlanEditing(true));
$("#cancelPlan").addEventListener("click", () => setPlanEditing(false));
$("#addMeal").addEventListener("click", () => $("#menuInputs").insertAdjacentHTML("beforeend", mealRow()));
$("#menuInputs").addEventListener("click", (e) => e.target.closest("[data-remove]")?.parentElement.remove());
$("#planEdit").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    rememberUser(await api("/api/me", { method: "PUT", body: JSON.stringify({ settings: readPlanEditor() }) }));
    buildWorkoutOptions();
    toast("Plan saved");
    loadPlan();
  } catch (err) {
    toast(err.message);
  }
});

// ---------- ME ----------
function loadMe() {
  const u = state.user;
  $("#avatar").textContent = (u.name || "?").trim()[0].toUpperCase();
  $("#meName").textContent = u.name;
  $("#meEmail").textContent = u.email;
  $("#nameForm").elements.name.value = u.name;
  return Promise.resolve();
}

$("#nameForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    rememberUser(await api("/api/me", { method: "PUT", body: JSON.stringify({ name: e.target.elements.name.value }) }));
    loadMe();
    toast("Name saved");
  } catch (err) {
    toast(err.message);
  }
});

$("#logoutBtn").addEventListener("click", logout);

$("#deleteBtn").addEventListener("click", async () => {
  const password = prompt("This deletes your account and every record, forever.\nType your password to confirm:");
  if (!password) return;
  try {
    await api("/api/me/delete", { method: "POST", body: JSON.stringify({ password }) });
    logout();
    toast("Account deleted");
  } catch (err) {
    toast(err.message);
  }
});

$("#exportBtn").addEventListener("click", async () => {
  try {
    const backup = await api("/api/export");
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `fitlog-backup-${isoDate(new Date())}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    toast(`Downloaded ${backup.days.length} days`);
  } catch (err) {
    toast(err.message);
  }
});

$("#importFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    let backup;
    try {
      backup = JSON.parse(await file.text());
    } catch {
      throw new Error("That file is not a FitLog backup");
    }
    if (!Array.isArray(backup.days)) throw new Error("That file is not a FitLog backup");
    if (!confirm(`Restore ${backup.days.length} days? Days with the same date are replaced.`)) return;
    const res = await api("/api/import", { method: "POST", body: JSON.stringify({ days: backup.days }) });
    toast(`Restored ${res.imported} days`);
  } catch (err) {
    toast(err.message);
  }
});

// Install button (Chrome / Edge / Android show it; iPhone uses Share → Add to Home Screen)
let installEvent = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installEvent = e;
  $("#installBtn").hidden = false;
});
$("#installBtn").addEventListener("click", async () => {
  if (!installEvent) return;
  installEvent.prompt();
  await installEvent.userChoice;
  installEvent = null;
  $("#installBtn").hidden = true;
});

// ---------- navigation ----------
const loaders = { today: loadToday, history: loadHistory, plan: loadPlan, me: loadMe };

function show(view) {
  state.view = view;
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  $("#datenav").style.visibility = view === "today" ? "visible" : "hidden";
  window.scrollTo(0, 0);
  loaders[view]().catch((e) => toast(e.message));
}

function goTo(date) {
  state.date = date;
  show("today");
}

document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));
$("#prev").addEventListener("click", () => goTo(shiftDate(state.date, -1)));
$("#next").addEventListener("click", () => goTo(shiftDate(state.date, 1)));
$("#dateInput").addEventListener("change", (e) => e.target.value && goTo(e.target.value));

$("#dayForm").addEventListener("input", () => { renderRings(); scheduleSave(); });
$("#dayForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (await save()) toast("Day saved");
});
$("#clearDay").addEventListener("click", async () => {
  if (!confirm(`Delete everything logged for ${prettyDate(state.date)}?`)) return;
  try {
    await api(`/api/days/${state.date}`, { method: "DELETE" });
    toast("Day cleared");
    loadToday();
  } catch (err) {
    toast(err.message);
  }
});

$("#rings").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-add]");
  if (!btn) return;
  const input = $(`#dayForm [name=${btn.dataset.add}]`);
  input.value = +((Number(input.value) || 0) + Number(btn.dataset.amount)).toFixed(2);
  renderRings();
  scheduleSave();
});

$("#workoutChips").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-set]");
  if (!chip) return;
  const select = $("#workoutSelect");
  select.value = select.value === chip.dataset.set ? "" : chip.dataset.set;
  save();
});

$("#range").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  state.range = Number(b.dataset.days);
  $("#range").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  loadHistory().catch((err) => toast(err.message));
});

$("#historyList").addEventListener("click", (e) => {
  const row = e.target.closest("[data-date]");
  if (row) goTo(row.dataset.date);
});

// ---------- offline banner + installable app ----------
const updateOnline = () => ($("#offline").hidden = navigator.onLine);
window.addEventListener("online", updateOnline);
window.addEventListener("offline", updateOnline);
updateOnline();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

// ---------- start ----------
(async function boot() {
  if (!localStorage.getItem(TOKEN_KEY)) return showAuth();
  try {
    rememberUser(await api("/api/me"));
    showApp();
  } catch (err) {
    const cached = localStorage.getItem(USER_KEY);
    if (err.offline && cached) {
      state.user = JSON.parse(cached);
      showApp();
    } else if (localStorage.getItem(TOKEN_KEY)) {
      showAuth();
    }
  }
})();
