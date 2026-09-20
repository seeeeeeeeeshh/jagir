from app.core.errors import humanize_exception


def test_known_network_pattern_is_humanized():
    assert "internet connection" in humanize_exception(Exception("net::ERR_CONNECTION_RESET"))


def test_known_timeout_pattern_is_humanized():
    assert "too long" in humanize_exception(TimeoutError("Timeout 30000ms exceeded"))


def test_unrecognized_exception_falls_back_to_first_line_not_full_traceback():
    exc = Exception("some very specific internal detail\nmore stack info here")
    assert humanize_exception(exc) == "some very specific internal detail"


def test_empty_message_falls_back_to_exception_class_name():
    assert humanize_exception(ValueError()) == "ValueError"
