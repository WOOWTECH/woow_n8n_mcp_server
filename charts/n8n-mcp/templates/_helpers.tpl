{{/*
Helper templates for the n8n-mcp chart.

Object names come from the release name (fullnameOverride wins), so a takeover
keeps the live names: release n8n-mcp -> Deployment n8n-mcp, release
cindytech-n8n-mcp -> Deployment cindytech-n8n-mcp. Selector and pod-template
labels are values, not derived: changing either would replace the Deployment or
restart every pod.
*/}}

{{- define "n8n-mcp.fullname" -}}
{{ default .Release.Name .Values.fullnameOverride }}
{{- end -}}

{{- define "n8n-mcp.ns" -}}
{{ default .Release.Namespace .Values.namespace.name }}
{{- end -}}

{{/* `annotations:` block with the keep policy, or nothing. */}}
{{- define "n8n-mcp.keepAnnotations" -}}
{{- if .Values.keepOnUninstall -}}
annotations:
  helm.sh/resource-policy: keep
{{- end -}}
{{- end -}}

{{/* Pod-template labels and selector (immutable). */}}
{{- define "n8n-mcp.selectorLabels" -}}
{{- if .Values.selectorLabels -}}
{{ toYaml .Values.selectorLabels }}
{{- else -}}
app: {{ include "n8n-mcp.fullname" . }}
{{- end -}}
{{- end -}}

{{- define "n8n-mcp.proxySelectorLabels" -}}
{{- if .Values.proxy.selectorLabels -}}
{{ toYaml .Values.proxy.selectorLabels }}
{{- else -}}
app: {{ include "n8n-mcp.fullname" . }}-proxy
{{- end -}}
{{- end -}}

{{- define "n8n-mcp.secretName" -}}
{{ default (printf "%s-secrets" (include "n8n-mcp.fullname" .)) .Values.secrets.name }}
{{- end -}}

{{- define "n8n-mcp.proxyConfigName" -}}
{{ default (printf "%s-proxy-config" (include "n8n-mcp.fullname" .)) .Values.proxy.config.name }}
{{- end -}}

{{- define "n8n-mcp.serviceName" -}}
{{ include "n8n-mcp.fullname" . }}{{ .Values.serviceSuffix }}
{{- end -}}

{{- define "n8n-mcp.proxyServiceName" -}}
{{ include "n8n-mcp.fullname" . }}-proxy{{ .Values.serviceSuffix }}
{{- end -}}

{{- define "n8n-mcp.dataPvcName" -}}
{{ default (printf "%s-data" (include "n8n-mcp.fullname" .)) .Values.bundle.persistence.name }}
{{- end -}}

{{/* Is the nginx proxy a container of the mcp pod? */}}
{{- define "n8n-mcp.proxyIsSidecar" -}}
{{- if and .Values.proxy.enabled (eq .Values.proxy.mode "sidecar") -}}true{{- end -}}
{{- end -}}

{{/* Host:port nginx proxies to. */}}
{{- define "n8n-mcp.proxyUpstream" -}}
{{- if .Values.proxy.config.upstream -}}
{{ .Values.proxy.config.upstream }}
{{- else if include "n8n-mcp.proxyIsSidecar" . -}}
127.0.0.1:{{ .Values.mcp.port }}
{{- else -}}
{{ include "n8n-mcp.serviceName" . }}:{{ .Values.mcp.port }}
{{- end -}}
{{- end -}}

{{/* Where the smoke pod reaches nginx. */}}
{{- define "n8n-mcp.proxyServiceHost" -}}
{{- if include "n8n-mcp.proxyIsSidecar" . -}}
{{ include "n8n-mcp.serviceName" . }}
{{- else -}}
{{ include "n8n-mcp.proxyServiceName" . }}
{{- end -}}
{{- end -}}

{{/*
env of the n8n-mcp container. The ORDER is part of the pod template: a reorder
changes the template hash and restarts the pod, so new settings are appended.
*/}}
{{- define "n8n-mcp.mcpEnv" -}}
{{- $s := .Values.secrets -}}
- name: N8N_API_URL
  value: {{ required "mcp.n8nApiUrl is required (the n8n REST API base URL)" .Values.mcp.n8nApiUrl | quote }}
- name: N8N_API_KEY
  valueFrom:
    secretKeyRef:
      key: {{ $s.keys.n8nApiKey }}
      name: {{ include "n8n-mcp.secretName" . }}
{{- if .Values.mcp.legacyMcpAuthTokenEnv }}
- name: MCP_AUTH_TOKEN
  valueFrom:
    secretKeyRef:
      key: {{ $s.keys.mcpAuthToken }}
      name: {{ include "n8n-mcp.secretName" . }}
{{- end }}
- name: AUTH_TOKEN
  valueFrom:
    secretKeyRef:
      key: {{ $s.keys.mcpAuthToken }}
      name: {{ include "n8n-mcp.secretName" . }}
- name: MCP_MODE
  value: {{ .Values.mcp.serverMode | quote }}
- name: NODE_ENV
  value: {{ .Values.mcp.nodeEnv | quote }}
- name: WEBHOOK_SECURITY_MODE
  value: {{ .Values.mcp.webhookSecurityMode | quote }}
- name: MCP_SESSION_TIMEOUT
  value: {{ .Values.mcp.sessionTimeout | quote }}
- name: MCP_MAX_SESSIONS
  value: {{ .Values.mcp.maxSessions | quote }}
{{- if .Values.mcp.authRateLimit.enabled }}
- name: AUTH_RATE_LIMIT_MAX
  value: {{ .Values.mcp.authRateLimit.max | quote }}
- name: AUTH_RATE_LIMIT_WINDOW
  value: {{ .Values.mcp.authRateLimit.windowMs | quote }}
{{- end }}
{{- with .Values.mcp.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
nginx.conf for the path-secret proxy. proxy.config.nginxConf replaces it
verbatim (to reproduce a hand-written config byte for byte).
*/}}
{{- define "n8n-mcp.nginxConf" -}}
{{- if .Values.proxy.config.nginxConf -}}
{{ .Values.proxy.config.nginxConf }}
{{- else -}}
{{- $c := .Values.proxy.config -}}
{{- $path := required "proxy.config.pathSecret is required when proxy.config.create=true" $c.pathSecret -}}
{{- $token := required "proxy.config.authToken is required when proxy.config.create=true" $c.authToken -}}
events { worker_connections 1024; }
http {
  client_max_body_size {{ $c.clientMaxBodySize }};
  map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
  }
  server {
    listen {{ .Values.proxy.port }};
{{ if $c.healthLocation }}
    location /health { return 200 'ok'; }
{{ end }}
    location /.well-known/ {
      return 404 '{"error":"not found"}';
    }

    location /register {
      return 404 '{"error":"not found"}';
    }

    location /private_{{ $path }}/ {
      rewrite ^/private_{{ $path }}/(.*) /$1 break;
      proxy_pass http://{{ include "n8n-mcp.proxyUpstream" . }};
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_set_header Authorization "Bearer {{ $token }}";
      proxy_http_version 1.1;
      proxy_set_header Connection '';
      proxy_buffering off;
      proxy_cache off;
      chunked_transfer_encoding off;
      proxy_read_timeout {{ $c.proxyTimeout }};
      proxy_send_timeout {{ $c.proxyTimeout }};
    }

    location / {
      return 404 '{"error":"not found"}';
    }
  }
}
{{- end -}}
{{- end -}}

{{/* The nginx container, shared by the sidecar and the standalone Deployment. */}}
{{- define "n8n-mcp.proxyContainer" -}}
{{- $p := .Values.proxy -}}
- name: {{ $p.containerName }}
  image: {{ $p.image.repository }}:{{ $p.image.tag }}
  imagePullPolicy: {{ $p.image.pullPolicy }}
  {{- with $p.extraEnv }}
  env:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  ports:
    - containerPort: {{ $p.port }}
      {{- with $p.portName }}
      name: {{ . }}
      {{- end }}
      protocol: TCP
  {{- if $p.probes.enabled }}
  livenessProbe:
    {{- toYaml $p.probes.liveness | nindent 4 }}
  readinessProbe:
    {{- toYaml $p.probes.readiness | nindent 4 }}
  {{- end }}
  {{- with $p.resources }}
  resources:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $p.securityContext }}
  securityContext:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  volumeMounts:
    - mountPath: /etc/nginx/nginx.conf
      name: {{ $p.volumes.configName }}
      {{- if $p.volumes.configReadOnly }}
      readOnly: true
      {{- end }}
      subPath: nginx.conf
    {{- range $p.volumes.emptyDirs }}
    - mountPath: {{ .mountPath }}
      name: {{ .name }}
    {{- end }}
{{- end -}}

{{- define "n8n-mcp.proxyVolumes" -}}
{{- $p := .Values.proxy -}}
volumes:
  - configMap:
      name: {{ include "n8n-mcp.proxyConfigName" . }}
    name: {{ $p.volumes.configName }}
  {{- range $p.volumes.emptyDirs }}
  - emptyDir: {}
    name: {{ .name }}
  {{- end }}
{{- end -}}

{{/*
metadata.labels of every object: the standard managed-by label (Helm sets it on
everything it manages, so rendering it keeps `kubectl diff` clean after a
takeover) plus commonLabels plus the per-object extras.
*/}}
{{- define "n8n-mcp.objectLabels" -}}
{{- $extra := default (dict) .extra -}}
{{- $common := default (dict) .ctx.Values.commonLabels -}}
{{ toYaml (merge (dict) $extra $common (dict "app.kubernetes.io/managed-by" .ctx.Release.Service)) }}
{{- end -}}
