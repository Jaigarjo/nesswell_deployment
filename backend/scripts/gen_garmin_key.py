"""Generate the key that encrypts stored Garmin tokens. Keep it secret; losing it means users reconnect."""
from cryptography.fernet import Fernet

print(f"GARMIN_TOKEN_KEY={Fernet.generate_key().decode()}")
