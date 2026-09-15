"""CUIT and CAE generation (spec: "Valid synthetic identifiers and consistent arithmetic")."""

import random

LEGAL_ENTITY_PREFIXES = ("30", "33", "34")
_CUIT_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit_check_digit(base10: str) -> int | None:
    """Mod-11 check digit for a 10-digit CUIT base. None when the base has no valid digit (would be 10)."""
    r = sum(int(d) * w for d, w in zip(base10, _CUIT_WEIGHTS)) % 11
    dv = 0 if r == 0 else 11 - r
    return None if dv == 10 else dv


def is_valid_cuit(cuit: str) -> bool:
    digits = "".join(c for c in cuit if c.isdigit())
    if len(digits) != 11:
        return False
    return cuit_check_digit(digits[:10]) == int(digits[10])


def generate_cuit(rng: random.Random, prefix: str | None = None) -> str:
    """An 11-digit CUIT with a legal-entity prefix (30/33/34) and a valid mod-11 check digit."""
    while True:
        p = prefix or rng.choice(LEGAL_ENTITY_PREFIXES)
        suffix = "".join(str(rng.randint(0, 9)) for _ in range(8))
        base10 = p + suffix
        dv = cuit_check_digit(base10)
        if dv is not None:
            return base10 + str(dv)


def generate_cae(rng: random.Random) -> str:
    """A 14-digit CAE. The first digit is nonzero so the string always has 14 digits."""
    first = str(rng.randint(1, 9))
    rest = "".join(str(rng.randint(0, 9)) for _ in range(13))
    return first + rest
