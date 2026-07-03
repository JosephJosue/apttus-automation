"""Join engines replicating the Power Query delta idioms.

Power Query's joins match null with null, so join columns are compared via
a sentinel that makes None deterministic. Row order of the left table is
always preserved (Table.NestedJoin keeps it)."""

from __future__ import annotations

import pandas as pd

from .normalize import map_column

_NULL = "\x00<null>"


def _isnull(v) -> bool:
    return v is None or v != v  # None or NaN


def _key_tuples(df: pd.DataFrame, on: list[str], normalize: dict | None = None):
    cols = []
    for c in on:
        s = df[c]
        if normalize and c in normalize:
            s = map_column(s, normalize[c])
        cols.append([_NULL if _isnull(v) else v for v in s])
    return list(zip(*cols)) if cols and len(df) else []


def left_anti(new: pd.DataFrame, old: pd.DataFrame, on: list[str],
              right_on: list[str] | None = None,
              normalize: dict | None = None) -> pd.DataFrame:
    """Rows of `new` with no match in `old` on the given columns
    (Table.NestedJoin JoinKind.LeftAnti). `right_on` names the old-side
    columns when they differ (position-matched to `on`). `normalize` maps a
    left-side column name to a function applied to both sides' values for
    matching only — output rows keep their original values."""
    right_on = right_on or on
    if len(new) == 0:
        return new.copy()
    norm_right = None
    if normalize:
        norm_right = {r: normalize[l] for l, r in zip(on, right_on) if l in normalize}
    old_keys = set(_key_tuples(old, right_on, norm_right))
    mask = [k not in old_keys for k in _key_tuples(new, on, normalize)]
    return new[pd.Series(mask, index=new.index)].copy()


def inner_semi(new: pd.DataFrame, scope: pd.DataFrame, left_on: list[str],
               right_on: list[str] | None = None) -> pd.DataFrame:
    """Rows of `new` whose key appears in `scope` (the M idiom of an inner
    NestedJoin against a de-duplicated single-column table, then dropping
    the nested column). Left row order is preserved and no fan-out can
    occur because only membership is tested."""
    right_on = right_on or left_on
    if len(new) == 0:
        return new.copy()
    scope_keys = set(_key_tuples(scope, right_on))
    mask = [k in scope_keys for k in _key_tuples(new, left_on)]
    return new[pd.Series(mask, index=new.index)].copy()


def distinct(df: pd.DataFrame, columns: list[str], rename: dict | None = None) -> pd.DataFrame:
    """Table.SelectColumns + Table.Distinct (keeps first occurrence order)."""
    out = df[columns].copy()
    if rename:
        out = out.rename(columns=rename)
    key = [tuple(_NULL if _isnull(v) else v for v in row) for row in out.itertuples(index=False)]
    return out[~pd.Series(key, index=out.index).duplicated()].copy()
