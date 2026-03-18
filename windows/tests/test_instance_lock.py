from __future__ import annotations

from s2t.platform.windows.instance_lock import SingleInstanceLock


def test_single_instance_lock_rejects_second_acquire() -> None:
    first = SingleInstanceLock(name="Local\\s2t-test-lock")
    second = SingleInstanceLock(name="Local\\s2t-test-lock")

    assert first.acquire() is True
    assert second.acquire() is False

    second.release()
    first.release()
