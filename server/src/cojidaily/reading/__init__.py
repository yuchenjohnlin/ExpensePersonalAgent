"""Reading photos into structured data, in the background (pm/decisions/reading-attempts-and-provenance-ownership.md).

reading owns its attempts (reading_reading) and knows nothing about receipts: it is given photo ids
and, optionally, a job to enqueue when the reading is done. Which service reads is a setting
(pm/decisions/reading-provider-is-a-setting.md). engine.py is pure and is what the bench can import.
"""
