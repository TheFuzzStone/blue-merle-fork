# blue-merle-fork — user guide

**Golden rule:** CLI is safest. Toggle is fastest without a laptop. LuCI
is simplest but has weaker IMSI-leak protection.

## Install

Download from [Releases](../../releases), then:

```sh
scp -O blue-merle_*.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'opkg update && opkg install --force-reinstall /tmp/blue-merle_*.ipk && reboot'
# opkg update is required: package lists live in RAM (lost every reboot),
# without it the python3-logging/urllib deps fail to resolve
# after reboot: new SSID (e.g. Emma's iPhone), same WiFi password
```

| Changes at reboot? | Identifier | When it changes |
|:---:|---|---|
| ✅ | Hostname, SSID, BSSID, client MAC, upstream MAC | every boot |
| ❌ | IMEI | only via CLI / toggle / LuCI |
| ❌ | IMSI / SIM | only via physical SIM swap |
| ❌ | WiFi password | never |

## Change the IMEI

| Method | Needs PC | IMSI-leak safe | IMEI type |
|---|:---:|:---:|---|
| CLI `blue-merle` | SSH | ✅ full | random or deterministic |
| Hardware toggle | no | ✅ full | random only |
| LuCI web UI | browser | ⚠️ partial | random only |

### CLI

```sh
ssh root@192.168.8.1
blue-merle    # → y → swap SIM → r → s (shutdown, change location)
# interactive only: aborts when stdin is not a terminal
```

### Toggle

1. Slide opposite → MCU: `Replace the SIM card.`
2. Swap SIM (don't touch slider).
3. Slide back → MCU: `IMEI changed. Powering off.`
4. Change location. Power on.

### LuCI

`http://192.168.8.1` → Blue Merle → `SIM swap…`. Shut down and swap
the SIM before powering back on.

## Rotate MAC / SSID (no reboot)

```sh
blue-merle-newmac --full          # all MACs + paired hostname/SSID identity
blue-merle-newmac --uplink        # only upstream MAC (AP clients stay)
blue-merle-newmac --pure-random   # RFC-7844 MAC instead of Apple OUI
blue-merle-newssid                # SSID + synced hostname
# --full with --uplink: upstream MAC + identity only (BSSIDs stay,
# but the SSID change still kicks AP clients)
```

## Configuration

```sh
uci set blue-merle.main.stable_identity=1 && uci commit blue-merle   # freeze identity
uci set blue-merle.main.tac_mode=phone && uci commit blue-merle     # or 'module'
```

`module` (default) preserves the baseline modem TAC captured at install
(no external database). `phone` uses your `tac-list-phone.txt` and fails
closed until you add TACs with documented GSMA provenance.

Pools — one entry per line, `#` = comment; `service blue-merle reload`
applies without reboot:

```sh
vi /lib/blue-merle/{apple-oui,us-first-names,tac-list,tac-list-phone}.txt
# OUI: lowercase aa:bb:cc. Names: ASCII letters only. TAC: 8 digits.
```

Env overrides: `BLUE_MERLE_TTY`, `BLUE_MERLE_FORCE=1`, `BM_READ_TRIES`,
`BLUE_MERLE_TAC`, `BLUE_MERLE_TAC_LIST`, `BLUE_MERLE_APPLE_OUI`,
`BLUE_MERLE_US_NAMES`.

**Disable features:**

```sh
service blue-merle disable
service blue-merle-esim-tmpfs disable
service volatile-client-macs disable
chmod -x /etc/hotplug.d/iface/0?-blue-merle-*   # both hotplug hooks
```

## Diagnostics

```sh
logread | grep blue-merle   # events only, never identifier values
sh /tmp/blue-merle-diag.sh  # redacted report
# harmless AT ERRORs to ignore: AT+QCFG="nwscanseq", AT+QSIMDET
```

## Uninstall

```sh
opkg remove blue-merle && reboot
```

Toggle reverts to `tor`. UCI values stay until reset:

```sh
for k in wireless.@wifi-iface[0].macaddr wireless.@wifi-iface[1].macaddr \
         wireless.@wifi-iface[0].ssid wireless.@wifi-iface[1].ssid \
         network.@device[1].macaddr glconfig.general.macclone_addr \
         system.@system[0].hostname; do uci -q delete "$k"; done
uci commit && reboot
```

## Cheat sheet (the less-obvious commands)

```sh
/usr/libexec/blue-merle read-identifiers  # masked IMEI+IMSI (JSON)
/usr/libexec/blue-merle prepare-sim-swap  # atomic RF-off + interim IMEI
/usr/libexec/blue-merle shutdown          # power off via MCU
python3 /lib/blue-merle/imei_generate.py --static <15-digit-IMEI>
mount | grep -E 'esim|oui-tertf'          # tmpfs mounts active?
```
