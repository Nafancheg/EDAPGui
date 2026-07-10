# MCDU HMI Specification

## Этап 1. Информационная архитектура

### 1. Общая концепция

Главная страница системы — **PROG**. Она открывается по умолчанию после загрузки и отображает текущую фазу полёта.

Приоритеты:
- Boot → PROG.
- Самые частые действия доступны без навигации.
- Максимальная глубина дерева — 2 уровня.

---

## 2. Функциональные клавиши

| Клавиша | Страница | Статус | Назначение |
|---|---|---|---|
| INIT | INIT | ✔ | Предполётная подготовка |
| PROG | Flight Progress | ✔ Boot | Главная фазовая страница |
| F-PLN | Primary Route | ✔ | Активный маршрут |
| SEC F-PLN | Secondary Route | ✔ | Альтернативный маршрут |
| DIR | Direct To | ✔ | Полёт напрямую |
| FUEL PRED | Fuel | ✔ | Контроль топлива |
| PERF | Performance | ✔ | RPY и настройки полёта |
| DATA | System Data | ✔ | EDSM и сканирование |
| MCDU MENU | Settings | ✔ | Настройки |
| RAD NAV | INOP | INOP | Нет аналога |
| ATC COMM | INOP | INOP | Резерв |
| AUTO TUNE | INOP | INOP | Auto Tune находится в PERF |

---

## 3. Дерево навигации

```text
BOOT
 └── PROG
      ├── DEPART
      ├── CLIMB
      ├── CRUISE
      ├── APPROACH
      ├── ARRIVAL
      └── LANDING
```

Отдельные страницы:

```text
INIT
F-PLN -> Route -> System Details
SEC F-PLN -> Compare
DIR
FUEL -> Refuel
PERF
DATA -> EDSM / Scan
MCDU MENU -> MAINT
```

Максимальная глубина: 2 уровня.

---

## 4. Постоянный Header

```text
PAGE NAME              CONTEXT
AP: <state>       MODE <mode>
```

---

## 5. Постоянный Footer

Scratchpad расположен всегда внизу экрана.
Поведение едино для всех страниц.

---

## 6. Контракт интерфейса

- Левая сторона LSK — действия и переключатели.
- Правая сторона LSK — параметры и индикация.
- L6 — RETURN.
- R6 — NEXT PAGE / NEXT PHASE.
- STOP ALL — отдельная аппаратная красная кнопка.
- Header и Footer имеют фиксированную структуру.

---

## 7. Annunciator LED

### PROG
- 🟢 ассист активен
- ⚫ ассист выключен

### FUEL PRED
- 🟢 NORMAL
- 🟡 WARNING
- 🔴 CRITICAL
- ⚫ UNKNOWN

---

## 8. Проверка соответствия

Все ограничения исходного ТЗ соблюдены:
- Boot = PROG
- глубина ≤ 2
- новые клавиши не добавлены
- DATA и MCDU MENU задействованы
- RAD NAV, ATC COMM и AUTO TUNE оставлены согласно требованиям
- STOP ALL вне LSK
- Header/Footer фиксированы
