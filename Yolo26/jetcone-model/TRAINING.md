# Инструкция по дообучению модели jetcone (YOLOv26)

## Обзор

Модель `jetcone-model` — YOLOv26 nano, 2 класса:
- `0: core` — яркое ядро нейтронной звезды / белого карлика
- `1: jetcone` — плазменный конус (джет)

Используется сервисом `services/jetcone_service.py` для автоматического входа в конус и зарядки FSD.

Файлы и папки:
```
Yolo26/jetcone-model/
├── yolo26n.pt          # базовая предобученная модель YOLOv26 nano
├── weights/best.pt     # обученные веса  ← грузится в MachineLearning.py
├── data.yaml           # конфиг датасета (пути, классы)
├── args.yaml           # последние параметры обучения
├── dataset/            # ── ГОТОВЫЙ датасет для обучения ──
│   ├── train/images/   #   .jpg кадры (80%)
│   ├── train/labels/   #   .txt разметка YOLO
│   ├── val/images/     #   .jpg кадры (20%)
│   └── val/labels/     #   .txt разметка YOLO
├── captures/           # сырые скриншоты → prelabel_jetcone.py → dataset/
├── auto_labels/        # автосохранения при успешном бусте в игре
└── runs/               # результаты обучения (создаётся YOLO)
```

Инструменты:
- `tools/jetcone_dataset.py` — сбор сырых кадров (3 режима)
- `tools/prelabel_jetcone.py` — авторазметка кадров из `captures/` → `dataset/`

---

## Полный цикл дообучения (7 шагов)

### Шаг 1. Собрать сырые кадры в `captures/`

Три способа — через единый скрипт `tools/jetcone_dataset.py`:

| Команда | Что делает |
|---------|-----------|
| `python tools/jetcone_dataset.py` | Интерактивный захват окна Elite Dangerous. Открывает preview-окно: **SPACE** = скриншот, **ESC** = выход. Кадры пишутся в `captures/jetcone_20260714_153022_123.jpg` |
| `python tools/jetcone_dataset.py clip.mp4` | Извлекает каждый 30-й кадр из локального видео. Поддерживает `.mp4 .avi .mkv .mov .webm` |
| `python tools/jetcone_dataset.py "https://youtube.com/..."` | Качает видео через `yt-dlp` (нужен `pip install yt-dlp`), затем извлекает кадры |

Все кадры попадают в `Yolo26/jetcone-model/captures/`.

**Что снимать:** нейтронные звёзды (N) и белые карлики (D) — разные ракурсы, разная дальность, разные цвета HUD. Минимум 50–100 кадров, лучше 200+.

Также периодически забирайте накопленные кадры из `auto_labels/` — они сохраняются автоматически при каждом успешном бусте в игре:
```powershell
# Перенести auto_labels в captures для последующей обработки
cp Yolo26/jetcone-model/auto_labels/*.jpg Yolo26/jetcone-model/captures/
cp Yolo26/jetcone-model/auto_labels/*.txt Yolo26/jetcone-model/captures/
```

---

### Шаг 2. Запустить прелейблинг

Скрипт `tools/prelabel_jetcone.py` берёт **все** `.jpg/.jpeg/.png` из `captures/` и для каждого кадра генерирует YOLO-разметку (`.txt`):

```powershell
cd EDAPGui
python tools/prelabel_jetcone.py
```

**Что конкретно делает скрипт (по шагам):**

1. Читает список всех изображений из `Yolo26/jetcone-model/captures/`
2. Перемешивает случайно, делит: 80% → `dataset/train/`, 20% → `dataset/val/`
3. Копирует каждый `.jpg` в `dataset/train/images/` или `dataset/val/images/`
4. Для каждого кадра вызывает `label_frame()` — вот её логика:

   **Детекция core (класс 0):**
   - Переводит в серый, берёт порог яркости — всё что выше 85-го перцентиля
   - Делает dilate (5×5, 2 итерации) — сливает соседние яркие пятна
   - Находит контуры, берёт самый большой
   - Фильтр: площадь бокса от 0.2% до 40% кадра (иначе не core)
   - Записывает: `0 cx cy w h` (нормализованные, 6 знаков)

   **Детекция jetcone (класс 1):**
   - HSV-фильтр: `H: 90–140, S: 20–255, V: 180–255` (сине-белый конус)
   - Морфология: CLOSE 7×7 (заполняет дыры в маске)
   - Находит контуры, берёт до 2 крупнейших
   - Фильтр: ширина > 30px, высота > 30px, площадь < 60% кадра
   - Записывает: `1 cx cy w h` для каждого найденного конуса

5. Выводит статистику: сколько кадров в train/val, сколько всего лейблов, сколько кадров пропущено (ничего не найдено)

**Пример вывода:**
```
  train: 160 images → .../dataset/train/images
  val: 40 images → .../dataset/val/images
Total labels: 380
Skipped 12 frames (no objects detected) — review manually
Dataset ready at: ...\Yolo26\jetcone-model\dataset
```

---

### Шаг 3. Проверить и поправить разметку

**Это самый важный шаг.** Авторазметка ошибается, если:
- Звезда очень далеко → core не детектится (слишком маленький)
- Звезда очень близко → core занимает >40% кадра (отфильтрован)
- Конус тусклый/короткий → не проходит HSV-порог
- Яркий HUD-элемент → может быть принят за core или jetcone
- Звезда не на чёрном фоне (туманность) → HSV-маска захватывает лишнее

**Что делать:**

Откройте папки `dataset/train/images/` и `dataset/val/images/` в любом YOLO-совместимом разметчике:
- **[LabelImg](https://github.com/HumanSignal/labelImg)** — простой, локальный, формат YOLO
- **[Label Studio](https://labelstud.io/)** — веб-интерфейс, можно локально
- **[CVAT](https://www.cvat.ai/)** — мощный, для больших датасетов

**Что проверять на КАЖДОМ кадре:**

| Проверка | Действие |
|----------|----------|
| Core (класс 0) — бокс точно вокруг яркого центра? | Поправить/перерисовать |
| Jetcone (класс 1) — бокс охватывает ВЕСЬ видимый конус? | Поправить/перерисовать |
| Два конуса видны — оба размечены как класс 1? | Добавить второй бокс |
| На кадре вообще нет конуса? | Удалить `.jpg` и `.txt` |
| Бокс захватил HUD или другие объекты? | Поправить |
| Core и jetcone пересекаются? | Разнести — они должны быть отдельными боксами |

Особенно внимательно проверьте кадры, которые скрипт пометил как `Skipped` — их всё равно нужно либо разметить вручную, либо удалить.

---

### Шаг 4. Добавить auto_labels в датасет (если не сделали в шаге 1)

Если вы скопировали `auto_labels/*` в `captures/` до запуска prelabel — они уже в датасете. Если нет:

```powershell
# Вариант А: скопировать в captures/ и перезапустить prelabel
cp Yolo26/jetcone-model/auto_labels/*.jpg Yolo26/jetcone-model/captures/
cp Yolo26/jetcone-model/auto_labels/*.txt Yolo26/jetcone-model/captures/
python tools/prelabel_jetcone.py

# Вариант Б: скопировать сразу в dataset/train/ (без перегенерации всего датасета)
cp Yolo26/jetcone-model/auto_labels/*.jpg Yolo26/jetcone-model/dataset/train/images/
cp Yolo26/jetcone-model/auto_labels/*.txt Yolo26/jetcone-model/dataset/train/labels/
```

**Внимание:** разметка из auto_labels тоже требует проверки — модель могла ошибиться. Особенно `.txt` от blind/OCR-входов (там только HSV-маска, без core).

---

### Шаг 5. Проверить `data.yaml`

```powershell
type Yolo26\jetcone-model\data.yaml
```

Должно быть:
```yaml
path: dataset
train: train/images
val: val/images
nc: 2
names: ['core', 'jetcone']
```

---

### Шаг 6. Запустить обучение

Все команды запускаются из `EDAPGui/`:

**Первое обучение с нуля (на CPU):**
```powershell
yolo train data=Yolo26/jetcone-model/data.yaml model=Yolo26/jetcone-model/yolo26n.pt epochs=100 patience=30 batch=16 imgsz=640 device=cpu
```

**Первое обучение с нуля (на GPU):**
```powershell
yolo train data=Yolo26/jetcone-model/data.yaml model=Yolo26/jetcone-model/yolo26n.pt epochs=100 patience=30 batch=16 imgsz=640 device=0
```

**Дообучение (fine-tune) существующих весов:**
```powershell
yolo train data=Yolo26/jetcone-model/data.yaml model=Yolo26/jetcone-model/weights/best.pt epochs=50 patience=15 batch=16 imgsz=640 device=0
```

**Параметры:**
| Параметр | Что значит |
|----------|-----------|
| `epochs=100` | Максимум эпох |
| `patience=30` | Остановка, если 30 эпох подряд без улучшения mAP |
| `batch=16` | Кадров за шаг (уменьшить до 8, если падает по памяти) |
| `imgsz=640` | Размер входного изображения |
| `device=0` | GPU #0; `device=cpu` если нет CUDA |

Результаты обучения: `Yolo26/jetcone-model/runs/detect/train/`
- `weights/best.pt` — лучшие веса
- `results.png` — графики всех метрик
- `confusion_matrix.png` — матрица ошибок

---

### Шаг 7. Задеплоить и протестировать

```powershell
# Бэкап текущей модели
cp Yolo26/jetcone-model/weights/best.pt Yolo26/jetcone-model/weights/best.backup.pt

# Новые веса на место
cp Yolo26/jetcone-model/runs/detect/train/weights/best.pt Yolo26/jetcone-model/weights/best.pt
```

Модель подхватится при следующем запуске ED Autopilot. Тестировать:
1. Найти нейтронную звезду, активировать автопилот
2. В логах: `Jet cone detected (conf=..., axis=...)`
3. Если confidence > 0.5 и вход успешен — хорошо
4. Если падает в blind-режим — модель не справляется, нужно больше/качественнее данных

---

## Метрики: на что смотреть в results.png

| Метрика | Хорошо | Нормально | Плохо |
|---------|--------|-----------|-------|
| mAP50 | > 0.85 | 0.70–0.85 | < 0.70 |
| mAP50-95 | > 0.60 | 0.40–0.60 | < 0.40 |
| Precision | > 0.85 | 0.70–0.85 | < 0.70 |
| Recall | > 0.80 | 0.60–0.80 | < 0.60 |

---

## Типичные проблемы

| Проблема | Причина | Решение |
|----------|---------|---------|
| Модель не находит конусы | Мало ракурсов | Добавить кадры под углом |
| Ложные срабатывания на обычных звёздах | Прелейблинг разметил яркий HUD как core | Проверить разметку, удалить FP кадры |
| Низкая confidence | Плохая/неточная разметка | Переразметить проблемные кадры вручную |
| Путает левый/правый конус | Боксы не точно обведены | Поправить bounding boxes |
| Модель «забыла» старые паттерны | Переобучение только на новых данных | Включить старые кадры в датасет |

---

## Шпаргалка (полный цикл одной командой)

```powershell
# 1. Собрать кадры
python tools/jetcone_dataset.py                    # интерактивно
cp Yolo26/jetcone-model/auto_labels/* captures/    # добавить автосбор

# 2. Прелейблинг
python tools/prelabel_jetcone.py

# 3. ПРОВЕРИТЬ РАЗМЕТКУ ВРУЧНУЮ ← не пропускать!

# 4. Обучение
yolo train data=Yolo26/jetcone-model/data.yaml model=Yolo26/jetcone-model/weights/best.pt epochs=50 patience=15 batch=16 imgsz=640 device=0

# 5. Деплой
cp Yolo26/jetcone-model/weights/best.pt Yolo26/jetcone-model/weights/best.backup.pt
cp Yolo26/jetcone-model/runs/detect/train/weights/best.pt Yolo26/jetcone-model/weights/best.pt
```
