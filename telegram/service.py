"""
Telegram service integration layer for Insider Trade Bot 2.0.

This module coordinates Telegram authentication, parsing, routing, and
response formatting. It does not implement the underlying research,
trading, risk, or execution logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .auth import TelegramAuthorizer
from .formatter import TelegramFormatter
from .handlers import TelegramHandlers
from .messages import TelegramMessage, TelegramResponse
from .parser import TelegramCommandParser
from .router import TelegramRouter


@dataclass(frozen=True)
class TelegramServiceResult:
    """Internal result produced while processing a Telegram message."""

    authorized: bool
    response: TelegramResponse


class TelegramService:
    """Coordinate the Telegram interface components."""

    def __init__(
        self,
        authorizer: TelegramAuthorizer,
        router: TelegramRouter,
        parser: TelegramCommandParser | None = None,
        formatter: TelegramFormatter | None = None,
    ) -> None:
        self.authorizer = authorizer
        self.router = router
        self.parser = parser or TelegramCommandParser()
        self.formatter = formatter or TelegramFormatter()

    @classmethod
    def create(
        cls,
        allowed_user_ids: tuple[int, ...],
        application_service: Any = None,
    ) -> "TelegramService":
        """Create a configured Telegram service."""
        authorizer = TelegramAuthorizer(allowed_user_ids)
        parser = TelegramCommandParser()
        formatter = TelegramFormatter()

        handlers = TelegramHandlers(
            formatter=formatter,
            service=application_service,
        )

        router = TelegramRouter()

        router.register("start", handlers.start)
        router.register("help", handlers.help)
        router.register("status", handlers.status)
        router.register("research", handlers.research)
        router.register("signal", handlers.signal)
        router.register("backtest", handlers.backtest)
        router.register("portfolio", handlers.portfolio)

        return cls(
            authorizer=authorizer,
            router=router,
            parser=parser,
            formatter=formatter,
        )

    def process(
        self,
        message: TelegramMessage,
        context: Any = None,
    ) -> TelegramServiceResult:
        """
        Process one normalized Telegram message.

        The sequence is:

        1. Authorization
        2. Command parsing
        3. Command routing
        4. Response formatting

        No underlying business operation is performed directly here.
        """
        authorization = self.authorizer.check(message.user.user_id)

        if not authorization.authorized:
            return TelegramServiceResult(
                authorized=False,
                response=TelegramResponse(
                    text=self.formatter.unauthorized(),
                    chat_id=message.chat_id,
                    reply_to_message_id=message.message_id,
                ),
            )

        try:
            parsed = self.parser.parse(message.text)
        except (TypeError, ValueError) as exc:
            return TelegramServiceResult(
                authorized=True,
                response=TelegramResponse(
                    text=self.formatter.error(
                        str(exc),
                        title="Invalid message",
                    ),
                    chat_id=message.chat_id,
                    reply_to_message_id=message.message_id,
                ),
            )

        route_result = self.router.route(
            parsed,
            context=context,
        )

        if not route_result.handled:
            text = self.formatter.unknown_command(
                parsed.name
            )
        elif route_result.error:
            text = self.formatter.error(
                route_result.error
            )
        else:
            text = self.formatter.success(
                route_result.result
            )

        return TelegramServiceResult(
            authorized=True,
            response=TelegramResponse(
                text=text,
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
            ),
      )
