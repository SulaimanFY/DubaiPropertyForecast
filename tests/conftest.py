"""Small synthetic deals for unit tests only. The real pipeline never uses these."""
import numpy as np
import pandas as pd
import pytest


def synthetic_deals(months=72, areas=("AREA A", "AREA B", "AREA C"), seed=0, start="2018-01"):
    rng = np.random.default_rng(seed)
    rows = []
    periods = pd.period_range(start, periods=months, freq="M")
    for ai, area in enumerate(areas):
        for measure, base in (("rent", 90.0), ("price", 1400.0)):
            for ptype in ("apartment", "villa"):
                for beds in ("1", "2", "3"):
                    trend = 0.004 * (ai + 1)
                    for t, m in enumerate(periods):
                        n = rng.integers(15, 40)
                        lvl = base * (1.2 if ptype == "villa" else 1.0) * np.exp(trend * t + 0.03 * np.sin(t / 6))
                        ppsf = lvl * np.exp(rng.normal(0, 0.15, n))
                        size = rng.uniform(600, 1500, n)
                        rows.append(pd.DataFrame({
                            "measure": measure, "month": str(m), "area_id": area, "ptype": ptype, "beds": beds,
                            "ppsf": ppsf, "size_sqft": size, "amount": ppsf * size,
                            "offplan": rng.random(n) < (0.5 if measure == "price" else 0),
                        }))
    return pd.concat(rows, ignore_index=True)


@pytest.fixture(scope="session")
def deals():
    return synthetic_deals()
