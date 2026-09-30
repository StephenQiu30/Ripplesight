from fastapi import FastAPI


def test_persisted_rule_preview_is_a_csrf_protected_anonymous_contract(app: FastAPI) -> None:
    operation = app.openapi()["paths"]["/api/topics/sample-preview"]["post"]
    assert operation["operationId"] == "previewMonitorTopicSamples"
    assert not operation.get("security")
    assert set(operation["responses"]) == {"200", "403", "422", "500", "503"}
