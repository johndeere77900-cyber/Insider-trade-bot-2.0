"""
Execution interfaces for Insider Trade Bot.

This module defines the contract that any future broker or exchange adapter
must satisfy.

Defining the interface separately prevents research, risk, and paper-trading
components from becoming coupled to a specific execution provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


OrderSide = Literal[
    "buy",
    "sell",
]


@dataclass(frozen=True)
class ExecutionRequest:
    """
    Request passed to an execution adapter.
    """

    client_order_id: str

    symbol: str
    side: OrderSide

    quantity: float

    reference_price: float


@dataclass(frozen=True)
class ExecutionResult:
    """
    Standardized result returned by an execution adapter.
    """

    client_order_id: str

    external_order_id: str | None

    status: str

    executed_quantity: float

    executed_price: float | None

    message: str | None = None


class ExecutionAdapterError(
    Exception
):
    """Base exception for execution-adapter failures."""


class ExecutionAdapter(
    ABC
):
    """
    Abstract execution-adapter contract.

    Implementations may connect to brokers or exchanges, but the rest of
    the application interacts only through this interface.
    """

    @abstractmethod
    def execute(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """
        Submit an execution request.
        """

        raise NotImplementedError

    @abstractmethod
    def cancel(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Request cancellation of an existing order.
        """

        raise NotImplementedError

    @abstractmethod
    def get_status(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Retrieve the current execution status of an order.
        """

        raise NotImplementedError
