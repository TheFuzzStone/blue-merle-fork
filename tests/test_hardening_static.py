"""Static regression checks for privacy-critical shell state machines."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage2_fails_closed_on_cfun_errors():
    src = _read("files/usr/bin/blue-merle-switch-stage2")
    assert 'CFUN=0 failed. Powering off.' in src
    assert 'CFUN=4 failed. Powering off.' in src
    assert '_safe_poweroff' in src
    assert '# Continue anyway' not in src


def test_stage2_requires_valid_readback_before_success():
    src = _read("files/usr/bin/blue-merle-switch-stage2")
    assert '_is_valid_imei_shape "$new_imei"' in src
    assert '_write_runtime_imei "$new_imei"' in src
    assert src.index('_write_runtime_imei "$new_imei"') < src.index('IMEI changed.')


def test_all_modem_entry_points_use_shared_lock():
    for path in (
        "files/usr/bin/blue-merle",
        "files/usr/bin/blue-merle-switch-stage1",
        "files/usr/bin/blue-merle-switch-stage2",
        "files/usr/libexec/blue-merle",
    ):
        src = _read(path)
        assert "_acquire_modem_lock" in src, path


def test_libexec_resolves_tty_only_after_operation_lock():
    src = _read("files/usr/libexec/blue-merle")
    block = src.split("prepare-sim-swap)", 1)[1].split(";;", 1)[0]
    assert block.index("_acquire_modem_lock") < block.index("_resolve_tty_for_operation")


def test_hotplug_respects_stable_identity():
    for path in (
        "files/etc/hotplug.d/iface/30-blue-merle-bssid-on-ifdown",
        "files/etc/hotplug.d/iface/31-blue-merle-uplink-mac",
    ):
        src = _read(path)
        assert "stable_identity" in src, path


def test_uplink_mac_rotates_on_ifdown_synchronously():
    src = _read("files/etc/hotplug.d/iface/31-blue-merle-uplink-mac")
    # Rotation at ifup only staged the MAC for the *next* association
    # and raced it from a backgrounded subshell — a lock-contended or
    # beaten commit left the next uplink with the previous MAC.
    # ifdown staging (same pattern as the BSSID hook) closes the race.
    assert '[ "$ACTION" = "ifdown" ]' in src
    assert '[ "$ACTION" = "ifup" ]' not in src
    # The rotation must not be fire-and-forget backgrounded.
    assert ') 9>"$LOCK" &' not in src


def test_luci_rpc_returns_masked_identifiers():
    src = _read("files/usr/libexec/blue-merle")
    assert "printf '%s' \"$masked\"" in src
    assert "read-identifiers)" in src
    assert "prepare-sim-swap" in src
    assert "shutdown-modem)" not in src
    assert "random-imei)" not in src


def test_luci_tac_acl_uses_exact_subcommands_without_arguments():
    acl = _read("files/usr/share/rpcd/acl.d/luci-app-blue-merle.json")
    libexec = _read("files/usr/libexec/blue-merle")
    assert "set-tac-mode-module" in acl
    assert "set-tac-mode-phone" in acl
    assert 'set-tac-mode)' not in libexec


def test_luci_acl_matches_libexec_surface():
    """The RPC surface is strictly enumerated: every libexec subcommand
    must be reachable through the ACL, and the ACL must not permit
    anything libexec does not implement. Dead subcommands that still
    open the modem / write to ttyS0 must not linger unreachable."""
    import json
    import re

    acl = json.loads(_read("files/usr/share/rpcd/acl.d/luci-app-blue-merle.json"))
    app = acl["luci-app-blue-merle"]
    permitted = set()
    for scope in ("read", "write"):
        for cmd in app.get(scope, {}).get("file", {}):
            assert cmd.startswith("/usr/libexec/blue-merle "), cmd
            permitted.add(cmd.split(" ", 1)[1])

    libexec = _read("files/usr/libexec/blue-merle")
    labels = set()
    for m in re.finditer(r"^    ([a-z0-9|_-]+)\)$", libexec, re.M):
        labels.update(m.group(1).split("|"))
    assert labels == permitted, f"surface/ACL drift: {labels ^ permitted}"


def test_network_tools_check_failures_before_reporting_success():
    newssid = _read("files/usr/bin/blue-merle-newssid")
    newmac = _read("files/usr/bin/blue-merle-newmac")
    assert 'RANDOMIZE_IDENTITY ||' in newssid
    assert 'wifi reload ||' in newssid
    assert 'ifdown "$_iface"' in newmac and 'ifdown $_iface failed' in newmac
    assert 'ifup "$_iface"' in newmac and 'ifup $_iface failed' in newmac


def test_build_does_not_mutate_source_tree():
    src = _read("Makefile")
    install = src.split("define Package/blue-merle/install", 1)[1].split("endef", 1)[0]
    assert "find ./files" not in install
    assert "find $(1)" in install


def test_package_has_uninstall_lifecycle_cleanup():
    makefile = _read("Makefile")
    assert "define Package/blue-merle/prerm" in makefile
    assert "/etc/init.d/volatile-client-macs stop" in makefile
    assert "/etc/init.d/blue-merle-esim-tmpfs stop" in makefile
    assert "/etc/init.d/gl_clients start" in makefile


def test_reload_rotates_identity_when_identity_is_not_stable():
    src = _read("files/etc/init.d/blue-merle")
    reload_block = src.split("reload()", 1)[1]
    assert "RANDOMIZE_IDENTITY || return 1" in reload_block


def test_boot_and_full_rotation_use_paired_identity():
    # Boot rotation and `blue-merle-newmac --full` must rotate SSID and
    # hostname from a single picked name — independent picks desync the
    # pair ("Emma's iPhone" SSID with an "iPhone-XR" hostname), a
    # passive tell for an observer who can see both.
    init = _read("files/etc/init.d/blue-merle")
    start_block = init.split("start()", 1)[1].split("}", 1)[0]
    assert "RANDOMIZE_IDENTITY || return 1" in start_block
    assert "RANDOMIZE_HOSTNAME" not in start_block
    assert "RANDOMIZE_SSID" not in start_block

    newmac = _read("files/usr/bin/blue-merle-newmac")
    assert "RANDOMIZE_IDENTITY || exit 1" in newmac

    functions = _read("files/lib/blue-merle/functions.sh")
    assert "RANDOMIZE_IDENTITY ()" in functions
    assert "_iphone_hostname_from_name ()" in functions
    # The paired helper must compose from ONE pick, not two.
    block = functions.split("RANDOMIZE_IDENTITY ()", 1)[1]
    assert block.count("_pick_iphone_name") == 1


def test_privacy_mounts_verify_tmpfs_type():
    for path in (
        "files/etc/init.d/blue-merle-esim-tmpfs",
        "files/etc/init.d/volatile-client-macs",
    ):
        src = _read(path)
        assert '$3 == "tmpfs"' in src


def test_libexec_sim_swap_applies_stage2_invariants():
    src = _read("files/usr/libexec/blue-merle")
    block = src.split("prepare-sim-swap)", 1)[1].split(";;", 1)[0]
    # The LuCI flow has no stage 2: the value it writes becomes the
    # on-air IMEI after reboot, so the stage2 fail-closed contract
    # applies — shape-validated readback, volatile-store persistence,
    # and poweroff on any uncertain state.
    assert '_is_valid_imei_shape "$new_imei"' in block
    assert '_write_runtime_imei "$new_imei"' in block
    assert "_safe_poweroff" in block
    # Regression: the old pipeline masked READ_IMEI's exit status behind
    # sed (always 0), so a failed readback reported a masked "success".
    assert "READ_IMEI | sed" not in block
    # Mask via the shared canonical helper (same as read-identifiers).
    assert '_mask_imei "$new_imei"' in block
    # Persistence must happen before the masked success output.
    assert block.index("_write_runtime_imei") < block.index('printf \'%s\' "$masked"')


def test_tac_mode_ui_makes_no_device_class_claims():
    # Policy: TAC prefixes do not encode manufacturer or device class.
    # The LuCI labels and libexec comments must not teach users the
    # 86xx=module / 35xx=phone heuristic the project itself rejects.
    for path in (
        "files/usr/libexec/blue-merle",
        "files/www/luci-static/resources/view/blue-merle.js",
    ):
        src = _read(path)
        assert "86xx" not in src, path
        assert "35xx" not in src, path


def test_ci_runs_unit_tests_and_shell_syntax_checks():
    ci = _read(".github/workflows/ci.yml")
    assert "python3 tests/run_all.py" in ci
    assert "sh -n" in ci
    assert "shellcheck -s sh" in ci
    # The package build must not publish artifacts for failing code.
    assert "needs: test" in ci
    # The built ipk is audited for purged/dead files and bytecode.
    assert "Audit package contents" in ci
    assert "__pycache__" in ci
    assert "iphone-models" in ci


def test_diag_script_is_versioned_and_masks_identifiers():
    # The on-device diagnostic used to live only in the gitignored
    # dist/ directory — untracked and easy to lose. It must stay under
    # version control, and it must mask every identifier class.
    diag = _read("tools/blue-merle-diag.sh")
    assert "mask_imei()" in diag
    assert "mask_imsi()" in diag
    assert "mask_mac()" in diag
    assert "mask_name()" in diag
    # The removed model pool must not be probed anymore.
    assert "iphone-models" not in diag


def test_write_runtime_imei_updates_every_modem_dir():
    src = _read("files/lib/blue-merle/functions.sh")
    block = src.split("_write_runtime_imei ()", 1)[1].split("\n}", 1)[0]
    # With several /tmp/modem.*/ candidates the alphabetically-first may
    # belong to a different modem; every integration dir is updated.
    assert "for modem_dir in /tmp/modem.*/" in block
    assert "head -n1" not in block
    # The volatile store remains the fail-closed gate.
    assert "_is_tmpfs_mount /root/esim" in block


def test_makefile_scriptlets_are_valid_busybox_sh():
    """preinst/postinst/prerm/postrm run on the real device at install
    time but are invisible to the CI shell syntax checks (they live in
    make defines). Extract them, undo the make-level $$ escaping, sh -n
    each one, and enforce the AGENTS.md busybox bans."""
    import os
    import re
    import subprocess
    import tempfile

    banned = [
        (r"echo -n", "echo -n (use printf)"),
        (r"\[\[ ", "[[ ]] (use [ ])"),
        (r"\$\{[A-Za-z_][A-Za-z0-9_]*:(?![-=?!+])", "${var:offset} (use cut)"),
        (r"\bmountpoint\b", "mountpoint (use awk on /proc/mounts)"),
        (r"\b(hexdump|od)\b", "od/hexdump (use /proc/sys/kernel/random/uuid)"),
        (r"flock -E", "flock -E (use fd-based flock -n 9)"),
    ]
    mk = _read("Makefile")
    found = 0
    for name in ("preinst", "postinst", "prerm", "postrm"):
        marker = f"define Package/blue-merle/{name}"
        assert marker in mk, f"{name} missing from Makefile"
        body = mk.split(marker, 1)[1].split("endef", 1)[0]
        script = body.replace("$$", "$")
        found += 1
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as tf:
            tf.write(script)
        res = subprocess.run(["sh", "-n", tf.name], capture_output=True, text=True)
        os.unlink(tf.name)
        assert res.returncode == 0, f"{name}: sh -n failed: {res.stderr}"
        for rx, why in banned:
            assert not re.search(rx, script), f"{name}: banned construct {why}"
    assert found == 4


def test_sim_sh_timeout_covers_stage_budget():
    # The stages' own worst-case budget (bounded CFUN retries + EGMR
    # timeout + readbacks + MCU sleeps) is ~100-120 s. The wrapper
    # timeout must clear it comfortably: a SIGTERM landing between the
    # EGMR write and the runtime-store update / safe poweroff would
    # leave a half-finished swap with a stale volatile store.
    import re

    src = _read("files/etc/gl-switch.d/sim.sh")
    timeouts = [int(t) for t in re.findall(r"timeout (\d+) ", src)]
    assert timeouts, "no timeout wrappers found in sim.sh"
    assert all(t >= 150 for t in timeouts), timeouts


def test_mcu_messages_fit_display_segments():
    """The 16x2 MCU display handles long text via whitespace-separated
    segments (the convention in the surviving upstream messages, e.g.
    "Please wait     >1min between   two SIM swaps."). A single segment
    longer than the 32-char screen risks silent truncation, so every
    message is pre-paginated: no segment may exceed 32 chars. Exact
    MCU behaviour is unverified on hardware — keeping segments within
    one screen is the safe choice under every interpretation."""
    import re

    pat = re.compile(
        r'mcu_send_message "([^"]*)"'
        r"|show_message \"([^\"]*)\""
        r"|'\{ ?\"msg\": ?\"([^\"]*)\" ?\}'"
        r'|\{"msg":"([^"]*)"\}'
    )
    for path in (
        "files/usr/bin/blue-merle-switch-stage1",
        "files/usr/bin/blue-merle-switch-stage2",
        "files/usr/bin/blue-merle",
        "files/etc/gl-switch.d/sim.sh",
        "files/etc/init.d/blue-merle",
        "files/usr/libexec/blue-merle",
        "files/lib/blue-merle/functions.sh",
        "Makefile",
    ):
        for line in _read(path).splitlines():
            if line.lstrip().startswith("#"):
                continue
            for m in pat.finditer(line):
                msg = next(g for g in m.groups() if g is not None)
                # Variables get an 8-char placeholder; %s the 32-char max.
                msg = re.sub(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", "XXXXXXXX", msg)
                msg = msg.replace("%s", "X" * 32)
                segs = [s for s in re.split(r" {2,}", msg) if s]
                worst = max((len(s) for s in segs), default=0)
                assert worst <= 32, f"{path}: segment too long in {msg!r}"


def test_tac_lists_do_not_ship_unverified_values():
    for path in (
        "files/lib/blue-merle/tac-list.txt",
        "files/lib/blue-merle/tac-list-phone.txt",
    ):
        lines = [
            line.split("#", 1)[0].strip()
            for line in _read(path).splitlines()
        ]
        assert not [line for line in lines if line], path


def test_imei_generate_log_calls_mask_identifiers():
    """A log.* call must never receive a raw identifier value.

    The script's stdout is the interface (callers capture the printed
    IMEI); every log line goes to stderr, which non-interactive callers
    historically left attached — a full IMEI there lands on terminals
    and likely in syslog via the gl_switch daemon chain. Identifier-
    bearing values (IMEI, IMSI, TAC, raw AT output) may only reach a
    log call wrapped in _mask_id()/_scrub_at_output().
    """
    import ast

    carriers = {
        "imei", "new_imei", "old_imei", "current_imei", "body", "tail",
        "tac", "output", "imsi", "imsi_seed", "candidates", "cmd",
    }
    wrappers = {"_mask_id", "_scrub_at_output", "len"}
    tree = ast.parse(_read("files/lib/blue-merle/imei_generate.py"))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "log"
        ):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id in wrappers
            ):
                continue
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Name) and sub.id in carriers:
                    violations.append(f"line {node.lineno}: raw {sub.id!r}")
                if (
                    isinstance(sub, ast.Attribute)
                    and sub.attr == "static"
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "args"
                ):
                    violations.append(f"line {node.lineno}: raw 'args.static'")
    assert not violations, (
        "unmasked identifier(s) in log call(s): " + "; ".join(violations)
    )


def test_noninteractive_imei_generate_calls_discard_stderr():
    """stage1/stage2/libexec capture stdout (the tool's contract) but
    must also discard stderr: the generator's log lines go there and
    the toggle/LuCI chains have no safe stderr sink (the gl_switch
    daemon's child stderr likely lands in syslog; fs.exec drops it).
    Defence in depth even though the log calls themselves mask
    identifiers."""
    for path in (
        "files/usr/bin/blue-merle-switch-stage1",
        "files/usr/bin/blue-merle-switch-stage2",
        "files/usr/libexec/blue-merle",
    ):
        for lineno, line in enumerate(_read(path).splitlines(), 1):
            if "imei_generate.py" not in line or "python3" not in line:
                continue  # prose comments mentioning the script
            assert "2>/dev/null" in line, f"{path}:{lineno}: {line.strip()}"


def test_cli_refuses_noninteractive_stdin():
    """Every `read` in the interactive CLI treats EOF as the default
    answer — and the default is always the *proceed* branch. With
    closed stdin (ssh router blue-merle </dev/null, ansible) the whole
    chain ran unattended and ended in poweroff. A tty guard must come
    before any prompt (same fix as the Makefile preinst), and every
    read must carry a non-zero-exit EOF handler for the Ctrl-D /
    dropped-SSH case."""
    import re

    src = _read("files/usr/bin/blue-merle")
    assert "[ -t 0 ]" in src
    assert src.index("[ -t 0 ]") < src.index("read -r"), (
        "tty guard must precede the first prompt"
    )
    reads = [
        line for line in src.splitlines()
        if re.search(r"\bread -r\b", line) and not line.strip().startswith("#")
    ]
    assert reads, "expected interactive read prompts in the CLI"
    for line in reads:
        assert "||" in line and "exit 1" in line, (
            f"read without EOF handler: {line.strip()}"
        )


def test_cli_cfun4_retry_loop_is_bounded_and_eof_safe():
    """The CFUN=4 retry prompt used to spin with no sleep on EOF (read
    returns empty, empty is not 'n', immediate retry — 100% CPU hammering
    gl_modem forever). It needs the same bounded escape as stage1
    (15 tries) plus an EOF exit on the read."""
    src = _read("files/usr/bin/blue-merle")
    block = src.split('while [ "$answer" -eq 1 ]', 1)[1].split("done", 1)[0]
    assert "cfun4_tries=$((cfun4_tries+1))" in block
    assert '"$cfun4_tries" -ge 15' in block
    assert "read -r reply ||" in block


def test_stage2_does_not_touch_switch_state_marker():
    """`sim_switch on` in stage2 was vestigial: the /tmp/sim_change_switch
    marker is written by sim.sh and read only by stage1's CHECK_ABORT —
    stage2 never aborts, and the tmpfs marker is wiped by the poweroff
    that ends stage2 anyway. Nobody may write it from stage2; stage1
    must still initialise it when missing (CHECK_ABORT needs a defined
    state on manual invocation)."""
    stage2 = _read("files/usr/bin/blue-merle-switch-stage2")
    for line in stage2.splitlines():
        if line.strip().startswith("#"):
            continue
        assert "sim_switch" not in line, f"stage2 writes switch state: {line}"
    stage1 = _read("files/usr/bin/blue-merle-switch-stage1")
    assert "sim_switch off" in stage1


def test_toggle_driven_marker_scoped_to_stage1():
    """/tmp/blue-merle/toggle-driven tells stage1's CHECK_ABORT that the
    run was toggle-driven. Creating it unconditionally (also for the
    off/stage2 branch) left it present outside stage1's lifetime; it
    must be created only in the on-branch, right before the stage-1
    flock."""
    src = _read("files/etc/gl-switch.d/sim.sh")
    create = ': > /tmp/blue-merle/toggle-driven'
    on_branch = src.split('if [ "$action" = "on" ]; then', 1)[1]
    on_branch = on_branch.split('elif [ "$action" = "off" ]', 1)[0]
    assert create in on_branch, "marker not created in the on-branch"
    assert on_branch.index(create) < on_branch.index("flock -n"), (
        "marker must be created before the stage-1 flock"
    )
    off_branch = src.split('elif [ "$action" = "off" ]; then', 1)[1]
    assert create not in off_branch, "marker must not be created for stage2"


def test_newmac_help_documents_uplink_full_scope():
    """`--full` under `--uplink` rotates only the uplink MAC + the paired
    identity (hostname+SSID) — BSSIDs/AP-side MACs stay untouched. The
    help text (the exact lines the script prints) must say so, and must
    not truncate the trailing --hostname/--ssid note mid-sentence."""
    import re
    import subprocess

    src = _read("files/usr/bin/blue-merle-newmac")
    m = re.search(r"sed -n '(\d+),(\d+)p'", src)
    assert m, "help print range not found"
    start, end = m.group(1), m.group(2)
    newmac = ROOT / "files" / "usr" / "bin" / "blue-merle-newmac"
    out = subprocess.run(
        ["sh", "-c", f"sed -n 's/^# \\{{0,1\\}}//p' {newmac} | sed -n '{start},{end}p'"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "--uplink" in out, "help does not mention the --uplink combination"
    assert "BSSID" in out, "help does not state BSSIDs stay untouched"
    assert "rotation. --ssid alone rotates SSID only." in out, (
        "trailing note truncated mid-sentence (help print range too short)"
    )


def test_announce_ssid_strips_json_breakers():
    """A custom user SSID containing a double quote or backslash would
    break the JSON embedded into the MCU ttyS0 write. The announce
    helper must strip both characters before embedding."""
    src = _read("files/etc/init.d/blue-merle")
    block = src.split("_announce_ssid_on_mcu()", 1)[1].split("\n}", 1)[0]
    needle = "tr -d '" + '"' + "\\" * 2 + "'"
    assert needle in block, "no quote/backslash stripping in _announce_ssid_on_mcu"
    assert block.index(needle) < block.index('printf \'{"msg"'), (
        "stripping must happen before the JSON printf"
    )


def test_announce_ssid_tr_pipeline_yields_valid_json():
    """Functional counterpart: the exact tr/printf pipeline used by
    _announce_ssid_on_mcu turns a hostile SSID into valid JSON with no
    residual quote or backslash."""
    import json
    import subprocess

    script = (
        "ssid='My \"Quoted\" \\ SSID'\n"
        "ssid=$(printf '%s' \"$ssid\" | tr -d '\"\\\\')\n"
        "printf '{\"msg\":\"WiFi:           %s\"}\\n' \"$ssid\"\n"
    )
    out = subprocess.run(
        ["sh", "-c", script], capture_output=True, text=True, check=True,
    ).stdout
    msg = json.loads(out)["msg"]
    assert '"' not in msg and "\\" not in msg, msg
    assert msg == "WiFi:           My Quoted  SSID", msg


def test_ci_pins_shellcheck_tarball_and_skips_feeds():
    """The shellcheck tarball must be verified by SHA256 (supply-chain
    pin), and the build must not run `feeds update` — the package is
    verified to build without it (EXTRA_DEPENDS is metadata-only), which
    the AGENTS.md handoff documents."""
    ci = _read(".github/workflows/ci.yml")
    assert "sha256sum -c" in ci, "shellcheck tarball not pinned by SHA256"
    assert "feeds update" not in ci, "feeds update crept back into CI"
    agents = _read("AGENTS.md")
    assert "without `feeds update`" in agents


def test_volatile_client_macs_guards_running_gl_clients():
    """Mounting tmpfs over /etc/oui-tertf while gl_clients has the
    SQLite db open corrupts the db (gl_clients keeps an fd to the
    hidden flash inode while its journal would land on tmpfs). The
    Makefile preinst stops gl_clients first; the init script itself
    must do the same for a manual `service volatile-client-macs start`
    on a live system — and must restart it on every outcome, so a
    failed take-over never leaves the stock daemon down."""
    src = _read("files/etc/init.d/volatile-client-macs")
    block = src.split("start() {", 1)[1]
    assert "pidof gl_clients" in block
    assert block.index("pidof gl_clients") < block.index("/etc/init.d/gl_clients stop")
    # Stop before the mount, restart after it.
    assert block.index("/etc/init.d/gl_clients stop") < block.index("mount -t tmpfs")
    assert block.index("/etc/init.d/gl_clients start") > block.index("mount -t tmpfs")
    # A single restart site after the mount/verify chain covers both
    # the success and the failure path.
    assert block.count("/etc/init.d/gl_clients start") == 1
    assert "return $rc" in block
    # The take-over is logged.
    import re
    assert re.search(r"logger[^\n]*gl_clients", block), "guard activation must be logged"


def test_no_backslash_s_in_shell_files():
    r"""`\s` is a GNU-ism: in POSIX/musl ERE (OpenWrt busybox grep) it is
    undefined and busybox treats it as a literal 's'. The pool picker
    used '^\s*(#|$)', which on-target silently stops excluding
    whitespace-prefixed comments and whitespace-only lines — a landmine
    for anyone editing a pool file. POSIX form is [[:space:]], which the
    rest of the project already uses. Ban `\s` in every shell file;
    Python regexes (.py, where \s is valid) are out of scope."""
    offenders = []
    for base in ("files", "tools"):
        for path in (ROOT / base).rglob("*"):
            if not path.is_file() or path.suffix == ".py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "\\s" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"\\s in shell file(s): {offenders}"
