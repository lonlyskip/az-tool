import os
import sqlite3
import secrets
import string
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_PATH = os.getenv("LICENSE_DB", "licenses.sqlite3")
# Set this in your hosting provider's environment variables. Never ship it in the client.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL,
            device_id TEXT,
            revoked INTEGER NOT NULL DEFAULT 0
        )""")

def utc_now():
    return datetime.now(timezone.utc)

def valid_row(row):
    if not row or row["revoked"]:
        return False
    try:
        return datetime.fromisoformat(row["expires_at"]) > utc_now()
    except Exception:
        return False

def make_key():
    alphabet = string.ascii_uppercase + string.digits
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(3))

@app.get("/")
def health():
    return jsonify({"ok": True, "service": "AFK Tool License API"})

@app.post("/api/activate")
def activate():
    data = request.get_json(silent=True) or {}
    key = str(data.get("key", "")).strip().upper()
    device_id = str(data.get("device_id", "")).strip()
    if not key or not device_id:
        return jsonify(ok=False, message="Missing key or device identifier."), 400
    with db() as con:
        row = con.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()
        if not valid_row(row):
            return jsonify(ok=False, message="Invalid, expired, or revoked license."), 403
        if row["device_id"] and row["device_id"] != device_id:
            return jsonify(ok=False, message="This license is already bound to another device."), 403
        if not row["device_id"]:
            con.execute("UPDATE licenses SET device_id=? WHERE key=?", (device_id, key))
    return jsonify(ok=True, message="Activation successful.")

@app.post("/api/validate")
def validate():
    data = request.get_json(silent=True) or {}
    key = str(data.get("key", "")).strip().upper()
    device_id = str(data.get("device_id", "")).strip()
    with db() as con:
        row = con.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()
    if not valid_row(row):
        return jsonify(ok=False, message="Invalid, expired, or revoked license."), 403
    if row["device_id"] != device_id:
        return jsonify(ok=False, message="License is not activated on this device."), 403
    return jsonify(ok=True, expires_at=row["expires_at"])

@app.post("/admin/create")
def create_license():
    if not ADMIN_TOKEN or request.headers.get("X-Admin-Token", "") != ADMIN_TOKEN:
        return jsonify(ok=False, message="Unauthorized."), 401
    data = request.get_json(silent=True) or {}
    try:
        days = int(data.get("days", 30))
        count = int(data.get("count", 1))
        if not 1 <= days <= 3650 or not 1 <= count <= 100:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify(ok=False, message="days must be 1-3650 and count must be 1-100."), 400
    created = []
    expiry = (utc_now() + timedelta(days=days)).isoformat()
    with db() as con:
        for _ in range(count):
            key = make_key()
            con.execute("INSERT INTO licenses(key, expires_at) VALUES (?, ?)", (key, expiry))
            created.append(key)
    return jsonify(ok=True, days=days, expires_at=expiry, keys=created)

@app.post("/admin/revoke")
def revoke_license():
    if not ADMIN_TOKEN or request.headers.get("X-Admin-Token", "") != ADMIN_TOKEN:
        return jsonify(ok=False, message="Unauthorized."), 401
    data = request.get_json(silent=True) or {}
    key = str(data.get("key", "")).strip().upper()
    with db() as con:
        cur = con.execute("UPDATE licenses SET revoked=1 WHERE key=?", (key,))
        if cur.rowcount == 0:
            return jsonify(ok=False, message="Key not found."), 404
    return jsonify(ok=True, message="License revoked.")

init_db()

if __name__ == "__main__":
    # For local testing only. In production use a production WSGI server and HTTPS.
    app.run(host="127.0.0.1", port=8000, debug=False)
