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

## Rules

- **Never push without explicit user request.** Never commit/amend without
  explicit "commit".
- **Never print full IMEI/IMSI.** Use masked forms (`354567******1234`).
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
- `READ_IMEI | sed …` → pipeline status is sed's (always 0). Validate
  the read first (`_is_valid_imei_shape`), mask only on success.
- LuCI `prepare-sim-swap` has no stage 2 — it must apply the same
  fail-closed invariants as stage2 (`_write_runtime_imei`, poweroff).
- TAC UI/comments must not claim `86xx`=module / `35xx`=phone; prefixes
  don't encode device class.
- Hostname must mirror the SSID name (`RANDOMIZE_IDENTITY`); iPhones
  send the device name (`Emmas-iPhone`), never a model string.
- `__pycache__` → `rm -rf` before `git add`; Makefile scrubs staged dir.
