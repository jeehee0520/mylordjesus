"""Optional checks against your own files (never committed):

    MA_GUIDELINE=/path/guidelines.pdf MA_MANUSCRIPT=/path/manuscript.docx pytest tests/test_real_files.py
"""
import os

import pytest

from core import guideline_loader
from core.manuscript_formatter import format_manuscript
from core.profile_extractor import extract_profile
from core.proofreader import proofread
from core.track_changes import apply_corrections

GUIDE = os.environ.get("MA_GUIDELINE")
MS = os.environ.get("MA_MANUSCRIPT")
pytestmark = pytest.mark.skipif(not (GUIDE and MS), reason="MA_GUIDELINE / MA_MANUSCRIPT not set")


@pytest.fixture(scope="module")
def profile():
    with open(GUIDE, "rb") as f:
        return extract_profile(guideline_loader.load(f.read(), GUIDE))


@pytest.fixture(scope="module")
def manuscript():
    with open(MS, "rb") as f:
        return f.read()


def test_format_keeps_content(profile, manuscript):
    res = format_manuscript(manuscript, profile)
    assert res.guard.ok, res.guard.details


def test_all_fixable_corrections_verify(profile, manuscript):
    issues = [i for i in proofread(manuscript, profile) if i.fixable]
    res = apply_corrections(manuscript, issues)
    assert res.ok, res.checks
