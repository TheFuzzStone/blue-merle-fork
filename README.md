# blue-merle-fork

> ⚠️ **For educational and research purposes only.** Changing a device's
> IMEI may be illegal in your jurisdiction. The author does not encourage
> or endorse any use. You alone are responsible for your actions.

Fork of [srlabs/blue-merle](https://github.com/srlabs/blue-merle) for the
**GL-E750 Mudi** 4G travel router. Fixes upstream bugs, adds an Apple-device
masquerade, hardens the IMEI-change state machine, and ships a regression
test suite.

- **Target:** firmware `4.3.26`, MCU ≥ `1.0.7`
- **Package:** `blue-merle_3.0.5-local` (opkg name unchanged)
- **Usage:** [`USAGE.md`](./USAGE.md) (EN) | [`USAGE_RU.md`](./USAGE_RU.md) (RU)
- **AI agents:** [`AGENTS.md`](./AGENTS.md)
- **License:** BSD-3-Clause

## Install

Download from [Releases](../../releases), verify checksum, then:

```sh
scp -O blue-merle_3.0.5-local-*.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'opkg install --force-reinstall /tmp/blue-merle_*.ipk && reboot'
```

After reboot the WiFi name changes (e.g. `GL-E750-a19` → `Emma's iPhone`).
Reconnect with the **same password** — it never rotates.

## What changed vs. upstream

### Privacy leaks fixed

- IMEI values removed from syslog (upstream logged old→new on every rotation)
- `/root/esim` tmpfs — IMEI lives in RAM only, flash originals wiped
- MAC generator sets U/L bit (was impersonating real vendors 50% of the time)
- `shred` → `rm` (theatrical on NAND); `coreutils-shred` dependency dropped
- IMEI/IMSI masked on MCU and in LuCI RPC (masked-only, no full-value reveal)
- Diagnostic report no longer emits raw `iwinfo`/`iw`/log identifiers

### Correctness bugs fixed

- `AT+QPOWD` → `AT+CFUN=1,1` (was powering modem off, then waiting forever)
- Lua `luhn_digit` returned 10 instead of 0 (dead Lua path since removed)
- `random.sample` → `random.choices` (was a statistical fingerprint)
- `_rand16` uses `/proc/sys/kernel/random/uuid` (busybox has no `od`)
- One shared modem lock across CLI/toggle/LuCI (was three separate locks)
- `_resolve_modem_tty` probes AT on each candidate (was checking existence only)
- stage1 persists real IMEI/IMSI to tmpfs for stage2 (was always empty)
- All retry loops bounded; fail-closed: errors → safe poweroff, not continue
- `postrm` commits UCI; `prerm` stops services and unmounts tmpfs
- IMSI regex accepts 14–15 digits (ITU-T E.212)
- Serial reads loop until OK/ERROR (was single 64-byte read)
- `flock -E 99` → portable fd-based lock (no util-linux dependency)

### Anonymity features

- Apple OUI MAC pool (30 prefixes) — vendor lookup matches iPhone hostname
- iPhone hostname pool (25 models) — replaces `Mudi-<serial>`
- Personal-Hotspot SSID (`<Name>'s iPhone`, 244 names) — replaces `GL-E750-<serial>`
- TAC policy: module mode preserves baseline modem TAC; phone mode is
  user-supplied and fail-closed (no guessed GSMA data shipped)
- Ethernet MAC + hostname + per-uplink MAC rotation
- `blue-merle-newmac`/`newssid` CLIs (`--uplink`, `--full`, `--dry-run`, `--pure-random`)
- Hotplug BSSID on `ifdown`; upstream MAC on `ifup`; both respect `stable_identity`
- `stable_identity` UCI flag — freeze all identifiers across reboots
- tmpfs started and verified immediately at install (no flash-leak window)
- Fresh client-MAC database on each boot (no historical import)

### Tests

63 unit tests including 13 static privacy-invariant regressions.

```sh
python3 tests/run_all.py
```

## Threat-model tradeoff

Rotating hostname/BSSID/SSID at every boot defeats cross-location correlation.
A real iPhone keeps these stable — an observer seeing an "iPhone" that
changes name every reboot may flag it as anomalous.

Default is unlinkability. To freeze identity:

```sh
uci set blue-merle.main.stable_identity=1
uci commit blue-merle
```

## Limitations

- **DHCP fingerprinting** — Linux DHCP client, not iOS. Observer can
  distinguish "iPhone hostname on Linux stack".
- **TLS fingerprinting** — traffic carries the client's ClientHello, not
  Mudi's.
- **Traffic analysis** — volume/timing/destinations visible to ISP.
- **Physical seizure** — RAM (tmpfs) recoverable via cold-boot; flash via
  chip-off. Physical destruction is the only reliable countermeasure.
- **Flash history** — UCI commits may leave stale SSID/MAC/hostname in
  NAND erase blocks. Volatile UCI overlay not enabled (risks breaking
  GL.iNet netifd without hardware testing).

## Build from source

```sh
cd "$OPENWRT_SDK"
ln -s "$PWD/../blue-merle-fork" package/blue-merle
./scripts/feeds update -a && ./scripts/feeds install -a
echo "CONFIG_PACKAGE_blue-merle=m" > .config
echo "CONFIG_SIGNED_PACKAGES=n" >> .config
make defconfig
make -j$(nproc) package/blue-merle/compile V=s
```
