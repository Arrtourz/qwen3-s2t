from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from s2t.platform.macos.instance_lock import SingleInstanceLock


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    """Point app_data_dir() at a temp dir via the documented env override."""
    monkeypatch.setenv("S2T_CONFIG_PATH", str(tmp_path / "config.toml"))
    return tmp_path


def test_acquire_then_second_instance_refused(lock_dir):
    first = SingleInstanceLock()
    assert first.acquire() is True
    second = SingleInstanceLock()
    assert second.acquire() is False
    first.release()


def test_lock_is_reusable_after_release(lock_dir):
    first = SingleInstanceLock()
    assert first.acquire() is True
    first.release()
    second = SingleInstanceLock()
    assert second.acquire() is True
    second.release()


def test_release_keeps_the_file(lock_dir):
    # Deleting it would let the next launch lock a fresh inode while a holder
    # still owns the old one -> two instances.
    lock = SingleInstanceLock()
    lock.acquire()
    lock.release()
    assert (lock_dir / "s2t.lock").exists()


def test_lock_file_records_holder_pid(lock_dir):
    lock = SingleInstanceLock()
    lock.acquire()
    assert (lock_dir / "s2t.lock").read_text().strip() == str(os.getpid())
    lock.release()


def test_failed_acquire_does_not_clobber_recorded_pid(lock_dir):
    holder = SingleInstanceLock()
    holder.acquire()
    SingleInstanceLock().acquire()  # fails
    assert (lock_dir / "s2t.lock").read_text().strip() == str(os.getpid())
    holder.release()


def test_failed_acquire_leaves_nothing_to_release(lock_dir):
    holder = SingleInstanceLock()
    holder.acquire()
    loser = SingleInstanceLock()
    assert loser.acquire() is False
    loser.release()  # must be a no-op, not a release of the holder's lock
    assert SingleInstanceLock().acquire() is False
    holder.release()


def test_lock_released_when_holder_process_dies(lock_dir, tmp_path):
    # The kernel drops flock on process death, including SIGKILL, which is why
    # no stale-file cleanup is needed.
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
        from s2t.platform.macos.instance_lock import SingleInstanceLock
        lock = SingleInstanceLock()
        print(lock.acquire(), flush=True)
        time.sleep(30)
    """)
    env = {**os.environ, "S2T_CONFIG_PATH": str(tmp_path / "config.toml")}
    child = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert child.stdout.readline().strip() == "True"
        assert SingleInstanceLock().acquire() is False  # child holds it
    finally:
        child.kill()
        child.wait(timeout=10)
    after = SingleInstanceLock()
    assert after.acquire() is True  # freed by the kernel on SIGKILL
    after.release()
