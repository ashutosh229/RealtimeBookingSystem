from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate

SPEC = Path(__file__).resolve().parents[3] / "docs" / "openapi.yaml"
pytestmark = pytest.mark.skipif(not SPEC.exists(), reason="docs/openapi.yaml not present")


def load() -> dict:
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


def test_spec_is_valid_openapi():
    validate(load())


def test_operation_ids_present_and_unique():
    ids = [
        op["operationId"]
        for path in load()["paths"].values()
        for method, op in path.items()
        if method in {"get", "post", "patch", "put", "delete"}
    ]
    assert len(ids) == len(set(ids))
