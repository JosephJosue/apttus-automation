import pandas as pd
import pytest

from apttus_delta.normalize import (
    NULL_ONLY,
    NULL_OR_EMPTY,
    PROPAGATE,
    DataFidelityError,
    key_series,
    nbsp_trim_end,
    normalize_number,
    reformat_spm_date,
    round_sig,
    to_text,
)


def test_to_text_basic():
    assert to_text(None) is None
    assert to_text("x ") == "x "          # no trimming
    assert to_text("a\xa0") == "a\xa0"    # NBSP preserved
    assert to_text(True) == "true"    # M's logical->text is lowercase
    assert to_text(False) == "false"
    assert to_text(120) == "120"
    assert to_text(120.0) == "120"        # integral floats lose the .0 like PQ
    assert to_text(187.970833333333) == "187.970833333333"  # shortest round-trip
    assert to_text(989607004541.0) == "989607004541"        # codes never go scientific


def test_to_text_rejects_datetimes():
    from datetime import datetime

    with pytest.raises(DataFidelityError):
        to_text(datetime(2026, 3, 9))


def test_normalize_number():
    assert normalize_number("2") == "2"
    assert normalize_number("2.0") == "2"
    assert normalize_number("2.00") == "2"
    assert normalize_number("187.970833333333") == "187.970833333333"
    assert normalize_number("abc") == "abc"   # non-numeric text unchanged
    assert normalize_number("") is None
    assert normalize_number(None) is None


def test_round_sig():
    assert round_sig(187.97083333333299, 15) == round_sig(187.970833333333, 15)
    assert round_sig(0, 15) == 0


def test_nbsp_trim_end():
    assert nbsp_trim_end("Upsell to Plus\xa0") == "Upsell to Plus"
    assert nbsp_trim_end("a\xa0b  ") == "a b"
    assert nbsp_trim_end(None) is None
    assert nbsp_trim_end(" lead kept ") == " lead kept"


def test_key_policies():
    df = pd.DataFrame({"a": ["x", None, ""], "b": ["y", "y", "y"]}, dtype=object)
    assert list(key_series(df, ["a", "b"], NULL_OR_EMPTY)) == ["x_y", "null_y", "null_y"]
    assert list(key_series(df, ["a", "b"], NULL_ONLY)) == ["x_y", "null_y", "_y"]
    assert list(key_series(df, ["a", "b"], PROPAGATE)) == ["x_y", None, "_y"]


def test_key_custom_separator():
    df = pd.DataFrame({"a": ["G"], "b": ["C"]}, dtype=object)
    assert list(key_series(df, ["a", "b"], PROPAGATE, sep=" - ")) == ["G - C"]


def test_reformat_spm_date():
    assert reformat_spm_date("09-03-2026 12:00:00 AM") == "2026-03-09T00:00:00.000+0000"
    assert reformat_spm_date("09-03-2026 12:00:00 PM") == "2026-03-09T12:00:00.000+0000"
    assert reformat_spm_date("09-03-2026 01:30:05 PM") == "2026-03-09T13:30:05.000+0000"
    assert reformat_spm_date("09-03-2026 09:00:00 AM") == "2026-03-09T09:00:00.000+0000"
    assert reformat_spm_date(None) is None
