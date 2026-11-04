#!/usr/bin/env python3
"""receipt-gate — validate a Canadian charity's donations CSV
against the CRA's official donation-receipt requirements BEFORE
the receipts go out, so a defective receipt is caught in the
spreadsheet instead of at a CRA review.

Pure Python standard library. Local only: no network, no
uploads, no accounts. The donor list never leaves the machine.

Small charities — about 90% of Canada's roughly 86,000
registered charities have fewer than 10 staff — issue official
donation receipts by hand every January and February, usually
out of one spreadsheet. The CRA prescribes the elements an
official receipt must carry; a receipt missing an element is
invalid, and defective receipting can cost a charity its
registration. The error-prone spots are mechanical: the
split-receipting subtraction (eligible amount = gift −
advantage), an advantage so large the gift is not receiptable
at all, a serial number used twice or skipped, a registration
number typed wrong, a receipt dated before the donation
arrived. Nothing in the usual workflow checks the sheet
against the requirements before the envelopes go out. This
tool does.

Commands:
  check DONATIONS.csv [--year YYYY] [--as-of YYYY-MM-DD]
        [--json]
  register DONATIONS.csv [--year YYYY] [--json]
  rules [--json]

Input CSV columns (headers matched case-insensitively, spaces
and underscores ignored — "Serial Number", "serial_number" and
"SerialNumber" are the same column; extra columns are
tolerated and ignored):

  serial_number       required: the receipt's unique serial
  charity_name        required: the charity's name
  charity_address     required: the charity's address
  registration_number required: 9 digits + RR + 4 digits
                      (e.g. 123456789RR0001)
  place_issued        required: where the receipt was issued
  official_statement  required: the statement that this is an
                      official receipt for income tax purposes
  cra_website         required: canada.ca/charities-giving
  donor_name          required: the donor's full name
  donor_address       required: the donor's address
  donation_date       required: YYYY-MM-DD, received date
  receipt_date        required: YYYY-MM-DD, issued date
  gift_type           required: cash or in_kind
  amount              required: the cash amount, or for a gift
                      in kind its deemed fair market value
  advantage_amount    optional: what the donor got back
                      (blank = 0)
  advantage_description
                      required when advantage_amount > 0
  eligible_amount     required: the recorded eligible amount
                      (checked against amount − advantage)
  gift_description    required for gifts in kind
  appraiser_name      optional: who appraised a gift in kind
  appraiser_address   required when appraiser_name is given

The encoded checks (also printed by `rules`; every finding
names the rule, the measured value and the limit): every CRA
element present for the row's gift type; the split-receipting
arithmetic; the 80% rule (an advantage over 80% of the amount
means no receipt may be issued at all) and the 10%
intention-to-make-a-gift warning; duplicate and gapped serial
numbers; the registration number's shape and consistency; the
issued date never before the received date.

HONESTY: these are ENCODED rules, checked 2026-11, drawn from
the CRA's published guidance for registered charities. The CRA
can change its guidance, and this tool checks a spreadsheet —
it cannot see the printed receipts, the charity's records with
the CRA, or whether an appraisal is genuine. A PASS means the
CSV satisfies the rules encoded in this tool — never a
guarantee the CRA accepts the receipts. This tool is a
checking aid: it does not issue receipts, and it is not tax
advice.

Exit codes: check — 0 = no errors (warnings may be listed) ·
1 = errors found · 2 = an input error. register / rules — 0
on success · 2 = an input error. Errors print only the error
— "ERROR: ..." as text, or a single {"error": ...} object
with --json. Never a traceback.
"""
import argparse
import csv
import io
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

__version__ = "0.1.0"
TOOL = "receipt-gate"

RULES_CHECKED = "2026-11"
RULES_NOTE = ("Encoded rules, checked 2026-11 — verify against "
              "the CRA's current guidance for registered "
              "charities before relying on them.")
DISCLAIMER = ("receipt-gate is a checking aid: it does not "
              "issue receipts, and it is not tax advice.")
HONESTY = ("A PASS means the file satisfies the rules encoded "
           "in this tool — never a guarantee the CRA accepts "
           "the receipts.")

CRA_WEBSITE = "canada.ca/charities-giving"
REGISTRATION_RE = re.compile(r"^\d{9}RR\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# CRA guidance: a gift of property (other than cash or
# securities) with a fair market value over $1,000 should be
# appraised by an independent appraiser. Encoded as a warning,
# not an error — it is guidance about the appraisal, and the
# receipt element is the appraiser's name/address IF appraised.
APPRAISAL_GUIDANCE_CENTS = 100_000  # $1,000.00

# The CRA elements an official donation receipt must carry, as
# encoded by this tool (printed by `rules`). "csv" names the
# column(s) that carry the element; "applies" the gift types.
ELEMENTS = [
    {"n": 1, "element": "a statement that it is an official "
     "receipt for income tax purposes",
     "csv": "official_statement", "applies": "all"},
    {"n": 2, "element": "the charity's name and address, as "
     "recorded with the CRA",
     "csv": "charity_name, charity_address", "applies": "all"},
    {"n": 3, "element": "the charity's registration number",
     "csv": "registration_number", "applies": "all"},
    {"n": 4, "element": "a unique serial number for the receipt",
     "csv": "serial_number", "applies": "all"},
    {"n": 5, "element": "the place or locality where the "
     "receipt was issued",
     "csv": "place_issued", "applies": "all"},
    {"n": 6, "element": "the date the donation was received",
     "csv": "donation_date", "applies": "all"},
    {"n": 7, "element": "the date the receipt was issued",
     "csv": "receipt_date", "applies": "all"},
    {"n": 8, "element": "the donor's full name and address",
     "csv": "donor_name, donor_address", "applies": "all"},
    {"n": 9, "element": "the amount of the gift — the cash "
     "amount, or for a gift in kind the amount that is its "
     "deemed fair market value",
     "csv": "amount", "applies": "all"},
    {"n": 10, "element": "for a gift in kind: a description of "
     "the gift, and the name and address of the appraiser if "
     "an appraisal was done",
     "csv": "gift_description, appraiser_name, "
     "appraiser_address", "applies": "in_kind"},
    {"n": 11, "element": "the amount of any advantage received "
     "by the donor, and a description of that advantage",
     "csv": "advantage_amount, advantage_description",
     "applies": "all"},
    {"n": 12, "element": "the eligible amount of the gift "
     "(amount − advantage)",
     "csv": "eligible_amount", "applies": "all"},
    {"n": 13, "element": "the name and website address of the "
     "Canada Revenue Agency: canada.ca/charities-giving",
     "csv": "cra_website", "applies": "all"},
]

# The encoded checks (printed by `rules`). Severity "error"
# fails `check` (exit 1); "warning" is listed but never fails.
CHECKS = [
    {"rule": "required_missing", "severity": "error",
     "basis": "CRA: an official receipt must carry every "
     "prescribed element for its gift type; a receipt missing "
     "an element is invalid. Encoded per gift type: cash and "
     "in-kind rows have different required columns, an "
     "advantage over $0 needs its description, and an "
     "appraiser's name needs the appraiser's address."},
    {"rule": "registration_number_format", "severity": "error",
     "basis": "CRA registration numbers are the charity's "
     "9-digit business number followed by RR and a 4-digit "
     "reference number (e.g. 123456789RR0001). Any other "
     "shape is a transcription error. (Spaces in the value "
     "are ignored; letter case is checked as-is — a "
     "lowercase 'rr' fails.)"},
    {"rule": "registration_inconsistent", "severity": "error",
     "basis": "Every receipt a charity issues bears the same "
     "registration number. Two different well-formed numbers "
     "in one file means two charities' data was merged, or "
     "some receipts carry another charity's number. "
     "(Malformed numbers are judged by "
     "registration_number_format instead.)"},
    {"rule": "cra_website_wrong", "severity": "error",
     "basis": "CRA: the receipt must show the name and website "
     "address of the Canada Revenue Agency — "
     "canada.ca/charities-giving. A different value is not "
     "that element."},
    {"rule": "statement_wording", "severity": "warning",
     "basis": "CRA prescribes the statement that the receipt "
     "is an official receipt for income tax purposes. The "
     "checker looks for the phrases 'official receipt' and "
     "'income tax' in the statement column; a statement "
     "missing either is flagged for a human to compare "
     "against the CRA's wording."},
    {"rule": "eligible_mismatch", "severity": "error",
     "basis": "Split receipting: the eligible amount of a "
     "gift is the amount of the gift minus the amount of any "
     "advantage. The recorded eligible amount must equal "
     "amount − advantage, to the cent."},
    {"rule": "advantage_over_80", "severity": "error",
     "basis": "CRA split-receipting rule: when the advantage "
     "exceeds 80% of the amount of the gift, the transfer is "
     "not a gift and no official receipt may be issued for "
     "it at all."},
    {"rule": "advantage_over_10", "severity": "warning",
     "basis": "CRA split-receipting guidance: when the "
     "advantage exceeds 10% of the amount of the gift, the "
     "donor's intention to make a gift is in question and "
     "the charity must be able to establish that intention. "
     "Receiptable, but expect to document it."},
    {"rule": "amount_not_positive", "severity": "error",
     "basis": "A gift amount of $0 or less cannot be "
     "receipted, and an advantage cannot be negative."},
    {"rule": "serial_duplicate", "severity": "error",
     "basis": "CRA: every official receipt bears a unique "
     "serial number. The same serial on two receipts (numeric "
     "serials compared by value, so 0105 duplicates 105) "
     "breaks the audit trail."},
    {"rule": "serial_gap", "severity": "warning",
     "basis": "Serial numbers are the receipt book's audit "
     "trail. A number with no receipt in the file may be a "
     "voided or lost receipt — explainable, but it must be "
     "explainable, so it is listed."},
    {"rule": "serial_non_numeric", "severity": "warning",
     "basis": "The gap check needs an all-numeric run of "
     "serials. A file mixing in non-numeric serials skips "
     "the gap check rather than guessing; duplicates are "
     "still checked."},
    {"rule": "issued_before_received", "severity": "error",
     "basis": "A receipt cannot be issued before the donation "
     "it receipts was received: the issued date must be on "
     "or after the received date."},
    {"rule": "donation_year_mismatch", "severity": "warning",
     "basis": "With --year, the run is scoped to one "
     "receipting year; a donation received in a different "
     "calendar year belongs to that year's receipts, not "
     "this run."},
    {"rule": "date_in_future", "severity": "warning",
     "basis": "With --as-of, dates after the as-of date are "
     "flagged. The tool never reads the machine clock on its "
     "own — no --as-of, no future check."},
    {"rule": "appraiser_missing", "severity": "warning",
     "basis": "CRA guidance: a gift of property with a fair "
     "market value over $1,000 should be appraised by an "
     "independent appraiser. An in-kind gift over that value "
     "with no appraiser named is flagged as guidance, not "
     "as a defective receipt."},
    {"rule": "charity_inconsistent", "severity": "warning",
     "basis": "One file, one charity: the charity's name "
     "should be identical on every row. A variation is "
     "usually a typo that will print on some receipts."},
]


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# input loading + validation (every error names its row)
# --------------------------------------------------------------------------

def _fail_row(row_no, msg):
    raise ToolError(f"row {row_no}: {msg}")


def _norm_header(name):
    """'Serial Number', 'serial_number' and 'SerialNumber' are
    one column."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


_HEADER_ALIASES = {
    "serialnumber": "serial_number", "serial": "serial_number",
    "receiptnumber": "serial_number",
    "charityname": "charity_name",
    "charityaddress": "charity_address",
    "registrationnumber": "registration_number",
    "charityregistrationnumber": "registration_number",
    "placeissued": "place_issued", "issuedat": "place_issued",
    "placeofissue": "place_issued",
    "officialstatement": "official_statement",
    "statement": "official_statement",
    "crawebsite": "cra_website", "craurl": "cra_website",
    "donorname": "donor_name",
    "donoraddress": "donor_address",
    "donationdate": "donation_date",
    "dateofdonation": "donation_date",
    "donatedate": "donation_date", "giftdate": "donation_date",
    "receiptdate": "receipt_date", "dateissued": "receipt_date",
    "issueddate": "receipt_date",
    "gifttype": "gift_type", "type": "gift_type",
    "amount": "amount", "giftamount": "amount",
    "donationamount": "amount",
    "fairmarketvalue": "amount", "fmv": "amount",
    "advantageamount": "advantage_amount",
    "advantage": "advantage_amount",
    "advantagedescription": "advantage_description",
    "eligibleamount": "eligible_amount",
    "eligible": "eligible_amount",
    "giftdescription": "gift_description",
    "description": "gift_description",
    "appraisername": "appraiser_name",
    "appraiseraddress": "appraiser_address",
}

# Columns the file itself must carry (a missing column is an
# input error, exit 2). Advantage, in-kind and appraiser
# columns may be absent entirely — absence just means no row
# can have those values, and the per-row rules judge what
# that implies.
REQUIRED_COLUMNS = (
    "serial_number", "charity_name", "charity_address",
    "registration_number", "place_issued", "official_statement",
    "cra_website", "donor_name", "donor_address",
    "donation_date", "receipt_date", "gift_type", "amount",
    "eligible_amount",
)

GIFT_TYPES = {"cash": "cash", "in_kind": "in_kind",
              "in-kind": "in_kind", "inkind": "in_kind",
              "gift in kind": "in_kind", "gift-in-kind": "in_kind",
              "non-cash": "in_kind", "noncash": "in_kind",
              "property": "in_kind"}


def _parse_money(raw, field, row_no):
    """Money text -> integer cents. Accepts 100, 100.5, 100.55,
    $100.55 and 1,000.55. Anything else — including more than
    two decimal places — is a clean input error naming the
    row, never a silent rounding."""
    text = (raw or "").strip().replace("$", "").replace(",", "")
    text = text.replace(" ", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        _fail_row(row_no, f"'{field}' must be an amount "
                          f"(got {raw!r})")
    if not value.is_finite() or value.as_tuple().exponent < -2:
        _fail_row(row_no, f"'{field}' must be an amount with "
                          f"at most two decimal places "
                          f"(got {raw!r})")
    return int(value * 100)


def _parse_date(raw, field, row_no):
    """YYYY-MM-DD text -> a date (None when blank). Any other
    shape is a clean input error naming the row."""
    text = (raw or "").strip()
    if not text:
        return None
    if not DATE_RE.match(text):
        _fail_row(row_no, f"'{field}' must be a date "
                          f"YYYY-MM-DD (got {raw!r})")
    try:
        return date.fromisoformat(text)
    except ValueError:
        _fail_row(row_no, f"'{field}' is not a real calendar "
                          f"date (got {raw!r})")


def money(cents):
    """Integer cents -> '1,234.56' (text display)."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100:,}.{cents % 100:02d}"


def money_json(cents):
    """Integer cents -> '1234.56' (JSON: exact, no separators,
    always two decimals)."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def normalize_row(row, row_no):
    """Validate one raw row dict -> a clean donation dict.
    Blank cells stay blank (the rules judge absence); a
    non-blank value that cannot be parsed is an input error."""
    def cell(name):
        return (row.get(name) or "").strip()

    gift_raw = cell("gift_type")
    gift_type = None
    if gift_raw:
        gift_type = GIFT_TYPES.get(gift_raw.lower())
        if gift_type is None:
            _fail_row(row_no, f"'gift_type' must be cash or "
                              f"in_kind (got {gift_raw!r})")
    serial = cell("serial_number")
    serial_int = None
    if serial:
        try:
            serial_int = int(serial)
        except ValueError:
            serial_int = None
    return {
        "serial": serial,
        "serial_int": serial_int,
        "charity_name": cell("charity_name"),
        "charity_address": cell("charity_address"),
        # Spaces are stripped (spreadsheets often group the
        # digits), but letter case is NOT normalized — the
        # CRA format uses capital RR, and a lowercase 'rr' on
        # the printed receipt is a defect to surface, not to
        # silently fix.
        "registration_number":
            cell("registration_number").replace(" ", ""),
        "place_issued": cell("place_issued"),
        "official_statement": cell("official_statement"),
        "cra_website": cell("cra_website"),
        "donor_name": cell("donor_name"),
        "donor_address": cell("donor_address"),
        "donation_date": _parse_date(row.get("donation_date"),
                                     "donation_date", row_no),
        "receipt_date": _parse_date(row.get("receipt_date"),
                                    "receipt_date", row_no),
        "gift_type": gift_type,
        "amount_cents": _parse_money(row.get("amount"),
                                     "amount", row_no),
        "advantage_cents": _parse_money(
            row.get("advantage_amount"), "advantage_amount",
            row_no),
        "advantage_description": cell("advantage_description"),
        "eligible_cents": _parse_money(
            row.get("eligible_amount"), "eligible_amount",
            row_no),
        "gift_description": cell("gift_description"),
        "appraiser_name": cell("appraiser_name"),
        "appraiser_address": cell("appraiser_address"),
    }


def load_donations(path):
    """Read a .csv donations file -> list of donation dicts."""
    if not path.is_file():
        raise ToolError(f"file not found: {path}")
    if path.suffix.lower() != ".csv":
        raise ToolError(f"expected a .csv file (got {path.name})")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"could not read {path.name} "
                        f"({exc.__class__.__name__})")
    # A field can legitimately be long (a full gift
    # description) — the csv module's 128K default field limit
    # would call that "malformed", which it is not.
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:  # pragma: no cover - 32-bit builds
        csv.field_size_limit(2 ** 31 - 1)
    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        if reader.fieldnames is None:
            raise ToolError(f"{path.name}: empty CSV — no header "
                            f"row")
        header_map = {}
        for raw_name in reader.fieldnames:
            canonical = _HEADER_ALIASES.get(_norm_header(raw_name))
            if canonical is not None:
                header_map[canonical] = True
        missing = [c for c in REQUIRED_COLUMNS
                   if c not in header_map]
        if missing:
            raise ToolError(
                f"{path.name}: CSV must have "
                f"{', '.join(repr(c) for c in missing)} column(s) "
                f"(headers found: "
                f"{', '.join(reader.fieldnames)})")
        entries = []
        for row in reader:
            row_no = len(entries) + 1
            if row.get(None):
                _fail_row(row_no, "more values than the header "
                                  "has columns")
            if all(v is None or (isinstance(v, str)
                                 and not v.strip())
                   for v in row.values()):
                continue  # a blank line is not a bad row
            mapped = {}
            for raw_name, value in row.items():
                canonical = _HEADER_ALIASES.get(
                    _norm_header(raw_name))
                if canonical is not None:
                    mapped[canonical] = value
            entries.append(normalize_row(mapped, row_no))
    except csv.Error as exc:
        raise ToolError(f"{path.name}: malformed CSV ({exc})")
    return entries


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------

def _finding(row_no, serial, field, rule, severity, measured,
             limit, message):
    return {"row": row_no, "serial": serial, "field": field,
            "rule": rule, "severity": severity,
            "measured": measured, "limit": limit,
            "message": message}


# Every field a row must carry regardless of gift type.
_ALWAYS_REQUIRED = (
    ("serial_number", "serial"),
    ("charity_name", "charity_name"),
    ("charity_address", "charity_address"),
    ("registration_number", "registration_number"),
    ("place_issued", "place_issued"),
    ("official_statement", "official_statement"),
    ("cra_website", "cra_website"),
    ("donor_name", "donor_name"),
    ("donor_address", "donor_address"),
    ("donation_date", "donation_date"),
    ("receipt_date", "receipt_date"),
    ("gift_type", "gift_type"),
    ("amount", "amount_cents"),
    ("eligible_amount", "eligible_cents"),
)


def check_row(entry, row_no, year, as_of):
    """All per-row findings for one donation."""
    out = []
    serial = entry["serial"] or None

    def add(field, rule, severity, measured, limit, message):
        out.append(_finding(row_no, serial, field, rule,
                            severity, measured, limit, message))

    def missing(field, why=""):
        add(field, "required_missing", "error", "blank",
            "the element present on the receipt",
            f"{field} is blank — the CRA element it carries "
            f"would be missing from the receipt{why}")

    for field, key in _ALWAYS_REQUIRED:
        value = entry[key]
        if value is None or (isinstance(value, str)
                             and not value):
            missing(field)
    if entry["gift_type"] == "in_kind" \
            and not entry["gift_description"]:
        missing("gift_description",
                " (required for a gift in kind)")
    advantage = entry["advantage_cents"] or 0
    if advantage > 0 and not entry["advantage_description"]:
        missing("advantage_description",
                " (required when there is an advantage)")
    if entry["appraiser_name"] and not entry["appraiser_address"]:
        missing("appraiser_address",
                " (an appraiser is named, so the appraiser's "
                "address is part of the element)")

    reg = entry["registration_number"]
    if reg and not REGISTRATION_RE.match(reg):
        add("registration_number", "registration_number_format",
            "error", reg, "9 digits + RR + 4 digits "
            "(e.g. 123456789RR0001)",
            f"registration number {reg!r} is not in the CRA "
            f"format (limit: 9 digits + RR + 4 digits, e.g. "
            f"123456789RR0001)")

    website = entry["cra_website"]
    if website:
        normalized = re.sub(r"^https?://", "", website.lower())
        normalized = normalized.rstrip("/")
        if normalized != CRA_WEBSITE:
            add("cra_website", "cra_website_wrong", "error",
                website, CRA_WEBSITE,
                f"cra_website is {website!r} (limit: the CRA "
                f"website element is {CRA_WEBSITE})")

    statement = entry["official_statement"].lower()
    if statement and ("official receipt" not in statement
                      or "income tax" not in statement):
        add("official_statement", "statement_wording", "warning",
            entry["official_statement"],
            "a statement that this is an official receipt for "
            "income tax purposes",
            "the statement does not contain both 'official "
            "receipt' and 'income tax' — compare it against "
            "the CRA's prescribed statement")

    amount = entry["amount_cents"]
    if amount is not None and amount <= 0:
        add("amount", "amount_not_positive", "error",
            money(amount), "an amount over $0.00",
            f"amount is {money(amount)} — a gift of $0 or "
            f"less cannot be receipted")
    if entry["advantage_cents"] is not None \
            and entry["advantage_cents"] < 0:
        add("advantage_amount", "amount_not_positive", "error",
            money(entry["advantage_cents"]), "an advantage of "
            "$0.00 or more",
            f"advantage_amount is "
            f"{money(entry['advantage_cents'])} — an advantage "
            f"cannot be negative")

    if amount is not None and entry["eligible_cents"] is not None:
        expected = amount - advantage
        if entry["eligible_cents"] != expected:
            add("eligible_amount", "eligible_mismatch", "error",
                f"recorded {money(entry['eligible_cents'])}",
                f"amount − advantage = {money(expected)}",
                f"recorded eligible amount is "
                f"{money(entry['eligible_cents'])} but amount "
                f"− advantage = {money(amount)} − "
                f"{money(advantage)} = {money(expected)}")

    if amount is not None and amount > 0:
        if advantage * 100 > amount * 80:
            add("advantage_amount", "advantage_over_80", "error",
                f"advantage {money(advantage)} of amount "
                f"{money(amount)}",
                "advantage at most 80% of the amount",
                f"advantage is {money(advantage)} on a gift "
                f"of {money(amount)} — over 80%: under the "
                f"encoded CRA split-receipting rule this is "
                f"not a gift and no receipt may be issued")
        elif advantage * 100 > amount * 10:
            add("advantage_amount", "advantage_over_10",
                "warning",
                f"advantage {money(advantage)} of amount "
                f"{money(amount)}",
                "advantage at most 10% of the amount needs no "
                "intention evidence",
                f"advantage is {money(advantage)} on a gift "
                f"of {money(amount)} — over 10%: under the "
                f"encoded CRA guidance the donor's intention "
                f"to make a gift must be establishable")

    donated, issued = entry["donation_date"], entry["receipt_date"]
    if donated is not None and issued is not None \
            and issued < donated:
        add("receipt_date", "issued_before_received", "error",
            f"issued {issued.isoformat()}",
            f"on or after the donation date "
            f"{donated.isoformat()}",
            f"receipt was issued {issued.isoformat()}, before "
            f"the donation was received {donated.isoformat()}")

    if year is not None and donated is not None \
            and donated.year != year:
        add("donation_date", "donation_year_mismatch", "warning",
            f"donation received {donated.isoformat()}",
            f"a donation received in {year}",
            f"donation was received in {donated.year}, "
            f"outside the {year} run — it belongs to that "
            f"year's receipts")
    if as_of is not None:
        for field, value in (("donation_date", donated),
                             ("receipt_date", issued)):
            if value is not None and value > as_of:
                add(field, "date_in_future", "warning",
                    f"{field} {value.isoformat()}",
                    f"on or before the as-of date "
                    f"{as_of.isoformat()}",
                    f"{field} is {value.isoformat()}, after "
                    f"the as-of date {as_of.isoformat()}")

    if entry["gift_type"] == "in_kind" and amount is not None \
            and amount > APPRAISAL_GUIDANCE_CENTS \
            and not entry["appraiser_name"]:
        add("appraiser_name", "appraiser_missing", "warning",
            "no appraiser named",
            "an appraiser for a gift in kind over $1,000 "
            "(CRA guidance)",
            f"gift in kind of {money(amount)} names no "
            f"appraiser — CRA guidance is that property over "
            f"$1,000 be appraised by an independent appraiser")
    return out


def check_file(entries):
    """File-level findings: serial duplicates and gaps, and
    charity-level consistency across the rows."""
    out = []

    by_serial = {}
    for i, entry in enumerate(entries):
        if not entry["serial"]:
            continue
        key = entry["serial_int"] if entry["serial_int"] \
            is not None else entry["serial"]
        by_serial.setdefault(key, []).append(i + 1)
    for key, rows in by_serial.items():
        if len(rows) > 1:
            shown = entries[rows[0] - 1]["serial"]
            for row_no in rows[1:]:
                out.append(_finding(
                    row_no, entries[row_no - 1]["serial"],
                    "serial_number", "serial_duplicate", "error",
                    f"serial {shown} used on rows "
                    f"{', '.join(str(r) for r in rows)}",
                    "a serial number unique in the file",
                    f"serial {shown} already appears on row "
                    f"{rows[0]} — every receipt must bear a "
                    f"unique serial number"))

    serials = [e["serial_int"] for e in entries]
    if entries and all(s is not None for s in serials):
        present = set(serials)
        for n in range(min(present), max(present) + 1):
            if n not in present:
                out.append(_finding(
                    None, str(n), "serial_number", "serial_gap",
                    "warning", f"serial {n} absent",
                    "an unbroken run of serials, or a note "
                    "explaining each gap",
                    f"serial {n} has no receipt in this file "
                    f"— a missing serial is an audit question "
                    f"(voided, lost, or issued from another "
                    f"book)"))
    elif entries:
        bad = sorted({e["serial"] for e in entries
                      if e["serial"] and e["serial_int"] is None})
        if bad:
            out.append(_finding(
                None, None, "serial_number", "serial_non_numeric",
                "warning",
                "non-numeric serial(s): " + ", ".join(bad),
                "an all-numeric run for the gap check",
                "some serials are not numbers, so the serial "
                "gap check was skipped rather than guessed "
                "(duplicates were still checked)"))

    wellformed = {e["registration_number"] for e in entries
                  if REGISTRATION_RE.match(
                      e["registration_number"])}
    if len(wellformed) > 1:
        out.append(_finding(
            None, None, "registration_number",
            "registration_inconsistent", "error",
            "registration numbers: "
            + ", ".join(sorted(wellformed)),
            "one registration number for the whole file",
            "the file carries more than one well-formed "
            "registration number — two charities' data may "
            "have been merged, or some receipts bear another "
            "charity's number"))
    names = {e["charity_name"] for e in entries if e["charity_name"]}
    if len(names) > 1:
        out.append(_finding(
            None, None, "charity_name", "charity_inconsistent",
            "warning",
            "charity names: " + ", ".join(sorted(names)),
            "the charity's name identical on every row",
            "the charity's name is not identical on every "
            "row — usually a typo that will print on some "
            "receipts"))
    return out


def run_check(entries, year, as_of):
    """Every finding, per-row in row order then file-level."""
    findings = []
    for i, entry in enumerate(entries):
        findings.extend(check_row(entry, i + 1, year, as_of))
    findings.extend(check_file(entries))
    findings.sort(key=lambda f: (f["row"] is None,
                                 f["row"] or 0, f["rule"]))
    return findings


# --------------------------------------------------------------------------
# the register
# --------------------------------------------------------------------------

def receiptable(entry):
    """(is_receiptable, reason_when_not). A gift is not
    receiptable when the encoded rules say no receipt may
    stand behind it: no amount recorded, a non-positive
    amount, or an advantage over 80% of the amount."""
    amount = entry["amount_cents"]
    if amount is None:
        return False, "no amount recorded"
    if amount <= 0:
        return False, "amount is not over $0.00"
    advantage = entry["advantage_cents"] or 0
    if advantage * 100 > amount * 80:
        return False, ("advantage exceeds 80% of the amount — "
                       "under the encoded CRA split-receipting "
                       "rule no receipt may be issued")
    return True, ""


def build_register(entries, year):
    """The year-end register: rows sorted by serial, the
    computed eligible amount (amount − advantage), totals over
    receiptable gifts only, and per-donor totals."""
    rows, excluded, undated = [], [], 0
    for i, entry in enumerate(entries):
        donated = entry["donation_date"]
        if year is not None:
            if donated is None:
                undated += 1
                continue
            if donated.year != year:
                continue
        ok, reason = receiptable(entry)
        amount = entry["amount_cents"]
        advantage = entry["advantage_cents"] or 0
        record = {
            "row": i + 1,
            "serial": entry["serial"] or None,
            "serial_int": entry["serial_int"],
            "donation_date": donated.isoformat()
            if donated else None,
            "donor_name": entry["donor_name"] or None,
            "gift_type": entry["gift_type"],
            "amount_cents": amount,
            "advantage_cents": advantage,
            "eligible_cents": (amount - advantage)
            if amount is not None else None,
            "receiptable": ok,
            "excluded_reason": reason if not ok else None,
        }
        (rows if ok else excluded).append(record)
    order = lambda r: (r["serial_int"] is None,  # noqa: E731
                       r["serial_int"] or 0, r["serial"] or "")
    rows.sort(key=order)
    excluded.sort(key=order)
    totals = {
        "count": len(rows),
        "amount_cents": sum(r["amount_cents"] for r in rows),
        "advantage_cents": sum(r["advantage_cents"]
                               for r in rows),
        "eligible_cents": sum(r["eligible_cents"] for r in rows),
    }
    donors = {}
    for r in rows:
        name = r["donor_name"] or "(no donor recorded)"
        slot = donors.setdefault(name, {"donor_name": name,
                                        "count": 0,
                                        "amount_cents": 0,
                                        "advantage_cents": 0,
                                        "eligible_cents": 0})
        slot["count"] += 1
        slot["amount_cents"] += r["amount_cents"]
        slot["advantage_cents"] += r["advantage_cents"]
        slot["eligible_cents"] += r["eligible_cents"]
    note = None
    if year is not None and undated:
        note = (f"{undated} row(s) had no donation date and "
                f"were left out of the {year} register.")
    elif not rows and not excluded:
        note = ("Note: no donations in scope — the register "
                "is empty, so these totals are vacuous.")
    return {"entries": rows, "excluded": excluded,
            "totals": totals,
            "by_donor": [donors[k] for k in sorted(donors)],
            "note": note}


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------

def _check_summary(findings):
    by_rule = {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    return {
        "errors": sum(1 for f in findings
                      if f["severity"] == "error"),
        "warnings": sum(1 for f in findings
                        if f["severity"] == "warning"),
        "by_rule": dict(sorted(by_rule.items())),
    }


def check_as_json(source_name, entries, findings, year, as_of,
                  note):
    summary = _check_summary(findings)
    return {
        "tool": TOOL, "version": __version__, "command": "check",
        "file": source_name, "rows": len(entries),
        "year": year,
        "as_of": as_of.isoformat() if as_of else None,
        "summary": summary,
        "findings": findings,
        "verdict": "FAIL" if summary["errors"] else "PASS",
        "note": note,
        "rules_note": RULES_NOTE,
        "honesty": HONESTY,
        "disclaimer": DISCLAIMER,
    }


def _where(f):
    if f["row"] is not None:
        return (f"row {f['row']} (serial {f['serial']})"
                if f["serial"] else f"row {f['row']}")
    return (f"file (serial {f['serial']})" if f["serial"]
            else "file")


def render_check_text(source_name, entries, findings, year,
                      as_of, note):
    scope = f" · year {year}" if year is not None else ""
    lines = [
        f"receipt-gate v{__version__} — check of {source_name} "
        f"({len(entries)} row(s)){scope}",
        RULES_NOTE,
        "",
    ]
    if note:
        lines.append(note)
        lines.append("")
    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings
                if f["severity"] == "warning"]
    if errors:
        lines.append(f"ERRORS — receipts that would be invalid, "
                     f"or that must not be issued "
                     f"({len(errors)}):")
        for f in errors:
            lines.append(f"  {_where(f)} — {f['rule']}: "
                         f"{f['message']}")
        lines.append("")
    if warnings:
        lines.append(f"WARNINGS — review before issuing "
                     f"({len(warnings)}):")
        for f in warnings:
            lines.append(f"  {_where(f)} — {f['rule']}: "
                         f"{f['message']}")
        lines.append("")
    if errors:
        lines.append(f"Verdict: FAIL — {len(errors)} error(s), "
                     f"{len(warnings)} warning(s). Fix the "
                     f"errors before these receipts go out.")
    elif warnings:
        lines.append(f"Verdict: PASS — no errors; "
                     f"{len(warnings)} warning(s) to review. "
                     f"Every row satisfies the encoded rules' "
                     f"error checks.")
    else:
        lines.append("Verdict: PASS — no errors, no warnings. "
                     "Every row satisfies the encoded rules.")
    lines.append(DISCLAIMER + " " + HONESTY)
    return "\n".join(lines)


def _register_entry_json(r):
    return {
        "row": r["row"], "serial": r["serial"],
        "donation_date": r["donation_date"],
        "donor_name": r["donor_name"],
        "gift_type": r["gift_type"],
        "amount": money_json(r["amount_cents"])
        if r["amount_cents"] is not None else None,
        "advantage": money_json(r["advantage_cents"]),
        "eligible": money_json(r["eligible_cents"])
        if r["eligible_cents"] is not None else None,
        "receiptable": r["receiptable"],
        "excluded_reason": r["excluded_reason"],
    }


def register_as_json(source_name, register, year, in_scope):
    totals = register["totals"]
    return {
        "tool": TOOL, "version": __version__,
        "command": "register",
        "file": source_name, "year": year,
        "rows_in_scope": in_scope,
        "entries": [_register_entry_json(r)
                    for r in register["entries"]],
        "excluded": [_register_entry_json(r)
                     for r in register["excluded"]],
        "totals": {
            "count": totals["count"],
            "amount": money_json(totals["amount_cents"]),
            "advantage": money_json(totals["advantage_cents"]),
            "eligible": money_json(totals["eligible_cents"]),
        },
        "by_donor": [{
            "donor_name": d["donor_name"], "count": d["count"],
            "amount": money_json(d["amount_cents"]),
            "advantage": money_json(d["advantage_cents"]),
            "eligible": money_json(d["eligible_cents"]),
        } for d in register["by_donor"]],
        "note": register["note"],
        "rules_note": RULES_NOTE,
        "honesty": ("The eligible total is the starting figure "
                    "for the charity's T3010 receipted-gifts "
                    "work — it is not a filing, and it is not "
                    "tax advice."),
        "disclaimer": DISCLAIMER,
    }


def render_register_text(source_name, register, year, in_scope):
    scope = f" · year {year}" if year is not None else ""
    lines = [
        f"receipt-gate v{__version__} — receipt register for "
        f"{source_name}{scope} ({in_scope} receipt(s) in "
        f"scope)",
        RULES_NOTE,
        "",
    ]
    if register["note"]:
        lines.append(register["note"])
        lines.append("")
    all_rows = register["entries"] + register["excluded"]
    all_rows.sort(key=lambda r: (r["serial_int"] is None,
                                 r["serial_int"] or 0,
                                 r["serial"] or ""))
    if all_rows:
        lines.append(f"  {'serial':<8} {'date':<12} "
                     f"{'donor':<24} {'type':<8} "
                     f"{'amount':>10} {'advantage':>10} "
                     f"{'eligible':>10}")
        for r in all_rows:
            line = (
                f"  {(r['serial'] or '—'):<8} "
                f"{(r['donation_date'] or '—'):<12} "
                f"{(r['donor_name'] or '—')[:24]:<24} "
                f"{(r['gift_type'] or '—'):<8} "
                f"{money(r['amount_cents']) if r['amount_cents'] is not None else '—':>10} "
                f"{money(r['advantage_cents']):>10} "
                f"{money(r['eligible_cents']) if r['eligible_cents'] is not None else '—':>10}")
            if not r["receiptable"]:
                line += (f"\n    NOT RECEIPTABLE — excluded "
                         f"from totals: "
                         f"{r['excluded_reason']}")
            lines.append(line)
        lines.append("")
    totals = register["totals"]
    lines.append(
        f"TOTALS ({totals['count']} receiptable receipt(s)): "
        f"amount {money(totals['amount_cents'])} · advantage "
        f"{money(totals['advantage_cents'])} · eligible "
        f"{money(totals['eligible_cents'])}")
    if register["excluded"]:
        face = sum(r["amount_cents"] or 0
                   for r in register["excluded"])
        lines.append(
            f"Excluded from totals: "
            f"{len(register['excluded'])} receipt(s), face "
            f"amount {money(face)} — see NOT RECEIPTABLE "
            f"above.")
    if register["by_donor"]:
        lines.append("")
        lines.append("Totals by donor (receiptable only):")
        for d in register["by_donor"]:
            lines.append(
                f"  {d['donor_name']} — {d['count']} "
                f"receipt(s) · amount "
                f"{money(d['amount_cents'])} · advantage "
                f"{money(d['advantage_cents'])} · eligible "
                f"{money(d['eligible_cents'])}")
    lines.append("")
    lines.append("Eligible amounts above are computed "
                 "(amount − advantage); the recorded eligible "
                 "column is judged by `check`, not repeated "
                 "here.")
    lines.append("The eligible total is the starting figure "
                 "for the charity's T3010 receipted-gifts "
                 "work — it is not a filing. " + DISCLAIMER)
    return "\n".join(lines)


def rules_as_json():
    return {
        "tool": TOOL, "version": __version__, "command": "rules",
        "rules_checked": RULES_CHECKED,
        "rules_note": RULES_NOTE,
        "elements": ELEMENTS,
        "checks": CHECKS,
        "honesty": HONESTY,
        "disclaimer": DISCLAIMER,
    }


def render_rules_text():
    lines = [
        f"receipt-gate v{__version__} — the encoded CRA "
        f"donation-receipt rules",
        RULES_NOTE,
        "",
        "THE ELEMENTS AN OFFICIAL RECEIPT MUST CARRY "
        "(encoded):",
    ]
    for e in ELEMENTS:
        lines.append(f"  {e['n']:>2}. {e['element']} "
                     f"[csv: {e['csv']}; applies: "
                     f"{e['applies']}]")
    lines.append("")
    lines.append("THE CHECKS:")
    for c in CHECKS:
        lines.append(f"  {c['rule']} ({c['severity']}) — "
                     f"{c['basis']}")
    lines.append("")
    lines.append(DISCLAIMER + " " + HONESTY)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in
    --json mode ({"error": ...} on stdout, same exit code 2)
    — an agent driving this tool with --json never gets plain
    text or a traceback. The flag lives on the class so
    subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _year_value(text):
    if not re.fullmatch(r"\d{4}", text or ""):
        raise argparse.ArgumentTypeError(
            f"year must be four digits (got {text!r})")
    return int(text)


def _as_of_value(text):
    if not DATE_RE.match(text or ""):
        raise ToolError(f"--as-of must be a date YYYY-MM-DD "
                        f"(got {text!r})")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ToolError(f"--as-of is not a real calendar date "
                        f"(got {text!r})")


def _scope_note(entries):
    if not entries:
        return ("Note: the file has a header row but no data "
                "rows — nothing was checked, so this PASS is "
                "vacuous.")
    return None


def cmd_check(a):
    path = Path(a.csv)
    entries = load_donations(path)
    findings = run_check(entries, a.year, a.as_of)
    note = _scope_note(entries)
    if a.json:
        print(json.dumps(check_as_json(path.name, entries,
                                       findings, a.year,
                                       a.as_of, note),
                         indent=2))
    else:
        print(render_check_text(path.name, entries, findings,
                                a.year, a.as_of, note))
    return 1 if _check_summary(findings)["errors"] else 0


def cmd_register(a):
    path = Path(a.csv)
    entries = load_donations(path)
    register = build_register(entries, a.year)
    in_scope = len(register["entries"]) \
        + len(register["excluded"])
    if a.json:
        print(json.dumps(register_as_json(path.name, register,
                                          a.year, in_scope),
                         indent=2))
    else:
        print(render_register_text(path.name, register, a.year,
                                   in_scope))
    return 0


def cmd_rules(a):
    if a.json:
        print(json.dumps(rules_as_json(), indent=2))
    else:
        print(render_rules_text())
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="Validate a donations CSV against the "
                    "CRA's encoded official-receipt rules "
                    "before the receipts go out (stdlib only, "
                    "local only). A checking aid — not a "
                    "receipt issuer, not tax advice.")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_check = sub.add_parser(
        "check", help="check a donations CSV against the "
                      "encoded CRA receipt rules")
    p_check.add_argument("csv", help="donations file (.csv)")
    p_check.add_argument("--year", type=_year_value,
                         default=None,
                         help="receipting year under check "
                              "(flags donations received in "
                              "other years)")
    p_check.add_argument("--as-of", type=_as_of_value,
                         default=None, metavar="YYYY-MM-DD",
                         help="flag dates after this date (the "
                              "tool never reads the clock "
                              "itself)")
    p_check.add_argument("--json", action="store_true",
                         help="print one JSON object instead of "
                              "the text report")
    p_check.set_defaults(func=cmd_check)

    p_register = sub.add_parser(
        "register", help="print the year-end receipt register "
                         "with eligible totals")
    p_register.add_argument("csv", help="donations file (.csv)")
    p_register.add_argument("--year", type=_year_value,
                            default=None,
                            help="limit the register to "
                                 "donations received in this "
                                 "year")
    p_register.add_argument("--json", action="store_true",
                            help="print one JSON object instead "
                                 "of text")
    p_register.set_defaults(func=cmd_register)

    p_rules = sub.add_parser(
        "rules", help="print the encoded CRA elements and "
                      "checks")
    p_rules.add_argument("--json", action="store_true",
                         help="print one JSON object instead of "
                              "text")
    p_rules.set_defaults(func=cmd_rules)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
