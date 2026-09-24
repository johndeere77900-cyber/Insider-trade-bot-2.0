from __future__ import annotations

import application.agent
import application.bootstrap
import application.factory
import application.health
import application.lifecycle
import application.runtime


def test_application_agent_module_imports() -> None:
    assert application.agent is not None


def test_application_bootstrap_module_imports() -> None:
    assert application.bootstrap is not None


def test_application_factory_module_imports() -> None:
    assert application.factory is not None


def test_application_health_module_imports() -> None:
    assert application.health is not None


def test_application_lifecycle_module_imports() -> None:
    assert application.lifecycle is not None


def test_application_runtime_module_imports() -> None:
    assert application.runtime is not None
