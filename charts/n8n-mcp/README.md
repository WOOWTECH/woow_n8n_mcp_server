# n8n-mcp Helm chart

[繁體中文](README_zh-TW.md)

The n8n MCP endpoint that AI assistants talk to, as a Helm chart. One release
per instance, independent of the n8n release itself.

Two modes:

| mode | what runs | status |
| --- | --- | --- |
| `upstream` (default) | `ghcr.io/czlonkowski/n8n-mcp` + an nginx **path-secret proxy** | what runs on woow-k3s |
| `bundle` | this repository's own admin-GUI image (GUI + proxy + embedded n8n-mcp) | experimental, image not published |

## Architecture (mode: upstream)

```
Cloudflare Tunnel ──► nginx (3001)  ──►  n8n-mcp (3000)  ──►  n8n REST API
                      only /private_<pathSecret>/ answers      N8N_API_URL
                      adds "Authorization: Bearer <token>"     N8N_API_KEY
```

* The MCP server itself requires `AUTH_TOKEN` on every request. nginx is the only
  place that knows the token, so a client only needs the **secret URL path**.
* Every other path answers `404` - including `/.well-known/` and `/register`, so
  the endpoint does not advertise itself to scanners.
* `proxy.mode=sidecar` (default) puts nginx in the MCP pod and proxies to
  `127.0.0.1:3000`, so the token never leaves the pod. `proxy.mode=standalone`
  gives nginx its own Deployment + Service (how the `woowtech-odoo` instance
  runs today).

The secret URL path and the bearer token are **secret material**. They live in
a Secret and in the proxy's ConfigMap, both managed outside Helm by default
(`secrets.create=false`, `proxy.config.create=false`), so an upgrade can never
overwrite or leak them. See [examples/secrets.example.yaml](examples/secrets.example.yaml).

## Instances on woow-k3s

| release | namespace | proxy | objects |
| --- | --- | --- | --- |
| `n8n-mcp` | `woowtech-odoo` | standalone | `Deployment/n8n-mcp`, `Deployment/n8n-mcp-proxy`, `Service/n8n-mcp`, `Service/n8n-mcp-proxy` |
| `cindytech-n8n-mcp` | `cindytech` | sidecar | `Deployment/cindytech-n8n-mcp`, `Service/cindytech-n8n-mcp-svc` |

Their values are in [`deploy/woow-k3s/`](../../deploy/woow-k3s) and contain no
secrets. Rendering with them reproduces the live objects field for field.

## Install

The chart lives in a subdirectory, so the GitHub branch tarball is not a chart
(`helm show chart .../main.tar.gz` → `Chart.yaml file is missing`). Clone, or
package the chart once and keep the `.tgz`.

```bash
git clone https://github.com/WOOWTECH/woow_n8n_mcp_server
cd woow_n8n_mcp_server

# A. Let the chart create the Secret and the proxy config (fresh instance)
helm install my-n8n-mcp charts/n8n-mcp -n my-ns --create-namespace \
  --set mcp.n8nApiUrl=http://n8n.my-ns.svc.cluster.local:5678 \
  --set secrets.create=true \
  --set secrets.n8nApiKey="$N8N_API_KEY" \
  --set secrets.mcpAuthToken="$(openssl rand -hex 32)" \
  --set proxy.config.create=true \
  --set proxy.config.pathSecret="$(openssl rand -hex 10)" \
  --set proxy.config.authToken="$MCP_AUTH_TOKEN"   # same value as mcpAuthToken

# B. Manage the secret material outside Helm (how woow-k3s runs)
cp charts/n8n-mcp/examples/secrets.example.yaml /secure/path/n8n-mcp-secrets.yaml
# ... replace every REPLACE_ME ...
kubectl --context woow-k3s apply -f /secure/path/n8n-mcp-secrets.yaml
helm install my-n8n-mcp charts/n8n-mcp -n my-ns \
  --set mcp.n8nApiUrl=http://n8n.my-ns.svc.cluster.local:5678 \
  --set secrets.name=n8n-secrets --set proxy.config.name=n8n-mcp-proxy-config

# C. Distribute as a package
helm package charts/n8n-mcp          # -> n8n-mcp-1.0.0.tgz
helm install my-n8n-mcp ./n8n-mcp-1.0.0.tgz -n my-ns -f my-values.yaml
```

An n8n API key comes from the n8n GUI (Settings → n8n API) or from
`POST /rest/api-keys` with a login cookie **and the matching `browser-id`
header** - n8n rejects cookie auth without it.

## Key values

| value | default | notes |
| --- | --- | --- |
| `mode` | `upstream` | `bundle` runs this repo's own image instead |
| `mcp.n8nApiUrl` | *(required)* | n8n REST base URL; `required()` fails without it |
| `mcp.image.tag` | `latest` | upstream publishes no pinned tag pattern we track yet |
| `mcp.legacyMcpAuthTokenEnv` | `false` | also set `MCP_AUTH_TOKEN` (the `woowtech-odoo` pod has it) |
| `mcp.probes.enabled` | `true` | off for `woowtech-odoo`: adding probes would restart the live pod |
| `proxy.mode` | `sidecar` | `standalone` = own Deployment + Service |
| `proxy.config.create` | `false` | `true` renders nginx.conf from `pathSecret` + `authToken` |
| `proxy.config.nginxConf` | `""` | verbatim nginx.conf, to reproduce a hand-written one byte for byte |
| `secrets.create` | `false` | `true` renders the Secret from `secrets.*` |
| `secrets.name` | `<release>-secrets` | the existing Secret to reference |
| `serviceSuffix` | `""` | `-svc` for the cindytech instance |
| `selectorLabels` | `{app: <release>}` | pod labels **and** selector - immutable |
| `commonLabels` | `{}` | merged into every object's `metadata.labels` |
| `keepOnUninstall` | `true` | `helm.sh/resource-policy: keep` on Namespace, PVC, Secret and the proxy ConfigMap |
| `namespace.create` | `false` | an MCP release joins the app's namespace |
| `tests.enabled` | `true` | read-only `helm test` smoke pod |

## Verify

```bash
kubectl -n <ns> rollout status deploy/<release> --timeout=5m
helm test <release> -n <ns> --logs
```

The smoke pod checks, read-only:

```
mcp /health 200
proxy / 404
proxy /health 200
unauthenticated /mcp 401          # the token gate works
proxied MCP initialize 200 (nginx injects the token)
SMOKE OK
```

The last line only runs when the test knows the secret path
(`proxy.config.create=true`, or `tests.pathSecret` for a throwaway install -
never put a production path secret there, it lands in the Pod spec).

End to end against a real n8n (what the chart was tested with): `initialize`,
`tools/list` (28 tools), then `tools/call n8n_health_check` and
`n8n_list_workflows` through `/private_<pathSecret>/mcp`.

Repo vs release vs cluster:

```bash
CONTEXT=woow-k3s RELEASE=n8n-mcp NAMESPACE=woowtech-odoo \
  VALUES=deploy/woow-k3s/n8n-mcp-woowtech-odoo.yaml ../../scripts/check-drift.sh
```

## Uninstall (data is kept)

```bash
helm uninstall <release> -n <ns>
```

With `keepOnUninstall=true` (default) Helm logs `Skipping delete ... due to
annotation` for the Secret, the proxy ConfigMap, the Namespace and (bundle mode)
the PVC. Deployments and Services go; the secret URL path, the token and the
`/data` volume stay. The kept objects belong to nobody afterwards, so a later
`helm install` of the same release either references them
(`secrets.create=false`, the default) or fails with *already exists* - delete
them by hand first if you really want a clean slate.

## Takeover of a live instance (nothing restarts)

The live objects were created with `kubectl apply`. Adopting them needs
`--take-ownership`; everything else must be **identical**, or the Deployment
rolls its pods.

```bash
# 1. Rehearse in a test namespace (export the live objects, adjust namespace,
#    generate a throwaway Secret + proxy ConfigMap, apply, then take over).
# 2. The real thing:
helm --kube-context woow-k3s upgrade --install n8n-mcp charts/n8n-mcp \
  -n woowtech-odoo -f deploy/woow-k3s/n8n-mcp-woowtech-odoo.yaml --take-ownership

helm --kube-context woow-k3s upgrade --install cindytech-n8n-mcp charts/n8n-mcp \
  -n cindytech -f deploy/woow-k3s/cindytech-n8n-mcp.yaml --take-ownership
```

What changes, and what must not:

* Helm adds the label `app.kubernetes.io/managed-by: Helm` and the annotations
  `meta.helm.sh/release-name` / `meta.helm.sh/release-namespace`. On a
  Deployment an annotation change bumps `metadata.generation` by one - the pod
  template hash, the ReplicaSet and the pods stay exactly as they are
  (`deployment.kubernetes.io/revision` does not move).
* The `kubectl.kubernetes.io/restartedAt` pod annotations are part of the pod
  template and are restated in the instance values. **Removing one restarts the
  pod.** Same for the env order, the empty `securityContext: {}`, the volume
  names (`config` vs `nginx-config`) and the container names (`nginx` vs
  `n8n-mcp-proxy`).
* The Secret and the proxy ConfigMap are *not* adopted (`create=false`), so the
  values in the cluster are untouched.

Rehearsed on 2026-09-12 for both instances: same pod UIDs, same container IDs,
zero restarts, revision unchanged.

## mode: bundle (experimental)

`mode=bundle` deploys this repository's own image: FastAPI + React admin GUI, a
token-protected MCP proxy and an embedded `n8n-mcp`, one uvicorn process on
`8080`, configuration in `/data/config.json` (PVC, kept on uninstall).

Do not expose it until you have changed the admin password: the first boot
writes the documented default password into `/data/config.json`, and the admin
API can set the MCP server's command line (i.e. run code in the container).
`ghcr.io/woowtech/n8n-mcp-admin:latest` does not exist yet - build and push the
image from `Dockerfile` first. Nothing on woow-k3s runs this mode and the chart
templates for it are validated but not functionally tested.

## Migrating from k8s-deploy.yaml

The old root `k8s-deploy.yaml` deployed `odoo-mcp-admin` and `n8n-mcp-admin`
into the hardcoded namespace `kasim-odoo` (image `jcr-prod.woowtech.io/...`,
container port 9002 while this repo's Dockerfile listens on 8080, env the code
never reads, no volume for `/data`, and a Role with read/write access to every
Secret in the namespace). That namespace is being deleted and the manifest has
been removed. Nothing to migrate: use this chart, or `mode=bundle` for the admin
GUI once its image is published.

## Follow-ups (deliberately not in this chart)

* Probes and a container `securityContext` for the `woowtech-odoo` instance: both
  change its pod template, so they are off in its values and belong to the next
  planned restart.
* `mcp.image.tag: latest` for both instances - pin a digest when upstream
  publishes stable tags we track.
* Move the `woowtech-odoo` instance from `proxy.mode=standalone` to `sidecar`
  (one hop less for the bearer token); that is a pod replacement.
* `mode=bundle`: build and publish the image, then test it.
