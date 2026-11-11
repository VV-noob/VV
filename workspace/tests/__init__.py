"""Test package marker for the motor controller test suite.

An explicit package (plus ``pytest.ini``'s ``--import-mode=importlib``)
prevents the pytest "import file mismatch" error that occurs when two
same-named test modules exist at different paths.

[Trace: REQ-MOTOR-001]
"""
