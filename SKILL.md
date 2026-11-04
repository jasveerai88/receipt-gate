---
name: receipt-gate
description: Validate a Canadian charity's donations CSV against the CRA's official donation-receipt requirements before receipts are issued — per-row findings (missing elements, registration-number shape, split-receipting math, the 80% and 10% advantage rules, serial duplicates and gaps, date logic) plus a year-end register with totals. Use before a charity issues receipts from a spreadsheet, or when preparing the T3010 starting figures. The rules are ENCODED, checked 2026-11 — a PASS means the file satisfies the encoded rules, never that the CRA will accept the receipts. The tool is a checking aid, not a receipt issuer and not tax advice.
---

# receipt-gate — agent skill

## Purpose

Small Canadian charities receipt donations from a spreadsheet —
the cash, cheques and e-transfers no donation platform covers.
The CRA can revoke a charity's registration over defective
receipts, and the defects are mechanical: a missing prescribed
element, a malformed registration number, split-receipting math
that doesn't recompute, a serial number used twice, a receipt
dated before the gift arrived. This tool checks the CSV against
the encoded CRA receipt rules *before* the receipts go out and
names every defective row, the rule that fired, and the measured
value against the limit. It also prints the year-end register —
serial, date, donor, amount, advantage, eligible, with totals —
whose eligible total is the starting figure for the charity's
T3010 work. Pure Python standard library; local only; reads the
CSV, writes nothing.

**The honesty core of this tool:** the CRA requirements are
encoded data, checked 2026-11, drawn from the CRA's published
guidance for registered charities. Guidance changes, and a
spreadsheet check cannot see the printed receipt, the actual
gift, or the donor's intention. A PASS means the file satisfies
the rules *encoded in this tool* — never present it as a
guarantee the CRA accepts the receipts, never call the tool tax
advice, and never say it issues receipts. It checks; humans
issue.

## When to use / not use

Use when:
- A charity is about to issue official donation receipts from
  a spreadsheet: run `check` first and fix every error in the
  sheet, not after the receipts are mailed.
- A receipting file needs a year-end register: run `register`
  for the serial-ordered list with totals and per-donor totals.
- An agent needs the requirements themselves: `rules` prints
  the 13 encoded elements and every check with its basis (text
  or JSON), so a spreadsheet can be built to satisfy them up
  front.

Do NOT use when:
- The question is whether the CRA *will* accept a receipt —
  that depends on current CRA guidance, the printed receipt,
  and facts about the gift this tool cannot see. PASS is a
  mechanical pre-flight, nothing more.
- Issuing receipts — the tool never generates receipt
  documents; it validates the data they would be printed from.
- Tax advice — whether a transfer is a gift, what an advantage
  is worth, or whether an appraisal was adequate are questions
  for the charity's advisors. The tool encodes the published
  thresholds; it does not judge the facts.
- The file mixes several charities or several receipt books —
  the consistency and serial checks assume one charity, one
  book; split the file first.

## Commands

```bash
# Validate a donations CSV (exit 0 clean / 1 any error / 2 input)
python3 src/receipt_gate.py check DONATIONS.csv
python3 src/receipt_gate.py check DONATIONS.csv --year 2026
python3 src/receipt_gate.py check DONATIONS.csv --year 2026 --as-of 2026-12-31
python3 src/receipt_gate.py check DONATIONS.csv --json

# Year-end register with totals (exit 0 / 2 input)
python3 src/receipt_gate.py register DONATIONS.csv [--year 2026] [--json]

# Print the encoded elements and checks with their bases (exit 0)
python3 src/receipt_gate.py rules [--json]
```

Every command accepts `--json` and prints exactly one JSON
object. Input and usage errors — including argparse errors —
print `{"error": "..."}` and exit 2. The tool never reads the
machine clock: future dates are flagged only against an
explicit `--as-of`, and year scoping only with `--year`.

## Input format

One CSV, one row per receipt. Headers are matched after
stripping non-alphanumerics and lowercasing, so `Serial
Number`, `serial-number` and `serial_number` are the same
column. Extra columns are ignored; blank lines are skipped; a
row with more values than the header is an input error (exit
2) naming the row.

Required columns (an absent one is an exit-2 error naming it):
`serial_number`, `charity_name`, `charity_address`,
`registration_number`, `place_issued`, `official_statement`,
`cra_website`, `donor_name`, `donor_address`, `donation_date`,
`receipt_date`, `gift_type`, `amount`, `eligible_amount`.

Optional columns: `advantage_amount` (blank = $0),
`advantage_description` (required when the advantage is over
$0), `gift_description` (required for `in_kind`),
`appraiser_name`, `appraiser_address` (required when an
appraiser is named).

Values: dates are strict `YYYY-MM-DD` and must be real calendar
dates; money accepts `$` and commas and at most two decimal
places, and is handled in integer cents; `gift_type` accepts
`cash` and the in-kind spellings (`in_kind`, `inkind`,
`gift in kind`, …). An unparseable amount, date or gift type
is an exit-2 input error naming the row and field — never a
traceback.

## The encoded rules (state them when you report results)

The 13 elements an official receipt must carry, encoded from
the CRA's published list: (1) the official-receipt statement;
(2) charity name and address; (3) registration number;
(4) unique serial number; (5) place issued; (6) date the
donation was received; (7) date the receipt was issued;
(8) donor's full name and address; (9) the gift amount (cash
amount, or deemed fair market value in kind); (10) for gifts
in kind, a description of the gift and the appraiser's name
and address if appraised; (11) the amount and description of
any advantage; (12) the eligible amount (amount − advantage);
(13) the CRA's name and website, canada.ca/charities-giving.

| Rule | Severity | Basis |
|------|----------|-------|
| `required_missing` | error | An official receipt must carry every prescribed element for its gift type; cash and in-kind rows have different required columns, an advantage over $0 needs its description, an appraiser's name needs the appraiser's address. |
| `registration_number_format` | error | CRA registration numbers are the 9-digit business number + `RR` + a 4-digit reference (e.g. 123456789RR0001). Spaces in the value are ignored; letter case is checked as-is — a lowercase `rr` fails. |
| `registration_inconsistent` | error | One charity, one registration number. Two different well-formed numbers in one file means merged data or wrong receipts. Malformed numbers are judged by the format rule instead. |
| `cra_website_wrong` | error | The receipt must show the CRA's name and website: canada.ca/charities-giving (scheme and trailing slash tolerated). Any other value is not that element. |
| `statement_wording` | warning | The statement must say the receipt is an official receipt for income tax purposes; the checker looks for both phrases and warns when either is missing, for a human to compare against the CRA's wording. |
| `eligible_mismatch` | error | Split receipting: eligible = amount − advantage, recomputed to the cent against the recorded eligible amount. |
| `advantage_over_80` | error | CRA split-receipting rule: an advantage over 80% of the gift means the transfer is not a gift — no receipt may be issued at all. |
| `advantage_over_10` | warning | CRA split-receipting guidance: an advantage over 10% puts the donor's intention to make a gift in question; the charity must be able to establish it. Receiptable, but document it. |
| `amount_not_positive` | error | A gift amount of $0 or less cannot be receipted; an advantage cannot be negative. |
| `serial_duplicate` | error | Every receipt bears a unique serial number. Numeric serials are compared by value (0105 duplicates 105); the second and later occurrences are flagged. |
| `serial_gap` | warning | A serial with no receipt in the file is an audit question — voided, lost, or issued from another book. One finding per missing number. |
| `serial_non_numeric` | warning | The gap check needs an all-numeric run; with non-numeric serials present it is skipped rather than guessed. Duplicates are still checked. |
| `issued_before_received` | error | The issued date must be on or after the date the donation was received. Issued on the day is fine. |
| `donation_year_mismatch` | warning | With `--year`: a donation received in another calendar year belongs to that year's receipts. |
| `date_in_future` | warning | With `--as-of`: a donation or receipt date after the as-of date. Never fires without `--as-of`. |
| `appraiser_missing` | warning | CRA guidance: property over $1,000 should be appraised by an independent appraiser. An in-kind gift over $1,000 with no appraiser named is guidance, not a defective receipt. |
| `charity_inconsistent` | warning | The charity's name should be identical on every row; a variation is usually a typo that will print on some receipts. |

Boundaries (pinned by tests): advantage at exactly 80% is
receiptable (the over-10 warning still fires); 80.01% is not.
Advantage at exactly 10% draws no warning; 10.01% does. The
appraisal guidance fires above $1,000.00, not at it.

## Output JSON schema (`--json`)

`check`:
```json
{
  "tool": "receipt-gate", "version": "0.1.0", "mode": "check",
  "source": "donations.csv", "rows": 10,
  "year": 2026, "as_of": null,
  "findings": [
    {"row": 2, "serial": "102", "field": "eligible_amount",
     "rule": "eligible_mismatch", "severity": "error",
     "measured": "eligible 150.00",
     "limit": "eligible 140.00 (= 200.00 - 60.00)",
     "message": "recorded eligible amount is 150.00 but amount − advantage = 200.00 − 60.00 = 140.00"}
  ],
  "summary": {"errors": 6, "warnings": 3,
              "by_rule": {"eligible_mismatch": 1}},
  "verdict": "FAIL",
  "note": null,
  "rules_note": "Encoded rules, checked 2026-11 — verify against the CRA's current guidance for registered charities before relying on them.",
  "disclaimer": "receipt-gate is a checking aid: it does not issue receipts, and it is not tax advice. ..."
}
```
`row` is the 1-based data-row number (null for file-level
findings such as serial gaps); `serial` is the row's serial
(null when not applicable). Findings are sorted errors and
warnings together by row, file-level findings last.

`register`: `entries` (serial order; each with `serial`,
`donation_date`, `donor_name`, `gift_type`, `amount`,
`advantage`, `eligible` — eligible computed as
amount − advantage, money as exact decimal strings like
`"3615.00"`), `excluded` (rows that cannot be receipted, each
with its `excluded_reason` and face figures), `totals`
(`count`, `amount`, `advantage`, `eligible` over receiptable
rows only), `by_donor` (same totals per donor, receiptable
only), `rows_in_scope`, `note`, and the same `rules_note` /
`disclaimer`.

`rules`: `elements` (the 13, each with `csv_columns` and
`applies_to`) and `checks` (each with `rule`, `severity`,
`basis`).

Errors (any command): `{"error": "..."}` with exit 2.

## Exit codes

- `check`: 0 = no errors (warnings may be present),
  1 = at least one error, 2 = the input could not be read or
  the command line was invalid.
- `register`, `rules`: 0 = success, 2 = input/usage error.

## Limits & honesty rules the agent must respect

- **Never present a PASS as CRA acceptance.** The encoded
  rules were checked 2026-11 against published guidance; the
  CRA's current guidance governs. Always carry the rules
  stamp and the disclaimer when reporting results.
- **Never call the tool tax advice or a receipt issuer.** It
  checks a spreadsheet; it issues nothing and advises nothing.
- **The register's eligible total is a starting figure** for
  the charity's T3010 work — not a filing, not a return, not
  an amount the CRA has seen.
- **Warnings are not failures, and errors are not
  suggestions.** An error means the receipt would be invalid
  or must not be issued as it stands; a warning means a human
  should look before issuing. Report both counts, by rule.
- **Thresholds are the encoded rules, stated with their
  basis:** 80% (not a gift), 10% (intention questioned),
  $1,000 (appraisal guidance). Do not restate them as the
  tool's opinion, and do not soften the 80% rule — over it,
  no receipt may be issued.
- **The statement check is a phrase check.** It does not
  certify the CRA's prescribed wording; flagged statements go
  to a human.
- **No clock, no network.** The tool never reads the machine
  clock (future checks need `--as-of`) and never sends the
  donor data anywhere. Do not pipe the CSV to an external
  service to "double-check" — the donor list stays local.
