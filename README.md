<div align="center">

<img src="./light_logo.svg" width="200" alt="nānā nalu logo" />

# nānā nalu

![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_%2B_PostGIS-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![Prefect](https://img.shields.io/badge/Prefect-024DFD?logo=prefect&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![React](https://img.shields.io/badge/React_19-20232A?logo=react&logoColor=61DAFB)
![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)

</div>

> **Note:** this project is actively under development, a live version is planned once MVP is completed

Surf forecast aggregation app for Maui. Ingests GRIB2 and NetCDF model output from NOAA and PacIOOS via scheduled Prefect pipelines, matches data to user-defined surf spots using spatial nearest-neighbor search, and serves it through a FastAPI REST API. No third-party forecast APIs. Spots are private: yours or your crew's. Condition profiles let you define exactly when a spot goes off across multiple models and get notified when it does.

The web app (React 19 + Vite) is a work in progress, planned to be mobile friendly.

---

## Data Sources

| Provider | Model | Format | Regions | Schedule |
|----------|-------|--------|---------|----------|
| NOAA NOMADS | NWPS:Nearshore Wave Prediction System | GRIB2 | Maui | 3×/day (10:00, 14:00, 21:00 UTC) |
| PacIOOS ERDDAP | Tide MHI:harmonic tidal predictions | NetCDF | Maui | Weekly (Sun 06:00 UTC) |
| NOAA NOMADS | GFS Wave / WaveWatch III | GRIB2 | Maui | planned |
| PacIOOS ERDDAP | SWAN:spectral wave model | NetCDF | Maui | planned |
| PacIOOS ERDDAP | ROMS:regional ocean model | NetCDF | Maui | planned |

GRIB2 files are fetched via the NOMADS grib filter API. NetCDF subsets are pulled via ERDDAP GridDAP with spatial and temporal constraints baked into the request URL. Forecast extraction uses a cKDTree nearest-neighbor search to match surf spots to the closest model grid cell, with a max distance threshold to prevent matching to inland or open-ocean points.

### Why multiple sources?

Having more than one model covering the same region means you can cross-verify. Global spectral models like WaveWatch III and GFS Wave cover a much larger domain and give a broader picture of what swell trains are in the water. NWPS resolves most of the nearshore data needs, with high-resolution wave transformation driven by forecaster-developed wind grids from local WFOs, and sea surface height. Layering in SWAN gives a second nearshore wave estimate. ROMS brings in sea surface height and currents, which can tell you whether higher-than-expected wave heights are getting a boost from increased water volume or whether a rip is running hard. Put it all together and a condition profile stops being just "swell height + period" and becomes something closer to a real read on whether a spot is actually on.

---

## Running Locally

**Prerequisites:** Docker, Docker Compose

1. Copy the dev env file and fill in credentials:

   ```bash
   cp .env.dev.example .env.dev
   ```

2. Start all services (first time: includes migrations + seed):

   ```bash
   make up-dev-full   # start, migrate, and seed
   # or
   make up-dev        # start only
   ```

3. Other useful commands:

   ```bash
   make logs-dev      # follow logs
   make watch-dev     # file sync / watch mode
   make migrate-dev   # apply latest migrations
   make down-dev      # stop all services
   make help          # list all commands
   ```

4. Services exposed on localhost:

   | Service | Port |
   |---------|------|
   | API (FastAPI) | `8000` |
   | Prefect UI | `4200` |
   | PostgreSQL | `5432` |
   | Redis | `6379` |

The Prefect worker auto-deploys flows on startup and connects to the `forecasts` work pool. Forecast workflows run on their configured schedules; trigger a manual run from the Prefect UI at `localhost:4200`.
