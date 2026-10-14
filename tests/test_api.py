"""Run with:  python -m pytest   (from the fitness-app folder)"""

import importlib
import os
import sqlite3
import sys

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def make_client(monkeypatch, db_path):
    monkeypatch.setenv("DB_PATH", str(db_path))
    for var in ("TABLE_NAME", "SECRET_KEY", "SIGNUP_CODE"):
        monkeypatch.delenv(var, raising=False)
    import app.main

    importlib.reload(app.main)
    return TestClient(app.main.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(monkeypatch, tmp_path / "test.db")


def signup(client, email="adam@example.com", name="Adam", password="strongpass1", **extra):
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password, **extra})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_signup_login_and_me(client):
    signup(client, email="Adam@Example.com")
    r = client.post("/api/auth/login", json={"email": "adam@example.com", "password": "strongpass1"})
    assert r.status_code == 200
    me = client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert me["name"] == "Adam" and me["email"] == "adam@example.com"
    assert "password_hash" not in me
    assert me["settings"]["split"][0]["name"] == "Push"


def test_bad_logins_and_duplicates(client):
    signup(client)
    assert client.post("/api/auth/login", json={"email": "adam@example.com", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "strongpass1"}).status_code == 401
    r = client.post("/api/auth/signup", json={"name": "A", "email": "adam@example.com", "password": "strongpass1"})
    assert r.status_code == 409
    assert client.post("/api/auth/signup", json={"name": "B", "email": "b@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/signup", json={"name": "B", "email": "not-an-email", "password": "longenough"}).status_code == 400


def test_everything_private_needs_login(client):
    for path in ["/api/me", "/api/plan", "/api/days", "/api/summary", "/api/export"]:
        assert client.get(path).status_code == 401, path
    assert client.get("/api/me", headers={"Authorization": "Bearer fake.token"}).status_code == 401
    headers = signup(client)
    token = headers["Authorization"].split()[1]
    body, sig = token.split(".")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {body}x.{sig}"}).status_code == 401


def test_users_only_see_their_own_records(client):
    adam = signup(client)
    sara = signup(client, email="sara@example.com", name="Sara")
    client.put("/api/days/2026-10-12", json={"weight": 65.2, "note": "adam's day"}, headers=adam)
    client.put("/api/days/2026-10-12", json={"weight": 54.0}, headers=sara)
    assert client.get("/api/days/2026-10-12", headers=adam).json()["note"] == "adam's day"
    assert client.get("/api/days/2026-10-12", headers=sara).json() == {"date": "2026-10-12", "weight": 54.0}
    assert len(client.get("/api/export", headers=sara).json()["days"]) == 1


def test_invite_code(client, monkeypatch):
    monkeypatch.setenv("SIGNUP_CODE", "gym2026")
    assert client.get("/api/config").json() == {"signup_code_required": True}
    r = client.post("/api/auth/signup", json={"name": "X", "email": "x@example.com", "password": "longenough"})
    assert r.status_code == 403
    signup(client, email="x@example.com", code="gym2026")


def test_save_and_read_a_day(client):
    h = signup(client)
    r = client.put("/api/days/2026-10-12", json={"weight": 65.2, "protein": 138, "workout": "Push"}, headers=h)
    assert r.json() == {"date": "2026-10-12", "weight": 65.2, "protein": 138, "workout": "Push"}
    assert client.put("/api/days/not-a-date", json={}, headers=h).status_code == 400
    assert client.put("/api/days/2026-10-12", json={"weight": 5}, headers=h).status_code == 422
    client.delete("/api/days/2026-10-12", headers=h)
    assert client.get("/api/days/2026-10-12", headers=h).status_code == 404


def test_edit_plan_changes_today(client):
    h = signup(client)
    settings = client.get("/api/me", headers=h).json()["settings"]
    settings["targets"]["protein"] = 110
    settings["split"][0] = {"name": "Chest", "exercises": ["Bench press", "  ", "Dips"]}
    settings["menu"] = [{"meal": "Lunch", "food": "Nasi ayam", "protein": 40}]
    r = client.put("/api/me", json={"settings": settings}, headers=h)
    assert r.status_code == 200
    s = client.get("/api/summary?day=2026-10-12", headers=h).json()  # a Monday
    assert s["workout"] == {"name": "Chest", "exercises": ["Bench press", "Dips"]}
    assert s["targets"]["protein"] == 110
    bad = {**settings, "split": settings["split"][:6]}
    assert client.put("/api/me", json={"settings": bad}, headers=h).status_code == 422


def test_summary_trend_and_streak(client):
    h = signup(client)
    for i, w in enumerate([65.6, 65.5, 65.5, 65.4, 65.6, 65.5, 65.4]):
        client.put(f"/api/days/2026-10-{5 + i:02d}", json={"weight": w}, headers=h)
    for i, w in enumerate([65.2, 65.1, 65.1, 65.0, 65.2, 65.1, 65.0]):
        client.put(f"/api/days/2026-10-{12 + i:02d}", json={"weight": w, "workout": "Push" if i == 0 else None}, headers=h)
    s = client.get("/api/summary?day=2026-10-18", headers=h).json()
    assert s["weekly_change"] == pytest.approx(-0.4, abs=0.01)
    assert "on track" in s["advice"]
    assert s["streak"] == 14
    assert s["sessions_this_week"] == 1
    assert s["workout"]["name"] == "Rest"  # 18 Oct 2026 is a Sunday


def test_backup_round_trip(client):
    h = signup(client)
    client.put("/api/days/2026-10-12", json={"weight": 65.2, "note": "first day"}, headers=h)
    client.put("/api/days/2026-10-13", json={"steps": 4300}, headers=h)
    backup = client.get("/api/export", headers=h).json()
    other = signup(client, email="new@example.com")
    assert client.post("/api/import", json=backup, headers=other).json() == {"imported": 2}
    assert client.get("/api/days/2026-10-12", headers=other).json()["note"] == "first day"
    bad = {"days": [{"date": "2026-10-14", "weight": 5}]}
    assert client.post("/api/import", json=bad, headers=other).status_code == 400


def test_delete_account(client):
    h = signup(client)
    client.put("/api/days/2026-10-12", json={"steps": 4200}, headers=h)
    assert client.post("/api/me/delete", json={"password": "wrong-pass"}, headers=h).status_code == 403
    assert client.post("/api/me/delete", json={"password": "strongpass1"}, headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/auth/login", json={"email": "adam@example.com", "password": "strongpass1"}).status_code == 401


def test_old_database_is_upgraded_and_given_to_first_account(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:  # the v1 layout, before accounts existed
        db.execute("CREATE TABLE days (date TEXT PRIMARY KEY, weight REAL, steps REAL, water REAL, protein REAL, "
                   "sleep REAL, workout TEXT, waist REAL, lifts TEXT, note TEXT)")
        db.execute("INSERT INTO days (date, weight, note) VALUES ('2026-10-11', 64.7, 'old entry')")
    client = make_client(monkeypatch, path)
    first = signup(client)
    second = signup(client, email="second@example.com")
    assert client.get("/api/days/2026-10-11", headers=first).json()["note"] == "old entry"
    assert client.get("/api/days/2026-10-11", headers=second).status_code == 404


def test_web_app_is_served(client):
    assert "Unforgedabble" in client.get("/").text
    assert client.get("/manifest.json").json()["display"] == "standalone"
    assert client.get("/sw.js").status_code == 200


@mock_aws
def test_dynamodb_store(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    ddb = boto3.client("dynamodb")
    ddb.create_table(
        TableName="fitlog-days",
        AttributeDefinitions=[{"AttributeName": "user", "AttributeType": "S"}, {"AttributeName": "date", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "user", "KeyType": "HASH"}, {"AttributeName": "date", "KeyType": "RANGE"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="fitlog-users",
        AttributeDefinitions=[{"AttributeName": "email", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "email", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    from app.storage import DynamoStore

    store = DynamoStore("fitlog-days", "fitlog-users")
    assert store.count_users() == 0
    user = {"id": "u1", "email": "a@x.com", "name": "A", "password_hash": "h", "settings": {"x": 1}, "created": "now"}
    store.create_user(user)
    with pytest.raises(Exception):
        store.create_user(user)  # same email twice is refused
    assert store.get_user_by_email("a@x.com")["settings"] == {"x": 1}
    assert store.count_users() == 1

    store.put("me", "2026-10-01", {"weight": 66.0})  # pre-accounts record
    store.claim_legacy("u1")
    store.put("u1", "2026-10-12", {"weight": 65.2, "steps": 4100, "water": 3.0, "note": "felt good", "waist": None})
    store.put("u2", "2026-10-12", {"weight": 50.0})
    assert store.get("u1", "2026-10-12") == {"date": "2026-10-12", "weight": 65.2, "steps": 4100, "water": 3.0, "note": "felt good"}
    assert [d["date"] for d in store.list("u1", "2026-01-01", "2026-12-31")] == ["2026-10-01", "2026-10-12"]
    assert store.list("me", "2026-01-01", "2026-12-31") == []

    store.delete_user(user)
    assert store.get_user_by_email("a@x.com") is None
    assert store.list("u1", "2026-01-01", "2026-12-31") == []
    assert store.get("u2", "2026-10-12")["weight"] == 50.0
