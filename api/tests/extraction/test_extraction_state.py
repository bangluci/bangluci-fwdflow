import pytest

from app.ai.extraction.models import EXTRACTION_TRANSITIONS, ExtractionStatus, assert_extraction_transition
from app.envelope import AppError

ALL = list(ExtractionStatus)


@pytest.mark.parametrize("to_status", ALL)
@pytest.mark.parametrize("from_status", ALL)
def test_extraction_transition(from_status, to_status):
    if to_status in EXTRACTION_TRANSITIONS.get(from_status, set()):
        assert_extraction_transition(from_status, to_status)
        return
    with pytest.raises(AppError) as err:
        assert_extraction_transition(from_status, to_status)
    assert err.value.code == "INVALID_TRANSITION" and err.value.status == 409


def test_exactly_eight_valid_edges():
    assert sum(len(targets) for targets in EXTRACTION_TRANSITIONS.values()) == 8
