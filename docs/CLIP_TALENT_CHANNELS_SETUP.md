# タレント切り抜きチャンネル（clip-fukada / clip-kaneko）セットアップ

作成: 2026-08-24 / 対象: `data/channels/clip-fukada.json`, `data/channels/clip-kaneko.json`

既存の `clip-lab`（ひろゆき切り抜き）と**同じ clip pipeline をそのまま使う**設定追加のみ。
コードは1行も変えていない。`clip-lab.json` にも触れていない。

| | clip-fukada | clip-kaneko |
|---|---|---|
| 名前 | 深田えいみ 切り抜きチャンネル | 金子みゆ 切り抜きチャンネル |
| 切り抜き尺 | 25〜35秒（目標30秒） | 25〜35秒（目標30秒） |
| 1本の元動画から | 4本 | 4本 |
| 投稿スロット | 毎日 20:00 | 毎日 20:30 |
| autopilot | **true**（2026-08-24 稼働開始） | **true**（2026-08-24 稼働開始） |
| default_privacy | **public** | **public** |
| 切り抜き元 | `UCRUdyowhXEQhoNT7uNEvGJA`（深田えいみ / Eimi Fukada） | `UCw_7_DkX4ftnQJJtZTrCOOQ`（金子みゆ / kaneko_miyu） |
| visual_guard | 有効 / max_static_ratio 0.7 | 有効 / max_static_ratio 0.6（厳しめ） |
| engine | local（fallback も local） | local（fallback も local） |

## 2026-08-24 稼働開始（この節が最新）

手順 1〜8 は全部完了。初投稿済み: https://youtube.com/watch?v=TJacs9E879U
（clip-fukada / public / 元動画「YouTubeを続けられなくなりました」31.1秒）

許諾の根拠は **ガジェット通信クリエイターネットワーク（MCN）**。
https://getnews.jp/mcn/kirinuki の切り抜き公認リストに「深田えいみ / Eimi Fukada」
「金子みゆ / kaneko_miyu」の両方が掲載されている。

**許諾は説明欄の文言では成立しない。** ガジェ通方式は「申請フォーム → 承認メール」で、
元動画の説明欄には何も書かれない（2026-08-24 に両ch＋サブch＋おかず作り の直近50本ずつ、
計200本を実測し、「切り抜き」「ガジェ通」「黙認」等の文言は**0件**）。
ひろゆき（説明欄に『切り抜き用にガジェ通クリエイターデータベース』と書く回がある）とは違う。
よって `require_permission_phrase: false` ＋ `permission_note` / `permission_source_url` /
`permission_checked_at` に根拠を書く方式で運用している。`permission_phrases` は将来
説明欄に文言が入ったとき用に残してあるが、今は参照されない。

### ⚠️ 残っているリスク（運用者が必ず読むこと）

1. **タイトルのブロックリストは原理的に取りこぼす。** 深田えいみ側は
   チャンネル全体が成人向け寄りで、タイトルが婉曲表現になっている。
   実測で漏れた例:
   - 「急にどうした？」→ 中身は**媚薬のPR回**（説明欄で判明。タイトルからは分からない）
   - 「よろしくお願いします」→ 中身は**ぷろたんとの共演回**（ゲスト側の許諾が別途必要）
   新しい婉曲表現が出るたびに `exclude_title_patterns` を足す運用は追いつかない。
   **公開前に人が1本ずつ見るゲートを入れるまで、autopilot は無人で回さない方がよい。**
2. **区間単位のゲートを追加した**（`segment_selection.exclude_text_patterns`）。
   タイトルが安全でも中の一区間だけが性的、という事故が実際に起きた。
   実測 2026-08-24: 追徴課税の話をしている回から
   「マネージャーは 私の裸も見てます」が最高スコアで選ばれた。
   このゲートを入れて別の区間（「2年間支えたマネージャーが退職」）に差し替わった。
   既定は空＝無効なので clip-lab 等の挙動は変わらない。
3. **素材が 360p しか取れない。** Python 3.9 では yt-dlp が 2025.10.14 で頭打ちになり、
   web は SABR 強制で形式ゼロ、android は itag 18（640x360 合成）のみ。
   `android_vr` は formats に 1080p DASH が並ぶが実ダウンロードが 403 になるので使えない。
   1080x1920 に引き伸ばすので画質は粗い。直すには Python 3.10+ 化が必要。
   clip-lab も同じ条件で回っている（＝新規の劣化ではない）。
4. **元動画によっては itag 18 の pixel format が壊れていて ffmpeg が code 183 で落ちる**
   （実測: `yjF8W6-BZd4`）。今の `download_section` は失敗すると例外で止まり、
   別の元動画にフォールバックしない。autopilot がこれを踏むとその日は投稿0本になる。
5. **カスタムサムネイルは 403**（`youtube.thumbnail / forbidden`）。
   投稿先チャンネルが電話番号未確認のため。動画自体の投稿には影響しない（scp-lab と同じ）。

## いま動くこと・動かないこと（立ち上げ時のメモ）

- ✅ `ChannelManager` が両チャンネルを読み込む（11ch になる）。`config_validation` はエラー0・警告0。
- ✅ `generate_clip("clip-fukada", dry_run=True)` は例外を出さず「素材なし」で正常に止まる。
  allowlist が `enabled: false` なので **YouTube API クォータも消費しない**（実測済み）。
- ❌ 切り抜きは1本も作られない。これは**故障ではなく設計**。許諾の根拠（`permission_phrases`）が空の間、
  `acquisition.classify()` は候補を `theme_only` に落とす＝映像には触らない。

## 稼働させる手順（この順番で開ける）

1. ~~**投稿先チャンネルを作る** → `youtube_channel_id` と `video_format.youtube.channel_id` に `UC...` を入れる~~
   ✅ 完了（2026-08-24）。clip-fukada = `UCKP4UWYLmzZgpXKITjUN5PQ` / clip-kaneko = `UCYF3swAtRdxup-qfEK53epw`。
   YouTube API `channels.list` で実在・タイトル一致・動画0本を確認済み。
2. **OAuth 連携**（管理画面から。クライアントは他chのものを流用可）
3. **切り抜き元チャンネルの ID を入れる**
   `clip.external_sources.allowlist_channels[0].channel_id` の
   `UC_TODO_FUKADA_EIMI_MAIN` / `UC_TODO_KANEKO_MIYU_MAIN` を実際の `UC...` に置換
4. **許諾を取る（ここが本丸）**
   - 説明欄に切り抜き許諾文言があるなら、その文言をそのまま `permission_phrases` に入れる
   - 事務所・本人からメール等で個別許諾を得た場合のみ `require_permission_phrase: false` にして
     `permission_note` / `permission_source_url` / `permission_checked_at` に根拠を書く
   - **どちらも無いなら開けない。** 2人とも「切り抜き公認」を公表しているタレントではない
     （ひろゆき＝ガジェ通クリエイターデータベース、岡田斗司夫＝「切り抜きを黙認します」のような
     公開された根拠が存在しない）。無許諾の切り抜きは著作権・肖像権・パブリシティ権の三重の問題になる。
5. `allowlist_channels[0].enabled` → `true`
6. `publish_settings.default_privacy` と `video_format.youtube.privacy_status` → `public`、
   `publish_settings.auto_publish` → `true`
7. `autopilot.enabled` → `true`
8. バックエンド再起動（新しい channel JSON は起動時にしか読まれない）
   `launchctl kickstart -k gui/$(id -u)/com.youtube-factory.backend`

手動でのテストは `python3 backend/run_clip_channel.py --channel clip-fukada`（投稿なし）。

## clip-lab と意図的に変えたところ

| 項目 | clip-lab | 新2ch | 理由 |
|---|---|---|---|
| 尺 | 30〜59秒 | 25〜35秒 | 指定の「30秒」。窓幅は `build_candidates` の min/max がそのまま候補条件になるので狭く取る |
| clips_per_video | 5 | 4 | 元素材が2〜6時間の生配信ではなく10〜20分のトーク。30秒×4本で総尺の10〜20% |
| 固定タグ・ハッシュタグ | 配信者名を入れない | タレント名を入れる | clip-lab は allowlist が複数あり出典が回ごとに変わる。こちらは単独タレント専用で出典が固定 |
| max_duration_sec（元動画） | 25200（7時間） | 10800（3時間） | 長時間の生配信を想定しないジャンル |
| download_dir / output_dir | 共用 | ch別サブフォルダ | 素材が混ざらないように分離。どちらも `~/Movies` 配下（`~/Desktop` は TCC で launchd から書けない） |
| exclude_title_patterns | ゲスト回のみ | ゲスト回＋性的表現に寄る回 | 後者は YouTube の性的コンテンツポリシー対策。グラビア・水着・撮影オフショット回、および過去の出演作（AV期）は許諾の有無に関わらず対象外 |

## 注意点

- **`data/analytics/clip_state.json` は全チャンネル共通**（キーは `元チャンネルID::元動画タイトル`）。
  同じ元動画を2つの切り抜きチャンネルで使うと使用済み区間を共有する。今回は素材が別人なので衝突しない。
- **visual_guard の閾値は clip-lab（ひろゆき配信）の実測値の流用**。トーク vlog は配信よりカメラが動くので
  甘い可能性がある。初回10本の `visual_check` を見て締め直すこと。
- **`source_crop_bottom_ratio: 0`**。外部素材に焼き込み字幕帯は無い前提だが、常時テロップが乗る編集の回だと
  打ち直し字幕と二重に見える。実素材で1本確認してから調整する。
- **自動字幕が無い動画は使えない**（`external.py` が字幕10行未満で除外）。タレント系は自動字幕が
  付いていないチャンネルもあるので、ID を入れたら `prepare_limit` の範囲で実際に字幕が取れるか確認する。
