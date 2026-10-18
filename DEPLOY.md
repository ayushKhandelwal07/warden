# Deploy

## Backend on EC2 (Docker)
1. Launch an Ubuntu instance (t3.medium or larger), open ports 80 and 443, install Docker and the Compose plugin.
2. Point a DNS name (for example `api.yourdomain.com`) at the instance.
3. `git clone` the repo, then `cp .env.example .env` and fill it in: `API_DOMAIN`, `GITHUB_*`, `LLM_API_KEY`, `SESSION_SECRET`, `CORS_ORIGINS` (your Vercel URL), `WARDEN_URL` (same), and either `DATABASE_URL` for Neon or `POSTGRES_PASSWORD` with the `localdb` profile.
4. `docker compose -f docker-compose.prod.yml up -d --build` (add `--profile localdb` to run Postgres on the box).
5. The first start clones the repository at `DEMO_REF` and builds the graph; check `https://API_DOMAIN/api/health`.

FalkorDB Cloud instead of the container: set `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, `FALKORDB_SSL=true` in `.env` and remove the `falkordb` service.

## Frontend on Vercel
1. Import the repo, set the root directory to `frontend`, framework Vite (`vercel.json` is already there).
2. Set `VITE_API_URL=https://API_DOMAIN`. Redeploy.
3. The API sets a `SameSite=None; Secure` cookie, so the browser keeps the session across the two origins.
