-- Create Prefect database for workflow orchestration
CREATE DATABASE prefect;


-- Enable postGIS extensions in timescaledb image 
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
