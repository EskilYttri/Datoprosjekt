"""Tests for scan.py. Run with:  python -m pytest

The product numbers here are made up.
"""

from datetime import date

import pytest

from scan import SEPARATOR, read_code


def test_normal_barcode_has_no_date():
    scan = read_code("7038010000065")

    assert scan.gtin == "07038010000065"  # filled up to 14 digits
    assert scan.expiry is None


def test_square_code_gives_product_and_date():
    scan = read_code("010703801000006517261015")

    assert scan.gtin == "07038010000065"
    assert scan.expiry == date(2026, 10, 15)


def test_same_product_gets_the_same_number_from_both_codes():
    stripes = read_code("7038010000065")
    square = read_code("010703801000006517261015")

    assert stripes.gtin == square.gtin


def test_scanner_prefix_is_ignored():
    scan = read_code("]d2010703801000006517261015")

    assert scan.expiry == date(2026, 10, 15)


def test_date_is_found_after_a_batch_number():
    # 10 = batch number "AB12", then the invisible separator, then the date.
    scan = read_code("010703801000006510AB12" + SEPARATOR + "17261015")

    assert scan.expiry == date(2026, 10, 15)


def test_date_is_found_after_a_weight():
    # 3103 = weight, 000750 = 0.750 kg
    scan = read_code("01070380100000653103000750" + "15261020")

    assert scan.expiry == date(2026, 10, 20)


def test_use_by_wins_over_best_before():
    scan = read_code("0107038010000065" + "15261020" + "17261015")

    assert scan.expiry == date(2026, 10, 15)


def test_square_code_without_a_date():
    scan = read_code("010703801000006510AB12")

    assert scan.gtin == "07038010000065"
    assert scan.expiry is None


def test_day_00_means_last_day_of_the_month():
    scan = read_code("010703801000006515270200")

    assert scan.expiry == date(2027, 2, 28)


def test_rubbish_gives_an_error():
    with pytest.raises(ValueError):
        read_code("hello")