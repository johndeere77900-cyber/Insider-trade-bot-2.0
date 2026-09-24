from __future__ import annotations

from data.corporate_actions_client import CorporateActionsClient
from data.corporate_actions_loader import CorporateActionsLoader


def test_corporate_actions_client_can_be_created() -> None:
    client = CorporateActionsClient()

    assert client is not None


def test_corporate_actions_client_accepts_configuration() -> None:
    client = CorporateActionsClient(
        api_key="test-key",
        base_url="https://example.test",
    )

    assert client is not None


def test_corporate_actions_loader_can_be_created() -> None:
    loader = CorporateActionsLoader()

    assert loader is not None


def test_corporate_actions_loader_accepts_client() -> None:
    client = CorporateActionsClient(
        api_key="test-key",
        base_url="https://example.test",
    )

    loader = CorporateActionsLoader(client=client)

    assert loader is not None
