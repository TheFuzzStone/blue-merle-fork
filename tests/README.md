# blue-merle unit tests

Run:

```
python3 -m pytest tests/
```

Or, if `pytest` is not available, use the built-in unittest-style runner:

```
python3 tests/run_all.py
```

The tests do not require a real modem — they stub out `pyserial` and only
exercise pure-logic paths (Luhn digit, IMEI validation, MAC bit patterns,
deterministic reproducibility).

Coverage:

* `test_imei_generate.py` — Luhn correctness (including the all-zero edge
  case that regressed in the Lua implementation), IMEI validation,
  entropy properties of the generated tail (regression test for the
  `random.sample` bug that made blue-merle IMEIs statistically
  distinguishable), determinism.
* `test_mac_generator.py` — sources `files/lib/blue-merle/functions.sh`
  in `/bin/sh` and verifies that every generated MAC has the unicast bit
  cleared and the locally-administered bit set (regression test for the
  historical MAC-generator bug).
