"""ForgeTrack API: the "backend" of the app.

Run locally (from the src folder):   uvicorn app.main:app --reload
Then open http://127.0.0.1:8000 in your browser. API docs: http://127.0.0.1:8000/docs
"""

import csv
import io
import os
import re
import uuid
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

from . import auth, insights, plan, planner
from .storage import FIELDS, get_store

app = FastAPI(title="ForgeTrack API", version="3.0")
store = get_store()

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Checked when the email doesn't exist, so a wrong email and a wrong password take the same time
DUMMY_HASH = auth.hash_password("not-a-real-password")
MIN_AGE = 16


def env_list(name: str) -> list[str]:
    return [v.strip().lower() for v in os.environ.get(name, "").split(",") if v.strip()]


# ---------- data shapes (FastAPI checks every request against these) ----------
class DayIn(BaseModel):
    weight: float | None = Field(None, ge=30, le=250)
    steps: int | None = Field(None, ge=0, le=100_000)
    water: float | None = Field(None, ge=0, le=10)
    protein: int | None = Field(None, ge=0, le=400)
    sleep: float | None = Field(None, ge=0, le=24)
    workout: str | None = Field(None, max_length=40)
    waist: float | None = Field(None, ge=40, le=200)
    lifts: str | None = Field(None, max_length=2000)
    note: str | None = Field(None, max_length=2000)
    calories: int | None = Field(None, ge=0, le=10_000)
    done: str | None = Field(None, max_length=500)


class Targets(BaseModel):
    calories: int = Field(ge=800, le=6000)
    protein: int = Field(ge=0, le=400)
    carbs: int | None = Field(None, ge=0, le=1000)
    fat: int | None = Field(None, ge=0, le=400)
    water: float = Field(ge=0.5, le=10)
    steps: int = Field(ge=0, le=50_000)
    sleep: float = Field(ge=3, le=14)


class SplitDay(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    exercises: list[str] = Field(max_length=12)

    @field_validator("exercises")
    @classmethod
    def clean(cls, items):
        return [i.strip()[:150] for i in items if i.strip()]


class Meal(BaseModel):
    meal: str = Field(min_length=1, max_length=30)
    food: str = Field(max_length=200)
    protein: int = Field(ge=0, le=200)
    kcal: int | None = Field(None, ge=0, le=3000)


class Settings(BaseModel):
    targets: Targets
    split: list[SplitDay] = Field(min_length=7, max_length=7)
    menu: list[Meal] = Field(max_length=10)


class Answers(BaseModel):
    """The setup questions. The plan is built from these."""
    goal: Literal[tuple(planner.GOALS)]
    sex: Literal["male", "female"]
    age: int = Field(ge=10, le=90)
    height: float = Field(ge=120, le=230)
    weight: float = Field(ge=30, le=250)
    target_weight: float | None = Field(None, ge=30, le=250)
    weeks: int | None = Field(None, ge=2, le=104)
    activity: Literal[tuple(planner.ACTIVITY)]
    experience: Literal["beginner", "intermediate", "advanced"]
    days: int = Field(ge=2, le=6)
    minutes: int = Field(ge=20, le=120)
    equipment: Literal[tuple(planner.EQUIPMENT_INDEX)]
    injuries: str | None = Field(None, max_length=100)
    diet: Literal[tuple(planner.DIETS)]
    avoid: list[Literal["pork", "beef", "dairy", "egg", "fish", "shellfish", "nuts", "gluten", "soy"]] = Field(
        default_factory=list, max_length=9)
    dislikes: str | None = Field(None, max_length=200)
    meals: int = Field(ge=2, le=5)
    cooking: Literal["none", "basic", "good"]
    budget: Literal[tuple(planner.BUDGET_MAX_COST)]
    budget_amount: float | None = Field(None, ge=0, le=10_000_000)
    currency: str | None = Field(None, max_length=8)
    sleep_now: float | None = Field(None, ge=0, le=16)
    extra: str | None = Field(None, max_length=300)


class SignUp(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=200)
    code: str | None = None
    consent: bool = False


class LogIn(BaseModel):
    email: str
    password: str


class GoogleLogIn(BaseModel):
    credential: str = Field(max_length=5000)
    consent: bool = False
    code: str | None = None


class Profile(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=40)
    settings: Settings | None = None


class DeleteAccount(BaseModel):
    password: str | None = None
    confirm: str | None = None


class Backup(BaseModel):
    days: list[dict]


# ---------- helpers ----------
def parse_date(value: str) -> Date:
    try:
        return Date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must look like 2026-10-12")


def avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_admin(user: dict) -> bool:
    return user["email"] in env_list("ADMIN_EMAILS")


def public(user: dict) -> dict:
    """What the browser may see about a user (never the password hash)."""
    s = user["settings"]
    return {
        "name": user["name"],
        "email": user["email"],
        "provider": "email" if user["password_hash"] else "google",
        "onboarded": bool(s.get("profile")),
        "is_admin": is_admin(user),
        "settings": {k: s[k] for k in ("targets", "split", "menu") if k in s},
        "profile": s.get("profile"),
    }


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Every private endpoint uses this: no valid token, no data."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    payload = auth.read_token(token) if token else None
    user = store.get_user_by_email(payload["email"]) if payload else None
    if not user or user["id"] != payload["uid"]:
        raise HTTPException(status_code=401, detail="Please log in")
    return user


def check_invite(code: str | None) -> None:
    expected = os.environ.get("SIGNUP_CODE")
    if expected and code != expected:
        raise HTTPException(status_code=403, detail="Wrong invite code")


def new_user(email: str, name: str, password_hash: str) -> dict:
    first_user = store.count_users() == 0
    settings = plan.default_settings()
    settings["consent_at"] = now()
    user = {"id": uuid.uuid4().hex, "email": email, "name": name[:40], "password_hash": password_hash,
            "settings": settings, "created": now()}
    store.create_user(user)
    if first_user:
        store.claim_legacy(user["id"])  # records logged before accounts existed
    return user


# ---------- accounts ----------
@app.get("/api/health")
def health():
    return {"ok": True, "storage": type(store).__name__}


@app.get("/api/config")
def config():
    return {
        "signup_code_required": bool(os.environ.get("SIGNUP_CODE")),
        "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "contact_email": os.environ.get("CONTACT_EMAIL", ""),
        "min_age": MIN_AGE,
    }


@app.post("/api/auth/signup")
def signup(body: SignUp):
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(status_code=400, detail="That email doesn't look right")
    check_invite(body.code)
    if not body.consent:
        raise HTTPException(status_code=400, detail="Please accept the Terms and Privacy Policy to continue")
    if store.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with that email already exists. Log in instead.")
    user = new_user(email, body.name.strip(), auth.hash_password(body.password))
    return {"token": auth.make_token(user), "user": public(user)}


@app.post("/api/auth/login")
def login(body: LogIn):
    user = store.get_user_by_email(body.email.strip().lower())
    ok = auth.check_password(body.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not ok:
        if user and not user["password_hash"]:
            raise HTTPException(status_code=401, detail="This account uses Google. Tap “Continue with Google”.")
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return {"token": auth.make_token(user), "user": public(user)}


@app.post("/api/auth/google")
def google_login(body: GoogleLogIn):
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=400, detail="Google sign-in is not set up yet")
    claims = auth.verify_google(body.credential, client_id)
    if not claims:
        raise HTTPException(status_code=401, detail="Google sign-in failed. Please try again.")
    email = claims["email"].strip().lower()
    user = store.get_user_by_email(email)
    if not user:
        check_invite(body.code)
        if not body.consent:
            # the app asks for consent, then sends the same credential again
            raise HTTPException(status_code=428, detail="consent_required")
        user = new_user(email, claims.get("given_name") or claims.get("name") or email.split("@")[0], "")
    return {"token": auth.make_token(user), "user": public(user)}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return public(user)


@app.put("/api/me")
def update_me(body: Profile, user: dict = Depends(current_user)):
    if body.name:
        user["name"] = body.name.strip()
    if body.settings:
        user["settings"].update(body.settings.model_dump())  # keeps profile, reports, notes
    store.update_user(user)
    return public(user)


@app.post("/api/me/delete")
def delete_me(body: DeleteAccount, user: dict = Depends(current_user)):
    if user["password_hash"]:
        if not auth.check_password(body.password or "", user["password_hash"]):
            raise HTTPException(status_code=403, detail="Wrong password")
    elif (body.confirm or "").strip().upper() != "DELETE":
        raise HTTPException(status_code=403, detail="Type DELETE to confirm")
    store.delete_user(user)
    return {"deleted": True}


# ---------- setup questions -> personal plan ----------
@app.post("/api/onboarding")
def onboarding(answers: Answers, user: dict = Depends(current_user)):
    if answers.age < MIN_AGE:
        raise HTTPException(status_code=400, detail=f"ForgeTrack is for people aged {MIN_AGE} and over.")
    profile = answers.model_dump()
    built = planner.build(profile)
    settings = user["settings"]
    if settings.get("profile") and settings.get("plan_start"):
        built["plan_start"] = settings["plan_start"]  # rebuilding keeps report history in step
    settings.update(built)
    settings["profile"] = {**profile, "answered": now()}
    store.update_user(user)
    return {"user": public(user), "plan": get_plan(user)}


@app.get("/api/plan")
def get_plan(user: dict = Depends(current_user)):
    s = user["settings"]
    split = [{"day": plan.WEEKDAYS[i], **s["split"][i]} for i in range(7)]
    return {"targets": s["targets"], "split": split, "menu": s["menu"], "rules": s.get("rules", plan.RULES),
            "notes": s.get("notes", []), "goal": s.get("goal"), "plan_start": s.get("plan_start")}


# ---------- daily log ----------
@app.get("/api/days")
def list_days(start: str = "2000-01-01", end: str = "2100-01-01", user: dict = Depends(current_user)):
    parse_date(start), parse_date(end)
    return store.list(user["id"], start, end)


@app.get("/api/days/{day}")
def get_day(day: str, user: dict = Depends(current_user)):
    parse_date(day)
    found = store.get(user["id"], day)
    if not found:
        raise HTTPException(status_code=404, detail="No entry for that day")
    return found


@app.put("/api/days/{day}")
def save_day(day: str, body: DayIn, user: dict = Depends(current_user)):
    parse_date(day)
    return store.put(user["id"], day, body.model_dump())


@app.delete("/api/days/{day}")
def delete_day(day: str, user: dict = Depends(current_user)):
    parse_date(day)
    store.delete(user["id"], day)
    return {"deleted": day}


@app.get("/api/export")
def export_days(user: dict = Depends(current_user)):
    """Every record as one JSON file: a backup, or a way to move between laptop and cloud."""
    return {"app": "forgetrack", "version": 3, "days": store.list(user["id"], "2000-01-01", "2100-01-01")}


@app.post("/api/import")
def import_days(backup: Backup, user: dict = Depends(current_user)):
    if len(backup.days) > 5000:
        raise HTTPException(status_code=400, detail="Backup is too big")
    clean = []
    for raw in backup.days:
        day = str(raw.get("date", ""))
        parse_date(day)
        try:
            clean.append((day, DayIn(**{k: v for k, v in raw.items() if k != "date"})))
        except ValidationError:
            raise HTTPException(status_code=400, detail=f"Bad values on {day}, nothing was imported")
    for day, data in clean:
        store.put(user["id"], day, data.model_dump())
    return {"imported": len(clean)}


def daily_tasks(settings: dict, entry: dict, weekday: int) -> list[dict]:
    """Today's checklist. Number goals tick themselves when the log reaches the target."""
    t, done = settings["targets"], set((entry.get("done") or "").split(","))
    w = settings["split"][weekday]
    rest = w["name"].strip().lower() == "rest"
    trained = entry.get("workout") not in (None, "", "Rest", "Skipped")
    tasks = [{"id": "workout", "label": "Rest and recover" if rest else f"{w['name']} workout",
              "detail": w["exercises"][0] if w["exercises"] else "", "done": "workout" in done or (trained and not rest)}]
    for i, m in enumerate(settings["menu"]):
        tasks.append({"id": f"meal-{i}", "label": m["meal"], "detail": m["food"], "done": f"meal-{i}" in done})
    for key, label, unit in (("protein", "Protein", "g"), ("water", "Water", "L"), ("steps", "Steps", ""),
                             ("sleep", "Sleep", "h")):
        value = entry.get(key) or 0
        goal = t[key]
        num = (lambda n: f"{n:,}") if key == "steps" else (lambda n: f"{n:g}")
        tasks.append({"id": key, "label": f"{label} {num(goal)}{unit and ' ' + unit}", "auto": True,
                      "detail": f"{num(value)} so far", "done": value >= goal})
    return tasks


@app.get("/api/summary")
def summary(day: str | None = None, user: dict = Depends(current_user)):
    """Everything the home screen needs in one call."""
    today = parse_date(day) if day else Date.today()
    history = store.list(user["id"], (today - timedelta(days=59)).isoformat(), today.isoformat())
    by_date = {d["date"]: d for d in history}
    settings = user["settings"]

    def weights(first: int, last: int):
        # weights from `first` to `last` days ago (inclusive)
        out = []
        for back in range(first, last + 1):
            d = by_date.get((today - timedelta(days=back)).isoformat())
            if d and d.get("weight"):
                out.append(d["weight"])
        return out

    this_week, last_week = avg(weights(0, 6)), avg(weights(7, 13))
    change = round(this_week - last_week, 2) if this_week and last_week else None
    gaining = any(word in (settings.get("goal") or "") for word in ("muscle", "Bodybuilder", "stronger"))
    if change is None:
        advice = "Log your weight most mornings. Trend advice starts after 2 weeks."
    elif gaining and "Lose" not in (settings.get("goal") or ""):
        advice = ("Gaining a little each week. Right on track." if 0.05 <= change <= 0.5 else
                  "Not gaining. Add about 150 kcal a day." if change < 0.05 else
                  "Gaining fast. Trim 100-150 kcal to keep it lean.")
    elif change < -1.0:
        advice = "Dropping over 1 kg a week. Eat a bit more to keep your muscle."
    elif change <= -0.2:
        advice = "Right on track. Keep going."
    else:
        advice = "Weight is flat. If it stays flat next week, cut 150-200 kcal or add a 10-min incline walk."

    streak = 0
    while (today - timedelta(days=streak)).isoformat() in by_date:
        streak += 1

    week_start = today - timedelta(days=today.weekday())
    trained = [d for d in history if d["date"] >= week_start.isoformat() and d.get("workout") not in insights.NOT_TRAINED]
    entry = by_date.get(today.isoformat())

    return {
        "date": today.isoformat(),
        "name": user["name"],
        "entry": entry,
        "workout": settings["split"][today.weekday()],
        "targets": settings["targets"],
        "tasks": daily_tasks(settings, entry or {}, today.weekday()),
        "weight_avg_7d": this_week,
        "weight_avg_prev_7d": last_week,
        "weekly_change": change,
        "advice": advice,
        "streak": streak,
        "sessions_this_week": len(trained),
        "unread_reports": sum(1 for r in settings.get("reports", []) if not r.get("read")),
    }


# ---------- progress reports ----------
@app.get("/api/reports")
def reports(day: str | None = None, user: dict = Depends(current_user)):
    today = parse_date(day) if day else Date.today()
    s = user["settings"]
    days = store.list(user["id"], s.get("plan_start") or "2000-01-01", today.isoformat())
    if insights.refresh(s, days, today):
        store.update_user(user)
    return {"reports": s.get("reports", []), "live": insights.so_far(s, days, today)}


@app.post("/api/reports/{rid}/read")
def read_report(rid: str, user: dict = Depends(current_user)):
    for r in user["settings"].get("reports", []):
        if r["id"] == rid:
            r["read"] = True
    store.update_user(user)
    return {"ok": True}


@app.delete("/api/reports/{rid}")
def delete_report(rid: str, user: dict = Depends(current_user)):
    s = user["settings"]
    s["reports"] = [r for r in s.get("reports", []) if r["id"] != rid]
    store.update_user(user)
    return {"deleted": rid}


# ---------- owner tools (only emails listed in ADMIN_EMAILS) ----------
def admin_user(user: dict = Depends(current_user)) -> dict:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Owner only")
    return user


PROFILE_COLUMNS = ["goal", "sex", "age", "height", "weight", "target_weight", "weeks", "activity", "experience",
                   "days", "minutes", "equipment", "injuries", "diet", "avoid", "dislikes", "meals", "cooking",
                   "budget", "budget_amount", "currency", "sleep_now", "extra"]


@app.get("/api/admin/users")
def admin_users(_: dict = Depends(admin_user)):
    out = []
    for u in store.list_users():
        days = store.list(u["id"], "2000-01-01", "2100-01-01")
        weights = [d["weight"] for d in days if d.get("weight")]
        out.append({
            "name": u["name"], "email": u["email"], "created": u["created"],
            "provider": "email" if u["password_hash"] else "google",
            "goal": u["settings"].get("goal"), "profile": u["settings"].get("profile"),
            "targets": u["settings"]["targets"], "days_logged": len(days),
            "last_log": days[-1]["date"] if days else None,
            "first_weight": weights[0] if weights else None, "last_weight": weights[-1] if weights else None,
        })
    return out


@app.get("/api/admin/export.csv")
def admin_export(_: dict = Depends(admin_user)):
    """One row per user per logged day, with their setup answers, ready for Excel / Google Sheets."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "name", "joined", *PROFILE_COLUMNS, "date", *FIELDS])
    for u in store.list_users():
        p = u["settings"].get("profile") or {}
        info = [u["email"], u["name"], u["created"][:10],
                *[",".join(p[c]) if isinstance(p.get(c), list) else p.get(c, "") for c in PROFILE_COLUMNS]]
        days = store.list(u["id"], "2000-01-01", "2100-01-01") or [{"date": ""}]
        for d in days:
            writer.writerow([*info, d["date"], *[d.get(f, "") for f in FIELDS]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=forgetrack-users.csv"})


# ---------- Android app link (lets the Play Store app open this site full screen) ----------
@app.get("/.well-known/assetlinks.json")
def assetlinks():
    package, fingerprints = os.environ.get("ANDROID_PACKAGE"), env_list("ANDROID_CERT_SHA256")
    if not package or not fingerprints:
        return JSONResponse([])
    return JSONResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {"namespace": "android_app", "package_name": package,
                   "sha256_cert_fingerprints": [f.upper() for f in fingerprints]},
    }])


# The web app (HTML/CSS/JS) is served from the same place as the API.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")

# AWS Lambda entry point. Mangum translates Lambda events into normal web requests.
try:
    from mangum import Mangum

    handler = Mangum(app)
except ImportError:  # not needed when running locally
    handler = None
