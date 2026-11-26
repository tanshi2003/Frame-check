from app.main import timestamp, clean_text


def test_timestamp_formats_hours_minutes_seconds():
    assert timestamp(3661.25) == "01:01:01.250"


def test_clean_text_collapses_whitespace():
    assert clean_text("Hello  \\n world") == "Hello world"
