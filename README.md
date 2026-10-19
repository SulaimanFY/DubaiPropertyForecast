# Dubai Property Forecast

**What will rent and prices be next year in my area?** 12-month forecasts of rent and sale prices for Dubai areas, by home type and bedroom count, built from Dubai Land Department open data. A scheduled pipeline downloads the new data every month, checks it, retrains the model, scores past forecasts against what really happened and republishes the site.

**Live site: [sulaimanfy.github.io/DubaiPropertyForecast](https://sulaimanfy.github.io/DubaiPropertyForecast/)**

## Accuracy on the test years

Forecasts made from 2023 to 2025, each scored 12 months later against what really happened. Those years were kept aside while the method was designed. Details and every horizon on the [track record](https://sulaimanfy.github.io/DubaiPropertyForecast/track-record.html) page.

| 12 months ahead | Rent | Sale price |
|---|---|---|
| Typical error of this model (median) | **4.9%** | **9.9%** |
| Assuming no change | 9.8% | 12.5% |
| Best simple benchmark (Dubai-wide trend applied to every area) | 8.6% | 8.4% |
| Real outcomes inside the 80% range | 82% | 69% |
| Direction right, where the real move was over 2% | 88% | 72% |

For rents, the model halves the error of assuming no change and beats every benchmark. For sale prices it beats no change, but the Dubai-wide trend did better and the ranges were too narrow. The site says so too.

## What it does

- Forecasts two things, 1 to 12 months ahead, with 50% and 80% ranges:
  - the yearly rent per sq ft of **new** Ejari lease contracts for a single home, by contract start month,
  - the sale price per sq ft of residential sales (ready and off-plan),
  
  for every Dubai area, apartments and villas or townhouses, studios to 4+ bedrooms, wherever there are at least 30 deals in the last 3 months and 3 years of history.
- Bedrooms are grouped by floor area, because rent contracts rarely state them. The size limits are measured once from the sales that do state bedrooms (a home counts as 2 bedrooms when its size is closer to a typical 2-bedroom than to a typical 1- or 3-bedroom) and saved in `data/size_bands.json`. The same groups apply to rents and prices, so yields compare like with like.
- Turns each forecast into a typical home: "a 1-bedroom apartment in Dubai Marina rents for about AED X a year today; most likely AED Y in 12 months, 8 in 10 chance between A and B".
- Ranks areas by expected change, and shows the gross rental yield where both rent and price exist.
- Publishes an honest track record: a backtest on years the model never saw, compared with simple benchmarks, plus a live record of every published forecast against the real outcome.

The history runs from January 2010 to September 2026: about 2.5 million new lease contracts and 1.0 million sales after cleaning. 109 areas have enough recent deals for a published forecast.

## Method in short

| Step | Choice | Why |
|---|---|---|
| Typical level | Geometric mean price per sq ft after trimming the 5% most extreme deals on each side, pooled over 3 months | Robust like a median, but adds up exactly from monthly totals, so history never needs the raw records |
| Model | One LightGBM model across all areas, horizons 1 to 12 months, quantile objectives (10, 25, 50, 75, 90%) | Small areas borrow strength from large ones; one model is easy to retrain monthly |
| Inputs | Momentum of the area and of Dubai, volatility, deal counts and their change, rent-to-price yield, off-plan share, season | All known on the forecast date; nothing from the future |
| Ranges | Conformal calibration on the most recent 12 months of outcomes | So that 8 in 10 real outcomes land inside the 80% range |
| Benchmarks | No change, last year's trend, Dubai-wide trend, ETS per series | The model is only worth using if it beats these |
| Test | Rolling-origin backtest; origins before 2023 for design choices, 2023 onward kept untouched as the test | Honest, out-of-sample accuracy |

## Monthly pipeline (MLOps)

`.github/workflows/monthly.yml` runs on the 3rd of every month:

1. **Download** the newest sales and lease records from the Land Department's open data feed.
2. **Check** them: volumes against the last 12 months, missing fields, impossible values, duplicates, sudden jumps in the Dubai-wide level. Any failure stops the run, keeps the last good site online and opens an issue.
3. **Measure** monthly statistics per segment and store them in `data/aggregates/` (versioned in git).
4. **Retrain** the model, recalibrate its ranges and check it has not got worse than last month.
5. **Score** every archived forecast whose target month has arrived.
6. **Publish**: save this month's forecast unchanged in `data/forecasts/` and deploy the site to GitHub Pages.

A second run on 31 December stores the last weeks of the year before the live feed moves to the new year.

## Run it yourself

The live feed only covers the current year. The full history comes from two datasets on data.dubai, which only open from inside the UAE: [Real Estate Transactions](https://data.dubai/en/l/470061) (2 CSV parts, about 1.1 GB) and [Rent Contracts](https://data.dubai/en/l/468586) (11 parts, about 5.1 GB). Download the CSV parts into one folder, then:

```bash
pip install -r requirements.txt
python -m dpf.run rebuild --raw <folder>   # monthly statistics from the history files (one-off)
python -m dpf.run update     # add recent months from the live feed, with data checks
python -m dpf.run backtest   # accuracy on past years (about 3.5 hours on 4 cores)
python -m dpf.run forecast   # retrain, forecast, archive, score
python -m dpf.run site       # write the website into _site/
pytest -q
```

## Data and licence

Source: Dubai Land Department open data, [Real Estate Transactions](https://data.dubai/en/l/470061) and [Rent Contracts](https://data.dubai/en/l/468586), published on [data.dubai](https://data.dubai) under the Dubai Open Data Licence. Only monthly statistics derived from it are stored and published here, never individual records; those statistics (`data/`) are shared under the same licence. This is an independent project, not associated with or endorsed by the Dubai Land Department or the Government of Dubai. Forecasts are statistical estimates, not financial advice.

Code: MIT licence.
