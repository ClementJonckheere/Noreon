"""La campagne attend les request_ids persistés, sans sleep final arbitraire."""
from __future__ import annotations

from scripts.shadow_campaign import wait_for_shadow_request_ids


class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Session:
    def __init__(self, factory):
        self.factory = factory

    def execute(self, _statement):
        values = self.factory.results.pop(0) if self.factory.results else []
        return _Result(values)

    def close(self):
        self.factory.closed += 1


class _Factory:
    def __init__(self, results):
        self.results = list(results)
        self.closed = 0

    def __call__(self):
        return _Session(self)


class _Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


def test_wait_returns_only_after_every_request_id_is_persisted():
    factory = _Factory([["r1"], ["r2"]])
    clock = _Clock()
    missing = wait_for_shadow_request_ids(
        ["r1", "r2"], connection_id=4, timeout=10, poll_interval=1,
        session_factory=factory, monotonic=clock.monotonic, sleeper=clock.sleep)
    assert missing == []
    assert factory.closed == 2


def test_wait_reports_request_ids_still_missing_at_timeout():
    factory = _Factory([[], [], []])
    clock = _Clock()
    missing = wait_for_shadow_request_ids(
        ["r1", "r2"], connection_id=4, timeout=1, poll_interval=0.5,
        session_factory=factory, monotonic=clock.monotonic, sleeper=clock.sleep)
    assert missing == ["r1", "r2"]
    assert clock.now == 1.0
