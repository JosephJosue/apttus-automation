"""Value-level normalization mirroring what Power Query sees.

Every value the delta engine compares or keys passes through here. The
guiding rule is to reproduce the M code exactly: no extra trimming, no
dtype guessing, case-sensitive comparisons. NBSP and trailing spaces are
real data except where a query has an explicit TrimEnd step.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time

NBSP = "\xa0"


def map_column(series, fn):
    """Apply fn to a column preserving None (Series.map would coerce a
    returned None to NaN, which then fails null-matching and writes as a
    float in Excel)."""
    import pandas as pd

    return pd.Series([fn(v) for v in series], index=series.index, dtype=object)


class DataFidelityError(ValueError):
    """A source value cannot be converted without guessing (e.g. a real
    datetime cell where the pipeline expects text)."""


def to_text(value):
    """Convert a raw cell value to the text Power Query's `type text`
    conversion would produce. None stays None (null)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        # M's logical-to-text conversion is lowercase; the queries that need
        # TRUE/FALSE apply an explicit Text.Upper / ReplaceValue afterwards.
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return float_to_text(value)
    if isinstance(value, (datetime, date, time)):
        raise DataFidelityError(
            f"unexpected date/time cell {value!r}; the source files store dates as "
            "text and the pipeline refuses to guess a format"
        )
    return str(value)


def float_to_text(x: float) -> str:
    """Shortest round-trip decimal text, matching both what Excel stores in
    the sheet XML and M's default number-to-text conversion."""
    if x == int(x) and abs(x) < 1e16:
        return str(int(x))
    return repr(x)


def normalize_number(text):
    """Canonicalize a numeric-looking text value so '2', '2.0' and '2.00'
    compare equal across the Excel side and a Salesforce CSV export.
    Non-numeric text is returned unchanged; None stays None."""
    if text is None:
        return None
    s = str(text).strip()
    if s == "":
        return None
    try:
        x = float(s)
    except ValueError:
        return text
    if math.isnan(x) or math.isinf(x):
        return text
    return float_to_text(x)


def round_sig(x: float, digits: int = 15) -> float:
    """Round to N significant digits (M's RoundToSigDigits helper in the
    iTest4 Service Price Matrix workbook). Uses banker's rounding like
    Number.Round."""
    if x == 0:
        return 0.0
    p = math.floor(math.log10(abs(x)))
    return round(x, digits - 1 - p)


def nbsp_trim_end(text):
    """Replace NBSP with a regular space then trim trailing whitespace —
    the explicit two-step cleanup some translation queries apply to their
    translated-value columns (and nowhere else)."""
    if text is None:
        return None
    return str(text).replace(NBSP, " ").rstrip(" \t\r\n")


# Key null policies (see build_key)
NULL_OR_EMPTY = "null_or_empty"  # null or "" -> the literal text "null"
NULL_ONLY = "null_only"          # null -> "null"; "" stays ""
PROPAGATE = "propagate"          # any null component -> whole key is null (M's `&`)


def key_series(df, columns, policy, sep: str = "_"):
    """Build a composite key column exactly like the M queries do."""
    import pandas as pd

    if policy not in (NULL_OR_EMPTY, NULL_ONLY, PROPAGATE):  # pragma: no cover
        raise ValueError(f"unknown key policy {policy!r}")

    def one(values):
        parts = []
        for v in values:
            if policy == NULL_OR_EMPTY:
                parts.append("null" if v is None or v == "" else str(v))
            elif policy == NULL_ONLY:
                parts.append("null" if v is None else str(v))
            else:  # PROPAGATE: M's `&` returns null if any operand is null
                if v is None:
                    return None
                parts.append(str(v))
        return sep.join(parts)

    keys = [one(row) for row in zip(*(df[c] for c in columns))] if len(df) else []
    return pd.Series(keys, index=df.index, dtype=object)


def reformat_spm_date(text):
    """`DD-MM-YYYY hh:mm:ss AM/PM` -> `YYYY-MM-DDThh:mm:ss.000+0000`,
    replicating the Service Price Matrix M transform (12 AM -> 00,
    PM adds 12 except for 12 PM)."""
    if text is None:
        return None
    parts = str(text).split(" ")
    day, month, year = parts[0].split("-")
    hour_s, minute, second = parts[1].split(":")
    meridiem = parts[2]
    if meridiem == "PM" and int(hour_s) != 12:
        hour = str(int(hour_s) + 12)
    elif meridiem == "AM" and hour_s == "12":
        hour = "00"
    else:
        hour = hour_s
    return f"{year}-{month}-{day}T{hour}:{minute}:{second}.000+0000"
