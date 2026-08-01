# Agent Identity and OBO

AgentKit Runtime can authenticate a signed-in user, bind the request to the
Runtime's own Workload Identity, and obtain a short-lived, target-bound workload
access token (TIP) before calling a protected downstream service.

This is a data-plane SDK. It is deliberately separate from
`agentkit.sdk.identity`, which configures Runtime inbound authorizers through the
management plane.

## Trust model

The deployment, not an inbound request, provides an immutable
`IdentityRuntimeConfig`:

- `runtime_id` is also the Workload Identity name in this version;
- the OIDC issuer and allowed client IDs define which user ID Tokens are trusted;
- the Workload Pool discovery URL pins the issuer/JWKS used to verify returned
  TIPs;
- every downstream alias maps to exactly one audience and, for HTTP, one HTTPS
  base URL;
- Runtime IAM credentials authorize the call to
  `GetWorkloadAccessTokenForJWT`.

For the first APIG integration, the gateway or deployment configuration can keep
the trusted `route/runtime -> workload -> audience` registry. A future control
plane can construct the same configuration object; callers must never supply or
override this binding in a request.

V1 therefore expects a pre-created Runtime/Workload and deployment-injected
configuration. It does not infer a trusted Runtime ID from Agent business code.

## Runtime integration

```python
from agentkit.apps import AgentkitAgentServerApp
from agentkit.identity import (
    IdentityClient,
    IdentityRuntimeConfig,
    ProtectedTarget,
    RuntimeIdentity,
)

identity = RuntimeIdentity(
    IdentityRuntimeConfig(
        runtime_id="runtime-123",  # also the Workload Identity name
        workload_pool="default",
        discovery_url=(
            "https://userpool-example.userpool.auth.id.cn-beijing."
            "volces.com"
        ),
        allowed_clients=("agentkit-public-client",),
        workload_discovery_url=(
            "https://auth.id.cn-beijing.volces.com/workloadpool/<pool-id>/"
            ".well-known/openid-configuration"
        ),
        targets={
            "expense": ProtectedTarget(
                alias="expense",
                audience="trn:customer:expense-api",
                base_url="https://gateway.example.com/expense",
            )
        },
    ),
    # Direct exchange is explicit. Use it only after the Identity service has
    # an authoritative Runtime-IAM -> Workload binding for this deployment.
    exchange=IdentityClient(region="cn-beijing"),
)

app = AgentkitAgentServerApp(
    agent=agent,
    short_term_memory=memory,
    identity=identity,
)
http = identity.authorized_session()
```

`AgentIdentityMiddleware` is installed by `AgentkitAgentServerApp`. Credential-
free browser `OPTIONS` preflight is delegated to the inner CORS middleware or
router. Before any authenticated Agent or Tool route runs, it:

1. reads exactly one inbound Bearer ID Token;
2. verifies signature, algorithm, issuer, audience/client, expiry, issued-at,
   subject, and the OIDC authorized party rule;
3. removes the raw `Authorization` header from the child ASGI scope;
4. binds an immutable `IdentityContext` for the whole streaming request;
5. uses the verified `sub`, not caller-provided `user_id`, on AgentKit's
   `/invoke` and `/run_sse` paths.

ADK session paths under `/apps/{app}/users/{user}/...` are rejected unless the
path user equals the verified subject. The unbound ADK `/run` route and A2A mount
are disabled in identity mode in V1; use `/invoke` or `/run_sse`. Identity mode
also rejects WebSocket, debug, eval, administrative, and future unknown routes
until they have an explicit subject-binding rule.

Verification is SDK middleware. It does not belong in `agent.py`.

## Calling a protected target

Agent or Tool code calls a registered alias, not an arbitrary host:

```python
response = http.request(
    "GET",
    "expense",
    "/v1/expenses/123",
    timeout=10,
)
response.raise_for_status()
```

For training and observability, callers can request token-free evidence after
the same exchange and validation path succeeds:

```python
receipt = identity.delegation_receipt("expense")
# DelegationReceipt(target_alias="expense", subject="alice",
#                   actor="runtime-123", audience="...", expires_at=...)
```

The receipt never contains the ID Token or TIP and is not an authorization
credential. Protected business calls must still use `AuthorizedSession`.

The SDK exchanges the verified user ID Token with
`GetWorkloadAccessTokenForJWT`, requesting the configured audience. It rejects a
response whose `sub`, direct `act.sub`, `aud`, or lifetime does not match the
request. It also verifies the TIP signature and issuer against the configured
Workload Pool discovery document, prevents a TIP from outliving the delegated
user token, caches it in a bounded in-memory cache keyed by the subject-token
fingerprint/user/Runtime/target, injects it as the downstream Bearer token, and
disables redirects. Business code cannot override the `Authorization` header or
target host through this transport. It also rejects routing/forwarding headers,
caller cookies, `TRACE`/`CONNECT`, response cookies, and security-sensitive
`requests` options. The returned response and any raised SDK error do not retain
the prepared request that carried the TIP.

The downstream service or APIG independently verifies the TIP and audience
and enforces policy over the user (`sub`), Agent/Workload (`act.sub`), action, and
resource.

`RuntimeIdentity` intentionally has no implicit exchange for protected targets.
Before the Identity control plane exposes an authoritative Runtime-to-Workload
binding, the demo deployment must inject a trusted `WorkloadTokenExchange`
implemented by APIG or a deployment-owned adapter. APIG keeps the immutable
`route/runtime -> workload -> audience` registry, authenticates the Runtime,
performs the exchange, and returns the TIP for SDK verification. This temporary
path does not put binding logic in `agent.py` and can later be replaced by the
control-plane binding without changing Agent or Tool APIs.

## CLI login flow

The browser login uses Authorization Code with PKCE and OIDC nonce validation.
AgentKit verifies the returned ID Token before saving the session. A cached,
still-valid ID Token can be read without opening the OS keychain; the refresh
token is resolved only when refresh is actually required.

For a direct JWT-authorized Runtime endpoint:

```shell
agentkit invoke --endpoint https://runtime.example.com --use-login "hello"
```

`--use-login` is explicit and cannot be combined with an API key or a manually
supplied `Authorization` header. It requires HTTPS, except for an explicit
loopback HTTP endpoint. Transport credentials are stripped when the CLI or
Runner converts a request into A2A business metadata.

## Security boundary and current limitations

- `runtime_id == workload_id` is the current product contract, but string
  equality inside Python is not proof of deployment ownership. Runtime IAM plus
  the Identity service, and later the APIG/control-plane registry, must enforce
  that ownership server-side.
- The repository includes `IdentityClient` for direct Identity OpenAPI exchange,
  but the host/service/version/action still require a live compatibility check.
  Do not use it where the Identity service has not yet enforced Runtime IAM to
  Workload ownership; inject an APIG-bound exchange instead.
- Token redaction and private Python attributes reduce accidental exposure; they
  do not isolate secrets from malicious code in the same process. A gateway,
  sidecar, or separate broker is required for that stronger threat model.
- Except for credential-free CORS preflight, the SDK authenticates every HTTP
  route when identity mode is enabled. V1 rejects mismatched ADK session paths
  and disables the unbound `/run` and A2A paths.
- The refresh token prefers the OS keychain. Existing compatibility behavior can
  fall back to a `0600` session file when no usable keychain exists; deployments
  that prohibit file-held refresh tokens must enforce a keychain-only policy.
- Saved sessions created before verified `user_sub` binding continue using a
  still-valid cached ID Token, but require one new browser login when refresh is
  next needed. This is a deliberate fail-closed upgrade behavior.
- Standard OIDC deployments may advertise HTTPS authorization, token, and JWKS
  endpoints on origins different from the issuer. AgentKit trusts the exact URLs
  in the issuer-matched discovery document, blocks cross-origin redirects for
  each request, and supports an explicit strict JWKS-origin allowlist.
- The Identity OpenAPI action, signing service, endpoint, and version in this
  implementation follow the repository's fixed API baseline. They require a
  live compatibility check before a production release.
