"""Progress reports: "in your first month you lost 1.8 kg, trained 11 of 12 sessions...".

A report is made for the first week of a plan and then for every 30 days.
Reports are saved on the user, so they stay in the app until the user deletes them.
"""

from datetime import date as Date, datetime, timedelta, timezone

NOT_TRAINED = (None, "", "Rest", "Skipped")


def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


def periods(plan_start: Date, today: Date, months: int = 12) -> list[tuple[str, str, Date, Date]]:
    """Every finished period: (id, title, first day, last day)."""
    out = []
    week_end = plan_start + timedelta(days=6)
    if week_end < today:
        out.append(("week-1", "Your first week", plan_start, week_end))
    for n in range(1, months + 1):
        first = plan_start + timedelta(days=30 * (n - 1))
        last = first + timedelta(days=29)
        if last >= today:
            break
        out.append((f"month-{n}", f"Month {n} report", first, last))
    return out


def build_report(rid: str, title: str, first: Date, last: Date, days: list[dict], settings: dict) -> dict | None:
    days = [d for d in days if first.isoformat() <= d["date"] <= last.isoformat()]
    if len(days) < 3:
        return None  # too little data to say anything useful
    targets, split = settings["targets"], settings["split"]
    length = (last - first).days + 1

    weights = [d["weight"] for d in days if d.get("weight")]
    start_w, end_w = (round(sum(w) / len(w), 1) if w else None for w in (weights[:3], weights[-3:]))
    change = round(end_w - start_w, 1) if len(weights) >= 4 else None
    waists = [d["waist"] for d in days if d.get("waist")]
    waist_change = round(waists[-1] - waists[0], 1) if len(waists) >= 2 else None

    planned = sum(1 for i in range(length)
                  if split[(first + timedelta(days=i)).weekday()]["name"].strip().lower() != "rest")
    trained = sum(1 for d in days if d.get("workout") not in NOT_TRAINED)
    protein_days = sum(1 for d in days if d.get("protein") and d["protein"] >= 0.9 * targets["protein"])
    stats = {
        "days_logged": len(days),
        "days_in_period": length,
        "weight_start": start_w,
        "weight_end": end_w,
        "weight_change": change,
        "waist_change": waist_change,
        "workouts_done": trained,
        "workouts_planned": planned,
        "protein_days": protein_days,
        "avg_protein": _avg([d["protein"] for d in days if d.get("protein")]),
        "avg_steps": _avg([d["steps"] for d in days if d.get("steps")]),
        "avg_sleep": _avg([d["sleep"] for d in days if d.get("sleep")]),
        "avg_water": _avg([d["water"] for d in days if d.get("water")]),
    }

    highlights, advice = [], []
    goal = settings.get("goal", "")
    if change is not None:
        direction = "lost" if change < 0 else "gained"
        highlights.append(f"You {direction} {abs(change):g} kg ({start_w:g} → {end_w:g} kg)." if change else
                          f"Your weight held steady at about {end_w:g} kg.")
        weekly = change / (length / 7)
        if "Lose" in goal:
            if weekly > -0.1:
                advice.append("Weight is not dropping yet. Cut about 150 kcal a day or add 2,000 steps.")
            elif weekly < -1.0:
                advice.append("You're losing fast. Eat a little more to protect your muscle.")
        elif "muscle" in goal or "Bodybuilder" in goal or "stronger" in goal:
            if weekly <= 0:
                advice.append("Weight isn't going up. Add about 150 kcal a day (an extra snack).")
            elif weekly > 0.5:
                advice.append("You're gaining quickly. Trim 100-150 kcal so it stays lean gain.")
    else:
        advice.append("Weigh yourself most mornings so the next report can show your weight trend.")
    if waist_change:
        highlights.append(f"Waist {'down' if waist_change < 0 else 'up'} {abs(waist_change):g} cm.")
    elif waist_change == 0:
        highlights.append("Waist unchanged.")
    if planned:
        highlights.append(f"Workouts: {trained} of {planned} planned sessions.")
        if trained < planned * 0.7:
            advice.append("You missed several sessions. Try fewer, shorter workouts you can always keep.")
    highlights.append(f"Protein target hit on {protein_days} of {length} days.")
    if protein_days < length * 0.6:
        advice.append("Protein was often short. Add a protein snack (yogurt, eggs, tuna, tofu or a shake).")
    if stats["avg_sleep"] and stats["avg_sleep"] < targets["sleep"] - 0.5:
        advice.append(f"Average sleep was {stats['avg_sleep']:g} h. More sleep helps recovery and appetite.")
    if not advice:
        advice.append("Great consistency. Keep the plan exactly as it is.")

    return {
        "id": rid,
        "title": title,
        "start": first.isoformat(),
        "end": last.isoformat(),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read": False,
        "stats": stats,
        "highlights": highlights,
        "advice": advice,
    }


def refresh(settings: dict, days: list[dict], today: Date) -> bool:
    """Adds any newly finished reports to settings. Returns True if something changed."""
    if not settings.get("plan_start"):
        return False
    made = set(settings.setdefault("report_ids", []))
    changed = False
    for rid, title, first, last in periods(Date.fromisoformat(settings["plan_start"]), today):
        if rid in made:
            continue
        report = build_report(rid, title, first, last, days, settings)
        if report:
            settings.setdefault("reports", []).insert(0, report)
            settings["report_ids"].append(rid)
            changed = True
    return changed


def so_far(settings: dict, days: list[dict], today: Date) -> dict | None:
    """Live numbers for the current 30-day block, shown before the report is ready."""
    if not settings.get("plan_start"):
        return None
    start = Date.fromisoformat(settings["plan_start"])
    block = max(0, (today - start).days) // 30
    first = start + timedelta(days=30 * block)
    report = build_report("live", f"Month {block + 1} so far", first, today, days, settings)
    if report:
        report["days_left"] = 30 - ((today - first).days + 1)
    return report
