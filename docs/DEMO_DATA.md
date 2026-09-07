# Demo dataset walkthrough

`backend/data/demo/` contains one small, entirely fictional syndicate, run through the real pipeline
on every backend startup (`AUTO_SEED_DEMO=true`, the default). It exists so every analytics module has
something genuine to surface the first time anyone opens the app — nothing about it is hard-coded into
the analytics themselves.

## The story

- **Vikram Rathore** ("Vicky") — the hub. Prior extortion/assault cases, drives `MP09AB1234`.
- **Ramesh Kumar** ("Ramu") — enforcer/courier, co-accused with Rathore, meets **Farhan Ali** (an
  outside narcotics supplier from Delhi) at a highway dhaba.
- **Suresh Yadav** — financier. Routes money through **Chatterjee Traders** (a shell trading firm) to
  **Anita Deshmukh**, who forwards a cut to Farhan Ali.
- **Zubair Khan**, **Sanjay Mehta**, **Deepak Verma**, **Om Prakash** — a looser, lower-level layer
  around Rathore.

Sources: `criminal_history.csv`, `cdr_records.csv`, `financial_transactions.csv`, `fir_reports.json`
(FIR + surveillance + intel narratives), `social_media_posts.json`.

## What each analytics module finds in it, and why

| Module | What it surfaces | Where it comes from in the data |
|---|---|---|
| **Key influencers** | Suresh Yadav and Farhan Ali rank highest by betweenness/PageRank — they bridge otherwise-separate clusters (financier ↔ shell company ↔ supplier), which a simple call-count wouldn't catch. | Financial + CDR + FIR co-mentions all reinforcing the same edges |
| **Communities** | 5-7 clusters, roughly: Rathore's core crew, the Yadav→Chatterjee Traders→Deshmukh money trail, the Mehta/Verma/Om Prakash periphery. | Louvain modularity over the whole graph |
| **BURST_CALLING** | 6 calls between Rathore's and Ramesh Kumar's numbers inside 48 hours. | `cdr_records.csv` rows on 2026-08-10/11 |
| **SHORT_DURATION_CALLS** | Every Rathore↔Zubair Khan call is under 20 seconds. | `cdr_records.csv`, the 9876543210↔9845123456 rows |
| **CIRCULAR_TRANSACTION** | ACC1001 → ACC1002 → ACC1004 → ACC1001, a classic layering loop. | `financial_transactions.csv` |
| **NEW_HIGH_DEGREE_NODE** | Suresh Yadav and Farhan Ali again — degree far above the network average. | Emergent from the combined graph |
| **Entity resolution** | `"Vikram Rathore"` (CDR) auto-merges with `"Rathore Vikram"` (a reversed-order CDR row) — a near-exact name match. `"Ramesh Kumar"` vs. the surveillance report's `"Ramesh Kr."` is surfaced as a **candidate for analyst review**, not auto-merged, because the name similarity alone isn't high enough and there's no independent corroborating shared connection at ingestion time. | `criminal_history.csv` + `cdr_records.csv` + `fir_reports.json` |

## Suggested walkthrough for a demo/judging session

1. **Dashboard** — point at the entity/relationship counts and the top-influencer list; note that
   Suresh Yadav (financier) outranks Vikram Rathore (the "obvious" kingpin by prior record) — that's
   the betweenness-centrality story worth narrating.
2. **Graph Explorer** — search "Vikram Rathore", view his 2-hop neighborhood, click through to his
   phone/vehicle/associates.
3. **Path Finder** — connect "Farhan Ali" to "Vikram Rathore" and show the 3-hop chain through Ramesh
   Kumar even though the two never appear together in any single record.
4. **Ingest Data** — paste a new one-off sentence (e.g. `"Zubair Khan met Farhan Ali near Chandan Nagar
   Indore and handed him a package."`) and show it landing in the graph live.
5. **Anomalies on the Dashboard** — walk through the burst-calling and circular-transaction flags and
   explain the plain-language reasoning behind each.
