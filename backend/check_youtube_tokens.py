#!/usr/bin/env python3
"""全チャンネルの YouTube リフレッシュトークン健康診断

    python3 backend/check_youtube_tokens.py            # 一覧表示
    python3 backend/check_youtube_tokens.py --warn-days 2   # 猶予2日未満だけ非0終了

なぜ必要か（2026-08-24）:
  GCP の OAuth 同意画面が「テスト中」のままだと、Google はリフレッシュトークンに
  7日の寿命を付ける（token エンドポイントの応答に `refresh_token_expires_in` が
  乗る＝テスト中の証拠）。期限が来ると invalid_grant で全チャンネルが順に沈黙し、
  autopilot は「YouTube 未連携」とだけ言って投稿をスキップする。
  実際 08-24 に 7チャンネルが同時に死んで、ショート2本が未投稿になった。

  恒久対策は同意画面を「本番」に公開すること（そうすれば無期限になる）。
  このスクリプトはそれまでの見張り役で、失効前に気づくためのもの。
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# Fernet 鍵は JWT_SECRET 由来。.env を読まないとトークンを復号できない。
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from pipeline import youtube_oauth as yt_oauth  # noqa: E402


def _probe(d):
    """リフレッシュトークンを実際に使ってみて、生死と残り寿命を返す。

    google-auth 経由だと理由が例外に埋もれるので、token エンドポイントを直接叩く。
    """
    data = urllib.parse.urlencode(
        {
            "client_id": d["client_id"],
            "client_secret": d["client_secret"],
            "refresh_token": d["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(
        d.get("token_uri") or "https://oauth2.googleapis.com/token", data=data
    )
    try:
        body = json.loads(urllib.request.urlopen(req, timeout=20).read())
        # テスト中クライアントだけが返すフィールド（＝7日で失効する印）
        return True, body.get("refresh_token_expires_in"), None
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode() or "{}")
        except Exception:
            err = {}
        return False, None, err.get("error_description") or err.get("error") or str(e.code)
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"


def collect(warn_days: float = 2.0):
    """全チャンネルを実測して 1 行 1 チャンネルの dict にして返す。

    日次 PDCA（`run_daily_pdca.py`）からも呼ぶので、表示と分離してある。
    dict のキー: channel_id / status(ok|warn|dead|unlinked) / days(None可) / detail
    """
    import datetime as _dt

    out = []
    for row in yt_oauth.list_connected_channels():
        ch = row.get("channel_id") or row.get("id")
        d = yt_oauth.load_credentials_dict_for(ch)
        if not d or not d.get("refresh_token"):
            out.append({"channel_id": ch, "status": "unlinked", "days": None,
                        "detail": "リフレッシュトークン未登録", "granted": None})
            continue
        # 認可時点の刻印（2026-09-02 以降に認可したトークンにだけ入る）。
        # 「同意画面を本番にしたのに直らない」の切り分けは、いま生きている
        # トークンの寿命ではなく、*認可した時刻* の刻印を見ないと誤る。
        g = d.get("refresh_token_granted_at")
        granted = (
            _dt.datetime.fromtimestamp(g).strftime("%m-%d %H:%M") if g else None
        )
        ok, ttl, err = _probe(d)
        if not ok:
            out.append({"channel_id": ch, "status": "dead", "days": None,
                        "detail": err, "granted": granted})
            continue
        if ttl is None:
            # `refresh_token_expires_in` が返らない＝無期限で発行されたトークン。
            out.append({"channel_id": ch, "status": "ok", "days": None,
                        "detail": "無期限", "granted": granted})
            continue
        days = ttl / 86400
        out.append({
            "channel_id": ch,
            "status": "ok" if days >= warn_days else "warn",
            "days": days,
            "detail": f"{days:.2f}日",
            "granted": granted,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--warn-days",
        type=float,
        default=2.0,
        help="残りがこれ未満なら警告扱い（既定 2 日）",
    )
    args = ap.parse_args()

    rows = collect(args.warn_days)
    if not rows:
        print("連携済みチャンネルがありません")
        return 1

    dead, warn = [], []
    stamped = []   # 7日の刻印が押されたまま生きているもの
    label = {"ok": "OK", "warn": "警告", "dead": "失効", "unlinked": "未連携"}
    print(f"{'channel':20s} {'状態':6s} {'残り寿命':12s} 認可日時")
    print("-" * 66)
    for r in rows:
        print(f"{r['channel_id']:20s} {label[r['status']]:6s} "
              f"{r['detail']:12s} {r.get('granted') or '—'}")
        if r["status"] in ("dead", "unlinked"):
            dead.append(r["channel_id"])
        elif r["status"] == "warn":
            warn.append((r["channel_id"], r["days"]))
        if r["status"] in ("ok", "warn") and r["days"] is not None:
            stamped.append(r["channel_id"])

    print()
    if dead:
        print(f"❌ 要再認可: {', '.join(dead)}")
        print("   ダッシュボードのチャンネル設定 →「YouTube 連携」からやり直す")
    if warn:
        print("⚠️ まもなく失効: " + ", ".join(f"{c}({d:.1f}日)" for c, d in warn))
    if stamped:
        # 「同意画面は本番にした（はず）なのに直らない」を切り分けるための注記。
        # 寿命の刻印はトークン発行時に押される。公開前に取ったトークンは公開後も
        # 7日で死ぬので、「残り寿命が出ている＝いまも本番になっていない」とは
        # 断定できない。判定できるのは *再認可した直後* のログだけ。
        print()
        print("ℹ️ 7日の刻印が付いたまま生きているトークン: " + ", ".join(stamped))
        print("   刻印は「認可した瞬間」の同意画面の状態で決まり、あとから本番公開しても")
        print("   既存トークンには遡って効かない。再認可して初めて無期限になる。")
        print("   再認可時のログに ♾️ が出れば本番公開済み、⏳ が出ればまだテスト扱い。")
    if dead or warn:
        print()
        print("恒久対策: GCP の OAuth 同意画面を「テスト中」→「本番」に公開する")
        print("  https://console.cloud.google.com/auth/audience (project 844705815004)")
        return 2
    print("✅ 全チャンネル正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
