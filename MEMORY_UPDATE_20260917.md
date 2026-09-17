# MEMORY UPDATE — 2026-09-17（指揮者 / 日次）

## 0. 結論（3行）

**2ch-matome が 09-13 以降 1 本も公開していないのは OAuth ではなくバグだった。指揮者が
`data/channels/*.json` へ直接書いた autopilot 設定は、backend を再起動するまで
APScheduler に一切反映されない。09-14 に入れた投稿枠の移設も同じ理由で効いていない。
今日コードを直した（要再起動、以後は自動反映）。**

**答え提示語の割り当てが実測と食い違っていた。yokai-watch の「理由」(0.26倍) と
company-facts の「実態」(0.47倍) という明確な負け語が、それぞれ `repair_with` の
第一に置かれていた。5ch すべてを ch 内実測の勝ち語へ付け替えた。**

**視聴維持率は登録者数の代理指標にならない。維持 75.6% で登録0人、維持 122.8% で0人、
維持 22.8% で 5.63 の本がある。維持率を目的関数にしない方針を config に明記した。**

---

## 1. ★本日の最重要発見★ 指揮者の設定変更はスケジューラに届いていなかった

### 症状

`logs/backend.log` の `🤖 Autopilot fired for ...` を数えると、2ch-matome は
**2026-09-13 11:30 を最後に一度も発火していない**。09-14・09-15・09-16・09-17 はゼロ。

一方 `data/channels/2ch-matome.json` は `autopilot.enabled = true`（09-16 10:10 更新）。
09-16 の指揮者が「トークンが生きているのに autopilot=false だった 2ch-matome だけを
復帰させた」と記録したとおりの内容がディスクにある。**設定は正しいのに動いていない。**

### 原因

```
ChannelManager._refresh_if_changed()   … ディスク変更を検知してメモリを読み直す ✅
    ↓（ここで終わっていた）
APScheduler のジョブ                    … 変わらない ❌
```

APScheduler のジョブを触るのは `api_channel_autopilot._refresh_channel_job()` だけで、
その呼び出し元は以下の 2 経路しかなかった:

1. 起動時の `restore_all()`（`main.py:1727`）
2. autopilot API 経由の書き込み（`api_channel_autopilot.py:293` の `set_section` 直後）

**指揮者はファイルを直接書くので、どちらも通らない。** 結果として

- `autopilot.enabled` の false → true は、再起動まで効かない
- `autopilot.schedule.times` の変更も、再起動まで効かない

最後の `🚫 Autopilot for 2ch-matome: disabled (enabled=false)` は
next_run が 2026-09-15 の起動時ログ、つまり **09-16 の設定変更より前の起動**のもの。
その後 backend は再起動されていないので、スケジューラは「無効」のまま固まっていた。

### 影響範囲（2ch-matome だけの話ではない）

09-14 の指揮者が 2ch-matome の投稿枠を実測に基づいて
9:00/12:15/21:00 → 7:30/12:15/17:30 へ移設している。
**これも同じ理由で 1 度も適用されていない。**
過去の指揮者が「投稿時間を最適化した」と記録した変更のうち、
backend 再起動を挟まなかったものは全て未適用の可能性がある。

### 修正

- `backend/channels/channel_manager.py`
  - `add_reload_hook(fn)` / `_fire_reload_hooks(channel_id)` を追加
  - `_refresh_if_changed` がディスク由来の読み直しをした直後にフックを呼ぶ
  - 同一関数の二重登録は無視。フック内で `cm.get()` を呼んでも再入しないようガード
- `backend/api_channel_autopilot.py`
  - `_on_channel_config_reloaded(channel_id)` を追加し `restore_all()` で登録
  - `_job_fingerprints` で autopilot の中身（enabled / schedule / publish_lead_minutes）を
    指紋比較し、**実際に変わったときだけ** `add_job` する
    （毎回登録すると `next_run_time` が押し出されて発火が後ろへずれる）
  - `json` の import 漏れも同時に追加（このモジュールは json を import していなかった）

### 検証

専用テストで、ディスク変更時のみ 1 回発火し、新しい値を見ており、
フック内 `get()` で再入しないことを確認した。
`backend/tests`: 653 passed / 10 failed。失敗 10 件のうち 9 件は sandbox に
moviepy・PIL が無い環境起因（変更前から同じ）。残り 1 件は下記 §4 で解消した。

### ★次回の指揮者への申し送り

**設定を書いたら必ず「スケジューラに載ったか」をログで確認すること。**
`grep "Autopilot scheduled for <ch>" logs/backend.log | tail -3` で
今日の日付の next_run が出ていなければ、載っていない。
今日の修正以降は自動で載るはずだが、それ自体がまだ実地で検証されていない。

---

## 2. 答え提示語の割り当てが実測と逆だった

### コーパス

公開 2026-08-15〜09-10 / 300再生以上 / 稼働5ch / **195本 / 総再生 194万 / 総登録 977人**。
指標は **登録者 ÷ 千再生**（至上目標が登録者数のため）。
各語について「その語を含む本」と「含まない本」を**同一チャンネル内で**比較した
（チャンネル間の地力差が交絡するため、全体集計では判断しない）。

### 実測

| ch | 語 | n | 該当 | 非該当 | 倍率 |
|---|---|---|---|---|---|
| daily-science | なぜ | 27 | 0.675 | 0.203 | **3.33** |
| daily-science | 正体 | 15 | 0.587 | 0.640 | 0.92（中立） |
| scp-lab | なぜ | 11 | 1.226 | 0.544 | **2.25** |
| scp-lab | 理由 | 4 | 1.496 | 0.689 | **2.17** |
| scp-lab | 本当の | 3 | 0.758 | 0.724 | 1.05（中立） |
| yokai-watch | なぜ | 7 | 1.375 | 0.344 | **3.99** |
| yokai-watch | 正体 | 6 | 0.788 | 0.492 | 1.60 |
| yokai-watch | 本当の | 3 | 0.320 | 0.612 | 0.52 |
| **yokai-watch** | **理由** | **7** | **0.195** | **0.748** | **0.26 ← 負け語** |
| company-facts | 実は | 11 | 0.963 | 0.472 | **2.04** |
| company-facts | 裏側 | 7 | 0.840 | 0.618 | 1.36 |
| **company-facts** | **実態** | **11** | **0.362** | **0.776** | **0.47 ← 負け語** |
| 2ch-matome | 理由 | 5 | 0.518 | 0.067 | **7.75** |
| 2ch-matome | 実は | 4 | 0.312 | 0.089 | **3.50** |
| 2ch-matome | なぜ | 11 | 0.286 | 0.046 | **6.20** |
| 2ch-matome | 正体 | 3 | 0.000 | 0.110 | 0.00 |

### 変更前の `repair_with`（＝ ch の主軸語）と実測の食い違い

| ch | 変更前 | 問題 | 変更後 |
|---|---|---|---|
| daily-science | `["正体"]` | 中立語(0.92)が主軸。3.33倍の「なぜ」が入っていない | `["なぜ","正体"]` |
| yokai-watch | `["正体","わけ","理由"]` | **負け語「理由」(0.26)を含む** | `["なぜ","正体"]`・words から「理由」除外 |
| scp-lab | `["真相","裏側","実態"]` | 3語とも n<3 で実測の裏付けなし | `["理由","なぜ"]` |
| company-facts | `["実態","裏側"]` | **負け語「実態」(0.47)が第一** | `["実は","裏側"]`・words から「実態」除外 |
| 2ch-matome | `["理由","わけ"]` | 「理由」は正しい。「わけ」は実測なし | `["理由","なぜ"]`・words から「正体」除外 |

### 横断ゲートの制約を守った割り当て

`cross_channel_gate.ANSWER_MARKER_DAILY_LIMIT = 6`（答え提示語は 1 日 6 本まで）。
1ch あたり 3〜4 本/日なので、同じ語を 3ch の主軸にすると溢れる。

- 「なぜ」主軸 … daily-science + yokai-watch = 6本/日（上限ちょうど）
- 「理由」主軸 … scp-lab + 2ch-matome = 6本/日（上限ちょうど）
- 「実は」主軸 … company-facts のみ = 4本/日

scp-lab は「なぜ」が 2.25倍で最良だが、上限を超えるため第二に置いた。
**この配分は上限に張り付いている。新しく ch を足すときは必ずここを再計算すること。**

---

## 3. daily-science だけ「なぜ〜のか」が逆効果だった

09-11 の指揮者が全ch共通で入れた
**【最優先】タイトルは「なぜ〇〇なのか」の疑問形を第一候補にする** は、
daily-science では逆効果になっている。

| 型 | n | 登録/千 |
|---|---|---|
| 「なぜ〜？」（短い疑問符止め） | 26 | **0.658** |
| 「なぜ〜のか」（長い形） | 13 | 0.275 |

差は 2.4倍。「なぜ」という語自体は 3.33倍で効いている（§2）ので、
**効いているのは語であって、長い『のか』の形ではない。**

実測トップも短い形:
- 「なぜ座ると腰だけ痛い？圧力1.4倍」3.48
- 「疲れた日の甘い物がすぐ消えるのはなぜ？」3.29

一方 scp-lab / yokai-watch / 2ch-matome では「なぜ〜のか」型が
それぞれ 2.16倍 / 3.85倍 / 4.76倍 で効いている。**ch ごとに逆。**
`theme_priority.title_style` に ch 別の実測を最優先で前置した。

---

## 4. 視聴維持について（2つの発見）

### 4-1. 離脱は冒頭ではなく「本題直後（尺の12〜25%）」に集中している

`retention_insights.json`（09-16 生成）の bucket 別平均離脱率:

| ch | intro | **early(12-25%)** | middle | late | ending |
|---|---|---|---|---|---|
| daily-science | 0.0110 | **0.0227** | 0.0047 | 0.0051 | 0.0034 |
| scp-lab | 0.0128 | **0.0217** | 0.0054 | 0.0046 | 0.0018 |
| 2ch-matome | 0.0096 | **0.0247** | 0.0055 | 0.0028 | 0.0020 |

**early は middle の約 4〜5 倍で、intro よりも大きい。**
冒頭3秒は持っている。切られているのは本題へ入った直後である。

離脱行の実例（`per_video[].drops[].scenario_line`）はいずれも
**「たとえるなら〜」「そう考えると分かりやすいです」で始まる 2 文つなぎの長行**
（scenario index 7〜12）だった。

対策として `short_format.retention_rule_20260917` を全5chに追加:
1. 尺の 12〜25%（おおむね 7〜12 行目）は **1行1文**。2文を `\n` でつながない
2. **たとえ話をこの区間に置かない**。たとえ話は結論を言い切ったあと（50%以降）へ
3. この区間には必ず**新しい事実を1つ**置く。言い換え・前置き・要約で埋めない

### 4-2. 維持率と登録は連動しない。維持率を目的関数にしてはいけない

| 本 | 維持率 | 再生 | 登録 |
|---|---|---|---|
| yokai「なぜあなたは階段で1段だけ外すのか？」 | 75.6% | 5,651 | **0** |
| scp「SCP-3288 大雨の真相 あなたの部屋も沈む」 | 122.8% | 1,521 | **0** |
| company「無印良品の正社員待遇、年間休日123日の実態」 | 40.0% | 8,806 | **0** |
| scp「実は完治後に4人が戻れなかった本当の理由とは？」 | **22.8%** | 3,020 | 17（5.63） |

`analytics_policy.avp_is_not_the_objective_20260917` に明記した。
**維持率は「離脱の原因を探す道具」として使い、最適化の目的関数にはしない。**

---

## 5. 稼働状況

### 公開本数（`data/video_publish.db`）

| 日付 | 本数 | |
|---|---|---|
| 09-05 | 33 | ピーク |
| 09-08 | 21 | |
| 09-09〜09-12 | 2/2/0/0 | OAuth 一斉失効 |
| 09-13 | 9 | 5ch 再認可で復帰 |
| 09-14 | 17 | |
| 09-15 | 13 | company4 / yokai3 / daily3 / scp2 / socio1 |
| 09-16 | 13 | company4 / scp3 / yokai3 / daily2 / socio1 |
| 09-17 | 0（10:00 時点） | daily-science が 06:45 に発火済み |

**ピーク 33本/日 に対し直近 13本/日。** 13ch 中 5ch しか動いていない。

### OAuth トークン（`data/youtube_tokens.db`、09-17 10:04 時点）

| ch | 最終更新 | 経過 | 状態 |
|---|---|---|---|
| daily-science | 09-17 06:50 | 0.1日 | ✅ |
| 2ch-matome / company-facts / scp-lab / socio-rx / yokai-watch | 09-16 22:30 | 0.5日 | ✅ |
| **pokemon-lab** | 09-10 07:43 | **7.1日** | ❌ 失効（09-16 の予告どおり） |
| clip-fukada / clip-kaneko / clip-lab | 09-08 23:00 | 8.5日 | ❌ |
| akashic-librarian | 09-07 13:47 | 9.8日 | ❌ |
| fake-paper | 09-07 10:20 | 10.0日 | ❌ |
| clip-animal | 09-06 23:00 | 10.5日 | ❌ |

09-16 の指揮者が「pokemon-lab は 6.1日でまもなく失効」と書いたとおり失効した。
09-15・09-16 の pokemon-lab の公開は 0 本。
**autopilot は `enabled=false` なのでレンダリングの無駄は出ていない**（09-10〜09-12 の
約90本を捨てた事故は再発していない）。ただしチャンネルは完全に停止している。

**★ 09-16 22:30 に更新された 5ch は、同意画面が「テスト」のままなら 09-23 前後に
また一斉に止まる。** 本番公開への切り替えが今もいちばん効く一手で、人手でしかできない。

---

## 5-2. ★同日の別実行が入れた投稿枠が、連投ガードに毎日1本捨てさせる形になっていた

本日この指揮者より前に、同じ 09-17 付で daily-science の枠が
**7:30 → 16:30** へ移されていた（`_times_comment` に「2026-09-17 指揮者・実測」とある）。
結果 `times = [16:30, 15:00, 17:00]`。

**16:30 と 17:00 は 30分しか離れていない。**
`publish_lead_minutes = 45` なので生成発火は 15:45 と 16:15 の 30分差。
`_MIN_FIRE_INTERVAL_MINUTES = 90` の連投ガードに落ちて
**毎日どちらか1本が黙って捨てられる**（`🛑 Autopilot ...: 前回発火から30分しか経っていないため スキップ`）。
`test_title_gates_20260904::test_autopilot_slots_respect_the_burst_guard` もこれを検出していた。

「夕方ブロックが強い」という判断自体は実測どおりなので撤回していない:

| daily-science 時間帯（JST） | n | 登録/千 |
|---|---|---|
| 07時台 | 4 | 0.343 |
| 12時台 | 6 | 0.356 |
| 13時台 | 4 | 0.361 |
| **17時台** | **19** | **0.766** |
| 18時台 | 6 | 0.241 |

**16:30 → 19:00** へ移し、`15:00 / 17:00 / 19:00` の 120分間隔に揃えた。
17時台（当ch最良）は温存。19時台は当ch実績ゼロだが、
scp-lab / yokai-watch / company-facts の3chが既に 19:00 枠を運用している。
バックアップ: `daily-science.json.bak_burstfix_20260917_orch`。

**★申し送り: 投稿枠を動かしたら、必ず同日の他の枠との間隔が90分以上あるか確認すること。**
`posting_optimizer` は最良の時刻を1つ返すだけで、他の枠との間隔を見ていない。

---

## 6. 本日のファイル変更

### コード
- `backend/channels/channel_manager.py` … リロードフック機構
- `backend/api_channel_autopilot.py` … `_on_channel_config_reloaded` / `_job_fingerprints` / `json` import

### 設定（`data/channels/*.json`。`channels_orchestrator/*.json` は symlink で同一実体）
バックアップ: `*.bak_pdca_20260917_orch`

- daily-science / scp-lab / yokai-watch / company-facts / 2ch-matome:
  - `title_rules.hard_constraints.require_any_of.repair_with` を実測の勝ち語へ
  - `title_rules.hard_constraints.require_any_of.words` から負け語を除外（該当3ch）
  - `title_rules.answer_marker_assignment` / `answer_markers` / 変更履歴 `_marker_change_20260917`
  - `theme_priority.title_style` に ch 別の実測を最優先で前置（旧文は `title_style_prev_20260917` へ退避）
  - `short_format.retention_rule_20260917`
  - `analytics_policy.avp_is_not_the_objective_20260917`
  - `pdca_log` に追記

- 負け語除外で不適合になった既存テーマ **10件**を、題材を変えずに言い換え
  （例「コストコの利益が会費で決まる実態」→「コストコの利益、実は会費で決まる」）
- yokai-watch の規約違反テーマ「口裂け女が1979年に全国へ広がった経路」（西暦の数字が
  ハードルール違反）を「なぜ口裂け女の噂は全国へ同時に広がったのか」へ修正。
  これで `test_title_gates_20260904::test_enforced_channels_have_clean_queues_and_seeds` が緑になった。
- daily-science の投稿枠 16:30 → 19:00（§5-2。`test_autopilot_slots_respect_the_burst_guard` も緑に）

### テスト結果の推移

| 時点 | 結果 |
|---|---|
| 着手前 | 653 passed / 11 failed |
| 本日の変更後 | **654 passed / 10 failed** |

解消した2件: `test_enforced_channels_have_clean_queues_and_seeds`（1979年）、
`test_autopilot_slots_respect_the_burst_guard`（16:30の間隔）。新規の失敗はゼロ。
残る10件のうち9件は sandbox に moviepy・PIL が無い環境起因で、変更前から同じ。

**残り1件は実在の設定ドリフトなので記録しておく:**
`test_fixes_20260907::TestDupCheckBlacklist::test_blacklisted_theme_is_not_reported` が
「scp-lab の blacklist に SCP-173 が無い」で落ちている。
git HEAD 時点でも本日の変更前バックアップでも同じく無いので、**今日の変更が原因ではない**。
どこかの時点で `theme_blacklist` から SCP-173 が消えた。
テストの前提が古いだけなのか、本当に再出題されうる状態なのかは未判定。次回に持ち越す。

### 成果物
- `reports/youtube_analysis_20260917.xlsx`（5シート・数式72本・エラー0）
- `restart_and_trigger_20260917.command`（backend 再起動＋制作指示＋OAuth診断）

---

## 7. Phase 1 / Phase 4 が実行できなかったことの記録

サンドボックスVMから外部ネットワーク（googleapis.com）へも Mac の localhost:8000 へも
到達できない。よって本日は:

- **Phase 1（YouTube Data API での新規取得）は実行していない。**
  分析は `analytics.db` の既存データ（最終取得 2026-09-16 22:30）に基づく。
  成熟コーパス（公開 08-15〜09-10）を使っているので、この分の鮮度不足は
  結論に影響しない。ただし **09-13 以降の公開分は日次行が欠けており**、
  この期間の見かけ上の不振（例: 09-13以降の登録/千 0.0〜0.42）は
  データ未成熟による可能性が高い。**これを実力低下と読み違えないこと。**
- **Phase 4（autopilot trigger）は実行していない。**
  `restart_and_trigger_20260917.command` として置いた。ユーザーの実行が必要。

---

## 8. 反証の期限 — 2026-09-24

- (a) 付け替えた答え提示語の ch 内 登録/千再生 が、旧語の実績を下回れば戻す
- (b) daily-science の「なぜ〜？」型が 0.658 を下回れば「なぜ〜のか」へ戻す
- (c) early バケットの離脱率が 0.022 を下回らなければ、行分割ルールは無効として撤回
- (d) §1 のスケジューラ修正が効いていれば、2ch-matome が 7:30/12:15/17:30 に発火する。
  発火しなければ修正は不十分なので、別の原因を探すこと

---

## 9. 積み残し（指揮者では解決できない）

1. **★最優先** Google OAuth 同意画面を「テスト」→「本番」へ。トークン寿命 7日 → 無期限。
   これをやらない限り、7日ごとに全チャンネルが止まる事故が再発し続ける。
2. **★** pokemon-lab の OAuth 再認可。
3. 失効放置の 6ch（clip-animal / fake-paper / akashic-librarian / clip-fukada /
   clip-kaneko / clip-lab）の再認可。いずれも autopilot=false で無駄は出ていない。
4. `restart_and_trigger_20260917.command` の実行。今日のコード修正はこれで初めて有効になる。
5. yokai-watch / company-facts / pokemon-lab は `retention_curve` が 0 本で離脱分析ができない
   （`retention_insights.json` に `no retention curves saved` と出る。`fetch_retention_for` は
   5 に設定済みなので、設定ではなく取得側の問題）。
   **yokai-watch は登録転換が全ch最良(1.312)なのに、なぜ効いているのかを維持率から検証できていない。**
