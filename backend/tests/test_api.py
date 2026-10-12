"""Tests for the web API in main.py. Run with:  python -m pytest

Each test gets its own empty database that only lives in memory.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app

MILK = "07038010000010"
MILK_BARCODE = "7038010000010"
MINCE = "07038010000065"
MINCE_SQUARE_CODE = "010703801000006517261015"  # use by 15 Oct 2026


@pytest.fixture
def client():
    # StaticPool = every request uses the same in-memory database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def add_products(client):
    client.put(f"/products/{MILK}", json={"name": "Melk 1L"})
    client.put(f"/products/{MINCE}", json={"name": "Kjøttdeig 400g"})


def open_delivery(client):
    return client.post("/deliveries", json={"supplier": "ASKO"}).json()["id"]


# --- /scan ---

def test_scan_known_product_with_date(client):
    add_products(client)

    answer = client.post("/scan", json={"code": MINCE_SQUARE_CODE}).json()

    assert answer == {"gtin": MINCE, "expiry": "2026-10-15", "name": "Kjøttdeig 400g"}


def test_scan_unknown_product_has_no_name(client):
    answer = client.post("/scan", json={"code": MILK_BARCODE}).json()

    assert answer == {"gtin": MILK, "expiry": None, "name": None}


def test_scan_rubbish_is_a_bad_request(client):
    assert client.post("/scan", json={"code": "hello"}).status_code == 400


# --- receiving a delivery ---

def test_line_with_date_in_the_code(client):
    add_products(client)
    delivery = open_delivery(client)

    answer = client.post(
        f"/deliveries/{delivery}/lines",
        json={"code": MINCE_SQUARE_CODE, "quantity": 6},
    ).json()

    assert answer["expiry"] == "2026-10-15"
    assert answer["quantity"] == 6
    assert answer["put_in_front"] is False


def test_line_with_normal_barcode_needs_a_typed_date(client):
    add_products(client)
    delivery = open_delivery(client)

    answer = client.post(
        f"/deliveries/{delivery}/lines",
        json={"code": MILK_BARCODE, "quantity": 12},
    )

    assert answer.status_code == 422


def test_same_date_on_a_later_delivery_goes_into_the_same_batch(client):
    add_products(client)
    line = {"code": MILK_BARCODE, "quantity": 12, "expiry": "2026-10-20"}

    first = client.post(f"/deliveries/{open_delivery(client)}/lines", json=line).json()
    second = client.post(f"/deliveries/{open_delivery(client)}/lines", json=line).json()

    assert second["batch_id"] == first["batch_id"]
    assert second["quantity"] == 24


def test_later_delivery_with_worse_date_must_go_in_front(client):
    # The ASKO case, all the way through the API.
    add_products(client)
    client.post(
        f"/deliveries/{open_delivery(client)}/lines",
        json={"code": MILK_BARCODE, "quantity": 12, "expiry": "2026-10-20"},
    )

    answer = client.post(
        f"/deliveries/{open_delivery(client)}/lines",
        json={"code": MILK_BARCODE, "quantity": 12, "expiry": "2026-10-15"},
    ).json()

    assert answer["put_in_front"] is True
    assert answer["quantity"] == 12  # a new batch, not added to the old one


def test_line_for_unknown_product(client):
    delivery = open_delivery(client)

    answer = client.post(
        f"/deliveries/{delivery}/lines",
        json={"code": MILK_BARCODE, "quantity": 12, "expiry": "2026-10-20"},
    )

    assert answer.status_code == 404


def test_line_for_unknown_delivery(client):
    add_products(client)

    answer = client.post(
        "/deliveries/999/lines",
        json={"code": MINCE_SQUARE_CODE, "quantity": 6},
    )

    assert answer.status_code == 404


def test_line_with_zero_items(client):
    add_products(client)
    delivery = open_delivery(client)

    answer = client.post(
        f"/deliveries/{delivery}/lines",
        json={"code": MINCE_SQUARE_CODE, "quantity": 0},
    )

    assert answer.status_code == 422


# --- sales ---

def receive_milk(client, quantity, expiry):
    client.post(
        f"/deliveries/{open_delivery(client)}/lines",
        json={"code": MILK_BARCODE, "quantity": quantity, "expiry": expiry},
    )


def checklist(client):
    return client.get("/checklist", params={"today": "2026-10-12", "days_ahead": 30}).json()


def test_sale_takes_from_the_oldest_date_and_marks_the_guess(client):
    add_products(client)
    receive_milk(client, 10, "2026-10-20")
    receive_milk(client, 10, "2026-10-15")  # later delivery, worse date

    answer = client.post("/sales", json={"code": MILK_BARCODE, "quantity": 4}).json()

    assert answer == {"gtin": MILK, "missing": 0}
    assert [(i["expiry"], i["quantity"], i["guessed"]) for i in checklist(client)] == [
        ("2026-10-15", 6, True),
        ("2026-10-20", 10, True),
    ]


def test_sale_with_date_in_the_code_takes_from_that_batch(client):
    add_products(client)
    delivery = open_delivery(client)
    client.post(f"/deliveries/{delivery}/lines", json={"code": MINCE_SQUARE_CODE, "quantity": 6})

    client.post("/sales", json={"code": MINCE_SQUARE_CODE})

    assert [(i["name"], i["quantity"], i["guessed"]) for i in checklist(client)] == [
        ("Kjøttdeig 400g", 5, False),
    ]


def test_sold_out_batch_leaves_the_checklist(client):
    add_products(client)
    receive_milk(client, 3, "2026-10-13")

    client.post("/sales", json={"code": MILK_BARCODE, "quantity": 3})

    assert checklist(client) == []


def test_selling_more_than_we_have_says_how_many_are_missing(client):
    add_products(client)
    receive_milk(client, 3, "2026-10-13")

    answer = client.post("/sales", json={"code": MILK_BARCODE, "quantity": 5}).json()

    assert answer["missing"] == 2


def test_sale_of_unknown_product(client):
    answer = client.post("/sales", json={"code": MILK_BARCODE})

    assert answer.status_code == 404


def test_sale_of_zero_items(client):
    add_products(client)

    answer = client.post("/sales", json={"code": MILK_BARCODE, "quantity": 0})

    assert answer.status_code == 422


# --- the list of what to check ---

def test_checklist_has_what_goes_out_soon_oldest_first(client):
    add_products(client)
    delivery = open_delivery(client)
    for line in [
        {"code": MILK_BARCODE, "quantity": 12, "expiry": "2026-10-13"},
        {"code": MINCE_SQUARE_CODE, "quantity": 6},                       # 15 Oct
        {"code": MILK_BARCODE, "quantity": 12, "expiry": "2026-10-11"},
        {"code": MILK_BARCODE, "quantity": 12, "expiry": "2026-10-30"},  # far away
    ]:
        client.post(f"/deliveries/{delivery}/lines", json=line)

    answer = client.get("/checklist", params={"today": "2026-10-12", "days_ahead": 3}).json()

    assert [(item["name"], item["expiry"]) for item in answer] == [
        ("Melk 1L", "2026-10-11"),
        ("Melk 1L", "2026-10-13"),
        ("Kjøttdeig 400g", "2026-10-15"),
    ]
