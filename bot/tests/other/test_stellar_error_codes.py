from other.stellar_error_codes import get_stellar_error_message


def test_reports_failing_operation_number_after_successful_operations() -> None:
    result_codes = {
        "transaction": "tx_failed",
        "operations": ["op_success", "op_success", "op_low_reserve"],
    }

    assert get_stellar_error_message(result_codes) == (
        "Operation 3: op_low_reserve — "
        "Not enough XLM to meet the minimum reserve"
    )
