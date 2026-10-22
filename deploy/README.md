# deploy/: running the rebuilt app on the PC

How `server/` and `web/` run outside development: Docker images built on the PC, one compose file for
every environment, and an observability stack beside them. The old app's `compose*.yaml` at the repo
root are not used here; they leave with Django.

## Three environments

| | dev | test | prod |
|---|---|---|---|
| Where | the Mac (any machine with Docker, uv and Node) | the PC | the PC |
| How | `server/dev.sh run` + `npm run dev` in `web/`: source code, reloads on every edit | the production images | the same images, once test passed |
| Data | a dev database you can throw away | can be reset (`deploy.sh reset test`) | real, backed up |
| Address | `http://localhost:5173` | `http://<lan-ip>:8091` | `http://<lan-ip>:8090` (not started yet) |
| Telemetry | off; on when you are chasing something (below) | on | on |

Dev stays on the machine where the code changes: a deployed dev environment would need a deploy for
every edit. Test and prod are the same compose file (`compose.yaml`) run as two compose projects,
`coji-test` and `coji-prod`, each with its own database and photo volumes; `test.env` and `prod.env`
hold what differs (name, port, CPU weight), and `secrets/<env>.env` (not in git) the passwords and
the model service. The old app keeps 8080 until it retires.

Each environment runs four containers:

- `db`: PostgreSQL 17, its data in the `pgdata` volume.
- `api`: the FastAPI app (two uvicorn processes), behind nginx.
- `worker`: `python -m cojidaily.worker`, which runs the readings and other jobs.
- `web`: nginx with the built page; it passes `/api/` to `api` and is the only port published.

`api` and `worker` share the `blobs` volume (the photos). Before they start, `migrate` (the same
image) brings the schema up to date once.

## A release: build once, promote the same images

```
Mac:  commit → merge into master → push
PC:   git pull --ff-only
      deploy/deploy.sh build          # cojidaily-server:<commit>, cojidaily-web:<commit>
      deploy/deploy.sh up test        # migrate, start, wait until healthy, check the page and API
      ... try it on test (the phone: http://<lan-ip>:8091) ...
      deploy/deploy.sh promote        # back up prod, then run it on the tag test runs
```

`build` refuses when `server/` or `web/` has uncommitted changes, so an image's tag is always the
commit it was built from. `promote` never builds: prod runs the image test ran, not a rebuild that
could differ. `deploy.sh status` shows which tag each environment runs.

## First time on the PC

```bash
deploy/deploy.sh init test         # writes deploy/secrets/test.env (VLLM_* from the repo's .env)
deploy/deploy.sh obs up            # Grafana on :3000
deploy/deploy.sh build
deploy/deploy.sh up test
deploy/deploy.sh cli test createuser NAME   # asks for the password
```

Prod later is `init prod`, then `promote`, then the nightly backup below.

## Observability: one stack for every environment

`observability/compose.yaml` is Grafana's all-in-one image (OpenTelemetry Collector, Prometheus,
Tempo, Loki, Pyroscope, Grafana) as a compose project of its own, `coji-obs`. Test and prod send to
it as `lgtm:4318` over the `coji-obs` network; every signal carries
`deployment.environment.name=test|prod`, so one Grafana shows either. Resetting test or stopping
an environment keeps its history.

It shares the PC with prod, so it is held back: at most 2 GiB of memory and two CPUs, a quarter of
the app's CPU weight when both want the CPU, and it is the first container the kernel kills if
memory runs out. Test, in turn, has half of prod's CPU weight. The app never waits for it: when the
collector is down the SDK drops what it cannot send.

What arrives:

- **Traces:** each request (FastAPI), its SQL (psycopg), the call to the model (urllib), each job
  (`job <kind>`, with how long it waited and how it ended), and the reading engine's own spans.
- **Metrics:** request durations, `coji.job.wait` (how long a ready job waited for a worker),
  `coji.job.duration` by outcome, the model's token use.
- **Logs:** the API's and worker's log lines, with the trace they belong to.

The code only calls the OpenTelemetry API; the SDK and the instrumentation are the `otel` extra in
`server/pyproject.toml`, installed in the image and switched by the `OTEL_*` variables in
`compose.yaml` (`OTEL_SDK_DISABLED=true` in an env file turns an environment's telemetry off). Dev
does not install them, so the same calls do nothing there. To look at dev for once, run the stack
locally and start the API under the instrumentation:

```bash
docker run --rm -p 3000:3000 -p 4318:4318 grafana/otel-lgtm:0.34.0
cd server && OTEL_SERVICE_NAME=cojidaily-dev OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf uv run --extra otel opentelemetry-instrument \
  uvicorn cojidaily.main:create_app --factory --port 8000   # with dev.sh's COJI_* variables
```

Grafana opens without a login and is on the home Wi-Fi: anyone there can read request paths, ids,
timings and errors (no photos). Retention: Prometheus keeps 15 days, at most 2 GB; Tempo and Loki
keep the image's defaults. Starting over: `deploy.sh obs down`, then `docker volume rm coji-obs_data`.

## Backups

`deploy.sh backup ENV` writes `~/cojidaily-backups/ENV/<time>/`: `db.dump` (`pg_dump`, custom
format), `blobs.tgz` (the photos) and `manifest` (the tag and time). It keeps the newest 14.
`deploy.sh restore-check ENV DIR` restores a backup into a scratch database beside ENV's, compares
the rows of every table and the number of photo files with the live ones, and drops it again: a
restore drill that touches nothing live. `promote` backs prod up before changing it.

When prod starts, back it up every night with a crontab line on the PC (`crontab -e`):

```
15 3 * * * cd ~/CojiDaily && deploy/deploy.sh backup prod >> ~/cojidaily-backups/backup.log 2>&1
```

The backups stay on the PC's disk: a dead disk takes them along. Copying them off the PC is not set up.

## Ports on the PC

| Port | What |
|---|---|
| 8090 | prod (not started yet) |
| 8091 | test |
| 3000 | Grafana (the old test stack's `OTEL=1` also wants it; run one at a time) |
| 8080 | the old app, until it retires |

Not here yet: HTTPS (plain HTTP on the home Wi-Fi, as decided in `pm/topics/app-hosting-setup.md`),
a limit on login attempts, alerts.
