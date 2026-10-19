"""Every setting the pipeline uses, in one place, so each choice can be read and explained."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
AGG_DIR = DATA / "aggregates"          # monthly statistics per segment (committed: this is the data history)
FORECAST_DIR = DATA / "forecasts"      # one file per monthly run, never edited afterwards (the public record)
REPORT_DIR = DATA / "reports"          # run log, data checks, accuracy tables
RAW_DIR = ROOT / ".raw"                # downloaded records, never committed
SITE_SRC = ROOT / "site"
SITE_OUT = ROOT / "_site"

SQM_TO_SQFT = 10.7639                  # Dubai quotes property in square feet; DLD records square metres

# What is forecast
MEASURES = ("rent", "price")           # rent = yearly rent per sq ft of new leases; price = sale price per sq ft
PTYPES = ("apartment", "villa")        # villa includes townhouses
BEDS = ("studio", "1", "2", "3", "4+")
ALL = "all"                            # roll-up label (all bedrooms, or all of Dubai)
DUBAI = "DUBAI"                        # area id of the Dubai-wide roll-up
HORIZON = 12                           # months ahead
QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)  # 80% range = 0.1 to 0.9, 50% range = 0.25 to 0.75

# How the monthly level is measured
TRIM = 0.05                            # drop the 5% most extreme deals on each side, per segment and month
WINDOW = 3                             # level = typical deal over the last 3 months (one month alone is too noisy)
MIN_DEALS_LEVEL = 12                   # a 3-month level needs at least this many deals
MIN_DEALS_PUBLISH = 30                 # a segment gets a published forecast only with 30+ deals in the last 3 months
MIN_HISTORY_MONTHS = 36                # ...and at least 3 years of levels

# Plausibility bounds per sq ft (AED). Deals outside are recording errors (e.g. AED 1 transfers, wrong sizes).
BOUNDS = {
    "rent": (8.0, 1500.0),             # yearly rent per sq ft
    "price": (150.0, 25000.0),         # sale price per sq ft
}
SIZE_BOUNDS_SQFT = {"apartment": (150, 15000), "villa": (600, 60000)}

# Backtest: design choices were made on the development origins only; the test origins are the honest score.
BACKTEST_START = "2015-01"
TEST_START = "2023-01"                 # first forecast origin of the untouched test period
BACKTEST_STEP = 3                      # one forecast origin every 3 months

# Monthly run gates (MLOps): if any fails, nothing is published and the last good version stays online.
GATES = {
    "volume_ratio": (0.4, 2.5),        # new month's deal count vs. median of the previous 12 months
    "max_missing_share": 0.10,         # share of rows missing area, size or amount
    "max_out_of_bounds_share": 0.05,
    "max_duplicate_share": 0.005,
    "max_dubai_level_jump": 0.25,      # Dubai-wide level may not move more than 25% in one month
    "max_error_worsening": 0.25,       # recent backtest error may not get more than 25% worse than last run
    "max_abs_12m_change": 0.60,        # no published 12-month forecast beyond +/-60% (sanity)
}

DEFAULT_AREA_SLUG = "dubai-marina"     # the area the forecast page opens on

SOURCE_NAME = "Dubai Land Department (DLD) open data"
ATTRIBUTION = (
    "Source: Dubai Land Department open data (sales transactions and Ejari rent contracts), "
    "Government of Dubai. Only monthly statistics derived from it are published here. "
    "Independent project, not affiliated with or endorsed by the Dubai Land Department or the Government of Dubai."
)
