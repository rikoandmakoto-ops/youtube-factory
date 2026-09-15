#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指揮者 Phase 3 — 2026-09-15 コンフィグ適用

本日の判断（すべて実測ベース）:

  A) 投稿枠・タイトル型ルール・voice_style は **一切変更しない**
     09-14 に投稿枠と型ルールを全6ch で変更したばかりで、その後の公開分
     （09-13以降 25本）は analytics 上すべて views=0 = 未計測である。
     同一データで二度目の意思決定をしない。評価は n≧20/ch が揃う 09-21。

  B) テーマキュー在庫を 7 日以上へ補充（autopilot 有効な 4ch のみ）
     現状 daily-science 6.0日 / scp-lab 6.0日 / yokai-watch 6.7日 /
     company-facts 6.5日。型は 09-14 に確定した ch 別の最良型を踏襲する。

  C) 新規知見の反映 —「維持率は高いほど良い」を撤回し目標帯 40〜50% を明示
     公開08-01以降・views≥200・n=350 を維持率バンドで割ると登録/千は
       <30% 0.243 / 30-40% 0.426 / **40-50% 0.624** / 50-60% 0.414 /
       60-70% 0.451 / >=70% 0.294
     と 40-50% を頂点にした逆U字になる。ch 内対照でも 維持率<50% の方が
     登録/千が高いのが 6ch 中 5ch（比 1.18〜1.70、company-facts のみ 0.83）。
     平均尺は 30-70% の各バンドで 33〜39 秒とほぼ一定なので尺の交絡ではない。
     → retention_target_band を config に明記し、「維持率改善のための
       voice_style 微調整」は今後行わない（指揮者スキルの既定手順を上書き）。

バックアップ: data/channels/<ch>.json.bak_pdca_20260915_orch
※ data/channels_orchestrator/*.json は data/channels/*.json への symlink。
  realpath で重複排除して二重適用を防ぐ。
"""
import json
import os
import shutil
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = "20260915"
TODAY = "2026-09-15"

# ---------------------------------------------------------------- 補充テーマ
# 型は 09-14 に ch 内対照で確定したものを踏襲する:
#   daily-science = A型（疑問フレーム＋具体的な倍率/秒数・身体感覚）  0.59(n=30)
#   scp-lab       = A型（疑問フレーム＋数字）                        1.00(n=25)
#   yokai-watch   = B型（疑問フレームのみ・数字を入れない）          1.37(n=9)
#   company-facts = C型（数字のみ・疑問フレーム不使用）              0.66(n=31)
NEW_THEMES = {
    "daily-science": [  # A型: 毎日起きる身体感覚 + 倍率/秒数を1つ
        {"id": "orch20260915ds01",
         "title": "なぜ正座を崩した3秒後にしびれが来るのか",
         "angle": "身体感覚＋秒数。血流再開と神経の発火順序を3行目で言い切る"},
        {"id": "orch20260915ds02",
         "title": "なぜ walking 中の視界だけ揺れないのか",
         "angle": "身体感覚＋倍率。前庭動眼反射が毎秒何回補正しているかを3行目に置く"},
        {"id": "orch20260915ds03",
         "title": "なぜ冷たい水は喉で2倍うまく感じるのか",
         "angle": "身体感覚＋倍率。温度と口腔内受容の関係を3行目で渡し切る"},
    ],
    "scp-lab": [  # A型: 疑問フレーム + 具体数字
        {"id": "orch20260915sc01",
         "title": "なぜ収容室の照明は4時間で切り替わるのか",
         "angle": "疑問＋時間数字。手順そのものが異常性の輪郭になる構成"},
        {"id": "orch20260915sc02",
         "title": "SCP-記録に残る「19分の空白」は何だったのか",
         "angle": "疑問＋分数。監視記録の欠落を軸に、正体を3行目で提示"},
        {"id": "orch20260915sc03",
         "title": "なぜ観測者3名だけが同じ数字を書いたのか",
         "angle": "疑問＋人数。認識汚染系。3行目で『何が共有されたか』を言い切る"},
    ],
    "yokai-watch": [  # B型: 疑問フレームのみ・数字禁止・末尾疑問符も禁止
        {"id": "orch20260915yk01",
         "title": "小豆洗いの音がなぜ川辺だけで聞こえたのか",
         "angle": "疑問形・数字なし。水音の伝承と実在の環境音を重ねる"},
    ],
    "company-facts": [  # C型: 数字のみ・疑問フレーム不使用
        {"id": "orch20260915cf01",
         "title": "キーエンスの平均年収2182万円、その原資の中身",
         "angle": "数値提示型。粗利率と少人数体制を数字で並べる"},
        {"id": "orch20260915cf02",
         "title": "セブン-イレブンの日販68万円、24時間営業の採算",
         "angle": "数値提示型。日販とFC取り分を数字で分解する"},
    ],
}

# 目標維持率帯（本日の新規知見）
RETENTION_NOTE = (
    "【2026-09-15 指揮者・実測】維持率は高いほど良いという前提を撤回する。"
    "公開08-01以降・views≧200・n=350 を維持率バンド別に見ると登録/千は "
    "<30% 0.243 / 30-40% 0.426 / 40-50% 0.624 / 50-60% 0.414 / 60-70% 0.451 / "
    ">=70% 0.294 と 40-50% を頂点にした逆U字になる。ch内対照でも維持率<50%の方が"
    "登録/千が高いのが 6ch 中 5ch（daily-science 1.43 / scp-lab 1.20 / "
    "2ch-matome 1.18 / pokemon-lab 1.70 / yokai-watch 1.20、company-facts のみ 0.83）。"
    "平均尺は 30-70% の各バンドで 33〜39 秒とほぼ一定であり尺の交絡ではない。"
    "維持率 >=70% 帯は平均再生 1,982 と最も伸びるが登録/千は最下位 0.294 で、"
    "『最後まで見て満足し、登録する理由が残らない』構造が疑われる。"
    "→ 維持率は最大化目標ではなく 40〜50% を目標帯とし、"
    "『維持率改善のための voice_style 微調整』は今後行わない。"
    "登録の主説明変数は引き続き高評価率（四分位 Q4/Q1 3.90倍・5回再現）。"
)
RETENTION_BAND = {"min": 40, "max": 50, "metric": "avg_view_percentage",
                  "policy": "target_band_not_maximize", "updated_at": TODAY}

ACTIVE = ["daily-science", "scp-lab", "yokai-watch", "company-facts"]
ALL6 = ACTIVE + ["2ch-matome", "pokemon-lab"]

changes = {"date": TODAY, "channels": {}, "skipped": {}, "escalations": []}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    # symlink の実体に書く
    real = os.path.realpath(path)
    tmp = real + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, real)
    return real


def main():
    seen_real = set()
    for ch in ALL6:
        path = os.path.join(REPO, "data", "channels", f"{ch}.json")
        real = os.path.realpath(path)
        if real in seen_real:
            print(f"  skip (realpath 重複): {ch}")
            continue
        seen_real.add(real)

        d = load(real)
        ap = d.setdefault("autopilot", {})
        q = ap.setdefault("theme_queue", [])
        slots = len(ap.get("schedule", {}).get("times", [])) or 1
        before = len(q)

        bak = f"{real}.bak_pdca_{STAMP}_orch"
        if not os.path.exists(bak):
            shutil.copy2(real, bak)

        ch_change = {"queue_before": before, "slots": slots,
                     "stock_days_before": round(before / slots, 1)}

        # --- B) キュー補充（autopilot 有効な4chのみ） ---
        added = 0
        if ch in ACTIVE:
            existing_ids = {t.get("id") for t in q if isinstance(t, dict)}
            existing_titles = {(t.get("title") or "").strip()
                               for t in q if isinstance(t, dict)}
            for t in NEW_THEMES.get(ch, []):
                if t["id"] in existing_ids or t["title"].strip() in existing_titles:
                    continue
                q.append(t)
                added += 1
            ap["_queue_rationale_20260915_orch"] = (
                f"【{TODAY} 指揮者】在庫を 7 日以上へ補充（+{added}件）。"
                f"型は 09-14 に ch 内対照で確定した最良型を踏襲し、型ルール自体は変更しない"
                f"（09-13以降の公開分が未計測のため同一データでの二重判断を避ける）。"
                f"評価は n≧20/ch が揃う 2026-09-21。"
            )
        else:
            changes["skipped"][ch] = (
                "autopilot.enabled=false のため補充しない"
                + ("（OAuth も invalid_grant のまま。09-15 のログで継続を確認）"
                   if ch == "pokemon-lab" else "")
            )

        # --- C) 維持率の目標帯を明示（全6ch） ---
        opt = d.setdefault("optimization", {})
        opt["retention_target_band"] = dict(RETENTION_BAND)
        opt["_retention_note_20260915_orch"] = RETENTION_NOTE

        ch_change["queue_after"] = len(q)
        ch_change["queue_added"] = added
        ch_change["stock_days_after"] = round(len(q) / slots, 1)
        ch_change["retention_target_band"] = "40-50%"
        ch_change["schedule_changed"] = False
        ch_change["title_rules_changed"] = False
        ch_change["voice_style_changed"] = False

        # pdca_log（重複防止）
        log = d.setdefault("pdca_log", [])
        marker = f"orch_{STAMP}"
        if not any(isinstance(e, dict) and e.get("marker") == marker for e in log):
            log.append({
                "marker": marker,
                "date": TODAY,
                "by": "orchestrator",
                "summary": (
                    f"キュー +{added}（在庫 {ch_change['stock_days_before']}→"
                    f"{ch_change['stock_days_after']}日）／維持率の目標帯を 40-50% に明示。"
                    f"投稿枠・型ルール・voice_style は 09-14 変更分の評価待ちのため据え置き。"
                ),
            })

        save(real, d)
        changes["channels"][ch] = ch_change
        print(f"  {ch:14} queue {before}->{len(q)} (+{added}) "
              f"在庫 {ch_change['stock_days_before']}->{ch_change['stock_days_after']}日")

    changes["escalations"] = [
        {"pri": 1, "item": "カスタムサムネイル 403（要・電話番号確認）",
         "detail": "09-15 のログでも scp-lab / company-facts / yokai-watch の全公開で "
                   "403 forbidden が継続。成功しているのは daily-science のみ。"
                   "https://www.youtube.com/verify を該当 9ch で通す。人手のみ。",
         "owner": "human"},
        {"pri": 2, "item": "Anthropic API キーが 401（新規）",
         "detail": "backend ログに claude_client call failed (thumbnail_brief): "
                   "Error code: 401 API key is invalid。series_engine も "
                   "『Claude 未応答のため続編候補を生成しません』で停止している。"
                   "サムネ指示文と続編候補が両方生成されていない。人手のみ。",
         "owner": "human"},
        {"pri": 3, "item": "OAuth 未再認可の 6ch",
         "detail": "pokemon-lab / clip-lab / clip-kaneko / clip-fukada / clip-animal / "
                   "fake-paper / akashic-librarian が invalid_grant のまま。"
                   "09-13 に再認可した 5ch（daily-science / scp-lab / yokai-watch / "
                   "company-facts / socio-rx）は 09-15 時点で正常。"
                   "同意画面を『本番』公開 → そのあと再認可の順で。",
         "owner": "human"},
        {"pri": 4, "item": "analytics バックフィル未実行",
         "detail": "09-13 以降に公開した 25 本が views=0 のまま記録されている。"
                   "OAuth 復旧後のバックフィルが走っていないため、本日の評価対象から除外した。",
         "owner": "backend"},
    ]

    out = os.path.join(REPO, "reports", f"orch_config_changes_{STAMP}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)
    print(f"\n変更サマリ: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
