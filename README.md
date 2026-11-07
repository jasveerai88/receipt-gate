> **Merged into [charity-compliance](https://github.com/jasveerai88/charity-compliance)** — this tool now ships as the `receipt-gate` module of the charity-compliance suite (v1.0.0, also on PyPI). New work happens there; this repo stays as the original standalone release.

# receipt-gate

**Check a Canadian charity's donations spreadsheet against the CRA's official receipt rules — before the receipts go out.**

Canada has roughly 86,000 registered charities, and about 90% of them are small — a treasurer, a spreadsheet, and a stack of receipts to issue by hand. The CRA can revoke a charity's registration over defective donation receipts, and the defects are usually boring ones: a missing element, a wrong registration number, split-receipting math that doesn't add up, a serial number used twice. receipt-gate reads the donations CSV you already keep and catches those defects locally, in seconds, before a single receipt is printed.

It covers the donors the online platforms don't: CanadaHelps receipts only the donations made through CanadaHelps. The cash in the collection plate, the cheque in the mail and the e-transfer from a long-time donor still land in a spreadsheet — and that spreadsheet is what receipt-gate checks. (CanadaHelps itself puts manual receipting at 5–15 minutes per receipt; services that automate it, like NonprofitStream, charge around $39 CAD/month. receipt-gate is free, local, and never sees your donor list leave the machine.)

> **Encoded rules, checked 2026-11 — verify against the CRA's current guidance for registered charities before relying on them.**
>
> receipt-gate is a checking aid: it does not issue receipts, and it is not tax advice. A PASS means your file satisfies the rules encoded in this tool — never a guarantee the CRA accepts the receipts.

## What it checks

Every row of your CSV is one receipt-to-be. The tool encodes the elements the CRA requires on an official donation receipt, and the checks that follow from them.

**The 13 elements an official receipt must carry (encoded):**

| # | Element | CSV columns |
|---|---------|-------------|
| 1 | A statement that it is an official receipt for income tax purposes | `official_statement` |
| 2 | The charity's name and address, as recorded with the CRA | `charity_name`, `charity_address` |
| 3 | The charity's registration number | `registration_number` |
| 4 | A unique serial number for the receipt | `serial_number` |
| 5 | The place or locality where the receipt was issued | `place_issued` |
| 6 | The date the donation was received | `donation_date` |
| 7 | The date the receipt was issued | `receipt_date` |
| 8 | The donor's full name and address | `donor_name`, `donor_address` |
| 9 | The amount of the gift — cash amount, or deemed fair market value for a gift in kind | `amount` |
| 10 | For a gift in kind: a description of the gift, and the appraiser's name and address if appraised | `gift_description`, `appraiser_name`, `appraiser_address` |
| 11 | The amount of any advantage the donor received, and a description of it | `advantage_amount`, `advantage_description` |
| 12 | The eligible amount of the gift (amount − advantage) | `eligible_amount` |
| 13 | The name and website of the Canada Revenue Agency | `cra_website` — must be `canada.ca/charities-giving` |

**The checks (run `receipt-gate rules` for the full table with the basis of each):**

| Check | Severity | What it catches |
|-------|----------|-----------------|
| `required_missing` | error | A required element blank for the row's gift type — cash and in-kind rows need different fields; an advantage over $0 needs its description; an appraiser's name needs the appraiser's address |
| `registration_number_format` | error | Registration number not in the CRA shape: 9 digits + `RR` + 4 digits (spaces ignored; case checked as-is) |
| `registration_inconsistent` | error | Two different well-formed registration numbers in one file |
| `cra_website_wrong` | error | The CRA website element is not `canada.ca/charities-giving` |
| `statement_wording` | warning | The statement doesn't contain both "official receipt" and "income tax" — compare it against the CRA's wording |
| `eligible_mismatch` | error | Recorded eligible amount ≠ amount − advantage, recomputed to the cent |
| `advantage_over_80` | error | Advantage over 80% of the gift — under the CRA split-receipting rule this is not a gift and **no receipt may be issued** |
| `advantage_over_10` | warning | Advantage over 10% — the donor's intention to make a gift must be establishable; receiptable, but document it |
| `amount_not_positive` | error | Gift amount $0 or less, or a negative advantage |
| `serial_duplicate` | error | The same serial on two receipts (numeric serials compared by value — `0105` duplicates `105`) |
| `serial_gap` | warning | A serial number with no receipt in the file — voided, lost, or issued from another book; an audit question |
| `serial_non_numeric` | warning | Non-numeric serials present, so the gap check was skipped rather than guessed (duplicates still checked) |
| `issued_before_received` | error | Receipt issued before the donation was received |
| `donation_year_mismatch` | warning | With `--year`: a donation received in a different calendar year than the run |
| `date_in_future` | warning | With `--as-of`: a date after the as-of date (the tool never reads the machine clock on its own) |
| `appraiser_missing` | warning | Gift in kind over $1,000 with no appraiser named — CRA guidance is an independent appraisal |
| `charity_inconsistent` | warning | The charity's name varies between rows — usually a typo that will print on some receipts |

## Input format

One CSV, one row per receipt. Headers are matched case-insensitively with spaces, dashes and underscores ignored (`Serial Number`, `serial-number` and `serial_number` all work). Extra columns are ignored. Blank lines are skipped.

| Column | Required | Notes |
|--------|----------|-------|
| `serial_number` | yes | Unique per receipt |
| `charity_name` | yes | As recorded with the CRA |
| `charity_address` | yes | |
| `registration_number` | yes | e.g. `123456789RR0001` |
| `place_issued` | yes | Place or locality |
| `official_statement` | yes | The official-receipt statement |
| `cra_website` | yes | `canada.ca/charities-giving` |
| `donor_name` | yes | Donor's full name |
| `donor_address` | yes | CRA requires name **and** address |
| `donation_date` | yes | `YYYY-MM-DD` |
| `receipt_date` | yes | `YYYY-MM-DD` |
| `gift_type` | yes | `cash` or `in_kind` (also accepts `inkind`, `gift in kind`, …) |
| `amount` | yes | Cash amount, or deemed fair market value in kind. `$` and commas accepted |
| `advantage_amount` | no | Blank means $0 |
| `advantage_description` | when advantage > $0 | What the donor got back (the gala dinner, the golf day) |
| `eligible_amount` | yes | Must equal amount − advantage |
| `gift_description` | for `in_kind` | What the gift was |
| `appraiser_name` | no | If appraised |
| `appraiser_address` | when appraiser named | |

A file that can't be read at all — missing required columns, a ragged row, an amount or date that won't parse — is an input error (exit 2) naming the row and the field. There is never a traceback.

## Usage

```bash
# Validate the year's donations before receipts go out
python3 src/receipt_gate.py check donations.csv --year 2026

# Same, pinned to a date (flags anything dated after it)
python3 src/receipt_gate.py check donations.csv --year 2026 --as-of 2026-12-31

# The year-end register: serial order, totals, per-donor totals
python3 src/receipt_gate.py register donations.csv --year 2026

# The encoded rules, with the basis for every check
python3 src/receipt_gate.py rules
```

Exit codes: `check` — 0 clean (warnings may be listed), 1 any error, 2 input error. `register` and `rules` — 0 on success, 2 on input error.

The register's eligible column is **computed** (amount − advantage) — the register is the charity's own record of what was receipted; the recorded eligible column is judged by `check`, not repeated there. Rows that cannot be receipted at all (no usable amount, or an advantage over 80%) are listed inline as NOT RECEIPTABLE and excluded from the totals, with their face amount shown. The eligible total is the starting figure for the charity's T3010 receipted-gifts work — it is not a filing.

### For agents and scripts

Every command takes `--json` and prints exactly one JSON object. Input and usage errors print `{"error": "..."}` and exit 2 — including argparse errors. Check findings carry `row`, `serial`, `field`, `rule`, `severity`, `measured`, `limit` and `message`; the register's money values are exact decimal strings. See `SKILL.md` for the full schemas, the rule table and the honesty rules an agent must keep.

## Real runs (verbatim)

The bundled `examples/sample.csv` is the fictional Exampleton Community Food Bank's 2026 spreadsheet, with nine defects planted — one per row, counted by hand below. `examples/clean.csv` is the same charity's tidy file.

```console
$ python3 src/receipt_gate.py check examples/sample.csv --year 2026
receipt-gate v0.1.0 — check of sample.csv (10 row(s)) · year 2026
Encoded rules, checked 2026-11 — verify against the CRA's current guidance for registered charities before relying on them.

ERRORS — receipts that would be invalid, or that must not be issued (6):
  row 2 (serial 102) — eligible_mismatch: recorded eligible amount is 150.00 but amount − advantage = 200.00 − 60.00 = 140.00
  row 3 (serial 103) — advantage_over_80: advantage is 85.00 on a gift of 100.00 — over 80%: under the encoded CRA split-receipting rule this is not a gift and no receipt may be issued
  row 6 (serial 105) — serial_duplicate: serial 105 already appears on row 5 — every receipt must bear a unique serial number
  row 7 (serial 107) — registration_number_format: registration number '12345RR001' is not in the CRA format (limit: 9 digits + RR + 4 digits, e.g. 123456789RR0001)
  row 8 (serial 108) — issued_before_received: receipt was issued 2026-06-15, before the donation was received 2026-06-20
  row 9 (serial 109) — required_missing: gift_description is blank — the CRA element it carries would be missing from the receipt (required for a gift in kind)

WARNINGS — review before issuing (3):
  row 2 (serial 102) — advantage_over_10: advantage is 60.00 on a gift of 200.00 — over 10%: under the encoded CRA guidance the donor's intention to make a gift must be establishable
  row 10 (serial 110) — appraiser_missing: gift in kind of 2,500.00 names no appraiser — CRA guidance is that property over $1,000 be appraised by an independent appraiser
  file (serial 106) — serial_gap: serial 106 has no receipt in this file — a missing serial is an audit question (voided, lost, or issued from another book)

Verdict: FAIL — 6 error(s), 3 warning(s). Fix the errors before these receipts go out.
receipt-gate is a checking aid: it does not issue receipts, and it is not tax advice. A PASS means the file satisfies the rules encoded in this tool — never a guarantee the CRA accepts the receipts.
(exit code: 1)
```

```console
$ python3 src/receipt_gate.py check examples/clean.csv
receipt-gate v0.1.0 — check of clean.csv (4 row(s))
Encoded rules, checked 2026-11 — verify against the CRA's current guidance for registered charities before relying on them.

Verdict: PASS — no errors, no warnings. Every row satisfies the encoded rules.
receipt-gate is a checking aid: it does not issue receipts, and it is not tax advice. A PASS means the file satisfies the rules encoded in this tool — never a guarantee the CRA accepts the receipts.
(exit code: 0)
```

```console
$ python3 src/receipt_gate.py register examples/sample.csv --year 2026
receipt-gate v0.1.0 — receipt register for sample.csv · year 2026 (10 receipt(s) in scope)
Encoded rules, checked 2026-11 — verify against the CRA's current guidance for registered charities before relying on them.

  serial   date         donor                    type         amount  advantage   eligible
  101      2026-01-15   Nadia Rahman             cash         100.00       0.00     100.00
  102      2026-02-14   Omar Haddad              cash         200.00      60.00     140.00
  103      2026-03-01   Rajiv Menon              cash         100.00      85.00      15.00
    NOT RECEIPTABLE — excluded from totals: advantage exceeds 80% of the amount — under the encoded CRA split-receipting rule no receipt may be issued
  104      2026-03-10   Ingrid Johansson         in_kind      120.00       0.00     120.00
  105      2026-04-02   Chris Pelletier          cash          50.00       0.00      50.00
  105      2026-05-01   Erin O'Connell           cash          75.00       0.00      75.00
  107      2026-05-18   Ben Callahan             cash          80.00       0.00      80.00
  108      2026-06-20   Grace Liu                cash         250.00       0.00     250.00
  109      2026-07-08   Sofia Almeida            in_kind      300.00       0.00     300.00
  110      2026-08-14   Peter Novak              in_kind    2,500.00       0.00   2,500.00

TOTALS (9 receiptable receipt(s)): amount 3,675.00 · advantage 60.00 · eligible 3,615.00
Excluded from totals: 1 receipt(s), face amount 100.00 — see NOT RECEIPTABLE above.

Totals by donor (receiptable only):
  Ben Callahan — 1 receipt(s) · amount 80.00 · advantage 0.00 · eligible 80.00
  Chris Pelletier — 1 receipt(s) · amount 50.00 · advantage 0.00 · eligible 50.00
  Erin O'Connell — 1 receipt(s) · amount 75.00 · advantage 0.00 · eligible 75.00
  Grace Liu — 1 receipt(s) · amount 250.00 · advantage 0.00 · eligible 250.00
  Ingrid Johansson — 1 receipt(s) · amount 120.00 · advantage 0.00 · eligible 120.00
  Nadia Rahman — 1 receipt(s) · amount 100.00 · advantage 0.00 · eligible 100.00
  Omar Haddad — 1 receipt(s) · amount 200.00 · advantage 60.00 · eligible 140.00
  Peter Novak — 1 receipt(s) · amount 2,500.00 · advantage 0.00 · eligible 2,500.00
  Sofia Almeida — 1 receipt(s) · amount 300.00 · advantage 0.00 · eligible 300.00

Eligible amounts above are computed (amount − advantage); the recorded eligible column is judged by `check`, not repeated here.
The eligible total is the starting figure for the charity's T3010 receipted-gifts work — it is not a filing. receipt-gate is a checking aid: it does not issue receipts, and it is not tax advice.
(exit code: 0)
```

The register's eligible total for the clean file is **2,220.00** (amount 2,250.00 − advantage 30.00), and Sofia Almeida's two gifts total 800.00 / 30.00 / 770.00 — her second gift's advantage is exactly 10% of its amount, so it draws no intention warning.

## Tests

```bash
python3 -m unittest discover -s tests -v   # 60 tests
```

The expected numbers were derived by hand from the rule table before the tool was run, and the tests pin them: the sample's 6 errors / 3 warnings with exactly one finding per planted rule; the register totals (3,675.00 / 60.00 / 3,615.00, one row excluded); the clean file's zero findings and 2,220.00 eligible total; and the boundaries — advantage at exactly 80% passes the 80% rule while 80.01 fails it, exactly 10% draws no intention warning while 10.01 does, an in-kind gift at exactly $1,000.00 draws no appraisal warning while $1,000.01 does, a receipt issued on the donation date is fine while one day before is an error, and `0105` duplicates `105`.

## Who it's for

- **Treasurers and administrators of small Canadian charities** who receipt from a spreadsheet — especially the cash, cheque and e-transfer donations no platform receipts for them.
- **Bookkeepers** preparing a client's year-end: run `check`, fix the file, then take the `register` totals as the starting point for the T3010 work.
- **Our own engine:** Focus Brilliant uses receipt-gate for receipt-readiness audits for local nonprofits and churches — the same check, run before their receipting season, not after the CRA writes.

## Known limits

- **Encoded rules, not the CRA.** The rule set is stamped "checked 2026-11". CRA guidance changes; verify against the current guidance for registered charities before relying on it. This tool is a checking aid — it does not issue receipts and it is not tax advice.
- **The statement check is a phrase check.** It looks for "official receipt" and "income tax" in the statement column and warns when either is missing; it does not certify the wording is the CRA's prescribed wording — a human compares flagged statements.
- **One file, one charity, one run.** The consistency checks (one registration number, one charity name, serial sequence) assume the file is one charity's receipts for one receipt book. Split books or merged charities will draw warnings to sort out by hand.
- **Dates must be full dates.** Donations are sometimes recorded with only a year; this tool requires `YYYY-MM-DD` and treats anything else as an input error rather than guessing.
- **The $1,000 appraisal line is guidance.** It is encoded as a warning, never an error — whether a particular gift needed an independent appraisal is a judgment for the charity and its advisors.
- **Nothing here files anything.** The register's eligible total is a starting figure for the T3010, not a return, and receipt-gate never connects to the CRA.

## Privacy

Everything runs locally on files you point it at. No network calls, no telemetry, no uploads — a donor list is sensitive, and it stays on your machine.

## Support

receipt-gate is free and MIT-licensed. If it saves your charity a receipting headache, consider [sponsoring the maintainer](https://github.com/sponsors/jasveerai88) — sponsorship funds the free local-first tools in this series.

## Licence

MIT — see `LICENSE`.
