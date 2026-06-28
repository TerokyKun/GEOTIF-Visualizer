# KENS — Correlation Extreme Navigation System

**Поисковая рельефометрическая КЭНС** — система коррекции инерциальной навигации (INS) на основе сопоставления рельефа местности с цифровой моделью рельефа (DEM).

---

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────┐
│                    C++ ЯДРО (10 Гц)                         │
│                                                             │
│  INS измерение ──→ ΔH_изм ──→ KENS поиск ──→ EKF ──→ SHM  │
│       │                │            │            │      │    │
│       │           DEM окно     коррекция    позиции   │    │
│       │           A(i,j)      позиции               │    │
│       ▼                ▼            ▼            ▼      ▼    │
│  ┌─────────┐    ┌──────────┐  ┌──────────┐  ┌─────┐  ┌──┐ │
│  │ INS Proc│    │ RV integ │  │ KENS Eng │  │ EKF │  │SM│ │
│  └─────────┘    └──────────┘  └──────────┘  └─────┘  └──┘ │
└─────────────────────────────────────────────────────────────┘
                         │ shared memory (kens_shm)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│           C# WPF ВИЗУАЛИЗАТОР (.NET 8, Windows)            │
│  ┌──────────────────┐  ┌──────────────────────────────┐    │
│  │ Terrain Map       │  │ Telemetry Dashboard          │    │
│  │ + Trajectories    │  │ INS / KENS / EKF / DEM Info  │    │
│  │ + Drone marker    │  │                              │    │
│  └──────────────────┘  └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Где реализован алгоритм (директории)

```
cpp_core/
├── include/
│   ├── math/types.h                    ← базовые типы: InsState, EfkState, KensParams, PipelineOutput
│   ├── math/simd_math.h               ← SIMD: матричные операции N×N, AVX2 корреляция
│   ├── dem/dem_engine.h               ← загрузчик GeoTIFF через GDAL, getElevation(), getWindow()
│   ├── ins/ins_processor.h            ← обработка INS, вычисление ΔH_изм из РВ
│   ├── kens/kens_engine.h             ← ядро КЭНС: корреляционный поиск A(i,j), валидация
│   ├── ekf/extended_kalman_filter.h   ← 7-мерный EKF: [X,Y,Vx,Vy,bias_ax,bias_ay,bias_alt]
│   ├── ipc/shared_memory.h            ← IPC: Win32 CreateFileMapping / POSIX shm_open
│   └── pipeline/kens_pipeline.h       ← оркестратор: цикл INS→KENS→EKF→SHM
│
└── src/
    ├── dem/dem_engine.cpp             ← GDAL: GDALOpen, GDALRasterIO, полная загрузка растра
    ├── ins/ins_processor.cpp          ← ΔH_изм = HRV(k) − HRV(k−1) − Wζ·Δt
    ├── kens/kens_engine.cpp           ← КОРРЕЛЯЦИЯ: A(i,j) = Σ(map−ref)², argmin, Lp, σ
    ├── ekf/extended_kalman_filter.cpp ← predict(dt), update(KENS 2D), updateRV(1D)
    ├── ipc/shared_memory.cpp          ← маппинг памяти: запись/чтение PipelineOutput
    ├── pipeline/kens_pipeline.cpp     ← оркестратор: извлечение DEM-шаблона, вызов КЭНС
    └── main.cpp                       ← демонстрация: генерация INS+RV траектории

csharp_viz/
├── Models/SharedMemoryLayout.cs       ← маппинг SharedMemoryLayout (Pack=1, точно как C++)
├── Services/SharedMemoryReader.cs     ← чтение kens_shm + фоновый опрос TelemetryPoller
├── Services/DemoSimulator.cs          ← генератор тестовых данных без C++ ядра
├── ViewModels/MainViewModel.cs        ← MVVM ViewModel: INS/KENS/EKF свойства + траектории
├── MainWindow.xaml                    ← UI: Canvas (карта+траектории) + Dashboard (телеметрия)
├── MainWindow.xaml.cs                 ← отрисовка: LoadTerrainImage, W2S конвертация, DrawPolyline
└── BoolToBrushConverter.cs            ← конвертер bool → Brush
```

---

## Шаги работы алгоритма

```
Шаг 1. Загрузка DEM (GDAL)
  ├─ GDALAllRegister() → GDALOpen(path, GA_ReadOnly)
  ├─ GDALGetRasterXSize / YSize → размер растра
  ├─ GDALGetGeoTransform → origin_x, origin_y, pixel_w, pixel_h
  └─ GDALRasterIO(GF_Read) → полный растр в память (float32)

Шаг 2. Получение данных INS + РВ (каждые 100мс)
  ├─ INS: позиция (X_north, Y_east), скорость (Vx, Vy), курс
  └─ РВ: высота AGL (HRV), скорость изменения высоты (Wζ)

Шаг 3. Вычисление ΔH_изм
  └─ ΔH_изм = HRV(k) − HRV(k−1) − Wζ·Δt

Шаг 4. EKF Predict (каждый шаг)
  ├─ x += Vx·dt, y += Vy·dt
  └─ P = F·P·F' + Q

Шаг 5. Корреляционный поиск КЭНС (каждые 3 шага)
  ├─ 5a. Извлечь окно DEM 8×8 вокруг позиции INS → ref_block (эталонный шаблон)
  ├─ 5b. Извлечь окно DEM 64×64 (поиск) → dem_window
  ├─ 5c. Для каждой гипотезы (i,j):
  │       A(i,j) = Σ (dem_window[i+bi,j+bj] − ref_block[bi,bj])²
  ├─ 5d. Найти argmin A(i,j) → лучшая гипотеза
  ├─ 5e. Вычислить σ_рельефа (средний градиент DEM)
  ├─ 5f. Вычислить σ_Σ = √(σ_к² + σ_п² + σ_РВ²)
  ├─ 5g. Вычислить Lp = 1 − (A_min / A_second_min)
  └─ 5h. Валидация: dh < порог, σ_рельефа/σ_Σ > 0.1, Lp > 0.01

Шаг 6. EKF Update (если KENS valid)
  ├─ z = [X_kens, Y_kens] (2D позиция)
  └─ K = P·H'·(H·P·H'+R)⁻¹, x += K·(z − H·x)

Шаг 7. EKF UpdateRV (каждый шаг)
  ├─ z = [dh_measured] (1D высота)
  └─ Коррекция bias_alt

Шаг 8. Запись в shared memory → C# визуализатор
  ├─ SharedMemoryLayout (Pack=1, ~250 байт)
  └─ Поля: INS, KENS, EKF, DEM метаданные
```

---

## Зависимости для сборки

### C++ ядро (MSYS2 MinGW64)

| Пакет | Установка (MSYS2 MinGW64 Shell) | Назначение |
|-------|--------------------------------|------------|
| **GDAL** | `pacman -S mingw-w64-x86_64-gdal` | Загрузка GeoTIFF (.tif) через GDAL |
| **CMake** | `pacman -S mingw-w64-x86_64-cmake` | Система сборки |
| **GCC** | `pacman -S mingw-w64-x86_64-gcc` | Компилятор C++17 |
| **Make** | `pacman -S mingw-w64-x86_64-make` | GNU Make |

Установка всех пакетов одной командой (MSYS2 MinGW64 Shell):
```bash
pacman -S mingw-w64-x86_64-gdal mingw-w64-x86_64-cmake mingw-w64-x86_64-gcc mingw-w64-x86_64-make
```

### C# визуализатор (Windows cmd / PowerShell)

| Зависимость | Установка | Назначение |
|-------------|-----------|------------|
| **.NET 8 SDK** | `winget install Microsoft.DotNet.SDK.8` или https://dotnet.microsoft.com/download/dotnet/8.0 | Компилятор C# |

Дополнительные NuGet-пакеты не требуются — проект использует только WPF (встроен в .NET 8 Windows).

---

## Сборка

### C++ (MSYS2 MinGW64 Shell)

```bash
cd cpp_core
mkdir -p build && cd build
cmake .. -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(nproc)
```

### C++ (Windows cmd, если MSYS2 в PATH)

```cmd
cd cpp_core
mkdir build && cd build
cmake .. -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build . -j%NUMBER_OF_PROCESSORS%
```

### C# (Windows cmd / PowerShell)

```cmd
cd csharp_viz
dotnet restore
dotnet build -c Release
```

---

## Запуск

### Вручную

**Терминал 1** — C++ ядро:
```cmd
cd cpp_core\build\bin
kens_main.exe "..\..\..\output_be.tif"
```

**Терминал 2** — C# визуализатор:
```cmd
cd csharp_viz
dotnet run -c Release
```

### Скриптами

```cmd
REM Из cmd:
run.bat
```

```bash
# Из MSYS2 MinGW64 Shell:
bash run.sh
```

### Демо-режим (без C++ ядра)

```cmd
cd csharp_viz\bin\Release\net8.0-windows
KensVisualizer.exe
```
Запускает DemoSimulator, который генерирует синтетические данные в shared memory.

---

## Структура файлов

```
kens_system/
├── run.bat                         ← запуск (Windows cmd)
├── run.sh                          ← запуск (MSYS2/Linux)
├── output_be.tif                   ← DEM (GeoTIFF) — цифровая модель рельефа
├── README.md
│
├── cpp_core/                       ← C++ ядро (GDAL + SIMD + EKF)
│   ├── CMakeLists.txt
│   ├── build.bat / build.sh
│   ├── include/                    ← заголовочные файлы
│   └── src/                        ← исходный код
│
└── csharp_viz/                     ← C# визуализатор (WPF, .NET 8)
    ├── KensVisualizer.csproj
    ├── App.xaml / App.xaml.cs
    ├── MainWindow.xaml             ← UI: карта + телеметрия
    ├── MainWindow.xaml.cs          ← отрисовка траекторий на Canvas
    ├── BoolToBrushConverter.cs
    ├── Models/
    │   └── SharedMemoryLayout.cs   ← маппинг shared memory (Pack=1)
    ├── Services/
    │   ├── SharedMemoryReader.cs   ← чтение kens_shm
    │   └── DemoSimulator.cs        ← демо-генератор данных
    └── ViewModels/
        └── MainViewModel.cs        ← MVVM привязки
```

---

## Формат вывода C++ ядра

```
[MAIN] t=26.4 INS=(5002.3,5001.1) EKF=(5002.1,5001.0) KENS=VALID dH=0.05 sigma_r=0.83
[KENS] Match: (32,33) delta=(1,-1) corr=1.23e+04 sigma_r=0.83 lp=0.15 valid=1
```

| Поле | Описание |
|------|----------|
| `t` | Время, сек |
| `INS=(X,Y)` | Позиция INS: North (м), East (м) |
| `EKF=(X,Y)` | Оценка EKF |
| `KENS` | `VALID` = коррекция принята, `NONE` = нет совпадения |
| `dH` | ΔH_изм = HRV(k)−HRV(k−1)−Wζ·Δt |
| `sigma_r` | σ_рельефа/σ_Σ |
| `Match (i,j)` | Индекс минимума A(i,j) |
| `delta=(dX,dY)` | Коррекция позиции (North, East), м |
| `lp` | Local Peak prominence (выразительность пика) |

---

## Система координат

- **North (X)** — ось X направлена на север, метры от начала координат DEM
- **East (Y)** — ось Y направлена на восток, метры
- **pixel_h < 0** — растр north-up (первая строка = север), поэтому North уменьшается вниз по растрю
- **World → Screen**: `col = (east - originX) / |pixelW|`, `row = (north - originY) / pixelH`

---

## Визуализация DEM (карта)

WPF не умеет отображать float32 GeoTIFF как изображение. Для отображения рельефа на карте конвертируйте GeoTIFF в PNG:

```bash
# Python (GDAL):
gdal_translate -of PNG -scale output_be.tif output_be.png
```

Если PNG файл рядом с `output_be.tif`, визуализатор загрузит его как фон карты.
Без PNG визуализатор работает с чёрным фоном — траектории и маркеры отображаются корректно.

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `GDAL not found` | `pacman -S mingw-w64-x86_64-gdal` |
| `Could NOT find GDAL` | cmake ищет GDAL в MSYS2. Убедитесь что пакет установлен. |
| `KENS=NONE` всегда | DEM слишком плоский. Снизьте `lp_threshold`, `sigma_ratio_min`. |
| `EKF=(0,0)` | EKF не инициализирован. Проверьте что INS позиция внутри DEM. |
| C# `Unable to open shared memory` | Сначала запустить C++ ядро. |
| C# `dotnet: command not found` | Установить .NET 8 SDK: https://dotnet.microsoft.com/download/dotnet/8.0 |
| C# белый экран | Убедитесь что `output_be.tif` доступен и C++ ядро запущено. |
