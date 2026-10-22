"""Receipts: the one module that coordinates others (pm/decisions/reading-attempts-and-provenance-ownership.md).

A receipt is an ordered group of photos from the photo library. receipts asks reading to read it,
decides whether the result may be posted (pm/decisions/reading-auto-post-when-checks-pass.md),
asks the ledger to create the expense, and keeps the links: which readings belong to a receipt,
which expense it was posted as, and which line came from which read item. Foreign keys go from
receipts to photos, reading and ledger, never back.
"""
