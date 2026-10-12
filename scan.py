"""Reading what the scanner gives us.

There are two kinds of codes in the store:

1. The normal barcode (the stripes). It only says WHICH product it is.
   A carton of milk tells you "I am Tine Lettmelk 1L" and nothing more.

2. The square code you see on a lot of the meat. It says which product
   it is AND the date on that exact pack.

This file takes the text from the scanner and figures out which of the
two it is. Nothing else happens here.
"""

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass
class Scan:
    gtin: str                   # the product number, always 14 digits
    expiry: date | None = None  # None = normal barcode, the code had no date


# The square codes are a row of small fields glued together. Each field
# starts with a 2 digit number that says what comes next:
#   01 = product number (always 14 digits)
#   15 = best before    (6 digits, YYMMDD)
#   17 = use by         (6 digits, YYMMDD)
#   11 = produced, 13 = packed (dates we don't care about, but we have to
#        know how long they are so we can jump over them)
FIXED_LENGTH = {"01": 14, "11": 6, "13": 6, "15": 6, "17": 6}

# These two have no fixed length (batch number and serial number). They
# just keep going until a special invisible character, or the end.
VARIABLE_LENGTH = {"10", "21"}
SEPARATOR = "\x1d"


def read_code(text: str) -> Scan:
    """Turn the text from the scanner into a Scan."""
    text = text.strip()

    # Some scanners put 3 characters first to say what type of code it
    # was, like "]d2". We don't need that, so cut it off.
    if text.startswith("]"):
        text = text[3:]

    # Only digits and a normal barcode length = the stripes. No date.
    if text.isdigit() and len(text) in (8, 12, 13, 14):
        return Scan(gtin=text.zfill(14))

    fields = split_fields(text)
    if "01" not in fields:
        raise ValueError(f"I don't understand this code: {text!r}")

    # If the pack has both dates, "use by" is the strict one, so it wins.
    date_text = fields.get("17") or fields.get("15")
    expiry = to_date(date_text) if date_text else None
    return Scan(gtin=fields["01"], expiry=expiry)


def split_fields(text: str) -> dict[str, str]:
    """Walk through a square code and pick out the fields one by one."""
    fields = {}
    pos = 0  # where in the text we are right now

    while pos < len(text):
        if text[pos] == SEPARATOR:
            pos += 1
            continue

        number = text[pos:pos + 2]

        if number in FIXED_LENGTH:
            start = pos + 2
            end = start + FIXED_LENGTH[number]
        elif number in VARIABLE_LENGTH:
            start = pos + 2
            end = text.find(SEPARATOR, start)
            if end == -1:          # no separator = it runs to the end
                end = len(text)
        elif text[pos:pos + 3] == "310":
            # Weight in kg, for meat that is priced by weight. This one
            # has a 4 digit number in front and then 6 digits of weight.
            number = "310"
            start = pos + 4
            end = start + 6
        else:
            # A field I haven't taught the program about. Stop here and
            # keep what we already found.
            break

        fields[number] = text[start:end]
        pos = end

    return fields


def to_date(yymmdd: str) -> date:
    """ "261015" -> 15 October 2026."""
    year = 2000 + int(yymmdd[0:2])
    month = int(yymmdd[2:4])
    day = int(yymmdd[4:6])

    # Day 00 is allowed and means "the last day of that month".
    if day == 0:
        day = calendar.monthrange(year, month)[1]

    return date(year, month, day)