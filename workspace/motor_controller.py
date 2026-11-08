"""Safety-interlocked three-state motor controller.

Implements requirement REQ-MOTOR-001 as an explicit class-based state machine
with states IDLE, RUNNING and FAULT.
"""

from __future__ import annotations

# [Trace: REQ-MOTOR-001/exceptions]
SAFE_TEMPERATURE_LIMIT = 80.0


class InvalidTransitionError(RuntimeError):
    """Raised when a trigger is not legal in the current state."""


class SafetyInterlockError(RuntimeError):
    """Raised when a safety interlock forbids an operation."""


class MotorController:
    """Three-state motor controller with temperature monitoring.

    States: IDLE (ST-001), RUNNING (ST-002), FAULT (ST-003).
    """

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    FAULT = "FAULT"

    def __init__(self, initial_temperature: float = 25.0) -> None:
        # [Trace: REQ-MOTOR-001/ST-001] initial state is IDLE
        self._state = self.IDLE
        self._temperature = self._validate_temperature(initial_temperature)

        # [Trace: REQ-MOTOR-001/AC-008] over-temperature at boot latches FAULT
        # [Trace: REQ-MOTOR-001/CN-002]
        if self._temperature > SAFE_TEMPERATURE_LIMIT:
            self._state = self.FAULT

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def state(self) -> str:
        """Current state: IDLE, RUNNING or FAULT."""
        return self._state

    @property
    def temperature(self) -> float:
        """Last observed temperature in degrees."""
        return self._temperature

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_temperature(value: float) -> float:
        # [Trace: REQ-MOTOR-001/interface.update_temperature] raises ValueError
        try:
            temperature = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"temperature must be a number, got {value!r}") from None
        if temperature != temperature:  # NaN check
            raise ValueError("temperature must be a real number, got NaN")
        return temperature

    def _is_safe(self) -> bool:
        return self._temperature <= SAFE_TEMPERATURE_LIMIT

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the motor: IDLE -> RUNNING when temperature <= 80."""
        if self._state == self.FAULT:
            # [Trace: REQ-MOTOR-001/CN-001]
            raise SafetyInterlockError(
                "cannot start while fault is latched; reset() first"
            )
        if self._state != self.IDLE:
            # [Trace: REQ-MOTOR-001/CN-004]
            raise InvalidTransitionError(
                f"start() not allowed in state {self._state}"
            )
        if not self._is_safe():
            # [Trace: REQ-MOTOR-001/TR-001] condition temperature <= 80
            # [Trace: REQ-MOTOR-001/CN-002]
            self._state = self.FAULT
            raise SafetyInterlockError(
                f"cannot start at unsafe temperature {self._temperature}"
            )
        # [Trace: REQ-MOTOR-001/TR-001]
        self._state = self.RUNNING

    def stop(self) -> None:
        """Stop the motor: RUNNING -> IDLE."""
        if self._state != self.RUNNING:
            # [Trace: REQ-MOTOR-001/CN-005]
            raise InvalidTransitionError(
                f"stop() not allowed in state {self._state}"
            )
        # [Trace: REQ-MOTOR-001/TR-002] always allowed from RUNNING
        self._state = self.IDLE

    def update_temperature(self, value: float) -> str:
        """Record a new temperature; over-temperature latches FAULT."""
        temperature = self._validate_temperature(value)
        self._temperature = temperature

        # [Trace: REQ-MOTOR-001/TR-003] IDLE or RUNNING -> FAULT if value > 80
        # [Trace: REQ-MOTOR-001/CN-002]
        if self._state in (self.IDLE, self.RUNNING) and not self._is_safe():
            self._state = self.FAULT

        # [Trace: REQ-MOTOR-001/TR-003] returns the resulting state
        return self._state

    def reset(self) -> None:
        """Clear a latched fault: FAULT -> IDLE when temperature <= 80."""
        if self._state != self.FAULT:
            # [Trace: REQ-MOTOR-001/CN-003] reset() is legal only in FAULT
            raise SafetyInterlockError(
                f"reset() not allowed in state {self._state}"
            )
        if not self._is_safe():
            # [Trace: REQ-MOTOR-001/CN-003]
            # [Trace: REQ-MOTOR-001/AC-006]
            raise SafetyInterlockError(
                f"cannot reset while temperature {self._temperature} is unsafe"
            )
        # [Trace: REQ-MOTOR-001/TR-004]
        self._state = self.IDLE
