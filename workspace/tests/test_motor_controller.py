"""Pytest suite for MotorController.

[Trace: REQ-MOTOR-001] Covers AC-001..AC-008 and safety constraints
CN-001..CN-005.
"""

from __future__ import annotations

import math

import pytest

from motor_controller import (
    FAULT,
    IDLE,
    MAX_SAFE_TEMPERATURE,
    RUNNING,
    InvalidTransitionError,
    MotorController,
    SafetyInterlockError,
)


# ----------------------------------------------------------------------
# AC-001 .. AC-008 acceptance criteria
# ----------------------------------------------------------------------
def test_ac_001_default_construction_is_idle_at_25():
    """[Trace: AC-001][ST-001]"""
    mc = MotorController()
    assert mc.state == IDLE
    assert mc.temperature == 25.0


def test_ac_002_start_from_idle_moves_to_running():
    """[Trace: AC-002][TR-001]"""
    mc = MotorController(initial_temperature=25.0)
    mc.start()
    assert mc.state == RUNNING


def test_ac_003_stop_from_running_returns_to_idle():
    """[Trace: AC-003][TR-002]"""
    mc = MotorController()
    mc.start()
    mc.stop()
    assert mc.state == IDLE


def test_ac_004_update_temperature_81_from_running_latches_fault():
    """[Trace: AC-004][TR-003][CN-002]"""
    mc = MotorController()
    mc.start()
    result = mc.update_temperature(81)
    assert result == FAULT
    assert mc.state == FAULT


def test_ac_005_start_in_fault_raises_and_stays_fault():
    """[Trace: AC-005][CN-001]"""
    mc = MotorController(initial_temperature=81)
    assert mc.state == FAULT
    with pytest.raises(SafetyInterlockError):
        mc.start()
    assert mc.state == FAULT


def test_ac_006_reset_in_fault_hot_raises_and_stays_fault():
    """[Trace: AC-006][CN-003]"""
    mc = MotorController(initial_temperature=81)
    assert mc.state == FAULT
    assert mc.temperature > MAX_SAFE_TEMPERATURE
    with pytest.raises(SafetyInterlockError):
        mc.reset()
    assert mc.state == FAULT


def test_ac_007_reset_in_fault_when_cool_returns_to_idle():
    """[Trace: AC-007][TR-004]"""
    mc = MotorController(initial_temperature=81)
    mc.update_temperature(25)
    assert mc.state == FAULT  # cooling alone never clears the latch
    mc.reset()
    assert mc.state == IDLE


def test_ac_008_hot_constructor_latches_fault():
    """[Trace: AC-008][CN-002]"""
    mc = MotorController(initial_temperature=81)
    assert mc.state == FAULT
    assert mc.temperature == 81


# ----------------------------------------------------------------------
# CN-001: FAULT interlock on start()
# ----------------------------------------------------------------------
def test_cn_001_start_in_fault_is_blocked_and_state_unchanged():
    """[Trace: CN-001]"""
    mc = MotorController()
    mc.start()
    mc.update_temperature(100)
    assert mc.state == FAULT
    before_temp = mc.temperature
    with pytest.raises(SafetyInterlockError):
        mc.start()
    assert mc.state == FAULT
    assert mc.temperature == before_temp


# ----------------------------------------------------------------------
# CN-002: over-temperature latches FAULT from BOTH IDLE and RUNNING
# ----------------------------------------------------------------------
@pytest.mark.parametrize("origin", [IDLE, RUNNING])
def test_cn_002_over_temperature_latches_fault_from_both_states(origin):
    """[Trace: CN-002][TR-003]"""
    mc = MotorController()
    if origin == RUNNING:
        mc.start()
    assert mc.state == origin
    result = mc.update_temperature(MAX_SAFE_TEMPERATURE + 1)
    assert result == FAULT
    assert mc.state == FAULT


def test_cn_002_boundary_value_80_is_safe():
    """[Trace: CN-002] 80 is the last safe value (condition is `> 80`)."""
    mc = MotorController()
    assert mc.update_temperature(80) == IDLE
    mc.start()
    assert mc.state == RUNNING
    assert mc.update_temperature(80) == RUNNING


def test_cn_002_fault_latch_is_sticky_across_legal_temperatures():
    """[Trace: CN-002][CN-003] Cooling must not silently clear the latch."""
    mc = MotorController(initial_temperature=90)
    assert mc.state == FAULT
    mc.update_temperature(20)
    assert mc.state == FAULT


# ----------------------------------------------------------------------
# CN-003: reset() only legal in FAULT and only when temperature <= 80
# ----------------------------------------------------------------------
def test_cn_003_reset_in_idle_raises_and_state_unchanged():
    """[Trace: CN-003]"""
    mc = MotorController()
    with pytest.raises(SafetyInterlockError):
        mc.reset()
    assert mc.state == IDLE


def test_cn_003_reset_in_running_raises_and_state_unchanged():
    """[Trace: CN-003]"""
    mc = MotorController()
    mc.start()
    with pytest.raises(SafetyInterlockError):
        mc.reset()
    assert mc.state == RUNNING


def test_cn_003_reset_in_fault_hot_raises_and_keeps_fault():
    """[Trace: CN-003][AC-006]"""
    mc = MotorController(initial_temperature=81)
    with pytest.raises(SafetyInterlockError):
        mc.reset()
    assert mc.state == FAULT


def test_cn_003_reset_boundary_80_is_safe():
    """[Trace: CN-003][TR-004] temperature exactly 80 permits reset."""
    mc = MotorController(initial_temperature=81)
    mc.update_temperature(80)
    mc.reset()
    assert mc.state == IDLE


# ----------------------------------------------------------------------
# CN-004: start() only legal in IDLE
# ----------------------------------------------------------------------
def test_cn_004_start_in_running_raises_invalid_transition():
    """[Trace: CN-004]"""
    mc = MotorController()
    mc.start()
    with pytest.raises(InvalidTransitionError):
        mc.start()
    assert mc.state == RUNNING


def test_cn_004_start_in_fault_raises_safety_interlock():
    """[Trace: CN-004][CN-001] FAULT takes precedence over InvalidTransition."""
    mc = MotorController(initial_temperature=81)
    with pytest.raises(SafetyInterlockError):
        mc.start()
    assert mc.state == FAULT


# ----------------------------------------------------------------------
# CN-005: stop() only legal in RUNNING
# ----------------------------------------------------------------------
def test_cn_005_stop_in_idle_raises_invalid_transition():
    """[Trace: CN-005]"""
    mc = MotorController()
    with pytest.raises(InvalidTransitionError):
        mc.stop()
    assert mc.state == IDLE


def test_cn_005_stop_in_fault_raises_invalid_transition():
    """[Trace: CN-005]"""
    mc = MotorController(initial_temperature=81)
    with pytest.raises(InvalidTransitionError):
        mc.stop()
    assert mc.state == FAULT


# ----------------------------------------------------------------------
# TR-003: temperature input validation
# ----------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["hot", None, [1], {"t": 1}, object()])
def test_update_temperature_non_numeric_raises_value_error(bad):
    """[Trace: TR-003] Non-numeric temperature input raises ValueError."""
    mc = MotorController()
    with pytest.raises(ValueError):
        mc.update_temperature(bad)
    assert mc.state == IDLE
    assert mc.temperature == 25.0


def test_update_temperature_bool_raises_value_error():
    """[Trace: TR-003] bool is not accepted as a temperature."""
    mc = MotorController()
    with pytest.raises(ValueError):
        mc.update_temperature(True)
    assert mc.state == IDLE


def test_update_temperature_nan_raises_value_error():
    """[Trace: TR-003][CN-002] NaN is unordered and must not bypass the guard."""
    mc = MotorController()
    with pytest.raises(ValueError):
        mc.update_temperature(float("nan"))
    assert mc.state == IDLE


def test_update_temperature_positive_infinity_latches_fault():
    """[Trace: TR-003][CN-002] +inf > 80, so it must latch FAULT (not raise)."""
    mc = MotorController()
    mc.start()
    result = mc.update_temperature(float("inf"))
    assert result == FAULT
    assert mc.state == FAULT
    assert math.isinf(mc.temperature)


def test_update_temperature_negative_infinity_is_safe():
    """[Trace: TR-003][CN-002] -inf is below the limit: state unchanged."""
    mc = MotorController()
    result = mc.update_temperature(float("-inf"))
    assert result == IDLE
    assert mc.state == IDLE
    assert mc.temperature == float("-inf")


def test_constructor_non_numeric_temperature_raises_value_error():
    """[Trace: TR-003] Constructor validates its input the same way."""
    with pytest.raises(ValueError):
        MotorController(initial_temperature="hot")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Exception taxonomy
# ----------------------------------------------------------------------
def test_exceptions_derive_from_runtime_error():
    """[Trace: CN-001][CN-004] Both exceptions extend RuntimeError."""
    assert issubclass(InvalidTransitionError, RuntimeError)
    assert issubclass(SafetyInterlockError, RuntimeError)


# ----------------------------------------------------------------------
# State properties are read-only (latch cannot be bypassed)
# ----------------------------------------------------------------------
def test_state_and_temperature_are_read_only():
    """[Trace: CN-001][CN-003] External writes must not bypass the latch."""
    mc = MotorController(initial_temperature=81)
    with pytest.raises(AttributeError):
        mc.state = IDLE  # type: ignore[misc]
    with pytest.raises(AttributeError):
        mc.temperature = 25.0  # type: ignore[misc]
    assert mc.state == FAULT
