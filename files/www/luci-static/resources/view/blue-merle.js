'use strict';
'require view';
'require fs';
'require ui';

/*
 * blue-merle LuCI view.
 *
 * Features:
 * - IMEI/IMSI displayed masked (click to reveal).
 * - TAC mode dropdown (Module / Phone) with confirmation modal.
 * - SIM swap and Shutdown guarded by confirmation modals.
 */

var isReadonlyView = !L.hasViewPermission() || null;

var css = ''
	+ '.controls { display: flex; margin: .5em 0 1em 0; flex-wrap: wrap; }'
	+ '.controls > div { padding: .25em; flex: 1 1 100%; display: flex; align-items: center; gap: .5em; }'
	+ '.controls label { min-width: 80px; font-weight: bold; }'
	+ '.controls input[type=text] { flex: 1; }'
	+ '.bm-warn { color: #c44; font-weight: bold; }'
	+ '.bm-danger { background: #c44; color: #fff; }'
	+ '.bm-tac-row { margin: .5em 0; display: flex; align-items: center; gap: .5em; }'
	+ '.bm-tac-row label { font-weight: bold; min-width: 80px; }'
	+ '.bm-tac-row select { min-width: 180px; }';

function callBlueMerle(arg, extraArgs) {
	var args = [arg];
	if (extraArgs) args = args.concat(extraArgs);
	return fs.exec('/usr/libexec/blue-merle', args).then(function(res) {
		if (res.code !== 0)
			throw new Error('blue-merle ' + arg + ' exited with code ' + res.code + (res.stderr ? ': ' + res.stderr : ''));
		return (res.stdout || '').trim();
	});
}

function readIMEI() { return callBlueMerle('read-imei'); }
function readIMSI() { return callBlueMerle('read-imsi'); }
function readTacMode() { return callBlueMerle('read-tac-mode'); }

function confirmModal(title, body, confirmLabel, onConfirm) {
	var dlg = ui.showModal(title, [
		E('div', {}, body),
		E('div', { 'class': 'right' }, [
			E('button', {
				'class': 'btn cbi-button-neutral',
				'click': ui.hideModal
			}, [ _('Cancel') ]),
			' ',
			E('button', {
				'class': 'btn bm-danger',
				'click': function() {
					ui.hideModal();
					onConfirm();
				}
			}, [ confirmLabel ])
		])
	]);
	return dlg;
}

function handleShutdown() {
	confirmModal(
		_('Shutdown Mudi?'),
		[
			E('p', {},
				_('The device will power off immediately. You must reboot manually before it can be used again.'))
		],
		_('Shutdown'),
		function() {
			callBlueMerle('shutdown').catch(function(err) {
				ui.addNotification(null, E('p', {}, _('Shutdown failed: ') + err));
			});
		}
	);
}

function runSimSwapFlow() {
	var spinnerID = 'bm-swap-spinner';
	var dlg = ui.showModal(_('SIM swap in progress'), [
		E('p', { 'class': 'spinning', 'id': spinnerID }, [
			_('Disabling modem RF (AT+CFUN=4)…')
		])
	]);

	callBlueMerle('prepare-sim-swap').then(function(maskedImei) {
			var spin = document.getElementById(spinnerID);
			if (spin) spin.style.display = 'none';

			dlg.appendChild(E('div', {}, [
				E('p', {}, _('New IMEI set (masked): ') + maskedImei),
				E('p', { 'class': 'bm-warn' }, [
					_('Now: (1) shut down the device below, (2) physically swap the SIM, '
					  + '(3) move to a different location before powering back on. '
					  + 'The modem is currently RF-off; do NOT bring it back up before the SIM is replaced.')
				]),
				E('div', { 'class': 'right' }, [
					E('button', {
						'class': 'btn cbi-button-neutral',
						'click': ui.hideModal
					}, [ _('Close') ]),
					' ',
					E('button', {
						'class': 'btn bm-danger',
						'click': function() { ui.hideModal(); handleShutdown(); },
						'disabled': isReadonlyView
					}, [ _('Shutdown now') ])
				])
			]));
	}).catch(function(err) {
		var spin = document.getElementById(spinnerID);
		if (spin) spin.style.display = 'none';
		dlg.appendChild(E('p', { 'class': 'bm-warn' },
			_('Error: ') + (err && err.message ? err.message : String(err))));
		dlg.appendChild(E('div', { 'class': 'right' }, [
			E('button', {
				'class': 'btn cbi-button-neutral',
				'click': ui.hideModal
			}, [ _('Dismiss') ])
		]));
	});
}

function handleSimSwap() {
	confirmModal(
		_('Start SIM swap workflow?'),
		[
			E('p', {},
				_('This will:')),
			E('ul', {}, [
				E('li', {}, _('Disable the modem radio (AT+CFUN=4).')),
				E('li', {}, _('Write a randomized IMEI to the modem.')),
				E('li', {}, _('Ask you to power off, swap the SIM, and move location.'))
			]),
			E('p', { 'class': 'bm-warn' },
				_('The device will lose cellular connectivity until you reboot after swapping the SIM. Do not proceed if you rely on the current session.'))
		],
		_('Start SIM swap'),
		runSimSwapFlow
	);
}

function handleTacModeChange(newMode, selectEl) {
	var modeLabel = newMode === 'phone' ? _('Phone (smartphone TACs)') : _('Module (LTE-module TACs)');
	var description = newMode === 'phone' ?
		_('<b>Phone mode</b> uses smartphone TACs (35xxxxxx). This gives a larger anonymity set '
		  + '(millions of devices) but may trigger a capability-mismatch flag at the operator: '
		  + 'the TAC says "Samsung Galaxy" but the device behaves like a data-only LTE modem. '
		  + '<br><br>'
		  + '<b>Use this if your SIM does not work in Module mode</b> — some operators block '
		  + 'consumer SIMs on M2M/module TACs.') :
		_('<b>Module mode</b> uses LTE-module TACs (86xxxxxx — Quectel, Sierra, Telit, u-blox). '
		  + 'This matches the device\'s actual behaviour and avoids the operator\'s capability-'
		  + 'mismatch flag. The anonymity set is smaller (industrial gateways) but consistent. '
		  + '<br><br>'
		  + '<b>This is the recommended default.</b>');

	/* Save the previous value so we can revert the dropdown if the
	 * UCI write fails. This is safer than assuming the opposite of
	 * newMode was the previous value — it explicitly captures the
	 * state before the change. */
	var prevMode = selectEl ? selectEl.getAttribute('data-prev-mode') || 'module' : 'module';

	confirmModal(
		_('Switch TAC mode to: ') + modeLabel + '?',
		[
			E('p', {}, description),
			E('p', { 'class': 'bm-warn' },
				_('The change takes effect at the next IMEI rotation (SIM swap, toggle, or '
				  + 'blue-merle-newmac --full). The current IMEI is not affected.'))
		],
		_('Switch mode'),
		function() {
			callBlueMerle('set-tac-mode', [newMode]).then(function() {
				if (selectEl) selectEl.setAttribute('data-prev-mode', newMode);
				ui.addNotification(null,
					E('p', {}, _('TAC mode switched to ') + modeLabel));
			}).catch(function(err) {
				ui.addNotification(null,
					E('p', { 'class': 'bm-warn' },
						_('Failed to switch TAC mode: ') + err));
				/* Revert the dropdown to the previous value */
				if (selectEl) selectEl.value = prevMode;
			});
		}
	);
}

return view.extend({
	load: function() {},

	render: function() {
		var imeiInputID = 'bm-imei-input';
		var imsiInputID = 'bm-imsi-input';
		var tacSelectID = 'bm-tac-select';

		var view = E([], [
			E('style', { 'type': 'text/css' }, [ css ]),
			E('h2', {}, _('Blue Merle')),
			E('p', {}, _('Anonymity enhancements for the GL-E750 Mudi. IMEI and IMSI are returned masked by the router.')),

			E('div', { 'class': 'controls' }, [
				E('div', {}, [
					E('label', {}, 'IMEI:'),
					E('input', {
						'id': imeiInputID,
						'type': 'text',
						'placeholder': _('reading…'),
						'value': '',
						'readonly': true
					})
				]),
				E('div', {}, [
					E('label', {}, 'IMSI:'),
					E('input', {
						'id': imsiInputID,
						'type': 'text',
						'placeholder': _('reading…'),
						'value': '',
						'readonly': true
					})
				])
			]),

			/* TAC mode dropdown. The initial value is NOT hardcoded —
			 * readTacMode() sets it after page render so the dropdown
			 * always reflects the actual UCI state. */
			E('div', { 'class': 'bm-tac-row' }, [
				E('label', {}, _('TAC mode:')),
				E('select', {
					'id': tacSelectID,
					'disabled': isReadonlyView,
					'change': function(ev) {
						var newMode = ev.target.value;
						if (newMode === 'module' || newMode === 'phone') {
							handleTacModeChange(newMode, ev.target);
						}
					}
				}, [
					E('option', { 'value': 'module' }, [ _('Module (86xx — recommended)') ]),
					E('option', { 'value': 'phone' }, [ _('Phone (35xx — fallback)') ])
				]),
				E('span', {}, [
					_('  Switch to Phone if your SIM does not work in Module mode.')
				])
			]),

			E('div', {}, [
				E('label', {}, _('Actions:')), ' ',
				E('button', {
					'class': 'btn cbi-button-positive',
					'click': handleSimSwap,
					'disabled': isReadonlyView
				}, [ _('SIM swap…') ]),
				' ',
				E('button', {
					'class': 'btn cbi-button-neutral',
					'click': handleShutdown,
					'disabled': isReadonlyView
				}, [ _('Shutdown…') ])
			])
		]);

		readIMEI().then(function(imei) {
			var el = document.getElementById(imeiInputID);
			if (el) {
				el.value = imei;
			}
		}).catch(function() {
			var el = document.getElementById(imeiInputID);
			if (el) el.value = _('unable to read');
		});

		readIMSI().then(function(imsi) {
			var el = document.getElementById(imsiInputID);
			if (el) {
				el.value = imsi;
			}
		}).catch(function() {
			var el = document.getElementById(imsiInputID);
			if (el) el.value = _('no IMSI (SIM missing?)');
		});

		/* Load current TAC mode and set the dropdown. The initial
		 * HTML has no 'selected' attribute — we set it here after
		 * the async read resolves, so the dropdown always reflects
		 * the actual UCI state rather than a hardcoded default. */
		readTacMode().then(function(mode) {
			var el = document.getElementById(tacSelectID);
			if (el) {
				el.value = mode;
				el.setAttribute('data-prev-mode', mode);
			}
		}).catch(function() {
			/* Default to 'module' if read fails */
			var el = document.getElementById(tacSelectID);
			if (el) {
				el.value = 'module';
				el.setAttribute('data-prev-mode', 'module');
			}
		});

		return view;
	},

	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
