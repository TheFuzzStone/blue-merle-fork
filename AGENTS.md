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

## Current status (handoff, 2026-07-25 — hardware session, SIM items pending)

`origin/main @ c3ec9ad` — all three hardware fixes committed and
pushed. **`dist/blue-merle_3.0.5-local-33_mips_24kc.ipk` is THE build
to flash** (content-audited: hooks 02/03, grep -ow, Depends includes
python3-logging/urllib; SHA256SUMS updated; local-28 pruned). Mudi is
running local-33 — verified on the official package files: version,
hooks, python deps, read-identifiers `868186******309`, rotation
(sta uci == runtime == macclone, ~2 s, fresh DHCP lease). Remaining
checklist items need 2 SIMs → `SIM-SESSION-CHECKLIST.md` (gitignored).
Queue re-prioritised same day by user decision: Top-4 (volatile uplink
history → iOS DHCP fingerprint → Apple vendor IE → GL telemetry
"go dark") then Second tier — see Queue. UNCOMMITTED.

Session checklist record: base state ✅ →
paired identity at reboot ✅ (all identifiers rotated, WiFi key md5
unchanged, runtime=UCI) → `stable_identity` ✅ (boot freeze identical;
hooks no-op under =1) → ifdown uplink rotation ✅ **after fix #2**
(both stores rotated ~2 s, runtime == staged, new DHCP lease) →
LuCI flow ✅ **after fix #3** (prepare-sim-swap: mask ==
/root/esim/imei == modem readback == `868186******309`, TAC 868186
preserved, 0 fifteen-digit lines in logread; TAC RPCs: phone-mode
fail-closed on empty list, unknown subcommand rc=2). LuCI web page
itself NOT yet eyeballed by the user.
Next: toggle flow (needs user + 2 SIMs; THE MCU pagination test) →
CLI (interactive; needs SIM swap mid-flow) → anti-forensics →
uninstall.
Device state: no SIM, uplink = WiFi repeater (wwan/wlan-sta0),
stable_identity=0, modem IMEI now `868186******309` (changed by the
LuCI test), CFUN restored to 1.

**THREE hardware finds, all fixed in tree (UNCOMMITTED, device
hot-patched, next ipk must include them):**

1. `gl_modem` passes CRLF through → `READ_IMEI`/`READ_IMSI` captured a
   trailing `\r` (len 16); every fail-closed gate misfired (stage2 /
   prepare-sim-swap would power off after *successful* writes).
   Fix: `grep -ow` in functions.sh. Tests: `tests/test_read_helpers.py`.
2. Uplink rotation broken two ways: (a) hook rotated only
   `glconfig.general.macclone_addr`, but FW 4.3.26's repeater runtime
   MAC comes from `wireless.sta.macaddr` (netifd applies it per-ifup;
   GL's `repeater` binary re-reads macclone_addr only at boot-restore /
   network change) — per-ifdown rotations never reached the air;
   (b) hooks numbered 30/31 ran AFTER 15/16-mwan3 + 20-firewall in the
   shared hotplug queue → commit landed ~28 s after ifdown, past the
   follow-up ifup (netifd doesn't wait). Fix: hooks renamed to
   `02-/03-`, and `03-blue-merle-uplink-mac` also rotates
   `wireless.sta.macaddr` (same NEW_MAC) when a sta config exists.
   Tests: `tests/test_hotplug_uplink.py` (functional with stub uci).
   Verified on hardware: rotation commits ~2 s after ifdown, runtime
   MAC == staged value, upstream hands out a fresh DHCP lease.
3. `imei_generate.py` could not run AT ALL: `ModuleNotFoundError:
   logging` — OpenWrt's python3-light lacks `logging`, and `pathlib`
   pulls `urllib` (also split). EXTRA_DEPENDS had only python3-pyserial
   → every IMEI-write path died on a stock install. Fix: Makefile
   EXTRA_DEPENDS += `python3-logging, python3-urllib`. Test:
   `test_makefile_declares_split_python3_modules_used_by_imei_generate`.
   On device: both packages installed via `opkg update && opkg install`.

107 tests + `sh -n` green. Device hot-patch state: functions.sh
(grep -ow), hotplug hooks (renamed + sta rotation), python3-logging +
python3-urllib installed.

Minor findings (no fix yet):
- Boot-time `logger` lines from init.d S10 never reach logread
  (logd starts at S12log) — e.g. the stable_identity notice is lost.
- `/etc/mcuversion` absent on FW 4.3.26 → postinst prints "Could not
  detect MCU version"; MCU pagination still unverified.
- Guest SSIDs keep factory `GL-E750-a19-Guest` (both disabled).
- ifup after manual ifdown takes ~20-30 s (netifd retry cycle: "link
  connectivity loss" → recover) — platform behaviour, not ours.

Everything before this session is merged and PUSHED: `origin/main @
f5e7173` (`034203c` → step series `7bc0560..b9405f4` → docs/cleanup
`88053ff..f5e7173`). 98 unit tests + CI's `sh -n` set + shellcheck
`-s sh -S warning` all green; every step-series commit individually
verified green in a worktree.

Everything before this session is merged and PUSHED: `origin/main @
f5e7173` (`034203c` → step series `7bc0560..b9405f4` → docs/cleanup
`88053ff..f5e7173`). 98 unit tests + CI's `sh -n` set + shellcheck
`-s sh -S warning` all green; every step-series commit individually
verified green in a worktree.

Build: local-28 (from `88053ff`) was flashed for the session start;
local-33 (from `c3ec9ad`) superseded it the same day with all three
fixes. The GitHub Release `v3.0.5-local` still carries local-28 —
consider re-releasing from local-33 after the SIM session confirms
the toggle/CLI paths. The package builds without `feeds update`
(SDK volatile — re-download per README).

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

0. **Hardware testing on the Mudi — BLOCKED on 2 physical SIM cards**
   (user will buy): toggle flow (= the MCU pagination test) → CLI →
   anti-forensics → uninstall. The full step-by-step lives in
   `SIM-SESSION-CHECKLIST.md` (gitignored, on the user's machine).
   Everything automatable was done 2026-07-25 (see Current status).

**Top-4 (do in this order — all seen first-hand on hardware):**

1. **Volatile uplink history.** `wireless.sta` persists every upstream
   network (SSID + BSSID + key) on NAND — a geolocatable movement log
   (BSSID → WiGLE) of everywhere the router has been. Options: never
   commit sta config to NAND (tmpfs shadow), or `blue-merle-purge-history`
   + auto-purge on network change. Biggest open anti-forensics hole.
2. **iOS-faithful DHCP fingerprint.** Masquerade contradicts itself at
   L3: Apple MAC + `Lucass-iPhone` hostname, but udhcpc sends a
   Linux-grade PRL/option set/vendor class — one packet gives it away.
   Research the exact iOS DHCPDISCOVER/REQUEST (PRL order, option set,
   no vendor class) and mimic it (udhcpc knobs or a shim). Absorbs the
   old queue item "DHCP fingerprinting".
3. **Apple vendor IE in beacons.** A real iPhone hotspot carries Apple
   vendor-specific IEs in beacon/probe-response; ours broadcasts plain
   hostapd frames. `hostapd` accepts `vendor_elements=hex` — research
   the exact bytes of an iOS Personal Hotspot beacon and apply them
   (per-radio; keep within the 750-byte IE limit).
4. **GL telemetry audit + "go dark" switch.** `99-gl-cloud` (GoodCloud/
   DDNS) calls home to GL servers — an "iPhone" talking to a router
   vendor's cloud is a self-own, besides the privacy leak. Inventory
   everything that phones home (gl-cloud, gl_health, cron jobs), then
   one UCI switch to silence it all.

**Second tier (in this order):**

5. **Ship the selftest.** `tools/blue-merle-diag.sh` is not in the ipk
   — package it (redacted) + a LuCI status page so users can verify
   masquerade coherence themselves (hostname↔SSID, pool MACs, tmpfs,
   no IMEI in logs).
6. **Guest SSID de-fingerprinting.** Both guest networks still broadcast
   (disabled, but configured) `GL-E750-a19-Guest` — one toggle and the
   hardware model is on the air. Rotate/rename alongside the main SSID
   or neutralise the defaults at install.
7. **Uplink-interface leak audit.** What else escapes via wlan-sta0/
   wwan0: avahi/mDNS announcements, IPv6 (RA/MLD/DHCPv6 link-local),
   `modem_AT` log destinations, GL persistent logs (`gl_logread`).
   Audit first, then plug.
8. **NAND wear + flash history.** Several `uci commit` per boot leave
   stale identifiers in erase blocks (README admits it) and wear NAND.
   Minimum: batch commits (one per file). Maximum: volatile store for
   rotated values.
9. **Session smalls.** Boot-time `logger` from S10 is lost (logd starts
   at S12log) — buffer and flush later. `/etc/mcuversion` absent on
   FW 4.3.26 — find where GL exposes the MCU version and fix the
   postinst/diag detection.

10. **TAC proposals — awaiting user decision:** (a) document obtaining
    provenance TACs + `original_tac` override; (b) LuCI read-only TAC
    status (mode + baseline present/absent — never the value, it reveals
    8/15 IMEI digits); (c) log line when postinst baseline capture
    fails; (d) optional `blue-merle-tac info` CLI.

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
- `c053a5a`/`f5e7173` — TODO.md merged into this file (RU docs
  dropped), vcm `stop()` gl_clients guard, branches + local-19 pruned.
  User decision: GitHub Actions dropped from the plan entirely
  (2026-07-25) — do not re-propose CI work.

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
- `gl_modem` passes CRLF through → captured values carry a trailing
  `\r`. Always extract with `grep -ow`, never `grep -w` on a line.
  (Killed every IMEI flow on real hardware; unit tests with stubs
  that emit `\n`-only will NOT catch this — stubs must use CRLF.)
- `/etc/hotplug.d/iface/` runs alphabetically and netifd does NOT wait;
  GL's 15/16-mwan3 + 20-firewall take ~28 s on the Mudi. Anything
  numbered after them commits long past the follow-up ifup.
- Repeater runtime MAC comes from `wireless.sta.macaddr` (applied by
  netifd per ifup), NOT from `glconfig.general.macclone_addr` (read by
  the GL `repeater` binary only at boot-restore / network change).
  Rotating macclone_addr alone never reaches the air interface.
- LuCI `prepare-sim-swap` has no stage 2 — it must apply the same
  fail-closed invariants as stage2 (`_write_runtime_imei`, poweroff).
- TAC UI/comments must not claim `86xx`=module / `35xx`=phone; prefixes
  don't encode device class.
- Hostname must mirror the SSID name (`RANDOMIZE_IDENTITY`); iPhones
  send the device name (`Emmas-iPhone`), never a model string.
- `__pycache__` → `rm -rf` before `git add`; Makefile scrubs staged dir.
