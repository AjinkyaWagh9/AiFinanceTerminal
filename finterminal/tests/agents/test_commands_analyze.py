"""Surface tests for the rewired _cmd_analyze."""
from __future__ import annotations

from finterminal import commands


def test_analyze_flag_parser_extracts_fresh():
    args = ["RELIANCE", "--fresh"]
    parsed_ticker, fresh = commands._parse_analyze_args(args)
    assert parsed_ticker == "RELIANCE"
    assert fresh is True


def test_analyze_flag_parser_default_no_fresh():
    parsed_ticker, fresh = commands._parse_analyze_args(["INFY"])
    assert parsed_ticker == "INFY"
    assert fresh is False


def test_analyze_flag_parser_rejects_zero_args():
    import pytest
    with pytest.raises(commands._UsageError):
        commands._parse_analyze_args([])


def test_analyze_flag_parser_rejects_extra_positionals():
    import pytest
    with pytest.raises(commands._UsageError):
        commands._parse_analyze_args(["RELIANCE", "INFY"])


def test_analyze_flag_parser_rejects_unknown_flags():
    import pytest
    with pytest.raises(commands._UsageError):
        commands._parse_analyze_args(["RELIANCE", "--bogus"])
