// ForgeTrack setup questions: a short step-by-step form. The answers go to /api/onboarding,
// which builds the person's plan. Uses $, api, esc and toast from app.js.

const CURRENCIES = ["USD", "THB", "MMK", "SGD", "MYR", "IDR", "PHP", "VND", "INR", "EUR", "GBP", "AUD", "JPY", "KRW", "CNY"];

const STEPS = [
  {
    title: "What's your goal?",
    sub: "Pick the one that matters most right now. You can change it later.",
    fields: [{ name: "goal", type: "cards", options: [
      ["lose_fat", "Lose fat", "Get leaner and lighter"],
      ["build_muscle", "Build muscle", "Get bigger and stronger"],
      ["bodybuilder", "Bodybuilder look", "Maximum muscle, aesthetic physique"],
      ["recomp", "Lose fat + build muscle", "Change shape at about the same weight"],
      ["strength", "Get stronger", "Lift heavier"],
      ["get_fit", "Get fit and healthy", "More energy, better fitness"],
      ["maintain", "Maintain", "Keep my weight, stay in shape"],
    ] }],
  },
  {
    title: "About you",
    sub: "We use these to work out your calories. Only you and the app owner can see them.",
    fields: [
      { name: "sex", label: "Sex", type: "seg", options: [["male", "Male"], ["female", "Female"]] },
      { name: "age", label: "Age", type: "number", min: 10, max: 90, unit: "years" },
      { name: "height", label: "Height", type: "number", min: 120, max: 230, step: 0.5, unit: "cm" },
      { name: "weight", label: "Weight now", type: "number", min: 30, max: 250, step: 0.1, unit: "kg" },
    ],
  },
  {
    title: "Your target",
    sub: "Optional. Leave empty if you just want to improve.",
    fields: [
      { name: "target_weight", label: "Target weight", type: "number", min: 30, max: 250, step: 0.1, unit: "kg", optional: true },
      { name: "weeks", label: "In how many weeks?", type: "number", min: 2, max: 104, unit: "weeks", optional: true },
    ],
  },
  {
    title: "Your daily life",
    fields: [
      { name: "activity", label: "How active are you outside the gym?", type: "cards", options: [
        ["sedentary", "Mostly sitting", "Desk job, little walking"],
        ["light", "Lightly active", "Some walking, on my feet a bit"],
        ["moderate", "Active", "On my feet most of the day"],
        ["very", "Very active", "Physical job or lots of sport"],
      ] },
      { name: "sleep_now", label: "Hours you usually sleep", type: "number", min: 0, max: 16, step: 0.5, unit: "h", optional: true },
    ],
  },
  {
    title: "Training",
    fields: [
      { name: "experience", label: "Experience", type: "seg", options: [["beginner", "New"], ["intermediate", "1-3 years"], ["advanced", "3+ years"]] },
      { name: "days", label: "Days a week you can train", type: "seg", options: [[2, "2"], [3, "3"], [4, "4"], [5, "5"], [6, "6"]] },
      { name: "minutes", label: "Minutes per session", type: "seg", options: [[30, "30"], [45, "45"], [60, "60"], [75, "75"], [90, "90"]] },
      { name: "equipment", label: "Where do you train?", type: "cards", options: [
        ["gym", "Gym", "Machines, barbells, dumbbells"],
        ["dumbbells", "Home with dumbbells", "A pair of dumbbells or a bench"],
        ["bodyweight", "No equipment", "Bodyweight only"],
      ] },
      { name: "injuries", label: "Any injuries or pain?", type: "text", placeholder: "e.g. lower back, left knee (optional)", optional: true, max: 100 },
    ],
  },
  {
    title: "Food",
    sub: "Your meal plan only uses foods you can eat.",
    fields: [
      { name: "diet", label: "Diet", type: "seg", options: [["any", "Anything"], ["halal", "Halal"], ["no_beef", "No beef"], ["pescatarian", "Pescatarian"], ["vegetarian", "Vegetarian"], ["vegan", "Vegan"]] },
      { name: "avoid", label: "Allergies / can't eat", type: "multi", optional: true, options: [["pork", "Pork"], ["beef", "Beef"], ["dairy", "Dairy"], ["egg", "Eggs"], ["fish", "Fish"], ["shellfish", "Shellfish"], ["nuts", "Nuts"], ["gluten", "Gluten"], ["soy", "Soy"]] },
      { name: "dislikes", label: "Foods you don't like", type: "text", placeholder: "e.g. tuna, oats (optional)", optional: true, max: 200 },
      { name: "meals", label: "Meals a day", type: "seg", options: [[2, "2"], [3, "3"], [4, "4"], [5, "5"]] },
      { name: "cooking", label: "Cooking", type: "seg", options: [["none", "I don't cook"], ["basic", "Simple meals"], ["good", "I like cooking"]] },
    ],
  },
  {
    title: "Food budget",
    sub: "We pick cheaper foods for tighter budgets.",
    fields: [
      { name: "budget", label: "Your budget", type: "cards", options: [
        ["tight", "Tight", "Cheapest foods: eggs, rice, tofu, beans, chicken thigh"],
        ["moderate", "Moderate", "Adds chicken breast, yogurt, tuna, whey"],
        ["flexible", "Flexible", "Adds salmon, shrimp, beef"],
      ] },
      { name: "budget_amount", label: "Roughly how much per day? (optional)", type: "money", optional: true },
      { name: "extra", label: "Anything else we should know?", type: "textarea", placeholder: "Optional", optional: true, max: 300 },
    ],
  },
];

const onboard = { step: 0, answers: {}, done: null };

function startOnboarding(existing, done) {
  onboard.step = 0;
  onboard.answers = existing ? { ...existing } : { currency: "USD" };
  onboard.done = done;
  $("#auth").hidden = true;
  $("#app").hidden = true;
  $("#onboard").hidden = false;
  $("#planReady").hidden = true;
  $("#stepForm").hidden = false;
  renderStep();
}

function fieldHtml(f) {
  const v = onboard.answers[f.name];
  const label = f.label ? `<em class="lt">${f.label}${f.unit ? ` <span>${f.unit}</span>` : ""}</em>` : "";
  switch (f.type) {
    case "cards":
      return `<div class="field">${label}<div class="cards">${f.options.map(([val, title, sub]) => `
        <button type="button" class="opt ${v === val ? "on" : ""}" data-field="${f.name}" data-value="${val}">
          <b>${title}</b><span>${sub}</span></button>`).join("")}</div></div>`;
    case "seg":
      return `<div class="field">${label}<div class="optrow">${f.options.map(([val, text]) => `
        <button type="button" class="chip ${v === val ? "on" : ""}" data-field="${f.name}" data-value="${val}">${text}</button>`).join("")}</div></div>`;
    case "multi": {
      const set = new Set(v || []);
      return `<div class="field">${label}<div class="optrow">${f.options.map(([val, text]) => `
        <button type="button" class="chip ${set.has(val) ? "on" : ""}" data-multi="${f.name}" data-value="${val}">${text}</button>`).join("")}</div></div>`;
    }
    case "money":
      return `<div class="field">${label}<div class="money">
        <input name="budget_amount" type="number" min="0" step="any" inputmode="decimal" value="${v ?? ""}" placeholder="Amount">
        <select name="currency">${CURRENCIES.map((c) => `<option ${onboard.answers.currency === c ? "selected" : ""}>${c}</option>`).join("")}</select>
      </div></div>`;
    case "textarea":
      return `<label>${label}<textarea name="${f.name}" rows="3" maxlength="${f.max}" placeholder="${f.placeholder || ""}">${esc(v ?? "")}</textarea></label>`;
    case "text":
      return `<label>${label}<input name="${f.name}" maxlength="${f.max}" placeholder="${f.placeholder || ""}" value="${esc(v ?? "")}"></label>`;
    default:
      return `<label>${label}<input name="${f.name}" type="number" inputmode="decimal" min="${f.min}" max="${f.max}" step="${f.step || 1}" value="${v ?? ""}"></label>`;
  }
}

function renderStep() {
  const s = STEPS[onboard.step];
  $("#stepCount").textContent = `Step ${onboard.step + 1} of ${STEPS.length}`;
  $("#stepBar").style.width = `${((onboard.step + 1) / STEPS.length) * 100}%`;
  $("#stepTitle").textContent = s.title;
  $("#stepSub").textContent = s.sub || "";
  $("#stepBody").innerHTML = s.fields.map(fieldHtml).join("");
  $("#stepError").textContent = "";
  $("#stepBack").style.visibility = onboard.step === 0 ? "hidden" : "visible";
  $("#stepNext").textContent = onboard.step === STEPS.length - 1 ? "Build my plan" : "Next";
  window.scrollTo(0, 0);
}

// read typed values into answers; returns an error message or ""
function collectStep() {
  for (const f of STEPS[onboard.step].fields) {
    if (["number", undefined, "text", "textarea", "money"].includes(f.type)) {
      const el = $(`#stepForm [name=${f.name}]`);
      const raw = el ? el.value.trim() : "";
      if (f.type === "money") onboard.answers.currency = $("#stepForm [name=currency]").value;
      if (raw === "") {
        delete onboard.answers[f.name];
      } else if (f.type === "text" || f.type === "textarea") {
        onboard.answers[f.name] = raw;
      } else {
        const n = Number(raw);
        const min = f.type === "money" ? 0 : f.min, max = f.type === "money" ? 1e7 : f.max;
        if (Number.isNaN(n) || n < min || n > max) return `${f.label || "Amount"} must be between ${min} and ${max}.`;
        onboard.answers[f.name] = n;
      }
    }
    if (!f.optional && (onboard.answers[f.name] === undefined || onboard.answers[f.name] === "")) {
      return `Please answer: ${f.label || STEPS[onboard.step].title}`;
    }
  }
  const a = onboard.answers;
  if (onboard.step === 1 && a.age < 16) return "ForgeTrack is for people aged 16 and over.";
  if (onboard.step === 2 && (a.target_weight == null) !== (a.weeks == null)) return "Fill in both the target weight and the weeks, or leave both empty.";
  return "";
}

$("#stepBody").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-field], [data-multi]");
  if (!btn) return;
  const raw = btn.dataset.value;
  const value = /^\d+$/.test(raw) ? Number(raw) : raw;
  if (btn.dataset.multi) {
    const set = new Set(onboard.answers[btn.dataset.multi] || []);
    set.has(value) ? set.delete(value) : set.add(value);
    onboard.answers[btn.dataset.multi] = [...set];
    btn.classList.toggle("on");
  } else {
    onboard.answers[btn.dataset.field] = value;
    btn.parentElement.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === btn));
  }
});

$("#stepBack").addEventListener("click", () => {
  collectStep();
  onboard.step = Math.max(0, onboard.step - 1);
  renderStep();
});

$("#stepForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = collectStep();
  if (error) {
    $("#stepError").textContent = error;
    return;
  }
  if (onboard.step < STEPS.length - 1) {
    onboard.step++;
    renderStep();
    return;
  }
  const btn = $("#stepNext");
  btn.disabled = true;
  btn.textContent = "Building your plan…";
  try {
    const { answered, ...answers } = onboard.answers;
    const res = await api("/api/onboarding", { method: "POST", body: JSON.stringify(answers) });
    showPlanReady(res);
  } catch (err) {
    $("#stepError").textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Build my plan";
  }
});

function showPlanReady(res) {
  const t = res.plan.targets;
  $("#stepForm").hidden = true;
  const box = $("#planReady");
  box.hidden = false;
  box.innerHTML = `
    <h1>Your plan is ready</h1>
    <p class="muted">${esc(res.plan.goal || "")}</p>
    <div class="targets">
      <div class="target"><b>${t.calories.toLocaleString()}</b><span>kcal / day</span></div>
      <div class="target"><b>${t.protein} g</b><span>protein</span></div>
      <div class="target"><b>${t.carbs ?? "–"} g</b><span>carbs</span></div>
      <div class="target"><b>${t.fat ?? "–"} g</b><span>fat</span></div>
    </div>
    <ul class="rules">${res.plan.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
    <p class="muted">Every day you'll get a checklist: your workout, your meals, protein, water, steps and sleep.
      After your first week and then every month, you'll get a progress report.</p>
    <p class="disclaimer">General fitness guidance, not medical advice. If you have a health condition, are pregnant or injured, check with a doctor first.</p>
    <button type="button" class="primary full" id="startBtn">Start</button>`;
  $("#startBtn").addEventListener("click", async () => {
    await askNotifications();
    $("#onboard").hidden = true;
    onboard.done(res.user);
  });
}
