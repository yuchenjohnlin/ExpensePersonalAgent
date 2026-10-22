"""CojiDaily, rebuilt as a modular monolith (server/README.md).

Each module owns its tables and is used by other modules only through its `api.py`:
platform (no domain knowledge), auth, ledger, photos, reading, receipts.
"""
