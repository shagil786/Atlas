import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, household_name TEXT NOT NULL, filing_status TEXT NOT NULL, target_year INTEGER NOT NULL, prior_year INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS people (id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, name TEXT NOT NULL, relationship TEXT NOT NULL, required_for_universal_docs INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS employments (id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL, employer TEXT NOT NULL, year INTEGER NOT NULL, start_month INTEGER, end_month INTEGER);
CREATE TABLE IF NOT EXISTS requirements (id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, stable_key TEXT NOT NULL, doc_type TEXT NOT NULL, tax_year INTEGER NOT NULL, person_id INTEGER, employer TEXT, source_rule TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'outstanding', manual INTEGER NOT NULL DEFAULT 0, UNIQUE(client_id, stable_key));
CREATE TABLE IF NOT EXISTS requirement_overrides (id INTEGER PRIMARY KEY, requirement_id INTEGER, client_id INTEGER NOT NULL, stable_key TEXT NOT NULL, decision TEXT NOT NULL, actor_id INTEGER NOT NULL, reason TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, object_key TEXT UNIQUE NOT NULL, file_hash TEXT NOT NULL, filename TEXT NOT NULL, doc_type TEXT, tax_year INTEGER, person_name TEXT, employer TEXT, confidence REAL NOT NULL, state TEXT NOT NULL, classifier_note TEXT, created_by INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, reviewer_id INTEGER NOT NULL, corrections TEXT, decision TEXT NOT NULL, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS idempotency_keys (key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, response_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


@contextmanager
def connect():
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as db:
        db.executescript(SCHEMA)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        _, iterations, salt_hex, digest_hex = stored.split("$", 3)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return secrets.compare_digest(candidate.hex(), digest_hex)
    # Compatibility for databases seeded before the password-hardening change.
    return secrets.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def seed_db():
    init_db()
    with connect() as db:
        if db.execute("SELECT 1 FROM clients LIMIT 1").fetchone():
            return
        db.executemany("INSERT INTO users(username,password_hash,role) VALUES (?,?,?)", [
            ("accountant", hash_password("accountant-demo"), "accountant"),
            ("reviewer", hash_password("reviewer-demo"), "reviewer"),
        ])
        db.execute("INSERT INTO clients(household_name,filing_status,target_year,prior_year) VALUES (?,?,?,?)", ("Patel household", "married_filing_jointly", 2025, 2024))
        client_id = db.execute("SELECT id FROM clients").fetchone()[0]
        db.executemany("INSERT INTO people(client_id,name,relationship) VALUES (?,?,?)", [
            (client_id, "Maya Patel", "taxpayer"), (client_id, "Rohan Patel", "spouse"), (client_id, "Isha Patel", "dependent")
        ])
        people = {r["name"]: r["id"] for r in db.execute("SELECT id,name FROM people")}
        db.executemany("INSERT INTO employments(person_id,employer,year,start_month,end_month) VALUES (?,?,?,?,?)", [
            (people["Maya Patel"], "Northstar Labs", 2024, 1, 12),
            (people["Maya Patel"], "Brightline Studio", 2024, 1, 12),
            (people["Rohan Patel"], "Cedar Health", 2024, 1, 5),
            (people["Rohan Patel"], "Harbor Finance", 2025, 6, 12),
            (people["Rohan Patel"], "Cedar Health", 2025, 1, 5),
        ])
        from .domain import reconcile_requirements
        reconcile_requirements(db, client_id)


def row_dict(row):
    return dict(row) if row else None
