import sys
import os
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
import threading
import time

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtChart import *
from PyQt5.Qt import QPainter

if getattr(sys, "frozen", False):
    library_path = Path(sys._MEIPASS) / 'library'
else:
    library_path = Path(__file__).resolve().parent.parent / 'library'

sys.path.insert(0, str(library_path))

try:
    from chromator import Chromator
    from oscilloscope import Oscilloscope
    from mathematics import integrate_signal, approximate_signal
except ImportError:
    class Chromator:
        def connect(self): return True
        def disconnect(self): pass
        def set_wavelength(self, wavelength): pass
        def set_slit_width(self, slit, width): pass
        def set_acquisition_type(self, acquisition_type): pass
        def set_average_count(self, count): pass
    
    class Oscilloscope:
        def connect(self): return True
        def disconnect(self): pass
        def set_channel_scale(self, channel, scale): pass
        def set_timebase_scale(self, scale): pass
        def set_trigger_source(self, source): pass
        def set_trigger_level(self, level): pass
        def capture_waveform(self, channel, points):
            time_values = np.linspace(-20e-6, 30e-6, points)
            signal_values = np.exp(-((time_values - 5e-6) ** 2) / (3e-6) ** 2) * 0.5 + np.random.normal(0, 0.02, points)
            return time_values.tolist(), signal_values.tolist()
        def acquire_averaged_waveform(self, channel, average_count, points):
            time_values = np.linspace(-20e-6, 30e-6, points)
            signal_values = np.exp(-((time_values - 5e-6) ** 2) / (3e-6) ** 2) * 0.5 + np.random.normal(0, 0.005, points)
            return time_values.tolist(), signal_values.tolist()
        def set_acquisition_type(self, acquisition_type): pass
        def set_average_count(self, count): pass
        def set_channel_enabled(self, channel, enable): pass
        def set_channel_coupling(self, channel, coupling): pass
        def run_acquisition(self): pass
        def stop_acquisition(self): pass
    
    def integrate_signal(time_values, signal_values):
        if len(time_values) < 2:
            return 0.0
        return np.trapz(signal_values, time_values)
    
    def approximate_signal(time_values, signal_values, use_background=True):
        return signal_values, {"fit_successful": True, "signal_amplitude_volts": max(signal_values) - min(signal_values)}

class SettingsManager:
    def __init__(self):
        self.settings_file = "spectrum_settings.json"
        self.default_settings = {
            'laser_wavelength': 1064.0,
            'start_wavelength': 1300.0,
            'end_wavelength': 1400.0,
            'wavelength_step': 0.5,
            'input_slit': 100.0,
            'output_slit': 100.0,
            'oscilloscope_channel': 1,
            'average_count': 1024,
            'power_average_count': 10,
            'dual_integration': False,
            'baseline_start': -10e-6,
            'baseline_end': -2e-6,
            'signal1_start': -2e-6,
            'signal1_end': 20e-6,
            'signal2_start': 10e-6,
            'signal2_end': 30e-6,
            'energy_points': 10,
            'reference_peak': 1308.0,
        }
        self.settings = self.default_settings.copy()
        self.load()
    
    def load(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as file_handle:
                    loaded_settings = json.load(file_handle)
                    self.settings.update(loaded_settings)
            except:
                pass
    
    def save(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as file_handle:
                json.dump(self.settings, file_handle, indent=2, ensure_ascii=False)
        except:
            pass
    
    def get(self, key, default_value=None):
        return self.settings.get(key, default_value)
    
    def set(self, key, value):
        self.settings[key] = value
        self.save()
    
    def reset_to_defaults(self):
        self.settings = self.default_settings.copy()
        self.save()

class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.dragging = False
        self.drag_position = None
        self.setFixedHeight(40)
        self.setMouseTracking(True)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(5)
        
        icon_label = QLabel()
        icon_path = Path(sys.executable).parent / "icon.png" if getattr(sys, "frozen", False) else Path(__file__).parent / "icon.png"
        if icon_path.exists():
            icon_pixmap = QPixmap(str(icon_path)).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(icon_pixmap)
        else:
            icon_pixmap = QPixmap(20, 20)
            icon_pixmap.fill(Qt.transparent)
            icon_label.setPixmap(icon_pixmap)
        layout.addWidget(icon_label)
        
        self.title_label = QLabel("Измерение спектров")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        self.minimize_button = QPushButton("─")
        self.minimize_button.setFixedSize(30, 25)
        self.minimize_button.clicked.connect(self.parent.showMinimized)
        layout.addWidget(self.minimize_button)
        
        self.maximize_button = QPushButton("☐")
        self.maximize_button.setFixedSize(30, 25)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        layout.addWidget(self.maximize_button)
        
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(30, 25)
        self.close_button.clicked.connect(self.parent.close)
        layout.addWidget(self.close_button)
        
        self.update_style()
    
    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.maximize_button.setText("☐")
        else:
            self.parent.showMaximized()
            self.maximize_button.setText("❐")
    
    def update_style(self):
        self.setStyleSheet("""
            QWidget { background-color: #f0f0f0; }
            QLabel { color: black; }
            QPushButton { background-color: transparent; color: black; border: none; font-size: 14px; }
            QPushButton:hover { background-color: #e0e0e0; }
            QPushButton#close_button:hover { background-color: #e81123; color: white; }
        """)
        self.close_button.setObjectName("close_button")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.parent.frameGeometry().topLeft()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.dragging:
            self.parent.move(event.globalPos() - self.drag_position)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
        super().mouseReleaseEvent(event)

class DraggableLineItem(QGraphicsLineItem):
    def __init__(self, position_x, label_text, color, parent_view, minimum_x=None, maximum_x=None):
        super().__init__()
        self.position_x = position_x
        self.label_text = label_text
        self.color = color
        self.parent_view = parent_view
        self.minimum_x = minimum_x
        self.maximum_x = maximum_x
        self.is_dragging = False
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.update_line()
    
    def update_line(self):
        plot_rect = self.parent_view.plot_area()
        if not plot_rect:
            return
        x_minimum, x_maximum, y_minimum, y_maximum = plot_rect
        if self.minimum_x is not None:
            self.position_x = max(self.minimum_x, self.position_x)
        if self.maximum_x is not None:
            self.position_x = min(self.maximum_x, self.position_x)
        self.setLine(self.position_x, y_minimum, self.position_x, y_maximum)
    
    def hoverEnterEvent(self, event):
        self.setCursor(QCursor(Qt.SizeHorCursor))
        super().hoverEnterEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.setCursor(QCursor(Qt.ClosedHandCursor))
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.is_dragging:
            mouse_position = event.pos()
            scene_position = self.mapToScene(mouse_position)
            self.position_x = scene_position.x()
            self.update_line()
            self.parent_view.update_integration_fields_from_lines()
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.setCursor(QCursor(Qt.SizeHorCursor))
            self.update_line()
            self.parent_view.update_integration_fields_from_lines()
        super().mouseReleaseEvent(event)

class SignalPlotView(QChartView):
    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.draggable_lines = []
        self.signal_time_data = None
        self.signal_voltage_data = None
        self.chart = QChart()
        self.chart.setAnimationOptions(QChart.NoAnimation)
        self.chart.legend().hide()
        self.setChart(self.chart)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRubberBand(QChartView.RectangleRubberBand)
    
    def plot_area(self):
        if not self.chart:
            return None
        chart_axes = self.chart.axes()
        if not chart_axes:
            return None
        x_axis = chart_axes[0] if len(chart_axes) > 0 else None
        y_axis = chart_axes[1] if len(chart_axes) > 1 else None
        if x_axis and y_axis:
            return (x_axis.min(), x_axis.max(), y_axis.min(), y_axis.max())
        return None
    
    def set_signal_data(self, time_values, voltage_values):
        self.signal_time_data = time_values
        self.signal_voltage_data = voltage_values
        self.update_plot()
    
    def update_plot(self):
        if not self.signal_time_data or not self.signal_voltage_data:
            return
        
        signal_series = QLineSeries()
        for time_value, voltage_value in zip(self.signal_time_data, self.signal_voltage_data):
            signal_series.append(time_value, voltage_value)
        
        self.chart.removeAllSeries()
        self.chart.addSeries(signal_series)
        self.chart.createDefaultAxes()
        
        horizontal_axes = self.chart.axes(Qt.Horizontal)
        vertical_axes = self.chart.axes(Qt.Vertical)
        if horizontal_axes:
            horizontal_axes[0].setTitleText("Время, с")
        if vertical_axes:
            vertical_axes[0].setTitleText("Сигнал, В")
        
        self.update_draggable_lines()
    
    def update_draggable_lines(self):
        for line_item in self.draggable_lines:
            self.chart.scene().removeItem(line_item)
        self.draggable_lines.clear()
        
        if not self.signal_time_data:
            return
        
        plot_rect = self.plot_area()
        if not plot_rect:
            return
        
        x_minimum, x_maximum, y_minimum, y_maximum = plot_rect
        measurement = self.parent_widget.measurement
        configuration = measurement.configuration
        dual_integration = self.parent_widget.settings.get('dual_integration', False)
        
        line_configurations = [
            (configuration.baseline_start_time_seconds, "Левый фон", Qt.red, "baseline_start"),
            (configuration.baseline_end_time_seconds, "Правый фон", Qt.red, "baseline_end"),
            (configuration.signal_integration_start_time_seconds, "Левый сигнал 1" if not dual_integration else "Левый сигнал 1", Qt.green, "signal1_start"),
            (configuration.signal_integration_end_time_seconds, "Правый сигнал 1" if not dual_integration else "Правый сигнал 1", Qt.green, "signal1_end"),
        ]
        
        if dual_integration:
            line_configurations.extend([
                (configuration.signal_integration_start_time_seconds_2, "Левый сигнал 2", Qt.blue, "signal2_start"),
                (configuration.signal_integration_end_time_seconds_2, "Правый сигнал 2", Qt.blue, "signal2_end"),
            ])
        
        for position_x, label_text, color, key in line_configurations:
            if x_minimum <= position_x <= x_maximum:
                line_item = DraggableLineItem(position_x, label_text, color, self, x_minimum, x_maximum)
                self.chart.scene().addItem(line_item)
                self.draggable_lines.append(line_item)
    
    def update_integration_fields_from_lines(self):
        if self.parent_widget:
            line_positions = []
            for line_item in self.draggable_lines:
                line_positions.append((line_item.position_x, line_item.label_text))
            self.parent_widget.update_integration_fields_from_lines(line_positions)

class SpectrumPlotView(QChartView):
    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.chart = QChart()
        self.chart.setAnimationOptions(QChart.NoAnimation)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignTop)
        self.setChart(self.chart)
        self.setRenderHint(QPainter.Antialiasing)
    
    def set_spectrum_data(self, wavelengths, integrated_values_1, approximated_values_1,
                         integrated_values_2=None, approximated_values_2=None):
        self.chart.removeAllSeries()
        
        if wavelengths and integrated_values_1:
            series_integration_1 = QLineSeries()
            series_integration_1.setName("Интегрирование 1" if integrated_values_2 is not None else "Интегрирование")
            series_integration_1.setColor(Qt.red)
            for wavelength, value in zip(wavelengths, integrated_values_1):
                series_integration_1.append(wavelength, value)
            self.chart.addSeries(series_integration_1)
            
            if integrated_values_2 is not None and len(integrated_values_2) > 0:
                series_integration_2 = QLineSeries()
                series_integration_2.setName("Интегрирование 2")
                series_integration_2.setColor(Qt.blue)
                for wavelength, value in zip(wavelengths, integrated_values_2):
                    series_integration_2.append(wavelength, value)
                self.chart.addSeries(series_integration_2)
        
        if wavelengths and approximated_values_1:
            series_approximation_1 = QLineSeries()
            series_approximation_1.setName("Аппроксимация 1" if approximated_values_2 is not None else "Аппроксимация")
            series_approximation_1.setColor(Qt.darkGreen)
            for wavelength, value in zip(wavelengths, approximated_values_1):
                series_approximation_1.append(wavelength, value)
            self.chart.addSeries(series_approximation_1)
            
            if approximated_values_2 is not None and len(approximated_values_2) > 0:
                series_approximation_2 = QLineSeries()
                series_approximation_2.setName("Аппроксимация 2")
                series_approximation_2.setColor(Qt.darkYellow)
                for wavelength, value in zip(wavelengths, approximated_values_2):
                    series_approximation_2.append(wavelength, value)
                self.chart.addSeries(series_approximation_2)
        
        if self.chart.series():
            self.chart.createDefaultAxes()
            chart_axes = self.chart.axes()
            if chart_axes:
                for axis in chart_axes:
                    if axis.orientation() == Qt.Horizontal:
                        axis.setTitleText("Длина волны, нм")
                    elif axis.orientation() == Qt.Vertical:
                        axis.setTitleText("Спектр, В·с")

class EnergyPlotView(QChartView):
    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.chart = QChart()
        self.chart.setAnimationOptions(QChart.NoAnimation)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignTop)
        self.setChart(self.chart)
        self.setRenderHint(QPainter.Antialiasing)
    
    def set_energy_data(self, energy_values, integrated_values_1, approximated_values_1,
                       integrated_values_2=None, approximated_values_2=None):
        self.chart.removeAllSeries()
        
        if energy_values and integrated_values_1:
            series_integration_1 = QLineSeries()
            series_integration_1.setName("Интегрирование 1" if integrated_values_2 is not None else "Интегрирование")
            series_integration_1.setColor(Qt.red)
            for energy_value, integrated_value in zip(energy_values, integrated_values_1):
                series_integration_1.append(energy_value, integrated_value)
            self.chart.addSeries(series_integration_1)
            
            if integrated_values_2 is not None and len(integrated_values_2) > 0:
                series_integration_2 = QLineSeries()
                series_integration_2.setName("Интегрирование 2")
                series_integration_2.setColor(Qt.blue)
                for energy_value, integrated_value in zip(energy_values, integrated_values_2):
                    series_integration_2.append(energy_value, integrated_value)
                self.chart.addSeries(series_integration_2)
        
        if energy_values and approximated_values_1:
            series_approximation_1 = QLineSeries()
            series_approximation_1.setName("Аппроксимация 1" if approximated_values_2 is not None else "Аппроксимация")
            series_approximation_1.setColor(Qt.darkGreen)
            for energy_value, approximated_value in zip(energy_values, approximated_values_1):
                series_approximation_1.append(energy_value, approximated_value)
            self.chart.addSeries(series_approximation_1)
            
            if approximated_values_2 is not None and len(approximated_values_2) > 0:
                series_approximation_2 = QLineSeries()
                series_approximation_2.setName("Аппроксимация 2")
                series_approximation_2.setColor(Qt.darkYellow)
                for energy_value, approximated_value in zip(energy_values, approximated_values_2):
                    series_approximation_2.append(energy_value, approximated_value)
                self.chart.addSeries(series_approximation_2)
        
        if self.chart.series():
            self.chart.createDefaultAxes()
            chart_axes = self.chart.axes()
            if chart_axes:
                for axis in chart_axes:
                    if axis.orientation() == Qt.Horizontal:
                        axis.setTitleText("Энергия лазерного импульса, МДж")
                    elif axis.orientation() == Qt.Vertical:
                        axis.setTitleText("Спектр, В·с")

class MeasurementConfiguration:
    def __init__(self):
        self.laser_wavelength_nanometers = 1064.0
        self.start_wavelength_nanometers = 1300.0
        self.end_wavelength_nanometers = 1400.0
        self.wavelength_step_nanometers = 0.5
        self.input_slit_micrometers = 100.0
        self.output_slit_micrometers = 100.0
        self.oscilloscope_average_count = 1024
        self.power_meter_average_count = 10
        self.oscilloscope_signal_channel = 1
        self.dual_integration_enabled = False
        self.baseline_start_time_seconds = -10e-6
        self.baseline_end_time_seconds = -2e-6
        self.signal_integration_start_time_seconds = -2e-6
        self.signal_integration_end_time_seconds = 20e-6
        self.signal_integration_start_time_seconds_2 = 10e-6
        self.signal_integration_end_time_seconds_2 = 30e-6
        self.reference_peak_nanometers = 1308.0
        self.calibration_offset_nanometers = 0.0
        self.calibration_performed = False

class SpectrumMeasurement:
    def __init__(self):
        self.configuration = MeasurementConfiguration()
        self.chromator_device = None
        self.oscilloscope_device = None
        self.is_chromator_connected = False
        self.is_oscilloscope_connected = False
        self.measured_spectrum = []
        self.energy_measurements = []
        self.integrated_values = []
        self.approximated_values = []
        self.integrated_values_2 = []
        self.approximated_values_2 = []
        self.energy_values = []
        self.test_signal_time = []
        self.test_signal_voltage = []
        self.processed_signal = []
        self.wavelengths_for_spectrum = []
        self.is_scanning = False
        self.is_measuring_energy = False
        self.stop_requested = False
        self.calibration_offset = 0.0
        self.calibration_performed = False
        self.saved_spectrum_data = {
            'wavelengths': [],
            'integrated_values': [],
            'approximated_values': [],
            'integrated_values_2': [],
            'approximated_values_2': []
        }
        self.saved_energy_data = {
            'energy_values': [],
            'integrated_values': [],
            'approximated_values': [],
            'integrated_values_2': [],
            'approximated_values_2': []
        }
        self.saved_signal_data = {
            'time_values': [],
            'voltage_values': []
        }
        self.saved_parameters = {}
        self.saved_timestamp = ''
    
    def connect_instruments(self):
        connection_success = True
        
        try:
            self.chromator_device = Chromator()
            if self.chromator_device.connect():
                self.is_chromator_connected = True
            else:
                connection_success = False
        except Exception:
            connection_success = False
        
        try:
            self.oscilloscope_device = Oscilloscope()
            if self.oscilloscope_device.connect():
                self.is_oscilloscope_connected = True
                self.setup_oscilloscope()
            else:
                connection_success = False
        except Exception:
            connection_success = False
        
        return connection_success
    
    def disconnect_instruments(self):
        if self.chromator_device:
            try:
                self.chromator_device.disconnect()
                self.is_chromator_connected = False
            except Exception:
                pass
        
        if self.oscilloscope_device:
            try:
                self.restore_oscilloscope_settings()
                self.oscilloscope_device.disconnect()
                self.is_oscilloscope_connected = False
            except Exception:
                pass
    
    def setup_oscilloscope(self):
        if self.oscilloscope_device:
            try:
                self.oscilloscope_device.set_acquisition_type("AVER")
                self.oscilloscope_device.set_average_count(self.configuration.oscilloscope_average_count)
                
                if self.configuration.oscilloscope_average_count > 256:
                    time.sleep(min(self.configuration.oscilloscope_average_count / 20, 30.0))
                
                self.oscilloscope_device.set_channel_enabled(self.configuration.oscilloscope_signal_channel, True)
                self.oscilloscope_device.set_channel_scale(self.configuration.oscilloscope_signal_channel, 1.0)
                self.oscilloscope_device.set_channel_coupling(self.configuration.oscilloscope_signal_channel, "DC")
                self.oscilloscope_device.set_trigger_source(f"CHAN{self.configuration.oscilloscope_signal_channel}")
                self.oscilloscope_device.set_trigger_level(0.0)
                self.oscilloscope_device.set_trigger_slope("POS")
                self.oscilloscope_device.run_acquisition()
            except Exception:
                pass
    
    def restore_oscilloscope_settings(self):
        if self.oscilloscope_device:
            try:
                self.oscilloscope_device.stop_acquisition()
                self.oscilloscope_device.set_acquisition_type("NORM")
                self.oscilloscope_device.set_average_count(2)
            except Exception:
                pass
    
    def set_chromator_wavelength(self, wavelength_nanometers):
        if self.chromator_device:
            adjusted_wavelength = wavelength_nanometers - self.calibration_offset
            self.chromator_device.set_wavelength(adjusted_wavelength)
            return True
        return False
    
    def set_slit_widths(self, input_slit_micrometers, output_slit_micrometers):
        if self.chromator_device:
            self.chromator_device.set_slit_width(0, input_slit_micrometers)
            self.chromator_device.set_slit_width(1, output_slit_micrometers)
            return True
        return False
    
    def capture_test_signal(self):
        if not self.oscilloscope_device:
            return False
        
        self.test_signal_time, self.test_signal_voltage = self.oscilloscope_device.acquire_averaged_waveform(
            self.configuration.oscilloscope_signal_channel,
            self.configuration.oscilloscope_average_count,
            2000
        )
        
        if not self.test_signal_voltage or len(self.test_signal_voltage) == 0:
            return False
        
        baseline_values = []
        for index in range(len(self.test_signal_time)):
            if self.configuration.baseline_start_time_seconds <= self.test_signal_time[index] <= self.configuration.baseline_end_time_seconds:
                baseline_values.append(self.test_signal_voltage[index])
        
        if baseline_values:
            baseline_level = np.mean(baseline_values)
            self.processed_signal = [voltage - baseline_level for voltage in self.test_signal_voltage]
        else:
            self.processed_signal = self.test_signal_voltage.copy()
        
        return True
    
    def measure_integrated_signal(self) -> float:
        if not self.oscilloscope_device:
            return 0.0
        
        time_values, voltage_values = self.oscilloscope_device.acquire_averaged_waveform(
            self.configuration.oscilloscope_signal_channel,
            self.configuration.oscilloscope_average_count,
            2000
        )
        
        if not voltage_values or len(voltage_values) == 0:
            return 0.0
        
        baseline_values = []
        for index in range(len(time_values)):
            if self.configuration.baseline_start_time_seconds <= time_values[index] <= self.configuration.baseline_end_time_seconds:
                baseline_values.append(voltage_values[index])
        
        if baseline_values:
            baseline_level = np.mean(baseline_values)
            corrected_signal = [voltage - baseline_level for voltage in voltage_values]
        else:
            corrected_signal = voltage_values.copy()
        
        integration_time_values = []
        integration_signal_values = []
        for index in range(len(time_values)):
            if self.configuration.signal_integration_start_time_seconds <= time_values[index] <= self.configuration.signal_integration_end_time_seconds:
                integration_time_values.append(time_values[index])
                integration_signal_values.append(corrected_signal[index])
        
        if len(integration_time_values) < 2:
            return 0.0
        
        return integrate_signal(integration_time_values, integration_signal_values)
    
    def measure_approximated_signal(self) -> float:
        if not self.oscilloscope_device:
            return 0.0
        
        time_values, voltage_values = self.oscilloscope_device.acquire_averaged_waveform(
            self.configuration.oscilloscope_signal_channel,
            self.configuration.oscilloscope_average_count,
            2000
        )
        
        if not voltage_values or len(voltage_values) == 0:
            return 0.0
        
        approximated_signal, fit_parameters = approximate_signal(time_values, voltage_values, use_background=True)
        
        if fit_parameters.get("fit_successful", False):
            return fit_parameters.get("signal_amplitude_volts", 0.0)
        
        return max(approximated_signal) if approximated_signal else 0.0
    
    def measure_integrated_signal_2(self) -> float:
        if not self.oscilloscope_device:
            return 0.0
        
        time_values, voltage_values = self.oscilloscope_device.acquire_averaged_waveform(
            self.configuration.oscilloscope_signal_channel,
            self.configuration.oscilloscope_average_count,
            2000
        )
        
        if not voltage_values or len(voltage_values) == 0:
            return 0.0
        
        baseline_values = []
        for index in range(len(time_values)):
            if self.configuration.baseline_start_time_seconds <= time_values[index] <= self.configuration.baseline_end_time_seconds:
                baseline_values.append(voltage_values[index])
        
        if baseline_values:
            baseline_level = np.mean(baseline_values)
            corrected_signal = [voltage - baseline_level for voltage in voltage_values]
        else:
            corrected_signal = voltage_values.copy()
        
        integration_time_values = []
        integration_signal_values = []
        for index in range(len(time_values)):
            if self.configuration.signal_integration_start_time_seconds_2 <= time_values[index] <= self.configuration.signal_integration_end_time_seconds_2:
                integration_time_values.append(time_values[index])
                integration_signal_values.append(corrected_signal[index])
        
        if len(integration_time_values) < 2:
            return 0.0
        
        return integrate_signal(integration_time_values, integration_signal_values)
    
    def measure_approximated_signal_2(self) -> float:
        if not self.oscilloscope_device:
            return 0.0
        
        time_values, voltage_values = self.oscilloscope_device.acquire_averaged_waveform(
            self.configuration.oscilloscope_signal_channel,
            self.configuration.oscilloscope_average_count,
            2000
        )
        
        if not voltage_values or len(voltage_values) == 0:
            return 0.0
        
        approximated_signal, fit_parameters = approximate_signal(time_values, voltage_values, use_background=True)
        
        if fit_parameters.get("fit_successful", False):
            return fit_parameters.get("signal_amplitude_volts", 0.0)
        
        return max(approximated_signal) if approximated_signal else 0.0
    
    def find_spectrum_peak(self, wavelengths, amplitudes):
        if not wavelengths or not amplitudes or len(wavelengths) < 3:
            return 0.0
        
        try:
            peak_index = np.argmax(amplitudes)
            if peak_index > 0 and peak_index < len(amplitudes) - 1:
                peak_wavelength = wavelengths[peak_index]
                return peak_wavelength
            return 0.0
        except Exception:
            return 0.0
    
    def perform_calibration(self, reference_peak):
        if not self.wavelengths_for_spectrum or not self.integrated_values:
            return 0.0, False
        
        measured_peak = self.find_spectrum_peak(self.wavelengths_for_spectrum, self.integrated_values)
        
        if measured_peak <= 0:
            return 0.0, False
        
        calibration_offset = measured_peak - reference_peak
        
        self.calibration_offset = calibration_offset
        self.calibration_performed = True
        
        return calibration_offset, True
    
    def reset_calibration(self):
        self.calibration_offset = 0.0
        self.calibration_performed = False
    
    def get_calibrated_wavelength(self, wavelength):
        return wavelength - self.calibration_offset
    
    def get_applied_calibration_offset(self):
        return self.calibration_offset
    
    def is_calibration_performed(self):
        return self.calibration_performed
    
    def save_data_to_memory(self):
        self.saved_spectrum_data = {
            'wavelengths': self.wavelengths_for_spectrum.copy(),
            'integrated_values': self.integrated_values.copy(),
            'approximated_values': self.approximated_values.copy(),
            'integrated_values_2': self.integrated_values_2.copy(),
            'approximated_values_2': self.approximated_values_2.copy()
        }
        self.saved_energy_data = {
            'energy_values': self.energy_values.copy(),
            'integrated_values': self.integrated_values.copy(),
            'approximated_values': self.approximated_values.copy(),
            'integrated_values_2': self.integrated_values_2.copy(),
            'approximated_values_2': self.approximated_values_2.copy()
        }
        self.saved_signal_data = {
            'time_values': self.test_signal_time.copy(),
            'voltage_values': self.processed_signal.copy()
        }
        self.saved_parameters = {
            'laser_wavelength': self.configuration.laser_wavelength_nanometers,
            'start_wavelength': self.configuration.start_wavelength_nanometers,
            'end_wavelength': self.configuration.end_wavelength_nanometers,
            'wavelength_step': self.configuration.wavelength_step_nanometers,
            'input_slit': self.configuration.input_slit_micrometers,
            'output_slit': self.configuration.output_slit_micrometers,
            'oscilloscope_channel': self.configuration.oscilloscope_signal_channel,
            'average_count': self.configuration.oscilloscope_average_count,
            'dual_integration': self.configuration.dual_integration_enabled,
            'reference_peak': self.configuration.reference_peak_nanometers,
            'calibration_offset': self.calibration_offset,
            'calibration_performed': self.calibration_performed
        }
        self.saved_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def get_saved_data(self):
        return {
            'spectrum': self.saved_spectrum_data,
            'energy': self.saved_energy_data,
            'signal_data': self.saved_signal_data,
            'parameters': self.saved_parameters,
            'timestamp': self.saved_timestamp
        }
    
    def scan_spectrum(self, progress_callback):
        self.stop_requested = False
        wavelength_list = np.arange(
            self.configuration.start_wavelength_nanometers,
            self.configuration.end_wavelength_nanometers + self.configuration.wavelength_step_nanometers,
            self.configuration.wavelength_step_nanometers
        )
        total_points = len(wavelength_list)
        self.integrated_values = []
        self.approximated_values = []
        self.integrated_values_2 = []
        self.approximated_values_2 = []
        self.wavelengths_for_spectrum = []
        
        if self.oscilloscope_device:
            try:
                self.oscilloscope_device.set_acquisition_type("AVER")
                self.oscilloscope_device.set_average_count(self.configuration.oscilloscope_average_count)
                
                if self.configuration.oscilloscope_average_count > 256:
                    time.sleep(min(self.configuration.oscilloscope_average_count / 20, 30.0))
            except Exception:
                pass
        
        for point_index, wavelength in enumerate(wavelength_list):
            if self.stop_requested:
                break
            
            self.set_chromator_wavelength(wavelength)
            
            if hasattr(self.chromator_device, 'wait_for_wavelength_stable'):
                self.chromator_device.wait_for_wavelength_stable(wavelength, 0.1, 10.0)
            else:
                time.sleep(0.3)
            
            integrated_value = self.measure_integrated_signal()
            approximated_value = self.measure_approximated_signal()
            
            self.wavelengths_for_spectrum.append(wavelength)
            self.integrated_values.append(integrated_value)
            self.approximated_values.append(approximated_value)
            
            if self.configuration.dual_integration_enabled:
                integrated_value_2 = self.measure_integrated_signal_2()
                approximated_value_2 = self.measure_approximated_signal_2()
                self.integrated_values_2.append(integrated_value_2)
                self.approximated_values_2.append(approximated_value_2)
            
            completion_percent = int((point_index + 1) / total_points * 100)
            progress_callback(completion_percent)
        
        self.restore_oscilloscope_settings()
        self.save_data_to_memory()
        
        return len(self.wavelengths_for_spectrum) > 0
    
    def measure_energy_series(self, points_count, progress_callback):
        self.stop_requested = False
        self.energy_values = []
        self.integrated_values = []
        self.approximated_values = []
        self.integrated_values_2 = []
        self.approximated_values_2 = []
        
        if self.oscilloscope_device:
            try:
                self.oscilloscope_device.set_acquisition_type("AVER")
                self.oscilloscope_device.set_average_count(self.configuration.oscilloscope_average_count)
                
                if self.configuration.oscilloscope_average_count > 256:
                    time.sleep(min(self.configuration.oscilloscope_average_count / 20, 30.0))
            except Exception:
                pass
        
        for point_index in range(points_count):
            if self.stop_requested:
                break
            
            energy_value = self.measure_integrated_signal()
            approximated_value = self.measure_approximated_signal()
            
            self.energy_values.append(energy_value)
            self.integrated_values.append(energy_value)
            self.approximated_values.append(approximated_value)
            
            if self.configuration.dual_integration_enabled:
                integrated_value_2 = self.measure_integrated_signal_2()
                approximated_value_2 = self.measure_approximated_signal_2()
                self.integrated_values_2.append(integrated_value_2)
                self.approximated_values_2.append(approximated_value_2)
            
            completion_percent = int((point_index + 1) / points_count * 100)
            progress_callback(completion_percent)
            
            time.sleep(0.1)
        
        self.restore_oscilloscope_settings()
        self.save_data_to_memory()
        
        return len(self.energy_values) > 0

class CenteredWidget(QWidget):
    def __init__(self, content_widget, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        layout.addWidget(content_widget)
        layout.addStretch()

class FieldRow(QWidget):
    def __init__(self, label_text, edit_widget, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.label = QLabel(label_text)
        self.label.setMinimumWidth(180)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.label)
        
        edit_widget.setFixedWidth(150)
        layout.addWidget(edit_widget)
        
        layout.addStretch()

class CheckBoxRow(QWidget):
    def __init__(self, checkbox, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        spacer = QWidget()
        spacer.setMinimumWidth(180)
        layout.addWidget(spacer)
        
        layout.addWidget(checkbox)
        
        layout.addStretch()

class DoubleFieldRow(QWidget):
    def __init__(self, label_text_left, edit_widget_left, label_text_right, edit_widget_right, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.label_left = QLabel(label_text_left)
        self.label_left.setMinimumWidth(180)
        self.label_left.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.label_left)
        
        edit_widget_left.setFixedWidth(150)
        layout.addWidget(edit_widget_left)
        
        self.label_right = QLabel(label_text_right)
        self.label_right.setMinimumWidth(180)
        self.label_right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.label_right)
        
        edit_widget_right.setFixedWidth(150)
        layout.addWidget(edit_widget_right)
        
        layout.addStretch()

class ButtonRow(QWidget):
    def __init__(self, button, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        layout.addStretch()
        layout.addWidget(button)
        layout.addStretch()

class MainApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1200, 800)
        self.settings = SettingsManager()
        self.measurement = SpectrumMeasurement()
        self.is_connected = False
        self.is_running = False
        self.dragging = False
        self.drag_position = None
        
        icon_path = Path(sys.executable).parent / "icon.png" if getattr(sys, "frozen", False) else Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        self.setup_user_interface()
        self.apply_theme()
        
        self.worker_thread = None
    
    def setup_user_interface(self):
        self.title_bar = CustomTitleBar(self)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        main_layout.addWidget(self.title_bar)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(5, 5, 5, 5)
        content_layout.setSpacing(5)
        
        self.tab_widget = QTabWidget()
        content_layout.addWidget(self.tab_widget)
        
        self.parameters_tab = self.create_parameters_tab()
        self.tab_widget.addTab(self.parameters_tab, "Параметры")
        
        self.signal_tab = self.create_signal_tab()
        self.tab_widget.addTab(self.signal_tab, "Сигнал")
        
        self.spectrum_tab = self.create_spectrum_tab()
        self.tab_widget.addTab(self.spectrum_tab, "Спектр")
        
        self.energy_tab = self.create_energy_tab()
        self.tab_widget.addTab(self.energy_tab, "Энергия")
        
        main_layout.addWidget(content_widget)
    
    def create_parameters_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 20, 0, 20)
        
        outer_widget = QWidget()
        outer_layout = QVBoxLayout(outer_widget)
        outer_layout.setSpacing(10)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch()
        
        # ★ ГРУППА ПОДКЛЮЧЕНИЯ И КАЛИБРОВКИ ★
        connection_group = QGroupBox("Подключение и калибровка")
        connection_group.setFixedWidth(450)
        connection_layout = QHBoxLayout(connection_group)
        connection_layout.setSpacing(10)
        connection_layout.setContentsMargins(20, 10, 20, 10)
        
        self.connect_button = QPushButton("Подключить")
        self.connect_button.clicked.connect(self.toggle_connection)
        self.connect_button.setFixedWidth(120)
        connection_layout.addStretch()
        connection_layout.addWidget(self.connect_button)
        
        self.calibration_button = QPushButton("Калибровка")
        self.calibration_button.clicked.connect(self.perform_calibration)
        self.calibration_button.setEnabled(False)
        self.calibration_button.setFixedWidth(120)
        connection_layout.addWidget(self.calibration_button)
        
        self.calibration_reset_button = QPushButton("Сброс")
        self.calibration_reset_button.clicked.connect(self.reset_calibration)
        self.calibration_reset_button.setEnabled(False)
        self.calibration_reset_button.setFixedWidth(120)
        connection_layout.addWidget(self.calibration_reset_button)
        connection_layout.addStretch()
        
        outer_layout.addWidget(CenteredWidget(connection_group, outer_widget))
        
        params_group = QGroupBox("Параметры измерения")
        params_group.setFixedWidth(450)
        params_group.setMinimumHeight(400)
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(5)
        params_layout.setContentsMargins(20, 15, 20, 15)
        
        self.laser_wavelength_edit = QLineEdit(str(self.settings.get('laser_wavelength', 1064.0)))
        params_layout.addWidget(FieldRow("Длина волны лазера (нм):", self.laser_wavelength_edit))
        
        self.start_wavelength_edit = QLineEdit(str(self.settings.get('start_wavelength', 1300.0)))
        params_layout.addWidget(FieldRow("Начальная длина волны (нм):", self.start_wavelength_edit))
        
        self.end_wavelength_edit = QLineEdit(str(self.settings.get('end_wavelength', 1400.0)))
        params_layout.addWidget(FieldRow("Конечная длина волны (нм):", self.end_wavelength_edit))
        
        self.wavelength_step_edit = QLineEdit(str(self.settings.get('wavelength_step', 0.5)))
        params_layout.addWidget(FieldRow("Шаг сканирования (нм):", self.wavelength_step_edit))
        
        self.input_slit_edit = QLineEdit(str(self.settings.get('input_slit', 100.0)))
        params_layout.addWidget(FieldRow("Входная щель (мкм):", self.input_slit_edit))
        
        self.output_slit_edit = QLineEdit(str(self.settings.get('output_slit', 100.0)))
        params_layout.addWidget(FieldRow("Выходная щель (мкм):", self.output_slit_edit))
        
        self.oscilloscope_channel_edit = QLineEdit(str(self.settings.get('oscilloscope_channel', 1)))
        params_layout.addWidget(FieldRow("Канал осциллографа:", self.oscilloscope_channel_edit))
        
        self.average_count_edit = QLineEdit(str(self.settings.get('average_count', 1024)))
        params_layout.addWidget(FieldRow("Усреднение осциллографа:", self.average_count_edit))
        
        self.power_average_edit = QLineEdit(str(self.settings.get('power_average_count', 10)))
        params_layout.addWidget(FieldRow("Усреднение измерителя энергии:", self.power_average_edit))
        
        self.energy_points_edit = QLineEdit(str(self.settings.get('energy_points', 10)))
        params_layout.addWidget(FieldRow("Количество точек энергии:", self.energy_points_edit))
        
        self.reference_peak_edit = QLineEdit(str(self.settings.get('reference_peak', 1308.0)))
        params_layout.addWidget(FieldRow("Эталонный пик (нм):", self.reference_peak_edit))
        
        self.dual_integration_checkbox = QCheckBox("Дополнительные границы интегрирования")
        self.dual_integration_checkbox.setChecked(self.settings.get('dual_integration', False))
        self.dual_integration_checkbox.toggled.connect(self.on_dual_integration_toggled)
        params_layout.addWidget(CheckBoxRow(self.dual_integration_checkbox))
        
        status_layout = QHBoxLayout()
        status_layout.setSpacing(10)
        status_layout.setContentsMargins(20, 5, 20, 5)
        
        calibration_status_label = QLabel("Калибровка:")
        calibration_status_label.setMinimumWidth(180)
        calibration_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_layout.addWidget(calibration_status_label)
        
        self.calibration_status_value = QLabel("Не выполнена")
        self.calibration_status_value.setMinimumWidth(150)
        self.calibration_status_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.calibration_status_value.setStyleSheet("color: #888;")
        status_layout.addWidget(self.calibration_status_value)
        
        status_layout.addStretch()
        params_layout.addLayout(status_layout)
        
        offset_layout = QHBoxLayout()
        offset_layout.setSpacing(10)
        offset_layout.setContentsMargins(20, 0, 20, 5)
        
        calibration_offset_label = QLabel("Смещение:")
        calibration_offset_label.setMinimumWidth(180)
        calibration_offset_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        offset_layout.addWidget(calibration_offset_label)
        
        self.calibration_offset_value = QLabel("0.00 нм")
        self.calibration_offset_value.setMinimumWidth(150)
        self.calibration_offset_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        offset_layout.addWidget(self.calibration_offset_value)
        
        offset_layout.addStretch()
        params_layout.addLayout(offset_layout)
        
        outer_layout.addWidget(CenteredWidget(params_group, outer_widget))
        
        control_group = QGroupBox("Управление экспериментом")
        control_layout = QHBoxLayout(control_group)
        control_layout.setSpacing(10)
        control_layout.setContentsMargins(20, 10, 20, 10)
        
        self.start_button = QPushButton("Начать")
        self.start_button.clicked.connect(self.start_experiment)
        self.start_button.setEnabled(False)
        self.start_button.setFixedWidth(120)
        control_layout.addStretch()
        control_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop_experiment)
        self.stop_button.setEnabled(False)
        self.stop_button.setFixedWidth(120)
        control_layout.addWidget(self.stop_button)
        
        self.reset_button = QPushButton("Сбросить")
        self.reset_button.clicked.connect(self.reset_parameters)
        self.reset_button.setFixedWidth(120)
        control_layout.addWidget(self.reset_button)
        control_layout.addStretch()
        
        outer_layout.addWidget(CenteredWidget(control_group, outer_widget))
        
        progress_group = QGroupBox("Прогресс")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setContentsMargins(20, 10, 20, 10)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        progress_layout.addWidget(self.progress_bar)
        outer_layout.addWidget(CenteredWidget(progress_group, outer_widget))
        
        outer_layout.addStretch()
        
        layout.addWidget(outer_widget)
        
        return tab
    
    def create_signal_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(5)
        
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setSpacing(10)
        
        control_group = QGroupBox("Управление сигналом")
        control_group.setFixedWidth(450)
        control_group.setMinimumHeight(150)
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(5)
        control_layout.setContentsMargins(15, 10, 15, 10)
        
        self.signal_wavelength_edit = QLineEdit(str(self.settings.get('start_wavelength', 1300.0)))
        control_layout.addWidget(FieldRow("Длина волны (нм):", self.signal_wavelength_edit))
        
        self.signal_input_slit_edit = QLineEdit(str(self.settings.get('input_slit', 100.0)))
        control_layout.addWidget(FieldRow("Входная щель (мкм):", self.signal_input_slit_edit))
        
        self.signal_output_slit_edit = QLineEdit(str(self.settings.get('output_slit', 100.0)))
        control_layout.addWidget(FieldRow("Выходная щель (мкм):", self.signal_output_slit_edit))
        
        self.capture_button = QPushButton("Захватить сигнал")
        self.capture_button.clicked.connect(self.capture_signal)
        self.capture_button.setEnabled(False)
        self.capture_button.setFixedWidth(150)
        control_layout.addWidget(ButtonRow(self.capture_button))
        
        top_layout.addWidget(CenteredWidget(control_group, top_widget))
        
        integration_group = QGroupBox("Границы интегрирования")
        integration_group.setFixedWidth(800)
        integration_group.setMinimumHeight(150)
        integration_layout = QVBoxLayout(integration_group)
        integration_layout.setSpacing(5)
        integration_layout.setContentsMargins(15, 10, 15, 10)
        
        self.baseline_start_edit = QLineEdit(str(self.settings.get('baseline_start', -10e-6)))
        self.baseline_end_edit = QLineEdit(str(self.settings.get('baseline_end', -2e-6)))
        integration_layout.addWidget(DoubleFieldRow(
            "Фон (левая):", self.baseline_start_edit,
            "Фон (правая):", self.baseline_end_edit
        ))
        
        self.signal1_start_edit = QLineEdit(str(self.settings.get('signal1_start', -2e-6)))
        self.signal1_end_edit = QLineEdit(str(self.settings.get('signal1_end', 20e-6)))
        integration_layout.addWidget(DoubleFieldRow(
            "Сигнал 1 (левая):", self.signal1_start_edit,
            "Сигнал 1 (правая):", self.signal1_end_edit
        ))
        
        self.signal2_start_edit = QLineEdit(str(self.settings.get('signal2_start', 10e-6)))
        self.signal2_end_edit = QLineEdit(str(self.settings.get('signal2_end', 30e-6)))
        self.signal2_row = DoubleFieldRow(
            "Сигнал 2 (левая):", self.signal2_start_edit,
            "Сигнал 2 (правая):", self.signal2_end_edit
        )
        self.signal2_row.setVisible(self.settings.get('dual_integration', False))
        integration_layout.addWidget(self.signal2_row)
        
        self.update_bounds_button = QPushButton("Обновить границы")
        self.update_bounds_button.clicked.connect(self.update_integration_bounds)
        self.update_bounds_button.setFixedWidth(150)
        integration_layout.addWidget(ButtonRow(self.update_bounds_button))
        
        top_layout.addWidget(CenteredWidget(integration_group, top_widget))
        
        layout.addWidget(top_widget)
        
        self.signal_plot = SignalPlotView(self)
        layout.addWidget(self.signal_plot)
        
        return tab
    
    def create_spectrum_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(5)
        
        control_layout = QHBoxLayout()
        control_layout.setSpacing(10)
        
        control_layout.addStretch()
        
        self.save_spectrum_graph_button = QPushButton("Сохранить график")
        self.save_spectrum_graph_button.clicked.connect(lambda: self.save_graph_as_png(self.spectrum_plot))
        self.save_spectrum_graph_button.setFixedWidth(150)
        control_layout.addWidget(self.save_spectrum_graph_button)
        
        self.save_spectrum_data_button = QPushButton("Сохранить данные")
        self.save_spectrum_data_button.clicked.connect(self.export_spectrum_to_file)
        self.save_spectrum_data_button.setFixedWidth(150)
        control_layout.addWidget(self.save_spectrum_data_button)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        self.spectrum_plot = SpectrumPlotView(self)
        layout.addWidget(self.spectrum_plot)
        
        return tab
    
    def create_energy_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(5)
        
        control_layout = QHBoxLayout()
        control_layout.setSpacing(10)
        
        control_layout.addStretch()
        
        self.save_energy_graph_button = QPushButton("Сохранить график")
        self.save_energy_graph_button.clicked.connect(lambda: self.save_graph_as_png(self.energy_plot))
        self.save_energy_graph_button.setFixedWidth(150)
        control_layout.addWidget(self.save_energy_graph_button)
        
        self.save_energy_data_button = QPushButton("Сохранить данные")
        self.save_energy_data_button.clicked.connect(self.export_energy_to_file)
        self.save_energy_data_button.setFixedWidth(150)
        control_layout.addWidget(self.save_energy_data_button)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        self.energy_plot = EnergyPlotView(self)
        layout.addWidget(self.energy_plot)
        
        return tab
    
    def apply_theme(self):
        self.title_bar.update_style()
        self.setPalette(self.style().standardPalette())
        self.setStyleSheet("""
            QMainWindow { background-color: #f0f0f0; }
            QWidget { background-color: #f0f0f0; }
            QToolBar { background-color: #f0f0f0; border: none; }
            QTabWidget::pane { border: 1px solid #ccc; background-color: #f0f0f0; }
            QTabBar::tab { padding: 6px 12px; }
            QTabBar::tab:selected { border-bottom: 2px solid #0078d4; }
            QGroupBox { border: 1px solid #ccc; margin-top: 10px; padding-top: 8px; background-color: #f0f0f0; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit { border: 1px solid #ccc; padding: 4px; border-radius: 2px; }
            QLineEdit:focus { border: 1px solid #0078d4; }
            QPushButton { border: 1px solid #ccc; padding: 5px 10px; border-radius: 3px; background-color: #f0f0f0; }
            QPushButton:hover { background-color: #e0e0e0; }
            QPushButton:pressed { background-color: #d0d0d0; }
            QPushButton:disabled { color: #999; }
            QProgressBar { border: 1px solid #ccc; border-radius: 3px; text-align: center; }
            QProgressBar::chunk { background-color: #0078d4; border-radius: 3px; }
            QComboBox { border: 1px solid #ccc; padding: 4px; border-radius: 2px; }
            QComboBox:hover { border: 1px solid #999; }
            QComboBox QAbstractItemView { selection-background-color: #0078d4; }
            QComboBox QAbstractItemView::item:hover { background-color: #e0e0e0; }
            QChartView { background-color: white; }
        """)
    
    def on_dual_integration_toggled(self, checked):
        self.settings.set('dual_integration', checked)
        self.measurement.configuration.dual_integration_enabled = checked
        self.signal2_row.setVisible(checked)
    
    def toggle_connection(self):
        if self.is_connected:
            self.disconnect_instruments()
        else:
            self.connect_instruments()
    
    def connect_instruments(self):
        def connection_task():
            self.connect_button.setEnabled(False)
            self.connect_button.setText("Подключение...")
            
            success = self.measurement.connect_instruments()
            
            if success:
                self.is_connected = True
                self.connect_button.setText("Отключить")
                self.start_button.setEnabled(True)
                self.calibration_button.setEnabled(True)
                self.calibration_reset_button.setEnabled(True)
                self.capture_button.setEnabled(True)
                
                self.measurement.set_slit_widths(
                    float(self.settings.get('input_slit', 100.0)),
                    float(self.settings.get('output_slit', 100.0))
                )
            else:
                self.is_connected = False
                self.connect_button.setText("Подключить")
                QMessageBox.critical(
                    self,
                    "Ошибка подключения",
                    "Не удалось подключить оборудование!\nПроверьте соединения!"
                )
            
            self.connect_button.setEnabled(True)
        
        threading.Thread(target=connection_task, daemon=True).start()
    
    def disconnect_instruments(self):
        def disconnection_task():
            self.connect_button.setEnabled(False)
            
            self.measurement.disconnect_instruments()
            
            self.is_connected = False
            self.connect_button.setText("Подключить")
            self.start_button.setEnabled(False)
            self.calibration_button.setEnabled(False)
            self.calibration_reset_button.setEnabled(False)
            self.capture_button.setEnabled(False)
            
            self.connect_button.setEnabled(True)
        
        threading.Thread(target=disconnection_task, daemon=True).start()
    
    def reset_parameters(self):
        self.settings.reset_to_defaults()
        
        self.laser_wavelength_edit.setText(str(self.settings.get('laser_wavelength', 1064.0)))
        self.start_wavelength_edit.setText(str(self.settings.get('start_wavelength', 1300.0)))
        self.end_wavelength_edit.setText(str(self.settings.get('end_wavelength', 1400.0)))
        self.wavelength_step_edit.setText(str(self.settings.get('wavelength_step', 0.5)))
        self.input_slit_edit.setText(str(self.settings.get('input_slit', 100.0)))
        self.output_slit_edit.setText(str(self.settings.get('output_slit', 100.0)))
        self.oscilloscope_channel_edit.setText(str(self.settings.get('oscilloscope_channel', 1)))
        self.average_count_edit.setText(str(self.settings.get('average_count', 1024)))
        self.power_average_edit.setText(str(self.settings.get('power_average_count', 10)))
        self.energy_points_edit.setText(str(self.settings.get('energy_points', 10)))
        self.reference_peak_edit.setText(str(self.settings.get('reference_peak', 1308.0)))
        self.dual_integration_checkbox.setChecked(False)
        
        self.baseline_start_edit.setText("-1e-05")
        self.baseline_end_edit.setText("-2e-06")
        self.signal1_start_edit.setText("-2e-06")
        self.signal1_end_edit.setText("2e-05")
        self.signal2_start_edit.setText("1e-05")
        self.signal2_end_edit.setText("3e-05")
        
        self.signal_wavelength_edit.setText(str(self.settings.get('start_wavelength', 1300.0)))
        self.signal_input_slit_edit.setText(str(self.settings.get('input_slit', 100.0)))
        self.signal_output_slit_edit.setText(str(self.settings.get('output_slit', 100.0)))
        
        self.apply_parameters()
    
    def apply_parameters(self):
        try:
            self.measurement.configuration.laser_wavelength_nanometers = float(self.laser_wavelength_edit.text())
            self.measurement.configuration.start_wavelength_nanometers = float(self.start_wavelength_edit.text())
            self.measurement.configuration.end_wavelength_nanometers = float(self.end_wavelength_edit.text())
            self.measurement.configuration.wavelength_step_nanometers = float(self.wavelength_step_edit.text())
            self.measurement.configuration.input_slit_micrometers = float(self.input_slit_edit.text())
            self.measurement.configuration.output_slit_micrometers = float(self.output_slit_edit.text())
            self.measurement.configuration.oscilloscope_signal_channel = int(self.oscilloscope_channel_edit.text())
            self.measurement.configuration.oscilloscope_average_count = int(self.average_count_edit.text())
            self.measurement.configuration.power_meter_average_count = int(self.power_average_edit.text())
            self.measurement.configuration.dual_integration_enabled = self.dual_integration_checkbox.isChecked()
            self.measurement.configuration.reference_peak_nanometers = float(self.reference_peak_edit.text())
            
            self.settings.set('laser_wavelength', float(self.laser_wavelength_edit.text()))
            self.settings.set('start_wavelength', float(self.start_wavelength_edit.text()))
            self.settings.set('end_wavelength', float(self.end_wavelength_edit.text()))
            self.settings.set('wavelength_step', float(self.wavelength_step_edit.text()))
            self.settings.set('input_slit', float(self.input_slit_edit.text()))
            self.settings.set('output_slit', float(self.output_slit_edit.text()))
            self.settings.set('oscilloscope_channel', int(self.oscilloscope_channel_edit.text()))
            self.settings.set('average_count', int(self.average_count_edit.text()))
            self.settings.set('power_average_count', int(self.power_average_edit.text()))
            self.settings.set('dual_integration', self.dual_integration_checkbox.isChecked())
            self.settings.set('energy_points', int(self.energy_points_edit.text()))
            self.settings.set('reference_peak', float(self.reference_peak_edit.text()))
            
            if self.measurement.is_chromator_connected:
                self.measurement.set_slit_widths(
                    self.measurement.configuration.input_slit_micrometers,
                    self.measurement.configuration.output_slit_micrometers
                )
                self.measurement.set_chromator_wavelength(
                    self.measurement.configuration.start_wavelength_nanometers
                )
        except Exception:
            pass
    
    def capture_signal(self):
        def capture_task():
            self.capture_button.setEnabled(False)
            
            try:
                wavelength = float(self.signal_wavelength_edit.text())
                input_slit = float(self.signal_input_slit_edit.text())
                output_slit = float(self.signal_output_slit_edit.text())
                
                if self.measurement.is_chromator_connected:
                    self.measurement.set_slit_widths(input_slit, output_slit)
                    self.measurement.set_chromator_wavelength(wavelength)
                    time.sleep(0.2)
                
                self.measurement.configuration.oscilloscope_signal_channel = int(self.oscilloscope_channel_edit.text())
                self.measurement.configuration.oscilloscope_average_count = int(self.average_count_edit.text())
                
                self.measurement.setup_oscilloscope()
                
                success = self.measurement.capture_test_signal()
                
                if success:
                    self.signal_plot.set_signal_data(
                        self.measurement.test_signal_time,
                        self.measurement.processed_signal
                    )
                    self.update_integration_bounds()
            except Exception:
                pass
            
            self.capture_button.setEnabled(True)
        
        threading.Thread(target=capture_task, daemon=True).start()
    
    def update_integration_bounds(self):
        try:
            baseline_start = float(self.baseline_start_edit.text())
            baseline_end = float(self.baseline_end_edit.text())
            signal1_start = float(self.signal1_start_edit.text())
            signal1_end = float(self.signal1_end_edit.text())
            
            self.measurement.configuration.baseline_start_time_seconds = baseline_start
            self.measurement.configuration.baseline_end_time_seconds = baseline_end
            self.measurement.configuration.signal_integration_start_time_seconds = signal1_start
            self.measurement.configuration.signal_integration_end_time_seconds = signal1_end
            
            self.settings.set('baseline_start', baseline_start)
            self.settings.set('baseline_end', baseline_end)
            self.settings.set('signal1_start', signal1_start)
            self.settings.set('signal1_end', signal1_end)
            
            dual_enabled = self.settings.get('dual_integration', False)
            if dual_enabled:
                signal2_start = float(self.signal2_start_edit.text())
                signal2_end = float(self.signal2_end_edit.text())
                self.measurement.configuration.signal_integration_start_time_seconds_2 = signal2_start
                self.measurement.configuration.signal_integration_end_time_seconds_2 = signal2_end
                self.settings.set('signal2_start', signal2_start)
                self.settings.set('signal2_end', signal2_end)
            
            self.signal_plot.update_draggable_lines()
        except Exception:
            pass
    
    def update_integration_fields_from_lines(self, line_positions):
        for position_x, label_text in line_positions:
            if "Левый фон" in label_text:
                self.baseline_start_edit.setText(f"{position_x:.6e}")
            elif "Правый фон" in label_text:
                self.baseline_end_edit.setText(f"{position_x:.6e}")
            elif "Левый сигнал 1" in label_text:
                self.signal1_start_edit.setText(f"{position_x:.6e}")
            elif "Правый сигнал 1" in label_text:
                self.signal1_end_edit.setText(f"{position_x:.6e}")
            elif "Левый сигнал 2" in label_text:
                self.signal2_start_edit.setText(f"{position_x:.6e}")
            elif "Правый сигнал 2" in label_text:
                self.signal2_end_edit.setText(f"{position_x:.6e}")
    
    def perform_calibration(self):
        if not self.is_connected:
            return
        
        def calibration_task():
            self.calibration_button.setEnabled(False)
            self.start_button.setEnabled(False)
            
            try:
                reference_peak = float(self.reference_peak_edit.text())
                
                self.measurement.configuration.reference_peak_nanometers = reference_peak
                self.settings.set('reference_peak', reference_peak)
                
                self.progress_bar.setValue(0)
                
                self.measurement.scan_spectrum(self.update_progress)
                
                if not self.measurement.stop_requested and self.measurement.wavelengths_for_spectrum:
                    offset, success = self.measurement.perform_calibration(reference_peak)
                    
                    if success:
                        self.calibration_offset_value.setText(f"{offset:.2f} нм")
                        self.calibration_status_value.setText("Выполнена")
                        self.calibration_status_value.setStyleSheet("color: green;")
                        
                        QMessageBox.information(
                            self,
                            "Калибровка выполнена",
                            f"Смещение калибровки: {offset:.2f} нм\n"
                            f"Эталонный пик: {reference_peak:.1f} нм\n"
                            f"Измеренный пик: {reference_peak + offset:.1f} нм"
                        )
                    else:
                        self.calibration_status_value.setText("Не выполнена")
                        self.calibration_status_value.setStyleSheet("color: #888;")
                        QMessageBox.warning(
                            self,
                            "Ошибка калибровки",
                            "Не удалось найти пик спектра!\n"
                            "Проверьте настройки измерения."
                        )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    f"Произошла ошибка при калибровке:\n{str(e)}"
                )
            
            self.calibration_button.setEnabled(True)
            self.start_button.setEnabled(True)
        
        threading.Thread(target=calibration_task, daemon=True).start()
    
    def reset_calibration(self):
        self.measurement.reset_calibration()
        self.calibration_offset_value.setText("0.00 нм")
        self.calibration_status_value.setText("Не выполнена")
        self.calibration_status_value.setStyleSheet("color: #888;")
        
        if self.measurement.is_chromator_connected:
            self.measurement.set_chromator_wavelength(
                self.measurement.configuration.start_wavelength_nanometers
            )
    
    def start_experiment(self):
        if self.is_running:
            return
        
        self.apply_parameters()
        self.is_running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        
        def experiment_task():
            try:
                energy_points = int(self.energy_points_edit.text())
                
                self.progress_bar.setValue(0)
                self.measurement.measure_energy_series(energy_points, self.update_progress)
                
                if not self.measurement.stop_requested and self.measurement.energy_values:
                    self.energy_plot.set_energy_data(
                        self.measurement.energy_values,
                        self.measurement.integrated_values,
                        self.measurement.approximated_values,
                        self.measurement.integrated_values_2 if self.settings.get('dual_integration', False) else None,
                        self.measurement.approximated_values_2 if self.settings.get('dual_integration', False) else None
                    )
                
                if not self.measurement.stop_requested:
                    self.progress_bar.setValue(0)
                    self.measurement.scan_spectrum(self.update_progress)
                    
                    if not self.measurement.stop_requested and self.measurement.wavelengths_for_spectrum:
                        self.spectrum_plot.set_spectrum_data(
                            self.measurement.wavelengths_for_spectrum,
                            self.measurement.integrated_values,
                            self.measurement.approximated_values,
                            self.measurement.integrated_values_2 if self.settings.get('dual_integration', False) else None,
                            self.measurement.approximated_values_2 if self.settings.get('dual_integration', False) else None
                        )
                
                if self.measurement.stop_requested:
                    self.progress_bar.setValue(0)
            except Exception:
                pass
            
            self.is_running = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
        
        threading.Thread(target=experiment_task, daemon=True).start()
    
    def stop_experiment(self):
        self.measurement.stop_requested = True
        self.stop_button.setEnabled(False)
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
        QApplication.processEvents()
    
    def export_spectrum_to_file(self):
        data = self.measurement.get_saved_data()
        
        if not data['spectrum']['wavelengths']:
            QMessageBox.warning(self, "Предупреждение", "Нет данных для экспорта!")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт спектра", "",
            "CSV files (*.csv);;JSON files (*.json);;All files (*.*)"
        )
        if not file_path:
            return
        
        try:
            if file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            elif file_path.endswith('.csv'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("wavelength_nanometers,integrated_signal,approximated_signal\n")
                    for i in range(len(data['spectrum']['wavelengths'])):
                        f.write(f"{data['spectrum']['wavelengths'][i]:.3f},"
                                f"{data['spectrum']['integrated_values'][i]:.6e},"
                                f"{data['spectrum']['approximated_values'][i]:.6e}\n")
            QMessageBox.information(self, "Успех", f"Данные сохранены в {file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить данные:\n{str(e)}")
    
    def export_energy_to_file(self):
        data = self.measurement.get_saved_data()
        
        if not data['energy']['energy_values']:
            QMessageBox.warning(self, "Предупреждение", "Нет данных для экспорта!")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт энергии", "",
            "CSV files (*.csv);;JSON files (*.json);;All files (*.*)"
        )
        if not file_path:
            return
        
        try:
            if file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data['energy'], f, indent=2, ensure_ascii=False)
            elif file_path.endswith('.csv'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("energy_value,integrated_signal,approximated_signal\n")
                    for i in range(len(data['energy']['energy_values'])):
                        f.write(f"{data['energy']['energy_values'][i]:.6e},"
                                f"{data['energy']['integrated_values'][i]:.6e},"
                                f"{data['energy']['approximated_values'][i]:.6e}\n")
            QMessageBox.information(self, "Успех", f"Данные сохранены в {file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить данные:\n{str(e)}")
    
    def save_graph_as_png(self, plot_view):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить график", "",
            "PNG files (*.png);;All files (*.*)"
        )
        if file_path:
            pixmap = plot_view.grab()
            pixmap.save(file_path, 'PNG')
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.title_bar.geometry().contains(event.pos()):
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            self.dragging = True
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if hasattr(self, 'dragging') and self.dragging:
            self.move(event.globalPos() - self.drag_position)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if hasattr(self, 'dragging'):
            self.dragging = False
        super().mouseReleaseEvent(event)


if __name__ == "__main__":
    application = QApplication(sys.argv)
    application.setStyle('Fusion')
    main_window = MainApplicationWindow()
    main_window.show()
    sys.exit(application.exec_())