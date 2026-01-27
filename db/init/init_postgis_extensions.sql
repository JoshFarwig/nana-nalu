-- NOTE: defensive connect incase scripts are reordered, database name is hard
-- coded though, change to DB__NAME if issues arise with PostGIS on init
\c nn_db

CREATE EXTENSION IF NOT EXISTS postgis; 

-- -- Potentially useful extensions for advanced spatial queries and data types
-- -- Topology support (optional, for advanced topological queries)
-- CREATE EXTENSION IF NOT EXISTS postgis_topology; 

-- -- Should enable for p3 
-- Raster support (for bathymetry, weather, or other gridded data) 
-- CREATE EXTENSION IF NOT EXISTS postgis_raster;

-- Fuzzy string matching (optional, for searching place names, etc.)
-- CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
