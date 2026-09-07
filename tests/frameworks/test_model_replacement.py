import logging
import os
import sys
from types import ModuleType

import pytest

from agentkit.frameworks import model_replacement as module
from agentkit.frameworks.model_replacement import (
    ARK_DEFAULT_BASE_URL,
    apply_agentkit_model_replacement,
)

_MODEL_ENV_KEYS = (
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "ARK_MODEL_ID",
    "ARK_MODEL_REPLACEMENT",
    "BEDROCK_MODEL_ID",
    "DEFAULT_MODEL",
    "MODEL_ID",
    "MODEL_NAME",
    "OPENAI_API_BASE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)


@pytest.fixture(autouse=True)
def _restore_model_environment():
    original = {key: os.environ[key] for key in _MODEL_ENV_KEYS if key in os.environ}
    for key in _MODEL_ENV_KEYS:
        os.environ.pop(key, None)
    yield
    for key in _MODEL_ENV_KEYS:
        os.environ.pop(key, None)
    os.environ.update(original)


def _install_fake_strands(monkeypatch):
    strands = ModuleType("strands")
    models = ModuleType("strands.models")
    openai = ModuleType("strands.models.openai")
    bedrock = ModuleType("strands.models.bedrock")
    anthropic = ModuleType("strands.models.anthropic")

    class OpenAIModel:
        def __init__(self, client=None, client_args=None, **config):
            if client is not None and client_args is not None:
                raise ValueError("client and client_args are mutually exclusive")
            self.client = client
            self.client_args = client_args
            self.config = config

    class BedrockModel:
        pass

    class AnthropicModel:
        pass

    openai.OpenAIModel = OpenAIModel
    models.OpenAIModel = OpenAIModel
    models.BedrockModel = BedrockModel
    bedrock.BedrockModel = BedrockModel
    anthropic.AnthropicModel = AnthropicModel
    strands.models = models
    models.openai = openai
    models.bedrock = bedrock
    models.anthropic = anthropic

    for fake_module in (strands, models, openai, bedrock, anthropic):
        monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)
    return models, bedrock, anthropic


def _install_fake_langchain(monkeypatch):
    langchain_openai = ModuleType("langchain_openai")
    chat_models = ModuleType("langchain_openai.chat_models")
    base = ModuleType("langchain_openai.chat_models.base")

    class ChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    langchain_openai.ChatOpenAI = ChatOpenAI
    chat_models.ChatOpenAI = ChatOpenAI
    base.ChatOpenAI = ChatOpenAI
    langchain_openai.chat_models = chat_models
    chat_models.base = base

    for fake_module in (langchain_openai, chat_models, base):
        monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)
    return langchain_openai


def _install_fake_adk(monkeypatch):
    google = ModuleType("google")
    adk = ModuleType("google.adk")
    models = ModuleType("google.adk.models")
    lite_llm = ModuleType("google.adk.models.lite_llm")

    class LiteLlm:
        def __init__(self, model, **kwargs):
            self.model = model
            self.kwargs = kwargs

    models.LiteLlm = LiteLlm
    lite_llm.LiteLlm = LiteLlm
    google.adk = adk
    adk.models = models
    models.lite_llm = lite_llm

    for fake_module in (google, adk, models, lite_llm):
        monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)
    return models


@pytest.mark.parametrize(
    ("framework", "model_kind"),
    (
        ("langchain", "langchain"),
        ("langgraph", "langchain"),
        ("adk", "adk"),
        ("strands", "strands"),
        ("agentcore", "agentcore"),
    ),
)
def test_structured_migration_model_routes_inject_required_veadk_header(
    monkeypatch, framework, model_kind
):
    langchain = _install_fake_langchain(monkeypatch)
    adk_models = _install_fake_adk(monkeypatch)
    strands_models, _, _ = _install_fake_strands(monkeypatch)
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-test-model")

    assert apply_agentkit_model_replacement() is True

    existing_headers = {
        "x-user-header": "preserved",
        "VEADK-SOURCE": "user-value",
    }
    if model_kind == "langchain":
        model = langchain.ChatOpenAI(default_headers=existing_headers)
        headers = model.kwargs["default_headers"]
    elif model_kind == "adk":
        model = adk_models.LiteLlm(
            model="openai/doubao-test-model", extra_headers=existing_headers
        )
        headers = model.kwargs["extra_headers"]
    elif model_kind == "strands":
        model = strands_models.OpenAIModel(
            client_args={
                "timeout": 30,
                "default_headers": existing_headers,
            }
        )
        assert model.client_args["timeout"] == 30
        headers = model.client_args["default_headers"]
    else:
        model = strands_models.BedrockModel(model_id="anthropic.claude")
        headers = model.client_args["default_headers"]

    assert (
        model_kind
        == {
            "langchain": "langchain",
            "langgraph": "langchain",
            "adk": "adk",
            "strands": "strands",
            "agentcore": "agentcore",
        }[framework]
    )
    expected_headers = {
        "x-user-header": "preserved",
        "veadk-source": "veadk",
    }
    if model_kind == "agentcore":
        expected_headers = {"veadk-source": "veadk"}
    assert headers == expected_headers
    assert existing_headers == {
        "x-user-header": "preserved",
        "VEADK-SOURCE": "user-value",
    }


def test_framework_header_patches_are_idempotent(monkeypatch):
    langchain = _install_fake_langchain(monkeypatch)
    adk_models = _install_fake_adk(monkeypatch)
    strands_models, _, _ = _install_fake_strands(monkeypatch)
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-test-model")

    assert apply_agentkit_model_replacement() is True
    patched_classes = (
        langchain.ChatOpenAI,
        adk_models.LiteLlm,
        strands_models.OpenAIModel,
    )

    assert apply_agentkit_model_replacement() is True
    assert (
        langchain.ChatOpenAI,
        adk_models.LiteLlm,
        strands_models.OpenAIModel,
    ) == patched_classes


@pytest.mark.parametrize("positional", (False, True))
def test_strands_preconfigured_client_remains_compatible(monkeypatch, positional):
    strands_models, _, _ = _install_fake_strands(monkeypatch)
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-test-model")

    assert apply_agentkit_model_replacement() is True
    client = object()
    if positional:
        model = strands_models.OpenAIModel(client)
    else:
        model = strands_models.OpenAIModel(client=client)

    assert model.client is client
    assert model.client_args is None


@pytest.mark.parametrize(
    ("patcher", "unavailable_module"),
    (
        (module._patch_langchain_model_headers, "langchain_openai.chat_models.base"),
        (module._patch_adk_model_headers, "google.adk.models.lite_llm"),
        (module._patch_strands_openai_model_headers, "strands.models.openai"),
    ),
)
def test_header_patchers_tolerate_unavailable_optional_frameworks(
    monkeypatch, patcher, unavailable_module
):
    import_module = module.importlib.import_module

    def unavailable(name):
        if name == unavailable_module:
            raise ImportError(name)
        return import_module(name)

    monkeypatch.setattr(module.importlib, "import_module", unavailable)

    assert patcher() is False


def test_model_replacement_sets_common_alias_envs_without_overwriting(monkeypatch):
    for key in (
        "BEDROCK_MODEL_ID",
        "MODEL_ID",
        "MODEL_NAME",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-target")
    monkeypatch.setenv("ARK_API_KEY", "ark-key")
    monkeypatch.setenv("ARK_BASE_URL", "https://ark.example/api/v3")
    monkeypatch.setenv("DEFAULT_MODEL", "existing-default")
    monkeypatch.setenv("OPENAI_API_KEY", "existing-openai-key")
    monkeypatch.setattr(module, "_patch_strands_model_classes", lambda: False)

    assert apply_agentkit_model_replacement() is True

    assert os.environ["BEDROCK_MODEL_ID"] == "doubao-target"
    assert os.environ["MODEL_ID"] == "doubao-target"
    assert os.environ["MODEL_NAME"] == "doubao-target"
    assert os.environ["DEFAULT_MODEL"] == "existing-default"
    assert os.environ["OPENAI_BASE_URL"] == "https://ark.example/api/v3"
    assert os.environ["OPENAI_API_BASE"] == "https://ark.example/api/v3"
    assert os.environ["OPENAI_API_KEY"] == "existing-openai-key"


def test_model_replacement_logs_startup_diagnostics_without_secrets(
    monkeypatch, caplog
):
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-target")
    monkeypatch.setenv("ARK_API_KEY", "secret-key")
    monkeypatch.setattr(module, "_patch_strands_model_classes", lambda: False)

    with caplog.at_level(logging.INFO, logger="agentkit.frameworks.model_replacement"):
        assert apply_agentkit_model_replacement() is True

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "AgentKit model replacement enabled" in messages
    assert "env_aliases=True" in messages
    assert "strands_model_patch=False" in messages
    assert "secret-key" not in messages


def test_model_replacement_patches_strands_bedrock_and_anthropic(monkeypatch):
    models, bedrock, anthropic = _install_fake_strands(monkeypatch)
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-test-model")

    assert apply_agentkit_model_replacement() is True

    model = models.BedrockModel(
        model_id="anthropic.claude",
        region_name="us-west-2",
        cache_prompt="default",
        max_tokens=128,
        context_window_limit=2048,
        stream=True,
    )

    assert type(model).__name__ == "AgentKitOpenAIModel"
    assert model.config["model_id"] == "doubao-test-model"
    assert model.config["params"] == {"max_tokens": 128}
    assert model.config["context_window_limit"] == 2048
    assert model.config["stream"] is True
    assert model.client_args == {
        "base_url": ARK_DEFAULT_BASE_URL,
        "api_key": "ark-test-key",
        "default_headers": {"veadk-source": "veadk"},
    }
    assert type(bedrock.BedrockModel()).__name__ == "AgentKitOpenAIModel"
    assert anthropic.AnthropicModel().config["model_id"] == "doubao-test-model"


def test_model_replacement_can_be_disabled(monkeypatch, caplog):
    monkeypatch.setenv("ARK_MODEL_REPLACEMENT", "off")
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-target")
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    with caplog.at_level(logging.INFO, logger="agentkit.frameworks.model_replacement"):
        assert apply_agentkit_model_replacement() is False

    assert "BEDROCK_MODEL_ID" not in os.environ
    assert "AgentKit model replacement disabled" in "\n".join(
        record.getMessage() for record in caplog.records
    )


def test_model_replacement_requires_ark_model_id_for_patched_strands(monkeypatch):
    models, _, _ = _install_fake_strands(monkeypatch)
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.delenv("ARK_MODEL_ID", raising=False)

    assert apply_agentkit_model_replacement() is True
    with pytest.raises(RuntimeError, match="ARK_MODEL_ID"):
        models.BedrockModel(model_id="anthropic.claude")


def test_model_replacement_requires_ark_api_key_for_patched_strands(monkeypatch):
    models, _, _ = _install_fake_strands(monkeypatch)
    monkeypatch.setenv("ARK_MODEL_ID", "doubao-test-model")
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    assert apply_agentkit_model_replacement() is True
    with pytest.raises(RuntimeError, match="ARK_API_KEY"):
        models.BedrockModel(model_id="anthropic.claude")


def test_model_replacement_returns_false_when_no_alias_or_supported_model_class(
    monkeypatch,
):
    monkeypatch.delenv("ARK_MODEL_ID", raising=False)
    monkeypatch.setattr(module, "_patch_langchain_model_headers", lambda: False)
    monkeypatch.setattr(module, "_patch_adk_model_headers", lambda: False)
    monkeypatch.setattr(module, "_patch_strands_openai_model_headers", lambda: False)
    monkeypatch.setattr(
        module,
        "_agentkit_openai_model_cls",
        lambda: (_ for _ in ()).throw(ImportError("missing strands")),
    )

    assert apply_agentkit_model_replacement() is False


def test_model_replacement_patch_attr_reports_missing_targets():
    assert module._patch_model_attr("json", "missing_attr", object) is False
    assert module._patch_model_attr("definitely_missing_module", "x", object) is False
