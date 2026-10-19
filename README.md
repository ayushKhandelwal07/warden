# Warden

Warden builds a graph of a software repository, its services, dependencies, vulnerabilities, owners, and change history. An AI agent uses that graph to answer security and change risk questions with traceable evidence. It can rehearse a dependency upgrade on a copy of the graph, explain the result, and prepare a change for human approval.

> A graph path is evidence of modeled reachability. It is not proof that a vulnerable function is called or that the application is exploitable.

## Live demo

| | |
|---|---|
| Repository | [github.com/ayushKhandelwal07/warden](https://github.com/ayushKhandelwal07/warden) |
| Live demo | [warden-bice.vercel.app](https://warden-bice.vercel.app/) |
| Demo login | `test@gmail.com` |
| Password | `test@gmail.com` |

These credentials are for the public demo account only. Do not reuse this password for any personal or production account.

## What it does

- **Maps repository structure.** Finds services, their dependencies, deployment topology, and service-to-service calls where repository configuration gives evidence for them.
- **Prioritizes vulnerability findings.** Connects installed package versions to OSV advisories and enriches findings with CISA KEV and FIRST EPSS data. NVD CVSS lookups are optional.
- **Explains findings.** The Ask view can show the graph path, source, Cypher query, and tool calls behind an answer. A deterministic verifier checks important claims against tool results.
- **Plans and rehearses fixes.** The planner applies candidate upgrades to a temporary FalkorDB graph copy, then re-runs exposure analysis and safety checks.
- **Keeps people in control.** Plans and PR analyses become pending approvals. Their GitHub writes happen only after a person approves, and only on the configured target. The Watcher has a clearly labeled demo control that directly commits a one-line exposure change to the connected repository; use a disposable fork for that simulation.
- **Tracks follow-up.** Sync and the watcher can re-read a repository and compare graph state. Warden can check whether an approved fix removed the exposure and notice newly modeled exposure.
- **Supports multiple projects.** A shared Online Boutique sample project is available. A new project can build its own graph from a GitHub repository and selected branch.
- **Provides MCP tools.** The graph tools are available to Warden and to external MCP clients through the MCP server.

## What it does not do

- It does not perform runtime traffic analysis or prove that an exploit works.
- It does not currently do function-level vulnerability reachability.
- Service calls may be inferred from manifests, environment variables, or Compose configuration. The UI labels inferred and curated evidence.
- A successful rehearsal only demonstrates graph impact. It does not prove that an upgrade preserves application behavior. Review and run the target project's CI/tests before merging.
- Warden does not automatically merge pull requests. Plan/PR actions require a configured target and human approval; the Watcher's explicit demo exposure/undo controls are documented exceptions that commit a one-line topology change directly.
- Repository discovery supports common layouts and dependency files, but it is not a universal importer. Results depend on what can be identified from the repository.
- EPSS and KEV are point-in-time data and should be refreshed for operational decisions.
- LLM answers require an external OpenAI-compatible model endpoint. Graph tools and non-LLM views work without an LLM key, but Ask cannot generate model answers.

## Project layout

| Path | Purpose |
|---|---|
| `backend/warden/` | FastAPI API, agent, graph tools, ingestion, planning, approvals, watcher, and MCP server |
| `backend/warden/ingest/` | Repository discovery, dependency parsing, threat-intel enrichment, and graph loading |
| `backend/org/` | Curated ownership, policy, data-sensitivity, and incident YAML for the sample organization |
| `backend/tests/` | Backend tests |
| `frontend/src/` | React + TypeScript user interface |
| `docker-compose.yml` | Local FalkorDB and PostgreSQL services (and optional API container profile) |
| `docker-compose.prod.yml` | Production API, FalkorDB, optional local PostgreSQL, and Caddy services |
| `.env.example` | Documented environment-variable template; copy to `.env` and edit locally |
| `DEPLOY.md` | Deployment notes for the API and Vercel frontend |
| `docs/DEMO_SCRIPT.md` | Suggested product demo sequence |

### Backend code map

| Module | Responsibility |
|---|---|
| `backend/warden/api/app.py` | FastAPI startup/shutdown, project-scoped API routes, health, graph views, agent/plan/approval/sync endpoints, evaluation, and public landing-page endpoints |
| `backend/warden/api/accounts.py` | Signup/login/logout, account sessions, organizations, invites, project CRUD, and project-scope middleware |
| `backend/warden/auth.py` | Password hashing and signed session handling |
| `backend/warden/config.py` | Loads root `.env`, service settings, per-request project graph/repository context, and graph naming |
| `backend/warden/db/` | SQLAlchemy engine/session setup and application database models |
| `backend/warden/graph/client.py` | FalkorDB connections, Cypher helpers, graph copies, and graph lifecycle operations |
| `backend/warden/graph/schema.py` | Graph indexes, constraints, and schema setup |
| `backend/warden/graph/overview.py`, `evidence.py` | Health/overview aggregates and evidence path formatting/provenance |
| `backend/warden/ingest/bootstrap.py` | First-start sample graph initialization and golden snapshot creation |
| `backend/warden/ingest/pipeline.py` | Coordinates repository checkout, service discovery, dependency parsing, vulnerability feeds, history, graph loading, and snapshots |
| `backend/warden/ingest/discover.py` | Detects service folders/topology from Kubernetes, Compose, or code-only repository layouts |
| `backend/warden/ingest/deps.py` | Parses supported dependency manifests and lockfiles |
| `backend/warden/ingest/osv.py`, `intel.py` | OSV package advisory lookup and threat-intelligence enrichment |
| `backend/warden/ingest/history.py` | Reads Git commits, changed files, authors, and pull request history where available |
| `backend/warden/ingest/orgdata.py` | Loads curated owners, policies, incidents, and sensitivity data from `backend/org/` |
| `backend/warden/ingest/load.py` | Writes the normalized ingest data and provenance into FalkorDB |
| `backend/warden/tools/base.py` | Tool definition, parameter metadata, registry, execution, and common result shape |
| `backend/warden/tools/security.py`, `risk.py` | Reachable findings, exploit intelligence, fix paths, and risk scoring |
| `backend/warden/tools/topology.py` | Blast radius, paths, rankings, and choke-point analysis |
| `backend/warden/tools/people.py`, `changes.py`, `incidents.py`, `policy.py`, `memory.py` | Owner/reviewer, PR, incident, policy, prior decision, contradiction, and timeline tools |
| `backend/warden/tools/repo.py`, `search.py` | Read-only graph/repository inspection and entity search |
| `backend/warden/agent.py`, `verification.py` | LLM tool-selection loop, streamed events, answer generation, and deterministic claim checks |
| `backend/warden/mcp_client.py`, `mcp_server.py` | MCP connection used by the agent and standalone stdio/HTTP MCP server |
| `backend/warden/planner.py`, `optimizer.py`, `proposals.py` | Candidate upgrades, plan comparison, optimization, graph-copy rehearsal, and pending approvals |
| `backend/warden/actions/` | GitHub target validation, patch generation, preflight checks, approval execution, and PR creation |
| `backend/warden/sync.py`, `watch.py`, `build.py`, `workspaces.py` | Project repository state, graph rebuilds, manual sync, polling watcher, and workspace scoping |
| `backend/warden/regression.py`, `counterfactual.py`, `surface.py`, `baseline.py` | Attack-path regression, what-if simulation, attack-surface data, and scanner baseline comparison |
| `backend/warden/conversations.py`, `replay.py`, `memory.py`, `timeline.py`, `contradictions.py` | Saved chats/tool runs, turn replay, decision context, graph timeline, and source disagreement checks |
| `backend/warden/eval/` | Designed evaluation scenarios and metric calculation |

### Frontend code map

| Path | Responsibility |
|---|---|
| `frontend/src/App.tsx` | Browser routes and signed-in project route tree |
| `frontend/src/main.tsx` | React entry point and global styles |
| `frontend/src/components/AppShell.tsx` | Authenticated app shell, current project selection, build status, and responsive sidebar layout |
| `frontend/src/components/Sidebar.tsx` | Project switcher, screen navigation, recent chats, and profile menu |
| `frontend/src/screens/` | Route-level screens: Home, Ask, PR impact, Approvals, Tools, Sync, Evaluation, Settings, auth, and public Landing |
| `frontend/src/components/` | Reusable graphs, evidence paths, plan/gate/review panels, forms, tables, chat, and status UI |
| `frontend/src/components/AttackSurfaceMap.tsx` | Cytoscape service/dependency/data route map |
| `frontend/src/components/PathGraph.tsx`, `PathProof.tsx` | Evidence-path visualization and graph-edge validation UI |
| `frontend/src/components/PlanView.tsx`, `GateView.tsx`, `Regression.tsx`, `ComparePlans.tsx` | Proposed upgrades, gate checks, before/after paths, and plan comparison |
| `frontend/src/components/RepositoryCard.tsx`, `BuildStatus.tsx` | Repository/branch selection and asynchronous graph build status |
| `frontend/src/lib/api.ts` | Frontend API types, cookie-aware fetch wrapper, endpoints, and API base URL |
| `frontend/src/lib/auth.tsx` | Auth context and selected-project helpers |
| `frontend/src/lib/useApi.ts` | Loading/error/reload state for API-backed screens |
| `frontend/src/lib/ask.ts`, `useExamples.ts`, `useContradictions.ts` | Ask input helpers and reusable graph-derived suggestions/state |
| `frontend/src/styles/` | Design tokens, global app styles, and component styling conventions |

The main dependency direction is **screen → reusable component → `frontend/src/lib/api.ts` → FastAPI route → graph/service module**. Keep API response types in `api.ts`; avoid making screens construct raw URLs directly.

### Runtime flow

```mermaid
flowchart LR
  Browser[React UI] -->|HTTPS + session cookie| API[FastAPI]
  API -->|project-scoped request| Graph[(FalkorDB)]
  API --> SQL[(PostgreSQL)]
  API --> Agent[Agent loop]
  Agent --> LLM[OpenAI-compatible LLM]
  Agent --> MCP[MCP tool registry]
  MCP --> Graph
  API -->|approved action only| GH[Configured GitHub target]
  API --> Feeds[OSV / KEV / EPSS]
```

For an Ask request, the API resolves the signed-in user's project, the agent selects graph tools through MCP, and each tool returns rows and evidence paths. The model drafts a short answer from those results; the verifier checks key names and claims against the same turn's tool results before the UI displays the answer and trace. For a fix, the planner rehearses candidate changes on a temporary graph copy and creates a pending approval. The approval executor performs plan/PR actions; the Watcher's separately labeled demo simulation controls can commit a topology change directly.

### Repository-to-graph build flow

1. Read the selected repository and ref into a project-specific checkout under `backend/data/raw/repos/`.
2. Discover services and topology from Kubernetes, Compose, or code folders.
3. Parse each service's manifests and dependency files into package nodes and direct/transitive dependency edges.
4. Query/cache OSV advisories and enrich them with CISA KEV and FIRST EPSS; optional NVD backfill is controlled by `WARDEN_NVD`.
5. Read Git history where it is available, then add curated owner/data/policy/incident context for the shared sample project.
6. Load the graph into FalkorDB, record source provenance, and save a golden snapshot for reset. New project builds run in the background; the project status tracks progress and failure detail.

Raw checkouts and cached feed responses are runtime data, not part of the committed source tree.

### API route map

All application routes live under `/api`. The interactive route catalog is at `http://localhost:8000/docs` while the API is running.

| Route area | What it serves |
|---|---|
| `/api/auth/*`, `/api/orgs/*`, `/api/invites/*`, `/api/projects/*` | Authentication, organizations, invites, project selection and project builds |
| `/api/health`, `/api/overview`, `/api/surface`, `/api/services`, `/api/baseline` | Current graph health and visual summaries |
| `/api/tools`, `/api/tools/{name}`, `/api/tool-runs/*`, `/api/mcp` | Tool catalog, direct tool execution, saved runs, MCP status |
| `/api/ask`, `/api/conversations/*`, `/api/replay/*` | Agent questions, saved chats, and replaying a tool turn |
| `/api/plans*`, `/api/impact` | Remediation-plan generation/comparison and pull-request impact analysis |
| `/api/approvals/*` | Pending action review, approval/rejection, preflight, merge status, and verification |
| `/api/github/*` | GitHub connection/repository/branch checks and configured project target |
| `/api/sync*`, `/api/watch*`, `/api/whatif`, `/api/contradictions*` | Re-ingestion, watcher control, simulation, and source disagreement checks |
| `/api/eval*`, `/api/metrics`, `/api/evidence/validate` | Designed evaluation runs and evidence verification |
| `/api/public/*` | Read-only sample graph data used by the public landing page |

Project-scoped routes use the signed-in user's current project context. The API scopes graph queries and GitHub settings for the request; client-supplied graph names are not a substitute for project access checks.

### Graph tool catalog

The Tools page and MCP server use one shared registry (`backend/warden/tools/`). Current tools are read-only graph/repository queries; write actions are handled by separate approval workflows.

| Category | Tools |
|---|---|
| Security | `reachable_findings`, `exploit_intel`, `fix_path` |
| Topology | `blast_radius`, `path_between`, `rank`, `choke_points` |
| People | `who_owns`, `who_knows` |
| Changes and incidents | `pr_touched_services`, `past_incidents` |
| Policies | `policies_for` |
| Memory and evidence | `decisions_about`, `contradictions_for`, `exposure_timeline` |
| Repository and graph | `graph_schema`, `graph_query`, `repo_info`, `person_profile` |
| Search | `find_entity` |

Every tool returns a common envelope with the normalized arguments, summary, result rows, evidence nodes/edges when available, source references, the Cypher query/parameters, elapsed time, and any user-facing tool error. New tools should register through the `@tool` decorator and use the shared `Trace` helper so queries remain visible and auditable.

## Requirements

- Docker Desktop on Windows/macOS, or Docker Engine and Compose on Linux
- Python 3.11 or newer
- Node.js 20 or newer and npm
- Git
- Internet access for first-time repository cloning and vulnerability-feed requests

Optional integrations:

- An API key for an OpenAI-compatible LLM service to use Ask and the agent
- A GitHub fine-grained token for private repository access, repository discovery, and approved GitHub actions
- A GitHub fork or repository where Warden is allowed to open branches and pull requests

## Quick start

### Windows

Open PowerShell in the project directory, make sure Docker Desktop is running, then run:

```powershell
Copy-Item .env.example .env
# Edit .env and add the optional credentials described below.
.\start.ps1
```

The launcher starts FalkorDB and PostgreSQL, prepares the Python environment, installs dependencies if needed, initializes the sample graph if it is empty, and starts the API and Vite development server. It opens the UI in a browser.

### macOS / Linux / Git Bash

```bash
cp .env.example .env
# Edit .env and add the optional credentials described below.
./start.sh
```

On first launch, ingestion can take several minutes. Later launches reuse the existing graph and cached feed data.

### Local addresses

| Service | Address | Notes |
|---|---|---|
| Warden UI | http://localhost:5173 | Vite development server |
| Warden API | http://localhost:8000 | FastAPI |
| API documentation | http://localhost:8000/docs | OpenAPI / Swagger UI |
| FalkorDB Browser | http://localhost:3000 | Graph inspection UI |
| FalkorDB graph port | `localhost:6380` | Host port mapped to container port 6379 |
| PostgreSQL | `localhost:5433` | Local application data |

Sign up at `/signup`. New users get access to a shared sample project. Create another project to build a graph from a different GitHub repository.

## Environment setup

The backend reads `.env` from the repository root. Never commit `.env` or put server secrets in frontend variables. `.env.example` is safe to copy and contains placeholders, not working credentials.

### Core database and graph settings

| Variable | Default / example | Required | Purpose |
|---|---|---:|---|
| `FALKORDB_HOST` | `localhost` | Yes | FalkorDB hostname. Local Docker uses `localhost`; the production Compose service uses `falkordb`. |
| `FALKORDB_PORT` | `6380` | Yes | FalkorDB port as seen by the backend. Local host mapping is 6380; inside Compose it is 6379. |
| `FALKORDB_USERNAME` | empty | No | Username for an authenticated FalkorDB instance. |
| `FALKORDB_PASSWORD` | empty | No | Password for an authenticated FalkorDB instance. |
| `FALKORDB_SSL` | `false` | No | Set `true` when connecting to FalkorDB Cloud or another TLS endpoint. |
| `FALKORDB_BROWSER_URL` | `http://localhost:3000` | No | Link shown by the API to open FalkorDB Browser. |
| `TENANT` | `demo` | No | Name used for the shared graph (`org_<tenant>`). |
| `DATABASE_URL` | `postgresql+psycopg://warden:warden@localhost:5433/warden` | Yes | SQLAlchemy URL for users, teams, projects, sessions, and conversations. Use PostgreSQL locally and in production. |

Local Compose uses a development-only PostgreSQL password configured in `docker-compose.yml`. `POSTGRES_PASSWORD` is used by `docker-compose.prod.yml` only when the `localdb` profile is enabled; use a strong unique value there. If production uses Neon or another hosted PostgreSQL service, set `DATABASE_URL` instead.

### Repository and ingestion settings

| Variable | Default / example | Required | Purpose |
|---|---|---:|---|
| `DEMO_REPO_URL` | `https://github.com/GoogleCloudPlatform/microservices-demo.git` | No | Source repository for the shared sample project. |
| `DEMO_REF` | `v0.8.0` | No | Branch or tag used by the shared sample graph and reset flow. |
| `HISTORY_SINCE` | `2022-06-15` | No | Start date used to limit repository history ingestion. |
| `WARDEN_NVD` | `0` | No | Set `1` or `true` to enable optional NVD CVSS backfill during bootstrap. First ingest takes longer. |

The project builder can discover service topology from Kubernetes manifests, Docker Compose files, or code/dependency folders. Supported package inputs include npm lockfiles, Python requirements/Poetry/uv/Pipenv locks, `go.mod`, NuGet `.csproj`, Maven POM/Gradle, Cargo, Ruby Bundler, and Composer lockfiles. Coverage depends on repository structure and the data files present.

### LLM settings

| Variable | Default / example | Required for |
|---|---|---|
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | OpenAI-compatible API base URL |
| `LLM_API_KEY` | empty | Ask and model-powered agent answers |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Model identifier accepted by the chosen endpoint |

If these values are unset, the app still starts and graph-backed pages/tools remain usable, but model-backed Ask requests cannot complete.

### GitHub settings

| Variable | Default / example | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | empty | Fine-grained token used for repository access and approved writes. Keep it on the backend only. |
| `GITHUB_OWNER` | empty | Default owner for the fork/repository Warden acts on. |
| `GITHUB_REPO` | `microservices-demo` | Default repository name for actions. |
| `GITHUB_BASE` | `demo-base` | Base branch for pull requests; empty uses the repository default branch. |

Without GitHub credentials, the shared sample graph can still be explored, but Warden cannot access private repositories or perform GitHub actions. Configure the token with the minimum permissions required for the target repository. Use a fork or dedicated test repository rather than an upstream project. Per-project GitHub targets can also be selected in the UI.

### Session, browser, and deployment settings

| Variable | Default / example | Purpose |
|---|---|---|
| `SESSION_SECRET` | development fallback in code | Secret used to sign sessions. Set a long random value before exposing the API publicly. |
| `SESSION_DAYS` | `14` | Session lifetime in days. |
| `COOKIE_SAMESITE` | `lax` | Cookie SameSite setting. Cross-site Vercel/API hosting generally needs `none`. |
| `COOKIE_SECURE` | `false` | Set `true` when the API is served over HTTPS. Required with `SameSite=None` in modern browsers. |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:5175` | Comma-separated exact frontend origins allowed to call the API with cookies. Do not use `*` with credentialed requests. |
| `WARDEN_URL` | `http://localhost:5173` | Public UI URL used in links from GitHub comments and pull requests. |
| `WATCH_INTERVAL` | `30` | Watcher polling interval in seconds. |
| `API_DOMAIN` | `api.example.com` | Production API hostname used by Caddy for HTTPS. |
| `VITE_API_URL` | empty in local dev | Frontend build-time API base URL. Set to the HTTPS API origin for Vercel, e.g. `https://api.example.com`. |
| `WARDEN_API` | `http://127.0.0.1:8000` | Optional Vite development proxy target for running the API on another local port. |

## Manual development setup

Use this if you prefer separate terminals over the launcher.

Start the local infrastructure from the repository root:

```bash
docker compose up -d falkordb postgres
```

Install and initialize the backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m warden.ingest.bootstrap
python -m uvicorn warden.api.app:app --host 127.0.0.1 --port 8000
```

On macOS/Linux, activate with `source .venv/bin/activate` and use the same Python commands.

In a second terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. Override this with `WARDEN_API` when the backend uses another local port.

## Resetting and stopping local data

- `python -m warden.prepare` from `backend/` restores the shared sample/demo graph snapshot, disables the watcher, clears its agent state, and runs the evaluation. This command is intended for the sample project.
- If GitHub is configured, the CLI reset also attempts to undo the demo's `paymentservice` exposure change on the configured target repository. It can make a GitHub commit; check the target before running it.
- The **Sync → Reset to the pinned release** action restores the open project's saved golden snapshot and clears that project's agent state. Read the confirmation before proceeding.
- Windows: `.\start.ps1 -Reset` starts services and runs the sample reset flow. Linux/macOS: `./start.sh --reset`.
- Stop containers but keep their data volumes with `docker compose down`.
- **Destructive:** `docker compose down -v` deletes local database and graph volumes. Use it only when you intend to erase local data.

## Main screens

| Screen | Purpose |
|---|---|
| Home | Attack-surface overview, high-priority exposure, plan builder, and project activity |
| Ask | Ask graph-backed questions and inspect the agent's tool trace and evidence |
| PR impact | Analyze a pull request's affected services, graph blast radius, owners, and related history |
| Approvals | Review plans/analyses and approve or reject proposed GitHub actions |
| Tools | Run graph tools directly and inspect their queries/results |
| Sync | Re-ingest the configured source and inspect graph changes |
| Evaluation | Run designed scenarios through the real tools and show their expected outcomes |
| Settings | Manage account, team/project, repository, and GitHub settings |

## How to use Warden

### 1. Sign in and choose a project

Open the UI, create an account at `/signup`, or sign in at `/login`. The project switcher in the sidebar changes which graph the app queries. Projects have separate FalkorDB graphs; a project build can take time, and the build screen shows its current step or error. Builds run in the backend, so you can return to the project later while the API stays running.

### 2. Add a repository project

Repository import requires a backend GitHub token that can read the repository. To create a project:

1. Open **Settings → Projects**.
2. Choose **New project**, select a repository and branch, select the team, and create it.
3. Watch the build status. Warden clones the selected ref, discovers services and dependencies, fetches vulnerability metadata, reads available history, and loads a graph for that project.
4. Open the project when its status is **ready**. If it fails, read the displayed build detail, fix repository/token/branch access, then rebuild from Settings.

Only team owners/admins can create projects or change the repository. The shared sample project is kept separate because everyone on its team uses the same graph. For your own target repository, create a dedicated project.

### 3. Find and understand a risk

On **Home**, review the attack-surface map and exploit-signal summary. Click a service to inspect its relationship to callers, dependencies, and sensitive data. Use the map's secure/what-if interaction to see which modeled routes pass through a selected service. For an individual finding, go to **Ask** and try prompts such as:

- `What should we fix first?`
- `Show the path for CVE-2023-44487.`
- `Is paymentservice reachable from the internet? Show the evidence.`
- `What does this service read, and who owns it?`

Read the answer together with its tool trace and evidence path. Open the query details when you want to inspect the Cypher and parameters. Treat “reachable” as reachability under Warden's repository-derived topology model.

On the attack-surface map, **Secure [service]** is a visual counterfactual: it highlights which current internet-to-sensitive-data routes would be cut if that service were secured. It does not change the repository or graph. Click a service node to select it; click the secure button again to undo the overlay.

### 4. Compare and propose dependency fixes

From **Home**, choose **Compare fix plans**. Set a maximum number of upgrades, optionally list frozen services, and optionally disallow major-version bumps. Choose **Compare** to rehearse the candidate strategies on graph copies. Review risk removed, changes, major upgrades, new advisories, residual KEV, and each plan's gate result. A blocked plan cannot be filed. Choose **File for approval** on a passing plan to create a pending approval; this step does not yet change GitHub.

You can also use **Build a fix plan** for the default plan. The detail page explains the selected package upgrades, before/after graph state, regression checks, and warnings. The Home page's deliberately unsafe plan is a demonstration of the gate; it is not sent to GitHub.

### 5. Review and approve actions

Open **Approvals** and select a pending item. Review the plan or PR impact, evidence, gate, proposed files, and target repository. You can reject it with a reason or approve it. With GitHub configured, approval performs the allowed action on the selected fork/repository and records the result. Without GitHub configured, Warden records the decision locally and tells you that no external action was sent. After a fix PR has opened, **Run local pre-flight** checks supported Go/npm steps on temporary copies; unavailable build tools are reported as skipped.

Warden does not merge PRs automatically. Review the generated patch and the PR's CI/test results before merging; the approval timeline may offer a manual merge action for an opened PR. Local pre-flight is not a replacement for the target project's full CI. After a merge, use Sync or the watcher to check whether the expected exposure is gone. The Watcher demo's **Make [service] public** and **Undo** controls are an exception to the approval flow: they directly commit the demo topology change to the connected branch so the watcher can detect it. Use only a disposable fork for this demonstration.

### 6. Analyze a pull request

Open **PR impact**, enter a pull request number from the connected repository, and run the analysis. Review the risk summary, affected services, blast radius at different depths, related incidents, reviewers, policies, and suggested comment. If you want Warden to post the proposed feedback, file it for approval and review it from **Approvals** first.

### 7. Run a graph tool directly

Open **Tools**, choose a category, and select a tool. Start from the example values, adjust required fields, then run it. Inspect the summary, rows, evidence path, query, and duration. These direct tools are read-only. The **MCP** panel shows the MCP server connection/tool status. `graph_query` only runs read-only Cypher.

### 8. Sync, watch, and evaluate

- **Sync:** run a repository re-read after changing the connected branch or after an external merge. Review the reported additions/removals and graph version. Reset restores the open project's saved golden snapshot and clears its agent state; do not use reset if you need to preserve current graph state.
- **Watcher:** enable polling when the GitHub target is configured. It checks for branch changes at `WATCH_INTERVAL`, re-reads the repository, and may create pending proposals when it detects a new exposure. Watcher proposals still go through the approval gate.
- **Evaluation:** open the page and run the designed scenarios. It reports whether the graph tools, plan gate, abstention behavior, and prioritization match the expected answers for those constructed cases. These scenarios are a regression suite, not an independent benchmark of arbitrary repositories.
- **Settings:** manage your profile, teams/invites, projects, and the repository/branch associated with each project.

### What GitHub configuration enables

Without a GitHub token, the local sample graph and many read-only graph views can still be used. A token is needed to enumerate private repositories, import repositories that require authentication, read GitHub history/PR metadata, or perform an approved GitHub write. To enable actions, configure a fine-grained token, connect a target repository in **Settings → Projects**, and confirm the target shown in the Approvals page. Use a test fork when trying write actions.

For a fine-grained GitHub token, grant access only to the target repository. Warden's common workflows need repository metadata read access, repository contents read/write for branch/commit changes, pull requests read/write, and issues read/write for issue/label actions. GitHub may require its repository metadata permission in addition to those scopes. If the token is read-only, graph import may still work, but repository listing and write features can be unavailable.

### Connect an external MCP client

The MCP server exposes the graph tool registry as read-only tools. Start with the same `.env`, Python environment, and graph service used by the API. From `backend/`, run:

```bash
python -m warden.mcp_server
```

This uses stdio and is suitable for MCP clients that launch a local command. Example configuration shape (replace the command and working directory with absolute paths):

```json
{
  "mcpServers": {
    "warden": {
      "command": "<absolute-path-to>/backend/.venv/Scripts/python.exe",
      "args": ["-m", "warden.mcp_server"],
      "cwd": "<absolute-path-to>/backend"
    }
  }
}
```

On macOS/Linux, use `backend/.venv/bin/python`. For a local streamable-HTTP server, run `python -m warden.mcp_server --http 8765`; the MCP endpoint is `http://localhost:8765/mcp`. A standalone server uses the default graph selected by `TENANT`; it does not inherit a signed-in user's project selection. It has access to that graph and the configured repository context, so do not expose it to an untrusted network without adding authentication and network controls.

## How the graph and risk model work

The graph connects services, ingress, calls, packages, package requirements, advisories, exploit catalogs, data assets, teams, people, pull requests, decisions, and provenance. The graph is the source of truth for answers; PostgreSQL stores application records such as accounts, sessions, and conversations.

The exposure model follows service calls from internet-facing services up to four hops, then follows service dependencies to advisories. Risk incorporates severity, exploit signal, hop distance, and modeled data sensitivity. Warden displays whether evidence is sourced from a repository/feed, inferred from configuration, or curated for the sample project.

The agent selects tools over MCP and writes answers from tool output. A verifier checks named services and vulnerabilities against the results returned during that turn. Planning and gate checks are deterministic and run against graph copies; they do not rely on the LLM's safety judgment.

## Data and privacy notes

- The sample repository is Google's Online Boutique (`GoogleCloudPlatform/microservices-demo`) and its data is read from its configured branch/tag.
- Vulnerability data comes from OSV, CISA KEV, and FIRST EPSS; NVD lookups are optional. Feed data is cached under `backend/data/raw/cache/` and is ignored by Git.
- Teams, service ownership, sensitive-data mappings, policies, and sample incidents in `backend/org/` are curated demo context. They are not claims about a real company's internal organization.
- Repository clones and feed caches are stored under `backend/data/raw/`; they are local runtime data and are ignored by Git.
- LLM prompts include the user's question and the tool data needed to answer it. Review your model provider's data handling terms before using private repository data.
- Treat imported repositories and any actions as sensitive. Use least-privilege tokens and review every proposed patch before merging.

## Testing and build

From the repository root:

```powershell
.\start.ps1 -Test
```

Or run the backend suite directly (the database services must be available):

```bash
cd backend
python -m pytest -q tests
```

Build/type-check the frontend:

```bash
cd frontend
npm run build
```

`npm run build` runs TypeScript project checks and creates the Vite production bundle in `frontend/dist/`.

## Changing the code

### Add or change a graph tool

1. Put the implementation in the appropriate module under `backend/warden/tools/` (or create a focused module).
2. Define the tool with the `@tool(...)` decorator and typed `Param` declarations. Import a new module from `backend/warden/tools/__init__.py` so it registers at startup.
3. Use `Trace.ro(cypher, params)` for every graph query and return a `Result`. This records the exact Cypher and parameters for the UI, agent, and MCP response.
4. Keep graph tools read-only. Use the `ro` query path; actions that write to GitHub belong behind a pending approval workflow.
5. Add focused tests under `backend/tests/` and confirm the tool appears on the Tools page and the MCP catalog.

### Add or change an API-backed screen

1. Define or update request/response types and the endpoint wrapper in `frontend/src/lib/api.ts`.
2. Implement the FastAPI route in `backend/warden/api/app.py` or `backend/warden/api/accounts.py`. Keep project-owned graph operations inside the project-scoped request context.
3. Add the screen/component under `frontend/src/screens/` or `frontend/src/components/`; use `useApi` for loaded state and the centralized API client for calls.
4. Add the route to `frontend/src/App.tsx`. Add sidebar navigation in `frontend/src/components/Sidebar.tsx` only when it should be a top-level page.
5. Build with `npm run build` and test the workflow against a disposable project/repository before deploying.

### Add support for another dependency format or repository layout

1. Update service discovery in `backend/warden/ingest/discover.py` if the service/topology shape needs new detection.
2. Add parsing and normalization in `backend/warden/ingest/deps.py`; preserve package identity, version, direct/transitive relationships, source file, and the direct dependency chain where available.
3. Ensure `backend/warden/ingest/pipeline.py` and `load.py` receive the same normalized structures used by existing parsers.
4. Add small fixture-based tests. Do not rely on downloading a large real repository in a unit test.
5. Update the supported-format list in this README and explain any uncertainty (for example, incomplete lockfiles).

### Change the graph schema or application database

- FalkorDB schema/index setup lives in `backend/warden/graph/schema.py`; graph names and query helpers live in `graph/client.py`.
- The SQLAlchemy tables are in `backend/warden/db/models.py`. `db.init_db()` creates missing tables and applies a few explicit additive column changes; it is not a general migration framework. For a production schema change that alters or removes existing data, add a deliberate migration/backup plan rather than relying on `create_all()`.
- Keep the user/account database and graph facts separate: user/team/chat records belong in PostgreSQL, repository/security relationships belong in FalkorDB.

### Curated sample organization data

The sample data files are `backend/org/teams.yaml`, `services.yaml`, `sensitivity.yaml`, `policies.yaml`, and `postmortems.yaml`. `backend/warden/ingest/orgdata.py` loads them. Label curated assumptions clearly; never present the sample's teams, incidents, or data sensitivity as discovered facts about a real repository.

### Before opening a pull request

```bash
cd backend
python -m pytest -q tests
cd ../frontend
npm run build
```

Also review the diff for secrets, generated caches, accidental dataset changes, and claims in the README that no longer match the implementation. Use a GitHub fork or disposable repo for action tests.

## Production deployment

See [`DEPLOY.md`](DEPLOY.md) for the full procedure. The supported layout is:

1. Deploy the API, FalkorDB, and Caddy on a server with a DNS name and HTTPS. Configure `.env` on the server; use a strong `SESSION_SECRET`, secure cookie settings, exact `CORS_ORIGINS`, and either hosted PostgreSQL (`DATABASE_URL`) or the production Compose `localdb` profile with a strong `POSTGRES_PASSWORD`.
2. Deploy the `frontend/` directory as a Vercel project. The repository's `frontend/vercel.json` sets the Vite build and output directory. Set `VITE_API_URL` to the API's HTTPS origin in Vercel's project environment and redeploy after changing it.
3. Set backend `WARDEN_URL` to the Vercel site URL and `CORS_ORIGINS` to the exact Vercel origin. For preview deployments, add the specific preview origin if it should be allowed to sign in.
4. Set required secrets in the hosting provider, not in committed files. Redeploy/restart the backend after backend environment changes; rebuild the frontend after `VITE_API_URL` changes.

The Vercel frontend is static; it does not host the graph, API, database, or secrets. API and frontend origins must agree on CORS and cookie settings for sign-in to work.

## Troubleshooting

| Symptom | Check |
|---|---|
| Docker prerequisite fails | Start Docker Desktop/Engine, then check `docker info`. |
| UI says it cannot reach the API | Open `http://localhost:8000/api/health`; check the API terminal/log and Vite proxy target. |
| Health says graph offline or graph is empty | Check FalkorDB is running on port 6380 and run `python -m warden.ingest.bootstrap` from `backend/`. |
| First ingest is slow or fails | Check internet access and repository URL/ref. Public advisory feeds and the source repository are used on first ingest. |
| Ask cannot answer | Configure `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`; check provider quota and model name. |
| GitHub actions are unavailable | Configure `GITHUB_TOKEN`, ensure it has access to the chosen target, and confirm the repository/base branch in project settings. |
| Vercel sign-in or API requests fail | Confirm `VITE_API_URL`, backend `CORS_ORIGINS`, HTTPS, `COOKIE_SAMESITE=none`, and `COOKIE_SECURE=true`. Rebuild the frontend after changing Vercel variables. |
| Project build is queued/failed | Open project settings for the build status/detail, then check backend logs and repository access/branch. Rebuild after fixing access or source issues. |
| Counts differ from a README/demo | Counts vary with the selected repository/ref and refreshed vulnerability feeds. Use the UI's query/evidence details for current values. |

## License and credits

Warden is built with FastAPI, React, Vite, TypeScript, Cytoscape.js, FalkorDB, PostgreSQL, and the Model Context Protocol. It uses public data from [OSV](https://osv.dev), [CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog), and [FIRST EPSS](https://www.first.org/epss). The sample service repository is [Google Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo).

Add the project's chosen `LICENSE` file before redistributing this repository; the sample repository's Apache-2.0 license does not automatically license Warden.
