"""一時診断: 各チャンネルのOAuthトークンを refresh_token で更新試行する。"""
import os
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent  # repo root

# .env を読み込んで環境変数へ（JWT_SECRET が復号に必須）
env_path = ROOT / "backend" / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(ROOT / "backend"))

from pipeline import youtube_oauth as yo  # noqa: E402
from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from datetime import datetime  # noqa: E402

CHANNELS = ["daily-science", "scp-lab"]

for ch in CHANNELS:
    print(f"\n{'='*60}\nチャンネル: {ch}\n{'='*60}")
    d = yo.load_credentials_dict_for(ch)
    if not d:
        print("  ✗ 保存されたトークンなし（復号失敗の可能性: JWT_SECRET 不一致）")
        continue
    has_rt = bool(d.get("refresh_token"))
    expiry = d.get("expiry")
    print(f"  account_email      : {d.get('_account_email')}")
    print(f"  youtube_channel_id : {d.get('_youtube_channel_id')}")
    print(f"  refresh_token      : {'あり' if has_rt else '✗ なし'}")
    print(f"  client_id          : {(d.get('client_id') or '')[:20]}...")
    print(f"  expiry             : {datetime.fromtimestamp(expiry).isoformat() if expiry else 'なし'}")
    if not has_rt:
        print("  → refresh_token が無いのでリフレッシュ不可。再認証が必要。")
        continue

    creds = Credentials(
        token=d.get("token"),
        refresh_token=d.get("refresh_token"),
        token_uri=d.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=d.get("client_id"),
        client_secret=d.get("client_secret"),
        scopes=d.get("scopes", yo.SCOPES),
    )
    print("  リフレッシュ試行中...")
    try:
        creds.refresh(Request())
        # 成功 → 保存
        d["token"] = creds.token
        d["expiry"] = int(creds.expiry.timestamp()) if creds.expiry else None
        yo.save_credentials_for(
            ch,
            {k: v for k, v in d.items() if not k.startswith("_")},
            account_email=d.get("_account_email"),
            youtube_channel_id=d.get("_youtube_channel_id"),
            youtube_channel_name=d.get("_youtube_channel_name"),
        )
        print(f"  ✓ 成功! 新しい expiry: {datetime.fromtimestamp(d['expiry']).isoformat() if d['expiry'] else '?'}")
        print(f"  ✓ DBへ保存済み (新access_token: {creds.token[:20]}...)")
    except Exception as e:
        print(f"  ✗ リフレッシュ失敗: {type(e).__name__}: {e}")
