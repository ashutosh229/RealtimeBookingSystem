"""Fails CI when the FastAPI app and docs/openapi.yaml disagree (routes, params, schemas, error codes)."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs" / "openapi.yaml"
APP_DIR = ROOT / "backend" / "app"
pytestmark = pytest.mark.skipif(not SPEC.exists(), reason="docs/openapi.yaml not present")

HTTP = {"get", "post", "put", "patch", "delete"}

# Documented in the contract but not built yet. Shrinks as phases land; a stale entry fails the test.
NOT_YET = set()

# Documented query params not built yet. Empty now that geo search and the free-window filter exist.
PARAMS_NOT_YET: dict[tuple[str, str], set[str]] = {}

SCHEMA_PAIRS = {  # yaml schema -> pydantic model
    "RegisterRequest": "RegisterRequest",
    "LoginRequest": "LoginRequest",
    "RefreshRequest": "RefreshRequest",
    "TokenPair": "TokenPair",
    "User": "UserOut",
    "Resource": "ResourceOut",
    "ResourceCreate": "ResourceCreate",
    "ResourceUpdate": "ResourceUpdate",
    "ResourcePage": "ResourcePage",
    "Availability": "AvailabilityOut",
    "BookingCreate": "BookingCreate",
    "Booking": "BookingDetail",
    "BookingPage": "BookingPage",
    "WaitlistEntry": "WaitlistEntryOut",
    "AllocationRecord": "AllocationRecordOut",
    "MetricsSummary": "MetricsSummaryOut",
    "AttemptRecord": "AttemptOut",
    "RejectionSummary": "RejectionSummaryOut",
    "ChanceSummary": "ChanceSummaryOut",
    "MyChance": "MyChanceOut",
    "Notification": "NotificationOut",
    "NotificationList": "NotificationList",
}


def spec() -> dict:
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


def spec_ops() -> dict:
    return {
        (m, p): op for p, item in spec()["paths"].items() for m, op in item.items() if m in HTTP
    }


def app_openapi() -> dict:
    from app.main import app

    return app.openapi()


def app_ops() -> set:
    # Read the app's own OpenAPI paths, not app.routes: newer FastAPI keeps included routers as
    # private wrapper objects there instead of flattening them into routes.
    return {
        (m, path[len("/v1") :])
        for path, item in app_openapi()["paths"].items()
        if path.startswith("/v1/")
        for m in item
        if m in HTTP
    }


def deref(root: dict, node: dict) -> dict:
    while "$ref" in node:
        target = root
        for part in node["$ref"].lstrip("#/").split("/"):
            target = target[part]
        node = target
    return node


def test_implemented_routes_are_documented():
    undocumented = app_ops() - set(spec_ops())
    assert not undocumented, f"routes missing from docs/openapi.yaml: {sorted(undocumented)}"


def test_documented_routes_are_implemented_or_listed():
    missing = set(spec_ops()) - app_ops() - NOT_YET
    assert not missing, (
        f"documented but not implemented (add to NOT_YET if intended): {sorted(missing)}"
    )


def test_not_yet_list_has_no_stale_entries():
    assert NOT_YET <= set(spec_ops()), "NOT_YET lists operations the spec does not document"
    assert not NOT_YET & app_ops(), (
        f"now implemented, remove from NOT_YET: {sorted(NOT_YET & app_ops())}"
    )


def test_parameters_match_the_contract():
    root, gen, problems = spec(), app_openapi(), []
    for (method, path), op in spec_ops().items():
        if (method, path) not in app_ops():
            continue
        documented = {
            (deref(root, p)["name"], deref(root, p)["in"]) for p in op.get("parameters", [])
        }
        documented -= {(n, "query") for n in PARAMS_NOT_YET.get((method, path), set())}
        built = {
            (p["name"], p["in"]) for p in gen["paths"]["/v1" + path][method].get("parameters", [])
        }
        if documented != built:
            problems.append(
                f"{method.upper()} {path}: only in spec {sorted(documented - built)}, "
                f"only in app {sorted(built - documented)}"
            )
    assert not problems, "\n".join(problems)


def test_schema_properties_match_the_contract():
    root, gen, problems = spec(), app_openapi()["components"]["schemas"], []
    for yaml_name, model in SCHEMA_PAIRS.items():
        built = next(
            (gen[n] for n in (model, f"{model}-Output", f"{model}-Input") if n in gen),
            None,
        )
        if built is None:
            problems.append(f"{yaml_name}: model {model} not found in the generated schema")
            continue
        documented = set(root["components"]["schemas"][yaml_name]["properties"])
        if documented != set(built["properties"]):
            problems.append(
                f"{yaml_name}: only in spec {sorted(documented - set(built['properties']))}, "
                f"only in app {sorted(set(built['properties']) - documented)}"
            )
    assert not problems, "\n".join(problems)


def test_every_error_code_in_source_is_in_the_contract():
    patterns = [
        r'ApiError\(\s*\d+,\s*"([A-Z_]+)"',
        r'"code":\s*"([A-Z_]+)"',
        r'_body\(request,\s*"([A-Z_]+)"',
        r'\d{3}:\s*"([A-Z_]+)"',
    ]
    found: set[str] = set()
    for f in APP_DIR.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for p in patterns:
            found |= set(re.findall(p, text))
    assert len(found) >= 15, f"code scanner looks broken, found only {sorted(found)}"
    documented = set(
        spec()["components"]["schemas"]["Error"]["properties"]["error"]["properties"]["code"][
            "enum"
        ]
    )
    assert not found - documented, (
        f"error codes missing from the contract: {sorted(found - documented)}"
    )
