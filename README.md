# Insider Trade Bot 2.0

Insider Trade Bot 2.0 is a Python-based research and trading system designed
for historical insider-trading analysis, market-data research, event studies,
signal generation, backtesting, paper trading, and controlled execution.

## Target Storage Architecture

Insider Trade Bot 2.0 uses a tiered, cost-efficient storage architecture designed for Neon PostgreSQL constraints:

```
SEC Quarterly ZIP (Official SEC Data)
    ↓
Immutable Raw Dataset Archive (Disk / S3 / R2 cold storage)
    ↓
Normalized Operational Database (Neon PostgreSQL)
    ↓
Research & Signal Engine
```

1. **Normalized Operational Database (Neon):** Retains parsed, normalized transaction fields required for querying, signal generation, and research (`insider_transactions`, `ingestion_state`, `dataset_period` provenance).
2. **Immutable Raw Archive:** Preserves complete quarterly SEC datasets and raw payloads separately for full auditing/reprocessing without bloating database index storage.
3. **Dataset-Level Provenance:** Provenance is tracked at the dataset period level (`dataset_period`) rather than per-transaction.

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
