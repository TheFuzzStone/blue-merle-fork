# blue-merle-fork — руководство пользователя (RU)

> English version: [`USAGE.md`](./USAGE.md).

Краткий справочник по установленному пакету `blue-merle_3.0.5-local`
на GL-E750 Mudi. Список отличий от upstream — в [`README.md`](./README.md).

**Золотое правило:** CLI — самый безопасный путь. Физический
переключатель — самый быстрый без ноутбука. LuCI — самый простой,
но с самой слабой защитой от IMSI-leak; используйте только когда
других вариантов нет.

---

## Содержание

1. [Установка](#1-установка)
2. [Смена IMEI](#2-смена-imei)
3. [Ротация MAC / BSSID / hostname / SSID](#3-ротация-mac--bssid--hostname--ssid)
4. [Автоматика при загрузке и hotplug](#4-автоматика-при-загрузке-и-hotplug)
5. [Настройка](#5-настройка)
6. [Диагностика](#6-диагностика)
7. [Удаление / откат](#7-удаление--откат)
8. [Рецепты](#8-рецепты)
9. [Шпаргалка команд](#9-шпаргалка-команд)

---

## 1. Установка

Скачайте ipk со страницы [Releases](../../releases) (см. README.md),
затем:

```sh
# С вашего ПК (Mudi доступен по 192.168.8.1 через WiFi/LAN):
scp -O blue-merle_3.0.5-local-*.ipk root@192.168.8.1:/tmp/

# На Mudi:
opkg install --force-reinstall /tmp/blue-merle_3.0.5-local-*.ipk
reboot                              # обязательно — mount tmpfs + первая ротация
```

**Что меняется при каждой перезагрузке — а что нет:**

| Идентификатор | Меняется при reboot? | Когда меняется? |
|---|:---:|---|
| **Hostname** (напр. `iPhone-15-Pro`) | ✅ да | при каждой загрузке |
| **SSID** (напр. `Emma's iPhone`) | ✅ да | при каждой загрузке |
| **BSSID** (WiFi MAC) | ✅ да | при каждой загрузке |
| **Клиентский MAC** (WiFi/Ethernet) | ✅ да | при каждой загрузке |
| **Upstream MAC** (repeater) | ✅ да | при каждой загрузке |
| **IMEI** | ❌ нет | только через `blue-merle` / toggle / LuCI |
| **IMSI / SIM** | ❌ нет | только при физической замене SIM |
| **WiFi пароль** | ❌ нет | никогда — тот же пароль при всех ротациях |

Ноутбук не подключится автоматически после reboot — SSID новый.
Кликните «Подключиться» на новом имени и введите **тот же** WiFi-
пароль, что и раньше. **Пароль не ротируется.**

---

## 2. Смена IMEI

Три интерфейса с разными гарантиями:

| Способ | Нужен ПК | Защита от IMSI-leak | Тип IMEI |
|---|:---:|:---:|---|
| CLI `blue-merle` | да (SSH) | ✅ полная (CFUN=4 до свапа SIM) | random или deterministic |
| Физический переключатель | нет | ✅ полная (две стадии) | только random |
| LuCI web UI | только браузер | ⚠️ частичная (нет шага swap SIM) | только random |

### 2.1. CLI (рекомендуется)

```sh
ssh root@192.168.8.1
blue-merle
```

Отвечать на промпты:

1. `Swap SIM card and update IMEI? (Y/n):` → `y`
2. Модем переходит в RF-off; **физически меняете SIM** сейчас.
3. Любая клавиша для продолжения.
4. `Random (r) or deterministic (d) IMEI? (R/d):` → `r` (по умолчанию);
   `d` — детерминированный IMEI из данного IMSI (полезно только если
   понимаете компромисс по linkability).
5. `Shutdown (s) or reset the modem (m)? (S/m):` → `s` (перед
   включением смените локацию для полной несвязываемости).

### 2.2. Физический переключатель

Ползунок Mudi имеет **два положения**, оба используются.

1. Сдвиньте в противоположное положение → MCU показывает
   `Starting SIM swap.` → модем RF off →
   `Replace the SIM card. Then pull the switch.`
2. Замените SIM. Ползунок **не двигайте** пока меняете.
3. Сдвиньте обратно → модем перезапускается, пишется финальный
   random IMEI, MCU: `IMEI changed. Powering off.` → устройство
   выключится через 5 секунд.
4. **Смените локацию.** Включите снова — остальное ротируется
   автоматически.

### 2.3. LuCI

Браузер → `http://192.168.8.1/cgi-bin/luci` → `System` →
`Advanced Settings` → `Network` → `Blue Merle` → `SIM swap…`.
Подтверждает через modal, потом просит вручную заменить SIM и
выключить устройство. **Ограничение:** нужно действительно выключить
Mudi и заменить SIM до следующего включения, иначе оператор увидит
`new IMEI + old SIM` в той же локации. Предпочтите CLI или переключатель,
если это критично.

---

## 3. Ротация MAC / BSSID / hostname / SSID

Это идентификаторы в эфире. Пакет ротирует их автоматически при
загрузке; ниже — как форсировать ротацию без reboot.

```sh
# Полная смена личности одной командой (все MAC + hostname + SSID;
# WiFi-клиенты будут отключены — BSSID меняется)
blue-merle-newmac --full

# Только upstream MAC (repeater / WAN); AP-клиенты не рвутся.
# Используйте перед подключением к новому hotspot.
blue-merle-newmac --uplink

# Только SSID
blue-merle-newssid

# Preview без применения
blue-merle-newmac --dry-run
blue-merle-newssid --dry-run
```

Добавить `--pure-random` к `blue-merle-newmac` — RFC-7844
locally-administered MAC вместо Apple OUI (полезно если upstream
делает fingerprinting «iPhone hostname на Linux DHCP stack»).

---

## 4. Автоматика при загрузке и hotplug

**При загрузке** (`/etc/init.d/blue-merle`, START=10):

1. Новые BSSID для обоих радио (Apple OUI).
2. Новые клиент-видимые MAC (WiFi, Ethernet, upstream — все Apple OUI).
3. Новый hostname из `/lib/blue-merle/iphone-models.txt`.
4. Новый SSID `<Name>'s iPhone` из `/lib/blue-merle/us-first-names.txt`.
5. MCU показывает `WiFi: <SSID>` чтобы вы знали к чему подключаться.

Плюс два вспомогательных сервиса монтируют tmpfs, чтобы
идентификаторы не переживали reboot: `blue-merle-esim-tmpfs`
(`/root/esim`) и `volatile-client-macs` (`/etc/oui-tertf`).

**При WiFi ifdown** (обычно во время `wifi reload`):
`/etc/hotplug.d/iface/30-blue-merle-bssid-on-ifdown` переписывает
BSSID, чтобы следующий ifup поднялся уже с новыми.

**При upstream ifup** (`wwan` или `wan`):
`/etc/hotplug.d/iface/31-blue-merle-uplink-mac` подготавливает
свежий `macclone_addr` для *следующего* подключения.

---

## 5. Настройка

Всё через UCI. Две полезные опции в `/etc/config/blue-merle`:

```sh
# Одна стабильная идентичность между reboot'ами (по Apple-style —
# настоящий iPhone тоже не ротирует MAC/SSID при каждой загрузке).
# Ручная ротация через `blue-merle-newmac --full` всё равно работает.
uci set blue-merle.main.stable_identity=1
uci commit blue-merle
service blue-merle reload
```

**Настройка пулов Apple-маскировки напрямую:**

```sh
vi /lib/blue-merle/iphone-models.txt      # hostname (iPhone-15-Pro-Max, …)
vi /lib/blue-merle/apple-oui.txt          # OUI-префиксы (3c:22:fb, …)
vi /lib/blue-merle/us-first-names.txt     # имена для SSID (Emma, …)
```

Правила: одна запись на строку, `#` — комментарий. **hostname** —
только `[A-Za-z0-9-]`, до 63 символов (RFC 952). **OUI** — формат
`aa:bb:cc` в нижнем регистре. **Имена** — только ASCII-буквы
(апостроф в SSID `<Name>'s iPhone` добавляется автоматически).
Невалидные записи молча игнорируются. `service blue-merle reload`
применяет без reboot.

**Переменные окружения** (для скриптов / отладки):

| Переменная | Действие |
|---|---|
| `BLUE_MERLE_TTY` | Путь к TTY модема (default: динамический поиск, потом `/dev/ttyUSB3`) |
| `BLUE_MERLE_FORCE=1` | Пропустить preinst-промпт при установке |
| `BM_READ_TRIES` | Retry-cap для чтения IMEI/IMSI (default 5) |
| `BLUE_MERLE_APPLE_OUI` | Путь к списку Apple-OUI (default: `/lib/blue-merle/apple-oui.txt`) |
| `BLUE_MERLE_IPHONE_MODELS` | Путь к списку моделей iPhone |
| `BLUE_MERLE_US_NAMES` | Путь к списку US-имён |

**Откат к нейтральной (не-Apple) ротации:**

```sh
# Удаление любого из этих файлов → соответствующая ротация
# откатывается на нейтральное поведение (locally-administered MAC /
# Mudi-<hex> hostname / стабильный SSID).
mv /lib/blue-merle/apple-oui.txt       /lib/blue-merle/apple-oui.txt.disabled
mv /lib/blue-merle/iphone-models.txt   /lib/blue-merle/iphone-models.txt.disabled
mv /lib/blue-merle/us-first-names.txt  /lib/blue-merle/us-first-names.txt.disabled
```

**Отключение отдельных функций:**

```sh
service blue-merle disable                 # нет ротации при загрузке
service blue-merle-esim-tmpfs disable      # IMEI будет оседать на flash
service volatile-client-macs disable       # БД MAC клиентов на flash
chmod -x /etc/hotplug.d/iface/30-blue-merle-bssid-on-ifdown   # нет BSSID hotplug
chmod -x /etc/hotplug.d/iface/31-blue-merle-uplink-mac        # нет uplink-MAC hotplug
```

---

## 6. Диагностика

**Event log** (значения никогда не логируются — только действия):

```sh
logread | grep blue-merle
```

Ожидаемые сообщения: `Running Stage 1/2`,
`IMEI change completed (values omitted)`,
`Refreshed BSSIDs (uci) after ifdown of wlanX — next ifup will use them`,
`Rotated upstream macclone_addr after ifup of wwan`.

**Полный маскированный отчёт** — используйте перед просьбой о помощи:

```sh
# С ПК:
scp -O dist/blue-merle-diag.sh root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'sh /tmp/blue-merle-diag.sh'
# Отчёт в /tmp/blue-merle-diag.out на Mudi.
scp -O root@192.168.8.1:/tmp/blue-merle-diag.out ./
less blue-merle-diag.out                # ID маскированы; безопасно шэрить
```

**Модем не отвечает:**

```sh
ls /dev/ttyUSB*
gl_modem AT AT
```

**Известные ERROR-ответы AT-команд (не проблемы):**

Некоторые AT-команды возвращают `ERROR` на стоковой прошивке Quectel
EP06 (`EP06ELAR03A08M4G`) — это **не** баги и не влияют на работу:

| Команда | Ответ | Причина |
|---|---|---|
| `AT+QCFG="nwscanseq"` | `ERROR` | Конфигурация последовательности сканирования сетей не поддерживается этой прошивкой; модем использует порядок по умолчанию. |
| `AT+QSIMDET` | `ERROR` | Hot-swap detection SIM не реализован; SIM определяется при подаче питания. Не влияет на смену SIM — blue-merle перезапускает модем через `CFUN=0`/`CFUN=4` после физической замены. |

Если видите `ERROR` от этих команд при диагностике — игнорируйте.

**Проверить что IMEI не утёк в syslog после ротации** (пусто = ok):

```sh
blue-merle
logread | grep -iE 'blue-merle.*[0-9]{14,15}'
```

**Unit-тесты** (dev-машина, не на Mudi):

```sh
python3 tests/run_all.py     # 44 passed, 0 failed
```

---

## 7. Удаление / откат

```sh
opkg remove blue-merle
reboot
```

- Переключатель возвращается к `tor` (postrm теперь коммитит UCI).
- Рандомизированные UCI-значения (BSSID/MAC/SSID/hostname)
  **остаются** в `/etc/config` до ручного сброса. Оригинальный MAC —
  на наклейке под аккумулятором. Сброс:

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

Ядерный вариант: `firstboot; reboot -f` (стирает `/overlay`).

---

## 8. Рецепты

**Полная смена личности перед пересечением границы:**

1. `ssh root@192.168.8.1` → `blue-merle` → свап SIM → `r` → `s`
   (shutdown).
2. Переместитесь хотя бы на пару сотен метров.
3. Включите Mudi — при загрузке автоматически сменятся BSSID / MAC /
   hostname / SSID.

**Быстрая смена IMEI без перезагрузки:**

```sh
blue-merle    # → 'r' (random), 'm' (reset modem)
```

Модем вернётся через ~30–60 с. **Минус:** та же локация → оператор
видит смену IMEI на том же месте.

**Ежедневная автоматическая ротация IMEI** (продвинуто, рискованно —
смена IMEI без смены SIM и локации связывает сессии):

```sh
cat > /etc/crontabs/root <<'EOF'
0 3 * * * /usr/libexec/blue-merle random-imei && /usr/libexec/blue-merle shutdown
EOF
service cron restart
```

**Восстановить оригинальный IMEI:**

blue-merle не сохраняет оригинал (это было бы forensic-артефактом).
Оригинал напечатан на наклейке под аккумулятором.

```sh
python3 /lib/blue-merle/imei_generate.py --static <оригинальный_15-значный_IMEI>
```

---

## 9. Шпаргалка команд

```sh
# Ротация идентичности (без reboot)
blue-merle                                # интерактивная смена IMEI (рекомендуется)
blue-merle-newmac --full                  # MAC + hostname + SSID
blue-merle-newmac --uplink                # только upstream MAC (AP-клиенты не рвутся)
blue-merle-newmac --pure-random           # RFC-7844 MAC вместо Apple OUI
blue-merle-newssid                        # только SSID
blue-merle-newssid --dry-run              # preview

# Чтение текущих значений (LuCI использует их тоже)
/usr/libexec/blue-merle read-imei
/usr/libexec/blue-merle read-imsi
/usr/libexec/blue-merle random-imei       # сгенерировать + записать
/usr/libexec/blue-merle shutdown-modem    # AT+CFUN=4
/usr/libexec/blue-merle shutdown          # чистое выключение через MCU

# Python IMEI-инструмент (advanced)
python3 /lib/blue-merle/imei_generate.py --random
python3 /lib/blue-merle/imei_generate.py --deterministic
python3 /lib/blue-merle/imei_generate.py --static <15-digit-IMEI>

# Управление services
service blue-merle          {start,stop,restart,reload,enable,disable}
service blue-merle-esim-tmpfs {start,stop,enable,disable}
service volatile-client-macs  {start,stop,enable,disable}

# Конфиг
uci set blue-merle.main.stable_identity=1 && uci commit blue-merle
vi /lib/blue-merle/{iphone-models,apple-oui,us-first-names}.txt

# Диагностика
sh /tmp/blue-merle-diag.sh                # пишет /tmp/blue-merle-diag.out
logread | grep blue-merle
mount | grep -E 'esim|oui-tertf'
uci show wireless | grep -E 'macaddr|ssid'
uci get system.@system[0].hostname

# Удаление
opkg remove blue-merle
```
