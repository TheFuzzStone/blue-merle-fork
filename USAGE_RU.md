# blue-merle-fork — руководство пользователя (RU)

> English version: [`USAGE.md`](./USAGE.md)

**Золотое правило:** CLI — самый безопасный. Toggle — самый быстрый без
ноутбука. LuCI — самый простой, но с более слабой защитой от IMSI-leak.

## Установка

Скачайте со страницы [Releases](../../releases), затем:

```sh
scp -O blue-merle_*.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'opkg install --force-reinstall /tmp/blue-merle_*.ipk && reboot'
# после reboot: новый SSID (напр. Emma's iPhone), тот же WiFi-пароль
```

| Меняется при reboot? | Идентификатор | Когда меняется |
|:---:|---|---|
| ✅ | Hostname, SSID, BSSID, клиентский MAC, upstream MAC | при каждой загрузке |
| ❌ | IMEI | только через CLI / toggle / LuCI |
| ❌ | IMSI / SIM | только при физической замене SIM |
| ❌ | WiFi пароль | никогда |

## Смена IMEI

| Способ | Нужен ПК | Защита от IMSI-leak | Тип IMEI |
|---|:---:|:---:|---|
| CLI `blue-merle` | SSH | ✅ полная | random или deterministic |
| Физический переключатель | нет | ✅ полная | только random |
| LuCI web UI | браузер | ⚠️ частичная | только random |

### CLI

```sh
ssh root@192.168.8.1
blue-merle    # → y → заменить SIM → r → s (shutdown, сменить локацию)
# только интерактивно: прерывается, если stdin не терминал
```

### Переключатель

1. Сдвинуть в противоположное положение → MCU: `Replace the SIM card.`
2. Заменить SIM (не трогать ползунок).
3. Сдвинуть обратно → MCU: `IMEI changed. Powering off.`
4. Сменить локацию. Включить.

### LuCI

`http://192.168.8.1` → Blue Merle → `SIM swap…`. Выключить и заменить
SIM перед следующим включением.

## Ротация MAC / SSID (без reboot)

```sh
blue-merle-newmac --full          # все MAC + парная идентичность hostname/SSID
blue-merle-newmac --uplink        # только upstream MAC (клиенты остаются)
blue-merle-newmac --pure-random   # RFC-7844 MAC вместо Apple OUI
blue-merle-newssid                # SSID + синхронизированный hostname
# --full с --uplink: только upstream MAC + идентичность (BSSID остаются,
# но смена SSID всё равно выкидывает клиентов)
```

## Настройка

```sh
uci set blue-merle.main.stable_identity=1 && uci commit blue-merle   # заморозить identity
uci set blue-merle.main.tac_mode=phone && uci commit blue-merle     # или 'module'
```

`module` (по умолчанию) сохраняет базовый TAC модема, снятый при
установке (без внешней базы). `phone` использует ваш
`tac-list-phone.txt` и отказывает, пока туда не добавлены TAC с
документированным источником GSMA.

Пулы — одна запись на строку, `#` = комментарий;
`service blue-merle reload` применяет без reboot:

```sh
vi /lib/blue-merle/{apple-oui,us-first-names,tac-list,tac-list-phone}.txt
# OUI: aa:bb:cc lowercase. Имена: только ASCII-буквы. TAC: 8 цифр.
```

Переменные окружения: `BLUE_MERLE_TTY`, `BLUE_MERLE_FORCE=1`,
`BM_READ_TRIES`, `BLUE_MERLE_TAC`, `BLUE_MERLE_TAC_LIST`,
`BLUE_MERLE_APPLE_OUI`, `BLUE_MERLE_US_NAMES`.

**Отключение функций:**

```sh
service blue-merle disable
service blue-merle-esim-tmpfs disable
service volatile-client-macs disable
chmod -x /etc/hotplug.d/iface/3?-blue-merle-*   # оба hotplug-хука
```

## Диагностика

```sh
logread | grep blue-merle   # только события, никогда значения идентификаторов
sh /tmp/blue-merle-diag.sh  # отредактированный отчёт
# безобидные AT ERROR (игнорировать): AT+QCFG="nwscanseq", AT+QSIMDET
```

## Удаление

```sh
opkg remove blue-merle && reboot
```

Переключатель возвращается к `tor`. UCI-значения остаются до сброса:

```sh
for k in wireless.@wifi-iface[0].macaddr wireless.@wifi-iface[1].macaddr \
         wireless.@wifi-iface[0].ssid wireless.@wifi-iface[1].ssid \
         network.@device[1].macaddr glconfig.general.macclone_addr \
         system.@system[0].hostname; do uci -q delete "$k"; done
uci commit && reboot
```

## Шпаргалка (менее очевидные команды)

```sh
/usr/libexec/blue-merle read-identifiers  # маскированные IMEI+IMSI (JSON)
/usr/libexec/blue-merle prepare-sim-swap  # атомарно RF-off + interim IMEI
/usr/libexec/blue-merle shutdown          # выключение через MCU
python3 /lib/blue-merle/imei_generate.py --static <15-значный-IMEI>
mount | grep -E 'esim|oui-tertf'          # tmpfs-монтирования активны?
```
