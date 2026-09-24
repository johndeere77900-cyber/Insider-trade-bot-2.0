# Insider Trade Bot 2.0

Insider Trade Bot 2.0 is a Python-based research and trading system designed
for historical insider-trading analysis, market-data research, event studies,
signal generation, backtesting, paper trading, and controlled execution.

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
