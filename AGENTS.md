# AGENTS.md

Guidance for AI agents working on this repository. This is the single
project memory: rules, platform constraints, pitfalls, current status
and the work queue. Read it first; update the status section at the
end of every session.

## Project

Fork of [srlabs/blue-merle](https://github.com/srlabs/blue-merle) for the
GL-E750 Mudi 4G router. Package name stays `blue-merle` on-device; do NOT
rename `PKG_NAME` without rewriting every path.

Added beyond upstream: Apple masquerade (OUI MAC + iPhone hostname +
`<Name>'s iPhone` SSID), TAC policy (module preserves baseline modem TAC;
phone is user-supplied, fail-closed), `stable_identity` UCI option, per-uplink
MAC rotation, tmpfs for `/root/esim` and `/etc/oui-tertf`, fail-closed state
machine, shared modem lock.

## Current status (handoff, 2026-07-25 — session closed)

Everything is merged and PUSHED: `origin/main @ 88053ff` (`034203c` →
step series `7bc0560..b9405f4` → docs refresh `88053ff`). 97 unit
tests + CI's `sh -n` set + shellcheck `-s sh -S warning` all green;
every step-series commit individually verified green in a worktree.

Build: `dist/blue-merle_3.0.5-local-28_mips_24kc.ipk` (from `88053ff`,
content-audited, SHA256SUMS updated) is the ONLY build to flash;
local-19 predates the session. The package builds
without `feeds update` (SDK volatile — re-download per README).

### Session workflow (conventions that proved themselves)

- Work ONE queue item per session unless the user says otherwise.
- Every fix gets a regression test verified to FAIL on pre-fix code
  before the fix is applied; every commit stays green.
- Green session = `python3 tests/run_all.py` passes + `sh -n` passes
  on all shell files (CI does both).
- Never commit/push without an explicit user request; record hashes in
  the session log when landing.
- Steelman reviewer proposals before dismissing; admit errors
  explicitly ("I was wrong because X").

### Queue (priority order)

1. **Hardware testing on the Mudi** (needs the device; user holds the
   checklist: base state → paired identity → `stable_identity` →
   ifdown uplink rotation → LuCI (incl. `/root/esim/imei` matching the
   masked value BEFORE shutdown) → toggle flow → CLI → anti-forensics →
   uninstall). Main unverified assumption: MCU display pagination.
   Follow-up: after a real toggle swap, confirm `logread` has no IMEI;
   note where gl_switch child stderr lands. Flash ONLY local-28.
2. **TAC proposals — awaiting user decision:** (a) document obtaining
   provenance TACs + `original_tac` override; (b) LuCI read-only TAC
   status (mode + baseline present/absent — never the value, it reveals
   8/15 IMEI digits); (c) log line when postinst baseline capture
   fails; (d) optional `blue-merle-tac info` CLI.
3. **DHCP fingerprinting** (udhcpc PRL/options vs iOS) — research +
   hardware.
4. Housekeeping: GitHub Release with the local-28 ipk + EN release
   note (drafted 2026-07-25); decide fate of `dist/local-19`; delete
   local branches `hardening-p0`, `p0-libexec-hardening`, `tac-filter`;
   optional symmetric gl_clients guard in `volatile-client-macs stop()`;
   confirm CI green on the pushed commits.

### Session log 2026-07-25 (steps 1-7)

- `c41c56b` — `imei_generate.py` logs masked only (`_mask_id`,
  `_scrub_at_output`); stage1/stage2/libexec drop stderr too.
- `bcf7cde` — CLI: `[ -t 0 ]` guard, EOF handler on every `read`
  (mid-swap → `_safe_poweroff`), CFUN=4 loop bounded to 15.
- `3553010` — canonical masks (IMEI first6+last3, IMSI first5+last4)
  in fail-closed `_mask_imei`/`_mask_imsi`; libexec/diag/docs aligned.
- `4782da6` — `_pick_random_line` uses POSIX `[[:space:]]`; `\s`
  banned in shell files by a static test.
- `3c59fe6` — `volatile-client-macs start()` stops/restarts a running
  gl_clients around the tmpfs mount.
- `d127a81` — batch: stage2/sim.sh switch-marker cleanup, newmac
  `--uplink --full` help, MCU JSON SSID sanitizing, shellcheck SHA256
  pin, CI no longer runs `feeds update`.
- `b9405f4` — repo hygiene (real-ESSID diag log deleted, stale ipk
  pruned); `88053ff` — README/USAGE refreshed and compressed.

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
