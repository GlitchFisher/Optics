import ctypes
import subprocess
import sys
import threading
import time
import tkinter

from pathlib import Path
from tkinter import ttk


CREATE_NO_WINDOW = 0x08000000


class DriverManager:
    def __init__(self):
        if getattr(sys, "frozen", False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent.parent

        self.drivers_path = base_path
        self.root_window = None
        self.operation_lock = threading.Lock()

        self.devices_configuration = [
            {
                "name": "Монохроматор",
                "path": "cypress/cyusb.inf",
                "ids": ["USB\\VID_0547&PID_1005"]
            },
            {
                "name": "Энергометр (шина)",
                "path": "ftdi/ftdibus.inf",
                "ids": ["USB\\VID_0403&PID_6001"]
            },
            {
                "name": "Энергометр (порт)",
                "path": "ftdi/ftdiport.inf",
                "ids": ["FTDIBUS\\COMPORT&VID_0403&PID_6001"]
            },
            {
                "name": "Лазерное излучение",
                "path": "prolific/ser2pl.inf",
                "ids": ["USB\\VID_067B&PID_2303"]
            }
        ]


    def extract_file_name(self, inf_path):
        file_name = Path(inf_path).name

        return file_name


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


    def get_installed_driver_packages(self):
        result = subprocess.run(["pnputil", "/enum-drivers"], capture_output=True, text=True, shell=False, creationflags=CREATE_NO_WINDOW)
        installed_drivers = {}
        lines = result.stdout.split("\n")

        for line_index, line in enumerate(lines):
            if "oem" in line.lower() and ".inf" in line.lower():
                oem_package_name = None

                for part in line.split():
                    if part.lower().startswith("oem") and part.lower().endswith(".inf"):
                        oem_package_name = part

                        break

                if oem_package_name:
                    for offset in range(line_index, min(len(lines), line_index + 5)):
                        for device in self.devices_configuration:
                            if self.extract_file_name(device["path"]) in lines[offset]:
                                installed_drivers[oem_package_name] = self.extract_file_name(device["path"])

                                break

        return installed_drivers


    def check_driver_installation(self, device):
        installed_drivers = self.get_installed_driver_packages()
        status = self.extract_file_name(device["path"]) in installed_drivers.values()

        return status


    def install_device_driver(self, device, log_widget):
        driver_file_path = (self.drivers_path / device["path"]).resolve()

        if not driver_file_path.exists():
            log_widget.insert(tkinter.END, f"❌ {device['name']}: не найден\n")
            log_widget.see(tkinter.END)

            return False

        result = subprocess.run(
            [
                "pnputil",
                "/add-driver",
                str(driver_file_path),
                "/install"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            cwd=driver_file_path.parent,
            creationflags=CREATE_NO_WINDOW
        )

        if result.returncode == 0:
            log_widget.insert(tkinter.END, f"✅ {device['name']}: установлен\n")
        else:
            log_widget.insert(tkinter.END, f"❌ {device['name']}: ошибка (код: {result.returncode})\n")

        log_widget.see(tkinter.END)

        status = result.returncode == 0

        return status


    def uninstall_device_by_hardware_id(self, hardware_id):
        result = subprocess.run(["pnputil", "/remove-device", hardware_id], capture_output=True, text=True, shell=False, creationflags=CREATE_NO_WINDOW)
        status = result.returncode == 0

        return status


    def delete_driver_package_from_store(self, inf_name, log_widget):
        installed_drivers = self.get_installed_driver_packages()
        driver_removed = False

        for oem_package_name, driver_name in installed_drivers.items():
            if driver_name == inf_name:
                result = subprocess.run(["pnputil", "/delete-driver", oem_package_name, "/uninstall"], capture_output=True, text=True, shell=False, creationflags=CREATE_NO_WINDOW)

                if result.returncode == 0:
                    log_widget.insert(tkinter.END, f"❌ Удалён пакет: {oem_package_name}\n")
                    driver_removed = True

                time.sleep(0.5)

        return driver_removed


    def uninstall_device_driver(self, device, log_widget):
        for hardware_id in device["ids"]:
            self.uninstall_device_by_hardware_id(hardware_id)

        removal_success = self.delete_driver_package_from_store(self.extract_file_name(device["path"]), log_widget)

        if removal_success:
            log_widget.insert(tkinter.END, f"❌ {device['name']}: удалён\n")
        else:
            log_widget.insert(tkinter.END, f"⚠️ {device['name']}: не найден\n")

        log_widget.see(tkinter.END)

        return removal_success


    def refresh_driver_status(self, status_tree):
        for row in status_tree.get_children():
            status_tree.delete(row)

        for device in self.devices_configuration:
            is_installed = self.check_driver_installation(device)
            status_text = "✅ Установлен" if is_installed else "❌ Не установлен"
            status_tree.insert("", tkinter.END, values=(device["name"], status_text))


    def install_all_drivers(self, log_widget, progress_bar, buttons, status_tree):
        with self.operation_lock:
            for button in buttons:
                button.config(state=tkinter.DISABLED)

            log_widget.insert(tkinter.END, "\nНачало установки драйверов...\n")
            log_widget.see(tkinter.END)

            progress_bar["maximum"] = len(self.devices_configuration)

            for index, device in enumerate(self.devices_configuration):
                log_widget.insert(tkinter.END, f"[{index + 1}/{len(self.devices_configuration)}] {device['name']}...\n")
                log_widget.see(tkinter.END)
                self.install_device_driver(device, log_widget)
                progress_bar["value"] = index + 1
                self.root_window.update()
                time.sleep(0.3)

            log_widget.insert(tkinter.END, "Установка завершена!\n")
            log_widget.see(tkinter.END)
            self.refresh_driver_status(status_tree)
            progress_bar["value"] = 0

            for button in buttons:
                button.config(state=tkinter.NORMAL)


    def uninstall_all_drivers(self, log_widget, progress_bar, buttons, status_tree):
        with self.operation_lock:
            for button in buttons:
                button.config(state=tkinter.DISABLED)

            log_widget.insert(tkinter.END, "\nНачало удаления драйверов...\n")
            log_widget.see(tkinter.END)

            progress_bar["maximum"] = len(self.devices_configuration)

            for index, device in enumerate(reversed(self.devices_configuration)):
                log_widget.insert(tkinter.END, f"[{index + 1}/{len(self.devices_configuration)}] {device['name']}...\n")
                log_widget.see(tkinter.END)
                self.uninstall_device_driver(device, log_widget)
                progress_bar["value"] = index + 1
                self.root_window.update()
                time.sleep(0.3)

            log_widget.insert(tkinter.END, "Удаление завершено!\n")
            log_widget.see(tkinter.END)
            self.refresh_driver_status(status_tree)
            progress_bar["value"] = 0

            for button in buttons:
                button.config(state=tkinter.NORMAL)


    def initialize_user_interface(self):
        self.root_window = tkinter.Tk()
        self.root_window.title("Драйвер менеджер")
        self.root_window.geometry("650x650")
        self.root_window.resizable(False, False)

        icon_path = self.drivers_path / "icon.png"

        if icon_path.exists():
            self.root_window.iconphoto(True, tkinter.PhotoImage(file=str(icon_path)))

        main_frame = ttk.Frame(self.root_window, padding=10)
        main_frame.pack(fill=tkinter.BOTH, expand=True)

        status_frame = ttk.LabelFrame(main_frame, text="Статус драйверов:", padding=5)
        status_frame.pack(fill=tkinter.X, pady=(0, 10))

        status_tree = ttk.Treeview(status_frame, columns=("device", "status"), show="headings", height=4)
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

            name_label = ttk.Label(driver_row, text=device["name"], width=35, anchor="w")
            name_label.pack(side=tkinter.LEFT, padx=5)

            remove_button = ttk.Button(driver_row, text="Удалить", width=12)
            install_button = ttk.Button(driver_row, text="Установить", width=12)
            remove_button.pack(side=tkinter.RIGHT, padx=2)
            install_button.pack(side=tkinter.RIGHT, padx=2)

            def make_install_function(d, install_button, remove_button):
                def install_function():
                    def task():
                        try:
                            install_button.config(state=tkinter.DISABLED)
                            remove_button.config(state=tkinter.DISABLED)
                            log_widget.insert(tkinter.END, f"\n{d['name']} установка...\n")
                            log_widget.see(tkinter.END)
                            self.install_device_driver(d, log_widget)
                            self.refresh_driver_status(status_tree)
                            log_widget.insert(tkinter.END, f"{d['name']} установка завершена!\n")
                            log_widget.see(tkinter.END)
                        finally:
                            install_button.config(state=tkinter.NORMAL)
                            remove_button.config(state=tkinter.NORMAL)

                    threading.Thread(target=task, daemon=True).start()

                return install_function
            
            def make_remove_function(d, install_button, remove_button):
                def remove_function():
                    def task():
                        try:
                            install_button.config(state=tkinter.DISABLED)
                            remove_button.config(state=tkinter.DISABLED)
                            log_widget.insert(tkinter.END, f"\n{d['name']} удаление...\n")
                            log_widget.see(tkinter.END)
                            self.uninstall_device_driver(d, log_widget)
                            self.refresh_driver_status(status_tree)
                            log_widget.insert(tkinter.END, f"{d['name']} удаление завершено!\n")
                            log_widget.see(tkinter.END)
                        finally:
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

        log_frame = ttk.LabelFrame(main_frame, text="Выводы:", padding=5)
        log_frame.pack(fill=tkinter.BOTH, expand=True)

        log_widget = tkinter.Text(log_frame, height=8, wrap=tkinter.WORD, font=("Consolas", 9), state="normal")
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tkinter.VERTICAL, command=log_widget.yview)
        log_widget.configure(yscrollcommand=log_scrollbar.set)
        log_widget.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)
        log_scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)

        def on_install_all_click():
            threading.Thread(target=self.install_all_drivers, args=(log_widget, progress_bar, [install_all_button, remove_all_button], status_tree), daemon=True).start()

        def on_remove_all_click():
            threading.Thread(target=self.uninstall_all_drivers, args=(log_widget, progress_bar, [install_all_button, remove_all_button], status_tree), daemon=True).start()

        install_all_button.config(command=on_install_all_click)
        remove_all_button.config(command=on_remove_all_click)

        self.root_window.after(100, lambda: self.refresh_driver_status(status_tree))
        self.root_window.protocol("WM_DELETE_WINDOW", self.root_window.destroy)
        self.root_window.mainloop()


if __name__ == "__main__":
    hwnd = ctypes.windll.user32.FindWindowW(None, "Драйвер менеджер")

    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 5)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        sys.exit(0)

    driver_manager = DriverManager()

    if not driver_manager.running_as_admin():
        driver_manager.restart_as_admin()

    driver_manager.initialize_user_interface()
