"""Where accounts and daily records are saved.

Two interchangeable "stores" with the same methods:
  - SqliteStore: a file on your laptop. Used when you run the app locally.
  - DynamoStore: AWS DynamoDB tables. Used in the cloud (when TABLE_NAME is set).

The rest of the app never knows which one it is talking to. Swapping storage
without touching the rest of the code is a common pattern in cloud apps.

Every daily record belongs to one user (user id + date), so people only ever
see their own log.
"""

import json
import os
import sqlite3
from decimal import Decimal

# Field name -> Python type for one day's record
FIELDS = {
    "weight": float,  # kg
    "steps": int,
    "water": float,  # litres
    "protein": int,  # grams
    "sleep": float,  # hours
    "workout": str,  # e.g. "Push", "Rest", "Skipped"
    "waist": float,  # cm
    "lifts": str,  # free text, e.g. "Incline DB 22.5 kg x 10,9,8"
    "note": str,
}

# Records saved before accounts existed belong to this placeholder user.
# The first account that signs up takes them over (see claim_legacy).
LEGACY_USER = "me"


class SqliteStore:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        cols = ", ".join(f"{name} {'TEXT' if t is str else 'REAL'}" for name, t in FIELDS.items())
        with self._connect() as db:
            old = db.execute("PRAGMA table_info(days)").fetchall()
            if old and "user_id" not in [c["name"] for c in old]:
                # upgrade a pre-accounts database: keep the rows, give them to LEGACY_USER
                db.execute("ALTER TABLE days RENAME TO days_v1")
            db.execute(
                f"CREATE TABLE IF NOT EXISTS days (user_id TEXT NOT NULL, date TEXT NOT NULL, {cols}, "
                "PRIMARY KEY (user_id, date))"
            )
            if old and "user_id" not in [c["name"] for c in old]:
                names = ", ".join(FIELDS)
                db.execute(f"INSERT INTO days (user_id, date, {names}) SELECT ?, date, {names} FROM days_v1", (LEGACY_USER,))
                db.execute("DROP TABLE days_v1")
            db.execute(
                "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
                "name TEXT, password_hash TEXT NOT NULL, settings TEXT NOT NULL, created TEXT NOT NULL)"
            )

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    # ----- users -----
    def _user(self, row) -> dict | None:
        if not row:
            return None
        user = dict(row)
        user["settings"] = json.loads(user["settings"])
        return user

    def get_user_by_email(self, email: str) -> dict | None:
        with self._connect() as db:
            return self._user(db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())

    def create_user(self, user: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO users (id, email, name, password_hash, settings, created) VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], user["email"], user["name"], user["password_hash"], json.dumps(user["settings"]), user["created"]),
            )

    def update_user(self, user: dict) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE users SET name = ?, password_hash = ?, settings = ? WHERE email = ?",
                (user["name"], user["password_hash"], json.dumps(user["settings"]), user["email"]),
            )

    def count_users(self) -> int:
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def delete_user(self, user: dict) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM days WHERE user_id = ?", (user["id"],))
            db.execute("DELETE FROM users WHERE email = ?", (user["email"],))

    def claim_legacy(self, user_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE days SET user_id = ? WHERE user_id = ?", (user_id, LEGACY_USER))

    # ----- days -----
    def _day(self, row) -> dict:
        day = {"date": row["date"]}
        for name, t in FIELDS.items():
            if row[name] is not None:
                day[name] = t(row[name])
        return day

    def get(self, user_id: str, date: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM days WHERE user_id = ? AND date = ?", (user_id, date)).fetchone()
        return self._day(row) if row else None

    def list(self, user_id: str, start: str, end: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM days WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date", (user_id, start, end)
            ).fetchall()
        return [self._day(r) for r in rows]

    def put(self, user_id: str, date: str, data: dict) -> dict:
        names = ["user_id", "date", *FIELDS]
        values = [user_id, date, *(data.get(n) for n in FIELDS)]
        with self._connect() as db:
            db.execute(
                f"INSERT OR REPLACE INTO days ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
                values,
            )
        return self.get(user_id, date)

    def delete(self, user_id: str, date: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM days WHERE user_id = ? AND date = ?", (user_id, date))


class DynamoStore:
    """Two tables:
      - days:  partition key "user" (user id), sort key "date" (YYYY-MM-DD),
               so a user's date range is one cheap Query.
      - users: partition key "email".
    """

    def __init__(self, days_table: str, users_table: str):
        import boto3  # only needed in the cloud

        db = boto3.resource("dynamodb")
        self.days = db.Table(days_table)
        self.users = db.Table(users_table)

    # ----- users -----
    def _user(self, item) -> dict | None:
        if not item:
            return None
        user = dict(item)
        user["settings"] = json.loads(user["settings"])
        return user

    def get_user_by_email(self, email: str) -> dict | None:
        return self._user(self.users.get_item(Key={"email": email}).get("Item"))

    def create_user(self, user: dict) -> None:
        # the condition stops two sign-ups with the same email overwriting each other
        self.users.put_item(
            Item={**user, "settings": json.dumps(user["settings"])},
            ConditionExpression="attribute_not_exists(email)",
        )

    def update_user(self, user: dict) -> None:
        self.users.put_item(Item={**user, "settings": json.dumps(user["settings"])})

    def count_users(self) -> int:
        return self.users.scan(Select="COUNT", Limit=2).get("Count", 0)

    def delete_user(self, user: dict) -> None:
        for day in self.list(user["id"], "0000-01-01", "9999-12-31"):
            self.delete(user["id"], day["date"])
        self.users.delete_item(Key={"email": user["email"]})

    def claim_legacy(self, user_id: str) -> None:
        for day in self.list(LEGACY_USER, "0000-01-01", "9999-12-31"):
            self.put(user_id, day["date"], day)
            self.delete(LEGACY_USER, day["date"])

    # ----- days -----
    def _day(self, item: dict) -> dict:
        day = {"date": item["date"]}
        for name, t in FIELDS.items():
            if name in item:
                day[name] = t(item[name])
        return day

    def get(self, user_id: str, date: str) -> dict | None:
        item = self.days.get_item(Key={"user": user_id, "date": date}).get("Item")
        return self._day(item) if item else None

    def list(self, user_id: str, start: str, end: str) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        cond = Key("user").eq(user_id) & Key("date").between(start, end)
        items, kwargs = [], {"KeyConditionExpression": cond}
        while True:
            page = self.days.query(**kwargs)
            items += page["Items"]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return [self._day(i) for i in items]

    def put(self, user_id: str, date: str, data: dict) -> dict:
        item = {"user": user_id, "date": date}
        for name, value in data.items():
            if name in FIELDS and value is not None:
                # DynamoDB stores numbers as Decimal, not float
                item[name] = Decimal(str(value)) if isinstance(value, float) else value
        self.days.put_item(Item=item)
        return self._day(item)

    def delete(self, user_id: str, date: str) -> None:
        self.days.delete_item(Key={"user": user_id, "date": date})


def get_store():
    table = os.environ.get("TABLE_NAME")
    if table:
        return DynamoStore(table, os.environ["USERS_TABLE"])
    here = os.path.dirname(__file__)
    return SqliteStore(os.environ.get("DB_PATH", os.path.join(here, "..", "..", "data", "fitness.db")))
