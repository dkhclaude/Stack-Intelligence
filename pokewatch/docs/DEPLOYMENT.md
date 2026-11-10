# Deployment — keeping PokéWatch running 24/7

Monitoring runs in the **worker** process. Deploying only the dashboard (for example on Streamlit Community Cloud)
would **not** run any checks. GitHub Actions is used for tests only. Its scheduled runs are delayed by 5–15+ minutes
and can be dropped, which makes it unsuitable for 5-minute restock checks.

## Options compared

| Option | Monthly cost | Runs with laptop closed? | Effort | Notes |
|---|---|---|---|---|
| **Small VPS + Docker Compose** *(recommended)* | ~$4–7 (Hetzner CX22 / DigitalOcean / Vultr 1–2 GB) | ✅ | Low | Choose a **US region**, since some US retailers geo-filter. Full control, Postgres included, restart-on-failure via Docker |
| Raspberry Pi at home (systemd) | ~$1 power (+ ~$60–80 once) | ✅ (if Pi stays on) | Medium | Home IP; depends on home internet/power. Use `deploy/pokewatch-worker.service` |
| Managed containers (Fly.io / Railway / Render) | ~$5–15 | ✅ | Low–Med | Needs an always-on worker plan (no scale-to-zero) plus managed Postgres or a volume |
| Your laptop | $0 | ❌ stops on sleep | Lowest | Fine for development and trying the dashboard |

Other running costs: Best Buy API free; Discord and Telegram free; Pokémon TCG API free tier; Claude classification is
optional, runs only on ambiguous new titles, and is cached, so it should be well under $1/month.

## VPS setup (Docker Compose)

```bash
# on a fresh Ubuntu VPS
curl -fsSL https://get.docker.com | sh
git clone <your repo> && cd Stack-Intelligence/pokewatch
cp .env.example .env && nano .env        # set POSTGRES_PASSWORD, BESTBUY_API_KEY, DISCORD_WEBHOOK_URL / TELEGRAM_*
docker compose up -d --build              # db + worker + dashboard + nightly backup
docker compose exec worker pokewatch verify bestbuy        # real API call → marks connector LIVE-VERIFIED
docker compose exec worker pokewatch test-alert discord    # sends a labelled test message
docker compose ps                                          # worker should become "healthy"
```

* **Database initialization:** automatic (tables are created on worker/dashboard start; `pokewatch init-db` also works).
* **Restart on failure:** `restart: unless-stopped` on every service. The worker healthcheck runs `pokewatch health`
  (fails if no heartbeat for about 4 minutes). For automatic restarts of an *unhealthy* (hung) container, add the
  `willfarrell/autoheal` container or a cron job: `docker compose ps --filter health=unhealthy -q | xargs -r docker restart`.
* **Recovery:** on start, the worker marks jobs left `running` by a crash as `abandoned`. Job locks expire on their own,
  and coalescing prevents a burst of missed runs.
* **Dashboard access:** bound to `127.0.0.1:8501`. Open it with `ssh -L 8501:localhost:8501 you@vps`, or install
  Tailscale. Don't expose it publicly without authentication.
* **Health monitoring:** the Command Center tile turns red when the heartbeat is missing. For phone alerts when the
  whole server is down, add a free external uptime monitor (for example, a cron job that hits a healthchecks.io URL
  after `pokewatch health` succeeds).

## Backups

* Compose's `backup` service writes `data/backups/pokewatch-YYYY-MM-DD.sql.gz` nightly and keeps the 14 newest.
* Copy them off the server weekly, for example with `rclone copy data/backups remote:pokewatch`.
* Restore: `gunzip -c file.sql.gz | docker compose exec -T db psql -U pokewatch pokewatch`.
* SQLite installs: `deploy/backup_sqlite.sh` (hot backup, safe while the worker runs).

## Without Docker (Pi / bare VPS)

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install --no-deps -e .
cp .env.example .env   # SQLite default is fine for one user
sudo cp deploy/pokewatch-worker.service /etc/systemd/system/ && sudo systemctl enable --now pokewatch-worker
streamlit run dashboard/app.py    # or a second systemd unit
```
