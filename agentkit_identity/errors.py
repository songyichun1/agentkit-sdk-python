# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Stable, token-safe errors for AgentKit Runtime identity."""

from __future__ import annotations


class IdentityError(RuntimeError):
    """Base error whose message must never contain bearer credentials."""


class IdentityAuthenticationError(IdentityError):
    """The inbound user identity is missing or invalid."""


class IdentityUnavailableError(IdentityError):
    """A trusted identity dependency is temporarily unavailable."""


class WorkloadBindingError(IdentityError):
    """The Runtime cannot establish its trusted Workload binding."""


class TargetNotConfiguredError(IdentityError):
    """Business code requested a target that is not registered."""


class TokenExchangeError(IdentityError):
    """Identity could not mint a target-bound workload token."""


class TargetRequestError(IdentityError):
    """A protected-target request failed without exposing its bearer token."""
