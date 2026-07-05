"""Unit tests for files/lib/blue-merle/imei_generate.py.

Run with:  python3 -m pytest tests/

We stub out the `serial` module so tests can run without pyserial or a
real modem attached.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path


# Provide a minimal fake `serial` module before importing the target.
class _FakeSerial:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Serial access is not expected in these unit tests")


class _FakeSerialException(Exception):
    pass


sys.modules.setdefault(
    "serial",
    types.SimpleNamespace(Serial=_FakeSerial, SerialException=_FakeSerialException),
)

# Add the module under test to sys.path.
_MODULE_DIR = Path(__file__).resolve().parent.parent / "files" / "lib" / "blue-merle"
sys.path.insert(0, str(_MODULE_DIR))

import imei_generate as m  # noqa: E402


# ---- Luhn check digit ----

def test_luhn_known_vectors():
    # Standard IMEI examples (body of 14 -> known check digit).
    assert m._luhn_check_digit("49015420323751") == 8
    assert m._luhn_check_digit("35398208003551") == 4
    # All-zeros edge case: previously the Lua implementation returned 10
    # here instead of 0. Verify we return the standards-compliant 0.
    assert m._luhn_check_digit("00000000000000") == 0


def test_luhn_odd_length():
    # The canonical right-to-left implementation must also work for
    # non-even lengths. Reference values:
    #   '123'         -> sum = 6+2+2 = 10 -> check 0
    #   '7992739871'  -> classic Wikipedia credit-card example, check 3
    assert m._luhn_check_digit("123") == 0
    assert m._luhn_check_digit("7992739871") == 3


# ---- validate_imei ----

def test_validate_accepts_correct():
    assert m.validate_imei("490154203237518") is True


def test_validate_rejects_wrong_check():
    assert m.validate_imei("490154203237519") is False


def test_validate_rejects_short():
    assert m.validate_imei("49015420323751") is False


def test_validate_rejects_long():
    assert m.validate_imei("4901542032375188") is False


def test_validate_rejects_non_digit():
    assert m.validate_imei("49015420323751a") is False


# ---- generate_imei ----

def test_random_generation_is_luhn_valid():
    m.mode = m.Modes.RANDOM
    for _ in range(200):
        imei = m.generate_imei(m.IMEI_PREFIX, None)
        assert len(imei) == 15
        assert imei.isdigit()
        assert m.validate_imei(imei), f"generated invalid IMEI: {imei}"
        # TAC comes from the curated list.
        assert imei[:8] in m.IMEI_PREFIX


def test_random_tail_is_uniform_over_digits():
    """The tail must include repeated digits sometimes (bug regression:
    the historical random.sample() prevented any repeats in the tail).
    """
    m.mode = m.Modes.RANDOM
    seen_repeat = False
    for _ in range(500):
        imei = m.generate_imei(m.IMEI_PREFIX, None)
        tail = imei[8:14]  # 6 random digits before Luhn check
        if len(set(tail)) < len(tail):
            seen_repeat = True
            break
    assert seen_repeat, "tail never had a repeated digit — random.sample regression?"


def test_deterministic_is_reproducible():
    m.mode = m.Modes.DETERMINISTIC
    seed = b"310150123456789"
    a = m.generate_imei(m.IMEI_PREFIX, seed)
    b = m.generate_imei(m.IMEI_PREFIX, seed)
    assert a == b, f"deterministic mismatch: {a} vs {b}"
    assert m.validate_imei(a)


def test_deterministic_differs_across_imsis():
    m.mode = m.Modes.DETERMINISTIC
    a = m.generate_imei(m.IMEI_PREFIX, b"310150111111111")
    b = m.generate_imei(m.IMEI_PREFIX, b"310150222222222")
    # Extremely unlikely to collide by chance.
    assert a != b
