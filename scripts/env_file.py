"""Small helpers to read the .env file, so no password has to be written in the code."""
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def read_env(path=None):
    path = path or os.path.join(ROOT, ".env")
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    return values


def database_url():
    """DATABASE_URL if it is set, otherwise built from .env (the database port is 5433 on your computer)."""
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env = read_env()
    if "POSTGRES_PASSWORD" not in env:
        raise RuntimeError("Set DATABASE_URL or create a .env file (copy .env.example).")
    return f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@localhost:5433/{env['POSTGRES_DB']}"
