"""
Loads the bundled synthetic demo dataset (backend/data/demo/) end-to-end
through the real ingestion pipeline -- CSV/JSON parsing, NLP extraction,
graph building, entity resolution -- so the app is immediately explorable
without a judge/reviewer having to source real (and sensitive) crime data
first.

The dataset models one small fictional syndicate: a kingpin, a
financier, an enforcer/courier, a money-mule shopfront, an outside
narcotics supplier, and their phone, vehicle and account trails --
deliberately containing a burst-calling pattern, a short-duration-call
pattern, a circular money-transfer loop, and a name-variant that needs
entity resolution, so every analytics module has something real to
surface on first load. See docs/DEMO_DATA.md for the intended "walkthrough".
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from app.db.graph_store import GraphStore
from app.services.pipeline import ingest_structured, ingest_text_document

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"


def _read_csv(name: str) -> list[dict]:
    with open(DEMO_DIR / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(name: str) -> list[dict]:
    with open(DEMO_DIR / name, encoding="utf-8-sig") as f:
        return json.load(f)


def seed(store: GraphStore) -> dict:
    summary = {"structured": {}, "documents": 0}

    summary["structured"]["criminal_history"] = ingest_structured(
        store, "criminal_history", _read_csv("criminal_history.csv"), "demo-criminal-history"
    ).model_dump()
    summary["structured"]["cdr"] = ingest_structured(
        store, "cdr", _read_csv("cdr_records.csv"), "demo-cdr"
    ).model_dump()
    summary["structured"]["financial"] = ingest_structured(
        store, "financial", _read_csv("financial_transactions.csv"), "demo-financial"
    ).model_dump()

    for report in _read_json("fir_reports.json"):
        ingest_text_document(
            store, "fir" if report["document_id"].startswith("FIR") else "surveillance",
            report["document_id"], report["text"], metadata={"document_date": report["document_date"]},
        )
        summary["documents"] += 1

    for i, post in enumerate(_read_json("social_media_posts.json")):
        ingest_text_document(
            store, "social_media", f"SOCIAL-{i}", post["text"],
            metadata={"document_date": post["timestamp"], "author": post["author"], "platform": post["platform"]},
        )
        summary["documents"] += 1

    return summary
