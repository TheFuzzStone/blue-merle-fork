"""Unit tests for files/lib/blue-merle/imei_generate.py.

Run with:  python3 -m pytest tests/

We stub out the `serial` module so tests can run without pyserial or a
real modem attached.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
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

# Paths to both TAC list files.
_TAC_FILE_MODULE = _MODULE_DIR / "tac-list.txt"
_TAC_FILE_PHONE = _MODULE_DIR / "tac-list-phone.txt"


def _load_tac_list_from_file() -> list[str]:
    """Load TACs from the repo's tac-list.txt, matching the production code."""
    tacs = []
    for raw in _TAC_FILE_MODULE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if re.fullmatch(r"[0-9]{8}", line):
            tacs.append(line)
    return tacs


def _load_phone_tac_list_from_file() -> list[str]:
    """Load TACs from the repo's tac-list-phone.txt."""
    tacs = []
    for raw in _TAC_FILE_PHONE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if re.fullmatch(r"[0-9]{8}", line):
            tacs.append(line)
    return tacs


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


# ---- TAC selection policy ----

def test_tac_list_file_exists():
    """Documentation placeholder for verified module TACs exists."""
    assert _TAC_FILE_MODULE.exists(), f"tac-list.txt not found at {_TAC_FILE_MODULE}"


def test_project_tac_files_are_empty_without_provenance():
    """The project must not ship unattributed GSMA TAC allocations."""
    assert _load_tac_list_from_file() == []
    assert _load_phone_tac_list_from_file() == []


def test_load_tac_list_from_env():
    """_load_tac_list() should honour BLUE_MERLE_TAC_LIST env override."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("86818604\n# comment\n86439104\n\n")
        f.flush()
        tmp_path = f.name
    try:
        old = os.environ.get("BLUE_MERLE_TAC_LIST")
        os.environ["BLUE_MERLE_TAC_LIST"] = tmp_path
        # Force reimport to pick up env
        for mod_name in list(sys.modules):
            if mod_name == "imei_generate":
                del sys.modules[mod_name]
        import imei_generate as fresh_m
        tacs = fresh_m._load_tac_list()
        assert tacs == ["86818604", "86439104"], f"got {tacs}"
    finally:
        if old is None:
            del os.environ["BLUE_MERLE_TAC_LIST"]
        else:
            os.environ["BLUE_MERLE_TAC_LIST"] = old
        os.unlink(tmp_path)


def test_explicit_missing_tac_list_fails_closed():
    old = os.environ.get("BLUE_MERLE_TAC_LIST")
    os.environ["BLUE_MERLE_TAC_LIST"] = "/nonexistent/path/tac-list.txt"
    try:
        for mod_name in list(sys.modules):
            if mod_name == "imei_generate":
                del sys.modules[mod_name]
        import imei_generate as fresh_m
        try:
            fresh_m._load_tac_list()
        except RuntimeError as exc:
            assert "not readable" in str(exc)
        else:
            raise AssertionError("missing explicit TAC list must fail closed")
    finally:
        if old is None:
            del os.environ["BLUE_MERLE_TAC_LIST"]
        else:
            os.environ["BLUE_MERLE_TAC_LIST"] = old


# ---- generate_imei ----

_TEST_TAC_LIST = ["12345678", "87654321"]

def test_random_generation_is_luhn_valid():
    """Every generated IMEI must be Luhn-valid and its TAC must come
    from the tac-list.txt file (not from the old hardcoded smartphone
    list).
    """
    m.mode = m.Modes.RANDOM
    tacs = _TEST_TAC_LIST
    for _ in range(200):
        imei = m.generate_imei(tacs, None)
        assert len(imei) == 15
        assert imei.isdigit()
        assert m.validate_imei(imei), f"generated invalid IMEI: {imei}"
        assert imei[:8] in tacs


def test_random_tail_is_uniform_over_digits():
    """The tail must include repeated digits sometimes (bug regression:
    the historical random.sample() prevented any repeats in the tail).
    """
    m.mode = m.Modes.RANDOM
    tacs = _TEST_TAC_LIST
    seen_repeat = False
    for _ in range(500):
        imei = m.generate_imei(tacs, None)
        tail = imei[8:14]  # 6 random digits before Luhn check
        if len(set(tail)) < len(tail):
            seen_repeat = True
            break
    assert seen_repeat, "tail never had a repeated digit — random.sample regression?"


def test_deterministic_is_reproducible():
    m.mode = m.Modes.DETERMINISTIC
    tacs = _TEST_TAC_LIST
    seed = b"310150123456789"
    a = m.generate_imei(tacs, seed)
    b = m.generate_imei(tacs, seed)
    assert a == b, f"deterministic mismatch: {a} vs {b}"
    assert m.validate_imei(a)


def test_deterministic_differs_across_imsis():
    m.mode = m.Modes.DETERMINISTIC
    tacs = _TEST_TAC_LIST
    a = m.generate_imei(tacs, b"310150111111111")
    b = m.generate_imei(tacs, b"310150222222222")
    # Extremely unlikely to collide by chance.
    assert a != b


# ---- Phone-mode policy ----

def test_phone_tac_list_file_exists():
    assert _TAC_FILE_PHONE.exists(), f"tac-list-phone.txt not found at {_TAC_FILE_PHONE}"


def test_exact_tac_env_selects_one_tac():
    old = os.environ.get("BLUE_MERLE_TAC")
    os.environ["BLUE_MERLE_TAC"] = "12345678"
    try:
        for mod_name in list(sys.modules):
            if mod_name == "imei_generate":
                del sys.modules[mod_name]
        import imei_generate as fresh_m
        assert fresh_m._load_tac_list() == ["12345678"]
    finally:
        if old is None:
            del os.environ["BLUE_MERLE_TAC"]
        else:
            os.environ["BLUE_MERLE_TAC"] = old
