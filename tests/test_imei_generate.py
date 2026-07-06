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

# Path to the TAC list file in the repo.
_TAC_FILE = _MODULE_DIR / "tac-list.txt"


def _load_tac_list_from_file() -> list[str]:
    """Load TACs from the repo's tac-list.txt, matching the production code."""
    tacs = []
    for raw in _TAC_FILE.read_text(encoding="utf-8").splitlines():
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


# ---- TAC list loading ----

def test_tac_list_file_exists():
    """The tac-list.txt file must exist in the repo."""
    assert _TAC_FILE.exists(), f"tac-list.txt not found at {_TAC_FILE}"


def test_tac_list_non_empty():
    tacs = _load_tac_list_from_file()
    assert len(tacs) >= 5, f"tac-list.txt has only {len(tacs)} entries"


def test_tac_list_all_8_digits():
    """Every TAC must be exactly 8 decimal digits."""
    tacs = _load_tac_list_from_file()
    for tac in tacs:
        assert re.fullmatch(r"[0-9]{8}", tac), f"invalid TAC: {tac!r}"


def test_tac_list_all_module_range():
    """All TACs should be in the 86xxxxxx (LTE-module) range, not
    35xxxxxx (smartphone). This is the core of the TAC-filter feature:
    prevent operator TAC-lookup mismatch.
    """
    tacs = _load_tac_list_from_file()
    for tac in tacs:
        assert tac.startswith("86"), \
            f"TAC {tac} is not in the 86xxxxxx module range — " \
            f"smartphone TACs cause capability-mismatch flags"


def test_tac_list_no_duplicates():
    tacs = _load_tac_list_from_file()
    assert len(tacs) == len(set(tacs)), f"duplicate TACs: {tacs}"


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


def test_load_tac_list_fallback_on_missing_file():
    """If the TAC file doesn't exist, _load_tac_list() should return
    the hardcoded fallback list (also 86xxxxxx range).
    """
    old = os.environ.get("BLUE_MERLE_TAC_LIST")
    os.environ["BLUE_MERLE_TAC_LIST"] = "/nonexistent/path/tac-list.txt"
    try:
        for mod_name in list(sys.modules):
            if mod_name == "imei_generate":
                del sys.modules[mod_name]
        import imei_generate as fresh_m
        tacs = fresh_m._load_tac_list()
        assert len(tacs) > 0, "fallback list is empty"
        assert all(t.startswith("86") for t in tacs), \
            "fallback TACs should all be 86xxxxxx module range"
    finally:
        if old is None:
            del os.environ["BLUE_MERLE_TAC_LIST"]
        else:
            os.environ["BLUE_MERLE_TAC_LIST"] = old


# ---- generate_imei ----

def test_random_generation_is_luhn_valid():
    """Every generated IMEI must be Luhn-valid and its TAC must come
    from the tac-list.txt file (not from the old hardcoded smartphone
    list).
    """
    m.mode = m.Modes.RANDOM
    tacs = _load_tac_list_from_file()
    for _ in range(200):
        imei = m.generate_imei(tacs, None)
        assert len(imei) == 15
        assert imei.isdigit()
        assert m.validate_imei(imei), f"generated invalid IMEI: {imei}"
        # TAC comes from the curated module list.
        assert imei[:8] in tacs, \
            f"TAC {imei[:8]} not in tac-list.txt — smartphone TAC leaked?"


def test_random_generation_uses_module_range():
    """All generated IMEIs must start with 86 (module range), not 35
    (smartphone range). This is the regression guard for the TAC-filter.
    """
    m.mode = m.Modes.RANDOM
    tacs = _load_tac_list_from_file()
    for _ in range(100):
        imei = m.generate_imei(tacs, None)
        assert imei.startswith("86"), \
            f"IMEI {imei} starts with {imei[:2]} — expected 86 (module range)"


def test_random_tail_is_uniform_over_digits():
    """The tail must include repeated digits sometimes (bug regression:
    the historical random.sample() prevented any repeats in the tail).
    """
    m.mode = m.Modes.RANDOM
    tacs = _load_tac_list_from_file()
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
    tacs = _load_tac_list_from_file()
    seed = b"310150123456789"
    a = m.generate_imei(tacs, seed)
    b = m.generate_imei(tacs, seed)
    assert a == b, f"deterministic mismatch: {a} vs {b}"
    assert m.validate_imei(a)


def test_deterministic_differs_across_imsis():
    m.mode = m.Modes.DETERMINISTIC
    tacs = _load_tac_list_from_file()
    a = m.generate_imei(tacs, b"310150111111111")
    b = m.generate_imei(tacs, b"310150222222222")
    # Extremely unlikely to collide by chance.
    assert a != b


def test_deterministic_uses_module_range():
    """Deterministic IMEIs must also use module TACs, not smartphone."""
    m.mode = m.Modes.DETERMINISTIC
    tacs = _load_tac_list_from_file()
    imei = m.generate_imei(tacs, b"310150123456789")
    assert imei.startswith("86"), \
        f"deterministic IMEI {imei} not in module range"
