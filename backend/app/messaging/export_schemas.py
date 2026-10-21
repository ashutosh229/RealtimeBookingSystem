"""Write docs/events/<EventType>.schema.json.

Run from the host: python -m app.messaging.export_schemas
"""

from pathlib import Path

from app.messaging.events import EVENT_TYPES, schema_json

OUT = Path(__file__).resolve().parents[3] / "docs" / "events"

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, cls in EVENT_TYPES.items():
        (OUT / f"{name}.schema.json").write_text(schema_json(cls), encoding="utf-8")
    print(f"wrote {len(EVENT_TYPES)} schemas to {OUT}")
