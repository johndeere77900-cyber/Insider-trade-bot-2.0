# Insider Trade Bot 2.0

Insider Trade Bot 2.0 is a Python-based research and trading system designed
for historical insider-trading analysis, market-data research, event studies,
signal generation, backtesting, paper trading, and controlled execution.

## Target Storage Architecture

Insider Trade Bot 2.0 uses a tiered, storage-safe architecture designed for Neon PostgreSQL storage constraints:

```
SEC (Acquisition Source Only)
    ↓
Quarterly ZIP
    ↓
Cloudflare R2 = COMPLETE IMMUTABLE SOURCE ARCHIVE (2006-Q1 → 2026-Q2)
    ↓
Research / Data Access Layer
    ├── Neon = lean operational / research cache (configured retention window)
    └── R2 = historical source fallback when data is not in Neon
    ↓
Research / Event Study / Backtest / Signal Engine
```

### System Layer Responsibilities

- **Cloudflare R2:**
  - Complete immutable SEC quarterly source archive (2006-Q1 through 2026-Q2).
  - Authoritative source for historical raw SEC datasets.
  - Receives and stores all historical quarterly ZIP archives upon acquisition.
  - Preserved permanently across database retries or resets.

- **Neon PostgreSQL:**
  - Lean operational/research database cache.
  - Stores configured recent operational retention window (`SEC_OPERATIONAL_RETENTION_YEARS=3`).
  - Indexed, research-ready operational data (`insider_transactions`, `market_prices`, `ingestion_state`, `dataset_period` provenance).
  - NOT the complete raw 20-year historical transaction warehouse.

- **Research / Data Access Layer:**
  - Clean abstraction (`research.research_data_access`) that hides storage location from research callers.
  - Transparently checks Neon operational cache first.
  - Verifies dataset completeness (`verify_dataset_coverage`).
  - Falls back to reading and normalizing immutable quarterly ZIPs directly from R2 for periods outside Neon retention.
  - Period-based deterministic retrieval (`get_historical_transactions`).

- **SEC:**
  - External acquisition source only.
  - Not directly queried during research operations.

- **RAW vs Point-in-Time Adjusted Price Rules:**
  - **RAW Market Prices** are used for:
    - Execution
    - Position sizing
    - Actual traded prices
    - Cost / slippage calculations
  - **Point-in-Time Adjusted Prices** (`research.price_adjustment`) are used for:
    - Research returns across splits/dividends
    - Technical indicators that must survive corporate actions
    - Research comparisons
  - RAW and Point-in-Time adjusted prices are NEVER mixed implicitly.

- **Event Study Engine & Adapter:** An adapter (`research.insider_adapter`) maps normalized insider transactions into research event inputs for `research.event_study`, enforcing price series mode selection (`RAW` vs `POINT_IN_TIME_ADJUSTED`) and data quality safety checks.

- **Feature & Signal Engine:** Feature engine (`features.engine`) builds point-in-time features with explicit provenance. Signal engine (`signals.engine`) creates research-only signal candidates that CANNOT directly authorize execution.

- **Signals & Backtesting:** Clean research event outputs feed directly into signal candidate generation and chronological portfolio backtesting simulation (`backtesting.engine`) with capital allocation, equity curve tracking, fees, slippage, and maximum drawdown calculations.

### Operational Retention Configuration (`SEC_OPERATIONAL_RETENTION_YEARS`)

Neon database storage is kept lean using configurable operational retention:

- **`SEC_OPERATIONAL_RETENTION_YEARS=3` (Default / Production):** Neon stores normalized transaction records for the most recent 3 years of operational data.
- **Historical Backfills:** For periods outside the operational retention window, acquisition downloads and validates the SEC ZIP, persists the complete archive in R2, records dataset-level provenance and completion state, and omits bulk transaction insertion into Neon.
- **`SEC_STORE_RAW_PAYLOAD=false` (Default / Production):** `raw_payload` is NOT persisted into `insider_transactions`, saving substantial database storage while retaining all normalized transaction fields, deterministic transaction identity (`record_hash`), dataset-level provenance, and ingestion state.

### Immutable Archive Configuration

- **`SEC_ARCHIVE_BACKEND` (Default: `filesystem`):** Archive storage backend implementation.
- **`SEC_ARCHIVE_PATH` (Default: `data/archive`):** Local filesystem directory path for storing quarterly SEC ZIP archives and sidecar manifest JSON files.

## Storage Recovery Production Sequence

When recovering Neon storage or preparing for production historical SEC backfill, execute the following explicit maintenance sequence:

1. **Merge Code Changes:** Deploy the storage architecture repair PR.
2. **Run Storage Audit:** Inspect database storage usage:
   `python main.py storage-audit`
3. **Run Redundant Index Migration:** Drop duplicate index `idx_insider_tx_uniq`:
   `python scripts/migrate_storage.py`
4. **Verify Storage Recovery:** Confirm index storage space has been reclaimed in Neon.
5. **Audit Legacy Provenance:** Verify legacy transaction-level provenance rows and safety prerequisites:
   `python main.py storage-maintenance provenance-audit`
6. **Perform Explicit Legacy Provenance Cleanup:** Clean up legacy per-transaction provenance rows:
   Dry-run mode: `python main.py storage-maintenance provenance-cleanup --dry-run`
   Execute mode: `python main.py storage-maintenance provenance-cleanup --execute`
7. **Run Final Storage Audit:** Verify recovered storage:
   `python main.py storage-audit`
8. **Resume Historical SEC Backfill:** Only after verifying storage recovery, resume SEC backfill:
   `python main.py historical --start 2006-Q1 --end 2026-Q2`

## Current System Principles

The system is designed around the following boundaries:

1. External data is ingested first.
2. Data is normalized and validated.
3. Provenance and integrity are preserved.
4. Validated records are stored permanently.
5. Historical data can be used for research.
6. Research can feed signal generation.
7. Signals can be evaluated through backtesting.
8. Paper trading remains separate from live execution.
9. Live execution requires explicit safety controls.
10. Telegram acts as an interface to the agent rather than replacing
   the underlying business logic.

## Configuration

Copy `.env.example` to `.env` and provide the required environment values.

The `.env` file must not be committed to Git.

At minimum, the application requires an identifying SEC User-Agent.

## Installation

Create and activate a Python virtual environment.

Install the project dependencies:

    pip install -r requirements.txt

The project can also be installed as a Python package:

    pip install -e .

## Running Tests

Run the test suite with:

    pytest

Tests are intended to verify the individual system boundaries before
integrated runtime validation.

## Running the Application

The executable entry point is:

    python main.py

At the current assembly stage, `main.py` validates configuration and
establishes the startup boundary.

The complete application runtime must pass integrated assembly and
safety validation before production operation.

## Trading Safety

Paper trading and live trading are separate execution modes.

Live trading must never be enabled merely because an environment variable
exists. The application must also satisfy its configured safety and
validation requirements.

Never place real trades until the complete system has been integrated,
audited, tested, and explicitly configured for live execution.

## Data

The intended permanent data layer includes:

- Historical SEC insider records
- Market-price history
- Corporate-action records
- Research/event-study results
- Generated signals
- Backtest results
- Trading outcomes
- Provenance and validation information

Historical ingestion is subject to source availability, rate limits,
provider requirements, and later integrated validation.

## Telegram

Telegram is an interface layer.

The intended flow is:

Telegram request
→ command/natural-language interpretation
→ application services
→ research/data/trading components
→ safety and execution controls
→ formatted response
→ Telegram

Telegram must not bypass the application's validation, risk, or execution
boundaries.

## Development Status

This repository is being assembled incrementally.

The presence of a source file does not by itself mean that the complete
production system has been validated.

The next required stage after assembly is integrated testing and audit.
Any discovered incompatibility must be corrected based on the actual
failure rather than by adding unnecessary wrapper layers.
