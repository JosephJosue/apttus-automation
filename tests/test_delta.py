import pandas as pd

from apttus_delta.delta import distinct, inner_semi, left_anti
from apttus_delta.normalize import normalize_number


def _df(rows, cols):
    return pd.DataFrame(rows, columns=cols, dtype=object)


def test_left_anti_preserves_order_and_duplicates():
    new = _df([["a", 1], ["b", 2], ["a", 3], ["c", 4]], ["k", "v"])
    old = _df([["b", 9]], ["k", "v"])
    out = left_anti(new, old, ["k"])
    assert list(out["k"]) == ["a", "a", "c"]
    assert list(out["v"]) == [1, 3, 4]


def test_left_anti_matches_nulls_like_power_query():
    new = _df([[None, "x"], ["a", "y"]], ["k", "v"])
    old = _df([[None, "z"]], ["k", "v"])
    out = left_anti(new, old, ["k"])
    assert list(out["v"]) == ["y"]  # the null-key row matched the null-key row


def test_left_anti_right_on():
    new = _df([["a"], ["b"]], ["left_key"])
    old = _df([["b"]], ["right_key"])
    out = left_anti(new, old, ["left_key"], right_on=["right_key"])
    assert list(out["left_key"]) == ["a"]


def test_left_anti_normalize_applies_to_both_sides():
    new = _df([["k1", "2.0"], ["k2", "5"]], ["k", "qty"])
    old = _df([["k1", "2"], ["k2", "4"]], ["k", "qty"])
    out = left_anti(new, old, ["k", "qty"], normalize={"qty": normalize_number})
    assert list(out["k"]) == ["k2"]  # 2.0 == 2 after normalization


def test_inner_semi_no_fanout():
    new = _df([["m1", 1], ["m2", 2], ["m1", 3]], ["model", "v"])
    scope = _df([["m1"], ["m1"]], ["model"])  # duplicates in scope must not fan out
    out = inner_semi(new, scope, ["model"])
    assert list(out["v"]) == [1, 3]


def test_distinct_keeps_first_occurrence_order():
    df = _df([["b", "1"], ["a", "2"], ["b", "1"]], ["x", "y"])
    out = distinct(df, ["x", "y"])
    assert out.values.tolist() == [["b", "1"], ["a", "2"]]
    renamed = distinct(df, ["x"], rename={"x": "Changed Models"})
    assert list(renamed.columns) == ["Changed Models"]
    assert list(renamed["Changed Models"]) == ["b", "a"]
