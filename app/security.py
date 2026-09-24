from pwdlib import PasswordHash


password_hasher = PasswordHash.recommended()


# Создаёт хеш пароля с индивидуальной солью.
def hash_password(password: str) -> str:
    return password_hasher.hash(password)
