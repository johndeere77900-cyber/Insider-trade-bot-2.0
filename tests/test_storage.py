from __future__ import annotations

from storage.repository import Repository


def test_repository_can_be_created(tmp_path) -> None:
    repository = Repository(
        database_url=f"sqlite:///{tmp_path / 'storage.db'}"
    )

    assert repository is not None


def test_repository_can_store_and_retrieve_a_record(tmp_path) -> None:
    repository = Repository(
        database_url=f"sqlite:///{tmp_path / 'storage.db'}"
    )

    record = {
        "symbol": "AAPL",
        "source": "TEST",
        "record_hash": "test-hash-001",
    }

    result = repository.store(
        table="insider_transactions",
        record=record,
    )

    assert result is not None
