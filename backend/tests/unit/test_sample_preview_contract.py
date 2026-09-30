from fastapi import FastAPI


def test_persisted_rule_preview_is_an_authenticated_read_contract(app: FastAPI) -> None:
    operation = app.openapi()["paths"]["/api/topics/sample-preview"]["post"]
    assert operation["operationId"] == "previewMonitorTopicSamples"
    assert operation["security"]
    assert set(operation["responses"]) == {"200", "401", "403", "422", "500"}
