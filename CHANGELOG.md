# Changelog

## v0.1.0 — 2026-11-04

First release. `receipt-gate` validates a donations CSV against the
CRA's official donation-receipt requirements for Canadian
registered charities before the receipts go out — the local,
no-upload pre-check a small charity runs on the spreadsheet it
already keeps.

- `check DONATIONS.csv [--year YYYY] [--as-of YYYY-MM-DD] [--json]`
  validates every row against the encoded rules: the 13 elements a
  CRA official receipt must carry (official-receipt statement,
  charity name/address, registration number, unique serial, place
  issued, donation date, issue date, donor name/address, gift
  amount, in-kind description and appraiser, advantage amount and
  description, eligible amount, and the canada.ca/charities-giving
  reference); registration-number shape (9 digits + RR + 4 digits)
  and consistency; split-receipting math recomputed to the cent;
  the 80% rule (advantage over 80% of the gift — not a gift, no
  receipt may be issued) as an ERROR and the 10% intention
  threshold as a WARNING; serial duplicates (numeric serials
  compared by value) as ERRORs and serial gaps as WARNINGs;
  issued-before-received dates; donation-year scoping with
  `--year`; future dates only against an explicit `--as-of` (the
  machine clock is never read silently); and the over-$1,000
  independent-appraisal guidance for gifts in kind.
- `register DONATIONS.csv [--year YYYY] [--json]` prints the
  year-end receipt register in serial order with per-receipt
  amount / advantage / eligible (eligible computed as
  amount − advantage), totals, per-donor totals, and any
  not-receiptable rows marked inline and excluded from the
  totals. The eligible total is labelled as the starting figure
  for the charity's T3010 work — not a filing.
- `rules [--json]` prints the encoded rule set with the basis for
  every check, stamped "Encoded rules, checked 2026-11 — verify
  against the CRA's current guidance for registered charities
  before relying on them."
- Every output carries the honesty line: receipt-gate is a
  checking aid — it does not issue receipts, and it is not tax
  advice. A PASS means the file satisfies the encoded rules,
  never a guarantee the CRA accepts the receipts.
- Agent-ready from birth: `--json` on every command, one object
  per run, `{"error": ...}` with exit 2 for input and usage
  errors (argparse included), exit 0 / 1 for clean / defective on
  `check`; SKILL.md documents the full rule table, the JSON
  shapes and the exit codes.
- Bundled examples: a 10-row donations CSV with nine planted
  defects — a split-receipting math error, an advantage-over-80%
  row, a duplicate serial, a serial gap, a malformed registration
  number, an issued-before-received receipt, an in-kind row
  missing its description, an over-10% advantage and an
  unappraised $2,500 gift in kind (6 errors, 3 warnings) — plus a
  clean 4-row file that passes and totals 2,250.00 / 30.00 /
  2,220.00 in the register. The charity and every donor are
  fictional.
- Pure Python 3.10+ standard library. No network code, no
  tracking; money is handled in integer cents, so the
  split-receipting math is exact to the cent.
