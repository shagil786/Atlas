from dataclasses import dataclass


@dataclass(frozen=True)
class RequirementSpec:
    stable_key: str
    doc_type: str
    tax_year: int
    person_id: int | None
    employer: str | None
    source_rule: str


class RuleRegistry:
    def derive(self, db, client_id: int) -> list[RequirementSpec]:
        client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        people = db.execute("SELECT * FROM people WHERE client_id=? AND required_for_universal_docs=1", (client_id,)).fetchall()
        specs: list[RequirementSpec] = []
        for person in people:
            specs.append(RequirementSpec(f"1040:{client['prior_year']}:{person['id']}", "1040", client["prior_year"], person["id"], None, "universal_return"))
            specs.append(RequirementSpec(f"government_id:{client['target_year']}:{person['id']}", "government_id", client["target_year"], person["id"], None, "universal_id"))
        employments = db.execute("SELECT DISTINCT person_id, employer FROM employments WHERE person_id IN (SELECT id FROM people WHERE client_id=?) AND year=?", (client_id, client["target_year"])).fetchall()
        for employment in employments:
            specs.append(RequirementSpec(f"w2:{client['target_year']}:{employment['person_id']}:{employment['employer']}", "w2", client["target_year"], employment["person_id"], employment["employer"], "employment"))
        return specs


def reconcile_requirements(db, client_id: int, registry: RuleRegistry | None = None):
    registry = registry or RuleRegistry()
    specs = registry.derive(db, client_id)
    for spec in specs:
        existing = db.execute("SELECT id FROM requirements WHERE client_id=? AND stable_key=?", (client_id, spec.stable_key)).fetchone()
        if not existing:
            db.execute("INSERT INTO requirements(client_id,stable_key,doc_type,tax_year,person_id,employer,source_rule) VALUES (?,?,?,?,?,?,?)", (client_id, spec.stable_key, spec.doc_type, spec.tax_year, spec.person_id, spec.employer, spec.source_rule))
    return specs


def apply_matches(db, client_id: int):
    requirements = db.execute("SELECT * FROM requirements WHERE client_id=?", (client_id,)).fetchall()
    for req in requirements:
        match = db.execute("""SELECT 1 FROM documents WHERE client_id=? AND state='approved' AND doc_type=? AND tax_year=? AND (person_name IS NULL OR person_name=(SELECT name FROM people WHERE id=?)) AND (employer IS NULL OR employer=?) LIMIT 1""", (client_id, req["doc_type"], req["tax_year"], req["person_id"], req["employer"])).fetchone()
        override = db.execute("SELECT decision FROM requirement_overrides WHERE requirement_id=? ORDER BY id DESC LIMIT 1", (req["id"],)).fetchone()
        status = "not_needed" if override and override["decision"] == "not_needed" else ("received" if match else "outstanding")
        db.execute("UPDATE requirements SET status=? WHERE id=?", (status, req["id"]))

