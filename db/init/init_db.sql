-- Create Prefect database for workflow orchestration
CREATE DATABASE prefect;

-- Enable timescaledb extension 
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Enable postGIS extensions in timescaledb image 
CREATE EXTENSION IF NOT EXISTS postgis;
