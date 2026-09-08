# YouTube Factory 引き継ぎ書

最終更新: 2026-09-07 23:50（深夜 nightly-full-progress）/ 作業ツリー: **未コミット164件**（実行結果。`main` は `c51c3de`・本日コミットなし）

> **2026-09-07 深夜の点検結果は `MEMORY_UPDATE_20260907_night.md`。**要点だけ:
>
> | 項目 | 実測 |
> |---|---|
> | 本日の公開 | **27本**（09-06 の30本から -3）。減少分は**すべて OAuth 失効**が原因 |
> | 🚨 **OAuth 失効が現実化** | `clip-animal` / `socio-rx`（09-06中）/ `fake-paper`（09-07 10:20頃）/ `akashic-librarian`（09-07 14:00頃）の**4chが死亡**。他9chは正常で次は09-10前後 |
> | 🆕 **失効の判別法** | `youtube_tokens.db` の **`expires_at` ではなく `updated_at`**（最後にリフレッシュ成功した時刻）を見る。**24時間以上更新されていなければ失効。**`expires_at` はアクセストークン(1時間)の期限で7日失効の指標ではない（3夜連続で誤読しているので確定させる） |
> | 🆕 🚨 **`ANTHROPIC_API_KEY` が `backend/.env` に無い** | `clip-lab` 20:45 海外バイラル枠が毎日落ちる真因。`series_engine` の「Claude 未応答」も同根。**環境変数1行で複数症状が同時に消える。明日の最優先。**`APIキー調査結果.md` の「キーあり」は誤り |
> | サムネ403 | **21/27本（78%）**。免れた6本は daily-science 3 + akashic 2 + **company-facts 1**。🆕 **09-04〜06 の「電話認証済み2ch＝6本」という規則が崩れた**（company-facts は3枠中1枠だけ通過）。明日追跡すること |
> | 🆕 枠移設は**再起動なしで反映されていた** | `pokemon-lab` は旧15:00と新19:00が両方発火して**4本**、`yokai-watch` は09:30移設が当日に間に合わず**2本**。**移設当日の本数は実績として評価しない。**翌日3本へ戻る |
> | 🚨 `yokai-watch` テーマキュー | 16 → **8（残2.7日）。09-09 に枯れる。**明朝の指揮者で必ず補充。次点 `pokemon-lab` 17（5.7日） |
> | 画像ブリッジ | `pending` **131 → 210**（+79）、`delivered` 依然 **0**。設定は完成済み。**残るはワーカーを人が回すことだけ** |
> | 🆕 `yokai-watch` の `video_metrics` | **欠測は解消**（09-06 49行 / 09-07 50行）。代わりに09-07欠測は `akashic` / `fake-paper` / `clip-animal` ＝**OAuth失効chと完全一致** |
> | Δ（09-06→09-07） | 再生 **20,144** / 表示 3,837 / 登録 **6**（登録/千再生 0.298）。**3ch欠測のため09-06との単純比較は不可** |
> | 7日序列 | company-facts 0.737 > akashic 0.727 > scp-lab 0.679 > daily-science 0.602 ≫ pokemon 0.275 / yokai 0.245 / **2ch-matome 0.186** / **clip-lab 0.000（再生181,545で登録0）** |
> | 🆕 主題の拡張 | 「再生は出るが登録に変わらない」問題は 2ch-matome だけでなく**切り抜き3ch（clip-lab / clip-fukada / clip-kaneko）も同型**。CTRは本編系の2〜6倍なのに登録0〜20。**まとめて1つの主題として扱う** |
> | 設定変更 | **なし**（`scp-lab` の6枠は平日/土日の分割、`clips_per_video` の重複は国内枠/バイラル枠の別設定で、いずれも正常だった） |

> **2026-09-06 深夜の点検結果は `MEMORY_UPDATE_20260906_night.md` と `reports/全進捗_2026-09-06.md`。**要点だけ:
>
> | 項目 | 実測 |
> |---|---|
> | 本日の公開 | **30本**（ゆっくり系24＝全枠成功 / 切り抜き6）。09-05 の33本から -3、減少分はすべて `clip-kaneko`（3→1） |
> | 🚨 **OAuth 7日失効** | `akashic-librarian` / `clip-animal` / `fake-paper` / `socio-rx` が **09-07 13:30頃**。**akashic は403を免れている2chの片方なので、落とすとサムネ付き動画が1日3本→0本になる** |
> | サムネ403 | **24 / 30本（80%）**。免れたのは `daily-science` 3本と `akashic-librarian` 3本＝**電話認証済みの2chだけ。09-04/05/06 で3日連続同じ構図** |
> | ⚠️ `youtube_tokens.db` の `expires_at` | **アクセストークン（1時間）の期限であって7日失効の指標ではない。**13ch が同じ値で揃うのは正常。**読み違えないこと** |
> | ChatGPT スレッドURL | **13 / 13 到達**（夕に `2ch-matome` を登録）。`missing` 0件 |
> | 画像ブリッジ | 真因2件は朝に修正済み・配送レッグも健全。だが `pending` **49 → 131**、`delivered` 依然 **0**。**残るはワーカーを回すことだけ** |
> | `clips_per_video` 修正（`c51c3de`・16:48） | **本日の実績には現れていない**（clip-animal 1→1 / clip-kaneko 3→1）。適用機会は 16:48 以降の3枠のみ。**09-07 の丸1日で再判定すること**。素材在庫は 20→23本 |
> | 🆕 `yokai-watch` の `video_metrics` | **2日連続で0行**（他11chは3〜50行）。投稿は動いているので取得側の障害 |
> | ⚠️ `yokai-watch` のテーマキュー | 24 → **16（残5.3日）**。09-09 までに補充。次点は pokemon-lab 22 / scp-lab 26 |
> | `scp-lab` の本数 | 4本 → **3本に復帰**（09-05 の再起動日の枠重複は解消。予測どおり） |
> | Δ（09-05→09-06） | 再生 **10,723** / 表示 2,540 / 登録 **8**（登録/千再生 0.746）。`yokai-watch` 欠測 |
> | `thumbnail_ab_tests` | 19件すべて `monitoring` のまま。切替ゼロ。**ただし11chはサムネ自体が付いていないので A/B の前提が成立していない** |
> | `channel_metrics` | 最新 **09-03**（3日遅れ）。日次の登録増減は `video_metrics` 差分で見ること |

> **2026-09-06 の変更まとめ** — 画像ブリッジが一度も配送していなかった件と、機械ゲートの取りこぼし
>
> | 内容 | 状態 |
> |---|---|
> | 🚨 **画像ブリッジが delivered 0 だった真因** | ✅ **2つ**あった。①イラスト依頼で `channel_id` が渡っていなかった（`video_generator` の `generate_illustration()` 呼び出し4箇所すべてで引数が欠落。pending 49件中36件が `channel_id=""`）②スレッド URL が **`image_generation` ブロックではなくトップレベル**に書かれていた（12ch分）。読む側は前者しか見ないので `thread_url_for()` が全chで None を返していた。**設定にも依頼にも URL があるのに、両者が繋がっていなかった** |
> | 配送レッグ自体 | ✅ **壊れていない**。一時ディレクトリで enqueue→deliver→cache ヒットまで通ることを実測。上の2つを直せば動く（＝ワーカーが処理するだけ） |
> | 対処 | ✅ 4箇所に `channel_id=channel_id` を追加 / 12ch の URL を `image_generation.chatgpt_thread_url` へ移設 / `thread_url_for()` は**旧置き場（トップレベル）も読む**ようにした（同じ事故を無言で再発させないため） |
> | 滞留していた49件 | ✅ 新設 `image_bridge.py backfill` で貼り直し。**36件の `channel_id` をプロンプト先頭の `art_style` から復元**（chごとに固有の長文なので決定論的に決まる）、48件に宛先スレッドが付いた。**依頼はキューに積まれた時点のスナップショットなので、スレッドを後から登録しても既存分は空のまま残る。設定を直したら必ず `backfill` を走らせること** |
> | ~~❌ 残り1件~~ | ✅ **09-06 夕に解消**。`2ch-matome` のスレッドを登録し `backfill` で3件に宛先が付いた（→ §11-3）。`missing` は0件 |
> | **dup_check の偽陽性** | ✅ `normalize_title` がハッシュタグを落としていなかった。`#架空論文` `#2ch` のような**全動画共通の定型タグ**が `_keyword_overlap` の重み（文字数²）で最大級に効き、判定の主語になっていた。09-05 レポートの類似ペア112件中94件がハッシュタグ入り → 修正後は **112件 → 59件（47%が消滅）**。閾値0.62をいじっても直らない種類の誤検出 |
> | ⚠️ 連番見出しは消さない | `1分ポケモン研究 #21：…` の `#` は**連番**であってタグではない。素朴に「#以降を全部消す」と本文が丸ごと消え、#21 と #13 が **0.707 → 1.0 に悪化**する。数字だけのタグは残す実装にしてある |
> | **SCP-173 の巻き添えブロック** | ✅ blacklist が素の部分一致だったため、正規化後の `scp173` が `scp1730`〜`scp1739` の先頭に含まれ、**無関係な10体をブロックしていた**。`theme_dedup.blacklist_match()` を新設し「数字の途中で切れる一致は認めない」規則に。明示指定用に `re:<正規表現>` と `=<完全一致>` の接頭辞も足した |
> | **company-facts の年収矛盾** | ✅ 新設 `pipeline/fact_ledger.py`＋`fact_consistency.enabled`。公開済み台本から (会社, 指標, 値, 期) を台帳化し、同じ会社の同じ指標が回ごとに食い違ったら止める。**期が違うだけなら `fact_main` に期を注記して両立させる（値には触らない）**、同じ期で違えば矛盾として警告 |
> | 棚卸しの結果 | ⚠️ 公開済み41本から **矛盾5件**を検出（報告のあったマクドナルドは1件目）。→ 下表 |
> | 会社名の正規化 | 「日本マクドナルド**株式会社**」と「日本マクドナルド**ホールディングス**株式会社」を同一社に寄せている。別会社扱いだとこの矛盾は永久に検出できない |
> | 複数社を扱う回 | 会社は**行ごとの `bg_query`** から採る。シナリオ単位で1社に決め打つと「退職金・3社で最大2000万円差」のような回で別会社の数字が混ざる（実装当初これで誤検出が1件出た） |
> | PDCA レポート | ✅ 「### 数値の整合チェック」節を追加（`_fact_conflicts`）。テーマ重複チェックとは**別の軸**として毎日出る |
> | `clip-animal` の `clips_per_video` | ✅ **すでに 1 → 3 済み**（09-05 の e4eef9f でコミット済み）。稼働中の backend が 09-05 12:41 起動＝そのコミットより前なので**古い値をメモリに抱えていた**だけ。再起動で解消 |
> | テスト | ✅ `tests/test_fixes_20260906.py`（24件）。全444件中、失敗は**既知の3件のみ**（pytest 未導入の `test_cta_enforcer` / clip-animal・clip-kaneko のハッシュタグ6個 > 上限5個） |
>
> **公開済み台本から見つかった数値の矛盾（company-facts / 41本）**
>
> | 会社 | 指標 | 食い違い |
> |---|---|---|
> | 日本マクドナルド | 年収 | 576万円(2023) / 670万円(2024-12) / 400万円(期不明) |
> | トヨタ自動車 | 年収 | 932万円(2024-03) / 895万円(2024) / 982万円(期不明) |
> | トヨタ自動車 | 平均勤続 | 35.0年(期不明) / 16.1年(2024-03) |
> | 味の素 | 有給消化 | 73.8%(2023) / 76.8%(**同じ2023**) ← どちらかが誤り |
> | サントリー | 残業 | 19.5時間(2023) / 26.4時間(期不明) |
>
> ⚠️ **台帳は「最初に出した数字」を基準にするので、上の5件は台帳に矛盾したまま入っている。**
> どれが正しいかは有報を当たって人が決める必要がある（`data/fact_ledger/company-facts.json` を直す）。
> ゲートが止められるのは**これから出す回**だけ。
>
> ⚠️ **OAuth 7日失効 — 対処できていない（レポートのみ）**:
> `akashic-librarian` / `clip-animal` / `fake-paper` / `socio-rx` の4chが **残り約1.57日（2026-09-07 13:30頃 失効）**。
> 他9chは4.44日。実測値（`check_youtube_tokens.collect()` が token エンドポイントを実際に叩いた結果）。
> **再認可は Google の同意画面をブラウザで人が通す必要があるので、ここでは実施していない。**
> 恒久対策は GCP の同意画面を「テスト中」→「本番」に公開すること
> （https://console.cloud.google.com/auth/audience / project 844705815004）。
> 寿命の刻印は**認可した瞬間**に決まるので、本番公開しても**再認可するまで既存トークンは7日のまま**。

> **2026-09-04（夕）の変更まとめ** — 画像生成から **OpenAI API をコードごと削除**し、
> ChatGPT の**チャンネル専用スレッド**で Claude が 生成→目視チェック→修正 を回す形にした回
>
> | 内容 | 状態 |
> |---|---|
> | **OpenAI Images API を廃止** | ✅ `video_generator` / `thumbnail_generator` から呼び出しコードごと削除。`tests/test_chatgpt_image_bridge.py::TestNoOpenAIImageCalls` が再混入を監視 |
> | **画像生成のブリッジ** | ✅ 新設 `pipeline/chatgpt_image_bridge.py`。`data/image_requests/` のファイルキュー。**パイプラインは待たない**（既定 `wait_seconds=0`）ので autopilot の枠を落とさない。採用後は `cache/<prompt_hash>.png` に入り**次回の同一プロンプトで即ヒット** |
> | **1ch = 1スレッド固定** | ✅ スレッド URL は **`data/channels/<ch>.json` の `image_generation.chatgpt_thread_url`**。毎回新しい会話を開くと ChatGPT 側の文脈もユーザーの修正指示も消えるので厳禁。未登録の洗い出しは `image_bridge.py missing` |
> | **Claude 主導の品質ループ** | ✅ ChatGPT は**レンダリング基盤としてだけ**使い、プロンプト設計と品質判定は Claude が持つ。`prompt` → スクショで確認 → NG なら `reject <id> "理由" --revision "修正指示"`（依頼は pending のまま残り、次の文面が修正指示に変わる）→ 同じスレッドへ投げ直し → OK なら `deliver --qc`。判定基準は skill に明文化 |
> | なぜ変えたか | ① API 直叩きだと会話が毎回消えて**ユーザーが横からプロンプトを直せない**＝品質がずっと同じところで止まっていた ② 09-03 18:49 の **OpenAI 429** で `clip-kaneko` 20:30 枠が落ちた（billing hard limit で `gpt-image-1` が丸ごと死ぬ時期もあった） |
> | **方針スイッチ** | ✅ 新設 `pipeline/openai_policy.py`。テキストの `direct_text_api_allowed()` は **Claude が使えるかを毎回見る**ので、`ANTHROPIC_API_KEY` を入れた時点で OpenAI は呼ばれなくなる（環境変数の変更は不要） |
> | 移行した箇所 | `video_generator._call_openai_image` / `thumbnail_generator.generate_background` / `api_phase5` の2エンドポイント / `gen_thumbs_v4.py` / `gen_thumbs_v4_all.py` / `gen_channel_icons.py` / `backend/scripts/setup_channel_branding.py` / `backend/scripts/generate_character_sprites.py` |
> | `OPENAI_API_KEY` 不在で落ちなくなった | ✅ サムネのデザインブリーフは **Claude → GPT → ローカル機械生成**の順に落ちる。背景が未納品なら繋ぎのグラデーションで組んでサムネ生成自体は通す |
> | 操作 CLI / ワーカー手順 | ✅ `scripts/image_bridge.py`（status/list/missing/show/prompt/reject/deliver/fail/thread/gc）と `.claude/skills/chatgpt-image-worker/SKILL.md`。全文は `docs/CHATGPT_IMAGE_BRIDGE.md` |
> | テスト | ✅ `backend/tests/test_chatgpt_image_bridge.py`（25件）。全 420 件中、失敗は**既知の3件のみ**（§6 の 0-d） |
>
> ⚠️ **残作業（人間の操作が要る。コード側は完了）**:
> ① **ChatGPT スレッドを13ch分作って登録する** — `python3 scripts/image_bridge.py thread set <ch> <URL>`。
> **現時点で登録はゼロ**（`missing` で全13ch が出る）。登録するまでワーカーは処理先を決められない。
> ② **Claude in Chrome の Chrome が ChatGPT にログインしていること**。
> ③ `ANTHROPIC_API_KEY` は `backend/.env` でコメントアウトのまま。入れれば OpenAI 依存はゼロになる。

> **2026-09-04（朝）の変更まとめ** — 「自然文ルールは守られない」を前提に、施策を**機械ゲート**へ移した回
>
> | 内容 | 状態 |
> |---|---|
> | **ch横断の同語ゲート** | ✅ 新設 `pipeline/auto_scenario/cross_channel_gate.py`。同日・全ch合計で**同一キーワードは2本まで**。09-03 に「正体」が5ch同時に出た件の対策。テーマ取り出し時（`_pop_or_refill_theme`）と最終タイトル確定時（`generator._enforce_cross_channel_keywords`）の2箇所で見る。状態は `data/analytics/cross_channel_keywords.json`（日付が変われば破棄） |
> | **タイトルの機械ゲート** | ✅ 新設 `pipeline/title_constraints.py`。`title_rules.hard_constraints` **だけ**が backend に読まれる（`require_*` 等の旧フィールドは 09-03 の検証どおり未参照のまま）。違反時は LLM 再生成2回 → それでも駄目なら決定論的に書き換える。適用: `yokai-watch`=数字禁止 / `pokemon-lab`=数字1つまで＋「なぜ」始まり禁止 / `fake-paper`=実在ブランド語の禁止 |
> | 旧ルールとの矛盾解消 | ✅ 09-03 に全ch一律で入れた「数字＋単位を全タイトルに1つ」は yokai/pokemon の実測と正面から矛盾していた。両chの `theme_priority.title_style` に無効化の追記を入れた（上書きはしていない） |
> | **判断軸を一本化** | ✅ 新設 `pipeline/optimization_policy.py`。全13chに `optimization` ブロック。**改善指標は 登録者/1000再生 のみ**。維持率は参考値へ降格し、`retention_feedback_loop`（シナリオ書き換え）と `scenario_feedback`（プロンプト注入）から**外した**。PDCA レポートに「判断軸」節と xlsx 列を追加 |
> | サムネ: 図解カード | ✅ 「値が未確定なら描かない」。`pillow_illustration.has_confident_render()` を新設し、語彙未ヒット時の**テーマ文ぶつ切りカード**と**一律の人型シルエット**を出さないようにした。流出文書風の偽寸法「?.?m」の印字も廃止 |
> | サムネ: 空き帯の処理 | ✅ カードを描かないときは立ち絵（幅 0.48→0.53 / 高さ 0.34→0.46）と見出し（×1.16）を拡大し、テキストを立ち絵上端まで含めた帯の中央に置いて詰める |
> | サムネ: 黄色帯 | ✅ **1行強制**。最小フォントでも収まらなければ末尾を「…」でトリム、それでも無理なら**帯自体を出さない**（従来は2行折り返しで見出しと競合していた） |
> | サムネ: ホラー系の表情 | ✅ `scp-lab / yokai-watch / akashic-librarian / fake-paper` は驚愕・戦慄側の差分（surprise → angry → sad）を優先。`thumbnail_template.expression_mood` で ch 単位に上書き可 |
> | 実写背景の一致検証 | ✅ 企業名（`entity`）とヒットのタイトル/出典URLを照合してから採用。一致しなければ最大4件まで次候補を試し、駄目ならその枠は使わない。キャッシュも企業ごとに分離（従来は `collected_000.png` が別企業の回で再利用されていた） |
> | **投稿量を増やした** | ✅ 1日あたり **15枠 → 34枠**。台本系8chは全て3本/日。切り抜きは clip-lab 3 / clip-kaneko 3 / clip-animal 2 / clip-fukada 2。枠の間隔は burst guard（90分）を満たす。テーマキューは +240本補充し、各ch 11〜17日分の在庫 |
> | **fake-paper の立て直し** | ✅ コンセプト外テーマ12件を除去＋blacklist（マック/RTX 5090/アベンジャーズ 等、`avoid_categories` の「実在の企業・団体を主語にした嘘」違反）。企画構造を「読み上げ」から**「視聴者が判定に参加する形」**へ（2行目で『信じましたか』と問い、7行目で必ず回収→コメント動機と登録動機を同じ導線に載せる） |
> | ゴミ流入の遮断 | ✅ `trend_scanner` を切り抜き4ch＋fake-paper で停止（`trend_scanner.enabled=false`）。`series_engine` の定型フォールバック3種（「〜に隠された本当の理由を掘り下げる」等）を**既定で無効**にした。ANTHROPIC_API_KEY が無い間ずっとこれが採用され、キューに溜まり続けていた |
> | テスト | ✅ `tests/test_title_gates_20260904.py` 追加（14件）。全 395 件中、失敗は**既知の3件のみ**（§6 の 0-d と同じ） |
>
> ⚠️ **未解決のまま持ち越し**: OAuth 7日失効（GCP 同意画面の本番公開が必要）/ `ANTHROPIC_API_KEY` 未設定 /
> 切り抜き4chの素材枯渇（特に `clip-fukada` は実質ゼロ。枠だけ増やしても素材が無ければ失敗が増えるだけ）/
> 切り抜き4chのテーマキュー計111件のゴミ（流入は止めたが**既存分は消していない**。切り抜きは使わないので実害なし）。

> **2026-09-03 の変更まとめ**（詳細は `MEMORY_UPDATE_20260903.md`（朝）と `MEMORY_UPDATE_20260903_night.md`（深夜））
>
> | 内容 | 状態 |
> |---|---|
> | 🚨 **OAuth 失効は誤診だった** | ✅ **正常動作していた**。`expires_at` は naive UTC を `.timestamp()` した値で**真の期限より9時間手前**。13ch全てで `updated_at − expires_at = 28,800秒` で一致。**失効判定は `expires_at + 32400` と比較すること** |
> | 本日の公開実績 | ✅ **12本に video_id が付与された**（moviepy 系8ch すべて成功。即時4本 / 予約8本） |
> | `clip-kaneko` 初投稿 | ✅ `mz_5-8LG4b8`（14:00）。08-24 稼働開始から10日目 |
> | `clip-animal` 初投稿 | ✅ `EZZqGk4U4-g`（16:55）。`clip.external_sources.enabled` が false だった設定バグを修正して開通 |
> | `clip-lab` 国内枠 | ✅ `hmwRNtzCMgM`（16:54）。7日連続ゼロを脱した |
> | `clip-fukada` | ❌ 3枠すべて失敗。**素材が実質ゼロで切り抜き4ch中もっとも深刻** |
> | タイトル分析の全面見直し | ✅ チャンネル内対照で再測定。「？」必須化を撤回、「正体」のみ採用（→ 朝メモ §3） |
> | 🆕 OpenAI API 429 | ❌ **本日新規**。`clip-kaneko` 20:30 枠がフック生成で落ちた。残高/レート上限の問題 |
> | 🆕 Reddit RSS 429 | ❌ **本日新規**。8サブレディット中6つが取得失敗。`REDDIT_CLIENT_ID` 未設定のため |
> | ⚠️ テーマキューが2箇所ある | 実際に使われるのは `data/channels/<ch>.json` の `autopilot.theme_queue`。同名の `data/channels/<ch>/theme_queue.json` は**死んでいる**（最終補充 06-22〜08-30） |
> | ⚠️ `trend_scanner` が切り抜きchを除外していない | 切り抜き4ch にゆっくり解説用テーマが**計120件**溜まっている（完全なゴミデータ） |
> | ⚠️ 「数字＋単位を必須」の副作用の疑い | 本日の2本に意味不明な同じ「127」が入った。要調査 |
> | GCP 同意画面の本番公開 | ❌ **未着手のまま**。テスト中である限り7日で再発する（08-24・08-31・09-02 と3回）。次は 09-09 前後 |
> | `ANTHROPIC_API_KEY` | ❌ `backend/.env` に**行自体が無い**。clip-lab 海外枠が毎日失敗し依頼書が**8件**滞留 |
> | `client_secret.json` 不在 | ℹ️ **実害なし**。アップロードは `oauth_tokens` DB 経由で成立している。優先度を下げてよい |

> **2026-09-02 の変更まとめ**
>
> | 内容 | 状態 |
> |---|---|
> | Git リモートを用意して push | ✅ 完了（`origin` = https://github.com/rikoandmakoto-ops/youtube-factory.git。`origin/main` が HEAD と一致。残タスク2は消し込み） |
> | 09-02 の PDCA をコンフィグへ反映 | ✅ 完了（テーマキュー +37本 / speed 引き下げ / 答えの遅延 / 2ch endcard。→ `MEMORY_UPDATE_20260902.md`） |
> | 🚨 OAuth 失効 | ❌ **未解決・2日連続**。09-02 も生成9本のうち公開できたのは2本だけ（→ §6 の 0-a） |
> | 切り抜き4ch | ❌ **6日連続ゼロ**（最終公開は clip-lab の 08-27。原因はch別で全て未解決） |
> | `video_status` の `published_at` が NULL | ⚠️ 新規発見。予約公開は `status='scheduled'` / `published_at=NULL` で入るため、`published_at` で集計すると 09-01・09-02 の成功分が0件に見える（→ §5） |

> **2026-09-01 の変更まとめ**
>
> | 内容 | 状態 |
> |---|---|
> | `video_status` が 06-07 で止まっていた問題 | ✅ 修正（`pipeline/publish_log.py` 新設 → §5「公開実績DB」） |
> | `data/channels_orchestrator/` との設定乖離 | ✅ 解消（symlink 化。master は `data/channels/`。→ `docs/CHANNEL_CONFIG_SOURCE_OF_TRUTH.md`） |
> | company-facts / akashic / 切り抜き4ch が analytics 未同期 | ⚠️ 設定は解消（`video_format.analytics.enabled` を追加）したが、**同日深夜に OAuth 失効が全10chへ拡大** → §6 の 0-a |
> | チャンネル一覧が 8ch のまま古かった（実際は13ch・akashic は稼働中） | ✅ 修正（→ §1。深夜の nightly-full-progress で検出） |
> | ショート投稿タイトルが `〜【ショート】` になり `#shorts` すら付いていなかった | ✅ 修正（`generate_descriptions` にタイトル行を追加） |
> | fake-paper 登録0 / yokai 登録効率最下位 | ✅ コンフィグ反映（→ §5「2026-09-01 のマーケ改善」） |

> `docs/HANDOFF.md` は 2026-07-02 時点の古い Dispatch 引き継ぎメモ。**このファイルが最新**。
> 仕様の全文は `youtube_factory_full_spec.md`（約 433KB）にある。

---

## 1. プロジェクト概要

「ゆっくり解説」系ショート動画を **台本生成 → 音声合成 → 映像合成 → サムネ生成 → YouTube 投稿 → 分析（PDCA）** まで
全自動で回す動画ファクトリー。1本のパイプラインを設定ファイルで多チャンネルに展開する構成。

現在 **13 チャンネル**が `data/channels/` に定義され、**12 チャンネルが autopilot 有効**
（`socio-rx` のみ `enabled: false`）。以下は **2026-09-03 23:20 時点の実設定・実績**
（`data/channels/<id>.json` と `data/video_publish.db` を実読み）。

> 🔄 **下の表は 2026-09-03 時点。累計公開・キュー残・投稿時刻は下記の 09-06 実測で置き換えて読むこと。**
>
> **【2026-09-06 23:20 実測】**
>
> | チャンネル ID | 名前 | autopilot | 公開枠 | 累計公開 | 本日 | キュー残 | 403 |
> |---|---|---|---|---:|---:|---:|---|
> | `daily-science` | リコとマコトのゆっくり日常科学 | ✅ | 07:30 / 12:30 / 17:00 | **200** | 3 | 38 | **なし** |
> | `scp-lab` | ゆっくり異常存在SCPラボ | ✅ | 13:00 / 17:00 / 19:00 | **194** | 3 | 26 | あり |
> | `pokemon-lab` | ゆっくりポケラボ | ✅ | 08:30 / 15:00 / 17:30 | **49** | 3 | 22 | あり |
> | `yokai-watch` | ゆっくり妖怪ラボ | ✅ | 12:00 / 16:00 / 17:45 | **49** | 3 | **16 ⚠️** | あり |
> | `2ch-matome` | ゆっくり2chスレまとめ劇場 | ✅ | 07:00 / 12:15 / 21:00 | **44** | 3 | 40 | あり |
> | `company-facts` | 企業のホンネ | ✅ | 08:15 / 13:30 / 17:00 | **36** | 3 | 43 | あり |
> | `fake-paper` | 虚構論文チャンネル | ✅ | 11:00 / 15:30 / 19:30 | **17** | 3 | 35 | あり |
> | `akashic-librarian` | ラグナロクの司書 | ✅ | 10:00 / 14:30 / 18:45 | **17** | 3 | 28 | **なし** |
> | `clip-lab` | ゆっくり解説 切り抜きラボ | ✅ | 11:45 / 17:45 国内 ＋ 20:45 viral | **14** | 2 | 33 ※未使用 | あり |
> | `clip-kaneko` | 金子みゆ 切り抜き | ✅ | 08:00 / 14:00 / 20:30 | **7** | **1** | 38 ※未使用 | あり |
> | `clip-fukada` | 深田えいみ 切り抜き | ✅ | 12:45 / 20:00 | **4** | 2 | 32 ※未使用 | あり |
> | `clip-animal` | 動物情報局 | ✅ | 09:30 / 18:00 | **3** | 1 | 14 ※未使用 | あり |
> | `socio-rx` | 社会学の処方箋 | ❌ | 20:00 / 15:00 | 0 | 0 | 5 | — |
>
> ★ **枠の時刻は「公開時刻」。ジョブ生成はその45分前に走る。**
> ★ `style_rules` 等の設定は実行ごとに読み直されるので即日効くが、**投稿枠（cron）は backend 再起動が要る。**
> ★ 「403」列は**電話認証の有無**。認証済みは `daily-science` と `akashic-librarian` の2chのみ。

| チャンネル ID | 名前 | autopilot | 投稿時刻（平日 / 土日） | 累計公開 | 最終公開 | speed | キュー残 | 登録/千再生 |
|---|---|---|---|---:|---|---:|---:|---:|
| `scp-lab` | ゆっくり異常存在SCPラボ | ✅ | 09:00・19:00 / 18:00・19:00 | 185 | **09-03**（2本） | 1.2 | 15 | 0.58 |
| `daily-science` | リコとマコトのゆっくり日常科学 | ✅ | 17:00 / 18:00 | 192 | **09-03** | 1.2 | 18 | 0.54 |
| `pokemon-lab` | ゆっくりポケラボ | ✅ | 17:30 / 18:00 | 41 | **09-03** | 1.2 | 12 | 0.30 |
| `yokai-watch` | ゆっくり妖怪ラボ | ✅ | 19:00 / 12:00 | 40 | **09-03** | 1.2 | 18 | 0.28 |
| `2ch-matome` | ゆっくり2chスレまとめ劇場 | ✅ | 18:00 / 18:00 | 36 | **09-03** | 1.25 | 23 | **0.16**（最下位） |
| `company-facts` | 企業のホンネ | ✅ | 17:00 / 18:00 | 28 | **09-03** | 1.2 ※対照群 | 26 | **0.73** |
| `fake-paper` | 虚構論文チャンネル | ✅ | 19:30 / 13:15 | 9 | **09-03** | 1.3 | 20 | 0.00 |
| `akashic-librarian` | ラグナロクの司書 | ✅ | 18:45 / 13:45 | 9 | **09-03** | 1.15 | **8**（最少） | **0.83**（1位） |
| `clip-lab` | ゆっくり解説 切り抜きラボ | ✅ | 17:45（国内）＋ 20:45（海外バイラル・毎日） | 8 | **09-03**（国内枠。海外枠は失敗） | 1.0 | 37 ※ゴミ | 0.00 |
| `clip-kaneko` | 金子みゆ 切り抜きチャンネル | ✅ | 08:00・14:00・20:30（毎日） | **1** | **09-03（初投稿）** | 1.0 | 38 ※ゴミ | — |
| `clip-animal` | 動物情報局 | ✅ | 18:00（毎日） | **1** | **09-03（初投稿）** | 1.0 | 14 ※ゴミ | — |
| `clip-fukada` | 深田えいみ 切り抜きチャンネル | ✅ | 20:00（毎日） | 0 | **未**（3枠すべて失敗・素材ゼロ） | 1.0 | 31 ※ゴミ | — |
| `socio-rx` | 社会学の処方箋 | ❌ | 20:00 / 15:00 | 0 | **未**（運用可否が未決） | 1.1 | 4 | — |

> ⚠️ **「キュー残」は `data/channels/<ch>.json` の `autopilot.theme_queue` の件数**（これが生成で使われる）。
> 同名の `data/channels/<ch>/theme_queue.json` は `auto_scenario/theme_queue.py` 管理の**別物で死んでいる**
> （最終補充 06-22〜08-30・30字超タイトルが多数残存）。**編集するなら前者。**
>
> ⚠️ **切り抜き4ch の「※ゴミ」は、`trend_scanner` / `series_engine` が流し込んだ
> ゆっくり解説用テーマ（計120件）。** 切り抜きchは元動画から区間を切るのでテーマキューを使わない。
> 例: `clip-fukada` に「久保建英の成長」「嵐の魅力」「アリアナ・グランデの音楽と心理学」。
> **対象chから `style: clip` 系を除外する設定が必要。**
>
> ⚠️ **BGM は 13ch すべて未設定。** `analytics.enabled` は `socio-rx` 以外の12chで true。

> ℹ️ **2026-09-03 に判明した重要な訂正:**
> - **`clip-animal` は「一度も動いたことがない」ではなくなった。** 09-03 に初投稿。
>   原因は `clip.external_sources.creative_commons.enabled` が true なのに
>   **親の `clip.external_sources.enabled` が false** だった設定バグ。18:30 に修正済み
>   （バックアップ `clip-animal.json.bak_20260903_clipfix`）。
>   ただし `clips_per_video: 1` なので素材1本＝クリップ1本で即枯渇する。
> - **`clip-kaneko` も累計0ではなくなった**（09-03 初投稿）。3枠のうち 08:00 と 20:30 は失敗し、
>   20:30 の失敗は **OpenAI API 429** が原因（素材問題ではない）。
> - **`clip-lab` は「6〜7日連続ゼロ」ではない**（09-03 に公開）。ただし別実行では
>   「未使用の切り抜き区間が残っていません」で失敗しており**素材枯渇は解消していない**。
> - `clip-lab` は直近14日で **平均再生 4,136 で全ch断トツ首位**（company-facts の約2.8倍）。
>   **ただし登録は0人。** 再生数だけで優先度を判断すると過大評価になる。

> ⚠️ **2026-09-01 深夜の点検で判明した、この表の旧版が間違っていた点**（同日中に修正）:
> - 「8チャンネル」ではなく **13チャンネル**。表に `fake-paper` / `clip-animal` / `socio-rx` が無かった。
> - `akashic-librarian` は **停止中ではなく稼働中**（§6 の残タスク13「有効化判断」は決着済み）。
> - 投稿時刻が 6ch で実設定とズレていた（scp-lab / daily-science / yokai-watch / 2ch-matome /
>   akashic-librarian / clip-kaneko）。**時刻を書き換えたら必ずこの表も直すこと。**
> - `clip-animal` は **一度も動いたことがない**。`clip.sources` が空で `external_sources` も無効のため
>   autopilot が毎日「sources が空」で落ちている。素材を入れるか autopilot を切るかの判断が要る。
> - `socio-rx` は `video_format.analytics.enabled` も未設定（他12chは true）。

公開本数は `data/video_publish.db` の `video_status` から集計（2026-09-01 23:00）。
チャンネル単位の登録者数は **2026-09-01 時点で取得できない**（→ §6 の OAuth 失効）。
`data/analytics/analytics.db` の `channel_metrics` も 08-28〜29 で更新が止まっている。

`clip-fukada` / `clip-kaneko` は**タレント単独の切り抜きチャンネル**。2026-08-24 に稼働開始。
許諾は**ガジェット通信クリエイターネットワーク（MCN / getnews.jp/mcn/kirinuki）経由**で、両名とも
切り抜き公認リストに掲載されている。ガジェ通方式は「申請 → 承認メール」なので元動画の説明欄に
許諾文言が無く、`require_permission_phrase: false` ＋ `permission_note` に根拠を書く運用。
初投稿: https://youtube.com/watch?v=TJacs9E879U （clip-fukada / 2026-08-24）。

> ⚠️ **深田えいみ側はタイトルのブロックリストだけでは性的な回・共演回を防ぎきれない。**
> 婉曲表現が多く、「急にどうした？」＝媚薬PR回、「よろしくお願いします」＝ぷろたん共演回、
> といった取りこぼしが実測で出ている。区間単位のゲート
> （`segment_selection.exclude_text_patterns`。今回追加）で最終防御しているが、
> **無人 autopilot で回すなら公開前の目視ゲートを足すこと。** 詳細は
> `docs/CLIP_TALENT_CHANNELS_SETUP.md` の「2026-08-24 稼働開始」節。

**海外バイラル翻訳切り抜き**は `clip-lab` の **20:45 スロット**として同居する
（2026-08-30 のユーザー決定。当初案の専用チャンネル `clip-viral` は作らず、
`data/channels/clip-viral.json` は削除して設定を `clip-lab.json` の
`clip.viral_sources` に統合した）。Reddit で今日バズった短尺動画を Whisper で
書き起こし → Claude で日本語化 → **専用レンダラ**で縦型ショートに焼く。

| 項目 | 決定（2026-08-30） |
|---|---|
| チャンネル | 既存 `clip-lab` に同居（17:45 = 国内切り抜き / 20:45 = 海外バイラル） |
| レンダラ | 国内と共有せず `renderer_overseas.py` に分離 |
| 翻訳失敗時 | スキップせず3回まで指数バックオフで再試行 |
| 公開設定 | 目視レビューなし。private を経ず直接 public |
| 投稿枠 | 毎日 20:45 に1枠 |

> ⚠️ 同居しているので **`autopilot.schedule.times` の 20:45 スロットにある
> `"engine": "viral"` を消してはいけない。** これが素材の探索先（Reddit か
> 許諾済み YouTube か）も決めている。消すと海外枠が国内素材で回る。

稼働に残っている条件は **`ANTHROPIC_API_KEY`（必須・現在空）** だけ。
YouTube チャンネルと OAuth は clip-lab の既存のものをそのまま使う。
`REDDIT_CLIENT_ID`/`SECRET` は無くても RSS 経路で動く（スコア・NSFW フラグが
取れないので強く推奨）。詳細は `docs/CLIP_VIRAL_CHANNEL.md`。

### 運用ルール（過去の指示・厳守）

- ショートのみ・1日1本・チャンネルごとの固定スロット
- 投稿設定の変更は必ず実データ分析に基づく（PDCA 厳守）
- 動画の大きな見た目変更・画像配置変更は、サンプルを出して承認を得てから反映
- 1リポジトリに複数タスクを並行させない（必ずマージしてから終了）
- ai-orchestrator は**明示的な指示があったときだけ**使う

---

## 2. 技術スタック

| 層 | 使っているもの |
|---|---|
| バックエンド | Python 3.9 + FastAPI（`backend/main.py`、uvicorn `0.0.0.0:8000`） |
| フロントエンド | Next.js 14.2 (App Router) + React 18 + Tailwind（`frontend/`） |
| 音声合成 | VOICEVOX（`VOICEVOX_URL`。ローカル or Docker） |
| 映像合成 | FFmpeg + Pillow（`backend/pipeline/` 配下） |
| 台本・分析 | OpenAI API / Anthropic Claude API |
| 素材収集 | Pexels / Pixabay / Unsplash / Google CSE |
| 投稿 | YouTube Data API v3（OAuth）、TikTok Content Posting API |
| 永続化 | JSON / JSONL + SQLite（`data/` 配下） |
| 外部公開 | ngrok 固定ドメイン（OAuth コールバック・Webhook 受け口） |
| 常駐 | launchd（`~/Library/LaunchAgents/com.youtube-factory.*.plist`） |
| ホスティング | Vercel（フロント + バックエンドを `experimentalServices` で同居） |

`data/` は**設定でもあり実行結果でもある**。`data/channels/<id>.json` がチャンネルの単一の真実（テーマキュー・
競合・サムネ設定・autopilot スケジュール・video_format まで全部ここ）。

---

## 3. デプロイ先・稼働環境

| 項目 | 値 |
|---|---|
| 本番 URL | https://youtube-factory-eight.vercel.app （HTTP 307 → `/login`。**認証ゲート付きで稼働中**） |
| Vercel プロジェクト名 | `youtube-factory` |
| Vercel projectId | `prj_LTRLM22VNZ9Qnp5MTZa6FjOI9BS5` |
| Vercel orgId | `team_r5d4Rpbmwu5q0EryE985968c` |
| ローカル API | `http://localhost:8000`（`/health` は 200 を返す＝稼働中） |
| 外部公開 URL | `https://agreeing-corrode-shabby.ngrok-free.dev` → localhost:8000（ngrok 固定ドメイン） |
| Git リモート | ✅ **2026-09-02 に設定・push 済み**。`origin` = https://github.com/rikoandmakoto-ops/youtube-factory.git（`neworigin` も同URLで残置）。`origin/main` はローカル HEAD と一致 |

### 常駐プロセス（launchd）の現況

| Label | 内容 | 状態（2026-08-20 時点） |
|---|---|---|
| `com.youtube-factory.backend` | uvicorn `main:app` を KeepAlive | ✅ **稼働中**（pid 20984） |
| `com.youtube-factory.ngrok` | ngrok http 8000（固定ドメイン） | ✅ **稼働中**（pid 37949） |
| `com.youtube-factory.pdca` | 毎日 23:00 に `backend/run_daily_pdca.py` | ⚠️ **ロードされていない**（`launchctl list` に無い） |
| `com.youtube-factory.agent` | `python -m agent run youtube-growth` を KeepAlive | ⚠️ **ロードされていない**（かつ `agent/` は `agent_deprecated/` にリネーム済み。このまま load すると起動失敗する） |

> plist は `~/Library/LaunchAgents/` にある。ロードは `launchctl load -w <plist>`、確認は `launchctl list | grep youtube`。

---

## 4. 認証情報の場所（値は書かない）

| 種別 | 場所 |
|---|---|
| API キー全般 | `backend/.env`（**gitignore 済み**。ひな型は `backend/.env.example`） |
| 必要なキー一覧 | `API_KEY` / `APP_PASSWORD_HASH` / `JWT_SECRET` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `YOUTUBE_API_KEY` / `PIXABAY_API_KEY` / `PEXELS_API_KEY` / `UNSPLASH_ACCESS_KEY` / `GOOGLE_CSE_API_KEY` / `GOOGLE_CSE_ID` / `CORS_ORIGINS` / `PORT` / `HOST` / `VOICEVOX_URL` / `NGROK_AUTHTOKEN` / `NGROK_DOMAIN` |
| YouTube OAuth トークン | `data/youtube_tokens.db`（SQLite。バックアップ `data/youtube_tokens.db.bak_20260520_223338` あり） |
| TikTok トークン | `data/tiktok_tokens.db` |
| Google OAuth クライアント | `backend/pipeline/credentials/oauth.db`（Fernet 暗号化済み。`.gitignore` で明示除外） |
| 管理画面ログイン | `APP_PASSWORD_HASH` + `JWT_SECRET` によるパスワード認証（本番 URL の `/login`） |

`.gitignore` で `.env` / `backend/.env` / `*.db` / `backend/pipeline/credentials/oauth.db` を除外済み。
**トークン DB は git に入っていない＝このマシンが飛ぶと再認可が必要**。

---

## 5. 現在の状態

**本番稼働中。** 毎日 autopilot でショートが自動投稿されている（バックエンドと ngrok は launchd で常駐）。

### 公開実績DB（`data/video_publish.db` の `video_status`）— 2026-09-01 修正

`video_status` は **2026-06-07 を最後に更新が止まっていた**。運用が
`gen_type="short"` の単体公開に移ったのに、その経路
（`api_phase4._start_single_short_publish`）と手動スクリプト経路
（`youtube_uploader.upload_video`）がどちらもこのテーブルに書いていなかったため。
`api_phase3` のペア公開と PublishDialog だけが書き手だった。

これを起点にしていた次の2つが静かに死んでいた:

- `pipeline/analytics/pdca_report.build_report()` — 期間内の動画が0件になり、
  ショート/メインの振り分けも登録者ソース分析も全部 `unknown` に落ちる
- `api_improvement._published_videos_for_channel()` — いいね率改善ループが
  毎回「公開済みの動画がまだありません」で空振り

対応:

| やったこと | ファイル |
|---|---|
| 記録を1箇所に集約（`is_short` / `title` カラムも冪等 ALTER で追加） | `backend/pipeline/publish_log.py`（新規） |
| `upload_video` 成功後に記録（手動スクリプト・clip_factory を含む全経路） | `backend/pipeline/youtube_uploader.py` |
| autopilot の単体ショート/メイン公開から記録 | `backend/api_phase4._record_publish_status` |
| 6〜8月の欠損 496 本を `analytics.db` から埋め戻し（API不使用・冪等） | `backend/backfill_video_status.py` |
| 同じ `video_id` の重複集計を防止 / 記録済み `is_short` を優先 | `pipeline/analytics/pdca_report.py` |

検証: scp-lab の `subscriber_sources` が「全部 unknown」から
`shorts 100% / 0.626 登録per1000再生` に復旧。

> ⚠️ **2026-09-02 に見つかった落とし穴 — `published_at` で集計してはいけない。**
> 予約公開（autopilot の通常経路）で入る行は `status='scheduled'` / **`published_at` が NULL** のまま。
> そのため `video_status` の `max(published_at)` は **08-31 で止まって見える**が、実際には
> 09-01 の `ryQIYHgujm4`・`LJpzN0NJFBw`、09-02 の `MWdbvHEeNhc`・`UKKWkdWN1MI` が
> `scheduled` として記録されている。**日次の公開本数を数えるときは `status` と挿入時刻で見ること。**
> あわせて **09-01 09:00 に即時公開できた scp-lab の `iAHGnvpHJwk` は `video_status` に1行も無い**。
> 即時公開経路の記録漏れが残っている疑いがあるので、次に触るときはここを確認する。

```bash
python3 backend/backfill_video_status.py --dry-run   # 欠損の件数だけ見る
python3 -m unittest tests.test_publish_log           # backend/ で実行
```

### ショート投稿タイトルの取りこぼし — 2026-09-01 修正

`generate_descriptions()` はメイン説明文の先頭にだけ `タイトル: ...` 行を書いており、
ショート説明文には書いていなかった。そのため `_read_desc()` が `title=""` を返し、
autopilot が `job.title + "【ショート】"` のフォールバックに落ちて、
`short_series_name` / `defaults.short_title_hashtags` / `short_title_core_max` で
組んだタイトルが **一度も YouTube に届いていなかった**（`#shorts` すら付いていない）。
実測: yokai-watch の8月投稿 39 本中 37 本がこの経路。

### 2026-09-01 のマーケ改善

**fake-paper（再生4,189・登録0）** — 他chとの比較で分かったこと:

| 指標 | fake-paper | scp-lab | daily-science |
|---|---:|---:|---:|
| 高評価率 | 0.43% | 0.46% | 0.46% |
| 平均視聴維持率 | **27.6%** | 38.3% | 57.2% |
| 登録/1000再生 | **0.00** | 0.79 | 0.37 |

高評価率は他chと同水準なので「刺さっていない」のではない。差は
**(a) 最終行に『高評価』の語が無い唯一のチャンネルだったこと**（`cta_fallback` も未設定で
`cta_enforcer` の文言をチャンネル側から制御できなかった）と、
**(b) 維持率27.6%＝全ch最下位**（実台本 228〜302字で設定帯 190〜235 を常に超過）。
→ 7行目を高評価→登録の順に、尺を 170〜210字に、2行目の「架空の掲載誌名＋研究機関名」を
リスナーの食いつきに差し替え（全ch共通の離脱地点である再生位置20%に報酬が無かった）、
タイトルの `#フィクション` を除去（オチの先出し）。

> ⚠️ fake-paper は電話認証未完了＝**カスタムサムネイルが無効**。`thumbnail_template` を
> いじっても YouTube 側には反映されない。サムネで手を打つには先に電話認証が要る。

**yokai-watch（登録0.28/1000再生）** — 高評価率 0.365% は6ch中5位。
実測四分位（n=322）で 0.2-0.4% 帯の登録転換は 0.32 なので、観測どおり。
`cta_fallback.like` の「ゾッとしたら高評価を押してね」は怖がらなかった視聴者を全部こぼすので
条件を外した。あわせて 30日以内に再投稿して公開3日目の再生が 1/8〜1/10 に沈んだ
「コマさん」「エンマ大王」を `theme_blacklist` に追加。

> 注: 08-20〜08-29 の再生崩壊（年齢を揃えた公開3日目の中央値 1,685 → 416）は
> テンプレ型タイトル（`1分妖怪ファイル #N：👁️〇〇に隠された3つの秘密…`）が原因で、
> 08-31 の PDCA が `title_style` と `short_series_name` を直して対処済み。
> 絵文字を足していた `title_emoji_injector` も 2ch-matome 以外では無効化済み。

### カスタムサムネイル（電話認証）

カスタムサムネイルの利用には YouTube の電話番号認証が必要。API からは認証できないため、チャンネルごとに手動で実施する。

| チャンネル ID | 電話認証 | カスタムサムネイル |
|---|---|---|
| `daily-science` | ✅ 済 | ✅ 有効 |
| `scp-lab` | ❌ 未完了 | ❌ 無効 |
| `pokemon-lab` | ❌ 未完了 | ❌ 無効 |
| `yokai-watch` | ❌ 未完了 | ❌ 無効 |
| `2ch-matome` | ❌ 未完了 | ❌ 無効 |
| `fake-paper` | ❌ 未完了 | ❌ 無効 |
| `company-facts` | ❌ 未完了 | ❌ 無効 |
| `akashic-librarian` | ❌ 未完了 | ❌ 無効 |
| `clip-lab` | ❌ 未完了 | ❌ 無効 |
| `clip-fukada` | ❌ 未完了 | ❌ 無効 |
| `clip-kaneko` | ❌ 未完了 | ❌ 無効 |

**認証手順:** YouTube Studio → 設定 → チャンネル → 機能の利用資格 → 「電話番号を確認」

### 台本 A/B テスト（Claude vs GPT）

台本生成を **Claude（自己生成）** と **GPT（Claude in Chrome 経由）** の 2 系統で並行運用し、データドリブンで勝者を決める。

| 項目 | Claude 系統 | GPT 系統 |
|---|---|---|
| 生成方法 | Claude タスク内で自己生成（API 不要） | Claude in Chrome で ChatGPT スレッド上に会話して生成 |
| API 依存 | なし（Claude 自身が書く） | **API 直叩き禁止。** 必ず ChatGPT の Web UI スレッド経由 |
| スレッド管理 | — | チャンネルごとに ChatGPT スレッドを 1 つ維持 |

> ⚠️ **GPT 側を ChatGPT スレッド経由にしている理由:** ユーザー（ザキ）が同じスレッドから横で介入・修正できるようにするため。API で叩くとその会話コンテキストが失われる。

**運用フロー:**

1. 投稿時に `script_source` メタデータ（`"claude"` | `"gpt"`）を記録
2. 一定本数が溜まったら YouTube Analytics で **再生数・維持率・エンゲージメント** を比較分析
3. 勝者を標準採用

**OpenAI API の用途:** 画像生成（`gpt-image-1`）**のみ**。台本生成には使わない。

### 未コミット変更: **あり（114 件）**

| 種別 | 件数 | 中身 |
|---|---:|---|
| リネーム（`R`） | 17 | `agent/` → `agent_deprecated/` 一式（旧・内蔵エージェントの退役） |
| 変更（`M`） | 35 | `backend/main.py` / `auto_comment.py` / `auto_scenario/generator.py` / `theme_queue.py` / `post_upload.py` / `video_generator.py`、および `data/` 配下の実行結果（channels 8件・pdca-memory・analytics・reports・series_links・scenarios の index） |
| 未追跡（`??`） | 62 | `backend/pipeline/` に新規追加された演出・最適化モジュール群（`comment_bait_injector.py` `completion_rate_optimizer.py` `contrast_amplifier.py` `cross_channel_bridge.py` `cta_rotator.py` `curiosity_gap_enforcer.py` `hook_ab_selector.py` `originality_guard.py` `retention_feedback_loop.py` `round6〜8_enhancer.py` `swipe_stop_injector.py` ほか多数） |

> ⚠️ **未追跡 62 ファイルは一度もコミットされていない実装。** `data/` 配下の差分は日々の実行で常に動くので、
> コミットするならコード（`backend/`）と実行結果（`data/`）を分けて積むこと。

---

## 6. 残タスク

### 2026-09-01 に判明して未解決のもの（最優先）

0-a. 🚨 **OAuth リフレッシュ失敗が 2ch から 10ch に広がった（2026-09-01 深夜に判明・最優先）。**

   > **【2026-09-02 深夜 追記】まだ直っていない。2日連続で同じ損失が出ている。**
   > 09-02 の実績は **生成9本 → 公開2本**（akashic-librarian `MWdbvHEeNhc` / fake-paper `UKKWkdWN1MI`）。
   > 残り7本（scp-lab 09:00・19:00 / daily-science / company-facts / pokemon-lab / 2ch-matome / yokai-watch）は
   > 全て「⚠️ 自動公開スキップ — トークン失効のため要再認可」。切り抜き4ch も別要因で全滅（0-a-3）。
   >
   > **09-02 の PDCA が示す失効/正常の切り分け（`data/reports/latest.md` 冒頭）:**
   >
   > | 状態 | チャンネル |
   > |---|---|
   > | ❌ 失効 (9ch) | clip-fukada / clip-kaneko / daily-science / scp-lab / yokai-watch / 2ch-matome / pokemon-lab / company-facts / clip-lab |
   > | ✅ OK・残り4.62日 (4ch) | akashic-librarian / clip-animal / fake-paper / socio-rx |
   >
   > **正常な4chは「残り4.62日」＝GCP 同意画面がテスト中のときの7日上限に乗っている。**
   > つまり**放置すると 09-07 前後にこの4chも同じように失効する**。
   > 再認可だけでは同じことが7日おきに起きるので、**GCP 同意画面の「本番」公開**
   > （https://console.cloud.google.com/auth/audience / project 844705815004）まで
   > やらないと恒久解決しない。これを 0-a の本命の打ち手として扱うこと。
   >
   > `backend/pipeline/youtube_oauth.py` と `backend/check_youtube_tokens.py` は 09-02 に更新されているが、
   > `backend/pipeline/credentials/client_secret.json` は依然として無く、
   > アップロード経路は `FileNotFoundError: client_secret.json が見つかりません` で落ち続けている（09-02 に5回）。
   `logs/backend.log` の集計では
   daily-science 40件 / scp-lab 27 / yokai-watch 26 / pokemon-lab 26 / company-facts 26 /
   clip-lab 25 / fake-paper 24 / clip-kaneko 17 / akashic-librarian 14 / clip-fukada 13
   ＝ **稼働中の全チャンネルで `invalid_grant: Token has been expired or revoked.`**。
   もともと clip-fukada / clip-kaneko だけの問題として記録していたが、そうではない。

   併発している二次障害（どちらも実害が出ている）:
   - **投稿は通っているが分析が全部死ぬ。** 09-01 23:00 の PDCA レポートは 12ch 中 **9ch が
     「登録者ソースが取得できないため判断保留」＋ 0本/0再生**。数字が出たのは
     akashic-librarian / fake-paper / 2ch-matome の3つだけ。**この状態の PDCA を根拠に
     コンフィグを触ってはいけない**（前日までの実測値のほうが信用できる）。
   - **切り抜き系はアップロード自体が落ちる。** clip-kaneko は 09-01 20:30 に動画を焼くところまで
     成功したが `youtube_uploader.get_authenticated_service()` が
     `FileNotFoundError: client_secret.json が見つかりません` で終わっている。

   **壊れた時刻はほぼ特定できている: 2026-09-01 の 11:36〜11:40。**
   同日 09:00 の scp-lab は**正常に公開できている**（`iAHGnvpHJwk`）。
   その後 11:40 の再起動（`cta_enforcer` 反映のためのもの）を挟んだ 17:00 以降の枠から
   全部トークン失効になった。`backend/pipeline/credentials/` の**ディレクトリ mtime が 09-01 11:36**。
   ＝ この再起動の前後で認可情報の置き場に何かが起きている。**まずここを疑うこと。**

   現状: `backend/pipeline/credentials/` には **`client_secret.json` が無く、`oauth.db` は 0 バイト**
   （May 21 作成のまま）。一方で `data/youtube_tokens.db`（61KB）は生きている。
   ＝ 認可情報の置き場が2系統あり、片方が空。
   コードでは直せない。**GCP から OAuth クライアント JSON を落として置き直し、管理画面から再認可する。**
   確認: `python3 -c "import sys;sys.path.insert(0,'backend');from pipeline import youtube_oauth as yo;print(yo.get_credentials_for('clip-fukada'))"`

   **09-01 の公開実績（生成9本 → 公開できたのは3本）:**

   | 枠 | ch | 結果 |
   |---|---|---|
   | 09:00 | scp-lab | ✅ 公開 `iAHGnvpHJwk`（※サムネ設定は 403。電話認証未完了なので既知） |
   | 17:00 | company-facts | ❌ 自動公開スキップ（トークン失効） |
   | 17:00 | daily-science | ❌ 自動公開スキップ |
   | 17:30 | pokemon-lab | ❌ 自動公開スキップ |
   | 18:00 | 2ch-matome | ❌ 自動公開スキップ |
   | 18:45 | akashic-librarian | ✅ 予約 `ryQIYHgujm4` |
   | 19:00 | yokai-watch | ❌ 自動公開スキップ |
   | 19:00 | scp-lab | ❌ 自動公開スキップ |
   | 19:30 | fake-paper | ✅ 予約 `LJpzN0NJFBw` |
   | 切り抜き4ch | — | ❌ 全滅（0-a-3） |

   > 動画自体は生成済みで手元にある。**再認可さえ通れば手動で上げ直せる。**

0-a-2. **`ANTHROPIC_API_KEY` 未設定で 09-01 も海外バイラル枠が2回とも落ちた。**
   `clip-lab` の 20:45 枠は 08-31・09-01 とも `TranslationUnavailable`。
   依頼書だけ `data/analytics/viral_translation_pending/` に溜まっている（`viral_1w2l6rn.json` /
   `viral_1w45v54.json`）。PDCA レポートの Claude 分析も全ch「スキップ（ANTHROPIC_API_KEY 未設定）」。
   翻訳を機械任せにしない設計は正しいので、**キーを入れるまでこの枠は動かない**と理解しておく。

0-a-3. **切り抜き4chが実質全滅している（09-01 実績）。**
   | ch | 09-01 の結果 |
   |---|---|
   | `clip-lab` 17:45 | 失敗「未使用の切り抜き区間が残っていません」（ヒカキン素材を使い切った。素材追加が要る） |
   | `clip-lab` 20:45 | 失敗（ANTHROPIC_API_KEY） |
   | `clip-fukada` 20:00 | 失敗「尺条件に合う区間なし: 急にどうした？」。※この素材は媚薬PR回で本来除外対象。区間ゲートは効いている |
   | `clip-kaneko` 20:30 | 生成成功 → **アップロードで OAuth 失敗**（0-a） |
   | `clip-animal` 18:00 | 失敗「clip.sources が空で external_sources も無効」（一度も成功していない） |
   → 切り抜き系の最終公開は **clip-lab の 08-27 が最後**。5日間 1本も出ていない。

0-b. **CTA 遵守率の実測は 2026-09-02 以降に取り直すこと。**
   `pipeline/cta_enforcer.py` は 09-01 10:30 に入ったが、稼働中バックエンドは
   08-31 起動でこのコードを持っていなかった（09-01 11:40 に再起動して反映済み）。
   `scripts/verify_cta_20260901.py` が見ている 08-25〜31 のアーカイブは全て補正前なので、
   高評価37% / 登録36% / 両方19% という数字は**修正の効果を測っていない**。

0-c. **`data/channels/` 以外に設定を書かないこと。** `data/channels_orchestrator/` は
   symlink になった。詳細は `docs/CHANNEL_CONFIG_SOURCE_OF_TRUTH.md`。
   確認: `python3 scripts/unify_channel_configs.py --check`

0-d. **既存の赤いテスト2件**（今回の変更とは無関係）:
   `tests.test_description_blocks.TestRealChannelHashtags` が `clip-animal` /
   `clip-kaneko` の `short_hashtags` 本数で落ちる。
   `tests.test_cta_enforcer` は `pytest` 未導入で import エラー。

### インフラ・運用

1. ~~未コミット 114 件の整理とコミット~~（2026-09-01 にコード分をコミット済み）
2. ~~**Git リモートを用意して push**~~ — ✅ **2026-09-02 完了**（→ §3）。以後はコミットしたら push まですること
3. **`com.youtube-factory.pdca` を load**（毎日の PDCA レポート生成が止まっている）
4. **`com.youtube-factory.agent` の扱いを決める**（`agent/` は退役済み＝この plist は今 load すると失敗する。削除するか ai-orchestrator に寄せる）

### 機能・コンテンツ

5. Anthropic API キー無効（401）問題 — 分析を Claude タスク方式に移行してキー依存を廃止する方針だった
6. Analytics API の views 取得が壊れている（時間帯分析が全部 0 を返す）
7. `daily-science` の OAuth `redirect_uri_mismatch` — UI からの再認可がブロックされている
8. GCP consent screen を Published にする（永続 OAuth 用。ユーザー操作が必要）
9. 再生 0 の動画を非公開にする（daily-science 21本 + scp-lab 29本の棚卸し）
10. OpenAI billing hard limit で `gpt-image-1` が使えない → 復旧後に `gen_images.py` を実行すれば完了
11. TikTok セットアップ（アカウント作成 → 開発者登録 → 審査申請）。手順は `docs/TIKTOK_SETUP.md`
12. 過去の SCP 非公開動画 5本（`dItYJed2Qog` 等）の手動公開 or スコープ拡張
13. ~~`akashic-librarian` の autopilot 有効化判断~~ — **決着済み。`enabled: true` で稼働中**
    （2026-09-01 確認。直近14日で6本公開・登録者2・平均再生 599.8）
14. テーマ重複が多い → 重複閾値の厳格化。**2026-09-01 時点で `2ch-matome` は類似ペア 5 件
    （閾値 0.62）まで下がっている**（08-31 は 15 件）。最悪は「ワイ、◯◯歴N年やけど質問ある？」
    テンプレの相互重複（0.667）。テンプレ自体を絞るのが早い
15. `clip-animal` の素材が空（→ §1 の表の注記）。素材を入れるか autopilot を切るか
16. `socio-rx` は autopilot も analytics も無効のまま。運用するのかしないのかを決める

---

## 7. 既知の制約・注意点

- **`data/` を消すな。** チャンネル設定・テーマキュー・PDCA メモリ・OAuth トークンが全部ここ。設定と実行結果が同居している。
- **`youtube_factory_full_spec.md` は約 433KB。** 丸ごと読むとコンテキストが飛ぶ。必要な節だけ grep すること。
- **Python は 3.9（システム標準）。** launchd も `/usr/bin/python3` を直指定。venv を使っていないので、`pip install` はシステムに入る。
- **`agent/` は退役済み**（`agent_deprecated/`）。自律運用は独立リポジトリの `ai-orchestrator` 側に移っている。
- YouTube Data API のクォータ上限に注意（分析ジョブを連打すると投稿ができなくなる）。
- ngrok は固定ドメイン契約。ドメインが変わると OAuth の redirect_uri が全部ズレる。
- バックエンドを `--reload` で起動すると、外部から叩いている処理が途中で死ぬ。`.command` スクリプト経由の再起動を使う。

---

## 8. 前回成功した方法

### バックエンドの起動・再起動

```bash
# launchd 経由（推奨。KeepAlive で落ちても復活する）
launchctl kickstart -k gui/$(id -u)/com.youtube-factory.backend

# 手動起動する場合（backend/ で実行すること。main:app のパス解決がカレント依存）
cd /Users/ayukiyamazaki/Developer/youtube-factory/backend
python3 -u -m uvicorn main:app --host 0.0.0.0 --port 8000
```

ルートに `restart_backend.sh` / `restart_backend.command` / `RestartBackend.app` があり、Finder からも再起動できる。

### 動作確認

```bash
curl -s http://localhost:8000/health          # → 200
curl -s https://agreeing-corrode-shabby.ngrok-free.dev/health   # 外部からの疎通
```

### 単発の動画生成・投稿

ルートの `.command` / `backend/run_*.py` がチャンネルごとの実行入口になっている。

```bash
cd /Users/ayukiyamazaki/Developer/youtube-factory
python3 backend/run_daily_science.py       # 日常科学
python3 backend/run_scp_short_upload.py    # SCP ショート投稿
python3 backend/run_daily_pdca.py          # PDCA レポート生成 → data/reports/latest.md
```

### フロントエンド

```bash
cd frontend && npm run dev     # http://localhost:3000
npm run typecheck              # tsc --noEmit
```

### 本番 API の叩き方

`/api/*` は JWT 認証。`APP_PASSWORD` でログインしてトークンを取り、`Authorization: Bearer` を付ける
（ai-orchestrator も同じ手順で叩いている。実装は `ai-orchestrator/src/tools/youtube_factory.py` が参考になる）。

---

## 9. 2026-09-03 指揮者定時実行の記録

### 🚨 OAuth: 全13chが失効（最優先）

`data/youtube_tokens.db` 実測（09-03 10:04）で **残寿命がプラスのチャンネルはゼロ**。
09-02 の「09-07 前後に全滅」という予測より5日早く、09-02 15:01 には既に全滅していた。

| 失効時刻 | ch |
|---|---|
| 08-31 05:07 | clip-fukada / clip-kaneko |
| 08-31 15:00 | daily-science |
| 09-01 03:04〜06 | 2ch-matome / clip-lab / company-facts / pokemon-lab / scp-lab / yokai-watch |
| 09-02 15:00〜01 | akashic-librarian / clip-animal / fake-paper / socio-rx |

再認可だけでは7日ごとに再発する（08-24・08-31・09-02 で既に3回）。
恒久策は GCP 同意画面の本番公開 → https://console.cloud.google.com/auth/audience?project=844705815004
実行手順は `restart_and_trigger_20260903.command` に落としてある。

`video_metrics` が moviepy 6ch中5chで 08-31 停止しているのも原因は同一（データ基盤の別障害ではない）。
このため **09-02 の speed 引き下げ実験は変更後データが1件も無く、09-05 期限の判定ができない**。
期限は再認可後にデータが揃うまで延長。

### ★ A/B判断は必ずチャンネル内対照で行うこと

これまでのタイトル分析はチャンネルをまたいで あり/なし を比較しており、
**「どの語が効くか」ではなく「どのチャンネルが強いか」を測っていた**。
登録/千再生は company-facts 0.73 vs 2ch-matome 0.16 と 4.6倍違うため、
強いチャンネルに多い語は何であれ有意に見えてしまう。

同一ch内で比較し直した結果（n=286・公開07-05以降・100再生以上）:

| 特徴 | 有 | 無 | 効果量 | 判定 |
|---|---:|---:|---:|---|
| 「正体」 | 0.64 | 0.42 | 1.53倍 | **強く採用**（4ch全て同方向） |
| 数字＋単位 | 0.61 | 0.39 | 1.56倍 | 採用 |
| 「実は」 | 0.51 | 0.49 | 1.03倍 | 効果なし |
| 絵文字 | 0.48 | 0.47 | 1.03倍 | 効果なし |
| 「なぜ」 | 0.42 | 0.45 | 0.94倍 | 効果なし |
| 連番 #NN： | 0.40 | 0.48 | 0.84倍 | 負・禁止継続 |
| 「？」疑問形 | 0.37 | 0.60 | 0.62倍 | **負・必須化を撤回** |

**08-23 の「疑問符2.16倍」「なぜ1.58倍」「実は0.70倍で禁止」は全て交絡による誤りとして撤回した。**
再現したのは「正体」（08-23夜の2.10倍 → 1.53倍）と連番の劣後（08-31）のみ。

### 高評価率 → 登録（08-29 の発見が再現）

n=339 で四分位ごとに 0.23 / 0.37 / 0.52 / 0.75 と単調増加、**Q4はQ1の3.3倍**。
登録の観測レバーは終盤維持率でも尺でもなく高評価率、という結論は維持。

### 維持率

6ch全てが再生位置15〜25%地点に最大離脱（-0.15〜-0.21）。
差が出るのは底の深さで、50%地点は company-facts 0.62 に対し他ch 0.33〜0.43。
原因は後半の情報密度（他chは4行目をたとえ話で埋めて数字が途切れる）。
→ 4行目・5行目に新規数字を1つずつ置くルールを全chへ追加。

### 適用済みコンフィグ変更（バックアップ `*.bak_pdca_20260903b`）

`title_rules` に `require_shoutai_per_batch=1` / `require_number_with_unit=true` /
`require_question_mark=false` を追加。`theme_priority.title_style` を断定形＋数字既定に変更。
`short_format.extra_rules` へ高評価CTA優先と4・5行目数字必須を挿入。
テーマキュー +28本（pokemon-lab 3→15 ※枯渇寸前 / daily-science 12→18 / scp-lab 10→16 / yokai-watch 15→19）。

**反証条件（09-08）**: 「正体」の効果量が1.2倍を下回れば必須化を撤回。
断定形 vs 疑問形の再比較、50%地点維持率が0.45を超えたかも同日に確認する。

### 要対応（登録転換の構造問題）

**2ch-matome は AVP 52.7%＝2位・平均再生912＝3位と閲覧指標は良いのに、登録/千 0.16 で最下位**
（company-facts の1/5）。尺や速度ではなく企画構造の問題。次回 company-facts型
（継続的に得する情報）の要素を投入して比較する。未着手。

**clip-lab は平均再生4,136で断トツ首位だが登録は0人**。09-02 メモの「1本あたり再生1位」は
事実だが、再生数だけで素材追加の優先度を判断すると過大評価になる点を併記しておく。

### 指揮者の実行環境（毎回ここで詰まる）

指揮者はサンドボックス Linux VM 上で動作し、**Mac の `localhost:8000` へ到達できない**。
Phase 1（API実績取得）と Phase 4（トリガ）は `.command` に落として Mac 上で実行する必要がある。

ただし **autopilot は Mac 上で既にスケジュール稼働している**（09-03 も scp-lab が 08:15 に発火）。
company-facts 16:15 / 2ch-matome 17:15 / scp-lab・yokai-watch 18:15。通常は手動トリガ不要。

09-02 の `.command` が使っていた `POST /api/autopilot/{ch}/trigger` は**存在しないパス**。
正しくは `POST /api/channels/{ch}/autopilot/run-now` ＋ `Authorization: Bearer`
（`POST /api/auth/login` に `APP_PASSWORD` を投げてトークン取得）。09-03 版で修正済み。

生成物: `reports/youtube_analysis_20260903.xlsx` / `restart_and_trigger_20260903.command` /
`MEMORY_UPDATE_20260903.md`

### 2026-09-03 検証で判明した重要事項（コンフィグを触る前に必ず読む）

**1. `title_rules` は backend が読まない。** `require_*` も `max_chars` も `forbid_patterns` も
参照コードが1件も無い。`generator.py` が実際に読むのは `theme_priority`（`title_style` /
`good_examples` / `viral_hooks`）11箇所、`short_format` 9箇所、`voice_style.style_rules` 3箇所のみ。
**読まれないフィールドに書いた施策は、適用済みに見えて何も起きていない。**
変更前に必ず grep で確認すること。09-03 に `title_rules.enforced_by_backend=false` と注記済み。

**2. `theme_priority.title_style` は上書きせず追記する。** 09-03 に6ch一律で上書きしてしまい、
2ch-matome のスレタイ型（一人称「ワイ」・語尾「w」）、scp-lab のSCP番号必須、
company-facts の企業名必須が消えた。しかも共通文の「断定形を既定・疑問符は必須にしない」が
2ch-matome の勝ちパターンと矛盾していた。修正済み（旧文＋`──【日付 追記】──` の形）。
**6chに同じ文字列を書き込んでいる時点で、ほぼ確実に何かを消している。**

**3. 効果量の n を必ず併記する。** 「正体」が4ch全て同方向というのは正しいが、
pokemon-lab は n=3 で採用基準ギリギリ。09-08 の再測定では pokemon-lab を除いた3chの効果量も併記する。

---

## 10. 2026-09-05 夜の記録（nightly-full-progress）— 過去メモの訂正を含む

全文は `MEMORY_UPDATE_20260905_night.md`。ここには**過去の記述を訂正する事実だけ**を残す。

### 10-1. 訂正: ChatGPT スレッド URL の置き場

09-04 メモは `image_generation.chatgpt_thread_url` と書いたが誤り。
正しくは **`data/channels/<ch>.json` の top-level `chatgpt_thread_url`**。
09-05 時点で **13ch中12ch が登録済み、未登録は `2ch-matome` のみ。**

### 10-2. ★ 新事実: `autopilot.schedule.times` の時刻は「公開時刻」であり、生成はその45分前

`backend.log` の `Autopilot scheduled for ... 17:00 JST (生成開始 16:15 / 公開 17:00)` が根拠。
**`job_queue.json` の `created_at` を公開時刻と読むと45分ずれる。**
09-05 の実測: 2ch-matome 20:17 生成 → 21:00 公開枠（新枠どおり）。

### 10-3. 09-05 の投稿枠変更とサムネA/B修正は**反映済み**

`apply_orchestrator_20260905.command` は実行された。根拠2点:
1. `backend.log` に本日の `Application startup complete.` があり、再起動後の `restore_all()` が
   新枠（2ch 21:00 / scp-lab 13・17・19時 / yokai 17:45）を登録している。
   **再起動は 12:15 と 12:45 の生成の間。**再起動日は旧枠と新枠が重なるため
   scp-lab だけ4本出ている（通常は3本）。
2. `thumbnail_ab_tests.channel_avg_ctr` が ch内で単一値に是正された
   （daily-science 0.03368 / scp-lab 0.01454）。`42.909` は消えた。
   ただし `status` は 19件すべて `monitoring` のままで切替はまだ発生していない。

### 10-4. ★ 施策の種類で反映タイミングが違う

- **`style_rules` / `max_count` は実行ごとに読み直されるので、config を書き換えた瞬間から効く。**
- **投稿枠（`autopilot.schedule.times`）は cron なのでバックエンド再起動が要る。**

09-05 の「正体」ルール上限は、朝の書き換え（10:12 頃）より前に生成された3本にのみ残り、
以降の30本には1本も混入しなかった（本日 3/33 = 9%。09-03 は 71%）。
**config を書き換えた日は、書き換え時刻より前に生成された分が旧ルールで公開される。**

### 10-5. 訂正: `theme_seeds` はテーマキューではない

キューは **`autopilot.theme_queue`**。`theme_seeds` は別物（件数が合わない）。

### 10-6. `retention_curve` のスキーマ

列は `(video_id, channel_id, curve, fetched_at)` のみ。**`curve` は JSON 文字列**で、
`elapsed_ratio` のような列は存在しない。比率は JSON をパースして取り出す。

### 10-7. `.env` の場所

リポジトリ直下ではなく **`backend/.env`**。09-05 実読みで
`ANTHROPIC_API_KEY` / `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` が未設定、`OPENAI_API_KEY` は設定あり。

### 10-8. ★ 数え方の訂正 — 切り抜き系は `upload_done` を出さない

ゆっくり系は `upload_done` を、**切り抜き系は `✅ アップロード完了` しか出さない。**
`upload_done` だけで数えると切り抜きが丸ごとゼロに見える。
正しくは `backend.log` の `watch?v=` のユニーク数で数えること。

**09-05 の実績は合計33本（ゆっくり25 + 切り抜き8）で過去最多**
（scp-lab 4 / 他ゆっくり7ch 各3 / clip-kaneko 3 / clip-lab 2 / clip-fukada 2 / clip-animal 1）。

### 10-8b. `ANTHROPIC_API_KEY` 未設定の影響範囲は限定的だった（09-04 メモの訂正）

09-05 の実測では **clip-kaneko は3枠すべて成功、clip-lab も local 2枠は成功**している。
**止まっているのは `clip-lab` の 20:45 `engine: viral` 枠だけ。**
local エンジンは OpenAI で代替されて動く。翻訳依頼書は10件に積み上がっている。

**あわせて `clip-fukada` の「素材ゼロ」ブロッカーは解消**（09-05 に2枠とも公開）。
`clip-animal` は `clips_per_video=1` のため2枠中1枠のみ成功。

### 10-9. サムネ403 は 33本中27本（82%）— 切り抜き4chも対象

403 を免れたのは daily-science 3本・akashic-librarian 3本のちょうど6本だけ。
絶対数は 09-04 の13本から **27本へ倍増**。
**電話認証が通っているのは `daily-science` と `akashic-librarian` の2chのみで、
切り抜き4chを含む残り11chはすべて 403。**
scp-lab の CTR 1.54%（全ch最下位・表示回数は全社の56%）は、A/B 以前にサムネが
設定できていないことが主因の可能性がある。**電話認証をサムネA/Bより先に行うこと。**

### 10-10. `video_metrics` の取得破損は継続・悪化

`views=0 かつ impressions>0` が 09-04 の7件 → 09-05 は **15件**。
累積 `views` の前日割れも 17動画（-4,814）。**取得後の整合チェックが必要。**
なお日次差分はスナップショット取得時刻のブレに弱いので、**1日単位の増減で判断しないこと。**

---

## 11. 2026-09-06 夕の記録 — 切り抜きchの「全て切り抜き済み」と残作業の消し込み

### 11-1. ★ 真因: 使い切った元動画が `prepare_limit` の枠を食い潰していた

`clip-kaneko` が 08:00・14:00 の2枠とも
「全ての元動画が切り抜き済みです（clips_per_video を上げるか元動画を増やしてください）」で
落ちていた件。**エラー文のとおりに `clips_per_video` を上げるのは誤対処。**

`external.discover_external_sources` は候補を **(weight, 再生数) 降順**に並べ、
**上から `prepare_limit` 本を無条件に**用意していた。`pick_source` は
「切り抜き済み < clips_per_video」でしか在庫を見ないので、
**上位が全部使い切られた時点で候補がゼロになる**。下に未使用の回が何本あっても届かない。

09-06 の実測（clip-kaneko / `UCw_7_DkX4ftnQJJtZTrCOOQ`）:

| | 本数 |
|---|---:|
| clippable な候補 | 25 |
| うち再生数上位 8本（= `prepare_limit`） | **全て 4/4 で使い切り** |
| 未使用（0/4）のまま候補に上がらなかった回 | **17** |

対処: `discover_external_sources` が**使い切った候補を `limit` に数えない**ようにした
（`clips_per_video` 以上使っている回は飛ばして次の候補へ）。在庫判定を `build_source` の
**前**に置いてあるので、使い切った回に yt-dlp（字幕取得）を叩き直すこともない。
`clips_per_video` も `prepare_limit` も**触っていない**（同じ元動画から取り過ぎる方向なので、
素材が残っている間はやらない）。

検証: `CLIP_CHANNEL_ID=clip-kaneko python3 run_clip_channel.py --dry-run` で
「切り抜き済みの元動画を 8 本飛ばしました（clips_per_video=4）」→ 既出0本の回を選んで区間確定。
回帰テストは `tests/test_clip_factory.py::TestExhaustedSourcesDoNotFillPrepareLimit`（3件）。

> ⚠️ **コード変更なのでバックエンドの再起動が要る**（稼働中プロセスは旧 `external.py` を抱えている）。

### 11-2. `clip-animal` — `clips_per_video` は既に解決済み。残るのは素材側

`clips_per_video` は 09-05 に 1→3 済み・バックエンドも 09-06 00:34 起動で反映済みで、
09-06 09:30 枠は成功している。11-1 の修正で「使い切った回が枠を食う」問題も消えた。

**残っているのは在庫そのもの。** 09-06 実測で clippable 8本のうち
**6本が「字幕なし」で `clip_subtitle_misses.json` 入り**、1本が使い切り、
実際に使えるのは1本だけだった。CC BY の動物動画は字幕が無いものが多く、
行タイムラインを作れないので原理的に切れない。
`creative_commons.queries`（3本）と `videoDuration=long` × `max_duration_sec=3600` の
組み合わせで母数も小さい。**増やすならクエリか許諾済み allowlist チャンネル。**

### 11-3. `2ch-matome` の ChatGPT スレッドを登録（13ch すべて登録済みに）

```
python3 scripts/image_bridge.py thread set 2ch-matome https://chatgpt.com/c/6a9af5b9-1548-83ee-bb2c-29a3157cb464
python3 scripts/image_bridge.py backfill      # → thread_url を更新した: 3 件
python3 scripts/image_bridge.py missing       # → 全チャンネルにスレッドが登録されています
```

保存先は **`data/channels/2ch-matome.json` の `image_generation.chatgpt_thread_url`**
（他12chと同じ置き場。§10-1 の「top-level」は 09-06 の移設前の記述）。

### 11-4. `ANTHROPIC_API_KEY` — **キー無しで動かす方法は無い**（実測して確定）

`backend/.env` の 18行目にキーはあるが**コメントアウトされたまま**で、
その値を実際に `POST /v1/messages` へ投げたところ **401 `API key is invalid.`**。
＝ コメントを外しても直らない。**新しいキーを人が発行して入れるまで
`clip-lab` 20:45（`engine: viral`）は動かない。**

キー無しの迂回路も**設計上存在しない**:

- `translate.py` は「翻訳を機械任せにすると意味の通らない字幕がそのまま公開される」ので
  **意図的にフォールバックしない**（`TranslationUnavailable` で枠ごと落とす）。
- 依頼書（`data/analytics/viral_translation_pending/`。現在10件）を Claude Code が埋める経路はあるが、
  `load_pending_result` は **`request_id`（= Reddit の投稿ID）が一致したときだけ**読み戻す。
  毎日の調達は当日バズった別の投稿を拾うので、**溜まった10件が将来の枠を救うことはない**。

> 20:45 枠を国内切り抜きにフォールバックさせる選択肢はあるが、
> 「海外バイラル枠」という企画そのものを変える判断なので手を付けていない。

### 11-5. 副作用として変わった挙動（把握しておくこと）

`list_available_sources`（UI の在庫一覧・`run_clip_channel.py --list --external`）は、
**使い切った外部素材を表示しなくなった**（`remaining_clips: 0` の行が消える）。
一覧に出るのは「これから切れる在庫」だけになる。
