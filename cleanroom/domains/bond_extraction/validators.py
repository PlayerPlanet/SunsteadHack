"""Bond field validators — deterministic format checks for corporate bond extraction.

Field types:
  - isin: International Securities Identification Number (ISIN) — 12-char alphanumeric
    with Luhn checksum (mod 10 over base-36 encoding).
  - coupon_rate: Numeric percentage (e.g., "3.5" or "4.125"), non-negative.
  - maturity_date: ISO 8601 date (YYYY-MM-DD) in the future.
  - currency: ISO 4217 currency code (e.g., "USD", "EUR").
  - issuer: Non-empty string (no format restriction).
"""

import re
from datetime import datetime


def isin_checksum(s: str) -> bool:
    """Validate ISIN via Luhn checksum (mod-10 over base-36 encoding).

    ISIN format: 2-char country code + 9 digits/alphanumerics + 1 check digit.
    Total: 12 characters.

    Luhn algorithm:
      1. Convert alphanumerics to base-36 (A=10, B=11, ..., Z=35).
      2. Expand each digit pair to two decimal digits.
      3. Apply Luhn (double every other digit from the right, sum, mod 10 = 0).

    Args:
        s: The ISIN string to validate.

    Returns:
        True if valid; False otherwise.
    """
    if not s or len(s) != 12:
        return False

    if not re.match(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$", s):
        return False

    # Convert to base-36 digit string.
    digits = []
    for c in s:
        if c.isdigit():
            digits.append(c)
        else:
            # A=10, B=11, ..., Z=35; each encodes as two decimal digits.
            val = ord(c) - ord("A") + 10
            digits.append(str(val))

    digit_str = "".join(digits)

    # Apply Luhn from right to left.
    total = 0
    for i, d in enumerate(reversed(digit_str)):
        digit_val = int(d)
        if i % 2 == 1:  # Every other digit (1-indexed from right)
            digit_val *= 2
            if digit_val > 9:
                digit_val -= 9
        total += digit_val

    return total % 10 == 0


def is_iso4217(s: str) -> bool:
    """Validate ISO 4217 currency code (3-letter uppercase).

    Args:
        s: The currency code to validate.

    Returns:
        True if valid 3-letter code; False otherwise.
    """
    return bool(re.match(r"^[A-Z]{3}$", s))


def is_numeric_coupon(s: str) -> bool:
    """Validate coupon rate (non-negative decimal number).

    Args:
        s: The coupon rate string to validate.

    Returns:
        True if a non-negative number; False otherwise.
    """
    try:
        val = float(s.strip())
        return val >= 0.0
    except (ValueError, AttributeError):
        return False


def is_parseable_date(s: str) -> bool:
    """Validate ISO 8601 date (YYYY-MM-DD).

    Args:
        s: The date string to validate.

    Returns:
        True if a valid future date; False otherwise.
    """
    try:
        dt = datetime.strptime(s.strip(), "%Y-%m-%d")
        # Check if it's in the future (relative to now).
        return dt > datetime.now()
    except (ValueError, AttributeError):
        return False


def validate_field(field_name: str, value: str) -> bool:
    """Dispatch validation by known field name.

    Known fields:
      - coupon_rate: numeric
      - maturity_date: future date (ISO 8601)
      - isin: ISIN checksum
      - currency: ISO 4217
      - issuer: non-empty string
      - unknown: non-empty string (lenient)

    Args:
        field_name: The field name to validate against.
        value: The value to validate.

    Returns:
        True if valid; False otherwise.
    """
    if not value or not isinstance(value, str):
        return False

    value = value.strip()
    if not value:
        return False

    if field_name == "coupon_rate":
        return is_numeric_coupon(value)
    elif field_name == "maturity_date":
        return is_parseable_date(value)
    elif field_name == "isin":
        return isin_checksum(value)
    elif field_name == "currency":
        return is_iso4217(value)
    elif field_name == "issuer":
        return len(value) > 0
    else:
        # Unknown field: just require non-empty string.
        return len(value) > 0
