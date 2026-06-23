import os
import sys
import time
import tempfile
import threading
import tkinter as tk

from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def check_single_instance():
    lock_file_path = Path(tempfile.gettempdir()) / "device_manager_running.lock"

    try:
        if lock_file_path.exists():
            try:
                with open(lock_file_path, "r") as file_handle:
                    pid = int(file_handle.read().strip())
                try:
                    os.kill(pid, 0)
                    return False, None
                except:
                    lock_file_path.unlink()
            except:
                pass

        with open(lock_file_path, "w") as file_handle:
            file_handle.write(str(os.getpid()))

        return True, lock_file_path
    except:
        return True, None


def get_library_path():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "library"
    else:
        return Path(__file__).resolve().parent.parent / "library"


library_path = get_library_path()
sys.path.insert(0, str(library_path))

if getattr(sys, "frozen", False):
    sdk_path = Path(sys._MEIPASS) / "sdk"
    driver_path = Path(sys._MEIPASS) / "driver"
else:
    sdk_path = Path(__file__).resolve().parent.parent / "sdk"
    driver_path = Path(__file__).resolve().parent.parent / "driver"


from chromator import Chromator
from energymeter import Energymeter
from laser_source import LaserSource
from oscilloscope import Oscilloscope


class DeviceManager:
    def __init__(self):
        if getattr(sys, "frozen", False):
            self.base_path = Path(sys._MEIPASS)
        else:
            self.base_path = Path(__file__).parent

        self.chromator_device = None
        self.laser_source_device = None
        self.oscilloscope_device = None
        self.energymeter_device = None

        self.chromator_connected = False
        self.laser_connected = False
        self.oscilloscope_connected = False
        self.energymeter_connected = False

        self.auto_update_enabled = True
        self.status_timer = None
        self.operation_lock = threading.Lock()
        self.update_lock = threading.Lock()

        self.root_window = None
        self.status_labels = {}
        self.control_buttons = {
            "chromator": [],
            "laser": [],
            "oscilloscope": [],
            "energymeter": []
        }
        self.oscilloscope_average_spin = None
        self.oscilloscope_channel_variable = None


    def _safe_widget_configuration(self, widget, **kwargs):
        try:
            if widget and widget.winfo_exists():
                widget.config(**kwargs)
        except:
            pass


    def _safe_label_configuration(self, label, text=None, foreground=None):
        try:
            if label and label.winfo_exists():
                if text is not None:
                    label.config(text=text)
                if foreground is not None:
                    label.config(foreground=foreground)
        except:
            pass


    def _set_buttons_state(self, button_list, state):
        for button in button_list:
            self._safe_widget_configuration(button, state=state)


    def _safe_get_float(self, entry, min_value=None, max_value=None, error_message="Введите корректное число!"):
        try:
            value = entry.get().strip()
            if not value:
                return None
            number = float(value)
            if min_value is not None and number < min_value:
                def show_error():
                    messagebox.showerror("Ошибка ввода", f"Значение должно быть не меньше {min_value}!")
                self.root_window.after(0, show_error)
                return None
            if max_value is not None and number > max_value:
                def show_error():
                    messagebox.showerror("Ошибка ввода", f"Значение должно быть не больше {max_value}!")
                self.root_window.after(0, show_error)
                return None
            return number
        except ValueError:
            def show_error():
                messagebox.showerror("Ошибка ввода", error_message)
            self.root_window.after(0, show_error)
            return None


    def _safe_get_int(self, entry, min_value=None, max_value=None, error_message="Введите корректное целое число!"):
        try:
            value = entry.get().strip()
            if not value:
                return None
            number = int(value)
            if min_value is not None and number < min_value:
                def show_error():
                    messagebox.showerror("Ошибка ввода", f"Значение должно быть не меньше {min_value}!")
                self.root_window.after(0, show_error)
                return None
            if max_value is not None and number > max_value:
                def show_error():
                    messagebox.showerror("Ошибка ввода", f"Значение должно быть не больше {max_value}!")
                self.root_window.after(0, show_error)
                return None
            return number
        except ValueError:
            def show_error():
                messagebox.showerror("Ошибка ввода", error_message)
            self.root_window.after(0, show_error)
            return None


    def update_chromator_status(self):
        with self.update_lock:
            if not self.chromator_connected or not self.chromator_device:
                self._safe_label_configuration(self.status_labels.get("chromator_wavelength"), text="--- нм")
                self._safe_label_configuration(self.status_labels.get("chromator_input_slit"), text="--- мкм")
                self._safe_label_configuration(self.status_labels.get("chromator_output_slit"), text="--- мкм")
                self._safe_label_configuration(self.status_labels.get("chromator_shutter"), text="---", foreground="black")
                self._safe_label_configuration(self.status_labels.get("chromator_grating"), text="---")
                self._safe_label_configuration(self.status_labels.get("chromator_grating_count"), text="---")
                return

            try:
                wavelength = self.chromator_device.get_wavelength()
                self._safe_label_configuration(self.status_labels.get("chromator_wavelength"), text=f"{wavelength:.2f} нм")

                slit_count = self.chromator_device.get_slit_count()

                if slit_count > 0:
                    input_width = self.chromator_device.get_slit_width(0)
                    self._safe_label_configuration(self.status_labels.get("chromator_input_slit"), text=f"{input_width:.2f} мкм")

                if slit_count > 1:
                    output_width = self.chromator_device.get_slit_width(1)
                    self._safe_label_configuration(self.status_labels.get("chromator_output_slit"), text=f"{output_width:.2f} мкм")

                shutter_state = self.chromator_device.get_shutter_state(0)

                if shutter_state == 1:
                    self._safe_label_configuration(self.status_labels.get("chromator_shutter"), text="Открыт", foreground="green")
                else:
                    self._safe_label_configuration(self.status_labels.get("chromator_shutter"), text="Закрыт", foreground="red")

                active_grating = self.chromator_device.get_active_grating()
                self._safe_label_configuration(self.status_labels.get("chromator_grating"), text=str(active_grating))
                grating_count = self.chromator_device.get_grating_count()
                self._safe_label_configuration(self.status_labels.get("chromator_grating_count"), text=str(grating_count))
            except:
                pass


    def update_laser_status(self):
        with self.update_lock:
            if not self.laser_connected or not self.laser_source_device:
                self._safe_label_configuration(self.status_labels.get("laser_wavelength"), text="--- нм")
                self._safe_label_configuration(self.status_labels.get("laser_position"), text="---")
                self._safe_label_configuration(self.status_labels.get("laser_speed"), text="---")
                self._safe_label_configuration(self.status_labels.get("laser_motor"), text="---", foreground="black")
                self._safe_label_configuration(self.status_labels.get("laser_shutter"), text="---", foreground="black")
                return

            try:
                wavelength = self.laser_source_device.get_wavelength()
                self._safe_label_configuration(self.status_labels.get("laser_wavelength"), text=f"{wavelength:.2f} нм")

                position = self.laser_source_device.get_position(1)
                self._safe_label_configuration(self.status_labels.get("laser_position"), text=str(position))

                speed = self.laser_source_device.get_speed(1)
                self._safe_label_configuration(self.status_labels.get("laser_speed"), text=str(speed))

                motor_status = self.laser_source_device.get_status(1)

                if motor_status == 0:
                    self._safe_label_configuration(self.status_labels.get("laser_motor"), text="Готов", foreground="green")
                elif motor_status == 1:
                    self._safe_label_configuration(self.status_labels.get("laser_motor"), text="Движение", foreground="orange")
                else:
                    self._safe_label_configuration(self.status_labels.get("laser_motor"), text="Ошибка", foreground="red")

                shutter_state = self.laser_source_device.get_shutter(1)

                if shutter_state:
                    self._safe_label_configuration(self.status_labels.get("laser_shutter"), text="Открыт", foreground="green")
                else:
                    self._safe_label_configuration(self.status_labels.get("laser_shutter"), text="Закрыт", foreground="red")
            except:
                pass


    def update_oscilloscope_status(self):
        with self.update_lock:
            if not self.oscilloscope_connected or not self.oscilloscope_device:
                self._safe_label_configuration(self.status_labels.get("oscilloscope_scale"), text="--- В/дел")
                self._safe_label_configuration(self.status_labels.get("oscilloscope_offset"), text="--- В")
                self._safe_label_configuration(self.status_labels.get("oscilloscope_coupling"), text="---")
                self._safe_label_configuration(self.status_labels.get("oscilloscope_enabled"), text="---", foreground="black")
                self._safe_label_configuration(self.status_labels.get("oscilloscope_timebase"), text="--- с/дел")
                self._safe_label_configuration(self.status_labels.get("oscilloscope_acquisition_type"), text="---")
                self._safe_label_configuration(self.status_labels.get("oscilloscope_average"), text="---")
                return

            try:
                channel_string = self.oscilloscope_channel_variable.get()
                channel = int(channel_string)

                scale = self.oscilloscope_device.get_channel_scale(channel)
                self._safe_label_configuration(self.status_labels.get("oscilloscope_scale"), text=f"{scale:.3f} В/дел")

                offset = self.oscilloscope_device.get_channel_offset(channel)
                self._safe_label_configuration(self.status_labels.get("oscilloscope_offset"), text=f"{offset:.3f} В")

                coupling = self.oscilloscope_device.get_channel_coupling(channel)
                self._safe_label_configuration(self.status_labels.get("oscilloscope_coupling"), text=coupling)

                enabled = self.oscilloscope_device.is_channel_enabled(channel)

                if enabled:
                    self._safe_label_configuration(self.status_labels.get("oscilloscope_enabled"), text="Включён", foreground="green")
                else:
                    self._safe_label_configuration(self.status_labels.get("oscilloscope_enabled"), text="Отключён", foreground="red")

                timebase = self.oscilloscope_device.get_timebase_scale()
                self._safe_label_configuration(self.status_labels.get("oscilloscope_timebase"), text=f"{timebase:.2e} с/дел")

                average_count = self.oscilloscope_device.get_average_count()
                self._safe_label_configuration(self.status_labels.get("oscilloscope_average"), text=str(average_count))

                acquisition_type = self.oscilloscope_device.get_acquisition_type()
                self._safe_label_configuration(self.status_labels.get("oscilloscope_acquisition_type"), text=acquisition_type)
            except:
                pass


    def update_energymeter_status(self):
        with self.update_lock:
            if not self.energymeter_connected or not self.energymeter_device:
                self._safe_label_configuration(self.status_labels.get("energymeter_power"), text="--- Вт")
                self._safe_label_configuration(self.status_labels.get("energymeter_average_power"), text="--- Вт")
                self._safe_label_configuration(self.status_labels.get("energymeter_scale"), text="---")
                self._safe_label_configuration(self.status_labels.get("energymeter_autoscale"), text="---", foreground="black")
                self._safe_label_configuration(self.status_labels.get("energymeter_wavelength"), text="--- нм")
                return

            try:
                power = self.energymeter_device.get_power()
                self._safe_label_configuration(self.status_labels.get("energymeter_power"), text=f"{power:.6e} Вт")

                scale_index = self.energymeter_device.get_current_scale_index()
                self._safe_label_configuration(self.status_labels.get("energymeter_scale"), text=str(scale_index))

                autoscale_enabled = self.energymeter_device.get_autoscale()

                if autoscale_enabled:
                    self._safe_label_configuration(self.status_labels.get("energymeter_autoscale"), text="Включена", foreground="green")
                else:
                    self._safe_label_configuration(self.status_labels.get("energymeter_autoscale"), text="Отключена", foreground="red")

                wavelength = self.energymeter_device.get_wavelength()

                if wavelength > 0:
                    self._safe_label_configuration(self.status_labels.get("energymeter_wavelength"), text=f"{wavelength} нм")
                else:
                    self._safe_label_configuration(self.status_labels.get("energymeter_wavelength"), text="--- нм")
            except:
                pass


    def update_all_status(self):
        if not self.auto_update_enabled:
            return

        self.update_chromator_status()
        self.update_laser_status()
        self.update_oscilloscope_status()
        self.update_energymeter_status()

        if self.auto_update_enabled:
            if self.status_timer:
                try:
                    self.status_timer.cancel()
                except:
                    pass

            self.status_timer = threading.Timer(1.5, self.update_all_status)
            self.status_timer.daemon = True
            self.status_timer.start()


    def start_auto_update(self):
        self.auto_update_enabled = True
        self.update_all_status()


    def stop_auto_update(self):
        self.auto_update_enabled = False

        if self.status_timer:
            try:
                self.status_timer.cancel()
            except:
                pass

            self.status_timer = None


    def disconnect_all_devices(self):
        try:
            if self.chromator_connected and self.chromator_device:
                self.chromator_device.disconnect()
                self.chromator_connected = False
                self.chromator_device = None
        except:
            self.chromator_connected = False
            self.chromator_device = None

        try:
            if self.laser_connected and self.laser_source_device:
                self.laser_source_device.disconnect()
                self.laser_connected = False
                self.laser_source_device = None
        except:
            self.laser_connected = False
            self.laser_source_device = None

        try:
            if self.oscilloscope_connected and self.oscilloscope_device:
                try:
                    self.oscilloscope_device.stop_acquisition()
                    time.sleep(0.3)
                except:
                    pass

                self.oscilloscope_device.disconnect()
                self.oscilloscope_connected = False
                self.oscilloscope_device = None
        except:
            self.oscilloscope_connected = False
            self.oscilloscope_device = None

        try:
            if self.energymeter_connected and self.energymeter_device:
                self.energymeter_device.disconnect()
                self.energymeter_connected = False
                self.energymeter_device = None
        except:
            self.energymeter_connected = False
            self.energymeter_device = None


    def connect_chromator(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["chromator_connect"], state=tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["chromator_disconnect"], state=tk.DISABLED)

                    self.chromator_device = Chromator()

                    if self.chromator_device.connect():
                        self.chromator_connected = True
                        self._set_buttons_state(self.control_buttons["chromator"], tk.NORMAL)
                        self._safe_widget_configuration(self.control_buttons["chromator_connect"], state=tk.DISABLED)
                        self._safe_widget_configuration(self.control_buttons["chromator_disconnect"], state=tk.NORMAL)
                        self._safe_label_configuration(self.status_labels.get("chromator_status"), text="Подключен", foreground="green")
                    else:
                        self.chromator_device = None
                        self.chromator_connected = False
                        self._safe_label_configuration(self.status_labels.get("chromator_status"), text="Ошибка", foreground="red")

                        def show_error():
                            messagebox.showerror("Ошибка", "Не удалось подключить монохроматор!")

                        self.root_window.after(0, show_error)
                except:
                    self.chromator_connected = False
                    self._safe_label_configuration(self.status_labels.get("chromator_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_configuration(self.control_buttons["chromator_connect"], state=tk.NORMAL)
                    self.update_chromator_status()

        threading.Thread(target=task, daemon=True).start()


    def disconnect_chromator(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["chromator_disconnect"], state=tk.DISABLED)

                    if self.chromator_device:
                        self.chromator_device.disconnect()
                        self.chromator_device = None

                    self.chromator_connected = False
                    self._set_buttons_state(self.control_buttons["chromator"], tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["chromator_connect"], state=tk.NORMAL)
                    self._safe_widget_configuration(self.control_buttons["chromator_disconnect"], state=tk.DISABLED)
                    self._safe_label_configuration(self.status_labels.get("chromator_status"), text="Отключен", foreground="black")
                except:
                    pass
                finally:
                    self.update_chromator_status()

        threading.Thread(target=task, daemon=True).start()


    def connect_laser(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["laser_connect"], state=tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["laser_disconnect"], state=tk.DISABLED)

                    self.laser_source_device = LaserSource()

                    if self.laser_source_device.connect():
                        self.laser_connected = True
                        self._set_buttons_state(self.control_buttons["laser"], tk.NORMAL)
                        self._safe_widget_configuration(self.control_buttons["laser_connect"], state=tk.DISABLED)
                        self._safe_widget_configuration(self.control_buttons["laser_disconnect"], state=tk.NORMAL)
                        self._safe_label_configuration(self.status_labels.get("laser_status"), text="Подключен", foreground="green")
                    else:
                        self.laser_source_device = None
                        self.laser_connected = False
                        self._safe_label_configuration(self.status_labels.get("laser_status"), text="Ошибка", foreground="red")

                        def show_error():
                            messagebox.showerror("Ошибка", "Не удалось подключить лазер!")

                        self.root_window.after(0, show_error)
                except:
                    self.laser_connected = False
                    self._safe_label_configuration(self.status_labels.get("laser_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_configuration(self.control_buttons["laser_connect"], state=tk.NORMAL)
                    self.update_laser_status()

        threading.Thread(target=task, daemon=True).start()


    def disconnect_laser(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["laser_disconnect"], state=tk.DISABLED)

                    if self.laser_source_device:
                        self.laser_source_device.disconnect()
                        self.laser_source_device = None

                    self.laser_connected = False
                    self._set_buttons_state(self.control_buttons["laser"], tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["laser_connect"], state=tk.NORMAL)
                    self._safe_widget_configuration(self.control_buttons["laser_disconnect"], state=tk.DISABLED)
                    self._safe_label_configuration(self.status_labels.get("laser_status"), text="Отключен", foreground="black")
                except:
                    pass
                finally:
                    self.update_laser_status()

        threading.Thread(target=task, daemon=True).start()


    def connect_oscilloscope(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["oscilloscope_connect"], state=tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["oscilloscope_disconnect"], state=tk.DISABLED)

                    self.oscilloscope_device = Oscilloscope()

                    if self.oscilloscope_device.connect(timeout_milliseconds=30000):
                        self.oscilloscope_connected = True
                        self._set_buttons_state(self.control_buttons["oscilloscope"], tk.NORMAL)
                        self._safe_widget_configuration(self.control_buttons["oscilloscope_connect"], state=tk.DISABLED)
                        self._safe_widget_configuration(self.control_buttons["oscilloscope_disconnect"], state=tk.NORMAL)
                        self._safe_label_configuration(self.status_labels.get("oscilloscope_status"), text="Подключен", foreground="green")
                    else:
                        self.oscilloscope_device = None
                        self.oscilloscope_connected = False
                        self._safe_label_configuration(self.status_labels.get("oscilloscope_status"), text="Ошибка", foreground="red")

                        def show_error():
                            messagebox.showerror("Ошибка подключения", "Не удалось подключить осциллограф!")

                        self.root_window.after(0, show_error)
                except ImportError:
                    self.oscilloscope_connected = False
                    self._safe_label_configuration(self.status_labels.get("oscilloscope_status"), text="Ошибка", foreground="red")

                    def show_import_error():
                        messagebox.showerror("Ошибка", "Установите библиотеку PyVISA!")

                    self.root_window.after(0, show_import_error)
                except:
                    self.oscilloscope_connected = False
                    self._safe_label_configuration(self.status_labels.get("oscilloscope_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_configuration(self.control_buttons["oscilloscope_connect"], state=tk.NORMAL)
                    self.update_oscilloscope_status()

        threading.Thread(target=task, daemon=True).start()


    def disconnect_oscilloscope(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["oscilloscope_disconnect"], state=tk.DISABLED)

                    if self.oscilloscope_device:
                        try:
                            self.oscilloscope_device.stop_acquisition()
                            time.sleep(0.3)
                        except:
                            pass

                        self.oscilloscope_device.disconnect()
                        self.oscilloscope_device = None
                    self.oscilloscope_connected = False
                    self._set_buttons_state(self.control_buttons["oscilloscope"], tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["oscilloscope_connect"], state=tk.NORMAL)
                    self._safe_widget_configuration(self.control_buttons["oscilloscope_disconnect"], state=tk.DISABLED)
                    self._safe_label_configuration(self.status_labels.get("oscilloscope_status"), text="Отключен", foreground="black")
                except:
                    pass
                finally:
                    self.update_oscilloscope_status()

        threading.Thread(target=task, daemon=True).start()


    def connect_energymeter(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["energymeter_connect"], state=tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["energymeter_disconnect"], state=tk.DISABLED)

                    self.energymeter_device = Energymeter()

                    if self.energymeter_device.connect():
                        self.energymeter_connected = True
                        self._set_buttons_state(self.control_buttons["energymeter"], tk.NORMAL)
                        self._safe_widget_configuration(self.control_buttons["energymeter_connect"], state=tk.DISABLED)
                        self._safe_widget_configuration(self.control_buttons["energymeter_disconnect"], state=tk.NORMAL)
                        self._safe_label_configuration(self.status_labels.get("energymeter_status"), text="Подключен", foreground="green")
                    else:
                        self.energymeter_device = None
                        self.energymeter_connected = False
                        self._safe_label_configuration(self.status_labels.get("energymeter_status"), text="Ошибка", foreground="red")

                        def show_error():
                            messagebox.showerror("Ошибка", "Не удалось подключить энергометр!")

                        self.root_window.after(0, show_error)
                except:
                    self.energymeter_connected = False
                    self._safe_label_configuration(self.status_labels.get("energymeter_status"), text="Ошибка", foreground="red")
                finally:
                    self._safe_widget_configuration(self.control_buttons["energymeter_connect"], state=tk.NORMAL)
                    self.update_energymeter_status()

        threading.Thread(target=task, daemon=True).start()


    def disconnect_energymeter(self):
        def task():
            with self.operation_lock:
                try:
                    self._safe_widget_configuration(self.control_buttons["energymeter_disconnect"], state=tk.DISABLED)

                    if self.energymeter_device:
                        self.energymeter_device.disconnect()
                        self.energymeter_device = None

                    self.energymeter_connected = False
                    self._set_buttons_state(self.control_buttons["energymeter"], tk.DISABLED)
                    self._safe_widget_configuration(self.control_buttons["energymeter_connect"], state=tk.NORMAL)
                    self._safe_widget_configuration(self.control_buttons["energymeter_disconnect"], state=tk.DISABLED)
                    self._safe_label_configuration(self.status_labels.get("energymeter_status"), text="Отключен", foreground="black")
                except:
                    pass
                finally:
                    self.update_energymeter_status()

        threading.Thread(target=task, daemon=True).start()


    def set_chromator_wavelength(self, entry):
        if not self.chromator_connected:
            return

        def task():
            wavelength = self._safe_get_float(entry, min_value=0, error_message="Введите корректное число для длины волны (нм)!")
            if wavelength is None:
                return
            self.chromator_device.set_wavelength(wavelength)
            time.sleep(0.3)
            self.update_chromator_status()

        threading.Thread(target=task, daemon=True).start()


    def set_chromator_input_slit(self, entry):
        if not self.chromator_connected:
            return

        def task():
            width = self._safe_get_float(entry, min_value=0, error_message="Введите корректное число для ширины щели (мкм)!")
            if width is None:
                return
            self.chromator_device.set_slit_width(0, width)
            self.update_chromator_status()

        threading.Thread(target=task, daemon=True).start()


    def set_chromator_output_slit(self, entry):
        if not self.chromator_connected:
            return

        def task():
            width = self._safe_get_float(entry, min_value=0, error_message="Введите корректное число для ширины щели (мкм)!")
            if width is None:
                return
            if self.chromator_device.get_slit_count() > 1:
                self.chromator_device.set_slit_width(1, width)
                self.update_chromator_status()

        threading.Thread(target=task, daemon=True).start()


    def open_chromator_shutter(self):
        if self.chromator_connected:
            try:
                self.chromator_device.shutter_open(0)
                self.update_chromator_status()
            except:
                pass


    def close_chromator_shutter(self):
        if self.chromator_connected:
            try:
                self.chromator_device.shutter_close(0)
                self.update_chromator_status()
            except:
                pass


    def set_chromator_grating(self, spinbox):
        if self.chromator_connected:
            try:
                grating_index = int(spinbox.get())
                grating_count = self.chromator_device.get_grating_count()
                if 0 <= grating_index < grating_count:
                    self.chromator_device.set_active_grating(grating_index)
                    self.update_chromator_status()
                else:
                    def show_error():
                        messagebox.showerror("Ошибка", f"Номер решётки должен быть от 0 до {grating_count - 1}!")
                    self.root_window.after(0, show_error)
            except:
                pass


    def set_chromator_filter(self, combobox):
        if self.chromator_connected:
            try:
                filter_index = int(combobox.get().split()[0])
                self.chromator_device.set_filter_state(filter_index, 0)
                self.update_chromator_status()
            except:
                pass


    def set_chromator_mirror(self, combobox):
        if self.chromator_connected:
            try:
                mirror_index = 0
                state = 0 if combobox.get() == "Осевой" else 1
                self.chromator_device.set_mirror_state(mirror_index, state)
                self.update_chromator_status()
            except:
                pass


    def reset_chromator_grating(self):
        if self.chromator_connected:
            try:
                self.chromator_device.reset_grating()
                self.update_chromator_status()
            except:
                pass


    def set_laser_wavelength(self, entry):
        if not self.laser_connected:
            return

        def task():
            wavelength = self._safe_get_float(entry, min_value=0, error_message="Введите корректное число для длины волны (нм)!")
            if wavelength is None:
                return
            self.laser_source_device.set_wavelength(wavelength)
            time.sleep(0.3)
            self.update_laser_status()

        threading.Thread(target=task, daemon=True).start()


    def set_laser_absolute_position(self, entry):
        if not self.laser_connected:
            return

        def task():
            position = self._safe_get_int(entry, error_message="Введите корректное целое число для положения (шаги)!")
            if position is None:
                return
            self.laser_source_device.set_absolute_position(1, position)
            time.sleep(0.3)
            self.update_laser_status()

        threading.Thread(target=task, daemon=True).start()


    def set_laser_relative_position(self, entry):
        if not self.laser_connected:
            return

        def task():
            steps = self._safe_get_int(entry, error_message="Введите корректное целое число для смещения (шаги)!")
            if steps is None:
                return
            self.laser_source_device.set_relative_position(1, steps)
            time.sleep(0.3)
            self.update_laser_status()

        threading.Thread(target=task, daemon=True).start()


    def set_laser_speed(self, entry):
        if not self.laser_connected:
            return

        def task():
            speed = self._safe_get_int(entry, min_value=1, error_message="Введите корректное число для скорости (шаги/с)!")
            if speed is None:
                return
            self.laser_source_device.set_speed(1, speed)
            self.update_laser_status()

        threading.Thread(target=task, daemon=True).start()


    def enable_laser_motor(self):
        if self.laser_connected:
            try:
                self.laser_source_device.enable_motor(1)
                self.update_laser_status()
            except:
                pass


    def disable_laser_motor(self):
        if self.laser_connected:
            try:
                self.laser_source_device.disable_motor(1)
                self.update_laser_status()
            except:
                pass


    def open_laser_shutter(self):
        if self.laser_connected:
            try:
                self.laser_source_device.set_shutter(1, True)
                self.update_laser_status()
            except:
                pass


    def close_laser_shutter(self):
        if self.laser_connected:
            try:
                self.laser_source_device.set_shutter(1, False)
                self.update_laser_status()
            except:
                pass


    def reset_laser(self):
        if self.laser_connected:
            try:
                self.laser_source_device.reset()
                self.update_laser_status()
            except:
                pass


    def set_oscilloscope_scale(self, entry):
        if not self.oscilloscope_connected:
            return

        def task():
            scale = self._safe_get_float(entry, min_value=0.001, error_message="Введите корректное число для масштаба (В/дел)!")
            if scale is None:
                return
            channel = int(self.oscilloscope_channel_variable.get())
            self.oscilloscope_device.set_channel_scale(channel, scale)
            self.update_oscilloscope_status()

        threading.Thread(target=task, daemon=True).start()


    def set_oscilloscope_offset(self, entry):
        if not self.oscilloscope_connected:
            return

        def task():
            offset = self._safe_get_float(entry, error_message="Введите корректное число для смещения (В)!")
            if offset is None:
                return
            channel = int(self.oscilloscope_channel_variable.get())
            self.oscilloscope_device.set_channel_offset(channel, offset)
            self.update_oscilloscope_status()

        threading.Thread(target=task, daemon=True).start()


    def set_oscilloscope_coupling(self, combobox):
        if self.oscilloscope_connected:
            try:
                channel = int(self.oscilloscope_channel_variable.get())
                coupling = combobox.get()
                self.oscilloscope_device.set_channel_coupling(channel, coupling)
                self.update_oscilloscope_status()
            except:
                pass


    def enable_oscilloscope_channel(self):
        if self.oscilloscope_connected:
            try:
                channel = int(self.oscilloscope_channel_variable.get())
                self.oscilloscope_device.set_channel_enabled(channel, True)
                self.update_oscilloscope_status()
            except:
                pass


    def disable_oscilloscope_channel(self):
        if self.oscilloscope_connected:
            try:
                channel = int(self.oscilloscope_channel_variable.get())
                self.oscilloscope_device.set_channel_enabled(channel, False)
                self.update_oscilloscope_status()
            except:
                pass


    def set_oscilloscope_timebase(self, entry):
        if not self.oscilloscope_connected:
            return

        def task():
            timebase = self._safe_get_float(entry, min_value=1e-9, error_message="Введите корректное число для масштаба времени (с/дел)!")
            if timebase is None:
                return
            self.oscilloscope_device.set_timebase_scale(timebase)
            self.update_oscilloscope_status()

        threading.Thread(target=task, daemon=True).start()


    def set_oscilloscope_average_count(self, entry):
        if not self.oscilloscope_connected:
            return

        def task():
            average_count = self._safe_get_int(entry, min_value=1, max_value=65536, error_message="Введите корректное число кадров!")

            if average_count is None:
                return

            self.oscilloscope_device.set_average_count(average_count)
            self.update_oscilloscope_status()

        threading.Thread(target=task, daemon=True).start()


    def set_oscilloscope_trigger_source(self, combobox):
        if self.oscilloscope_connected:
            try:
                source = combobox.get()
                self.oscilloscope_device.set_trigger_source(source)
                self.update_oscilloscope_status()
            except:
                pass


    def set_oscilloscope_trigger_level(self, entry):
        if not self.oscilloscope_connected:
            return

        def task():
            level = self._safe_get_float(entry, error_message="Введите корректное число для уровня триггера (В)!")
            if level is None:
                return
            self.oscilloscope_device.set_trigger_level(level)
            self.update_oscilloscope_status()

        threading.Thread(target=task, daemon=True).start()


    def set_oscilloscope_trigger_slope(self, combobox):
        if self.oscilloscope_connected:
            try:
                slope = combobox.get()
                self.oscilloscope_device.set_trigger_slope(slope)
                self.update_oscilloscope_status()
            except:
                pass


    def set_oscilloscope_impedance(self, combobox):
        if self.oscilloscope_connected:
            try:
                channel = int(self.oscilloscope_channel_variable.get())
                impedance_string = combobox.get()

                if "М" in impedance_string:
                    impedance = float(impedance_string.split()[0]) * 1e6
                else:
                    impedance = 50.0

                self.oscilloscope_device.set_channel_impedance(channel, impedance)
                self.update_oscilloscope_status()
            except:
                pass


    def run_oscilloscope_acquisition(self):
        if self.oscilloscope_connected:
            try:
                self.oscilloscope_device.run_acquisition()
            except:
                pass


    def stop_oscilloscope_acquisition(self):
        if self.oscilloscope_connected:
            try:
                self.oscilloscope_device.stop_acquisition()
            except:
                pass


    def single_oscilloscope_acquisition(self):
        if self.oscilloscope_connected:
            try:
                self.oscilloscope_device.single_acquisition()
            except:
                pass


    def force_oscilloscope_trigger(self):
        if self.oscilloscope_connected:
            try:
                self.oscilloscope_device.force_trigger()
            except:
                pass


    def capture_waveform(self, averaged=False, average_count=64):
        if not self.oscilloscope_connected or not self.oscilloscope_device:
            return None, None

        try:
            channel = int(self.oscilloscope_channel_variable.get())

            for attempt in range(3):
                try:
                    if averaged:
                        time_values, voltage_values = self.oscilloscope_device.acquire_averaged_waveform_retry(
                            channel, average_count, 2000, max_retries=2
                        )
                    else:
                        time_values, voltage_values = self.oscilloscope_device.capture_waveform(channel, 2000)

                    if time_values and voltage_values and len(voltage_values) > 10:
                        return time_values, voltage_values
                except:
                    time.sleep(0.5)
                    continue

            return None, None
        except:
            return None, None


    def save_waveform_to_csv(self, time_values, voltage_values, filename=None):
        if not time_values or not voltage_values:
            return None

        try:
            if filename is None:
                timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
                filename = f"waveform_{timestamp}.csv"

            dialog_completed = threading.Event()
            file_path_container = [None]

            def show_dialog():
                file_path_container[0] = filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                    initialfile=filename
                )
                dialog_completed.set()

            self.root_window.after(0, show_dialog)
            dialog_completed.wait()

            file_path = file_path_container[0]

            if not file_path:
                return None

            with open(file_path, "w", encoding="utf-8") as file_handle:
                file_handle.write("time_seconds,voltage_volts\n")

                for time_value, voltage_value in zip(time_values, voltage_values):
                    file_handle.write(f"{time_value:.8e},{voltage_value:.6f}\n")

            return file_path
        except:
            return None


    def save_waveform_to_png(self, time_values, voltage_values, filename=None):
        if not time_values or not voltage_values:
            return None

        try:
            if filename is None:
                timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
                filename = f"waveform_{timestamp}.png"

            dialog_completed = threading.Event()
            file_path_container = [None]

            def show_dialog():
                file_path_container[0] = filedialog.asksaveasfilename(
                    defaultextension=".png",
                    filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
                    initialfile=filename
                )
                dialog_completed.set()

            self.root_window.after(0, show_dialog)
            dialog_completed.wait()

            file_path = file_path_container[0]

            if not file_path:
                return None

            plt.figure(figsize=(12, 6))
            plt.plot(time_values, voltage_values, "b-", linewidth=1)
            plt.grid(True, alpha=0.3)
            plt.xlabel("Время, с")
            plt.ylabel("Напряжение, В")
            plt.title(f"Сигнал с осциллографа (канал {self.oscilloscope_channel_variable.get()})")
            plt.tight_layout()
            plt.savefig(file_path, dpi=300, bbox_inches="tight")
            plt.close()

            return file_path
        except:
            return None


    def capture_and_save_waveform(self, averaged=False, average_count=64, format_type="both"):
        def task():
            try:
                time_values, voltage_values = self.capture_waveform(averaged, average_count)

                if time_values is None or voltage_values is None:
                    def show_error():
                        messagebox.showwarning("Предупреждение", "Не удалось захватить сигнал!")
                    self.root_window.after(0, show_error)
                    return

                saved_files = []

                if format_type in ["csv", "both"]:
                    prefix = "averaged" if averaged else "waveform"
                    filename = f"{prefix}_{datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.csv"
                    csv_path = self.save_waveform_to_csv(time_values, voltage_values, filename)

                    if csv_path:
                        saved_files.append(f"CSV: {os.path.basename(csv_path)}")

                if format_type in ["png", "both"]:
                    prefix = "averaged" if averaged else "waveform"
                    filename = f"{prefix}_{datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.png"
                    png_path = self.save_waveform_to_png(time_values, voltage_values, filename)

                    if png_path:
                        saved_files.append(f"PNG: {os.path.basename(png_path)}")

                def show_result():
                    if saved_files:
                        messagebox.showinfo("Успех", f"Файлы сохранены!")
                    else:
                        messagebox.showwarning("Предупреждение", "Файлы не сохранены!")

                self.root_window.after(0, show_result)
            except:
                pass

        threading.Thread(target=task, daemon=True).start()


    def capture_and_save_normal_waveform(self):
        self.capture_and_save_waveform(averaged=False, format_type="both")


    def capture_and_save_averaged_waveform(self):
        average_count = 64

        try:
            if self.oscilloscope_average_spin:
                average_count = int(self.oscilloscope_average_spin.get())
        except:
            average_count = 64

        self.capture_and_save_waveform(averaged=True, average_count=average_count, format_type="both")


    def capture_and_save_normal_waveform_csv(self):
        self.capture_and_save_waveform(averaged=False, format_type="csv")


    def capture_and_save_normal_waveform_png(self):
        self.capture_and_save_waveform(averaged=False, format_type="png")


    def capture_and_save_averaged_waveform_csv(self):
        average_count = 64

        try:
            if self.oscilloscope_average_spin:
                average_count = int(self.oscilloscope_average_spin.get())
        except:
            average_count = 64

        self.capture_and_save_waveform(averaged=True, average_count=average_count, format_type="csv")


    def capture_and_save_averaged_waveform_png(self):
        average_count = 64

        try:
            if self.oscilloscope_average_spin:
                average_count = int(self.oscilloscope_average_spin.get())
        except:
            average_count = 64

        self.capture_and_save_waveform(averaged=True, average_count=average_count, format_type="png")


    def refresh_energymeter_power(self):
        if self.energymeter_connected:
            try:
                power = self.energymeter_device.get_power()
                self._safe_label_configuration(self.status_labels.get("energymeter_power"), text=f"{power:.6e} Вт")
            except:
                pass


    def measure_average_energymeter_power(self):
        if not self.energymeter_connected:
            return

        def task():
            try:
                count = int(self.status_labels.get("energymeter_average_count", tk.StringVar(value="10")).get())
                average = self.energymeter_device.get_average_power(count, 0.1)
                self._safe_label_configuration(self.status_labels.get("energymeter_average_power"), text=f"{average:.6e} Вт")
            except:
                pass

        threading.Thread(target=task, daemon=True).start()


    def increase_energymeter_scale(self):
        if self.energymeter_connected:
            try:
                self.energymeter_device.set_scale_up()
                self.update_energymeter_status()
            except:
                pass


    def decrease_energymeter_scale(self):
        if self.energymeter_connected:
            try:
                self.energymeter_device.set_scale_down()
                self.update_energymeter_status()
            except:
                pass


    def set_energymeter_scale(self, entry):
        if not self.energymeter_connected:
            return

        def task():
            scale_index = self._safe_get_int(entry, min_value=0, max_value=41, error_message="Введите число от 0 до 41!")
            if scale_index is None:
                return
            self.energymeter_device.set_scale(scale_index)
            self.update_energymeter_status()

        threading.Thread(target=task, daemon=True).start()


    def enable_energymeter_autoscale(self):
        if self.energymeter_connected:
            try:
                self.energymeter_device.set_autoscale(True)
                self.update_energymeter_status()
            except:
                pass


    def disable_energymeter_autoscale(self):
        if self.energymeter_connected:
            try:
                self.energymeter_device.set_autoscale(False)
                self.update_energymeter_status()
            except:
                pass


    def set_energymeter_wavelength(self, entry):
        if not self.energymeter_connected:
            return

        def task():
            wavelength = self._safe_get_int(entry, min_value=0, error_message="Введите корректное число для длины волны (нм)!")
            if wavelength is None:
                return
            self.energymeter_device.set_wavelength_nanometers(wavelength)
            self.update_energymeter_status()

        threading.Thread(target=task, daemon=True).start()


    def zero_energymeter(self):
        if self.energymeter_connected:
            try:
                self.energymeter_device.set_zero_offset()
                self.update_energymeter_status()
            except:
                pass


    def set_energymeter_trigger_level(self, entry):
        if not self.energymeter_connected:
            return

        def task():
            level = self._safe_get_float(entry, min_value=0.1, max_value=99.9, error_message="Введите число от 0.1 до 99.9!")

            if level is None:
                return

            self.energymeter_device.set_trigger_level(level)
            self.update_energymeter_status()

        threading.Thread(target=task, daemon=True).start()


    def create_centered_frame(self, parent, title):
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        top_spacer = ttk.Frame(container, height=0)
        top_spacer.pack(fill=tk.BOTH, expand=True)

        frame = ttk.LabelFrame(container, text=title, padding=10)
        frame.pack(fill=tk.NONE, expand=False, padx=10, pady=10)

        bottom_spacer = ttk.Frame(container, height=0)
        bottom_spacer.pack(fill=tk.BOTH, expand=True)

        return frame


    def create_chromator_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = self.create_centered_frame(tab, "Монохроматор:")

        connection_frame = ttk.Frame(main_frame)
        connection_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(connection_frame)
        center.pack(anchor="center")

        connect_button = ttk.Button(center, text="Подключить", width=16)
        disconnect_button = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        connect_button.pack(side=tk.LEFT, padx=5)
        disconnect_button.pack(side=tk.LEFT, padx=5)

        self.control_buttons["chromator_connect"] = connect_button
        self.control_buttons["chromator_disconnect"] = disconnect_button
        self.control_buttons["chromator"] = [disconnect_button]

        connect_button.config(command=self.connect_chromator)
        disconnect_button.config(command=self.disconnect_chromator)

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
        self.status_labels["chromator_grating"] = ttk.Label(grid, text="---")
        self.status_labels["chromator_grating"].grid(row=5, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Всего решёток:").grid(row=6, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["chromator_grating_count"] = ttk.Label(grid, text="---")
        self.status_labels["chromator_grating_count"].grid(row=6, column=1, sticky="w", padx=5, pady=2)

        control_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=0)
        control_frame.columnconfigure(2, weight=0)

        ttk.Label(control_frame, text="Длина волны (нм):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        wavelength_entry = ttk.Entry(control_frame, width=16)
        wavelength_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_chromator_wavelength(wavelength_entry)).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Входная щель (мкм):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        input_entry = ttk.Entry(control_frame, width=16)
        input_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_chromator_input_slit(input_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Выходная щель (мкм):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        output_entry = ttk.Entry(control_frame, width=16)
        output_entry.grid(row=2, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_chromator_output_slit(output_entry)).grid(row=2, column=2, padx=5, pady=2)

        shutter_frame = ttk.Frame(control_frame)
        shutter_frame.grid(row=3, column=0, columnspan=3, pady=5)
        shutter_center = ttk.Frame(shutter_frame)
        shutter_center.pack(anchor="center")
        ttk.Button(shutter_center, text="Открыть затвор", width=16, command=self.open_chromator_shutter).pack(side=tk.LEFT, padx=5)
        ttk.Button(shutter_center, text="Закрыть затвор", width=16, command=self.close_chromator_shutter).pack(side=tk.LEFT, padx=5)

        grating_frame = ttk.Frame(control_frame)
        grating_frame.grid(row=4, column=0, columnspan=3, pady=5)
        grating_center = ttk.Frame(grating_frame)
        grating_center.pack(anchor="center")
        ttk.Label(grating_center, text="Номер решётки:").pack(side=tk.LEFT, padx=5)
        grating_spinbox = ttk.Spinbox(grating_center, from_=0, to=10, width=12)
        grating_spinbox.pack(side=tk.LEFT, padx=5)
        ttk.Button(grating_center, text="Выбрать", width=12, command=lambda: self.set_chromator_grating(grating_spinbox)).pack(side=tk.LEFT, padx=5)
        ttk.Button(grating_center, text="Сброс", width=12, command=self.reset_chromator_grating).pack(side=tk.LEFT, padx=5)

        filter_frame = ttk.Frame(control_frame)
        filter_frame.grid(row=5, column=0, columnspan=3, pady=5)
        filter_center = ttk.Frame(filter_frame)
        filter_center.pack(anchor="center")
        ttk.Label(filter_center, text="Фильтр:").pack(side=tk.LEFT, padx=5)
        filter_combobox = ttk.Combobox(filter_center, values=["Без фильтра", "Фильтр 1", "Фильтр 2"], width=20, state="readonly")
        filter_combobox.set("Без фильтра")
        filter_combobox.pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_center, text="Установить", width=14, command=lambda: self.set_chromator_filter(filter_combobox)).pack(side=tk.LEFT, padx=5)

        mirror_frame = ttk.Frame(control_frame)
        mirror_frame.grid(row=6, column=0, columnspan=3, pady=5)
        mirror_center = ttk.Frame(mirror_frame)
        mirror_center.pack(anchor="center")
        ttk.Label(mirror_center, text="Выходной порт:").pack(side=tk.LEFT, padx=5)
        mirror_combobox = ttk.Combobox(mirror_center, values=["Осевой", "Боковой"], width=15, state="readonly")
        mirror_combobox.set("Осевой")
        mirror_combobox.pack(side=tk.LEFT, padx=5)
        ttk.Button(mirror_center, text="Установить", width=14, command=lambda: self.set_chromator_mirror(mirror_combobox)).pack(side=tk.LEFT, padx=5)

        return tab


    def create_laser_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = self.create_centered_frame(tab, "Лазер:")

        connection_frame = ttk.Frame(main_frame)
        connection_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(connection_frame)
        center.pack(anchor="center")

        connect_button = ttk.Button(center, text="Подключить", width=16)
        disconnect_button = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        connect_button.pack(side=tk.LEFT, padx=5)
        disconnect_button.pack(side=tk.LEFT, padx=5)

        self.control_buttons["laser_connect"] = connect_button
        self.control_buttons["laser_disconnect"] = disconnect_button
        self.control_buttons["laser"] = [disconnect_button]

        connect_button.config(command=self.connect_laser)
        disconnect_button.config(command=self.disconnect_laser)

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

        control_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=0)
        control_frame.columnconfigure(2, weight=0)

        ttk.Label(control_frame, text="Длина волны (нм):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        wavelength_entry = ttk.Entry(control_frame, width=16)
        wavelength_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_laser_wavelength(wavelength_entry)).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Абсолютное положение (шаги):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        absolute_entry = ttk.Entry(control_frame, width=16)
        absolute_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_laser_absolute_position(absolute_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Относительное смещение (шаги):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        relative_entry = ttk.Entry(control_frame, width=16)
        relative_entry.grid(row=2, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Переместить", width=14, command=lambda: self.set_laser_relative_position(relative_entry)).grid(row=2, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Скорость (шаги/с):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        speed_entry = ttk.Entry(control_frame, width=16)
        speed_entry.grid(row=3, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_laser_speed(speed_entry)).grid(row=3, column=2, padx=5, pady=2)

        motor_frame = ttk.Frame(control_frame)
        motor_frame.grid(row=4, column=0, columnspan=3, pady=5)
        motor_center = ttk.Frame(motor_frame)
        motor_center.pack(anchor="center")
        ttk.Button(motor_center, text="Включить двигатель", width=24, command=self.enable_laser_motor).pack(side=tk.LEFT, padx=5)
        ttk.Button(motor_center, text="Отключить двигатель", width=24, command=self.disable_laser_motor).pack(side=tk.LEFT, padx=5)

        shutter_frame = ttk.Frame(control_frame)
        shutter_frame.grid(row=5, column=0, columnspan=3, pady=5)
        shutter_center = ttk.Frame(shutter_frame)
        shutter_center.pack(anchor="center")
        ttk.Button(shutter_center, text="Открыть затвор", width=16, command=self.open_laser_shutter).pack(side=tk.LEFT, padx=5)
        ttk.Button(shutter_center, text="Закрыть затвор", width=16, command=self.close_laser_shutter).pack(side=tk.LEFT, padx=5)

        reset_frame = ttk.Frame(control_frame)
        reset_frame.grid(row=6, column=0, columnspan=3, pady=5)
        reset_center = ttk.Frame(reset_frame)
        reset_center.pack(anchor="center")
        ttk.Button(reset_center, text="Сброс", width=18, command=self.reset_laser).pack(side=tk.LEFT, padx=5)

        return tab


    def create_oscilloscope_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = self.create_centered_frame(tab, "Осциллограф:")

        connection_frame = ttk.Frame(main_frame)
        connection_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(connection_frame)
        center.pack(anchor="center")

        connect_button = ttk.Button(center, text="Подключить", width=16)
        disconnect_button = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        connect_button.pack(side=tk.LEFT, padx=5)
        disconnect_button.pack(side=tk.LEFT, padx=5)

        self.control_buttons["oscilloscope_connect"] = connect_button
        self.control_buttons["oscilloscope_disconnect"] = disconnect_button
        self.control_buttons["oscilloscope"] = [disconnect_button]

        connect_button.config(command=self.connect_oscilloscope)
        disconnect_button.config(command=self.disconnect_oscilloscope)

        status_frame = ttk.LabelFrame(main_frame, text="Состояние:", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        grid = ttk.Frame(status_frame)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.status_labels["oscilloscope_status"] = ttk.Label(grid, text="Отключен", foreground="black")
        self.status_labels["oscilloscope_status"].grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Номер канала:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.oscilloscope_channel_variable = tk.StringVar(value="1")
        channel_combobox = ttk.Combobox(grid, textvariable=self.oscilloscope_channel_variable, values=["1", "2", "3", "4"], width=14, state="readonly")
        channel_combobox.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        channel_combobox.bind("<<ComboboxSelected>>", lambda event: self.update_oscilloscope_status())

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

        ttk.Label(grid, text="Количество кадров:").grid(row=8, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["oscilloscope_average"] = ttk.Label(grid, text="---")
        self.status_labels["oscilloscope_average"].grid(row=8, column=1, sticky="w", padx=5, pady=2)

        control_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=0)
        control_frame.columnconfigure(2, weight=0)

        ttk.Label(control_frame, text="Вертикальный масштаб (В/дел):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        scale_entry = ttk.Entry(control_frame, width=16)
        scale_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_scale(scale_entry)).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Вертикальное смещение (В):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        offset_entry = ttk.Entry(control_frame, width=16)
        offset_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_offset(offset_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Тип связи:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        coupling_combobox = ttk.Combobox(control_frame, values=["DC", "AC", "GND"], width=14, state="readonly")
        coupling_combobox.set("DC")
        coupling_combobox.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_coupling(coupling_combobox)).grid(row=2, column=2, padx=5, pady=2)

        channel_frame = ttk.Frame(control_frame)
        channel_frame.grid(row=3, column=0, columnspan=3, pady=5)
        channel_center = ttk.Frame(channel_frame)
        channel_center.pack(anchor="center")
        ttk.Button(channel_center, text="Включить канал", width=18, command=self.enable_oscilloscope_channel).pack(side=tk.LEFT, padx=5)
        ttk.Button(channel_center, text="Отключить канал", width=18, command=self.disable_oscilloscope_channel).pack(side=tk.LEFT, padx=5)

        ttk.Label(control_frame, text="Горизонтальный масштаб (с/дел):").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        timebase_entry = ttk.Entry(control_frame, width=16)
        timebase_entry.grid(row=4, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_timebase(timebase_entry)).grid(row=4, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Количество кадров:").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        average_entry = ttk.Entry(control_frame, width=16)
        average_entry.grid(row=5, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_average_count(average_entry)).grid(row=5, column=2, padx=5, pady=2)

        trigger_frame = ttk.LabelFrame(control_frame, text="Триггер:", padding=5)
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
        trigger_level_entry = ttk.Entry(trigger_frame, width=16)
        trigger_level_entry.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(trigger_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_trigger_level(trigger_level_entry)).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(trigger_frame, text="Наклон:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        trigger_slope = ttk.Combobox(trigger_frame, values=["POS", "NEG", "EITH"], width=14, state="readonly")
        trigger_slope.set("POS")
        trigger_slope.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(trigger_frame, text="Установить", width=14, command=lambda: self.set_oscilloscope_trigger_slope(trigger_slope)).grid(row=2, column=2, padx=5, pady=2)

        impedance_frame = ttk.Frame(control_frame)
        impedance_frame.grid(row=7, column=0, columnspan=3, pady=5)
        impedance_center = ttk.Frame(impedance_frame)
        impedance_center.pack(anchor="center")
        ttk.Label(impedance_center, text="Импеданс:").pack(side=tk.LEFT, padx=5)
        impedance_combobox = ttk.Combobox(impedance_center, values=["1 МОм", "50 Ом"], width=12, state="readonly")
        impedance_combobox.set("1 МОм")
        impedance_combobox.pack(side=tk.LEFT, padx=5)
        ttk.Button(impedance_center, text="Установить", width=14, command=lambda: self.set_oscilloscope_impedance(impedance_combobox)).pack(side=tk.LEFT, padx=5)

        acquisition_frame = ttk.Frame(control_frame)
        acquisition_frame.grid(row=8, column=0, columnspan=3, pady=5)
        acquisition_center = ttk.Frame(acquisition_frame)
        acquisition_center.pack(anchor="center")
        ttk.Button(acquisition_center, text="Запустить", width=14, command=self.run_oscilloscope_acquisition).pack(side=tk.LEFT, padx=5)
        ttk.Button(acquisition_center, text="Остановить", width=14, command=self.stop_oscilloscope_acquisition).pack(side=tk.LEFT, padx=5)
        ttk.Button(acquisition_center, text="Однократно", width=14, command=self.single_oscilloscope_acquisition).pack(side=tk.LEFT, padx=5)
        ttk.Button(acquisition_center, text="Принудить", width=14, command=self.force_oscilloscope_trigger).pack(side=tk.LEFT, padx=5)

        capture_frame = ttk.LabelFrame(main_frame, text="Сигнал:", padding=10)
        capture_frame.pack(fill=tk.X, pady=5)

        average_frame = ttk.Frame(capture_frame)
        average_frame.pack(fill=tk.X, pady=2)
        average_center = ttk.Frame(average_frame)
        average_center.pack(anchor="center")
        ttk.Label(average_center, text="Число кадров для усреднения:").pack(side=tk.LEFT, padx=5)
        self.oscilloscope_average_spin = ttk.Spinbox(average_center, from_=2, to=65536, width=10, increment=1)
        self.oscilloscope_average_spin.set("64")
        self.oscilloscope_average_spin.pack(side=tk.LEFT, padx=5)

        normal_capture_frame = ttk.Frame(capture_frame)
        normal_capture_frame.pack(fill=tk.X, pady=2)
        normal_capture_center = ttk.Frame(normal_capture_frame)
        normal_capture_center.pack(anchor="center")
        ttk.Label(normal_capture_center, text="Обычный:").pack(side=tk.LEFT, padx=5)
        ttk.Button(normal_capture_center, text="Данные", width=10, command=self.capture_and_save_normal_waveform_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(normal_capture_center, text="График", width=10, command=self.capture_and_save_normal_waveform_png).pack(side=tk.LEFT, padx=2)
        ttk.Button(normal_capture_center, text="Вместе", width=10, command=self.capture_and_save_normal_waveform).pack(side=tk.LEFT, padx=2)

        averaged_capture_frame = ttk.Frame(capture_frame)
        averaged_capture_frame.pack(fill=tk.X, pady=2)
        averaged_capture_center = ttk.Frame(averaged_capture_frame)
        averaged_capture_center.pack(anchor="center")
        ttk.Label(averaged_capture_center, text="Усреднённый:").pack(side=tk.LEFT, padx=5)
        ttk.Button(averaged_capture_center, text="Данные", width=10, command=self.capture_and_save_averaged_waveform_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(averaged_capture_center, text="График", width=10, command=self.capture_and_save_averaged_waveform_png).pack(side=tk.LEFT, padx=2)
        ttk.Button(averaged_capture_center, text="Вместе", width=10, command=self.capture_and_save_averaged_waveform).pack(side=tk.LEFT, padx=2)

        return tab


    def create_energymeter_tab(self, parent):
        tab = ttk.Frame(parent)
        main_frame = self.create_centered_frame(tab, "Энергометр:")

        connection_frame = ttk.Frame(main_frame)
        connection_frame.pack(fill=tk.X, pady=5)
        center = ttk.Frame(connection_frame)
        center.pack(anchor="center")

        connect_button = ttk.Button(center, text="Подключить", width=16)
        disconnect_button = ttk.Button(center, text="Отключить", width=16, state=tk.DISABLED)
        connect_button.pack(side=tk.LEFT, padx=5)
        disconnect_button.pack(side=tk.LEFT, padx=5)

        self.control_buttons["energymeter_connect"] = connect_button
        self.control_buttons["energymeter_disconnect"] = disconnect_button
        self.control_buttons["energymeter"] = [disconnect_button]

        connect_button.config(command=self.connect_energymeter)
        disconnect_button.config(command=self.disconnect_energymeter)

        status_frame = ttk.LabelFrame(main_frame, text="Состояние:", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        grid = ttk.Frame(status_frame)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=0)

        self.status_labels["energymeter_status"] = ttk.Label(grid, text="Отключен", foreground="black")
        self.status_labels["energymeter_status"].grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Мощность:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["energymeter_power"] = ttk.Label(grid, text="--- Вт")
        self.status_labels["energymeter_power"].grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(grid, text="Обновить", width=14, command=self.refresh_energymeter_power).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(grid, text="Количество измерений:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["energymeter_average_count"] = tk.StringVar(value="10")
        average_spinbox = ttk.Spinbox(grid, from_=1, to=100, width=14, textvariable=self.status_labels["energymeter_average_count"])
        average_spinbox.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Средняя мощность:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["energymeter_average_power"] = ttk.Label(grid, text="--- Вт")
        self.status_labels["energymeter_average_power"].grid(row=3, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(grid, text="Измерить", width=14, command=self.measure_average_energymeter_power).grid(row=3, column=2, padx=5, pady=2)

        ttk.Label(grid, text="Индекс шкалы:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["energymeter_scale"] = ttk.Label(grid, text="---")
        self.status_labels["energymeter_scale"].grid(row=4, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Автошкала:").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["energymeter_autoscale"] = ttk.Label(grid, text="---")
        self.status_labels["energymeter_autoscale"].grid(row=5, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(grid, text="Длина волны:").grid(row=6, column=0, sticky="w", padx=5, pady=2)
        self.status_labels["energymeter_wavelength"] = ttk.Label(grid, text="--- нм")
        self.status_labels["energymeter_wavelength"].grid(row=6, column=1, sticky="w", padx=5, pady=2)

        control_frame = ttk.LabelFrame(main_frame, text="Управление:", padding=10)
        control_frame.pack(fill=tk.X, pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=0)
        control_frame.columnconfigure(2, weight=0)

        scale_button_frame = ttk.Frame(control_frame)
        scale_button_frame.grid(row=0, column=0, columnspan=3, pady=5)
        scale_center = ttk.Frame(scale_button_frame)
        scale_center.pack(anchor="center")
        ttk.Button(scale_center, text="Увеличить шкалу", width=24, command=self.increase_energymeter_scale).pack(side=tk.LEFT, padx=5)
        ttk.Button(scale_center, text="Уменьшить шкалу", width=24, command=self.decrease_energymeter_scale).pack(side=tk.LEFT, padx=5)

        ttk.Label(control_frame, text="Индекс шкалы (0-41):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        scale_entry = ttk.Entry(control_frame, width=16)
        scale_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_energymeter_scale(scale_entry)).grid(row=1, column=2, padx=5, pady=2)

        autoscale_button_frame = ttk.Frame(control_frame)
        autoscale_button_frame.grid(row=2, column=0, columnspan=3, pady=5)
        autoscale_center = ttk.Frame(autoscale_button_frame)
        autoscale_center.pack(anchor="center")
        ttk.Button(autoscale_center, text="Включить автошкалу", width=24, command=self.enable_energymeter_autoscale).pack(side=tk.LEFT, padx=5)
        ttk.Button(autoscale_center, text="Отключить автошкалу", width=24, command=self.disable_energymeter_autoscale).pack(side=tk.LEFT, padx=5)

        ttk.Label(control_frame, text="Длина волны (нм):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        wavelength_entry = ttk.Entry(control_frame, width=16)
        wavelength_entry.grid(row=3, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_energymeter_wavelength(wavelength_entry)).grid(row=3, column=2, padx=5, pady=2)

        ttk.Label(control_frame, text="Уровень триггера (%):").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        trigger_entry = ttk.Entry(control_frame, width=16)
        trigger_entry.grid(row=4, column=1, sticky="e", padx=5, pady=2)
        ttk.Button(control_frame, text="Установить", width=14, command=lambda: self.set_energymeter_trigger_level(trigger_entry)).grid(row=4, column=2, padx=5, pady=2)

        zero_frame = ttk.Frame(control_frame)
        zero_frame.grid(row=5, column=0, columnspan=3, pady=5)
        zero_center = ttk.Frame(zero_frame)
        zero_center.pack(anchor="center")
        ttk.Button(zero_center, text="Обнулить", width=18, command=self.zero_energymeter).pack(side=tk.LEFT, padx=5)

        return tab


    def initialize_user_interface(self):
        self.root_window = tk.Tk()
        self.root_window.title("Управление оборудованием")
        self.root_window.geometry("700x1000")
        self.root_window.resizable(False, False)

        icon_path = self.base_path / "icon.png"

        if icon_path.exists():
            try:
                icon = tk.PhotoImage(file=str(icon_path))
                self.root_window.iconphoto(True, icon)
            except:
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

        notebook.add(self.create_chromator_tab(notebook), text="Монохроматор")
        notebook.add(self.create_laser_tab(notebook), text="Лазер")
        notebook.add(self.create_oscilloscope_tab(notebook), text="Осциллограф")
        notebook.add(self.create_energymeter_tab(notebook), text="Энергометр")

        self.start_auto_update()

        self.root_window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root_window.mainloop()


    def on_closing(self):
        self.stop_auto_update()
        self.disconnect_all_devices()
        self.root_window.destroy()


if __name__ == "__main__":
    is_first_instance, lock_file = check_single_instance()

    if not is_first_instance:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Ошибка", "Программа уже запущена!")
            root.destroy()
        except:
            pass

        sys.exit(0)

    try:
        application = DeviceManager()
        application.initialize_user_interface()
    finally:
        if lock_file and lock_file.exists():
            try:
                lock_file.unlink()
            except:
                pass
