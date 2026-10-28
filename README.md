# Sales Data Analytics Agent

A **Google ADK** agent that answers sales-data questions by running **Polars** code in a
sandbox (local subprocess or remote **Daytona**), with a **Streamlit** chat UI.

## How to run

### 1. Install dependencies

This project uses [uv](https://docs.astral.sh/uv/). Dependencies are declared in `pyproject.toml`.

```bash
uv sync
```

### 2. Set environment variables

Create a `.env` file in the project root (loaded automatically via `python-dotenv`). Three
variables cover the stack — Google ADK, Streamlit, and Daytona:

```
# Google ADK (Gemini) — required for the agent
GEMINI_API_KEY=your-gemini-api-key

# Sandbox backend: "subprocess" (local, default) or "daytona" (remote)
SANDBOX_BACKEND=subprocess

# Daytona — required only when SANDBOX_BACKEND=daytona
DAYTONA_API_KEY=your-daytona-api-key
```

See [`.env.example`](.env.example) for the full list (including `LLM_MODEL`). The Streamlit
UI reads the same `.env`, so no extra configuration is needed to run it.

### 3. Run

**CLI — single question:**

```bash
uv run python app.py "What is the total revenue by category?"
```

**CLI — interactive mode:**

```bash
uv run python app.py
```

**Streamlit UI:**

```bash
uv run streamlit run ui.py
```

## Configuration

`config.py` is the single place to switch the LLM, the execution sandbox, and the dataset. Each value can also be overridden with an environment variable.

| Setting | Env var | Default | What it does |
| --- | --- | --- | --- |
| `LLM_MODEL` | `LLM_MODEL` | `gemini-3.5-flash-lite` | Model the agent runs on. |
| `SANDBOX_BACKEND` | `SANDBOX_BACKEND` | `subprocess` | Where generated Polars code runs. |
| `DEFAULT_CSV` | — | `data/sales_data.csv` | Dataset the agent analyzes. |

### Sandbox backends

Model-generated code runs in a sandbox. Two are available, selected by `SANDBOX_BACKEND`:

- **`subprocess`** (default) — runs code locally in an isolated `python -I` subprocess with CPU, file-size, and wall-clock limits. No extra setup.
- **`daytona`** — runs code in a remote [Daytona](https://www.daytona.io/) sandbox. The sandbox is created once and reused, the CSV is uploaded to it, and the remote Polars is pinned to your local version.

To use Daytona:

```bash
uv pip install -e '.[daytona]'
```

Then add your key to `.env` and select the backend:

```
DAYTONA_API_KEY=...
SANDBOX_BACKEND=daytona
```

```bash
SANDBOX_BACKEND=daytona uv run streamlit run ui.py
```

## Project structure

| File | Purpose |
| --- | --- |
| `config.py` | Central configuration — LLM, sandbox backend, and dataset. |
| `app.py` | Agent factory (`create_agent`) and CLI entrypoint. |
| `tool.py` | The `execute_polars_code` tool — runs model-generated Polars code in the configured sandbox — plus `get_csv_context`. |
| `sandbox.py` | Execution backends (`subprocess` and `daytona`) behind a common interface, selected via `config.py`. |
| `analytics.py` | Deterministic Polars helpers (KPIs, revenue-by, top products, monthly trend, rep leaderboard) that power the Report page — no LLM involved. |
| `ui.py` | Streamlit entrypoint: the Chat page, backed by the agent. |
| `nav.py` | Shared sidebar navigation across pages. |
| `pages/` | Additional Streamlit pages: `Report` (prebuilt dashboard) and `Data Explorer`. |
| `data/sales_data.csv` | The sales dataset. |

The **Chat** page uses the LLM agent to answer free-form questions; the **Report**
and **Data Explorer** pages use `analytics.py` directly for fast, deterministic
numbers with no model calls.
