# Инструкция по дообучению модели jetcone (YOLOv26)

## Обзор

Модель `jetcone-model` — YOLOv26 nano, 2 класса:
- `0: core` — яркое ядро нейтронной звезды / белого карлика
- `1: jet` — плазменный конус (джет)

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
- `tools/jetcone_dataset.py` — сбор сырых кадров (3 режима: интерактив, локальное видео, YouTube)
- `tools/prelabel_jetcone.py` — HSV-авторазметка кадров из `captures/` → `dataset/`
- `tools/auto_label_jetcone.py` — **доразметка обученной моделью** (best.pt) всех train-изображений
- `tools/predict_all.py` — переразметка всех кадров моделью (замена HSV-лейблов)
- `tools/auto_label2.py` — разметка моделью только непромаркированных кадров в `unlabeled/`
- `tools/yolo_bbox_editor/` — **GUI-редактор боксов** (свой, не нужно ставить LabelImg)

---

## Полный цикл дообучения (6 шагов)

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

   **Детекция jet (класс 1):**
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

### Шаг 2.5. Доразметить обученной моделью

HSV-прелейблинг ловит яркие конусы, но пропускает тусклые/дальние. Обученная модель (`weights/best.pt`, mAP50 ≈ 0.72) находит то, что HSV пропустил:

```powershell
python tools/auto_label_jetcone.py
```

**Что делает:** прогоняет `best.pt` по ВСЕМ train-изображениям и перезаписывает лейблы там, где модель уверена (conf ≥ 0.5). HSV-лейблы на кадрах, где модель ничего не нашла, остаются без изменений.

**Альтернативные скрипты:**

| Скрипт | Когда использовать |
|--------|-------------------|
| `auto_label_jetcone.py` | После prelabel — доразметить моделью все train-кадры |
| `predict_all.py` | Полностью заменить ВСЕ лейблы на модельные (сбросить HSV) |
| `auto_label2.py` | Разметить только кадры без лейблов (положить в `dataset/train/unlabeled/`) |

**Типичный результат после HSV + модели:**
```
TRAIN: 286 img | 239 lbl | 47 без лейблов   ← кадры без джета (дальний полёт)
VAL:    89 img |  64 lbl | 25 без лейблов
```
Кадры без лейблов — кандидаты на удаление из датасета (нет объекта для детекции).

---

### Шаг 3. Проверить и поправить разметку (yolo_bbox_editor)

**Это самый важный шаг.** И HSV, и модель ошибаются. Используйте встроенный редактор:

```powershell
# Из корня EDAPGui:
tools\yolo_bbox_editor\run_bbox_editor.bat
```

**Интерфейс редактора:**

| Действие | Как |
|----------|-----|
| Открыть датасет | «Open Folder» → выбрать `dataset/train/` (авточитает `data.yaml` для имён классов) |
| Навигация | `A` / `D` или кнопки «◀ Prev» / «Next ▶» |
| Новый бокс | ЛКМ по пустому месту — растянуть прямоугольник |
| Переместить бокс | Зажать и тащить (внутри бокса, не за край) |
| Resize бокса | Тянуть за край/угол (8 направлений) |
| Сменить класс | Выделить бокс → цифра `0` (core) или `1` (jet) |
| Удалить бокс | Выделить → `Delete` |
| Удалить все | Кнопка «Del All» |
| Зум | `Ctrl+Колесо` или кнопки «Zoom ±» / «100%» / «Fit» |
| Пан | `Пробел+ЛКМ` или средняя кнопка мыши |
| Сохранить | `Ctrl+S` или кнопка «Save» (автосохраняется при переходе к след. кадру) |

**Что проверять на КАЖДОМ кадре:**

| Проверка | Действие |
|----------|----------|
| Core (класс 0) — бокс точно вокруг яркого центра? | Поправить/перерисовать |
| Jet (класс 1) — бокс охватывает ВЕСЬ видимый конус? | Поправить/перерисовать |
| Два конуса видны — оба размечены как класс 1? | Добавить второй бокс |
| На кадре вообще нет конуса? | Удалить `.jpg` и `.txt` из папки |
| Бокс захватил HUD или другие объекты? | Поправить |
| Core и jet пересекаются? | Разнести — они должны быть отдельными боксами |

---

### Шаг 4. Проверить `data.yaml`

```powershell
type Yolo26\jetcone-model\data.yaml
```

Должно быть:
```yaml
path: C:/Users/nafan/Documents/ED Autopilot/EDAPGui/Yolo26/jetcone-model/dataset
train: train/images
val: val/images
nc: 2
names: ['core', 'jet']
```

---

### Шаг 5. Запустить обучение

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

### Шаг 6. Задеплоить и протестировать

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
python tools/jetcone_dataset.py                              # интерактивно
python tools/jetcone_dataset.py "clip.mp4"                   # или из видео
cp Yolo26/jetcone-model/auto_labels/* captures/              # добавить автосбор

# 2. HSV-прелейблинг
python tools/prelabel_jetcone.py

# 3. Доразметка моделью
python tools/auto_label_jetcone.py

# 4. ПРОВЕРИТЬ РАЗМЕТКУ ВРУЧНУЮ ← не пропускать!
tools\yolo_bbox_editor\run_bbox_editor.bat
#   Open Folder → выбрать dataset/train/
#   A/D — навигация, ЛКМ — новый бокс, 0/1 — класс, Delete — удалить, Ctrl+S — сохранить

# 5. Обучение
yolo train data=Yolo26/jetcone-model/data.yaml model=Yolo26/jetcone-model/weights/best.pt epochs=50 patience=15 batch=16 imgsz=640 device=0

# 6. Деплой
cp Yolo26/jetcone-model/weights/best.pt Yolo26/jetcone-model/weights/best.backup.pt
cp Yolo26/jetcone-model/runs/detect/train/weights/best.pt Yolo26/jetcone-model/weights/best.pt
```
