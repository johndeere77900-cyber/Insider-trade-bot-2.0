from __future__ import annotations


def test_core_system_packages_are_importable() -> None:
    import config
    import core
    import database
    import data
    import execution
    import ingestion
    import outcomes
    import research
    import risk
    import signals
    import storage
    import trading
    import validation


def test_interface_packages_are_importable() -> None:
    import application
    import telegram


def test_main_entrypoint_is_available() -> None:
    import main

    assert callable(main.main)
