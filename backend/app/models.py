"""The tables in the database.

The rules for batches live in core/batches.py and work on plain Batch
objects. These tables are only how we SAVE them between requests.
"""

from datetime import date, datetime, timezone

from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    gtin: str = Field(primary_key=True)  # 14 digits, same as Scan.gtin
    name: str


class Delivery(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    supplier: str                    # "ASKO", for example
    delivered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BatchRow(SQLModel, table=True):
    """A Batch from core/batches.py, saved in the database."""

    id: int | None = Field(default=None, primary_key=True)
    gtin: str = Field(foreign_key="product.gtin", index=True)
    # The delivery the batch first came on. If a later delivery has the
    # same date, it goes into this same batch (see receive()).
    delivery_id: int | None = Field(default=None, foreign_key="delivery.id")
    expiry: date
    quantity: int
    guessed: bool = False
