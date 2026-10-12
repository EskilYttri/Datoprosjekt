"""The web API. Start it with:  uvicorn app.main:app --reload

Every endpoint does the same three things: load what it needs from the
database, let core/ decide what happens, and save the result. No rules
about dates or batches are written here.
"""

from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.batches import Batch, items_to_check, receive, register_sale
from app.core.scan import read_code
from app.db import create_tables, get_session
from app.models import BatchRow, Delivery, Product


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(title="Datovarsel", lifespan=lifespan)


# --- what the requests and answers look like ---

class ScanIn(BaseModel):
    code: str  # the text from the scanner


class ScanOut(BaseModel):
    gtin: str
    expiry: date | None
    name: str | None  # None = we don't know this product yet


class ProductIn(BaseModel):
    name: str


class DeliveryIn(BaseModel):
    supplier: str


class LineIn(BaseModel):
    code: str
    quantity: int
    # Only needed when the code has no date (normal barcode). If the code
    # has a date, that one is used.
    expiry: date | None = None


class LineOut(BaseModel):
    batch_id: int
    gtin: str
    name: str
    expiry: date
    quantity: int        # how many are in the batch now, in total
    put_in_front: bool   # True = older than what's already in the store


class SaleIn(BaseModel):
    code: str          # the code that was scanned at the till
    quantity: int = 1


class SaleOut(BaseModel):
    gtin: str
    # How many we could NOT find a batch for. 0 = it all added up.
    # Anything else means our numbers for this product are off.
    missing: int


class CheckItem(BaseModel):
    batch_id: int
    gtin: str
    name: str
    expiry: date
    quantity: int
    guessed: bool


def load_batches(pairs) -> tuple[list[Batch], dict[int, BatchRow]]:
    """Turn rows from the database into Batch objects that core/ understands.

    Also gives back which row each Batch came from, so we know what to
    save afterwards.
    """
    batches = []
    row_for = {}
    for row, product in pairs:
        batch = Batch(row.gtin, product.name, row.quantity, row.expiry, row.guessed)
        row_for[id(batch)] = row
        batches.append(batch)
    return batches, row_for


# --- endpoints ---

@app.post("/scan")
def scan(body: ScanIn, session: Session = Depends(get_session)) -> ScanOut:
    """What is this code? Used by the app to show the product right away."""
    try:
        result = read_code(body.code)
    except ValueError as error:
        raise HTTPException(400, str(error))

    product = session.get(Product, result.gtin)
    return ScanOut(
        gtin=result.gtin,
        expiry=result.expiry,
        name=product.name if product else None,
    )


@app.put("/products/{gtin}")
def save_product(
    gtin: str, body: ProductIn, session: Session = Depends(get_session)
) -> Product:
    """Add a product, or change its name."""
    product = session.get(Product, gtin) or Product(gtin=gtin, name=body.name)
    product.name = body.name
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@app.post("/deliveries")
def open_delivery(
    body: DeliveryIn, session: Session = Depends(get_session)
) -> Delivery:
    delivery = Delivery(supplier=body.supplier)
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


@app.post("/deliveries/{delivery_id}/lines")
def add_line(
    delivery_id: int, body: LineIn, session: Session = Depends(get_session)
) -> LineOut:
    """One line on the delivery was scanned. Put it in the right batch."""
    if session.get(Delivery, delivery_id) is None:
        raise HTTPException(404, f"No delivery with id {delivery_id}")

    try:
        result = read_code(body.code)
    except ValueError as error:
        raise HTTPException(400, str(error))

    expiry = result.expiry or body.expiry
    if expiry is None:
        raise HTTPException(422, "The code has no date, so it must be typed in")

    product = session.get(Product, result.gtin)
    if product is None:
        raise HTTPException(404, f"Unknown product {result.gtin}, add it first")

    # Every batch we have of this product, so receive() can compare dates.
    rows = session.exec(select(BatchRow).where(BatchRow.gtin == result.gtin)).all()
    batches, row_for = load_batches((row, product) for row in rows)

    try:
        received = receive(batches, result.gtin, product.name, expiry, body.quantity)
    except ValueError as error:
        raise HTTPException(422, str(error))

    # Save it: either an existing row got more, or it is a new batch.
    row = row_for.get(id(received.batch))
    if row is None:
        row = BatchRow(gtin=result.gtin, delivery_id=delivery_id, expiry=expiry, quantity=0)
    row.quantity = received.batch.quantity
    session.add(row)
    session.commit()
    session.refresh(row)

    return LineOut(
        batch_id=row.id,
        gtin=row.gtin,
        name=product.name,
        expiry=row.expiry,
        quantity=row.quantity,
        put_in_front=received.put_in_front,
    )


@app.post("/sales")
def sale(body: SaleIn, session: Session = Depends(get_session)) -> SaleOut:
    """Something was sold. Take it out of the right batch."""
    try:
        result = read_code(body.code)
    except ValueError as error:
        raise HTTPException(400, str(error))

    if body.quantity <= 0:
        raise HTTPException(422, f"Can't sell {body.quantity} items")

    product = session.get(Product, result.gtin)
    if product is None:
        raise HTTPException(404, f"Unknown product {result.gtin}")

    rows = session.exec(select(BatchRow).where(BatchRow.gtin == result.gtin)).all()
    batches, row_for = load_batches((row, product) for row in rows)

    missing = register_sale(batches, result, body.quantity)

    # register_sale can change the count and the guessed mark on any of
    # the batches, so save them all.
    for batch in batches:
        row = row_for[id(batch)]
        row.quantity = batch.quantity
        row.guessed = batch.guessed
        session.add(row)
    session.commit()

    return SaleOut(gtin=result.gtin, missing=missing)


@app.get("/checklist")
def checklist(
    today: date | None = None,
    days_ahead: int = 2,
    session: Session = Depends(get_session),
) -> list[CheckItem]:
    """What somebody has to go and look at today, oldest date first."""
    today = today or date.today()

    pairs = session.exec(select(BatchRow, Product).join(Product)).all()
    batches, row_for = load_batches(pairs)

    return [
        CheckItem(
            batch_id=row_for[id(b)].id,
            gtin=b.gtin,
            name=b.name,
            expiry=b.expiry,
            quantity=b.quantity,
            guessed=b.guessed,
        )
        for b in items_to_check(batches, today, days_ahead)
    ]
