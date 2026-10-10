"""Genera el hash bcrypt de la contraseña del administrador.

Uso:
    python -m app.hash_password
    docker compose run --rm backend python -m app.hash_password
"""

from __future__ import annotations

import getpass
import secrets
import sys

import bcrypt


def main() -> int:
    password = getpass.getpass("Contraseña del administrador: ")
    if len(password) < 8:
        print("La contraseña debe tener al menos 8 caracteres.", file=sys.stderr)
        return 1
    if len(password.encode()) > 72:
        print("La contraseña no puede superar 72 bytes (límite de bcrypt).", file=sys.stderr)
        return 1
    if getpass.getpass("Repite la contraseña: ") != password:
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    print("\nCopia estas líneas en backend/.env:\n")
    # Comillas simples: el hash contiene '$' y docker compose lo interpolaría.
    print(f"ADMIN_PASSWORD_HASH='{hashed}'")
    print(f"SESSION_SECRET={secrets.token_urlsafe(48)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
