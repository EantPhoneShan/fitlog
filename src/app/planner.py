"""Builds a personal plan from the answers to the setup questions.

Everything here is plain arithmetic and lookup tables, so it is easy to read and test:
  1. calories: Mifflin-St Jeor BMR x activity, then adjusted for the goal
  2. macros: protein from body weight, 25 % fat, the rest carbs
  3. a weekly workout split matched to training days, equipment and goal
  4. a menu built from foods the person can eat and afford

It is general fitness guidance, not medical advice (the app says so on sign-up).
"""

import re
from datetime import date

GOALS = {
    "lose_fat": "Lose fat",
    "build_muscle": "Build muscle",
    "bodybuilder": "Bodybuilder physique",
    "strength": "Get stronger",
    "recomp": "Lose fat and build muscle",
    "get_fit": "Get fit and healthy",
    "maintain": "Maintain my weight",
}
ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "very": 1.725}
# calories vs maintenance, protein g per kg body weight
GOAL_CALORIES = {"lose_fat": -0.20, "build_muscle": 0.10, "bodybuilder": 0.12, "strength": 0.05,
                 "recomp": -0.10, "get_fit": 0.0, "maintain": 0.0}
GOAL_PROTEIN = {"lose_fat": 2.0, "build_muscle": 1.8, "bodybuilder": 2.2, "strength": 1.8,
                "recomp": 2.0, "get_fit": 1.6, "maintain": 1.6}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# which weekdays are training days (0 = Monday) for each number of sessions a week
TRAINING_DAYS = {2: [0, 3], 3: [0, 2, 4], 4: [0, 1, 3, 4], 5: [0, 1, 2, 4, 5], 6: [0, 1, 2, 3, 4, 5]}

# ---------- exercises: movement pattern -> (gym, dumbbells at home, bodyweight only) ----------
EXERCISES = {
    "squat": ("Barbell back squat", "Goblet squat", "Bodyweight squat (slow, 3 s down)"),
    "hinge": ("Romanian deadlift", "Dumbbell Romanian deadlift", "Single-leg hip hinge"),
    "lunge": ("Leg press", "Dumbbell reverse lunge", "Reverse lunge"),
    "single_leg": ("Bulgarian split squat", "Dumbbell Bulgarian split squat", "Bulgarian split squat"),
    "glute": ("Hip thrust", "Dumbbell hip thrust", "Glute bridge"),
    "hamstring": ("Lying leg curl", "Dumbbell leg curl", "Sliding hamstring curl"),
    "calf": ("Standing calf raise", "Dumbbell calf raise", "Single-leg calf raise"),
    "h_push": ("Barbell bench press", "Dumbbell floor press", "Push-up"),
    "incline_push": ("Incline dumbbell press", "Incline dumbbell press (on a bench or step)", "Feet-elevated push-up"),
    "v_push": ("Overhead press", "Seated dumbbell shoulder press", "Pike push-up"),
    "fly": ("Cable fly", "Dumbbell fly", "Wide push-up"),
    "lateral": ("Cable lateral raise", "Dumbbell lateral raise", "Lateral raise with water bottles"),
    "triceps": ("Triceps pushdown", "Overhead dumbbell triceps extension", "Bench dip"),
    "v_pull": ("Lat pulldown / pull-up", "Dumbbell pullover", "Pull-up or door-frame row"),
    "h_pull": ("Seated cable row", "One-arm dumbbell row", "Inverted row under a table"),
    "rear_delt": ("Face pull", "Dumbbell rear-delt fly", "Prone Y-T-W raise"),
    "biceps": ("EZ-bar curl", "Dumbbell curl", "Towel curl (isometric)"),
    "hammer": ("Cable hammer curl", "Hammer curl", "Backpack hammer curl"),
    "core": ("Cable crunch", "Weighted dead bug", "Dead bug"),
    "core2": ("Hanging knee raise", "Plank (40 s)", "Plank (40 s)"),
}
EQUIPMENT_INDEX = {"gym": 0, "dumbbells": 1, "bodyweight": 2}

# Each session type is an ordered list of patterns: the first ones matter most,
# so a short session simply drops the ones at the end.
SESSIONS = {
    "Full body A": ["squat", "h_push", "h_pull", "hinge", "lateral", "core", "biceps"],
    "Full body B": ["hinge", "incline_push", "v_pull", "lunge", "rear_delt", "triceps", "core2"],
    "Full body C": ["single_leg", "v_push", "h_pull", "glute", "fly", "hammer", "core"],
    "Push": ["h_push", "incline_push", "v_push", "lateral", "fly", "triceps", "core"],
    "Pull": ["v_pull", "h_pull", "rear_delt", "biceps", "hammer", "core2", "h_pull"],
    "Legs": ["squat", "hinge", "lunge", "hamstring", "calf", "core", "glute"],
    "Upper": ["h_push", "v_pull", "v_push", "h_pull", "lateral", "biceps", "triceps"],
    "Lower": ["squat", "hinge", "single_leg", "hamstring", "glute", "calf", "core2"],
}
SPLITS = {
    2: ["Full body A", "Full body B"],
    3: ["Full body A", "Full body B", "Full body C"],
    "3+": ["Push", "Pull", "Legs"],
    4: ["Upper", "Lower", "Upper", "Lower"],
    5: ["Push", "Pull", "Legs", "Upper", "Lower"],
    6: ["Push", "Pull", "Legs", "Push", "Pull", "Legs"],
}

# ---------- foods: name, serving, protein g, kcal, cost (1 cheap .. 3 pricey), tags, needs cooking ----------
PROTEINS = [
    ("Eggs", "3 eggs", 19, 215, 1, {"egg"}, True),
    ("Chicken breast", "150 g raw", 34, 180, 2, {"meat"}, True),
    ("Chicken thigh", "150 g raw, skinless", 28, 210, 1, {"meat"}, True),
    ("Canned tuna", "1 can (120 g drained)", 30, 140, 2, {"fish"}, False),
    ("Canned sardines", "1 can (110 g)", 22, 210, 1, {"fish"}, False),
    ("Firm tofu", "200 g", 24, 220, 1, {"soy"}, False),
    ("Tempeh", "120 g", 23, 230, 2, {"soy"}, True),
    ("White fish (tilapia)", "180 g raw", 34, 170, 2, {"fish"}, True),
    ("Salmon", "150 g raw", 30, 300, 3, {"fish"}, True),
    ("Shrimp", "180 g raw", 36, 180, 3, {"shellfish"}, True),
    ("Lean beef", "150 g raw", 32, 240, 3, {"meat", "beef"}, True),
    ("Pork loin", "150 g raw", 33, 210, 2, {"meat", "pork"}, True),
    ("Greek yogurt", "200 g", 20, 150, 2, {"dairy"}, False),
    ("Lentils or beans", "1 cup cooked", 17, 230, 1, set(), False),
    ("Whey protein shake", "1 scoop + water", 24, 120, 2, {"dairy"}, False),
    ("Soy milk + soy protein", "300 ml + 1 scoop", 30, 230, 2, {"soy"}, False),
    ("Cottage cheese", "200 g", 24, 200, 2, {"dairy"}, False),
]
CARBS = [
    ("Rice", "1 cup cooked", 4, 205, 1, set(), True),
    ("Oats", "60 g dry", 8, 230, 1, {"gluten"}, False),
    ("Wholegrain bread", "2 slices", 8, 200, 1, {"gluten"}, False),
    ("Potatoes", "300 g", 6, 230, 1, set(), True),
    ("Sweet potato", "250 g", 4, 215, 1, set(), True),
    ("Noodles", "1 cup cooked", 7, 220, 1, {"gluten"}, True),
    ("Banana", "1 large", 1, 120, 1, set(), False),
    ("Fruit (apple / orange / mango)", "1 cup", 1, 90, 1, set(), False),
]
EXTRAS = [
    ("Mixed vegetables", "2 cups", 4, 70, 1, set(), True),
    ("Salad + cucumber + tomato", "1 bowl", 2, 50, 1, set(), False),
    ("Milk", "250 ml", 8, 160, 1, {"dairy"}, False),
    ("Peanut butter", "1 tbsp", 4, 95, 1, {"nuts"}, False),
    ("Handful of nuts", "30 g", 6, 180, 2, {"nuts"}, False),
    ("Avocado", "half", 1, 120, 2, set(), False),
]
DIETS = {  # tags each diet type rules out
    "any": set(),
    "halal": {"pork"},
    "no_beef": {"beef"},
    "pescatarian": {"meat"},
    "vegetarian": {"meat", "fish", "shellfish"},
    "vegan": {"meat", "fish", "shellfish", "dairy", "egg"},
}
MEAL_NAMES = {2: ["Lunch", "Dinner"], 3: ["Breakfast", "Lunch", "Dinner"],
              4: ["Breakfast", "Lunch", "Snack", "Dinner"], 5: ["Breakfast", "Snack", "Lunch", "Snack 2", "Dinner"]}
BUDGET_MAX_COST = {"tight": 1, "moderate": 2, "flexible": 3}


def _r(value: float, step: float) -> float:
    return round(round(value / step) * step, 2)


def bmr(sex: str, weight: float, height: float, age: int) -> float:
    return 10 * weight + 6.25 * height - 5 * age + (5 if sex == "male" else -161)


def targets_for(p: dict) -> tuple[dict, list[str]]:
    """Daily targets plus plain-English notes about the goal and timeline."""
    notes = []
    maintenance = bmr(p["sex"], p["weight"], p["height"], p["age"]) * ACTIVITY[p["activity"]]
    calories = maintenance * (1 + GOAL_CALORIES[p["goal"]])

    target, weeks = p.get("target_weight"), p.get("weeks")
    if target and weeks:
        per_week = (target - p["weight"]) / weeks
        # at most 1 % of body weight a week down, or about 1 % a month up (faster gain is mostly fat)
        safe_loss, safe_gain = -0.01 * p["weight"], 0.0025 * p["weight"]
        if per_week < safe_loss or per_week > safe_gain:
            realistic = abs(target - p["weight"]) / (abs(safe_loss) if per_week < 0 else safe_gain)
            why = "is faster than is healthy" if per_week < 0 else "is faster than your body can build lean muscle"
            notes.append(f"Going from {p['weight']:g} to {target:g} kg in {weeks} weeks {why}. "
                         f"Plan on about {round(realistic)} weeks; the plan below uses the safe pace.")
            per_week = max(min(per_week, safe_gain), safe_loss)
        else:
            notes.append(f"{p['weight']:g} → {target:g} kg in {weeks} weeks means about "
                         f"{abs(per_week):.2f} kg a week. That's realistic.")
        # ~7700 kcal per kg of body weight change, spread over 7 days
        calories = maintenance + per_week * 7700 / 7

    floor = 1500 if p["sex"] == "male" else 1200
    if calories < floor:
        calories = floor
        notes.append(f"Calories are kept at {floor} at least, so you get enough food to train and recover.")
    calories = int(_r(calories, 50))

    protein_kg = min(p["weight"], target or p["weight"]) if p["goal"] in ("lose_fat", "recomp") else p["weight"]
    protein = int(min(_r(protein_kg * GOAL_PROTEIN[p["goal"]], 5), 250))
    fat = int(_r(calories * 0.25 / 9, 5))
    carbs = int(max(_r((calories - protein * 4 - fat * 9) / 4, 5), 50))
    water = min(max(_r(p["weight"] * 0.035, 0.25), 2.0), 5.0)
    steps = 8000 if p["goal"] in ("lose_fat", "recomp") else 7000
    if p["activity"] == "sedentary":
        steps -= 1000
    sleep = 8.0 if p["age"] < 18 else 7.5
    notes.append(f"Maintenance is about {int(_r(maintenance, 50))} kcal a day; your target is {calories} kcal.")
    return ({"calories": calories, "protein": protein, "carbs": carbs, "fat": fat,
             "water": water, "steps": steps, "sleep": sleep}, notes)


def split_for(p: dict) -> list[dict]:
    days = p["days"]
    names = SPLITS["3+"] if days == 3 and p["experience"] != "beginner" else SPLITS[days]
    eq = EQUIPMENT_INDEX[p["equipment"]]
    count = max(3, min(7, p["minutes"] // 10))
    sets = {"strength": "4 x 4-6", "bodybuilder": "4 x 8-12", "build_muscle": "3-4 x 8-12",
            "lose_fat": "3 x 10-15", "recomp": "3 x 8-12"}.get(p["goal"], "3 x 10-12")
    if p["experience"] == "beginner":
        sets = "3 x 8-12" if p["goal"] != "lose_fat" else "3 x 10-15"
    injury = (p.get("injuries") or "").strip()

    week = [None] * 7
    for slot, weekday in enumerate(TRAINING_DAYS[days]):
        name = names[slot]
        moves = [EXERCISES[m][eq] for m in SESSIONS[name][:count]]
        exercises = [f"{moves[0]}: {sets}"] + [f"{m}: 3 x 10-12" for m in moves[1:]]
        if p["goal"] in ("lose_fat", "recomp", "get_fit"):
            exercises.append("Finish: 10-15 min incline walk or bike")
        if injury:
            exercises.append(f"Careful with your {injury[:60]}: skip or swap anything that hurts")
        week[weekday] = {"name": name, "exercises": exercises}
    for i in range(7):
        if week[i] is None:
            week[i] = {"name": "Rest", "exercises": ["Rest day: easy walk for your step goal", "10 min stretching"]}
    week[6]["exercises"].append("Weekly check-in: weigh in and measure your waist")
    return week


def _allowed(item, banned: set, dislikes: list[str], max_cost: int, can_cook: bool) -> bool:
    name, _, _, _, cost, tags, cooking = item
    if tags & banned or cost > max_cost or (cooking and not can_cook):
        return False
    return not any(word in name.lower() for word in dislikes)


def menu_for(p: dict, targets: dict) -> list[dict]:
    banned = set(DIETS[p["diet"]]) | set(p.get("avoid") or [])
    dislikes = [w.strip().lower() for w in (p.get("dislikes") or "").replace(";", ",").split(",") if len(w.strip()) > 2]
    max_cost = BUDGET_MAX_COST[p["budget"]]
    can_cook = p["cooking"] != "none"

    def pick(pool):
        ok = [f for f in pool if _allowed(f, banned, dislikes, max_cost, can_cook)]
        if not ok:  # nothing fits the budget/cooking filter: relax those, never the diet or allergies
            ok = [f for f in pool if _allowed(f, banned, dislikes, 3, True)]
        return ok or [("Ask a dietitian", "-", 0, 0, 1, set(), False)]

    proteins, carbs, extras = pick(PROTEINS), pick(CARBS), pick(EXTRAS)
    veg = [e for e in extras if e[0] in ("Mixed vegetables", "Salad + cucumber + tomato")] or extras
    fruit = [c for c in carbs if c[0] in ("Banana", "Fruit (apple / orange / mango)")] or carbs
    staples = [c for c in carbs if c not in fruit] or carbs
    ready = [f for f in proteins if not f[6]] or proteins  # snacks shouldn't need cooking
    names = MEAL_NAMES[p["meals"]]
    # a snack is half a main meal, for both protein and calories
    shares = [0.5 if n.startswith("Snack") else 1 for n in names]
    used, menu = [], []
    half = lambda x: max(0.5, min(2.0, round(x * 2) / 2))  # noqa: E731 (portions in half servings)
    for i, meal in enumerate(names):
        snack = meal.startswith("Snack")
        share = shares[i] / sum(shares)
        pool = ready if snack else proteins
        prot = next((f for f in pool if f not in used), pool[i % len(pool)])  # no repeats while we can
        used.append(prot)
        sides = [fruit[i % len(fruit)]] if snack else [staples[i % len(staples)], veg[i % len(veg)]]
        side_protein = sum(s[2] for s in sides)
        servings = half((targets["protein"] * share - side_protein) / max(prot[2], 1))
        # the carb portion fills the meal up to its share of the day's calories
        room = targets["calories"] * share - prot[3] * servings - sum(s[3] for s in sides[1:])
        parts = [(prot, servings), (sides[0], half(room / sides[0][3]))] + [(s, 1) for s in sides[1:]]
        menu.append({
            "meal": meal,
            "food": " + ".join(f"{name} ({scale(serving, n)})" for (name, serving, *_), n in parts)[:200],
            "protein": int(sum(f[2] * n for f, n in parts)),
            "kcal": int(sum(f[3] * n for f, n in parts)),
        })
    return menu


def scale(serving: str, n: float) -> str:
    """'150 g raw' x 1.5 -> '225 g raw', '3 eggs' x 1.5 -> '5 eggs'."""
    if n == 1:
        return serving

    def num(m):
        v = float(m.group()) * n
        v = int(v / 5 + 0.5) * 5 if v >= 20 else int(v + 0.5) if v >= 3 else round(v * 2) / 2
        return f"{v:g}"

    return re.sub(r"\d+(\.\d+)?", num, serving)


def rules_for(p: dict) -> list[str]:
    rules = ["Judge progress by 7-day average weight, not one weigh-in.",
             "Add a rep or a little weight each week when you hit the top of the rep range.",
             "Hit your protein every day; it matters more than perfect meals."]
    if p["goal"] in ("lose_fat", "recomp"):
        rules += ["Losing 0.3-1 % of body weight a week is the sweet spot.",
                  "Flat for 2 weeks: cut 150 kcal or add 2,000 steps a day."]
    elif p["goal"] in ("build_muscle", "bodybuilder", "strength"):
        rules += ["Aim to gain about 0.25-0.5 kg a month (beginners a bit more).",
                  "Not gaining for 3 weeks: add 150 kcal a day."]
    else:
        rules.append("Stay within ±1 kg; move every day and sleep well.")
    rules.append("Take a lighter week every 6-8 weeks.")
    return rules


def build(p: dict) -> dict:
    """The answers in, a complete plan out (the same shape as the user's settings)."""
    targets, notes = targets_for(p)
    return {
        "targets": targets,
        "split": split_for(p),
        "menu": menu_for(p, targets),
        "rules": rules_for(p),
        "notes": notes,
        "goal": GOALS[p["goal"]],
        "plan_start": date.today().isoformat(),
    }
