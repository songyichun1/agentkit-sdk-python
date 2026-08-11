# AgentKit Harness Sidecar Integration

Public integration for configuring and launching the private Harness Sidecar
Runtime. Projects that use the capability can declare the SDK extra:

```bash
pip install "agentkit-sdk-python[harness-sidecar]"
```

This public integration is a separate optional distribution. A default
`agentkit-sdk-python` installation does not contain
`agentkit.extensions.harness_sidecar`, does not register the `agentkit harness`
CLI group, and does not add any Sidecar dependency. Install the integration only
through the SDK extra shown above.

The private Runtime wheel is installed only while AgentKit builds a managed,
immutable Sidecar-enabled Runtime image in an authorized cloud environment.
Customer projects and deploy machines never resolve or download the private
wheel. The final application image retains the compiled Runtime but not the
wheel, private package index, source, or build cache.

At Runtime startup, veADK's `HarnessExtension` owns the single Sidecar process.
For managed cloud delivery, `apig_runtime_port` sends model requests through the
Runtime Gateway with fixed `X-Faas-Proxy-Port` routing. It also rewrites the
configured managed-Toolset URL (for example, `TOOL_MCP_ROUTER_URL`) to a local
relay. That relay reaches the Sidecar MCP Gateway through APIG on fixed port
18788; the Sidecar replaces Runtime Gateway authorization with the separately
configured Toolset authorization before calling the upstream Toolset. Missing
Runtime or Toolset authorization fails closed. Missing private Runtime support
is an incompatible-image error: customers should select a Sidecar-enabled
managed image or disable the capability, not install a private package
themselves.
