from app.classifier import classify


PEOPLE = ["Maya Patel", "Rohan Patel", "Isha Patel"]


def test_confident_w2_classification():
    result = classify("w2_2025_rohan_patel_harbor_finance.pdf", b"content", PEOPLE, 2025)
    assert result["doc_type"] == "w2"
    assert result["state"] == "approved"
    assert result["employer"] == "harbor finance"


def test_unreadable_scan_needs_attention():
    result = classify("unreadable_scan.pdf", b"content", PEOPLE, 2025)
    assert result["state"] == "unreadable"


def test_unknown_person_is_low_confidence():
    result = classify("w2_2025_unknown_harbor_finance.pdf", b"content", PEOPLE, 2025)
    assert result["state"] == "needs_review"
    assert result["person_name"] is None
