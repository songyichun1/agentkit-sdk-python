# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Request-scoped AgentKit identity context."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from agentkit.identity.errors import IdentityAuthenticationError


@dataclass(frozen=True, repr=False)
class IdentityContext:
    """Verified user plus the current AgentKit Runtime/Workload identity."""

    user_sub: str
    issuer: str
    client_id: str
    user_expires_at: int
    runtime_id: str
    workload_pool: str
    invocation_id: str

    def __repr__(self) -> str:
        return (
            "IdentityContext("
            f"user_sub={self.user_sub!r}, issuer={self.issuer!r}, "
            f"client_id={self.client_id!r}, runtime_id={self.runtime_id!r}, "
            f"user_expires_at={self.user_expires_at!r}, "
            f"workload_pool={self.workload_pool!r}, "
            f"invocation_id={self.invocation_id!r})"
        )


@dataclass(frozen=True, repr=False)
class _IdentityBinding:
    context: IdentityContext
    owner: Any = field(repr=False)
    user_token: str = field(repr=False)


_CURRENT_BINDING: ContextVar[_IdentityBinding | None] = ContextVar(
    "agentkit_current_identity_binding", default=None
)


def current_identity(*, required: bool = True) -> IdentityContext | None:
    """Return the current verified identity without exposing its bearer token."""

    binding = _CURRENT_BINDING.get()
    if binding is None and required:
        raise IdentityAuthenticationError(
            "no verified identity is bound to the current Runtime request"
        )
    return binding.context if binding is not None else None


def _bind_identity(
    identity: IdentityContext,
    *,
    owner: Any,
    user_token: str,
) -> Token[_IdentityBinding | None]:
    """Bind safe metadata and its private credential for one SDK Runtime."""

    return _CURRENT_BINDING.set(
        _IdentityBinding(context=identity, owner=owner, user_token=user_token)
    )


def _reset_identity(marker: Token[_IdentityBinding | None]) -> None:
    """Restore the previous context after a request, exception, or cancellation."""

    _CURRENT_BINDING.reset(marker)


def _current_binding(owner: Any) -> _IdentityBinding:
    binding = _CURRENT_BINDING.get()
    if binding is None:
        raise IdentityAuthenticationError(
            "no verified identity is bound to the current Runtime request"
        )
    if binding.owner is not owner:
        raise IdentityAuthenticationError(
            "the verified identity belongs to a different Runtime"
        )
    return binding
