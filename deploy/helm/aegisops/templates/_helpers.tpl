{{/*
Expand the name of the chart.
*/}}
{{- define "aegisops.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully-qualified app name — used as the base name for every rendered object.
Truncated at 63 chars to satisfy DNS-1123.
*/}}
{{- define "aegisops.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart label used in `helm.sh/chart` selector.
*/}}
{{- define "aegisops.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels attached to every rendered object.
*/}}
{{- define "aegisops.labels" -}}
helm.sh/chart: {{ include "aegisops.chart" . }}
{{ include "aegisops.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: aegisops
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
Selector labels (workload-agnostic).
*/}}
{{- define "aegisops.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aegisops.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Per-component labels and selectors. Callers pass the component name (api,
worker, web, postgres, redis).
Usage: {{- include "aegisops.componentLabels" (dict "root" . "component" "api") -}}
*/}}
{{- define "aegisops.componentLabels" -}}
{{ include "aegisops.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "aegisops.componentSelectorLabels" -}}
{{ include "aegisops.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
Resource name helpers per component.
*/}}
{{- define "aegisops.apiName" -}}
{{- printf "%s-api" (include "aegisops.fullname" .) -}}
{{- end -}}

{{- define "aegisops.workerName" -}}
{{- printf "%s-worker" (include "aegisops.fullname" .) -}}
{{- end -}}

{{- define "aegisops.webName" -}}
{{- printf "%s-web" (include "aegisops.fullname" .) -}}
{{- end -}}

{{- define "aegisops.postgresName" -}}
{{- printf "%s-postgres" (include "aegisops.fullname" .) -}}
{{- end -}}

{{- define "aegisops.redisName" -}}
{{- printf "%s-redis" (include "aegisops.fullname" .) -}}
{{- end -}}

{{- define "aegisops.configMapName" -}}
{{- printf "%s-config" (include "aegisops.fullname" .) -}}
{{- end -}}

{{/*
Secret name — either the chart-managed secret or an existing one that the
operator supplied via values.
*/}}
{{- define "aegisops.secretName" -}}
{{- if .Values.secret.existingSecret -}}
{{- .Values.secret.existingSecret -}}
{{- else -}}
{{- printf "%s-secret" (include "aegisops.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
ServiceAccount name (respects `serviceAccount.create`/`.name`).
*/}}
{{- define "aegisops.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "aegisops.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image tag defaulting — uses Chart.appVersion when values leave the tag blank.
Usage: {{ include "aegisops.image" (dict "img" .Values.image.api "root" .) }}
*/}}
{{- define "aegisops.image" -}}
{{- $registry := .root.Values.global.imageRegistry -}}
{{- $tag := default .root.Chart.AppVersion .img.tag -}}
{{- printf "%s/%s:%s" $registry .img.repository $tag -}}
{{- end -}}

{{/*
imagePullSecrets rendered from global.imagePullSecrets.
*/}}
{{- define "aegisops.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
  {{- range . }}
  - name: {{ . }}
  {{- end }}
{{- end }}
{{- end -}}
