from inspect import signature

from ai.services import load_saved_ai_call_in_transaction, recover_abandoned_ai_calls_in_transaction


def test_saved_call_and_abandoned_recovery_are_caller_transaction_contracts():
    assert set(signature(load_saved_ai_call_in_transaction).parameters) == {
        "session",
        "owner_id",
        "call_id",
        "job_id",
        "purpose",
    }
    assert set(signature(recover_abandoned_ai_calls_in_transaction).parameters) == {
        "session",
        "owner_id",
        "job_id",
        "current_epoch",
        "now",
    }
