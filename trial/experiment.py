import sys
import os
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
import threading
import time
import traceback

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
    from mathematics import integrate_signal, approximate_signal, energy_calibration
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
    
    def integrate_signal(time_values, signal_values):
        if len(time_values) < 2:
            return 0.0
        return np.trapz(signal_values, time_values)
    
    def approximate_signal(time_values, signal_values, use_background=True):
        return signal_values, {"fit_successful": True, "signal_amplitude_volts": max(signal_values) - min(signal_values)}
    
    def energy_calibration(reference_energies, measured_signals, force_zero=True):
        return {"calibration_success": True, "detector_sensitivity": 1e-6, "fit_quality": 0.99, "dark_signal_offset": 0}

class SettingsManager:
    def __init__(self):
        self.settings_file = "spectrum_settings.json"
        self.settings = {
            'language': 'ru',
            'theme': 'light',
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
        }
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
        
        self.maximize_button = QPushButton("□")
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
            self.maximize_button.setText("□")
        else:
            self.parent.showMaximized()
            self.maximize_button.setText("❐")
    
    def update_style(self):
        theme = self.parent.current_theme if hasattr(self.parent, 'current_theme') else 'light'
        if theme == 'dark':
            self.setStyleSheet("""
                QWidget { background-color: #353535; }
                QLabel { color: white; }
                QPushButton { background-color: transparent; color: white; border: none; font-size: 14px; }
                QPushButton:hover { background-color: #454545; }
                QPushButton#close_button:hover { background-color: #e81123; }
            """)
            self.close_button.setObjectName("close_button")
        else:
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
            (configuration.baseline_start_time_seconds, "Левый\nфон", Qt.red, "baseline_start"),
            (configuration.baseline_end_time_seconds, "Правый\nфон", Qt.red, "baseline_end"),
            (configuration.signal_integration_start_time_seconds, "Левый\nсигнал" if not dual_integration else "Левый\nсигнал 1", Qt.green, "signal1_start"),
            (configuration.signal_integration_end_time_seconds, "Правый\nсигнал" if not dual_integration else "Правый\nсигнал 1", Qt.green, "signal1_end"),
        ]
        
        if dual_integration:
            line_configurations.extend([
                (configuration.signal_integration_start_time_seconds_2, "Левый\nсигнал 2", Qt.blue, "signal2_start"),
                (configuration.signal_integration_end_time_seconds_2, "Правый\nсигнал 2", Qt.blue, "signal2_end"),
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
                self.oscilloscope_device.disconnect()
                self.is_oscilloscope_connected = False
            except Exception:
                pass
    
    def set_chromator_wavelength(self, wavelength_nanometers):
        if self.chromator_device:
            self.chromator_device.set_wavelength(wavelength_nanometers)
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
        
        self.test_signal_time, self.test_signal_voltage = self.oscilloscope_device.capture_waveform(
            self.configuration.oscilloscope_signal_channel, 2000
        )
        if not self.test_signal_voltage:
            return False
        
        baseline_time_values = []
        baseline_signal_values = []
        for index in range(len(self.test_signal_time)):
            if self.configuration.baseline_start_time_seconds <= self.test_signal_time[index] <= self.configuration.baseline_end_time_seconds:
                baseline_time_values.append(self.test_signal_time[index])
                baseline_signal_values.append(self.test_signal_voltage[index])
        if baseline_signal_values:
            baseline_level = np.mean(baseline_signal_values)
            self.processed_signal = [voltage - baseline_level for voltage in self.test_signal_voltage]
        else:
            self.processed_signal = self.test_signal_voltage.copy()
        return True
    
    def measure_integrated_signal(self):
        if not self.oscilloscope_device:
            return 0.0
        time_values, voltage_values = self.oscilloscope_device.capture_waveform(
            self.configuration.oscilloscope_signal_channel, 2000
        )
        if not voltage_values:
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
        result = integrate_signal(integration_time_values, integration_signal_values)
        return result
    
    def measure_approximated_signal(self):
        if not self.oscilloscope_device:
            return 0.0
        time_values, voltage_values = self.oscilloscope_device.capture_waveform(
            self.configuration.oscilloscope_signal_channel, 2000
        )
        if not voltage_values:
            return 0.0
        approximated_signal, fit_parameters = approximate_signal(time_values, voltage_values, use_background=True)
        if fit_parameters.get("fit_successful", False):
            return fit_parameters.get("signal_amplitude_volts", 0.0)
        return max(approximated_signal) if approximated_signal else 0.0
    
    def measure_integrated_signal_2(self):
        if not self.oscilloscope_device:
            return 0.0
        time_values, voltage_values = self.oscilloscope_device.capture_waveform(
            self.configuration.oscilloscope_signal_channel, 2000
        )
        if not voltage_values:
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
    
    def measure_approximated_signal_2(self):
        if not self.oscilloscope_device:
            return 0.0
        time_values, voltage_values = self.oscilloscope_device.capture_waveform(
            self.configuration.oscilloscope_signal_channel, 2000
        )
        if not voltage_values:
            return 0.0
        approximated_signal, fit_parameters = approximate_signal(time_values, voltage_values, use_background=True)
        if fit_parameters.get("fit_successful", False):
            return fit_parameters.get("signal_amplitude_volts", 0.0)
        return max(approximated_signal) if approximated_signal else 0.0
    
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
        
        if self.chromator_device:
            self.chromator_device.set_acquisition_type("AVER")
            self.chromator_device.set_average_count(self.configuration.oscilloscope_average_count)
        
        for point_index, wavelength in enumerate(wavelength_list):
            if self.stop_requested:
                break
            
            self.set_chromator_wavelength(wavelength)
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
        
        return len(self.wavelengths_for_spectrum) > 0
    
    def measure_energy_series(self, points_count, progress_callback):
        self.stop_requested = False
        self.energy_values = []
        self.integrated_values = []
        self.approximated_values = []
        self.integrated_values_2 = []
        self.approximated_values_2 = []
        
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
        self.settings = SettingsManager()
        self.measurement = SpectrumMeasurement()
        self.current_language = self.settings.get('language', 'ru')
        self.current_theme = self.settings.get('theme', 'light')
        self.is_connected = False
        self.is_running = False
        self.translations = self.get_translations()
        
        icon_path = Path(sys.executable).parent / "icon.png" if getattr(sys, "frozen", False) else Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        self.setup_user_interface()
        self.apply_theme(self.current_theme)
        self.update_language(self.current_language)
        
        self.worker_thread = None
    
    def get_translations(self):
        return {
            'ru': {
                'window_title': 'Измерение спектров',
                'tab_params': 'Параметры',
                'tab_signal': 'Сигнал',
                'tab_spectrum': 'Спектр',
                'tab_energy': 'Энергия',
                'language': 'Язык:',
                'theme': 'Тема:',
                'russian': 'Русский',
                'english': 'English',
                'light': 'Светлая',
                'dark': 'Тёмная',
                'connect': 'Подключить',
                'disconnect': 'Отключить',
                'start': 'Начать',
                'stop': 'Остановить',
                'reset': 'Сбросить',
                'params_group': 'Параметры измерения',
                'laser_wavelength': 'Длина волны лазера (нм):',
                'start_wavelength': 'Начальная длина волны (нм):',
                'end_wavelength': 'Конечная длина волны (нм):',
                'scan_step': 'Шаг сканирования (нм):',
                'input_slit': 'Входная щель (мкм):',
                'output_slit': 'Выходная щель (мкм):',
                'osc_channel': 'Канал осциллографа:',
                'osc_averaging': 'Усреднение осциллографа:',
                'power_averaging': 'Усреднение измерителя энергии:',
                'dual_integration': 'Дополнительные границы интегрирования',
                'energy_points': 'Количество точек энергии:',
                'control_group': 'Управление',
                'progress_group': 'Прогресс',
                'signal_control': 'Управление сигналом',
                'wavelength': 'Длина волны (нм):',
                'capture': 'Захватить сигнал',
                'integration_bounds': 'Границы интегрирования',
                'bg_left': 'Фон (левая):',
                'bg_right': 'Фон (правая):',
                'sig1_left': 'Сигнал 1 (левая):',
                'sig1_right': 'Сигнал 1 (правая):',
                'sig2_left': 'Сигнал 2 (левая):',
                'sig2_right': 'Сигнал 2 (правая):',
                'update_bounds': 'Обновить границы',
                'save_graph': 'Сохранить график',
                'save_data': 'Сохранить данные',
                'connection_error': 'Не удалось подключить оборудование!\nПроверьте соединения!',
                'connection_error_title': 'Ошибка подключения',
                'integration': 'Интегрирование',
                'approximation': 'Аппроксимация',
            },
            'en': {
                'window_title': 'Spectrum Measurement',
                'tab_params': 'Parameters',
                'tab_signal': 'Signal',
                'tab_spectrum': 'Spectrum',
                'tab_energy': 'Energy',
                'language': 'Language:',
                'theme': 'Theme:',
                'russian': 'Russian',
                'english': 'English',
                'light': 'Light',
                'dark': 'Dark',
                'connect': 'Connect',
                'disconnect': 'Disconnect',
                'start': 'Start',
                'stop': 'Stop',
                'reset': 'Reset',
                'params_group': 'Measurement Parameters',
                'laser_wavelength': 'Laser wavelength (nm):',
                'start_wavelength': 'Start wavelength (nm):',
                'end_wavelength': 'End wavelength (nm):',
                'scan_step': 'Scan step (nm):',
                'input_slit': 'Input slit (µm):',
                'output_slit': 'Output slit (µm):',
                'osc_channel': 'Oscilloscope channel:',
                'osc_averaging': 'Oscilloscope averaging:',
                'power_averaging': 'Power meter averaging:',
                'dual_integration': 'Additional integration bounds',
                'energy_points': 'Energy points count:',
                'control_group': 'Control',
                'progress_group': 'Progress',
                'signal_control': 'Signal Control',
                'wavelength': 'Wavelength (nm):',
                'capture': 'Capture signal',
                'integration_bounds': 'Integration bounds',
                'bg_left': 'Background (left):',
                'bg_right': 'Background (right):',
                'sig1_left': 'Signal 1 (left):',
                'sig1_right': 'Signal 1 (right):',
                'sig2_left': 'Signal 2 (left):',
                'sig2_right': 'Signal 2 (right):',
                'update_bounds': 'Update bounds',
                'save_graph': 'Save graph',
                'save_data': 'Save data',
                'connection_error': 'Failed to connect equipment!\nCheck connections!',
                'connection_error_title': 'Connection Error',
                'integration': 'Integration',
                'approximation': 'Approximation',
            }
        }
    
    def tr(self, text):
        return self.translations.get(self.current_language, {}).get(text, text)
    
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
        
        toolbar = self.create_toolbar()
        content_layout.addWidget(toolbar)
        
        self.tab_widget = QTabWidget()
        content_layout.addWidget(self.tab_widget)
        
        self.parameters_tab = self.create_parameters_tab()
        self.tab_widget.addTab(self.parameters_tab, self.tr('tab_params'))
        
        self.signal_tab = self.create_signal_tab()
        self.tab_widget.addTab(self.signal_tab, self.tr('tab_signal'))
        
        self.spectrum_tab = self.create_spectrum_tab()
        self.tab_widget.addTab(self.spectrum_tab, self.tr('tab_spectrum'))
        
        self.energy_tab = self.create_energy_tab()
        self.tab_widget.addTab(self.energy_tab, self.tr('tab_energy'))
        
        main_layout.addWidget(content_widget)
    
    def create_toolbar(self):
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(5, 2, 5, 2)
        toolbar_layout.setSpacing(10)
        
        self.language_label = QLabel(self.tr('language'))
        toolbar_layout.addWidget(self.language_label)
        
        self.language_combo = QComboBox()
        self.language_combo.addItems([self.tr('russian'), self.tr('english')])
        self.language_combo.setCurrentIndex(0 if self.current_language == 'ru' else 1)
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)
        self.language_combo.setFixedWidth(100)
        toolbar_layout.addWidget(self.language_combo)
        
        toolbar_layout.addSpacing(10)
        
        self.theme_label = QLabel(self.tr('theme'))
        toolbar_layout.addWidget(self.theme_label)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([self.tr('light'), self.tr('dark')])
        self.theme_combo.setCurrentIndex(0 if self.current_theme == 'light' else 1)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        self.theme_combo.setFixedWidth(100)
        toolbar_layout.addWidget(self.theme_combo)
        
        toolbar_layout.addSpacing(10)
        
        self.connect_button = QPushButton(self.tr('connect'))
        self.connect_button.clicked.connect(self.toggle_connection)
        self.connect_button.setFixedWidth(100)
        toolbar_layout.addWidget(self.connect_button)
        
        toolbar_layout.addStretch()
        
        return toolbar_widget
    
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
        
        params_group = QGroupBox(self.tr('params_group'))
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(5)
        params_layout.setContentsMargins(20, 15, 20, 15)
        
        self.laser_wavelength_edit = QLineEdit(str(self.settings.get('laser_wavelength', 1064.0)))
        params_layout.addWidget(FieldRow(self.tr('laser_wavelength'), self.laser_wavelength_edit))
        
        self.start_wavelength_edit = QLineEdit(str(self.settings.get('start_wavelength', 1300.0)))
        params_layout.addWidget(FieldRow(self.tr('start_wavelength'), self.start_wavelength_edit))
        
        self.end_wavelength_edit = QLineEdit(str(self.settings.get('end_wavelength', 1400.0)))
        params_layout.addWidget(FieldRow(self.tr('end_wavelength'), self.end_wavelength_edit))
        
        self.wavelength_step_edit = QLineEdit(str(self.settings.get('wavelength_step', 0.5)))
        params_layout.addWidget(FieldRow(self.tr('scan_step'), self.wavelength_step_edit))
        
        self.input_slit_edit = QLineEdit(str(self.settings.get('input_slit', 100.0)))
        params_layout.addWidget(FieldRow(self.tr('input_slit'), self.input_slit_edit))
        
        self.output_slit_edit = QLineEdit(str(self.settings.get('output_slit', 100.0)))
        params_layout.addWidget(FieldRow(self.tr('output_slit'), self.output_slit_edit))
        
        self.oscilloscope_channel_edit = QLineEdit(str(self.settings.get('oscilloscope_channel', 1)))
        params_layout.addWidget(FieldRow(self.tr('osc_channel'), self.oscilloscope_channel_edit))
        
        self.average_count_edit = QLineEdit(str(self.settings.get('average_count', 1024)))
        params_layout.addWidget(FieldRow(self.tr('osc_averaging'), self.average_count_edit))
        
        self.power_average_edit = QLineEdit(str(self.settings.get('power_average_count', 10)))
        params_layout.addWidget(FieldRow(self.tr('power_averaging'), self.power_average_edit))
        
        self.energy_points_edit = QLineEdit(str(self.settings.get('energy_points', 10)))
        params_layout.addWidget(FieldRow(self.tr('energy_points'), self.energy_points_edit))
        
        self.dual_integration_checkbox = QCheckBox(self.tr('dual_integration'))
        self.dual_integration_checkbox.setChecked(self.settings.get('dual_integration', False))
        self.dual_integration_checkbox.toggled.connect(self.on_dual_integration_toggled)
        params_layout.addWidget(CheckBoxRow(self.dual_integration_checkbox))
        
        outer_layout.addWidget(CenteredWidget(params_group, outer_widget))
        
        control_group = QGroupBox(self.tr('control_group'))
        control_layout = QHBoxLayout(control_group)
        control_layout.setSpacing(10)
        control_layout.setContentsMargins(20, 10, 20, 10)
        
        self.start_button = QPushButton(self.tr('start'))
        self.start_button.clicked.connect(self.start_experiment)
        self.start_button.setEnabled(False)
        self.start_button.setFixedWidth(120)
        control_layout.addStretch()
        control_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton(self.tr('stop'))
        self.stop_button.clicked.connect(self.stop_experiment)
        self.stop_button.setEnabled(False)
        self.stop_button.setFixedWidth(120)
        control_layout.addWidget(self.stop_button)
        
        self.reset_button = QPushButton(self.tr('reset'))
        self.reset_button.clicked.connect(self.reset_parameters)
        self.reset_button.setFixedWidth(120)
        control_layout.addWidget(self.reset_button)
        control_layout.addStretch()
        
        outer_layout.addWidget(CenteredWidget(control_group, outer_widget))
        
        progress_group = QGroupBox(self.tr('progress_group'))
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
        
        control_group = QGroupBox(self.tr('signal_control'))
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(5)
        control_layout.setContentsMargins(15, 10, 15, 10)
        
        self.signal_wavelength_edit = QLineEdit(str(self.settings.get('start_wavelength', 1300.0)))
        control_layout.addWidget(FieldRow(self.tr('wavelength'), self.signal_wavelength_edit))
        
        self.signal_input_slit_edit = QLineEdit(str(self.settings.get('input_slit', 100.0)))
        control_layout.addWidget(FieldRow(self.tr('input_slit'), self.signal_input_slit_edit))
        
        self.signal_output_slit_edit = QLineEdit(str(self.settings.get('output_slit', 100.0)))
        control_layout.addWidget(FieldRow(self.tr('output_slit'), self.signal_output_slit_edit))
        
        self.capture_button = QPushButton(self.tr('capture'))
        self.capture_button.clicked.connect(self.capture_signal)
        self.capture_button.setEnabled(False)
        self.capture_button.setFixedWidth(150)
        control_layout.addWidget(ButtonRow(self.capture_button))
        
        top_layout.addWidget(CenteredWidget(control_group, top_widget))
        
        integration_group = QGroupBox(self.tr('integration_bounds'))
        integration_layout = QVBoxLayout(integration_group)
        integration_layout.setSpacing(5)
        integration_layout.setContentsMargins(15, 10, 15, 10)
        
        self.baseline_start_edit = QLineEdit(str(self.settings.get('baseline_start', -10e-6)))
        self.baseline_end_edit = QLineEdit(str(self.settings.get('baseline_end', -2e-6)))
        integration_layout.addWidget(DoubleFieldRow(
            self.tr('bg_left'), self.baseline_start_edit,
            self.tr('bg_right'), self.baseline_end_edit
        ))
        
        self.signal1_start_edit = QLineEdit(str(self.settings.get('signal1_start', -2e-6)))
        self.signal1_end_edit = QLineEdit(str(self.settings.get('signal1_end', 20e-6)))
        integration_layout.addWidget(DoubleFieldRow(
            self.tr('sig1_left'), self.signal1_start_edit,
            self.tr('sig1_right'), self.signal1_end_edit
        ))
        
        self.signal2_start_edit = QLineEdit(str(self.settings.get('signal2_start', 10e-6)))
        self.signal2_end_edit = QLineEdit(str(self.settings.get('signal2_end', 30e-6)))
        self.signal2_row = DoubleFieldRow(
            self.tr('sig2_left'), self.signal2_start_edit,
            self.tr('sig2_right'), self.signal2_end_edit
        )
        self.signal2_row.setVisible(self.settings.get('dual_integration', False))
        integration_layout.addWidget(self.signal2_row)
        
        self.update_bounds_button = QPushButton(self.tr('update_bounds'))
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
        
        self.save_spectrum_graph_button = QPushButton(self.tr('save_graph'))
        self.save_spectrum_graph_button.clicked.connect(lambda: self.save_graph_as_png(self.spectrum_plot))
        self.save_spectrum_graph_button.setFixedWidth(150)
        control_layout.addWidget(self.save_spectrum_graph_button)
        
        self.save_spectrum_data_button = QPushButton(self.tr('save_data'))
        self.save_spectrum_data_button.clicked.connect(self.save_spectrum_to_file)
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
        
        self.save_energy_graph_button = QPushButton(self.tr('save_graph'))
        self.save_energy_graph_button.clicked.connect(lambda: self.save_graph_as_png(self.energy_plot))
        self.save_energy_graph_button.setFixedWidth(150)
        control_layout.addWidget(self.save_energy_graph_button)
        
        self.save_energy_data_button = QPushButton(self.tr('save_data'))
        self.save_energy_data_button.clicked.connect(self.save_energy_to_file)
        self.save_energy_data_button.setFixedWidth(150)
        control_layout.addWidget(self.save_energy_data_button)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        self.energy_plot = EnergyPlotView(self)
        layout.addWidget(self.energy_plot)
        
        return tab
    
    def on_language_changed(self, index):
        language = 'ru' if index == 0 else 'en'
        self.current_language = language
        self.settings.set('language', language)
        self.update_language(language)
    
    def update_language(self, language):
        self.title_bar.title_label.setText(self.tr('window_title'))
        self.setWindowTitle(self.tr('window_title'))
        
        self.tab_widget.setTabText(0, self.tr('tab_params'))
        self.tab_widget.setTabText(1, self.tr('tab_signal'))
        self.tab_widget.setTabText(2, self.tr('tab_spectrum'))
        self.tab_widget.setTabText(3, self.tr('tab_energy'))
        
        self.language_label.setText(self.tr('language'))
        self.theme_label.setText(self.tr('theme'))
        
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        self.language_combo.addItems([self.tr('russian'), self.tr('english')])
        self.language_combo.setCurrentIndex(0 if language == 'ru' else 1)
        self.language_combo.blockSignals(False)
        
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems([self.tr('light'), self.tr('dark')])
        self.theme_combo.setCurrentIndex(0 if self.current_theme == 'light' else 1)
        self.theme_combo.blockSignals(False)
        
        self.connect_button.setText(self.tr('disconnect' if self.is_connected else 'connect'))
        self.start_button.setText(self.tr('start'))
        self.stop_button.setText(self.tr('stop'))
        self.reset_button.setText(self.tr('reset'))
        self.capture_button.setText(self.tr('capture'))
        self.update_bounds_button.setText(self.tr('update_bounds'))
        self.save_spectrum_graph_button.setText(self.tr('save_graph'))
        self.save_spectrum_data_button.setText(self.tr('save_data'))
        self.save_energy_graph_button.setText(self.tr('save_graph'))
        self.save_energy_data_button.setText(self.tr('save_data'))
        
        self.update_tab_texts()
    
    def update_tab_texts(self):
        for child in self.parameters_tab.findChildren(QGroupBox):
            title = child.title()
            if title in ['Параметры измерения', 'Measurement Parameters']:
                child.setTitle(self.tr('params_group'))
            elif title in ['Управление', 'Control']:
                child.setTitle(self.tr('control_group'))
            elif title in ['Прогресс', 'Progress']:
                child.setTitle(self.tr('progress_group'))
        
        for child in self.signal_tab.findChildren(QGroupBox):
            title = child.title()
            if title in ['Управление сигналом', 'Signal Control']:
                child.setTitle(self.tr('signal_control'))
            elif title in ['Границы интегрирования', 'Integration bounds']:
                child.setTitle(self.tr('integration_bounds'))
        
        self.dual_integration_checkbox.setText(self.tr('dual_integration'))
        
        for widget in self.signal_tab.findChildren(DoubleFieldRow):
            if hasattr(widget, 'label_left') and widget.label_left:
                if 'Фон (левая):' in widget.label_left.text() or 'Background (left):' in widget.label_left.text():
                    widget.label_left.setText(self.tr('bg_left'))
                elif 'Сигнал 1 (левая):' in widget.label_left.text() or 'Signal 1 (left):' in widget.label_left.text():
                    widget.label_left.setText(self.tr('sig1_left'))
                elif 'Сигнал 2 (левая):' in widget.label_left.text() or 'Signal 2 (left):' in widget.label_left.text():
                    widget.label_left.setText(self.tr('sig2_left'))
            
            if hasattr(widget, 'label_right') and widget.label_right:
                if 'Фон (правая):' in widget.label_right.text() or 'Background (right):' in widget.label_right.text():
                    widget.label_right.setText(self.tr('bg_right'))
                elif 'Сигнал 1 (правая):' in widget.label_right.text() or 'Signal 1 (right):' in widget.label_right.text():
                    widget.label_right.setText(self.tr('sig1_right'))
                elif 'Сигнал 2 (правая):' in widget.label_right.text() or 'Signal 2 (right):' in widget.label_right.text():
                    widget.label_right.setText(self.tr('sig2_right'))
        
        for widget in self.signal_tab.findChildren(FieldRow):
            if hasattr(widget, 'label') and widget.label:
                if 'Длина волны (нм):' in widget.label.text() or 'Wavelength (nm):' in widget.label.text():
                    widget.label.setText(self.tr('wavelength'))
                elif 'Входная щель (мкм):' in widget.label.text() or 'Input slit (µm):' in widget.label.text():
                    widget.label.setText(self.tr('input_slit'))
                elif 'Выходная щель (мкм):' in widget.label.text() or 'Output slit (µm):' in widget.label.text():
                    widget.label.setText(self.tr('output_slit'))
        
        for widget in self.parameters_tab.findChildren(FieldRow):
            if hasattr(widget, 'label') and widget.label:
                text = widget.label.text()
                if 'Длина волны лазера (нм):' in text or 'Laser wavelength (nm):' in text:
                    widget.label.setText(self.tr('laser_wavelength'))
                elif 'Начальная длина волны (нм):' in text or 'Start wavelength (nm):' in text:
                    widget.label.setText(self.tr('start_wavelength'))
                elif 'Конечная длина волны (нм):' in text or 'End wavelength (nm):' in text:
                    widget.label.setText(self.tr('end_wavelength'))
                elif 'Шаг сканирования (нм):' in text or 'Scan step (nm):' in text:
                    widget.label.setText(self.tr('scan_step'))
                elif 'Входная щель (мкм):' in text or 'Input slit (µm):' in text:
                    widget.label.setText(self.tr('input_slit'))
                elif 'Выходная щель (мкм):' in text or 'Output slit (µm):' in text:
                    widget.label.setText(self.tr('output_slit'))
                elif 'Канал осциллографа:' in text or 'Oscilloscope channel:' in text:
                    widget.label.setText(self.tr('osc_channel'))
                elif 'Усреднение осциллографа:' in text or 'Oscilloscope averaging:' in text:
                    widget.label.setText(self.tr('osc_averaging'))
                elif 'Усреднение измерителя энергии:' in text or 'Power meter averaging:' in text:
                    widget.label.setText(self.tr('power_averaging'))
                elif 'Количество точек энергии:' in text or 'Energy points count:' in text:
                    widget.label.setText(self.tr('energy_points'))
    
    def on_theme_changed(self, index):
        theme = 'light' if index == 0 else 'dark'
        self.current_theme = theme
        self.settings.set('theme', theme)
        self.apply_theme(theme)
    
    def apply_theme(self, theme):
        self.title_bar.update_style()
        
        if theme == 'dark':
            dark_palette = QPalette()
            dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.WindowText, Qt.white)
            dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
            dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
            dark_palette.setColor(QPalette.ToolTipText, Qt.white)
            dark_palette.setColor(QPalette.Text, Qt.white)
            dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ButtonText, Qt.white)
            dark_palette.setColor(QPalette.BrightText, Qt.red)
            dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.HighlightedText, Qt.black)
            self.setPalette(dark_palette)
            
            self.setStyleSheet("""
                QMainWindow { background-color: #353535; }
                QWidget { background-color: #353535; }
                QToolBar { background-color: #353535; border: none; }
                QToolBar QLabel { color: white; }
                QTabWidget::pane { background-color: #353535; border: 1px solid #555; }
                QTabBar::tab { background-color: #353535; color: white; padding: 6px 12px; }
                QTabBar::tab:selected { background-color: #2d2d2d; border-bottom: 2px solid #42a5f5; }
                QTabBar::tab:hover { background-color: #454545; }
                QGroupBox { color: white; border: 1px solid #555; margin-top: 10px; padding-top: 8px; background-color: #353535; }
                QGroupBox::title { color: white; subcontrol-origin: margin; left: 10px; padding: 0 5px; }
                QLabel { color: white; }
                QLineEdit { background-color: #2d2d2d; color: white; border: 1px solid #555; padding: 4px; border-radius: 2px; }
                QLineEdit:focus { border: 1px solid #42a5f5; }
                QPushButton { background-color: #2d2d2d; color: white; border: 1px solid #555; padding: 5px 10px; border-radius: 3px; }
                QPushButton:hover { background-color: #3d3d3d; border: 1px solid #666; }
                QPushButton:pressed { background-color: #1d1d1d; }
                QPushButton:disabled { color: #666; background-color: #1d1d1d; }
                QCheckBox { color: white; }
                QCheckBox::indicator { width: 16px; height: 16px; }
                QProgressBar { background-color: #2d2d2d; border: 1px solid #555; border-radius: 3px; text-align: center; color: white; }
                QProgressBar::chunk { background-color: #42a5f5; border-radius: 3px; }
                QComboBox { background-color: #2d2d2d; color: white; border: 1px solid #555; padding: 4px; border-radius: 2px; }
                QComboBox:hover { background-color: #3d3d3d; border: 1px solid #666; }
                QComboBox::drop-down { border: none; }
                QComboBox::down-arrow { image: none; border-left: 1px solid #555; padding: 2px; }
                QComboBox QAbstractItemView { background-color: #2d2d2d; color: white; selection-background-color: #42a5f5; border: 1px solid #555; }
                QComboBox QAbstractItemView::item:hover { background-color: #3d3d3d; }
                QChartView { background-color: #2d2d2d; }
            """)
        else:
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
                self.connect_button.setText(self.tr('disconnect'))
                self.start_button.setEnabled(True)
                self.capture_button.setEnabled(True)
                
                self.measurement.set_slit_widths(
                    float(self.settings.get('input_slit', 100.0)),
                    float(self.settings.get('output_slit', 100.0))
                )
            else:
                self.is_connected = False
                self.connect_button.setText(self.tr('connect'))
                error_box = QMessageBox()
                error_box.setIcon(QMessageBox.Critical)
                error_box.setWindowTitle(self.tr('connection_error_title'))
                error_box.setText(self.tr('connection_error'))
                error_box.exec_()
            
            self.connect_button.setEnabled(True)
        
        threading.Thread(target=connection_task, daemon=True).start()
    
    def disconnect_instruments(self):
        def disconnection_task():
            self.connect_button.setEnabled(False)
            
            self.measurement.disconnect_instruments()
            
            self.is_connected = False
            self.connect_button.setText(self.tr('connect'))
            self.start_button.setEnabled(False)
            self.capture_button.setEnabled(False)
            
            self.connect_button.setEnabled(True)
        
        threading.Thread(target=disconnection_task, daemon=True).start()
    
    def reset_parameters(self):
        self.laser_wavelength_edit.setText("1064.0")
        self.start_wavelength_edit.setText("1300.0")
        self.end_wavelength_edit.setText("1400.0")
        self.wavelength_step_edit.setText("0.5")
        self.input_slit_edit.setText("100.0")
        self.output_slit_edit.setText("100.0")
        self.oscilloscope_channel_edit.setText("1")
        self.average_count_edit.setText("1024")
        self.power_average_edit.setText("10")
        self.energy_points_edit.setText("10")
        self.dual_integration_checkbox.setChecked(False)
        
        self.baseline_start_edit.setText("-1e-05")
        self.baseline_end_edit.setText("-2e-06")
        self.signal1_start_edit.setText("-2e-06")
        self.signal1_end_edit.setText("2e-05")
        self.signal2_start_edit.setText("1e-05")
        self.signal2_end_edit.setText("3e-05")
        
        self.signal_wavelength_edit.setText("1300.0")
        self.signal_input_slit_edit.setText("100.0")
        self.signal_output_slit_edit.setText("100.0")
        
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
    
    def save_graph_as_png(self, plot_view):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Graph", "",
            "PNG files (*.png);;All files (*.*)"
        )
        if file_path:
            pixmap = plot_view.grab()
            pixmap.save(file_path, 'PNG')
    
    def save_spectrum_to_file(self):
        if not self.measurement.wavelengths_for_spectrum:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Spectrum Data", "",
            "CSV files (*.csv);;All files (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file_handle:
                    file_handle.write("wavelength_nanometers,integrated_signal_1,approximated_signal_1")
                    if self.settings.get('dual_integration', False):
                        file_handle.write(",integrated_signal_2,approximated_signal_2")
                    file_handle.write("\n")
                    
                    for index in range(len(self.measurement.wavelengths_for_spectrum)):
                        line = f"{self.measurement.wavelengths_for_spectrum[index]:.3f},"
                        line += f"{self.measurement.integrated_values[index]:.6e},"
                        line += f"{self.measurement.approximated_values[index]:.6e}"
                        if self.settings.get('dual_integration', False):
                            line += f",{self.measurement.integrated_values_2[index]:.6e},"
                            line += f"{self.measurement.approximated_values_2[index]:.6e}"
                        file_handle.write(line + "\n")
            except Exception:
                pass
    
    def save_energy_to_file(self):
        if not self.measurement.energy_values:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Energy Data", "",
            "CSV files (*.csv);;All files (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file_handle:
                    file_handle.write("energy_value,integrated_signal_1,approximated_signal_1")
                    if self.settings.get('dual_integration', False):
                        file_handle.write(",integrated_signal_2,approximated_signal_2")
                    file_handle.write("\n")
                    
                    for index in range(len(self.measurement.energy_values)):
                        line = f"{self.measurement.energy_values[index]:.6e},"
                        line += f"{self.measurement.integrated_values[index]:.6e},"
                        line += f"{self.measurement.approximated_values[index]:.6e}"
                        if self.settings.get('dual_integration', False):
                            line += f",{self.measurement.integrated_values_2[index]:.6e},"
                            line += f"{self.measurement.approximated_values_2[index]:.6e}"
                        file_handle.write(line + "\n")
            except Exception:
                pass
    
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