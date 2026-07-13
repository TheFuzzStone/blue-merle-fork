# AGENTS.md

Guidance for AI agents (Claude, etc.) working on this repository.

## What this project is

**blue-merle-fork** — a fork of
[srlabs/blue-merle](https://github.com/srlabs/blue-merle), a privacy
tool for the GL-E750 Mudi 4G router. See [`README.md`](./README.md)
for the change list vs. upstream.

The repository, the package (opkg), and every on-device path all keep
the upstream name **blue-merle**. Do NOT rename `PKG_NAME` in the
Makefile without a full uninstall/reinstall on the target and a
matching rewrite of every path in the tree.

Key features added beyond upstream: Apple-device masquerade (OUI MACs
+ iPhone hostname + `<Name>'s iPhone` SSID), dual-mode TAC filter
(module/phone IMEI TACs), `stable_identity` UCI option, per-uplink
MAC rotation, tmpfs for `/root/esim` and `/etc/oui-tertf`.

## Ground rules

- **Never push to `origin`** unless the user explicitly asks. All work
  lives on the `main` branch.
- **Never commit, amend, push, or create PRs unless the user explicitly asks.**
  Show diffs, propose commit messages; wait for the user to say "commit".
- **Never log or print full IMEI/IMSI values.** Use masked forms
  (`354567******1234`) for user-visible output.
- **`shred` is banned.** It is theatrical on NAND flash (wear leveling)
  and pointless on tmpfs. Use `rm`, or better, mount tmpfs.
- **Do not add MAC generators without the U/L bit set unless the caller
  explicitly opts into an Apple OUI.** Free-form random MACs must be
  locally-administered (RFC 7844). Apple-OUI MACs are the exception,
  handled via `APPLE_MAC_GEN` only.

## Quality standard (read this before every response)

This project protects people in high-risk situations. Mistakes can have
real-world consequences. Therefore:

- **Self-verify every claim before stating it.** Read the actual code,
  run the actual command, check the actual file — do not rely on memory
  or assumptions. If you are not sure, say "I am not sure" and verify.
- **Do not optimise for token efficiency or response speed.** Thoroughness
  is more important than brevity. Take the extra turn to read a file,
  run a test, or grep for a pattern before answering.
- **When proposing a fix, walk through the code path mentally** — trace
  every function call, every variable, every branch. Ask yourself:
  "what happens if this variable is empty? what if the file is missing?
  what if the modem is in CFUN=4?"
- **When reviewing someone else's proposal, steelman it first.** Assume
  they are right and find the strongest argument for their position.
  Only then evaluate whether your counter-argument still holds. We have
  already been wrong once by dismissing a reviewer's suggestion too
  quickly (the TAC/Quectel discussion) — do not repeat that mistake.
- **Admit errors explicitly.** If a previous answer was wrong, say "I was
  wrong because X" and correct it. Do not quietly move on.

## Files that need caution

| File | Why it's sensitive |
|---|---|
| `files/lib/blue-merle/functions.sh` | Central helpers — MAC/hostname/SSID randomizers, IMEI readers, `_rand16`, `_resolve_modem_tty`. Every function used by init, CLI and toggle. |
| `files/usr/bin/blue-merle-switch-stage{1,2}` | Toggle-driven SIM swap. Runs without TTY. Split across two processes with tmpfs state. Timing-sensitive around `AT+CFUN=4` (asynchronous). Both now resolve TAC mode from UCI before calling Python. |
| `files/usr/bin/blue-merle` | Interactive CLI. Uses the shared fd-based modem lock. Must not deadlock; every `until` must be bounded. |
| `files/lib/blue-merle/imei_generate.py` | Talks to modem over pyserial with `exclusive=True` + `fcntl.flock`. Loads TAC list from external file via `_load_tac_list()` with fallback. |
| `files/lib/blue-merle/tac-list.txt` | Documentation / optional explicit TAC list. Do not add values without authoritative GSMA provenance. Default module mode preserves the physical modem TAC instead. |
| `files/lib/blue-merle/tac-list-phone.txt` | User-supplied advanced-mode list; intentionally empty and fail-closed until verified TAC allocations are added. |
| `files/etc/config/blue-merle` | UCI config: `stable_identity` (freeze identity across reboots) and `tac_mode` (module/phone). Both control boot-time and rotation behaviour. |
| `files/usr/libexec/blue-merle` | RPC entry point for LuCI. Enumerated subcommands only. Resolves TAC/TTY, validates phone TAC data, and writes UCI through exact mode-specific commands. |
| `Makefile` | `preinst`/`postinst` run on the actual Mudi. Bugs here = broken install. Also scrubs dead filenames and `__pycache__` from staged pkgdir. |
| `files/usr/share/rpcd/acl.d/luci-app-blue-merle.json` | LuCI ACL. Do not add wildcards. Every subcommand enumerated explicitly. |

## Target platform

- **Architecture:** `mips_24kc` (ath79/nand)
- **OpenWrt:** 23.05, busybox ash (not bash). Avoid `[[ ]]`, `==`,
  bash arrays, `${var:offset:length}`, `echo -n`/`echo -ne`. Test
  scripts with `sh -n`.
- **Modem:** Quectel EP06-E/A, controlled via AT commands. TTY is
  discovered dynamically by `_resolve_modem_tty` (falls back through
  `/dev/ttyUSB{3,2,1,0}`). Override via `BLUE_MERLE_TTY` env.
- **MCU:** 16x2 char display accessed via `/dev/ttyS0` JSON protocol.
- **Python:** 3.x from `python3-pyserial` package.

## Build

```sh
# See README.md §Build for the full sequence.
SDK=/tmp/opencode/bm-build/openwrt-sdk-23.05.0-ath79-nand_gcc-12.3.0_musl.Linux-x86_64
cd $SDK && make -j$(nproc) package/blue-merle/{clean,compile} V=s
# Result: bin/packages/mips_24kc/base/blue-merle_3.0.5-local-*.ipk
cp $SDK/bin/packages/mips_24kc/base/blue-merle_*.ipk ./dist/
```

## Test

```sh
python3 tests/run_all.py   # all tests must pass (count may grow)
```

If pytest is not available, `run_all.py` is a lightweight replacement.

## Common pitfalls (each one has bitten us — learn from our pain)

- **`${var:offset:length}` is a bashism.** Busybox ash does not support
  it. Use `printf '%s' "$var" | cut -c1-6` instead. `sh -n` will not
  catch this — it fails at expansion time on the device.

- **`echo -n` / `echo -ne` are non-portable.** Busybox echo behaviour
  depends on `CONFIG_FEATURE_FANCY_ECHO`. Use `printf` consistently.

- **`mountpoint` is not in busybox.** Use `grep -q " $dir " /proc/mounts`
  instead. The `mountpoint -q` command silently failed and spammed the
  boot log with "mountpoint: not found" on every reboot.

- **`od` and `hexdump` are not in busybox on stock Mudi.** The old
  `od -An -N2 -tu2 /dev/urandom | tr -d ' '` returned empty → every
  `$(( "" % N + 1 ))` evaluated to 1 → rotation always picked the
  first entry (`Aaron`, `iPhone-X`). Use `/proc/sys/kernel/random/uuid`
  instead — kernel interface, no external tools. See `_rand16`.

- **`uci commit` matters:** setting `glconfig.general.macclone_addr`
  requires `uci commit glconfig`, not `uci commit network`.

- **5 GHz interface may be disabled** in the user's config: always use
  `uci -q … 2>/dev/null || true` when touching `wireless.@wifi-iface[1]`.

- **Interactive `read` in stage1/stage2:** these run without TTY. Never
  `read` there; use tmpfs state files instead.

- **`__pycache__` leaking into ipk:** local test runs create bytecode.
  Makefile scrubs it at package time, but also `rm -rf` before `git add`.

- **Entropy at boot on MIPS-without-hwrng:** `entropy_avail` can be
  128–256 during `START=10` init. `/proc/sys/kernel/random/uuid` still
  works but quality may be low. Not a blocker for privacy randomization.

## When exploring / auditing

- Use `python3 tests/run_all.py` as a smoke test after any change.
- `sh -n path/to/script` to verify POSIX syntax.
- `USAGE.md` and `USAGE_RU.md` document day-to-day commands; update
  if behavior changes.
