"""The Land Department history files, published on data.dubai.

  Real Estate Transactions  https://data.dubai/en/l/470061  transactions_<date>_0001.csv ... (about 1.1 GB)
  Rent Contracts            https://data.dubai/en/l/468586  rent_contracts_<date>_0001.csv ... (about 5.1 GB)

The site only answers from inside the UAE, so the files are downloaded in a browser there and this
module runs on that computer. Only the monthly statistics it produces are stored in the repository.

Large files come split into numbered parts. The parts are read in order as one stream: a part that
starts with the header row again has it skipped, a part that starts mid-line is joined to the last one.
The site stores the parts gzip-compressed, so a downloaded ".csv" may really be a .csv.gz: both are read.
"""
import gzip
import io
import re
from pathlib import Path

import pandas as pd

from ..clean import FIELDS, clean

PATTERNS = {"price": "transactions_*.csv", "rent": "rent_contracts_*.csv"}
CHUNK_ROWS = 400_000
FIRST_MONTH = "2010-01"


def files(folder: Path, measure: str) -> list[Path]:
    # "name (1).csv" is a second copy of the same download: ignore it
    found = sorted(p for p in Path(folder).glob(PATTERNS[measure]) if re.search(r"_\d{4}\.csv$", p.name))
    if not found:
        raise FileNotFoundError(f"no {PATTERNS[measure]} in {folder}")
    # if several exports were downloaded, use the newest one (its date is in the name)
    export = lambda p: re.sub(r"_\d{4}\.csv$", "", p.name)
    newest = max({export(p) for p in found})
    return [p for p in found if export(p) == newest]


class Parts(io.RawIOBase):
    """Several CSV parts read as one file."""

    def __init__(self, paths):
        self.paths, self.i, self.f, self.header = list(paths), -1, None, None
        self._next()

    def _next(self):
        if self.f:
            self.f.close()
        self.i += 1
        if self.i >= len(self.paths):
            self.f = None
            return
        f = open(self.paths[self.i], "rb")
        packed = f.read(2) == b"\x1f\x8b"
        f.seek(0)
        self.f = gzip.GzipFile(fileobj=f) if packed else f
        first = self.f.readline()
        bare = first.removeprefix(b"\xef\xbb\xbf")
        if self.header is None:
            self.header = bare
            self.pending = bare
        elif bare.strip() == self.header.strip():
            self.pending = b""
        else:
            self.pending = bare

    def readable(self):
        return True

    def readinto(self, b):
        while self.f is not None:
            if self.pending:
                n = min(len(b), len(self.pending))
                b[:n], self.pending = self.pending[:n], self.pending[n:]
                return n
            n = self.f.readinto(b)
            if n:
                return n
            self._next()
        return 0


def _wanted(measure):
    names = {n for v in FIELDS[measure].values() for n in v}
    return names | {"master_project_en"}


def chunks(folder: Path, measure: str):
    wanted = _wanted(measure)
    stream = io.TextIOWrapper(io.BufferedReader(Parts(files(folder, measure)), 1 << 20), encoding="utf-8",
                              errors="replace", newline="")
    yield from pd.read_csv(stream, dtype=str, chunksize=CHUNK_ROWS, on_bad_lines="warn",
                           usecols=lambda c: c.strip().lower() in wanted)


def clean_all(folder: Path, measure: str, work: Path, last_month: str, log=print):
    """Cleans every record and stores them by year in work/<measure>/<year>.parquet (outside the repository).

    Returns (counts, area hints)."""
    out = Path(work) / measure
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.parquet"):
        old.unlink()
    counts = {"rows": 0, "missing": 0, "out_of_bounds": 0, "duplicates": 0}
    hints, read, k = [], 0, 0
    for raw in chunks(folder, measure):
        raw.columns = [c.strip().lower() for c in raw.columns]
        read += len(raw)
        rec, cnt = clean(raw, measure)
        for c in counts:
            counts[c] += cnt[c]
        rec = rec[(rec["month"] >= FIRST_MONTH) & (rec["month"] <= last_month)].drop(columns="date")
        area_col = next((c for c in FIELDS[measure]["area"] if c in raw.columns), None)
        if area_col and "master_project_en" in raw.columns:
            # which master projects each official area contains, to give areas the names people use
            h = pd.DataFrame({"area_id": raw.loc[rec.index, area_col].str.strip().str.upper(),
                              "master_project": raw.loc[rec.index, "master_project_en"].str.strip()})
            hints.append(h.dropna().value_counts().rename("deals").reset_index())
        for year, part in rec.groupby(rec["month"].str.slice(0, 4)):
            part.to_parquet(out / f"{year}_{k:04d}.parquet", index=False)
        k += 1
        log(f"  {measure}: {read:,} rows read, {counts['rows']:,} homes in scope")
    hints = (pd.concat(hints).groupby(["area_id", "master_project"])["deals"].sum().reset_index()
             if hints else pd.DataFrame(columns=["area_id", "master_project", "deals"]))
    return counts, hints


def years(work: Path, measure: str) -> dict[str, list[Path]]:
    by = {}
    for p in sorted((Path(work) / measure).glob("*.parquet")):
        by.setdefault(p.name[:4], []).append(p)
    return by


def read_year(paths) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
