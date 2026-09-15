"""Pin fpdf's PDF `/CreationDate` so identical inputs render identical bytes (design D6).

`fpdf/fpdf.py` calls `datetime.now()` directly (confirmed in task 3.4: it cannot be
monkeypatched on the built-in class, and it is the only source of nondeterminism found
in a clean render). We replace the module-level `datetime` name with a subclass whose
`now()` returns a fixed value derived from the document's own date.
"""

from contextlib import contextmanager
from datetime import datetime as _real_datetime

import fpdf.fpdf as _fpdf_module


@contextmanager
def pinned_creation_date(when: _real_datetime):
    class _FixedDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return when

    original = _fpdf_module.datetime
    _fpdf_module.datetime = _FixedDatetime
    try:
        yield
    finally:
        _fpdf_module.datetime = original
