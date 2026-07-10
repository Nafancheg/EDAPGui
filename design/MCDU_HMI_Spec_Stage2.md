# MCDU HMI Specification

# Этап 2. Структура страниц

## PROG (главная)

Назначение: выполнение полёта.

Фазы: 1. DEPART 2. CLIMB 3. CRUISE 4. APPROACH 5. ARRIVAL 6. LANDING

Навигация: - ←/→ --- переход между фазами. - R6 --- NEXT PHASE. - L6 ---
RETURN (если открыта подстраница).

### DEPART

  Строка   Левая сторона     Правая сторона
  -------- ----------------- ------------------
  1        Undock / Launch   Ship status
  2        Throttle          Current throttle
  3        Route confirm     Destination
  4        ---               Target system
  5        ---               Ready state
  6        RETURN\*          NEXT PHASE

### CLIMB

1.  Align to target / Heading
2.  Throttle / Speed
3.  Enter supercruise / Mode
4.  --- / Target
5.  --- / Status
6.  RETURN / NEXT

### CRUISE

1.  FSD Assist / Jump progress
2.  Honk / ETA
3.  FSS / Distance
4.  ELW Scanner / Current star
5.  Scoop status / Fuel
6.  RETURN / NEXT

### APPROACH

1.  Supercruise Assist / Distance
2.  Align to Target / Bearing
3.  Drop readiness / Target
4.  --- / Speed
5.  --- / Status
6.  RETURN / NEXT

### ARRIVAL

1.  Request Dock / Target
2.  Dock / Dock state
3.  Services / Fuel state
4.  Undock / Station
5.  --- / Status
6.  RETURN / NEXT

### LANDING

1.  Drop to OC / Altitude
2.  Enter Glide / Coordinates
3.  Surface approach / Heading
4.  Target POI / Distance
5.  Target Coordinates / Bearing
6.  RETURN / NEXT

------------------------------------------------------------------------

## INIT

Назначение: - выбор корабля; - подтверждение маршрута; - готовность к
вылету; - переходы в основные разделы.

------------------------------------------------------------------------

## F-PLN

Назначение: активный маршрут.

Подстраницы: - Route list - System details

Листание маршрута --- slew ↑↓

------------------------------------------------------------------------

## SEC F-PLN

Назначение: резервный маршрут.

Подстраница: - Compare

------------------------------------------------------------------------

## DIR

Назначение: Direct-To.

Строки: - ближайшая scoopable; - ближайшая система; - ввод имени
системы; - информация о цели.

------------------------------------------------------------------------

## FUEL PRED

Строки: 1. Fuel onboard 2. Fuel tons 3. Avg fuel/jump 4. Jumps until
refuel 5. Refuel threshold 6. Refuel menu

Подстраница: REFUEL SOURCE

-   Star in current system
-   Nearest station (backend)
-   Nearest refuel point (backend)

------------------------------------------------------------------------

## PERF

Строки: - RPY editor - Auto Tune - Speed context - Save ship - Save all

------------------------------------------------------------------------

## DATA

Подстраницы: - EDSM - Scan data - System information

------------------------------------------------------------------------

## MCDU MENU

Корневая страница: - Voice - Overlay - Randomness - Hotkeys - Automatic
logout - MAINT

### MAINT

-   CV View
-   Debug
-   Timing
-   Reload bindings
-   Refresh settings
-   Save All

## Проверка

-   Каждая страница отвечает одной предметной области.
-   Глубина не превышает двух уровней.
-   Полётные функции находятся только в PROG.
-   Настройки вынесены в MCDU MENU.
-   Маршруты разделены на F-PLN / SEC F-PLN / DIR.
