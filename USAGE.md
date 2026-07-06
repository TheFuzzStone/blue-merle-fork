# blue-merle-fork — user guide

> Русская версия: [`USAGE_RU.md`](./USAGE_RU.md).

Concise reference for the installed `blue-merle_3.0.5-local` package on
a GL-E750 Mudi. See [`README.md`](./README.md) for the change list vs.
upstream.

**Golden rule:** the CLI path is the safest. The physical toggle is
the fastest without a laptop. LuCI is the simplest but has the
weakest IMSI-leak protection — use only when the others aren't
available.

---

## Contents

1. [Install](#1-install)
2. [Change the IMEI](#2-change-the-imei)
3. [Rotate MAC / BSSID / hostname / SSID](#3-rotate-mac--bssid--hostname--ssid)
4. [Automatic behaviour at boot / hotplug](#4-automatic-behaviour-at-boot--hotplug)
5. [Configuration](#5-configuration)
6. [Diagnostics](#6-diagnostics)
7. [Uninstall / rollback](#7-uninstall--rollback)
8. [Recipes](#8-recipes)
9. [Command cheat sheet](#9-command-cheat-sheet)

---

## 1. Install

Download the ipk from the
[Releases](../../releases) page (see README.md for details), then:

```sh
# On your PC (Mudi reachable at 192.168.8.1 via its WiFi or LAN):
scp -O blue-merle_3.0.5-local-*.ipk root@192.168.8.1:/tmp/

# On the Mudi:
opkg install --force-reinstall /tmp/blue-merle_3.0.5-local-*.ipk
reboot                              # required — mounts tmpfs, first rotation
```

**What changes after reboot — and what doesn't:**

| Identifier | Changes at every reboot? | When does it change? |
|---|:---:|---|
| **Hostname** (e.g. `iPhone-15-Pro`) | ✅ yes | every boot |
| **SSID** (e.g. `Emma's iPhone`) | ✅ yes | every boot |
| **BSSID** (WiFi MAC) | ✅ yes | every boot |
| **Client MAC** (WiFi/Ethernet) | ✅ yes | every boot |
| **Upstream MAC** (repeater) | ✅ yes | every boot |
| **IMEI** | ❌ no | only via `blue-merle` / toggle / LuCI |
| **IMSI / SIM** | ❌ no | only via physical SIM swap |
| **WiFi password** | ❌ no | never — same password across all rotations |

Your laptop won't auto-connect after reboot — the SSID is fresh. Click
"Connect" on the new network name and enter the same WiFi password as
before.

---

## 2. Change the IMEI

Three interfaces, all safe but with different guarantees:

| Method | Needs PC | IMSI-leak safe? | IMEI type |
|---|:---:|:---:|---|
| CLI `blue-merle` | yes (SSH) | ✅ full (CFUN=4 before SIM swap) | random or deterministic |
| Hardware toggle | no | ✅ full (two stages) | random only |
| LuCI web UI | browser only | ⚠️ partial (no SIM-swap step) | random only |

### 2.1. CLI (recommended)

```sh
ssh root@192.168.8.1
blue-merle
```

Answer prompts:

1. `Swap SIM card and update IMEI? (Y/n):` → `y`
2. Modem is put into RF-off; you physically **swap the SIM** now.
3. Press any key to continue.
4. `Random (r) or deterministic (d) IMEI? (R/d):` → `r` (default);
   `d` derives the same IMEI from a given IMSI every time — useful only
   if you understand the linkability trade-off.
5. `Shutdown (s) or reset the modem (m)? (S/m):` → `s` (change location
   before powering back on for full unlinkability).

### 2.2. Hardware toggle

The physical slider on the Mudi has **two positions**; both are used.

1. Slide to the opposite position → MCU shows `Starting SIM swap.` →
   modem RF off → `Replace the SIM card. Then pull the switch.`
2. Replace the SIM. Do **not** touch the slider while doing this.
3. Slide back → modem restarts, writes final random IMEI, MCU shows
   `IMEI changed. Powering off.` → device shuts down after 5 s.
4. **Change location.** Power on again — everything else rotates
   automatically.

### 2.3. LuCI

Browser → `http://192.168.8.1/cgi-bin/luci` → `System` → `Advanced Settings`
→ `Network` → `Blue Merle` → `SIM swap…`. Confirms via modal, then
prompts you to swap the SIM manually and shut the device down.
**Limitation:** you must actually shut down and swap the SIM before
powering back on, otherwise the operator sees `new IMEI + old SIM` on
the same location. Prefer CLI or toggle when the risk matters.

---

## 3. Rotate MAC / BSSID / hostname / SSID

These are the on-air identifiers. The package rotates them
automatically at boot; below is how to force a rotation without a
reboot, or to change what happens.

```sh
# Full identity swap in one go (all MACs + hostname + SSID; kicks
# WiFi clients because BSSID changes)
blue-merle-newmac --full

# Only the upstream-facing MAC (repeater / WAN); AP clients stay
# online. Use before switching to a new hotspot.
blue-merle-newmac --uplink

# Only the SSID
blue-merle-newssid

# Preview without applying
blue-merle-newmac --dry-run
blue-merle-newssid --dry-run
```

Add `--pure-random` to `blue-merle-newmac` to use RFC-7844
locally-administered MACs instead of Apple OUIs (useful if a specific
upstream fingerprints "iPhone hostname on Linux DHCP stack").

---

## 4. Automatic behaviour at boot / hotplug

**At boot** (`/etc/init.d/blue-merle`, START=10):

1. New BSSIDs for both radios (Apple OUI).
2. New client-visible MACs (WiFi, Ethernet, upstream — all Apple OUI).
3. New hostname from `/lib/blue-merle/iphone-models.txt`.
4. New SSID `<Name>'s iPhone` from `/lib/blue-merle/us-first-names.txt`.
5. MCU shows `WiFi: <SSID>` so you know what to connect to.

Two support services also mount tmpfs so identifiers can't survive
across reboots: `blue-merle-esim-tmpfs` (`/root/esim`) and
`volatile-client-macs` (`/etc/oui-tertf`).

**On WiFi ifdown** (typically during `wifi reload`):
`/etc/hotplug.d/iface/30-blue-merle-bssid-on-ifdown` rewrites BSSIDs
so the immediately-following ifup uses fresh values.

**On upstream ifup** (`wwan` or `wan`):
`/etc/hotplug.d/iface/31-blue-merle-uplink-mac` stages a fresh
`macclone_addr` for the *next* connection to that upstream.

---

## 5. Configuration

Everything is UCI. Two useful knobs live in `/etc/config/blue-merle`:

```sh
# One truly stable identity across reboots (Apple-style — a real
# iPhone doesn't rotate its MAC/SSID every boot either). Manual
# rotation via `blue-merle-newmac --full` still works.
uci set blue-merle.main.stable_identity=1
uci commit blue-merle
service blue-merle reload
```

**Tune the Apple masquerade pools directly:**

```sh
vi /lib/blue-merle/iphone-models.txt      # hostnames (iPhone-15-Pro-Max, …)
vi /lib/blue-merle/apple-oui.txt          # OUI prefixes (3c:22:fb, …)
vi /lib/blue-merle/us-first-names.txt     # names for SSIDs (Emma, …)
vi /lib/blue-merle/tac-list.txt           # IMEI TACs (LTE-module range)
```

Rules: one entry per line, `#` = comment. **hostname** — only
`[A-Za-z0-9-]`, up to 63 chars (RFC 952). **OUI** — lowercase
`aa:bb:cc`. **Names** — ASCII letters only (the apostrophe in the
`<Name>'s iPhone` SSID template is added automatically). **TAC** —
exactly 8 decimal digits. Invalid entries are silently ignored.
`service blue-merle reload` applies without a reboot.

**TAC list and the two-layer masquerade:**

The Apple masquerade (hostname + SSID + MAC) operates on the
**WiFi/Ethernet layer** — it's what nearby scanners and upstream
networks see. The TAC list operates on the **cellular layer** —
it's what the mobile operator sees when the modem registers.

By default, `tac-list.txt` contains TACs from LTE **modules**
(Quectel, Sierra, Telit, u-blox — all in the `86xxxxxx` range),
not from consumer smartphones (`35xxxxxx`). This prevents the most
obvious operator-side flag: a TAC that says "Samsung Galaxy" while
the device behaves like a data-only LTE modem with a Linux stack.

If your threat model prefers "blend in with millions of phones"
over "look like a consistent industrial gateway", replace the file
with smartphone TACs — but be aware that operators with
capability-checking will flag the mismatch.

**Environment overrides** (for scripts / debug):

| Variable | Effect |
|---|---|
| `BLUE_MERLE_TTY` | Modem TTY path (default: dynamic discovery, then `/dev/ttyUSB3`) |
| `BLUE_MERLE_FORCE=1` | Skip preinst prompt during install |
| `BM_READ_TRIES` | Retry cap for IMEI/IMSI reads (default 5) |
| `BLUE_MERLE_APPLE_OUI` | Path to the Apple-OUI list (default `/lib/blue-merle/apple-oui.txt`) |
| `BLUE_MERLE_IPHONE_MODELS` | Path to the iPhone-model list |
| `BLUE_MERLE_US_NAMES` | Path to the US first-name list |
| `BLUE_MERLE_TAC_LIST` | Path to the TAC list for IMEI generation (default `/lib/blue-merle/tac-list.txt`) |

**Fall back to neutral (non-Apple) rotation:**

```sh
# Remove any of these files → the corresponding rotation falls back
# to a neutral value (locally-administered MAC / Mudi-<hex> hostname
# / stable SSID).
mv /lib/blue-merle/apple-oui.txt       /lib/blue-merle/apple-oui.txt.disabled
mv /lib/blue-merle/iphone-models.txt   /lib/blue-merle/iphone-models.txt.disabled
mv /lib/blue-merle/us-first-names.txt  /lib/blue-merle/us-first-names.txt.disabled
```

**Disable individual features:**

```sh
service blue-merle disable                 # no rotation at boot
service blue-merle-esim-tmpfs disable      # IMEI will persist on flash
service volatile-client-macs disable       # client-MAC db on flash
chmod -x /etc/hotplug.d/iface/30-blue-merle-bssid-on-ifdown   # no BSSID hotplug
chmod -x /etc/hotplug.d/iface/31-blue-merle-uplink-mac        # no uplink-MAC hotplug
```

---

## 6. Diagnostics

**Event log** (values are never logged — only actions):

```sh
logread | grep blue-merle
```

Expected messages: `Running Stage 1/2`, `IMEI change completed (values
omitted)`, `Refreshed BSSIDs (uci) after ifdown of wlanX — next ifup
will use them`, `Rotated upstream macclone_addr after ifup of wwan`.

**Full masked report** — use this before asking for help:

```sh
# From your PC:
scp -O dist/blue-merle-diag.sh root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'sh /tmp/blue-merle-diag.sh'
# Report lands at /tmp/blue-merle-diag.out on the Mudi.
scp -O root@192.168.8.1:/tmp/blue-merle-diag.out ./
less blue-merle-diag.out                # IDs are masked; safe to share
```

**Modem not responding:**

```sh
ls /dev/ttyUSB*
gl_modem AT AT
```

**Known AT-command ERRORs (not problems):**

Some AT commands return `ERROR` on the stock Quectel EP06 firmware
(`EP06ELAR03A08M4G`) — these are **not** bugs and do not affect
operation:

| Command | Response | Why |
|---|---|---|
| `AT+QCFG="nwscanseq"` | `ERROR` | Network scan sequence config not supported by this firmware; modem uses the default scan order. |
| `AT+QSIMDET` | `ERROR` | SIM hot-swap detection not implemented; SIM is detected at power-on instead. Does not affect swap — blue-merle reboots the modem via `CFUN=0`/`CFUN=4` after a physical SIM change. |

If you see `ERROR` from these commands during diagnostics, ignore it.

**Verify no IMEI leaks to syslog after a rotation** (should print nothing):

```sh
blue-merle
logread | grep -iE 'blue-merle.*[0-9]{14,15}'
```

**Unit tests** (dev machine, not on the Mudi):

```sh
python3 tests/run_all.py     # 44 passed, 0 failed
```

---

## 7. Uninstall / rollback

```sh
opkg remove blue-merle
reboot
```

- Toggle reverts to `tor` (postrm now commits UCI).
- Randomised UCI values (BSSID/MAC/SSID/hostname) **stay** in
  `/etc/config` until you reset them. Original MAC is on the sticker
  under the battery. Reset:

  ```sh
  for k in wireless.@wifi-iface[0].macaddr wireless.@wifi-iface[1].macaddr \
           wireless.@wifi-iface[0].ssid    wireless.@wifi-iface[1].ssid \
           network.@device[1].macaddr      glconfig.general.macclone_addr \
           system.@system[0].hostname; do
      uci -q delete "$k"
  done
  uci commit
  reboot
  ```

Nuclear option: `firstboot; reboot -f` (wipes `/overlay`).

---

## 8. Recipes

**Full identity swap before crossing a border:**

1. `ssh root@192.168.8.1` → `blue-merle` → swap SIM → `r` → `s`
   (shutdown).
2. Physically move at least a few hundred metres.
3. Power on again — BSSID / MAC / hostname / SSID all rotate
   automatically at boot.

**Quick IMEI change without a reboot:**

```sh
blue-merle    # → 'r' (random), 'm' (reset modem)
```

Modem returns in ~30–60 s. **Downside:** same location → operator
sees the IMEI change on the same spot.

**Automated daily IMEI rotation** (advanced, risky — changing IMEI
without changing SIM and location links the sessions):

```sh
cat > /etc/crontabs/root <<'EOF'
0 3 * * * /usr/libexec/blue-merle random-imei && /usr/libexec/blue-merle shutdown
EOF
service cron restart
```

**Restore the original IMEI:**

blue-merle doesn't save the original (it would be exactly the
forensic artefact this tool erases). The original is printed on the
sticker under the battery.

```sh
python3 /lib/blue-merle/imei_generate.py --static <original_15_digit_IMEI>
```

---

## 9. Command cheat sheet

```sh
# Identity rotation (no reboot)
blue-merle                                # interactive IMEI change (recommended)
blue-merle-newmac --full                  # rotate MAC + hostname + SSID
blue-merle-newmac --uplink                # only upstream MAC (AP clients stay)
blue-merle-newmac --pure-random           # RFC-7844 MAC instead of Apple OUI
blue-merle-newssid                        # only SSID
blue-merle-newssid --dry-run              # preview

# Read current values (LuCI uses these too)
/usr/libexec/blue-merle read-imei
/usr/libexec/blue-merle read-imsi
/usr/libexec/blue-merle random-imei       # generate + write
/usr/libexec/blue-merle shutdown-modem    # AT+CFUN=4
/usr/libexec/blue-merle shutdown          # clean power-off via MCU

# Python IMEI tool (advanced)
python3 /lib/blue-merle/imei_generate.py --random
python3 /lib/blue-merle/imei_generate.py --deterministic
python3 /lib/blue-merle/imei_generate.py --static <15-digit-IMEI>

# Service management
service blue-merle          {start,stop,restart,reload,enable,disable}
service blue-merle-esim-tmpfs {start,stop,enable,disable}
service volatile-client-macs  {start,stop,enable,disable}

# Config
uci set blue-merle.main.stable_identity=1 && uci commit blue-merle
vi /lib/blue-merle/{iphone-models,apple-oui,us-first-names}.txt

# Diagnostics
sh /tmp/blue-merle-diag.sh                # writes /tmp/blue-merle-diag.out
logread | grep blue-merle
mount | grep -E 'esim|oui-tertf'
uci show wireless | grep -E 'macaddr|ssid'
uci get system.@system[0].hostname

# Uninstall
opkg remove blue-merle
```
