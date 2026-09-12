# n8n-mcp Helm chart

[English](README.md)

AI 助理實際連線的 n8n MCP 端點，打包成 Helm chart。每個實例一個 release，和 n8n
本身的 release 互相獨立。

兩種模式：

| mode | 跑什麼 | 狀態 |
| --- | --- | --- |
| `upstream`（預設） | `ghcr.io/czlonkowski/n8n-mcp` + nginx **祕密路徑代理** | woow-k3s 上就是這個 |
| `bundle` | 本 repo 自己的 admin GUI 映像（GUI + proxy + 內嵌 n8n-mcp） | 實驗性，映像尚未發布 |

## 架構（mode: upstream）

```
Cloudflare Tunnel ──► nginx (3001)  ──►  n8n-mcp (3000)  ──►  n8n REST API
                      只有 /private_<pathSecret>/ 有回應        N8N_API_URL
                      由它補上 "Authorization: Bearer <token>"  N8N_API_KEY
```

* MCP server 本身每個請求都要 `AUTH_TOKEN`。只有 nginx 知道這個 token，所以
  用戶端只需要知道**祕密 URL 路徑**。
* 其他路徑一律回 `404`，包含 `/.well-known/` 與 `/register`，不對掃描器暴露自己。
* `proxy.mode=sidecar`（預設）把 nginx 放進 MCP pod，代理到 `127.0.0.1:3000`，
  token 不會離開 pod。`proxy.mode=standalone` 讓 nginx 有自己的 Deployment 與
  Service（`woowtech-odoo` 實例目前就是這樣跑）。

祕密路徑與 bearer token 都是**機密資料**，分別放在 Secret 與 proxy 的 ConfigMap，
預設都不由 Helm 管理（`secrets.create=false`、`proxy.config.create=false`），
所以升級永遠不會覆蓋或外洩它們。範例見
[examples/secrets.example.yaml](examples/secrets.example.yaml)。

## woow-k3s 上的實例

| release | namespace | proxy | 物件 |
| --- | --- | --- | --- |
| `n8n-mcp` | `woowtech-odoo` | standalone | `Deployment/n8n-mcp`、`Deployment/n8n-mcp-proxy`、`Service/n8n-mcp`、`Service/n8n-mcp-proxy` |
| `cindytech-n8n-mcp` | `cindytech` | sidecar | `Deployment/cindytech-n8n-mcp`、`Service/cindytech-n8n-mcp-svc` |

它們的 values 在 [`deploy/woow-k3s/`](../../deploy/woow-k3s)，不含任何機密。
用這些 values 渲染出來的物件與線上逐欄一致。

## 安裝

chart 放在子目錄，所以 GitHub 分支 tarball 不是一個 chart
（`helm show chart .../main.tar.gz` → `Chart.yaml file is missing`）。請 clone，
或先 `helm package` 出 `.tgz` 再用。

```bash
git clone https://github.com/WOOWTECH/woow_n8n_mcp_server
cd woow_n8n_mcp_server

# A. 讓 chart 建立 Secret 與 proxy 設定（全新實例）
helm install my-n8n-mcp charts/n8n-mcp -n my-ns --create-namespace \
  --set mcp.n8nApiUrl=http://n8n.my-ns.svc.cluster.local:5678 \
  --set secrets.create=true \
  --set secrets.n8nApiKey="$N8N_API_KEY" \
  --set secrets.mcpAuthToken="$(openssl rand -hex 32)" \
  --set proxy.config.create=true \
  --set proxy.config.pathSecret="$(openssl rand -hex 10)" \
  --set proxy.config.authToken="$MCP_AUTH_TOKEN"   # 與 mcpAuthToken 相同

# B. 機密資料放在 Helm 之外（woow-k3s 的做法）
cp charts/n8n-mcp/examples/secrets.example.yaml /secure/path/n8n-mcp-secrets.yaml
# ……把每個 REPLACE_ME 換掉……
kubectl --context woow-k3s apply -f /secure/path/n8n-mcp-secrets.yaml
helm install my-n8n-mcp charts/n8n-mcp -n my-ns \
  --set mcp.n8nApiUrl=http://n8n.my-ns.svc.cluster.local:5678 \
  --set secrets.name=n8n-secrets --set proxy.config.name=n8n-mcp-proxy-config

# C. 打包散佈
helm package charts/n8n-mcp          # -> n8n-mcp-1.0.0.tgz
helm install my-n8n-mcp ./n8n-mcp-1.0.0.tgz -n my-ns -f my-values.yaml
```

n8n API key 從 n8n GUI（設定 → n8n API）取得，或用 `POST /rest/api-keys` 搭配
登入 cookie **以及對應的 `browser-id` header**——少了它 n8n 會拒絕 cookie 認證。

## 主要 values

| value | 預設 | 說明 |
| --- | --- | --- |
| `mode` | `upstream` | `bundle` 改跑本 repo 自己的映像 |
| `mcp.n8nApiUrl` | *（必填）* | n8n REST base URL；沒填 `required()` 直接失敗 |
| `mcp.image.tag` | `latest` | 上游目前沒有我們追蹤的固定 tag |
| `mcp.legacyMcpAuthTokenEnv` | `false` | 額外帶 `MCP_AUTH_TOKEN`（`woowtech-odoo` 的 pod 有） |
| `mcp.probes.enabled` | `true` | `woowtech-odoo` 關掉：加探測會重啟線上 pod |
| `proxy.mode` | `sidecar` | `standalone` = 自己的 Deployment + Service |
| `proxy.config.create` | `false` | `true` 由 `pathSecret` + `authToken` 產生 nginx.conf |
| `proxy.config.nginxConf` | `""` | 原文 nginx.conf，用來逐位元重現手寫設定 |
| `secrets.create` | `false` | `true` 由 `secrets.*` 產生 Secret |
| `secrets.name` | `<release>-secrets` | 要引用的既有 Secret |
| `serviceSuffix` | `""` | cindytech 實例用 `-svc` |
| `selectorLabels` | `{app: <release>}` | pod 標籤**與** selector，不可變更 |
| `commonLabels` | `{}` | 併入每個物件的 `metadata.labels` |
| `keepOnUninstall` | `true` | 在 Namespace、PVC、Secret 與 proxy ConfigMap 加上 `helm.sh/resource-policy: keep` |
| `namespace.create` | `false` | MCP release 併入應用的 namespace |
| `tests.enabled` | `true` | 唯讀的 `helm test` 煙霧測試 pod |

## 驗證

```bash
kubectl -n <ns> rollout status deploy/<release> --timeout=5m
helm test <release> -n <ns> --logs
```

煙霧測試 pod 只讀不寫，檢查：

```
mcp /health 200
proxy / 404
proxy /health 200
unauthenticated /mcp 401          # token 閘門有效
proxied MCP initialize 200 (nginx injects the token)
SMOKE OK
```

最後一行只有在測試知道祕密路徑時才跑（`proxy.config.create=true`，或用
`tests.pathSecret` 做一次性安裝——正式環境的祕密路徑絕對不要放進去，它會出現在
Pod spec 裡）。

對真的 n8n 做的端到端驗證（本 chart 就是這樣測的）：`initialize`、`tools/list`
（28 個工具），再經 `/private_<pathSecret>/mcp` 呼叫 `tools/call n8n_health_check`
與 `n8n_list_workflows`。

repo 對 release 對叢集：

```bash
CONTEXT=woow-k3s RELEASE=n8n-mcp NAMESPACE=woowtech-odoo \
  VALUES=deploy/woow-k3s/n8n-mcp-woowtech-odoo.yaml ../../scripts/check-drift.sh
```

## 卸載（資料保留）

```bash
helm uninstall <release> -n <ns>
```

`keepOnUninstall=true`（預設）時 Helm 會對 Secret、proxy ConfigMap、Namespace
以及（bundle 模式）PVC 印出 `Skipping delete ... due to annotation`。Deployment
與 Service 會被刪除；祕密路徑、token 與 `/data` 內容留著。保留下來的物件之後不
屬於任何 release，所以再 `helm install` 同名 release 時，要嘛引用它們
（`secrets.create=false`，預設），要嘛就會因為 *already exists* 失敗——真的要清乾
淨就先手動刪掉。

## 接管線上實例（不會重啟）

線上物件是用 `kubectl apply` 建的，接管需要 `--take-ownership`；其餘欄位必須
**完全一致**，否則 Deployment 會滾動重建 pod。

```bash
# 1. 先在測試 namespace 演練（匯出線上物件、改 namespace、產生一次性的 Secret 與
#    proxy ConfigMap、apply，然後接管）。
# 2. 正式執行：
helm --kube-context woow-k3s upgrade --install n8n-mcp charts/n8n-mcp \
  -n woowtech-odoo -f deploy/woow-k3s/n8n-mcp-woowtech-odoo.yaml --take-ownership

helm --kube-context woow-k3s upgrade --install cindytech-n8n-mcp charts/n8n-mcp \
  -n cindytech -f deploy/woow-k3s/cindytech-n8n-mcp.yaml --take-ownership
```

會變的與絕對不能變的：

* Helm 會加上標籤 `app.kubernetes.io/managed-by: Helm` 與註解
  `meta.helm.sh/release-name`、`meta.helm.sh/release-namespace`。Deployment 的
  註解變動會讓 `metadata.generation` +1——但 pod template hash、ReplicaSet 與 pod
  完全不動（`deployment.kubernetes.io/revision` 不會前進）。
* `kubectl.kubernetes.io/restartedAt` 這個 pod 註解屬於 pod template，已在實例
  values 裡原樣保留。**少一個就會重啟 pod。** env 的順序、空的
  `securityContext: {}`、volume 名稱（`config` 對 `nginx-config`）與容器名稱
  （`nginx` 對 `n8n-mcp-proxy`）同理。
* Secret 與 proxy ConfigMap **不會**被接管（`create=false`），叢集裡的值不動。

2026-09-12 對兩個實例都演練過：pod UID 相同、container ID 相同、重啟次數 0、
revision 沒變。

## mode: bundle（實驗性）

`mode=bundle` 部署本 repo 自己的映像：FastAPI + React 管理 GUI、token 保護的 MCP
proxy 與內嵌的 `n8n-mcp`，單一 uvicorn 程序監聽 `8080`，設定在
`/data/config.json`（PVC，卸載時保留）。

在改掉管理者密碼之前不要對外暴露：第一次啟動會把文件上公開的預設密碼寫進
`/data/config.json`，而且管理 API 可以設定 MCP server 的命令列（等於在容器內執行
任意程式）。`ghcr.io/woowtech/n8n-mcp-admin:latest` 目前不存在，要先用
`Dockerfile` 建置並推送。woow-k3s 上沒有任何實例跑這個模式，這部分 template 只通
過渲染與 schema 驗證，沒有做功能測試。

## 從 k8s-deploy.yaml 遷移

舊的根目錄 `k8s-deploy.yaml` 把 `odoo-mcp-admin` 與 `n8n-mcp-admin` 部署到寫死的
`kasim-odoo` namespace（映像是 `jcr-prod.woowtech.io/...`、containerPort 9002 但本
repo 的 Dockerfile 監聽 8080、注入的 env 程式根本不讀、`/data` 沒有掛任何 volume、
Role 對該 namespace 所有 Secret 有讀寫權）。那個 namespace 即將刪除，檔案已移除。
沒有東西需要遷移：請用這個 chart；管理 GUI 等映像發布後用 `mode=bundle`。

## 後續事項（刻意不放進這次變更）

* 給 `woowtech-odoo` 實例加上探測與容器 `securityContext`：兩者都會改動 pod
  template，所以在它的 values 裡是關閉的，留到下一次計畫性重啟。
* 兩個實例的 `mcp.image.tag: latest`——等上游有可追蹤的穩定 tag 再釘 digest。
* 把 `woowtech-odoo` 實例從 `proxy.mode=standalone` 改成 `sidecar`（bearer token
  少一跳）；這會替換 pod。
* `mode=bundle`：建置並發布映像，然後做功能測試。
