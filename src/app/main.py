"""FitLog API: the "backend" of the app.

Run locally (from the src folder):   uvicorn app.main:app --reload
Then open http://127.0.0.1:8000 in your browser. API docs: http://127.0.0.1:8000/docs
"""

import os
import re
import uuid
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

from . import auth, plan
from .storage import get_store

app = FastAPI(title="FitLog API", version="2.0")
store = get_store()

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Checked when the email doesn't exist, so a wrong email and a wrong password take the same time
DUMMY_HASH = auth.hash_password("not-a-real-password")


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


class Targets(BaseModel):
    calories: int = Field(ge=800, le=6000)
    protein: int = Field(ge=0, le=400)
    water: float = Field(ge=0.5, le=10)
    steps: int = Field(ge=0, le=50_000)
    sleep: float = Field(ge=3, le=14)


class SplitDay(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    exercises: list[str] = Field(max_length=12)

    @field_validator("exercises")
    @classmethod
    def clean(cls, items):
        items = [i.strip()[:150] for i in items if i.strip()]
        return items


class Meal(BaseModel):
    meal: str = Field(min_length=1, max_length=30)
    food: str = Field(max_length=200)
    protein: int = Field(ge=0, le=200)


class Settings(BaseModel):
    targets: Targets
    split: list[SplitDay] = Field(min_length=7, max_length=7)
    menu: list[Meal] = Field(max_length=10)


class SignUp(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=200)
    code: str | None = None


class LogIn(BaseModel):
    email: str
    password: str


class Profile(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=40)
    settings: Settings | None = None


class DeleteAccount(BaseModel):
    password: str


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


def public(user: dict) -> dict:
    """What the browser may see about a user (never the password hash)."""
    return {"name": user["name"], "email": user["email"], "settings": user["settings"]}


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Every private endpoint uses this: no valid token, no data."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    payload = auth.read_token(token) if token else None
    user = store.get_user_by_email(payload["email"]) if payload else None
    if not user or user["id"] != payload["uid"]:
        raise HTTPException(status_code=401, detail="Please log in")
    return user


# ---------- accounts ----------
@app.get("/api/health")
def health():
    return {"ok": True, "storage": type(store).__name__}


@app.get("/api/config")
def config():
    return {"signup_code_required": bool(os.environ.get("SIGNUP_CODE"))}


@app.post("/api/auth/signup")
def signup(body: SignUp):
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(status_code=400, detail="That email doesn't look right")
    code = os.environ.get("SIGNUP_CODE")
    if code and body.code != code:
        raise HTTPException(status_code=403, detail="Wrong invite code")
    if store.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with that email already exists. Log in instead.")
    first_user = store.count_users() == 0
    user = {
        "id": uuid.uuid4().hex,
        "email": email,
        "name": body.name.strip(),
        "password_hash": auth.hash_password(body.password),
        "settings": plan.default_settings(),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    store.create_user(user)
    if first_user:
        store.claim_legacy(user["id"])  # records logged before accounts existed
    return {"token": auth.make_token(user), "user": public(user)}


@app.post("/api/auth/login")
def login(body: LogIn):
    user = store.get_user_by_email(body.email.strip().lower())
    ok = auth.check_password(body.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return {"token": auth.make_token(user), "user": public(user)}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return public(user)


@app.put("/api/me")
def update_me(body: Profile, user: dict = Depends(current_user)):
    if body.name:
        user["name"] = body.name.strip()
    if body.settings:
        user["settings"] = body.settings.model_dump()
    store.update_user(user)
    return public(user)


@app.post("/api/me/delete")
def delete_me(body: DeleteAccount, user: dict = Depends(current_user)):
    if not auth.check_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=403, detail="Wrong password")
    store.delete_user(user)
    return {"deleted": True}


# ---------- plan & daily log ----------
@app.get("/api/plan")
def get_plan(user: dict = Depends(current_user)):
    s = user["settings"]
    split = [{"day": plan.WEEKDAYS[i], **s["split"][i]} for i in range(7)]
    return {"targets": s["targets"], "split": split, "menu": s["menu"], "rules": plan.RULES}


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
    return {"app": "fitlog", "version": 2, "days": store.list(user["id"], "2000-01-01", "2100-01-01")}


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


@app.get("/api/summary")
def summary(day: str | None = None, user: dict = Depends(current_user)):
    """Everything the home screen needs in one call."""
    today = parse_date(day) if day else Date.today()
    history = store.list(user["id"], (today - timedelta(days=59)).isoformat(), today.isoformat())
    by_date = {d["date"]: d for d in history}

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
    if change is None:
        advice = "Log your weight most mornings. Trend advice starts after 2 weeks."
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
    trained = [
        d for d in history
        if d["date"] >= week_start.isoformat() and d.get("workout") not in (None, "", "Rest", "Skipped")
    ]

    return {
        "date": today.isoformat(),
        "name": user["name"],
        "entry": by_date.get(today.isoformat()),
        "workout": user["settings"]["split"][today.weekday()],
        "targets": user["settings"]["targets"],
        "weight_avg_7d": this_week,
        "weight_avg_prev_7d": last_week,
        "weekly_change": change,
        "advice": advice,
        "streak": streak,
        "sessions_this_week": len(trained),
    }


# The web app (HTML/CSS/JS) is served from the same place as the API.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")

# AWS Lambda entry point. Mangum translates Lambda events into normal web requests.
try:
    from mangum import Mangum

    handler = Mangum(app)
except ImportError:  # not needed when running locally
    handler = None
