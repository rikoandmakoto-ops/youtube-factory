#!/usr/bin/env python3
"""data/channels/ と data/channels_orchestrator/ の二重管理を解消する。

【結論: master of record は data/channels/】
    リポジトリ全体を grep した結果、本番コードで
    data/channels_orchestrator/ を読むものは1つも無い
    （backend/ 配下は全て data/channels/ を見ている。ChannelManager /
     post_upload / auto_comment / playlist_manager / shorts_length_guard /
     youtube_analytics / run_daily_pdca ほか）。書いているのは
    scripts/ 配下の日付付き PDCA 反映スクリプトだけで、それらが
    「両方に書く」形になっていたために、片側にしか当たらない事故が
    起きていた（実例: 2026-08-31 の 2ch-matome theme_blacklist は
    orchestrator 側にしか反映されていなかった）。

    別リポジトリの ai-orchestrator も channels_orchestrator を参照していない。

【解決方法】
    data/channels_orchestrator/<id>.json を data/channels/<id>.json への
    相対 symlink に置き換える。こうすると

      - どちらのパスから読んでも同じ内容になる（乖離が起こりえない）
      - 古いスクリプトが orchestrator 側に書いても master に届く
      - 今後は data/channels/ だけを更新すればよい

    *.bak_* は履歴なのでそのまま残す。

使い方:
    python3 scripts/unify_channel_configs.py --report   # 差分だけ出す
    python3 scripts/unify_channel_configs.py --apply    # symlink 化する
    python3 scripts/unify_channel_configs.py --check    # CI/確認用（差分があれば exit 1）
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "channels"
MIRROR = ROOT / "data" / "channels_orchestrator"
ARCHIVE = ROOT / "data" / "channels_orchestrator_pre_symlink_20260901"


def live_jsons(d: Path) -> Iterator[Path]:
    """*.bak_* を除いた稼働中の JSON。"""
    for p in sorted(d.glob("*.json")):
        if ".bak_" in p.name:
            continue
        yield p


def flatten(obj: Any, prefix: str = "") -> Iterator[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        yield prefix, json.dumps(obj, ensure_ascii=False)
    else:
        yield prefix, obj


def diff_one(master: Path, mirror: Path) -> Dict[str, Tuple[Any, Any]]:
    a = dict(flatten(json.loads(master.read_text(encoding="utf-8"))))
    b = dict(flatten(json.loads(mirror.read_text(encoding="utf-8"))))
    return {
        k: (a.get(k), b.get(k))
        for k in sorted(set(a) | set(b))
        if a.get(k) != b.get(k)
    }


def report() -> int:
    """乖離を人が読める形で出す。戻り値は乖離のあるチャンネル数。"""
    diverged = 0
    for mirror in live_jsons(MIRROR):
        master = MASTER / mirror.name
        if mirror.is_symlink():
            target = os.readlink(mirror)
            print(f"✅ {mirror.name}: symlink → {target}")
            continue
        if not master.exists():
            print(f"⚠️  {mirror.name}: master 側に存在しない（orchestrator 専用）")
            diverged += 1
            continue
        d = diff_one(master, mirror)
        if not d:
            print(f"✅ {mirror.name}: 同一")
            continue
        diverged += 1
        print(f"❌ {mirror.name}: 差分 {len(d)} キー")
        for k, (av, bv) in d.items():
            print(f"     {k}")
            print(f"       channels     : {str(av)[:110]}")
            print(f"       orchestrator : {str(bv)[:110]}")
    only_master = {p.name for p in live_jsons(MASTER)} - {
        p.name for p in live_jsons(MIRROR)
    }
    if only_master:
        print(f"\nℹ️ master にのみ存在: {sorted(only_master)}")
    return diverged


def apply() -> None:
    """orchestrator 側の実ファイルを master への相対 symlink に置き換える。"""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    converted = 0
    for mirror in live_jsons(MIRROR):
        if mirror.is_symlink():
            continue
        master = MASTER / mirror.name
        if not master.exists():
            print(f"⚠️  {mirror.name}: master に対応が無いので触らない")
            continue
        # 消す前に退避しておく（orchestrator 側にしか無い値の追跡用）
        shutil.copy2(mirror, ARCHIVE / mirror.name)
        mirror.unlink()
        mirror.symlink_to(Path("..") / "channels" / mirror.name)
        converted += 1
        print(f"🔗 {mirror.name} → ../channels/{mirror.name}")

    # master にしか無いチャンネル（fake-paper 等、orchestrator が作られた後に
    # 増えたもの）も symlink を張って、2つのディレクトリの一覧を一致させる。
    existing = {p.name for p in live_jsons(MIRROR)}
    for master in live_jsons(MASTER):
        if master.name in existing:
            continue
        link = MIRROR / master.name
        link.symlink_to(Path("..") / "channels" / master.name)
        converted += 1
        print(f"🔗 {master.name} → ../channels/{master.name} (新規)")

    print(f"\n{converted} 件を symlink 化。退避先: {ARCHIVE.relative_to(ROOT)}")


def main() -> None:
    if "--apply" in sys.argv:
        apply()
        print("\n--- 反映後の確認 ---")
        report()
        return
    diverged = report()
    if "--check" in sys.argv and diverged:
        print(f"\n❌ {diverged} チャンネルで乖離が残っている")
        sys.exit(1)


if __name__ == "__main__":
    main()
