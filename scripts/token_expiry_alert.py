#!/usr/bin/env python3
"""OAuth トークンの残り寿命を見て、危ういときだけメールで知らせる。

PDCA レポートの中にも同じ警告は出ているが、245KB のログと長いレポートに埋もれて
2026-09-19 の「6ch が 0.5 日で一斉失効」を誰も拾えなかった。届く場所に出すのが目的。

実行: /usr/bin/python3 scripts/token_expiry_alert.py [--warn-days 3] [--dry-run]
メールは aiseki の Resend キーを流用する（youtube-factory 側に通知経路がないため）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AISEKI_ENV = ROOT.parent / "aiseki" / ".env"
TO = "theoffzaki@gmail.com"
STATE = ROOT / "data" / "reports" / ".token_alert_state.json"


def read_env(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def check(warn_days: float) -> tuple[list[str], list[str], str]:
    """check_youtube_tokens.py を動かして (警告ch, 失効ch, 生出力) を返す。"""
    proc = subprocess.run(
        [sys.executable, "backend/check_youtube_tokens.py", "--warn-days", str(warn_days)],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    out = proc.stdout
    warn: list[str] = []
    dead: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ch, state = parts[0], parts[1]
        if state == "警告":
            warn.append(line.strip())
        elif state == "失効":
            dead.append(ch)
    return warn, dead, out


def send_mail(subject: str, body: str) -> bool:
    """Resend へ送る。Python の urllib だと Cloudflare に 403(1010) で弾かれるので node を使う。"""
    key = read_env(AISEKI_ENV, "RESEND_API_KEY")
    if not key:
        print("RESEND_API_KEY が読めないためメールは送れない", file=sys.stderr)
        return False
    payload = json.dumps({
        "from": "相席マッチ 運営 <noreply@aisekimatch.com>",
        "to": [TO], "subject": subject, "text": body,
    })
    script = (
        "const p=JSON.parse(process.argv[1]);"
        "fetch('https://api.resend.com/emails',{method:'POST',"
        "headers:{Authorization:'Bearer '+process.argv[2],'Content-Type':'application/json'},"
        "body:JSON.stringify(p)})"
        ".then(async r=>{if(!r.ok){console.error(r.status,(await r.text()).slice(0,200));process.exit(1);}})"
        ".catch(e=>{console.error(e.message);process.exit(1);});"
    )
    for node in ("/opt/homebrew/bin/node", "node"):
        try:
            proc = subprocess.run([node, "-e", script, payload, key],
                                  capture_output=True, text=True, timeout=60)
            if proc.returncode == 0:
                return True
            print(f"メール送信に失敗: {proc.stderr.strip()[:200]}", file=sys.stderr)
            return False
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"メール送信に失敗: {exc}", file=sys.stderr)
            return False
    print("node が見つからずメールを送れない", file=sys.stderr)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn-days", type=float, default=3.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    warn, dead, raw = check(args.warn_days)
    if not warn:
        print(f"OAuth: 残り {args.warn_days} 日を切っているチャンネルはない（失効済み {len(dead)}ch）")
        return 0

    subject = f"【要対応】YouTube OAuth {len(warn)}ch が {args.warn_days} 日以内に失効します"
    body = (
        f"稼働中チャンネルのうち {len(warn)} 件が、まもなく認可切れになります。\n"
        "切れると投稿が止まります。ダッシュボードから再接続してください。\n\n"
        "  https://youtube-factory-eight.vercel.app\n"
        "  → チャンネル設定 → 対象ch →「YouTube連携」→「再接続」\n\n"
        "対象:\n" + "\n".join(f"  {w}" for w in warn) + "\n\n"
        f"失効済み（投稿・計測とも停止中）: {', '.join(dead) if dead else 'なし'}\n\n"
        "--- 生出力 ---\n" + raw
    )

    if args.dry_run:
        print(subject); print(); print(body)
        return 0

    ok = send_mail(subject, body)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"warn": warn, "dead": dead, "mailed": ok}, ensure_ascii=False, indent=1))
    print(("通知した: " if ok else "通知に失敗: ") + subject)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
