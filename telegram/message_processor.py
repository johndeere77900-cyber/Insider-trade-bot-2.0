"""
Telegram message processor for Insider Trade Bot 2.0.

This module is the bridge between normalized Telegram messages and the
Telegram command/natural-language layers.

Authorization is performed before any request interpretation.
Trading requests remain subject to the dedicated execution boundary.
"""

from __future__ import annotations

from typing import Any

from .auth import TelegramAuthorizer
from .context import TelegramRequestContext
from .formatter import TelegramFormatter
from .handlers import TelegramHandlers
from .messages import TelegramMessage, TelegramResponse
from .natural_language import NaturalLanguageInterpreter
from .natural_language_router import NaturalLanguageRouter
from .parser import TelegramCommandParser
from .router import TelegramRouter


class TelegramMessageProcessor:
    """Process authorized Telegram messages."""

    def __init__(
        self,
        authorizer: TelegramAuthorizer,
        router: TelegramRouter,
        handlers: TelegramHandlers,
        parser: TelegramCommandParser | None = None,
        formatter: TelegramFormatter | None = None,
        natural_language_router: NaturalLanguageRouter | None = None,
    ) -> None:
        self.authorizer = authorizer
        self.router = router
        self.handlers = handlers
        self.parser = parser or TelegramCommandParser()
        self.formatter = formatter or TelegramFormatter()

        self.natural_language_router = (
            natural_language_router
            or NaturalLanguageRouter(
                handlers=handlers,
                interpreter=NaturalLanguageInterpreter(),
            )
        )

    def process(
        self,
        message: TelegramMessage,
        context: Any = None,
    ) -> TelegramResponse:
        """Process one Telegram message into a Telegram response."""
        authorization = self.authorizer.check(
            message.user.user_id
        )

        if not authorization.authorized:
            return TelegramResponse(
                text=self.formatter.unauthorized(),
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
            )

        request_context = context

        if request_context is None:
            request_context = TelegramRequestContext(
                user=message.user,
                chat_id=message.chat_id,
                message_id=message.message_id,
                received_at=message.received_at,
            )

        text = message.text.strip()

        try:
            if text.startswith("/"):
                response_text = self._process_command(
                    text=text,
                    context=request_context,
                )
            else:
                response_text = self.natural_language_router.route(
                    text=text,
                    context=request_context,
                )

        except Exception as exc:
            response_text = self.formatter.error(
                str(exc) or exc.__class__.__name__
            )

        return TelegramResponse(
            text=response_text,
            chat_id=message.chat_id,
            reply_to_message_id=message.message_id,
        )

    def _process_command(
        self,
        text: str,
        context: Any,
    ) -> str:
        """Process a slash command."""
        parsed = self.parser.parse(text)

        route_result = self.router.route(
            parsed,
            context=context,
        )

        if not route_result.handled:
            return self.formatter.unknown_command(
                parsed.name
            )

        if route_result.error:
            return self.formatter.error(
                route_result.error
            )

        return self.formatter.success(
            route_result.result
      )
