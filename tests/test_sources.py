import pandas as pd

from dpf import bands as B
from dpf.clean import clean
from dpf.sources import bulk

SALES_HEADER = ("transaction_id,trans_group_en,procedure_name_en,instance_date,property_type_en,property_sub_type_en,"
                "property_usage_en,reg_type_en,area_name_en,rooms_en,procedure_area,actual_worth,master_project_en\n")


def sale(i, day, sqm, worth, rooms="1 B/R"):
    return (f"{i},Sales,Sell,{day}-03-2024,Unit,Flat,Residential,Existing Properties,Marsa Dubai,{rooms},"
            f"{sqm},{worth},Dubai Marina\n")


def test_parts_are_read_as_one_file(tmp_path):
    rows = [sale(i, 10 + i % 15, 70 + i % 9, 1_500_000 + 1000 * i) for i in range(30)]
    body = "".join(rows)
    cut = body.index(rows[20]) + 7          # second part starts in the middle of a line
    (tmp_path / "transactions_2026-10-16_17-48-05_0001.csv").write_text("﻿" + SALES_HEADER + body[:cut])
    (tmp_path / "transactions_2026-10-16_17-48-05_0002.csv").write_text(body[cut:])
    (tmp_path / "transactions_2025-01-01_00-00-00_0001.csv").write_text(SALES_HEADER + sale(99, 1, 70, 1))  # older export
    got = pd.concat(bulk.chunks(tmp_path, "price"))
    assert len(got) == 30 and got["transaction_id"].tolist() == [str(i) for i in range(30)]


def test_parts_that_repeat_the_header(tmp_path):
    rows = [sale(i, 10, 75, 1_600_000) for i in range(10)]
    (tmp_path / "transactions_x_0001.csv").write_text(SALES_HEADER + "".join(rows[:4]))
    (tmp_path / "transactions_x_0002.csv").write_text(SALES_HEADER + "".join(rows[4:]))
    got = pd.concat(bulk.chunks(tmp_path, "price"))
    assert len(got) == 10


def test_gzipped_parts_and_duplicate_downloads(tmp_path):
    import gzip
    rows = [sale(i, 12, 80, 1_700_000) for i in range(8)]
    (tmp_path / "transactions_y_0001.csv").write_bytes(gzip.compress((SALES_HEADER + "".join(rows[:5])).encode()))
    (tmp_path / "transactions_y_0002.csv").write_bytes(gzip.compress("".join(rows[5:]).encode()))
    (tmp_path / "transactions_y_0002 (1).csv").write_text(SALES_HEADER + sale(50, 1, 70, 1))
    got = pd.concat(bulk.chunks(tmp_path, "price"))
    assert got["transaction_id"].tolist() == [str(i) for i in range(8)]


def test_live_rent_feed_rows_are_cleaned():
    feed = pd.DataFrame([
        {"REGISTRATION_DATE": "2026-09-15T09:00:01", "START_DATE": "2026-09-15T00:00:00", "VERSION_EN": "New",
         "AREA_EN": "Al Barsha South Fourth", "PROJECT_EN": "Binghatti Azure", "ANNUAL_AMOUNT": 80000,
         "ACTUAL_AREA": 67.6, "PROP_TYPE_EN": "Unit", "PROP_SUB_TYPE_EN": "Flat", "ROOMS": None,
         "USAGE_EN": "Residential", "CONTRACT_NUMBER": None, "TOTAL_PROPERTIES": 1},
        {"REGISTRATION_DATE": "2026-09-15T09:00:02", "START_DATE": "2026-09-15T00:00:00", "VERSION_EN": "Renewed",
         "AREA_EN": "Al Barsha South Fourth", "PROJECT_EN": "X", "ANNUAL_AMOUNT": 70000, "ACTUAL_AREA": 60,
         "PROP_TYPE_EN": "Unit", "PROP_SUB_TYPE_EN": "Flat", "USAGE_EN": "Residential", "TOTAL_PROPERTIES": 1},
        {"REGISTRATION_DATE": "2026-09-15T09:00:03", "START_DATE": "2026-09-15T00:00:00", "VERSION_EN": "New",
         "AREA_EN": "Al Barsha South Fourth", "PROJECT_EN": "Y", "ANNUAL_AMOUNT": 900000, "ACTUAL_AREA": 600,
         "PROP_TYPE_EN": "Unit", "PROP_SUB_TYPE_EN": "Flat", "USAGE_EN": "Residential", "TOTAL_PROPERTIES": 6},
        {"REGISTRATION_DATE": "2026-09-15T09:00:04", "START_DATE": "2026-09-15T00:00:00", "VERSION_EN": "New",
         "AREA_EN": "Al Barsha South Fourth", "PROJECT_EN": "Z", "ANNUAL_AMOUNT": 120000, "ACTUAL_AREA": 90,
         "PROP_TYPE_EN": "Unit", "PROP_SUB_TYPE_EN": "Office", "USAGE_EN": "Commercial", "TOTAL_PROPERTIES": 1},
    ])
    rec, counts = clean(feed, "rent")
    assert len(rec) == 1                      # renewal, multi-unit contract and office are left out
    r = rec.iloc[0]
    assert (r["month"], r["area_id"], r["ptype"]) == ("2026-09", "AL BARSHA SOUTH FOURTH", "apartment")
    assert abs(r["ppsf"] - 80000 / (67.6 * 10.7639)) < 1e-6
    assert counts["duplicates"] == 0


def test_size_groups_from_stated_bedrooms():
    import numpy as np
    rng = np.random.default_rng(1)
    typical = {"studio": 430, "1": 800, "2": 1250, "3": 1800, "4+": 2900}
    rows = [pd.DataFrame({"ptype": "apartment", "stated_beds": b, "size_sqft": s * np.exp(rng.normal(0, 0.12, 400))})
            for b, s in typical.items()]
    bands = B.calibrate(pd.concat(rows, ignore_index=True))
    lim = bands["limits_sqft"]["apartment"]
    assert bands["measured"]["apartment"] and not bands["measured"]["villa"]
    assert abs(lim[0] - (430 * 800) ** 0.5) < 25 and lim == sorted(lim)
    assert bands["limits_sqft"]["villa"] == B.DEFAULT["villa"]
    got = B.assign(pd.Series([300, 700, 1300, 1700, 5000, 1000]),
                   pd.Series(["apartment"] * 5 + ["villa"]), bands)
    assert got.tolist() == ["studio", "1", "2", "3", "4+", "2"]
