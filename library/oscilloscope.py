import numpy
import pyvisa
import time
import re

from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple


class Oscilloscope:
    def __init__(self):
        self._instrument = None
        self._resource_manager = None
        self._is_connected = False
        self._timeout_milliseconds = 15000
        self._manufacturer = ""
        self._model_number = ""
        self._capabilities = {}

        self.acquisition_type_normal = "NORM"
        self.acquisition_type_average = "AVER"
        self.acquisition_type_peak = "PEAK"
        self.acquisition_type_high_resolution = "HRES"

        self.coupling_type_ac = "AC"
        self.coupling_type_dc = "DC"
        self.coupling_type_ground = "GND"

        self.trigger_slope_positive = "POS"
        self.trigger_slope_negative = "NEG"
        self.trigger_slope_either = "EITH"

        self.trigger_mode_auto = "AUTO"
        self.trigger_mode_normal = "NORM"
        self.trigger_mode_single = "SING"

        self.bandwidth_limit_full = "FULL"
        self.bandwidth_limit_twenty_megahertz = "20MHZ"
        self.bandwidth_limit_one_hundred_megahertz = "100MHZ"
        self.bandwidth_limit_two_hundred_megahertz = "200MHZ"

        self.cursor_mode_off = "OFF"
        self.cursor_mode_x = "X"
        self.cursor_mode_y = "Y"
        self.cursor_mode_xy = "XY"

        self.math_function_addition = "ADD"
        self.math_function_subtraction = "SUBT"
        self.math_function_multiplication = "MULT"
        self.math_function_division = "DIV"
        self.math_function_fft = "FFT"

        self.fft_window_rectangular = "RECT"
        self.fft_window_hamming = "HAMM"
        self.fft_window_hanning = "HANN"
        self.fft_window_blackman = "BLAC"

        self.timebase_mode_main = "MAIN"
        self.timebase_mode_window = "WIND"
        self.timebase_mode_xy = "XY"
        self.timebase_mode_roll = "ROLL"

        self.measurement_parameter_voltage_peak_to_peak = "VPP"
        self.measurement_parameter_voltage_maximum = "VMAX"
        self.measurement_parameter_voltage_minimum = "VMIN"
        self.measurement_parameter_voltage_rms = "VRMS"
        self.measurement_parameter_frequency = "FREQuency"
        self.measurement_parameter_period = "PERiod"
        self.measurement_parameter_rise_time = "RISetime"
        self.measurement_parameter_fall_time = "FALLtime"
        self.measurement_parameter_positive_width = "PWIDth"
        self.measurement_parameter_negative_width = "NWIDth"
        self.measurement_parameter_duty_cycle = "DUTYcycle"
        self.measurement_parameter_mean_voltage = "MEAN"
        self.measurement_parameter_ac_rms = "RMS"
        self.measurement_parameter_overshoot = "OVERS"
        self.measurement_parameter_preshoot = "PREShoot"
        self.measurement_parameter_delay = "DELay"
        self.measurement_parameter_phase = "PHASe"


    def connect(self, resource_string: str = None, timeout_milliseconds: int = 15000) -> bool:
        self._timeout_milliseconds = timeout_milliseconds

        try:
            self._resource_manager = pyvisa.ResourceManager("@py")

            if resource_string is not None:
                self._instrument = self._resource_manager.open_resource(resource_string)

                if not self._configure_and_verify_instrument():
                    connection_status = False
                else:
                    connection_status = True
            else:
                available_resources = self._resource_manager.list_resources()
                found_valid_instrument = False

                for single_resource in available_resources:
                    try:
                        temporary_instrument = self._resource_manager.open_resource(single_resource)
                        temporary_instrument.timeout = self._timeout_milliseconds
                        temporary_instrument.read_termination = "\n"
                        temporary_instrument.write_termination = "\n"

                        temporary_instrument.write("*IDN?")
                        time.sleep(0.2)
                        identification_string = temporary_instrument.read()

                        if self._is_oscilloscope(identification_string):
                            self._instrument = temporary_instrument
                            found_valid_instrument = True

                            break
                        else:
                            temporary_instrument.close()
                    except Exception:
                        continue

                if not found_valid_instrument:
                    connection_status = False
                else:
                    connection_status = True

            if connection_status:
                self._is_connected = True
                self._detect_capabilities()
        except Exception:
            self._is_connected = False
            connection_status = False

        return connection_status


    def _configure_and_verify_instrument(self) -> bool:
        try:
            self._instrument.timeout = self._timeout_milliseconds
            self._instrument.read_termination = "\n"
            self._instrument.write_termination = "\n"

            self._instrument.write("*IDN?")
            time.sleep(0.2)
            response_string = self._instrument.read()

            verification_status = len(response_string) > 0
        except Exception:
            verification_status = False

        return verification_status


    def _is_oscilloscope(self, identification_string: str) -> bool:
        oscilloscope_brands = ["AGILENT", "KEYSIGHT", "RIGOL", "TEKTRONIX", "SIGLENT", "ROHDE", "SCHWARZ"]
        upper_identification = identification_string.upper()
        is_oscilloscope_device = False

        for single_brand in oscilloscope_brands:
            if single_brand in upper_identification:
                is_oscilloscope_device = True

                break

        return is_oscilloscope_device


    def _detect_capabilities(self):
        try:
            identification_string = self._query_string("*IDN?")
            parts = identification_string.split(",")

            if len(parts) > 0:
                self._manufacturer = parts[0]

            if len(parts) > 1:
                self._model_number = parts[1]
        except Exception:
            pass

        self._capabilities["has_average_mode"] = self._check_command_support(":ACQuire:TYPE AVER")
        self._capabilities["has_math_fft"] = self._check_command_support(":MATH:FUNCtion FFT")
        self._capabilities["has_mask_test"] = self._check_command_support(":MASK:LOAD \"\"")
        self._capabilities["has_segmented_memory"] = self._check_command_support(":ACQuire:SEGMent:COUNt?")
        self._capabilities["maximum_channels"] = self._detect_channel_count()
        self._capabilities["supports_binary_waveform"] = self._check_binary_waveform_support()


    def _check_command_support(self, command: str) -> bool:
        try:
            self._write_raw(command)
            command_supported = True
        except Exception:
            command_supported = False

        return command_supported


    def _detect_channel_count(self) -> int:
        channel_count = 4

        for channel_index in range(1, 5):
            try:
                self._write_raw(f":CHANnel{channel_index}:DISPlay?")
                self._read_raw()
            except Exception:
                channel_count = channel_index - 1

                break

        return channel_count


    def _check_binary_waveform_support(self) -> bool:
        try:
            self._write_raw(":WAVeform:FORMat WORD")
            binary_supported = True
        except Exception:
            binary_supported = False

        return binary_supported


    def wait_for_ready(self, timeout_seconds: float = 10.0) -> bool:
        if not self._is_safe_to_operate():
            return False

        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                self._write_raw("*OPC?")
                response = self._read_raw()

                if response == "1":
                    return True
            except Exception:
                pass

            time.sleep(0.1)

        return False


    def wait_for_ready_polling(self, timeout_seconds: float = 30.0) -> bool:
        if not self._is_safe_to_operate():
            return False
        
        original_timeout = self._instrument.timeout
        self._instrument.timeout = 500
        
        try:
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                try:
                    self._write_raw("*OPC?")
                    response = self._read_raw()
                    if response.strip() == "1":
                        return True
                except Exception:
                    pass
                time.sleep(0.05)
            return False
        finally:
            self._instrument.timeout = original_timeout


    def wait_for_average_complete(self, average_count: int, timeout_seconds: float = 120.0) -> bool:
        if not self._is_safe_to_operate():
            return False
        
        original_timeout = self._instrument.timeout
        self._instrument.timeout = 500
        
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout_seconds:
                try:
                    self._write_raw(":ACQuire:COMPlete?")
                    response = self._read_raw()
                    
                    if response.strip():
                        completion = int(float(response))
                        if completion >= 100:
                            return True
                    
                    if average_count > 4096:
                        time.sleep(0.5)
                    elif average_count > 1024:
                        time.sleep(0.3)
                    elif average_count > 256:
                        time.sleep(0.2)
                    else:
                        time.sleep(0.1)
                        
                except Exception:
                    time.sleep(0.1)
                    
            return False
        finally:
            self._instrument.timeout = original_timeout


    def disconnect(self):
        if self._instrument is not None:
            try:
                self._instrument.close()
            except Exception:
                pass

        if self._resource_manager is not None:
            try:
                self._resource_manager.close()
            except Exception:
                pass

        self._is_connected = False
        self._instrument = None
        self._resource_manager = None


    def _is_safe_to_operate(self) -> bool:
        if not self._is_connected:
            safe_to_operate = False
        elif self._instrument is None:
            safe_to_operate = False
        else:
            safe_to_operate = True

        return safe_to_operate


    def _write_raw(self, command: str):
        if self._is_safe_to_operate():
            self._instrument.write(command)


    def _read_raw(self) -> str:
        if not self._is_safe_to_operate():
            read_result = ""
        else:
            try:
                read_result = self._instrument.read().strip()
            except Exception:
                read_result = ""

        return read_result


    def _query_string(self, command: str) -> str:
        if not self._is_safe_to_operate():
            query_result = ""
        else:
            self._write_raw(command)
            query_result = self._read_raw()

        return query_result


    def _query_float(self, command: str) -> float:
        if not self._is_safe_to_operate():
            query_result = 0.0
        else:
            response = self._query_string(command)

            try:
                query_result = float(response)
            except Exception:
                query_result = 0.0

        return query_result


    def _query_integer(self, command: str) -> int:
        if not self._is_safe_to_operate():
            query_result = 0
        else:
            response = self._query_string(command)

            try:
                query_result = int(float(response))
            except Exception:
                query_result = 0

        return query_result


    def _query_boolean(self, command: str) -> bool:
        if not self._is_safe_to_operate():
            query_result = False
        else:
            response = self._query_string(command)
            query_result = response == "1"

        return query_result


    def get_trigger_status(self) -> str:
        if not self._is_safe_to_operate():
            return ""

        try:
            self._write_raw(":TRIGger:STATus?")
            status = self._read_raw()

            return status.strip().upper()
        except Exception:
            return ""


    def set_timeout(self, milliseconds: int):
        self._timeout_milliseconds = milliseconds

        if self._is_safe_to_operate():
            try:
                self._instrument.timeout = milliseconds
            except Exception:
                pass


    def get_identification(self) -> str:
        identification_string = self._query_string("*IDN?")

        return identification_string


    def reset(self):
        if self._is_safe_to_operate():
            self._write_raw("*RST")
            self.wait_for_ready(5.0)


    def self_test(self) -> bool:
        if not self._is_safe_to_operate():
            test_passed = False
        else:
            self._write_raw("*TST?")
            test_result = self._read_raw()
            test_passed = test_result == "0"

        return test_passed


    def clear_errors(self):
        if self._is_safe_to_operate():
            self._write_raw("*CLS")


    def get_next_error(self) -> str:
        error_message = self._query_string(":SYSTem:ERRor?")

        return error_message


    def get_all_errors(self) -> List[str]:
        if not self._is_safe_to_operate():
            error_list = []
        else:
            error_list = []

            while True:
                single_error = self.get_next_error()

                if "No error" in single_error or not single_error:
                    break

                error_list.append(single_error)

        return error_list


    def is_acquisition_complete(self) -> bool:
        if not self._is_safe_to_operate():
            acquisition_complete = False
        else:
            completion_percent = self._query_integer(":ACQuire:COMPlete?")
            acquisition_complete = completion_percent >= 100

        return acquisition_complete


    def set_channel_enabled(self, channel_number: int, enable_status: bool):
        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                self._write_raw(f":CHANnel{channel_number}:DISPlay {1 if enable_status else 0}")
                time.sleep(0.05)


    def is_channel_enabled(self, channel_number: int) -> bool:
        if not self._is_safe_to_operate():
            enabled_status = False
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            enabled_status = False
        else:
            enabled_status = self._query_boolean(f":CHANnel{channel_number}:DISPlay?")

        return enabled_status


    def set_channel_scale(self, channel_number: int, volts_per_division: float):
        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                if volts_per_division > 0:
                    self._write_raw(f":CHANnel{channel_number}:SCALe {volts_per_division}")


    def get_channel_scale(self, channel_number: int) -> float:
        if not self._is_safe_to_operate():
            scale_value = 0.0
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            scale_value = 0.0
        else:
            scale_value = self._query_float(f":CHANnel{channel_number}:SCALe?")

        return scale_value


    def set_channel_offset(self, channel_number: int, offset_volts: float):
        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                self._write_raw(f":CHANnel{channel_number}:OFFSet {offset_volts}")


    def get_channel_offset(self, channel_number: int) -> float:
        if not self._is_safe_to_operate():
            offset_value = 0.0
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            offset_value = 0.0
        else:
            offset_value = self._query_float(f":CHANnel{channel_number}:OFFSet?")

        return offset_value


    def set_channel_coupling(self, channel_number: int, coupling_type: str):
        valid_coupling_types = [self.coupling_type_ac, self.coupling_type_dc, self.coupling_type_ground]

        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                if coupling_type in valid_coupling_types:
                    self._write_raw(f":CHANnel{channel_number}:COUPling {coupling_type}")


    def get_channel_coupling(self, channel_number: int) -> str:
        if not self._is_safe_to_operate():
            coupling_value = ""
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            coupling_value = ""
        else:
            coupling_value = self._query_string(f":CHANnel{channel_number}:COUPling?")

        return coupling_value


    def set_channel_impedance(self, channel_number: int, impedance_ohms: float):
        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                if impedance_ohms in [50.0, 1000000.0]:
                    self._write_raw(f":CHANnel{channel_number}:IMPedance {impedance_ohms}")


    def get_channel_impedance(self, channel_number: int) -> float:
        if not self._is_safe_to_operate():
            impedance_value = 0.0
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            impedance_value = 0.0
        else:
            impedance_value = self._query_float(f":CHANnel{channel_number}:IMPedance?")

        return impedance_value


    def set_channel_probe_attenuation(self, channel_number: int, attenuation_factor: float):
        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                if attenuation_factor > 0:
                    self._write_raw(f":CHANnel{channel_number}:PROBe {attenuation_factor}")


    def get_channel_probe_attenuation(self, channel_number: int) -> float:
        if not self._is_safe_to_operate():
            attenuation_value = 0.0
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            attenuation_value = 0.0
        else:
            attenuation_value = self._query_float(f":CHANnel{channel_number}:PROBe?")

        return attenuation_value


    def set_channel_inverted(self, channel_number: int, invert_status: bool):
        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                self._write_raw(f":CHANnel{channel_number}:INVert {1 if invert_status else 0}")


    def is_channel_inverted(self, channel_number: int) -> bool:
        if not self._is_safe_to_operate():
            inverted_status = False
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            inverted_status = False
        else:
            inverted_status = self._query_boolean(f":CHANnel{channel_number}:INVert?")

        return inverted_status


    def set_channel_bandwidth_limit(self, channel_number: int, bandwidth_limit: str):
        valid_limits = [
            self.bandwidth_limit_full,
            self.bandwidth_limit_twenty_megahertz,
            self.bandwidth_limit_one_hundred_megahertz,
            self.bandwidth_limit_two_hundred_megahertz
        ]

        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                if bandwidth_limit in valid_limits:
                    self._write_raw(f":CHANnel{channel_number}:BANDwidth {bandwidth_limit}")


    def get_channel_bandwidth_limit(self, channel_number: int) -> str:
        if not self._is_safe_to_operate():
            bandwidth_value = ""
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            bandwidth_value = ""
        else:
            bandwidth_value = self._query_string(f":CHANnel{channel_number}:BANDwidth?")

        return bandwidth_value


    def set_channel_label(self, channel_number: int, label_text: str):
        if self._is_safe_to_operate():
            if channel_number >= 1 and channel_number <= self._capabilities.get("maximum_channels", 4):
                if len(label_text) > 10:
                    label_text = label_text[:10]

                self._write_raw(f":CHANnel{channel_number}:LABel \"{label_text}\"")


    def get_channel_label(self, channel_number: int) -> str:
        if not self._is_safe_to_operate():
            label_value = ""
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            label_value = ""
        else:
            label_value = self._query_string(f":CHANnel{channel_number}:LABel?").strip("\"")

        return label_value


    def auto_scale(self):
        if self._is_safe_to_operate():
            self._write_raw(":AUToscale")
            self.wait_for_ready(10.0)


    def set_timebase_scale(self, seconds_per_division: float):
        if self._is_safe_to_operate():
            if seconds_per_division > 0:
                self._write_raw(f":TIMebase:SCALe {seconds_per_division}")


    def get_timebase_scale(self) -> float:
        if not self._is_safe_to_operate():
            scale_value = 0.0
        else:
            scale_value = self._query_float(":TIMebase:SCALe?")

        return scale_value


    def set_timebase_delay(self, delay_seconds: float):
        if self._is_safe_to_operate():
            self._write_raw(f":TIMebase:DELay {delay_seconds}")


    def get_timebase_delay(self) -> float:
        if not self._is_safe_to_operate():
            delay_value = 0.0
        else:
            delay_value = self._query_float(":TIMebase:DELay?")

        return delay_value


    def set_timebase_reference(self, reference_position: str):
        valid_positions = ["LEFT", "CENTER", "RIGHT"]

        if self._is_safe_to_operate():
            if reference_position.upper() in valid_positions:
                self._write_raw(f":TIMebase:REFerence {reference_position}")


    def get_timebase_reference(self) -> str:
        if not self._is_safe_to_operate():
            reference_value = ""
        else:
            reference_value = self._query_string(":TIMebase:REFerence?")

        return reference_value


    def set_timebase_mode(self, timebase_mode: str):
        valid_modes = [
            self.timebase_mode_main,
            self.timebase_mode_window,
            self.timebase_mode_xy,
            self.timebase_mode_roll
        ]

        if self._is_safe_to_operate():
            if timebase_mode in valid_modes:
                self._write_raw(f":TIMebase:MODE {timebase_mode}")


    def get_timebase_mode(self) -> str:
        if not self._is_safe_to_operate():
            mode_value = ""
        else:
            mode_value = self._query_string(":TIMebase:MODE?")

        return mode_value


    def run_acquisition(self):
        if self._is_safe_to_operate():
            self._write_raw(":RUN")


    def stop_acquisition(self):
        if self._is_safe_to_operate():
            self._write_raw(":STOP")


    def single_acquisition(self):
        if self._is_safe_to_operate():
            self._write_raw(":SINGle")
            self.wait_for_ready(5.0)


    def force_trigger(self):
        if self._is_safe_to_operate():
            self._write_raw(":TRIGger:FORCe")


    def set_trigger_source(self, source_channel: str):
        valid_sources = ["CHAN1", "CHAN2", "CHAN3", "CHAN4", "LINE", "EXT", "EXT5"]

        if self._is_safe_to_operate():
            if source_channel.upper() in valid_sources:
                self._write_raw(f":TRIGger:SOURce {source_channel.upper()}")


    def get_trigger_source(self) -> str:
        if not self._is_safe_to_operate():
            source_value = ""
        else:
            source_value = self._query_string(":TRIGger:SOURce?")

        return source_value


    def set_trigger_level(self, level_volts: float):
        if self._is_safe_to_operate():
            self._write_raw(f":TRIGger:LEVel {level_volts}")


    def get_trigger_level(self) -> float:
        if not self._is_safe_to_operate():
            level_value = 0.0
        else:
            level_value = self._query_float(":TRIGger:LEVel?")

        return level_value


    def set_trigger_slope(self, slope_direction: str):
        valid_slopes = [self.trigger_slope_positive, self.trigger_slope_negative, self.trigger_slope_either]

        if self._is_safe_to_operate():
            if slope_direction in valid_slopes:
                self._write_raw(f":TRIGger:SLOPe {slope_direction}")


    def get_trigger_slope(self) -> str:
        if not self._is_safe_to_operate():
            slope_value = ""
        else:
            slope_value = self._query_string(":TRIGger:SLOPe?")

        return slope_value


    def set_trigger_mode(self, mode_type: str):
        valid_modes = [self.trigger_mode_auto, self.trigger_mode_normal, self.trigger_mode_single]

        if self._is_safe_to_operate():
            if mode_type in valid_modes:
                self._write_raw(f":TRIGger:MODE {mode_type}")


    def get_trigger_mode(self) -> str:
        if not self._is_safe_to_operate():
            mode_value = ""
        else:
            mode_value = self._query_string(":TRIGger:MODE?")

        return mode_value


    def set_trigger_coupling(self, coupling_type: str):
        valid_coupling = [self.coupling_type_ac, self.coupling_type_dc, self.coupling_type_ground]

        if self._is_safe_to_operate():
            if coupling_type in valid_coupling:
                self._write_raw(f":TRIGger:COUPling {coupling_type}")


    def get_trigger_coupling(self) -> str:
        if not self._is_safe_to_operate():
            coupling_value = ""
        else:
            coupling_value = self._query_string(":TRIGger:COUPling?")

        return coupling_value


    def set_trigger_holdoff(self, holdoff_seconds: float):
        if self._is_safe_to_operate():
            if holdoff_seconds >= 0:
                self._write_raw(f":TRIGger:HOLDoff {holdoff_seconds}")


    def get_trigger_holdoff(self) -> float:
        if not self._is_safe_to_operate():
            holdoff_value = 0.0
        else:
            holdoff_value = self._query_float(":TRIGger:HOLDoff?")

        return holdoff_value


    def set_acquisition_type(self, acquisition_type: str):
        valid_types = [
            self.acquisition_type_normal,
            self.acquisition_type_average,
            self.acquisition_type_peak,
            self.acquisition_type_high_resolution
        ]

        if self._is_safe_to_operate():
            if acquisition_type in valid_types:
                self._write_raw(f":ACQuire:TYPE {acquisition_type}")
                time.sleep(0.05)


    def get_acquisition_type(self) -> str:
        if not self._is_safe_to_operate():
            type_value = ""
        else:
            type_value = self._query_string(":ACQuire:TYPE?")

        return type_value


    def set_average_count(self, averages_number: int):
        if self._is_safe_to_operate():
            if averages_number < 1:
                averages_number = 1

            if averages_number > 65536:
                averages_number = 65536

            self._write_raw(f":ACQuire:COUNt {averages_number}")
            time.sleep(0.05)

            self._write_raw(":ACQuire:TYPE AVER")
            time.sleep(0.05)


    def get_average_count(self) -> int:
        if not self._is_safe_to_operate():
            count_value = 0
        else:
            count_value = self._query_integer(":ACQuire:COUNt?")

        return count_value


    def measure_parameter(self, measurement_parameter: str, channel_number: int = 1) -> Optional[float]:
        if not self._is_safe_to_operate():
            measurement_result = None
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            measurement_result = None
        else:
            try:
                old_timeout = self._instrument.timeout
                self._instrument.timeout = self._timeout_milliseconds

                result = self._query_float(f":MEASure:{measurement_parameter}? CHAN{channel_number}")

                self._instrument.timeout = old_timeout

                if result == 0.0:
                    measurement_result = None
                else:
                    measurement_result = result
            except Exception:
                measurement_result = None

        return measurement_result


    def measure_voltage_peak_to_peak(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_voltage_peak_to_peak, channel_number)

        return measurement_result


    def measure_voltage_maximum(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_voltage_maximum, channel_number)

        return measurement_result


    def measure_voltage_minimum(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_voltage_minimum, channel_number)

        return measurement_result


    def measure_voltage_rms(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_voltage_rms, channel_number)

        return measurement_result


    def measure_frequency(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_frequency, channel_number)

        return measurement_result


    def measure_period(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_period, channel_number)

        return measurement_result


    def measure_rise_time(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_rise_time, channel_number)

        return measurement_result


    def measure_fall_time(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_fall_time, channel_number)

        return measurement_result


    def measure_positive_width(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_positive_width, channel_number)

        return measurement_result


    def measure_negative_width(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_negative_width, channel_number)

        return measurement_result


    def measure_duty_cycle(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_duty_cycle, channel_number)

        return measurement_result


    def measure_mean_voltage(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_mean_voltage, channel_number)

        return measurement_result


    def measure_overshoot(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_overshoot, channel_number)

        return measurement_result


    def measure_preshoot(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_preshoot, channel_number)

        return measurement_result


    def measure_delay(self, first_source: str = "CHAN1", second_source: str = "CHAN2") -> Optional[float]:
        if not self._is_safe_to_operate():
            delay_value = None
        else:
            try:
                delay_value = self._query_float(f":MEASure:DELay? {first_source},{second_source}")
            except Exception:
                delay_value = None

        return delay_value


    def measure_phase(self, first_source: str = "CHAN1", second_source: str = "CHAN2") -> Optional[float]:
        if not self._is_safe_to_operate():
            phase_value = None
        else:
            try:
                phase_value = self._query_float(f":MEASure:PHASe? {first_source},{second_source}")
            except Exception:
                phase_value = None

        return phase_value


    def measure_ac_rms(self, channel_number: int = 1) -> Optional[float]:
        measurement_result = self.measure_parameter(self.measurement_parameter_ac_rms, channel_number)

        return measurement_result


    def set_cursor_mode(self, cursor_mode: str):
        valid_modes = [self.cursor_mode_off, self.cursor_mode_x, self.cursor_mode_y, self.cursor_mode_xy]

        if self._is_safe_to_operate():
            if cursor_mode in valid_modes:
                self._write_raw(f":CURSor:MODE {cursor_mode}")


    def get_cursor_mode(self) -> str:
        if not self._is_safe_to_operate():
            mode_value = ""
        else:
            mode_value = self._query_string(":CURSor:MODE?")

        return mode_value


    def set_cursor_position(self, cursor_name: str, position_value: float):
        valid_cursors = ["X1P", "X2P", "Y1P", "Y2P"]

        if self._is_safe_to_operate():
            if cursor_name.upper() in valid_cursors:
                self._write_raw(f":CURSor:{cursor_name} {position_value}")


    def get_cursor_position(self, cursor_name: str) -> float:
        valid_cursors = ["X1P", "X2P", "Y1P", "Y2P"]

        if not self._is_safe_to_operate():
            position_value = 0.0
        elif cursor_name.upper() not in valid_cursors:
            position_value = 0.0
        else:
            position_value = self._query_float(f":CURSor:{cursor_name}?")

        return position_value


    def get_cursor_deltas(self) -> Dict[str, float]:
        if not self._is_safe_to_operate():
            delta_values = {"delta_x": 0.0, "delta_y": 0.0, "inverse_delta_x": 0.0}
        else:
            delta_values = {
                "delta_x": self._query_float(":CURSor:XDELta?"),
                "delta_y": self._query_float(":CURSor:YDELta?"),
                "inverse_delta_x": self._query_float(":CURSor:INVXDELta?")
            }

        return delta_values


    def set_math_function(self, math_function: str):
        valid_functions = [
            self.math_function_addition,
            self.math_function_subtraction,
            self.math_function_multiplication,
            self.math_function_division,
            self.math_function_fft
        ]

        if self._is_safe_to_operate():
            if math_function in valid_functions:
                self._write_raw(f":MATH:FUNCtion {math_function}")


    def get_math_function(self) -> str:
        if not self._is_safe_to_operate():
            function_value = ""
        else:
            function_value = self._query_string(":MATH:FUNCtion?")

        return function_value


    def set_math_sources(self, first_source: str, second_source: str = None):
        if self._is_safe_to_operate():
            self._write_raw(f":MATH:SOURce1 {first_source}")

            if second_source is not None:
                self._write_raw(f":MATH:SOURce2 {second_source}")


    def set_math_scale(self, scale_value: float):
        if self._is_safe_to_operate():
            if scale_value > 0:
                self._write_raw(f":MATH:SCALe {scale_value}")


    def get_math_scale(self) -> float:
        if not self._is_safe_to_operate():
            scale_value = 0.0
        else:
            scale_value = self._query_float(":MATH:SCALe?")

        return scale_value


    def set_math_offset(self, offset_value: float):
        if self._is_safe_to_operate():
            self._write_raw(f":MATH:OFFSet {offset_value}")


    def get_math_offset(self) -> float:
        if not self._is_safe_to_operate():
            offset_value = 0.0
        else:
            offset_value = self._query_float(":MATH:OFFSet?")

        return offset_value


    def set_math_fft_window(self, window_type: str):
        valid_windows = [
            self.fft_window_rectangular,
            self.fft_window_hamming,
            self.fft_window_hanning,
            self.fft_window_blackman
        ]

        if self._is_safe_to_operate():
            if window_type in valid_windows:
                self._write_raw(f":MATH:FFT:WINDow {window_type}")


    def _get_waveform_preamble(self) -> Dict[str, Any]:
        if not self._is_safe_to_operate():
            return {}

        try:
            self._write_raw(":WAVeform:PREamble?")
            time.sleep(0.1)

            preamble_string = self._read_raw()

            if not preamble_string:
                return {}

            preamble_string = preamble_string.replace("\n", "").replace("\r", "").strip()
            preamble_parts = preamble_string.split(",")

            if len(preamble_parts) < 10:
                return {}

            preamble = {
                "format_code": int(preamble_parts[0]),
                "acquisition_type": int(preamble_parts[1]),
                "points_count": int(preamble_parts[2]),
                "average_count": int(preamble_parts[3]),
                "x_increment": float(preamble_parts[4]),
                "x_origin": float(preamble_parts[5]),
                "x_reference": float(preamble_parts[6]),
                "y_increment": float(preamble_parts[7]),
                "y_origin": float(preamble_parts[8]),
                "y_reference": float(preamble_parts[9])
            }

            return preamble
        except Exception:
            return {}


    def _read_waveform_data(self, points_count: int = 2000) -> List[float]:
        if not self._is_safe_to_operate():
            return []

        self._write_raw(f":WAVeform:POINts {points_count}")
        self._write_raw(":WAVeform:FORMat ASCII")
        self._write_raw(":WAVeform:DATA?")
        time.sleep(0.1)

        data_string = self._read_raw()

        if data_string.startswith("#"):
            header_length = int(data_string[1])
            data_string = data_string[2 + header_length:]

        if not data_string:
            return []

        data_string = data_string.replace("\n", "").replace("\r", "").strip()

        data_string = re.sub(r'[^0-9eE+\-., ]', '', data_string)

        if "," in data_string:
            parts = data_string.split(",")
        else:
            parts = data_string.split()

        voltage_values = []

        for part in parts:
            part = part.strip()

            if part:
                try:
                    voltage_values.append(float(part))
                except ValueError:
                    continue

        return voltage_values


    def capture_waveform(self, channel_number: int = 1, points_count: int = 2000) -> Tuple[List[float], List[float]]:
        if not self._is_safe_to_operate():
            return [], []

        if channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            return [], []

        old_timeout = self._instrument.timeout
        self._instrument.timeout = 10000

        try:
            current_acquisition_type = self.get_acquisition_type()
            current_average_count = self.get_average_count()
        except:
            current_acquisition_type = "NORM"
            current_average_count = 2

        try:
            self._write_raw(":STOP")
            time.sleep(0.1)

            self._write_raw(":RUN")
            time.sleep(0.1)

            self._write_raw(":STOP")
            time.sleep(0.1)

            self._write_raw(f":WAVeform:SOURce CHAN{channel_number}")
            self._write_raw(f":WAVeform:POINts {points_count}")
            self._write_raw(":WAVeform:FORMat ASCII")

            voltage_values = self._read_waveform_data(points_count)

            if not voltage_values:
                self._write_raw(":RUN")

                return [], []

            preamble = self._get_waveform_preamble()

            if preamble:
                x_increment = preamble.get("x_increment", 1.0)
                x_origin = preamble.get("x_origin", 0.0)
            else:
                timebase = self.get_timebase_scale()
                x_increment = timebase * 10 / points_count
                x_origin = -x_increment * points_count / 2

            time_values = [x_origin + index * x_increment for index in range(len(voltage_values))]

            self._write_raw(":RUN")
            time.sleep(0.1)

            return time_values, voltage_values
        except Exception:
            try:
                self._write_raw(":RUN")
            except:
                pass

            return [], []
        finally:
            try:
                self.set_acquisition_type(current_acquisition_type)
                time.sleep(0.05)

                self.set_average_count(current_average_count)
                time.sleep(0.05)
            except:
                pass

            self._instrument.timeout = old_timeout


    def acquire_averaged_waveform(self, channel_number: int = 1, average_count: int = 64, points_count: int = 2000, timeout_seconds: float = 180.0) -> Tuple[List[float], List[float]]:
        if not self._is_safe_to_operate():
            return [], []
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            return [], []
        elif not self._capabilities.get("has_average_mode", False):
            return [], []

        old_average_count = self.get_average_count()
        old_acquisition_type = self.get_acquisition_type()
        old_timeout = self._instrument.timeout
        self._instrument.timeout = 60000

        try:
            self.set_acquisition_type(self.acquisition_type_average)
            self.set_average_count(average_count)
            time.sleep(0.1)

            self._write_raw(":RUN")
            time.sleep(0.1)

            if average_count <= 256:
                wait_time = max(0.5, average_count / 20)
                time.sleep(wait_time)
            else:
                start_time = time.time()
                data_ready = False

                while time.time() - start_time < timeout_seconds:
                    try:
                        completion = self._query_integer(":ACQuire:COMPlete?")

                        if completion >= 100:
                            data_ready = True

                            break
                    except:
                        pass

                    if average_count > 4096:
                        time.sleep(0.5)
                    elif average_count > 1024:
                        time.sleep(0.3)
                    else:
                        time.sleep(0.2)

                if not data_ready:
                    time.sleep(min(average_count / 10, 30.0))

            if average_count > 512:
                wait_time = min(average_count / 20, 60.0)
                time.sleep(wait_time)
            elif average_count > 128:
                time.sleep(min(average_count / 50, 10.0))

            self._write_raw(":STOP")
            time.sleep(0.2)

            self._write_raw(f":DIGitize CHANnel{channel_number}")
            
            if not self.wait_for_ready_polling(30.0):
                self.set_acquisition_type(old_acquisition_type)
                self.set_average_count(old_average_count)
                self._write_raw(":RUN")

                return [], []

            self._write_raw(f":WAVeform:SOURce CHAN{channel_number}")
            self._write_raw(f":WAVeform:POINts {points_count}")
            self._write_raw(":WAVeform:FORMat ASCII")

            voltage_values = self._read_waveform_data(points_count)

            if not voltage_values:
                self.set_acquisition_type(old_acquisition_type)
                self.set_average_count(old_average_count)
                self._write_raw(":RUN")

                return [], []

            preamble = self._get_waveform_preamble()

            if preamble:
                x_increment = preamble.get("x_increment", 1.0)
                x_origin = preamble.get("x_origin", 0.0)
            else:
                timebase = self.get_timebase_scale()
                x_increment = timebase * 10 / points_count
                x_origin = -x_increment * points_count / 2

            time_values = [x_origin + index * x_increment for index in range(len(voltage_values))]

            self.set_acquisition_type(old_acquisition_type)
            time.sleep(0.05)
            self.set_average_count(old_average_count)
            time.sleep(0.05)
            self._write_raw(":RUN")
            time.sleep(0.05)

            return time_values, voltage_values
        except Exception:
            try:
                self.set_acquisition_type(old_acquisition_type)
                self.set_average_count(old_average_count)
                self._write_raw(":RUN")
            except:
                pass

            return [], []
        finally:
            self._instrument.timeout = old_timeout


    def acquire_averaged_waveform_retry(self, channel_number: int = 1, average_count: int = 64, points_count: int = 2000, max_retries: int = 3, timeout_seconds: float = 180.0) -> Tuple[List[float], List[float]]:
        time_values = []
        voltage_values = []

        for attempt_index in range(max_retries):
            time_values, voltage_values = self.acquire_averaged_waveform(
                channel_number, average_count, points_count, timeout_seconds
            )

            if time_values and voltage_values:
                break

            time.sleep(1.0)
            self.stop_acquisition()
            time.sleep(0.2)
            self.run_acquisition()
            time.sleep(0.2)

        return time_values, voltage_values


    def get_acquisition_status(self) -> Dict[str, Any]:
        status_info = {}

        if self._is_safe_to_operate():
            try:
                status_info["type"] = self.get_acquisition_type()
                status_info["average_count"] = self.get_average_count()
                status_info["is_complete"] = self.is_acquisition_complete()

                self._write_raw(":OPERation:CONDition?")
                response = self._read_raw()

                if response:
                    status_info["operation_status"] = int(response)

                self._write_raw(":TRIGger:STATus?")
                response = self._read_raw()

                if response:
                    status_info["trigger_status"] = response.strip()
            except Exception:
                pass

        return status_info


    def capture_segmented_waveform(self, segment_index: int, channel_number: int = 1, points_count: int = 2000) -> Tuple[List[float], List[float]]:
        if not self._is_safe_to_operate():
            return [], []
        elif not self._capabilities.get("has_segmented_memory", False):
            return [], []
        else:
            self._write_raw(f":ACQuire:SEGMent:INDex {segment_index}")

            return self.capture_waveform(channel_number, points_count)


    def get_segment_count(self) -> int:
        if not self._is_safe_to_operate():
            return 0
        elif not self._capabilities.get("has_segmented_memory", False):
            return 0
        else:
            return self._query_integer(":ACQuire:SEGMent:COUNt?")


    def set_segment_count(self, segment_quantity: int):
        if self._is_safe_to_operate():
            if self._capabilities.get("has_segmented_memory", False):
                if segment_quantity >= 1:
                    self._write_raw(f":ACQuire:SEGMent:COUNt {segment_quantity}")


    def setup_for_experiment(self, channel_number: int = 1, volts_per_division: float = 1.0, seconds_per_division: float = 0.01) -> bool:
        if not self._is_safe_to_operate():
            return False
        elif channel_number < 1 or channel_number > self._capabilities.get("maximum_channels", 4):
            return False
        else:
            try:
                self.stop_acquisition()
                time.sleep(0.1)

                self.set_channel_enabled(channel_number, True)
                self.set_channel_scale(channel_number, volts_per_division)
                self.set_channel_offset(channel_number, 0.0)
                self.set_channel_coupling(channel_number, self.coupling_type_dc)
                self.set_timebase_scale(seconds_per_division)
                self.set_trigger_source(f"CHAN{channel_number}")
                self.set_trigger_level(0.0)
                self.set_trigger_slope(self.trigger_slope_positive)
                self.run_acquisition()

                return True
            except Exception:
                return False


    def save_screenshot(self, file_name: str = None) -> str:
        if not self._is_safe_to_operate():
            return ""
        else:
            self._write_raw(":DISPlay:DATA? PNG")

            try:
                image_data = self._instrument.read_raw()
            except Exception:
                image_data = None

            if not image_data:
                return ""
            else:
                if file_name is None:
                    file_name = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"

                try:
                    with open(file_name, "wb") as file_handle:
                        if image_data.startswith(b"#"):
                            header_length = int(chr(image_data[1]))
                            image_data = image_data[2 + header_length:]

                        file_handle.write(image_data)

                    return file_name
                except Exception:
                    return ""


    def save_setup(self, memory_location: str = "1"):
        if self._is_safe_to_operate():
            self._write_raw(f":SAVE:SETup {memory_location}")


    def recall_setup(self, memory_location: str = "1"):
        if self._is_safe_to_operate():
            self._write_raw(f":RECall:SETup {memory_location}")


    def get_ip_address(self) -> str:
        if not self._is_safe_to_operate():
            return ""
        else:
            try:
                return self._query_string(":SYSTem:COMMunicate:LAN:IPADdress?")
            except Exception:
                return ""


    def get_mac_address(self) -> str:
        if not self._is_safe_to_operate():
            return ""
        else:
            try:
                return self._query_string(":SYSTem:COMMunicate:LAN:MAC?")
            except Exception:
                return ""


    def get_device_information(self) -> Dict[str, str]:
        if not self._is_safe_to_operate():
            return {
                "manufacturer": "Unknown",
                "model_number": "Unknown",
                "serial_number": "Unknown",
                "firmware_version": "Unknown",
                "capabilities": str({})
            }
        else:
            device_info = {
                "manufacturer": self._manufacturer if self._manufacturer else "Unknown",
                "model_number": self._model_number if self._model_number else "Unknown",
                "serial_number": "Unknown",
                "firmware_version": "Unknown",
                "capabilities": str(self._capabilities)
            }

            try:
                full_identification = self._query_string("*IDN?")
                parts = full_identification.split(",")

                if len(parts) > 2:
                    device_info["serial_number"] = parts[2]

                if len(parts) > 3:
                    device_info["firmware_version"] = parts[3]
            except Exception:
                pass

            return device_info


    def get_all_settings(self) -> Dict[str, Any]:
        if not self._is_safe_to_operate():
            return {}
        else:
            all_settings = {
                "identification": self.get_identification(),
                "timebase_scale": self.get_timebase_scale(),
                "timebase_delay": self.get_timebase_delay(),
                "timebase_mode": self.get_timebase_mode(),
                "acquisition_type": self.get_acquisition_type(),
                "average_count": self.get_average_count(),
                "trigger_source": self.get_trigger_source(),
                "trigger_level": self.get_trigger_level(),
                "trigger_slope": self.get_trigger_slope(),
                "trigger_mode": self.get_trigger_mode(),
            }

            for channel_index in range(1, self._capabilities.get("maximum_channels", 4) + 1):
                try:
                    all_settings[f"channel_{channel_index}_enabled"] = self.is_channel_enabled(channel_index)
                    all_settings[f"channel_{channel_index}_scale"] = self.get_channel_scale(channel_index)
                    all_settings[f"channel_{channel_index}_offset"] = self.get_channel_offset(channel_index)
                    all_settings[f"channel_{channel_index}_coupling"] = self.get_channel_coupling(channel_index)
                except Exception:
                    continue

            return all_settings


    def compute_waveform_statistics(self, voltage_values: List[float]) -> Dict[str, float]:
        if not voltage_values:
            return {}
        else:
            try:
                voltage_array = numpy.array(voltage_values)

                return {
                    "points_count": len(voltage_values),
                    "maximum_voltage": float(numpy.max(voltage_array)),
                    "minimum_voltage": float(numpy.min(voltage_array)),
                    "peak_to_peak_voltage": float(numpy.ptp(voltage_array)),
                    "mean_voltage": float(numpy.mean(voltage_array)),
                    "rms_voltage": float(numpy.sqrt(numpy.mean(voltage_array ** 2))),
                    "standard_deviation": float(numpy.std(voltage_array))
                }
            except Exception:
                return {}
