import sys
import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path

# =====================================================
# Путь к библиотекам (для сборки в один EXE)
# =====================================================
def get_library_path():
    """Возвращает путь к папке library."""
    if getattr(sys, 'frozen', False):
        # Запуск из EXE: библиотеки внутри _MEIPASS
        return Path(sys._MEIPASS) / 'library'
    else:
        # Запуск из исходного кода: библиотеки в ../library
        return Path(__file__).resolve().parent.parent / 'library'

# Путь к library
library_path = get_library_path()
sys.path.insert(0, str(library_path))

# Пути к sdk и driver (для работы внутри EXE)
if getattr(sys, 'frozen', False):
    sdk_path = Path(sys._MEIPASS) / 'sdk'
    driver_path = Path(sys._MEIPASS) / 'driver'
else:
    sdk_path = Path(__file__).resolve().parent.parent / 'sdk'
    driver_path = Path(__file__).resolve().parent.parent / 'driver'

# Импорты библиотек
from chromator import Chromator
from laser_source import LaserSource
from oscilloscope import Oscilloscope
from powermeter import Powermeter


print(f"MEIPASS: {sys._MEIPASS if getattr(sys, 'frozen', False) else 'Not frozen'}")
print(f"Library path: {library_path}")
print(f"Exists: {library_path.exists()}")


class DeviceManager:
    """Полноценный менеджер управления всем оборудованием."""

    def __init__(self):
        # Путь к иконке (для EXE)
        if getattr(sys, "frozen", False):
            self.base_path = Path(sys._MEIPASS)
        else:
            self.base_path = Path(__file__).parent

        # Объекты устройств
        self.chromator_device = None
        self.laser_source_device = None
        self.oscilloscope_device = None
        self.powermeter_device = None

        # Флаги подключения
        self.chromator_connected = False
        self.laser_connected = False
        self.oscilloscope_connected = False
        self.powermeter_connected = False

        # Управление потоками
        self.auto_update_enabled = True
        self.status_timer = None
        self.operation_lock = threading.Lock()

        # GUI
        self.root_window = None
        self.status_labels = {}
        self.control_buttons = {"chromator": [], "laser": [], "oscilloscope": [], "powermeter": []}

    # =====================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =====================================================

    def _safe_widget_config(self, widget, **kwargs):
        """Безопасное изменение состояния виджета с обработкой ошибок."""
        try:
            if widget and widget.winfo_exists():
                widget.config(**kwargs)
        except Exception:
            pass

    def _safe_label_config(self, label, text=None, foreground=None):
        """Безопасное обновление текста метки."""
        try:
            if label and label.winfo_exists():
                if text is not None:
                    label.config(text=text)
                if foreground is not None:
                    label.config(foreground=foreground)
        except Exception:
            pass

    def _safe_command(self, func, *args, **kwargs):
        """Безопасный вызов функции с подавлением ошибок."""
        try:
            return func(*args, **kwargs)
        except Exception:
            return None

    def _set_buttons_state(self, button_list, state):
        """Установка состояния группы кнопок."""
        for btn in button_list:
            self._safe_widget_config(btn, state=state)

    # =====================================================
    # ОБНОВЛЕНИЕ СТАТУСА (многопоточное)
    # =====================================================

    def update_chromator_status(self):
        """Обновление статуса монохроматора."""
        if not self.chromator_connected or not self.chromator_device:
            self._safe_label_config(self.status_labels.get("chromator_wavelength"), text="--- нм")
            self._safe_label_config(self.status_labels.get("chromator_input_slit"), text="--- мкм")
            self._safe_label_config(self.status_labels.get("chromator_output_slit"), text="--- мкм")
            self._safe_label_config(self.status_labels.get("chromator_shutter"), text="---", foreground="black")
            self._safe_label_config(self.status_labels.get("chromator_grating"), text="-")
            self._safe_label_config(self.status_labels.get("chromator_grating_count"), text="0")
            return

        try:
            # Длина волны
            wl = self.chromator_device.get_wavelength()
            self._safe_label_config(self.status_labels.get("chromator_wavelength"), text=f"{wl:.2f} нм")

            # Щели
            slit_count = self.chromator_device.get_slit_count()
            if slit_count > 0:
                input_w = self.chromator_device.get_slit_width(0)
                self._safe_label_config(self.status_labels.get("chromator_input_slit"), text=f"{input_w:.2f} мкм")
            if slit_count > 1:
                output_w = self.chromator_device.get_slit_width(1)
                self._safe_label_config(self.status_labels.get("chromator_output_slit"), text=f"{output_w:.2f} мкм")

            # Затвор
            shutter = self.chromator_device.get_shutter_state(0)
            if shutter == 1:
                self._safe_label_config(self.status_labels.get("chromator_shutter"), text="Открыт", foreground="green")
            else:
                self._safe_label_config(self.status_labels.get("chromator_shutter"), text="Закрыт", foreground="red")

            # Решётки
            grating = self.chromator_device.get_active_grating()
            self._safe_label_config(self.status_labels.get("chromator_grating"), text=str(grating))
            grating_count = self.chromator_device.get_grating_count()
            self._safe_label_config(self.status_labels.get("chromator_grating_count"), text=str(grating_count))
        except Exception:
            pass

    def update_laser_status(self):
        """Обновление статуса лазера."""
        if not self.laser_connected or not self.laser_source_device:
            self._safe_label_config(self.status_labels.get("laser_wavelength"), text="--- нм")
            self._safe_label_config(self.status_labels.get("laser_position"), text="---")
            self._safe_label_config(self.status_labels.get("laser_speed"), text="---")
            self._safe_label_config(self.status_labels.get("laser_motor"), text="---", foreground="black")
            self._safe_label_config(self.status_labels.get("laser_shutter"), text="---", foreground="black")
            return

        try:
            wl = self.laser_source_device.get_wavelength()
            self._safe_label_config(self.status_labels.get("laser_wavelength"), text=f"{wl:.2f} нм")

            pos = self.laser_source_device.get_position(1)
            self._safe_label_config(self.status_labels.get("laser_position"), text=str(pos))

            speed = self.laser_source_device.get_speed(1)
            self._safe_label_config(self.status_labels.get("laser_speed"), text=str(speed))

            motor_status = self.laser_source_device.get_status(1)
            if motor_status == 0:
                self._safe_label_config(self.status_labels.get("laser_motor"), text="Готов", foreground="green")
            elif motor_status == 1:
                self._safe_label_config(self.status_labels.get("laser_motor"), text="Движение", foreground="orange")
            else:
                self._safe_label_config(self.status_labels.get("laser_motor"), text="Ошибка", foreground="red")

            shutter = self.laser_source_device.get_shutter(1)
            if shutter:
                self._safe_label_config(self.status_labels.get("laser_shutter"), text="Открыт", foreground="green")
            else:
                self._safe_label_config(self.status_labels.get("laser_shutter"), text="Закрыт", foreground="red")
        except Exception:
            pass

    def update_oscilloscope_status(self):
        """Обновление статуса осциллографа."""
        if not self.oscilloscope_connected or not self.oscilloscope_device:
            self._safe_label_config(self.status_labels.get("oscilloscope_scale"), text="--- В/дел")
            self._safe_label_config(self.status_labels.get("oscilloscope_offset"), text="--- В")
            self._safe_label_config(self.status_labels.get("oscilloscope_coupling"), text="---")
            self._safe_label_config(self.status_labels.get("oscilloscope_enabled"), text="---", foreground="black")
            self._safe_label_config(self.status_labels.get("oscilloscope_timebase"), text="--- с/дел")
            self._safe_label_config(self.status_labels.get("oscilloscope_acquisition_type"), text="---")
            self._safe_label_config(self.status_labels.get("oscilloscope_average"), text="---")
            return

        try:
            channel_str = self.status_labels.get("oscilloscope_channel", tk.StringVar(value="1")).get()
            channel = int(channel_str)

            scale = self.oscilloscope_device.get_channel_scale(channel)
            self._safe_label_config(self.status_labels.get("oscilloscope_scale"), text=f"{scale:.3f} В/дел")

            offset = self.oscilloscope_device.get_channel_offset(channel)
            self._safe_label_config(self.status_labels.get("oscilloscope_offset"), text=f"{offset:.3f} В")

            coupling = self.oscilloscope_device.get_channel_coupling(channel)
            self._safe_label_config(self.status_labels.get("oscilloscope_coupling"), text=coupling)

            enabled = self.oscilloscope_device.is_channel_enabled(channel)
            if enabled:
                self._safe_label_config(self.status_labels.get("oscilloscope_enabled"), text="Включён", foreground="green")
            else:
                self._safe_label_config(self.status_labels.get("oscilloscope_enabled"), text="Отключён", foreground="red")

            timebase = self.oscilloscope_device.get_timebase_scale()
            self._safe_label_config(self.status_labels.get("oscilloscope_timebase"), text=f"{timebase:.2e} с/дел")

            avg = self.oscilloscope_device.get_average_count()
            self._safe_label_config(self.status_labels.get("oscilloscope_average"), text=str(avg))

            acq_type = self.oscilloscope_device.get_acquisition_type()
            self._safe_label_config(self.status_labels.get("oscilloscope_acquisition_type"), text=acq_type)
        except Exception:
            pass

    def update_powermeter_status(self):
        """Обновление статуса энергометра."""
        if not self.powermeter_connected or not self.powermeter_device:
            self._safe_label_config(self.status_labels.get("powermeter_power"), text="--- Вт")
            self._safe_label_config(self.status_labels.get("powermeter_average_power"), text="--- Вт")
            self._safe_label_config(self.status_labels.get("powermeter_scale"), text="---")
            self._safe_label_config(self.status_labels.get("powermeter_autoscale"), text="---", foreground="black")
            self._safe_label_config(self.status_labels.get("powermeter_wavelength"), text="--- нм")
            return

        try:
            power = self.powermeter_device.get_power()
            self._safe_label_config(self.status_labels.get("powermeter_power"), text=f"{power:.6e} Вт")

            scale_idx = self.powermeter_device.get_current_scale_index()
            self._safe_label_config(self.status_labels.get("powermeter_scale"), text=str(scale_idx))

            autoscale = self.powermeter_device.get_autoscale()
            if autoscale:
                self._safe_label_config(self.status_labels.get("powermeter_autoscale"), text="Включена", foreground="green")
            else:
                self._safe_label_config(self.status_labels.get("powermeter_autoscale"), text="Отключена", foreground="red")

            wl = self.powermeter_device.get_wavelength()
            if wl > 0:
                self._safe_label_config(self.status_labels.get("powermeter_wavelength"), text=f"{wl} нм")
            else:
                self._safe_label_config(self.status_labels.get("powermeter_wavelength"), text="--- нм")
        except Exception:
            pass

    def update_all_status(self):
        """Обновление статуса всех устройств (запускается в потоке)."""
        if not self.auto_update_enabled:
            return

        self.update_chromator_status()
        self.update_laser_status()
        self.update_oscilloscope_status()
        self.update_powermeter_status()

        # Запуск следующего обновления через 1.5 секунды
        if self.auto_update_enabled:
            if self.status_timer:
                try:
                    self.status_timer.cancel()
                except Exception:
                    pass
            self.status_timer = threading.Timer(1.5, self.update_all_status)
            self.status_timer.daemon = True
            self.status_timer.start()

    def start_auto_update(self):
        """Запуск автоматического обновления статуса."""
        if self.auto_update_enabled:
            self.auto_update_enabled = True
            self.update_all_status()

    def stop_auto_update(self):
        """Остановка автоматического обновления статуса."""
        self.auto_update_enabled = False
        if self.status_timer:
            try:
                self.status_timer.cancel()
            except Exception:
                pass
            self.status_timer = None

    # =====================================================
    # ПОДКЛЮЧЕНИЕ / ОТКЛЮЧЕНИЕ УСТРОЙСТВ
    # =====================================================

    def connect_chromator(self):
        """Подключение монохроматора."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["chromator_connect"], state=tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["chromator_disconnect"], state=tk.DISABLED)

                    self.chromator_device = Chromator()
                    if self.chromator_device.connect():
                        self.chromator_connected = True
                        self._set_buttons_state(self.control_buttons["chromator"], tk.NORMAL)
                        self._safe_widget_config(self.control_buttons["chromator_connect"], state=tk.DISABLED)
                        self._safe_widget_config(self.control_buttons["chromator_disconnect"], state=tk.NORMAL)
                        self._safe_label_config(self.status_labels.get("chromator_status"), text="Подключен", foreground="green")
                    else:
                        self.chromator_device = None
                        self.chromator_connected = False
                        self._safe_label_config(self.status_labels.get("chromator_status"), text="Ошибка", foreground="red")
                        messagebox.showerror("Ошибка", "Не удалось подключить монохроматор")
                except Exception:
                    self.chromator_connected = False
                    self._safe_label_config(self.status_labels.get("chromator_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_config(self.control_buttons["chromator_connect"], state=tk.NORMAL)
                    self.update_chromator_status()
        threading.Thread(target=task, daemon=True).start()

    def disconnect_chromator(self):
        """Отключение монохроматора."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["chromator_disconnect"], state=tk.DISABLED)
                    if self.chromator_device:
                        self.chromator_device.disconnect()
                        self.chromator_device = None
                    self.chromator_connected = False
                    self._set_buttons_state(self.control_buttons["chromator"], tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["chromator_connect"], state=tk.NORMAL)
                    self._safe_widget_config(self.control_buttons["chromator_disconnect"], state=tk.DISABLED)
                    self._safe_label_config(self.status_labels.get("chromator_status"), text="Отключен", foreground="black")
                except Exception:
                    pass
                finally:
                    self.update_chromator_status()
        threading.Thread(target=task, daemon=True).start()

    def connect_laser(self):
        """Подключение лазера."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["laser_connect"], state=tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["laser_disconnect"], state=tk.DISABLED)

                    self.laser_source_device = LaserSource()
                    if self.laser_source_device.connect():
                        self.laser_connected = True
                        self._set_buttons_state(self.control_buttons["laser"], tk.NORMAL)
                        self._safe_widget_config(self.control_buttons["laser_connect"], state=tk.DISABLED)
                        self._safe_widget_config(self.control_buttons["laser_disconnect"], state=tk.NORMAL)
                        self._safe_label_config(self.status_labels.get("laser_status"), text="Подключен", foreground="green")
                    else:
                        self.laser_source_device = None
                        self.laser_connected = False
                        self._safe_label_config(self.status_labels.get("laser_status"), text="Ошибка", foreground="red")
                        messagebox.showerror("Ошибка", "Не удалось подключить лазер")
                except Exception:
                    self.laser_connected = False
                    self._safe_label_config(self.status_labels.get("laser_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_config(self.control_buttons["laser_connect"], state=tk.NORMAL)
                    self.update_laser_status()
        threading.Thread(target=task, daemon=True).start()

    def disconnect_laser(self):
        """Отключение лазера."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["laser_disconnect"], state=tk.DISABLED)
                    if self.laser_source_device:
                        self.laser_source_device.disconnect()
                        self.laser_source_device = None
                    self.laser_connected = False
                    self._set_buttons_state(self.control_buttons["laser"], tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["laser_connect"], state=tk.NORMAL)
                    self._safe_widget_config(self.control_buttons["laser_disconnect"], state=tk.DISABLED)
                    self._safe_label_config(self.status_labels.get("laser_status"), text="Отключен", foreground="black")
                except Exception:
                    pass
                finally:
                    self.update_laser_status()
        threading.Thread(target=task, daemon=True).start()

    def connect_oscilloscope(self):
        """Подключение осциллографа."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["oscilloscope_connect"], state=tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["oscilloscope_disconnect"], state=tk.DISABLED)

                    self.oscilloscope_device = Oscilloscope()
                    if self.oscilloscope_device.connect():
                        self.oscilloscope_connected = True
                        self._set_buttons_state(self.control_buttons["oscilloscope"], tk.NORMAL)
                        self._safe_widget_config(self.control_buttons["oscilloscope_connect"], state=tk.DISABLED)
                        self._safe_widget_config(self.control_buttons["oscilloscope_disconnect"], state=tk.NORMAL)
                        self._safe_label_config(self.status_labels.get("oscilloscope_status"), text="Подключен", foreground="green")
                    else:
                        self.oscilloscope_device = None
                        self.oscilloscope_connected = False
                        self._safe_label_config(self.status_labels.get("oscilloscope_status"), text="Ошибка", foreground="red")
                        messagebox.showerror("Ошибка", "Не удалось подключить осциллограф")
                except Exception:
                    self.oscilloscope_connected = False
                    self._safe_label_config(self.status_labels.get("oscilloscope_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_config(self.control_buttons["oscilloscope_connect"], state=tk.NORMAL)
                    self.update_oscilloscope_status()
        threading.Thread(target=task, daemon=True).start()

    def disconnect_oscilloscope(self):
        """Отключение осциллографа."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["oscilloscope_disconnect"], state=tk.DISABLED)
                    if self.oscilloscope_device:
                        self.oscilloscope_device.disconnect()
                        self.oscilloscope_device = None
                    self.oscilloscope_connected = False
                    self._set_buttons_state(self.control_buttons["oscilloscope"], tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["oscilloscope_connect"], state=tk.NORMAL)
                    self._safe_widget_config(self.control_buttons["oscilloscope_disconnect"], state=tk.DISABLED)
                    self._safe_label_config(self.status_labels.get("oscilloscope_status"), text="Отключен", foreground="black")
                except Exception:
                    pass
                finally:
                    self.update_oscilloscope_status()
        threading.Thread(target=task, daemon=True).start()

    def connect_powermeter(self):
        """Подключение энергометра."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["powermeter_connect"], state=tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["powermeter_disconnect"], state=tk.DISABLED)

                    self.powermeter_device = Powermeter()
                    if self.powermeter_device.connect():
                        self.powermeter_connected = True
                        self._set_buttons_state(self.control_buttons["powermeter"], tk.NORMAL)
                        self._safe_widget_config(self.control_buttons["powermeter_connect"], state=tk.DISABLED)
                        self._safe_widget_config(self.control_buttons["powermeter_disconnect"], state=tk.NORMAL)
                        self._safe_label_config(self.status_labels.get("powermeter_status"), text="Подключен", foreground="green")
                    else:
                        self.powermeter_device = None
                        self.powermeter_connected = False
                        self._safe_label_config(self.status_labels.get("powermeter_status"), text="Ошибка", foreground="red")
                        messagebox.showerror("Ошибка", "Не удалось подключить энергометр")
                except Exception:
                    self.powermeter_connected = False
                    self._safe_label_config(self.status_labels.get("powermeter_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_config(self.control_buttons["powermeter_connect"], state=tk.NORMAL)
                    self.update_powermeter_status()
        threading.Thread(target=task, daemon=True).start()

    def disconnect_powermeter(self):
        """Отключение энергометра."""
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_config(self.control_buttons["powermeter_disconnect"], state=tk.DISABLED)
                    if self.powermeter_device:
                        self.powermeter_device.disconnect()
                        self.powermeter_device = None
                    self.powermeter_connected = False
                    self._set_buttons_state(self.control_buttons["powermeter"], tk.DISABLED)
                    self._safe_widget_config(self.control_buttons["powermeter_connect"], state=tk.NORMAL)
                    self._safe_widget_config(self.control_buttons["powermeter_disconnect"], state=tk.DISABLED)
                    self._safe_label_config(self.status_labels.get("powermeter_status"), text="Отключен", foreground="black")
                except Exception:
                    pass
                finally:
                    self.update_powermeter_status()
        threading.Thread(target=task, daemon=True).start()

    # =====================================================
    # УПРАВЛЕНИЕ МОНОХРОМАТОРОМ
    # =====================================================

    def set_chromator_wavelength(self, entry):
        if not self.chromator_connected:
            return
        def task():
            try:
                wl = float(entry.get())
                self.chromator_device.set_wavelength(wl)
                time.sleep(0.3)
                self.update_chromator_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_chromator_input_slit(self, entry):
        if not self.chromator_connected:
            return
        def task():
            try:
                width = float(entry.get())
                self.chromator_device.set_slit_width(0, width)
                self.update_chromator_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_chromator_output_slit(self, entry):
        if not self.chromator_connected:
            return
        def task():
            try:
                width = float(entry.get())
                if self.chromator_device.get_slit_count() > 1:
                    self.chromator_device.set_slit_width(1, width)
                    self.update_chromator_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def open_chromator_shutter(self):
        if self.chromator_connected:
            self.chromator_device.shutter_open(0)
            self.update_chromator_status()

    def close_chromator_shutter(self):
        if self.chromator_connected:
            self.chromator_device.shutter_close(0)
            self.update_chromator_status()

    def set_chromator_grating(self, spinbox):
        if self.chromator_connected:
            try:
                grating_index = int(spinbox.get())
                self.chromator_device.set_active_grating(grating_index)
                self.update_chromator_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректный номер решётки")
            except Exception:
                pass

    def set_chromator_filter(self, combobox):
        """Установка фильтра монохроматора."""
        if self.chromator_connected:
            try:
                filter_index = int(combobox.get().split()[0])
                self.chromator_device.set_filter_state(filter_index, 0)
                self.update_chromator_status()
            except Exception:
                pass

    def set_chromator_mirror(self, combobox):
        """Переключение выходного порта монохроматора."""
        if self.chromator_connected:
            try:
                mirror_index = 0
                state = 0 if combobox.get() == "Осевой" else 1
                self.chromator_device.set_mirror_state(mirror_index, state)
                self.update_chromator_status()
            except Exception:
                pass

    def reset_chromator_grating(self):
        """Сброс решётки монохроматора."""
        if self.chromator_connected:
            self.chromator_device.reset_grating()
            self.update_chromator_status()

    # =====================================================
    # УПРАВЛЕНИЕ ЛАЗЕРОМ
    # =====================================================

    def set_laser_wavelength(self, entry):
        if not self.laser_connected:
            return
        def task():
            try:
                wl = float(entry.get())
                self.laser_source_device.set_wavelength(wl)
                time.sleep(0.3)
                self.update_laser_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_laser_absolute_position(self, entry):
        if not self.laser_connected:
            return
        def task():
            try:
                pos = int(entry.get())
                self.laser_source_device.set_absolute_position(1, pos)
                time.sleep(0.3)
                self.update_laser_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное целое число")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_laser_relative_position(self, entry):
        if not self.laser_connected:
            return
        def task():
            try:
                steps = int(entry.get())
                self.laser_source_device.set_relative_position(1, steps)
                time.sleep(0.3)
                self.update_laser_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное целое число")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_laser_speed(self, entry):
        if not self.laser_connected:
            return
        def task():
            try:
                speed = int(entry.get())
                self.laser_source_device.set_speed(1, speed)
                self.update_laser_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное целое число")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def enable_laser_motor(self):
        if self.laser_connected:
            self.laser_source_device.enable_motor(1)
            self.update_laser_status()

    def disable_laser_motor(self):
        if self.laser_connected:
            self.laser_source_device.disable_motor(1)
            self.update_laser_status()

    def open_laser_shutter(self):
        if self.laser_connected:
            self.laser_source_device.set_shutter(1, True)
            self.update_laser_status()

    def close_laser_shutter(self):
        if self.laser_connected:
            self.laser_source_device.set_shutter(1, False)
            self.update_laser_status()

    def reset_laser(self):
        """Сброс лазера (RESET)."""
        if self.laser_connected:
            self.laser_source_device.reset()
            self.update_laser_status()

    # =====================================================
    # УПРАВЛЕНИЕ ОСЦИЛЛОГРАФОМ
    # =====================================================

    def set_oscilloscope_scale(self, entry):
        if not self.oscilloscope_connected:
            return
        def task():
            try:
                channel = int(self.status_labels["oscilloscope_channel"].get())
                scale = float(entry.get())
                self.oscilloscope_device.set_channel_scale(channel, scale)
                self.update_oscilloscope_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_oscilloscope_offset(self, entry):
        if not self.oscilloscope_connected:
            return
        def task():
            try:
                channel = int(self.status_labels["oscilloscope_channel"].get())
                offset = float(entry.get())
                self.oscilloscope_device.set_channel_offset(channel, offset)
                self.update_oscilloscope_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_oscilloscope_coupling(self, combobox):
        if self.oscilloscope_connected:
            try:
                channel = int(self.status_labels["oscilloscope_channel"].get())
                coupling = combobox.get()
                self.oscilloscope_device.set_channel_coupling(channel, coupling)
                self.update_oscilloscope_status()
            except Exception:
                pass

    def enable_oscilloscope_channel(self):
        if self.oscilloscope_connected:
            try:
                channel = int(self.status_labels["oscilloscope_channel"].get())
                self.oscilloscope_device.set_channel_enabled(channel, True)
                self.update_oscilloscope_status()
            except Exception:
                pass

    def disable_oscilloscope_channel(self):
        if self.oscilloscope_connected:
            try:
                channel = int(self.status_labels["oscilloscope_channel"].get())
                self.oscilloscope_device.set_channel_enabled(channel, False)
                self.update_oscilloscope_status()
            except Exception:
                pass

    def set_oscilloscope_timebase(self, entry):
        if not self.oscilloscope_connected:
            return
        def task():
            try:
                timebase = float(entry.get())
                self.oscilloscope_device.set_timebase_scale(timebase)
                self.update_oscilloscope_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_oscilloscope_average(self, entry):
        if not self.oscilloscope_connected:
            return
        def task():
            try:
                avg = int(entry.get())
                self.oscilloscope_device.set_average_count(avg)
                self.update_oscilloscope_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное целое число")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_oscilloscope_trigger_source(self, combobox):
        """Установка источника триггера."""
        if self.oscilloscope_connected:
            try:
                source = combobox.get()
                self.oscilloscope_device.set_trigger_source(source)
                self.update_oscilloscope_status()
            except Exception:
                pass

    def set_oscilloscope_trigger_level(self, entry):
        """Установка уровня триггера."""
        if not self.oscilloscope_connected:
            return
        def task():
            try:
                level = float(entry.get())
                self.oscilloscope_device.set_trigger_level(level)
                self.update_oscilloscope_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное числовое значение")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def set_oscilloscope_trigger_slope(self, combobox):
        """Установка наклона триггера."""
        if self.oscilloscope_connected:
            try:
                slope = combobox.get()
                self.oscilloscope_device.set_trigger_slope(slope)
                self.update_oscilloscope_status()
            except Exception:
                pass

    def set_oscilloscope_impedance(self, combobox):
        """Установка импеданса канала (50 Ом / 1 МОм)."""
        if self.oscilloscope_connected:
            try:
                channel = int(self.status_labels["oscilloscope_channel"].get())
                imp = float(combobox.get().split()[0]) * 1e6 if "М" in combobox.get() else 50.0
                self.oscilloscope_device.set_channel_impedance(channel, imp)
                self.update_oscilloscope_status()
            except Exception:
                pass

    def run_oscilloscope_acquisition(self):
        if self.oscilloscope_connected:
            self.oscilloscope_device.run_acquisition()

    def stop_oscilloscope_acquisition(self):
        if self.oscilloscope_connected:
            self.oscilloscope_device.stop_acquisition()

    def single_oscilloscope_acquisition(self):
        if self.oscilloscope_connected:
            self.oscilloscope_device.single_acquisition()

    def force_oscilloscope_trigger(self):
        if self.oscilloscope_connected:
            self.oscilloscope_device.force_trigger()

    def save_oscilloscope_screenshot(self):
        if not self.oscilloscope_connected:
            return
        def task():
            try:
                fname = f"screenshot_{datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.png"
                path = os.path.join(os.getcwd(), fname)
                self.oscilloscope_device.save_screenshot(path)
                messagebox.showinfo("Успех", f"Скриншот сохранён: {fname}")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def save_oscilloscope_csv(self):
        if not self.oscilloscope_connected:
            return
        def task():
            try:
                channel = int(self.status_labels["oscilloscope_channel"].get())
                fname = f"waveform_{datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.csv"
                path = os.path.join(os.getcwd(), fname)
                time_vals, volt_vals = self.oscilloscope_device.capture_waveform(channel, 2000)
                if time_vals and volt_vals:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("time_seconds,voltage_volts\n")
                        for t, v in zip(time_vals, volt_vals):
                            f.write(f"{t:.8e},{v:.6f}\n")
                    messagebox.showinfo("Успех", f"Данные сохранены: {fname}")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    # =====================================================
    # УПРАВЛЕНИЕ ЭНЕРГОМЕТРОМ
    # =====================================================

    def refresh_powermeter_power(self):
        if self.powermeter_connected:
            try:
                power = self.powermeter_device.get_power()
                self._safe_label_config(self.status_labels.get("powermeter_power"), text=f"{power:.6e} Вт")
            except Exception:
                pass

    def measure_average_powermeter_power(self):
        if not self.powermeter_connected:
            return
        def task():
            try:
                count = int(self.status_labels.get("powermeter_average_count", tk.StringVar(value="10")).get())
                avg = self.powermeter_device.get_average_power(count, 0.1)
                self._safe_label_config(self.status_labels.get("powermeter_average_power"), text=f"{avg:.6e} Вт")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def increase_powermeter_scale(self):
        if self.powermeter_connected:
            self.powermeter_device.set_scale_up()
            self.update_powermeter_status()

    def decrease_powermeter_scale(self):
        if self.powermeter_connected:
            self.powermeter_device.set_scale_down()
            self.update_powermeter_status()

    def set_powermeter_scale(self, entry):
        if not self.powermeter_connected:
            return
        def task():
            try:
                idx = int(entry.get())
                if 0 <= idx <= 41:
                    self.powermeter_device.set_scale(idx)
                    self.update_powermeter_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите число от 0 до 41")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def enable_powermeter_autoscale(self):
        if self.powermeter_connected:
            self.powermeter_device.set_autoscale(True)
            self.update_powermeter_status()

    def disable_powermeter_autoscale(self):
        if self.powermeter_connected:
            self.powermeter_device.set_autoscale(False)
            self.update_powermeter_status()

    def set_powermeter_wavelength(self, entry):
        if not self.powermeter_connected:
            return
        def task():
            try:
                wl = int(entry.get())
                self.powermeter_device.set_wavelength_nanometers(wl)
                self.update_powermeter_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное целое число")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def zero_powermeter(self):
        """Обнуление энергометра (Zero)."""
        if self.powermeter_connected:
            self.powermeter_device.set_zero_offset()
            self.update_powermeter_status()

    def set_powermeter_trigger_level(self, entry):
        """Установка уровня триггера энергометра."""
        if not self.powermeter_connected:
            return
        def task():
            try:
                level = float(entry.get())
                if 0.1 <= level <= 99.9:
                    self.powermeter_device.set_trigger_level(level)
                    self.update_powermeter_status()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите число от 0.1 до 99.9")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    # =====================================================
    # СОЗДАНИЕ GUI
    # =====================================================

    def create_chromator_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = ttk.LabelFrame(tab, text="Монохроматор:", padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Подключение
        conn_frame = ttk.Frame(main_frame)
        conn_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(conn_frame)
        center.pack(anchor="center")

        btn_connect = ttk.Button(center, text="Подключить", width=16)
        btn_disconnect = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        btn_connect.pack(side=tk.LEFT, padx=5)
        btn_disconnect.pack(side=tk.LEFT, padx=5)

        self.control_buttons["chromator_connect"] = btn_connect
        self.control_buttons["chromator_disconnect"] = btn_disconnect
        self.control_buttons["chromator"] = [btn_disconnect]

        btn_connect.config(command=self.connect_chromator)
        btn_disconnect.config(command=self.disconnect_chromator)

        # Статус
        status_frame = ttk.LabelFrame(main_frame, text="Состояние:", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        grid = ttk.Frame(status_frame)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.status_labels["chromator_status"] = ttk.Label(grid, text="Отключен", foreground="black")
        self.status_labels["chromator_status"].grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Длина волны:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["chromator_wavelength"] = ttk.Label(grid, text="--- нм")
        self.status_labels["chromator_wavelength"].grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Входная щель:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["chromator_input_slit"] = ttk.Label(grid, text="--- мкм")
        self.status_labels["chromator_input_slit"].grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Выходная щель:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["chromator_output_slit"] = ttk.Label(grid, text="--- мкм")
        self.status_labels["chromator_output_slit"].grid(row=3, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Затвор:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["chromator_shutter"] = ttk.Label(grid, text="---")
        self.status_labels["chromator_shutter"].grid(row=4, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Активная решётка:").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["chromator_grating"] = ttk.Label(grid, text="-")
        self.status_labels["chromator_grating"].grid(row=5, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Всего решёток:").grid(row=6, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["chromator_grating_count"] = ttk.Label(grid, text="0")
        self.status_labels["chromator_grating_count"].grid(row=6, column=1, sticky="w", padx=5, pady=2)

        # Управление
        ctrl_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=5)
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=0)
        ctrl_frame.columnconfigure(2, weight=0)

        ttk.Label(ctrl_frame, text="Длина волны (нм):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        wl_entry = ttk.Entry(ctrl_frame, width=16)
        wl_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_chromator_wavelength(wl_entry)).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Входная щель (мкм):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        input_entry = ttk.Entry(ctrl_frame, width=16)
        input_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_chromator_input_slit(input_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Выходная щель (мкм):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        output_entry = ttk.Entry(ctrl_frame, width=16)
        output_entry.grid(row=2, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_chromator_output_slit(output_entry)).grid(row=2, column=2, padx=5, pady=2)

        # Затвор
        shutter_frame = ttk.Frame(ctrl_frame)
        shutter_frame.grid(row=3, column=0, columnspan=3, pady=5)
        shutter_center = ttk.Frame(shutter_frame)
        shutter_center.pack(anchor="center")
        ttk.Button(shutter_center, text="Открыть затвор", width=16, command=self.open_chromator_shutter).pack(side=tk.LEFT, padx=5)
        ttk.Button(shutter_center, text="Закрыть затвор", width=16, command=self.close_chromator_shutter).pack(side=tk.LEFT, padx=5)

        # Решётка
        grating_frame = ttk.Frame(ctrl_frame)
        grating_frame.grid(row=4, column=0, columnspan=3, pady=5)
        grating_center = ttk.Frame(grating_frame)
        grating_center.pack(anchor="center")
        ttk.Label(grating_center, text="Номер решётки:").pack(side=tk.LEFT, padx=5)
        grating_spin = ttk.Spinbox(grating_center, from_=0, to=10, width=12)
        grating_spin.pack(side=tk.LEFT, padx=5)
        ttk.Button(grating_center, text="Выбрать", width=12, command=lambda: self.set_chromator_grating(grating_spin)).pack(side=tk.LEFT, padx=5)
        ttk.Button(grating_center, text="Сброс", width=12, command=self.reset_chromator_grating).pack(side=tk.LEFT, padx=5)

        # Фильтры
        filter_frame = ttk.Frame(ctrl_frame)
        filter_frame.grid(row=5, column=0, columnspan=3, pady=5)
        filter_center = ttk.Frame(filter_frame)
        filter_center.pack(anchor="center")
        ttk.Label(filter_center, text="Фильтр:").pack(side=tk.LEFT, padx=5)
        filter_combo = ttk.Combobox(filter_center, values=["0 - Без фильтра", "1 - Фильтр 1", "2 - Фильтр 2"], width=20, state="readonly")
        filter_combo.set("0 - Без фильтра")
        filter_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_center, text="Установить", width=14, command=lambda: self.set_chromator_filter(filter_combo)).pack(side=tk.LEFT, padx=5)

        # Зеркала
        mirror_frame = ttk.Frame(ctrl_frame)
        mirror_frame.grid(row=6, column=0, columnspan=3, pady=5)
        mirror_center = ttk.Frame(mirror_frame)
        mirror_center.pack(anchor="center")
        ttk.Label(mirror_center, text="Выходной порт:").pack(side=tk.LEFT, padx=5)
        mirror_combo = ttk.Combobox(mirror_center, values=["Осевой", "Боковой"], width=15, state="readonly")
        mirror_combo.set("Осевой")
        mirror_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(mirror_center, text="Установить", width=14, command=lambda: self.set_chromator_mirror(mirror_combo)).pack(side=tk.LEFT, padx=5)

        return tab

    def create_laser_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = ttk.LabelFrame(tab, text="Лазер:", padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        conn_frame = ttk.Frame(main_frame)
        conn_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(conn_frame)
        center.pack(anchor="center")

        btn_connect = ttk.Button(center, text="Подключить", width=16)
        btn_disconnect = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        btn_connect.pack(side=tk.LEFT, padx=5)
        btn_disconnect.pack(side=tk.LEFT, padx=5)

        self.control_buttons["laser_connect"] = btn_connect
        self.control_buttons["laser_disconnect"] = btn_disconnect
        self.control_buttons["laser"] = [btn_disconnect]

        btn_connect.config(command=self.connect_laser)
        btn_disconnect.config(command=self.disconnect_laser)

        status_frame = ttk.LabelFrame(main_frame, text="Состояние:", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        grid = ttk.Frame(status_frame)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.status_labels["laser_status"] = ttk.Label(grid, text="Отключен", foreground="black")
        self.status_labels["laser_status"].grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Длина волны:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["laser_wavelength"] = ttk.Label(grid, text="--- нм")
        self.status_labels["laser_wavelength"].grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Положение (шаги):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["laser_position"] = ttk.Label(grid, text="---")
        self.status_labels["laser_position"].grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Скорость (шаги/с):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["laser_speed"] = ttk.Label(grid, text="---")
        self.status_labels["laser_speed"].grid(row=3, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Статус двигателя:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["laser_motor"] = ttk.Label(grid, text="---")
        self.status_labels["laser_motor"].grid(row=4, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Затвор:").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["laser_shutter"] = ttk.Label(grid, text="---")
        self.status_labels["laser_shutter"].grid(row=5, column=1, sticky="w", padx=5, pady=2)

        ctrl_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=5)
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=0)
        ctrl_frame.columnconfigure(2, weight=0)

        ttk.Label(ctrl_frame, text="Длина волны (нм):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        wl_entry = ttk.Entry(ctrl_frame, width=16)
        wl_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_laser_wavelength(wl_entry)).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Абсолютное положение:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        abs_entry = ttk.Entry(ctrl_frame, width=16)
        abs_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_laser_absolute_position(abs_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Относительное смещение:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        rel_entry = ttk.Entry(ctrl_frame, width=16)
        rel_entry.grid(row=2, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Переместить", width=14, command=lambda: self.set_laser_relative_position(rel_entry)).grid(row=2, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Скорость (шаги/с):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        speed_entry = ttk.Entry(ctrl_frame, width=16)
        speed_entry.grid(row=3, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_laser_speed(speed_entry)).grid(row=3, column=2, padx=5, pady=2)

        motor_frame = ttk.Frame(ctrl_frame)
        motor_frame.grid(row=4, column=0, columnspan=3, pady=5)
        motor_center = ttk.Frame(motor_frame)
        motor_center.pack(anchor="center")
        ttk.Button(motor_center, text="Включить двигатель", width=18, command=self.enable_laser_motor).pack(side=tk.LEFT, padx=5)
        ttk.Button(motor_center, text="Отключить двигатель", width=18, command=self.disable_laser_motor).pack(side=tk.LEFT, padx=5)

        shutter_frame = ttk.Frame(ctrl_frame)
        shutter_frame.grid(row=5, column=0, columnspan=3, pady=5)
        shutter_center = ttk.Frame(shutter_frame)
        shutter_center.pack(anchor="center")
        ttk.Button(shutter_center, text="Открыть затвор", width=16, command=self.open_laser_shutter).pack(side=tk.LEFT, padx=5)
        ttk.Button(shutter_center, text="Закрыть затвор", width=16, command=self.close_laser_shutter).pack(side=tk.LEFT, padx=5)

        reset_frame = ttk.Frame(ctrl_frame)
        reset_frame.grid(row=6, column=0, columnspan=3, pady=5)
        reset_center = ttk.Frame(reset_frame)
        reset_center.pack(anchor="center")
        ttk.Button(reset_center, text="Сброс (RESET)", width=18, command=self.reset_laser).pack(side=tk.LEFT, padx=5)

        return tab

    def create_oscilloscope_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = ttk.LabelFrame(tab, text="Осциллограф:", padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        conn_frame = ttk.Frame(main_frame)
        conn_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(conn_frame)
        center.pack(anchor="center")

        btn_connect = ttk.Button(center, text="Подключить", width=16)
        btn_disconnect = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        btn_connect.pack(side=tk.LEFT, padx=5)
        btn_disconnect.pack(side=tk.LEFT, padx=5)

        self.control_buttons["oscilloscope_connect"] = btn_connect
        self.control_buttons["oscilloscope_disconnect"] = btn_disconnect
        self.control_buttons["oscilloscope"] = [btn_disconnect]

        btn_connect.config(command=self.connect_oscilloscope)
        btn_disconnect.config(command=self.disconnect_oscilloscope)

        status_frame = ttk.LabelFrame(main_frame, text="Состояние:", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        grid = ttk.Frame(status_frame)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.status_labels["oscilloscope_status"] = ttk.Label(grid, text="Отключен", foreground="black")
        self.status_labels["oscilloscope_status"].grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Номер канала:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_channel"] = tk.StringVar(value="1")
        channel_combo = ttk.Combobox(grid, textvariable=self.status_labels["oscilloscope_channel"], values=["1", "2", "3", "4"], width=14, state="readonly")
        channel_combo.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        channel_combo.bind("<<ComboboxSelected>>", lambda e: self.update_oscilloscope_status())

        ttk.Label(grid, text="Вертикальный масштаб:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_scale"] = ttk.Label(grid, text="--- В/дел")
        self.status_labels["oscilloscope_scale"].grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Вертикальное смещение:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_offset"] = ttk.Label(grid, text="--- В")
        self.status_labels["oscilloscope_offset"].grid(row=3, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Тип связи:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_coupling"] = ttk.Label(grid, text="---")
        self.status_labels["oscilloscope_coupling"].grid(row=4, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Состояние канала:").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_enabled"] = ttk.Label(grid, text="---")
        self.status_labels["oscilloscope_enabled"].grid(row=5, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Горизонтальный масштаб:").grid(row=6, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_timebase"] = ttk.Label(grid, text="--- с/дел")
        self.status_labels["oscilloscope_timebase"].grid(row=6, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Режим усреднения:").grid(row=7, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_acquisition_type"] = ttk.Label(grid, text="---")
        self.status_labels["oscilloscope_acquisition_type"].grid(row=7, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Кол-во кадров:").grid(row=8, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_average"] = ttk.Label(grid, text="---")
        self.status_labels["oscilloscope_average"].grid(row=8, column=1, sticky="w", padx=5, pady=2)

        ctrl_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=5)
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=0)
        ctrl_frame.columnconfigure(2, weight=0)

        ttk.Label(ctrl_frame, text="Вертикальный масштаб:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        scale_entry = ttk.Entry(ctrl_frame, width=16)
        scale_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_scale(scale_entry)).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Вертикальное смещение:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        offset_entry = ttk.Entry(ctrl_frame, width=16)
        offset_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_offset(offset_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Тип связи:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        coupling_combo = ttk.Combobox(ctrl_frame, values=["DC", "AC", "GND"], width=14, state="readonly")
        coupling_combo.set("DC")
        coupling_combo.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_coupling(coupling_combo)).grid(row=2, column=2, padx=5, pady=2)

        channel_frame = ttk.Frame(ctrl_frame)
        channel_frame.grid(row=3, column=0, columnspan=3, pady=5)
        channel_center = ttk.Frame(channel_frame)
        channel_center.pack(anchor="center")
        ttk.Button(channel_center, text="Включить канал", width=16, command=self.enable_oscilloscope_channel).pack(side=tk.LEFT, padx=5)
        ttk.Button(channel_center, text="Отключить канал", width=16, command=self.disable_oscilloscope_channel).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="Горизонтальный масштаб:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        timebase_entry = ttk.Entry(ctrl_frame, width=16)
        timebase_entry.grid(row=4, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_timebase(timebase_entry)).grid(row=4, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Кол-во кадров:").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        avg_entry = ttk.Entry(ctrl_frame, width=16)
        avg_entry.grid(row=5, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_average(avg_entry)).grid(row=5, column=2, padx=5, pady=2)

        # Триггер
        trigger_frame = ttk.LabelFrame(ctrl_frame, text="Триггер:", padding=5)
        trigger_frame.grid(row=6, column=0, columnspan=3, pady=5, sticky="ew")
        trigger_frame.columnconfigure(0, weight=1)
        trigger_frame.columnconfigure(1, weight=0)
        trigger_frame.columnconfigure(2, weight=0)

        ttk.Label(trigger_frame, text="Источник:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        trigger_source = ttk.Combobox(trigger_frame, values=["CHAN1", "CHAN2", "CHAN3", "CHAN4", "LINE", "EXT"], width=14, state="readonly")
        trigger_source.set("CHAN1")
        trigger_source.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(trigger_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_trigger_source(trigger_source)).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(trigger_frame, text="Уровень (В):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        trig_level_entry = ttk.Entry(trigger_frame, width=16)
        trig_level_entry.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(trigger_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_trigger_level(trig_level_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(trigger_frame, text="Наклон:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        trig_slope = ttk.Combobox(trigger_frame, values=["POS", "NEG", "EITH"], width=14, state="readonly")
        trig_slope.set("POS")
        trig_slope.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(trigger_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_trigger_slope(trig_slope)).grid(row=2, column=2, padx=5, pady=2)

        # Импеданс
        imp_frame = ttk.Frame(ctrl_frame)
        imp_frame.grid(row=7, column=0, columnspan=3, pady=5)
        imp_center = ttk.Frame(imp_frame)
        imp_center.pack(anchor="center")
        ttk.Label(imp_center, text="Импеданс:").pack(side=tk.LEFT, padx=5)
        imp_combo = ttk.Combobox(imp_center, values=["1 МОм", "50 Ом"], width=12, state="readonly")
        imp_combo.set("1 МОм")
        imp_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(imp_center, text="Установить", width=14, command=lambda: self.set_oscilloscope_impedance(imp_combo)).pack(side=tk.LEFT, padx=5)

        # Сбор данных
        acq_frame = ttk.Frame(ctrl_frame)
        acq_frame.grid(row=8, column=0, columnspan=3, pady=5)
        acq_center = ttk.Frame(acq_frame)
        acq_center.pack(anchor="center")
        ttk.Button(acq_center, text="Запустить", width=14, command=self.run_oscilloscope_acquisition).pack(side=tk.LEFT, padx=5)
        ttk.Button(acq_center, text="Остановить", width=14, command=self.stop_oscilloscope_acquisition).pack(side=tk.LEFT, padx=5)
        ttk.Button(acq_center, text="Однократно", width=14, command=self.single_oscilloscope_acquisition).pack(side=tk.LEFT, padx=5)
        ttk.Button(acq_center, text="Принудить", width=14, command=self.force_oscilloscope_trigger).pack(side=tk.LEFT, padx=5)

        # Сохранение
        save_frame = ttk.Frame(ctrl_frame)
        save_frame.grid(row=9, column=0, columnspan=3, pady=5)
        save_center = ttk.Frame(save_frame)
        save_center.pack(anchor="center")
        ttk.Button(save_center, text="Скриншот", width=16, command=self.save_oscilloscope_screenshot).pack(side=tk.LEFT, padx=5)
        ttk.Button(save_center, text="Сохранить CSV", width=16, command=self.save_oscilloscope_csv).pack(side=tk.LEFT, padx=5)

        return tab

    def create_powermeter_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = ttk.LabelFrame(tab, text="Энергометр:", padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        conn_frame = ttk.Frame(main_frame)
        conn_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(conn_frame)
        center.pack(anchor="center")

        btn_connect = ttk.Button(center, text="Подключить", width=16)
        btn_disconnect = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        btn_connect.pack(side=tk.LEFT, padx=5)
        btn_disconnect.pack(side=tk.LEFT, padx=5)

        self.control_buttons["powermeter_connect"] = btn_connect
        self.control_buttons["powermeter_disconnect"] = btn_disconnect
        self.control_buttons["powermeter"] = [btn_disconnect]

        btn_connect.config(command=self.connect_powermeter)
        btn_disconnect.config(command=self.disconnect_powermeter)

        status_frame = ttk.LabelFrame(main_frame, text="Состояние:", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        grid = ttk.Frame(status_frame)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=0)

        self.status_labels["powermeter_status"] = ttk.Label(grid, text="Отключен", foreground="black")
        self.status_labels["powermeter_status"].grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Мощность:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["powermeter_power"] = ttk.Label(grid, text="--- Вт")
        self.status_labels["powermeter_power"].grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(grid, text="Обновить", width=14, command=self.refresh_powermeter_power).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(grid, text="Кол-во измерений:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["powermeter_average_count"] = tk.StringVar(value="10")
        avg_spin = ttk.Spinbox(grid, from_=1, to=100, width=14, textvariable=self.status_labels["powermeter_average_count"])
        avg_spin.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Средняя мощность:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["powermeter_average_power"] = ttk.Label(grid, text="--- Вт")
        self.status_labels["powermeter_average_power"].grid(row=3, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(grid, text="Измерить", width=14, command=self.measure_average_powermeter_power).grid(row=3, column=2, padx=5, pady=2)

        ttk.Label(grid, text="Индекс шкалы:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["powermeter_scale"] = ttk.Label(grid, text="---")
        self.status_labels["powermeter_scale"].grid(row=4, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Автошкала:").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["powermeter_autoscale"] = ttk.Label(grid, text="---")
        self.status_labels["powermeter_autoscale"].grid(row=5, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Длина волны:").grid(row=6, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["powermeter_wavelength"] = ttk.Label(grid, text="--- нм")
        self.status_labels["powermeter_wavelength"].grid(row=6, column=1, sticky="w", padx=5, pady=2)

        ctrl_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=5)
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=0)
        ctrl_frame.columnconfigure(2, weight=0)

        scale_btn_frame = ttk.Frame(ctrl_frame)
        scale_btn_frame.grid(row=0, column=0, columnspan=3, pady=5)
        scale_center = ttk.Frame(scale_btn_frame)
        scale_center.pack(anchor="center")
        ttk.Button(scale_center, text="Увеличить шкалу", width=16, command=self.increase_powermeter_scale).pack(side=tk.LEFT, padx=5)
        ttk.Button(scale_center, text="Уменьшить шкалу", width=16, command=self.decrease_powermeter_scale).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="Индекс шкалы (0-41):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        scale_entry = ttk.Entry(ctrl_frame, width=16)
        scale_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_powermeter_scale(scale_entry)).grid(row=1, column=2, padx=5, pady=2)

        auto_btn_frame = ttk.Frame(ctrl_frame)
        auto_btn_frame.grid(row=2, column=0, columnspan=3, pady=5)
        auto_center = ttk.Frame(auto_btn_frame)
        auto_center.pack(anchor="center")
        ttk.Button(auto_center, text="Включить автошкалу", width=18, command=self.enable_powermeter_autoscale).pack(side=tk.LEFT, padx=5)
        ttk.Button(auto_center, text="Отключить автошкалу", width=18, command=self.disable_powermeter_autoscale).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="Длина волны (нм):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        wl_entry = ttk.Entry(ctrl_frame, width=16)
        wl_entry.grid(row=3, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_powermeter_wavelength(wl_entry)).grid(row=3, column=2, padx=5, pady=2)

        ttk.Label(ctrl_frame, text="Уровень триггера (%):").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        trig_entry = ttk.Entry(ctrl_frame, width=16)
        trig_entry.grid(row=4, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Установить", width=14, command=lambda: self.set_powermeter_trigger_level(trig_entry)).grid(row=4, column=2, padx=5, pady=2)

        zero_frame = ttk.Frame(ctrl_frame)
        zero_frame.grid(row=5, column=0, columnspan=3, pady=5)
        zero_center = ttk.Frame(zero_frame)
        zero_center.pack(anchor="center")
        ttk.Button(zero_center, text="Обнулить (Zero)", width=18, command=self.zero_powermeter).pack(side=tk.LEFT, padx=5)

        return tab

    # =====================================================
    # ЗАПУСК GUI
    # =====================================================

    def initialize_user_interface(self):
        """Запуск графического интерфейса."""
        self.root_window = tk.Tk()
        self.root_window.title("Полное управление оборудованием")
        self.root_window.geometry("600x750")
        self.root_window.resizable(False, False)

        # Иконка
        icon_path = self.base_path / "icon.png"
        if icon_path.exists():
            try:
                icon = tk.PhotoImage(file=str(icon_path))
                self.root_window.iconphoto(True, icon)
            except Exception:
                pass

        style = ttk.Style()
        style.configure("TNotebook.Tab", padding=[10, 6])
        style.configure("TLabelframe.Label", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9))
        style.configure("TLabel", font=("Segoe UI", 9))

        main_frame = ttk.Frame(self.root_window, padding=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Создаём вкладки
        notebook.add(self.create_chromator_tab(notebook), text="Монохроматор")
        notebook.add(self.create_laser_tab(notebook), text="Лазер")
        notebook.add(self.create_oscilloscope_tab(notebook), text="Осциллограф")
        notebook.add(self.create_powermeter_tab(notebook), text="Энергометр")

        # Запускаем обновление статуса
        self.start_auto_update()

        self.root_window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root_window.mainloop()

    def on_closing(self):
        """Корректное закрытие приложения."""
        self.stop_auto_update()

        # Отключаем все устройства
        if self.chromator_device:
            try:
                self.chromator_device.disconnect()
            except Exception:
                pass
        if self.laser_source_device:
            try:
                self.laser_source_device.disconnect()
            except Exception:
                pass
        if self.oscilloscope_device:
            try:
                self.oscilloscope_device.disconnect()
            except Exception:
                pass
        if self.powermeter_device:
            try:
                self.powermeter_device.disconnect()
            except Exception:
                pass

        self.root_window.destroy()


if __name__ == "__main__":
    app = DeviceManager()
    app.initialize_user_interface()
