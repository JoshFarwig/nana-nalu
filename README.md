<div align="center">

<img src="./light_logo.svg" width="200" alt="nānā nalu logo" />

# nānā nalu

![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white)
![TimescaleDB](https://img.shields.io/badge/TimescaleDB_%2B_PostGIS-FDB515?logo=timescale&logoColor=black)
![Prefect](https://img.shields.io/badge/Prefect-024DFD?logo=prefect&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![React](https://img.shields.io/badge/React_19-20232A?logo=react&logoColor=61DAFB)
![MapLibre](https://img.shields.io/badge/MapLibre_GL-396CB2?logo=maplibre&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)

</div>

> **Status:** active refactor toward a public ocean-data dashboard. MVP target is a no-auth MapLibre frontend backed by full-grid forecast ingestion.

Open Maui ocean-data dashboard. Prefect pipelines ingest GRIB2 and NetCDF model output from NOAA and PacIOOS, store full forecast grids in TimescaleDB hypertables, and serve them via a public FastAPI. MapLibre frontend paints the grid and resolves point forecasts via nearest-neighbor at query time.

---

## Data Sources

| Provider | Model | Format | Region | Schedule |
|----------|-------|--------|--------|----------|
| NOAA NOMADS | NWPS — Nearshore Wave Prediction System | GRIB2 | Maui | 3×/day (10:00, 14:00, 21:00 UTC) |
| PacIOOS ERDDAP | Tide MHI — harmonic tidal predictions | NetCDF | Maui | Weekly (Sun 06:00 UTC) |
| NDBC | Realtime buoy observations (51202, 51201, 51204) | fixed-width txt | Maui | hourly *(planned)* |
| NOAA NOMADS | GFS-Wave / WaveWatch III | GRIB2 | Maui | *(planned)* |
| PacIOOS ERDDAP | ROMS — regional ocean currents + SSH | NetCDF | Maui | *(planned)* |

Ingestion fetches per-source subregions (NOMADS grib filter, ERDDAP GridDAP) and writes every valid ocean cell as a JSONB-payload row into a TimescaleDB hypertable, anchored to a `model_runs` row keyed by `(provider, model, region, run_time)`. Nearest-neighbor is no longer an ingestion concern — the API resolves it at query time against the stored grid.

### Why multiple sources

Cross-verification. Global spectral models (WW3, GFS-Wave) reveal which swell trains are in the water; NWPS resolves nearshore wave transformation at high resolution with WFO-developed wind grids and sea surface height; ROMS adds currents and SSH; buoys ground-truth all of it.

---

## Running Locally

**Prerequisites:** Docker, Docker Compose

```bash
cp .env.dev.example .env.dev    # fill in credentials
make up-dev-full                # start + migrate + seed
```

Useful commands:

```bash
make logs-dev      # follow logs
make watch-dev     # file sync / hot reload
make migrate-dev   # apply latest migrations
make down-dev      # stop all services
make help          # full command list
```

Exposed on localhost:

| Service | Port |
|---------|------|
| API (FastAPI) | `8000` |
| Prefect UI | `4200` |
| TimescaleDB | `5432` |

Prefect worker auto-deploys flows on startup against the `forecasts` work pool. Trigger manual runs from `localhost:4200`.
