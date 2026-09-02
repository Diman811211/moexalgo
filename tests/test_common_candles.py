from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from moexalgo.features import common

CANDLE_COLUMNS = ("begin", "end", "open", "high", "low", "close", "volume", "value")


def _candle_row(time: str, price: int) -> list[object]:
    return [
        f"2026-08-31 {time}:00",
        f"2026-08-31 {time}:59",
        price,
        price,
        price,
        price,
        1,
        price,
    ]


class FakeClient:
    def __init__(self, pages: dict[int, list[list[object]]]) -> None:
        self.pages = pages
        self.requests: list[dict[str, Any]] = []

    def get_objects(
        self,
        path: str,
        deserializer: Callable[[dict[str, Any]], Any],
        **params: Any,
    ) -> Any:
        self.requests.append(params.copy())
        section = {"columns": CANDLE_COLUMNS, "data": self.pages.get(params["start"], [])}
        return deserializer({"candles": section})


class FakeSession:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    def __enter__(self) -> FakeClient:
        return self.client

    def __exit__(self, *exc_info: object) -> None:
        return None


def _ticker_with_pages(
    monkeypatch: pytest.MonkeyPatch,
    pages: dict[int, list[list[object]]],
) -> tuple[common.CommonTicker, FakeClient]:
    client = FakeClient(pages)
    monkeypatch.setattr(common, "Session", lambda: FakeSession(client))
    ticker = common.CommonTicker(
        SimpleNamespace(engine="stock", market="shares"),
        "TQBR",
        "SBER",
        2,
        False,
    )
    return ticker, client


def test_resampled_candle_limit_and_offset_apply_after_resampling(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker, client = _ticker_with_pages(
        monkeypatch,
        {
            0: [_candle_row("10:00", 100), _candle_row("10:15", 101)],
            2: [_candle_row("10:30", 102)],
        },
    )
    monkeypatch.setattr(common, "CANDLE_PAGE_SIZE", 2)

    candles = list(
        ticker.candles(
            period="15min",
            start="2026-08-31",
            end="2026-08-31",
            offset=1,
            native=True,
        )
    )

    assert [candle["begin"] for candle in candles] == [
        "2026-08-31T10:15:00",
        "2026-08-31T10:30:00",
    ]
    assert [request["start"] for request in client.requests] == [0, 2, 3]
    assert {request["interval"] for request in client.requests} == {1}


@pytest.mark.parametrize(
    ("period", "expected_interval"),
    [
        pytest.param("10min", 10, id="ten-minutes"),
        pytest.param(4, 4, id="quarter"),
    ],
)
def test_native_period_preserves_moex_offset_and_exact_limit(
    monkeypatch: pytest.MonkeyPatch,
    period: str | int,
    expected_interval: int,
) -> None:
    ticker, client = _ticker_with_pages(
        monkeypatch,
        {
            7: [
                _candle_row("10:00", 100),
                _candle_row("10:10", 101),
                _candle_row("10:20", 102),
            ]
        },
    )
    monkeypatch.setattr(common, "CANDLE_PAGE_SIZE", 2)

    candles = list(
        ticker.candles(
            period=period,
            start="2026-08-31",
            end="2026-08-31",
            offset=7,
            native=True,
        )
    )

    assert [candle["begin"] for candle in candles] == [
        "2026-08-31 10:00:00",
        "2026-08-31 10:10:00",
    ]
    assert [request["start"] for request in client.requests] == [7]
    assert client.requests[0]["interval"] == expected_interval


def test_native_latest_returns_exactly_one_candle(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker, client = _ticker_with_pages(
        monkeypatch,
        {0: [_candle_row("10:20", 102), _candle_row("10:10", 101)]},
    )

    candles = list(
        ticker.candles(
            period="10min",
            start="2026-08-31",
            end="2026-08-31",
            latest=True,
            native=True,
        )
    )

    assert [candle["begin"] for candle in candles] == ["2026-08-31 10:20:00"]
    assert client.requests[0]["iss.reverse"] is True


def test_resampled_latest_uses_chronological_source_candles(monkeypatch: pytest.MonkeyPatch) -> None:
    latest_interval = [_candle_row(f"10:{minute:02d}", 100 + minute) for minute in range(14, -1, -1)]
    ticker, client = _ticker_with_pages(
        monkeypatch,
        {0: [*latest_interval, _candle_row("09:59", 99)]},
    )

    candles = list(
        ticker.candles(
            period="15min",
            start="2026-08-31",
            end="2026-08-31",
            latest=True,
            native=True,
        )
    )

    assert candles == [
        {
            "begin": "2026-08-31T10:00:00",
            "end": "2026-08-31T10:14:59",
            "open": 100,
            "high": 114,
            "low": 100,
            "close": 114,
            "volume": 15,
            "value": 1605,
        }
    ]
    assert client.requests[0]["iss.reverse"] is True


def test_resampled_empty_source_returns_no_candles(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker, client = _ticker_with_pages(monkeypatch, {0: []})

    candles = list(
        ticker.candles(
            period="15min",
            start="2026-08-31",
            end="2026-08-31",
            native=True,
        )
    )

    assert candles == []
    assert [request["start"] for request in client.requests] == [0]
