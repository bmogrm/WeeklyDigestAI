from cryptography.fernet import Fernet
import base64
import os

# Инициализация ключа шифрования
def get_cipher():
    """Возвращает объект шифра на основе ключа из .env файла."""
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        raise ValueError("Ключ шифрования отсутствует в .env файле")
    return Fernet(key)

def encrypt_message(message: str) -> str:
    """Шифрует текстовое сообщение."""
    cipher = get_cipher()
    encrypted = cipher.encrypt(message.encode())
    return encrypted.decode()

def decrypt_message(encrypted_message: str) -> str:
    """Расшифровывает текстовое сообщение."""
    cipher = get_cipher()
    decrypted = cipher.decrypt(encrypted_message.encode())
    return decrypted.decode()
