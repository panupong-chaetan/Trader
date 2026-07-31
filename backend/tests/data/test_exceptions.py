from data.exceptions import DataIntegrityError


def test_data_integrity_error_carries_range_and_message() -> None:
    error = DataIntegrityError(
        "large gap detected",
        start="2024-01-01T00:00:00+00:00",
        end="2024-01-02T00:00:00+00:00",
    )

    assert str(error) == "large gap detected"
    assert error.start == "2024-01-01T00:00:00+00:00"
    assert error.end == "2024-01-02T00:00:00+00:00"


def test_data_integrity_error_defaults_range_to_none() -> None:
    error = DataIntegrityError("conflicting duplicate rows")

    assert error.start is None
    assert error.end is None
