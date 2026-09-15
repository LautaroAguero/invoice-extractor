from dataclasses import replace

import pytest

from generator.cases import CASES
from generator.manifest import CompositionError, check_composition


def test_real_case_list_passes():
    check_composition(CASES)


def test_removing_one_case_fails_with_a_message():
    mutated = CASES[:-1]
    with pytest.raises(CompositionError, match="30"):
        check_composition(mutated)


def test_removing_the_only_case_with_a_required_tag_fails_with_a_message():
    # A04 is the only dense_table-tagged case in the whole list.
    mutated = [c for c in CASES if c.id != "A04"]
    # Swap in a duplicate of another A/qr_base case (untagged) to keep the
    # letter/layout counts intact, so the failure is specifically the missing tag.
    replacement = replace(next(c for c in CASES if c.id == "A01"), id="A04")
    mutated.append(replacement)
    with pytest.raises(CompositionError, match="dense_table"):
        check_composition(mutated)
