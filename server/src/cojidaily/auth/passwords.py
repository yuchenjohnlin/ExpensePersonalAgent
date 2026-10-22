"""Password hashes: Argon2id with the parameters backend/ and api/ use (Django 5.2's), so checking a
password costs the same, in argon2-cffi's standard encoding ($argon2id$v=19$m=102400,t=2,p=8$...)."""
import argon2

HASHER = argon2.PasswordHasher(time_cost=2, memory_cost=102400, parallelism=8, hash_len=32, salt_len=16)
# Checked against when the name is unknown, so a wrong name takes as long as a wrong password.
_DUMMY = HASHER.hash("a password nobody has")


def make_password(password: str) -> str:
    return HASHER.hash(password)


def check_password(password: str, encoded: str | None) -> tuple[bool, bool]:
    """(whether it matches, whether the hash should be remade with today's parameters)."""
    try:
        HASHER.verify(encoded or _DUMMY, password)
    except (argon2.exceptions.VerificationError, argon2.exceptions.InvalidHashError):
        return False, False
    if encoded is None:
        return False, False
    return True, HASHER.check_needs_rehash(encoded)


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 8:
        problems.append("密碼至少 8 個字元。")
    if password.isdigit():
        problems.append("密碼不能全是數字。")
    return problems
