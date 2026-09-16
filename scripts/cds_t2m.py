import cdsapi, sys
S=sys.argv[1]
import pathlib
key=[l.split(":",1)[1].strip() for l in pathlib.Path.home().joinpath(".cdsapirc").read_text().splitlines() if l.startswith("key")][0]
c=cdsapi.Client(url="https://cds.climate.copernicus.eu/api", key=key)
area=[16,-3,12.5,1.5]   # N,W,S,E — covers Loroum/Oudalan/Séno/Yagha with margin
common=dict(originating_centre="ecmwf", system="51", variable=["2m_temperature"], product_type=["monthly_mean"],
            month=["09"], leadtime_month=["1","2","3"], area=area, data_format="netcdf")
c.retrieve("seasonal-monthly-single-levels", dict(common, year=["2026"]), f"{S}/seas5_t2m/fc_2026_09.nc")
c.retrieve("seasonal-monthly-single-levels", dict(common, year=[str(y) for y in range(1993,2017)]), f"{S}/seas5_t2m/hc_1993_2016_09.nc")
print("done")
