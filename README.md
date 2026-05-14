# koi-net-github-processor-node

A [KOI-net](https://github.com/DynamicalSystemsGroup/koi-net) processor node that subscribes to GitHub event manifests from sensor nodes, indexes the event metadata in a local SQLite database, and exposes a REST API for querying tracked repositories and their events. The node stores **metadata only** — it never clones repositories or fetches file contents, which keeps it lightweight and avoids Git-level dependencies.

## What this node is and isn't

| Is | Isn't |
|---|---|
| A KOI-net `FullNode` that consumes `GitHubEvent` bundles broadcast by a sensor node | A GitHub mirror or backup — no Git operations are performed |
| A queryable index of repositories and events with a small REST API | A full webhook receiver — events arrive via the KOI-net protocol, not directly from GitHub |
| A SQLite-backed local index with two tables and two indexes | Distributed storage — each processor instance maintains its own local index |

## Architecture

Five components, defined in `github_processor_node/`:

```
┌───────────────────┐     ┌────────────────┐     ┌──────────────────┐
│  Sensor node(s)   │────►│  KOI-net node  │────►│  Other KOI-net   │
│  (GitHubEvent     │     │   interface    │     │     nodes        │
│   manifests)      │     │  (server.py)   │     │                  │
└───────────────────┘     └────────┬───────┘     └──────────────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │   Processor handlers   │
                      │     (handlers.py)      │
                      │   • Manifest handler   │
                      │   • Bundle handler     │
                      │   • Network handler    │
                      └────────────┬───────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │  Repository service    │
                      │   (repository.py)      │
                      └────────────┬───────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │   SQLite index DB      │
                      │    (index_db.py)       │
                      │   • repositories       │
                      │   • events             │
                      └────────────┬───────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │  REST API / CLI tool   │
                      │  (server.py, cli.py)   │
                      └────────────────────────┘
```

## Data model (SQLite)

Two tables created on first run (see `index_db.py`):

```sql
CREATE TABLE repositories (
    repo_rid       TEXT PRIMARY KEY,        -- orn:github.repo:<owner>/<name>
    repo_url       TEXT NOT NULL,
    first_indexed  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE events (
    event_rid    TEXT PRIMARY KEY,           -- orn:github.event:<owner>/<repo>:<id>
    repo_rid     TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    timestamp    TIMESTAMP NOT NULL,
    commit_sha   TEXT,
    summary      TEXT,
    bundle_rid   TEXT,
    FOREIGN KEY (repo_rid) REFERENCES repositories(repo_rid)
);

CREATE INDEX idx_events_repo   ON events (repo_rid);
CREATE INDEX idx_events_commit ON events (commit_sha);
```

## REST API

All endpoints exist as real FastAPI routes in `server.py`. KOI-net protocol endpoints (under the configurable `koi_net.server.path`, default `/koi-net`):

| Method + path | Purpose |
|---|---|
| `POST /events/broadcast` | Receive event broadcasts from other nodes |
| `POST /events/poll` | Allow partial nodes to poll for events |
| `POST /rids/fetch` | Return RIDs of a given type |
| `POST /manifests/fetch` | Return manifests for given RIDs |
| `POST /bundles/fetch` | Return full bundles for given RIDs |

Application-specific endpoints (under `/api/processor/github`):

| Method + path | Purpose |
|---|---|
| `GET /status` | Node status (`StatusResponse` schema) |
| `GET /repositories` | List tracked repositories (`List[RepositoryInfo]`) |
| `GET /repositories/{repo_rid}/events` | List events for a repo (`List[EventInfo]`); supports `limit` and `offset` query params |

## CLI

A standalone CLI in `cli.py` for inspecting the local index without going through the API:

| Command | Underlying function | Purpose |
|---|---|---|
| `python cli.py list-repos` | `list_repos_cmd` | List all tracked repositories |
| `python cli.py show-events <repo>` | `show_events_cmd` | Show events for a repository (`<repo>` is `owner/name` or full RID) |
| `python cli.py event-details <event_rid>` | `show_event_details_cmd` | Show full event detail for a single RID |
| `python cli.py add-repo <owner/name>` | `add_repo_cmd` | Register a repository for tracking |
| `python cli.py summarize-events` | `summarize_events_cmd` | Aggregate event-count summary across the DB |

The CLI opens a separate read-only connection to the same SQLite DB the server writes to.

## Install and run

The repo does not have a `pyproject.toml` or `setup.py` — it is not (yet) published to PyPI. Install from source:

```bash
git clone https://github.com/DynamicalSystemsGroup/koi-net-github-processor-node.git
cd koi-net-github-processor-node
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Dependencies (`requirements.txt`):

```
uvicorn        # ASGI server
fastapi        # REST framework
pydantic       # config + response schemas
rich           # CLI output formatting
ruamel.yaml    # config.yaml parsing
python-dotenv  # .env loading
koi-net>=1.0.0b17
rid-lib>=3.2.3
```

Create a `config.yaml` (see Configuration below), set `GITHUB_TOKEN` in the environment, and run:

```bash
python -m github_processor_node
```

The node starts a Uvicorn server (see `__main__.py`) on the host/port from `config.yaml`.

## Configuration

Minimal `config.yaml`:

```yaml
server:
  host: 127.0.0.1
  port: 8004
  path: /koi-net
koi_net:
  node_name: processor_github
  node_rid: orn:koi-net.node:processor_github+0bf78f28-9f56-4d31-8377-a33f49a0828e
  node_profile:
    base_url: http://127.0.0.1:8004/koi-net
    node_type: FULL
    provides:
      event: []
      state: []
  cache_directory_path: .koi/processor-github/cache
  event_queues_path: .koi/processor-github/queues.json
  first_contact: http://127.0.0.1:8000/koi-net
index_db_path: .koi/processor-github/index.db
env:
  github_token: GITHUB_TOKEN
```

Top-level keys (`config.py`):

| Key | Default | Description |
|---|---|---|
| `server.host` | `127.0.0.1` | Bind address |
| `server.port` | `8004` | Listen port |
| `server.path` | `/koi-net` | Base path for KOI-net protocol endpoints |
| `koi_net.node_name` | `processor_github` | Logical node identifier |
| `koi_net.node_rid` | generated | RID for this node instance |
| `koi_net.node_profile.node_type` | `FULL` | Full vs partial node |
| `koi_net.cache_directory_path` | `.koi/processor-github/cache` | Bundle cache root |
| `koi_net.event_queues_path` | `.koi/processor-github/queues.json` | Persisted event-queue state |
| `koi_net.first_contact` | (none) | URL of a node to register with on startup |
| `index_db_path` | `.koi/processor-github/index.db` | SQLite database path |
| `env.github_token` | `GITHUB_TOKEN` | Name of env var holding the GitHub token |

## Source layout

```
.
├── github_processor_node/
│   ├── __main__.py           # entrypoint: starts uvicorn
│   ├── core.py               # FullNode instance
│   ├── config.py             # ProcessorNodeConfig schema
│   ├── server.py             # FastAPI app + all REST routes
│   ├── handlers.py           # KOI-net processor handlers (Manifest, Bundle, Network)
│   ├── repository.py         # RepositoryService (DB + cache writes)
│   ├── index_db.py           # SQLite schema + connection
│   ├── cache_manager.py      # Bundle cache integration
│   └── utils.py              # Helpers
├── cli.py                    # Standalone read-only CLI
├── rid_types.py              # GitHubEvent RID-type definition
├── requirements.txt
├── pyrightconfig.json
└── Makefile
```

## Contributing

This node is part of the [koi-net](https://github.com/DynamicalSystemsGroup/koi-net) ecosystem. See the koi-net main repo for contribution guidelines and the broader protocol context.

## License

MIT. See [LICENSE](LICENSE).
