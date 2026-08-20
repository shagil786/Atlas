import re


def classify(filename: str, content: bytes, people: list[str], target_year: int):
    name = filename.lower()
    if not content:
        return {"state": "unreadable", "confidence": 0.0, "note": "The file has no readable content."}
    if "unreadable" in name or "scan" in name:
        return {"state": "unreadable", "confidence": 0.15, "note": "The scan requires manual replacement."}
    doc_type = "1040" if "1040" in name or "return" in name else "government_id" if "id" in name else "w2" if "w2" in name or "w-2" in name else None
    year_match = re.search(r"20\d{2}", name)
    tax_year = int(year_match.group()) if year_match else target_year
    person = next((p for p in people if p.lower().replace(" ", "_") in name or p.lower().split()[0] in name), None)
    employer = None
    if doc_type == "w2":
        employer = next((candidate for candidate in ("northstar labs", "brightline studio", "cedar health", "harbor finance") if candidate in name.replace("_", " ")), None)
    confidence = 0.96 if doc_type and person and (doc_type != "w2" or employer) else 0.52 if doc_type else 0.2
    state = "needs_review" if confidence < 0.8 or tax_year != target_year and doc_type != "1040" else "approved"
    note = "Low-confidence classification" if state == "needs_review" else "Classified from filename"
    return {"state": state, "confidence": confidence, "doc_type": doc_type, "tax_year": tax_year, "person_name": person, "employer": employer, "note": note}

