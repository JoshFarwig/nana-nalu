import pytest

from utils.password import hash_password, verify_password, password_needs_rehash


@pytest.mark.unit
class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        hashed = hash_password("surfmaui123", rounds=4)
        assert verify_password("surfmaui123", hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("surfmaui123", rounds=4)
        assert verify_password("wrongpassword", hashed) is False

    def test_empty_password_returns_false(self):
        hashed = hash_password("surfmaui123", rounds=4)
        assert verify_password("", hashed) is False


@pytest.mark.unit
class TestPasswordNeedsRehash:
    def test_lower_cost_factor_requires_rehash(self):
        hashed = hash_password("password", rounds=4)
        assert password_needs_rehash(hashed, rounds=12) is True

    def test_same_cost_factor_does_not_require_rehash(self):
        hashed = hash_password("password", rounds=4)
        assert password_needs_rehash(hashed, rounds=4) is False

    def test_malformed_hash_returns_true(self):
        assert password_needs_rehash("not-a-bcrypt-hash", rounds=12) is True
