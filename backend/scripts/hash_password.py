#!/usr/bin/env python3
"""
APP_PASSWORD_HASH を生成するヘルパー。

使い方:
    python backend/scripts/hash_password.py
    > パスワードを入力: ********
    > APP_PASSWORD_HASH='$2b$12$abc...'

  生成されたハッシュを backend/.env に貼り付けてください。
"""
import getpass
import sys

try:
    import bcrypt
except ImportError:
    print("bcrypt が必要です: pip install bcrypt", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    p1 = getpass.getpass("パスワードを入力: ")
    p2 = getpass.getpass("もう一度入力:    ")
    if p1 != p2:
        print("一致しません", file=sys.stderr)
        sys.exit(1)
    if not p1:
        print("空のパスワードは設定できません", file=sys.stderr)
        sys.exit(1)
    h = bcrypt.hashpw(p1.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()
    print()
    print("backend/.env に以下を追加してください（シングルクォート必須）:")
    print(f"APP_PASSWORD_HASH='{h}'")


if __name__ == "__main__":
    main()
