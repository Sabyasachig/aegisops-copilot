from __future__ import annotations

from aegisops_api.events import build_incident_event, incident_events_channel


def test_incident_events_channel_format() -> None:
    assert incident_events_channel("INC-2048") == "aegisops:incident:INC-2048:events"


def test_build_incident_event_contains_type_and_timestamp() -> None:
    payload = build_incident_event("node_started", incident_id="INC-2048", node="assess")
    assert payload["event"] == "node_started"
    assert payload["incident_id"] == "INC-2048"
    assert payload["node"] == "assess"
    assert "ts" in payload