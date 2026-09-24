"""
Natural-language routing for Insider Trade Bot 2.0.

This module converts interpreted natural-language requests into calls to the
existing Telegram command handlers.

It does not bypass authorization, risk controls, execution safety, or any
other core agent boundary.
"""

from __future__ import annotations

from typing import Any

from .handlers import TelegramHandlers
from .natural_language import NaturalLanguageInterpreter
from .parser import ParsedCommand


class NaturalLanguageRouter:
    """Route natural-language requests to existing application handlers."""

    def __init__(
        self,
        handlers: TelegramHandlers,
        interpreter: NaturalLanguageInterpreter | None = None,
    ) -> None:
        self.handlers = handlers
        self.interpreter = interpreter or NaturalLanguageInterpreter()

    def route(
        self,
        text: str,
        context: Any = None,
    ) -> str:
        """
        Interpret and route one natural-language request.

        Unknown requests are returned as a safe explanatory response rather
        than being guessed into an action.
        """
        request = self.interpreter.interpret(text)

        if request.intent == "help":
            return self.handlers.help(
                ParsedCommand(
                    name="help",
                    arguments=(),
                    raw_text=text.strip(),
                ),
                context,
            )

        if request.intent == "status":
            return self.handlers.status(
                ParsedCommand(
                    name="status",
                    arguments=(),
                    raw_text=text.strip(),
                ),
                context,
            )

        if request.intent == "research":
            arguments = (text.strip(),)

            return self.handlers.research(
                ParsedCommand(
                    name="research",
                    arguments=arguments,
                    raw_text=text.strip(),
                ),
                context,
            )

        if request.intent == "signal":
            if not request.symbol:
                return (
                    "I could not identify a stock symbol.\n\n"
                    "Example: research the insider activity for AAPL"
                )

            return self.handlers.signal(
                ParsedCommand(
                    name="signal",
                    arguments=(request.symbol,),
                    raw_text=text.strip(),
                ),
                context,
            )

        if request.intent == "backtest":
            if not request.symbol:
                return (
                    "I could not identify a stock symbol.\n\n"
                    "Example: backtest AAPL"
                )

            return self.handlers.backtest(
                ParsedCommand(
                    name="backtest",
                    arguments=(request.symbol,),
                    raw_text=text.strip(),
                ),
                context,
            )

        if request.intent == "portfolio":
            return self.handlers.portfolio(
                ParsedCommand(
                    name="portfolio",
                    arguments=(),
                    raw_text=text.strip(),
                ),
                context,
            )

        if request.intent in {"trade_buy", "trade_sell"}:
            return (
                "Trading requests are not executed through the "
                "natural-language interpreter.\n\n"
                "Any trading request must pass the dedicated execution "
                "mode, risk controls, and execution safety boundaries."
            )

        return (
            "I could not determine the requested operation.\n\n"
            "Try asking for research, a signal, a backtest, portfolio "
            "information, or system status."
          )
