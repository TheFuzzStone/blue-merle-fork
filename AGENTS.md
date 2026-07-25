# AGENTS.md

Guidance for AI agents working on this repository.

## Project

Fork of [srlabs/blue-merle](https://github.com/srlabs/blue-merle) for the
GL-E750 Mudi 4G router. Package name stays `blue-merle` on-device; do NOT
rename `PKG_NAME` without rewriting every path.

Added beyond upstream: Apple masquerade (OUI MAC + iPhone hostname +
`<Name>'s iPhone` SSID), TAC policy (module preserves baseline modem TAC;
phone is user-supplied, fail-closed), `stable_identity` UCI option, per-uplink
MAC rotation, tmpfs for `/root/esim` and `/etc/oui-tertf`, fail-closed state
machine, shared modem lock.

## Current status (session handoff, 2026-07-25)

Remove this section once stale.

Base is `origin/main @ 034203c` (previous hardening session, pushed).
On top, this session's TODO.md step series landed UNPUSHED as 8 local
commits, each verified green in a detached worktree
(`python3 tests/run_all.py` + CI's `sh -n` set):

- `7bc0560` — docs: the 2026-07-18 handoff (this section's old form).
- `c41c56b` — step 1: `imei_generate.py` no longer leaks full
  IMEI/IMSI to stderr (`_mask_id`/`_scrub_at_output` on all 12 log
  sites; the three non-interactive call sites also drop stderr).
- `bcf7cde` — step 2: CLI refuses non-interactive stdin (`[ -t 0 ]`),
  every `read` has an EOF handler, CFUN=4 loop bounded to 15.
- `3553010` — step 3: canonical mask forms (IMEI first6+last3, IMSI
  first5+last4) centralized in `_mask_imei`/`_mask_imsi`; libexec,
  diag, AGENTS.md aligned.
- `4782da6` — step 4: `_pick_random_line` uses POSIX `[[:space:]]`.
- `3c59fe6` — step 5: `volatile-client-macs start()` stops/restarts a
  running gl_clients around the tmpfs mount.
- `d127a81` — step 6 batch: stage2/sim.sh switch-marker cleanup,
  newmac `--uplink --full` help, MCU JSON SSID sanitizing, shellcheck
  tarball SHA256 pin, CI no longer runs `feeds update`.
- step 7 (this commit) — repo hygiene: real-ESSID diag log deleted,
  stale pre-fix ipk pruned from dist/, TODO.md committed.

97 unit tests; shellcheck clean at `-s sh -S warning` (verified
locally with the pinned 0.10.0 tarball). Build state:
`dist/blue-merle_3.0.5-local-19_mips_24kc.ipk` + `SHA256SUMS`,
content-audited. The package builds without `feeds update` (SDK
volatile — re-download per README); **the ipk predates this session's
changes — rebuild before flashing**.

Step-sized work items live in `TODO.md` (committed; steps 1-7 done,
its "Later" queue is the live queue). The strategic queue is
unchanged:

1. **Hardware testing on the Mudi** (user holds the full checklist;
   MCU display behaviour is the main unverified assumption).
2. **TAC proposals awaiting user decision** (see TODO.md "Later").
3. Strategic: DHCP fingerprinting (udhcpc PRL/options vs iOS).

Working agreements that proved themselves: every new regression test
must be verified to fail on the pre-fix code; every commit stays
green; steelman before dismissing.

## Rules

- **Never push without explicit user request.** Never commit/amend without
  explicit "commit".
- **Never print full IMEI/IMSI.** Masked forms only, one canonical shape
  per class: IMEI first6+last3 (`354567******345`), IMSI first5+last4
  (`31015******6789`). The IMSI form deliberately reveals MCC+MNC (the
  carrier — the admin UI shows it anyway); the subscriber tail stays
  masked. Helpers: `_mask_imei`/`_mask_imsi` in `functions.sh`.
- **`shred` is banned** — theatrical on NAND, pointless on tmpfs. Use `rm`.
- **MAC generators:** set U/L bit unless explicitly using Apple OUI
  (`APPLE_MAC_GEN`). Free-form random MACs must be locally-administered.
- **TAC lists must not ship unverified values.** Prefixes don't encode
  manufacturer or device class. Add TACs only with documented GSMA provenance.

## Quality standard

This project protects people in high-risk situations. Mistakes have
real-world consequences.

- **Self-verify every claim** — read code, run commands, check files.
- **Do not optimise for token speed** — thoroughness over brevity.
- **Walk through code paths mentally** — trace every call, variable, branch.
  "What if this is empty? What if the file is missing? What if modem is
  in CFUN=4?"
- **Steelman reviewer proposals first** — assume they're right, find the
  strongest argument, then evaluate. We've been wrong by dismissing too
  quickly (TAC/Quectel discussion).
- **Admit errors explicitly** — "I was wrong because X" and correct it.

## Platform

- **Arch:** `mips_24kc` (ath79/nand), OpenWrt 23.05, busybox ash.
- **Avoid:** `[[ ]]`, `==`, `${var:offset}`, `echo -n`, `mountpoint`,
  `od`, `hexdump`. Use `printf`, `cut`, `grep /proc/mounts`,
  `/proc/sys/kernel/random/uuid`. Test with `sh -n`.
- **Modem:** Quectel EP06 via AT commands. TTY discovered by
  `_resolve_modem_tty` (AT probe on each candidate). Override:
  `BLUE_MERLE_TTY`.
- **MCU:** 16x2 display via `/dev/ttyS0` JSON. Python 3.x (pyserial).

## Build & test

```sh
cd $SDK && make -j$(nproc) package/blue-merle/{clean,compile} V=s
cp $SDK/bin/packages/mips_24kc/base/blue-merle_*.ipk ./dist/
python3 tests/run_all.py   # all must pass
# shellcheck (gated in CI; optional locally):
# shellcheck -s sh -S warning $(find files/usr/bin files/usr/libexec \
#   files/etc/init.d files/etc/hotplug.d files/etc/gl-switch.d -type f) \
#   files/lib/blue-merle/functions.sh tools/blue-merle-diag.sh
```

## Sensitive files

| File | Risk |
|---|---|
| `functions.sh` | Central helpers — MAC/hostname/SSID/IMEI, lock, TTY, TAC. |
| `stage{1,2}` | Toggle SIM swap. No TTY. tmpfs state. CFUN timing. |
| `blue-merle` (CLI) | Interactive. Shared lock. Every `until` bounded. |
| `imei_generate.py` | pyserial + fcntl.flock. TAC loading fail-closed. |
| `tac-list*.txt` | Empty by default. Add only with GSMA provenance. |
| `/etc/config/blue-merle` | `stable_identity`, `tac_mode`, `original_tac`. |
| `libexec/blue-merle` | LuCI RPC. Enumerated subcommands. Masked output. |
| `Makefile` | preinst/postinst/prerm/postrm run on real Mudi. |

## Pitfalls (each has bitten us)

- `${var:offset}` → bashism. Use `cut`.
- `echo -n` → non-portable. Use `printf`.
- `mountpoint` → not in busybox. Use `awk` on `/proc/mounts`.
- `od`/`hexdump` → not in busybox. Use `/proc/sys/kernel/random/uuid`.
- `flock -E` → util-linux only. Use fd-based `flock -n 9`.
- `uci commit` → must match the section (`glconfig`, not `network`).
- `wifi-iface[1]` → may be disabled. Always `uci -q … || true`.
- `read` in stage1/2 → no TTY. Use tmpfs files.
- `read` in the CLI → stdin EOF yields the *default* (proceed) answer.
  Keep the `[ -t 0 ]` guard first and an `|| … exit 1` handler on every
  `read` (mid-swap handlers power off via `_safe_poweroff`).
- `READ_IMEI | sed …` → pipeline status is sed's (always 0). Validate
  the read first (`_is_valid_imei_shape`), mask only on success.
- LuCI `prepare-sim-swap` has no stage 2 — it must apply the same
  fail-closed invariants as stage2 (`_write_runtime_imei`, poweroff).
- TAC UI/comments must not claim `86xx`=module / `35xx`=phone; prefixes
  don't encode device class.
- Hostname must mirror the SSID name (`RANDOMIZE_IDENTITY`); iPhones
  send the device name (`Emmas-iPhone`), never a model string.
- `__pycache__` → `rm -rf` before `git add`; Makefile scrubs staged dir.
