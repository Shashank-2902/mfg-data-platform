"""Create n8n/credentials.json from the values in .env.

n8n imports this file when it starts. The file contains secrets, so it is
listed in .gitignore and never committed.
    python scripts/make_n8n_credentials.py
"""
import json
import os

from env_file import read_env

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def main():
    env = read_env()

    credentials = [
        {
            "id": "mfgpostgres01",
            "name": "mfg Postgres",
            "type": "postgres",
            "data": {
                "host": "timescaledb",
                "port": 5432,
                "database": env["POSTGRES_DB"],
                "user": env["POSTGRES_USER"],
                "password": env["POSTGRES_PASSWORD"],
                "ssl": "disable",
                "allowUnauthorizedCerts": False,
                "sshTunnel": False,
            },
        },
        {
            "id": "mfgtelegram01",
            "name": "mfg Telegram",
            "type": "telegramApi",
            "data": {
                "accessToken": env.get("TELEGRAM_BOT_TOKEN") or "token-not-set",
                "baseUrl": env.get("TELEGRAM_BASE_URL") or "https://api.telegram.org",
            },
        },
    ]

    path = os.path.join(ROOT, "n8n", "credentials.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
