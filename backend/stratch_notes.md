# backend scratch notes

## PacifIOOS

### maui's SWAN model

important to note, each field needs time, depth, lat/long constraints
(some constraints have defaults)

example for dumps: with at of lat 20.615 and long 203.45
(pacioos does also include a erddap https api for -/+ 180 long)

> using october 1-5th times since shutdown on the 17th? not sure why?

- <https://pae-paha.pacioos.hawaii.edu/erddap/griddap/swan_maui.json?mdir[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)>][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],mper[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],pdir[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],pper[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],shgt[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)]

## surfline v2

surfline does expose is public api and has been [reverse engineered](https://github.com/swrobel/meta-surf-forecast?tab=readme-ov-file#surfline) a few times. refer to the params in this readme

when creating a new spot, consider having an optional surfline_v2_id to
allow for pulling forecast data from surfline for a greater breath of options?

example url for dumps:

- <https://services.surfline.com/kbyg/spots/forecasts/wave?spotId=5842041f4e65fad6a7708b2b>

## NOAA WaveWatcher III  

noaa provides a global wave-model forcasting option, this or surfline should act as a fall-back

## todos

- [x] complete startup.py and integate it into app.py
- [x] validate new model structure works, refactor to include dev / prod configs
- [ ] add entrypoint for container to execute seed script and add spots

- [ ] add celery/ folder for worker + beat
