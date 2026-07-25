# blue-merle-fork

> ⚠️ **For educational and research purposes only.** Changing a device's
> IMEI may be illegal in your jurisdiction. The author does not encourage
> or endorse any use. You alone are responsible for your actions.

Fork of [srlabs/blue-merle](https://github.com/srlabs/blue-merle) for the
**GL-E750 Mudi** 4G travel router. Fixes upstream bugs, adds an
Apple-device masquerade, and hardens every IMEI/identity code path.

- **Target:** firmware `4.3.26`, MCU ≥ `1.0.7`
- **Package:** `blue-merle_3.0.5-local` (opkg name unchanged)
- **Usage:** [`USAGE.md`](./USAGE.md)
- **AI agents:** [`AGENTS.md`](./AGENTS.md)
- **License:** BSD-3-Clause

## Install

Download from [Releases](../../releases), verify the checksum, then:

```sh
scp -O blue-merle_3.0.5-local-*.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'opkg install --force-reinstall /tmp/blue-merle_*.ipk && reboot'
```

After reboot the WiFi name changes (e.g. `GL-E750-a19` → `Emma's iPhone`).
Reconnect with the **same password** — it never rotates.

## What changed vs. upstream

### Privacy

- No full IMEI/IMSI anywhere: masked in syslog, MCU, LuCI RPC and the
  generator's stderr (which is also dropped at non-interactive call
  sites); one canonical masked form per identifier class, fail-closed
- `/root/esim` + `/etc/oui-tertf` on tmpfs — IMEI and the client-MAC
  database live in RAM only, wiped on poweroff
- MAC generator always sets the U/L bit; `shred` → `rm` (theatrical on
  NAND, pointless on tmpfs)

### Correctness

- Modem control: `AT+CFUN=1,1` reset (was `AT+QPOWD` poweroff), serial
  reads loop until OK/ERROR, IMSI regex 14–15 digits (ITU-T E.212)
- Entropy: `random.choices` (no sampling fingerprint), `_rand16` from
  `/proc/sys/kernel/random/uuid` (busybox has no `od`)
- One shared flock across CLI/toggle/LuCI; modem TTY probed via AT
- Fail-closed everywhere: bounded retry loops, errors → safe poweroff;
  stage1 persists originals for stage2; tmpfs mounts stop gl_clients first
- CLI refuses non-interactive stdin — a closed stdin used to answer
  "yes" to every prompt and end in an unattended poweroff
- Install/uninstall lifecycle: `postrm` commits UCI, `prerm` stops
  services and unmounts tmpfs; dead Lua Luhn path removed

### Anonymity

- Apple OUI pool (30 prefixes) + paired identity: one picked name →
  SSID `<Name>'s iPhone`, hostname `<Name>s-iPhone` (244 names)
- TAC policy: module mode preserves the baseline modem TAC; phone mode
  is user-supplied, fail-closed (no guessed GSMA data shipped)
- Per-uplink MAC rotation on `ifdown`; hotplug BSSID rotation;
  `stable_identity` flag freezes all identifiers across reboots
- `blue-merle-newmac` / `blue-merle-newssid` CLIs

## Tests

97 unit tests (static privacy invariants + functional regressions):

```sh
python3 tests/run_all.py
```

## Threat-model tradeoff

Rotating hostname/BSSID/SSID every boot defeats cross-location
correlation; a real iPhone keeps them stable, so an observer may flag
an "iPhone" that changes its name every reboot as anomalous. Default
is unlinkability. To freeze identity:

```sh
uci set blue-merle.main.stable_identity=1 && uci commit blue-merle
```

## Limitations

- **DHCP fingerprinting** — Linux DHCP client, not iOS.
- **TLS fingerprinting** — traffic carries the client's ClientHello.
- **Traffic analysis** — volume/timing/destinations visible to ISP.
- **Physical seizure** — RAM recoverable via cold-boot, flash via
  chip-off; physical destruction is the only countermeasure.
- **Flash history** — UCI commits may leave stale values in NAND erase
  blocks (volatile UCI overlay not enabled).

## Build from source

No feeds update needed — the package is plain files:

```sh
cd "$OPENWRT_SDK"   # OpenWrt 23.05, ath79/nand
mkdir -p package/blue-merle
ln -s "$PWD/../blue-merle-fork"/{Makefile,files} package/blue-merle/
echo "CONFIG_SIGNED_PACKAGES=n" > .config
make defconfig
make -j"$(nproc)" package/blue-merle/compile V=s
# ipk: bin/packages/mips_24kc/base/
```
