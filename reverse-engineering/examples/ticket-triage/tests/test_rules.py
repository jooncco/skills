from packages.triage_core.rules import CATEGORY_KEYWORDS, GROUP_BY_CATEGORY


def test_every_category_has_a_group():
    for category in CATEGORY_KEYWORDS:
        assert category in GROUP_BY_CATEGORY
