# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Cloud-Provider awareness of the auth ADMIN path (`agentkit auth admin sso-setup`).

Regression tests for Meego #7363652733: with CLOUD_PROVIDER=byteplus the admin
OpenApiClient must resolve BYTEPLUS_ACCESS_KEY / BYTEPLUS_SECRET_KEY (via the
SDK's unified credential chain) and sign against the BytePlus OpenAPI gateway,
instead of hardcoding the Volcengine env vars and host.
"""

from __future__ import annotations

import os

import pytest

from agentkit.auth._openapi import OpenApiClient
from agentkit.auth.errors import AuthError
from agentkit.platform.provider import CloudProvider


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """No ambient creds/provider/config: only what each test sets is visible."""
    for key in list(os.environ):
        if key.startswith(("VOLC", "BYTEPLUS")) or key in {
            "CLOUD_PROVIDER",
            "AGENTKIT_CLOUD_PROVIDER",
            "AGENTKIT_AUTH_PROFILE",
        }:
            monkeypatch.delenv(key)
    # Keep the cwd `.env` fallback out of the chain.
    monkeypatch.chdir(tmp_path)
    # Neutralize ~/.agentkit/config.yaml.
    monkeypatch.setattr(
        "agentkit.platform.configuration.read_global_config_dict", dict
    )
    monkeypatch.setattr(
        "agentkit.platform.configuration.get_global_config_str", lambda *k: None
    )
    monkeypatch.setattr(
        "agentkit.platform.configuration.get_global_config_value", lambda *k: None
    )
    # Never touch the real SSO session store (Keychain) from tests.
    from agentkit.auth import providers as auth_providers

    monkeypatch.setattr(
        auth_providers.SsoStsCredentialProvider, "resolve", lambda self: None
    )
    return monkeypatch


@pytest.fixture
def stub_caller_identity(monkeypatch):
    """Stub the network so the constructor's GetCallerIdentity guard is offline."""
    calls: list[tuple[str, str]] = []

    def _fake_call(self, service, action, version, body):
        calls.append((service, action))
        return {"AccountId": "2100000000"}

    monkeypatch.setattr(OpenApiClient, "call", _fake_call)
    return calls


class TestOpenApiClientProviderAware:
    def test_byteplus_env_credentials(self, isolated_env, stub_caller_identity):
        isolated_env.setenv("CLOUD_PROVIDER", "byteplus")
        isolated_env.setenv("BYTEPLUS_ACCESS_KEY", "BP_AK")
        isolated_env.setenv("BYTEPLUS_SECRET_KEY", "BP_SK")
        isolated_env.setenv("BYTEPLUS_SESSION_TOKEN", "BP_TOKEN")

        api = OpenApiClient()

        assert api.provider == CloudProvider.BYTEPLUS
        assert (api.ak, api.sk, api.token) == ("BP_AK", "BP_SK", "BP_TOKEN")
        assert api._host == "open.byteplusapi.com"
        assert api.region == "ap-southeast-1"  # BytePlus default region
        assert ("sts", "GetCallerIdentity") in stub_caller_identity

    def test_byteplus_region_sources(self, isolated_env, stub_caller_identity):
        isolated_env.setenv("CLOUD_PROVIDER", "byteplus")
        isolated_env.setenv("BYTEPLUS_ACCESS_KEY", "BP_AK")
        isolated_env.setenv("BYTEPLUS_SECRET_KEY", "BP_SK")
        isolated_env.setenv("BYTEPLUS_REGION", "ap-southeast-3")

        assert OpenApiClient().region == "ap-southeast-3"
        # An explicit --region always wins over the env.
        assert OpenApiClient(region="ap-southeast-1").region == "ap-southeast-1"

    def test_volcengine_env_credentials(self, isolated_env, stub_caller_identity):
        isolated_env.setenv("VOLCENGINE_ACCESS_KEY", "VE_AK")
        isolated_env.setenv("VOLCENGINE_SECRET_KEY", "VE_SK")

        api = OpenApiClient()

        assert api.provider == CloudProvider.VOLCENGINE
        assert (api.ak, api.sk) == ("VE_AK", "VE_SK")
        assert api._host == "open.volcengineapi.com"
        assert api.region == "cn-beijing"

    def test_volcengine_legacy_env_credentials(
        self, isolated_env, stub_caller_identity
    ):
        isolated_env.setenv("VOLC_ACCESSKEY", "LEGACY_AK")
        isolated_env.setenv("VOLC_SECRETKEY", "LEGACY_SK")

        api = OpenApiClient()
        assert (api.ak, api.sk) == ("LEGACY_AK", "LEGACY_SK")

    def test_explicit_args_win_over_env(self, isolated_env, stub_caller_identity):
        isolated_env.setenv("CLOUD_PROVIDER", "byteplus")
        isolated_env.setenv("BYTEPLUS_ACCESS_KEY", "ENV_AK")
        isolated_env.setenv("BYTEPLUS_SECRET_KEY", "ENV_SK")

        api = OpenApiClient(access_key="ARG_AK", secret_key="ARG_SK")
        assert (api.ak, api.sk) == ("ARG_AK", "ARG_SK")

    def test_missing_byteplus_credentials(self, isolated_env, stub_caller_identity):
        isolated_env.setenv("CLOUD_PROVIDER", "byteplus")
        # Volcengine creds present must NOT satisfy a BytePlus deploy.
        isolated_env.setenv("VOLCENGINE_ACCESS_KEY", "VE_AK")
        isolated_env.setenv("VOLCENGINE_SECRET_KEY", "VE_SK")

        with pytest.raises(AuthError) as exc:
            OpenApiClient()
        assert "BytePlus" in str(exc.value)
        assert "BYTEPLUS_ACCESS_KEY" in (exc.value.hint or "")

    def test_missing_volcengine_credentials(self, isolated_env, stub_caller_identity):
        with pytest.raises(AuthError) as exc:
            OpenApiClient()
        assert "Volcengine" in str(exc.value)
        assert "VOLCENGINE_ACCESS_KEY" in (exc.value.hint or "")

    def test_sso_session_rejected_for_admin(
        self, isolated_env, stub_caller_identity
    ):
        """`agentkit login` (end-user sandbox STS role) must not silently become
        the admin provisioning identity."""
        from agentkit.auth import providers as auth_providers

        isolated_env.setattr(
            auth_providers.SsoStsCredentialProvider,
            "resolve",
            lambda self: auth_providers.ResolvedCredentials(
                "SSO_AK", "SSO_SK", "SSO_TOKEN", "sso-sts"
            ),
        )
        with pytest.raises(AuthError) as exc:
            OpenApiClient()
        assert "sandbox role" in str(exc.value)
        assert "VOLCENGINE_ACCESS_KEY" in (exc.value.hint or "")


class TestResolveIssuer:
    """The issuer must come from the platform (GetUserPool), not a domain template —
    IAM CreateOIDCProvider validates the issuer's discovery endpoint, and the
    Volcengine template is wrong on BytePlus."""

    class _FakeApi:
        def __init__(self, result=None, exc=None):
            self._result = result
            self._exc = exc

        def call(self, service, action, version, body):
            assert (service, action) == ("id", "GetUserPool")
            assert body == {"UserPoolUid": "uid-1"}
            if self._exc:
                raise self._exc
            return self._result

    def test_platform_issuer_url_wins(self):
        from agentkit.auth.admin import resolve_issuer

        api = self._FakeApi(
            {"IssuerUrl": "https://userpool-uid-1.userpool.auth.id.ap-southeast-1.byteplus.example/"}
        )
        assert (
            resolve_issuer(api, "uid-1", "ap-southeast-1")
            == "https://userpool-uid-1.userpool.auth.id.ap-southeast-1.byteplus.example"
        )

    def test_domain_fallback(self):
        from agentkit.auth.admin import resolve_issuer

        api = self._FakeApi({"IssuerUrl": "", "Domain": "pool.example.com"})
        assert resolve_issuer(api, "uid-1", "cn-beijing") == "https://pool.example.com"

    def test_template_fallback_on_api_error(self):
        from agentkit.auth._openapi import ApiError
        from agentkit.auth.admin import resolve_issuer

        api = self._FakeApi(exc=ApiError("GetUserPool", "InternalError", "boom"))
        assert (
            resolve_issuer(api, "uid-1", "cn-beijing")
            == "https://userpool-uid-1.userpool.auth.id.cn-beijing.volces.com"
        )


class _ScriptedApi:
    """Fake OpenApiClient: canned responses/errors keyed by (service, action)."""

    def __init__(self, script):
        self.script = script  # {(service, action): result | Exception | callable(body)}
        self.calls = []

    def call(self, service, action, version, body):
        self.calls.append((service, action, body))
        entry = self.script[(service, action)]
        if callable(entry) and not isinstance(entry, Exception):
            entry = entry(body)
        if isinstance(entry, Exception):
            raise entry
        return entry

    call_ok = call


class TestIdempotentReruns:
    """Re-running sso-setup must reuse what earlier runs left behind."""

    def test_create_user_pool_reuses_same_name_pool(self):
        from agentkit.auth._openapi import ApiError
        from agentkit.auth.admin import create_user_pool

        api = _ScriptedApi({
            ("id", "CreateUserPool"): ApiError("CreateUserPool", "Duplicated", "already exists"),
            ("id", "ListUserPools"): {"Data": [
                {"Name": "other", "Uid": "u-other"},
                {"Name": "agentkit-cli-pool", "Uid": "u-reused"},
            ]},
            ("id", "GetUserPool"): {"IssuerUrl": "https://pool.example"},
        })
        uid, issuer = create_user_pool("agentkit-cli-pool", region="ap-southeast-1", api=api)
        assert (uid, issuer) == ("u-reused", "https://pool.example")

    def test_create_user_pool_other_errors_propagate(self):
        from agentkit.auth._openapi import ApiError
        from agentkit.auth.admin import create_user_pool

        api = _ScriptedApi({
            ("id", "CreateUserPool"): ApiError("CreateUserPool", "AccessDenied", "no"),
        })
        with pytest.raises(ApiError):
            create_user_pool("p", region="cn-beijing", api=api)

    def test_ensure_role_updates_existing_without_create(self):
        """Quota-full accounts return LimitExceeded before the duplicate-name check,
        so an existing role must be detected via GetRole, never via CreateRole."""
        from agentkit.auth.admin import _ensure_role

        api = _ScriptedApi({
            ("iam", "GetRole"): {"RoleName": "r"},
            ("iam", "UpdateRole"): {},
            ("iam", "CreatePolicy"): {},
            ("iam", "AttachRolePolicy"): {},
        })
        _ensure_role(api, "trn:iam::1:oidc-provider/p", role_name="r")
        actions = [a for _, a, _ in api.calls]
        assert "CreateRole" not in actions
        assert "UpdateRole" in actions

    def test_ensure_role_creates_when_missing(self):
        from agentkit.auth._openapi import ApiError
        from agentkit.auth.admin import _ensure_role

        api = _ScriptedApi({
            ("iam", "GetRole"): ApiError("GetRole", "RoleNotExist", "missing"),
            ("iam", "CreateRole"): {},
            ("iam", "CreatePolicy"): {},
            ("iam", "AttachRolePolicy"): {},
        })
        _ensure_role(api, "trn:iam::1:oidc-provider/p", role_name="r")
        assert "CreateRole" in [a for _, a, _ in api.calls]

    def test_ensure_role_quota_error_propagates_when_truly_missing(self):
        from agentkit.auth._openapi import ApiError
        from agentkit.auth.admin import _ensure_role

        api = _ScriptedApi({
            ("iam", "GetRole"): ApiError("GetRole", "RoleNotExist", "missing"),
            ("iam", "CreateRole"): ApiError("CreateRole", "LimitExceeded", "RolesPerAccount"),
        })
        with pytest.raises(ApiError) as exc:
            _ensure_role(api, "trn:iam::1:oidc-provider/p", role_name="r")
        assert exc.value.code == "LimitExceeded"


class TestTosPublicHost:
    def test_volcengine(self, isolated_env):
        from agentkit.auth.admin import tos_public_host

        assert tos_public_host("cn-beijing") == "tos-cn-beijing.volces.com"

    def test_byteplus(self, isolated_env):
        from agentkit.auth.admin import tos_public_host

        isolated_env.setenv("CLOUD_PROVIDER", "byteplus")
        assert tos_public_host("ap-southeast-1") == "tos-ap-southeast-1.bytepluses.com"


class TestStsHostPlumbing:
    """The discovery doc carries the provider's STS endpoint (`sts_host`) and the
    end-user login honors it — a BytePlus pool must not call the Volcengine STS."""

    def test_sts_public_host_by_provider(self, isolated_env):
        from agentkit.auth.admin import sts_public_host

        assert sts_public_host("cn-beijing") == "sts.volcengineapi.com"
        isolated_env.setenv("CLOUD_PROVIDER", "byteplus")
        assert sts_public_host("ap-southeast-1") == "sts.ap-southeast-1.byteplusapi.com"

    def test_discovery_doc_carries_sts_host(self):
        from agentkit.auth.admin import CliAccessCoords

        kwargs = dict(
            account_id="1", region="ap-southeast-1", user_pool_uid="u", issuer="https://i",
            client_id="c", role_trn="trn:iam::1:role/r", provider_trn="trn:iam::1:oidc-provider/p",
        )
        doc = CliAccessCoords(**kwargs, sts_host="sts.ap-southeast-1.byteplusapi.com").discovery_doc()
        assert doc["sts_host"] == "sts.ap-southeast-1.byteplusapi.com"
        # Back-compat: no sts_host -> field omitted, older docs keep their shape.
        assert "sts_host" not in CliAccessCoords(**kwargs).discovery_doc()

    def test_resolve_profile_parses_sts_host(self, isolated_env, tmp_path):
        import json

        from agentkit.auth.resolve import resolve_profile

        doc = {
            "issuer": "https://userpool-u.userpool.auth.id.ap-southeast-1.example",
            "client_id": "c",
            "role_trn": "trn:iam::1:role/r",
            "provider_trn": "trn:iam::1:oidc-provider/p",
            "region": "ap-southeast-1",
            "sts_host": "sts.ap-southeast-1.byteplusapi.com",
        }
        path = tmp_path / "agentkit-cli.json"
        path.write_text(json.dumps(doc))
        prof = resolve_profile(str(path), harden_ssl=False)
        assert prof.sts_host == "sts.ap-southeast-1.byteplusapi.com"

        path.write_text(json.dumps({k: v for k, v in doc.items() if k != "sts_host"}))
        assert resolve_profile(str(path), harden_ssl=False).sts_host is None

    def test_assume_role_honors_host(self, monkeypatch):
        import io
        import json

        from agentkit.auth import sts as sts_mod

        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append(req.full_url)
            return io.BytesIO(json.dumps({"Result": {"Credentials": {
                "AccessKeyId": "AK", "SecretAccessKey": "SK", "SessionToken": "TOK",
                "ExpiredTime": "2026-08-18T00:00:00+00:00",
            }}}).encode())

        monkeypatch.setattr(sts_mod.urllib.request, "urlopen", fake_urlopen)

        sts_mod.assume_role_with_oidc("tok", "trn:iam::1:role/r", host="sts.ap-southeast-1.byteplusapi.com")
        assert seen[-1].startswith("https://sts.ap-southeast-1.byteplusapi.com/")
        # Default (older discovery docs without sts_host) is unchanged.
        sts_mod.assume_role_with_oidc("tok", "trn:iam::1:role/r")
        assert seen[-1].startswith("https://sts.volcengineapi.com/")
