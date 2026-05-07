"""Test NSE universe loader."""
import pytest
from finterminal.data.india.nse_universe import load_equity_list, load_sector_map


def test_load_equity_list_returns_dict():
    universe = load_equity_list()
    assert isinstance(universe, dict)
    assert len(universe) > 10


def test_known_ticker_present():
    universe = load_equity_list()
    assert "RELIANCE" in universe
    assert "INFY" in universe


def test_aliases_generated():
    universe = load_equity_list()
    rel = universe["RELIANCE"]
    assert "aliases" in rel
    assert len(rel["aliases"]) >= 1


def test_ltd_stripped_from_alias():
    """'Reliance Industries Limited' alias list should include 'Reliance Industries'."""
    universe = load_equity_list()
    rel = universe["RELIANCE"]
    aliases_lower = [a.lower() for a in rel["aliases"]]
    assert "reliance industries" in aliases_lower


def test_load_sector_map_returns_dict():
    sector_map = load_sector_map()
    assert isinstance(sector_map, dict)
    assert len(sector_map) > 5


def test_reliance_in_sector_map():
    sector_map = load_sector_map()
    assert "RELIANCE" in sector_map
    assert sector_map["RELIANCE"] == "Energy"
