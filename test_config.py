import rasterio
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from math import cos, sin, pi, radians
from scipy.ndimage import map_coordinates
from scipy.interpolate import interp1d
import warnings
import sys
import math
warnings.filterwarnings('ignore')

#  КЛАСС ФИЛЬТРА КАЛМАНА 

class KalmanFilter1D:
    def __init__(self, process_noise=0.1, measurement_noise=1.0):
        self.Q = process_noise
        self.R = measurement_noise
        self.x = 0
        self.P = 1
        
    def update(self, z):
        if np.isnan(z):
            return self.x
        x_pred = self.x
        P_pred = self.P + self.Q
        K = P_pred / (P_pred + self.R)
        self.x = x_pred + K * (z - x_pred)
        self.P = (1 - K) * P_pred
        return self.x

def smooth_profile_kalman(values, q_noise=0.05, r_noise=2.0):
    """Применяет фильтр Калмана к массиву значений"""
    kf = KalmanFilter1D(process_noise=q_noise, measurement_noise=r_noise)
    valid_idx = np.where(~np.isnan(values))[0]
    if len(valid_idx) == 0:
        return values
    kf.x = values[valid_idx[0]]
    kf.P = 1.0
    smoothed = np.copy(values)
    for i in range(len(values)):
        if not np.isnan(values[i]):
            smoothed[i] = kf.update(values[i])
        else:
            smoothed[i] = kf.x 
    return smoothed

# == ФУНКЦИИ ЗАГРУЗКИ И ПОДГОТОВКИ == 

def load_altimeter_data(file_path):
    """Загружает данные высот из текстового файла."""
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
        data = [float(line.strip()) for line in lines if line.strip()]
        return np.array(data)
    except Exception as e:
        print(f" Ошибка чтения файла высот {file_path}: {e}")
        sys.exit(1)

def get_profile_values(elevation, center, angle_deg, max_dist_px):
    """Извлекает профиль высот из растра по углу и дистанции в пикселях"""
    center_row, center_col = center
    height, width = elevation.shape
    
    angle_rad = radians(angle_deg)
    dx = cos(angle_rad)
    dy = -sin(angle_rad) 
    
    dist_array_px = np.arange(0, max_dist_px, 1.0) 
    
    rows = center_row + dy * dist_array_px
    cols = center_col + dx * dist_array_px
    
    mask = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
    rows_v = rows[mask]
    cols_v = cols[mask]
    dist_v_px = dist_array_px[mask]
    
    if len(rows_v) < 5:
        return None, None
        
    coords = np.array([rows_v, cols_v])
    values = map_coordinates(elevation, coords, order=1, mode='nearest')
    
    valid = ~np.isnan(values)
    if np.sum(valid) < 5:
        return None, None
        
    return values[valid], dist_v_px[valid]

def calculate_correlation_interp(p1_vals, p1_dist, p2_vals, p2_dist, common_dist):
    """Вычисляет корреляцию через интерполяцию на общую сетку"""
    if p1_vals is None or p2_vals is None:
        return np.nan
    try:
        f1 = interp1d(p1_dist, p1_vals, kind='linear', bounds_error=False, fill_value=np.nan)
        f2 = interp1d(p2_dist, p2_vals, kind='linear', bounds_error=False, fill_value=np.nan)
        
        v1 = f1(common_dist)
        v2 = f2(common_dist)
        
        valid = ~(np.isnan(v1) | np.isnan(v2))
        if np.sum(valid) < 5:
            return np.nan
            
        arr1 = v1[valid]
        arr2 = v2[valid]
        
        if np.std(arr1) == 0 or np.std(arr2) == 0:
            return 0.0
            
        return np.corrcoef(arr1, arr2)[0, 1]
    except:
        return np.nan

# ОСНОВНОЙ АЛГОРИТМ 

def build_hierarchical_match(elevation, start_pixel, ref_heights_raw, pixel_step_m, 
                             coarse_step=10, fine_step=1, corr_threshold=0.3,
                             use_kalman=True, kalman_q=0.1, kalman_r=1.0):
    
    print(f"\n ЗАПУСК ИЕРАРХИЧЕСКОГО ПОИСКА С ФИЛЬТРОМ КАЛМАНА")
    print(f"{'='*60}")
    if use_kalman:
        print(f" Фильтр Калмана: Q={kalman_q}, R={kalman_r}")
    print(f" Шаг дискретизации: {pixel_step_m:.2f} м/замер")
    
    height, width = elevation.shape
    center = start_pixel
    
    max_dist_m = len(ref_heights_raw) * pixel_step_m
    max_dist_px = int(np.ceil(len(ref_heights_raw) * pixel_step_m)) 
    
    max_possible_px = int(np.ceil(max(
        np.sqrt(center[0]**2 + center[1]**2),
        np.sqrt(center[0]**2 + (width - center[1])**2),
        np.sqrt((height - center[0])**2 + center[1]**2),
        np.sqrt((height - center[0])**2 + (width - center[1])**2)
    )))
    max_dist_px = min(max_dist_px, max_possible_px)
    
    common_dist = np.linspace(0, max_dist_px, max_dist_px)
    
    # Подготовка эталона
    if use_kalman:
        ref_smoothed = smooth_profile_kalman(ref_heights_raw, kalman_q, kalman_r)
    else:
        ref_smoothed = ref_heights_raw
        
    ref_dists = np.arange(len(ref_smoothed)) * pixel_step_m 
    
    if len(ref_dists) > max_dist_px:
        ref_smoothed = ref_smoothed[:max_dist_px]
        ref_dists = ref_dists[:max_dist_px]

    print(f" Эталон подготовлен: {len(ref_smoothed)} точек, длина {ref_dists[-1]:.1f} ед.")

    # Шаг 1: Грубый поиск
    coarse_angles = list(range(0, 360, coarse_step))
    candidates = []
    coarse_corrs = {}
    
    print(f" Шаг 1: Грубое сканирование...")
    
    for angle in coarse_angles:
        vals_raw, dist_px = get_profile_values(elevation, center, angle, max_dist_px)
        if vals_raw is None: continue
        
        if use_kalman:
            vals_smooth = smooth_profile_kalman(vals_raw, kalman_q, kalman_r)
        else:
            vals_smooth = vals_raw
            
        corr = calculate_correlation_interp(vals_smooth, dist_px, ref_smoothed, ref_dists, common_dist)
        coarse_corrs[angle] = corr
        
        if not np.isnan(corr) and corr > corr_threshold:
            candidates.append(angle)
            
    print(f"   Найдено {len(candidates)} перспективных секторов (корреляция > {corr_threshold})")
    
    # Шаг 2: Детальное изучение
    final_profiles = {}
    final_corrs = {}
    
    print(f" Шаг 2: Детализация кандидатов...")
    
    processed_sectors = set()
    
    for cand_angle in candidates:
        start_a = cand_angle - coarse_step // 2
        end_a = cand_angle + coarse_step // 2
        sector_angles = np.arange(start_a, end_a + fine_step, fine_step)
        
        for angle in sector_angles:
            norm_angle = int(angle % 360)
            if norm_angle in processed_sectors:
                continue
            processed_sectors.add(norm_angle)
            
            vals_raw, dist_px = get_profile_values(elevation, center, angle, max_dist_px)
            if vals_raw is None: continue
            
            if use_kalman:
                vals_smooth = smooth_profile_kalman(vals_raw, kalman_q, kalman_r)
            else:
                vals_smooth = vals_raw
                
            corr = calculate_correlation_interp(vals_smooth, dist_px, ref_smoothed, ref_dists, common_dist)
            
            if not np.isnan(corr):
                final_corrs[norm_angle] = corr
                final_profiles[norm_angle] = (vals_smooth, dist_px)
                
    all_correlations = np.full(360, np.nan)
    for ang, corr in final_corrs.items():
        all_correlations[ang] = corr
    for ang, corr in coarse_corrs.items():
        if np.isnan(all_correlations[ang]):
            all_correlations[ang] = corr
            
    print(f" Расчет завершен. Точных профилей: {len(final_profiles)}")
    
    return {
        'elevation': elevation,
        'center': center,
        'correlations': all_correlations,
        'profiles': final_profiles,
        'reference_profile': {'values': ref_smoothed, 'distances': ref_dists},
        'use_kalman': use_kalman,
        'kalman_params': {'Q': kalman_q, 'R': kalman_r}
    }

# НОВАЯ ФУНКЦИЯ: РАСЧЕТ КООРДИНАТ ТРАЕКТОРИИ 

def calculate_trajectory_coordinates(src, start_pixel, best_angle, profile_data, pixel_step_m):
    """
    Рассчитывает глобальные и локальные координаты для лучшей траектории.
    
    :param src: объект rasterio dataset (для transform)
    :param start_pixel: (row, col)
    :param best_angle: угол в градусах
    :param profile_data: кортеж (values, dists_px)
    :param pixel_step_m: масштабный коэффициент (м/ед)
    :return: список строк с координатами
    """
    start_row, start_col = start_pixel
    vals, dists_px = profile_data
    
    # Преобразование угла
    angle_rad = radians(best_angle)
    dx = cos(angle_rad)
    dy = -sin(angle_rad)
    
    # Получаем transform из растра
    transform = src.transform
    
    trajectory_lines = []
    # Заголовок (опционально, можно убрать если нужен чистый массив)
    # trajectory_lines.append("Index,Local_Dist_m,Height_m,Global_X,Global_Y")
    
    for i in range(len(vals)):
        d_px = dists_px[i]
        h = vals[i]
        
        # Локальные координаты (смещение от старта в пикселях)
        local_row = start_row + dy * d_px
        local_col = start_col + dx * d_px
        
        # Глобальные координаты (X, Y) через transform
        # rasterio.transform.xy принимает row, col
        global_x, global_y = rasterio.transform.xy(transform, local_row, local_col)
        
        # Локальная дистанция в метрах (приблизительно, если pixel_step_m согласован с метрами)
        # Или просто используем d_px * pixel_step_m если это физический шаг
        local_dist_m = d_px * pixel_step_m 
        
        # Формируем строку вывода: X Y Height LocalDist
        # Или более подробно:
        line = f"{global_x:.6f} {global_y:.6f} {h:.2f} {local_dist_m:.2f}"
        trajectory_lines.append(line)
        
    return trajectory_lines

# == ОТЧЕТЫ И ВИЗУАЛИЗАЦИЯ == 

def print_analysis_report(data):
    correlations = data['correlations']
    valid_corr = correlations[~np.isnan(correlations)]
    
    if len(valid_corr) == 0:
        print("\n Нет совпадений с заданным порогом.")
        return

    print("\n" + "="*60)
    print(" ОТЧЕТ СРАВНЕНИЯ С РАДИОВЫСОТОМЕРОМ")
    print("="*60)
    
    print(f"\n1.  СТАТИСТИКА КОРРЕЛЯЦИИ:")
    print(f"   Среднее: {np.mean(valid_corr):.4f}")
    print(f"   Максимум: {np.max(valid_corr):.4f}")
    
    sorted_indices = np.argsort(-correlations)
    print(f"\n2.  ЛУЧШИЕ НАПРАВЛЕНИЯ СОВПАДЕНИЯ:")
    count = 0
    for idx in sorted_indices:
        if np.isnan(correlations[idx]): continue
        print(f"   Угол: {idx:>3}° | Корреляция: {correlations[idx]:.4f}")
        count += 1
        if count >= 3: break
        
    print(f"\n3.  ПАРАМЕТРЫ:")
    print(f"   Фильтр Калмана: {'ВКЛ' if data['use_kalman'] else 'ВЫКЛ'}")
    print("="*60 + "\n")

def plot_results(data, output_png='drone_kalman_result.png'):
    elevation = data['elevation']
    center = data['center']
    correlations = data['correlations']
    profiles = data['profiles']
    ref_prof = data['reference_profile']
    
    height, width = elevation.shape
    cr, cc = center
    
    fig = plt.figure(figsize=(18, 6))
    
    # Подготовка цветовой шкалы
    corr_min = np.nanmin(correlations)
    corr_max = np.nanmax(correlations)
    norm = Normalize(vmin=corr_min, vmax=corr_max)
    cmap = plt.cm.RdBu_r
    
    # Находим топ углов для отрисовки
    sorted_ang = np.argsort(-correlations)
    top_angles = [a for a in sorted_ang if not np.isnan(correlations[a])][:10]
    
    # == 1. КАРТА С ЛУЧАМИ ==
    ax1 = fig.add_subplot(131)
    im = ax1.imshow(elevation, cmap='terrain', aspect='equal')
    
    for angle in top_angles:
        #  ИСПРАВЛЕННАЯ ФОРМУЛА ДЛЯ АЗИМУТОВ 
        # Азимут: 0=Север, 90=Восток. 
        # В массиве изображения: Row уменьшается вверх (Север), Col увеличивается вправо (Восток).
        
        az_rad = radians(angle)
        
        # Смещение по колонкам (Восток) = sin(азимут)
        d_col = math.sin(az_rad)
        
        # Смещение по строкам (Север) = -cos(азимут). 
        # Минус нужен, потому что индекс строки растет ВНИЗ, а Север это ВВЕРХ.
        d_row = -math.cos(az_rad) 
        
        # Длина луча
        if angle in profiles:
            _, dists = profiles[angle]
            max_d = dists[-1] if len(dists) > 0 else 100
        else:
            max_d = 100
            
        end_col = cc + d_col * max_d
        end_row = cr + d_row * max_d
        
        ax1.plot([cc, end_col], [cr, end_row], color=cmap(norm(correlations[angle])), linewidth=2, alpha=0.8)
                
    ax1.plot(cc, cr, 'wo', markersize=8, label='Старт')
    ax1.set_title(f"Лучшие совпадения направлений\n(0°=Север)")
    ax1.legend()
    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    plt.colorbar(sm, ax=ax1, label='Корреляция')
    
    # == 2. ПОЛЯРНАЯ ДИАГРАММА ==
    ax2 = fig.add_subplot(132, projection='polar')
    
    theta = np.deg2rad(np.arange(360))
    r = np.ones(360)
    colors = []
    for c in correlations:
        if np.isnan(c):
            colors.append((0.5, 0.5, 0.5, 0.1))
        else:
            colors.append(cmap(norm(c)))
            
    ax2.bar(theta, r, width=2*pi/360, color=colors, edgecolor='none')
    
    # Настройки полярной системы под азимуты
    ax2.set_theta_zero_location('N')  # 0 градусов сверху
    ax2.set_theta_direction(-1)       # Отсчет по часовой стрелке
    ax2.set_title("Карта корреляции (360°)")
    
    # == 3. ГРАФИК ПРОФИЛЯ ==
    ax3 = fig.add_subplot(133)
    best_angle = sorted_ang[0]
    
    if best_angle in profiles:
        map_vals, map_dists = profiles[best_angle]
        ax3.plot(map_dists, map_vals, 'r-', linewidth=2, label=f'Карта (Азимут {best_angle}°)')
        
    ax3.plot(ref_prof['distances'], ref_prof['values'], 'b--', linewidth=2, label='Данные высотомера')
    
    ax3.set_xlabel('Дистанция')
    ax3.set_ylabel('Высота')
    ax3.set_title('Сравнение профилей')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_png, dpi=150, bbox_inches='tight')
    print(f" График сохранен: {output_png}")
    plt.show()

# ГЛАВНЫЙ БЛОК

if __name__ == "__main__":
    print("="*60)
    print(" СИСТЕМА НАВИГАЦИИ")
    print("="*60)
    
    # 1. Ввод путей
    geotiff_path = input("Путь к рельефу (.tif) [example.tif]: ").strip() or 'example.tif'
    heights_txt_path = input("Путь к высотам (.txt) [qwe.txt]: ").strip() or 'qwe.txt'

    # 2. Информация о карте и ввод координат
    try:
        # Открываем для получения инфо, но потом закроем и откроем снова для чтения данных
        with rasterio.open(geotiff_path) as src_info:
            bounds = src_info.bounds
            center_x = (bounds.left + bounds.right) / 2
            center_y = (bounds.bottom + bounds.top) / 2
            
            print(f"\n КАРТА: X[{bounds.left:.2f}..{bounds.right:.2f}], Y[{bounds.bottom:.2f}..{bounds.top:.2f}]")
            
            input_x = input(f"Координата X (Enter={center_x:.4f}): ").strip()
            geo_x = float(input_x) if input_x else center_x
            
            input_y = input(f"Координата Y (Enter={center_y:.4f}): ").strip()
            geo_y = float(input_y) if input_y else center_y
            
            drone_speed = float(input("Скорость дрона (м/с) [10]: ") or "10")
            radio_freq = float(input("Частота высотомера (Гц) [10]: ") or "10")
            
            pixel_step_m = drone_speed / radio_freq
            print(f" Шаг дискретизации данных: {pixel_step_m:.2f} м")

    except Exception as e:
        print(f" Ошибка инициализации: {e}")
        sys.exit(1)

    # 3. Загрузка данных и выполнение
    print("\n Загрузка и обработка...")
    alimeter_data = load_altimeter_data(heights_txt_path)
    
    try:
        with rasterio.open(geotiff_path) as src:
            elevation = src.read(1).astype(float)
            if src.nodata is not None:
                elevation[elevation == src.nodata] = np.nan
                
            try:
                start_row, start_col = src.index(geo_x, geo_y)
            except:
                print(" Координаты вне карты!")
                sys.exit(1)
                
            print(f" Старт: Пиксель({start_row}, {start_col})")
            print(f" Исходная точка (гео): X={geo_x}, Y={geo_y}")
            
            # 4. Запуск алгоритма
            data = build_hierarchical_match(
                elevation=elevation,
                start_pixel=(start_row, start_col),
                ref_heights_raw=alimeter_data,
                pixel_step_m=pixel_step_m,
                coarse_step=10,
                fine_step=1,
                corr_threshold=0.3,
                use_kalman=True,
                kalman_q=0.1,
                kalman_r=2.0
            )
            
            # 5. Вывод результатов анализа
            print_analysis_report(data)
            
            # 6.  ВЫВОД ТРАЕКТОРИИ (Глобальные и Локальные координаты) 
            correlations = data['correlations']
            sorted_indices = np.argsort(-correlations)
            best_angle = sorted_indices[0]
            
            if best_angle in data['profiles']:
                print(f"\n ТРАЕКТОРИЯ ДВИЖЕНИЯ (Лучший азимут: {best_angle}°)")
                print(f"{'='*60}")
                print("Формат: Global_X Global_Y Height_m Local_Dist_m")
                
                profile_vals, profile_dists = data['profiles'][best_angle]
                
                # Рассчитываем координаты
                trajectory_lines = calculate_trajectory_coordinates(
                    src=src,
                    start_pixel=(start_row, start_col),
                    best_angle=best_angle,
                    profile_data=(profile_vals, profile_dists),
                    pixel_step_m=pixel_step_m
                )
                
                # Вывод в консоль (одномерный массив, разделенный строками)
                for line in trajectory_lines:
                    print(line)
                    
                # Опционально: сохранение в файл
                # with open('trajectory_output.txt', 'w') as f:
                #     f.write('\n'.join(trajectory_lines))
                # print(" Траектория сохранена в trajectory_output.txt")
                
            else:
                print(" Не удалось построить траекторию для лучшего угла.")

            # 7. Визуализация
            plot_results(data)
            
    except Exception as e:
        print(f" Ошибка выполнения: {e}")
        import traceback
        traceback.print_exc()
