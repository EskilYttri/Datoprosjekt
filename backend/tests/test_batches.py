"""Tests for batches.py. Run with:  python -m pytest"""

from datetime import date

import pytest

from app.core.batches import Batch, items_to_check, receive, register_sale
from app.core.scan import Scan

TODAY = date(2026, 10, 12)

MILK = "07038010000010"
MINCE = "07038010000065"   # kjøttdeig, has the square code with a date
YOGHURT = "07038010000027"


# --- a delivery comes in ---

def test_new_product_becomes_a_new_batch():
    batches = []

    received = receive(batches, MILK, "Melk 1L", date(2026, 10, 20), 12)

    assert batches == [Batch(MILK, "Melk 1L", 12, date(2026, 10, 20))]
    assert received.batch is batches[0]
    assert not received.put_in_front


def test_same_product_and_same_date_goes_into_the_same_batch():
    shelf = Batch(MILK, "Melk 1L", 4, date(2026, 10, 20))
    batches = [shelf]

    received = receive(batches, MILK, "Melk 1L", date(2026, 10, 20), 12)

    assert batches == [shelf]
    assert shelf.quantity == 16
    assert received.batch is shelf


def test_same_product_with_another_date_is_a_new_batch():
    shelf = Batch(MILK, "Melk 1L", 4, date(2026, 10, 15))
    batches = [shelf]

    receive(batches, MILK, "Melk 1L", date(2026, 10, 20), 12)

    assert len(batches) == 2
    assert shelf.quantity == 4


def test_worse_date_than_the_shelf_must_go_in_front():
    # The ASKO case: the new delivery goes out of date before the old one.
    batches = [Batch(MILK, "Melk 1L", 4, date(2026, 10, 20))]

    received = receive(batches, MILK, "Melk 1L", date(2026, 10, 15), 12)

    assert received.put_in_front


def test_better_date_than_the_shelf_goes_behind_as_usual():
    batches = [Batch(MILK, "Melk 1L", 4, date(2026, 10, 15))]

    received = receive(batches, MILK, "Melk 1L", date(2026, 10, 20), 12)

    assert not received.put_in_front


def test_sold_out_batches_do_not_count_for_put_in_front():
    batches = [Batch(MILK, "Melk 1L", 0, date(2026, 10, 20))]

    received = receive(batches, MILK, "Melk 1L", date(2026, 10, 15), 12)

    assert not received.put_in_front


def test_other_products_do_not_count_for_put_in_front():
    batches = [Batch(YOGHURT, "Yoghurt", 4, date(2026, 10, 20))]

    received = receive(batches, MILK, "Melk 1L", date(2026, 10, 15), 12)

    assert not received.put_in_front


def test_receiving_zero_gives_an_error():
    with pytest.raises(ValueError):
        receive([], MILK, "Melk 1L", date(2026, 10, 20), 0)


# --- normal barcode: we have to guess which pack was sold ---

def test_no_date_takes_from_the_oldest_date_first():
    # The later delivery has the WORSE date (the ASKO case).
    first_delivery = Batch(MILK, "Melk 1L", 10, date(2026, 10, 20))
    later_delivery = Batch(MILK, "Melk 1L", 10, date(2026, 10, 15))

    register_sale([first_delivery, later_delivery], Scan(MILK), 4)

    assert later_delivery.quantity == 6
    assert first_delivery.quantity == 10


def test_no_date_spills_over_into_the_next_batch():
    old = Batch(MILK, "Melk 1L", 3, date(2026, 10, 15))
    new = Batch(MILK, "Melk 1L", 10, date(2026, 10, 20))

    register_sale([old, new], Scan(MILK), 5)

    assert old.quantity == 0
    assert new.quantity == 8


def test_no_date_and_two_batches_is_marked_as_a_guess():
    old = Batch(MILK, "Melk 1L", 5, date(2026, 10, 15))
    new = Batch(MILK, "Melk 1L", 5, date(2026, 10, 20))

    register_sale([old, new], Scan(MILK))

    assert old.guessed
    assert new.guessed


def test_no_date_but_only_one_batch_is_not_a_guess():
    only = Batch(MILK, "Melk 1L", 5, date(2026, 10, 15))

    register_sale([only], Scan(MILK))

    assert only.quantity == 4
    assert not only.guessed


# --- square code: the date is in the code, so we know ---

def test_date_in_code_takes_from_exactly_that_batch():
    old = Batch(MINCE, "Kjøttdeig 400g", 5, date(2026, 10, 14))
    new = Batch(MINCE, "Kjøttdeig 400g", 5, date(2026, 10, 18))

    # The customer dug out a pack with the newer date.
    register_sale([old, new], Scan(MINCE, date(2026, 10, 18)))

    assert old.quantity == 5
    assert new.quantity == 4
    assert not old.guessed
    assert not new.guessed


def test_date_in_code_that_we_have_no_batch_for():
    old = Batch(MINCE, "Kjøttdeig 400g", 5, date(2026, 10, 14))

    missing = register_sale([old], Scan(MINCE, date(2026, 10, 30)))

    assert old.quantity == 5
    assert missing == 1


# --- both kinds ---

def test_sale_does_not_touch_other_products():
    milk = Batch(MILK, "Melk 1L", 5, date(2026, 10, 15))
    yoghurt = Batch(YOGHURT, "Yoghurt", 5, date(2026, 10, 14))

    register_sale([milk, yoghurt], Scan(MILK), 2)

    assert yoghurt.quantity == 5


def test_selling_more_than_we_have_returns_the_rest():
    milk = Batch(MILK, "Melk 1L", 3, date(2026, 10, 15))

    missing = register_sale([milk], Scan(MILK), 5)

    assert milk.quantity == 0
    assert missing == 2


# --- the list of what to check ---

def test_check_list_has_what_goes_out_soon_oldest_first():
    batches = [
        Batch(YOGHURT, "Yoghurt", 4, date(2026, 10, 14)),  # in 2 days
        Batch(MILK, "Melk 1L", 6, date(2026, 10, 13)),     # tomorrow
        Batch(MINCE, "Kjøttdeig 400g", 2, date(2026, 10, 11)),  # yesterday
        Batch("07038010000034", "Juice", 8, date(2026, 10, 30)),  # far away
    ]

    result = items_to_check(batches, TODAY)

    assert [b.name for b in result] == ["Kjøttdeig 400g", "Melk 1L", "Yoghurt"]


def test_check_list_skips_what_is_sold_out():
    batches = [Batch(MILK, "Melk 1L", 0, date(2026, 10, 13))]

    assert items_to_check(batches, TODAY) == []