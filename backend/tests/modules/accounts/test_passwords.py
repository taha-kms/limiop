from app.modules.accounts.passwords import hash_password, verify_password


def test_a_hash_does_not_contain_the_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in hashed


def test_the_same_password_hashes_differently_every_time() -> None:
    assert hash_password("hunter2") != hash_password("hunter2")


def test_the_right_password_verifies() -> None:
    assert verify_password("hunter2", hash_password("hunter2")) is True


def test_the_wrong_password_does_not() -> None:
    assert verify_password("hunter3", hash_password("hunter2")) is False


def test_a_malformed_hash_is_a_failure_rather_than_a_crash() -> None:
    assert verify_password("hunter2", "not-a-hash") is False
