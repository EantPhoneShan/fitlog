"""Setup questions, generated plans, daily tasks, progress reports, Google sign-in and owner tools."""

import sqlite3
from datetime import date, timedelta

import pytest

from test_api import make_client, signup

ANSWERS = {
    "goal": "lose_fat", "sex": "male", "age": 25, "height": 175, "weight": 80, "target_weight": 74, "weeks": 12,
    "activity": "light", "experience": "intermediate", "days": 4, "minutes": 60, "equipment": "gym",
    "injuries": "", "diet": "any", "avoid": [], "dislikes": "", "meals": 4, "cooking": "basic",
    "budget": "moderate", "budget_amount": 300, "currency": "THB",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(monkeypatch, tmp_path / "test.db")


def onboard(client, headers, **changes):
    r = client.post("/api/onboarding", json={**ANSWERS, **changes}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_planner_numbers():
    from app import planner

    p = {**ANSWERS, "target_weight": None, "weeks": None}
    targets, _ = planner.targets_for(p)
    # BMR 1774 x 1.375 = 2439 maintenance, minus 20 % = 1951 -> 1950
    assert targets["calories"] == 1950
    assert targets["protein"] == 160  # 2 g per kg
    assert targets["fat"] == 55  # 25 % of calories
    assert targets["carbs"] == 205  # the rest
    assert targets["water"] == 2.75 and targets["steps"] == 8000

    fast = {**ANSWERS, "target_weight": 60, "weeks": 4}
    _, notes = planner.targets_for(fast)
    assert "faster than is healthy" in notes[0]


def test_onboarding_builds_a_personal_plan(client):
    h = signup(client)
    res = onboard(client, h)
    assert res["user"]["onboarded"] is True
    plan = res["plan"]
    assert plan["goal"] == "Lose fat"
    training = [d for d in plan["split"] if d["name"] != "Rest"]
    assert len(training) == 4 and {d["name"] for d in training} == {"Upper", "Lower"}
    assert len(plan["menu"]) == 4 and all(m["protein"] > 0 for m in plan["menu"])
    assert any("realistic" in n for n in plan["notes"])
    assert client.get("/api/me", headers=h).json()["profile"]["currency"] == "THB"


def test_diet_and_allergies_are_respected(client):
    h = signup(client)
    vegan = onboard(client, h, diet="vegan", avoid=["soy"], budget="flexible")["plan"]["menu"]
    text = " ".join(m["food"] for m in vegan).lower()
    for banned in ("chicken", "beef", "pork", "egg", "fish", "tuna", "shrimp", "yogurt", "whey", "milk", "tofu", "tempeh"):
        assert banned not in text, banned
    halal = onboard(client, h, diet="halal", budget="flexible")["plan"]["menu"]
    assert "pork" not in " ".join(m["food"] for m in halal).lower()
    home = onboard(client, h, equipment="bodyweight", days=3, experience="beginner")["plan"]["split"]
    names = [d["name"] for d in home if d["name"] != "Rest"]
    assert names == ["Full body A", "Full body B", "Full body C"]
    assert "Barbell" not in str(home)


def test_under_16_cannot_get_a_plan(client):
    h = signup(client)
    r = client.post("/api/onboarding", json={**ANSWERS, "age": 14}, headers=h)
    assert r.status_code == 400 and "16" in r.json()["detail"]
    assert client.post("/api/onboarding", json={**ANSWERS, "goal": "fly"}, headers=h).status_code == 422


def test_daily_tasks(client):
    h = signup(client)
    onboard(client, h)
    monday = "2026-10-12"
    tasks = client.get(f"/api/summary?day={monday}", headers=h).json()["tasks"]
    ids = [t["id"] for t in tasks]
    assert ids[0] == "workout" and "meal-0" in ids and "protein" in ids
    client.put(f"/api/days/{monday}", json={"done": "meal-0,meal-1", "protein": 200, "workout": "Upper"}, headers=h)
    tasks = {t["id"]: t for t in client.get(f"/api/summary?day={monday}", headers=h).json()["tasks"]}
    assert tasks["meal-0"]["done"] and tasks["meal-1"]["done"] and not tasks["meal-2"]["done"]
    assert tasks["protein"]["done"] and tasks["workout"]["done"] and not tasks["water"]["done"]


def test_progress_reports(client):
    h = signup(client)
    onboard(client, h)
    start = date.today()
    for i in range(35):
        d = (start + timedelta(days=i)).isoformat()
        client.put(f"/api/days/{d}", json={"weight": round(80 - i * 0.06, 1), "protein": 165, "steps": 8200,
                                           "workout": "Upper" if i % 2 else None}, headers=h)
    later = (start + timedelta(days=36)).isoformat()
    data = client.get(f"/api/reports?day={later}", headers=h).json()
    ids = [r["id"] for r in data["reports"]]
    assert ids == ["month-1", "week-1"]
    month = data["reports"][0]
    assert month["stats"]["weight_change"] < 0 and "lost" in month["highlights"][0]
    assert month["read"] is False
    assert client.get(f"/api/summary?day={later}", headers=h).json()["unread_reports"] == 2
    assert data["live"]["title"] == "Month 2 so far"

    client.post("/api/reports/month-1/read", headers=h)
    client.delete("/api/reports/week-1", headers=h)
    again = client.get(f"/api/reports?day={later}", headers=h).json()["reports"]
    assert [r["id"] for r in again] == ["month-1"] and again[0]["read"] is True  # deleted reports stay deleted


def test_google_sign_in(client, monkeypatch):
    from app import auth

    assert client.post("/api/auth/google", json={"credential": "x"}).status_code == 400  # not set up
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setattr(auth, "verify_google", lambda cred, cid: None if cred == "bad" else
                        {"email": "Lin@Gmail.com", "given_name": "Lin", "email_verified": "true"})
    assert client.post("/api/auth/google", json={"credential": "bad"}).status_code == 401
    assert client.post("/api/auth/google", json={"credential": "good"}).status_code == 428  # asks for consent first
    r = client.post("/api/auth/google", json={"credential": "good", "consent": True})
    assert r.status_code == 200 and r.json()["user"]["provider"] == "google"
    again = client.post("/api/auth/google", json={"credential": "good"})  # existing account: no consent needed
    assert again.status_code == 200
    h = {"Authorization": f"Bearer {again.json()['token']}"}
    pw = client.post("/api/auth/login", json={"email": "lin@gmail.com", "password": "anything12"})
    assert pw.status_code == 401 and "Google" in pw.json()["detail"]
    assert client.post("/api/me/delete", json={"confirm": "nope"}, headers=h).status_code == 403
    assert client.post("/api/me/delete", json={"confirm": "DELETE"}, headers=h).status_code == 200


def test_owner_tools(client, monkeypatch):
    owner = signup(client, email="owner@example.com")
    user = signup(client, email="user@example.com", name="User")
    onboard(client, user)
    client.put("/api/days/2026-10-12", json={"weight": 79.5}, headers=user)
    assert client.get("/api/admin/users", headers=owner).status_code == 403
    monkeypatch.setenv("ADMIN_EMAILS", "Owner@example.com")
    assert client.get("/api/me", headers=owner).json()["is_admin"] is True
    users = client.get("/api/admin/users", headers=owner).json()
    assert [u["email"] for u in users] == ["owner@example.com", "user@example.com"]
    assert users[1]["profile"]["goal"] == "lose_fat" and users[1]["last_weight"] == 79.5
    csv = client.get("/api/admin/export.csv", headers=owner).text
    assert csv.splitlines()[0].startswith("email,name,joined,goal")
    assert "user@example.com" in csv and "79.5" in csv
    assert client.get("/api/admin/users", headers=user).status_code == 403


def test_android_asset_links(client, monkeypatch):
    assert client.get("/.well-known/assetlinks.json").json() == []
    monkeypatch.setenv("ANDROID_PACKAGE", "com.forgetrack.app")
    monkeypatch.setenv("ANDROID_CERT_SHA256", "aa:bb")
    link = client.get("/.well-known/assetlinks.json").json()[0]
    assert link["target"]["package_name"] == "com.forgetrack.app"
    assert link["target"]["sha256_cert_fingerprints"] == ["AA:BB"]


def test_v2_database_gets_new_columns(tmp_path, monkeypatch):
    path = tmp_path / "v2.db"
    with sqlite3.connect(path) as db:  # accounts existed, but no calories / done columns yet
        db.execute("CREATE TABLE days (user_id TEXT NOT NULL, date TEXT NOT NULL, weight REAL, steps REAL, water REAL, "
                   "protein REAL, sleep REAL, workout TEXT, waist REAL, lifts TEXT, note TEXT, PRIMARY KEY (user_id, date))")
    client = make_client(monkeypatch, path)
    h = signup(client)
    r = client.put("/api/days/2026-10-12", json={"calories": 2100, "done": "workout"}, headers=h)
    assert r.json() == {"date": "2026-10-12", "calories": 2100, "done": "workout"}
