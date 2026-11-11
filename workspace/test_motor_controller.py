"""pytest tests for MotorController. [Trace: REQ-MOTOR-001]"""

from __future__ import annotations

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
# Acceptance criteria
# ----------------------------------------------------------------------
def test_ac_001_defaults_to_idle_at_25() -> None:
    # [Trace: AC-001][ST-001]
    ctrl = MotorController()
    assert ctrl.state == IDLE
    assert ctrl.temperature == pytest.approx(25.0)


def test_ac_002_start_from_idle_safe_temp_reaches_running() -> None:
    # [Trace: AC-002][TR-001]
    ctrl = MotorController(25.0)
    ctrl.start()
    assert ctrl.state == RUNNING


def test_ac_003_stop_from_running_reaches_idle() -> None:
    # [Trace: AC-003][TR-002]
    ctrl = MotorController()
    ctrl.start()
    ctrl.stop()
    assert ctrl.state == IDLE
    assert ctrl.temperature == pytest.approx(25.0)


def test_ac_004_update_temperature_81_in_running_latches_fault() -> None:
    # [Trace: AC-004][TR-003]
    ctrl = MotorController()
    ctrl.start()
    result = ctrl.update_temperature(81)
    assert result == FAULT
    assert ctrl.state == FAULT


def test_ac_005_start_in_fault_raises_and_stays_fault() -> None:
    # [Trace: AC-005][CN-001]
    ctrl = MotorController()
    ctrl.start()
    ctrl.update_temperature(81)
    assert ctrl.state == FAULT

    with pytest.raises(SafetyInterlockError):
        ctrl.start()
    assert ctrl.state == FAULT


def test_ac_006_reset_in_fault_hot_raises_and_stays_fault() -> None:
    # [Trace: AC-006][CN-003]
    ctrl = MotorController(81)
    assert ctrl.state == FAULT
    assert ctrl.temperature == pytest.approx(81.0)

    with pytest.raises(SafetyInterlockError):
        ctrl.reset()
    assert ctrl.state == FAULT


def test_ac_007_reset_in_fault_cold_reaches_idle() -> None:
    # [Trace: AC-007][TR-004]
    ctrl = MotorController(81)
    assert ctrl.state == FAULT
    ctrl.update_temperature(25)
    assert ctrl.state == FAULT  # fault stays latched until reset
    ctrl.reset()
    assert ctrl.state == IDLE
    assert ctrl.temperature == pytest.approx(25.0)


def test_ac_008_construct_hot_starts_in_fault() -> None:
    # [Trace: AC-008][CN-002]
    ctrl = MotorController(81)
    assert ctrl.state == FAULT


# ----------------------------------------------------------------------
# Safety constraint specific tests
# ----------------------------------------------------------------------
def test_cn_001_fault_start_never_changes_state() -> None:
    # [Trace: CN-001]
    ctrl = MotorController(95.5)
    assert ctrl.state == FAULT
    for _ in range(3):
        with pytest.raises(SafetyInterlockError):
            ctrl.start()
        assert ctrl.state == FAULT
    assert ctrl.temperature == pytest.approx(95.5)


def test_cn_002_over_temperature_latches_from_idle() -> None:
    # [Trace: CN-002] IDLE path
    ctrl = MotorController()
    assert ctrl.state == IDLE
    assert ctrl.update_temperature(80.5) == FAULT
    assert ctrl.state == FAULT


def test_cn_002_over_temperature_latches_from_running() -> None:
    # [Trace: CN-002] RUNNING path
    ctrl = MotorController()
    ctrl.start()
    assert ctrl.state == RUNNING
    assert ctrl.update_temperature(81) == FAULT
    assert ctrl.state == FAULT


def test_cn_002_boundary_temperature_80_is_safe() -> None:
    # [Trace: CN-002] Boundary: exactly 80 is still safe.
    ctrl = MotorController(MAX_SAFE_TEMPERATURE)
    assert ctrl.state == IDLE
    ctrl.start()
    assert ctrl.state == RUNNING
    assert ctrl.update_temperature(MAX_SAFE_TEMPERATURE) == RUNNING


def test_cn_002_fault_is_not_cleared_by_cooling_update() -> None:
    # [Trace: CN-002][CN-003] Latch survives temperature drops.
    ctrl = MotorController(90)
    assert ctrl.state == FAULT
    assert ctrl.update_temperature(25) == FAULT
    assert ctrl.state == FAULT


def test_cn_003_reset_outside_fault_raises_and_preserves_state() -> None:
    # [Trace: CN-003]
    ctrl = MotorController()
    with pytest.raises(SafetyInterlockError):
        ctrl.reset()
    assert ctrl.state == IDLE

    ctrl.start()
    with pytest.raises(SafetyInterlockError):
        ctrl.reset()
    assert ctrl.state == RUNNING


def test_cn_004_start_outside_idle_raises_invalid_transition() -> None:
    # [Trace: CN-004]
    ctrl = MotorController()
    ctrl.start()
    assert ctrl.state == RUNNING
    with pytest.raises(InvalidTransitionError):
        ctrl.start()
    assert ctrl.state == RUNNING


def test_cn_005_stop_outside_running_raises_invalid_transition() -> None:
    # [Trace: CN-005] IDLE path
    ctrl = MotorController()
    with pytest.raises(InvalidTransitionError):
        ctrl.stop()
    assert ctrl.state == IDLE


def test_cn_005_stop_in_fault_raises_invalid_transition() -> None:
    # [Trace: CN-005] FAULT path
    ctrl = MotorController(81)
    with pytest.raises(InvalidTransitionError):
        ctrl.stop()
    assert ctrl.state == FAULT


def test_exception_hierarchy() -> None:
    # [Trace: REQ-MOTOR-001] Both exceptions derive from RuntimeError.
    assert issubclass(InvalidTransitionError, RuntimeError)
    assert issubclass(SafetyInterlockError, RuntimeError)


def test_update_temperature_rejects_non_numeric() -> None:
    # [Trace: TR-003] Non-numeric input must raise ValueError.
    ctrl = MotorController()
    for bad in ("hot", None, [81], {"t": 81}, True):
        with pytest.raises(ValueError):
            ctrl.update_temperature(bad)  # type: ignore[arg-type]
        assert ctrl.state == IDLE
        assert ctrl.temperature == pytest.approx(25.0)


def test_constructor_rejects_non_numeric_temperature() -> None:
    # [Trace: REQ-MOTOR-001] Constructor input validation.
    with pytest.raises(ValueError):
        MotorController("hot")  # type: ignore[arg-type]


def test_state_and_temperature_are_read_only() -> None:
    # [Trace: ST-001][ST-002][ST-003] Latched state cannot be bypassed.
    ctrl = MotorController(81)
    with pytest.raises(AttributeError):
        ctrl.state = IDLE  # type: ignore[misc]
    with pytest.raises(AttributeError):
        ctrl.temperature = 25.0  # type: ignore[misc]
    assert ctrl.state == FAULT
    assert ctrl.temperature == pytest.approx(81.0)


def test_full_recovery_cycle() -> None:
    # [Trace: REQ-MOTOR-001] IDLE -> RUNNING -> FAULT -> IDLE -> RUNNING.
    ctrl = MotorController()
    ctrl.start()
    assert ctrl.state == RUNNING
    ctrl.update_temperature(85)
    assert ctrl.state == FAULT
    with pytest.raises(SafetyInterlockError):
        ctrl.reset()
    assert ctrl.state == FAULT
    ctrl.update_temperature(30)
    ctrl.reset()
    assert ctrl.state == IDLE
    ctrl.start()
    assert ctrl.state == RUNNING
