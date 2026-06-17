import numpy

from typing import List
from typing import Tuple


def _estimate_signal_roughness(signal_values: List[float]) -> float:
    signal_array = numpy.array(signal_values)
    first_derivative = numpy.diff(signal_array)
    second_derivative = numpy.diff(first_derivative)
    roughness_value = numpy.std(second_derivative) / (numpy.std(signal_array) + 1e-10)

    return roughness_value


def _detect_signal_peaks(signal_values: List[float], deviation_threshold: float = 3.0) -> List[int]:
    signal_array = numpy.array(signal_values)
    mean_value = numpy.mean(signal_array)
    standard_deviation = numpy.std(signal_array)
    peak_detection_level = mean_value + deviation_threshold * standard_deviation
    peak_positions = []

    for point_index in range(1, len(signal_array) - 1):
        is_peak_center = signal_array[point_index] > signal_array[point_index - 1] and signal_array[point_index] > signal_array[point_index + 1]
        is_above_threshold = signal_array[point_index] > peak_detection_level

        if is_peak_center and is_above_threshold:
            peak_positions.append(point_index)

    return peak_positions


def _trapezoidal_integration(time_values: List[float], signal_values: List[float]) -> float:
    integral_sum = 0.0

    for point_index in range(len(time_values) - 1):
        time_difference = time_values[point_index + 1] - time_values[point_index]
        amplitude_sum = signal_values[point_index + 1] + signal_values[point_index]
        integral_sum = integral_sum + time_difference * amplitude_sum / 2.0

    return integral_sum


def _simpson_integration(time_values: List[float], signal_values: List[float]) -> float:
    points_count = len(time_values)

    if points_count % 2 == 0:
        integration_result = _trapezoidal_integration(time_values, signal_values)
        return integration_result

    time_array = numpy.array(time_values)
    amplitude_array = numpy.array(signal_values)
    integral_sum = 0.0

    for point_index in range(0, points_count - 2, 2):
        time_difference = time_array[point_index + 2] - time_array[point_index]
        amplitude_sum = amplitude_array[point_index] + 4 * amplitude_array[point_index + 1] + amplitude_array[point_index + 2]
        integral_sum = integral_sum + time_difference * amplitude_sum / 6.0

    return integral_sum


def integrate_signal(time_values: List[float], signal_values: List[float]) -> float:
    signal_length_match = len(time_values) == len(signal_values)
    insufficient_points = len(time_values) < 2
    integration_result = 0.0

    if not signal_length_match or insufficient_points:
        return integration_result

    signal_roughness = _estimate_signal_roughness(signal_values)
    detected_peaks = _detect_signal_peaks(signal_values)
    total_points = len(time_values)
    is_smooth_signal = signal_roughness < 0.01 and len(detected_peaks) == 0
    is_odd_points = total_points % 2 == 1 and total_points >= 5

    if is_smooth_signal and is_odd_points:
        integration_result = _simpson_integration(time_values, signal_values)
    else:
        integration_result = _trapezoidal_integration(time_values, signal_values)

    return integration_result


def _impulse_model(time_moment: float, amplitude_value: float, fast_rate: float, slow_rate: float, time_shift: float, background_level: float = 0.0) -> float:
    if slow_rate == fast_rate:
        return background_level

    if time_moment <= time_shift:
        return background_level

    adjusted_time = time_moment - time_shift
    amplitude_factor = amplitude_value * fast_rate / (slow_rate - fast_rate)
    fast_exponential = numpy.exp(-fast_rate * adjusted_time)
    slow_exponential = numpy.exp(-slow_rate * adjusted_time)
    model_value = background_level + amplitude_factor * (fast_exponential - slow_exponential)

    return model_value


def approximate_signal(time_values: List[float], signal_values: List[float], use_background: bool = True) -> Tuple[List[float], dict]:
    signal_match = len(time_values) == len(signal_values)
    insufficient_points = len(time_values) < 5
    empty_result = (signal_values, {"operation_error": "Недостаточно точек для аппроксимации"})

    if not signal_match or insufficient_points:
        return empty_result

    min_signal = numpy.min(signal_values)
    max_signal = numpy.max(signal_values)

    if use_background:
        approximated_signal = []
        background_offset = min_signal
        signal_amplitude = max_signal - min_signal
        start_shift = time_values[0]

        for time_point in time_values:
            model_value = _impulse_model(time_point, signal_amplitude, 1.0, 10.0, start_shift, background_offset)
            approximated_signal.append(model_value)

        fitting_parameters = {
            "background_offset_volts": background_offset,
            "signal_amplitude_volts": signal_amplitude,
            "fast_decay_rate": 1.0,
            "slow_decay_rate": 10.0,
            "time_shift_seconds": start_shift,
            "fit_successful": False
        }
    else:
        approximated_signal = []
        signal_amplitude = max_signal - min_signal
        start_shift = time_values[0]

        for time_point in time_values:
            model_value = _impulse_model(time_point, signal_amplitude, 1.0, 10.0, start_shift, 0.0)
            approximated_signal.append(model_value)

        fitting_parameters = {
            "signal_amplitude_volts": signal_amplitude,
            "fast_decay_rate": 1.0,
            "slow_decay_rate": 10.0,
            "time_shift_seconds": start_shift,
            "fit_successful": False
        }

    original_array = numpy.array(signal_values)
    approximated_array = numpy.array(approximated_signal)
    max_original = numpy.max(original_array)

    if max_original > 0:
        residual_sum = numpy.sum((original_array - approximated_array) ** 2)
        total_sum = numpy.sum((original_array - numpy.mean(original_array)) ** 2)
        fitting_parameters["determination_coefficient"] = 1 - residual_sum / total_sum
    else:
        fitting_parameters["determination_coefficient"] = 0.0

    return approximated_signal, fitting_parameters
