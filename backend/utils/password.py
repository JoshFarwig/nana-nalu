import bcrypt


def hash_password(password: str, rounds: int) -> str:
    salt = bcrypt.gensalt(rounds)
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed.decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def password_needs_rehash(hashed_password: str, rounds: int) -> bool:
    try:
        # bcrypt hashes use $version$cost$salt+hash
        parts = hashed_password.split("$")
        current_cost = int(parts[1])
        return current_cost < rounds
    except (ValueError, IndexError):
        return True
