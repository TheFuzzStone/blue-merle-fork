include $(TOPDIR)/rules.mk

PKG_NAME:=blue-merle
PKG_VERSION:=3.0.5-local
PKG_RELEASE:=$(AUTORELEASE)

PKG_MAINTAINER:=Matthias <matthias@srlabs.de>
PKG_LICENSE:=BSD-3-Clause

include $(INCLUDE_DIR)/package.mk

define Package/blue-merle
	SECTION:=utils
	CATEGORY:=Utilities
	# coreutils-shred was an upstream dependency for the shred-based
	# wipes; this fork replaced them with plain rm (shred is theatre
	# on NAND and pointless on tmpfs). Dropping the dep saves ~50 KB
	# of flash on the device.
	EXTRA_DEPENDS:=luci-base, gl-sdk4-mcu, python3-pyserial
	TITLE:=Anonymity Enhancements for GL-E750 Mudi
endef

define Package/blue-merle/description
	The blue-merle package enhances anonymity and reduces forensic traceability of the GL-E750 Mudi 4G mobile wi-fi router
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/blue-merle/install
	# Copy first, then scrub the staged directory. Builds must never mutate
	# the source checkout.
	$(CP) ./files/* $(1)/
	$(INSTALL_BIN) ./files/etc/init.d/* $(1)/etc/init.d/
	$(INSTALL_BIN) ./files/etc/gl-switch.d/* $(1)/etc/gl-switch.d/
	$(INSTALL_BIN) ./files/etc/hotplug.d/iface/* $(1)/etc/hotplug.d/iface/
	$(INSTALL_BIN) ./files/usr/bin/* $(1)/usr/bin/
	$(INSTALL_BIN) ./files/usr/libexec/blue-merle $(1)/usr/libexec/blue-merle
	$(INSTALL_BIN) ./files/lib/blue-merle/imei_generate.py  $(1)/lib/blue-merle/imei_generate.py
	# Purge known-dead filenames that must never ship even if a copy
	# slipped into the tree as untracked (git rm removes only from the
	# index — $(CP) still copies whatever exists on disk). Extend this
	# list when deprecating files rather than relying on humans to keep
	# their working tree clean.
	rm -f $(1)/etc/hotplug.d/iface/30-blue-merle-rerandomize
	rm -f $(1)/lib/blue-merle/luhn.lua
	# Final scrub of Python bytecode and editor backups from the staged
	# directory. This is the authoritative cleanup — the ipk never
	# contains anything matched by these patterns.
	find $(1) \( -name __pycache__ -o -name '*.pyc' -o -name '*~' \) -exec rm -rf {} + 2>/dev/null || true
endef

define Package/blue-merle/preinst
	#!/bin/sh
	[ -n "$${IPKG_INSTROOT}" ] && exit 0	# if run within buildroot exit

	ABORT_GLVERSION () {
		echo
		if [ -f "/tmp/sysinfo/model" ] && [ -f "/etc/glversion" ]; then
			echo "You have a `cat /tmp/sysinfo/model`, running firmware version `cat /etc/glversion`."
		fi
		echo "blue-merle has only been tested with GL-E750 Mudi versions up to 4.3.26."
		echo "The device or firmware version you are using has not been verified."
		# In non-interactive contexts (ansible, cloud-init, opkg with closed
		# stdin) refuse rather than block on read(). Users who need to force
		# the install can set BLUE_MERLE_FORCE=1.
		if [ "$${BLUE_MERLE_FORCE:-0}" = "1" ]; then
			echo "BLUE_MERLE_FORCE=1 set, continuing anyway."
			return 0
		fi
		if [ ! -t 0 ]; then
			echo "Non-interactive install; refusing on unverified firmware."
			echo "Re-run with BLUE_MERLE_FORCE=1 to override."
			exit 1
		fi
		echo -n "Would you like to continue at your own risk? (y/N): "
		read answer
		case $$answer in
			y*|Y*) return 0 ;;
			*)     exit 1 ;;
		esac
	}

	# Always stop gl_clients first: the volatile-client-macs init script we
	# are about to install replaces /etc/oui-tertf with a tmpfs mount, and
	# doing that while gl_clients has the SQLite db open corrupts the db.
	# Previously an early `exit 0` on the fully-supported 4.3.26 branch
	# skipped this step, so on the *supported* firmware installation could
	# silently break the client database.
	if grep -q "GL.iNet GL-E750" /proc/cpuinfo; then
	    GL_VERSION=$$(cat /etc/glversion 2>/dev/null || echo unknown)
	    case $$GL_VERSION in
		4.3.26)
		    echo "Version $$GL_VERSION is supported."
		    ;;
		4.*)
		    echo "Version $$GL_VERSION is *probably* supported."
		    ABORT_GLVERSION
		    ;;
		*)
		    echo "Unknown firmware version $$GL_VERSION."
		    ABORT_GLVERSION
		    ;;
	    esac
	else
		ABORT_GLVERSION
	fi

	# Optional MCU version check. blue-merle needs MCU >= 1.0.7 for the
	# SIM-swap toggle behaviour; if we can't determine the version we warn
	# but do not fail (the MCU may be older on some units).
	if [ -r /etc/mcuversion ]; then
		mcuver=$$(cat /etc/mcuversion)
		echo "Detected MCU version $$mcuver (need >= 1.0.7)."
	else
		echo "Could not detect MCU version; assuming compatible."
	fi

	/etc/init.d/gl_clients stop 2>/dev/null || true

	# Erase legacy flash artefacts left by an earlier upstream install.
	# Upstream PR #63 wrote the current IMEI to /root/esim/imei on flash;
	# without this cleanup the artefact persists under the tmpfs mount
	# and remains recoverable via forensic analysis of NAND whenever the
	# tmpfs is not mounted. Silent failure is fine: absence of the files
	# is the desired state.
	rm -f /root/esim/imei    2>/dev/null || true
	rm -f /root/esim/log.txt 2>/dev/null || true
endef

define Package/blue-merle/postinst
	#!/bin/sh
	[ -n "$${IPKG_INSTROOT}" ] && exit 0

	uci set switch-button.@main[0].func='sim'
	uci commit switch-button
	# Capture the physical modem's current TAC once. Storing only the
	# first 8 digits avoids retaining the full IMEI while allowing module
	# mode to preserve a real, device-proven TAC without a guessed GSMA DB.
	if ! uci -q get blue-merle.main.original_tac >/dev/null 2>&1; then
		original_imei=$$(gl_modem AT AT+GSN 2>/dev/null | grep -E '^[0-9]{15}$$' | head -n1)
		case $$original_imei in
			[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9])
				uci set blue-merle.main.original_tac="$${original_imei%???????}"
				uci commit blue-merle
				;;
		esac
	fi

	# Enable the new services introduced by this fork.
	/etc/init.d/blue-merle-esim-tmpfs enable 2>/dev/null || true
	/etc/init.d/blue-merle enable 2>/dev/null || true
	/etc/init.d/volatile-client-macs enable 2>/dev/null || true

	# Make privacy mounts effective immediately; enabling without starting
	# left an install-to-reboot window where identifiers could hit flash.
	/etc/init.d/blue-merle-esim-tmpfs start || exit 1
	/etc/init.d/volatile-client-macs start || exit 1
	awk '$$2 == "/root/esim" && $$3 == "tmpfs" { esim=1 }
	     $$2 == "/etc/oui-tertf" && $$3 == "tmpfs" { clients=1 }
	     END { exit !(esim && clients) }' /proc/mounts || exit 1

	/etc/init.d/gl_clients start 2>/dev/null || exit 1

	# Announce completion on the MCU screen if we have one.
	if [ -c /dev/ttyS0 ]; then
		printf '{"msg":"Successfully installed Blue Merle"}\n' > /dev/ttyS0
	fi
endef

define Package/blue-merle/prerm
	#!/bin/sh
	[ -n "$${IPKG_INSTROOT}" ] && exit 0
	/etc/init.d/gl_clients stop 2>/dev/null || true
	/etc/init.d/blue-merle disable 2>/dev/null || true
	/etc/init.d/blue-merle-esim-tmpfs disable 2>/dev/null || true
	/etc/init.d/volatile-client-macs disable 2>/dev/null || true
	/etc/init.d/volatile-client-macs stop 2>/dev/null || true
	/etc/init.d/blue-merle-esim-tmpfs stop 2>/dev/null || true
endef

define Package/blue-merle/postrm
	#!/bin/sh
	[ -n "$${IPKG_INSTROOT}" ] && exit 0

	# Restore the switch to its default (Tor) function. Without the commit
	# the change would be lost on the next reboot.
	uci set switch-button.@main[0].func='tor'
	uci commit switch-button
	# prerm stopped gl_clients before removing the tmpfs services. Bring
	# the stock service back immediately so uninstall leaves a coherent
	# running router even before the recommended reboot.
	/etc/init.d/gl_clients start 2>/dev/null || true
endef
$(eval $(call BuildPackage,$(PKG_NAME)))
