#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026-09-02 根拠テキストの訂正。

初回適用時に引用した維持率の数値は published_at>=2026-08-20・再生200超 の窓で算出しており、
レポート本体（published_at>=2026-08-10・再生150超・n=138）と窓が食い違っていた。
また「尺による交絡は否定される」という記述は、統一コホートで再計算した結果、誤りだった。

統一コホート（published_at>=2026-08-10, views>150, n=138）での再計算:
  ch              speed   n   AVP%   視聴s  推定尺s   転換%
  daily-science    1.3   25   42.3   15.0    36.8   0.047
  scp-lab          1.3   23   40.3   14.8    39.8   0.066
  2ch-matome      1.35   29   52.4   15.6    30.7   0.016
  pokemon-lab      1.3   21   43.1   16.4    41.6   0.024
  yokai-watch      1.3   20   46.6   17.3    37.6   0.022
  company-facts    1.2   20   58.5   33.9    55.5   0.076

訂正点:
  (a) 2ch-matome は speed 1.35（最速）でありながら AVP 52.4% と2位。
      よって「速度が低いほど維持率が高い」は単純には成立しない。
      2ch-matome の高AVPは推定尺30.7秒（最短）による機械的なもので、
      絶対視聴秒は15.6秒と他chと同水準、登録転換は0.016%で最下位。
      → AVP（率）は尺に交絡する。絶対視聴秒のほうが頑健な指標。
  (b) company-facts は推定尺55.5秒（最長）を AVP 58.5% で維持し、
      絶対視聴秒33.9秒＝他ch（14.8-17.3秒）の約2倍。登録転換も0.076%で最良。
      速度が単独要因である証拠はなく、尺との交絡も残る。
      ただし speed は設定上の唯一の差分であり、対照群を残した単一変数の試行としては妥当。
  (c) 絶対視聴秒 × 登録転換（統一コホート）:
      0-14秒 0.031% / 14-17秒 0.038% / 17-22秒 0.035% / 22秒以上 0.061%
      → 22秒以上視聴されると登録転換が約2倍。これが speed 変更の実質的な狙い。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORCH = os.path.join(ROOT, "data", "channels_orchestrator")
CHANNELS = ["daily-science", "scp-lab", "2ch-matome",
            "pokemon-lab", "yokai-watch", "company-facts"]

CORRECTED_EVIDENCE = {
    "window": "published_at>=2026-08-10, views>150, n=138（レポートと統一）",
    "avp_pct_by_channel": {
        "daily-science": 42.3, "scp-lab": 40.3, "2ch-matome": 52.4,
        "pokemon-lab": 43.1, "yokai-watch": 46.6, "company-facts": 58.5,
    },
    "watch_seconds_by_channel": {
        "daily-science": 15.0, "scp-lab": 14.8, "2ch-matome": 15.6,
        "pokemon-lab": 16.4, "yokai-watch": 17.3, "company-facts": 33.9,
    },
    "est_length_sec_by_channel": {
        "daily-science": 36.8, "scp-lab": 39.8, "2ch-matome": 30.7,
        "pokemon-lab": 41.6, "yokai-watch": 37.6, "company-facts": 55.5,
    },
    "sub_conversion_pct": {
        "company-facts": 0.076, "scp-lab": 0.066, "daily-science": 0.047,
        "pokemon-lab": 0.024, "yokai-watch": 0.022, "2ch-matome": 0.016,
    },
    "watch_seconds_vs_conversion": {
        "0-14s": 0.031, "14-17s": 0.038, "17-22s": 0.035, "22s+": 0.061,
    },
    "hypothesis": (
        "絶対視聴秒が登録転換の実質的なドライバ（22秒以上で約2倍）。"
        "company-facts のみ視聴33.9秒＝他chの約2倍で、登録転換も最良。"
        "speed=1.2 は company-facts の設定上の唯一の差分であるため、"
        "他5chの speed を下げて単一変数として検証する。"
    ),
    "caveats": [
        "2ch-matome は speed 1.35（最速）で AVP 52.4%（2位）。"
        "『速度が低いほど維持率が高い』は単純には成立しない。",
        "2ch-matome の高AVPは推定尺30.7秒（最短）による機械的なもの。"
        "絶対視聴秒15.6秒・登録転換0.016%（最下位）であり、AVPは尺に交絡する。",
        "company-facts は尺55.5秒（最長）でもあり、speed 単独の効果とは分離できていない。",
        "したがって本変更は確定的な改善ではなく仮説検証である。",
    ],
    "falsification": (
        "変更した5chの絶対視聴秒が3日以内に改善しない場合、速度は主因ではないと判断し "
        "speed を元の値（daily-science/scp-lab/pokemon-lab/yokai-watch=1.3, 2ch-matome=1.35）へ戻す。"
    ),
    "control": "company-facts は speed=1.2 のまま据え置き（対照群）",
}

RETENTION_RULE_FIX = {
    "scp-lab": "**答えの遅延（2026-09-02追加・維持率対策）**: "
               "1行目のフックで提示した『何が起きたのか』の核心は、5行目まで明かしてはならない。"
               "3行目・4行目では被害の規模と状況だけを積み上げ、"
               "『では何がそれをやったのか』を伏せたまま進める。"
               "根拠: 統一コホート(n=138)で scp-lab は平均維持率40.3%・平均視聴14.8秒と"
               "いずれも全ch最下位。3行目で答えを出し切る構成が原因と判断。",
    "pokemon-lab": "**答えの遅延（2026-09-02追加・維持率対策）**: "
                   "1行目で提示した『どっちが勝つ』『なぜそうなる』の結論は5行目まで出さない。"
                   "3行目・4行目は数値と条件の提示に留め、勝敗や理由を断定しない。"
                   "根拠: 統一コホート(n=138)で pokemon-lab は登録転換0.024%と下位。"
                   "推定尺41.6秒に対し視聴16.4秒＝39%地点で離脱している。",
    "daily-science": "**答えの遅延（2026-09-02追加・維持率対策）**: "
                     "1行目の疑問に対する『正体』の一語は5行目まで温存する。"
                     "3行目は現象の規模（数字）だけを出し、機序の名前を先に言わない。"
                     "根拠: 推定尺36.8秒に対し平均視聴15.0秒＝41%地点で離脱。",
    "yokai-watch": "**答えの遅延（2026-09-02追加・維持率対策）**: "
                   "1行目で匂わせた原典の恐怖の核心は5行目まで明かさない。"
                   "3行目は出典と年代の提示に留める。"
                   "根拠: 推定尺37.6秒に対し平均視聴17.3秒＝46%地点で離脱。",
}


def main():
    for ch in CHANNELS:
        real = os.path.realpath(os.path.join(ORCH, f"{ch}.json"))
        with open(real, encoding="utf-8") as f:
            d = json.load(f)

        # pdca_log の 2026-09-02 エントリの evidence を訂正
        fixed = False
        for entry in d.get("pdca_log", []):
            if entry.get("date") == "2026-09-02":
                entry["evidence"] = CORRECTED_EVIDENCE
                entry["evidence_corrected_at"] = "2026-09-02 検証フェーズ"
                fixed = True

        # structure の根拠文を差し替え
        if ch in RETENTION_RULE_FIX:
            sf = d.setdefault("short_format", {})
            struct = sf.get("structure", [])
            for i, s in enumerate(struct):
                if "答えの遅延" in s:
                    struct[i] = RETENTION_RULE_FIX[ch]
                    break

        tmp = real + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        json.load(open(tmp, encoding="utf-8"))
        os.replace(tmp, real)
        print(f"{ch:<15} evidence訂正={fixed} structure訂正={ch in RETENTION_RULE_FIX}")


if __name__ == "__main__":
    main()
