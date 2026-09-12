#!/usr/bin/env python3
"""指揮者 2026-09-12 の適用スクリプト。

本日の analytics は 09-08 が最終スナップショット（5日連続で新規実績ゼロ）。
`.auto-memory/INDEX.md` の鉄則「新規の再生実績が無い日は config を変更しない」に従い、
**実績に基づく施策変更は一切行わない**。

本日行うのは「config と キュー の内部矛盾」の解消のみ。これは実績の再解釈では
ないので二重適用にならない。

1. 切り抜き3ch（clip-lab / clip-fukada / clip-kaneko）に `title_rules.hard_constraints`
   を新規付与する。この3chは `is_enforced()` が False で**検査が丸ごとスキップ**され、
   禁止したはずの負け型（「秘密」「99%が知らない」「連番プレフィックス」「絵文字」）が
   素通りしていた。
   引用を壊す制約は入れない:
     - `min_effective_chars` は入れない（タイトルが発言の引用のため。09-11 の判断を踏襲）
     - `require_any_of` は入れない（引用に語を足すことになる）
   入れるのは禁止系のみ。

2. theme_queue の「自chのゲートに落ちる候補」を機械修復する。
   とくに company-facts は12件全部が自ch の `banned_words` にある絵文字を
   先頭に付けており、100%自滅していた。

3. 修復は `title_constraints.repair()` に一本化し、**違反数が減った場合のみ採用**する。
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from pipeline import title_constraints as tc  # noqa: E402

SUFFIX = ".bak_pdca_20260912_orch"

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️]")

# 切り抜き3ch へ入れる禁止系ゲート（引用を壊さないものだけ）
CLIP_HARD_CONSTRAINTS = {
    "max_chars": 48,
    "banned_words": ["秘密"],
    "forbid_patterns": [
        {
            "pattern": "(?:9\\s*9|９\\s*９)\\s*[%％]",
            "label": "99%が知らない型の希少性ワード",
        },
        {"pattern": "#\\d+[：:]", "label": "連番プレフィックス"},
        {
            "pattern": "[\\U0001F300-\\U0001FAFF\\u2600-\\u27BF\\u2B00-\\u2BFF\\uFE0F]",
            "label": "絵文字",
        },
    ],
    "_note_20260912": (
        "【2026-09-12 新規付与】この3chは hard_constraints 未設定のため "
        "title_constraints.is_enforced() が False になり、検査が丸ごとスキップされていた。"
        "禁止したはずの負け型が素通りする状態。"
        "min_effective_chars と require_any_of は入れない — タイトルが発言の引用なので、"
        "文字数下限や語の必須化は誤引用を作りうる（09-11 の判断を踏襲）。"
        "禁止系だけなら引用を壊さない。"
    ),
}

CLIP_CHANNELS = ["clip-lab", "clip-fukada", "clip-kaneko"]
ALL_CHANNELS = [
    "scp-lab", "daily-science", "pokemon-lab", "yokai-watch", "2ch-matome",
    "company-facts", "clip-lab", "clip-fukada", "clip-kaneko", "fake-paper",
    "akashic-librarian",
]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    """バックアップを取ってから tmp+replace で書く（部分書き込みを残さない）。"""
    bak = path.with_name(path.name + SUFFIX)
    if not bak.exists():
        shutil.copy2(path, bak)
    tmp = path.with_name(path.name + ".tmp_20260912")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def apply_clip_gates() -> list[str]:
    log = []
    for ch in CLIP_CHANNELS:
        p = ROOT / "data" / "channels" / f"{ch}.json"
        cfg = load(p)
        tr = cfg.get("title_rules") or {}
        if tr.get("hard_constraints"):
            log.append(f"{ch}: 既に hard_constraints あり — スキップ")
            continue
        tr["enforced_by_backend"] = True
        tr["hard_constraints"] = json.loads(json.dumps(CLIP_HARD_CONSTRAINTS))
        cfg["title_rules"] = tr
        save(p, cfg)
        # 書いた直後に backend と同じ経路で読み直して、本当に効くか確認する
        again = load(p)
        assert tc.is_enforced(again), f"{ch}: is_enforced が False のまま"
        log.append(f"{ch}: hard_constraints を新規付与（is_enforced=True を確認）")
    return log


def queue_path(ch: str) -> Path:
    return ROOT / "data" / "channels" / ch / "theme_queue.json"


def n_violations(title: str, cfg) -> int:
    return len(tc.check(title, cfg)["violations"])


def clean_queues() -> tuple[list[str], list[dict]]:
    log, changes = [], []
    for ch in ALL_CHANNELS:
        qp = queue_path(ch)
        if not qp.exists():
            continue
        cfg = load(ROOT / "data" / "channels" / f"{ch}.json")
        q = load(qp)
        items = q.get("items") if isinstance(q, dict) else q
        if not isinstance(items, list):
            continue
        fixed = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            if it.get("status") in ("done", "published", "used"):
                continue
            orig = it.get("title")
            if not orig:
                continue
            before = n_violations(orig, cfg)
            if before == 0:
                continue

            # 禁止絵文字を落とすだけ。これは**意味を一切変えない**唯一の安全な修復。
            #
            # 【2026-09-12 実測】ここで `tc.repair()` も併用したところ、57件中ほぼ全てで
            # 日本語が壊れた。repair は max_chars 違反を「末尾切り落とし」で、
            # forbid_digits 違反を「数字の削除」で通そうとするため:
            #   「…愛らしい外見が起こした財団史上最恐の収容違反」
            #     → 「…愛らしい外見が起こしの真相」（文法破壊）
            #   「…が[DATA EXPUNGED]した恐ろしい記録」→「…が[DATA EXP」（トークン途中切り）
            #   「シェイミの2形態を分ける気温5度の正体」→「シェイミの2形態を分ける気温正体」
            #     （事実の欠落＋文法破壊）
            #   「ぬらりひょんの正体、江戸期4図で姿が変わった」→「…江戸期図で…」（事実の欠落）
            # 違反数は確かに減るが、**公開できないタイトルが「合格」として通る**ので
            # 検査より悪い。長さ・数字の違反は LLM 再生成に回すのが正しい。
            best = EMOJI_RE.sub("", orig).strip()

            after = n_violations(best, cfg)
            if best != orig and after < before:
                it["title"] = best
                it.setdefault("_title_before_20260912", orig)
                fixed += 1
                changes.append(
                    {
                        "channel": ch,
                        "before": orig,
                        "after": best,
                        "violations_before": before,
                        "violations_after": after,
                        "passes_now": after == 0,
                    }
                )
        if fixed:
            save(qp, q)
            log.append(f"{ch}: キュー {fixed} 件を修復")
    return log, changes


def report_conformance() -> list[dict]:
    out = []
    for ch in ALL_CHANNELS:
        cfg = load(ROOT / "data" / "channels" / f"{ch}.json")
        qp = queue_path(ch)
        titles = []
        if qp.exists():
            q = load(qp)
            items = q.get("items") if isinstance(q, dict) else q
            for it in items or []:
                if isinstance(it, dict) and it.get("status") not in (
                    "done", "published", "used",
                ):
                    if it.get("title"):
                        titles.append(it["title"])
        ok = sum(1 for t in titles if tc.check(t, cfg)["ok"])
        out.append(
            {
                "channel": ch,
                "enforced": tc.is_enforced(cfg),
                "queue_pending": len(titles),
                "queue_pass": ok,
                "queue_pass_rate": round(ok / len(titles) * 100, 1) if titles else None,
            }
        )
    return out


def main() -> None:
    print("=== 1. 切り抜き3ch へゲート付与 ===")
    for line in apply_clip_gates():
        print("  ", line)

    print("\n=== 2. theme_queue の自滅候補を修復 ===")
    log, changes = clean_queues()
    for line in log:
        print("  ", line)
    print(f"   合計 {len(changes)} 件を修復（うち完全合格 "
          f"{sum(1 for c in changes if c['passes_now'])} 件）")

    print("\n=== 3. 適用後のキュー適合率 ===")
    conf = report_conformance()
    for r in conf:
        print(f"   {r['channel']:20s} enforced={str(r['enforced']):5s} "
              f"{r['queue_pass']}/{r['queue_pending']} "
              f"({r['queue_pass_rate']}%)")

    outp = ROOT / "reports" / "orch_apply_20260912_result.json"
    outp.write_text(
        json.dumps(
            {"changes": changes, "conformance": conf}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(f"\n結果を書き出し: {outp}")


if __name__ == "__main__":
    main()
