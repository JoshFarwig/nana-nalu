# NOAA's NWPS (nearshore wave prediction system)

## NOMADS portal, model, and data

accessible via [nomads prod url](https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod), provides grib2 files and includes model generations for each region, split into specific [sites](https://www.census.gov/topics/preparedness/related-sites/nws.html) (hawaii is HFO)

each site runs models at at 00 06 12 and 18Z
sites may include more than one grid. the online
model viewer portal makes it a bit easier to figure out which CG (computational grid?) is related to
what section. i.e. for [Maui](https://polar.ncep.noaa.gov/nwps/nwpsloop.php?site=HFO&cg=4), the CG=4.

unforunately no OPenDAP portal for the NWPS, grib filter + https is accessible though

model runs include 2d wave spectral files for noaa bouys that exist
in the region. not sure if I will need this or not

grib2 files for hawaii range from 50-100MB due to being an island chain,
requiring a denser computational grid to portray accurate representations.
also just more marine geometry vs the mainland.

grib filters do exist! -> [url](https://nomads.ncep.noaa.gov/gribfilter.php?ds=prnwps), for more [info](https://nomads.ncep.noaa.gov/info.php?page=gribfilter)
use partial http-transfer method for just specific parameters.
honestly, smaller area for the grib2 (since only coastlines really are needed for the grib2 file, could cut 30% of generation w/ grib2 filter), should make it smaller and better for maui.

## grid data implementation brainsplash

considering the multi-user approach, think it makes the most sense
to make all spots global to the application (if the home-surf forecasting)
is planned to just be used by friends.

IF spots are planned to be localized by user, where different users can have spots that
are the same (but are seperate instances), ALL grib2 data should be stored in redis cache
in a grid format, then personal spots all fetch from the grid based on their point geometry.
this approach is a much more V2-V3 kind of thing, the MVP should just focus
on a self-deployed app that can be shared with friends. account creations are required to
make spots / add observations.

To develop for all of hawaii, consider using CG=1 and gribfilter to
create subsections of coastlines of each island.

this goes the same for any island encompassed by the NWPS.

normal mainland sections should be easier.

decide if admin spots are public and user spots are only visible to users + admin, like this better
