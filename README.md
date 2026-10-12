# Datoprosjekt

Small app for keeping better track of the expiry dates of food delivered to retail stores.

The idea: every delivery is registered as one or more *batches* (a product, a quantity and an expiry date). When items are scanned at the till, they are taken out of the right batch, so the store always has a list of what is about to go out of date and should be checked on the shelf.

## Status

Early backend. There is no user interface yet, only the core logic and its tests.

## How it works

### `scan.py` – reading barcodes

The store has two kinds of codes:

- **Normal barcodes** (the stripes, EAN/UPC). They only say *which* product it is.
- **Square codes** (GS1 DataMatrix, common on meat). They say which product it is *and* the date on that exact pack.

`read_code(text)` takes the text from the scanner and returns a `Scan` with the 14-digit product number (`gtin`) and, if the code had one, the `expiry` date. It understands:

- scanner prefixes like `]d2`
- use-by (`17`) and best-before (`15`) dates – use-by wins if both are present
- day `00`, which means the last day of the month
- batch numbers, serial numbers and weights, which are skipped over

### `batches.py` – tracking what is in the store

- `register_sale(batches, scan, quantity=1)` takes sold items out of the right batch:
  - If the scan had a date, it takes from exactly that batch.
  - If not, it assumes the oldest date was sold. If there were several dates to choose from, the batches are marked as `guessed`.
  - Returns how many items it could not find a batch for (`0` means everything added up).
- `items_to_check(batches, today, days_ahead=2)` returns everything still in stock that expires within `days_ahead` days, including what has already expired, oldest date first.

## Getting started

Requires Python 3.10 or newer and [pytest](https://pytest.org).

```bash
git clone https://github.com/EskilYttri/Datoprosjekt.git
cd Datoprosjekt
python -m pip install pytest
python -m pytest
```

## Contributing

Make changes on a separate branch and merge them into `main` through a pull request.
