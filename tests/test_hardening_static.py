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


def test_network_tools_check_failures_before_reporting_success():
    newssid = _read("files/usr/bin/blue-merle-newssid")
    newmac = _read("files/usr/bin/blue-merle-newmac")
    assert 'RANDOMIZE_SSID ||' in newssid
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


def test_reload_rotates_hostname_when_identity_is_not_stable():
    src = _read("files/etc/init.d/blue-merle")
    reload_block = src.split("reload()", 1)[1]
    assert "RANDOMIZE_HOSTNAME || return 1" in reload_block


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
    # Mask form matches read-imei (cut-based), not the old sed 4+4 form.
    assert "cut -c1-6" in block
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
