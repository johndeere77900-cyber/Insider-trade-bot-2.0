from __future__ import annotations

from telegram.auth import TelegramAuthenticator
from telegram.messages import TelegramMessage
from telegram.parser import TelegramParser


def test_telegram_message_can_be_created() -> None:
    message = TelegramMessage(
        user_id="123456",
        chat_id="123456",
        text="research AAPL",
    )

    assert message.user_id == "123456"
    assert message.chat_id == "123456"
    assert message.text == "research AAPL"


def test_telegram_parser_can_parse_text() -> None:
    parser = TelegramParser()

    result = parser.parse("research AAPL")

    assert result is not None


def test_telegram_authenticator_rejects_unknown_user() -> None:
    authenticator = TelegramAuthenticator(
        allowed_user_ids={"123456"}
    )

    assert authenticator.is_authorized("999999") is False


def test_telegram_authenticator_accepts_allowed_user() -> None:
    authenticator = TelegramAuthenticator(
        allowed_user_ids={"123456"}
    )

    assert authenticator.is_authorized("123456") is True
