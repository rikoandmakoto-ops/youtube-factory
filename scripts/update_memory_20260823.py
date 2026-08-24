#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDCAメモリ更新 2026-08-23（Phase 6）"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEM = ROOT / "data" / "pdca-memory"
DATE = "2026-08-23"

FINDINGS = [
    ("cohort-confounding-flipped-conclusion",
     "【方法論・最重要】集計コホートの不一致が結論を反転させることが実証された。scp-lab の全角ダッシュ「—」は"
     "全期間集計だと CTR 0.72倍（95%CI 0.62-0.85）で有意に有害に見えるが、登録者指標と同じ直近60日コホートに"
     "揃えると 0.97倍（95%CI 0.81-1.16）で差が消える。差の実体は61日以上前の動画による期間交絡だった。"
     "08-23朝の指揮者はこれに気づかず一度『使用禁止』をコンフィグに書き込み、自己検証で撤回した。"
     "今後タイトル効果を測るときは必ず (1)コホートを明示して揃える (2)再生・CTR・1本あたり登録者の3指標を併記 "
     "(3)95%CIが1をまたぐ場合は『必須』にしない、の3点を満たすこと"),
    ("title-rules-were-never-applied",
     "【根本原因・重要】voice_style.style_rules に書いたタイトル規則はテーマ生成に一切反映されない。"
     "backend/pipeline/auto_scenario/generator.py の suggest_themes()（2755-2972行）が channel から参照するのは "
     "name / concept / style / content_policy.tone と theme_priority だけで、voice_style を読んでいない。"
     "そのため 08-22 朝に style_rules へ書いた全てのタイトル施策は無効で、scp-lab の theme_queue 23件は"
     "禁止したはずのダッシュ形式のまま残っていた。タイトル書式を変えたいときは "
     "theme_priority.title_style / good_examples を必ず編集すること（08-23 に4chとも移設済み）"),
    ("subs-per-video-is-the-decision-metric",
     "至上目標が登録者である以上、判断指標は『1本あたり登録者』に統一すべき。これは再生数を経た最終成果であり、"
     "CTRや再生数と符号が食い違ったときは常にこちらを採る。08-22朝〜08-23で、再生数だけを見て決めた施策が"
     "5件連続で覆っている（yokai『怖』優先、yokai『なぜ』禁止、daily『なぜ』抑制、daily『99%が知らない』禁止、"
     "scp ダッシュ維持）。ただしCTRは中間指標として併記し、登録者が正でCTRが負の場合はサムネ側で補う"),
    ("ds-99-percent-ban-was-wrong",
     "daily-science の「99%が知らない」禁止は誤りだった。1本あたり登録者 0.417 vs 0.265（1.57倍）、"
     "登録/1000再生 0.47 vs 0.29、CTR 1.53% vs 1.28% と3指標すべてで正。"
     "禁止の根拠は再生数0.94倍のみだった。08-23に解除（95%CI 0.76-3.26 と非有意のため必須化はせず）。"
     "夜間ランの title-numbers-lower-views-higher-subs と同じ結論"),
    ("yokai-ip-confirmed-2nd-time",
     "yokai-watch の『妖怪ウォッチ作品ネタ』優位を08-23の独立分析でも再現。作品名・キャラ名を含む10本は"
     "1本あたり登録者 0.700 vs 伝承のみ0.286（2.45倍）、登録/1000再生 0.55 vs 0.19、CTR 1.96% vs 1.47%。"
     "伝承のみは平均再生では上回る（1543 vs 1281）。2日連続で独立に同じ結論が出たため "
     "theme_priority.title_style の第一条（⓪最優先）に格上げした"),
    ("retention-drop-was-data-immaturity",
     "週次集計で全5chが最新週に維持率20-36%へ急落したのは、公開直後の動画がデータ未成熟なための見かけ。"
     "公開後3日で揃えると41-55%で急落はない。ただし age=3d で揃えても pokemon-lab 78.7%→55.0%、"
     "yokai-watch 63.3%→50.2% と4週連続の緩やかな低下があり、これは実在する。週次の生値で維持率を語らないこと"),
    ("estimated-duration-is-self-correlated",
     "推定尺（avg_view_duration ÷ avg_view_percentage）で尺の効果を測ると、維持率が分母にあるため"
     "『短い尺ほど維持率が高い』が自動的に出る自己相関がある。単純な三分位比較では短尺が登録2-3倍に見えるが、"
     "維持率45-70%に絞ると1.33倍（95%CI 0.88-2.01）で有意ではない。尺を根拠に施策を打つときは必ず維持率を統制する"),
    ("scp-lab-is-the-bottleneck-and-the-lever",
     "scp-lab は登録者の54%（30日純増38/70人）を1chで稼ぐ一方、CTR 1.52%で全ch最下位、"
     "視聴維持カーブの30%地点残存0.64も全ch最下位（最良のpokemon-labは0.81）。"
     "リーチは43,997インプレッションで全ch最大。つまりCTRと維持率の改善余地が最も大きく、"
     "同じ改善幅なら全社の登録者数に最も効く。ここを一点集中で改善する"),
    ("fabricated-numbers-in-queue-titles",
     "【事故】08-23にテーマキューのタイトルを一括書き換えした際、title_style の『数字を1つ以上入れる』を"
     "満たすため実在しない数字（「9つ」「26部隊」「4名」「機密レベル4」）を付与してしまった。"
     "報告書らしさを売りにするチャンネルで数字を創作するのは信頼性を損なうため、全削除したうえで "
     "title_style を『原典に実在する場合のみ入れる。確認できない数字を創作してはならない』に改めた。"
     "タイトル自動生成・一括書き換えでは必ずこの制約を明示すること"),
    ("mechanical-title-rewrite-breaks-japanese",
     "タイトル一括書き換えを正規表現＋接尾辞付与で行うと『〜の恐怖の恐怖』『〜とはに隠された秘密』のような"
     "破綻した日本語が生成される。また必須語を機械的に差し込むと『不思議な進化の過程に隠された秘密』のように"
     "固有名を欠いた検索性のないタイトルになる。ルール適合の機械チェックはこれらを検出できないため、"
     "書き換えは必ず1件ずつ書き、(a)固有名を含むか (b)重複していないか (c)good_examplesと同一でないか も併せて検査する"),
    ("clip-lab-was-spinning-idle",
     "clip-lab は運用方針で凍結中にもかかわらず autopilot.enabled=true のまま平日2枠＋休日2枠がスケジュールされ、"
     "theme_seeds 0件・theme_queue 未作成・video_metrics 実績0件で空回りしていた。08-23に enabled=false へ変更。"
     "運用方針で止めたチャンネルは autopilot も必ず落とすこと"),
    ("viral-hooks-were-corrupted",
     "全4chの theme_priority.viral_hooks が文字列を1文字ずつlistに分解した状態で保存されていた"
     "（scp-lab 90要素 / yokai-watch 69 / daily-science 159 / pokemon-lab 70）。プロンプトを汚染していた。"
     "08-23に文字列へ復元。JSONを機械編集するときは list(str) と [str] の取り違えに注意する"),
    ("reach-lags-two-days",
     "video_reach_daily（インプレッション・クリックの唯一の情報源）は video_metrics より2日古い"
     "（08-23時点で reach=08-20、metrics=08-22）。当日投稿分のCTRは翌々日まで評価できない。"
     "また video_metrics.impressions（scp-lab 29,585）と video_reach_daily（43,997）が一致しないため、"
     "CTR分析は母数の大きい video_reach_daily を使う"),
]

CHANGES = [
    (f"data/channels{{,_orchestrator}}/{{scp-lab,yokai-watch,daily-science,pokemon-lab}}.json",
     "タイトル規則を voice_style.style_rules から theme_priority.title_style / good_examples へ移設（根本原因対応）",
     ["生成プロンプトが style_rules を読まない実装のため、前日までのタイトル施策は全て無効だった",
      "4ch の title_style を全面改訂し、good_examples も新規則に沿って全件差し替え",
      "viral_hooks の1文字分解破損を4chとも修復"]),
    ("data/channels/{scp-lab,yokai-watch,pokemon-lab}/theme_queue.json",
     "既存キュー40件のタイトルを新規則に沿って全件書き直し",
     ["scp-lab 23件・yokai-watch 6件→10件（補充4件）・pokemon-lab 7件",
      "初回の機械置換で破綻日本語・数字捏造・固有名欠落が発生したため、バックアップから復元して1件ずつ書き直した",
      "最終状態でルール適合／捏造数字なし／固有名あり／キュー内重複なし／good_examplesとの重複なしを機械検証済み"]),
    ("data/channels{,_orchestrator}/scp-lab.json",
     "全角ダッシュ「—」規則を中立化（前日の『必ず維持』と本日の『使用禁止』を両方撤回）",
     ["直近60日コホートで CTR 0.97倍（95%CI 0.81-1.16）、1本あたり登録者0.74倍（95%CI 0.47-1.18）＝有意差なし",
      "「怖」「恐」は1本あたり登録者1.51倍のため推奨に格下げして維持（CTR単体では非有意）",
      "数字の付与を『原典に実在する場合のみ・創作禁止』に変更"]),
    ("data/channels{,_orchestrator}/yokai-watch.json",
     "作品ネタ最優先へ変更、「怖」優先を撤回、尺を短縮",
     ["⓪最優先: 妖怪ウォッチ作品ネタ（1本あたり登録者2.45倍・登録/1k 2.9倍・CTR 1.33倍）",
      "「怖」優先を撤回（登録者0.75倍）、「なぜ」禁止も解除（1.12倍で中立）",
      "「秘密」「隠」「本当」「実は」のいずれかを必須化",
      "short_format 320-390字 → 270-310字（前日の延長を部分撤回。330字は line_chars から到達不能だったため310に）"]),
    ("data/channels{,_orchestrator}/daily-science.json",
     "「なぜ」抑制と「99%が知らない」禁止を両方撤回",
     ["「なぜ」始まり: 1本あたり登録者1.58倍（ただし同コホートのCTRは0.53倍で符号が食い違う）",
      "「99%が知らない」: 1本あたり登録者1.57倍・登録/1k 1.62倍・CTR 1.20倍と3指標で正のため禁止解除",
      "疑問符「？」を必須化（2.16倍）、「本当」「実は」は禁止（0.70倍）"]),
    ("data/channels{,_orchestrator}/pokemon-lab.json",
     "「秘密」「隠」型を毎バッチ1本必須化、対決型を1本までに制限",
     ["秘密/隠: 1本あたり登録者3.17倍（95%CI 1.02-9.82）だがA群n=6・寄与が1本に集中する弱い証拠",
      "対決型: 1本あたり登録者0.63倍。個別CTRは高いが群比較では1.35倍（95%CI 0.69-2.64）で非有意"]),
    ("data/channels{,_orchestrator}/clip-lab.json",
     "autopilot を停止（enabled: true → false）",
     ["運用方針で凍結中なのに平日2枠＋休日2枠がスケジュールされ空回りしていた"]),
    ("backend/pipeline/auto_scenario/generator.py",
     "テーマ補充プロンプトの続編タイトル例からダッシュ「—」を除去（2871行付近）",
     ["プロンプト文字列のみの変更でロジックは非改変。py_compile 済み"]),
    ("reports/youtube_analysis_20260823.xlsx",
     "日次分析レポートを出力（5シート・数式30件エラー0）",
     ["サマリー / チャンネル別詳細 / 動画別パフォーマンス / 改善アクション(23件) / トレンド"]),
]


def main():
    # known_findings
    p = MEM / "known_findings.json"
    shutil.copy2(p, p.with_suffix(f".json.bak_{DATE.replace('-','')}"))
    d = json.loads(p.read_text(encoding="utf-8"))
    have = {f.get("id") for f in d["findings"]}
    add = 0
    for fid, note in FINDINGS:
        if fid in have:
            continue
        d["findings"].append({"date": DATE, "id": fid, "note": note})
        add += 1
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"known_findings: +{add}件 → 計{len(d['findings'])}件")

    # applied_changes
    p = MEM / "applied_changes.json"
    shutil.copy2(p, p.with_suffix(f".json.bak_{DATE.replace('-','')}"))
    d = json.loads(p.read_text(encoding="utf-8"))
    for f, action, items in CHANGES:
        d["changes"].append({"date": DATE, "file": f, "action": action, "items": items})
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"applied_changes: +{len(CHANGES)}件 → 計{len(d['changes'])}件")


if __name__ == "__main__":
    main()
