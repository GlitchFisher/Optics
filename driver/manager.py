import os
import sys
import time
import ctypes
import winreg
import tkinter
import usb.core
import usb.util
import threading
import subprocess

from tkinter import ttk
from pathlib import Path


CREATE_NO_WINDOW = 0x08000000


class DriverManager:
    def __init__(self):
        if getattr(sys, "frozen", False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent

        self.drivers_path = base_path
        self.root_window = None
        self.operation_lock = threading.Lock()
        self.operation_in_progress = False

        self.devices_configuration = [
            {
                "device_name": "Монохроматор",
                "service_name": "cyusb",
                "system_file": "cyusb.sys",
                "identifiers": "USB\\VID_0547&PID_1005",
                "class_name": "USB",
                "class_guid": "{36FC9E60-C465-11CF-8056-444553540000}"
            },
            {
                "device_name": "Энергометр (шина)",
                "service_name": "ftdibus",
                "system_file": "ftdibus.sys",
                "identifiers": "USB\\VID_0403&PID_6011",
                "class_name": "USB",
                "class_guid": "{36FC9E60-C465-11CF-8056-444553540000}"
            },
            {
                "device_name": "Энергометр (порт)",
                "service_name": "ftdiport",
                "system_file": "ftdiport.sys",
                "identifiers": "USB\\VID_0403&PID_6011&MI_00",
                "class_name": "Ports",
                "class_guid": "{4d36e978-e325-11ce-bfc1-08002be10318}"
            },
            {
                "device_name": "Лазерное излучение",
                "service_name": "ser2pl",
                "system_file": "ser2pl.sys",
                "identifiers": "USB\\VID_067B&PID_2303",
                "class_name": "Ports",
                "class_guid": "{4d36e978-e325-11ce-bfc1-08002be10318}"
            },
            {
                "device_name": "Осциллограф",
                "service_name": "usbtmc",
                "system_file": "usbtmc.sys",
                "identifiers": "USB\\VID_0957&PID_1796",
                "class_name": "USBTestAndMeasurementDevice",
                "class_guid": "{a9fdbb24-128a-11d5-9961-00108335e361}"
            }
        ]


    def running_as_admin(self):
        try:
            status = ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            status = False

        return status


    def restart_as_admin(self):
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{sys.argv[0]}"', None, 1)
        time.sleep(1)
        sys.exit(0)


    def file_exists_in_system32(self, file_name):
        old_redirection_value = ctypes.c_void_p()

        try:
            ctypes.windll.kernel32.Wow64DisableWow64FsRedirection(ctypes.byref(old_redirection_value))
            full_path = f"C:\\Windows\\System32\\drivers\\{file_name}"

            return os.path.exists(full_path)
        finally:
            ctypes.windll.kernel32.Wow64RevertWow64FsRedirection(old_redirection_value)


    def check_driver_installation(self, device):
        if not self.file_exists_in_system32(device["system_file"]):
            return False

        try:
            registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"SYSTEM\\CurrentControlSet\\Services\\{device['service_name']}")
            winreg.CloseKey(registry_key)

            return True
        except FileNotFoundError:
            return False


    def copy_file_using_windows_api(self, source_path, destination_path, log_widget):
        old_redirection_value = ctypes.c_void_p()

        try:
            ctypes.windll.kernel32.Wow64DisableWow64FsRedirection(ctypes.byref(old_redirection_value))

            if not os.path.exists(source_path):
                log_widget.insert(tkinter.END, f"❌ Файл не найден!\n")
                log_widget.see(tkinter.END)

                return False

            copy_result = ctypes.windll.kernel32.CopyFileW(source_path, destination_path, 0)

            if copy_result:
                if self.file_exists_in_system32(os.path.basename(destination_path)):
                    return True
                else:
                    log_widget.insert(tkinter.END, f"❌ Файл не скопирован\n")
                    log_widget.see(tkinter.END)

                    return False
            else:
                error_code = ctypes.windll.kernel32.GetLastError()
                error_message = self.get_windows_error_message(error_code)
                log_widget.insert(tkinter.END, f"❌ Ошибка копирования:\n")
                log_widget.insert(tkinter.END, f"{error_message}\n")
                log_widget.see(tkinter.END)

                return False
        except Exception as error:
            log_widget.insert(tkinter.END, f"❌ Ошибка: {error}\n")
            log_widget.see(tkinter.END)

            return False
        finally:
            ctypes.windll.kernel32.Wow64RevertWow64FsRedirection(old_redirection_value)


    def get_windows_error_message(self, error_code):
        try:
            buffer = ctypes.create_unicode_buffer(256)
            ctypes.windll.kernel32.FormatMessageW(0x00001000, None, error_code, 0, buffer, 256, None)

            return buffer.value.strip()
        except Exception:
            return f"Неизвестная ошибка"


    def run_pnputil(self, arguments):
        old_redirection_value = ctypes.c_void_p()

        try:
            ctypes.windll.kernel32.Wow64DisableWow64FsRedirection(ctypes.byref(old_redirection_value))
            result = subprocess.run([r"C:\Windows\System32\pnputil.exe"] + arguments, capture_output=True, creationflags=CREATE_NO_WINDOW)

            return result
        finally:
            ctypes.windll.kernel32.Wow64RevertWow64FsRedirection(old_redirection_value)


    def check_and_install_winusb_auto(self, log_widget):
        try:
            usbtmc_devices = []

            for devices in usb.core.find(find_all=True):
                try:
                    if devices.bDeviceClass == 0xFE:
                        usbtmc_devices.append(devices)
                except:
                    continue

            if not usbtmc_devices:
                log_widget.insert(tkinter.END, f"✅ Устройства не найдены!\n")
                log_widget.see(tkinter.END)

                return False

            log_widget.insert(tkinter.END, f"✅ Найдено {len(usbtmc_devices)} устройств!\n")
            log_widget.see(tkinter.END)

            need_install = False

            for devices in usbtmc_devices:
                try:
                    devices.get_active_configuration()
                    log_widget.insert(tkinter.END, f"✅ Драйвер устройства правильный!\n")
                    log_widget.see(tkinter.END)
                except usb.core.USBError:
                    need_install = True
                    log_widget.insert(tkinter.END, f"⚠️ Драйвер устройства неправильный!\n")
                    log_widget.see(tkinter.END)
                except:
                    continue

            if not need_install:
                log_widget.insert(tkinter.END, f"✅ Все устройства уже настроены!\n")
                log_widget.see(tkinter.END)

                return True

            log_widget.insert(tkinter.END, f"✅ Установка драйвера для устройств...\n")
            log_widget.see(tkinter.END)

            if getattr(sys, "frozen", False):
                kernel_path = Path(sys._MEIPASS) / "kernel"
            else:
                kernel_path = self.drivers_path / "kernel"

            zadig_path = kernel_path / "zadig.exe"

            if not zadig_path.exists():
                log_widget.insert(tkinter.END, f"❌ Утилита не найдена!\n")
                log_widget.see(tkinter.END)

                return False

            result = subprocess.run([str(zadig_path), "/install", "/silent", "/class", "FE", "/subclass", "03", "/driver", "libusb-win32"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)

            if result.returncode == 0:
                log_widget.insert(tkinter.END, f"✅ Нужный драйвер установлен!\n")
                log_widget.see(tkinter.END)
                log_widget.insert(tkinter.END, f"⚠️ Переподключите осциллограф!\n")
                log_widget.see(tkinter.END)

                return True
            else:
                log_widget.insert(tkinter.END, f"❌ Ошибка установки драйвера!\n")
                log_widget.see(tkinter.END)

                return False

        except Exception:
            log_widget.insert(tkinter.END, f"❌ Общая ошибка!\n")
            log_widget.see(tkinter.END)

            return False


    def install_device_driver(self, device, log_widget):
        kernel_path = self.drivers_path / "kernel"

        if not kernel_path.exists():
            log_widget.insert(tkinter.END, f"❌ Папка не найдена!\n")
            log_widget.see(tkinter.END)

            return False

        source_file_path = str((kernel_path / device["system_file"]).absolute())
        destination_file_path = f"C:\\Windows\\System32\\drivers\\{device['system_file']}"

        copy_success = self.copy_file_using_windows_api(source_file_path, destination_file_path, log_widget)

        if not copy_success:
            return False

        service_registry_path = f"SYSTEM\\CurrentControlSet\\Services\\{device['service_name']}"

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, service_registry_path)
        except Exception:
            pass

        try:
            registry_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, service_registry_path)
            winreg.SetValueEx(registry_key, "Type", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(registry_key, "Start", 0, winreg.REG_DWORD, 3)
            winreg.SetValueEx(registry_key, "ErrorControl", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(registry_key, "ImagePath", 0, winreg.REG_EXPAND_SZ, f"\\SystemRoot\\System32\\drivers\\{device['system_file']}")
            winreg.CloseKey(registry_key)
        except Exception as error:
            log_widget.insert(tkinter.END, f"❌ Ошибка регистрации службы!\n")
            log_widget.see(tkinter.END)

            return False

        enum_path = device["identifiers"].replace("\\", "#")
        device_key_path = f"SYSTEM\\CurrentControlSet\\Enum\\{enum_path}\\0"
        enum_parent_path = f"SYSTEM\\CurrentControlSet\\Enum\\{enum_path}"

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, device_key_path)
        except Exception:
            pass

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, enum_parent_path)
        except Exception:
            pass

        try:
            registry_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, enum_parent_path)
            winreg.CloseKey(registry_key)

            registry_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, device_key_path)
            winreg.SetValueEx(registry_key, "Service", 0, winreg.REG_SZ, device["service_name"])
            winreg.SetValueEx(registry_key, "Class", 0, winreg.REG_SZ, device["class_name"])
            winreg.SetValueEx(registry_key, "ClassGUID", 0, winreg.REG_SZ, device["class_guid"])
            winreg.CloseKey(registry_key)
        except Exception as error:
            log_widget.insert(tkinter.END, f"❌ Ошибка регистрации устройства!\n")
            log_widget.see(tkinter.END)

            return False

        self.run_pnputil(["/scan-devices"])

        log_widget.insert(tkinter.END, f"✅ {device['device_name']}: установлен!\n")
        log_widget.see(tkinter.END)

        return True


    def stop_driver_service(self, service_name):
        try:
            subprocess.run(["sc", "stop", service_name], capture_output=True, creationflags=CREATE_NO_WINDOW)
            time.sleep(1)
        except:
            pass


    def remove_device_by_hardware_id(self, hardware_id):
        try:
            subprocess.run(["pnputil", "/remove-device", hardware_id], capture_output=True, creationflags=CREATE_NO_WINDOW)
            time.sleep(1)
        except:
            pass


    def uninstall_device_driver(self, device, log_widget):
        log_widget.insert(tkinter.END, f"  ⏹️ Остановка службы...\n")
        self.stop_driver_service(device["service_name"])
        log_widget.see(tkinter.END)

        log_widget.insert(tkinter.END, f"  ⚡ Отключение устройства...\n")
        self.remove_device_by_hardware_id(device["identifiers"])
        log_widget.see(tkinter.END)

        log_widget.insert(tkinter.END, f"  ❌ Удаление из списка...\n")
        enum_path = device["identifiers"].replace("\\", "#")

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, f"SYSTEM\\CurrentControlSet\\Enum\\{enum_path}\\0")
        except:
            pass

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, f"SYSTEM\\CurrentControlSet\\Enum\\{enum_path}")
        except:
            pass

        log_widget.see(tkinter.END)

        log_widget.insert(tkinter.END, f"  ✂️ Удаление службы...\n")

        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, f"SYSTEM\\CurrentControlSet\\Services\\{device['service_name']}")
        except:
            pass

        log_widget.see(tkinter.END)

        log_widget.insert(tkinter.END, f"  ❌ Удаление {device['system_file']}...\n")
        file_path = f"C:\\Windows\\System32\\drivers\\{device['system_file']}"
        old_redirection = ctypes.c_void_p()

        try:
            ctypes.windll.kernel32.Wow64DisableWow64FsRedirection(ctypes.byref(old_redirection))

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    log_widget.insert(tkinter.END, f"  ✅ Файл удалён!\n")
                except Exception:
                    log_widget.insert(tkinter.END, f"  ⚠️ Принудительное удаление...\n")

                    try:
                        subprocess.run(["takeown", "/f", file_path], capture_output=True, creationflags=CREATE_NO_WINDOW)
                        subprocess.run(["icacls", file_path, "/grant", "*S-1-5-32-544:F"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                        os.remove(file_path)
                        log_widget.insert(tkinter.END, f"  ✅ Файл принудительно удалён!\n")
                    except Exception:
                        log_widget.insert(tkinter.END, f"  ❌ Не удалось удалить файл!\n")
            else:
                log_widget.insert(tkinter.END, f"  ⚠️ Файл не найден!\n")
        finally:
            ctypes.windll.kernel32.Wow64RevertWow64FsRedirection(old_redirection)

        log_widget.see(tkinter.END)

        log_widget.insert(tkinter.END, f"  ⭕ Обновление списка...\n")
        self.run_pnputil(["/scan-devices"])
        log_widget.see(tkinter.END)

        if self.check_driver_installation(device):
            log_widget.insert(tkinter.END, f"  ⚠️ {device['device_name']}: не удалён!\n")
            log_widget.see(tkinter.END)

            return False
        else:
            log_widget.insert(tkinter.END, f"  ✅ {device['device_name']}: удалён!\n")
            log_widget.see(tkinter.END)

            return True


    def refresh_driver_status(self, status_tree):
        for row in status_tree.get_children():
            status_tree.delete(row)

        for device in self.devices_configuration:
            is_installed = self.check_driver_installation(device)
            status_text = "✅ Установлен" if is_installed else "❌ Не установлен"
            status_tree.insert("", tkinter.END, values=(device["device_name"], status_text))


    def install_all_drivers(self, log_widget, progress_bar, buttons, status_tree):
        with self.operation_lock:
            self.operation_in_progress = True

            try:
                for button in buttons:
                    button.config(state=tkinter.DISABLED)

                log_widget.insert(tkinter.END, "\nНачало установки драйверов...\n")
                log_widget.see(tkinter.END)

                progress_bar["maximum"] = len(self.devices_configuration)

                for index, device in enumerate(self.devices_configuration):
                    if not self.operation_in_progress:
                        break

                    log_widget.insert(tkinter.END, f"[{index + 1}/{len(self.devices_configuration)}] {device['device_name']}...\n")
                    log_widget.see(tkinter.END)
                    self.install_device_driver(device, log_widget)
                    progress_bar["value"] = index + 1
                    self.root_window.update()
                    time.sleep(0.3)

                log_widget.insert(tkinter.END, "\n⚠️ Проверка сторонних устройств...\n")
                log_widget.see(tkinter.END)
                self.check_and_install_winusb_auto(log_widget)

                log_widget.insert(tkinter.END, "Установка завершена!\n")
                log_widget.see(tkinter.END)
                self.refresh_driver_status(status_tree)
                progress_bar["value"] = 0
            finally:
                self.operation_in_progress = False

                for button in buttons:
                    button.config(state=tkinter.NORMAL)


    def uninstall_all_drivers(self, log_widget, progress_bar, buttons, status_tree):
        with self.operation_lock:
            self.operation_in_progress = True

            try:
                for button in buttons:
                    button.config(state=tkinter.DISABLED)

                log_widget.insert(tkinter.END, "\nНачало удаления драйверов...\n")
                log_widget.see(tkinter.END)

                progress_bar["maximum"] = len(self.devices_configuration)

                for index, device in enumerate(self.devices_configuration):
                    if not self.operation_in_progress:
                        break

                    log_widget.insert(tkinter.END, f"[{index + 1}/{len(self.devices_configuration)}] {device['device_name']}...\n")
                    log_widget.see(tkinter.END)
                    self.uninstall_device_driver(device, log_widget)
                    progress_bar["value"] = index + 1
                    self.root_window.update()
                    time.sleep(0.3)

                log_widget.insert(tkinter.END, "Удаление завершено!\n")
                log_widget.see(tkinter.END)
                self.refresh_driver_status(status_tree)
                progress_bar["value"] = 0
            finally:
                self.operation_in_progress = False

                for button in buttons:
                    button.config(state=tkinter.NORMAL)


    def initialize_user_interface(self):
        self.root_window = tkinter.Tk()
        self.root_window.title("Менеджер драйверов")
        self.root_window.geometry("650x650")
        self.root_window.resizable(False, False)

        icon_path = self.drivers_path / "icon.png"

        if icon_path.exists():
            self.root_window.iconphoto(True, tkinter.PhotoImage(file=str(icon_path)))

        main_frame = ttk.Frame(self.root_window, padding=10)
        main_frame.pack(fill=tkinter.BOTH, expand=True)

        status_frame = ttk.LabelFrame(main_frame, text="Статус драйверов:", padding=5)
        status_frame.pack(fill=tkinter.X, pady=(0, 10))

        status_tree = ttk.Treeview(status_frame, columns=("device", "status"), show="headings", height=5)
        status_tree.heading("device", text="Устройство:")
        status_tree.heading("status", text="Статус:")
        status_tree.column("device", width=400)
        status_tree.column("status", width=130, anchor="center")
        status_tree.pack(fill=tkinter.X)

        drivers_frame = ttk.LabelFrame(main_frame, text="Управление драйверами:", padding=5)
        drivers_frame.pack(fill=tkinter.X, pady=(0, 10))

        for device in self.devices_configuration:
            driver_row = ttk.Frame(drivers_frame)
            driver_row.pack(fill=tkinter.X, pady=2)

            name_label = ttk.Label(driver_row, text=device["device_name"], width=35, anchor="w")
            name_label.pack(side=tkinter.LEFT, padx=5)

            remove_button = ttk.Button(driver_row, text="Удалить", width=12)
            install_button = ttk.Button(driver_row, text="Установить", width=12)
            remove_button.pack(side=tkinter.RIGHT, padx=2)
            install_button.pack(side=tkinter.RIGHT, padx=2)

            def make_install_function(d, install_button, remove_button):
                def install_function():
                    if self.operation_in_progress:
                        return

                    def task():
                        try:
                            self.operation_in_progress = True
                            install_button.config(state=tkinter.DISABLED)
                            remove_button.config(state=tkinter.DISABLED)
                            log_widget.insert(tkinter.END, f"\n{d['device_name']} установка...\n")
                            log_widget.see(tkinter.END)
                            self.install_device_driver(d, log_widget)
                            self.refresh_driver_status(status_tree)
                            log_widget.insert(tkinter.END, f"{d['device_name']} установка завершена!\n")
                            log_widget.see(tkinter.END)
                        finally:
                            self.operation_in_progress = False
                            install_button.config(state=tkinter.NORMAL)
                            remove_button.config(state=tkinter.NORMAL)

                    threading.Thread(target=task, daemon=True).start()

                return install_function

            def make_remove_function(d, install_button, remove_button):
                def remove_function():
                    if self.operation_in_progress:
                        return

                    def task():
                        try:
                            self.operation_in_progress = True
                            install_button.config(state=tkinter.DISABLED)
                            remove_button.config(state=tkinter.DISABLED)
                            log_widget.insert(tkinter.END, f"\n{d['device_name']} удаление...\n")
                            log_widget.see(tkinter.END)
                            self.uninstall_device_driver(d, log_widget)
                            self.refresh_driver_status(status_tree)
                            log_widget.insert(tkinter.END, f"{d['device_name']} удаление завершено!\n")
                            log_widget.see(tkinter.END)
                        finally:
                            self.operation_in_progress = False
                            install_button.config(state=tkinter.NORMAL)
                            remove_button.config(state=tkinter.NORMAL)

                    threading.Thread(target=task, daemon=True).start()

                return remove_function

            install_button.config(command=make_install_function(device, install_button, remove_button))
            remove_button.config(command=make_remove_function(device, install_button, remove_button))

        ttk.Separator(main_frame, orient='horizontal').pack(fill=tkinter.X, pady=5)

        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tkinter.X, pady=5)

        install_all_button = ttk.Button(buttons_frame, text="Установить все", width=15)
        install_all_button.pack(side=tkinter.LEFT, padx=5)

        remove_all_button = ttk.Button(buttons_frame, text="Удалить все", width=15)
        remove_all_button.pack(side=tkinter.LEFT, padx=5)

        progress_bar = ttk.Progressbar(main_frame, mode="determinate")
        progress_bar.pack(fill=tkinter.X, pady=5)

        log_frame = ttk.LabelFrame(main_frame, text="Выводы событий:", padding=5)
        log_frame.pack(fill=tkinter.BOTH, expand=True)

        log_widget = tkinter.Text(log_frame, height=8, wrap=tkinter.WORD, font=("Consolas", 9), state="normal")
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tkinter.VERTICAL, command=log_widget.yview)
        log_widget.configure(yscrollcommand=log_scrollbar.set)
        log_widget.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)
        log_scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)

        log_widget.insert(tkinter.END, "Добро пожаловать в менеджер драйверов!!!\n")
        log_widget.see(tkinter.END)

        def on_install_all_click():
            if self.operation_in_progress:
                return

            threading.Thread(target=self.install_all_drivers, args=(log_widget, progress_bar, [install_all_button, remove_all_button], status_tree), daemon=True).start()

        def on_remove_all_click():
            if self.operation_in_progress:
                return

            threading.Thread(target=self.uninstall_all_drivers, args=(log_widget, progress_bar, [install_all_button, remove_all_button], status_tree), daemon=True).start()

        install_all_button.config(command=on_install_all_click)
        remove_all_button.config(command=on_remove_all_click)

        def on_closing():
            if self.operation_in_progress:
                log_widget.insert(tkinter.END, "\nОжидание завершения операции...\n")
                log_widget.see(tkinter.END)

                while self.operation_in_progress:
                    self.root_window.update()
                    time.sleep(0.1)

            self.root_window.destroy()

        self.root_window.protocol("WM_DELETE_WINDOW", on_closing)
        self.root_window.after(100, lambda: self.refresh_driver_status(status_tree))
        self.root_window.mainloop()


if __name__ == "__main__":
    window_handle = ctypes.windll.user32.FindWindowW(None, "Менеджер драйверов")

    if window_handle:
        ctypes.windll.user32.ShowWindow(window_handle, 5)
        ctypes.windll.user32.SetForegroundWindow(window_handle)
        sys.exit(0)

    driver_manager = DriverManager()

    if not driver_manager.running_as_admin():
        driver_manager.restart_as_admin()

    driver_manager.initialize_user_interface()
