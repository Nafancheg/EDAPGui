# MCDU HMI Specification

# Этап 3. Раскладка органов управления

> Ниже приведена раскладка органов управления. На всех страницах
> соблюдается контракт:
>
> -   L1--L5 --- действия/переключатели.
> -   R1--R5 --- параметры/индикация.
> -   L6 --- RETURN.
> -   R6 --- NEXT PAGE / NEXT PHASE.
> -   STOP ALL --- отдельная аппаратная красная кнопка.

## PROG / DEPART

  LSK   Метка           Тип   Назначение
  ----- --------------- ----- ---------------------
  L1    UNDOCK/LAUNCH   A     Отстыковка/взлёт
  L2    THROTTLE 50     A     50% тяги
  L3    THROTTLE 100    A     100% тяги
  L4    ROUTE CONFIRM   A     Подтвердить маршрут
  L5    ---                   
  L6    RETURN          A     Возврат
  R1    SHIP STATUS     V     Статус корабля
  R2    THROTTLE        V     Текущая тяга
  R3    DESTINATION     V     Цель
  R4    TARGET          V     Следующая цель
  R5    READY           V     Готовность
  R6    NEXT PHASE      A     CLIMB

## PROG / CLIMB

  LSK   Метка          Тип   Назначение
  ----- -------------- ----- ------------
  L1    ALIGN TARGET   A     Доворот
  L2    THR 50         A     50%
  L3    ENTER SC       A     Вход в SC
  L4    THR 100        A     100%
  L5    ---                  
  L6    RETURN         A     
  R1    HEADING        V     
  R2    SPEED          V     
  R3    MODE           V     
  R4    TARGET         V     
  R5    STATUS         V     
  R6    NEXT PHASE     A     

## PROG / CRUISE

  LSK   Метка         Тип
  ----- ------------- -----
  L1    FSD ROUTE     T
  L2    HONK          A
  L3    FSS SCAN      A
  L4    ELW SCANNER   T
  L5    SCOOP NOW     A
  L6    RETURN        A
  R1    JUMPS         V
  R2    ETA           V
  R3    DISTANCE      V
  R4    STAR CLASS    V
  R5    FUEL          V
  R6    NEXT PHASE    A

## PROG / APPROACH

L1 Supercruise Assist \[T\] L2 Align Target \[A\] L3 Drop \[A\] R1
Distance \[V\] R2 Bearing \[V\] R3 Target \[V\] R4 Speed \[V\] R5 Status
\[V\] L6 Return / R6 Next

## PROG / ARRIVAL

L1 Request Dock \[A\] L2 Dock \[A\] L3 Services \[A\] L4 Undock \[A\] R1
Dock state \[V\] R2 Fuel \[V\] R3 Station \[V\] R4 Status \[V\] L6
Return / R6 Next

## PROG / LANDING

L1 Orbital Cruise \[A\] L2 Glide \[A\] L3 Surface Approach \[A\] L4
Target POI \[A\] L5 Target Coordinates \[E\] R1 Altitude \[V\] R2
Lat/Lon \[V\] R3 Heading \[V\] R4 Distance \[V\] R5 Bearing \[V\] L6
Return / R6 Next

Scratchpad: - формат координат: LAT/LON - пример: -74.12/5.48 - проверка
диапазонов согласно ТЗ - INVALID при ошибке с сохранением ввода.

## F-PLN

L1-L5 выбор маршрута/систем. R1-R5 информация. ↑↓ листание. R6 следующая
страница.

## SEC F-PLN

L1 Activate Secondary L2 Fuel Safe L3 Fast/Risky R1 Compare R6 Next

## DIR

L1 Nearest Scoopable L2 Nearest System L3 Direct To \[E\] R1 Target info

## FUEL

L1 Activate Refuel L2 Threshold \[E\] R1 Fuel % R2 Tons R3 Avg/Jump R4
Remaining jumps R5 Fuel Status R6 Next

LED: PROG: Green=assist active. FUEL: Green/Yellow/Red/Off.

## PERF

L1 RPY L2 Auto Tune L3 Save Ship L4 Save All R1 Roll R2 Pitch R3 Yaw

## DATA

L1 EDSM L2 Scan Data L3 Objects R1 System info

## MCDU MENU

L1 Voice L2 Overlay L3 Randomness L4 Hotkeys L5 MAINT

MAINT: CV View Debug Timings Reload Bindings Refresh Settings Save All
