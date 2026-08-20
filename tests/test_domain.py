import sqlite3

from app.db import SCHEMA
from app.domain import RuleRegistry, apply_matches, reconcile_requirements


def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    connection.execute("INSERT INTO clients VALUES (1,'Test household','joint',2025,2024)")
    connection.executemany("INSERT INTO people VALUES (?,?,?, ?,1)", [(1,1,'Maya Patel','taxpayer'),(2,1,'Rohan Patel','spouse')])
    return connection


def test_rules_include_universal_documents_and_w2s():
    connection = db()
    connection.execute("INSERT INTO employments(person_id,employer,year) VALUES (1,'Northstar Labs',2025)")
    specs = RuleRegistry().derive(connection, 1)
    assert any(s.doc_type == "1040" and s.tax_year == 2024 for s in specs)
    assert any(s.doc_type == "w2" and s.employer == "Northstar Labs" for s in specs)


def test_reconciliation_preserves_manual_override():
    connection = db()
    reconcile_requirements(connection, 1)
    req = connection.execute("SELECT * FROM requirements LIMIT 1").fetchone()
    connection.execute("INSERT INTO requirement_overrides(requirement_id,client_id,stable_key,decision,actor_id) VALUES (?,?,?,?,1)", (req['id'],1,req['stable_key'],'not_needed'))
    reconcile_requirements(connection, 1)
    assert connection.execute("SELECT COUNT(*) FROM requirement_overrides WHERE requirement_id=?", (req['id'],)).fetchone()[0] == 1


def test_exact_approved_document_matches_requirement():
    connection = db()
    connection.execute("INSERT INTO employments(person_id,employer,year) VALUES (1,'Northstar Labs',2025)")
    reconcile_requirements(connection, 1)
    req = connection.execute("SELECT * FROM requirements WHERE doc_type='w2'").fetchone()
    connection.execute("INSERT INTO documents(client_id,object_key,file_hash,filename,doc_type,tax_year,person_name,employer,confidence,state,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (1,'k','h','w2.pdf','w2',2024,'Maya Patel','Northstar Labs',.99,'approved',1))
    apply_matches(connection, 1)
    assert connection.execute("SELECT status FROM requirements WHERE id=?", (req['id'],)).fetchone()[0] == 'outstanding'
