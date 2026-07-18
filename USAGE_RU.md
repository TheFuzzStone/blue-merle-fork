# blue-merle-fork — руководство пользователя (RU)

> English version: [`USAGE.md`](./USAGE.md)

**Золотое правило:** CLI — самый безопасный. Toggle — самый быстрый без
ноутбука. LuCI — самый простой, но с более слабой защитой от IMSI-leak.

## Установка

Скачайте со страницы [Releases](../../releases), затем:

```sh
scp -O blue-merle_*.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'opkg install --force-reinstall /tmp/blue-merle_*.ipk && reboot'
```

После reboot: новый SSID (напр. `Emma's iPhone`), тот же WiFi-пароль.

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
```

### Переключатель

1. Сдвинуть в противоположное положение → MCU: `Replace the SIM card.`
2. Заменить SIM (не трогать ползунок).
3. Сдвинуть обратно → MCU: `IMEI changed. Powering off.`
4. Сменить локацию. Включить.

### LuCI

`http://192.168.8.1` → Blue Merle → `SIM swap…`. Нужно выключить и
заменить SIM перед следующим включением.

## Ротация MAC / SSID (без reboot)

```sh
blue-merle-newmac --full          # все MAC + парная идентичность hostname/SSID
blue-merle-newmac --uplink        # только upstream MAC (клиенты остаются)
blue-merle-newmac --pure-random   # RFC-7844 MAC вместо Apple OUI
blue-merle-newssid                # SSID + синхронизированный hostname
```

## Настройка

```sh
uci set blue-merle.main.stable_identity=1 && uci commit blue-merle   # заморозить identity
uci set blue-merle.main.tac_mode=phone && uci commit blue-merle     # или 'module'
```

**Политика TAC:**

| Режим | Источник | Примечания |
|---|---|---|
| module (по умолчанию) | Базовый TAC модема при установке | Без внешней базы. |
| phone | `tac-list-phone.txt` (пользовательский) | Отказывает, пока не добавлены проверенные TAC с источником GSMA. |

**Редактирование пулов:**

```sh
vi /lib/blue-merle/{apple-oui,us-first-names,tac-list,tac-list-phone}.txt
```

Одна запись на строку, `#` = комментарий.
OUI: `aa:bb:cc` lowercase. Имена: только ASCII-буквы. TAC: 8 цифр.
`service blue-merle reload` применяет без reboot.

**Переменные окружения:** `BLUE_MERLE_TTY`, `BLUE_MERLE_FORCE=1`,
`BM_READ_TRIES`, `BLUE_MERLE_TAC`, `BLUE_MERLE_TAC_LIST`,
`BLUE_MERLE_APPLE_OUI`, `BLUE_MERLE_US_NAMES`.

**Отключение функций:**

```sh
service blue-merle disable
service blue-merle-esim-tmpfs disable
service volatile-client-macs disable
chmod -x /etc/hotplug.d/iface/30-blue-merle-bssid-on-ifdown
chmod -x /etc/hotplug.d/iface/31-blue-merle-uplink-mac
```

## Диагностика

```sh
logread | grep blue-merle                           # только события, без значений
sh /tmp/blue-merle-diag.sh                          # отредактированный отчёт
```

Известные безобидные AT ERROR: `AT+QCFG="nwscanseq"`, `AT+QSIMDET` — игнорировать.

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

## Шпаргалка

```sh
blue-merle                                # интерактивная смена IMEI
blue-merle-newmac --full                  # ротация всего
blue-merle-newmac --uplink                # только upstream MAC
blue-merle-newssid                        # SSID + синхронизированный hostname
/usr/libexec/blue-merle read-identifiers  # маскированные IMEI+IMSI (JSON)
/usr/libexec/blue-merle prepare-sim-swap  # атомарно RF-off + interim IMEI
/usr/libexec/blue-merle shutdown           # выключение через MCU
python3 /lib/blue-merle/imei_generate.py --static <15-значный-IMEI>
service blue-merle {start,stop,reload,enable,disable}
logread | grep blue-merle
mount | grep -E 'esim|oui-tertf'
```
