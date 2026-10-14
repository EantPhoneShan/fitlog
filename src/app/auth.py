"""Accounts: password hashing and log-in tokens, using only Python's standard library.

- Passwords are never stored. We store a salted PBKDF2 hash, so even someone who
  reads the database cannot get the password back.
- After log-in the app gets a signed token (like a wristband at a concert).
  The browser sends it with every request; the server checks the signature with
  SECRET_KEY, so nobody can fake or edit one.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from pathlib import Path

ITERATIONS = 200_000
TOKEN_DAYS = 30


def _secret_key() -> bytes:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key.encode()
    # Local laptop: make a random key once and keep it next to the database.
    path = Path(os.environ.get("DB_PATH", Path(__file__).parents[2] / "data" / "fitness.db")).with_name("secret.key")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip().encode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    if not stored:  # accounts made with Google have no password
        hash_password(password)  # same work either way, so timing gives nothing away
        return False
    _, iterations, salt, digest = stored.split("$")
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(test.hex(), digest)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user: dict) -> str:
    payload = {"uid": user["id"], "email": user["email"], "exp": int(time.time()) + TOKEN_DAYS * 86400}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(_secret_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> dict | None:
    """Returns the token's payload, or None if it is fake, edited or expired."""
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(_secret_key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        payload = json.loads(_unb64(body))
        return payload if payload["exp"] > time.time() else None
    except (ValueError, KeyError):
        return None


GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


def verify_google(credential: str, client_id: str) -> dict | None:
    """Checks a "Sign in with Google" ID token with Google and returns its claims, or None.

    Google's tokeninfo endpoint verifies the signature and expiry for us; we then make sure
    the token was issued to *this* app (aud) and that Google has verified the email.
    """
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": credential})
    try:
        with urllib.request.urlopen(url, timeout=5) as res:
            claims = json.loads(res.read())
    except (OSError, ValueError):
        return None
    if claims.get("aud") != client_id or claims.get("iss") not in GOOGLE_ISSUERS:
        return None
    if str(claims.get("email_verified")).lower() != "true" or int(claims.get("exp", 0)) < time.time():
        return None
    return claims