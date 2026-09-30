"""Tests for the AegisOps Helm chart (Issue #20).

Runs `helm lint` and `helm template` against the packaged chart when the
`helm` CLI is available on `PATH`. Skips cleanly on environments without
`helm` installed (e.g. some CI jobs) so the API test suite stays green.

The chart lives at ``deploy/helm/aegisops/`` relative to the repository
root. These tests only verify chart *structure*: they do not require a
Kubernetes cluster.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART_DIR = REPO_ROOT / "deploy" / "helm" / "aegisops"
DEV_VALUES = CHART_DIR / "examples" / "values-dev.yaml"


needs_helm = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason="helm CLI not installed on PATH",
)


# ---------------------------------------------------------------------------
# Static / offline checks — always run.
# ---------------------------------------------------------------------------


def test_chart_yaml_exists_with_required_fields() -> None:
    chart_yaml = CHART_DIR / "Chart.yaml"
    assert chart_yaml.is_file(), f"missing {chart_yaml}"
    parsed = yaml.safe_load(chart_yaml.read_text())
    assert parsed["apiVersion"] == "v2"
    assert parsed["name"] == "aegisops"
    assert parsed["type"] == "application"
    assert parsed["version"]
    assert parsed["appVersion"]


def test_expected_template_files_present() -> None:
    templates = CHART_DIR / "templates"
    required = {
        "_helpers.tpl",
        "configmap.yaml",
        "secret.yaml",
        "serviceaccount.yaml",
        "api-deployment.yaml",
        "api-service.yaml",
        "api-hpa.yaml",
        "api-pdb.yaml",
        "worker-deployment.yaml",
        "worker-hpa.yaml",
        "web-deployment.yaml",
        "web-service.yaml",
        "web-hpa.yaml",
        "web-pdb.yaml",
        "ingress.yaml",
        "postgres-statefulset.yaml",
        "redis-deployment.yaml",
        "NOTES.txt",
    }
    present = {p.name for p in templates.iterdir() if p.is_file()}
    missing = required - present
    assert not missing, f"missing chart templates: {missing}"


def test_values_yaml_has_new_settings_fields() -> None:
    """Ensure values.yaml exposes the settings we added in Issues #17/#18."""
    values = yaml.safe_load((CHART_DIR / "values.yaml").read_text())
    assert values["config"]["publicBaseUrl"]
    assert "slackNotificationsEnabled" in values["config"]
    assert "webhookSecret" in values["secret"]["data"]


# ---------------------------------------------------------------------------
# Helm-driven checks — skipped when helm is not on PATH.
# ---------------------------------------------------------------------------


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


@needs_helm
def test_helm_lint_passes() -> None:
    result = _run(["helm", "lint", str(CHART_DIR)])
    assert result.returncode == 0, (
        f"helm lint failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "0 chart(s) failed" in result.stdout


@needs_helm
def test_helm_template_default_renders_expected_kinds() -> None:
    result = _run(["helm", "template", "aegisops", str(CHART_DIR)])
    assert result.returncode == 0, result.stderr
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    kinds = {d.get("kind") for d in docs}
    for expected in {
        "ConfigMap",
        "Secret",
        "ServiceAccount",
        "Deployment",
        "Service",
        "HorizontalPodAutoscaler",
        "PodDisruptionBudget",
    }:
        assert expected in kinds, f"missing kind {expected} in default render"

    # API/worker/web deployments are all present by default.
    deployments = {d["metadata"]["name"] for d in docs if d.get("kind") == "Deployment"}
    assert any(name.endswith("-api") for name in deployments)
    assert any(name.endswith("-worker") for name in deployments)
    assert any(name.endswith("-web") for name in deployments)


@needs_helm
def test_helm_template_dev_values_enables_postgres_and_redis() -> None:
    result = _run(
        ["helm", "template", "aegisops", str(CHART_DIR), "-f", str(DEV_VALUES)]
    )
    assert result.returncode == 0, result.stderr
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    kinds = [d.get("kind") for d in docs]

    # Dev values disable HPAs / PDBs / Ingress …
    assert "HorizontalPodAutoscaler" not in kinds
    assert "PodDisruptionBudget" not in kinds
    assert "Ingress" not in kinds

    # … and enable in-cluster Postgres StatefulSet + Redis Deployment.
    stateful_sets = [d for d in docs if d.get("kind") == "StatefulSet"]
    assert stateful_sets, "expected in-cluster postgres StatefulSet"
    assert any("postgres" in ss["metadata"]["name"] for ss in stateful_sets)

    deployments = {d["metadata"]["name"] for d in docs if d.get("kind") == "Deployment"}
    assert any(name.endswith("-redis") for name in deployments)


@needs_helm
def test_api_deployment_probes_target_health_endpoint() -> None:
    result = _run(["helm", "template", "aegisops", str(CHART_DIR)])
    assert result.returncode == 0, result.stderr
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    api = next(
        d
        for d in docs
        if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-api")
    )
    container = api["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/api/health"
    assert container["readinessProbe"]["httpGet"]["path"] == "/api/health"
    # Env vars come from ConfigMap + Secret via envFrom.
    env_from = container["envFrom"]
    assert any("configMapRef" in ef for ef in env_from)
    assert any("secretRef" in ef for ef in env_from)


@needs_helm
def test_secret_is_rendered_by_default_with_placeholder_keys() -> None:
    result = _run(["helm", "template", "aegisops", str(CHART_DIR)])
    assert result.returncode == 0, result.stderr
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    secret = next(d for d in docs if d.get("kind") == "Secret")
    assert "AIOPS_JWT_SECRET_KEY" in secret["stringData"]
    assert "AIOPS_INITIAL_ADMIN_PASSWORD" in secret["stringData"]
