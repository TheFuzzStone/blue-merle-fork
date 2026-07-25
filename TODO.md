# TODO — session work list

One step per session. Each step is self-contained: what to read, what to
do, how to verify. Pick the first `pending` step, work it, then update
statuses at the end of the session (and trim stale notes).

Status markers: `pending` | `in-progress` | `done` | `blocked`.

## How to use this file

- Work exactly ONE step per session unless the user says otherwise.
- Read `AGENTS.md` first (rules, platform constraints, pitfalls), then
  the files listed in the step's "Read first".
- Every fix gets a regression test, and the test MUST be verified to
  fail against the pre-fix code before the fix is applied
  (`AGENTS.md` working agreements).
- Session is green only when: `python3 tests/run_all.py` passes,
  `sh -n` passes on all shell files (CI does this; see
  `.github/workflows/ci.yml`), and the new regression test is proven.
- Never commit/push without an explicit user request. When a step lands,
  move it to "Done" with the commit hash (or "uncommitted" if the user
  did not ask to commit).

## Global rules (short version — AGENTS.md is authoritative)

- Never print full IMEI/IMSI anywhere (logs, MCU, LuCI, diag, agent
  output). Masked forms only.
- busybox ash only: no `[[ ]]`, `${var:offset}`, `echo -n`, `mountpoint`,
  `od`/`hexdump`, `flock -E`.
- `shred` is banned; use `rm`.
- Free-form random MACs must set the U/L bit; Apple OUI only via
  `APPLE_MAC_GEN`.
- TAC lists ship empty; never infer device class from TAC prefixes.

---

## Step 7 — Repo hygiene (no code changes) — `pending`

- Delete `logs/blue-merle-diag.out` locally — it contains a REAL
  upstream ESSID + BSSID from the user's environment (lines ~210,
  ~240-247). Gitignored, so local-only, but should not linger.
- `rm -rf tests/__pycache__ files/lib/blue-merle/__pycache__`.
- Decide the fate of `dist/blue-merle_3.0.5-local-231009.78335` (old
  pre-fix build) — keep for reference or delete.
- AGENTS.md handoff section is uncommitted; decide with the user
  whether to commit it (plus this TODO.md) or keep local.

---

## Later — from the AGENTS.md handoff (not step-sized yet)

1. **Hardware testing on the Mudi** — user holds the full checklist
   (base state → paired identity → stable_identity → ifdown rotation →
   LuCI → toggle flow → CLI → anti-forensics → uninstall). MCU display
   behaviour is the main unverified assumption.
2. **TAC proposals awaiting user decision:** (a) document provenance
   TACs + `original_tac` override; (b) LuCI read-only TAC status
   (mode + baseline present/absent, never the value); (c) log line when
   postinst baseline capture fails; (d) optional `blue-merle-tac info`.
3. **DHCP fingerprinting** (udhcpc PRL/options vs iOS) — research +
   hardware.

## Done

### Step 7 — Repo hygiene (no code changes) — done (this commit, 2026-07-25)

- `logs/blue-merle-diag.out` deleted (contained a real ESSID + BSSID
  from the user's environment; was gitignored, so local-only).
- `tests/__pycache__` and `files/lib/blue-merle/__pycache__` removed.
- Old pre-fix build `dist/blue-merle_3.0.5-local-231009.78335` deleted
  per user decision; SHA256SUMS pruned to the local-19 build
  (re-verified with `sha256sum -c`).
- User chose: commit the whole session as a per-step series (no push):
  `7bc0560` (handoff docs), `c41c56b..d127a81` (steps 1-6), then this
  step-7 docs commit. Every commit verified green in a detached
  worktree (75/78/80/88/90/91/97 tests + sh -n).

### Step 6 — Minor hardening batch — done (d127a81, 2026-07-25)

All five items, each with a regression test proven red pre-fix:
- stage2: vestigial `sim_switch on` removed (the marker is owned by
  sim.sh, read only by stage1's CHECK_ABORT; stage2 never aborts and
  tmpfs is wiped at its poweroff) — explanatory comment left in place.
- sim.sh: `toggle-driven` marker is now created only in the on-branch,
  right before the stage-1 flock (comment updated to describe the
  actual abort handshake); trailing rm kept as cleanup, off-branch
  never creates it.
- newmac help: states that `--full` under `--uplink` rotates only the
  uplink MAC + paired identity (BSSIDs/AP MACs untouched, SSID change
  still kicks clients); print range 3,28p→3,34p which also fixes the
  previously truncated trailing note. Test extracts the range from the
  script itself and checks the real help output.
- `_announce_ssid_on_mcu`: strips `"` and `\` from the SSID before the
  ttyS0 JSON write (custom user SSIDs could break MCU JSON). Static
  test + functional pipeline test (hostile SSID → valid JSON).
- ci.yml: shellcheck tarball pinned by SHA256
  (6c881ab0…df87, downloaded from the official release and
  extract/run-verified); `feeds update packages` step dropped —
  EXTRA_DEPENDS is metadata-only and the handoff-verified claim
  "builds without feeds update" is now pinned by a test.
- Bonus: ran the downloaded shellcheck 0.10.0 with exact CI flags over
  the whole tree — clean, so all shell diffs from steps 1-6 pass the
  CI shellcheck gate.
- Suite: 97 passed, 0 failed; `sh -n` clean.

### Step 5 — Guard `volatile-client-macs` against a running gl_clients — done (3c59fe6, 2026-07-25)

- `start()` now checks `pidof gl_clients` before touching the db dir:
  stops it via `/etc/init.d/gl_clients stop` (mirroring preinst), does
  rm+mount+verify, then restarts it via a SINGLE restart site that
  covers both success and failure paths (`return $rc`) — a failed
  take-over never leaves the stock daemon down. Guard activation is
  logged at notice level; header "Ordering" comment updated.
- Verified the prerm lifecycle was already correctly ordered (gl_clients
  stop → vcm stop/unmount → postrm gl_clients start) — the gap was only
  the manual `service volatile-client-macs start` on a live system.
- Functional sandbox check (stubbed mount/pidof/logger/gl_clients,
  tmp dir instead of /etc/oui-tertf): guard skipped when not running;
  stop→mount→start order when running; restart despite mount failure;
  idempotent early return when already mounted (no calls at all).
- Static regression test (proven red pre-fix): pidof-before-stop,
  stop-before-mount, single restart site after the mount chain,
  `return $rc`, logger mentions gl_clients.
- Suite: 91 passed, 0 failed; `sh -n` clean.
- NOTED, out of scope (future candidate): manual `service
  volatile-client-macs stop` on a live system still unmounts under a
  running gl_clients (symmetric hidden-inode issue on the stop path);
  `restart` self-heals the daemon side via the new start() guard.

### Step 4 — Replace `\s` with `[[:space:]]` in grep patterns — done (uncommitted, 2026-07-25)

- Both `_pick_random_line` patterns now `^[[:space:]]*(#|$)` (count and
  select lines kept identical so total/indexing stay consistent).
- Verified the repo had no other `\s`/`\S` outside .py (only the two
  picker lines; JS view clean).
- Regression tests: static total ban of the `\s` sequence in every
  shell file under files/ + tools/ (proven red pre-fix — it caught
  functions.sh, and even caught my own first draft of the explanatory
  comment containing the literal sequence); functional picker test
  against a pool with whitespace-prefixed comments + whitespace-only
  lines (passes on GNU grep either way by design — the static test is
  the gate — but pins the contract for busybox on-target).
- Suite: 90 passed, 0 failed; `sh -n` clean.

### Step 3 — Standardize identifier mask forms — done (3553010, 2026-07-25)

- Canonical forms (the libexec shapes, strictest shipped): IMEI (15)
  first6+last3, IMSI (14/15) first5+last4. IMSI revealing MCC+MNC =
  carrier is now a documented decision (admin UI shows the carrier
  anyway; subscriber tail stays masked) — in functions.sh, AGENTS.md
  and the test module docstring.
- New `_mask_imei`/`_mask_imsi` helpers in functions.sh, fail-closed
  (misshaped/garbage input → full mask): READ_IMEI greps 14-15 digits
  and READ_IMSI 6-15, so validation inside the helper matters. libexec
  uses the helpers at all three sites; happy-path LuCI output is
  byte-identical to before.
- AGENTS.md rule example fixed (was first6+last4) and now states both
  canonical forms + the helper names.
- diag: the first4+last4 `mask_id` was DEAD code (diag deliberately
  never reads IMEI/IMSI) — replaced by self-contained canonical
  `mask_imei`/`mask_imsi` copies; header comment corrected
  ("never read at all" vs the old "masked before output" claim).
- Python `_mask_id` (step 1) deliberately left uniform first6+last3:
  it is a debug redaction filter for logs, not a display surface.
- New tests/test_mask_forms.py (8 tests): exact-output functional
  checks via sourced functions.sh (incl. 14-digit IMSI and fail-closed
  shapes), single-definition grep, libexec-uses-helpers grep, no stray
  `******` literals under files/, AGENTS.md canonical examples, diag
  canonical forms. Two existing assertions updated for the helper
  interface. All shown red on pre-fix code.
- Suite: 88 passed, 0 failed; `sh -n` clean.

### Step 2 — CLI `blue-merle`: stdin EOF must not mean "yes" — done (bcf7cde, 2026-07-25)

- Top-level guard `[ -t 0 ] || { … exit 1; }` placed BEFORE sourcing
  functions.sh (mirrors the Makefile preinst fix); verified it fires for
  pipe and `</dev/null` stdin without touching anything else.
- All 5 `read` sites got single-line `|| { … exit 1; }` EOF handlers
  (kept single-line so the static grep stays trivially strict):
  - first prompt + CFUN retry prompt → plain abort (modem untouched);
  - mid-swap prompts ("press any key", r/d) → `_safe_poweroff` per the
    script's own fail-closed convention (CFUN=4 + interim IMEI written);
  - final shutdown/reset prompt → power off to finish (a plain exit
    would strand the modem in CFUN=4 with no service).
- CFUN=4 retry loop: bounded to 15 tries (mirrors stage1) + EOF exit —
  the no-sleep spin is gone.
- Regression tests (both verified to FAIL on pre-fix code): tty-guard
  presence/order + per-read EOF handler grep; CFUN loop bound + EOF
  safety grep.
- Functional acceptance on dev host via pty (`script -qec`) + stubbed
  functions.sh: 9 scenarios — guard on pipe/dev-null; EOF at each of
  the 5 prompts; interactive decline paths; CFUN retry decline. All
  abort/exit correctly and instantly. Scenario C (EOF at final prompt)
  re-run 3× stable.
- Suite: 80 passed, 0 failed; `sh -n` clean.

### Step 1 — Stop full IMEI leaking to stderr from `imei_generate.py` — done (c41c56b, 2026-07-25)

- Root cause: `log.info`/`log.error` emitted full IMEI (and `-v` debug
  emitted TAC, 14-digit body, full IMEI, and raw AT responses containing
  IMEI/IMSI) to stderr; every non-interactive caller redirected only
  stdout.
- Fix: `_mask_id()` (first6+last3, shorter values fully masked) and
  `_scrub_at_output()` (masks 6+ digit runs in raw AT output) helpers;
  all 12 identifier-carrying `log.*` calls now log masked forms only.
  stdout `print()` contract unchanged (verified: still full 15-digit,
  Luhn-valid). `validate_imei` exit codes/messages preserved (masked).
- Defence in depth: python calls in stage1/stage2/libexec now end
  `2>/dev/null`. Interactive CLI call sites intentionally unchanged.
- Regression tests (all verified to FAIL on pre-fix code):
  AST static check that no `log.*` call receives a raw identifier
  variable; static grep that all three non-interactive call sites use
  `2>/dev/null`; functional test capturing stderr from `main()` at
  default level and `-v` (no full IMEI/body/TAC, masked form present).
- Suite: 78 passed, 0 failed; `sh -n` clean on all shell files.
- Open hardware follow-up (not blocking): after a real toggle swap,
  confirm `logread` shows no IMEI and observe where gl_switch child
  stderr actually lands.
