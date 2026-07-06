# blue-merle-fork

> ⚠️ **Disclaimer — please read.**
>
> This project is provided strictly for **educational and research purposes**.
> Changing a device's IMEI may be **illegal in your jurisdiction** and can carry
> criminal penalties. The author does not encourage, endorse, or incite anyone
> to use this software for any purpose. You alone are responsible for
> your actions.

> **TL;DR:** Fork of [srlabs/blue-merle](https://github.com/srlabs/blue-merle) for the
> GL-E750 Mudi 4G travel router. Fixes upstream bugs, adds an Apple-device
> masquerade (iPhone hostname + Apple MACs + `<Name>'s iPhone` SSID), and ships
> 44 unit tests. Install in 3 commands from [Releases](../../releases).

The **GL-E750 Mudi** is a pocket-sized 4G WiFi router marketed to
privacy-conscious users. The upstream *blue-merle* package lets you change
its IMEI, randomise MACs and wipe client-MAC logs. This fork inherits all
of that and adds:

- **Bug fixes** — upstream had a deadlock, an entropy bug that always picked
  the same name, an IMEI leak to syslog, and a flash-persistence hole.
- **Apple masquerade** — the router now looks like an iPhone Personal Hotspot
  to anyone scanning WiFi (Apple OUI MAC + `iPhone-15-Pro` hostname +
  `Emma's iPhone` SSID), not a `GL-E750-<serial>`.
- **44 unit tests** — upstream shipped none.

**Target:** GL-E750 firmware `4.3.26` with MCU ≥ `1.0.7`

**Package:** `blue-merle_3.0.5-local` (opkg name unchanged from upstream)

**Usage:** [`USAGE.md`](./USAGE.md) (EN) | [`USAGE_RU.md`](./USAGE_RU.md) (RU)

**For AI agents:** [`AGENTS.md`](./AGENTS.md)
**License:** BSD-3-Clause — see [`LICENSE.md`](./LICENSE.md)

## Prerequisites

- A **GL-E750 Mudi** router running firmware **4.3.26** (other 4.3.x may work).
- **SSH access** to the Mudi (enabled by default; root password = web UI password).
- Your PC on the Mudi's WiFi or LAN (Mudi's default IP is `192.168.8.1`).

## Install

### Option A: prebuilt ipk (recommended)

Download `blue-merle_3.0.5-local-*.ipk` and `SHA256SUMS` from the
[Releases](../../releases) page, verify, then install:

```sh
# verify checksum
sha256sum blue-merle_3.0.5-local-*.ipk    # must match SHA256SUMS

# install
scp -O blue-merle_3.0.5-local-*.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 \
  'opkg install --force-reinstall /tmp/blue-merle_3.0.5-local-*.ipk && reboot'
```

**After reboot:** the WiFi network name will change (e.g. from
`GL-E750-a19` to `Emma's iPhone`). Your laptop won't auto-connect —
select the new network and enter the **same password** as before.
The password never rotates.

### Option B: build from source

You probably don't need this — use the prebuilt ipk above. If you want
to build yourself, see [Build from source](#build-from-source) at the
bottom of this file.

---

## Delta vs. [srlabs/blue-merle](https://github.com/srlabs/blue-merle) v3.0

Every row: **what** — *why*.

### 1. Anti-anonymity leaks fixed (critical)

The tool exists to erase forensic artefacts. Upstream still shipped
several. Each of these is a place where the identifier we're trying to
hide was leaking somewhere despite the rest of the code being correct.

| Change | Why |
|---|---|
| Removed IMEI values from `logger`/`syslog` in stage2 | Upstream wrote `old→new IMEI` on every rotation → survives in `logread`. |
| Mounted tmpfs on `/root/esim`, wiped flash originals before mounting | Upstream PR #63 wrote the new IMEI to flash; after unmount the plaintext IMEI remained recoverable from NAND. Now the file lives only in RAM and the pre-existing flash copy is removed both at install-time (Makefile preinst) and every boot (init.d). |
| MAC generator sets locally-administered bit (`U/L=1`) | Old mask only cleared I/G, so ~50 % of "random" MACs impersonated real vendors → WIDS spoofing alerts and OUI collisions. |
| Replaced `shred` with `rm`; removed `coreutils-shred` dependency | Shred is theatre on NAND (wear-leveling) and pointless on tmpfs; it only created a false sense of destruction. |
| Masked IMEI/IMSI on MCU display and in LuCI | Full identifiers left over the serial link and over unencrypted HTTP. |
| Diagnostic script masks name-pool samples | Section 7/8 previously printed 30–35 raw first names → ~13 % chance the current live SSID name leaked into a pastable report, plus leakage of the PRNG state. |

### 2. Correctness bugs fixed

Real bugs that made upstream not do what it says on the tin.

| Change | Why |
|---|---|
| `AT+QPOWD` → `AT+CFUN=1,1` in CLI reset path | `QPOWD` powered the modem off; the following `AT+CIMI` loop then waited forever. |
| Lua `luhn_digit` returns `0` for `sum%10==0` (later removed with the whole dead Lua path) | Previously returned `10`, producing 16-char IMEIs. |
| Python: `random.sample` → `random.choices` | Sampling without replacement removed repeated digits from the tail — a statistical fingerprint of blue-merle IMEIs. |
| `_rand16` reads `/proc/sys/kernel/random/uuid` instead of `od`/`hexdump` | Stock Mudi busybox has no `od`; the old picker returned empty → index 1 forever (`Aaron`, `iPhone-X` on every reboot). |
| `fcntl.flock` on the serial fd in `imei_generate.py` | pyserial's `exclusive=True` only blocks new `open()`s; a zombie process holding the fd could interleave AT bytes. Two kernel layers (TIOCEXCL + advisory flock) prevent that. |
| Central `_resolve_modem_tty` helper used in every caller | `/dev/ttyUSB3` was hard-coded in stage1/stage2/libexec while only the CLI probed dynamically — a shifted USB enumeration silently broke toggle-driven and LuCI SIM-swap. |
| stage1 persists real `old_imei`/`old_imsi` on tmpfs | Upstream shared them as shell variables between processes → always empty in stage2 → "Did you swap the SIM?" unreachable. |
| Every `until … done` loop bounded | Unbounded retries hung until the outer 90 s timeout, sometimes leaving the modem mid-transition. |
| `gl_clients stop` no longer skipped on 4.3.26 | An early `exit 0` in preinst risked SQLite corruption when tmpfs mounted over the open db. |
| `postrm` runs `uci commit` | Restoring `switch-button` to `tor` was silently discarded on the next reboot after uninstall. |
| IMSI regex accepts 14–15 digits | Fixed-15 broke deterministic mode on shorter IMSIs; ITU-T E.212 allows both. |
| Serial reads loop until `OK`/`ERROR` | A single 64-byte read could miss fragmented modem responses. |
| Python: `exit(1)` instead of `exit(-1)` | POSIX turned `-1` into 255, confusing shell wrappers. |
| `flock -n -E 99` in CLI | Without `-E`, lock-contention exit code (1) collided with the child's own `exit 1` (e.g. user answers 'n' at the prompt), so the "another operation in progress" message printed on every rejected prompt. |
| Hotplug BSSID rewrite moved from `ifup` to `ifdown`, run synchronously | Writing on ifup was off-by-one — the new BSSID only surfaced at the *next* `wifi reload`. Ifdown writes it in time for the immediately-following ifup. Synchronous execution prevents a race with that follow-up ifup. |
| `blue-merle-newmac --uplink` bounces only `wwan`/`wan` via `ifdown/ifup` | Upstream's `service network restart` also cycled wlan → AP clients were kicked, contrary to the flag's promise. |

### 3. Anonymity features added

Upstream randomised WiFi-facing MACs at boot and left everything else
alone. This fork rotates a coherent Apple identity end-to-end.

| Change | Why |
|---|---|
| Apple OUI pool (`apple-oui.txt`, 30 real Apple prefixes) | Consistent story: MAC vendor lookup matches the iPhone hostname & SSID. |
| iPhone hostname pool (`iphone-models.txt`, 25 models) | Replaces `Mudi-<serial>` — a stable per-device fingerprint that also identified the model. |
| Personal-Hotspot SSID rotation (`<Name>'s iPhone`, 244 US names) | Replaces `GL-E750-<serial>` — WIGLE-indexable and model-identifying. |
| Dual-mode TAC filter (`tac-list.txt` + `tac-list-phone.txt`, 14 module + 78 phone TACs) | Upstream used smartphone TACs (`35xxxxxx`) which cause a capability-mismatch flag at the operator's TAC-lookup: "Samsung Galaxy" TAC on a data-only LTE modem with Linux DHCP. Module TACs (`86xxxxxx` — Quectel, Sierra, Telit, u-blox) match the device's actual behaviour. Phone TACs (6 manufacturers: Samsung, Apple, Xiaomi, Huawei, Google, OnePlus) serve as fallback when operators block consumer SIMs on module TACs. Switchable via LuCI dropdown or `uci set blue-merle.main.tac_mode=phone`. |
| Ethernet MAC + hostname + per-uplink MAC rotation | Upstream only touched WiFi MACs at boot → Ethernet and hostname stayed as factory fingerprints between locations. |
| `blue-merle-newmac`, `blue-merle-newssid` CLIs (`--uplink`, `--full`, `--dry-run`, `--pure-random`) | On-demand rotation without a reboot; different modes for different needs (repeater-switch, full identity change, RFC-7844 mode). |
| Hotplug BSSID rewrite on WiFi `ifdown` (`30-blue-merle-bssid-on-ifdown`) | Every `wifi reload` now yields a fresh BSSID in the air on the very next ifup. |
| Hotplug upstream-MAC rotation on `wwan`/`wan` `ifup` (`31-blue-merle-uplink-mac`) | Switching hotspots without a reboot no longer reuses the same MAC. |
| Opt-in `stable_identity` UCI flag | Users whose threat model favours realism over unlinkability can freeze the whole identity across reboots with one `uci set` — see the tradeoff section below. |

### 4. Defense-in-depth

| Change | Why |
|---|---|
| LuCI ACL enumerated (no `blue-merle *` wildcard) | Removed dead `shred`/`upload.ipk` entries and an unbounded exec surface. |
| Confirmation modals on SIM-swap and Shutdown | A misclick used to instantly kill the modem or power off the device. |
| CLI `blue-merle` serialised via `flock` | Concurrent AT access to `/dev/ttyUSB3` left the modem inconsistent. |
| `/dev/ttyS0` writes guarded by a character-device test | SDK / buildroot installs crashed on the MCU write. |
| Dynamic modem TTY discovery (`BLUE_MERLE_TTY` env override) | Hardcoded `/dev/ttyUSB3` broke on USB re-enumeration. |
| `preinst` refuses instead of blocking on `read` when non-TTY | ansible / cloud-init installs used to hang forever. |
| Makefile install-time scrub of dead filenames + `__pycache__` | Even if `luhn.lua` or `30-blue-merle-rerandomize` slipped back into the source tree as untracked, they will not ship in the ipk. |

### 5. Cleanup

| Change | Why |
|---|---|
| ~250 lines of dead LuCI code removed | Opkg-management boilerplate, `handleConfig` with undefined `resolveFn`/`rejectFn`, broken `randomIMEI` referencing an undefined variable. |
| Removed dead Lua IMEI path (`luhn.lua`, `GENERATE_IMEI`, `SET_IMEI`) | Second generator disagreeing with the Python one — dangerous if ever accidentally used (random TAC would produce IMEIs that don't match any real device). |
| `chmod +x` in git for all shell scripts | Upstream relied on `$(INSTALL_BIN)` to set the bit; `git clone && ./script.sh` was broken. |
| `postinst`/`postrm` guarded by `IPKG_INSTROOT` | Buildroot builds failed on device-specific commands. |
| `PKG_VERSION`: `2.0.5` → `3.0.5-local` | Upstream `main` was stale relative to its own v3.0 release. |

### 6. Tests

Upstream shipped no test suite. This fork has **44 unit tests** under
`tests/` covering Luhn digit correctness (incl. the all-zero edge
case that regressed in Lua), IMEI generation and validation, entropy
of the random tail, deterministic-mode reproducibility, MAC bit
patterns (RFC 7844 + Apple OUI), hostname/SSID pool validity,
`_rand16` resilience with `od` scrubbed from `$PATH`, and
`fcntl.flock` retry behaviour. Every regression above has at least
one guard.

```sh
python3 tests/run_all.py     # 44 passed, 0 failed
```

---

## What is *not* changed from upstream

- Quectel `AT+EGMR` mechanism for IMEI writes.
- The two-stage SIM-swap workflow triggered by the hardware toggle.
- BSD-3 license and copyright headers.
- LuCI menu integration point (`admin/network/blue-merle`).
- Overall project structure — same Makefile layout, same install paths.

---

## Threat-model tradeoff (Apple masquerade)

The masquerade defaults trade **realism** for **session
unlinkability**, and these two goals genuinely conflict:

- **Rotating** hostname/BSSID/SSID at every boot defeats
  correlation-across-locations by WIGLE-style scanners and by any
  upstream keeping DHCP-lease history.
- **A real iPhone** keeps its Personal-Hotspot SSID and hostname
  stable across boots. An observer who sees an "iPhone" whose name
  changes every reboot may flag the device as anomalous.

**The default is unlinkability** because stable IDs are trivially
correlated across cafés A→B→C, while distinguishing "iPhone that
rebooted with a new name" from a masquerade requires deeper
fingerprinting (DHCP option order, TLS ClientHello, timing). If your
adversary is a targeted observer rather than a passive tracker, flip
the tradeoff with one flag:

```sh
uci set blue-merle.main.stable_identity=1
uci commit blue-merle
service blue-merle reload
```

Boot-time rotation now leaves hostname, BSSID, SSID **and**
client-visible MACs alone — you get one stable Apple-style identity
until you manually invoke `blue-merle-newmac --full`. Matches real
iPhone behaviour.

Any pattern is a fingerprint; any absence of a pattern is also a
fingerprint. Pick the one that hurts your specific adversary more.

---

## Build from source

Requires OpenWrt SDK 23.05 for `ath79/nand` (mips_24kc).

```sh
cd "$OPENWRT_SDK"
ln -s "$PWD/../blue-merle" package/blue-merle
./scripts/feeds update -a && ./scripts/feeds install -a
echo "CONFIG_PACKAGE_blue-merle=m" >  .config
echo "CONFIG_SIGNED_PACKAGES=n"    >> .config
make defconfig
make -j"$(nproc)" package/blue-merle/compile V=s
# result: bin/packages/mips_24kc/base/blue-merle_3.0.5-local-*.ipk
```

---

## Limitations (what this tool does NOT protect against)

- **DHCP fingerprinting.** The Mudi runs a Linux DHCP client, not
  iOS. A sophisticated observer comparing DHCP option ordering can
  distinguish "iPhone hostname on Linux stack" from a real iPhone.
  Use `--pure-random` and remove the iPhone hostname pool if this
  matters to you.
- **TLS fingerprinting.** Traffic through the Mudi carries the
  ClientHello fingerprint of whatever client (browser, app) made the
  connection — blue-merle does not proxy or modify TLS.
- **Traffic analysis.** Volume, timing and destination patterns are
  visible to the ISP and to anyone monitoring the upstream link.
- **Active probing.** An adversary who sends crafted packets and
  observes the Mudi's responses can fingerprint the OS and services
  regardless of MAC/hostname/SSID.
- **Physical seizure.** If the device is captured while running,
  RAM contents (including tmpfs-mounted identifiers) are recoverable
  via cold-boot attacks. If captured while powered off, flash
  contents are recoverable via chip-off — `shred` does not help on
  NAND (wear leveling). Physical destruction is the only reliable
  countermeasure.

blue-merle-fork raises the cost of casual tracking and forensic
recovery. It does not make you invisible to a determined adversary
with physical access or deep network monitoring.

## Why this fork is not upstreamed

- Some changes are opinionated defaults (Apple-OUI MACs, iPhone
  hostnames, hotspot SSID) that fit *this* author's threat model but
  are debatable in general — upstream would rightly ask about the
  DHCP-fingerprint mismatch between "iPhone hostname" and a Linux
  DHCP client.
- The scope is broad and hard to bisect into small PRs.

Individual single-bug fixes suitable for upstream submission:
`AT+QPOWD` deadlock, Lua Luhn digit, `random.sample` entropy,
syslog IMEI leak, `postrm` uci commit, `_rand16` `od` dependency,
`flock -E`.
