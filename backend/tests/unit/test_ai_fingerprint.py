from ai.services import _input_fingerprint


def test_instruction_changes_are_part_of_the_paid_call_input_identity() -> None:
    common = {
        "model": "model",
        "prompt_version": "v1",
        "prompt": "material",
        "output_schema": {"type": "object"},
    }
    assert _input_fingerprint(**common, instructions="判断相关性") != _input_fingerprint(
        **common, instructions="判断精选价值"
    )


def test_field_boundaries_cannot_collide_by_concatenation() -> None:
    common = {"prompt": "material", "output_schema": {"type": "object"}}
    assert _input_fingerprint(model="ab", prompt_version="c", **common) != _input_fingerprint(
        model="a", prompt_version="bc", **common
    )
