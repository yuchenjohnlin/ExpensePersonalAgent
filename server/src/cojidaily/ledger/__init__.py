"""The ledger: what was paid (expenses), what it bought (lines), and the owner's categories.

It knows nothing about receipts, readings or photos (pm/decisions/reading-attempts-and-provenance-ownership.md).
Modules that create expenses (receipts) call api.py and keep their own links to the rows made.
"""
