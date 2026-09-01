# メモリ更新差分 — 2026-08-31（nightly-full-progress）

> ⛔ **`~/.auto-memory/` は本セッションの接続フォルダ外のため、直接書き込めなかった。**
> 接続済みは `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つのみ。
> このファイルの内容を `~/.auto-memory/` の該当ファイルへ反映すること。
> 恒久対応としては `~/.auto-memory` を Cowork の接続フォルダに追加するのが早い。

---

## reference_all_projects.md 反映分

| プロジェクト | 現状 | 最終コミット |
|---|---|---|
| youtube-factory | 稼働中（13ch設定・12ch autopilot ON） | 2026-08-31 `ed5cbe5` |
| aiseki | 本番稼働 `aisekimatch.com` | 2026-08-31 `f02b80c` |
| fanup | 本番稼働 `fanup-rouge.vercel.app` | 2026-08-31 `2681dfd` |
| oripa | 未公開（古物商許可待ち） | 2026-08-11 `5c15784` |
| ai-english-coach | 本番未デプロイ | 2026-08-18 `a90c4ad` |
| ai-orchestrator | 停滞 | 2026-08-09 `052a617` |
| rhythm-pop | 停滞 | 2026-06-22 `1cfde97` |
| claude-codex-bridge | 停滞 | 2026-07-04 `eb23d8a` |

## project_aiseki_lp.md / project_aiseki_business_decisions.md 反映分

- **URL が変わっている。** 定期タスク定義に残る `aiseki-xi.vercel.app` は旧URL。
  現行は **`https://aisekimatch.com`**（2026-08-22 独自ドメイン移行済み）。タスク定義側も直すこと。
- Supabase project ref は `melfyxfvhyknqhruytms`（旧 `tvydtsqirogdxglkoicz` は接続先ではない）。
- Git リモート: `https://github.com/zaki21016/aiseki`（private）。
- 2026-08-31 の変更: Vercel Hobby の Serverless Function 上限12個対策で **15個→5個に集約**。

## project_aiseki_sms.md 反映分

- SMS認証は Twilio Verify で実装済み・本番デプロイ済み（08-30, §28）。
- ⛔ **Twilio がトライアルのまま。公開前にアップグレードが必要**（未解消）。

## project_aiseki_dm_tool.md 反映分

- `/admin/dm`（インフルエンサー営業DM管理）実装済み。運営メール＋管理者パスワードの2段認証（08-30, §29/§30）。
- Instagram初回DMは自動送信不可のため、送信は人が押す設計。自動化しないこと。

## project_clip_channels.md / project_clip_lab_freeze.md 反映分

**設定（2026-08-31 時点）**

| ch | 投稿枠 | エンジン | 状態 |
|---|---|---|---|
| clip-lab | 17:45 / 20:45 | local（国内）/ viral（海外） | 両枠とも本日失敗 |
| clip-fukada | 20:00 ×1 | local | 失敗（ffmpeg 183） |
| clip-kaneko | 08:00 / 14:00 / 20:30 ×3 | local | 生成は成功・投稿はOAuth切れ |
| clip-animal | 18:00 ×1 | viral | sources 空で失敗 |

**恒久ブロッカー（新規記録）**

1. `clip-fukada` / `clip-kaneko` の OAuth リフレッシュトークンが **revoked**。
   さらに `backend/pipeline/credentials/client_secret.json` が存在せず再認証もできない。
2. `ANTHROPIC_API_KEY` 未設定 → clip-lab 海外バイラル枠の翻訳が全停止。
   未処理依頼書が `data/analytics/viral_translation_pending/` に溜まる設計。
3. Reddit RSS が HTTP 429（レート制限）。viral 素材の取得元が細っている。
4. `clip-animal` は `clip.sources` が空・`external_sources` も無効で1本も生成できない。

## project_channel_name.md ほかチャンネル系 反映分

**チャンネル総数は13。** うち autopilot 有効12（`socio-rx` のみ無効）。

| id | 表示名 | YouTube ch ID |
|---|---|---|
| daily-science | リコとマコトのゆっくり日常科学 | UC1OckVkZahT3_fM6W8hD6dg |
| scp-lab | ゆっくり異常存在SCPラボ | UCXEyJqJt9Ug94iOHdpd5a8w |
| company-facts | 企業のホンネ | UCB07OOxWeKK6v86KsSYgnNA |
| akashic-librarian | ラグナロクの司書 | UClXnuH-KPDXnX0bn2NJlMhg |
| 2ch-matome | ゆっくり2chスレまとめ劇場 | UCqvn5FC_B1nj2VhlFTFw8CA |
| pokemon-lab | ゆっくりポケラボ | UCGgc5REGTWRLnBiSeXXkJ5w |
| yokai-watch | ゆっくり妖怪ラボ | UCYf2lsHuHUXbj_HGmqojkUw |
| fake-paper | 虚構論文チャンネル | UCU-awiWyxa1KUN_IIeuJ3kg |
| socio-rx | 社会学の処方箋（autopilot OFF） | UCbAfCMyBVNHHeM3A2TcfN1w |
| clip-lab | ゆっくり解説 切り抜きラボ | UCbWZ5quEFE2VpHPh5TGyPCw |
| clip-fukada | 深田えいみ 切り抜きチャンネル | UCKP4UWYLmzZgpXKITjUN5PQ |
| clip-kaneko | 金子みゆ 切り抜きチャンネル | UCYF3swAtRdxup-qfEK53epw |
| clip-animal | 動物情報局 | UCKlM0WqlO0z2JJN5z6Zd5uQ |

## project_orchestrator.md 反映分（本日のコンフィグ変更）

2026-08-31 の PDCA で確定・適用済み:

- **連番プレフィックス廃止。** `short_series_name` を6ch（daily-science / scp-lab / company-facts / 2ch-matome / pokemon-lab / yokai-watch）で空にした。旧値は `series_name_disabled_20260831` に退避。
  - ⚠ **`fake-paper` と clip系4chは連番テンプレが残ったまま**（本日も「架空論文ファイル #5：」で公開）。意図的な除外か未適用かが不明。次回判断すること。
- **台本尺ガードを本番経路に接続。** `video_generator.py` から `enforce_band()` を呼ぶようにした。本日のログでトリム実行を確認（例: company-facts 263字→205字、2ch-matome 255字→208字）。上限は 210〜225字。
- タイトル実効上限 **30字**、**絵文字禁止**、連番テンプレ禁止を `auto_scenario/generator.py` に明示。
- 撤回した仮説: pokemon-lab「秘密/隠」型（3.17倍→実測0.47倍）、scp-lab「怖/恐」（1.51倍→0.36倍）、yokai-watch 作品ネタ（2.45倍→1.00倍）、pokemon-lab 対決型の抑制（実測で優位のため解除）。
- 高評価CTAを常時前置きに変更（従来は6種均等ローテで約1/6しか言及していなかった）。

**投稿スケジュール（現行）**

平日: scp-lab 09:00 / company-facts 17:00 / daily-science 17:00 / pokemon-lab 17:30 / clip-lab 17:45 / 2ch-matome 18:00 / clip-animal 18:00 / akashic-librarian 18:45 / scp-lab 19:00 / yokai-watch 19:00 / fake-paper 19:30 / clip-fukada 20:00 / clip-kaneko 08:00・14:00・20:30 / clip-lab 20:45（viral）

## 新規記録すべき恒久ブロッカー

1. **YouTube カスタムサムネイル権限が無い（HTTP 403 forbidden）。** 本日公開した8本のうち少なくとも6本でサムネ設定に失敗。
   → 各チャンネルで電話番号認証を済ませる必要がある。**動画は公開されるがサムネはYouTube自動生成のまま**で、CTRを潰し続けている。最優先。
2. **`ANTHROPIC_API_KEY` 未設定。** 日次PDCAの成功パターン分析・維持率分析が全チャンネルで「スキップ」。切り抜き海外枠も停止。
3. **分析同期が6chしか回っていない。** company-facts / akashic-librarian / clip系4ch は `analytics.db` にデータが無く、日次PDCAレポートにも載らない。投稿はしているのに数値が見えていない。
4. **`data/video_publish.db` が 2026-06-07 で更新停止。** 公開実績の追跡はログ頼りになっている。
5. youtube-factory の未コミット変更 750件（うち未追跡527件）／未push 6コミット。aiseki 未push 2コミット。
