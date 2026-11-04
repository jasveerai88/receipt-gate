#!/usr/bin/env python3
"""Tests for receipt-gate. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

The expected numbers are worked BY HAND from the encoded
rules in src/receipt_gate.py (and stated in the README), not
copied out of the tool's own output:

  Sample (examples/sample.csv, 10 rows — one planted defect
  family per row, written out in the README):
    errors 6 — row 2 eligible_mismatch (recorded 150.00,
               computed 200.00 − 60.00 = 140.00),
               row 3 advantage_over_80 (85.00 on 100.00),
               row 6 serial_duplicate (serial 105 on rows
               5 and 6), row 7 registration_number_format
               (12345RR001), row 8 issued_before_received
               (issued 2026-06-15, received 2026-06-20),
               row 9 required_missing (gift_description on
               an in-kind row)
    warnings 3 — row 2 advantage_over_10 (60.00 on 200.00),
               serial_gap (serial 106 absent),
               row 10 appraiser_missing (in-kind 2,500.00,
               no appraiser)
    register (--year 2026): 9 receiptable rows, the serial
               103 row excluded (advantage over 80%); totals
               amount 3,675.00, advantage 60.00, eligible
               3,615.00 (sum of the per-row amount − advantage
               over the 9 receiptable rows, added by hand)

  Clean (examples/clean.csv, 4 rows): no findings, exit 0;
  register totals amount 2,250.00, advantage 30.00, eligible
  2,220.00; Sofia Almeida's two gifts total 800.00 / 30.00 /
  770.00. Row 202's advantage is exactly 10% of its amount —
  at the threshold, so no intention warning.

Boundaries are pinned exactly: advantage at exactly 80%
passes the 80% rule, 80.01 fails it; at exactly 10% no
intention warning, at 10.01 there is one; the appraisal
guidance at exactly $1,000.00 does not fire, at $1,000.01 it
does; a receipt issued ON the donation date is fine, one day
before is an error.
"""
import csv as csv_mod
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "receipt_gate.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import receipt_gate as rg  # noqa: E402

HEADER = ["serial_number", "charity_name", "charity_address",
          "registration_number", "place_issued",
          "official_statement", "cra_website", "donor_name",
          "donor_address", "donation_date", "receipt_date",
          "gift_type", "amount", "advantage_amount",
          "advantage_description", "eligible_amount",
          "gift_description", "appraiser_name",
          "appraiser_address"]


def run_cli(*args):
    return subprocess.run([sys.executable, str(SRC), *args],
                          capture_output=True, text=True)


def write_tmp(content, suffix=".csv"):
    f = tempfile.NamedTemporaryFile("w", suffix=suffix,
                                    delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def csv_of(*rows):
    buf = io.StringIO()
    writer = csv_mod.writer(buf)
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow([row.get(col, "") for col in HEADER])
    return buf.getvalue()


def good_row(**overrides):
    row = {
        "serial_number": "1",
        "charity_name": "Exampleton Community Food Bank",
        "charity_address": "123 Example Street, Kelowna, "
                           "BC V1Y 0A0",
        "registration_number": "123456789RR0001",
        "place_issued": "Kelowna, BC",
        "official_statement": "Official receipt for income "
                              "tax purposes",
        "cra_website": "canada.ca/charities-giving",
        "donor_name": "Nadia Rahman",
        "donor_address": "45 Maple Crescent, Kelowna, "
                         "BC V1Y 3B2",
        "donation_date": "2026-01-15",
        "receipt_date": "2026-02-01",
        "gift_type": "cash",
        "amount": "100.00",
        "advantage_amount": "",
        "advantage_description": "",
        "eligible_amount": "100.00",
        "gift_description": "",
        "appraiser_name": "",
        "appraiser_address": "",
    }
    row.update(overrides)
    return row


def check_json(*rows, extra=()):
    path = write_tmp(csv_of(*rows))
    proc = run_cli("check", path, "--json", *extra)
    return proc, json.loads(proc.stdout)


def rules_of(findings):
    return [f["rule"] for f in findings]


class TestBundledSamples(unittest.TestCase):
    def test_sample_counts(self):
        proc = run_cli("check", str(EXAMPLES / "sample.csv"),
                       "--year", "2026", "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(data["summary"]["errors"], 6)
        self.assertEqual(data["summary"]["warnings"], 3)
        self.assertEqual(data["verdict"], "FAIL")
        self.assertEqual(
            data["summary"]["by_rule"],
            {"advantage_over_10": 1, "advantage_over_80": 1,
             "appraiser_missing": 1, "eligible_mismatch": 1,
             "issued_before_received": 1,
             "registration_number_format": 1,
             "required_missing": 1, "serial_duplicate": 1,
             "serial_gap": 1})

    def test_sample_findings_are_where_expected(self):
        proc = run_cli("check", str(EXAMPLES / "sample.csv"),
                       "--year", "2026", "--json")
        data = json.loads(proc.stdout)
        by_rule = {}
        for f in data["findings"]:
            by_rule.setdefault(f["rule"], []).append(f)
        self.assertEqual(by_rule["eligible_mismatch"][0]["row"],
                         2)
        self.assertIn("140.00",
                      by_rule["eligible_mismatch"][0]["message"])
        self.assertEqual(by_rule["advantage_over_80"][0]["row"],
                         3)
        self.assertEqual(by_rule["serial_duplicate"][0]["row"],
                         6)
        self.assertEqual(
            by_rule["registration_number_format"][0]["row"], 7)
        self.assertEqual(
            by_rule["issued_before_received"][0]["row"], 8)
        missing = by_rule["required_missing"][0]
        self.assertEqual(missing["row"], 9)
        self.assertEqual(missing["field"], "gift_description")
        gap = by_rule["serial_gap"][0]
        self.assertIsNone(gap["row"])
        self.assertEqual(gap["serial"], "106")

    def test_sample_text_run(self):
        proc = run_cli("check", str(EXAMPLES / "sample.csv"),
                       "--year", "2026")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Verdict: FAIL — 6 error(s), "
                      "3 warning(s)", proc.stdout)
        self.assertIn("not tax advice", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)

    def test_clean_passes(self):
        proc = run_cli("check", str(EXAMPLES / "clean.csv"),
                       "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(data["findings"], [])
        self.assertEqual(data["verdict"], "PASS")

    def test_summary_recounts_against_findings(self):
        proc = run_cli("check", str(EXAMPLES / "sample.csv"),
                       "--json")
        data = json.loads(proc.stdout)
        recount = {}
        for f in data["findings"]:
            recount[f["rule"]] = recount.get(f["rule"], 0) + 1
        self.assertEqual(data["summary"]["by_rule"], recount)
        self.assertEqual(
            data["summary"]["errors"]
            + data["summary"]["warnings"],
            len(data["findings"]))


class TestBoundaries(unittest.TestCase):
    def test_advantage_exactly_80_percent_is_receiptable(self):
        _, data = check_json(good_row(
            amount="100.00", advantage_amount="80.00",
            advantage_description="Banquet", 
            eligible_amount="20.00"))
        self.assertNotIn("advantage_over_80",
                         rules_of(data["findings"]))
        # ...but 80% is well over 10%, so the intention
        # warning still fires.
        self.assertIn("advantage_over_10",
                      rules_of(data["findings"]))
        self.assertEqual(data["summary"]["errors"], 0)

    def test_advantage_just_over_80_percent_fails(self):
        _, data = check_json(good_row(
            amount="100.00", advantage_amount="80.01",
            advantage_description="Banquet",
            eligible_amount="19.99"))
        self.assertIn("advantage_over_80",
                      rules_of(data["findings"]))
        self.assertNotIn("advantage_over_10",
                         rules_of(data["findings"]))

    def test_advantage_exactly_10_percent_no_warning(self):
        _, data = check_json(good_row(
            amount="100.00", advantage_amount="10.00",
            advantage_description="Dinner",
            eligible_amount="90.00"))
        self.assertEqual(data["findings"], [])

    def test_advantage_just_over_10_percent_warns(self):
        _, data = check_json(good_row(
            amount="100.00", advantage_amount="10.01",
            advantage_description="Dinner",
            eligible_amount="89.99"))
        self.assertEqual(rules_of(data["findings"]),
                         ["advantage_over_10"])
        self.assertEqual(data["summary"]["errors"], 0)

    def test_eligible_mismatch_by_one_cent(self):
        _, data = check_json(good_row(
            amount="100.00", advantage_amount="20.00",
            advantage_description="Dinner",
            eligible_amount="80.01"))
        self.assertIn("eligible_mismatch",
                      rules_of(data["findings"]))

    def test_eligible_exact_passes(self):
        _, data = check_json(good_row(
            amount="100.00", advantage_amount="20.00",
            advantage_description="Dinner",
            eligible_amount="80.00"))
        self.assertNotIn("eligible_mismatch",
                         rules_of(data["findings"]))

    def test_appraisal_guidance_boundary(self):
        base = dict(gift_type="in_kind",
                    gift_description="A grand piano")
        _, at = check_json(good_row(amount="1000.00",
                                    eligible_amount="1000.00",
                                    **base))
        self.assertNotIn("appraiser_missing",
                         rules_of(at["findings"]))
        _, over = check_json(good_row(amount="1000.01",
                                      eligible_amount="1000.01",
                                      **base))
        self.assertIn("appraiser_missing",
                      rules_of(over["findings"]))

    def test_issued_on_donation_date_is_fine(self):
        _, data = check_json(good_row(receipt_date="2026-01-15"))
        self.assertNotIn("issued_before_received",
                         rules_of(data["findings"]))

    def test_issued_one_day_before_is_an_error(self):
        _, data = check_json(good_row(receipt_date="2026-01-14"))
        self.assertIn("issued_before_received",
                      rules_of(data["findings"]))


class TestSerials(unittest.TestCase):
    def test_two_missing_serials_two_gap_findings(self):
        _, data = check_json(good_row(serial_number="10"),
                             good_row(serial_number="13"))
        gaps = [f for f in data["findings"]
                if f["rule"] == "serial_gap"]
        self.assertEqual([g["serial"] for g in gaps],
                         ["11", "12"])

    def test_leading_zero_duplicate(self):
        _, data = check_json(good_row(serial_number="0105"),
                             good_row(serial_number="105"))
        dups = [f for f in data["findings"]
                if f["rule"] == "serial_duplicate"]
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["row"], 2)

    def test_triple_duplicate_flags_rows_two_and_three(self):
        rows = [good_row(serial_number="7") for _ in range(3)]
        _, data = check_json(*rows)
        dups = [f for f in data["findings"]
                if f["rule"] == "serial_duplicate"]
        self.assertEqual([d["row"] for d in dups], [2, 3])

    def test_non_numeric_serial_skips_gap_check(self):
        _, data = check_json(good_row(serial_number="A-1"),
                             good_row(serial_number="3"))
        found = rules_of(data["findings"])
        self.assertIn("serial_non_numeric", found)
        self.assertNotIn("serial_gap", found)

    def test_blank_serial_is_required_missing_not_a_dup(self):
        _, data = check_json(good_row(serial_number=""),
                             good_row(serial_number=""))
        found = rules_of(data["findings"])
        self.assertEqual(found.count("required_missing"), 2)
        self.assertNotIn("serial_duplicate", found)


class TestRowRules(unittest.TestCase):
    def test_blank_donor_address_is_required_missing(self):
        _, data = check_json(good_row(donor_address=""))
        miss = [f for f in data["findings"]
                if f["rule"] == "required_missing"]
        self.assertEqual([f["field"] for f in miss],
                         ["donor_address"])
        self.assertEqual(data["summary"]["errors"], 1)

    def test_in_kind_needs_a_gift_description(self):
        _, data = check_json(good_row(gift_type="in_kind"))
        miss = [f for f in data["findings"]
                if f["rule"] == "required_missing"]
        self.assertEqual([f["field"] for f in miss],
                         ["gift_description"])

    def test_cash_row_needs_no_gift_description(self):
        _, data = check_json(good_row())
        self.assertEqual(data["findings"], [])

    def test_advantage_needs_a_description(self):
        _, data = check_json(good_row(
            advantage_amount="5.00", eligible_amount="95.00"))
        miss = [f for f in data["findings"]
                if f["rule"] == "required_missing"]
        self.assertEqual([f["field"] for f in miss],
                         ["advantage_description"])

    def test_appraiser_name_needs_the_address(self):
        _, data = check_json(good_row(
            gift_type="in_kind", gift_description="A piano",
            amount="400.00", eligible_amount="400.00",
            appraiser_name="Linda Cho"))
        miss = [f for f in data["findings"]
                if f["rule"] == "required_missing"]
        self.assertEqual([f["field"] for f in miss],
                         ["appraiser_address"])

    def test_registration_number_shapes(self):
        for bad in ("12345RR001", "12345678RR0001",
                    "123456789rr0001", "123456789XX0001",
                    "123456789RR001"):
            _, data = check_json(good_row(
                registration_number=bad))
            self.assertIn("registration_number_format",
                          rules_of(data["findings"]), bad)
        _, data = check_json(good_row(
            registration_number="123456789RR0001"))
        self.assertNotIn("registration_number_format",
                         rules_of(data["findings"]))

    def test_registration_number_with_spaces_is_fine(self):
        _, data = check_json(good_row(
            registration_number="123456789 RR 0001"))
        self.assertNotIn("registration_number_format",
                         rules_of(data["findings"]))

    def test_two_wellformed_numbers_are_inconsistent(self):
        _, data = check_json(
            good_row(serial_number="1"),
            good_row(serial_number="2",
                     registration_number="987654321RR0002"))
        self.assertIn("registration_inconsistent",
                      rules_of(data["findings"]))

    def test_malformed_second_number_is_not_inconsistent(self):
        _, data = check_json(
            good_row(serial_number="1"),
            good_row(serial_number="2",
                     registration_number="12345RR001"))
        found = rules_of(data["findings"])
        self.assertIn("registration_number_format", found)
        self.assertNotIn("registration_inconsistent", found)

    def test_charity_name_variation_warns(self):
        _, data = check_json(
            good_row(serial_number="1"),
            good_row(serial_number="2",
                     charity_name="Exampleton Food Bank"))
        self.assertIn("charity_inconsistent",
                      rules_of(data["findings"]))

    def test_cra_website_variants(self):
        _, data = check_json(good_row(
            cra_website="https://canada.ca/charities-giving/"))
        self.assertEqual(data["findings"], [])
        _, data = check_json(good_row(
            cra_website="canada.ca"))
        self.assertIn("cra_website_wrong",
                      rules_of(data["findings"]))
        _, data = check_json(good_row(cra_website=""))
        found = rules_of(data["findings"])
        self.assertIn("required_missing", found)
        self.assertNotIn("cra_website_wrong", found)

    def test_statement_wording(self):
        _, data = check_json(good_row(
            official_statement="Donation receipt"))
        self.assertIn("statement_wording",
                      rules_of(data["findings"]))
        _, data = check_json(good_row())
        self.assertNotIn("statement_wording",
                         rules_of(data["findings"]))

    def test_amount_not_positive(self):
        for amount, eligible in (("0.00", "0.00"),
                                 ("-5.00", "-5.00")):
            _, data = check_json(good_row(
                amount=amount, eligible_amount=eligible))
            self.assertIn("amount_not_positive",
                          rules_of(data["findings"]), amount)

    def test_negative_advantage(self):
        _, data = check_json(good_row(
            advantage_amount="-1.00", eligible_amount="101.00"))
        self.assertIn("amount_not_positive",
                      rules_of(data["findings"]))

    def test_blank_eligible_is_missing_not_mismatched(self):
        _, data = check_json(good_row(eligible_amount=""))
        found = rules_of(data["findings"])
        self.assertIn("required_missing", found)
        self.assertNotIn("eligible_mismatch", found)

    def test_year_mismatch_only_with_year_flag(self):
        row = good_row(donation_date="2025-06-01",
                       receipt_date="2025-06-02")
        _, data = check_json(row)
        self.assertNotIn("donation_year_mismatch",
                         rules_of(data["findings"]))
        _, data = check_json(row, extra=("--year", "2026"))
        self.assertIn("donation_year_mismatch",
                      rules_of(data["findings"]))
        _, data = check_json(row, extra=("--year", "2025"))
        self.assertNotIn("donation_year_mismatch",
                         rules_of(data["findings"]))

    def test_as_of_future_dates(self):
        row = good_row(donation_date="2026-01-15",
                       receipt_date="2026-02-01")
        _, data = check_json(row)
        self.assertNotIn("date_in_future",
                         rules_of(data["findings"]))
        _, data = check_json(row, extra=("--as-of", "2026-01-20"))
        future = [f for f in data["findings"]
                  if f["rule"] == "date_in_future"]
        self.assertEqual([f["field"] for f in future],
                         ["receipt_date"])
        _, data = check_json(row, extra=("--as-of", "2026-01-01"))
        future = [f for f in data["findings"]
                  if f["rule"] == "date_in_future"]
        self.assertEqual(len(future), 2)


class TestRegister(unittest.TestCase):
    def register_json(self, path, *extra):
        proc = run_cli("register", path, "--json", *extra)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        return json.loads(proc.stdout)

    def test_sample_register_totals(self):
        data = self.register_json(str(EXAMPLES / "sample.csv"),
                                  "--year", "2026")
        self.assertEqual(data["totals"],
                         {"count": 9, "amount": "3675.00",
                          "advantage": "60.00",
                          "eligible": "3615.00"})
        self.assertEqual(len(data["entries"]), 9)
        self.assertEqual(len(data["excluded"]), 1)
        self.assertEqual(data["excluded"][0]["serial"], "103")
        self.assertIn("80%", data["excluded"][0]
                      ["excluded_reason"])

    def test_clean_register_totals_and_by_donor(self):
        data = self.register_json(str(EXAMPLES / "clean.csv"))
        self.assertEqual(data["totals"],
                         {"count": 4, "amount": "2250.00",
                          "advantage": "30.00",
                          "eligible": "2220.00"})
        by_donor = {d["donor_name"]: d
                    for d in data["by_donor"]}
        sofia = by_donor["Sofia Almeida"]
        self.assertEqual(
            (sofia["count"], sofia["amount"],
             sofia["advantage"], sofia["eligible"]),
            (2, "800.00", "30.00", "770.00"))

    def test_register_year_filter(self):
        rows = [good_row(serial_number="1"),
                good_row(serial_number="2",
                         donation_date="2025-06-01",
                         receipt_date="2025-06-02")]
        path = write_tmp(csv_of(*rows))
        data = self.register_json(path, "--year", "2026")
        self.assertEqual(data["totals"]["count"], 1)
        self.assertEqual(data["rows_in_scope"], 1)
        data = self.register_json(path)
        self.assertEqual(data["totals"]["count"], 2)

    def test_register_sorts_by_serial(self):
        rows = [good_row(serial_number="3"),
                good_row(serial_number="1"),
                good_row(serial_number="2")]
        path = write_tmp(csv_of(*rows))
        data = self.register_json(path)
        self.assertEqual([e["serial"] for e in data["entries"]],
                         ["1", "2", "3"])

    def test_register_uses_computed_eligible(self):
        # The recorded eligible says 999.00; the register must
        # show the computed 100.00 - 0.00 = 100.00. (check is
        # where the mismatch is judged.)
        path = write_tmp(csv_of(good_row(
            eligible_amount="999.00")))
        data = self.register_json(path)
        self.assertEqual(data["entries"][0]["eligible"],
                         "100.00")
        self.assertEqual(data["totals"]["eligible"], "100.00")

    def test_register_header_only_file(self):
        path = write_tmp(csv_of())
        data = self.register_json(path)
        self.assertEqual(data["totals"]["count"], 0)
        self.assertIsNotNone(data["note"])


class TestRulesCommand(unittest.TestCase):
    def test_rules_text(self):
        proc = run_cli("rules")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("advantage_over_80", proc.stdout)
        self.assertIn("canada.ca/charities-giving",
                      proc.stdout)
        self.assertIn("not tax advice", proc.stdout)

    def test_rules_json(self):
        proc = run_cli("rules", "--json")
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(len(data["elements"]), 13)
        rules = {c["rule"] for c in data["checks"]}
        self.assertIn("serial_gap", rules)
        self.assertIn("eligible_mismatch", rules)


class TestInputErrors(unittest.TestCase):
    def assert_clean_error(self, proc, *needles):
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)
        for needle in needles:
            self.assertIn(needle, proc.stdout)

    def test_missing_file(self):
        proc = run_cli("check", "/nonexistent/donations.csv")
        self.assert_clean_error(proc, "ERROR:", "file not found")

    def test_missing_file_json(self):
        proc = run_cli("check", "/nonexistent/donations.csv",
                       "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(list(json.loads(proc.stdout)), ["error"])

    def test_wrong_suffix(self):
        proc = run_cli("check", write_tmp("{}", suffix=".json"))
        self.assert_clean_error(proc, "expected a .csv file")

    def test_empty_file(self):
        proc = run_cli("check", write_tmp(""))
        self.assert_clean_error(proc, "empty CSV")

    def test_missing_column_is_named(self):
        header = [c for c in HEADER if c != "donor_address"]
        buf = io.StringIO()
        writer = csv_mod.writer(buf)
        writer.writerow(header)
        writer.writerow(["x"] * len(header))
        proc = run_cli("check", write_tmp(buf.getvalue()))
        self.assert_clean_error(proc, "'donor_address'")

    def test_ragged_row(self):
        text = ",".join(HEADER) + "\n" \
            + ",".join(["x"] * (len(HEADER) + 1)) + "\n"
        proc = run_cli("check", write_tmp(text))
        self.assert_clean_error(proc, "row 1",
                                "more values than the header")

    def test_unparseable_amount_names_the_row(self):
        proc = run_cli("check", write_tmp(csv_of(
            good_row(serial_number="1"),
            good_row(serial_number="2", amount="abc"))))
        self.assert_clean_error(proc, "row 2", "'amount'")

    def test_three_decimal_amount_is_an_error(self):
        proc = run_cli("check", write_tmp(csv_of(
            good_row(amount="10.005"))))
        self.assert_clean_error(proc, "row 1",
                                "two decimal places")

    def test_unparseable_and_impossible_dates(self):
        proc = run_cli("check", write_tmp(csv_of(
            good_row(donation_date="15/01/2026"))))
        self.assert_clean_error(proc, "row 1", "YYYY-MM-DD")
        proc = run_cli("check", write_tmp(csv_of(
            good_row(donation_date="2026-02-30"))))
        self.assert_clean_error(proc, "row 1",
                                "not a real calendar date")

    def test_unknown_gift_type(self):
        proc = run_cli("check", write_tmp(csv_of(
            good_row(gift_type="cheque"))))
        self.assert_clean_error(proc, "row 1", "'gift_type'")

    def test_bad_year_in_json_mode_is_a_json_error(self):
        proc = run_cli("check", str(EXAMPLES / "clean.csv"),
                       "--year", "26", "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(list(json.loads(proc.stdout)), ["error"])

    def test_no_subcommand_in_json_mode(self):
        proc = run_cli("--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(list(json.loads(proc.stdout)), ["error"])

    def test_header_only_file_passes_vacuously(self):
        proc = run_cli("check", write_tmp(csv_of()), "--json")
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["findings"], [])
        self.assertIn("vacuous", data["note"])

    def test_extra_columns_are_tolerated(self):
        buf = io.StringIO()
        writer = csv_mod.writer(buf)
        writer.writerow(HEADER + ["notes"])
        row = good_row()
        writer.writerow([row.get(col, "") for col in HEADER]
                        + ["treasurer note"])
        proc = run_cli("check", write_tmp(buf.getvalue()),
                       "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["findings"],
                         [])


class TestUnits(unittest.TestCase):
    def test_money_parse_and_format(self):
        self.assertEqual(rg._parse_money("$1,000.55", "amount", 1),
                         100055)
        self.assertEqual(rg._parse_money("100.5", "amount", 1),
                         10050)
        self.assertEqual(rg._parse_money("", "amount", 1), None)
        self.assertEqual(rg.money(361500), "3,615.00")
        self.assertEqual(rg.money_json(361500), "3615.00")
        self.assertEqual(rg.money(-250), "-2.50")

    def test_no_network_or_execution_code(self):
        source = SRC.read_text(encoding="utf-8")
        for banned in ("urllib", "socket", "requests",
                       "http.client", "subprocess", "os.system",
                       "ftplib"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
