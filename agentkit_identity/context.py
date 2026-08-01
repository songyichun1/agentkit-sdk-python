# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Request-scoped AgentKit identity context."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from threading import Condition
from typing import Any

from agentkit_identity.errors import IdentityAuthenticationError


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


class _RequestLease:
    """A revocable request lease shared by copied async contexts."""

    def __init__(self) -> None:
        self._active = True
        self._uses = 0
        self._condition = Condition()

    @property
    def active(self) -> bool:
        with self._condition:
            return self._active

    def revoke(self) -> None:
        """Reject new uses without blocking the ASGI event loop."""

        with self._condition:
            self._active = False

    def wait_idle(self) -> None:
        """Wait until every operation admitted before revocation has finished."""

        with self._condition:
            while self._uses:
                self._condition.wait()

    @contextmanager
    def use(self) -> Iterator[None]:
        """Prevent request revocation while one credential operation is active."""

        with self._condition:
            if not self._active:
                raise IdentityAuthenticationError(
                    "the verified identity request lease has ended"
                )
            self._uses += 1
        try:
            yield
        finally:
            with self._condition:
                self._uses -= 1
                if not self._uses:
                    self._condition.notify_all()


@dataclass(frozen=True, repr=False)
class _IdentityBinding:
    context: IdentityContext
    owner: Any = field(repr=False)
    user_token: str = field(repr=False)
    lease: _RequestLease = field(repr=False)


@dataclass(frozen=True, repr=False)
class _BindingMarker:
    token: Token[_IdentityBinding | None] = field(repr=False)
    lease: _RequestLease = field(repr=False)


_CURRENT_BINDING: ContextVar[_IdentityBinding | None] = ContextVar(
    "agentkit_current_identity_binding", default=None
)


def current_identity(*, required: bool = True) -> IdentityContext | None:
    """Return the current verified identity without exposing its bearer token."""

    binding = _CURRENT_BINDING.get()
    if (binding is None or not binding.lease.active) and required:
        raise IdentityAuthenticationError(
            "no verified identity is bound to the current Runtime request"
        )
    if binding is None or not binding.lease.active:
        return None
    return binding.context


def _bind_identity(
    identity: IdentityContext,
    *,
    owner: Any,
    user_token: str,
) -> _BindingMarker:
    """Bind safe metadata and its private credential for one SDK Runtime."""

    lease = _RequestLease()
    token = _CURRENT_BINDING.set(
        _IdentityBinding(
            context=identity,
            owner=owner,
            user_token=user_token,
            lease=lease,
        )
    )
    return _BindingMarker(token=token, lease=lease)


def _reset_identity(marker: _BindingMarker) -> None:
    """Restore the previous context after a request, exception, or cancellation."""

    # A child task created during the request receives a copied ContextVar value,
    # but it still shares this mutable lease. Revocation therefore invalidates
    # identity use in detached work before the parent context is restored.
    marker.lease.revoke()
    _CURRENT_BINDING.reset(marker.token)


async def _drain_identity(marker: _BindingMarker) -> None:
    """Drain admitted operations even while the parent request is cancelled."""

    drain = asyncio.create_task(asyncio.to_thread(marker.lease.wait_idle))
    cancelled = False
    while not drain.done():
        try:
            await asyncio.shield(drain)
        except asyncio.CancelledError:
            cancelled = True
    drain.result()
    if cancelled:
        raise asyncio.CancelledError


def _current_binding(owner: Any) -> _IdentityBinding:
    binding = _CURRENT_BINDING.get()
    if binding is None:
        raise IdentityAuthenticationError(
            "no verified identity is bound to the current Runtime request"
        )
    if not binding.lease.active:
        raise IdentityAuthenticationError(
            "the verified identity request lease has ended"
        )
    if binding.owner is not owner:
        raise IdentityAuthenticationError(
            "the verified identity belongs to a different Runtime"
        )
    return binding
