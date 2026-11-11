"""Motor controller module.

[Trace: REQ-MOTOR-001] Safety-interlocked three-state motor controller
with temperature monitoring.

States:
    [Trace: ST-001] IDLE    - motor stopped; start allowed only at safe temp.
    [Trace: ST-002] RUNNING - motor energized; over-temperature latches FAULT.
    [Trace: ST-003] FAULT   - fault latched; start forbidden until safe reset.
"""

from __future__ import annotations

import math

# [Trace: REQ-MOTOR-001] State literals.
IDLE = "IDLE"        # [Trace: ST-001]
RUNNING = "RUNNING"  # [Trace: ST-002]
FAULT = "FAULT"      # [Trace: ST-003]

# [Trace: CN-002] Temperature above this value forces a latched FAULT.
MAX_SAFE_TEMPERATURE = 80.0


# [Trace: CN-004][CN-005] Raised for structurally illegal transitions.
class InvalidTransitionError(RuntimeError):
    """Raised when a transition is not legal from the current state."""


# [Trace: CN-001][CN-003] Raised when a safety interlock forbids the action.
class SafetyInterlockError(RuntimeError):
    """Raised when a safety interlock prevents the requested action."""


class MotorController:
    """Three-state motor controller with latched over-temperature fault.

    [Trace: REQ-MOTOR-001]
    """

    def __init__(self, initial_temperature: float = 25.0) -> None:
        # [Trace: AC-008][CN-002] Constructor must latch FAULT on hot start.
        self._temperature = self._coerce_temperature(
            initial_temperature, parameter="initial_temperature"
        )
        if self._temperature > MAX_SAFE_TEMPERATURE:
            self._state = FAULT
        else:
            self._state = IDLE

    # ------------------------------------------------------------------
    # Properties (read-only so the latched state cannot be bypassed)
    # ------------------------------------------------------------------
    @property
    def state(self) -> str:
        """Current state: IDLE, RUNNING or FAULT.

        [Trace: ST-001][ST-002][ST-003]
        """
        return self._state

    @property
    def temperature(self) -> float:
        """Current monitored temperature in degrees.

        [Trace: ST-001]
        """
        return self._temperature

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_temperature(value: object, parameter: str = "value") -> float:
        """Validate and normalise a temperature input.

        [Trace: TR-003] Non-numeric input must raise ValueError.
        NaN is rejected because it is not an ordered temperature reading and
        would silently defeat the `> MAX_SAFE_TEMPERATURE` guard in CN-002.
        +inf / -inf are *valid* numbers per the design: +inf exceeds the limit
        and therefore latches FAULT (CN-002), -inf is safely below the limit.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"{parameter} must be a real number, got {type(value).__name__}"
            )
        number = float(value)
        if math.isnan(number):
            raise ValueError(f"{parameter} must be an ordered number (not NaN)")
        return number

    def _latch_fault_if_hot(self) -> None:
        """Latch FAULT whenever the temperature exceeds the safe limit.

        [Trace: CN-002][TR-003]
        """
        if self._temperature > MAX_SAFE_TEMPERATURE:
            self._state = FAULT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Energise the motor: IDLE -> RUNNING.

        [Trace: TR-001][AC-002]
        [Trace: CN-001][AC-005] In FAULT raise SafetyInterlockError, stay FAULT.
        [Trace: CN-004] Only legal from IDLE, otherwise InvalidTransitionError.
        """
        # Interlock check first: a latched fault must never be bypassed.
        if self._state == FAULT:
            raise SafetyInterlockError(
                "start() forbidden: fault is latched; call reset() when safe"
            )
        if self._state != IDLE:
            raise InvalidTransitionError(
                f"start() is only legal in {IDLE}, current state is {self._state}"
            )
        # [Trace: TR-001] Guard on temperature; a hot IDLE latches FAULT.
        if self._temperature > MAX_SAFE_TEMPERATURE:
            self._state = FAULT
            raise SafetyInterlockError(
                "start() forbidden: temperature "
                f"{self._temperature} exceeds {MAX_SAFE_TEMPERATURE}"
            )
        self._state = RUNNING

    def stop(self) -> None:
        """De-energise the motor: RUNNING -> IDLE.

        [Trace: TR-002][AC-003]
        [Trace: CN-005] Only legal from RUNNING, otherwise InvalidTransitionError.
        """
        if self._state != RUNNING:
            raise InvalidTransitionError(
                f"stop() is only legal in {RUNNING}, current state is {self._state}"
            )
        self._state = IDLE

    def update_temperature(self, value: float) -> str:
        """Update the monitored temperature and return the resulting state.

        [Trace: TR-003][CN-002][AC-004]
        """
        self._temperature = self._coerce_temperature(value, parameter="value")
        # Latched fault is never cleared here; over-temperature latches FAULT.
        self._latch_fault_if_hot()
        return self._state

    def reset(self) -> None:
        """Clear a latched fault: FAULT -> IDLE when safe.

        [Trace: TR-004][AC-007]
        [Trace: CN-003][AC-006] Legal only in FAULT and only when temperature
        is safe; otherwise SafetyInterlockError and state remains FAULT.
        """
        if self._state != FAULT:
            raise SafetyInterlockError(
                f"reset() is only legal in {FAULT}, current state is {self._state}"
            )
        if self._temperature > MAX_SAFE_TEMPERATURE:
            raise SafetyInterlockError(
                "reset() forbidden: temperature "
                f"{self._temperature} exceeds {MAX_SAFE_TEMPERATURE}"
            )
        self._state = IDLE
