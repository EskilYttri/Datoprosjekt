"""Keeping track of what we think is in the store, and what to check.

A "batch" is one line on a delivery: a product, how many we got, and the
date on them. The same product can have several batches in the store at
once, for example when ASKO comes with a new delivery that has a worse
date than what we already have on the shelf.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from scan import Scan


@dataclass
class Batch:
    gtin: str        # product number, 14 digits (same as in scan.py)
    name: str        # just so a person can read the list
    quantity: int    # how many we THINK are left
    expiry: date
    guessed: bool = False  # True = the number left is a guess, see below


def register_sale(batches: list[Batch], scan: Scan, quantity: int = 1) -> int:
    """Something was scanned at the till. Take it out of the right batch.

    Two cases:

    - The code had a date (the square code on meat). Then we KNOW which
      batch it came from, so we take it from exactly that one.

    - The code had no date (normal barcode). The till has no idea which
      pack the customer picked. We assume it was the oldest one, because
      that is what should be at the front of the shelf. If the product
      has more than one date in the store, that is a guess, so those
      batches get marked as guessed.

    Returns how many we could NOT find a batch for. 0 means it all added
    up. Anything else means our numbers are off for this product.
    """
    # Everything we still have of this product, oldest date first.
    in_stock = sorted(
        (b for b in batches if b.gtin == scan.gtin and b.quantity > 0),
        key=lambda b: b.expiry,
    )

    if scan.expiry is not None:
        # We know the date, so only that batch is allowed.
        in_stock = [b for b in in_stock if b.expiry == scan.expiry]
    elif len(in_stock) > 1:
        # No date and more than one to choose from = guessing.
        for batch in in_stock:
            batch.guessed = True

    remaining = quantity
    for batch in in_stock:
        if remaining == 0:
            break
        taken = min(batch.quantity, remaining)
        batch.quantity -= taken
        remaining -= taken

    return remaining


def items_to_check(
    batches: list[Batch], today: date, days_ahead: int = 2
) -> list[Batch]:
    """The list of what somebody has to go and look at today.

    Everything we think we still have that goes out of date within
    `days_ahead` days. Stuff that is already out of date is on the list
    too, and the oldest date comes first.
    """
    limit = today + timedelta(days=days_ahead)
    due = [b for b in batches if b.quantity > 0 and b.expiry <= limit]
    return sorted(due, key=lambda b: b.expiry)