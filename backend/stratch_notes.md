# backend scratch notes

## example urls for PacIOOS Maui SWAN erddap

important to note, each field needs time, depth, lat/long constraints
(some constraints have defaults)

example for dumps: with at of lat 20.615 and long 203.45
(pacioos does also include a erddap https api for -/+ 180 long)

> using october 1-5th times since government shutdown
> has shut down new SWAN model runs

- `https://pae-paha.pacioos.hawaii.edu/erddap/griddap/swan_maui.json?mdir[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],mper[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],pdir[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],pper[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)],shgt[(2025-10-01T00:00:00Z):1:(2025-10-05T00:00:00Z)][(0.0):1:(0.0)][(20.615):1:(20.615)][(203.45):1:(203.45)]`

## todos

- [x] complete startup.py and integate it into app.py
- [ ] validate new model structure works, refactor to include dev / prod configs
- [ ] add entrypoint for container to execute seed script
- [ ] add celery/ folder for worker + beat

## infra-todos

- [ ] add json logging for production + dozzle for monitoring?

## v2 todos

- [ ] (look into loki,grafana for future for v2-learning distributed k8's etc) 
