#!/usr/bin/env ash

# This script provides helper functions for blue-merle


# Discover the modem's AT-command TTY device and print its path.
#
# The Quectel EP06 in the GL-E750 normally enumerates /dev/ttyUSB{0..3}
# with the AT interface on /dev/ttyUSB3, but firmware updates or USB
# re-enumeration can shift the layout. The old code hard-coded ttyUSB3
# in stage1/stage2/libexec, so a shifted enumeration made toggle-driven
# and LuCI-driven SIM-swap fail silently while the CLI (which already
# discovered the port dynamically) worked. This helper centralises the
# logic so every caller resolves the same way.
#
# Precedence:
#   1. \$BLUE_MERLE_TTY if it's set and points to an existing char device.
#   2. Any of ttyUSB3 / ttyUSB2 / ttyUSB1 / ttyUSB0 that exists.
#   3. As a last resort, print /dev/ttyUSB3 anyway so the caller can
#      still error out with a familiar message.
#
# Callers typically invoke it as:
#     BLUE_MERLE_TTY=$(_resolve_modem_tty)
#     export BLUE_MERLE_TTY
# before running imei_generate.py, so the Python side inherits the
# resolved path.
_resolve_modem_tty () {
    if [ -n "${BLUE_MERLE_TTY:-}" ] && [ -c "$BLUE_MERLE_TTY" ]; then
        printf '%s\n' "$BLUE_MERLE_TTY"
        return 0
    fi
    for cand in /dev/ttyUSB3 /dev/ttyUSB2 /dev/ttyUSB1 /dev/ttyUSB0; do
        if [ -c "$cand" ]; then
            printf '%s\n' "$cand"
            return 0
        fi
    done
    printf '/dev/ttyUSB3\n'
    return 1
}


# Generate a valid, locally-administered, unicast MAC address.
#
# Bit layout of the first octet:
#   bit 0 (I/G, LSB) = 0  -> unicast
#   bit 1 (U/L)      = 1  -> locally-administered (not tied to a vendor OUI)
# All other bits random. Setting U/L=1 is what RFC 7844 recommends for
# MAC randomization; without it we would forge a vendor MAC and trip
# WIDS "spoofing detected" heuristics.
#
# This helper is kept for callers that explicitly want a randomized-
# looking MAC (e.g. `blue-merle-newmac --pure-random`). The default
# rotation now uses APPLE_MAC_GEN to match the iPhone/iPad hostname.
UNICAST_MAC_GEN () {
    python3 - <<'PY'
import os
b = bytearray(os.urandom(6))
b[0] = (b[0] & 0xFC) | 0x02  # clear I/G and old U/L, then set U/L=1
print(":".join(f"{x:02x}" for x in b))
PY
}

# Generate a MAC using a real Apple OUI prefix + 3 random octets.
#
# Rationale: the hostname we advertise via DHCP is an "iPhone-*" or
# "iPad-*" model name. If the MAC's OUI does not match a real Apple
# range, upstream fingerprinting immediately sees the mismatch and the
# masquerade is defeated (or worse, flagged as a spoof). Presenting an
# Apple OUI keeps the story consistent.
#
# The OUI list lives in /lib/blue-merle/apple-oui.txt so the user can
# edit it without repackaging.
APPLE_MAC_GEN () {
    local oui_file=${BLUE_MERLE_APPLE_OUI:-/lib/blue-merle/apple-oui.txt}
    if [ ! -r "$oui_file" ]; then
        # No OUI list available — fall back to RFC 7844 style random MAC.
        UNICAST_MAC_GEN
        return
    fi
    APPLE_OUI_FILE="$oui_file" python3 - <<'PY'
import os, random, re, sys

path = os.environ["APPLE_OUI_FILE"]
ouis = []
with open(path) as f:
    for raw in f:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        # Accept the "aa:bb:cc" form; reject anything else so a
        # typo cannot produce an invalid MAC.
        if re.fullmatch(r"[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){2}", line):
            ouis.append(line.lower())

if not ouis:
    # No usable OUI in the file; emit a locally-administered MAC as
    # a safe fallback.
    b = bytearray(os.urandom(6))
    b[0] = (b[0] & 0xFC) | 0x02
    print(":".join(f"{x:02x}" for x in b))
    sys.exit(0)

oui = random.choice(ouis)
tail = os.urandom(3)
print(oui + ":" + ":".join(f"{x:02x}" for x in tail))
PY
}

# Randomize both AP BSSIDs (2.4 GHz + 5 GHz) using Apple OUIs.
RESET_BSSIDS () {
    uci set wireless.@wifi-iface[0].macaddr="$(APPLE_MAC_GEN)"
    uci -q set wireless.@wifi-iface[1].macaddr="$(APPLE_MAC_GEN)" 2>/dev/null || true
    uci commit wireless
    # you need to reset wifi for changes to apply, i.e. executing "wifi"
}

# Randomize the wired-side / repeater / bridge MAC addresses using Apple OUIs.
#
# Historically this only touched network.@device[1] and
# glconfig.general.macclone_addr, but left the Ethernet br-lan MAC and the
# base hostname alone — both of which are strong fingerprints for a
# travel-router that connects to different upstream networks over cable.
RANDOMIZE_MACADDR () {
    # WiFi-facing device (clients on the AP see this MAC).
    uci set network.@device[1].macaddr="$(APPLE_MAC_GEN)"

    # MAC used when acting as an upstream-WiFi client (repeater mode).
    uci set glconfig.general.macclone_addr="$(APPLE_MAC_GEN)"

    # Ethernet bridge (br-lan). Present in most Mudi firmwares; ignore
    # errors if the section name differs on other versions.
    uci -q set network.@device[0].macaddr="$(APPLE_MAC_GEN)" 2>/dev/null || true

    uci commit network
    uci commit glconfig
    # You need to restart the network, i.e. /etc/init.d/network restart
}

# Return a random 16-bit unsigned integer (0..65535) as a decimal string.
#
# Historically this was `od -An -N2 -tu2 /dev/urandom | tr -d ' '`, but
# busybox on stock Mudi firmware does NOT ship `od`, so the pipeline
# failed silently, $rnd came out empty, and every $(( "" % N + 1 ))
# evaluated to 1 -> _pick_random_line always returned the first entry
# ("Aaron", "iPhone-X"). This was the real cause of "same SSID after
# every reboot".
#
# /proc/sys/kernel/random/uuid is provided by the kernel random driver,
# needs no external tools, and returns a fresh 128-bit random UUID on
# each read. We slice 4 hex chars (16 bits) out of the leading segment
# using pure shell parameter expansion + printf, so this works with any
# combination of installed utilities.
_rand16 () {
    local uuid hex n
    if [ -r /proc/sys/kernel/random/uuid ]; then
        read -r uuid < /proc/sys/kernel/random/uuid || uuid=""
        hex=${uuid%%-*}
        hex=$(printf '%.4s' "$hex")
        # printf '%d' interprets 0x... as hex; wrap in a subshell so a
        # malformed input can't kill the caller.
        n=$(printf '%d' "0x${hex}" 2>/dev/null) || n=""
    fi
    # Last-resort fallback: derive something at least reboot-varying
    # from uptime nanoseconds. This is not cryptographic, but is far
    # better than returning "" (which selects index 1 forever).
    if [ -z "$n" ] || [ "$n" -lt 0 ] 2>/dev/null; then
        if [ -r /proc/uptime ]; then
            n=$(awk 'NR==1{printf "%d", ($1*1000000)%65536}' /proc/uptime 2>/dev/null)
        fi
    fi
    [ -n "$n" ] || n=$(( $$ * 31 % 65536 ))
    printf '%s\n' "$n"
}

# Pick a random non-comment, non-empty line from a file.
# Prints the picked line on stdout; prints nothing and returns 1 if the
# file is missing/unreadable/empty. Callers must supply their own
# fallback when this returns non-zero.
_pick_random_line () {
    local file=$1
    [ -r "$file" ] || return 1
    local total
    total=$(grep -cvE '^\s*(#|$)' "$file" 2>/dev/null || echo 0)
    [ "$total" -gt 0 ] || return 1
    local rnd
    rnd=$(_rand16)
    # Additional guard: a broken _rand16 must never make $idx == 1
    # deterministically. If rnd is empty or non-numeric, bail with a
    # random-ish salt from $$ so callers see variation.
    case "$rnd" in
        ''|*[!0-9]*) rnd=$(( $$ + total )) ;;
    esac
    local idx=$(( rnd % total + 1 ))
    grep -vE '^\s*(#|$)' "$file" | sed -n "${idx}p"
}

# Randomize the hostname so DHCP requests / mDNS don't advertise the
# stable "Mudi-<serial suffix>" identifier across sessions.
#
# Picks a random model from /lib/blue-merle/iphone-models.txt. Combined
# with APPLE_MAC_GEN'd MACs, upstream DHCP/mDNS sees a consistent
# "iPhone" story (matching hostname + Apple OUI + Personal-Hotspot SSID).
RANDOMIZE_HOSTNAME () {
    local iphone_file=${BLUE_MERLE_IPHONE_MODELS:-/lib/blue-merle/iphone-models.txt}
    local model
    model=$(_pick_random_line "$iphone_file")

    # Guard against missing list, pathological entries, or invalid chars.
    # A hostname must match RFC 952/1123: letters/digits/hyphen, 1..63 chars.
    case "$model" in
        ''|*[!A-Za-z0-9-]*)
            local suffix
            suffix=$(printf '%04x' "$(_rand16)")
            model="Mudi-${suffix}"
            ;;
    esac

    uci set system.@system[0].hostname="$model"
    uci commit system
    # /etc/init.d/system reload picks it up.
}

# Randomize the AP SSID to look like an iPhone Personal Hotspot.
#
# Picks a random first name from /lib/blue-merle/us-first-names.txt and
# composes "<Name>'s iPhone" — the exact broadcast format iOS uses.
# Applies to both wifi-iface[0] (2.4 GHz) and wifi-iface[1] (5 GHz) so
# a single-radio dual-band configuration keeps the same SSID on both
# bands (standard iPhone hotspot behaviour). Guest network
# (wifi-iface[2]), if any, is left alone.
#
# The Wi-Fi password is deliberately not touched: rotating both SSID
# and password on every reboot would force the user to re-enter the
# key on every client, every time.
RANDOMIZE_SSID () {
    local names_file=${BLUE_MERLE_US_NAMES:-/lib/blue-merle/us-first-names.txt}
    local name
    name=$(_pick_random_line "$names_file")

    # Guard: allow ASCII letters only. Anything unexpected -> silently
    # bail out so we don't smash the existing SSID with garbage.
    case "$name" in
        ''|*[!A-Za-z]*)
            return 0
            ;;
    esac

    local ssid="${name}'s iPhone"

    # Apply to both bands. `uci -q ... || true` protects the case where
    # wifi-iface[1] is disabled or missing (e.g. user runs 5 GHz only).
    uci set wireless.@wifi-iface[0].ssid="$ssid"
    uci -q set wireless.@wifi-iface[1].ssid="$ssid" 2>/dev/null || true
    uci commit wireless
}

READ_ICCID() {
    gl_modem AT AT+CCID
}


# Read the modem's current IMEI. Bounded retry: at most $BM_READ_TRIES
# attempts, each separated by 1s. In non-interactive contexts (toggle
# stages, LuCI) we cannot prompt the user, so we simply give up and return
# an empty string rather than hang on `read`.
READ_IMEI () {
	local tries=0
	local max=${BM_READ_TRIES:-5}
	local imei=""
	while [ "$tries" -lt "$max" ]; do
		# grep may match multiple candidates in a chatty AT response;
		# take only the first for safety.
		imei=$(gl_modem AT AT+GSN | grep -w -E "[0-9]{14,15}" | head -n1)
		if [ -n "$imei" ]; then
			printf '%s' "$imei"
			return 0
		fi
		tries=$((tries+1))
		sleep 1
	done
	return 1
}

READ_IMSI () {
	local tries=0
	local max=${BM_READ_TRIES:-5}
	local imsi=""
	while [ "$tries" -lt "$max" ]; do
		imsi=$(gl_modem AT AT+CIMI | grep -w -E "[0-9]{6,15}" | head -n1)
		if [ -n "$imsi" ]; then
			printf '%s' "$imsi"
			return 0
		fi
		tries=$((tries+1))
		sleep 1
	done
	return 1
}


# The abort switch works only when we were actually invoked from the
# physical toggle (sim.sh sets /tmp/blue-merle/toggle-driven). Otherwise
# /tmp/sim_change_switch defaults to "off" and would abort every manual
# stage1 invocation on the very first modem retry.
CHECK_ABORT () {
        local sim_change_switch
        sim_change_switch=$(cat /tmp/sim_change_switch 2>/dev/null)
        if [ "$sim_change_switch" = "off" ] && [ -f /tmp/blue-merle/toggle-driven ]; then
                if [ -c /dev/ttyS0 ]; then
                        echo '{ "msg": "SIM change      aborted." }' > /dev/ttyS0
                fi
                sleep 1
                exit 1
        fi
}
