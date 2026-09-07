"""Target model replacement helpers for migrated AgentKit apps."""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)
ARK_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
VEADK_SOURCE_HEADER = "veadk-source"
VEADK_SOURCE_VALUE = "veadk"
_DISABLED_VALUES = {"0", "false", "off", "none", "disabled"}
_HEADER_PATCH_MARKER = "__agentkit_veadk_source_header__"
_MODEL_PARAM_KEYS = {
    "frequency_penalty",
    "max_tokens",
    "presence_penalty",
    "stop",
    "temperature",
    "top_p",
}
_MODEL_ID_ALIAS_ENV_KEYS = (
    "BEDROCK_MODEL_ID",
    "DEFAULT_MODEL",
    "MODEL_ID",
    "MODEL_NAME",
)
_BASE_URL_ALIAS_ENV_KEYS = (
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
)
_API_KEY_ALIAS_ENV_KEYS = ("OPENAI_API_KEY",)


def _target_model_id() -> str:
    return os.getenv("ARK_MODEL_ID") or ""


def _target_api_key() -> str:
    return os.getenv("ARK_API_KEY") or ""


def _target_base_url() -> str:
    return os.getenv("ARK_BASE_URL") or ARK_DEFAULT_BASE_URL


def _replacement_enabled() -> bool:
    value = os.getenv("ARK_MODEL_REPLACEMENT", "ark").strip().lower()
    return value not in _DISABLED_VALUES


def _merge_veadk_source_header(headers: Any = None) -> dict[str, Any]:
    merged = {
        key: value
        for key, value in dict(headers or {}).items()
        if key.lower() != VEADK_SOURCE_HEADER
    }
    merged[VEADK_SOURCE_HEADER] = VEADK_SOURCE_VALUE
    return merged


def _header_kwarg_model_cls(base_cls: type[Any], header_kwarg: str) -> type[Any]:
    if getattr(base_cls, _HEADER_PATCH_MARKER, False):
        return base_cls

    class AgentKitHeaderModel(base_cls):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs[header_kwarg] = _merge_veadk_source_header(kwargs.get(header_kwarg))
            super().__init__(*args, **kwargs)

    AgentKitHeaderModel.__name__ = base_cls.__name__
    AgentKitHeaderModel.__qualname__ = base_cls.__qualname__
    AgentKitHeaderModel.__module__ = base_cls.__module__
    setattr(AgentKitHeaderModel, _HEADER_PATCH_MARKER, True)
    return AgentKitHeaderModel


def _openai_client_args_model_cls(base_cls: type[Any]) -> type[Any]:
    if getattr(base_cls, _HEADER_PATCH_MARKER, False):
        return base_cls

    class AgentKitHeaderModel(base_cls):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if args or kwargs.get("client") is not None:
                super().__init__(*args, **kwargs)
                return
            client_args = dict(kwargs.get("client_args") or {})
            client_args["default_headers"] = _merge_veadk_source_header(
                client_args.get("default_headers")
            )
            kwargs["client_args"] = client_args
            super().__init__(*args, **kwargs)

    AgentKitHeaderModel.__name__ = base_cls.__name__
    AgentKitHeaderModel.__qualname__ = base_cls.__qualname__
    AgentKitHeaderModel.__module__ = base_cls.__module__
    setattr(AgentKitHeaderModel, _HEADER_PATCH_MARKER, True)
    return AgentKitHeaderModel


def _replacement_model_config(config: dict[str, Any]) -> dict[str, Any]:
    model_id = _target_model_id()
    if not model_id:
        raise RuntimeError(
            "AgentKit model replacement is enabled, but no target model was "
            "configured. Set ARK_MODEL_ID."
        )

    params = dict(config.get("params") or {})
    for key in _MODEL_PARAM_KEYS:
        if key in config and config[key] is not None:
            params.setdefault(key, config[key])

    replacement: dict[str, Any] = {"model_id": model_id}
    if params:
        replacement["params"] = params
    if "context_window_limit" in config:
        replacement["context_window_limit"] = config["context_window_limit"]
    if "stream" in config:
        replacement["stream"] = config["stream"]
    return replacement


def _agentkit_openai_model_cls() -> type[Any]:
    from strands.models.openai import OpenAIModel

    class AgentKitOpenAIModel(OpenAIModel):
        """OpenAI-compatible Strands model backed by the AgentKit target model."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args
            api_key = _target_api_key()
            if not api_key:
                raise RuntimeError(
                    "AgentKit model replacement is enabled, but no API key was "
                    "configured. Set ARK_API_KEY."
                )
            super().__init__(
                client_args={
                    "base_url": _target_base_url(),
                    "api_key": api_key,
                    "default_headers": _merge_veadk_source_header(),
                },
                **_replacement_model_config(kwargs),
            )

    AgentKitOpenAIModel.__name__ = "AgentKitOpenAIModel"
    return AgentKitOpenAIModel


def _patch_model_attr(module_name: str, attr: str, replacement: type[Any]) -> bool:
    try:
        module = importlib.import_module(module_name)
    except Exception:  # noqa: BLE001 - optional framework imports are best effort
        return False
    if hasattr(module, attr):
        setattr(module, attr, replacement)
        return True
    return False


def _patch_langchain_model_headers() -> bool:
    try:
        module = importlib.import_module("langchain_openai.chat_models.base")
        replacement = _header_kwarg_model_cls(module.ChatOpenAI, "default_headers")
    except Exception:  # noqa: BLE001 - optional framework imports are best effort
        return False

    patched = False
    for module_name in (
        "langchain_openai",
        "langchain_openai.chat_models",
        "langchain_openai.chat_models.base",
    ):
        patched = _patch_model_attr(module_name, "ChatOpenAI", replacement) or patched
    return patched


def _patch_adk_model_headers() -> bool:
    try:
        module = importlib.import_module("google.adk.models.lite_llm")
        replacement = _header_kwarg_model_cls(module.LiteLlm, "extra_headers")
    except Exception:  # noqa: BLE001 - optional framework imports are best effort
        return False

    patched = False
    for module_name in ("google.adk.models", "google.adk.models.lite_llm"):
        patched = _patch_model_attr(module_name, "LiteLlm", replacement) or patched
    return patched


def _patch_strands_openai_model_headers() -> bool:
    try:
        module = importlib.import_module("strands.models.openai")
        replacement = _openai_client_args_model_cls(module.OpenAIModel)
    except Exception:  # noqa: BLE001 - optional framework imports are best effort
        return False

    patched = False
    for module_name in ("strands.models", "strands.models.openai"):
        patched = _patch_model_attr(module_name, "OpenAIModel", replacement) or patched
    return patched


def _apply_env_aliases() -> bool:
    changed = False
    model_id = _target_model_id()
    if not model_id:
        return False

    for key in _MODEL_ID_ALIAS_ENV_KEYS:
        if key not in os.environ:
            os.environ[key] = model_id
            changed = True

    base_url = _target_base_url()
    for key in _BASE_URL_ALIAS_ENV_KEYS:
        if key not in os.environ:
            os.environ[key] = base_url
            changed = True

    api_key = _target_api_key()
    if api_key:
        for key in _API_KEY_ALIAS_ENV_KEYS:
            if key not in os.environ:
                os.environ[key] = api_key
                changed = True
    return changed


def _patch_strands_model_classes() -> bool:
    try:
        replacement = _agentkit_openai_model_cls()
    except Exception:  # noqa: BLE001 - optional framework imports are best effort
        return False

    patched = False
    for module_name, attr in (
        ("strands.models", "BedrockModel"),
        ("strands.models.bedrock", "BedrockModel"),
        ("strands.models.anthropic", "AnthropicModel"),
    ):
        patched = _patch_model_attr(module_name, attr, replacement) or patched
    return patched


def apply_agentkit_model_replacement() -> bool:
    """Apply explicit target-model replacement for generated migration wrappers.

    The helper intentionally stays low-intrusion: it normalizes common model
    environment variables and patches stable framework model constructors before
    user code constructs them. It does not rewrite project source code or patch
    global HTTP/OpenAI clients.
    """

    if not _replacement_enabled():
        logger.info("AgentKit model replacement disabled by ARK_MODEL_REPLACEMENT.")
        return False
    env_changed = _apply_env_aliases()
    langchain_headers_patched = _patch_langchain_model_headers()
    adk_headers_patched = _patch_adk_model_headers()
    strands_headers_patched = _patch_strands_openai_model_headers()
    patched = _patch_strands_model_classes()
    logger.info(
        "AgentKit model replacement enabled: env_aliases=%s langchain_headers=%s adk_headers=%s strands_headers=%s strands_model_patch=%s target_model_configured=%s base_url_configured=%s",
        env_changed,
        langchain_headers_patched,
        adk_headers_patched,
        strands_headers_patched,
        patched,
        bool(_target_model_id()),
        bool(_target_base_url()),
    )
    return (
        env_changed
        or langchain_headers_patched
        or adk_headers_patched
        or strands_headers_patched
        or patched
    )
