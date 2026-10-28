"""Colony reports built from PyRAT (read-only).

Each report module exposes ``build_report(...)`` returning plain rows and a
``write_xlsx(report, target)`` so the same code can back a CLI today and a
web "Reports" button later.
"""
