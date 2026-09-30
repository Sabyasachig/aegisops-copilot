"""Tests for the managed database & cache migration path (Issue #21).

Covers three orthogonal areas:

1. **Settings surface** — asserts that the application still exposes
   ``AIOPS_DATABASE_URL`` / ``AIOPS_REDIS_URL`` (plus Celery and rate-limit
   variants) as the sole URL surface. Regressions here would break the
   "URLs are the only required change" contract with managed services.
2. **Documentation** — verifies ``docs/managed-services.md`` exists and
   walks through both AWS RDS + ElastiCache and GCP Cloud SQL +
   Memorystore.
3. **Terraform module** — sanity-checks that
   ``deploy/terraform/aws/`` contains the expected files and outputs
   ``database_url`` / ``redis_url`` / ``celery_broker_url`` /
   ``celery_result_backend`` / ``rate_limit_storage_uri`` (the exact
   variables consumed by the Helm secret).
4. **Helm secret** — asserts ``AIOPS_RATE_LIMIT_STORAGE_URI`` is now
   rendered by the chart secret (added in this issue) so managed installs
   can point rate-limit storage at the same managed Redis.

These are all static / offline checks — no Terraform provider download and
no live cluster required.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_FILE = REPO_ROOT / "docs" / "managed-services.md"
TERRAFORM_DIR = REPO_ROOT / "deploy" / "terraform" / "aws"
CHART_DIR = REPO_ROOT / "deploy" / "helm" / "aegisops"

needs_helm = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason="helm CLI not installed on PATH",
)


# ---------------------------------------------------------------------------
# 1. Settings surface — the DATABASE_URL / REDIS_URL contract.
# ---------------------------------------------------------------------------


def test_settings_expose_managed_url_env_vars() -> None:
    """`AIOPS_DATABASE_URL` and friends must be the only URLs required.

    We check the *class defaults* (not an instantiated Settings) because
    the test suite's conftest overrides some env vars (e.g. sets
    ``AIOPS_RATE_LIMIT_STORAGE_URI=memory://`` for in-process rate-limit
    isolation). The class defaults represent the production contract.
    """
    from aegisops_api.settings import Settings

    fields = Settings.model_fields
    assert fields["database_url"].default.startswith(
        ("postgresql://", "postgresql+asyncpg://")
    )
    assert fields["redis_url"].default.startswith(("redis://", "rediss://"))
    assert fields["celery_broker_url"].default.startswith(("redis://", "rediss://"))
    assert fields["celery_result_backend"].default.startswith(("redis://", "rediss://"))
    assert fields["rate_limit_storage_uri"].default.startswith(
        ("redis://", "rediss://")
    )


def test_settings_use_aiops_env_prefix() -> None:
    from aegisops_api.settings import Settings

    prefix = Settings.model_config.get("env_prefix")
    assert prefix == "AIOPS_", (
        "Settings.env_prefix must stay `AIOPS_` — the Helm chart, "
        "docs/managed-services.md and the Terraform module all depend on it."
    )


# ---------------------------------------------------------------------------
# 2. Documentation — migration guide.
# ---------------------------------------------------------------------------


def test_managed_services_doc_covers_aws_and_gcp() -> None:
    assert DOCS_FILE.is_file(), f"missing {DOCS_FILE}"
    text = DOCS_FILE.read_text()

    # Both cloud paths must be documented.
    assert "AWS RDS" in text or "RDS PostgreSQL" in text
    assert "ElastiCache" in text
    assert "Cloud SQL" in text
    assert "Memorystore" in text

    # The env-var contract table must list every URL variable.
    for env_var in [
        "AIOPS_DATABASE_URL",
        "AIOPS_REDIS_URL",
        "AIOPS_CELERY_BROKER_URL",
        "AIOPS_CELERY_RESULT_BACKEND",
        "AIOPS_RATE_LIMIT_STORAGE_URI",
    ]:
        assert env_var in text, f"docs/managed-services.md missing {env_var}"


# ---------------------------------------------------------------------------
# 3. Terraform module.
# ---------------------------------------------------------------------------


def test_terraform_aws_module_structure() -> None:
    assert TERRAFORM_DIR.is_dir(), f"missing {TERRAFORM_DIR}"
    expected = {
        "README.md",
        "versions.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "example.tfvars",
        ".gitignore",
    }
    present = {p.name for p in TERRAFORM_DIR.iterdir() if p.is_file()}
    missing = expected - present
    assert not missing, f"terraform module missing files: {sorted(missing)}"


def test_terraform_outputs_expose_all_aiops_urls() -> None:
    outputs_tf = (TERRAFORM_DIR / "outputs.tf").read_text()
    for name in [
        "database_url",
        "redis_url",
        "celery_broker_url",
        "celery_result_backend",
        "rate_limit_storage_uri",
        "secrets_manager_arn",
    ]:
        assert f'output "{name}"' in outputs_tf, f"outputs.tf missing `{name}`"


def test_terraform_main_provisions_rds_and_elasticache() -> None:
    main_tf = (TERRAFORM_DIR / "main.tf").read_text()
    assert 'resource "aws_db_instance" "postgres"' in main_tf
    assert 'resource "aws_elasticache_replication_group" "redis"' in main_tf
    assert 'resource "aws_secretsmanager_secret" "urls"' in main_tf
    # Postgres must use the asyncpg SQLAlchemy driver.
    assert "postgresql+asyncpg" in main_tf
    # Encryption in transit toggles the redis vs rediss scheme.
    assert "redis_transit_encryption_enabled" in main_tf


def test_terraform_variables_require_multi_az_subnets() -> None:
    variables_tf = (TERRAFORM_DIR / "variables.tf").read_text()
    # The subnet validation enforces >= 2 AZs to keep the module honest
    # about Multi-AZ readiness.
    assert "private_subnet_ids" in variables_tf
    assert "length(var.private_subnet_ids) >= 2" in variables_tf


# ---------------------------------------------------------------------------
# 4. Helm secret — rate-limit storage URI wiring.
# ---------------------------------------------------------------------------


def test_helm_secret_exposes_rate_limit_storage_uri() -> None:
    secret_tpl = (CHART_DIR / "templates" / "secret.yaml").read_text()
    values = (CHART_DIR / "values.yaml").read_text()
    assert ".Values.secret.data.rateLimitStorageUri" in secret_tpl
    assert "AIOPS_RATE_LIMIT_STORAGE_URI" in secret_tpl
    assert "rateLimitStorageUri" in values


@needs_helm
def test_helm_template_wires_rate_limit_storage_uri_when_set() -> None:
    """Verify the rendered Secret picks up rateLimitStorageUri from values."""
    proc = subprocess.run(
        [
            "helm",
            "template",
            "aegisops",
            str(CHART_DIR),
            "--set",
            "secret.data.rateLimitStorageUri=rediss://elasticache.example:6379/3",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "AIOPS_RATE_LIMIT_STORAGE_URI" in proc.stdout
    assert "rediss://elasticache.example:6379/3" in proc.stdout


@needs_helm
def test_helm_template_omits_rate_limit_storage_uri_when_blank() -> None:
    """When left blank, the Secret must omit the key entirely (not emit empty string)."""
    proc = subprocess.run(
        ["helm", "template", "aegisops", str(CHART_DIR)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "AIOPS_RATE_LIMIT_STORAGE_URI" not in proc.stdout
