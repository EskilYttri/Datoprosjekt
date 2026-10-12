# Datovarsel

Warns a grocery store about goods that are about to go out of date, without anyone having to check every item on the shelf.

The idea: every delivery is registered as one or more *batches* (a product, a quantity and an expiry date). When items are scanned at the till, they are taken out of the right batch, so the store always has a list of what is about to go out of date and should be checked on the shelf.

## Status

Early backend: the core logic and a web API with a database. There is no user interface yet.

```
backend/
├── app/
│   ├── core/          the rules: scan.py and batches.py, no database here
│   ├── models.py      the tables in the database
│   ├── db.py          the connection to the database (SQLite by default)
│   └── main.py        the web API
└── tests/
```

## How it works

### `core/scan.py` – reading barcodes

The store has two kinds of codes:

- **Normal barcodes** (the stripes, EAN/UPC). They only say *which* product it is.
- **Square codes** (GS1 DataMatrix, common on meat). They say which product it is *and* the date on that exact pack.

`read_code(text)` takes the text from the scanner and returns a `Scan` with the 14-digit product number (`gtin`) and, if the code had one, the `expiry` date. It understands:

- scanner prefixes like `]d2`
- use-by (`17`) and best-before (`15`) dates – use-by wins if both are present
- day `00`, which means the last day of the month
- batch numbers, serial numbers and weights, which are skipped over

### `core/batches.py` – tracking what is in the store

- `receive(batches, gtin, name, expiry, quantity)` registers one line of a delivery:
  - If there already is a batch with the same product and the same date, the goods go into that batch.
  - Otherwise a new batch is added to the list.
  - The result says `put_in_front` when the new date is earlier than a date still in the store (for example when a later delivery has a worse date), so the new goods should be placed in front on the shelf.
- `register_sale(batches, scan, quantity=1)` takes sold items out of the right batch:
  - If the scan had a date, it takes from exactly that batch.
  - If not, it assumes the oldest date was sold. If there were several dates to choose from, the batches are marked as `guessed`.
  - Returns how many items it could not find a batch for (`0` means everything added up).
- `items_to_check(batches, today, days_ahead=2)` returns everything still in stock that expires within `days_ahead` days, including what has already expired, oldest date first.

### `main.py` – the web API

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/scan` | Text from the scanner in, product number, date and name out |
| PUT | `/products/{gtin}` | Add a product or change its name |
| POST | `/deliveries` | Open a new delivery, for example from ASKO |
| POST | `/deliveries/{id}/lines` | One scanned line of the delivery: goes into the right batch, says `put_in_front` if it must go in front |
| POST | `/sales` | Something was sold: takes it out of the right batch |
| GET | `/checklist` | What to check today, oldest date first |

The endpoints only load and save. All rules about dates and batches are in `core/`.

## Getting started

Requires Python 3.10 or newer.

```bash
git clone https://github.com/EskilYttri/Datoprosjekt.git
cd Datoprosjekt/backend
python -m pip install -e ".[test]"
python -m pytest
```

Start the server and open http://127.0.0.1:8000/docs to try the API in the browser:

```bash
uvicorn app.main:app --reload
```

The data is saved in `datovarsel.db` in the folder you start the server from.

## Contributing

Make changes on a separate branch and merge them into `main` through a pull request.
