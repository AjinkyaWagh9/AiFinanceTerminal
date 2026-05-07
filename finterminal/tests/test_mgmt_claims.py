from datetime import datetime
import pytest
from finterminal.data.duckdb_store import connect, insert_mgmt_claim, list_mgmt_claims

TS = datetime(2026, 4, 29, 9, 0)

def test_insert_mgmt_claim_returns_uuid(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    claim_id = insert_mgmt_claim(conn, {
        "ticker": "TCS",
        "claimed_at": TS,
        "claim_text": "We will double revenue in 2 years.",
        "horizon_days": 730,
        "source_ref": "Q4-2026-earnings-call",
    })
    assert isinstance(claim_id, str) and len(claim_id) == 36   # UUID4

def test_list_mgmt_claims_returns_inserted(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    insert_mgmt_claim(conn, {
        "ticker": "TCS", "claimed_at": TS,
        "claim_text": "Double revenue in 2 years.", "horizon_days": 730,
    })
    rows = list_mgmt_claims(conn, "TCS")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "TCS"
    assert rows[0]["claim_text"] == "Double revenue in 2 years."
    assert rows[0]["outcome_verified"] is None

def test_list_mgmt_claims_filters_by_ticker(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    insert_mgmt_claim(conn, {"ticker": "TCS",  "claimed_at": TS,
                              "claim_text": "TCS claim", "horizon_days": 365})
    insert_mgmt_claim(conn, {"ticker": "INFY", "claimed_at": TS,
                              "claim_text": "INFY claim", "horizon_days": 180})
    tcs_rows  = list_mgmt_claims(conn, "TCS")
    infy_rows = list_mgmt_claims(conn, "INFY")
    assert len(tcs_rows) == 1 and tcs_rows[0]["ticker"] == "TCS"
    assert len(infy_rows) == 1 and infy_rows[0]["ticker"] == "INFY"

def test_list_mgmt_claims_empty_when_none(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    assert list_mgmt_claims(conn, "TCS") == []

def test_insert_mgmt_claim_with_outcome(tmp_path):
    conn = connect(str(tmp_path / "t.duckdb"))
    from datetime import date
    claim_id = insert_mgmt_claim(conn, {
        "ticker": "TCS", "claimed_at": TS,
        "claim_text": "Margin will expand 200bps.", "horizon_days": 365,
        "outcome_date": date(2027, 4, 29), "outcome_verified": True,
        "source_ref": "Annual-Report-2027",
    })
    rows = list_mgmt_claims(conn, "TCS")
    assert rows[0]["outcome_verified"] is True
    assert rows[0]["source_ref"] == "Annual-Report-2027"
