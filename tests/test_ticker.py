import os

import pytest

from moexalgo import Ticker, session

session.TOKEN = os.environ["APIKEY"]


def test_market():
    moex = Ticker("MOEX")

    assert len(moex.info())

    data = moex.tradestats(start="2024-01-05", end="2024-02-05")
    assert len(data) > 500


if __name__ == "__main__":
    pytest.main()
