from types import SimpleNamespace

import jwt
import pytest
from pydantic import SecretStr

from core.security import SecurityManager


@pytest.fixture
def security_manager():
    fake_settings = SimpleNamespace(
        api=SimpleNamespace(
            jwt_secret_key=SecretStr("test-secret-key-for-unit-tests"),
            jwt_algorithm="HS256",
            access_token_expire_minutes=15,
        )
    )
    return SecurityManager(fake_settings)  # type: ignore[arg-type]


@pytest.fixture
def sample_claims():
    return {
        "user_id": 42,
        "username": "testuser",
        "email": "test@nananalu.com",
        "first_name": "Test",
        "last_name": "User",
        "tier": "free",
        "tier_id": 1,
        "is_admin": False,
    }


class TestAccessToken:
    def test_encodes_correct_claims(self, security_manager, sample_claims):
        token = security_manager.create_access_token(**sample_claims)
        decoded = security_manager.decode_access_token(token)

        assert decoded["sub"] == str(sample_claims["user_id"])
        assert decoded["email"] == sample_claims["email"]
        assert decoded["username"] == sample_claims["username"]
        assert decoded["first_name"] == sample_claims["first_name"]
        assert decoded["last_name"] == sample_claims["last_name"]
        assert decoded["tier"] == sample_claims["tier"]
        assert decoded["tier_id"] == sample_claims["tier_id"]
        assert decoded["is_admin"] == sample_claims["is_admin"]

    def test_token_contains_iat_and_exp(self, security_manager, sample_claims):
        token = security_manager.create_access_token(**sample_claims)
        decoded = security_manager.decode_access_token(token)

        assert "iat" in decoded
        assert "exp" in decoded
        assert decoded["exp"] > decoded["iat"]

    def test_expired_token_raises(self, sample_claims):
        expired_settings = SimpleNamespace(
            api=SimpleNamespace(
                jwt_secret_key=SecretStr("test-secret-key-for-unit-tests"),
                jwt_algorithm="HS256",
                access_token_expire_minutes=-1,
            )
        )
        manager = SecurityManager(expired_settings)  # type: ignore[arg-type]
        token = manager.create_access_token(**sample_claims)

        with pytest.raises(jwt.ExpiredSignatureError):
            manager.decode_access_token(token)


class TestDecodeAccessToken:
    def test_malformed_token_raises(self, security_manager):
        with pytest.raises(jwt.DecodeError):
            security_manager.decode_access_token("not.a.real.token")

    def test_wrong_secret_raises(self, security_manager, sample_claims):
        token = security_manager.create_access_token(**sample_claims)

        wrong_secret_manager = SecurityManager(
            SimpleNamespace(  # type: ignore[arg-type]
                api=SimpleNamespace(
                    jwt_secret_key=SecretStr("wrong-secret"),
                    jwt_algorithm="HS256",
                    access_token_expire_minutes=15,
                )
            )
        )

        with pytest.raises(jwt.InvalidSignatureError):
            wrong_secret_manager.decode_access_token(token)
