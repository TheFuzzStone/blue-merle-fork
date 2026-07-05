"""Test that _open_serial in imei_generate.py acquires fcntl.flock.

This is the C4 fix: TIOCEXCL (via pyserial's exclusive=True) only
blocks *new* open() calls on the tty; it does not stop a process that
already has an fd from continuing to write. fcntl.flock on the fd is
a second layer that makes concurrent access impossible.

We can't exercise a real modem here, so we build a mock pyserial that
returns an object exposing a real fd (a pipe or /dev/null) which
imei_generate.py can flock. Then we verify:

  * _open_serial calls fcntl.flock LOCK_EX | LOCK_NB.
  * If flock raises BlockingIOError, _open_serial retries.
  * After the configured number of attempts, it raises
    serial.SerialException so callers' retry logic still applies.
"""

from __future__ import annotations

import errno
import os
import sys
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MOD_DIR = ROOT / "files" / "lib" / "blue-merle"
sys.path.insert(0, str(MOD_DIR))


class _MockSerial:
    """Minimal drop-in for serial.Serial returning a real fd we can
    flock and close. Uses /dev/null so the fd is always valid."""

    def __init__(self, *args, **kwargs):
        self._fd = os.open("/dev/null", os.O_RDWR)
        self.closed = False

    def fileno(self) -> int:
        return self._fd

    def close(self) -> None:
        if not self.closed:
            os.close(self._fd)
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _install_mock_serial():
    """Replace the module-level `serial` object with our mock so
    imei_generate can be imported and _open_serial exercised."""
    class _SerialException(Exception):
        pass

    fake = types.SimpleNamespace(
        Serial=_MockSerial,
        SerialException=_SerialException,
    )
    sys.modules["serial"] = fake
    return _SerialException


def _fresh_import():
    """Force a fresh import of imei_generate under the current mocks."""
    for mod in list(sys.modules):
        if mod == "imei_generate":
            del sys.modules[mod]
    import imei_generate  # noqa: F401
    return sys.modules["imei_generate"]


# ---- Tests ----

def test_open_serial_acquires_flock_on_success():
    """Happy path: fcntl.flock succeeds first try → _open_serial
    returns the serial object without retrying.
    """
    _install_mock_serial()
    im = _fresh_import()

    with mock.patch.object(im.fcntl, "flock") as flock:
        ser = im._open_serial("/dev/null-fake-tty")
        # flock must have been called exactly once with LOCK_EX|LOCK_NB.
        assert flock.call_count == 1
        _fd_arg, flags = flock.call_args.args
        assert flags == im.fcntl.LOCK_EX | im.fcntl.LOCK_NB
        ser.close()


def test_open_serial_retries_on_contention():
    """If flock raises BlockingIOError repeatedly, _open_serial must
    retry _FLOCK_ATTEMPTS times before giving up. We patch time.sleep
    so the test runs fast.
    """
    SerialException = _install_mock_serial()
    im = _fresh_import()

    def always_busy(fd, flags):
        raise BlockingIOError(errno.EWOULDBLOCK, "test contention")

    with mock.patch.object(im.fcntl, "flock", side_effect=always_busy), \
         mock.patch.object(im.time, "sleep") as sleep_mock:
        try:
            im._open_serial("/dev/null-fake-tty")
        except im.serial.SerialException as exc:
            # Expect a SerialException raised after retries exhausted.
            assert "held by another process" in str(exc) or "tried" in str(exc)
        else:
            raise AssertionError("_open_serial should have raised")
        # Slept between attempts (attempts-1 times).
        assert sleep_mock.call_count == im._FLOCK_ATTEMPTS - 1


def test_open_serial_succeeds_after_transient_contention():
    """Simulate: first attempt fails with EWOULDBLOCK, second succeeds.
    _open_serial should return the serial object without raising.
    """
    _install_mock_serial()
    im = _fresh_import()

    calls = {"n": 0}

    def maybe_busy(fd, flags):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BlockingIOError(errno.EWOULDBLOCK, "test contention")
        return None  # success

    with mock.patch.object(im.fcntl, "flock", side_effect=maybe_busy), \
         mock.patch.object(im.time, "sleep"):
        ser = im._open_serial("/dev/null-fake-tty")
        assert calls["n"] == 2
        ser.close()


def test_open_serial_raises_serialexception_on_unexpected_oserror():
    """A non-EWOULDBLOCK OSError from flock is a genuine failure, not
    contention. It should be wrapped as SerialException so the caller's
    retry loop treats it uniformly.
    """
    _install_mock_serial()
    im = _fresh_import()

    def hard_error(fd, flags):
        raise OSError(errno.EIO, "genuine i/o failure")

    with mock.patch.object(im.fcntl, "flock", side_effect=hard_error):
        try:
            im._open_serial("/dev/null-fake-tty")
        except im.serial.SerialException as exc:
            assert "flock" in str(exc)
        else:
            raise AssertionError("_open_serial should have raised")
