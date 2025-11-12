# NOAA's NWPS (nearshore wave prediction system)

## the data

accessible via [nomads prod url](https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod), provides grib2 files annd includes model generations for each region, split into specific [sites](https://www.census.gov/topics/preparedness/related-sites/nws.html) (hawaii is HFO)

each site runs models at different times. i.e. for HFO its 00 and 12.
they will also include may include more than one grid or section. the online
model viewer portal makes it a bit easier to figure out which CG (computational grid?) is related to
what section. I.e. for [Maui](https://polar.ncep.noaa.gov/nwps/nwpsloop.php?site=HFO&cg=4), the CG=4.

unforunately no OPenDAP portal for the NWPS, I assume it would be difficult with diferent sites
having different requirements or data needs for their SWAN models.

model runs include 2d wave spectral files for noaa bouys that exist
in the region. not sure if I will need this or not.

grib2 files for hawaii range from 50-100MB due to being an island chain,
requiring a denser computational grid to portray accurate representations.
