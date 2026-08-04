# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""AgentKit CLI - Model Gateway commands."""

from __future__ import annotations

from enum import Enum
import json
import time
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentkit.sdk.model_gateway.client import AgentkitModelGatewayClient
from agentkit.sdk.model_gateway import types as mgw

console = Console()

MODEL_GATEWAY_RUNNING_STATUS = "Running"
MODEL_GATEWAY_FAILED_STATUSES = {"CreatedFailed", "UpdatedFailed", "DeletedFailed"}
MODEL_GATEWAY_ERROR_STATUSES = MODEL_GATEWAY_FAILED_STATUSES | {"Error"}


class ModelGatewayExampleType(str, Enum):
    curl = "curl"
    openai = "openai"
    anthropic = "anthropic"
    agentkit = "agentkit"


model_gateway_app = typer.Typer(
    name="model-gateway",
    help="Manage AgentKit Model Gateway.",
    add_completion=False,
)
provider_app = typer.Typer(
    name="provider",
    help="Manage model gateway providers.",
    add_completion=False,
)
consumer_app = typer.Typer(
    name="consumer",
    help="Manage model gateway consumers.",
    add_completion=False,
)


def _print_api_error(action: str, exc: Exception) -> None:
    msg = str(exc)
    server_message = None
    code = None
    try:
        start = msg.find("{")
        end = msg.rfind("}")
        if start != -1 and end > start:
            payload = json.loads(msg[start : end + 1])
            err = payload.get("ResponseMetadata", {}).get("Error", {})
            code = err.get("Code")
            server_message = err.get("Message")
    except Exception:
        pass

    lines = []
    if code:
        lines.append(f"Code: [yellow]{code}[/yellow]")
    lines.append(f"Message: [red]{server_message or msg}[/red]")
    console.print(
        Panel.fit(
            "\n".join(lines),
            title=f"{action} Error",
            border_style="red",
        )
    )


def _client(region: Optional[str]) -> AgentkitModelGatewayClient:
    return AgentkitModelGatewayClient(region=(region or "").strip())


def _require_value(option_name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise typer.BadParameter(f"{option_name} cannot be empty")
    return normalized


def _require_values(option_name: str, values: List[str]) -> List[str]:
    if not values:
        raise typer.BadParameter(f"{option_name} requires at least one value")
    return [_require_value(option_name, value) for value in values]


def _require_single_protocol(values: Optional[List[str]]) -> List[str]:
    protocols = _require_values("--protocol", values or [])
    if len(protocols) != 1:
        raise typer.BadParameter("--protocol currently requires exactly one value")
    return protocols


def _require_allow_models(values: Optional[List[str]]) -> Optional[List[str]]:
    if not values:
        return None

    normalized_values = _require_values("--allow-model", values)
    for item in normalized_values:
        if "/" not in item:
            _require_value("--allow-model provider name", item)
            continue
        provider_name, model_name = item.split("/", 1)
        _require_value("--allow-model provider name", provider_name)
        _require_value("--allow-model model name", model_name)
    return normalized_values


def _get_model_gateway(
    client: AgentkitModelGatewayClient,
    model_gateway_id: str,
) -> mgw.ModelGatewaysForModelGateway:
    resp = client.list_model_gateways(
        mgw.ListModelGatewaysRequest(page_number=1, page_size=100)
    )
    for gateway in resp.model_gateways or []:
        if gateway.model_gateway_id == model_gateway_id:
            return gateway
    raise RuntimeError(f"Model gateway not found: {model_gateway_id}")


def _wait_model_gateway_running(
    client: AgentkitModelGatewayClient,
    model_gateway_id: str,
    action: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 2,
) -> mgw.ModelGatewaysForModelGateway:
    time.sleep(1)
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    with console.status(
        "[cyan]Waiting for ModelGateway status to become Running...[/cyan]",
        spinner="dots",
    ) as wait_status:
        while True:
            gateway = _get_model_gateway(client, model_gateway_id)
            status = gateway.status or ""
            if status != last_status:
                last_status = status
                wait_status.update(
                    f"[cyan]ModelGateway status: {status or 'Unknown'}[/cyan]"
                )
            if status == MODEL_GATEWAY_RUNNING_STATUS:
                return gateway
            if status in MODEL_GATEWAY_ERROR_STATUSES:
                message = f"ModelGateway status is {status}"
                if gateway.message:
                    message = f"{message}: {gateway.message}"
                raise RuntimeError(message)
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Timed out waiting for ModelGateway to become Running "
                    f"after {action}. Last status: {status or 'Unknown'}"
                )
            time.sleep(poll_interval_seconds)


def _resolve_model_gateway_id(
    client: AgentkitModelGatewayClient,
) -> str:
    resp = client.list_model_gateways(
        mgw.ListModelGatewaysRequest(page_number=1, page_size=100)
    )
    gateways = resp.model_gateways or []
    if gateways and gateways[0].model_gateway_id:
        return gateways[0].model_gateway_id
    raise typer.BadParameter(
        "No model gateway found. Run 'agentkit model-gateway activate' first."
    )


def _normalize_protocol(protocol: str) -> str:
    value = protocol.strip()
    aliases = {
        "openai": "OpenAICompatible",
        "openai-compatible": "OpenAICompatible",
        "OpenAICompatible": "OpenAICompatible",
        "anthropic": "AnthropicCompatible",
        "anthropic-compatible": "AnthropicCompatible",
        "AnthropicCompatible": "AnthropicCompatible",
    }
    if value not in aliases:
        raise typer.BadParameter(
            "--protocol must be one of: openai, anthropic, "
            "OpenAICompatible, AnthropicCompatible"
        )
    return aliases[value]


def _build_credentials(api_keys: List[str]) -> mgw.CredentialsForModelGateway:
    return mgw.CredentialsForModelGateway(
        type="APIKey",
        api_keys=[
            mgw.ApiKeysForModelGateway(name=f"key_{idx}", value=value)
            for idx, value in enumerate(api_keys, start=1)
        ],
    )


def _provider_models(models: List[str]) -> List[mgw.ProviderModelsForModelGateway]:
    return [mgw.ProviderModelsForModelGateway(model_name=model) for model in models]


def _provider_table(providers: List[mgw.ProvidersForModelGateway]) -> Table:
    table = Table(title="Model Gateway Providers")
    table.add_column("Provider ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Access URL", style="blue")
    table.add_column("Models", style="green")
    for item in providers:
        models = ", ".join(m.model_name or "" for m in item.provider_models or [])
        table.add_row(
            item.provider_id or "",
            item.provider_name or "",
            item.base_url or "",
            models,
        )
    return table


def _consumer_table(
    consumers: List[mgw.ConsumersForModelGateway],
    provider_names_by_id: Optional[dict[str, str]] = None,
    provider_model_names_by_id: Optional[dict[str, str]] = None,
) -> Table:
    provider_names_by_id = provider_names_by_id or {}
    provider_model_names_by_id = provider_model_names_by_id or {}
    table = Table(title="Model Gateway Consumers")
    table.add_column("Consumer ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Authorization", style="green")
    table.add_column("TPM", style="magenta")
    table.add_column("TPD", style="magenta")
    for item in consumers:
        tpm, tpd = _consumer_rate_limits(item)
        table.add_row(
            item.consumer_id or "",
            item.consumer_name or "",
            _consumer_authz(item, provider_names_by_id, provider_model_names_by_id),
            tpm,
            tpd,
        )
    return table


def _print_fields(fields: List[tuple[str, str]]) -> None:
    for key, value in fields:
        typer.echo(f"{key}: {value}")


def _provider_show(provider: mgw.ProvidersForModelGateway) -> None:
    models = ", ".join(m.model_name or "" for m in provider.provider_models or [])
    base_url = provider.provider_spec.base_url if provider.provider_spec else ""
    api_keys = (
        ", ".join(key.value or "" for key in provider.credentials.api_keys or [])
        if provider.credentials
        else ""
    )
    _print_fields(
        [
            ("Provider ID", provider.provider_id or ""),
            ("Name", provider.provider_name or ""),
            ("Access URL", provider.base_url or ""),
            ("Base URL", base_url),
            ("API Keys", api_keys),
            ("Models", models),
        ]
    )


def _consumer_authz(
    consumer: mgw.ConsumersForModelGateway,
    provider_names_by_id: dict[str, str],
    provider_model_names_by_id: dict[str, str],
) -> str:
    if not consumer.authz_config:
        return ""
    if consumer.authz_config.allow_all_providers:
        return "All"
    if not consumer.authz_config.provider_authz_configs:
        return ""

    parts = []
    for config in consumer.authz_config.provider_authz_configs:
        provider_id = config.provider_id or ""
        provider_name = provider_names_by_id.get(provider_id, provider_id)
        if config.allow_all_provider_models:
            parts.append(f"{provider_name}:*")
        else:
            for model_id in config.allowed_provider_model_ids or []:
                model_name = provider_model_names_by_id.get(model_id, model_id)
                parts.append(f"{provider_name}:{model_name}")
    return "; ".join(parts)


def _consumer_rate_limits(consumer: mgw.ConsumersForModelGateway) -> tuple[str, str]:
    tpm = ""
    tpd = ""
    if consumer.token_rate_limit_config:
        for rule in consumer.token_rate_limit_config.rules or []:
            if rule.time_window == 60:
                tpm = str(rule.value or "")
            elif rule.time_window == 86400:
                tpd = str(rule.value or "")
    return tpm, tpd


def _consumer_show(
    consumer: mgw.ConsumersForModelGateway,
    provider_names_by_id: dict[str, str],
    provider_model_names_by_id: dict[str, str],
) -> None:
    tpm, tpd = _consumer_rate_limits(consumer)
    _print_fields(
        [
            ("Consumer ID", consumer.consumer_id or ""),
            ("Name", consumer.consumer_name or ""),
            ("API Keys", ", ".join(consumer.api_keys or [])),
            (
                "Authorization",
                _consumer_authz(
                    consumer,
                    provider_names_by_id,
                    provider_model_names_by_id,
                ),
            ),
            ("TPM", tpm),
            ("TPD", tpd),
        ]
    )


def _provider_authz_display_maps(
    client: AgentkitModelGatewayClient,
    model_gateway_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    resp = client.list_model_gateway_providers(
        mgw.ListModelGatewayProvidersRequest(
            model_gateway_id=model_gateway_id,
            page_number=1,
            page_size=100,
        )
    )
    provider_names_by_id = {}
    provider_model_names_by_id = {}
    for item in resp.providers or []:
        if item.provider_id:
            provider_names_by_id[item.provider_id] = (
                item.provider_name or item.provider_id
            )
        for model in item.provider_models or []:
            if model.provider_model_id:
                provider_model_names_by_id[model.provider_model_id] = (
                    model.model_name or model.provider_model_id
                )
    return provider_names_by_id, provider_model_names_by_id


def _find_provider_by_name(
    client: AgentkitModelGatewayClient,
    model_gateway_id: str,
    name: str,
) -> mgw.ProvidersForModelGateway:
    resp = client.list_model_gateway_providers(
        mgw.ListModelGatewayProvidersRequest(
            model_gateway_id=model_gateway_id,
            provider_name=name,
            page_number=1,
            page_size=100,
        )
    )
    matches = [p for p in resp.providers or [] if p.provider_name == name]
    if len(matches) != 1 or not matches[0].provider_id:
        raise typer.BadParameter(f"Provider not found or ambiguous: {name}")
    return matches[0]


def _find_consumer_by_name(
    client: AgentkitModelGatewayClient,
    model_gateway_id: str,
    name: str,
) -> mgw.ConsumersForModelGateway:
    resp = client.list_model_gateway_consumers(
        mgw.ListModelGatewayConsumersRequest(
            model_gateway_id=model_gateway_id,
            consumer_name=name,
            page_number=1,
            page_size=100,
        )
    )
    matches = [c for c in resp.consumers or [] if c.consumer_name == name]
    if len(matches) != 1 or not matches[0].consumer_id:
        raise typer.BadParameter(f"Consumer not found or ambiguous: {name}")
    return matches[0]


def _build_token_rate_limit_config(
    tpm: Optional[int],
    tpd: Optional[int],
) -> Optional[mgw.TokenRateLimitConfigForModelGateway]:
    rules = []
    if tpm is not None:
        rules.append(mgw.TokenRateLimitRulesForModelGateway(time_window=60, value=tpm))
    if tpd is not None:
        rules.append(
            mgw.TokenRateLimitRulesForModelGateway(time_window=86400, value=tpd)
        )
    if not rules:
        return None
    return mgw.TokenRateLimitConfigForModelGateway(enable=True, rules=rules)


def _build_authz_config(
    client: AgentkitModelGatewayClient,
    model_gateway_id: str,
    allow_models: Optional[List[str]],
) -> Optional[mgw.AuthzConfigForModelGateway]:
    if not allow_models:
        return None

    grouped: dict[str, list[str]] = {}
    allow_all_provider_ids: set[str] = set()
    for item in allow_models:
        if "/" not in item:
            provider_name = _require_value("--allow-model provider name", item)
            provider = _find_provider_by_name(client, model_gateway_id, provider_name)
            allow_all_provider_ids.add(provider.provider_id or "")
            grouped.pop(provider.provider_id or "", None)
            continue
        provider_name, model_name = item.split("/", 1)
        provider_name = _require_value("--allow-model provider name", provider_name)
        model_name = _require_value("--allow-model model name", model_name)
        provider_item = _find_provider_by_name(client, model_gateway_id, provider_name)
        provider_resp = client.get_model_gateway_provider(
            mgw.GetModelGatewayProviderRequest(provider_id=provider_item.provider_id)
        )
        provider = provider_resp.provider or provider_item
        provider_id = provider.provider_id or ""
        provider_model_id = ""
        for model in provider.provider_models or []:
            if model.model_name == model_name:
                provider_model_id = model.provider_model_id or ""
                break
        if not provider_model_id:
            raise typer.BadParameter(
                f"Model not found or has no ID for provider '{provider_name}': "
                f"{model_name}"
            )
        if provider_id not in allow_all_provider_ids:
            grouped.setdefault(provider_id, []).append(provider_model_id)

    provider_authz_configs = [
        mgw.ProviderAuthzConfigsForModelGateway(
            provider_id=provider_id,
            allow_all_provider_models=True,
        )
        for provider_id in allow_all_provider_ids
    ]
    provider_authz_configs.extend(
        mgw.ProviderAuthzConfigsForModelGateway(
            provider_id=provider_id,
            allow_all_provider_models=False,
            allowed_provider_model_ids=models,
        )
        for provider_id, models in grouped.items()
    )

    return mgw.AuthzConfigForModelGateway(
        allow_all_providers=False,
        provider_authz_configs=provider_authz_configs,
    )


@model_gateway_app.command("show-example")
def show_example_command(
    provider: str = typer.Option(..., "--provider", help="Provider name"),
    consumer: str = typer.Option(..., "--consumer", help="Consumer name"),
    example: ModelGatewayExampleType = typer.Option(
        ModelGatewayExampleType.curl,
        "--example",
        help="Example type: curl, openai, anthropic, or agentkit",
    ),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Show an example for calling the model gateway."""
    provider = _require_value("--provider", provider)
    consumer = _require_value("--consumer", consumer)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        provider_item = _find_provider_by_name(client, gateway_id, provider)
        provider_resp = client.get_model_gateway_provider(
            mgw.GetModelGatewayProviderRequest(provider_id=provider_item.provider_id)
        )
        consumer_item = _find_consumer_by_name(client, gateway_id, consumer)
        consumer_resp = client.get_model_gateway_consumer(
            mgw.GetModelGatewayConsumerRequest(consumer_id=consumer_item.consumer_id)
        )

        if not provider_resp.provider:
            raise typer.BadParameter(f"Provider not found: {provider}")
        if not consumer_resp.consumer:
            raise typer.BadParameter(f"Consumer not found: {consumer}")

        access_url = provider_resp.provider.base_url or ""
        if not access_url:
            raise typer.BadParameter(f"Provider has no Access URL: {provider}")

        api_keys = consumer_resp.consumer.api_keys or []
        api_key = api_keys[0] if api_keys else ""
        if not api_key:
            raise typer.BadParameter(f"Consumer has no API key: {consumer}")

        protocols = provider_resp.provider.protocols or []
        protocol = protocols[0] if protocols else "OpenAICompatible"
        if protocol == "OpenAICompatible":
            path = "/chat/completions"
        elif protocol == "AnthropicCompatible":
            path = "/messages"
        else:
            raise typer.BadParameter(f"Unsupported provider protocol: {protocol}")

        provider_models = [
            (item.provider_model_id or "", item.model_name)
            for item in provider_resp.provider.provider_models or []
            if item.model_name
        ]
        if not provider_models:
            raise typer.BadParameter(f"Provider has no model: {provider}")

        provider_id = provider_resp.provider.provider_id or provider_item.provider_id
        authz_config = consumer_resp.consumer.authz_config
        accessible_models: List[str] = []
        if authz_config and authz_config.allow_all_providers:
            accessible_models = [model_name for _, model_name in provider_models]
        elif authz_config and authz_config.provider_authz_configs:
            allow_all_models = False
            allowed_model_ids: set[str] = set()
            for config in authz_config.provider_authz_configs:
                if config.provider_id != provider_id:
                    continue
                if config.allow_all_provider_models:
                    allow_all_models = True
                    break
                allowed_model_ids.update(config.allowed_provider_model_ids or [])
            if allow_all_models:
                accessible_models = [model_name for _, model_name in provider_models]
            else:
                accessible_models = [
                    model_name
                    for model_id, model_name in provider_models
                    if model_id in allowed_model_ids
                ]
        if not accessible_models:
            console.print(
                Panel.fit(
                    f"No accessible model for consumer '{consumer}' "
                    f"on provider '{provider}'.",
                    title="ShowModelGatewayExample Warning",
                    border_style="yellow",
                )
            )
            return
        model = accessible_models[0]

        if example == ModelGatewayExampleType.curl:
            typer.echo(
                f'curl "{access_url}{path}" \\\n'
                '  -H "Content-Type: application/json" \\\n'
                f'  -H "Authorization: Bearer {api_key}" \\\n'
                "  -d '{\n"
                f'    "model": "{model}",\n'
                '    "messages": [\n'
                "      {\n"
                '        "role": "user",\n'
                '        "content": "Hello, world"\n'
                "      }\n"
                "    ]\n"
                "  }'"
            )
        elif example == ModelGatewayExampleType.openai:
            if protocol != "OpenAICompatible":
                raise typer.BadParameter(
                    f"OpenAI example requires OpenAI-Compatible protocol: {protocol}"
                )
            typer.echo(
                "from openai import OpenAI\n\n"
                "client = OpenAI(\n"
                f'    api_key="{api_key}",\n'
                f'    base_url="{access_url}",\n'
                ")\n\n"
                "completion = client.chat.completions.create(\n"
                f'    model="{model}",\n'
                "    messages=[\n"
                "        {\n"
                '            "role": "user",\n'
                '            "content": "你是谁？",\n'
                "        }\n"
                "    ],\n"
                ")\n\n"
                "print(completion.choices[0].message)"
            )
        elif example == ModelGatewayExampleType.anthropic:
            if protocol != "AnthropicCompatible":
                raise typer.BadParameter(
                    f"Anthropic example requires Anthropic-Compatible protocol: {protocol}"
                )
            typer.echo(
                "from anthropic import Anthropic\n\n"
                "client = Anthropic(\n"
                f'    api_key="{api_key}",\n'
                f'    base_url="{access_url}",\n'
                ")\n\n"
                "for message in client.messages.create(\n"
                "    max_tokens=1024,\n"
                "    messages=[\n"
                "        {\n"
                '            "role": "user",\n'
                '            "content": "Hello, world",\n'
                "        }\n"
                "    ],\n"
                f'    model="{model}",\n'
                "):\n"
                "    print(message)"
            )
        elif example == ModelGatewayExampleType.agentkit:
            if protocol != "OpenAICompatible":
                raise typer.BadParameter(
                    f"AgentKit example requires OpenAI-Compatible protocol: {protocol}"
                )
            typer.echo(
                "agentkit config \n"
                f"  -e MODEL_AGENT_NAME={model} \\\n"
                f"  -e MODEL_AGENT_API_BASE={access_url} \\\n"
                f"  -e MODEL_AGENT_API_KEY={api_key}"
            )
    except Exception as e:
        _print_api_error("ShowModelGatewayExample", e)
        raise typer.Exit(1)


@model_gateway_app.command("activate")
def activate_command(
    apig_gateway_id: Optional[str] = typer.Option(
        None, "--apig-gateway-id", help="API Gateway instance ID"
    ),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Activate the model gateway."""
    if apig_gateway_id is not None:
        apig_gateway_id = _require_value("--apig-gateway-id", apig_gateway_id)
    try:
        client = _client(region)
        existing = client.list_model_gateways(
            mgw.ListModelGatewaysRequest(page_number=1, page_size=100)
        )
        gateways = existing.model_gateways or []
        if gateways and gateways[0].model_gateway_id:
            gateway = gateways[0]
            status = gateway.status or "Unknown"
            title = "ModelGateway Already Exists"
            border_style = "green"
            state = "[green]Already exists[/green]"
            if status != MODEL_GATEWAY_RUNNING_STATUS:
                border_style = (
                    "red" if status in MODEL_GATEWAY_ERROR_STATUSES else "yellow"
                )
                state = (
                    "[red]Already exists with error status[/red]"
                    if status in MODEL_GATEWAY_ERROR_STATUSES
                    else "[yellow]Already exists but not Running[/yellow]"
                )
            lines = [
                state,
                f"ModelGatewayId: {gateway.model_gateway_id}",
                f"Status: {status}",
            ]
            if gateway.message:
                lines.append(f"Message: {gateway.message}")
            console.print(
                Panel.fit(
                    "\n".join(lines),
                    title=title,
                    border_style=border_style,
                )
            )
            if status in MODEL_GATEWAY_ERROR_STATUSES:
                raise typer.Exit(1)
            return

        resp = client.create_model_gateway(
            mgw.CreateModelGatewayRequest(
                type="Standard" if apig_gateway_id else "Shared",
                apig_gateway_id=apig_gateway_id,
                consumer=mgw.ConsumerForCreateModelGateway(consumer_name="default"),
            )
        )
        if resp.model_gateway_id:
            _wait_model_gateway_running(
                client,
                resp.model_gateway_id,
                "CreateModelGateway",
            )
        console.print(
            Panel.fit(
                "[green]Activated[/green]\n" f"ModelGatewayId: {resp.model_gateway_id}",
                title="CreateModelGateway",
                border_style="green",
            )
        )
    except typer.Exit:
        raise
    except Exception as e:
        _print_api_error("CreateModelGateway", e)
        raise typer.Exit(1)


@provider_app.command("add")
def provider_add_command(
    name: str = typer.Option(..., "--name", help="Provider name"),
    base_url: str = typer.Option(..., "--base-url", help="Provider base URL"),
    api_keys: List[str] = typer.Option(..., "--api-key", help="API key, repeatable"),
    models: List[str] = typer.Option(..., "--model", help="Model name, repeatable"),
    protocol: List[str] = typer.Option(
        ["openai"], "--protocol", help="openai or anthropic, exactly once"
    ),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Add a provider."""
    name = _require_value("--name", name)
    base_url = _require_value("--base-url", base_url)
    api_keys = _require_values("--api-key", api_keys)
    models = _require_values("--model", models)
    protocol = _require_single_protocol(protocol)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        resp = client.create_model_gateway_provider(
            mgw.CreateModelGatewayProviderRequest(
                model_gateway_id=gateway_id,
                provider_type="Custom",
                provider_name=name,
                protocols=[_normalize_protocol(p) for p in protocol],
                provider_source="Domain",
                provider_spec=mgw.ProviderSpecForModelGateway(base_url=base_url),
                credentials=_build_credentials(api_keys),
                provider_models=_provider_models(models),
            )
        )
        _wait_model_gateway_running(client, gateway_id, "CreateModelGatewayProvider")
        console.print(
            Panel.fit(
                f"[green]Added[/green]\nProviderId: {resp.provider_id}",
                title="CreateModelGatewayProvider",
                border_style="green",
            )
        )
    except Exception as e:
        _print_api_error("CreateModelGatewayProvider", e)
        raise typer.Exit(1)


@provider_app.command("list")
def provider_list_command(
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """List providers."""
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        resp = client.list_model_gateway_providers(
            mgw.ListModelGatewayProvidersRequest(
                model_gateway_id=gateway_id,
                page_number=1,
                page_size=100,
            )
        )
        console.print(_provider_table(resp.providers or []))
    except Exception as e:
        _print_api_error("ListModelGatewayProviders", e)
        raise typer.Exit(1)


@provider_app.command("show")
def provider_show_command(
    name: str = typer.Option(..., "--name", help="Provider name"),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Show a provider by name."""
    name = _require_value("--name", name)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        provider = _find_provider_by_name(client, gateway_id, name)
        resp = client.get_model_gateway_provider(
            mgw.GetModelGatewayProviderRequest(provider_id=provider.provider_id)
        )
        if resp.provider:
            _provider_show(resp.provider)
    except Exception as e:
        _print_api_error("GetModelGatewayProvider", e)
        raise typer.Exit(1)


@provider_app.command("update")
def provider_update_command(
    name: str = typer.Option(..., "--name", help="Provider name"),
    base_url: Optional[str] = typer.Option(
        None, "--base-url", help="Provider base URL"
    ),
    api_keys: Optional[List[str]] = typer.Option(
        None, "--api-key", help="API key, repeatable"
    ),
    models: Optional[List[str]] = typer.Option(
        None, "--model", help="Model name, repeatable"
    ),
    protocol: Optional[List[str]] = typer.Option(
        None, "--protocol", help="openai or anthropic, repeatable"
    ),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Update a provider by name."""
    name = _require_value("--name", name)
    if base_url is not None:
        base_url = _require_value("--base-url", base_url)
    if api_keys is not None:
        api_keys = _require_values("--api-key", api_keys)
    if models is not None:
        models = _require_values("--model", models)
    if protocol:
        protocol = _require_single_protocol(protocol)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        provider = _find_provider_by_name(client, gateway_id, name)
        request_kwargs = {}
        if protocol:
            request_kwargs["protocols"] = [_normalize_protocol(p) for p in protocol]
        if base_url is not None:
            request_kwargs["provider_source"] = "Domain"
            request_kwargs["provider_spec"] = mgw.ProviderSpecForModelGateway(
                base_url=base_url
            )
        if api_keys is not None:
            request_kwargs["credentials"] = _build_credentials(api_keys)
        if models is not None:
            provider_resp = client.get_model_gateway_provider(
                mgw.GetModelGatewayProviderRequest(provider_id=provider.provider_id)
            )
            current_provider = provider_resp.provider or provider
            provider_models = []
            existing_models = {
                item.model_name: item
                for item in current_provider.provider_models or []
                if item.model_name
            }
            for model_name in models:
                existing_model = existing_models.get(model_name)
                if not existing_model:
                    provider_models.append(
                        mgw.ProviderModelsForModelGateway(model_name=model_name)
                    )
                    continue
                if not existing_model.provider_model_id:
                    raise typer.BadParameter(
                        f"Existing provider model has no ID: {model_name}"
                    )
                provider_models.append(
                    mgw.ProviderModelsForModelGateway(
                        provider_model_id=existing_model.provider_model_id,
                        model_name=model_name,
                    )
                )
            request_kwargs["provider_models"] = provider_models
        resp = client.update_model_gateway_provider(
            mgw.UpdateModelGatewayProviderRequest(
                provider_id=provider.provider_id,
                **request_kwargs,
            )
        )
        _wait_model_gateway_running(client, gateway_id, "UpdateModelGatewayProvider")
        console.print(
            Panel.fit(
                f"[green]Updated[/green]\nProviderId: {resp.provider_id}",
                title="UpdateModelGatewayProvider",
                border_style="green",
            )
        )
    except Exception as e:
        _print_api_error("UpdateModelGatewayProvider", e)
        raise typer.Exit(1)


@provider_app.command("delete")
def provider_delete_command(
    name: str = typer.Option(..., "--name", help="Provider name"),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Delete a provider by name."""
    name = _require_value("--name", name)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        provider = _find_provider_by_name(client, gateway_id, name)
        client.delete_model_gateway_provider(
            mgw.DeleteModelGatewayProviderRequest(provider_id=provider.provider_id)
        )
        _wait_model_gateway_running(client, gateway_id, "DeleteModelGatewayProvider")
        console.print(
            Panel.fit("[green]Deleted[/green]", title="DeleteModelGatewayProvider")
        )
    except Exception as e:
        _print_api_error("DeleteModelGatewayProvider", e)
        raise typer.Exit(1)


@consumer_app.command("add")
def consumer_add_command(
    name: str = typer.Option(..., "--name", help="Consumer name"),
    allow_models: Optional[List[str]] = typer.Option(
        None,
        "--allow-model",
        help="provider-name or provider-name/model-name, repeatable",
    ),
    tpm: Optional[int] = typer.Option(None, "--tpm", help="Tokens per minute"),
    tpd: Optional[int] = typer.Option(None, "--tpd", help="Tokens per day"),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Add a consumer."""
    name = _require_value("--name", name)
    allow_models = _require_allow_models(allow_models)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        resp = client.create_model_gateway_consumer(
            mgw.CreateModelGatewayConsumerRequest(
                consumer_name=name,
                model_gateway_id=gateway_id,
                authz_config=_build_authz_config(client, gateway_id, allow_models),
                token_rate_limit_config=_build_token_rate_limit_config(tpm, tpd),
            )
        )
        _wait_model_gateway_running(client, gateway_id, "CreateModelGatewayConsumer")
        console.print(
            Panel.fit(
                f"[green]Added[/green]\nConsumerId: {resp.consumer_id}",
                title="CreateModelGatewayConsumer",
                border_style="green",
            )
        )
    except Exception as e:
        _print_api_error("CreateModelGatewayConsumer", e)
        raise typer.Exit(1)


@consumer_app.command("list")
def consumer_list_command(
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """List consumers."""
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        resp = client.list_model_gateway_consumers(
            mgw.ListModelGatewayConsumersRequest(
                model_gateway_id=gateway_id,
                page_number=1,
                page_size=100,
            )
        )
        provider_names_by_id, provider_model_names_by_id = _provider_authz_display_maps(
            client,
            gateway_id,
        )
        console.print(
            _consumer_table(
                resp.consumers or [],
                provider_names_by_id,
                provider_model_names_by_id,
            )
        )
    except Exception as e:
        _print_api_error("ListModelGatewayConsumers", e)
        raise typer.Exit(1)


@consumer_app.command("show")
def consumer_show_command(
    name: str = typer.Option(..., "--name", help="Consumer name"),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Show a consumer by name."""
    name = _require_value("--name", name)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        consumer = _find_consumer_by_name(client, gateway_id, name)
        resp = client.get_model_gateway_consumer(
            mgw.GetModelGatewayConsumerRequest(consumer_id=consumer.consumer_id)
        )
        if resp.consumer:
            (
                provider_names_by_id,
                provider_model_names_by_id,
            ) = _provider_authz_display_maps(client, gateway_id)
            _consumer_show(
                resp.consumer,
                provider_names_by_id,
                provider_model_names_by_id,
            )
    except Exception as e:
        _print_api_error("GetModelGatewayConsumer", e)
        raise typer.Exit(1)


@consumer_app.command("update")
def consumer_update_command(
    name: str = typer.Option(..., "--name", help="Consumer name"),
    allow_models: Optional[List[str]] = typer.Option(
        None,
        "--allow-model",
        help="provider-name or provider-name/model-name, repeatable",
    ),
    tpm: Optional[int] = typer.Option(None, "--tpm", help="Tokens per minute"),
    tpd: Optional[int] = typer.Option(None, "--tpd", help="Tokens per day"),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Update a consumer by name."""
    name = _require_value("--name", name)
    allow_models = _require_allow_models(allow_models)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        consumer = _find_consumer_by_name(client, gateway_id, name)
        request_kwargs = {}
        if allow_models is not None:
            request_kwargs["authz_config"] = _build_authz_config(
                client, gateway_id, allow_models
            )
        if tpm is not None or tpd is not None:
            request_kwargs["token_rate_limit_config"] = _build_token_rate_limit_config(
                tpm, tpd
            )
        resp = client.update_model_gateway_consumer(
            mgw.UpdateModelGatewayConsumerRequest(
                consumer_id=consumer.consumer_id,
                **request_kwargs,
            )
        )
        _wait_model_gateway_running(client, gateway_id, "UpdateModelGatewayConsumer")
        console.print(
            Panel.fit(
                f"[green]Updated[/green]\nConsumerId: {resp.consumer_id}",
                title="UpdateModelGatewayConsumer",
                border_style="green",
            )
        )
    except Exception as e:
        _print_api_error("UpdateModelGatewayConsumer", e)
        raise typer.Exit(1)


@consumer_app.command("delete")
def consumer_delete_command(
    name: str = typer.Option(..., "--name", help="Consumer name"),
    region: Optional[str] = typer.Option(None, "--region", help="Region override"),
):
    """Delete a consumer by name."""
    name = _require_value("--name", name)
    try:
        client = _client(region)
        gateway_id = _resolve_model_gateway_id(client)
        consumer = _find_consumer_by_name(client, gateway_id, name)
        client.delete_model_gateway_consumer(
            mgw.DeleteModelGatewayConsumerRequest(consumer_id=consumer.consumer_id)
        )
        _wait_model_gateway_running(client, gateway_id, "DeleteModelGatewayConsumer")
        console.print(
            Panel.fit("[green]Deleted[/green]", title="DeleteModelGatewayConsumer")
        )
    except Exception as e:
        _print_api_error("DeleteModelGatewayConsumer", e)
        raise typer.Exit(1)


model_gateway_app.add_typer(provider_app, name="provider")
model_gateway_app.add_typer(consumer_app, name="consumer")
