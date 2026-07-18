#!/bin/sh
# blue-merle diagnostic — run on Mudi via SSH.
#
# Canonical source: tools/blue-merle-diag.sh in the blue-merle-fork
# repository. Copy to the device with:
#   scp -O tools/blue-merle-diag.sh root@192.168.8.1:/tmp/
#
# All identifiers (IMEI/IMSI/serial/MAC) are masked before output so the
# result is safe to paste into a chat / issue without leaking.
#
# The script writes the full report to /tmp/blue-merle-diag.out on the
# Mudi (nothing is streamed to your terminal), so it survives long
# outputs that would otherwise scroll past your terminal buffer.
#
# ----------------------------------------------------------------------
# Usage on Mudi:
#   sh /tmp/blue-merle-diag.sh
#   cat /tmp/blue-merle-diag.out          # view or pipe to `less`
#
# Pull the file to your PC (recommended — read it in your editor):
#   scp -O root@192.168.8.1:/tmp/blue-merle-diag.out ./
#
# Or copy paste the last N lines section-by-section:
#   sed -n '/== 1\./,/== 2\./p' /tmp/blue-merle-diag.out
#   sed -n '/== 5\./,/== 6\./p' /tmp/blue-merle-diag.out
# ----------------------------------------------------------------------

set -u

# All output goes to this file (never to stdout) so long reports don't
# scroll off small terminal buffers like Konsole's default.
OUT=/tmp/blue-merle-diag.out
: > "$OUT"           # truncate any previous run
exec >> "$OUT" 2>&1  # redirect all subsequent stdout+stderr to the file

# ---- helpers (must be defined before the first section header
#      so the report banner itself can mask sensitive fields) ----

mask_id() {
    # Show first 4 and last 4 chars, mask middle. Works for IMEI/IMSI.
    v=$1
    n=${#v}
    if [ "$n" -le 8 ]; then
        printf '****\n'
    else
        head=$(printf '%s' "$v" | cut -c1-4)
        tail=$(printf '%s' "$v" | cut -c$((n-3))-)
        printf '%s******%s\n' "$head" "$tail"
    fi
}

mask_mac() {
    # Keep only OUI (first 3 octets), mask rest.
    v=$1
    case "$v" in
        [0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:*)
            oui=$(printf '%s' "$v" | cut -c1-8)
            printf '%s:xx:xx:xx\n' "$oui"
            ;;
        *)
            printf '%s\n' "$v"
            ;;
    esac
}

mask_name() {
    # Mask for hostnames, SSIDs and name-pool samples.
    #
    # Design goal: keep enough of the value for pattern debugging
    # (iPho…, iPad…, Emma…) but never leak the specific identifier.
    # In particular, short entries (≤ 4 chars, common for first
    # names like "Amy" or "Anna") MUST NOT pass through unchanged
    # — 52 of the 244 pool names are that short, and letting them
    # through in diag section 7 would leak ~21 % of picks.
    #
    # Rule: show at most min(2, n/2) leading chars, then '***'.
    #   n=3   → '***'
    #   n=4   → 'A***'   (still gives pattern, hides identity)
    #   n=5+  → 'Am***'
    #   n=10+ → 'Amel***'
    v=$1
    n=${#v}
    if [ "$n" -le 3 ]; then
        printf '***\n'
    elif [ "$n" -le 4 ]; then
        head=$(printf '%s' "$v" | cut -c1-1)
        printf '%s***\n' "$head"
    elif [ "$n" -le 8 ]; then
        head=$(printf '%s' "$v" | cut -c1-2)
        printf '%s***\n' "$head"
    else
        head=$(printf '%s' "$v" | cut -c1-4)
        printf '%s***\n' "$head"
    fi
}

# ---- Report banner (uses mask_name so the system hostname, which
#      is a rotated iPhone-* identifier, doesn't leak) ----

echo "blue-merle diagnostic report"
echo "Generated: $(date 2>/dev/null || echo unknown)"
echo "Host:      $(mask_name "$(hostname 2>/dev/null || echo unknown)")"

section() {
    printf '\n=========================================================\n'
    printf '== %s\n' "$1"
    printf '=========================================================\n'
}

# ---------------------------------------------------------------
section "1. blue-merle package version"
# ---------------------------------------------------------------
opkg list-installed 2>/dev/null | grep -i blue-merle || echo "NOT INSTALLED"

# ---------------------------------------------------------------
section "2. Firmware & hardware"
# ---------------------------------------------------------------
echo "Model:    $(cat /tmp/sysinfo/model 2>/dev/null || echo unknown)"
echo "GLver:    $(cat /etc/glversion 2>/dev/null || echo unknown)"
echo "MCUver:   $(cat /etc/mcuversion 2>/dev/null || echo unknown)"
echo "Uptime:   $(cat /proc/uptime 2>/dev/null | awk '{printf "%.1fs\n", $1}')"
echo "Uname:    $(uname -srmo 2>/dev/null)"
echo "CPU:      $(grep -m1 'system type' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ //')"

# ---------------------------------------------------------------
section "3. Current identity (MASKED)"
# ---------------------------------------------------------------
# hostname and SSID are on-the-air identifiers just like MACs, so we
# mask them too. The first 4 characters are preserved so patterns
# (iPho…, Emma…) can still be verified against expectations without
# revealing the specific value.
hn=$(uci -q get system.@system[0].hostname 2>/dev/null || echo "")
[ -n "$hn" ] && echo "hostname:   $(mask_name "$hn")"

for i in 0 1 2; do
    s=$(uci -q get wireless.@wifi-iface[$i].ssid 2>/dev/null || true)
    d=$(uci -q get wireless.@wifi-iface[$i].disabled 2>/dev/null || true)
    if [ -n "$s" ]; then
        printf 'SSID[%d]:    %-30s (disabled=%s)\n' "$i" "$(mask_name "$s")" "${d:-0}"
    fi
done

echo ""
echo "MAC addresses (OUI shown, tail masked):"
for i in 0 1 2; do
    m=$(uci -q get wireless.@wifi-iface[$i].macaddr 2>/dev/null || true)
    [ -n "$m" ] && echo "  BSSID[$i]:    $(mask_mac "$m")"
done
for i in 0 1; do
    m=$(uci -q get network.@device[$i].macaddr 2>/dev/null || true)
    [ -n "$m" ] && echo "  net dev[$i]: $(mask_mac "$m")"
done
up=$(uci -q get glconfig.general.macclone_addr 2>/dev/null || true)
[ -n "$up" ] && echo "  upstream:    $(mask_mac "$up")"

# ---------------------------------------------------------------
section "4. Service state"
# ---------------------------------------------------------------
for s in blue-merle blue-merle-esim-tmpfs volatile-client-macs; do
    printf '  %-24s ' "$s"
    if [ -x /etc/init.d/"$s" ]; then
        if /etc/init.d/"$s" enabled 2>/dev/null; then
            echo "enabled"
        else
            echo "DISABLED"
        fi
    else
        echo "NOT INSTALLED"
    fi
done

echo ""
echo "tmpfs mounts:"
mount | grep -E 'esim|oui-tertf' | sed 's/^/  /' || echo "  (none)"

# ---------------------------------------------------------------
section "5. Entropy state (critical for randomness)"
# ---------------------------------------------------------------
echo "entropy_avail:  $(cat /proc/sys/kernel/random/entropy_avail 2>/dev/null || echo n/a)"
echo "poolsize:       $(cat /proc/sys/kernel/random/poolsize 2>/dev/null || echo n/a)"
echo "hwrng present:  $([ -e /dev/hwrng ] && echo yes || echo no)"
[ -r /sys/class/misc/hw_random/rng_current ] && \
    echo "rng_current:    $(cat /sys/class/misc/hw_random/rng_current)"
[ -r /sys/class/misc/hw_random/rng_available ] && \
    echo "rng_available:  $(cat /sys/class/misc/hw_random/rng_available)"

echo ""
echo "NOTE: on MIPS routers without a hardware RNG, entropy_avail < 200"
echo "in the first seconds after boot means /dev/urandom may return"
echo "a deterministic sequence, causing the same hostname/SSID pick"
echo "across reboots. This is the leading hypothesis for 'Aaron/Aaron'."

# ---------------------------------------------------------------
section "6. Random-source sanity"
# ---------------------------------------------------------------

# Whether `od` is available at all — historical picker used it.
echo "Utility availability:"
for u in od hexdump awk sed grep printf head; do
    if command -v "$u" >/dev/null 2>&1; then
        echo "  $u: $(command -v "$u")"
    else
        echo "  $u: NOT FOUND"
    fi
done

echo ""
echo "Direct 16-bit reads from /proc/sys/kernel/random/uuid (10x, must differ):"
i=0
while [ $i -lt 10 ]; do
    if [ -r /proc/sys/kernel/random/uuid ]; then
        u=$(head -1 /proc/sys/kernel/random/uuid)
        hex=${u%%-*}
        hex=$(printf '%.4s' "$hex")
        n=$(printf '%d' "0x${hex}" 2>/dev/null || echo "<ERR>")
        printf '  sample %2d: uuid=%s.. hex=%s decimal=%s\n' "$i" "${u%%-*}" "$hex" "$n"
    else
        echo "  /proc/sys/kernel/random/uuid NOT READABLE"
        break
    fi
    i=$((i+1))
done

echo ""
echo "_rand16 output (via installed functions.sh, 10x):"
if [ -r /lib/blue-merle/functions.sh ]; then
    . /lib/blue-merle/functions.sh
    i=0
    while [ $i -lt 10 ]; do
        printf '  sample %2d: %s\n' "$i" "$(_rand16)"
        i=$((i+1))
    done
fi

echo ""
echo "If _rand16 samples are all the same or empty, _pick_random_line will"
echo "always return index 1 ('Aaron'). The historic bug was that busybox"
echo "on Mudi lacks 'od' — that's why the earlier version returned empty."

# ---------------------------------------------------------------
section "7. _pick_random_line distribution (30 picks, MASKED)"
# ---------------------------------------------------------------
# Names from us-first-names.txt are on-air identifiers (they compose
# the SSID). Printing 30 raw picks would (a) potentially include the
# current live SSID name (~12 % probability at pool size 244) and
# (b) leak the PRNG state right now — enough to predict future picks.
# Mask each name via mask_name() so the diagnostic still shows that
# the picker draws diverse values without revealing which values.
if [ -r /lib/blue-merle/functions.sh ] && [ -r /lib/blue-merle/us-first-names.txt ]; then
    . /lib/blue-merle/functions.sh
    tmp=$(mktemp)
    i=0
    while [ $i -lt 30 ]; do
        _pick_random_line /lib/blue-merle/us-first-names.txt >> "$tmp"
        i=$((i+1))
    done
    echo "Distribution (count, masked-name):"
    # Mask each raw name before aggregation so uniqueness statistics
    # still reflect the underlying entropy (two names sharing a
    # 4-char prefix would collide after masking, but that's rare).
    masked_tmp=$(mktemp)
    while IFS= read -r rawname; do
        mask_name "$rawname" >> "$masked_tmp"
    done < "$tmp"
    sort "$masked_tmp" | uniq -c | sort -rn | sed 's/^/  /'
    echo ""
    echo "Unique names in 30 picks: $(sort -u "$tmp" | wc -l)  (healthy: ≥ 20)"
    echo "Total lines picked:       $(wc -l < "$tmp")"
    rm -f "$tmp" "$masked_tmp"
else
    echo "SKIPPED — functions.sh or names file missing"
fi

# ---------------------------------------------------------------
section "8. SSID/identity candidates (dry preview, MASKED)"
# ---------------------------------------------------------------
# Same leak risk as section 7. Show masked names so the SSID pattern
# is visible for debugging without exposing which concrete values the
# picker would use right now.
if [ -r /lib/blue-merle/functions.sh ] && [ -r /lib/blue-merle/us-first-names.txt ]; then
    . /lib/blue-merle/functions.sh
    echo "5 candidate SSIDs the picker would generate right now:"
    j=1
    while [ $j -le 5 ]; do
        n=$(_pick_random_line /lib/blue-merle/us-first-names.txt)
        echo "  $(mask_name "$n")'s iPhone"
        j=$((j+1))
    done
fi

# ---------------------------------------------------------------
section "9. blue-merle log summary"
# ---------------------------------------------------------------
count=$(logread 2>/dev/null | grep -ic blue-merle || true)
printf '  blue-merle-related entries in current ring buffer: %s\n' "$count"

# ---------------------------------------------------------------
section "10. Init script setup"
# ---------------------------------------------------------------
echo "/etc/rc.d/ entries for blue-merle:"
# shellcheck disable=SC2010 # ls|grep is fine in a read-only diagnostic
ls -la /etc/rc.d/ 2>/dev/null | grep -i blue-merle | sed 's/^/  /' || echo "  (none)"

echo ""
echo "START priorities in /etc/init.d/*:"
for s in blue-merle blue-merle-esim-tmpfs volatile-client-macs; do
    if [ -r /etc/init.d/"$s" ]; then
        start=$(grep -E '^START=' /etc/init.d/"$s" | head -1)
        printf '  %-24s %s\n' "$s" "$start"
    fi
done

# ---------------------------------------------------------------
section "11. Package data files present?"
# ---------------------------------------------------------------
for f in \
    /lib/blue-merle/functions.sh \
    /lib/blue-merle/apple-oui.txt \
    /lib/blue-merle/us-first-names.txt \
    /lib/blue-merle/imei_generate.py \
    /usr/bin/blue-merle \
    /usr/bin/blue-merle-newmac \
    /usr/bin/blue-merle-newssid \
    /usr/bin/blue-merle-switch-stage1 \
    /usr/bin/blue-merle-switch-stage2 \
    /usr/libexec/blue-merle \
    /etc/init.d/blue-merle \
    /etc/init.d/blue-merle-esim-tmpfs \
    /etc/init.d/volatile-client-macs \
    /etc/hotplug.d/iface/30-blue-merle-bssid-on-ifdown \
    /etc/hotplug.d/iface/31-blue-merle-uplink-mac
do
    if [ -e "$f" ]; then
        printf '  OK       %s  (%d bytes)\n' "$f" "$(wc -c < "$f" 2>/dev/null)"
    else
        printf '  MISSING  %s\n' "$f"
    fi
done

# ---------------------------------------------------------------
section "12. Names / OUI list sanity"
# ---------------------------------------------------------------
for f in \
    /lib/blue-merle/us-first-names.txt \
    /lib/blue-merle/apple-oui.txt
do
    if [ -r "$f" ]; then
        total=$(grep -cvE '^[[:space:]]*(#|$)' "$f")
        unique=$(grep -vE '^[[:space:]]*(#|$)' "$f" | sort -u | wc -l)
        first=$(grep -vE '^[[:space:]]*(#|$)' "$f" | head -1)
        printf '  %s\n    total=%d unique=%d first=%s\n' "$f" "$total" "$unique" "$first"
    fi
done

# ---------------------------------------------------------------
section "13. Modem TTY availability (no AT commands issued)"
# ---------------------------------------------------------------
ls -la /dev/ttyUSB* 2>/dev/null | sed 's/^/  /' || echo "  (no ttyUSB)"
echo ""
echo "IMEI/IMSI read is intentionally SKIPPED — they would leak into"
echo "this diagnostic output. Ask blue-merle CLI or /usr/libexec masks."

# ---------------------------------------------------------------
section "14. Wireless interface summary (redacted)"
# ---------------------------------------------------------------
if command -v iw >/dev/null 2>&1; then
    iw dev 2>/dev/null | awk '/Interface/{count++} END{printf "  interfaces: %d\n", count+0}'
else
    echo "  iw missing"
fi

# ---------------------------------------------------------------
section "15. Reboot-count heuristic"
# ---------------------------------------------------------------
# Some Mudi firmwares maintain a boot counter; useful to correlate with
# repeated 'Aaron' selection.
[ -r /etc/glversion ] && echo "glversion mtime:  $(stat -c '%y' /etc/glversion 2>/dev/null || echo n/a)"
[ -r /etc/mcuversion ] && echo "mcuversion mtime: $(stat -c '%y' /etc/mcuversion 2>/dev/null || echo n/a)"
echo "wtmp last boots (if wtmp exists):"
last reboot 2>/dev/null | head -5 | sed 's/^/  /' || echo "  (no wtmp)"

echo ""
echo "========================================================="
echo "== END OF DIAGNOSTIC — paste this whole output back."
echo "== Masked: IMEI/IMSI (not read at all), MAC tails, hostname,"
echo "==         SSID, name-pool samples in sections 7-8."
echo "== Not masked: package versions, mount table, log excerpts,"
echo "==             utility availability, entropy pool state."
echo "== Review before pasting into a public issue."
echo "========================================================="

# Restore stdout and tell the user where the file is (this is the
# only thing they see in the terminal — the actual report lives in
# $OUT so long outputs don't scroll away).
exec 1>&- 2>&-       # close the redirected FDs so they flush
{
    echo ""
    echo "Diagnostic complete."
    echo "Report:  $OUT   ($(wc -l < "$OUT" 2>/dev/null || echo ?) lines,"
    echo "                  $(wc -c < "$OUT" 2>/dev/null || echo ?) bytes)"
    echo ""
    echo "View:      less  $OUT"
    echo "Head:      head -60 $OUT"
    echo "Copy to PC:"
    echo "  scp -O root@192.168.8.1:$OUT ./"
    echo ""
} > /dev/tty 2>/dev/null
