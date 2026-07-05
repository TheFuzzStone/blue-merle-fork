'use strict';
'require view';
'require fs';
'require ui';

/*
 * blue-merle LuCI view.
 *
 * Trimmed down from the historical version, which carried a large chunk
 * of unused boilerplate copied from the opkg management view (dead
 * handlers, a broken handleConfig with undefined resolveFn/rejectFn, an
 * unreachable Set-Random button, etc.). All that is removed.
 *
 * Design decisions:
 *
 * - IMEI/IMSI are considered sensitive. We display them masked in the
 *   UI so a screenshot / shoulder-surf does not immediately capture the
 *   full identifier. A small "Reveal" button expands the field on
 *   demand.
 *
 * - The SIM swap and shutdown actions are destructive and irreversible
 *   in a single click; both are guarded by a confirmation modal.
 */

var isReadonlyView = !L.hasViewPermission() || null;

var css = ''
	+ '.controls { display: flex; margin: .5em 0 1em 0; flex-wrap: wrap; }'
	+ '.controls > div { padding: .25em; flex: 1 1 100%; display: flex; align-items: center; gap: .5em; }'
	+ '.controls label { min-width: 80px; font-weight: bold; }'
	+ '.controls input[type=text] { flex: 1; }'
	+ '.bm-warn { color: #c44; font-weight: bold; }'
	+ '.bm-danger { background: #c44; color: #fff; }';

function callBlueMerle(arg) {
	return fs.exec('/usr/libexec/blue-merle', [arg]).then(function(res) {
		if (res.code !== 0)
			throw new Error('blue-merle ' + arg + ' exited with code ' + res.code + (res.stderr ? ': ' + res.stderr : ''));
		return (res.stdout || '').trim();
	});
}

function maskId(id) {
	if (!id || id.length < 8)
		return id || '';
	return id.substring(0, 4) + '******' + id.substring(id.length - 4);
}

function readIMEI() { return callBlueMerle('read-imei'); }
function readIMSI() { return callBlueMerle('read-imsi'); }

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

	callBlueMerle('shutdown-modem').then(function() {
		dlg.appendChild(E('p', {}, _('Generating a random IMEI…')));

		return callBlueMerle('random-imei').then(function(newImei) {
			var spin = document.getElementById(spinnerID);
			if (spin) spin.style.display = 'none';

			dlg.appendChild(E('div', {}, [
				E('p', {}, _('New IMEI set (masked): ') + maskId(newImei)),
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
		});
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

function attachRevealHandler(inputEl, fullValueGetter) {
	var revealed = false;
	inputEl.addEventListener('click', function() {
		if (revealed) return;
		revealed = true;
		var full = fullValueGetter();
		if (full) inputEl.value = full;
	});
}

return view.extend({
	load: function() {},

	render: function() {
		var imeiInputID = 'bm-imei-input';
		var imsiInputID = 'bm-imsi-input';
		var imeiCache = '';
		var imsiCache = '';

		var view = E([], [
			E('style', { 'type': 'text/css' }, [ css ]),
			E('h2', {}, _('Blue Merle')),
			E('p', {}, _('Anonymity enhancements for the GL-E750 Mudi. IMEI and IMSI are shown masked; click a field to reveal it.')),

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
			imeiCache = imei;
			var el = document.getElementById(imeiInputID);
			if (el) {
				el.value = maskId(imei);
				attachRevealHandler(el, function() { return imeiCache; });
			}
		}).catch(function() {
			var el = document.getElementById(imeiInputID);
			if (el) el.value = _('unable to read');
		});

		readIMSI().then(function(imsi) {
			imsiCache = imsi;
			var el = document.getElementById(imsiInputID);
			if (el) {
				el.value = maskId(imsi);
				attachRevealHandler(el, function() { return imsiCache; });
			}
		}).catch(function() {
			var el = document.getElementById(imsiInputID);
			if (el) el.value = _('no IMSI (SIM missing?)');
		});

		return view;
	},

	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
