"""
Telegram interface package for Insider Trade Bot 2.0.

This package contains the Telegram-facing layer only.

The Telegram layer is responsible for:
- receiving user messages and commands,
- authenticating and authorizing users,
- routing requests to internal agent services,
- formatting results for Telegram,
- handling Telegram-specific errors and responses.

Business logic, research logic, trading logic, risk controls,
and execution safety must remain outside this package.
"""
