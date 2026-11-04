# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** receipt-gate's promise is
  "clone and run". Pull requests that add a third-party dependency
  will not be merged.
- **Local only.** No network calls, no telemetry, no uploads of user
  files. A donations file is some of the most sensitive data a small
  charity holds; it never leaves the machine.
- **The rules are data, and they stay honest.** Every check lives
  in the `CHECKS` table and every prescribed element in the
  `ELEMENTS` table in `src/receipt_gate.py`, and the README,
  SKILL.md and CHANGELOG state the same rules. Any change to a
  check, a threshold (80%, 10%, the $1,000 appraisal guidance) or
  the element list is a behaviour change: it needs all three
  documents, the changelog and the tests updated together, with
  the CRA source for the new value named in the pull request.
  Rules must never be presented — in code, docs or output — as a
  substitute for the CRA's current guidance; they are encoded
  rules with a "checked" date.
- **A PASS must never be worded as CRA acceptance.** The honesty
  lines in the reports are load-bearing. Wording changes that
  soften "satisfies the encoded rules" into "the CRA will accept
  these receipts" will not be merged. The tool is a checking aid,
  not a receipt issuer and not tax advice — that sentence stays
  in every output.
- **Boundaries are pinned by hand.** A new or changed threshold
  needs tests at the threshold (passes) and one step past it
  (fails), with the expected counts derived from the rule table —
  not copied from the tool's own output. The bundled sample's
  6-error / 3-warning findings and its register totals
  (amount 3,675.00 · advantage 60.00 · eligible 3,615.00) were
  counted by hand when the file was built; if a change moves
  them, the recount must be shown.

## Getting started

```bash
git clone https://github.com/jasveerai88/receipt-gate
cd receipt-gate
python3 -m unittest discover -s tests -v
python3 src/receipt_gate.py check examples/sample.csv --year 2026
python3 src/receipt_gate.py register examples/sample.csv --year 2026
python3 src/receipt_gate.py rules
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if the
   CLI output changes.
