from greeting import greet


def test_greet_alice():
    assert greet("Alice") == "Hello, Alice!"


def test_greet_bob():
    assert greet("Bob") == "Hello, Bob!"
