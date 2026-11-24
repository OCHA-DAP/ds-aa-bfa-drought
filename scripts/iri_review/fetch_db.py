"""Pull SEAS5 forecasts and ERA5 observations for the AOI from the team's prod DB (read-only).

AOI = the old regions Boucle du Mouhoun BF46, Centre-Nord BF49, Nord BF54, Sahel BF56 (the DB uses
the 2020 COD-AB: 13 regions, 45 provinces), at admin 1 and admin 2, plus polygon areas.
SEAS5: issues Feb-Jul, valid Jun-Oct, ensemble-mean precipitation (mm/day), leadtime 0 = issue month.
ERA5: monthly precipitation (mm/day), Jun-Oct.

Usage: DSCI_AZ_DB_PROD_HOST=127.0.0.1:15433 BFA_DATA_DIR=... uv run --no-project --with ocha-stratus \
           --with psycopg2-binary --with pandas --with pyarrow python fetch_db.py
"""

import ocha_stratus as stratus
import pandas as pd
from sqlalchemy import text

import data

AOI1 = ["BF46", "BF49", "BF54", "BF56"]


def main() -> None:
    out = data.data_dir() / "db"
    out.mkdir(exist_ok=True)
    eng = stratus.get_engine(stage="prod")
    like = " or ".join(f"pcode like '{p}%'" for p in AOI1)
    with eng.connect() as c:
        poly = pd.read_sql(text(f"select pcode, name, area, adm_level from polygon where iso3='BFA' and ({like})"), c)
        s5 = pd.read_sql(text(
            f"select pcode, adm_level, issued_date, valid_date, leadtime, mean from seas5 "
            f"where iso3='BFA' and adm_level in (1,2) and ({like}) "
            f"and extract(month from issued_date) between 2 and 7 and extract(month from valid_date) between 6 and 10"), c)
        e5 = pd.read_sql(text(
            f"select pcode, adm_level, valid_date, mean from era5 where iso3='BFA' and adm_level in (1,2) "
            f"and ({like}) and extract(month from valid_date) between 6 and 10"), c)
    poly.to_csv(out / "polygon_aoi.csv", index=False)
    s5.to_parquet(out / "seas5_aoi.parquet", index=False)
    e5.to_parquet(out / "era5_aoi.parquet", index=False)
    print(len(poly), len(s5), len(e5), s5.issued_date.min(), s5.issued_date.max(), e5.valid_date.max())


if __name__ == "__main__":
    main()
