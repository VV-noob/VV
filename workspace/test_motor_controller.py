"""Pytest suite for REQ-MOTOR-001: MotorController state machine."""

import pytest

from motor_controller import (
    InvalidTransitionError,
    MotorController,
    SafetyInterlockError,
)


# ----------------------------------------------------------------------
# Initial state / constructor
# ----------------------------------------------------------------------
def test_initial_state_idle_at_25():
    # [Trace: REQ-MOTOR-001/AC-001] [Trace: REQ-MOTOR-001/ST-001]
    m = MotorController()
    assert m.state == "IDLE"
    assert m.temperature == 25.0


def test_initial_state_default_parameter_explicit():
    # [Trace: REQ-MOTOR-001/AC-001]
    m = MotorController(initial_temperature=25.0)
    assert (m.state, m.temperature) == ("IDLE", 25.0)


def test_constructor_hot_latches_fault():
    # [Trace: REQ-MOTOR-001/AC-008] [Trace: REQ-MOTOR-001/CN-002]
    m = MotorController(81)
    assert m.state == "FAULT"
    assert m.temperature == 81.0


def test_constructor_at_boundary_80_stays_idle():
    # [Trace: REQ-MOTOR-001/TR-001] condition temperature <= 80
    m = MotorController(80)
    assert m.state == "IDLE"
    assert m.temperature == 80.0


def test_constructor_rejects_non_numeric_temperature():
    # [Trace: REQ-MOTOR-001/interface.update_temperature] ValueError path
    with pytest.raises(ValueError):
        MotorController("hot")


# ----------------------------------------------------------------------
# TR-001: start IDLE -> RUNNING
# ----------------------------------------------------------------------
def test_start_from_idle_moves_to_running():
    # [Trace: REQ-MOTOR-001/AC-002] [Trace: REQ-MOTOR-001/TR-001]
    m = MotorController()
    assert m.start() is None
    assert m.state == "RUNNING"


def test_start_allowed_at_boundary_temperature_80():
    # [Trace: REQ-MOTOR-001/TR-001] temperature <= 80
    m = MotorController(80)
    m.start()
    assert m.state == "RUNNING"


# ----------------------------------------------------------------------
# TR-002: stop RUNNING -> IDLE
# ----------------------------------------------------------------------
def test_stop_from_running_moves_to_idle():
    # [Trace: REQ-MOTOR-001/AC-003] [Trace: REQ-MOTOR-001/TR-002]
    m = MotorController()
    m.start()
    assert m.stop() is None
    assert m.state == "IDLE"


def test_full_cycle_start_stop_twice():
    # [Trace: REQ-MOTOR-001/TR-001] [Trace: REQ-MOTOR-001/TR-002]
    m = MotorController()
    m.start()
    m.stop()
    m.start()
    m.stop()
    assert m.state == "IDLE"


# ----------------------------------------------------------------------
# TR-003: update_temperature -> FAULT when value > 80
# ----------------------------------------------------------------------
def test_update_temperature_from_running_latches_fault():
    # [Trace: REQ-MOTOR-001/AC-004] [Trace: REQ-MOTOR-001/TR-003]
    # [Trace: REQ-MOTOR-001/CN-002]
    m = MotorController()
    m.start()
    result = m.update_temperature(81)
    assert result == "FAULT"
    assert m.state == "FAULT"
    assert m.temperature == 81.0


def test_update_temperature_from_idle_latches_fault():
    # [Trace: REQ-MOTOR-001/TR-003] from IDLE
    # [Trace: REQ-MOTOR-001/CN-002]
    m = MotorController()
    assert m.update_temperature(90) == "FAULT"
    assert m.state == "FAULT"
    assert m.temperature == 90.0


def test_update_temperature_safe_keeps_running():
    # [Trace: REQ-MOTOR-001/TR-003] condition value > 80 must hold
    m = MotorController()
    m.start()
    assert m.update_temperature(80) == "RUNNING"
    assert m.state == "RUNNING"
    assert m.temperature == 80.0


def test_update_temperature_safe_keeps_idle():
    # [Trace: REQ-MOTOR-001/TR-003]
    m = MotorController()
    assert m.update_temperature(50) == "IDLE"
    assert m.state == "IDLE"
    assert m.temperature == 50.0


def test_update_temperature_fault_stays_latched():
    # [Trace: REQ-MOTOR-001/ST-003] fault is latched
    m = MotorController()
    m.update_temperature(95)
    assert m.update_temperature(20) == "FAULT"
    assert m.state == "FAULT"
    assert m.temperature == 20.0


@pytest.mark.parametrize("bad_value", ["hot", None, object(), float("nan")])
def test_update_temperature_rejects_invalid_values(bad_value):
    # [Trace: REQ-MOTOR-001/interface.update_temperature] ValueError
    m = MotorController()
    with pytest.raises(ValueError):
        m.update_temperature(bad_value)
    # state and temperature untouched by a rejected value
    assert m.state == "IDLE"
    assert m.temperature == 25.0


# ----------------------------------------------------------------------
# CN-001 / CN-004: start() legality
# ----------------------------------------------------------------------
def test_start_in_fault_raises_safety_interlock_and_stays_fault():
    # [Trace: REQ-MOTOR-001/AC-005] [Trace: REQ-MOTOR-001/CN-001]
    m = MotorController(81)
    with pytest.raises(SafetyInterlockError):
        m.start()
    assert m.state == "FAULT"


def test_start_in_running_raises_invalid_transition():
    # [Trace: REQ-MOTOR-001/CN-004] start legal only in IDLE
    m = MotorController()
    m.start()
    with pytest.raises(InvalidTransitionError):
        m.start()
    assert m.state == "RUNNING"


def test_start_error_types_are_distinct():
    # [Trace: REQ-MOTOR-001/CN-004] [Trace: REQ-MOTOR-001/CN-001]
    assert issubclass(InvalidTransitionError, RuntimeError)
    assert issubclass(SafetyInterlockError, RuntimeError)
    hot = MotorController(85)
    with pytest.raises(SafetyInterlockError):
        hot.start()
    with pytest.raises(RuntimeError):
        hot.start()


# ----------------------------------------------------------------------
# CN-005: stop() legality
# ----------------------------------------------------------------------
def test_stop_in_idle_raises_invalid_transition():
    # [Trace: REQ-MOTOR-001/CN-005]
    m = MotorController()
    with pytest.raises(InvalidTransitionError):
        m.stop()
    assert m.state == "IDLE"


def test_stop_in_fault_raises_invalid_transition():
    # [Trace: REQ-MOTOR-001/CN-005]
    m = MotorController(81)
    with pytest.raises(InvalidTransitionError):
        m.stop()
    assert m.state == "FAULT"


# ----------------------------------------------------------------------
# TR-004 / CN-003: reset() legality
# ----------------------------------------------------------------------
def test_reset_in_fault_hot_raises_and_stays_fault():
    # [Trace: REQ-MOTOR-001/AC-006] [Trace: REQ-MOTOR-001/CN-003]
    m = MotorController(81)
    with pytest.raises(SafetyInterlockError):
        m.reset()
    assert m.state == "FAULT"


def test_reset_in_fault_cool_moves_to_idle():
    # [Trace: REQ-MOTOR-001/AC-007] [Trace: REQ-MOTOR-001/TR-004]
    m = MotorController(81)
    m.update_temperature(25)
    assert m.reset() is None
    assert m.state == "IDLE"


def test_reset_after_latching_fault_from_running():
    # [Trace: REQ-MOTOR-001/TR-003] -> [Trace: REQ-MOTOR-001/TR-004]
    m = MotorController()
    m.start()
    m.update_temperature(99)
    assert m.state == "FAULT"
    m.update_temperature(25)
    m.reset()
    assert m.state == "IDLE"


def test_reset_at_boundary_temperature_80_allowed():
    # [Trace: REQ-MOTOR-001/TR-004] temperature <= 80
    m = MotorController(81)
    m.update_temperature(80)
    m.reset()
    assert m.state == "IDLE"


def test_reset_in_idle_raises_safety_interlock():
    # [Trace: REQ-MOTOR-001/CN-003] reset legal only in FAULT
    m = MotorController()
    with pytest.raises(SafetyInterlockError):
        m.reset()
    assert m.state == "IDLE"


def test_reset_in_running_raises_safety_interlock():
    # [Trace: REQ-MOTOR-001/CN-003] reset legal only in FAULT
    m = MotorController()
    m.start()
    with pytest.raises(SafetyInterlockError):
        m.reset()
    assert m.state == "RUNNING"


def test_after_reset_start_and_stop_work_again():
    # [Trace: REQ-MOTOR-001/TR-004] then TR-001 / TR-002
    m = MotorController(95)
    m.update_temperature(25)
    m.reset()
    m.start()
    assert m.state == "RUNNING"
    m.stop()
    assert m.state == "IDLE"


def test_state_values_are_limited_to_declared_states():
    # [Trace: REQ-MOTOR-001/ST-001] [Trace: REQ-MOTOR-001/ST-002]
    # [Trace: REQ-MOTOR-001/ST-003]
    m = MotorController()
    seen = {m.state}
    m.start()
    seen.add(m.state)
    m.update_temperature(120)
    seen.add(m.state)
    assert seen == {"IDLE", "RUNNING", "FAULT"}
