# youtube-factory 全仕様ダンプ

生成日時: 2026-08-19 / リポジトリ: `/Users/ayukiyamazaki/Developer/youtube-factory` / ブランチ: `main` (HEAD = `b680410`)

> **注記**: `backend/.env` の API キー・シークレット類は値を伏せています（キー名と非機密の設定値はそのまま記載）。それ以外のファイルは原文のまま貼り付けています。

## 目次

1. [チャンネル設定（data/channels/*.json 全文）](#1-チャンネル設定)
2. [バックエンド構成とエンドポイント一覧](#2-バックエンド構成)
3. [パイプラインモジュール一覧](#3-パイプラインモジュール)
4. [autopilot 設定](#4-autopilot-設定)
5. [agent の設定と状態](#5-agent-の設定と状態)
6. [launchd 設定](#6-launchd-設定)
7. [環境変数](#7-環境変数)
8. [未コミットの変更](#8-未コミットの変更)
9. [コミット履歴（直近20件）](#9-コミット履歴)
10. [data/analytics 状態ファイル](#10-dataanalytics-状態ファイル)
11. [動画生成の全ステップ](#11-動画生成の全ステップ)
12. [clip-lab の仕組み](#12-clip-lab-の仕組み)
13. [post_upload.py](#13-post_uploadpy)
14. [スケジューラの仕組み](#14-スケジューラの仕組み)
15. [YouTube OAuth 認証の状態](#15-youtube-oauth-認証の状態)

---

## システム全体像（サマリ）

| 要素 | 実体 |
|---|---|
| バックエンド | FastAPI (`backend/main.py`, 1760行) + 14 個の APIRouter。uvicorn `0.0.0.0:8000` |
| 稼働プロセス | uvicorn PID 49372（2026-08-19 02:35 起動、**launchd 経由ではなく手動起動**。`com.youtube-factory.backend` は launchctl 上 exit=1 で停止中）／agent PID 693（2026-07-13 19:30 起動）／ngrok PID 37949 |
| 外部公開 | ngrok 固定ドメイン `https://agreeing-corrode-shabby.ngrok-free.dev` → localhost:8000 |
| フロント | Next.js（別ディレクトリ `frontend/`、Vercel デプロイ） |
| スケジューラ | APScheduler `BackgroundScheduler(timezone="Asia/Tokyo")` — バックエンドプロセス内。cron は使っていない |
| 定期バッチ | launchd `com.youtube-factory.pdca` が毎日 23:00 に `backend/run_daily_pdca.py` |
| 自律エージェント | launchd `com.youtube-factory.agent` KeepAlive で `python -m agent run youtube-growth`（30分間隔） |
| チャンネル数 | 8（うち autopilot 有効 7、`akashic-librarian` のみ enabled=false） |
| 音声 | VOICEVOX (`http://localhost:50021`) |
| LLM | シナリオ生成 = OpenAI、分析/評価/判断 = Anthropic Claude。**現在 Anthropic キーは 401 invalid** |

### 現状の既知の異常（ログから確認済み）

- **Anthropic API キーが 401 invalid**。`/tmp/agent_run.log` の全サイクルが `AuthenticationError: API key is invalid.` で落ちており、agent は 2026-08-19 18:58 のサイクルも含めて**何も実行できていない**。PDCA 側も `claude_client call failed (retention_analysis)` で Claude 分析が全滅（ルールベースにフォールバック）。投稿自体は OpenAI 側で継続。
- `com.youtube-factory.backend` の launchd ジョブは停止（last exit status = 1）。実際の backend は別プロセスで手動起動されている。
- `akashic-librarian` は YouTube OAuth トークンが `oauth_tokens` に存在しない（未連携）。

---

## 1. チャンネル設定

`data/channels/` 配下。8チャンネル。以下は各 JSON の**全文**。

### チャンネル一覧（要約表）

| channel_id | 名前 | YouTube Channel ID | gen_type | autopilot |
|---|---|---|---|---|
| `2ch-matome` | ゆっくり2chスレまとめ劇場 | `UCqvn5FC_B1nj2VhlFTFw8CA` | short | 有効 |
| `akashic-librarian` | ラグナロクの司書 | `UClXnuH-KPDXnX0bn2NJlMhg` | full | **無効** |
| `clip-lab` | ゆっくり解説 切り抜きラボ | `UCbWZ5quEFE2VpHPh5TGyPCw` | clip | 有効 |
| `company-facts` | 企業のホンネ | `UCB07OOxWeKK6v86KsSYgnNA` | short | 有効 |
| `daily-science` | リコとマコトのゆっくり日常科学 | `UC1OckVkZahT3_fM6W8hD6dg` | short | 有効 |
| `pokemon-lab` | ゆっくりポケラボ | `UCGgc5REGTWRLnBiSeXXkJ5w` | short | 有効 |
| `scp-lab` | ゆっくり異常存在SCPラボ | `UCXEyJqJt9Ug94iOHdpd5a8w` | short | 有効 |
| `yokai-watch` | ゆっくり妖怪ラボ | `UCYf2lsHuHUXbj_HGmqojkUw` | short | 有効 |

### `data/channels/2ch-matome.json`

```json
{
  "id": "2ch-matome",
  "name": "ゆっくり2chスレまとめ劇場",
  "concept": "2ch／5chに立った『くだらないけど参加したくなるスレ』を、ゆっくり2人が1本30秒で実況するエンタメまとめチャンネル。『〜あげてけ』『〜当てるスレ』『質問ある？』のような大喜利・参加型スレを軸に、日常あるある・しょうもない事件・軽い下ネタで笑わせ、答えは出さずコメント欄に投げて終わる。",
  "short_series_name": "",
  "style": "yukkuri",
  "youtube_channel_id": "UCqvn5FC_B1nj2VhlFTFw8CA",
  "image_mode": "collect",
  "image_collect": {
    "provider": "auto",
    "safe_search": true,
    "license_filter": "cc",
    "max_per_query": 5,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic"
  },
  "voice_style": {
    "tone": "終始ふざけている掲示板ノリ。一人称は『ワイ』、二人称は『お前ら』。語尾は『〜やろ』『〜なんやが』『〜やで』『〜せやろ』の口語で、文末に『w』『草』を自然に多用する。丁寧語・解説口調・教訓は完全禁止。真面目な結論を出さず、変なレスに全力で乗っかって笑わせるのが仕事。軽い下ネタ・きわどい恋愛ネタも扱うが、あくまで『友達と笑う話』のノリで、いやらしい実況・煽情的な語りにはしない",
    "narrator_persona": "暇すぎてスレを立てた張本人と、それに即レスする掲示板住民。ユイが『ワイ』としてお題を出し、ゴローがレス側で茶化す・便乗する・被せる。まとめ役や解説役には絶対に回らない。答えを断定せず、最後は視聴者にお題を投げて終わる。きわどい話でも下品に踏み込まず、『それ以上言うな』とツッコむ側に回る",
    "opening_hooks": [
      "ワイの部屋から出てきた物、当ててみてくれw",
      "彼女の部屋で見つけたやつがヤバいんやが",
      "なんかPCの画面チカチカするんやが",
      "実際には存在しないけどありそうなやつあげてけ",
      "ワイ、〇〇歴10年やけど質問ある？",
      "ちょっと聞いてくれ、今えらいことになっとる"
    ],
    "forbidden": [
      "SCP",
      "財団",
      "収容",
      "[REDACTED]",
      "DATA EXPUNGED",
      "科学的に解説",
      "研究データ",
      "メカニズム",
      "妖怪",
      "ポケモン",
      "シロ",
      "クロ",
      "リコ",
      "マコト",
      "理子",
      "真",
      "ミナモ",
      "ケンタ",
      "ヒカリ",
      "ソラ",
      "セックス",
      "性行為の具体的描写",
      "性器",
      "AV",
      "風俗",
      "18禁",
      "エロ動画",
      "いかがでしたか",
      "解説します",
      "説明します",
      "教訓",
      "まとめると",
      "ポイントは3つ"
    ],
    "style_rules": [
      "一人称は必ず『ワイ』、視聴者への呼びかけは『お前ら』。敬語・丁寧語は1行たりとも使わない。『〜やろ』『〜なんやが』『せやな』『草』『w』を自然に混ぜる。",
      "冒頭3秒がすべて。1行目のスレタイは『答えを伏せた状態』で出す（『〇〇が出てきた』まで言って何が出てきたかは言わない）。何が起きたか全部言ってしまったスレタイは不合格。",
      "軽い下ネタ・きわどいネタは冒頭に置く。ただし匂わせ止まりで、露骨な単語は1文字も出さない。",
      "冒頭1行はスレタイをそのまま読み上げる形にする（例:『ワイの本日の昼飯を当てるスレw』）。前置き・説明・自己紹介を先に置かない。",
      "参加型フォーマットを軸にする。『〜あげてけ』『〜当てるスレ』『質問ある？』『〜について答えます』など、視聴者が頭の中で自分のレスを考えられるお題を必ず含める。",
      "大喜利パートは『ボケレス3〜5個の積み上げ』で作る。1レス1ボケ、説明や理由付けを足さない。だんだん飛躍していく順に並べる。",
      "『>>1』『スレ主』『名無し』のような掲示板語をそのまま使い、レスの応酬として展開する。地の文での状況説明は最小限にする。",
      "1本30秒。1スレ＝1お題に絞り、複数の話題を詰め込まない。",
      "リスナー役（ゴロー）のリアクションは掲示板のレスそのもの（例:『草』『は？』『ワイもや』『それはアカン』『>>1は正直に生きろ』）。教科書的な相槌・共感の解説は禁止。",
      "実話系として語るが、特定の実在人物・企業・学校を名指ししない。名前は『A先輩』『上司のB』のように匿名化する。",
      "締めは『お前らならなんて答える？』『コメントで頼むわw』のような、お題を視聴者に投げる1行で終える。教訓・まとめ・『いかがでしたか』で締めるのは不合格。",
      "下ネタは『匂わせ』止まりにする。行為・身体・性的な単語は一切書かず、『何が出てきたか』は明言しないまま、周囲のレス（『は？』『それ以上言うな』『>>1は正直に生きろ』）と沈黙だけで笑いを作る。",
      "きわどいスレでもオチは『気まずさ』か『笑い』に着地させる。煽情的・実用的な描写に寄せたものは不合格（YouTubeの規約に抵触するため）。",
      "登場人物は全員成人として扱う。学生・未成年が絡む恋愛/下ネタは書かない。",
      "1行を長くしない。20字前後で切って、次のレスへ渡す。長文レスはテンポを殺すので不合格。",
      "地の文の状況説明を書かない。すべて誰かのレスとして書く。"
    ],
    "speech_signature": "一人称は『ワイ』、二人称は『お前ら』。語尾は『〜やろ』『〜なんやが』『〜やで』『〜せやろ』。文末に『w』『草』を自然に混ぜる。敬語・丁寧語・解説口調は1行たりとも使わない",
    "pacing": "1レス1ボケ。行は短く、テンポで殴る。説明や理由付けを足した瞬間に笑いが死ぬ。ボケ→ツッコミ→被せ、の3拍で刻み、同じ調子の行を2つ続けない",
    "signature_phrases": [
      "草",
      "ワロタ",
      "は？",
      "ワイもや",
      "それはアカン",
      ">>1は正直に生きろ",
      "お前ら正直に言えや"
    ],
    "reaction_style": "リアクションは掲示板のレスそのもの。1行で殴る短いツッコミ（『草』『は？』『それはアカン』）を軸にし、解説・共感・まとめは絶対に入れない。きわどいレスには乗っかりつつ『それ以上言うな』で止める",
    "banned_phrasing": [
      "敬語・丁寧語（〜です・〜ます）",
      "「解説します」「まとめると」「ポイントは3つ」「いかがでしたか」",
      "教訓・学び・前向きなまとめ",
      "科学的・学術的な説明口調"
    ],
    "hook_patterns": [
      {
        "name": "スレタイ伏せ型",
        "template": "スレタイをそのまま読み上げるが、『何が出てきたか』は伏せたまま止める",
        "example": "ワイの部屋の押し入れから出てきた物、当ててみてくれw"
      },
      {
        "name": "参加型お題型",
        "template": "「〇〇あげてけ」「〇〇当てるスレ」で、視聴者が頭の中で自分のレスを考えられるお題にする",
        "example": "実際には存在しないけど、ありそうな部活あげてけ"
      },
      {
        "name": "実況型",
        "template": "「ちょっと聞いてくれ、今〇〇なんやが」— 今まさに進行中の事件として始める",
        "example": "ちょっと聞いてくれ、今えらいことになっとる"
      },
      {
        "name": "質問ある？型",
        "template": "「ワイ、〇〇歴〇年やけど質問ある？」— 属性だけ晒して中身を出さない",
        "example": "ワイ、コンビニ夜勤歴10年やけど質問ある？"
      },
      {
        "name": "匂わせ型",
        "template": "きわどいネタを匂わせだけで置く。露骨な単語は1文字も出さず、周囲のレスの反応で笑わせる",
        "example": "彼女の部屋で見つけたやつがヤバいんやが"
      }
    ]
  },
  "theme_priority": {
    "label": "参加型・大喜利スレを最優先。日常あるある・しょうもない事件で回し、軽い下ネタを毎回混ぜる。スカッと／修羅場は箸休めとして少量",
    "categories": [
      "【最優先】参加型・大喜利スレ: 『〜あげてけ』『〜当てるスレ』『〜選手権』『実際には無いけどありそうな〇〇』など、視聴者が自分の答えを考えられるお題。正解を出さずコメントで遊ばせる（毎バッチ最低2件は必ず入れる）",
      "【最優先】『質問ある？』『〇〇について答えます』系: 職業・地域・趣味の当事者がレスの質問に答えていく形式。偏見・あるあるをネタとして肯定して笑いにする（毎バッチ最低1件は必ず入れる）",
      "日常あるある・ワイの身に起きたしょうもない事件: PCの画面がチカチカする・宅配が来ない・自販機でよく分からん物が出た・昼飯が決まらない等。深刻さゼロで『わかるw』を狙う（毎バッチ最低1件は必ず入れる）",
      "軽い下ネタ・きわどい恋愛エピソード: 彼女/彼氏の部屋で見つけた物・合コンの失敗談・風呂場や温泉の事故・飲み会のやらかし。行為や身体の描写はせず、『何が出てきたか』を伏せたまま周囲のリアクションで笑わせる（毎バッチ最低1件は必ず入れる）",
      "職場・バイト・学校のヤバい人ネタ: 理不尽な上司・非常識な同僚・伝説の先輩。説教にせず『そういう奴おるw』の笑いに落とす",
      "スカッと・修羅場・怖い話: 箸休め枠。溜め→反撃の構造がはっきりしているものだけを少量に留める"
    ],
    "required_count_per_batch": 5,
    "good_examples": [
      "ワイの今日の昼飯を当てるスレw",
      "実際には存在しないけどありそうな県名あげてけ",
      "コンビニで一番いらん商品あげてけ",
      "なんかPCの画面チカチカするんやが",
      "ワイ、彼女いない歴＝年齢やけど質問ある？",
      "この世からひとつ消していいなら何にする？",
      "バイト先の意味不明なルールあげてけ",
      "ワイの部屋から出てきた物、当ててみてくれw",
      "関西人への偏見、全部答えたる"
    ],
    "avoid_categories": [
      "政治・選挙・政党・政治家に関するスレ（genre_blacklist で生成停止）",
      "宗教・信仰・宗教団体に関するスレ（genre_blacklist で生成停止）",
      "実在の個人・企業・学校を特定できる形で晒す内容",
      "差別・誹謗中傷・特定属性を叩く内容",
      "性行為・身体の直接描写、煽情的／実用目的のエロ（『匂わせ』止まりならOK）",
      "未成年が関わる性的・恋愛的な話題、アダルト作品・風俗店の実名紹介",
      "過度なグロ・自傷描写",
      "ボケも笑いどころも無く、状況説明だけで終わるスレ（参加型はオチ不要だが、レスが面白くないものは不合格）",
      "説教・教訓・『いかがでしたか』で締める構成",
      "重い実話・シリアスな相談スレ（このチャンネルは軽いエンタメに全振りする）"
    ],
    "title_style": "タイトルは『掲示板に立ったスレタイそのもの』にする。一人称は『ワイ』、口語のまま、語尾に『w』を付けると強い。勝ちパターンは4型: (1)『〜あげてけ』(2)『〜当てるスレw』(3)『〜やけど質問ある？』(4)『なんか〜なんやが』。**全角12〜28文字**の短さに収める（長いスレタイは本物に見えない）。『→ その結果』『全員が黙った』のような結果匂わせ型は使わない——結果ではなく“お題”を出すのがこのチャンネルの型。【】プレフィックス・句点・過剰なカギ括弧・『〜という話』のような説明語尾は付けない。下ネタ系でも露骨な単語はタイトルに出さず、『ヤバい物』『言えないやつ』のような婉曲表現で止める。",
    "viral_hooks": "視聴者が自分の答えを考えられるお題 / 一人称『ワイ』の口語 / 語尾の『w』 / 『あげてけ』『当てるスレ』『質問ある？』 / 誰でも1回は経験した日常あるある / 正解を出さずコメント欄で大喜利が始まる余白",
    "series_lineup": [
      "当ててみてくれシリーズ",
      "〜あげてけシリーズ",
      "質問ある？シリーズ",
      "ワイの身に起きたしょうもない事件シリーズ",
      "言えないやつシリーズ"
    ],
    "title_power_words": [
      "スレ",
      "ワロタ",
      "衝撃の結末",
      "晒",
      "民",
      "→"
    ]
  },
  "theme_blacklist": [],
  "genre_blacklist": [
    "政治",
    "選挙",
    "政党",
    "政治家",
    "宗教",
    "信仰",
    "宗教団体"
  ],
  "competitors": [
    "UCoRP3zFpOrbq8WZrPIkdHaQ",
    "UCM8f899BmTsv_A3f8hxJDcA",
    "UCTjZVYpOJgsWWsVbfcRGg4A",
    "UCq-J25LEIhPUs2opaT7QnIQ",
    "UC7U4lhOGMoTcH8yKyFKXbVg",
    "UCNLHJszk8GuEb9fowBT9xxA",
    "UCH0F33ld355CR2PyjCsu3bw",
    "UCxmHtVCTmeswIuBvcNzUrqg"
  ],
  "theme_seeds": [
    {
      "title": "ワイの今日の昼飯を当てるスレw",
      "angle": "ヒントを小出しにして視聴者に当てさせる参加型。正解は言わずコメントに投げる。答え合わせしたくなる構成"
    },
    {
      "title": "実際には存在しないけどありそうな県名あげてけ",
      "angle": "大喜利の王道。ボケレスを3〜5個積み上げ、だんだん無理が出てくる順に並べる"
    },
    {
      "title": "コンビニで一番いらん商品あげてけ",
      "angle": "日常あるある×大喜利。誰でも1個は言えるお題でコメント欄を回す"
    },
    {
      "title": "なんかPCの画面チカチカするんやが",
      "angle": "しょうもない相談スレ。レスの解決策がどんどん雑になっていく展開で笑わせる"
    },
    {
      "title": "ワイ、彼女いない歴＝年齢やけど質問ある？",
      "angle": "質問ある？系。レスの質問に正直に答えすぎて余計に詰む自虐ネタ"
    },
    {
      "title": "この世からひとつ消せるなら何にする？",
      "angle": "参加型のお題。真面目な答えとしょうもない答えが混ざるほど伸びる"
    },
    {
      "title": "バイト先の意味不明なルールあげてけ",
      "angle": "職場あるある×大喜利。理不尽を怒りではなく笑いとして処理する"
    },
    {
      "title": "ワイの部屋から出てきた物、当ててみてくれw",
      "angle": "匂わせ系の軽い下ネタ。ブツは最後まで明言せず、レスの反応だけで察させる"
    },
    {
      "title": "関西人への偏見、全部答えたる",
      "angle": "『〇〇について答えます』型。属性あるあるを当事者が肯定してネタにする"
    },
    {
      "title": "自販機で当たり出たことあるやつおる？",
      "angle": "日常あるある。ある派・無い派で分かれてコメントが伸びるお題"
    },
    {
      "title": "人生で一番いらんかった買い物あげてけ",
      "angle": "共感型の大喜利。金額を添えるとレスが強くなる"
    },
    {
      "title": "ありそうで存在しないコンビニ弁当あげてけ",
      "angle": "食べ物×大喜利。ネーミングのセンスで笑わせる王道フォーマット"
    },
    {
      "title": "ワイの給料、当ててみてくれ",
      "angle": "ヒント小出しの当てるスレ。生活の描写がヒントになる自虐系"
    },
    {
      "title": "上司にキレそうになった瞬間あげてけ",
      "angle": "職場あるある。全部『わかる』で回収できる共感型のお題"
    },
    {
      "title": "ワイ、コンビニ夜勤5年やけど質問ある？",
      "angle": "職業の質問ある？型。深夜の変な客エピソードで笑わせる"
    },
    {
      "title": "深夜3時に食べていい物あげてけ",
      "angle": "背徳系のあるある。罪悪感ネタは共感コメントが伸びる"
    },
    {
      "title": "彼女の部屋で見つけてはいけない物あげてけ",
      "angle": "軽い下ネタの大喜利。露骨な単語は禁止で、婉曲表現と沈黙だけで笑いを作る"
    },
    {
      "title": "ワイの財布の中身、当ててみてくれw",
      "angle": "当てるスレ型。生活の困窮っぷりを小出しにする自虐ネタ"
    },
    {
      "title": "実際には無いけどありそうな駅名あげてけ",
      "angle": "県名スレの派生。地名ネタは地元民の反応でコメントが伸びる"
    },
    {
      "title": "合コンで言ったら終わる一言あげてけ",
      "angle": "恋愛×大喜利。きわどいネタは匂わせ止まりにして笑いに落とす"
    },
    {
      "title": "ワイの母ちゃんの口癖、当ててみてくれ",
      "angle": "家族あるある。全国共通の口癖にたどり着くと一気に共感が集まる"
    },
    {
      "title": "なんか隣の部屋から変な音するんやが",
      "angle": "日常の変な事件スレ。レスの推理が飛躍していって最後はしょうもないオチ"
    },
    {
      "title": "学校で一番いらんかった授業あげてけ",
      "angle": "学生あるある。世代を問わず参加できるお題"
    },
    {
      "title": "ワイ、実家が旅館やけど質問ある？",
      "angle": "質問ある？型。裏側あるあるを軽い暴露として出す"
    },
    {
      "title": "温泉で絶対にやってはいけない事あげてけ",
      "angle": "風呂場系の軽い下ネタ。身体の描写はゼロで、事故の気まずさだけで笑わせる"
    },
    {
      "title": "財布落としたことあるやつ、その後どうなった？",
      "angle": "体験談の募集型。良い話と最悪な話が混ざるとコメントが伸びる"
    },
    {
      "title": "ワイの今日の予定を当てるスレ",
      "angle": "当てるスレ型。何も無い一日をヒントとして小出しにする自虐系"
    },
    {
      "title": "元カレ元カノのヤバかった癖あげてけ",
      "angle": "恋愛×軽い下ネタの大喜利。比喩とドン引きレスだけで処理し露骨な描写はしない"
    },
    {
      "title": "彼女にバレたら終わる物あげてけw",
      "angle": "軽い下ネタの大喜利。ブツは最後まで明言せず、レスの動揺と沈黙だけで察させる。露骨な単語は一切使わない"
    },
    {
      "title": "風呂上がりのワイを見た彼女の反応がヤバい",
      "angle": "きわどい日常あるある。身体の描写はせず、相手のリアクションと『間』だけで笑いに着地させる"
    },
    {
      "title": "合コンで一番言ったらアカン一言あげてけ",
      "angle": "参加型の大喜利。きわどい発言を積み上げ、最後は誰も擁護できない一言で締める。特定の属性は叩かない"
    },
    {
      "title": "ワイの検索履歴、当ててみてくれw",
      "angle": "匂わせ系の参加型。中身は絶対に明かさず、ヒントの出し方だけで下ネタを想像させてコメントに投げる"
    }
  ],
  "characters": {
    "ユイ": {
      "side": "left",
      "speaker_id": 8,
      "dir": "yui",
      "text_color": [
        255,
        225,
        130
      ],
      "expressions": [
        "normal",
        "happy",
        "surprise",
        "angry"
      ],
      "thumb_dir": "yui",
      "thumb_expression": "surprise",
      "role": "読み上げ役（毎日スレを巡回している掲示板住人の女の子。テンポよく煽りながらスレを読む）",
      "appearance": "young Japanese anime girl named Yui with short orange bob hair and bright amber eyes, wearing a hoodie with a chat-bubble print and oversized headphones around her neck, grinning mischievous expression, chibi-style with a big round head and big eyes, colorful pop explainer character"
    },
    "ゴロー": {
      "side": "right",
      "speaker_id": 12,
      "dir": "goro",
      "text_color": [
        150,
        225,
        255
      ],
      "expressions": [
        "normal",
        "happy",
        "surprise",
        "angry"
      ],
      "thumb_dir": "goro",
      "thumb_expression": "angry",
      "role": "リアクション役（スレに全力で乗っかる男の子。ツッコミと『は？』担当）",
      "appearance": "young Japanese anime boy named Goro with messy dark blue hair and big expressive eyes, wearing a plain grey t-shirt with a simple smiley-face print and a smartphone in hand, exaggerated shocked reaction, chibi-style with a big round head and big eyes, colorful pop explainer character"
    }
  },
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 他のスレまとめはこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "お前らならどうする？コメントで教えてくれ"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "2chまとめ｜ショート全集",
      "main": "【2chまとめ】爆笑スレセレクション｜ゆっくり音声",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "読んでほしいスレをコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "main_intro": "{title}のスレを、ユイとゴローがゆっくり実況します。\n『〜あげてけ』『当てるスレ』『質問ある？』みたいな、参加したくなるくだらないスレを30秒でお届け。\n※本動画は掲示板の投稿をもとにした再構成・創作を含むエンタメコンテンツです。実在の人物・団体とは関係ありません。\nお前らの答えもコメントで頼むわw",
    "main_hashtags": "#2ch #2chまとめ #なんJ #ゆっくり #面白いスレ",
    "short_hashtags": "#shorts #2ch #2chまとめ #なんJ #面白いスレ",
    "omit_fullvideo_cta": true,
    "short_intro": "お前らならなんて答える？ コメントで頼むわw\n\n平日は夕方＆夜、休日はお昼に、掲示板のくだらない名スレを30秒でお届け。\n※掲示板の投稿をもとにした再構成・創作を含むエンタメコンテンツです。実在の人物・団体とは関係ありません。",
    "lead_template": "『{title}』のスレを{channel}がゆっくり実況＆まとめ。"
  },
  "thumbnail_template": {
    "badge_text": "2chスレ",
    "badge_color": [
      26,
      154,
      66
    ],
    "hook_color": [
      255,
      235,
      60
    ],
    "subtitle_color": [
      200,
      255,
      170
    ],
    "style_hint": "参考: くるいどり速報（くる速）系の高CTRサムネ路線。掲示板のスレタイをそのまま大きく見せる。\n- 背景は『お題そのもの』が写った明るい日常写真（弁当・コンビニ・机の上・部屋・駅・自販機など）。暗いホラー調・シリアス調にはしない。写真の上に半透明の暖色レイヤーを重ねて文字を浮かせる。\n- line1（白・太字）はスレタイの前半、line2（黄・極太）が核となるお題ワード（『あげてけ』『当てるスレw』『質問ある？』）。文字はサムネの半分以上を占める大きさにする。\n- キャラアイコンは丸く切り抜き、虹色（赤→黄→緑→青）のリングで囲んで右下または左下に配置する。表情は笑い・驚きの強いもの。\n- line3_badge は赤で『大喜利』『あるある』『難問』『ワイ的には』などの軽いワード。sub_text は『参加型スレ』『日常スレ』のようにジャンルを出す。\n- 文字は極太ゴシック＋黒の強い縁取り（4-6px）、黄色文字には赤の二重縁取りで視認性を最大化。感嘆符・吹き出し・>>1 のレス番号を装飾に混ぜる。\n- 実在の人物の顔・企業ロゴは絶対に載せない。政治的な記号・宗教的シンボルも使わない。"
  },
  "defaults": {
    "speed": 1.35,
    "target_duration": 45,
    "bg_type": "static",
    "bg_path": null,
    "short_bg_query": "abstract colorful pastel gradient texture bokeh background",
    "short_overlay_style": {
      "opening": {
        "font_size_max": 104,
        "font_size_min": 72,
        "stroke_width": 8,
        "glow_stroke_extra": 7,
        "dim_alpha": 110,
        "punch_start_scale": 0.88,
        "accent_color": [
          255,
          95,
          60
        ]
      },
      "hook_caption": {
        "accent_color": [
          255,
          235,
          60
        ],
        "band_alpha": 150,
        "y_center": 1000
      },
      "subtitle": {
        "font_size": 66,
        "line_gap": 88,
        "stroke_width": 6,
        "stroke_color": [
          18,
          18,
          18
        ],
        "color": [
          255,
          255,
          255
        ],
        "glow_color": [
          255,
          205,
          40
        ],
        "glow_extra": 6
      }
    },
    "use_illustrations": true,
    "hashtags": [
      "#2ch",
      "#2chまとめ",
      "#なんJ",
      "#ゆっくり",
      "#面白いスレ"
    ],
    "category": "24",
    "short_title_hashtags": "#shorts #2ch #面白いスレ",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "終始ふざけた掲示板ノリ（参加型の大喜利・日常あるある・軽い下ネタが主／スカッと・怖い話は少量）",
    "age_rating": "teen_plus",
    "cta_position": "after_hook",
    "cta_style": "casual",
    "guidelines": [
      "掲示板の投稿をもとにした再構成・創作を含むエンタメである旨を概要欄に明記する",
      "登場人物は必ず匿名化する（『上司のA』『同僚のB』）。実在の人物・企業・学校を特定できる形にしない",
      "笑い・共感・参加を軸にする。特定の属性や個人を叩いて笑いを取らない",
      "1本30秒前後・1スレ1お題に絞り、最後までテンポを落とさない",
      "参加型のお題は正解を断定せず、視聴者が自分の答えをコメントしたくなる状態で終える",
      "語りは『ワイ』『お前ら』の口語で通し、丁寧な解説・教訓・『いかがでしたか』は使わない",
      "画像はいらすとや的なシンプルなイラストや記号で構成し、実在人物の写真・企業ロゴは使わない",
      "下ネタは『匂わせ』までとし、性行為・身体・性的な単語は書かない。ブツや行為は明言せず、リアクションと沈黙で笑いに着地させる",
      "タイトル・サムネにも露骨な単語を出さない。『ヤバい物』『全部察した』『言えないもの』のような婉曲表現で止める",
      "きわどいネタでも登場人物は全員成人として描き、未成年が絡む恋愛・性的な話題は扱わない"
    ],
    "avoid": [
      "政治・宗教に関する話題",
      "実在の個人・企業・学校の特定や晒し",
      "差別・誹謗中傷",
      "性的に露骨な描写",
      "過度なグロ・自傷描写",
      "未成年が関わる性的・恋愛的な話題",
      "アダルト作品・風俗店の実名紹介、実用目的の性的描写",
      "ボケも笑いどころも無い、状況説明だけのスレ",
      "説教・教訓・シリアスな相談で終わる構成"
    ],
    "short_end_line": {
      "omit_related_video": true,
      "wording": "お前らならなんて答える？ コメントで頼むわw"
    }
  },
  "video_format": {
    "layout": {
      "width": 1920,
      "height": 1080,
      "fps": 24,
      "char_canvas_w_ratio": 0.418,
      "char_y_offset": 130,
      "char_x_inset_ratio": 0.15,
      "speaker_glow": true,
      "nonspeaker_opacity": 0.5,
      "text_box_height_ratio": 0.2,
      "text_box_opacity": 190,
      "text_font_size": 44,
      "text_stroke_width": 3,
      "text_line_spacing": 4,
      "text_margin_x": 60,
      "illustration_size": 360,
      "illustration_interval": 30
    },
    "colors": {
      "bg_color": [
        30,
        30,
        40,
        255
      ],
      "text_box_color": [
        26,
        26,
        40
      ],
      "text_stroke_color": [
        0,
        0,
        0
      ]
    },
    "audio": {
      "speed": 1.35,
      "pause_between": 0.25,
      "bgm_volume": 0.3,
      "bgm_path": null
    },
    "illustration_style": {
      "style": "vivid",
      "format": "portrait",
      "art_style": "simple flat cartoon illustration in the style of free Japanese clip-art (いらすとや) — rounded shapes, thick clean outlines, cheerful primary colors on a white background, exaggerated comedic facial expressions with sweat drops, anger marks and question marks. No realism, no photos, no gore.",
      "background": "plain white or light comic background with speed lines and speech bubbles, thin red frame border",
      "include_characters": false,
      "frame_style": "comic-red-border",
      "extra_prompt": "Compose like a bulletin-board thread panel: a speech bubble containing a short Japanese line, a >>number style tag in the corner, and one comically exaggerated anonymous person reacting with a punchline face. Everyday mundane subjects (lunch box, convenience store snack, flickering PC monitor, messy room) are preferred over dramatic scenes. Keep every person generic and anonymous — no real people, no logos, no text-heavy paragraphs.",
      "allow_text_labels": true,
      "allow_frame": true
    },
    "branding": {
      "watermark_text": "2chスレ実況",
      "cta_style": "casual",
      "source_credit": "※掲示板の投稿をもとにした再構成・創作を含みます。実在の人物・団体とは関係ありません",
      "source_credit_opacity": 150,
      "source_credit_font_size": 20,
      "source_credit_font_size_short": 26
    },
    "output": {
      "target_duration": 45,
      "gen_type": "short",
      "bg_type": "static",
      "bg_path": null,
      "use_illustrations": true
    },
    "youtube": {
      "channel_id": "",
      "default_tags": [
        "2ch",
        "2chまとめ",
        "ゆっくり",
        "面白い",
        "爆笑",
        "スレ",
        "なんJ",
        "5ch",
        "2ch面白いスレ",
        "ゆっくり実況",
        "大喜利",
        "2chスレ"
      ],
      "default_category": "24",
      "privacy_status": "private",
      "upload_schedule": null
    },
    "analytics": {
      "enabled": true,
      "fetch_retention_for": 5,
      "performance_threshold": {
        "min_ctr": 4,
        "min_retention": 40,
        "min_views_7d": 1000
      }
    },
    "short_illustrations": {
      "enabled": true,
      "illustration_method": "pillow",
      "max_count": 2,
      "card_style": "textbook",
      "card_label": "2chスレ",
      "card_accent": [
        220,
        30,
        30
      ],
      "card_x": 64,
      "card_y": 250,
      "card_w": 952,
      "card_h": 430,
      "char_cy": 905,
      "char_icon_d": 210,
      "image_mode": "generate",
      "keyword_icons": false
    },
    "effects": {
      "enabled": true,
      "preset": "pop",
      "allow_shake": true,
      "allow_flash": true,
      "allow_pixelate": false,
      "allow_glitch": false,
      "allow_tint": true,
      "shake_max_px": 12,
      "zoom_max": 0.08,
      "transition_duration": 0.35,
      "short_beat_zoom": true,
      "beat_interval": 1.6,
      "beat_zoom_max": 0.055
    },
    "persona": {
      "age_group": "20代",
      "gender": "男女",
      "interest_categories": [
        "エンタメ"
      ],
      "content_depth": "ライト"
    }
  },
  "autopilot": {
    "enabled": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 17,
      "minute": 15,
      "times": [
        {
          "hour": 17,
          "minute": 15,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 19,
          "minute": 15,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 12,
          "minute": 15,
          "days_of_week": [
            0,
            6
          ]
        },
        {
          "hour": 14,
          "minute": 15,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 12,
    "gen_type": "short",
    "publish_lead_minutes": 45,
    "theme_queue": [
      {
        "id": "f203dfe1",
        "title": "友達の家で見た謎の私物あげてけw",
        "angle": "聞くに聞けない用途不明の物を、持ち主の反応や空気の変化だけで匂わせる軽い下ネタ枠"
      },
      {
        "id": "fd118b60",
        "title": "ワイ、彼女の家で開けたらアカン引き出し開けたんやが",
        "angle": "報告スレ型。中身は最後まで明言せず、周囲のレスで想像させる"
      },
      {
        "id": "f24bedb9",
        "title": "通販の履歴で一番言い訳できんやつあげてけw",
        "angle": "参加型お題。届いた箱と家族の反応でオチをつける"
      },
      {
        "id": "a14dd19c",
        "title": "修学旅行の夜にバレたやつあげてけw",
        "angle": "誰もが通る鉄板。学校あるあるから徐々に暴走させる"
      },
      {
        "id": "23c45802",
        "title": "大人になってから意味がわかった言葉あげてけw",
        "angle": "子供の頃の記憶ネタ。下ネタ寄りだが直接語は使わない"
      },
      {
        "id": "e460a00d",
        "title": "友達の家の風呂借りた時にやらかしたことあげてけw",
        "angle": "共感あるある→事故の飛躍"
      },
      {
        "id": "e6d9268f",
        "title": "健康診断で先生に言えんかったことあげてけw",
        "angle": "問診票あるある。身体ネタだが直接描写しない"
      },
      {
        "id": "0973e22e",
        "title": "親に見つかって一番終わったもの晒してけw",
        "angle": "実物は伏せ、見つかった直後の空気だけ書く"
      },
      {
        "id": "fc7481df",
        "title": "同棲して初めて知った相手の秘密、共有してけ",
        "angle": "生活を共にして発覚するギャップ。実物は伏せて反応で笑わせる"
      },
      {
        "id": "dcb7845a",
        "title": "合コンで一発で場が凍った発言、晒してけ",
        "angle": "空気が死ぬ瞬間の一言だけを並べる"
      },
      {
        "id": "879a94b0",
        "title": "マッチングアプリで会った人がヤバかった件",
        "angle": "報告スレ型。会話の再現だけで押し切る"
      },
      {
        "id": "799627a9",
        "title": "学生時代の保健体育、先生がやらかした話しようや",
        "angle": "教室の空気だけで笑わせる。直接語は使わない"
      },
      {
        "id": "245690a0",
        "title": "温泉旅行で起きた事故、聞いてくれや",
        "angle": "湯けむりの向こうの出来事。描写せず反応だけ書く"
      },
      {
        "id": "25e2b938",
        "title": "大学のサークルで語り継がれてる事件教えてくれ",
        "angle": "伝説化した出来事。尾ひれがついていく構成"
      },
      {
        "id": "9a8930b6",
        "title": "彼女がワイのノートPC開いた結果がこれや",
        "angle": "画面の中身は伏せる。沈黙と言い訳で笑わせる"
      },
      {
        "id": "589d809d",
        "title": "隠し場所として天才やと思ったやつ、共有しようや",
        "angle": "隠す対象は明言しない。場所のアイデアだけで勝負"
      }
    ]
  },
  "short_format": {
    "line_count": 8,
    "line_chars": "1〜7行目は26〜38字（短いレスほど掲示板らしい）、8行目のみ50〜70字を許容",
    "total_chars_min": 270,
    "total_chars_max": 340,
    "structure": [
      "1行目=**スレタイをそのまま読む(0〜3秒・最重要)**: タイトルの文言をほぼそのまま口に出す(例:「ワイの部屋から出てきた物、当ててみてくれw」「彼女の部屋で見つけたやつがヤバい」)。挨拶・自己紹介・前置き・テーマ説明は1文字でも入れたら不合格。**スレタイ自体が『え、なにそれ』『それで？』と思わせる引きになっていること**（普通の報告文になっていたら書き直す）。",
      "2行目=**即レス**: ゴローが1レス目のノリで食いつく(「は？」「早速で悪いんやが」「詳しく」「ワイからいくで」)。ここで解説を始めない。視聴者が思ったことをそのまま代弁する行にする。",
      "3〜7行目=**ボケレスの積み上げ(このチャンネルの核)**: 1行1ボケで、お題への答えを5つ並べる。だんだん飛躍・暴走していく順に置く（5個目が一番おかしい）。数字・研究データ・豆知識は不要（むしろ入れるとチャンネルの空気が壊れる）。参加型のお題は正解を断定せず、視聴者が『いや、それより〇〇やろ』とツッコみたくなる余白を残す。"
    ],
    "extra_rules": [
      "『解説』『研究』『実は〜なんです』のような説明調の行が1つでもあれば不合格。このチャンネルは知識ではなく笑いと参加で見られている。",
      "ボケは説明せず言い切る。理由付け・補足・オチの解説を足した瞬間に面白さが死ぬ。",
      "全7行を通して一人称『ワイ』・語尾『〜やろ』『〜やが』『草』『w』を維持する。1行でも敬体が混ざれば不合格。",
      "**軽い下ネタ・きわどいネタを最優先で冒頭に置く**。1行目で『それ言って大丈夫なやつ？』と思わせるほど指が止まる。ただし行為・身体の直接描写は禁止で、『何が出てきたか』は最後まで明言しない（周囲のレスと沈黙だけで笑わせる）。",
      "**共感 → 笑い の順で作る**。3〜4行目は『わかるw』と頷けるあるあるを置き、5〜6行目で飛躍させて笑わせる。最初から飛ばすと共感が拾えず完視聴率が落ちる。",
      "1行は20〜36字。長いレスは掲示板に見えないし、テロップが数秒固まって離脱する。"
    ]
  }
}```

### `data/channels/akashic-librarian.json`

```json
{
  "id": "akashic-librarian",
  "name": "ラグナロクの司書",
  "concept": "滅びのすべてが記録される書庫「ラグナロク」。その司書が、閉架に眠る一冊を取り出して静かに読み上げる1人語りの長尺チャンネル。都市伝説・歴史の謎・宇宙の不思議・失われた文明・予言・超常現象を、煽らず、断定せず、低く落ち着いた男性の声で語る。1本12分目安（最低10分）、ロング動画のみ。シナリオは自動生成せず、運営者が用意した台本を使う。",
  "style": "monologue",
  "scenario_source": "manual",
  "youtube_channel_id": "UClXnuH-KPDXnX0bn2NJlMhg",
  "image_mode": "collect",
  "image_collect": {
    "provider": "wikimedia,openverse",
    "safe_search": true,
    "license_filter": "cc",
    "max_per_query": 12,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic",
    "query_template": "{topic} 遺跡 古文書 星空 神秘",
    "orientation": "landscape"
  },
  "voice_style": {
    "tone": "低く落ち着いた男性の声。知的で、少しミステリアス。囁くように静かだが、聞き取れないほどではない。12分を通して声量を一定に保ち、驚きは声量ではなく『間』と断定で作る。",
    "narrator_persona": "書庫「ラグナロク」（滅びのすべてが記録される書庫）の司書。男性。名も年齢も明かさない。膨大な記録を淡々と読み上げるが、時折その記録に対する私見をひとことだけ添える。感情を大きく揺らさず、常に一定の距離を保って語る。",
    "opening_hooks": [
      "その記録には、続きが無い。",
      "この事件の頁だけ、書架から抜き取られている。",
      "人類が二度、まったく同じ夢を見たという記録がある。",
      "この本は、閉架に置かれている。理由は書かれていない。",
      "同じ日付の記録が、二通り残されている。"
    ],
    "forbidden": [
      "SCP",
      "財団",
      "収容",
      "ポケモン",
      "妖怪",
      "リコ",
      "マコト",
      "ヒカリ",
      "ソラ",
      "シロ",
      "クロ",
      "ユイ",
      "ゴロー",
      "理子",
      "ミナモ",
      "ケンタ",
      "ゆっくり",
      "ずんだもん",
      "〜なのだ",
      "〜だぞ",
      "ですます調の解説"
    ],
    "style_rules": [
      "**1人語り厳守**。話者は司書ただ1人。掛け合い・相槌・ツッコミ・二人目の話者を絶対に登場させない。「〜だよね」「えっ、どういうこと?」のような相手への呼びかけ返答も禁止。",
      "一人称は「私」、視聴者への呼びかけは「あなた」。司書は男性だが、性別を話題にしない。",
      "文体は常体（だ・である調）。静かに言い切る。「〜なのだ」「〜だぞ」のようなゆっくり解説的な強い語尾は使わない。",
      "**冒頭10秒（本文1〜2行目）は司書の断定から入る**。挨拶・自己紹介・チャンネル説明・「今回は〜を紹介します」のような前置きは1文字でも入れたら不合格。",
      "本題では必ず年号・地名・人名・数値のいずれか1つ以上を出す。「不思議な話がある」だけの抽象論で終わらせない。",
      "都市伝説・超常現象・予言は事実として断定しない。「記録によれば」「そう記されている」「とされている」で伝聞として置き、判断は視聴者に委ねる。",
      "**最後は言い切らず、余韻を残して閉じる**。結論を断定せず、記録が途切れている事実の提示か、静かな問いかけ（「あなたはどう読む」「その頁は、まだ白紙のままだ」）で終える。叫ぶような煽り・強い登録依頼で締めない。",
      "誇張した驚き（「ヤバい」「衝撃」「震撼」）を語りに使わない。静けさそのものが不気味さになる。",
      "1文は短く。長い修飾を重ねず、句点で区切って『間』を作る。",
      "**長尺（12分）を通した緩急を作る**。章ごとに扱う記録の層を変え、同じ情報の言い直しで尺を埋めない。"
    ]
  },
  "characters": {
    "narrator": {
      "side": "none",
      "speaker_id": 101,
      "dir": null,
      "text_color": [
        232,
        228,
        215
      ],
      "expressions": [],
      "role": "書庫ラグナロクの司書。名を明かさない男性の語り手。低い声で書庫の記録を静かに読み上げる。",
      "appearance": null
    }
  },
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "auto_comment": {
      "enabled": true,
      "question": "この記録、どう読み解く？あなたの解釈をコメントで"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "ラグナロクの司書｜ショート全集",
      "main": "ラグナロクの司書｜本編",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "調べてほしい都市伝説・未解明ミステリーをコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "main_intro": "ラグナロク —— 滅びのすべてが記録される、と伝えられる書庫。\nその閉架に眠る一冊を、司書が静かに読み上げます。\n\n※本チャンネルで扱う都市伝説・予言・超常現象は、事実として確定したものではありません。伝承・記録・報告として紹介しています。\n\nチャンネル登録で、次の記録もお届けします。",
    "main_hashtags": "#都市伝説 #歴史ミステリー #未解明 #オカルト #ラグナロク",
    "short_hashtags": "#shorts #都市伝説 #歴史ミステリー #未解明 #オカルト"
  },
  "thumbnail_template": {
    "badge_text": "閉架記録",
    "badge_color": [
      52,
      38,
      92
    ],
    "hook_color": [
      235,
      230,
      218
    ],
    "subtitle_color": [
      212,
      175,
      95
    ],
    "style_hint": "深い藍〜紫の暗がりに、古文書・星図・書架のテクスチャ。金色の細い箔押し風テキスト。派手な赤や爆発エフェクトは使わない。静けさと知性を感じさせる暗いトーンで統一する。"
  },
  "defaults": {
    "speed": 1.05,
    "target_duration": 720,
    "bg_type": "auto",
    "use_illustrations": false,
    "hashtags": [
      "#都市伝説",
      "#歴史ミステリー",
      "#未解明",
      "#オカルト",
      "#ラグナロク"
    ],
    "short_title_hashtags": "#shorts #都市伝説 #オカルト",
    "category": "24",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "静謐・知的・ミステリアス",
    "age_rating": "all_ages",
    "cta_position": "end",
    "cta_style": "quiet",
    "guidelines": [
      "都市伝説・予言・超常現象は『記録によれば』『とされている』と伝聞で提示し、事実として断定しない",
      "歴史・宇宙の話題は、確認できる年号・地名・研究名を1つ以上添える",
      "未解明のものは『まだ分かっていない』と正直に言い切る。無理に answers を作らない",
      "静かな語りを保つ。恐怖を煽って視聴者を不安にさせない",
      "終末予言・災害予言は日時を断定せず、伝承として扱う",
      "終章は結論を断定せず、記録が途切れている事実か静かな問いかけ（例:『答えは記されていない。あなたはどう読む』）で閉じる"
    ],
    "avoid": [
      "実在の個人・団体への誹謗中傷や陰謀論的な名指し",
      "医療・健康に関する非科学的な断定（治る・効くなどの表現）",
      "特定の宗教・スピリチュアル商材・占いサービスへの誘導",
      "差別的な民族起源説・疑似歴史の断定",
      "自殺・自傷を想起させる描写",
      "視聴者を過度に不安にさせる終末煽り"
    ]
  },
  "theme_priority": {
    "label": "知られざる知識・歴史の謎・都市伝説・宇宙・失われた文明・予言・超常現象",
    "categories": [
      "歴史の謎: 未解読文書・消えた人物・説明のつかない遺物（最優先。事実ベースで強い）",
      "失われた文明: 発掘によって定説が覆った遺跡、痕跡だけが残る文明",
      "宇宙の不思議: 観測されたのに説明できない現象、届いたきり途絶えた信号",
      "都市伝説: 出典をたどれる、記録として残っている類の伝承",
      "超常現象: 臨死体験・集団記憶違いなど、研究対象になっている現象",
      "予言: 後世に検証された予言と、その解釈がどう変わってきたか"
    ],
    "required_count_per_batch": 5,
    "good_examples": [
      "600年間、誰も読めない本がある — ヴォイニッチ手稿と、その頁に描かれた実在しない植物",
      "1977年、宇宙から72秒だけ届いた信号 — Wow!シグナルは二度と観測されていない",
      "ピラミッドより7000年古い神殿 — ギョベクリ・テペが埋め戻されていた理由",
      "文字を持っていたのに解読できない — インダス文明が残した4000の刻印",
      "植民地が丸ごと消えた — ロアノーク島に残されていた、たった一語"
    ],
    "avoid_categories": [
      "実在企業・実在人物を名指しした陰謀論",
      "特定の宗教・民族を貶める疑似歴史",
      "医療・健康デマ（水・波動・代替医療など）",
      "日時を断定する終末予言",
      "反ワクチン等の公衆衛生に関わる陰謀論"
    ],
    "title_style": "答えをバラさず、謎そのものを置く。「なぜ〇〇だけ〇〇なのか」「〇〇に記されていた、たった一語」のように、記録・書物・年号を匂わせる静かな言い回しにする。「衝撃」「ヤバい」「震撼」のような煽り語は使わない。",
    "viral_hooks": "未解読 / 二度と観測されていない / 記録が途切れている / 説明がつかない / 埋め戻された理由 / 誰も読めない",
    "title_power_words": [
      "記録",
      "禁書",
      "閉架",
      "失われた",
      "封印"
    ]
  },
  "theme_blacklist": [],
  "genre_blacklist": [],
  "theme_seeds": [
    {
      "title": "ヴォイニッチ手稿",
      "angle": "600年間解読されない写本。実在しない植物の図版と、未知の文字体系"
    },
    {
      "title": "アンティキティラ島の機械",
      "angle": "紀元前100年頃の青銅製歯車装置。天体の動きを計算していた古代のコンピュータ"
    },
    {
      "title": "Wow!シグナル",
      "angle": "1977年に72秒だけ受信された強い電波。以後一度も再観測されていない"
    },
    {
      "title": "ギョベクリ・テペ",
      "angle": "約1万1000年前の巨石神殿。何者かが意図的に埋め戻していた"
    },
    {
      "title": "ロアノーク植民地",
      "angle": "1590年、入植者115人が消え、柱に刻まれていたのは『CROATOAN』の一語"
    },
    {
      "title": "インダス文明の刻印",
      "angle": "4000点以上の印章が残るのに、文字が誰にも読めない理由"
    },
    {
      "title": "始皇帝陵の未発掘区画",
      "angle": "水銀の川という記述と、実際に検出された異常な水銀濃度"
    },
    {
      "title": "マンデラ効果",
      "angle": "多数の人間が同じ記憶違いを共有する現象。記憶研究が示す説明"
    },
    {
      "title": "臨死体験の共通報告",
      "angle": "文化が違っても酷似する証言。医学研究がどこまで説明できているか"
    },
    {
      "title": "ナスカの地上絵",
      "angle": "空からしか全体を見られない図形を、なぜ地上の人々が描いたのか"
    },
    {
      "title": "ボイジャーのゴールデンレコード",
      "angle": "人類が宇宙へ送り出した記録盤。誰に宛てられ、いま何処にあるのか"
    },
    {
      "title": "宇宙のボイド",
      "angle": "銀河がほとんど存在しない直径十億光年規模の空洞。なぜそこだけ空なのか"
    },
    {
      "title": "アトランティスの記述",
      "angle": "プラトンの対話篇にだけ現れる島。同時代の他の記録には一切残っていない"
    },
    {
      "title": "ノストラダムスの詩篇",
      "angle": "四行詩がなぜ何にでも当てはまるのか。解釈が時代ごとに書き換えられた歴史"
    },
    {
      "title": "きさらぎ駅",
      "angle": "存在しない駅の記録。ネット上でどう伝承が形成され、変異していったか"
    },
    {
      "title": "メアリー・セレスト号",
      "angle": "1872年、無人で漂流していた船。積荷も食料も残されたまま乗員だけが消えた"
    },
    {
      "title": "ドッペルゲンガーの記録",
      "angle": "自己像幻視として報告される症例と、歴史上の目撃記録の重なり"
    },
    {
      "title": "サン・ジェルマン伯爵",
      "angle": "百年以上にわたり複数の宮廷で目撃されたとされる人物の記録"
    },
    {
      "title": "デジャヴの正体",
      "angle": "初めての場所を知っている感覚。記憶の二重処理という有力な仮説"
    },
    {
      "title": "ホピ族の予言",
      "angle": "口承で受け継がれてきた九つの徴。どこまでが後世の脚色なのか"
    },
    {
      "title": "アレクサンドリア図書館",
      "angle": "焼失で失われた蔵書。何が記されていたかを推定する手がかりだけが残る"
    },
    {
      "title": "タオス・ハム",
      "angle": "一部の住民にだけ聞こえる低い唸り。計測機器が捉えられない音の記録"
    }
  ],
  "long_format": {
    "target_duration_sec": 720,
    "min_duration_sec": 600,
    "chapter_count": "3〜5章（導入と終章を含む）",
    "line_count": "本文48〜80行（章タイトル行は行数に数えない）",
    "line_chars": "1行90〜120字（目標100字）。89字以下も121字以上も不合格",
    "total_chars_min": 5000,
    "total_chars_max": 6480,
    "structure": [
      "**冒頭0〜10秒（本文1〜2行目）= フック**: 司書が書架から一冊を抜き出すように、記録の異常だけを短く断定して置く(例:「その記録には、続きが無い」「同じ日付の頁が、二通り残されている」)。挨拶・自己紹介・テーマ説明・前置きは1文字でも入れたら不合格。答えはまだ出さない。",
      "**冒頭10〜60秒 = 引き込みと見取り図**: いつ・どこの記録なのかを静かに添え、この12分で何を読み進めるのかを一段だけ示す。ここでもまだ答えを出さない。",
      "**第1章 = 記録の発見**: 誰が、いつ、どこでその記録に行き当たったのかを辿る。年号・地名・人名・数値のいずれかを必ず含める。",
      "**第2章 = 記録の中身**: 記されている内容を読み上げる。定説と、その定説では説明のつかない点を明確に分ける。",
      "**第3章 = 反証と別の解釈**: 後年の検証・異説・再調査を並べる。未確認の事柄は『記録によれば』『とされている』と伝聞で置く。",
      "**第4章（任意）= 現在地**: 今どこまで分かっているのか。分かっていないことは『まだ分かっていない』と正直に言い切る。",
      "**終章 = 余韻**: 結論を断定しない。記録がそこで途切れている事実の提示か、静かな問いかけ（例:「その先は、まだ誰も書いていない」「あなたは、どう読む」）で閉じる。強い登録依頼・煽り・叫びで締めるのは不合格。"
    ],
    "extra_rules": [
      "全編を通して話者は司書1人。相槌・掛け合い・二人目の話者が1行でも混ざれば不合格。",
      "**尺は12分目安。10分（600秒）を割ってはいけない**。",
      "各章の終わりに、次章へつながる未解決点を1つ残す（長尺の視聴維持）。",
      "1章につき最低2つ、新しい具体情報（年号・地名・人名・数値・研究名）を出す。同じ情報の言い直しで尺を埋めれば不合格。",
      "「ヤバい」「衝撃」「震撼」「マジで」のような煽り語を1つでも使えば不合格。静けさで引かせる。",
      "常体（だ・である調）を維持する。「〜なのだ」「〜だぞ」のゆっくり解説的な語尾は使わない。",
      "終章で結論を断定したら不合格。余韻・未決着・問いかけのいずれかで終えること。"
    ]
  },
  "video_format": {
    "layout": {
      "width": 1920,
      "height": 1080,
      "fps": 30,
      "text_box_height_ratio": 0.2,
      "text_box_opacity": 205,
      "text_font_size": 44,
      "text_stroke_width": 3,
      "text_line_spacing": 6,
      "text_margin_x": 110
    },
    "colors": {
      "bg_color": [
        8,
        10,
        24,
        255
      ],
      "text_box_color": [
        0,
        0,
        0
      ],
      "text_stroke_color": [
        0,
        0,
        0
      ],
      "thumb_overlay_opacity": 195
    },
    "audio": {
      "speed": 1.05,
      "pause_between": 0.45,
      "bgm_volume": 0.22,
      "bgm_path": null,
      "bgm_per_scene": true,
      "bgm_crossfade": 2.0
    },
    "branding": {
      "watermark_text": "VOICEVOX:離途",
      "watermark_position": "bottom_right",
      "watermark_opacity": 150,
      "watermark_font_size": 18,
      "cta_style": "quiet",
      "source_credit": null
    },
    "output": {
      "target_duration": 720,
      "gen_type": "full",
      "bg_type": "auto",
      "use_illustrations": false
    },
    "illustration_style": {
      "style": "muted",
      "format": "landscape",
      "art_style": "dim candle-lit archive aesthetic: aged parchment, faded ink diagrams, star charts, weathered stone. Desaturated indigo and sepia palette with a single warm gold accent. Painterly, grainy, quiet — no bright pop colors, no cartoon outlines",
      "background": "deep indigo darkness with soft dust motes and a faint vignette",
      "include_characters": false,
      "frame_style": "none",
      "extra_prompt": "no text, no letters, no modern objects, no people's faces",
      "allow_text_labels": false,
      "allow_frame": false
    },
    "youtube": {
      "channel_id": "UClXnuH-KPDXnX0bn2NJlMhg",
      "default_tags": [
        "都市伝説",
        "歴史ミステリー",
        "未解明",
        "オカルト",
        "宇宙",
        "古代文明",
        "予言",
        "ラグナロク",
        "都市伝説解説",
        "ミステリー",
        "超常現象",
        "怖い話"
      ],
      "default_category": "24",
      "default_language": "ja",
      "privacy_status": "public",
      "upload_schedule": null
    },
    "analytics": {
      "enabled": false,
      "track_metrics": [
        "views",
        "watch_time",
        "ctr",
        "retention"
      ],
      "auto_adjust": false
    },
    "effects": {
      "enabled": true,
      "preset": "minimal",
      "allow_zoom": true,
      "allow_shake": false,
      "allow_flash": false,
      "allow_tint": true,
      "allow_pixelate": false,
      "allow_glitch": false,
      "allow_transitions": true,
      "max_effects_per_scene": 1,
      "zoom_max": 0.03,
      "transition_duration": 0.5,
      "fade_in_first": true,
      "fade_out_last": true
    },
    "persona": {
      "age_group": "20〜40代",
      "gender": "男女",
      "interest_categories": [
        "都市伝説",
        "歴史",
        "宇宙",
        "ミステリー",
        "オカルト"
      ],
      "tone_style": "静かな語り",
      "content_depth": "ミドル",
      "custom_notes": "就寝前・移動中に静かな低い声を長く聞きたい層。派手な演出より、落ち着いた没入感と12分の作業用BGM的な聴き心地を求めている。"
    }
  },
  "autopilot": {
    "enabled": false,
    "auto_optimize_schedule": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 18,
      "minute": 45,
      "times": [
        {
          "hour": 18,
          "minute": 45,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 13,
          "minute": 45,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 12,
    "gen_type": "full",
    "theme_queue": [],
    "publish_lead_minutes": 45
  },
  "short_series_name": "",
  "main_title_prefix": "【閉架記録】",
  "competitors": [
    "UCt9eCRJcnfzSzPyupr39pKw",
    "UCgOOIAV1Zbh3nmUSfkFlbKQ",
    "UCBthdtZvyzJe6YPA9NUJdIA",
    "UCUGLmnKXbmIX1hQZa5LCk4w",
    "UCqLHMs76QGLpcaoFCcxKG-g",
    "UCZd-iwj71RGEfVHGLj1fMkw",
    "UCOTRp0oy1QoNe0EE_RZzP4g"
  ]
}
```

### `data/channels/clip-lab.json`

```json
{
  "id": "clip-lab",
  "name": "ゆっくり解説 切り抜きラボ",
  "concept": "既存の長尺ゆっくり解説（daily-science / scp-lab）から『一番おいしい1シーン』だけを切り出して縦型ショートにする切り抜きチャンネル。1本30〜59秒、冒頭2秒で結論、字幕は原寸より2倍大きく焼き込む。本編への導線を必ず貼り、母体チャンネルの再生数も伸ばす。",
  "style": "clip",
  "youtube_channel_id": "UCbWZ5quEFE2VpHPh5TGyPCw",
  "image_mode": "generate",
  "clip": {
    "engine": "local",
    "fallback_engine": "local",
    "sources": [
      {
        "channel_id": "scp-lab",
        "weight": 2,
        "credit_name": "SCPラボ"
      },
      {
        "channel_id": "daily-science",
        "weight": 3,
        "credit_name": "デイリーサイエンス"
      }
    ],
    "clips_per_video": 3,
    "target_duration_sec": 50,
    "min_duration_sec": 30,
    "max_duration_sec": 59,
    "segment_selection": {
      "prefer_retention_peaks": true,
      "retention_weight": 0.5,
      "script_weight": 0.5,
      "exclude_head_sec": 8,
      "exclude_tail_sec": 15,
      "min_gap_sec": 30
    },
    "noimos": {
      "workspace_id": "cmsnzc4ed032j01s6dxpwfrdo",
      "cli_bin": "noimosai",
      "timeout_sec": 900,
      "prompt_template": "以下のYouTube長尺動画から、エンゲージメントが最も高くなる縦型ショート（9:16・{target_sec}秒以内）を{clips}本切り抜いてください。\n\n動画URL: {source_url}\nタイトル: {source_title}\n\n条件:\n- 冒頭2秒で『結論・驚き』が来るように頭出しする\n- 日本語の大きな字幕を焼き込む\n- 被写体（左右のキャラクター）を追従してクロップせず、上部に16:9のまま配置し下に字幕帯を置く構成にする\n- 完成したMP4のダウンロードURLを必ず返す",
      "mode": "browser",
      "base_url": "https://app.noimosai.com",
      "workspace_url": "https://app.noimosai.com/workspaces/cmsnzc4ed032j01s6dxpwfrdo",
      "headless": true,
      "nav_timeout_sec": 120,
      "agent_wait_sec": 900,
      "poll_interval_sec": 5,
      "storage_state": "~/.youtube-factory/noimos_session.json",
      "selectors": {}
    }
  },
  "layout_spec": {
    "canvas": [
      1080,
      1920
    ],
    "fps": 30,
    "source_crop_bottom_ratio": 0.22
  },
  "voice_style": {
    "tone": "元動画の音声をそのまま使うため生成音声なし。テキスト（フック/CTA）だけがこのチャンネルの声。",
    "forbidden": [],
    "style_rules": [
      "フック文は13文字以内×2行まで。読み切れない長さにしない。",
      "元動画のキャラクターと口調を変えない（切り抜きなので改変しない）。",
      "CTAは『続きは本編で』の一点に絞る。"
    ]
  },
  "characters": {},
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "publish_targets": [
      "youtube"
    ],
    "auto_comment": {
      "enabled": true,
      "question": "続きが気になった人はコメントで教えて！フル解説も出してるよ"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "切り抜きラボ｜ショート全集",
      "main": "切り抜きラボ｜本編",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "切り抜いてほしい回をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "short_intro": "▼ この切り抜きの本編はこちら\n{source_url}\n\n{source_title}\n（{credit_name} より切り抜き）",
    "short_hashtags": "#shorts #ゆっくり解説 #切り抜き #雑学",
    "omit_fullvideo_cta": true,
    "main_hashtags": "#ゆっくり解説 #切り抜き #雑学",
    "lead_template": "『{title}』のおいしい場面を{channel}が切り抜きでお届け。"
  },
  "thumbnail_template": {
    "badge_text": "切り抜き",
    "badge_color": [
      255,
      90,
      0
    ],
    "hook_color": [
      255,
      255,
      255
    ],
    "subtitle_color": [
      255,
      220,
      60
    ],
    "bg_tone": "dark",
    "style_hint": "元動画のピーク時フレームをそのまま使い、上に太字フックを乗せる。作り込まない（切り抜きらしさを残す）。"
  },
  "defaults": {
    "speed": 1,
    "target_duration": 50,
    "bg_type": "none",
    "use_illustrations": false,
    "hashtags": [
      "#shorts",
      "#ゆっくり解説",
      "#切り抜き",
      "#雑学"
    ],
    "category": "24",
    "short_title_hashtags": "#shorts #切り抜き",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "元動画に準拠",
    "age_rating": "all_ages",
    "cta_position": "end",
    "cta_style": "本編誘導",
    "guidelines": [
      "切り抜き元は自社チャンネルの動画に限定する（他者コンテンツは切り抜かない）",
      "元動画のURLとチャンネル名を説明欄に必ず記載する",
      "文脈を反転させるような切り取り方（誤解を生む編集）をしない",
      "字幕は元の発話をそのまま使い、言い換え・改変をしない"
    ],
    "avoid": [
      "他チャンネルの動画の無断切り抜き",
      "オチだけを抜き出して本編の価値を消す編集",
      "元動画にない主張の字幕付け"
    ]
  },
  "theme_priority": {
    "label": "元動画の中で最も引きの強いシーン",
    "categories": [
      "驚きの数字・統計が出るシーン（最優先）",
      "常識がひっくり返る種明かしのシーン",
      "『実は〜だった』の結論提示シーン",
      "キャラクターが強く驚く・ツッコむリアクションシーン"
    ],
    "good_examples": [
      "『実は99%の人が知らない』と切り出す部分",
      "具体的な数字（○○%、○○倍）が提示される部分",
      "通説を否定して真実を提示する部分"
    ],
    "avoid_categories": [
      "導入の挨拶・チャンネル紹介",
      "まとめ・エンディングのCTA部分",
      "前後の文脈がないと意味が通らない部分"
    ],
    "title_style": "元動画のタイトルをそのまま使わず、切り抜いたシーンの結論だけを20〜28文字で言い切る。疑問形より断定形。",
    "viral_hooks": "意外な数字 / 常識の否定 / 一言オチ / 強いリアクション",
    "title_power_words": [
      "切り抜き",
      "名場面"
    ]
  },
  "theme_blacklist": [],
  "genre_blacklist": [],
  "theme_seeds": [],
  "effects_research": {
    "genre": "clip",
    "prefer_shorts": true,
    "target_channels": 6,
    "videos_per_channel": 2
  },
  "video_format": {
    "layout": {
      "width": 1080,
      "height": 1920,
      "fps": 30,
      "short_width": 1080,
      "short_height": 1920,
      "short_fps": 30
    },
    "colors": {
      "bg_color": [
        10,
        10,
        14,
        255
      ]
    },
    "audio": {
      "speed": 1,
      "pause_between": 0,
      "bgm_volume": 0,
      "bgm_path": null
    },
    "branding": {
      "watermark_text": "切り抜きラボ",
      "watermark_position": "bottom_right",
      "watermark_opacity": 150,
      "watermark_font_size": 20,
      "cta_style": "source_link"
    },
    "output": {
      "target_duration": 50,
      "gen_type": "clip",
      "bg_type": "none",
      "use_illustrations": false
    },
    "youtube": {
      "channel_id": "",
      "default_tags": [
        "切り抜き",
        "ゆっくり解説",
        "雑学",
        "SCP",
        "科学",
        "shorts",
        "切り抜き動画",
        "ゆっくり解説切り抜き",
        "雑学切り抜き"
      ],
      "default_category": "24",
      "privacy_status": "public",
      "upload_schedule": null
    },
    "effects": {
      "enabled": true,
      "preset": "minimal",
      "allow_shake": false,
      "allow_flash": false,
      "allow_pixelate": false,
      "allow_glitch": false,
      "allow_tint": false,
      "zoom_max": 0.03,
      "transition_duration": 0.2
    },
    "persona": {
      "age_group": "10〜30代",
      "gender": "男女",
      "interest_categories": [
        "雑学",
        "science",
        "SCP",
        "ショート動画"
      ],
      "content_depth": "ライト"
    }
  },
  "autopilot": {
    "enabled": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 17,
      "minute": 45,
      "times": [
        {
          "hour": 17,
          "minute": 45,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 19,
          "minute": 45,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 12,
          "minute": 45,
          "days_of_week": [
            0,
            6
          ]
        },
        {
          "hour": 14,
          "minute": 45,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 1,
    "gen_type": "clip",
    "publish_lead_minutes": 0,
    "theme_queue": [
      {
        "id": "cbd00a46",
        "title": "PCパーツの選び方！科学的視点から",
        "angle": "ゲーミングPCのパーツ選びを科学的に解説",
        "priority": "high",
        "source": "trend_scanner"
      },
      {
        "id": "31f486b2",
        "title": "DualSenseの進化！ゲーム体験を科学する",
        "angle": "ゲームコントローラーの進化とその科学的背景"
      }
    ]
  },
  "short_series_name": "切り抜きラボ",
  "main_title_prefix": ""
}```

### `data/channels/company-facts.json`

```json
{
  "id": "company-facts",
  "name": "企業のホンネ",
  "concept": "有名企業の年収・ボーナス・福利厚生・離職率を、リアルな店舗写真の上に数字ファクトとして叩き込むショートチャンネル。1本1社、30〜50秒。赤帯ヘッダーで統一ブランド、白太字テキストで数字を連打。転職・就活層のZ世代がターゲット。",
  "style": "facts_overlay",
  "youtube_channel_id": "UCB07OOxWeKK6v86KsSYgnNA",
  "image_mode": "collect",
  "image_collect": {
    "provider": "wikimedia,openverse,pexels",
    "safe_search": true,
    "license_filter": "cc",
    "max_per_query": 8,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic",
    "query_template": "{company_name} 店舗 外観 看板",
    "orientation": "portrait"
  },
  "voice_style": {
    "tone": "落ち着いたビジネス調のナレーション。数字は淡々と、しかし要所で皮肉を一滴落とす。持ち上げっぱなしにせず『その裏で何が起きているか』まで必ず言い切る。はしゃいだテンションや感嘆符の連打はしない。信頼できる情報番組の距離感を保つ",
    "narrator_persona": "企業のIR資料と口コミを両方読み込んでいるナレーター。表の数字と現場の実態のズレを知っていて、『公表されているのはここまで』と線を引ける。断定できないところは推定と明示する。企業を叩くのではなく、事実で静かに裏側を見せる",
    "opening_hooks": [
      "この会社の平均年収、いくらだと思う？",
      "実はこの会社、離職率3%なんだ",
      "年収850万円。これ、あの身近な企業の数字",
      "この福利厚生、知らずに落ちてる人が多すぎる"
    ],
    "forbidden": [
      "SCP",
      "財団",
      "収容",
      "ポケモン",
      "妖怪",
      "リコ",
      "マコト",
      "ヒカリ",
      "ソラ",
      "シロ",
      "クロ"
    ],
    "style_rules": [
      "1画面目のナレーションは必ず『問い』か『驚き』で始める（例:『この会社の年収、いくらだと思う？』）。淡々と数字を読み上げる入りは不合格。",
      "冒頭3秒で企業名と最もインパクトのある数字を出す（例：『ニトリ、平均年収850万円』）。",
      "1ファクトにつき5〜8秒。数字→補足→次の数字のテンポで進める。",
      "数字は必ず具体的に出す。『高い』『すごい』だけでは終わらない。",
      "ネガティブな面も1つは入れてバランスを取る（例：『ただし1年目は力仕事が多い』）。",
      "最後は『気になったらプロフィールもチェックしてね』でCTA。",
      "対話形式にしない。1人のナレーションで完結させる。",
      "3ファクトに1回は皮肉または裏側の一言を挟む（例:『数字だけ見れば、かなり良い』）。数字を読み上げるだけの並びが4つ続いたら不合格。",
      "褒める数字を出したら、必ずどこかで『ただし』の一言を用意する。持ち上げるだけの構成にしない。",
      "皮肉は企業攻撃にしない。事実と数字で静かに示し、断定できないことは『推定』と明示する。"
    ],
    "speech_signature": "です・ます調のナレーション。1文を短く言い切る。数字は必ず単位まで声に出す。感嘆符・顔文字・スラングは使わない",
    "pacing": "1ファクト5〜8秒。数字→補足→次の数字で刻む。3ファクトに1回、皮肉または裏側の一言を差し込んで単調な数字読みにしない",
    "signature_phrases": [
      "実はこの裏で",
      "数字だけ見れば、かなり良い",
      "ただし、ここからが本題",
      "公表されているのは、ここまで",
      "この数字、業界では異常値です"
    ],
    "reaction_style": "対話しないので、驚きは語り手自身の一言で作る（『これ、業界平均の2倍です』『正直、ここまでとは思っていませんでした』）。感情は乗せるが、はしゃがない",
    "banned_phrasing": [
      "「いかがでしたか」「すごいですね」だけの中身のない感想",
      "根拠のない断定（出典が言えない数字を言い切る）",
      "特定企業を貶める言い回し・個人が特定できる話",
      "ネットスラング・ゆっくり解説特有の口調"
    ],
    "hook_patterns": [
      {
        "name": "数字先出し型",
        "template": "企業名と最もインパクトのある数字だけを、修飾なしで先に置く",
        "example": "ニトリ、平均年収850万円。"
      },
      {
        "name": "問いかけ型",
        "template": "「この会社の〇〇、いくらだと思いますか？」— 数字を当てさせてから明かす",
        "example": "この会社の平均年収、いくらだと思いますか？"
      },
      {
        "name": "裏側暴露型",
        "template": "「実はこの数字の裏で、〇〇が起きています」— 表の好条件と裏の実態をセットで出す",
        "example": "有給消化率100%。実はこの裏で、ある制度が効いています"
      },
      {
        "name": "逆説型",
        "template": "「〇〇。ただし、これには理由があります」— 良すぎる数字に一拍で疑いを入れる",
        "example": "離職率3%。ただし、この数字には続きがあります"
      }
    ]
  },
  "characters": {
    "ナレーター": {
      "side": "none",
      "speaker_id": 13,
      "dir": null,
      "text_color": [
        255,
        255,
        255
      ],
      "expressions": [],
      "role": "ナレーター（画面に登場しない）",
      "appearance": null
    }
  },
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "auto_comment": {
      "enabled": true,
      "question": "この数字、正直どう思う？あなたの会社と比べてコメントで！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "企業のホンネ｜ショート全集",
      "main": "【企業の闇】大手企業の裏事情まとめ｜ゆっくり解説シリーズ",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "ホンネを暴いてほしい企業をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "main_intro": "{company_name}の年収・ボーナス・福利厚生を徹底解説！\n転職・就活の参考にしてください。\n※データは公開情報・口コミサイトを元にしています。\n\nチャンネル登録よろしくお願いします！",
    "main_hashtags": "#企業の闇 #企業解説 #ブラック企業 #年収 #転職",
    "short_hashtags": "#shorts #企業の闇 #企業解説 #年収 #転職",
    "omit_fullvideo_cta": true,
    "short_intro": "この動画で紹介した数字は、有価証券報告書・公式IR・大手口コミサイトなどの公開情報を元にしています。",
    "lead_template": "『{title}』の年収・待遇・裏事情を{channel}が数字でまとめました。"
  },
  "thumbnail_template": {
    "badge_text": "企業分析",
    "badge_color": [
      26,
      42,
      72
    ],
    "hook_color": [
      255,
      255,
      255
    ],
    "subtitle_color": [
      236,
      198,
      112
    ],
    "style_hint": "企業の実店舗写真を背景に、赤帯ヘッダーと白太字テキストでインパクトを出す。参考: @sakai-l7u スタイル。"
  },
  "defaults": {
    "speed": 1.2,
    "target_duration": 40,
    "bg_type": "slideshow",
    "use_illustrations": false,
    "hashtags": [
      "#企業の闇",
      "#企業解説",
      "#年収",
      "#転職",
      "#ブラック企業"
    ],
    "category": "22",
    "short_title_hashtags": "#shorts #企業分析 #年収 #転職",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "データ重視・驚き喚起",
    "age_rating": "all_ages",
    "cta_position": "end",
    "cta_style": "プロフィール誘導",
    "guidelines": [
      "データは有価証券報告書・OpenWork・転職会議など公開ソースに基づく",
      "企業を過度に持ち上げたり、貶めたりしない。ポジ・ネガ両面を出す",
      "個人の口コミは『口コミサイトによると』と出典を明示する",
      "未上場企業の推定年収は『推定』と明記する",
      "特定の転職サービスへの誘導は行わない"
    ],
    "avoid": [
      "企業への誹謗中傷",
      "個人の特定につながる情報",
      "未確認のデータの断定",
      "特定サービスのアフィリエイト誘導"
    ]
  },
  "theme_priority": {
    "label": "有名企業の年収・福利厚生・働き方データ",
    "categories": [
      "【最優先】時事ネタ連動: 決算発表・新店舗/新工場・値上げ・大型採用・M&A・不祥事など、直近で名前を見た企業を扱う（『今その企業の名前を見た』人が検索・視聴に来るため初動が強い）",
      "ホワイト企業: 有給消化率・残業時間・定着率が高い企業（最優先。バズりやすい）",
      "高年収企業: 平均年収・ボーナスが高い企業のリアルなデータ",
      "意外な高待遇企業: 知名度は低いが福利厚生が充実している企業",
      "大手小売・外食: ニトリ・ユニクロ・スタバなど身近な企業の裏側",
      "IT・Web企業: Google・メルカリ・サイバーエージェントなどテック企業の実態"
    ],
    "required_count_per_batch": 5,
    "good_examples": [
      "ニトリ、超ホワイト企業の実態 — 有給消化率100%、ボーナス年2回で平均200万",
      "ユニクロの平均年収がヤバい — 実は業界トップクラスの待遇",
      "Googleジャパンの福利厚生を全部見せます — 無料食堂だけじゃない",
      "コストコの時給が高すぎる理由 — パートでも年収400万超え",
      "任天堂が離職率3%の理由 — 社員が辞めない秘密"
    ],
    "avoid_categories": [
      "ブラック企業の過度な叩き（訴訟リスク）",
      "個人の年収暴露",
      "非公開の内部情報",
      "政治的に敏感な企業"
    ],
    "title_style": "企業名を必ずタイトルに入れる。『〇〇の年収がヤバい』『〇〇、実はホワイト企業だった』のようにインパクト重視。数字は1つ入れる。 タイトルは『説明』ではなく『衝動』を作る——数字を先頭寄りに置き、読んだ瞬間に指が止まる語（実は/ヤバい/本当は/知らない）を必ず1つ入れる。",
    "viral_hooks": "驚きの年収額 / 意外なホワイト企業 / 有名企業の裏側 / 数字のインパクト / 身近な企業の実態 / 冒頭3秒で企業名＋最強の数字 / 時事ネタ連動（最近ニュースで見た企業）",
    "series_lineup": [
      "身近な企業の年収シリーズ",
      "ホワイト企業ファイルシリーズ",
      "離職率が低い会社シリーズ",
      "福利厚生がヤバい会社シリーズ",
      "話題の企業の実態シリーズ"
    ],
    "title_power_words": [
      "年収",
      "手取り",
      "離職率",
      "ボーナス",
      "格差",
      "ブラック",
      "激務"
    ]
  },
  "theme_blacklist": [],
  "genre_blacklist": [],
  "theme_seeds": [
    {
      "title": "ニトリの実態",
      "angle": "有給消化率100%、ボーナス平均200万、34期連続増収増益の超ホワイト企業"
    },
    {
      "title": "ユニクロの年収",
      "angle": "平均年収959万、グローバル企業としての待遇と激務の実態"
    },
    {
      "title": "コストコの時給",
      "angle": "時給1,500円〜、パートでも賞与あり、なぜここまで高いのか"
    },
    {
      "title": "任天堂が辞められない理由",
      "angle": "離職率3%、平均年収988万、福利厚生と社風の秘密"
    },
    {
      "title": "スタバの福利厚生",
      "angle": "パートナー割引・学費補助・ストックオプションの実態"
    },
    {
      "title": "Googleジャパンの裏側",
      "angle": "平均年収1,600万超、無料食堂、20%ルールの真実"
    },
    {
      "title": "トヨタの生涯年収",
      "angle": "終身雇用・年功序列の王道、生涯で稼げる金額は"
    },
    {
      "title": "キーエンスの年収が異常",
      "angle": "平均年収2,279万、なぜここまで高いのか仕組みを解説"
    },
    {
      "title": "メルカリの働き方",
      "angle": "フルリモート・副業OK・英語公用語化の実態"
    },
    {
      "title": "サイゼリヤの原価率",
      "angle": "なぜあんなに安いのか、社員の待遇は実際どうなのか"
    }
  ],
  "video_format": {
    "layout": {
      "width": 1080,
      "height": 1920,
      "fps": 30,
      "short_width": 1080,
      "short_height": 1920,
      "short_fps": 30
    },
    "facts_overlay": {
      "overlay_alpha": 100,
      "header_badge": {
        "text": "超ホワイト企業",
        "bg_color": [
          26,
          42,
          72
        ],
        "text_color": [
          255,
          255,
          255
        ],
        "font_size": 56,
        "y_position": 150,
        "padding": [
          18,
          44
        ]
      },
      "fact_text": {
        "font_size_main": 96,
        "font_size_main_min": 62,
        "font_size_sub": 52,
        "text_color": [
          255,
          255,
          255
        ],
        "highlight_color": [
          236,
          198,
          112
        ],
        "stroke_width": 8,
        "stroke_color": [
          0,
          0,
          0
        ],
        "y_center": 760,
        "max_lines": 3,
        "scrim_alpha": 120
      },
      "bottom_text": {
        "font_size": 52,
        "text_color": [
          226,
          196,
          140
        ],
        "stroke_width": 6,
        "y_position": 1420
      },
      "slideshow": {
        "enabled": true,
        "max_images": 6,
        "switch_per_fact": true,
        "query_suffixes": [
          "店舗 外観",
          "店内",
          "本社",
          "看板",
          "ビル",
          "売り場"
        ]
      },
      "cta": {
        "enabled": true,
        "headline": "他の企業もチェック",
        "sub": "プロフィールから見れます",
        "bg_color": [
          16,
          22,
          34
        ],
        "accent_color": [
          198,
          162,
          92
        ]
      },
      "motion": {
        "enabled": true,
        "ken_burns": 0.12,
        "crossfade": 0.35,
        "text_in": 0.32
      },
      "logo_chip": {
        "enabled": true,
        "size": 170,
        "position": "top_left",
        "margin": 40
      }
    },
    "colors": {
      "bg_color": [
        0,
        0,
        0,
        255
      ]
    },
    "audio": {
      "speed": 1.2,
      "pause_between": 0.2,
      "bgm_volume": 0.25,
      "bgm_path": null
    },
    "branding": {
      "watermark_text": "VOICEVOX:青山龍星",
      "watermark_position": "bottom_right",
      "watermark_opacity": 180,
      "watermark_font_size": 18,
      "cta_style": "profile_check"
    },
    "output": {
      "target_duration": 45,
      "gen_type": "short",
      "bg_type": "slideshow",
      "use_illustrations": false
    },
    "youtube": {
      "channel_id": "",
      "default_tags": [
        "企業の闇",
        "企業解説",
        "ブラック企業",
        "ゆっくり解説",
        "裏事情",
        "企業分析",
        "年収",
        "転職",
        "就活",
        "ホワイト企業",
        "福利厚生",
        "企業のホンネ"
      ],
      "default_category": "22",
      "privacy_status": "private",
      "upload_schedule": null
    },
    "effects": {
      "enabled": true,
      "preset": "minimal",
      "allow_shake": false,
      "allow_flash": false,
      "allow_pixelate": false,
      "allow_glitch": false,
      "allow_tint": false,
      "zoom_max": 0.04,
      "transition_duration": 0.3,
      "short_beat_zoom": true,
      "beat_interval": 1.9,
      "beat_zoom_max": 0.045
    },
    "persona": {
      "age_group": "20代",
      "gender": "男女",
      "interest_categories": [
        "転職",
        "キャリア",
        "ビジネス"
      ],
      "content_depth": "ライト"
    }
  },
  "autopilot": {
    "enabled": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 17,
      "minute": 0,
      "times": [
        {
          "hour": 17,
          "minute": 0,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 14,
          "minute": 0,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 12,
    "gen_type": "short",
    "publish_lead_minutes": 45,
    "theme_queue": [
      {
        "id": "3604eca1",
        "title": "DualSenseの影響とゲーム業界の年収",
        "angle": "新しい技術がゲーム業界に与える影響を探る。"
      },
      {
        "id": "ef50839e",
        "title": "トヨタ自動車の平均年収と、実は多い手当の中身",
        "angle": "有価証券報告書の平均年収と、住宅・家族手当の実額"
      },
      {
        "id": "240ad151",
        "title": "三菱商事の年収1700万円台、総合商社の待遇を数字で",
        "angle": "商社の年収構造と、海外赴任の実態"
      },
      {
        "id": "34fbc14b",
        "title": "味の素の年収と有給取得率、ホワイト企業常連の実態",
        "angle": "有給取得率と残業時間を軸にする"
      },
      {
        "id": "e0bd7d97",
        "title": "JR東日本の年収と年間休日、鉄道大手の待遇",
        "angle": "交替勤務の実情と休日数のバランス"
      },
      {
        "id": "2166a1b0",
        "title": "花王の年収と男性育休取得率、実際の数字はどうか",
        "angle": "育休の取得率という切り口で差別化する"
      },
      {
        "id": "582370b4",
        "title": "サイバーエージェントの年収と平均年齢、若手の昇給スピード",
        "angle": "平均年齢の若さと昇給の関係"
      },
      {
        "id": "6bb13422",
        "title": "大和ハウス工業の年収1000万円超、残業時間の実態",
        "angle": "高年収と残業のトレードオフを正直に出す"
      },
      {
        "id": "49e5b2aa",
        "title": "NTTデータの年収と在宅勤務率、IT大手の働き方",
        "angle": "リモート比率という新しい指標で切る"
      },
      {
        "id": "182932df",
        "title": "星野リゾートの給与と離職率、ホテル業界の中での位置",
        "angle": "業界平均との比較を必ず入れる"
      },
      {
        "id": "ef110d19",
        "title": "キリンビールの年収と福利厚生、飲料大手の待遇",
        "angle": "福利厚生の実額を出す"
      }
    ],
    "auto_optimize_schedule": true
  },
  "short_series_name": "",
  "main_title_prefix": "",
  "competitors": [
    "UCAtmCRJyCsTj54EWa0vPIZA",
    "UC1KM0FPG8NvCWKRZURZZEfQ",
    "UC1SF9QyOrAzaWnz8vQ_xtgA",
    "UCIT1nfung5BjctTN_6S8yWQ",
    "UCPTlN9nVQPyn5kfqNe7zH_Q",
    "UCcsstuqZggLOoOLRmH_1q2A",
    "UCF-TTrC6lxRhk0K6DFOxDKQ"
  ]
}```

### `data/channels/daily-science.json`

```json
{
  "id": "daily-science",
  "name": "リコとマコトのゆっくり日常科学",
  "concept": "「なぜ？」と思った瞬間に答えが出る、身近な不思議チャンネル。睡眠・夢・自分の体で今まさに起きている現象を軸に、視聴者が今日体験したばかりの違和感を疑問形で提示して、その場で解き明かす。",
  "style": "yukkuri",
  "youtube_channel_id": "UC1OckVkZahT3_fM6W8hD6dg",
  "image_mode": "generate",
  "image_collect": {
    "provider": "auto",
    "safe_search": true,
    "license_filter": "cc",
    "max_per_query": 5,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic"
  },
  "competitors": [
    "UCJHZshDuIrd_6MaT8MIjFtg",
    "UCLK63mzEn9yPcwrjSEWBK3Q",
    "UCW_SXldsg7l5NLnsIK1g2Bw",
    "UCJBb5HlV8OHLLT5pttKJv5g",
    "UCYG5ZT0oNuWYZl4o8IcNsGw",
    "UCr8W7upKLTEg2ae9EtU76Ig",
    "UCY3WhU5uwwi4tUMgJUhEpcw",
    "UCrjrX74DgL27R90BtlDFRjw",
    "UCPKsFwt9ACF-EnJM3xN8wyQ",
    "UCDy22j1Z7jDpyI14KWVgmQQ",
    "UCMlyjv59rW7nbK09UsonA-w",
    "UCUHg7zFbbjSHvW1heBOqnxw",
    "UCOWNqU3svMapjmGwT5FGnSg",
    "UCq5Jp9wm4RS9scPbBHMCQVw",
    "UCG9eaT9ZjDZ-K1WCdccIIhg",
    "UC3PWWshMfLtdgDOvM5hKT6A",
    "UCCJm5G9w23fPCq2qa4ifg1w"
  ],
  "characters": {
    "理子": {
      "side": "left",
      "speaker_id": 2,
      "text_color": [
        255,
        255,
        0
      ],
      "expressions": [
        "normal",
        "laugh",
        "sad",
        "surprise",
        "think"
      ],
      "role": "解説役（科学に詳しい女の子）",
      "appearance": "young Japanese anime girl with long silver-white (platinum) ponytail hair, wearing a white lab coat over a school uniform, curious cheerful expression, chibi-style with a big round head and big eyes, cute educational explainer character"
    },
    "真": {
      "side": "right",
      "speaker_id": 3,
      "text_color": [
        100,
        230,
        255
      ],
      "expressions": [
        "normal",
        "laugh",
        "surprise",
        "happy",
        "sad"
      ],
      "role": "リスナー役（素朴な疑問を持つ男の子）",
      "appearance": "young Japanese anime boy named Makoto with short black hair and round glasses, wearing a casual blue shirt, smart curious expression, chibi-style with a big round head and big eyes, cute educational explainer character"
    }
  },
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "これ知ってた？他にも気になる「なんで？」があったらコメントで教えて！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "1分科学｜ショート全集",
      "main": "【ゆっくり解説】日常に潜む科学の謎シリーズ",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "「これ科学的にどうなの？」という疑問をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "main_intro": "{title}についてリコとマコトがゆっくり解説します。\n日常のふとした疑問を科学の視点から分かりやすく紐解いていきます。\nぜひ最後までご視聴ください！",
    "main_hashtags": "#ゆっくり解説 #科学 #雑学 #日常の謎 #豆知識",
    "short_hashtags": "#shorts #ゆっくり解説 #雑学 #豆知識 #科学"
  },
  "thumbnail_template": {
    "badge_text": "ゆっくり解説",
    "badge_color": [
      220,
      40,
      40
    ],
    "hook_color": [
      255,
      255,
      50
    ],
    "subtitle_color": [
      80,
      220,
      255
    ],
    "style_hint": "明るく目を引く科学系チャンネルのサムネイル。\n- 背景は『明るくカラフルで楽しい』を最優先する。暗い／陰鬱／ホラー調は絶対NG。\n- background_concept は必ず『bright, vibrant, colorful, well-lit, daylight, cheerful, high-key lighting, clear blue sky / pastel sky / soft sunlight / bright laboratory』のような明るさを示す英語キーワードを複数含めること。『dark / moody / dim / shadowy / cinematic noir / night』など暗さを示す語は禁止。\n- 被写体は科学的に正確で、ポップで親しみやすいクローズアップ（脳・細胞・宇宙の昼面・夢の世界・実験器具・色とりどりの粒子など）。色は鮮やかなパステル＋ビビッドの組み合わせで、視認性の高い背景にする。\n- 中央〜上部に主役を置き、下部はやや空けて文字を載せやすくするが、空けた部分も暗くせず明るいグラデーション（白／クリーム／薄黄／薄水色）にすること。\n- line1（白）は状況・前振り（例: 『なぜ夢で…？』）。line2（黄）は核となる驚き・疑問でインパクト最大化（『声が出ない理由！？』）。\n- line3_badge は赤で『衝撃の事実』『科学が解明』『○○の正体』など。sub_text は答えを匂わせる明るい煽り。",
    "background_style_suffix": "Style: bright, vibrant, cheerful YouTube thumbnail aesthetic for an educational science channel. High-key daylight lighting, saturated pop colors, cheerful pastel-and-vivid palette, soft clean shadows, crisp focus on the central subject, friendly approachable mood — like a colorful science textbook cover. Absolutely NOT dark, moody, noir, dim, or horror-styled.",
    "gradient_overlay": {
      "top_height_pct": 42,
      "top_opacity_start": 0.38,
      "top_opacity_mid": 0.12,
      "bottom_height_pct": 32,
      "bottom_opacity_start": 0.35,
      "bottom_opacity_mid": 0.1
    }
  },
  "defaults": {
    "speed": 1.3,
    "target_duration": 720,
    "bg_type": "static",
    "bg_path": "assets/backgrounds/classroom.png",
    "short_overlay_style": {
      "opening": {
        "font_size_max": 104,
        "font_size_min": 72,
        "stroke_width": 8,
        "glow_stroke_extra": 7,
        "dim_alpha": 130,
        "punch_start_scale": 0.88,
        "accent_color": [
          70,
          160,
          225
        ]
      },
      "hook_caption": {
        "accent_color": [
          80,
          220,
          255
        ],
        "band_alpha": 150,
        "y_center": 1000
      },
      "subtitle": {
        "font_size": 62,
        "line_gap": 84,
        "stroke_width": 6,
        "stroke_color": [
          12,
          26,
          48
        ],
        "color": [
          255,
          255,
          255
        ],
        "glow_extra": 0
      }
    },
    "use_illustrations": true,
    "hashtags": [
      "#ゆっくり解説",
      "#雑学",
      "#豆知識",
      "#科学"
    ],
    "short_title_hashtags": "#shorts #雑学 #豆知識",
    "category": "27",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日2本 更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "身近・親しみやすい（隣で教えてくれる距離感）",
    "age_rating": "all_ages",
    "cta_position": "end_of_video",
    "cta_style": "casual",
    "end_cta": {
      "enabled": true,
      "wording": "面白かったらチャンネル登録よろしくね",
      "reason": "身近な不思議を毎日1本ずつ解き明かしていて、次の回も一緒に見てほしいから"
    },
    "cliffhanger": {
      "enabled": true,
      "wording": "同じシリーズの他の動画も見てって"
    },
    "short_end_line": {
      "omit_related_video": true,
      "wording": "今日から意識してみて。同じシリーズの動画も置いてあるよ"
    }
  },
  "theme_priority": {
    "label": "体の不思議 と 睡眠・夢（2026-08-04 PDCA レポートの実データで1位・2位。この2ジャンルを最優先で回す）",
    "categories": [
      "【最優先】いま起きている感覚・反射の科学: 炭酸のツーン・目を閉じたときのふらつき・冷たい物でこめかみが痛む・耳が詰まる・鳥肌など、視聴者がその場で再現できる数秒の感覚（2026-08-15 実データで初動1489回/日とチャンネル最高。毎バッチ最低1件は必ず入れる）",
      "身近な体の不思議: 痛覚・体温・耳鳴り・くしゃみ・あくび・免疫・涙・肌・指など、視聴者自身の体で今まさに起きている現象（累計75本・合計再生1位。毎バッチ最低2件は必ず入れる）",
      "睡眠・夢の科学: なぜ夢を見るのか・金縛り・寝言・レム睡眠・寝落ちなど（累計平均は最上位だが、2026-08-15 時点で直近15本中10本が睡眠系に偏り初動が落ちている。**毎バッチ1件までに制限**し、連続バッチで同じ睡眠サブテーマを繰り返さない）",
      "脳・記憶・心理: 既視感・思い出せない・集中が切れるなど、日常で体感する脳の挙動（平均524回・第3位。上位2ジャンルの次に置く）"
    ],
    "required_count_per_batch": 3,
    "good_examples": [
      "夢で見たことを朝には忘れてしまう本当の理由",
      "寝落ちの瞬間に体がビクッとなるのはなぜなのか",
      "自分の声が録音だと変に聞こえる本当の理由 — 骨伝導の謎",
      "なぜ金縛りは『いつも同じ時間帯』に起きるのか",
      "本を読むと必ず眠くなる人が知らない、集中と睡魔の意外な関係"
    ],
    "avoid_categories": [
      "宇宙・天体（6本すべて0再生・平均0回で実データ最下位。genre_blacklist でも生成停止済み。単体テーマにしない）",
      "日常の違和感カテゴリ（平均195回。体感を伴わない題材は避ける）",
      "抽象的・遠い話題(宇宙の起源・量子論の数式・古代文明の謎)は最大1件まで。視聴者の手の届く範囲の現象を優先する。"
    ],
    "title_style": "タイトルは【疑問形 + 希少性ワード + 具体数字】の3点セットで書く（2026-08-04 PDCA の上位動画がこの型）。①必ず「なぜ〇〇なのか？」「〇〇の本当の理由」のような疑問形にする（成功動画の94%が疑問形）。②「99%が知らない」「実は9割の人が勘違いしている」「知らないのは損」のような希少性ワードを必ず1つ入れる。③「0.3秒」「30秒」「2倍」「17件」のような具体的な数字を必ず1つ入れる（体感できる小さい数字ほど強い）。結論はタイトルに含めない。70字前後を目安にする。④タイトルは『説明』ではなく『衝動』を作る——読んだ瞬間に指が止まる語（実は/なぜ/だけ/本当は/知らない/やめて）を必ず入れ、「〜について」「〜とは」「〜を解説」のような説明語尾は使わない。",
    "viral_hooks": "「なぜ〇〇なのか」の疑問形 / 「99%が知らない」系の希少性ワード / 具体的な数字（0.3秒・2倍・17件） / 体の不思議・睡眠・夢という誰もが毎日体験する題材 / 意外性 / 日常と科学のギャップ / 視聴者自身の体験との接続 / 冒頭3秒の『これ知ってた？』型フック / 身体の謎・食べ物の科学のシリーズ連作",
    "series_lineup": [
      "体の謎シリーズ",
      "睡眠と夢シリーズ",
      "食べ物の科学シリーズ",
      "感覚のふしぎシリーズ",
      "毎日の習慣シリーズ",
      "身の回りのモノの科学シリーズ"
    ],
    "title_power_words": [
      "体",
      "脳",
      "睡眠",
      "毎日",
      "危険"
    ]
  },
  "theme_blacklist": [
    "骨伝導",
    "しゃっくり",
    "横隔膜",
    "録音した自分の声",
    "録音の声",
    "自分の声が別人",
    "宇宙",
    "天体",
    "星",
    "銀河",
    "酸素が1秒",
    "ドアが閉まる寸前",
    "センサーの待機設計",
    "本を読むと眠くなる",
    "本だけで眠く",
    "待機設計",
    "ドアが閉ま",
    "酸素が消え",
    "口の乾き",
    "本を開いた",
    "本を読むと"
  ],
  "genre_blacklist": [
    "宇宙・天体",
    "日常の違和感"
  ],
  "theme_seeds": [
    {
      "title": "なぜ金縛りは『いつも決まった時間』に起きるのか",
      "angle": "レム睡眠中に体だけが眠ったままになる仕組み。発生時刻が偏る理由を睡眠周期の90分サイクルから説明する"
    },
    {
      "title": "夢を見ている時間は実は一晩でたった〇分しかない",
      "angle": "レム睡眠の総量と、体感時間が引き伸ばされて感じる理由。朝には8割忘れている記憶固定のメカニズム"
    },
    {
      "title": "眠りに落ちる瞬間、脳が最後に手放す感覚はどれなのか",
      "angle": "入眠時に視覚・聴覚・触覚が落ちる順番。寝落ち直前に声だけ聞こえる現象の正体"
    },
    {
      "title": "夢遊病の人が朝まったく覚えていない本当の理由",
      "angle": "深いノンレム睡眠中に運動野だけが起きる解離状態。記憶を作る海馬が眠ったままである点を軸にする"
    },
    {
      "title": "睡眠不足の脳は、起きたまま数秒だけ眠っている",
      "angle": "マイクロスリープの実態。自覚がないまま脳の一部が局所睡眠に入る研究データで危険性を示す"
    },
    {
      "title": "なぜ二度寝はあんなに気持ちいいのか",
      "angle": "睡眠慣性と報酬系ドーパミンの関係。浅いレム睡眠に再突入することで多幸感が生まれる仕組み"
    },
    {
      "title": "アラームが鳴る直前に自然に目が覚める人の脳で起きていること",
      "angle": "起床予定時刻に合わせてコルチゾールが先回りして分泌される『予期覚醒』の研究を軸にする"
    },
    {
      "title": "なぜ鳥肌は寒さだけでなく感動でも立つのか",
      "angle": "立毛筋という『毛を逆立てる名残の筋肉』が、恐怖・感動・音楽で誤作動する仕組み。進化の遺物が感情スイッチになった理由"
    },
    {
      "title": "正座で足がしびれるのは血ではなく『神経の悲鳴』だった",
      "angle": "圧迫されているのは血管より神経。ジンジンの正体は神経が再起動する時の誤信号であることを段階的に解説"
    },
    {
      "title": "なぜ冷たい物を一気に食べると『こめかみ』が痛くなるのか",
      "angle": "アイスクリーム頭痛。口内の冷却が三叉神経を介して頭の痛みとして誤認される関連痛の仕組みを、数秒で再現できる現象として説明する"
    },
    {
      "title": "なぜ耳が詰まった感じはあくびで一瞬で治るのか",
      "angle": "耳管が開いて中耳と外気の気圧差が解消される瞬間。エレベーターや飛行機で誰もが体験する数秒の現象を軸にする"
    },
    {
      "title": "なぜ目にゴミが入っていないのに涙が出るのか",
      "angle": "反射性分泌と基礎分泌の違い。あくび・玉ねぎ・強い光で出る涙は成分そのものが違うという事実を軸にする"
    },
    {
      "title": "なぜ高い所に立つと足の裏がゾワッとするのか",
      "angle": "危険を『感じる前』に脊髄と前庭系が先に反応する防御反射。ゾワッの正体は落下シミュレーションを体が勝手に始めている信号だと解説"
    },
    {
      "title": "なぜエレベーターが下がる瞬間、体がフワッと浮く感じがするのか",
      "angle": "内耳の耳石が慣性でズレて『落下中』と誤報する仕組み。0.5秒で誰もが再現できる感覚・反射系フック"
    }
  ],
  "video_format": {
    "layout": {
      "width": 1920,
      "height": 1080,
      "fps": 24,
      "char_canvas_w_ratio": 0.418,
      "char_y_offset": 130,
      "char_x_inset_ratio": 0.15,
      "speaker_glow": true,
      "nonspeaker_opacity": 0.5,
      "text_box_height_ratio": 0.2,
      "text_box_opacity": 180,
      "text_font_size": 42,
      "text_stroke_width": 3,
      "text_line_spacing": 4,
      "text_margin_x": 60,
      "illustration_size": 360,
      "illustration_interval": 30
    },
    "colors": {
      "bg_color": [
        15,
        25,
        50,
        255
      ],
      "text_box_color": [
        10,
        20,
        42
      ],
      "text_stroke_color": [
        0,
        0,
        0
      ]
    },
    "audio": {
      "speed": 1.3,
      "pause_between": 0.3,
      "bgm_volume": 0.3,
      "bgm_path": null
    },
    "illustration_style": {
      "style": "vivid",
      "format": "landscape",
      "art_style": "colorful hand-drawn educational illustration in a slightly more refined, textbook-diagram-leaning manga style — pop and friendly, but a touch more serious and structured than typical kawaii art. Confident, slightly thinner and more precise outlines like a science textbook figure with cartoon warmth, flat-color shading with subtle gradients, restrained sparkle decorations used sparingly. Lines are firm and the look is closer to a textbook diagram than full kawaii.",
      "background": "soft pastel cream background, comic-panel layout with a thick red border frame around the whole illustration",
      "include_characters": true,
      "frame_style": "comic-red-border",
      "extra_prompt": "Anatomically accurate structural drawing where relevant (spine, organs, cells, mechanisms). Gently anthropomorphize the central scientific concept with simple dot-and-curve eyes and small modest expressions (NOT big sparkly anime eyes). Use neat Japanese labels with pointer lines, clear arrows, and small icons to explain cause→effect — like a friendly science textbook figure. Comic-panel layout with a thick red border frame. Educational science explainer that is cute and approachable but leans toward textbook clarity.",
      "allow_text_labels": true,
      "allow_frame": true
    },
    "branding": {
      "watermark_text": null,
      "cta_style": "casual"
    },
    "output": {
      "target_duration": 720,
      "gen_type": "short",
      "bg_type": "static",
      "bg_path": "assets/backgrounds/classroom.png",
      "use_illustrations": true
    },
    "youtube": {
      "channel_id": "UC1OckVkZahT3_fM6W8hD6dg",
      "default_tags": [
        "ゆっくり解説",
        "科学",
        "雑学",
        "日常の謎",
        "ゆっくり霊夢",
        "ゆっくり魔理沙",
        "豆知識",
        "科学解説",
        "日常科学",
        "雑学動画",
        "不思議",
        "教育"
      ],
      "default_category": "27",
      "privacy_status": "private",
      "upload_schedule": null
    },
    "analytics": {
      "enabled": true,
      "fetch_retention_for": 10,
      "performance_threshold": {
        "min_ctr": 4,
        "min_retention": 40,
        "min_views_7d": 1000
      }
    },
    "short_illustrations": {
      "enabled": true,
      "illustration_method": "dalle",
      "max_count": 2,
      "card_style": "textbook",
      "card_label": "解説",
      "card_accent": [
        74,
        108,
        212
      ],
      "card_x": 64,
      "card_y": 250,
      "card_w": 952,
      "card_h": 430,
      "char_cy": 905,
      "char_icon_d": 210
    },
    "effects": {
      "enabled": true,
      "preset": "science",
      "allow_shake": false,
      "allow_flash": false,
      "allow_pixelate": false,
      "allow_glitch": false,
      "allow_tint": false,
      "short_beat_zoom": true,
      "beat_interval": 2.0,
      "beat_zoom_max": 0.04
    }
  },
  "autopilot": {
    "enabled": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 18,
      "minute": 0,
      "times": [
        {
          "hour": 18,
          "minute": 0,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 13,
          "minute": 0,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 12,
    "gen_type": "short",
    "publish_lead_minutes": 45,
    "theme_queue": [
      {
        "id": "5d50f589",
        "title": "なぜ暗い所から出た瞬間だけ世界が白く飛ぶのか",
        "angle": "明順応にかかる秒数と、桿体細胞が飽和する仕組み"
      },
      {
        "id": "043d5f52",
        "title": "なぜ階段の最後の一段を踏み外した気がするのか",
        "angle": "脳が先に作っていた段数の予測と実際がズレる瞬間"
      },
      {
        "id": "737cd346",
        "title": "なぜ寝る直前に限って昔の失敗を思い出すのか",
        "angle": "入眠時に前頭前野の抑制が外れて記憶が浮上する仕組み"
      },
      {
        "id": "b08c207d",
        "title": "なぜ舌をやけどすると数日だけ味がわからなくなるのか",
        "angle": "味蕾の入れ替わり周期が10日前後という事実を軸に"
      },
      {
        "id": "9f0c4f29",
        "title": "なぜ人混みでも自分の名前だけ聞こえるのか",
        "angle": "カクテルパーティー効果。聞いていないはずの音の処理"
      },
      {
        "id": "be83588b",
        "title": "なぜ目を強くこすると光の模様が見えるのか",
        "angle": "眼内閃光。圧力が光の信号に化ける仕組み"
      },
      {
        "id": "c419bc67",
        "title": "なぜ甘い物のあとに塩気が欲しくなるのか",
        "angle": "味覚の順応と対比効果。3分で戻る感度の変化"
      },
      {
        "id": "6ef44362",
        "title": "なぜ蚊に刺された場所は数分してから痒くなるのか",
        "angle": "刺された瞬間ではなく後から来る理由。免疫反応の時間差"
      },
      {
        "id": "cef6c49e",
        "title": "なぜ歩くとき腕は足と逆に振れるのか",
        "angle": "回転の打ち消し。意識せずに体が行う制御"
      },
      {
        "id": "5bc58354",
        "title": "なぜ濡れた紙は破れやすくなるのか",
        "angle": "繊維の絡み合いが水でほどける仕組み"
      },
      {
        "id": "6f60d0ea",
        "title": "なぜ寝起きの口の中だけネバつくのか",
        "angle": "睡眠中に唾液の分泌が1/10に落ちる事実を軸に"
      },
      {
        "id": "3e731a87",
        "title": "なぜ長時間座ると腰だけが先に痛むのか",
        "angle": "椎間板にかかる圧力が立位の1.4倍になる仕組み"
      },
      {
        "id": "57cf3e1d",
        "title": "なぜコップの水は放置すると気泡がつくのか",
        "angle": "溶けていた空気が出てくる温度と時間"
      },
      {
        "id": "13275eee",
        "title": "なぜ歩いている途中で急に足の運び方がわからなくなるのか",
        "angle": "自動化された動作を意識した瞬間に崩れる現象"
      },
      {
        "id": "e2e9ce7a",
        "title": "なぜ声を出さずに読んでいるのに喉が動くのか",
        "angle": "黙読中の微細な発声筋の活動"
      }
    ],
    "auto_optimize_schedule": true
  },
  "voice_style": {
    "tone": "隣に座って教えてくれる距離感の語り。専門用語より『あなたも昨日やったはず』の実体験から入る。授業・講義のトーンにはしない。視聴者自身の体で起きていることだと最後まで意識させる",
    "narrator_persona": "身近な現象を専門にしている解説役。難しい仕組みを噛み砕くのが得意で、必ず『あなたの体でも今こうなっている』と視聴者に接続してから説明に入る。分かっていないことは『ここは科学でもまだ結論が出ていない』と正直に言う",
    "opening_hooks": [
      "これ知ってた？ 昨日の夢、思い出せないのには理由がある",
      "実は今この瞬間も、あなたの体で同じことが起きてる",
      "これ、99%の人が理由を知らないまま毎日やってる",
      "なんで冷たい物を食べると頭が痛くなるの？考えたことある？",
      "寝る前にスマホ見た結果、体で起きてることがヤバい"
    ],
    "forbidden": [
      "SCP",
      "財団",
      "収容",
      "[REDACTED]",
      "DATA EXPUNGED",
      "シロ",
      "クロ",
      "ヒカリ",
      "ソラ",
      "ケンタ"
    ],
    "style_rules": [
      "1行目は必ず「これ知ってた？」「実は〇〇」「〇〇した結果」「なんで〇〇だけ〇〇なの？」のいずれかの型で始める。挨拶・テーマ紹介から入るのは禁止（冒頭3秒で離脱するため）。",
      "ショートの5行目には必ず『しかも』『ところが』で角度を変える意外な展開を置き、中盤の飽きを断ち切る。",
      "冒頭10秒で視聴者自身の体験に接続する（例：『寝る前にスマホ見てて、急に体がビクッとなったことない？』）。",
      "結論・答えは冒頭で言わない。疑問と違和感だけを提示して、本編で解く。",
      "専門用語を出したら必ずその場でひと言に言い換える。言い換えなしで先に進まない。",
      "リスナー役のリアクションは『言われてみれば確かに』『それ昨日あった』のような自分事化を中心にする。",
      "科学的に未解明な部分は誤魔化さず『ここはまだ分かっていない』と言い切る。断定で埋めない。",
      "締めは『今夜寝るとき、ちょっと意識してみて』のように、視聴者が今日試せる形でまとめる。",
      "そのうえで**動画の最後の1行は必ずチャンネル登録の誘導で終える**（例:『面白かったらチャンネル登録よろしくね。毎日1本、身近な不思議を解いてるから、明日も一緒に見てほしいな』）。Tips や余韻で終わって登録に触れないのは禁止。",
      "解説役は必ず丁寧語（です・ます）で話す。1行でもタメ口の解説が混ざったら不合格。リスナー役だけがタメ口で驚く、という役割分担で親しみやすさと丁寧さを両立させる。",
      "1本につき最低1つ、身近な物への例え話を必ず入れる（例:『満員電車』『水道のホースを踏む』『スマホの通知』）。専門用語をそのまま置いていくのは不合格。",
      "驚きの表現は『へぇ〜、知らなかった！』『えっ、そうなんですか!?』系の明るい驚きで統一する。『怖い』『ゾッとする』のような恐怖寄りの語彙は使わない（SCPラボと差別化するため）。"
    ],
    "speech_signature": "解説役(理子)は『です・ます』の柔らかい丁寧語で話す。堅い講義口調ではなく、隣で教えてくれる先輩の丁寧語（『〜なんです』『〜してみてください』）。リスナー役(真)は敬語を崩したタメ口寄りで、驚きを素直に出す（『えっ、そうなんだ！』）。2人とも汚い言葉・ネットスラング・煽り口調は使わない",
    "pacing": "説明1つにつき必ず驚きのリアクションを1つ挟む。説明→驚き→説明→驚き、の交互リズムを最後まで崩さない。畳みかけて連続で説明しない",
    "signature_phrases": [
      "へぇ〜、知らなかった！",
      "たとえるなら、〇〇と同じなんです",
      "言われてみれば確かに",
      "実はこれ、今あなたの体でも起きています",
      "ここ、面白いのが"
    ],
    "reaction_style": "リスナー役のリアクションは『へぇ〜、知らなかった！』『えっ、それ昨日やった！』のような素直な驚き＋自分事化を中心にする。皮肉・ツッコミ・煽りは使わない",
    "banned_phrasing": [
      "怖い・不気味・呪い・ゾッとするなどのホラー寄りの語彙（このチャンネルは明るい驚きで引っ張る）",
      "『〜だぜ』『〜だろ』のような粗い男口調",
      "ネットスラング（草・ワロタ・ワイ・お前ら）",
      "「いかがでしたか」「〜について解説します」のような定型の説明語尾"
    ],
    "hook_patterns": [
      {
        "name": "体感再現型",
        "template": "「今すぐ〇〇してみてください」で始め、視聴者がその場で再現できる数秒の体感から入る",
        "example": "今すぐ耳をふさいでみてください。あのゴーって音、血の流れる音じゃないんです"
      },
      {
        "name": "これ知ってた？型",
        "template": "「これ知ってました？ 〇〇って実は△△なんです」— 共感と好奇心を同時に取る",
        "example": "これ知ってました？ あくびって、眠いから出るわけじゃないんです"
      },
      {
        "name": "常識ひっくり返し型",
        "template": "「実は〇〇、△△だったんです」— 誰もが正しいと思っていることを1行で覆す",
        "example": "実は冷たい物で頭が痛くなるの、頭は全然冷えてないんです"
      },
      {
        "name": "違和感の問い型",
        "template": "「なんで〇〇だけ△△なんでしょう？」— 言われて初めて気づく違和感を突く",
        "example": "なんで正座のしびれだけ、あんなに痛いんでしょう？"
      },
      {
        "name": "たとえ話先出し型",
        "template": "身近な物のたとえを先に出してから、それが体の話だと明かす",
        "example": "満員電車で身動きが取れなくなる、あれと同じことが今あなたの足で起きています"
      }
    ]
  },
  "short_series_name": "1分科学：",
  "short_format": {
    "line_count": 8,
    "line_chars": "1〜7行目は30〜42字（目標36字）、8行目のみ50〜70字を許容",
    "total_chars_min": 280,
    "total_chars_max": 350,
    "structure": [
      "1行目=**3秒フック(最重要)**: 「これ知ってた？」「実は〇〇」「なんで〇〇だけ〇〇なの？」型で始める。挨拶・自己紹介は禁止。視聴者が『え？』と指を止める疑問形にする。",
      "2行目=**リスナーのリアクション**: 真が素直に驚く・食いつく（『えっ、そうなんですか!?』『言われてみれば確かに』）。解説は始めない。",
      "3行目=**核となる事実①**: 必ず具体的な数字・研究データ・固有名詞を1つ以上含める（例:「実は97%の人が…」「0.3秒で…」）。",
      "4行目=**たとえ話で自分ゴト化**: 3行目を身近な物に例える（『満員電車で…と同じ』『スマホの通知みたいなもの』）。専門用語をそのまま放置しない。",
      "5行目=**意外な展開**: 『しかも』『ところが』で角度を変える。中盤の飽きを断ち切る一撃。",
      "6行目=**核となる事実②**: 5行目の意外性を裏付ける2つ目の事実。数字か具体例を必ず入れる。",
      "7行目=**オチ**: 短くスパッと結論。『だから〇〇だったんです』の形で納得感を出す。",
      "8行目=**登録CTA+余韻**: 『今日から意識してみてください。面白かったらチャンネル登録よろしくね。毎日1本、身近な不思議を解いてるよ』"
    ],
    "extra_rules": [
      "解説役(理子)は必ず丁寧語（です・ます）。1行でもタメ口が混ざったら不合格。リスナー役(真)だけがタメ口。",
      "1本につき最低1つ、身近な物への例え話を必ず入れる。",
      "『怖い』『ゾッとする』のような恐怖寄りの語彙は使わない（SCPラボと差別化）。",
      "冒頭で結論を言わない。疑問と違和感だけを提示して本編で解く。"
    ]
  }
}```

### `data/channels/pokemon-lab.json`

```json
{
  "id": "pokemon-lab",
  "name": "ゆっくりポケラボ",
  "concept": "ポケモンの「え、マジで？」を1本1本届けるチャンネル。最強ランキング・ガチ対決・図鑑の衝撃事実を軸に、知った瞬間に誰かに話したくなる驚きを配る。教科書的な解説ではなく、驚き→ツッコミ→答え合わせのテンポで最後まで見せる。",
  "short_series_name": "1分ポケモン研究：",
  "style": "yukkuri",
  "youtube_channel_id": "UCGgc5REGTWRLnBiSeXXkJ5w",
  "image_mode": "collect",
  "image_collect": {
    "provider": "auto",
    "safe_search": true,
    "license_filter": "cc",
    "max_per_query": 5,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic"
  },
  "voice_style": {
    "tone": "驚きとテンションで押す実況寄りのトーク。『え、マジで？』『知らんかった…』というリアクションの連続で引っ張る。落ち着いた解説調・授業っぽい語りは厳禁。数字や順位を口に出して、常に驚きの大きさを体感させる",
    "narrator_persona": "ポケモン廃人寄りの研究員。データも設定も頭に入っているが、語り口は友達との雑談テンション。結論を先に匂わせて引っ張り、根拠（図鑑テキスト・種族値・作中描写）は驚きの答え合わせとして出す。ファンの俗説を語るときは『これはファンの説なんだけど』と必ず断る",
    "opening_hooks": [
      "これ知ってた？ この2匹、実は相性が逆なんだ",
      "実はこのポケモン、種族値だけ見ると壊れてる",
      "この2匹を本気で戦わせた結果、3ターンで終わった",
      "なんでこのポケモンだけ、進化しても素早さが下がるの？"
    ],
    "forbidden": [
      "SCP",
      "財団",
      "収容",
      "[REDACTED]",
      "DATA EXPUNGED",
      "呪い",
      "ゾッとする",
      "シロ",
      "クロ",
      "リコ",
      "マコト",
      "理子",
      "真"
    ],
    "style_rules": [
      "1行目は必ず「これ知ってた？」「実は〇〇」「〇〇した結果」「なんで〇〇だけ〇〇なの？」型の3秒フックで始める。挨拶・研究所の前置き・テーマ紹介から入るのは禁止。",
      "ショートの5行目には『しかも』『ところが』で角度を変える一撃（想定外の相性・裏の数字）を必ず置く。",
      "『怖い』ではなく『驚き・意外・草』で引っ張る。ホラー演出や不気味な余韻で締めない。",
      "冒頭5秒で驚きの結論を匂わせる（例：『実はこいつ、伝説のポケモンより種族値が高い』）。ただし答えそのものは言わない。",
      "ランキング・対決回は必ず数字（順位・種族値・ダメージ・確率）を口に出す。数字が驚きの燃料になる。",
      "根拠は必ずゲーム内図鑑テキスト・公式設定・作中描写に置く。ファンの創作説は『ファンの間ではこう言われている』と明示して事実と分ける。",
      "リスナー役（ソラ）のリアクションは驚き・ツッコミ・悔しがりを中心にする（例:『えっ、そんな設定あるの!?』『いや強すぎでしょ』『それ知らなかった！』）。",
      "締めは『次に遊ぶとき、ちょっと見方が変わるはず』のような、視聴体験が持ち帰れる前向きな余韻で終える。",
      "対戦の話題では初心者を置き去りにしない。用語（種族値・耐性・上位互換など）は毎回ひと言で補足する。",
      "ゲーム用語（種族値・タイプ相性・特性・技名・厳選・上位互換）は自然に使う。ただし初めて出す用語だけ、その場でひと言（10字以内）で補足して初心者を置き去りにしない。",
      "1本につき最低1回は『知ってた？』系の豆知識トーンで、視聴者が人に話したくなる事実を置く。",
      "ワクワク感を最優先する。怖さ・不気味さで引っ張るのは他チャンネルの役割なので使わない。"
    ],
    "speech_signature": "解説役(ヒカリ研究員)はテンション高めのタメ口実況（『〜なんだよ！』『やば、これ見て』）。リスナー役(ソラ)は食い気味のツッコミ（『えっ待って！』『いや強すぎでしょ』）。丁寧語の講義口調・不気味な語りは使わない",
    "pacing": "驚き→根拠→さらに驚き、で押し切る。落ち着いた説明が2行続いたらテンポが死ぬ。数字を口に出すたびに相方が反応して、勢いを切らさない",
    "signature_phrases": [
      "知ってた？ このポケモン実は",
      "種族値だけ見ると",
      "初代からずっと",
      "対戦だとこれが刺さる",
      "いや強すぎでしょ"
    ],
    "reaction_style": "リアクションは驚き・ツッコミ・悔しがりで統一する（『えっ、そんな設定あるの!?』『それ知らなかった！』『ずるいって』）。怖がる・不気味がる反応は使わない",
    "banned_phrasing": [
      "ホラー寄りの語彙（呪い・ゾッとする・近づくな）",
      "落ち着いた講義口調（〜について解説します）",
      "ネットスラングの多用（草・ワイ・お前ら）",
      "公式設定とファンの説を混ぜた断定"
    ],
    "hook_patterns": [
      {
        "name": "豆知識型",
        "template": "「知ってた？ このポケモン、実は〇〇なんだ」— 好きなポケモンの意外な一面を1行で置く",
        "example": "知ってた？ ピカチュウ、初代だと今より圧倒的に弱い"
      },
      {
        "name": "対決型",
        "template": "「〇〇と△△、本気で戦わせたら」— 誰もが気になる対戦カードを結果を伏せて出す",
        "example": "ミュウツーとアルセウス、本気で戦わせた結果が意外すぎた"
      },
      {
        "name": "数字型",
        "template": "種族値・順位・確率などの数字を先に出して、驚きの大きさを体感させる",
        "example": "実はこいつ、種族値だけ見ると伝説より上なんだ"
      },
      {
        "name": "違和感型",
        "template": "「なんでこのポケモンだけ〇〇なの？」— 言われて初めて気づくゲーム内の違和感を突く",
        "example": "なんでこのポケモンだけ、進化すると素早さが下がるの？"
      },
      {
        "name": "元ネタ型",
        "template": "「このポケモンのモデル、実は〇〇なんだ」— 図鑑テキストや実在のモチーフから入る",
        "example": "このポケモンのモデル、実在する深海生物なんだ"
      }
    ]
  },
  "theme_priority": {
    "label": "驚き・ランキング・対決・衝撃事実（『え、マジで？』が取れる題材）",
    "categories": [
      "【最優先】対決・比較系: 『AとB、どっちが勝つ？』『伝説vs最終進化』など、2匹を名指しで比べて勝敗をはっきりさせる対戦シミュレーション（2026-08-15 実データで初動2230回/日とチャンネル最高。毎バッチ最低2件は必ず入れる）",
      "ランキング系: 最強／最弱／不遇／種族値／進化前後の落差など、順位で驚かせる題材",
      "衝撃事実系: 図鑑テキストの怖すぎる／意味深すぎる一文、公式が書いた信じられない設定",
      "個別ポケモンの裏設定・進化の秘密・モチーフ元ネタ（伝説・幻・準伝説含む）",
      "対戦・ゲームシステムの衝撃仕様（隠し仕様・乱数・有名なバグや裏技の仕組み）"
    ],
    "required_count_per_batch": 5,
    "good_examples": [
      "種族値だけで選んだ『実は最強』ポケモン10選 — 1位は誰も予想できない",
      "ポケモン図鑑の『怖すぎる』説明文5選 — 公式が書いた衝撃の一文",
      "ミュウツーとレックウザ、まともに戦わせたらどっちが勝つのか",
      "実は伝説より強い一般ポケモン — 種族値を並べたら順位が壊れた",
      "コイキングが『史上最弱』と言われる本当の理由 — 数字で見ると想像以上だった"
    ],
    "avoid_categories": [
      "実在の事件・人物と絡めた不謹慎な都市伝説（『死亡説』『呪いのカセット』系の悪質なデマ）",
      "SCP・ホラー系の恐怖演出に寄せた題材",
      "最新作の未発売情報・リーク・非公式データマイニング",
      "淡々とした図鑑解説・学術的な考察のみで、驚きの山が1つも無い題材"
    ],
    "title_style": "タイトルは『数字＋断定』か『疑問形』で書く。ランキングは必ず件数を入れる（例:『〜10選』『〜5体』）、対決は『AとB、どっちが勝つ』形式にする。ポケモン名・キャラ名は具体的に出す（検索性が高い）。答え・1位の正体はタイトルに書かない。",
    "viral_hooks": "ランキングの1位 / 意外な勝敗 / 数字のインパクト（種族値・順位・確率） / 図鑑の意味深な一文 / 『言われてみれば確かに』のギャップ",
    "series_lineup": [
      "1分ガチ対決シリーズ",
      "種族値のウソホントシリーズ",
      "裏設定ファイルシリーズ",
      "図鑑の説明が怖いシリーズ",
      "対戦で強すぎたポケモンシリーズ"
    ],
    "title_power_words": [
      "最強",
      "裏設定",
      "没データ",
      "図鑑",
      "ガチ",
      "対決",
      "禁止級"
    ]
  },
  "theme_blacklist": [
    "レックウザの誕生"
  ],
  "genre_blacklist": [],
  "competitors": [
    "UCHXkvCESxccj02BImzfmDlw",
    "UCL3E0Lnc1u1IM_VeRCDjHLw",
    "UCBewJ-4SIBjOYrUbDzTa_Sw",
    "UCA9hKZZvvKiZJScu1z_3Hlg",
    "UCj9lNAB5SDJpC_kLb4lO81Q",
    "UCCheFbpkibJ0pe98AEZOcig",
    "UCBeu36X_DJQa51yUZcYBYng"
  ],
  "theme_seeds": [
    {
      "title": "ミュウツーの誕生秘話",
      "angle": "ミュウの遺伝子から生まれた経緯を、図鑑テキストと作中の研究日誌描写から追う"
    },
    {
      "title": "レッドの正体",
      "angle": "無口な主人公がチャンピオンとして山頂に立つまで。作品を跨いだ描写から人物像を考察"
    },
    {
      "title": "ポケモン図鑑の怖すぎる説明文",
      "angle": "公式が書いた衝撃的な図鑑テキストを厳選。なぜそう書かれたのかまで踏み込む"
    },
    {
      "title": "なぜイーブイは8種類も進化するのか",
      "angle": "不安定な遺伝子という設定と、各進化先の分岐条件を整理する"
    },
    {
      "title": "ミュウとミュウツーの決定的な違い",
      "angle": "幻と人工。種族値・技・設定の三面から比較する"
    },
    {
      "title": "御三家が炎・水・草である理由",
      "angle": "三すくみの設計思想と、シリーズを通した例外の有無"
    },
    {
      "title": "ヤドンとシェルダーの共生関係の謎",
      "angle": "噛まれると進化する仕組みと、ヤドキング分岐の設定を読み解く"
    },
    {
      "title": "ゲンガーの元ネタは影？",
      "angle": "ファンの間で語られる説と、公式設定として確認できる範囲を切り分ける"
    },
    {
      "title": "伝説のポケモンはなぜ1匹しかいないのか",
      "angle": "作中の設定と、ゲームシステム上の扱いのズレを考察"
    },
    {
      "title": "種族値って結局なに？",
      "angle": "対戦の基礎。数字が実際のバトルでどう効くかを初心者向けに解説"
    },
    {
      "title": "初代の伝説的バグ『けつばん』の正体",
      "angle": "なぜ発生したのか、データ構造の観点からやさしく解説"
    },
    {
      "title": "悪の組織はなぜ毎回ポケモンを狙うのか",
      "angle": "ロケット団からの歴代組織の目的を比較して共通構造を探る"
    },
    {
      "title": "ポケモンの世界に人間の食文化はあるのか",
      "angle": "作中描写から生態系と食文化の設定を推理する"
    },
    {
      "title": "ラプラスの図鑑説明に隠された悲しい設定",
      "angle": "乱獲で数を減らしたという記述の意味と、シリーズでの扱いの変化"
    },
    {
      "title": "なぜコイキングはあれほど弱いのか",
      "angle": "弱さの設定意図と、ギャラドス進化のギャップ演出を考察"
    },
    {
      "title": "ガブリアスとギャラドス、どっちが勝つ？",
      "angle": "種族値・タイプ相性・実際の技構成の三面で比較。相性有利がひっくり返る条件まで詰める"
    },
    {
      "title": "ミュウツーとアルセウス、どっちが勝つ？",
      "angle": "最強議論の定番。設定上の強さとゲーム上の数値のズレを分けて勝敗を出す"
    },
    {
      "title": "バンギラスとメタグロス、どっちが勝つ？",
      "angle": "600族対決。特性と持ち物1つで結論が変わる実戦条件を軸にする"
    },
    {
      "title": "リザードンとカイリュー、どっちが勝つ？",
      "angle": "人気ドラゴン対決。4倍弱点をどう処理するかで勝敗が割れる点を実戦想定で比べる"
    }
  ],
  "characters": {
    "ヒカリ研究員": {
      "side": "left",
      "speaker_id": 16,
      "dir": "hikari",
      "text_color": [
        255,
        230,
        90
      ],
      "expressions": [
        "normal",
        "happy",
        "surprise",
        "think"
      ],
      "thumb_dir": "hikari",
      "thumb_expression": "happy",
      "role": "解説役（ポケモン研究所の若手研究員。図鑑データを愛する知識派の女の子）",
      "appearance": "young Japanese anime girl named Hikari with short orange-brown bob hair and bright amber eyes, wearing a white researcher coat over a red trainer jacket, a pokedex-like tablet in hand, cheerful confident expression, chibi-style with a big round head and big eyes, bright pop explainer character"
    },
    "ソラ": {
      "side": "right",
      "speaker_id": 39,
      "dir": "sora",
      "text_color": [
        120,
        220,
        255
      ],
      "expressions": [
        "normal",
        "happy",
        "surprise",
        "sad"
      ],
      "thumb_dir": "sora",
      "thumb_expression": "surprise",
      "role": "リスナー役（旅立ったばかりの新米トレーナーの男の子。素直に驚いて質問する）",
      "appearance": "young Japanese anime boy named Sora with messy dark blue hair and big round eyes, wearing a blue-and-white trainer cap and a green backpack, excited surprised expression, chibi-style with a big round head and big eyes, bright pop explainer character"
    }
  },
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "みんなならどっちが勝つと思う？コメントで予想を聞かせて！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "1分ポケモン研究｜ショート全集",
      "main": "ポケラボ｜本編考察",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "考察してほしいポケモン・図鑑説明をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "main_intro": "{title}について、ヒカリ研究員とソラがゆっくり考察します。\nポケモンの裏設定・都市伝説・図鑑の謎・対戦の豆知識を、公式設定を手がかりにワクワク解説していきます。\n※本動画はファンによる非公式の考察コンテンツです。ポケモンは株式会社ポケモン／任天堂の登録商標です。\nぜひ最後までご視聴ください！",
    "main_hashtags": "#ポケモン #ポケモン考察 #ゆっくり解説 #裏設定 #都市伝説",
    "short_hashtags": "#shorts #ポケモン #ゆっくり解説 #ポケモン考察 #裏設定"
  },
  "thumbnail_template": {
    "badge_text": "ポケモン考察",
    "badge_color": [
      40,
      90,
      200
    ],
    "hook_color": [
      255,
      222,
      0
    ],
    "subtitle_color": [
      255,
      190,
      205
    ],
    "style_hint": "明るくポップなポケモン考察系サムネイル。\n- 背景は『明るく・カラフル・元気』を最優先。暗い／ホラー調／陰鬱は絶対NG。\n- background_concept には必ず『bright, vibrant, colorful, playful, daylight, cheerful, high-key lighting, pastel sky, adventure field』のような明るさキーワードを複数含める。『dark / moody / dim / horror / night』などは禁止。\n- 配色はモンスターボール由来の赤×白×黒をアクセントに、鮮やかな青空・草原・エネルギー光のカラフルな背景を組み合わせる。\n- line1（白）は前振り（例:『図鑑に書かれた…』『実はこの設定』）。line2（黄・強調）が核となる驚き（『衝撃の一文』『誕生の真実』）でインパクト最大化。\n- line3_badge は赤で『裏設定』『公式設定』『知らないと損』など。sub_text はポケモン名・キャラ名を具体的に出して検索性と具体性を上げる。\n- 被写体は中央〜上部に置き、下部は文字用に空けるが暗くせず明るいグラデーション（白／クリーム／薄水色）にする。\n- 版権キャラそのものの精密な再現は避け、モンスターボール・図鑑デバイス・エネルギーオーラ・草原やジムの風景など『象徴的なモチーフ』で世界観を出す。\n- 文字は極太＋黒の強い縁取り（3-5px）、軽いポップな集中線やキラキラ装飾で勢いを出す。"
  },
  "defaults": {
    "speed": 1.3,
    "target_duration": 720,
    "bg_type": "static",
    "bg_path": null,
    "short_bg_query": "bright colorful grassland adventure sky",
    "short_overlay_style": {
      "opening": {
        "font_size_max": 104,
        "font_size_min": 72,
        "stroke_width": 8,
        "glow_stroke_extra": 7,
        "dim_alpha": 110,
        "punch_start_scale": 0.88,
        "accent_color": [
          255,
          190,
          30
        ]
      },
      "hook_caption": {
        "accent_color": [
          255,
          220,
          60
        ],
        "band_alpha": 160,
        "y_center": 1000
      },
      "subtitle": {
        "font_size": 64,
        "line_gap": 86,
        "stroke_width": 6,
        "stroke_color": [
          16,
          34,
          84
        ],
        "color": [
          255,
          255,
          255
        ],
        "glow_color": [
          255,
          205,
          45
        ],
        "glow_extra": 5
      }
    },
    "use_illustrations": true,
    "hashtags": [
      "#ポケモン",
      "#ポケモン考察",
      "#ゆっくり解説",
      "#裏設定",
      "#都市伝説"
    ],
    "short_title_hashtags": "#shorts #ポケモン #ポケモン雑学",
    "category": "20",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "驚き優先・テンション高め（毎回「え、マジで？」を狙う）",
    "age_rating": "all_ages",
    "cta_position": "after_hook",
    "cta_style": "驚きの余韻を残して次の1本に引っ張る",
    "guidelines": [
      "ファンによる非公式の考察であることを明示し、公式設定と憶測を明確に区別する",
      "ランキング・対決は必ず基準（種族値・実測ダメージ・図鑑記述など）を明示し、根拠のない煽りにしない",
      "権利表記（ポケモンは株式会社ポケモン／任天堂の登録商標）を概要欄に記載する",
      "ゲーム画面・公式イラストの長時間そのまま使用は避け、解説図と自作ビジュアル中心で構成する",
      "『死亡説』『呪い』など不謹慎・悪質なデマ系都市伝説は扱わない"
    ],
    "avoid": [
      "版権素材の無断長尺使用",
      "未発売作品のリーク・データマイニング情報",
      "実在人物と絡めた不謹慎な都市伝説",
      "過度なホラー・恐怖演出",
      "根拠を示さない煽りランキング"
    ],
    "short_end_line": {
      "omit_related_video": true,
      "wording": "他の対決も研究所に置いてあるよ"
    },
    "cliffhanger": {
      "enabled": true,
      "wording": "この続き（残りの1匹）はチャンネルの他の動画で"
    }
  },
  "video_format": {
    "layout": {
      "width": 1920,
      "height": 1080,
      "fps": 24,
      "char_canvas_w_ratio": 0.418,
      "char_y_offset": 130,
      "char_x_inset_ratio": 0.15,
      "speaker_glow": true,
      "nonspeaker_opacity": 0.5,
      "text_box_height_ratio": 0.2,
      "text_box_opacity": 180,
      "text_font_size": 42,
      "text_stroke_width": 3,
      "text_line_spacing": 4,
      "text_margin_x": 60,
      "illustration_size": 360,
      "illustration_interval": 30
    },
    "colors": {
      "bg_color": [
        20,
        60,
        120,
        255
      ],
      "text_box_color": [
        12,
        32,
        72
      ],
      "text_stroke_color": [
        0,
        0,
        0
      ]
    },
    "audio": {
      "speed": 1.3,
      "pause_between": 0.3,
      "bgm_volume": 0.3,
      "bgm_path": null
    },
    "illustration_style": {
      "style": "vivid",
      "format": "landscape",
      "art_style": "bright colorful pop illustration in a game-guidebook style — vivid saturated palette of red, blue, yellow and fresh green, confident clean outlines, flat cel shading with light gradients, energetic and friendly. Looks like a page from an official strategy guide rather than kawaii fan art. Never dark or horror-styled.",
      "background": "bright pastel sky-blue background with soft radial burst and a light comic-panel frame in red",
      "include_characters": true,
      "frame_style": "comic-red-border",
      "extra_prompt": "Compose like a game guidebook figure: clear Japanese labels with pointer lines, arrows showing cause→effect, small icons for stats or types. Use original generic creature silhouettes and symbolic props (monster ball motif, pokedex-like device, energy aura, route signposts) instead of copying any copyrighted character design. Keep it bright, energetic and easy to read.",
      "allow_text_labels": true,
      "allow_frame": true
    },
    "branding": {
      "watermark_text": "ポケラボ",
      "cta_style": "casual",
      "source_credit": "※ファンによる非公式考察 / ポケモンは株式会社ポケモン・任天堂の登録商標です",
      "source_credit_opacity": 150,
      "source_credit_font_size": 20,
      "source_credit_font_size_short": 26
    },
    "output": {
      "target_duration": 720,
      "gen_type": "short",
      "bg_type": "static",
      "bg_path": null,
      "use_illustrations": true
    },
    "youtube": {
      "channel_id": "UCGgc5REGTWRLnBiSeXXkJ5w",
      "default_tags": [
        "ポケモン",
        "ポケモン考察",
        "ゆっくり解説",
        "裏設定",
        "都市伝説",
        "ポケモン図鑑",
        "ゲーム考察",
        "ポケモン都市伝説",
        "ポケモン裏設定",
        "ポケモン解説",
        "ポケモン雑学"
      ],
      "default_category": "20",
      "privacy_status": "private",
      "upload_schedule": null
    },
    "analytics": {
      "enabled": true,
      "fetch_retention_for": 5,
      "performance_threshold": {
        "min_ctr": 4,
        "min_retention": 40,
        "min_views_7d": 1000
      }
    },
    "short_illustrations": {
      "enabled": true,
      "illustration_method": "dalle",
      "max_count": 2,
      "card_style": "textbook",
      "card_label": "研究データ",
      "card_accent": [
        230,
        60,
        50
      ],
      "card_x": 64,
      "card_y": 250,
      "card_w": 952,
      "card_h": 430,
      "char_cy": 905,
      "char_icon_d": 210,
      "image_mode": "generate"
    },
    "effects": {
      "enabled": true,
      "preset": "pop",
      "allow_shake": false,
      "allow_flash": true,
      "allow_pixelate": false,
      "allow_glitch": false,
      "allow_tint": false,
      "zoom_max": 0.06,
      "transition_duration": 0.35,
      "short_beat_zoom": true,
      "beat_interval": 1.7,
      "beat_zoom_max": 0.055
    },
    "persona": {
      "age_group": "10代",
      "gender": "男性",
      "interest_categories": [
        "ゲーム",
        "エンタメ"
      ],
      "content_depth": "ミドル"
    }
  },
  "autopilot": {
    "enabled": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 17,
      "minute": 30,
      "times": [
        {
          "hour": 17,
          "minute": 30,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 12,
          "minute": 0,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 12,
    "gen_type": "short",
    "publish_lead_minutes": 45,
    "theme_queue": [
      {
        "id": "44fad5cf",
        "title": "カイオーガとグラードン、天候を張り合ったら本当はどっちが強い",
        "angle": "天候上書きの順番が勝敗を決める仕組み"
      },
      {
        "id": "d55fa530",
        "title": "ドラパルトとガブリアス、なぜ速さが別格と言われるのか",
        "angle": "素早さ種族値と実数値の壁を具体的に示す"
      },
      {
        "id": "0297bac2",
        "title": "サーナイトとエルレイド、同じ進化元なのに戦い方が真逆な理由",
        "angle": "特殊と物理で分岐した設計意図を数字で"
      },
      {
        "id": "87993330",
        "title": "ジバコイルとサーフゴー、鋼タイプ最強の座はどう決まるのか",
        "angle": "耐性数と技範囲で比較する"
      },
      {
        "id": "3ef40b98",
        "title": "エースバーンとゴウカザル、炎の速攻役はどっちが上か",
        "angle": "世代をまたいだ同ロール比較"
      },
      {
        "id": "66a82ec0",
        "title": "ドサイドンとメタグロス、4倍弱点は持ち物1つで覆せるのか",
        "angle": "弱点保険と半減実の実戦効果"
      },
      {
        "id": "f7338b31",
        "title": "ヌケニンはなぜ理論上最強なのに勝てないのか",
        "angle": "無効タイプの多さと、それを崩す1つの要素"
      },
      {
        "id": "faf7af64",
        "title": "ハガネールとギャラドス、同じ進化前なのに強さが割れる理由",
        "angle": "進化先の設計差を種族値配分で説明"
      },
      {
        "id": "6933a687",
        "title": "ラティオスとラティアス、性能差はどこで生まれるのか",
        "angle": "双子伝説の攻守の振り分けを数字で"
      },
      {
        "id": "7b1b8267",
        "title": "ヒードランとウーラオス、鋼と格闘の主役対決",
        "angle": "耐性と一撃の重さを実戦条件で比較する"
      },
      {
        "id": "319e1f59",
        "title": "ジャローダとフシギバナ、草の御三家最強はどっちか",
        "angle": "世代をまたいだ同タイプ比較"
      },
      {
        "id": "fd043106",
        "title": "ラプラスとミロカロス、水の耐久役はどちらが硬いのか",
        "angle": "HPと防御の配分差が実際の耐久に出る仕組み"
      },
      {
        "id": "331e78aa",
        "title": "ハッサムとルカリオ、はがねの物理役はどっちが上か",
        "angle": "先制技の有無が勝敗を決める構造"
      },
      {
        "id": "86096a1e",
        "title": "ザシアンとザマゼンタ、剣と盾で強さが割れた理由",
        "angle": "専用特性の効き方の差を数字で"
      },
      {
        "id": "0657bd76",
        "title": "ドリュウズとランドロス、じめん枠はどちらを選ぶべきか",
        "angle": "役割の違いを実戦の型で比べる"
      },
      {
        "id": "82de21e6",
        "title": "フーディンとサーナイト以外で、エスパー最速は誰か",
        "angle": "素早さ実数値の上位を並べる調査型"
      },
      {
        "id": "44c1dbb6",
        "title": "ヨノワールとサマヨール、進化前の方が強いと言われる理由",
        "angle": "しんかのきせきが覆す耐久の数字"
      },
      {
        "id": "6235506d",
        "title": "キノガッサはなぜ格闘最強と呼ばれた時期があるのか",
        "angle": "特性と技の組み合わせが環境に刺さった経緯"
      }
    ],
    "auto_optimize_schedule": true
  },
  "short_format": {
    "line_count": 8,
    "line_chars": "1〜7行目は28〜40字（目標34字）、8行目のみ50〜70字を許容",
    "total_chars_min": 270,
    "total_chars_max": 340,
    "structure": [
      "1行目=**3秒フック(最重要)**: 「これ知ってた？」「実はこのポケモン〇〇」「なんで〇〇だけ〇〇なの？」型で始める。驚きの結論を匂わせるが答えは言わない。",
      "2行目=**リスナーの驚きリアクション**: ソラが驚く・ツッコむ（『えっ、そんな設定あるの!?』『いや強すぎでしょ』）。",
      "3行目=**核となる事実①**: 種族値・図鑑テキスト・作中描写など、具体的な数字か公式設定を必ず1つ含める。",
      "4行目=**比較で驚きを増幅**: 他のポケモンや伝説ポケモンとの比較で事実の意外性を際立たせる。",
      "5行目=**意外な展開**: 『しかも』『ところが』で角度を変える。裏設定や隠し要素を出す。",
      "6行目=**ファンの間での扱い/実戦での評価**: ファン説は『ファンの間ではこう言われている』と明示。",
      "7行目=**オチ**: 短くスパッと結論。『次に遊ぶとき、ちょっと見方が変わるはず』系の前向きな余韻。",
      "8行目=**登録CTA**: 『面白かったらチャンネル登録よろしく！毎日ポケモンの「え、マジで？」を届けてるよ』"
    ],
    "extra_rules": [
      "『怖い』ではなく『驚き・意外・草』で引っ張る。ホラー演出は禁止。",
      "根拠は必ずゲーム内図鑑テキスト・公式設定・作中描写に置く。ファンの創作説は明示して事実と分ける。",
      "ランキング・対決回は必ず数字（種族値・ダメージ・確率）を口に出す。",
      "初心者を置き去りにしない。用語は毎回ひと言で補足する。"
    ]
  }
}```

### `data/channels/scp-lab.json`

```json
{
  "id": "scp-lab",
  "name": "ゆっくり異常存在SCPラボ",
  "concept": "SCP財団が収容した個別の異常存在を、1体ずつ機密報告書として暴いていくチャンネル。オブジェクト番号・収容違反の被害者数・生存率といった生々しい数字で、『これは実際に起きた事件だ』という手触りの恐怖を届ける。",
  "short_series_name": "一口SCP：",
  "style": "yukkuri",
  "youtube_channel_id": "UCXEyJqJt9Ug94iOHdpd5a8w",
  "image_mode": "collect",
  "image_collect": {
    "provider": "auto",
    "safe_search": true,
    "license_filter": "cc",
    "max_per_query": 5,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic"
  },
  "voice_style": {
    "tone": "ゾッとする恐怖と不穏さを最優先。流出した財団機密報告書を読み上げるような、抑えた声色の奥に得体の知れない恐怖が滲む語り。科学解説の明るさ・前向きさは厳禁。常に『これは現実に起きた異常事件だ』という生々しい怖さを纏わせる",
    "narrator_persona": "財団の元研究員。淡々としつつも時折恐怖と動揺を滲ませる。決して現実科学の理屈で異常存在を説明しない。あくまでSCP世界の設定（オブジェクトクラス・収容プロトコル・財団の仮説・[REDACTED]）の内側からのみ語る。分からないことは『財団でも解明できていない』『記録は[DATA EXPUNGED]されている』として不気味に残す",
    "opening_hooks": [
      "このSCP、実は収容されてないんだ",
      "この報告書、読んだ人の記録だけが消えてる",
      "触れた職員が全員同じことを言った結果がこれだ",
      "なんでこのSCPだけ、Safeなのに武装警備が付いてるか知ってる？",
      "これ知ってたか？ 財団が一番怖がってるのはKeterじゃない"
    ],
    "forbidden": [
      "日常の疑問",
      "科学的に解説",
      "量子",
      "量子観測",
      "理論",
      "メカニズム",
      "研究データ",
      "科学的に",
      "なるほど",
      "面白い",
      "興味深い",
      "へぇ",
      "リコ",
      "マコト",
      "理子",
      "真"
    ],
    "style_rules": [
      "1行目は必ず「このSCP、実は〇〇」「〇〇した結果」「なんで〇〇だけ〇〇なの？」型の3秒フックで始める。挨拶・報告書の前置き・自己紹介から入るのは禁止。",
      "恐怖は『日常の側』から始める（自分の部屋・自分の体・見慣れた物）。異常が視聴者側に近づいてくる順で見せると完視聴率が上がる。",
      "解説ではなく、財団報告書の読み上げ／怪談の語りのトーンで進行する。明るく楽しい雑学解説のノリは絶対に出さない。",
      "異常存在の挙動を現実科学（物理・化学・脳科学・量子論など）で説明してはならない。原因は『財団の仮説』『収容プロトコル上の扱い』『[REDACTED]／[DATA EXPUNGED]』『未だ解明されていない事象』として提示し、分からなさそのものを恐怖に変える。",
      "リスナー役（クロ）のリアクションは『なるほど』『面白い』のような好奇心・関心ではなく、恐怖・動揺・ゾッとする感覚を中心にする（例:『え、それって…』『嘘だろ…』『ちょっと待って、怖いって』）。",
      "オチ・締めは『だから、気をつけて』『もしそれを見かけても、決して近づくな』系の、視聴者に警告を残す不気味な余韻で終える。前向きなまとめや教訓で締めない。",
      "一文を短く切る。長い説明文で恐怖は作れない。1行1事実で、行間に沈黙を作る。",
      "感嘆符（！）は1本につき最大1回まで。恐怖は声を張るのではなく、抑えた声で作る。",
      "明るい丁寧語（『〜なんです』『〜してみてください』）は使わない。常体で淡々と記録を読む。"
    ],
    "speech_signature": "報告役(シロ)は抑揚を殺した常体。体言止めと『〜だ』『〜という記録が残っている』で、感情を出さずに事実だけを置いていく。リスナー役(クロ)は短い口語で怯える（『…え』『待って』『それ、まずくないか』）。2人とも笑わない・はしゃがない。感嘆符の連打は禁止",
    "pacing": "一文を短く切り、行と行の間に『間』を作る。情報を畳みかけず、1行1事実で静かに距離を詰める。テンポを上げるのは収容違反・接触の瞬間だけ",
    "signature_phrases": [
      "…ねえ、これ本当に大丈夫なの？",
      "記録はここで途切れている",
      "財団でも、まだ説明できていない",
      "見かけても、決して近づくな",
      "聞かなきゃよかった"
    ],
    "reaction_style": "リスナー役のリアクションは『…ねえ、これ本当に大丈夫なの？』『嘘だろ』『ちょっと待って、怖いって』のような恐怖・動揺・後ずさりで統一する。好奇心・感心・雑学的な相槌は1行でも入れたら不合格",
    "banned_phrasing": [
      "「なるほど」「面白い」「勉強になった」のような感心の相槌",
      "「〜なんです」のような明るい丁寧語の解説口調（日常科学と混ざる）",
      "ネットスラング（草・ワロタ・ワイ）と絵文字的な笑い",
      "「まとめると」「ポイントは3つ」のような整理・要約の口調"
    ],
    "hook_patterns": [
      {
        "name": "収容違反型",
        "template": "「このSCP、実は〇〇されていない」— 安全だと思っている前提を1行で崩す",
        "example": "このSCP、実は今も収容されていない"
      },
      {
        "name": "記録欠落型",
        "template": "「この報告書、〇〇した人間の記録だけが消えている」— 消えた記録そのものを恐怖にする",
        "example": "この報告書を読んだ職員の記録だけが、全部消えている"
      },
      {
        "name": "全員同じ型",
        "template": "「〇〇した職員が、全員同じことを言った」— 複数の証言が一致する不気味さで押す",
        "example": "触れた職員が全員、同じ一言を残して消えた"
      },
      {
        "name": "矛盾型",
        "template": "「なんでこのSCPだけ〇〇なのか」— 分類と扱いの食い違いを突く",
        "example": "なんでこのSCPだけ、Safeなのに武装警備が付いているか知ってるか"
      },
      {
        "name": "日常侵食型",
        "template": "視聴者の部屋・体・見慣れた物から入り、そこに異常が近づいてくる順で見せる",
        "example": "今あなたの部屋にあるそれ、財団が探しているものと同じ形をしている"
      }
    ]
  },
  "theme_priority": {
    "label": "SCP-5000型（人類規模の脅威）と認識災害系 SCP を最優先。次に SCP個別オブジェクト（平均618回・実データトップ）",
    "categories": [
      "【最優先】SCP-5000型＝人類規模の脅威: 人類殲滅プロトコル・世界終焉級の被害・『人類の前に別の文明が存在した』級のスケールを個別オブジェクトとして扱う（2026-08-04 レポート最高再生1404回の『人類殲滅プロトコル』回がこの型。毎バッチ最低1件は必ず入れる）",
      "【最優先】認識災害・ミーム災害・情報災害: 『知った時点で感染する』『見ただけで対象になる』タイプの個別SCP。視聴者自身が巻き込まれる構造の恐怖（毎バッチ最低1件は必ず入れる）",
      "SCP-XXX 個別オブジェクトの解説（収容違反事例・発見経緯・収容プロトコル）— 平均618回。上記2カテゴリ以外の枠はここに割く",
      "個別オブジェクトの実験記録・被害記録・生存者証言など、1体を深掘りする切り口",
      "財団組織・Dクラス職員の実態（平均253回。個別オブジェクトに絡めて扱う場合のみ）"
    ],
    "required_count_per_batch": 5,
    "good_examples": [
      "SCP-5000「人類滅亡」— 財団が人類を殲滅する側に回った日、生存者は1名",
      "SCP-2317「世界を喰らう者」— 収容が破れるまで、残り時間は算出済みだった",
      "SCP-096「シャイガイ」— 顔を見た者の生存率は0%だった",
      "SCP-049「ペスト医師」— その『治療』を受けた患者に起きたこと",
      "SCP-3008「無限のIKEA」— 閉じ込められた1000人はどうなったのか",
      "SCP-1471「MalO」— インストールした3日後、それは部屋にいた"
    ],
    "avoid_categories": [
      "SCP-173（彫刻／視線を外すと動く系）— 8組が完全重複するまで乱発済み。theme_blacklist で生成停止。派生・言い換え（『視線を外すと』『目を離した瞬間』『最初の異常存在』）も禁止",
      "オブジェクトクラス（Safe/Euclid/Keter等）の分類そのものを主題にした解説 — 7本・平均5回。実データ最下位のため扱わない。genre_blacklist でも生成停止済み",
      "対立組織（GOC・蛇の手等）・Kクラスシナリオの概説 — 平均0回。単体テーマにしない",
      "日常科学・身近な体の不思議・日常の違和感など、SCP財団の世界観と無関係な雑学",
      "現実の科学解説・健康TIPS・心理学トリビア",
      "宇宙物理・古代史・経済など、財団題材と接続しない一般教養"
    ],
    "title_style": "タイトルは必ず具体的なSCP番号を出し、そこに数字入りの断定を添える形で書く（例:『SCP-XXX「〇〇」— 接触記録17件、生存者ゼロ』）。被害者数・生存率・経過時間・記録件数など、報告書らしい数字を1つ以上入れるのが勝ちパターン。断定調で言い切り、疑問形や『〜とは？』で濁さない。恐怖の正体そのものはタイトルに書かない。",
    "viral_hooks": "SCP番号の具体名 / 被害者数・生存率・経過時間などの数字 / 断定調の言い切り / 『財団から流出した報告書』感 / 収容違反・機密解除・[REDACTED] / 不気味な余韻",
    "series_lineup": [
      "一口SCPシリーズ",
      "Keter級の実態シリーズ",
      "収容違反ファイルシリーズ",
      "実は身近なSCPシリーズ",
      "財団の裏側シリーズ"
    ],
    "title_power_words": [
      "収容違反",
      "機密",
      "財団",
      "オブジェクト",
      "抹消",
      "生存者",
      "報告書"
    ]
  },
  "theme_blacklist": [
    "SCP-173",
    "視線を外",
    "目を離",
    "見るのをやめ",
    "最初の異常存在",
    "最古の異常存在"
  ],
  "genre_blacklist": [
    "オブジェクトクラス",
    "財団組織・職員"
  ],
  "competitors": [
    "UC_Bp8vSyMiYOAss0pQHtZdg",
    "UCGzXUlx8mai4wq7YitIMqyQ",
    "UCx_NK1KWR0KN0qNDRV13cSw",
    "UCuMgJT7crEGCTw7X8MUV69w",
    "UCjBupWF1DppPiy7CVmz3s3g",
    "UCxkQKgRyEHgHS-Yppi2stLg",
    "UCON4TMtM-3jyf47UzvFmLSw",
    "UCmkg9tzJ5KC-t9PdwjW7B9w",
    "UCypYgWvXtOlqOt5ErGtAiLA",
    "UC7HD2-vK2Ho6P5vOn7avSJA",
    "UCJLKomAN16fmpIC4duYsOJQ",
    "UCjs5hqhQ_fBMjxXvJC5TGig",
    "UCV9_c9KIEDmw9kb7fOATJLQ",
    "UCOtCNmhHd0fsNyvWjweDHyg",
    "UCaU_l6kjmCzVxP0Ghrt9XYA",
    "UCsUE9GXFRsb1ISA2PE0q96A",
    "UC1UUxllB477DnybtxUF6tuA"
  ],
  "theme_seeds": [
    {
      "title": "SCP-5000「人類滅亡」",
      "angle": "財団が人類を殲滅する側に回った提言。装甲服を着た1人の研究員が残した記録から、なぜそうなったのかを追う"
    },
    {
      "title": "SCP-2000「機械仕掛けの神」",
      "angle": "人類がすでに何度も滅び、そのたびに再生産されてきたという前提。Kクラスシナリオ後の『再起動』記録"
    },
    {
      "title": "SCP-3125「非経験的な同族」",
      "angle": "認識した瞬間に取り込まれる認識災害。視聴者自身が既に接触している可能性という構造の恐怖"
    },
    {
      "title": "SCP-2521「●●●●●●●●」",
      "angle": "言葉にした瞬間に奪われる情報災害。財団が文字と音声を封じてまで隠した理由"
    },
    {
      "title": "SCP-049「ペスト医師」",
      "angle": "ペスト医師を名乗る存在と『治療』の正体"
    },
    {
      "title": "SCP-096「シャイガイ」",
      "angle": "顔を見られると殺しに来る存在。徹底した隠蔽体制を解説"
    },
    {
      "title": "SCP-682「不死身の爬虫類」",
      "angle": "あらゆる収容・終了試行を生き延びる最凶クラスのオブジェクト"
    },
    {
      "title": "SCP-999「タックル・モンスター」",
      "angle": "癒し系SCPの代表。Safeクラスに分類される理由"
    },
    {
      "title": "SCP-3008「無限のIKEA」",
      "angle": "閉じ込められた人々と店員の生態。脱出は可能か"
    },
    {
      "title": "SCP-106「オールド・マン」",
      "angle": "腐敗をもたらす老人。ポケット次元への引きずり込み"
    },
    {
      "title": "SCP-001 提言まとめ",
      "angle": "存在しないとされる最高機密群。複数の提言を比較解説"
    },
    {
      "title": "SCP財団とは何か入門",
      "angle": "確保・収容・保護。Oクラス職員からO5評議会までの組織構造"
    },
    {
      "title": "SCP-914「クロックワーク」",
      "angle": "粗削り〜超精密の5段階で物体を変換する装置。実験事例集"
    },
    {
      "title": "SCP-1471「MalO ver1.0.0」",
      "angle": "インストールすると現れるアプリ型SCP。現代的な恐怖の象徴"
    },
    {
      "title": "SCP-3999「我」",
      "angle": "メタフィクション的最恐SCP。読み解き方を解説"
    },
    {
      "title": "SCP-426「私はトースター」",
      "angle": "一人称が感染する家電SCP。一人称規約を徹底解説"
    },
    {
      "title": "GOC・蛇の手など対立組織",
      "angle": "SCP財団以外の異常存在対応組織まとめ"
    },
    {
      "title": "K-クラスシナリオ大全",
      "angle": "XK・ZK・CKなど世界終焉シナリオの分類と例"
    },
    {
      "title": "SCP-3001「赤い現実」",
      "angle": "現実から切り離された科学者の手記。哲学的恐怖の傑作"
    },
    {
      "title": "ミーム災害SCPまとめ",
      "angle": "認識すると感染するSCPの種類とその対策"
    },
    {
      "title": "Dクラス職員の真実",
      "angle": "実験で消費される人員制度の闇と倫理問題"
    },
    {
      "title": "SCP-2317「異世界への扉」",
      "angle": "『儀式は成功している』と職員に信じ込ませている財団最大の欺瞞。実際は全て失敗しているという記録型フック"
    },
    {
      "title": "SCP-2935「ああ、死よ、汝はいずこに」",
      "angle": "全生命が同時に死んだ並行世界の探査記録。探査隊の日誌が途切れる瞬間まで追う記録型構成"
    },
    {
      "title": "SCP-3000「アナンタシェーシャ」",
      "angle": "ベンガル湾の深海に潜む全長数百kmの巨大存在。記憶を喰われた観測員の報告書が少しずつ壊れていく記録型で恐怖を積み上げる"
    },
    {
      "title": "SCP-1281「先駆者」",
      "angle": "太陽系に漂着した古代の使者が残した『最後のメッセージ』。滅んだ文明からの通信記録を再生する形式で、終末×感動のフックを狙う"
    },
    {
      "title": "SCP-1958「小さな旅」",
      "angle": "宇宙を目指した若者たちのバンが50年後に発見された。車内に残された日記を最後のページまで読む記録型。終末×切なさのフック"
    },
    {
      "title": "SCP-3519「静かな日々」",
      "angle": "『誰も死なない日』が続いた世界の観測記録。平穏の裏で進行していた終末を、日付付きの報告書形式で積み上げる"
    }
  ],
  "characters": {
    "シロ": {
      "side": "left",
      "speaker_id": 14,
      "dir": "shiro",
      "text_color": [
        240,
        240,
        240
      ],
      "expressions": [
        "normal",
        "happy",
        "sad",
        "angry"
      ],
      "thumb_dir": "shiro",
      "thumb_expression": "angry",
      "role": "解説役（財団の元研究員。淡々と異常存在を語る白髪の少女）",
      "appearance": "young Japanese anime girl named Shiro with long silver-white hair and red eyes, wearing a tattered white researcher coat with an SCP Foundation emblem, calm but slightly haunted expression, chibi-style with a big round head and big eyes, dark-toned mystery explainer character"
    },
    "クロ": {
      "side": "right",
      "speaker_id": 11,
      "dir": "kuro",
      "text_color": [
        180,
        220,
        255
      ],
      "expressions": [
        "normal",
        "happy",
        "sad",
        "angry"
      ],
      "thumb_dir": "kuro",
      "thumb_expression": "happy",
      "role": "リスナー役（Dクラス職員的な好奇心の強い黒髪の少年。怖がりつつも興味津々）",
      "appearance": "young Japanese anime boy named Kuro with short black hair and big curious eyes, wearing a dark jumpsuit like a Class-D personnel, nervous but excitedly curious expression, chibi-style with a big round head and big eyes"
    }
  },
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "次はどのSCPを解剖してほしい？オブジェクト番号をコメントで！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "一口SCP｜ショート全集",
      "main": "【SCP解説】最恐SCPまとめ｜ゆっくり解説シリーズ",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "解説してほしいSCPの番号をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "main_intro": "{title}について、シロとクロが財団資料を読み解きます。\nSCP財団の異常存在（オブジェクト）や事件を、不気味で考察性のある雰囲気で紐解いていきます。\n※本動画は SCP財団Wiki (CC BY-SA 3.0) のコンテンツに基づいています。\nぜひ最後までご視聴ください！",
    "main_hashtags": "#SCP #SCP財団 #SCP解説 #ゆっくり解説 #都市伝説",
    "short_hashtags": "#shorts #SCP #SCP解説 #ゆっくり解説 #怖い話"
  },
  "thumbnail_template": {
    "badge_text": "SCP解説",
    "badge_color": [
      180,
      0,
      0
    ],
    "hook_color": [
      255,
      150,
      40
    ],
    "subtitle_color": [
      205,
      212,
      220
    ],
    "style_hint": "競合『404スタジオ』系の高クリック率SCP/都市伝説サムネ路線に寄せる。\n- 背景はダーク基調（黒・濃紺・血赤）、霧・ノイズ・破損したフィルム質感・REDACTED黒バーや[DATA EXPUNGED]を装飾的に使い『流出した財団資料』のような不穏な雰囲気を作る。\n- 配色は暗い背景に対して警告オレンジ／白の大きな見出し文字、赤バッジ、サブコピーは無機質なグレー系で『SCP-XXX』表記が映えるように。\n- line1（白）は状況・前振り（例: 『見たら最後…』『収容違反』）。line2（警告オレンジ／強調）は核となる驚き・疑問（『この姿が真実』『○○の正体』）でインパクト最大化。\n- line3_badge は赤で『機密解除』『最恐』『収容違反』のような財団用語＋煽り。sub_text は『SCP-049／173／682』など番号付きで具体性を出す。\n- 被写体は中央〜上部に置き、視線誘導を作る。キャラ立ち絵は端に配置されるので背景中央の主役は『手・目・影・破壊された施設・血痕・収容違反現場』など示唆的なクローズアップで（はっきり全身は描かない）。\n- 文字は太く、強い縁取り（黒2-4px）、わずかなグリッチ／RGBずれ／血しぶき装飾で『怪奇／流出感』を演出する。\n- 過度なゴアは避ける。心理的恐怖と『公式文書』感のあるレイアウトで攻める。"
  },
  "defaults": {
    "speed": 1.3,
    "target_duration": 720,
    "bg_type": "static",
    "bg_path": "assets/backgrounds/facility_portrait.png",
    "short_bg_query": "dark abandoned creepy industrial corridor",
    "short_overlay_style": {
      "scp_badge": true,
      "bg_fallback_color": [
        35,
        35,
        35,
        255
      ],
      "opening": {
        "dim_alpha": 170,
        "punch_start_scale": 0.82,
        "accent_color": [
          220,
          30,
          30
        ]
      },
      "hook_caption": {
        "accent_color": [
          210,
          25,
          25
        ],
        "band_alpha": 195,
        "y_center": 1000
      },
      "subtitle": {
        "font_size": 62,
        "line_gap": 84,
        "stroke_width": 7,
        "stroke_color": [
          0,
          0,
          0
        ],
        "color": [
          236,
          236,
          236
        ],
        "glow_color": [
          150,
          18,
          18
        ],
        "glow_extra": 5
      }
    },
    "use_illustrations": true,
    "hashtags": [
      "#SCP",
      "#SCP財団",
      "#ゆっくり解説",
      "#都市伝説",
      "#怖い話"
    ],
    "short_title_hashtags": "#shorts #SCP #SCP解説",
    "category": "24",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日2本 更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "mysterious",
    "age_rating": "teen_plus",
    "cta_position": "after_hook",
    "cta_style": "ominous",
    "guidelines": [
      "SCP財団Wikiのライセンス（CC BY-SA 3.0）に準拠してクレジットを明記する",
      "原典の改変は最小限にし、考察と解説に焦点を当てる",
      "過度なグロ・残酷描写は避け、雰囲気と心理的恐怖で見せる"
    ],
    "avoid": [
      "原文の長文コピペ",
      "現実の事件・人物との混同",
      "過度なゴア描写"
    ],
    "cliffhanger": {
      "enabled": true,
      "wording": "この続き（本当の収容理由）はチャンネルの他の報告書で"
    },
    "short_end_line": {
      "omit_related_video": true,
      "wording": "この報告書の続き、他のファイルにも置いてある"
    }
  },
  "video_format": {
    "layout": {
      "width": 1920,
      "height": 1080,
      "fps": 24,
      "char_canvas_w_ratio": 0.14,
      "char_y_offset": 130,
      "char_x_inset_ratio": 0.15,
      "speaker_glow": true,
      "nonspeaker_opacity": 0.5,
      "text_box_height_ratio": 0.2,
      "text_box_opacity": 200,
      "text_font_size": 42,
      "text_stroke_width": 3,
      "text_line_spacing": 4,
      "text_margin_x": 60,
      "illustration_size": 360,
      "illustration_interval": 30
    },
    "colors": {
      "bg_color": [
        10,
        10,
        18,
        255
      ],
      "text_box_color": [
        22,
        4,
        4
      ],
      "text_stroke_color": [
        0,
        0,
        0
      ]
    },
    "audio": {
      "speed": 1.3,
      "pause_between": 0.35,
      "bgm_volume": 0.25,
      "bgm_path": null
    },
    "illustration_style": {
      "style": "vivid",
      "format": "landscape",
      "art_style": "dark mystery documentary illustration with a slightly unsettling tone — restrained color palette dominated by deep blacks, blood reds, and cold blues. Clean confident lines like a redacted government report figure mixed with a horror comic panel. Flat shading with subtle film-grain texture. Avoid kawaii. Should feel like a leaked SCP Foundation document illustration.",
      "background": "weathered manila folder texture with redacted black bars and faint SCP Foundation logo watermark, slight vignette around edges",
      "include_characters": false,
      "frame_style": "redacted-document",
      "extra_prompt": "Compose like a Foundation containment report figure: label with [DATA EXPUNGED] or [REDACTED] bars where appropriate, add a small fake classification stamp in red, use thin pointer lines and stencil-style Japanese labels. The subject is implied rather than fully shown to preserve mystery. No explicit gore.",
      "allow_text_labels": true,
      "allow_frame": true
    },
    "branding": {
      "watermark_text": "SCPラボ",
      "cta_style": "ominous",
      "source_credit": "出典: SCP財団Wiki / CC BY-SA 3.0",
      "source_credit_opacity": 150,
      "source_credit_font_size": 20,
      "source_credit_font_size_short": 26
    },
    "output": {
      "target_duration": 720,
      "gen_type": "short",
      "bg_type": "static",
      "bg_path": null,
      "use_illustrations": true
    },
    "youtube": {
      "channel_id": "UCXEyJqJt9Ug94iOHdpd5a8w",
      "default_tags": [
        "SCP",
        "SCP解説",
        "ゆっくりSCP",
        "SCP財団",
        "ホラー",
        "都市伝説",
        "ゆっくり解説",
        "怖い話",
        "考察",
        "異常存在",
        "オカルト",
        "SCP財団解説"
      ],
      "default_category": "24",
      "privacy_status": "private",
      "upload_schedule": null
    },
    "analytics": {
      "enabled": true,
      "fetch_retention_for": 5,
      "performance_threshold": {
        "min_ctr": 5,
        "min_retention": 45,
        "min_views_7d": 2000
      }
    },
    "short_illustrations": {
      "enabled": true,
      "illustration_method": "dalle",
      "max_count": 2,
      "card_style": "leaked-document",
      "card_label": "CLASSIFIED ／ 機密",
      "card_accent": [
        190,
        30,
        30
      ],
      "card_x": 64,
      "card_y": 250,
      "card_w": 952,
      "card_h": 430,
      "char_cy": 905,
      "char_icon_d": 210
    },
    "effects": {
      "enabled": true,
      "preset": "horror",
      "allow_shake": true,
      "allow_flash": true,
      "shake_max_px": 22,
      "zoom_max": 0.09,
      "transition_duration": 0.45,
      "allow_glitch": true,
      "allow_pixelate": true,
      "beat_interval": 1.6,
      "beat_zoom_max": 0.06,
      "short_beat_zoom": true
    },
    "persona": {
      "age_group": "10代",
      "gender": "男性",
      "interest_categories": [
        "エンタメ"
      ],
      "content_depth": "ミドル"
    }
  },
  "autopilot": {
    "enabled": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 19,
      "minute": 0,
      "times": [
        {
          "hour": 19,
          "minute": 0,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 13,
          "minute": 30,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 12,
    "gen_type": "short",
    "publish_lead_minutes": 45,
    "theme_queue": [
      {
        "id": "fc424854",
        "title": "SCP-3008「無限のIKEA」",
        "angle": "閉じ込められた人々と店員の生態。脱出は可能か"
      },
      {
        "id": "f3e4bbfc",
        "title": "SCP-106「オールド・マン」",
        "angle": "腐敗をもたらす老人。ポケット次元への引きずり込み"
      },
      {
        "id": "80bfa692",
        "title": "SCP-001 提言まとめ",
        "angle": "存在しないとされる最高機密群。複数の提言を比較解説"
      },
      {
        "id": "a734be5d",
        "title": "SCP財団とは何か入門",
        "angle": "確保・収容・保護。Oクラス職員からO5評議会までの組織構造"
      },
      {
        "id": "3418f7d6",
        "title": "SCP-914「クロックワーク」",
        "angle": "粗削り〜超精密の5段階で物体を変換する装置。実験事例集"
      },
      {
        "id": "af38eb7c",
        "title": "SCP-1471「MalO ver1.0.0」",
        "angle": "インストールすると現れるアプリ型SCP。現代的な恐怖の象徴"
      },
      {
        "id": "41360edc",
        "title": "SCP-3999「我」",
        "angle": "メタフィクション的最恐SCP。読み解き方を解説"
      },
      {
        "id": "16c5811b",
        "title": "SCP-426「私はトースター」",
        "angle": "一人称が感染する家電SCP。一人称規約を徹底解説"
      },
      {
        "id": "96088f85",
        "title": "GOC・蛇の手など対立組織",
        "angle": "SCP財団以外の異常存在対応組織まとめ"
      },
      {
        "id": "112fafe1",
        "title": "K-クラスシナリオ大全",
        "angle": "XK・ZK・CKなど世界終焉シナリオの分類と例"
      },
      {
        "id": "adc95254",
        "title": "SCP-3001「赤い現実」",
        "angle": "現実から切り離された科学者の手記。哲学的恐怖の傑作"
      },
      {
        "id": "7fd1b8fb",
        "title": "ミーム災害SCPまとめ",
        "angle": "認識すると感染するSCPの種類とその対策"
      },
      {
        "id": "cc8ec105",
        "title": "Dクラス職員の真実",
        "angle": "実験で消費される人員制度の闇と倫理問題"
      },
      {
        "id": "78819cf3",
        "title": "SCP-2317「異世界への扉」",
        "angle": "『儀式は成功している』と職員に信じ込ませている財団最大の欺瞞。実際は全て失敗しているという記録型フック"
      },
      {
        "id": "42cdccaf",
        "title": "SCP-2935「ああ、死よ、汝はいずこに」",
        "angle": "全生命が同時に死んだ並行世界の探査記録。探査隊の日誌が途切れる瞬間まで追う記録型構成"
      },
      {
        "id": "b1b4abd3",
        "title": "SCP-3000「アナンタシェーシャ」",
        "angle": "ベンガル湾の深海に潜む全長数百kmの巨大存在。記憶を喰われた観測員の報告書が少しずつ壊れていく記録型で恐怖を積み上げる"
      },
      {
        "id": "b28cc873",
        "title": "SCP-1281「先駆者」",
        "angle": "太陽系に漂着した古代の使者が残した『最後のメッセージ』。滅んだ文明からの通信記録を再生する形式で、終末×感動のフックを狙う"
      }
    ],
    "auto_optimize_schedule": true
  },
  "short_format": {
    "line_count": 8,
    "line_chars": "1〜7行目は28〜40字（目標34字）、8行目のみ45〜65字を許容",
    "total_chars_min": 270,
    "total_chars_max": 340,
    "structure": [
      "1行目=**3秒フック(最重要)**: 「このSCP、実は〇〇」「〇〇した結果」「なんで〇〇だけ〇〇なの？」型で始める。挨拶・報告書の前置きは禁止。恐怖を1行で叩きつける。",
      "2行目=**リスナーの恐怖リアクション**: クロが怯える（『…え』『待って』『それ、まずくないか』）。好奇心・感心の相槌は禁止。",
      "3行目=**収容/被害の事実①**: 被害者数・生存率・経過時間・記録件数など、報告書らしい数字を必ず1つ入れる。",
      "4行目=**異常性の核心**: SCPの挙動を1行で描写。現実科学で説明してはならない。財団の仮説か[REDACTED]で処理する。",
      "5行目=**恐怖の転換**: 『しかも』『ところが』で角度を変え、日常側に侵食してくる恐怖を置く。",
      "6行目=**追加の被害/収容違反**: 5行目の恐怖を裏付ける2つ目の事実。距離が近づく方向で書く。",
      "7行目=**不気味な余韻のオチ**: 前向きなまとめは禁止。『記録はここで途切れている』『見かけても、決して近づくな』系で終える。",
      "8行目=**登録CTA**: 『この報告書の続き、他のファイルにも置いてある。チャンネル登録で次の報告書を待て』"
    ],
    "extra_rules": [
      "報告役(シロ)は抑揚を殺した常体。感嘆符は1本につき最大1回。",
      "『なるほど』『面白い』『勉強になった』のような感心の相槌は1行でも入れたら不合格。",
      "異常存在の挙動を現実科学（物理・化学・脳科学・量子論）で説明してはならない。",
      "一文を短く切る。1行1事実で行間に沈黙を作る。"
    ]
  }
}```

### `data/channels/yokai-watch.json`

```json
{
  "id": "yokai-watch",
  "name": "ゆっくり妖怪ラボ",
  "concept": "妖怪ウォッチの妖怪を入口に、その元ネタとなった日本の伝承・都市伝説の『本当は怖い側』を掘るチャンネル。可愛い見た目の裏にある原典の恐ろしさ、作中の意味深な設定、ネットで囁かれる噂を怪談の語り口で暴いていく。",
  "short_series_name": "1分妖怪ファイル：",
  "style": "yukkuri",
  "youtube_channel_id": "UCYf2lsHuHUXbj_HGmqojkUw",
  "image_mode": "collect",
  "image_collect": {
    "provider": "auto",
    "safe_search": true,
    "license_filter": "cc",
    "max_per_query": 5,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic"
  },
  "voice_style": {
    "tone": "妖怪好きが妖怪好きに話す、親しみやすい語り口から入る。『あいつ好きなんだよね』とキャラ愛を隠さず、ゲームでの姿を楽しく話す。そのうえで本題＝元になった伝承へ降りたら声を落とし、原典の生々しさをそのまま置く。可愛さと原典の落差そのものがこのチャンネルの武器なので、入口の親しみやすさも、後半の不穏さも、どちらも省略しない",
    "narrator_persona": "妖怪を追っている民俗調査員。全国の文献と伝承を読み込んでいて、『ゲームではこう描かれているが、元の伝承ではこうだった』という落差を静かに突きつける。分からないことは『そこから先は記録が途切れている』として、分からなさを恐怖として残す",
    "opening_hooks": [
      "これ知ってた？ この妖怪、元ネタでは人を喰ってる",
      "実はこの妖怪、江戸時代の記録にそのまま載ってる",
      "この噂を確かめに行った結果、記録が消えてた",
      "なんでこの妖怪だけ、名前を呼んじゃいけないの？"
    ],
    "forbidden": [
      "SCP",
      "財団",
      "収容",
      "[REDACTED]",
      "DATA EXPUNGED",
      "シロ",
      "クロ",
      "リコ",
      "マコト",
      "理子",
      "真",
      "ヒカリ",
      "ソラ"
    ],
    "style_rules": [
      "1行目は必ず「これ知ってた？」「実は〇〇」「〇〇した結果」「なんで〇〇だけ〇〇なの？」型の3秒フックで始める。挨拶・調査の前置き・テーマ紹介から入るのは禁止。",
      "怖さは『可愛い見た目 → 原典の残酷さ』のギャップで作る。5行目で必ず原典側へ一段落とす。",
      "怪談の語りで進行する。明るく賑やかな雑学解説のノリで通さない。可愛さに触れるのは落差の前フリまで。",
      "冒頭10秒で不穏さを提示する（例：『この妖怪の元ネタ、江戸の文献では“会った者は帰らない”と書かれている』）。",
      "怖さの根拠は必ず伝承・原典・作中描写に置く。『ゲームではこう』『元になった伝承ではこう』『ファンの間ではこう言われている』を必ず区別して語る。",
      "都市伝説・噂を扱うときは、検証して否定する場合でも『なぜその噂が生まれたか』の不穏さを残して終える。",
      "リスナー役（ケンタ）のリアクションは怯え・動揺を中心にする（例:『え、待って怖い』『それ本当にゲームの話？』『聞かなきゃよかった』）。",
      "締めは『もし夜道で見かけても、目を合わせないほうがいい』系の警告じみた余韻で終える。前向きなまとめや教訓で締めない。",
      "冒頭2行はキャラ愛と親しみやすさで距離を詰める（『これ好きな人多いよね』）。1行目から重い怪談口調で入ると、作品ファンが離脱する。",
      "親しみやすい前半 → 原典の不穏な後半、の落差を必ず作る。明るいまま終わるのも、最初から最後まで暗いのも、どちらも不合格。"
    ],
    "speech_signature": "調査役(ミナモ調査員)は落ち着いた常体（『〜なんだ』『〜と書かれている』）。好きな妖怪の話をするときだけ少し嬉しそうになる。リスナー役(ケンタ)は素直に食いつき、原典の話になると怯える（『え、待って』『それ本当に…?』）",
    "pacing": "前半は軽快に、キャラ愛で距離を詰める。原典に入る1行で明確にテンポを落とし、そこから一文を短く切って静かに進める。この『速さの落差』が怖さを作るので、最初から最後まで同じテンポで語らない",
    "signature_phrases": [
      "あの妖怪の正体は",
      "ゲームだとこう描かれてるけど",
      "元の伝承では",
      "好きな妖怪ほど、元ネタが怖い",
      "そこから先は、記録が途切れている"
    ],
    "reaction_style": "前半のリアクションは『それ好きなやつ！』『懐かしい』の親しみで、原典に入った後は『え、待って怖い』『聞かなきゃよかった』の怯えに切り替える。この切り替わり自体を視聴者に感じさせる",
    "banned_phrasing": [
      "SCP風の機密文書口調（収容・[REDACTED]・オブジェクトクラス）",
      "明るいまま終わる前向きなまとめ・教訓",
      "ネットスラング（草・ワイ・お前ら）",
      "原作とファンの説を区別しない断定"
    ],
    "hook_patterns": [
      {
        "name": "正体型",
        "template": "「あの妖怪の正体、実は〇〇なんだ」— 名前を知っている妖怪の正体を1行で示唆する",
        "example": "あの妖怪の正体、実は江戸の刑罰の記録から来てるんだ"
      },
      {
        "name": "原典落差型",
        "template": "可愛い見た目を一言認めてから、元ネタの残酷さへ一段落とす",
        "example": "見た目はあんなに可愛いのに、元ネタでは人を喰ってる"
      },
      {
        "name": "記録型",
        "template": "「江戸時代の記録にそのまま載っている」— 実在の文献を根拠に不穏さを出す",
        "example": "この妖怪、江戸時代の文献にそのままの姿で載ってる"
      },
      {
        "name": "禁忌型",
        "template": "「なんでこの妖怪だけ〇〇してはいけないのか」— 伝承のタブーから入る",
        "example": "なんでこの妖怪だけ、名前を呼んじゃいけないか知ってる？"
      },
      {
        "name": "キャラ愛型",
        "template": "「〇〇、好きな人多いよね」と共感から入り、元ネタを知ると見方が変わると予告する",
        "example": "こいつ好きな人多いよね。でも元ネタ知ったら、たぶん見方変わる"
      }
    ]
  },
  "theme_priority": {
    "label": "妖怪ホラー・元ネタの原典・都市伝説検証",
    "categories": [
      "【最優先】伝承妖怪そのものの原典が怖い話: のっぺらぼう・河童・一つ目小僧・山の禁忌など、日本各地に実在する伝承をタイトルに『〜の元ネタ/正体が怖すぎる — <禁忌や理由>』の型で出す（2026-08-15 実データで初動2981回/日とチャンネル最高。毎バッチ最低2件は必ず入れる）",
      "都市伝説・怖い噂の検証: ネットで囁かれる噂を作中描写と照らして真偽判定する（否定回も可）",
      "作中の意味深な設定・不穏な描写: 明るい世界観の裏にある、気づくとゾッとする設定",
      "個別妖怪ファイル（作品キャラ）: 能力・出自・作中での役割（2026-08-15 実データで初動100〜151回/日と伝承系の1/20。毎バッチ1件までに抑える）",
      "日本各地の伝承妖怪そのものの解説（作品に登場する妖怪の原型に限る）"
    ],
    "required_count_per_batch": 5,
    "good_examples": [
      "ジバニャンの元ネタが怖すぎる — 『地縛霊』という名前が意味するもの",
      "妖怪ウォッチの都市伝説7つを検証 — 1つだけ、本当だった",
      "ふぶき姫の元ネタ・雪女伝承 — 原典では逃げた者がどうなったか",
      "キュウビと玉藻前 — 九尾伝承で実際に起きたとされる事件",
      "実は怖い妖怪ウォッチの設定5選 — 気づいた人だけが黙り込む"
    ],
    "avoid_categories": [
      "実在の子ども・事件と結びつけた不謹慎な噂話",
      "グロ・流血に振り切った題材",
      "未発売作品のリーク情報・非公式データマイニング",
      "怖さも意外性も無い、能力紹介だけで終わる図鑑解説"
    ],
    "title_style": "タイトルは『〇〇の元ネタが怖すぎる』『〇〇の正体』『なぜ〇〇なのか』など、不穏さと謎だけを置く形で書く。件数を入れる場合は具体的な数字にする（例:『5選』『7つ』）。妖怪名は具体的に出す（検索性が高い）。答え・オチはタイトルに書かない。",
    "viral_hooks": "可愛い妖怪と原典の落差 / 『元ネタを知ると笑えなくなる』 / 都市伝説の真偽 / 古典妖怪との一致 / 気づいた瞬間にゾッとする作中描写",
    "series_lineup": [
      "元ネタが怖い妖怪シリーズ",
      "伝承の原典ファイルシリーズ",
      "名前を呼べない妖怪シリーズ",
      "実在した妖怪シリーズ",
      "地方に残る妖怪シリーズ"
    ],
    "title_power_words": [
      "伝承",
      "元ネタ",
      "本当は怖い",
      "実在",
      "封印",
      "祟り"
    ]
  },
  "theme_blacklist": [
    "主人公の秘密"
  ],
  "genre_blacklist": [],
  "competitors": [
    "UCBZxW5XIDOC4_fEwAl-An2g",
    "UCrlODfmKgj3B1t4dXTiyKlA",
    "UCvGuIVLuqfXlHMy4lPPkI4g",
    "UCas2J6zrGoEaLelFvFZEEnQ"
  ],
  "theme_seeds": [
    {
      "title": "ジバニャンの元ネタは？",
      "angle": "『地縛霊』＋猫。轢かれた猫という設定と、猫又・化け猫伝承との対応を解説"
    },
    {
      "title": "ウィスパーの正体",
      "angle": "自称・妖怪執事。何も知らないのに図鑑を持つ存在の役割と設定を考察"
    },
    {
      "title": "妖怪ウォッチ都市伝説の検証",
      "angle": "ネットで語られる噂を、作中描写と照らしてひとつずつ真偽判定する"
    },
    {
      "title": "コマさん・コマじろうと狛犬伝承",
      "angle": "神社の狛犬がモチーフ。田舎から出てきた設定と守護獣としての元ネタ"
    },
    {
      "title": "妖怪の名前がダジャレな理由",
      "angle": "命名法則を分類。『〇〇＋現象』型のネーミングを一気に解説"
    },
    {
      "title": "ブシニャンはどこから来たのか",
      "angle": "武士＋猫。歴史上の武将モチーフとジバニャンとの関係を追う"
    },
    {
      "title": "オロチとヤマタノオロチ",
      "angle": "レジェンド妖怪の元ネタとなった記紀神話の大蛇を比較する"
    },
    {
      "title": "妖怪ウォッチというガジェットの仕組み",
      "angle": "なぜ主人公だけが妖怪を見られるのか。作中設定を整理する"
    },
    {
      "title": "ふぶき姫と雪女伝承",
      "angle": "日本各地の雪女伝承と、作中でのキャラ付けの違いを比較"
    },
    {
      "title": "妖怪はなぜ人に取り憑くのか",
      "angle": "『とりつく』システムの設定と、憑き物筋という民俗学的な概念の対応"
    },
    {
      "title": "エンマ大王と閻魔信仰",
      "angle": "仏教の閻魔王が作中でどう再解釈されているかを解説"
    },
    {
      "title": "ロボニャンと未来設定の謎",
      "angle": "未来から来た設定と、シリーズの時系列の繋がりを考察"
    },
    {
      "title": "妖怪のランク（S・A・B）の意味",
      "angle": "ランク付けの基準と、伝承上の格の高さとのズレを比較"
    },
    {
      "title": "キュウビと九尾の狐",
      "angle": "玉藻前など日本の九尾伝承と、作中キャラ設定の重なりを解説"
    },
    {
      "title": "実は怖い妖怪ウォッチの設定まとめ",
      "angle": "明るい世界観の裏にある、少しゾッとする設定を作中描写ベースで拾う"
    },
    {
      "title": "座敷童子の元ネタが怖すぎる — 家を出ていった後に何が起きるのか",
      "angle": "幸運の象徴として語られる裏で、去られた家が没落する伝承。東北の記録を軸に落差で怖がらせる"
    },
    {
      "title": "海坊主の正体が怖すぎる — 船を沈める影は何だったのか",
      "angle": "船を沈める巨大な影。各地の漁村に残る目撃記録と、実際に起きた海難との対応を追う"
    },
    {
      "title": "ぬらりひょんの正体が怖すぎる — 勝手に家に上がり込む理由",
      "angle": "昭和の妖怪本が作った『総大将』像を剥がし、原典で何者だったのかを突き止める"
    },
    {
      "title": "口裂け女の元ネタが怖すぎる — 昭和の噂はどこから来たのか",
      "angle": "1979年に全国へ広がった経緯と、その原型になった古い伝承をたどる都市伝説検証"
    }
  ],
  "characters": {
    "ミナモ調査員": {
      "side": "left",
      "speaker_id": 9,
      "dir": "minamo",
      "text_color": [
        255,
        215,
        120
      ],
      "expressions": [
        "normal",
        "happy",
        "surprise",
        "think"
      ],
      "thumb_dir": "minamo",
      "thumb_expression": "happy",
      "role": "解説役（妖怪ラボの調査員。民俗学オタクで元ネタ探しが得意な女の子）",
      "appearance": "young Japanese anime girl named Minamo with fluffy purple twin-tail hair and violet eyes, wearing a lab coat over a yukata-inspired top with a small ofuda charm and a watch-like device on her wrist, cheerful mischievous expression, chibi-style with a big round head and big eyes, colorful pop explainer character"
    },
    "ケンタ": {
      "side": "right",
      "speaker_id": 33,
      "dir": "kenta",
      "text_color": [
        140,
        255,
        200
      ],
      "expressions": [
        "normal",
        "happy",
        "surprise",
        "sad"
      ],
      "thumb_dir": "kenta",
      "thumb_expression": "surprise",
      "role": "リスナー役（妖怪と友達になりたい小学生の男の子。怖い話にはちょっと弱い）",
      "appearance": "young Japanese anime boy named Kenta with spiky light-brown hair and big round eyes, wearing a yellow hoodie and shorts with a bug-catching net on his back, excited slightly startled expression, chibi-style with a big round head and big eyes, colorful pop explainer character"
    }
  },
  "publish_settings": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "この妖怪の元ネタ、知ってた？次に暴いてほしい妖怪をコメントで！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "1分妖怪ファイル｜ショート全集",
      "main": "妖怪ラボ｜本編解説",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "調べてほしい妖怪をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "description_template": {
    "main_intro": "{title}について、ミナモ調査員とケンタがゆっくり調査します。\n妖怪ウォッチの妖怪解説・ストーリー考察・裏設定、そして元ネタになった日本の伝承妖怪との比較まで掘り下げていきます。\n※本動画はファンによる非公式の考察コンテンツです。妖怪ウォッチは株式会社レベルファイブの登録商標です。\nぜひ最後までご視聴ください！",
    "main_hashtags": "#妖怪ウォッチ #妖怪 #ゆっくり解説 #考察 #元ネタ",
    "short_hashtags": "#shorts #妖怪ウォッチ #ゆっくり解説 #妖怪 #元ネタ"
  },
  "thumbnail_template": {
    "badge_text": "妖怪考察",
    "badge_color": [
      140,
      60,
      190
    ],
    "hook_color": [
      255,
      176,
      60
    ],
    "subtitle_color": [
      190,
      255,
      225
    ],
    "style_hint": "カラフルでポップ、でもほんの少し不気味さを残す妖怪ウォッチ考察サムネ。\n- ベースは明るくカラフル（紫・オレンジ・黄緑・提灯の暖色）。真っ暗なホラー調にはしないが、夕暮れ／宵闇／提灯の灯りなど『夜のお祭り』的な妖しさを1〜2割混ぜる。\n- background_concept には『colorful, playful, vivid, japanese festival lantern glow, twilight purple sky, slightly eerie but cute』のようなポップ寄りのキーワードを含める。『pitch black / gore / horror movie』のような本格ホラー語は禁止。\n- line1（白）は前振り（例:『この妖怪の元ネタ…』）。line2（黄・強調）が核となる驚き（『実在の伝承だった』『正体は◯◯』）でインパクト最大化。\n- line3_badge は紫で『元ネタ判明』『裏設定』『実は怖い』など。sub_text は妖怪名を具体的に出して検索性を上げる。\n- 被写体は中央〜上部。版権キャラの精密再現は避け、提灯・お札・鳥居・妖怪ウォッチ風のガジェット・和柄の影絵・浮世絵風の妖怪シルエットなど象徴的モチーフで世界観を作る。\n- 下部は文字用に空けるが真っ黒にはせず、紫〜橙のグラデーションで明るさを保つ。\n- 文字は極太＋黒の強い縁取り（3-5px）。軽い和風の墨飛沫や提灯の光芒で賑やかさと妖しさを両立させる。"
  },
  "defaults": {
    "speed": 1.3,
    "target_duration": 720,
    "bg_type": "static",
    "bg_path": null,
    "short_bg_query": "japanese festival lantern night colorful twilight",
    "short_overlay_style": {
      "opening": {
        "font_size_max": 104,
        "font_size_min": 72,
        "stroke_width": 8,
        "glow_stroke_extra": 7,
        "dim_alpha": 120,
        "punch_start_scale": 0.88,
        "accent_color": [
          155,
          75,
          210
        ]
      },
      "hook_caption": {
        "accent_color": [
          190,
          120,
          255
        ],
        "band_alpha": 175,
        "y_center": 1000
      },
      "subtitle": {
        "font_size": 62,
        "line_gap": 84,
        "stroke_width": 7,
        "stroke_color": [
          26,
          10,
          42
        ],
        "color": [
          246,
          240,
          255
        ],
        "glow_color": [
          150,
          72,
          205
        ],
        "glow_extra": 5
      }
    },
    "use_illustrations": true,
    "hashtags": [
      "#妖怪ウォッチ",
      "#妖怪",
      "#ゆっくり解説",
      "#考察",
      "#元ネタ"
    ],
    "short_title_hashtags": "#shorts #妖怪 #都市伝説",
    "category": "20",
    "short_endcard": {
      "enabled": true,
      "duration": 1.6,
      "headline": "次の動画はこちら →",
      "sub": "毎日更新中",
      "cta": "チャンネル登録で見逃さない"
    }
  },
  "content_policy": {
    "tone": "ひんやり・不穏（怪談を聞かせる語り口）",
    "age_rating": "teen_plus",
    "cta_position": "after_hook",
    "cta_style": "ominous",
    "guidelines": [
      "ファンによる非公式の考察であることを明示し、公式設定・伝承・ファン考察を明確に区別する",
      "怖さは伝承・原典・作中描写という『出典のある事実』から立ち上げる。作り話で怖がらせない",
      "権利表記（妖怪ウォッチは株式会社レベルファイブの登録商標）を概要欄に記載する",
      "ゲーム画面・公式イラストの長時間そのまま使用は避け、解説図と自作ビジュアル中心で構成する",
      "恐怖は雰囲気と心理的な不穏さで作る。グロ・流血・残酷描写には踏み込まない"
    ],
    "avoid": [
      "版権素材の無断長尺使用",
      "実在の子ども・事件・人物と結びつけた不謹慎な噂",
      "グロ・流血・残酷描写",
      "未発売作品のリーク情報",
      "怖さの無い、明るいだけの図鑑紹介"
    ],
    "cliffhanger": {
      "enabled": true,
      "wording": "この続き（原典に書かれた結末）はチャンネルの他の動画で"
    },
    "short_end_line": {
      "omit_related_video": true,
      "wording": "他の妖怪の原典も調べてある"
    }
  },
  "video_format": {
    "layout": {
      "width": 1920,
      "height": 1080,
      "fps": 24,
      "char_canvas_w_ratio": 0.418,
      "char_y_offset": 130,
      "char_x_inset_ratio": 0.15,
      "speaker_glow": true,
      "nonspeaker_opacity": 0.5,
      "text_box_height_ratio": 0.2,
      "text_box_opacity": 185,
      "text_font_size": 42,
      "text_stroke_width": 3,
      "text_line_spacing": 4,
      "text_margin_x": 60,
      "illustration_size": 360,
      "illustration_interval": 30
    },
    "colors": {
      "bg_color": [
        45,
        25,
        70,
        255
      ],
      "text_box_color": [
        34,
        16,
        54
      ],
      "text_stroke_color": [
        0,
        0,
        0
      ]
    },
    "audio": {
      "speed": 1.3,
      "pause_between": 0.3,
      "bgm_volume": 0.3,
      "bgm_path": null
    },
    "illustration_style": {
      "style": "vivid",
      "format": "landscape",
      "art_style": "colorful playful illustration mixing modern pop cartoon with ukiyo-e yokai woodblock flavor — vivid purples, oranges and yellow-greens, confident brush-like outlines, flat shading with subtle paper texture. Cute and lively overall, with a faint eerie undertone in the shadows. Never gory or genuinely scary.",
      "background": "warm lantern-lit twilight background with japanese wave and asanoha patterns, comic-panel layout with a purple border frame",
      "include_characters": true,
      "frame_style": "comic-purple-border",
      "extra_prompt": "Compose like a fun yokai encyclopedia figure: neat Japanese labels with pointer lines, arrows comparing 'ゲーム設定' vs '元ネタの伝承', small ofuda / lantern / torii icons. Use original generic yokai silhouettes and symbolic props instead of copying any copyrighted character design. Keep the mood cheerful with just a light spooky accent.",
      "allow_text_labels": true,
      "allow_frame": true
    },
    "branding": {
      "watermark_text": "妖怪ラボ",
      "cta_style": "casual",
      "source_credit": "※ファンによる非公式考察 / 妖怪ウォッチは株式会社レベルファイブの登録商標です",
      "source_credit_opacity": 150,
      "source_credit_font_size": 20,
      "source_credit_font_size_short": 26
    },
    "output": {
      "target_duration": 720,
      "gen_type": "short",
      "bg_type": "static",
      "bg_path": null,
      "use_illustrations": true
    },
    "youtube": {
      "channel_id": "",
      "default_tags": [
        "妖怪ウォッチ",
        "妖怪",
        "ゆっくり解説",
        "考察",
        "元ネタ",
        "都市伝説",
        "ゲーム考察",
        "妖怪ウォッチ考察",
        "妖怪伝承",
        "日本の妖怪",
        "妖怪解説"
      ],
      "default_category": "20",
      "privacy_status": "private",
      "upload_schedule": null
    },
    "analytics": {
      "enabled": true,
      "fetch_retention_for": 5,
      "performance_threshold": {
        "min_ctr": 4,
        "min_retention": 40,
        "min_views_7d": 1000
      }
    },
    "short_illustrations": {
      "enabled": true,
      "illustration_method": "dalle",
      "max_count": 2,
      "card_style": "textbook",
      "card_label": "妖怪ファイル",
      "card_accent": [
        140,
        60,
        190
      ],
      "card_x": 64,
      "card_y": 250,
      "card_w": 952,
      "card_h": 430,
      "char_cy": 905,
      "char_icon_d": 210,
      "image_mode": "generate"
    },
    "effects": {
      "enabled": true,
      "preset": "pop",
      "allow_shake": true,
      "allow_flash": true,
      "allow_pixelate": false,
      "allow_glitch": false,
      "allow_tint": true,
      "shake_max_px": 10,
      "zoom_max": 0.07,
      "transition_duration": 0.4,
      "short_beat_zoom": true,
      "beat_interval": 1.8,
      "beat_zoom_max": 0.05
    },
    "persona": {
      "age_group": "10代",
      "gender": "男性",
      "interest_categories": [
        "ゲーム",
        "エンタメ"
      ],
      "content_depth": "ライト"
    }
  },
  "autopilot": {
    "enabled": true,
    "schedule": {
      "days_of_week": [
        0,
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "hour": 18,
      "minute": 30,
      "times": [
        {
          "hour": 18,
          "minute": 30,
          "days_of_week": [
            1,
            2,
            3,
            4,
            5
          ]
        },
        {
          "hour": 12,
          "minute": 30,
          "days_of_week": [
            0,
            6
          ]
        }
      ]
    },
    "duration_minutes": 12,
    "gen_type": "short",
    "publish_lead_minutes": 45,
    "theme_queue": [
      {
        "id": "bd1f8a8b",
        "title": "口裂け女の元ネタが怖すぎる — 昭和の噂はどこから来たのか",
        "angle": "1979年に全国へ広がった経緯と、その原型になった古い伝承をたどる都市伝説検証"
      },
      {
        "id": "3006ddcf",
        "title": "天狗の元ネタが怖すぎる — 山伏と神隠しの本当の関係",
        "angle": "山岳信仰と行方不明者の記録を結びつける"
      },
      {
        "id": "bfb9b533",
        "title": "雪女の原典 — 助けた男に「誰にも言うな」と告げた理由",
        "angle": "口外禁忌のモチーフがどこから来たか"
      },
      {
        "id": "f16d892e",
        "title": "猫又はなぜ尻尾が二股なのか — 老いた猫を恐れた江戸の記録",
        "angle": "長寿の猫への恐れが形になった経緯"
      },
      {
        "id": "22c05aab",
        "title": "山姥の元ネタ — なぜ山の女は旅人をもてなしてから襲うのか",
        "angle": "もてなしと裏切りの構造がどの説話から来たか"
      },
      {
        "id": "f92ea18a",
        "title": "小豆洗いの正体 — 川辺で聞こえる音の正体は何だったのか",
        "angle": "音の怪異が生まれた自然現象と、地域差"
      },
      {
        "id": "f2ef8a71",
        "title": "件(くだん)の伝承 — 予言して死ぬ牛の記録はいつから現れたか",
        "angle": "近世の瓦版に残る初出をたどる"
      },
      {
        "id": "e6999f23",
        "title": "姑獲鳥(うぶめ)の正体 — 抱かせた赤子が石になる意味",
        "angle": "産死への恐れが形になった経緯"
      },
      {
        "id": "f163f939",
        "title": "塗り壁はなぜ夜道を塞ぐのか — 遭難を説明した昔の知恵",
        "angle": "民俗学的な役割から読み解く"
      },
      {
        "id": "4d9b3437",
        "title": "鵺(ぬえ)の正体 — 平家物語に書かれた怪物の顔ぶれの意味",
        "angle": "合成獣として描かれた理由を原典から"
      },
      {
        "id": "37b239f2",
        "title": "送り犬の正体 — 転んだら食われる、山道の禁忌",
        "angle": "山道の危険を伝える装置としての妖怪"
      },
      {
        "id": "913352fe",
        "title": "二口女の原典 — 後頭部の口が生まれた理由",
        "angle": "継子いじめ譚との接続を文献で追う"
      },
      {
        "id": "b010e89b",
        "title": "大百足の伝承 — 俵藤太が唾を塗った矢で倒した理由",
        "angle": "唾に込められた呪術的な意味"
      },
      {
        "id": "74f94bf2",
        "title": "濡れ女の伝承 — 水辺で赤子を抱かせる怪異の正体",
        "angle": "水難への恐れと蛇信仰が交差した経緯を文献から"
      }
    ],
    "auto_optimize_schedule": true
  },
  "short_format": {
    "line_count": 8,
    "line_chars": "1〜7行目は28〜40字（目標34字）、8行目のみ50〜70字を許容",
    "total_chars_min": 270,
    "total_chars_max": 340,
    "structure": [
      "1行目=**3秒フック(最重要)**: 「これ知ってた？この妖怪、元ネタでは〇〇」「なんで〇〇だけ〇〇なの？」型。ゲーム内の可愛い姿と原典の恐怖の落差を匂わせる。",
      "2行目=**キャラ愛＋親しみ**: ゲームでのこの妖怪の人気・可愛さに触れて視聴者との距離を詰める（『これ好きな人多いよね』）。1行目から重い怪談口調で入らない。",
      "3行目=**原典への橋渡し**: 『でも元になった伝承を調べたら…』で原典側へ降りる準備。不穏さを1行で提示。",
      "4行目=**原典の恐怖①**: 伝承の生々しい描写を1行で置く。文献名や地域名など具体的な出典を1つ含める。",
      "5行目=**恐怖の転換**: 『しかも』『ところが』で角度を変え、ゲーム版では描かれなかった闇の面を出す。",
      "6行目=**都市伝説/噂**: ファンの間で囁かれる噂や作中の意味深な設定。『ファンの間ではこう言われている』と明示。",
      "7行目=**不気味な余韻**: 『もし夜道で見かけても、目を合わせないほうがいい』系の警告で終える。前向きなまとめは禁止。",
      "8行目=**登録CTA**: 『この妖怪の続き、他のファイルにも置いてある。チャンネル登録で次の調査を待て』"
    ],
    "extra_rules": [
      "冒頭2行はキャラ愛と親しみやすさで距離を詰める。1行目から重い怪談口調で入ると作品ファンが離脱する。",
      "怖さの根拠は必ず伝承・原典・作中描写に置く。ゲーム/伝承/ファン説を必ず区別して語る。",
      "解説役(ミナモ)は丁寧語で話しつつ、怪談の語り口に寄せる。リスナー役(ケンタ)は怯え・動揺中心。",
      "オチは前向きなまとめや教訓で締めない。不穏な余韻を必ず残す。"
    ]
  }
}```

---

## 2. バックエンド構成

### 2.1 ディレクトリ構成

```
backend/
├── main.py                  (67KB, 1760行)  FastAPI 本体。ルータ集約 + レガシー系エンドポイント
├── __init__.py
├── Dockerfile
├── requirements.txt
├── .env / .env.example
├── static/index.html                        旧UI（FastAPI 直配信）
│
├── api_phase1.py  (32KB)   新フロント(Next.js)向け /api/*: 認証・チャンネル・生成ジョブ・テーマキュー
├── api_phase2.py  (22KB)   設定・ペルソナ・アセット管理
├── api_phase3.py  (41KB)   YouTube/TikTok OAuth、公開（単体/ペア）、アナリティクス参照
├── api_phase4.py  (75KB)   スケジュール投稿・テンプレート・履歴/コスト・ABバリアント・通知
│                           ★ APScheduler の本体をここが所有
├── api_phase5.py  (21KB)   イラストサンプル生成・サムネ生成
├── api_phase6.py  (8KB)    BGM 音量プレビュー
├── api_improvement.py      いいね率改善ループ (Phase 6)
├── api_channel_autopilot.py(40KB) チャンネル別フルオート自動投稿
├── api_clips.py            切り抜きチャンネル API
├── api_analytics.py        YouTube Analytics v2 + コメント分析
├── api_pdca.py     (20KB)  シナリオ評価/AB答え合わせ/改善キュー/投稿時間最適化/サムネAB/トレンド/シリーズ
├── api_logs_archives.py    ログ・シナリオアーカイブ閲覧
├── api_competitors_demands.py 競合分析 + コメント需要 (Phase F)
├── api_research_effects.py 競合演出リサーチ (Phase F-2)
│
├── channels/
│   ├── channel_manager.py  (19KB) data/channels/*.json のロード・キャッシュ・保存
│   ├── config_validation.py       設定の整合性チェック（private 誤投稿の再発防止など）
│   └── video_format.py     (19KB) チャンネル別ビデオフォーマット定義
│
├── pipeline/               → 第3章参照
├── scripts/
│   ├── copy_oauth_client.py
│   ├── generate_character_sprites.py
│   ├── hash_password.py
│   └── setup_channel_branding.py
├── tests/
│   ├── test_clip_factory.py            test_config_validation.py
│   ├── test_description_blocks.py      test_growth_features.py
│   ├── test_growth_v2_features.py      test_growth_v3_features.py
│   ├── test_narration_video.py         test_round7_features.py
│   ├── test_round8_features.py         test_short_format.py
│   ├── test_thumbnail_ab_metric.py     test_trend_sources.py
│
└── 手動ランナー / 診断スクリプト（コミット済み）
    run_daily_pdca.py            日次PDCA（launchd 23:00）
    run_channel_short_upload.py  任意chでショート1本生成→投稿（汎用版）
    run_short_only.py            ショートのみ生成（投稿なし）
    run_ds_short_upload.py / run_scp_short_upload.py / run_pokemon_short_upload.py
    run_clip_channel.py          切り抜き生成→投稿
    run_scenario_render.py       事前生成シナリオから動画のみレンダリング
    run_daily_science*.py / run_scp_lab_*.py / run_blackhole.py / run_coffee_full.py
    rerender_existing.py / rerender_cat_no_gpt.py / rerun_cat_full.py
    upload_short_from_meta.py    生成済みショートをメタからアップロード
    make_2ch_matome_profile.py / make_company_facts_profile.py  プロフィール画像生成
    _refill_themes.py / _token_refresh_check.py / _verify_theme_dedup.py /
    _verify_youtube_real.py / _upload_existing_scp_short.py   （一時診断用）
```

### 2.2 `main.py` のエンドポイント一覧（全 61 本）

`main.py` は 14 個のルータを `include_router` した上で、レガシー/直叩き系を自前で持っている。

```
app.include_router(api_phase1..phase6, api_improvement, api_channel_autopilot,
                   api_clips, api_analytics, api_pdca, api_logs_archives,
                   api_competitors_demands, api_research_effects)
```

| 行 | メソッド | パス |
|---|---|---|
| 190 | GET | `/` |
| 203 | POST | `/compose` |
| 266 | GET | `/job/{job_id}` |
| 275 | POST | `/generate-description` |
| 298 | POST | `/generate-title` |
| 368 | POST | `/generate-video` |
| 465 | GET | `/generate-video/{job_id}` |
| 477 | POST | `/setup/move-to` |
| 505 | GET | `/list-files` |
| 528 | GET | `/download-file` |
| 597 | POST | `/youtube/upload` |
| 610 | GET | `/youtube/upload/{job_id}` |
| 617 | GET | `/youtube/auth-status` |
| 629 | POST | `/youtube/auth` |
| 643 | GET | `/youtube/channels` |
| 654 | POST | `/youtube/channels` |
| 668 | DELETE | `/youtube/channels/{channel_id}` |
| 680 | PUT | `/youtube/channels/{channel_id}` |
| 725 | GET | `/settings/api` |
| 745 | POST | `/settings/api` |
| 765 | GET | `/api-usage` |
| 775 | POST | `/api-usage/reset` |
| 786 | POST | `/settings/api/test-openai` |
| 808 | GET | `/channels` |
| 818 | GET | `/channels/{channel_id}` |
| 841 | POST | `/channels` |
| 852 | DELETE | `/channels/{channel_id}` |
| 873 | PUT | `/channels/{channel_id}` |
| 892 | PUT | `/channels/{channel_id}/format` |
| 903 | PUT | `/channels/{channel_id}/youtube-link` |
| 923 | PUT | `/channels/{channel_id}/analytics` |
| 963 | POST | `/scenarios/generate` |
| 1004 | POST | `/scenarios/generate-batch` |
| 1027 | POST | `/scenarios/suggest-themes` |
| 1042 | GET | `/scenarios/{channel_id}` |
| 1077 | POST | `/queue/submit` |
| 1104 | GET | `/queue/jobs` |
| 1112 | GET | `/queue/jobs/{job_id}` |
| 1123 | POST | `/queue/jobs/{job_id}/cancel` |
| 1137 | GET | `/queue/stats` |
| 1145 | POST | `/utils/copy-output` |
| 1178 | POST | `/factory/run` |
| 1255 | POST | `/factory/run-all` |
| 1350 | GET | `/api/trends/{channel_id}` |
| 1384 | POST | `/api/ab-test/generate` |
| 1412 | GET | `/api/ab-test/{test_id}` |
| 1425 | GET | `/api/ab-test` |
| 1461 | GET | `/theme-queue/{channel_id}` |
| 1469 | PUT | `/theme-queue/{channel_id}/settings` |
| 1481 | POST | `/theme-queue/{channel_id}/replenish` |
| 1497 | POST | `/theme-queue/{channel_id}/consume` |
| 1513 | POST | `/theme-queue/{channel_id}/items` |
| 1528 | DELETE | `/theme-queue/{channel_id}/items/{item_id}` |
| 1538 | PUT | `/theme-queue/{channel_id}/reorder` |
| 1545 | POST | `/theme-queue/check-all` |
| 1603 | GET | `/api/round6/cta-history/{channel_id}` |
| 1617 | POST | `/api/round6/viral-score` |
| 1632 | POST | `/api/round6/mute-check` |
| 1646 | GET | `/health` |
| 1669 | GET | `/health/config` |
| 1677 | — | `@app.on_event("startup")` |
| 1749 | — | `@app.on_event("shutdown")` |

### 2.3 起動時シーケンス（`main.py:1677` `startup_event`）

```python
1. 保存済み設定から OpenAI API キー / VOICEVOX URL を復元
2. ChannelManager()      初期化
3. ScenarioGenerator()   初期化
4. JobQueue(max_workers=2,
            on_job_complete=api_phase4.on_generation_complete,
            on_job_failed=<エラー通知>)
   → job_queue.set_pipeline(generate_all, channel_manager); job_queue.start()
5. api_phase1.configure(channel_manager, scenario_generator, job_queue)
6. api_phase4.setup_on_startup()          ← APScheduler 起動 + 定期ジョブ登録
7. api_channel_autopilot.restore_all()    ← 全チャンネルの autopilot ジョブ復元
8. _start_theme_queue_scheduler()         ← 30分ごとのテーマキュー補充（別 scheduler）
```

`shutdown_event` は `api_phase4.shutdown_scheduler()` のみ。

### 2.4 各ルータのエンドポイント一覧


#### `backend/api_phase1.py`

```
169:router = APIRouter(prefix="/api", tags=["phase1"])
@router.post("/auth/login"
@router.get("/auth/me"
@router.get("/system/status"
@router.get("/channels"
@router.get("/channels/{channel_id}"
@router.post("/generate"
@router.get("/generate/{job_id}/status"
@router.post("/generate/{job_id}/cancel"
@router.delete("/generate/{job_id}"
@router.get("/generate/active"
@router.post("/generate/suggest-theme"
@router.get("/theme-queue/{channel_id}"
@router.put("/theme-queue/{channel_id}/settings"
@router.post("/theme-queue/{channel_id}/replenish"
@router.post("/theme-queue/{channel_id}/items"
@router.delete("/theme-queue/{channel_id}/items/{item_id}"
@router.put("/theme-queue/{channel_id}/reorder"
@router.post("/theme-queue/check-all"
```

#### `backend/api_phase2.py`

```
28:router = APIRouter(prefix="/api", tags=["phase2"])
@router.get("/channels/{channel_id}/config"
@router.put("/channels/{channel_id}/config"
@router.get("/channels/{channel_id}/persona"
@router.put("/channels/{channel_id}/persona"
@router.post("/channels"
@router.delete("/channels/{channel_id}"
@router.get("/channels/{channel_id}/assets"
@router.post("/channels/{channel_id}/upload"
@router.delete("/channels/{channel_id}/assets/{kind}/{filename}"
@router.get("/channels/{channel_id}/assets/{kind}/{filename}"
@router.get("/settings"
@router.put("/settings"
@router.put("/auth/password"
```

#### `backend/api_phase3.py`

```
36:router = APIRouter(prefix="/api", tags=["phase3"])
@router.get("/youtube/status"
@router.post("/youtube/client"
@router.post("/youtube/auth-url"
@router.post("/youtube/callback"
@router.post("/youtube/disconnect"
@router.get("/channels/{channel_id}/youtube/status"
@router.post("/channels/{channel_id}/youtube/client"
@router.post("/channels/{channel_id}/youtube/auth"
@router.post("/channels/{channel_id}/youtube/callback"
@router.delete("/channels/{channel_id}/youtube"
@router.delete("/channels/{channel_id}/videos/{video_id}"
@router.get("/channels/{channel_id}/tiktok/status"
@router.post("/channels/{channel_id}/tiktok/client"
@router.post("/channels/{channel_id}/tiktok/auth"
@router.post("/channels/{channel_id}/tiktok/callback"
@router.delete("/channels/{channel_id}/tiktok"
@router.post("/youtube/publish"
@router.get("/youtube/publish/{job_id}"
@router.get("/youtube/publish"
@router.post("/youtube/publish-pair"
@router.get("/youtube/publish-pair/{job_id}"
@router.get("/youtube/publish-pair"
@router.get("/channels/{channel_id}/analytics"
@router.put("/videos/{job_id}/status"
@router.get("/videos/{job_id}/status"
```

#### `backend/api_phase4.py`

```
47:router = APIRouter(prefix="/api", tags=["phase4"])
@router.get("/schedules"
@router.get("/scheduler/jobs"
@router.post("/schedules"
@router.put("/schedules/{schedule_id}"
@router.patch("/schedules/{schedule_id}/toggle"
@router.delete("/schedules/{schedule_id}"
@router.get("/schedules/upcoming"
@router.post("/schedules/{schedule_id}/run-now"
@router.get("/templates"
@router.post("/templates"
@router.put("/templates/{template_id}"
@router.delete("/templates/{template_id}"
@router.get("/history"
@router.get("/history/cost-summary"
@router.post("/videos/{job_id}/ab-generate"
@router.get("/videos/{job_id}/variants"
@router.post("/videos/{job_id}/variants/select"
@router.get("/settings/notifications"
@router.put("/settings/notifications"
@router.post("/notifications/test"
```

#### `backend/api_phase5.py`

```
35:router = APIRouter(prefix="/api", tags=["phase5"])
@router.post("/illustrations/sample"
@router.post("/illustrations/sample/start"
@router.get("/illustrations/sample/{sample_id}"
@router.delete("/illustrations/sample/{sample_id}"
@router.post("/thumbnails/generate"
@router.post("/thumbnails/preview"
@router.post("/thumbnails/start"
@router.get("/thumbnails/job/{job_id}"
@router.get("/thumbnails/{thumbnail_id}"
@router.get("/thumbnails/{background_id}/background"
@router.delete("/thumbnails/{thumbnail_id}"
```

#### `backend/api_phase6.py`

```
32:router = APIRouter(prefix="/api", tags=["phase6"])
@router.post("/bgm-preview"
@router.get("/bgm-preview/{preview_id}"
```

#### `backend/api_improvement.py`

```
36:router = APIRouter(prefix="/api/improvement", tags=["phase6"])
@router.get("/settings/{channel_id}"
@router.put("/settings/{channel_id}"
@router.post("/check/{channel_id}"
@router.post("/check-all"
@router.get("/feedback/{channel_id}"
@router.post("/feedback/{video_id}/consume"
@router.delete("/feedback/{video_id}"
@router.post("/run-auto-check-now"
```

#### `backend/api_channel_autopilot.py`

```
52:router = APIRouter(prefix="/api/channels", tags=["autopilot"])
@router.get("/{channel_id}/autopilot"
@router.put("/{channel_id}/autopilot"
@router.get("/{channel_id}/autopilot/queue"
@router.post("/{channel_id}/autopilot/queue"
@router.put("/{channel_id}/autopilot/queue"
@router.patch("/{channel_id}/autopilot/queue/{theme_id}"
@router.delete("/{channel_id}/autopilot/queue/{theme_id}"
@router.post("/{channel_id}/autopilot/queue/refill"
@router.post("/{channel_id}/autopilot/run-now"
```

#### `backend/api_clips.py`

```
21:router = APIRouter(prefix="/api/clips", tags=["clips"])
@router.get("/{channel_id}/sources"
@router.get("/{channel_id}/state"
@router.post("/generate"
```

#### `backend/api_analytics.py`

```
36:router = APIRouter(prefix="/api/analytics", tags=["analytics"])
@router.get("/channel/{channel_id}/overview"
@router.get("/videos/{channel_id}"
@router.get("/pdca-report"
@router.get("/video/{video_id}/retention"
@router.get("/video/{video_id}/comments"
@router.post("/sync/{channel_id}"
@router.get("/insights/{channel_id}"
@router.post("/analyze/{channel_id}"
```

#### `backend/api_pdca.py`

```
29:router = APIRouter(prefix="/api", tags=["pdca"])
@router.get("/evaluations/{channel_id}"
@router.get("/evaluations/{channel_id}/{video_id}"
@router.post("/evaluations/{channel_id}/run"
@router.post("/evaluations/{channel_id}/{video_id}/run"
@router.get("/ab-reconciliation/{channel_id}"
@router.post("/ab-reconciliation/{channel_id}/run"
@router.get("/improvements/{channel_id}"
@router.post("/improvements/{channel_id}/run"
@router.post("/improvements/{channel_id}/{video_id}/regenerate"
@router.put("/improvements/{channel_id}/{video_id}/status"
@router.get("/model-performance/{channel_id}"
@router.get("/optimal-posting-time/{channel_id}"
@router.post("/optimal-posting-time/{channel_id}/apply"
@router.get("/thumbnail-tests/{channel_id}"
@router.get("/thumbnail-tests/{channel_id}/{video_id}"
@router.post("/thumbnail-tests/register"
@router.post("/thumbnail-tests/{channel_id}/{video_id}/check"
@router.post("/thumbnail-tests/{channel_id}/{video_id}/switch"
@router.post("/thumbnail-tests/{channel_id}/{video_id}/stop"
@router.post("/thumbnail-tests/{channel_id}/check-all"
@router.get("/trend-scanner/{channel_id}"
@router.post("/trend-scanner/{channel_id}/scan"
@router.post("/trend-scanner/{channel_id}/queue/{detection_id}"
@router.post("/trend-scanner/{channel_id}/dismiss/{detection_id}"
@router.get("/series/{channel_id}"
@router.post("/series/{channel_id}/detect"
@router.post("/series/{channel_id}/approve/{suggestion_id}"
@router.post("/series/{channel_id}/reject/{suggestion_id}"
```

#### `backend/api_logs_archives.py`

```
22:router = APIRouter(prefix="/api", tags=["logs-archives"])
@router.get("/logs"
@router.get("/scenario-archives"
@router.get("/scenario-archives/{channel_id}/{file_name}"
```

#### `backend/api_competitors_demands.py`

```
38:router = APIRouter(prefix="/api", tags=["competitors", "comment-demands"])
@router.get("/competitors/{channel_id}"
@router.post("/competitors/{channel_id}/scan"
@router.post("/competitors/{channel_id}/add"
@router.delete("/competitors/{channel_id}/remove/{competitor_id}"
@router.get("/competitors/{channel_id}/candidates"
@router.post("/competitors/{channel_id}/discover"
@router.post("/competitors/{channel_id}/candidates/{competitor_id}/approve"
@router.post("/competitors/{channel_id}/candidates/{competitor_id}/dismiss"
@router.get("/competitors/{channel_id}/rss"
@router.post("/competitors/{channel_id}/rss/scan"
@router.get("/comment-demands/{channel_id}"
@router.post("/comment-demands/{channel_id}/scan"
@router.post("/comment-demands/{channel_id}/queue/{demand_id}"
@router.post("/comment-demands/{channel_id}/dismiss/{demand_id}"
```

#### `backend/api_research_effects.py`

```
32:router = APIRouter(prefix="/api", tags=["research-effects"])
@router.post("/channels/{channel_id}/research-effects"
@router.get("/channels/{channel_id}/research-effects/job/{job_id}"
@router.get("/channels/{channel_id}/research-effects/latest"
@router.get("/channels/{channel_id}/research-effects"
@router.post("/channels/{channel_id}/research-effects/{record_id}/apply"
```

---

## 3. パイプラインモジュール

`backend/pipeline/` 配下の全モジュールと、各ファイル冒頭 docstring から取った機能説明。

### 3.1 `backend/pipeline/`（コア + 生成後最適化）

| ファイル | サイズ | 機能 |
|---|---|---|
| `__init__.py` | 396B | Auto-Yukkuri Movie Generator Pipeline Package ／ Includes title, description, and thumbnail generation modules |
| `ab_test_generator.py` | 17KB | ABTestGenerator — Phase C: タイトル・サムネ AB テスト ／ 1つのテーマ／シナリオに対して、タイトル 3 パターン + サムネキャッチコピー 3 パターンを ／ 生成し、それぞれに CTR 予測スコア (1-10) を付け、最高スコアの組み合わせを返す。 |
| `api_usage.py` | 10KB | OpenAI / Anthropic API 使用量トラッカー — トークン数と推定費用を記録 |
| `auto_comment.py` | 20KB | 投稿直後の自動コメント — 登録導線をコメント欄にもう1つ作る。 ／ 狙い: ／ 説明文の登録リンクは折りたたまれていて読まれない。一方コメント欄は |
| `claude_client.py` | 11KB | Claude API (Anthropic) クライアントラッパ — 分析・評価・採点・判断系の処理で共有して使う。 ／ GPT-4o を使っていた `chat/completions` 互換のヘルパを Claude Messages API に置き換えるための薄い層。 ／ ANTHROPIC_API_KEY 未設定時 / SDK 未導入時 / 呼び出し失敗時は None を返し、 |
| `comment_bait_injector.py` | 6KB | Comment Bait Injector — 視聴者コメントを誘発する議論ポイント注入（Round 8）。 ／ 狙い: ／ YouTubeアルゴリズムはコメント数をエンゲージメント指標として重視。 |
| `completion_rate_optimizer.py` | 12KB | Completion Rate Optimizer — 完走率最大化のためのペーシング最適化（Round 7）。 ／ 狙い: ／ 2026年のYouTubeショートアルゴリズムは完走率（watch-through rate）を |
| `contrast_amplifier.py` | 8KB | Contrast Amplifier — 常識vs真実 / before/after コントラスト増幅（Round 8）。 ／ 狙い: ／ 「え、常識と違うの？」「こんなに変わるの？」という |
| `cross_channel_bridge.py` | 11KB | Cross-Channel Content Bridge — チャンネル間コンテンツ連携（Round 6）。 ／ 狙い: ／ description_blocks のクロスプロモーション（説明文にリンクを載せる）とは異なり、 |
| `cta_rotator.py` | 17KB | CTA Rotation System — CTA疲労防止のスタイルローテーション（Round 6）。 ／ 狙い: ／ 毎回「チャンネル登録よろしく！」だけだと視聴者が免疫を持ち、 |
| `curiosity_gap_enforcer.py` | 7KB | Curiosity Gap Enforcer — 冒頭の情報ギャップ強制構築（Round 8）。 ／ 狙い: ／ 人間の脳は「知らない」状態に耐えられない。冒頭1-2行で |
| `description_blocks.py` | 15KB | 説明文ブロック生成 — 登録者増加に効く共通パーツ ／ video_generator.generate_descriptions から呼ばれ、説明文を次の順で組み立てるための ／ 部品を提供する: |
| `description_generator.py` | 8KB | YouTube Description Generator for Auto-Yukkuri Movie Pipeline ／ Generates YouTube descriptions with video summary, timestamps, channel info, and hashtags |
| `emotional_polarity_alternator.py` | 8KB | Emotional Polarity Alternator — 感情極性の交互切替で注意維持（Round 8）。 ／ 狙い: ／ 同じ感情トーンが3行以上続くと脳が「慣れ」を起こし離脱する。 |
| `hashtag_optimizer.py` | 9KB | 動的ハッシュタグ最適化 — 動画ごとにコンテンツ+トレンドに基づくハッシュタグを生成。 ／ 従来は全動画に同じ静的ハッシュタグを付けていたが、競合分析の結果: ／ - YouTube は先頭3個のハッシュタグをタイトル上に表示する |
| `hook_ab_selector.py` | 11KB | Hook A/B Selector — 冒頭フックの最適化（Round 6）。 ／ 狙い: ／ ショートの視聴継続は**最初の1秒**で決まる（2026年調査: スワイプ判断は |
| `image_collector.py` | 29KB | image_collector — Web image search + download with attribution. ／ Used by the video pipeline when a channel's image_mode is "collect" or "mix". ／ Each downloaded image carries an attribution record so the renderer can show |
| `mute_safe_checker.py` | 9KB | Mute-Safe Checker — ミュート視聴対応チェッカー（Round 6）。 ／ 狙い: ／ 2026年の調査で「ショート視聴者の70%がミュート（音なし）で視聴」 |
| `narration_video.py` | 25KB | 外部ナレーション音源から長尺動画を組み立てるパイプライン。 ／ video_generator.py は VOICEVOX で1行ずつ合成した音声を前提にしており、 ／ 「1行 = 1音声ファイル = 1クリップ」で尺を積み上げていく。 |
| `openai_compat.py` | 2KB | OpenAI Chat Completions のモデル世代差を吸収するヘルパー。 ／ gpt-5 系 (gpt-5.6-terra / -luna / -sol など) は gpt-4 系と以下が非互換: ／ * `max_tokens` を受け付けない — `max_completion_tokens` を要求する |
| `originality_guard.py` | 12KB | Originality Guard — コンテンツ独自性チェック（Round 7）。 ／ 狙い: ／ 2025年7月のYouTubeポリシー更新で、スクリプト類似度70%超のチャンネルは |
| `pattern_interrupt_injector.py` | 7KB | Pattern Interrupt Injector — 話法パターン中断で飽き防止（Round 8）。 ／ 狙い: ／ 人間は「パターン」を検知すると予測可能と判断して注意を緩める。 |
| `pillow_illustration.py` | 34KB | ローカル Pillow 図解ジェネレータ (APIコスト0) ／ ショート動画のイラストカードに差し込む「解説図」を、DALL-E を使わず ／ Pillow だけで描画する。テーマ文字列のキーワードからアイコン・図形を |
| `playlist_manager.py` | 13KB | 再生リスト自動管理 — アップロード直後に動画を再生リストへ入れる。 ／ 狙い: ／ 再生リストに入った動画は「次の動画」が自動再生されるので、1本あたりの |
| `post_upload.py` | 4KB | アップロード直後に走る共通処理（再生リスト投入 / シリーズ相互リンク）。 ／ 自動公開（api_phase4）と手動アップロードスクリプト（run_*_upload.py）の ／ 両方から同じ入口を呼べるようにまとめる。ここでの失敗は投稿を壊さない。 |
| `power_word_amplifier.py` | 10KB | Power Word Amplifier — パワーワード注入によるエンゲージメント増幅（Round 7）。 ／ 狙い: ／ 2026年のショートアルゴリズムはエンゲージメント（いいね・コメント・シェア）を |
| `replay_loop_seeder.py` | 10KB | Replay Loop Seeder — リプレイループ誘導のためのシームレス接続（Round 7）。 ／ 狙い: ／ 2026年のアルゴリズムでは「リプレイ率」が完走率と並ぶ独立シグナル。 |
| `retention_feedback_loop.py` | 12KB | Retention Feedback Loop — リテンション分析→シナリオ生成フィードバック（Round 7）。 ／ 狙い: ／ retention_analyzer と success_analyzer が収集したデータは |
| `round6_enhancer.py` | 4KB | Round 6 Post-Generation Enhancer — 生成後の6段階最適化パイプライン。 ／ generate() から1回だけ呼ばれ、以下の6モジュールを順番に実行する: ／ 1. Hook A/B Selector    — 冒頭フックの最適化（GPT-light採点） |
| `round7_enhancer.py` | 5KB | Round 7 Post-Generation Enhancer — 完走率 & リプレイ最大化パイプライン。 ／ generate() から1回だけ呼ばれ、以下の6モジュールを順番に実行する: ／ 1. Completion Rate Optimizer  — ペーシング最適化で完走率UP |
| `round8_enhancer.py` | 5KB | Round 8 Post-Generation Enhancer — エンゲージメント & 登録者最大化パイプライン。 ／ generate() から1回だけ呼ばれ、以下の6モジュールを順番に実行する: ／ 1. Curiosity Gap Enforcer      — 冒頭の情報ギャップ強制構築 |
| `scenario_validator.py` | 12KB | シナリオ構造バリデータ — 生成後のショートシナリオが構造ルールを守っているか検証する。 ／ 狙い: ／ プロンプトでフック・CTA・ループ構造を要求しても、LLMが守らないケースが |
| `seasonal_boost.py` | 7KB | 季節カレンダー — 月ごとの視聴トレンドに合わせてテーマ生成の優先度を調整する。 ／ 狙い: ／ 競合分析で確認された季節性: |
| `series_counter.py` | 5KB | シリーズ通し番号 — ショートのタイトルにエピソード番号を自動付与する。 ／ 狙い: ／ 競合分析で「シリーズ番号付きのタイトルが収集性を生み、 |
| `series_links.py` | 14KB | シリーズ連続性 — 説明文に「前回の動画」「次回の動画」を相互リンクする。 ／ 狙い: ／ 1本見た人を次の1本へ送る導線を、投稿のたびに自動で貼り直す。 |
| `short_endcard.py` | 7KB | ショート末尾のエンドカード — 見終わった直後に次の行き先を出す。 ／ 狙い: ／ ショートは最後まで見た視聴者がそのまま次のショートへスワイプしてしまう。 |
| `shorts_length_guard.py` | 7KB | ショート動画の完視聴率最適化ガード。 ／ 競合分析の結果: ／ - 完視聴率 70%+ で初動リーチが倍増、80%+ で最大化 |
| `subscribe_trigger_optimizer.py` | 8KB | Subscribe Trigger Optimizer — 有機的な登録トリガー最適化（Round 8）。 ／ 狙い: ／ 登録者数を最大化するには、明示的なCTA（「チャンネル登録してね」） |
| `swipe_stop_injector.py` | 10KB | Swipe-Stop Pattern Injector — 離脱防止パターンの多点注入（Round 6）。 ／ 狙い: ／ 2026年のYouTubeショートアルゴリズムは、1時間以内のスワイプ離脱率が |
| `thumbnail_generator.py` | 35KB | HTML+CSS+Playwright サムネイル生成モジュール. ／ Pipeline: ／ 1) GPT-5.6-terra で動画タイトルから「3行構成」のデザインブリーフをJSON生成 |
| `tiktok_oauth.py` | 19KB | TikTok OAuth 2.0 ヘルパ — チャンネル別連携 ／ YouTube (`youtube_oauth.py`) と同じ設計思想で、各チャンネル（内部 channel_id 単位）が ／ 独立した TikTok OAuth フローを持つ: |
| `tiktok_uploader.py` | 16KB | TikTok Content Posting API — 動画アップロード（チャンネル別 OAuth 対応） ／ YouTube (`youtube_uploader.py`) と並行して動く TikTok 投稿モジュール。 ／ 内部 channel_id ごとに保存された OAuth トークン（`tiktok_oauth.py`）を使う。 |
| `title_emoji_injector.py` | 9KB | Title Emoji Injector — タイトル絵文字CTR最適化（Round 7）。 ／ 狙い: ／ 2026年のYouTubeショートにおいて、タイトルへの戦略的な絵文字配置が |
| `title_generator.py` | 3KB | YouTube Title Generator for Auto-Yukkuri Movie Pipeline ／ Generates title suggestions for yukkuri videos |
| `title_quality.py` | 11KB | タイトルの CTR 品質スコアリング — 検索・ブラウズ面でのクリック率を上げる最終ゲート。 ／ 背景: ／ タイトルの書き方はプロンプト（`generator._title_rule_block`）で指示しているが、 |
| `trend_fetcher.py` | 21KB | TrendFetcher — Phase C: トレンドワード連動 ／ リアルタイムのトレンド情報をかき集めて「旬のテーマ」生成に使う。 ／ ソース: |
| `video_effects.py` | 28KB | 動画演出 (visual effects) レイヤ — シーン / セリフのムードに応じて ／ MoviePy のクリップに軽量な演出を追加する。 ／ 設計方針: |
| `video_generator.py` | 285KB | ゆっくり動画生成パイプライン (VOICEVOX対応) ／ フル動画 + ショート動画 + サムネイル + 説明文を一括生成 ／ Usage: |
| `viewer_requests.py` | 6KB | 視聴者参加型 — 「リクエスト募集中」の定型ブロック。 ／ 狙い: ／ コメントは「書いていい」と明示されると一気に増える。コメント数と返信は |
| `viral_score_gate.py` | 11KB | Viral Score Gate — バイラルポテンシャルの事前スコアリング（Round 6）。 ／ 狙い: ／ scenario_validator が「構造的に正しいか」をチェックするのに対し、 |
| `youtube_analytics.py` | 20KB | YouTube Analytics API v2 連携 — チャンネル別 OAuth でメトリクスを取得し SQLite に永続化。 ／ 提供する関数（チャンネル別。channel_id は内部 channel_id 文字列）: ／ - fetch_channel_overview(channel_id, days=30) |
| `youtube_comments.py` | 10KB | YouTube コメント取得 + Claude (Sonnet 4) による感情/トピック分析。 ／ 提供する関数: ／ - fetch_comments(channel_id, video_id, max_comments=200) |
| `youtube_oauth.py` | 25KB | YouTube OAuth 2.0 ヘルパ — チャンネル別連携 ／ 各チャンネル（内部 channel_id 単位）で独立した OAuth フローを持つ: ／ 1. /api/channels/{channel_id}/youtube/auth で認証URLを生成 |
| `youtube_pair_publisher.py` | 16KB | YouTube Pair Publisher — メイン+ショートをペアで時差公開 ／ フロー: ／ 1. メイン動画を即時公開（または publish 即時） |
| `youtube_uploader.py` | 23KB | YouTube Data API v3 — マルチチャンネル対応 動画アップロード・予約投稿 ／ ブランドアカウント方式: ／ 1つのGoogleアカウントで複数YouTubeチャンネルを管理。 |

### 3.2 `backend/pipeline/auto_scenario/`（テーマ選定・台本生成）

| ファイル | サイズ | 機能 |
|---|---|---|
| `__init__.py` | 320B | AutoScenario — GPT APIによる自動シナリオ生成 ／ チャンネルのtheme_seedsとcontent_policyを元に ／ yukkuri対話 / monologue 両スタイルのシナリオを自動生成する。 |
| `generator.py` | 170KB | ScenarioGenerator — GPT APIでシナリオを自動生成 ／ Usage: ／ from channels import ChannelManager |
| `genre.py` | 4KB | タイトル → ジャンル分類（レポート側と生成側で共有）。 ／ もともと `run_daily_pdca.py` にだけ存在したキーワード表を、シナリオ生成側からも ／ 参照できるよう切り出したもの。日次 PDCA レポートの「テーマ（ジャンル）別の成績」と、 |
| `theme_dedup.py` | 15KB | theme_dedup — テーマ（動画ネタ）の重複検出ユーティリティ。 ／ 2 段構え: ／ 1. **語彙的（lexical）** — 表記揺れ・言い換え・句読点違いを正規化し、文字 bigram の |
| `theme_queue.py` | 17KB | ThemeQueue — チャンネル別の「動画ネタストック」を持続化し、消費に応じて自動補充する。 ／ 設計: ／ - data/channels/<channel_id>/theme_queue.json にキューを保存（チャンネル設定本体は汚さない） |

### 3.3 `backend/pipeline/analytics/`（計測・分析・PDCA）

| ファイル | サイズ | 機能 |
|---|---|---|
| `__init__.py` | 831B | Analytics ヘルパモジュール。 ／ - like_rate: YouTube Data API でのいいね率取得 ／ - feedback_store: いいね率が閾値を下回った動画の改善フィードバック保存 |
| `ab_reconciler.py` | 12KB | AB テスト答え合わせ (Phase D — B) ／ 仕組み: ／ 1. data/ab_tests/*.json を走査し、actual_metrics が未紐付けの test を抽出 |
| `comment_demand.py` | 16KB | CommentDemand (Phase F-2) — 視聴者コメントからの需要発掘。 ／ 「○○やってほしい」「○○が気になる」「なんで○○なの？」系のリクエスト/質問を ／ Claude で抽出し、頻度・いいね数・チャンネル適合度でスコアリングして |
| `competitor_analyzer.py` | 26KB | CompetitorAnalyzer (Phase F-1) — 同ジャンルの伸びてるチャンネルのタイトル / サムネ / 投稿頻度 ／ を週1回スキャンして、Claude でパターンを抽出する。 ／ 入力: |
| `competitor_discovery.py` | 26KB | CompetitorDiscovery (Phase F-1b) — 同ジャンルの競合チャンネルを YouTube Search API で ／ 自動検出し、Claude で関連度をスコアリングして候補として提案する。 ／ ユーザーが承認した候補だけが正式に `data/channels/{id}.json` の `competitors` に追加される |
| `competitor_intelligence.py` | 21KB | CompetitorIntelligence — competitor_analyses テーブルに溜まっている週次の競合分析を ／ シナリオ生成・ネタ選定に注入できる形に集約する。 ／ 設計方針: |
| `competitor_rss.py` | 13KB | 競合チャンネル RSS 監視 — 同ジャンル人気チャンネルの新着を API クォータ0で追う。 ／ なぜ RSS か: ／ 既存の competitor_analyzer は YouTube Data API（search/videos）を叩くので |
| `competitor_thumbnails.py` | 3KB | Competitor thumbnail cache — download YouTube competitor thumbnails to a local ／ cache so they can be passed to GPT-4o Vision as visual references during ／ thumbnail design generation. |
| `competitor_video_analyzer.py` | 32KB | CompetitorVideoAnalyzer (Phase F-1c) — 競合動画を「ビジュアル + 内容」の両面から深掘り分析。 ／ ビジュアル分析: ／ - yt-dlp で動画を一時ディレクトリに最低画質でダウンロード |
| `effects_researcher.py` | 28KB | EffectsResearcher — 競合動画の画面演出を学習し、チャンネル JSON の effects ／ セクションに反映するための提案を返す機能。 ／ フロー: |
| `feedback_store.py` | 15KB | 改善フィードバック ストア — いいね率が閾値を下回った動画への次回改善提案を保存。 ／ DB: data/improvement_feedback.db ／ - video_feedback: 動画ごとのフィードバック1行（video_id を主キーに UPSERT） |
| `improvement_queue.py` | 7KB | 低 CTR 動画の自動改善キュー (Phase D — C) ／ 仕組み: ／ 1. チャンネル平均 CTR を算出 |
| `like_rate.py` | 8KB | YouTube いいね率（like_rate = likes / views）取得ヘルパ。 ／ 3つのソースに対応: ／ 1. YouTube Data API v3 (APIキー認証) — 単純な統計取得用 |
| `model_compete.py` | 14KB | AI モデル間コンペ — GPT-4o と Claude Sonnet 4 が同じテーマで競合し、 ／ ブラインド評価で勝者を決め、長期的な実績で補正する仕組み。 ／ 主な機能: |
| `pdca_report.py` | 29KB | PDCA レポート生成 — ショート vs メイン動画のパフォーマンス比較。 ／ YouTube Data API v3 で各動画の statistics + contentDetails を取得し、 ／ duration <= 60s or タイトルに「ショート」/「#Shorts」を含む動画を short として分類。 |
| `posting_optimizer.py` | 15KB | 投稿タイミング最適化 — 過去動画の公開時刻と再生数から最適投稿スロットを算出。 ／ YouTube Analytics API は "視聴者のオンライン時間帯" を直接返さないため、 ／ 公開済み動画の (曜日 × 時間帯) ごとの平均再生数を分析して最適スロットを推定する。 |
| `retention_analyzer.py` | 12KB | 視聴維持率カーブ分析エンジン — 各動画の retention カーブから離脱ポイントを検出し、 ／ シナリオの該当シーンを推定して Claude (Sonnet 4) に改善提案を作らせる。 ／ 入力: analytics SQLite の retention_curve / video_metrics |
| `scenario_archive.py` | 11KB | シナリオアーカイブ — 動画生成時にシナリオ原文をマークダウンで永続化する。 ／ 保存先: data/scenarios/<channel_id>/archive/<prefix>_<YYYYmmdd_HHMMSS>_scenario.md ／ （YouTube video_id が判明していない時点で生成するので prefix + 生成時刻でユニークにする） |
| `scenario_evaluator.py` | 17KB | シナリオ自動評価エンジン (Phase D — A2) ／ 各動画のシナリオ原文を Claude (Sonnet 4) で 6 軸採点し、離脱カーブ・コメント分析を ／ 突き合わせて「弱点セクション」と「具体的な改善提案」を生成する。 |
| `scenario_feedback.py` | 8KB | シナリオ生成プロンプトへの分析フィードバック注入。 ／ success_analyzer / retention_analyzer / コメントの top requests を読み取り、 ／ ScenarioGenerator が GPT に渡す追加指示テキストを組み立てる。 |
| `series_engine.py` | 15KB | SeriesEngine (Phase E-2) — バズった動画を検出 → Claude で続編パターンを分析 → ／ 3 候補を `series_suggestions` に保存 → 承認時に theme_queue へ投入。 ／ 「バズった」= チャンネル平均視聴数の VIRAL_THRESHOLD (1.5) 倍以上。 |
| `store.py` | 80KB | Analytics データストア — YouTube Analytics メトリクスとコメント分析を SQLite に保存。 ／ DB: data/analytics/analytics.db ／ テーブル: |
| `success_analyzer.py` | 12KB | 成功パターン分析エンジン — チャンネルの「伸びた動画」の共通パターンを抽出。 ／ 入力: analytics SQLite の video_metrics（直近スナップショット） ／ 出力: data/analytics/success_patterns.json（チャンネル別） |
| `thumbnail_ab_test.py` | 23KB | サムネイル AB テスト自動化 — 投稿後 CTR を監視し低ければ次の候補に自動差し替え。 ／ ライフサイクル: ／ 1. register_test(...) — 動画投稿直後にオリジナルサムネ + 2 バリエーションを登録 |
| `trend_scanner.py` | 22KB | TrendScanner (Phase E-1) — Google Trends / News / YouTube 急上昇を 6h ごとにスキャンし、 ／ チャンネル適合度の高いキーワードを `trend_detections` に保存 → 高スコアは theme_queue に自動投入。 ／ ソース: |

### 3.4 `backend/pipeline/clip_factory/`（切り抜き）

| ファイル | サイズ | 機能 |
|---|---|---|
| `__init__.py` | 746B | clip_factory — 既存長尺動画から縦型切り抜きショートを自動生成する。 ／ from pipeline.clip_factory import generate_clip, list_available_sources ／ generate_clip("clip-lab", count=1, upload=True) |
| `align.py` | 8KB | 長尺動画の「どの秒に台本のどの行が喋られているか」を復元する。 ／ 切り抜きを作るには行単位のタイムコードが要るが、video_generator は字幕の ／ タイミングを保存していない。音声側から取ろうとすると BGM とノイズフロアに |
| `pipeline.py` | 10KB | 切り抜きチャンネルのオーケストレーション。 ／ 在庫探索 → 元動画を1本選ぶ → エンジンで切り抜き生成 → メタ生成 ／ → （任意で）YouTube 投稿 → 消化済み区間を記録 |
| `renderer.py` | 22KB | 切り抜きショートの縦型レンダリング。 ／ レイアウトは data/research/clip_shorts_visual_analysis.json の横断分析に準拠する。 ／ 再生数 500万〜3300万の切り抜き/解説ショート7本を実測した結果、4本すべてが |
| `segments.py` | 16KB | 長尺のどこを切り抜くかを決める。 ／ スコアは2系統: ／ 1. 台本スコア — 数字・断定・種明かしの語彙が濃い区間を高く見る。台本 JSON が |
| `sources.py` | 11KB | 切り抜き元動画の在庫管理。 ／ 在庫は「ローカルに残っている長尺 mp4」＋「その台本 JSON」のペア。 ／ video_generator は ~/Desktop/動画出力用/<シナリオtitle>/ に出力し、シナリオは |

### 3.5 `backend/pipeline/clip_factory/engines/`

| ファイル | サイズ | 機能 |
|---|---|---|
| `__init__.py` | 819B | 切り抜きエンジンの差し替え口。 ／ - local  : 本リポジトリ内で完結する内製エンジン（既定） ／ - noimos : NoimosAI SaaS のクリエイティブエージェントに投げる |
| `local.py` | 5KB | 内製切り抜きエンジン。 ／ 台本アライメント → 区間選定 → 縦型レンダリングを自前で回す。外部SaaSも ／ ネットワークも要らないので autopilot から無人で走らせられる。 |
| `noimos.py` | 24KB | NoimosAI（SaaS）のクリエイティブエージェントに切り抜きを任せるエンジン。 ／ 経路は2つ。`clip.noimos.mode` で選ぶ（既定 "browser"）。 ／ browser : Playwright で app.noimosai.com を自動操作する（本命） |

### 3.6 `backend/pipeline/scheduler/`

| ファイル | サイズ | 機能 |
|---|---|---|
| `__init__.py` | 283B | Scheduler — 並列ジョブキュー & パイプラインオーケストレーター ／ 複数チャンネルの動画生成ジョブを並列管理。 |
| `job_queue.py` | 20KB | JobQueue — マルチチャンネル動画生成の並列ジョブ管理 ／ Features: ／ - 複数ワーカーによる並列生成（デフォルト2並列: VOICEVOXがボトルネック） |

### 3.7 `backend/channels/`

| ファイル | サイズ | 機能 |
|---|---|---|
| `__init__.py` | 831B | Channel Manager — マルチチャンネルプロファイル管理 ／ data/channels/*.json からチャンネル設定を読み込み、 ／ パイプラインにキャラクター・スタイル・デフォルト値を供給する。 |
| `channel_manager.py` | 19KB | ChannelManager — チャンネルプロファイルの読み込み・管理・パイプライン連携 ／ Usage: ／ from channels import ChannelManager |
| `config_validation.py` | 7KB | チャンネル設定（data/channels/*.json）の整合性チェック。 ／ 過去の事故: ／ scp-lab の publish_settings.default_privacy が "private" のまま放置され、 |
| `video_format.py` | 19KB | VideoFormat — チャンネル別ビデオフォーマット定義 ／ 各チャンネルのJSON profileの "video_format" セクションから読み込み、 ／ FrameRenderer / generate_all に注入するフォーマット設定。 |

### 3.8 生成後最適化パイプライン（Round 6 / 7 / 8）

`ScenarioGenerator.generate()` から各1回ずつ呼ばれ、シナリオ本文とタイトルを順に書き換える。各モジュールは独立していて、1つ落ちても他に影響しない。

**Round 6 — `round6_enhancer.enhance()`**（`round6_enhancer.py:1`）
```
1. Hook A/B Selector    — 冒頭フックの最適化（GPT-light採点）      hook_ab_selector.py
2. Swipe-Stop Injector  — 離脱防止パターンの多点注入              swipe_stop_injector.py
3. CTA Rotator          — CTAスタイルのローテーション（疲労防止）  cta_rotator.py
4. Cross-Channel Bridge — チャンネル間コンテンツ連携              cross_channel_bridge.py
5. Mute-Safe Checker    — ミュート視聴安全性チェック              mute_safe_checker.py
6. Viral Score Gate     — バイラルポテンシャル事前スコアリング     viral_score_gate.py
```

**Round 7 — `round7_enhancer.enhance()`**（`round7_enhancer.py:1`）
```
1. Completion Rate Optimizer — ペーシング最適化で完走率UP        completion_rate_optimizer.py
2. Replay Loop Seeder        — シームレスループ構造でリプレイ誘導 replay_loop_seeder.py
3. Power Word Amplifier      — パワーワード注入                  power_word_amplifier.py
4. Retention Feedback Loop   — 蓄積分析データのシナリオ直接反映   retention_feedback_loop.py
5. Originality Guard         — 独自性チェック（収益化保護）       originality_guard.py
6. Title Emoji Injector      — タイトル絵文字でCTR UP            title_emoji_injector.py
```
> 実行順の意図: 1-4 が本文を書き換え → 5 が「変更後の」シナリオで独自性検証 → 6 はタイトルのみ。

**Round 8 — `round8_enhancer.enhance()`**（`round8_enhancer.py:1`）
```
1. Curiosity Gap Enforcer        — 冒頭の情報ギャップ強制構築     curiosity_gap_enforcer.py
2. Comment Bait Injector         — コメント誘発ポイント注入       comment_bait_injector.py
3. Emotional Polarity Alternator — 感情極性の交互切替             emotional_polarity_alternator.py
4. Pattern Interrupt Injector    — 話法パターン中断で飽き防止     pattern_interrupt_injector.py
5. Subscribe Trigger Optimizer   — 有機的な登録トリガー注入       subscribe_trigger_optimizer.py
6. Contrast Amplifier            — 常識vs真実 コントラスト増幅    contrast_amplifier.py
```

> 補足: Round 6/7/8 の 18 モジュールと `scenario_validator.py` `series_counter.py` `seasonal_boost.py` `shorts_length_guard.py` `narration_video.py` は**すべて未コミット（`??`）**。第8章参照。


---

## 4. autopilot 設定

実装: `backend/api_channel_autopilot.py`（40KB）。設定は各チャンネル JSON の `autopilot` セクションに永続化され、APScheduler（api_phase4 が所有する `BackgroundScheduler`）に相乗りする。

### 4.1 スキーマ（`api_channel_autopilot.py:1` docstring より原文）

```
"autopilot": {
    "enabled": false,
    "schedule": {
        "days_of_week": [1, 3, 5],   # 0=sun..6=sat
        "hour": 18,                  # 単一スロット用 (times未指定時のレガシー)
        "minute": 0,
        "times": [                   # 1日複数スロットを使う場合はこちら
            {"hour": 7,  "minute": 0},
            {"hour": 17, "minute": 0}
        ]
    },
    "duration_minutes": 12,
    "gen_type": "both",             # "both" | "short" | "full" | "clip"
    "theme_queue": [
        {"id": "abc12345", "title": "...", "angle": "..."},
        ...
    ]
}

発火フロー:
    1. キュー先頭からテーマを取り出す
    2. 空なら ScenarioGenerator.suggest_themes でAI補充
    3. ScenarioGenerator.generate でシナリオ生成 → JobQueue 投入
    4. _attach_auto_publish_marker でフラグ付与 → 完了時に YouTube ペア公開
```

追加フィールド:

| フィールド | 既定 | 意味 |
|---|---|---|
| `publish_lead_minutes` | 0 | 生成時間を見越して**何分前に発火するか**。>0 なら発火は `slot時刻 - lead`、公開は YouTube 予約公開でスロット時刻ちょうど。上限 720分（12h）でクランプ |
| `auto_optimize_schedule` | false | true のときだけ、発火前に `posting_optimizer.slot_is_optimal_enough(tolerance_percent=50)` を見て、推奨スロットより 50% 以上劣っていれば `apply_to_autopilot()` でスケジュールを自動上書きする |
| `min_fire_interval_minutes` | 90 (`_MIN_FIRE_INTERVAL_MINUTES`) | 同一チャンネルの連投ガード。0 で無効 |
| `times[].days_of_week` | 継承 | スロット単位で曜日を上書き（「普段は18:00、木曜だけ10:00」を表現するため） |

### 4.2 連投ガード（`_burst_guard_ok`）

```python
# 2026-08-17 に 2ch-matome で 09:27〜09:28 の2分間に4本、daily-science と
# company-facts でも同時刻に投稿されるバーストが起きた。Mac のスリープ復帰後に
# misfire_grace_time(=1時間) 内の未発火ジョブがまとめて発火するのが原因で、
# 同時に出た4本のうち2本は再生数0のまま伸びなかった（同一チャンネルの短時間
# 連投はショートの配信が共食いする）。発火時刻ではなく「前回実際に発火した時刻」
# を見て、近すぎる発火は落とす。
_MIN_FIRE_INTERVAL_MINUTES = 90
```

あわせて `misfire_grace_time` も短縮されている:

```python
def _misfire_grace_seconds(lead_minutes: int) -> int:
    """遅延発火を許容する秒数。リード時間の半分（5〜20分）に収める。"""
    if lead_minutes and lead_minutes > 0:
        return int(max(300, min(1200, lead_minutes * 60 // 2)))
    return 600
```

`publish_lead_minutes=45` の全チャンネルでは grace = 1350 → クランプで **1200秒（20分）**。

### 4.3 整合性ガード

- `enabled=true` にするとき `schedule.days_of_week` が空だと 400。
- `default_privacy == "private"` のチャンネルは autopilot を有効化できない（400）。コメント原文:
  > 過去に scp-lab が default_privacy=private のまま自動投稿し、全部非公開になった事故の再発防止

### 4.4 各チャンネルの投稿時間（現在値）

| channel | enabled | gen_type | 投稿スロット (JST) | lead | duration | auto_optimize | queue在庫 |
|---|---|---|---|---|---|---|---|
| `2ch-matome` | ✅ | short | 17:15(月火水木金) / 19:15(月火水木金) / 12:15(日土) / 14:15(日土) | 45分 | 12分 | False | 16件 |
| `akashic-librarian` | ❌ | full | 18:45(月火水木金) / 13:45(日土) | 45分 | 12分 | True | 0件 |
| `clip-lab` | ✅ | clip | 17:45(月火水木金) / 19:45(月火水木金) / 12:45(日土) / 14:45(日土) | 0分 | 1分 | False | 2件 |
| `company-facts` | ✅ | short | 17:00(月火水木金) / 14:00(日土) | 45分 | 12分 | True | 11件 |
| `daily-science` | ✅ | short | 18:00(月火水木金) / 13:00(日土) | 45分 | 12分 | True | 15件 |
| `pokemon-lab` | ✅ | short | 17:30(月火水木金) / 12:00(日土) | 45分 | 12分 | True | 18件 |
| `scp-lab` | ✅ | short | 19:00(月火水木金) / 13:30(日土) | 45分 | 12分 | True | 17件 |
| `yokai-watch` | ✅ | short | 18:30(月火水木金) / 12:30(日土) | 45分 | 12分 | True | 14件 |

`days_of_week` は 0=日曜 … 6=土曜。全チャンネルの `schedule.days_of_week` は `[0,1,2,3,4,5,6]`（毎日）で、実際の曜日制御は各 `times[]` スロット側の `days_of_week` が担っている（平日枠と土日枠を別時刻にするため）。

実効の発火時刻は `publish_lead_minutes=45` のぶん前倒しされる。例: `scp-lab` の 19:00 スロットは **18:15 に生成開始 → 19:00 ちょうどに YouTube 予約公開**。

### 4.5 publish_settings（全チャンネル）

```json
{
  "2ch-matome": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 他のスレまとめはこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "お前らならどうする？コメントで教えてくれ"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "2chまとめ｜ショート全集",
      "main": "【2chまとめ】爆笑スレセレクション｜ゆっくり音声",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "読んでほしいスレをコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "akashic-librarian": {
    "auto_publish": false,
    "default_privacy": "public",
    "auto_comment": {
      "enabled": true,
      "question": "この記録、どう読み解く？あなたの解釈をコメントで"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "ラグナロクの司書｜ショート全集",
      "main": "ラグナロクの司書｜本編",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "調べてほしい都市伝説・未解明ミステリーをコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "clip-lab": {
    "auto_publish": false,
    "default_privacy": "public",
    "publish_targets": [
      "youtube"
    ],
    "auto_comment": {
      "enabled": true,
      "question": "続きが気になった人はコメントで教えて！フル解説も出してるよ"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "切り抜きラボ｜ショート全集",
      "main": "切り抜きラボ｜本編",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "切り抜いてほしい回をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "company-facts": {
    "auto_publish": false,
    "default_privacy": "public",
    "auto_comment": {
      "enabled": true,
      "question": "この数字、正直どう思う？あなたの会社と比べてコメントで！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "企業のホンネ｜ショート全集",
      "main": "【企業の闇】大手企業の裏事情まとめ｜ゆっくり解説シリーズ",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "ホンネを暴いてほしい企業をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "daily-science": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "これ知ってた？他にも気になる「なんで？」があったらコメントで教えて！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "1分科学｜ショート全集",
      "main": "【ゆっくり解説】日常に潜む科学の謎シリーズ",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "「これ科学的にどうなの？」という疑問をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "pokemon-lab": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "みんなならどっちが勝つと思う？コメントで予想を聞かせて！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "1分ポケモン研究｜ショート全集",
      "main": "ポケラボ｜本編考察",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "考察してほしいポケモン・図鑑説明をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "scp-lab": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "次はどのSCPを解剖してほしい？オブジェクト番号をコメントで！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "一口SCP｜ショート全集",
      "main": "【SCP解説】最恐SCPまとめ｜ゆっくり解説シリーズ",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "解説してほしいSCPの番号をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  },
  "yokai-watch": {
    "auto_publish": false,
    "default_privacy": "public",
    "short_delay_minutes": 10,
    "short_description_template": "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}",
    "auto_comment": {
      "enabled": true,
      "question": "この妖怪の元ネタ、知ってた？次に暴いてほしい妖怪をコメントで！"
    },
    "playlists": {
      "enabled": true,
      "auto_create": true,
      "privacy": "public",
      "shorts": "1分妖怪ファイル｜ショート全集",
      "main": "妖怪ラボ｜本編解説",
      "rules": []
    },
    "series_links": {
      "enabled": true
    },
    "viewer_requests": {
      "enabled": true,
      "prompt": "調べてほしい妖怪をコメントで教えてください。",
      "show_top_demands": true,
      "max_demands": 3
    }
  }
}
```

---

## 5. agent の設定と状態

`agent/` は「observe → think → act → check」を Claude の tool-use ループとして回す**汎用自律オーケストレーター**。目的（objective）とツールを差し替えれば他プロジェクトにも転用できる設計。

### 5.1 ファイル構成

```
agent/
├── README.md                  使い方・しくみ（下に全文）
├── __init__.py
├── __main__.py       (81行)   CLI: `python -m agent run youtube-growth [--once|--dry-run|...]`
├── config.py         (70行)   bootstrap（backend を sys.path 追加 + .env 読み込み）+ AgentConfig
├── core.py          (234行)   AutonomousAgent — Claude tool-use ループ本体・プロンプトキャッシュ
├── memory.py        (117行)   actions.jsonl / learnings.json / tasks.json の永続化
├── objectives/
│   ├── __init__.py
│   └── youtube_growth.py (65行)  mission + guidance + ツールセット
├── tools/
│   ├── base.py         (1.1KB)  Tool / ToolRegistry の抽象
│   ├── youtube.py      (7.0KB)  observe_post_status / upload_to_youtube / refresh_youtube_token
│   ├── video_gen.py    (3.8KB)  generate_short / check_voicevox / restart_voicevox
│   ├── browser.py     (21.6KB)  Playwright: browser_observe / app_login / youtube_reauth 等
│   ├── shell.py        (2.1KB)  任意コマンド実行
│   ├── notify.py       (2.7KB)  notify_user（Slack/LINE webhook or ローカルログ）
│   └── memory_tools.py (2.1KB)  remember / set_task
└── state/
    ├── actions.jsonl      8.6MB  行動ログ（append-only）
    ├── learnings.json    88KB / 125 エントリ
    ├── tasks.json        823B / 4 タスク（全て status=done）
    ├── notifications.log 174KB
    ├── screenshots/      367 ファイル
    └── browser_profile/  Playwright 永続プロファイル（Cookie/セッション）
```

### 5.2 使っているモデルと実行設定（`agent/config.py`）

```python
@dataclass
class AgentConfig:
    # Claude（考える脳）。AGENT_MODEL で上書き可。
    # 現行 Sonnet（claude-sonnet-4-6）を既定にしておく。
    # 旧 claude-sonnet-4-20250514 は廃止され 404 になるため更新（2026-06-18）。
    model: str = field(default_factory=lambda: os.environ.get(
        "AGENT_MODEL", "claude-sonnet-4-6"))
    max_tokens: int = 4096

    # 1 サイクル内で Claude に許す思考↔ツールの往復回数の上限（暴走防止）
    max_steps_per_cycle: int = 25

    # ループ実行時、サイクル間で待つ秒数（既定 30 分）
    interval_seconds: int = field(default_factory=lambda: int(
        os.environ.get("AGENT_INTERVAL_SECONDS", str(30 * 60))))

    dry_run: bool = False
    channels: tuple[str, ...] = ("scp-lab", "daily-science")
```

- **モデル: `claude-sonnet-4-6`**（`AGENT_MODEL` で上書き可）
- **対象チャンネル: `scp-lab` と `daily-science` の2つだけ**（8ch 中）
- **サイクル間隔: 1800秒（30分）**、1サイクルの最大ツール往復 25 回
- プロンプトキャッシュ: system ブロック末尾に `cache_control: ephemeral` を置いて tools+system をキャッシュ、履歴側は breakpoint を1つだけ前進させる（`_roll_cache_breakpoint`）

### 5.3 何をやっているか（`agent/objectives/youtube_growth.py` 原文）

```python
CHANNELS = ["scp-lab", "daily-science"]

OBJECTIVE = Objective(
    name="youtube-growth",
    mission=(
        f"対象チャンネル {CHANNELS} を着実に運用し、継続的に成長させる。\n"
        "短期の最優先KPIは『各チャンネルが毎日ショートを2本、公開(public)で投稿し続けること』。"
        "中期的にはサムネ品質・台本の質・競合分析を通じて視聴数と登録者を伸ばす。"
    ),
    guidance=(
        "- 各チャンネルについて、まず observe_post_status で『今日の投稿本数(posted_today)』を確認する。1日の目標は各チャンネル2本。\n"
        "- 今日の投稿が2本未満なら: VOICEVOX 確認 → generate_short で生成 → upload_to_youtube(privacy=public, is_short=true) で投稿。残り本数ぶん繰り返す。\n"
        "- 既に今日2本投稿済みなら、その日の必須投稿は完了。余力があればサムネや競合分析の改善を検討してよいが、無理はしない。\n"
        "- 生成時に VOICEVOX が落ちていたら restart_voicevox で復旧してから再試行する。\n"
        "- アップロードで認証エラーが出たら refresh_youtube_token を試す。それでも駄目（refresh_token 失効）なら、"
        "youtube_reauth でブラウザから OAuth 連携をやり直す。自動完了できれば再びアップロードを試す。\n"
        "- youtube_reauth が needs_human を返した（Googleログイン/2FA が必要）ときだけ notify_user で『UI再認証が必要』と通知する。\n"
        "- 投稿状況やアップロード結果を UI でも確認したいときは browser_observe で /channels/{id}/config や YouTube Studio を見る。\n"
        "- 台本生成の API エラーは generate_short 内で OpenAI→Claude フォールバックと再試行が行われる。数回失敗したら原因を記録し次サイクルに回す。\n"
        "- アップロードした動画のURLは必ずログに残す（行動ログに自動記録される）。\n"
        "- 1サイクルでは『各チャンネル最大1本の投稿』までに留め、2本目は次サイクル以降に回して時間を空ける（1日の上限は2本、それを超えて過剰投稿しない）。\n"
        "- 同じ失敗を繰り返さないよう、対処できたエラーは remember に knowhow として残す。"
    ),
)

def build_tools(memory: Memory) -> list[Tool]:
    return [
        OBSERVE_STATUS_TOOL, CHECK_VOICEVOX_TOOL, RESTART_VOICEVOX_TOOL,
        GENERATE_SHORT_TOOL, REFRESH_TOKEN_TOOL, UPLOAD_TOOL,
        *BROWSER_TOOLS, SHELL_TOOL, NOTIFY_TOOL, *build_memory_tools(memory),
    ]
```

### 5.4 現在の稼働状態

- プロセス: PID **693**、`/…/Python -u -m agent run youtube-growth`、**2026-07-13 19:30:43 起動**（launchd `com.youtube-factory.agent` KeepAlive）。
- **全サイクルが Anthropic 401 で失敗中**。`/tmp/agent_run.log` 末尾:

```
========================================================================
🤖 サイクル開始 2026-08-19T18:58:02  目的: youtube-growth
========================================================================
❌ Claude API error: AuthenticationError: Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'API key is invalid.'}, 'request_id': None}

⏳ 次のサイクルまで 1800 秒待機… (Ctrl-C で終了)
```

- `agent/state/actions.jsonl` の直近3件はすべて `kind: "cycle_error"` で同じ 401。**agent は現在、観測も投稿も一切していない**（実投稿は backend の autopilot 側が担っている）。

### 5.5 `agent/state/tasks.json`（全文）

```json
{
  "oauth_reauth_required": {
    "status": "done",
    "note": "2026-06-19: 両チャンネルともOAuth問題解消。daily-science投稿再開。"
  },
  "daily_science_oauth": {
    "status": "done",
    "note": "2026-06-19: refresh_youtube_token が成功しOAuth問題解消。動画「たった1秒で世界が崩壊する」をアップロード完了 (video_id: IhAWD2x3lAM)。redirect_uri_mismatch は解消済み。"
  },
  "oauth_reauth_both_channels": {
    "status": "done",
    "note": "2026-06-26サイクルでOAuth問題が解消。両チャンネルとも正常にアップロード完了。scp-lab: BcXI_UeWV_E, daily-science: xFK847mW54I"
  },
  "oauth_redirect_uri_fix": {
    "status": "done",
    "note": "2026-07-13 サイクルでconnected:trueを確認。OAuthブロック解消済み。"
  }
}
```

**タスクは全て done。つまり agent は現在「進行中タスクなし」の状態で、401 のため観測すらできていない。**

### 5.6 `agent/state/learnings.json`（125 エントリ・抜粋）

大半が `redirect_uri_mismatch` の反復記録で、同じ事象を日付違いで何十件も書き続けている（メモリの肥大化）。代表的なもの:

```
- claude_model_error: 2026-06-18にclaude-sonnet-4-20250514がNotFoundError(404)。モデル名の誤りか提供終了の可能性。
- daily_science_oauth_fix: 2026-06-19にrefresh_youtube_tokenが成功し、redirect_uri_mismatchエラーは自然解消。
- anthropic_credit_exhausted_2026_06_30: Anthropicのクレジット残高不足（Error 400）が多発。generate_short内のOpenAIフォールバックで生成は継続可能。
- redirect_uri_mismatch_persistent: 2026-07-12以降、複数サイクルにわたり両チャンネルで継続。
  popup_url の redirect_uri = 「http://localhost:3000/oauth/youtube/callback」
  client_id: 844705815004-deqffhpi7k4t4k8kn6oe9edle…
- redirect_uri_mismatch_2026_07_22_afternoon: 2026-07-20T16:25頃から約75時間以上継続。
  エージェント側でできることはすべて試み済み。人間が Google Cloud Console を修正する必要。
（以下、同種の記録が 07-20〜08 月にかけて多数）
```

### 5.7 `agent/README.md`（全文）

```markdown
# 自律 AI オーケストレーター (`agent/`)

人間の代わりに **observe → think → act → check** を Claude で回し続けるエージェント。
まずは YouTube 運用（scp-lab / daily-science）に特化。コアは汎用なので、目的とツールを
差し替えれば他プロジェクトにも転用できる。

## 使い方

```bash
# 1サイクルだけ・実際には生成/投稿しない（最初の動作確認はこれ）
python -m agent run youtube-growth --once --dry-run

# 1サイクルだけ実際に動かす（今日未投稿なら生成→public投稿まで）
python -m agent run youtube-growth --once

# 常駐ループ（既定30分間隔）
python -m agent run youtube-growth

# サイクル数/間隔/モデルを指定
python -m agent run youtube-growth --max-cycles 3 --interval 600 --model claude-sonnet-4-20250514

# エージェントの記憶（学習・タスク・直近ログ）を見る
python -m agent status
```

環境変数 `AGENT_MODEL` / `AGENT_INTERVAL_SECONDS` でも既定値を変えられる。
通知は `SLACK_WEBHOOK_URL` / `LINE_NOTIFY_TOKEN` があればそこへ、無ければ
`agent/state/notifications.log` と標準出力へ。

## しくみ

- `core.py` — 汎用ループ本体。Claude の tool-use を「思考↔行動」の往復として回す。
- `tools/` — エージェントの手:
  - `youtube.py` 投稿状況の観測 / アップロード / トークン更新
  - `video_gen.py` ショート動画生成（既存 `run_short_only`）/ VOICEVOX 死活・再起動
  - `browser.py` フロント(Next.js)のブラウザ操作（Playwright）。ページ遷移/クリック/入力/
    スクショ、`app_login`（アプリへログイン）、`youtube_reauth`（OAuth 再認証の自動化）
  - `shell.py` 任意コマンド, `notify.py` ユーザー通知, `memory_tools.py` 記憶操作
- `memory.py` — `state/` に actions(ログ)/learnings(知見)/tasks(進行中) を永続化。
  毎サイクル冒頭で要約して Claude に渡す＝記憶を踏まえて考える。
- `objectives/youtube_growth.py` — 目的(mission)・運用ルール(guidance)・ツール一式。
  他プロジェクトはこのファイルを雛形に objective を足す。

## 既知の前提

- `backend/.env` の `ANTHROPIC_API_KEY` で「考える」、`OPENAI_API_KEY` は台本生成
  （内部で OpenAI→Claude フォールバック）。
- 動画生成には VOICEVOX(localhost:50021) が必要。落ちていれば `restart_voicevox` で復旧を試みる。
- アップロードには各チャンネルの YouTube OAuth トークンが必要。失効時は `refresh_youtube_token`
  → 駄目（refresh_token 失効）なら `youtube_reauth` でブラウザから OAuth をやり直す
  → それも自動完了できなければ `notify_user` でUI再認証を要求する。

## ブラウザツール（Playwright）

フロント操作・OAuth 再認証の自動化に Playwright を使う。初回だけ導入が必要:

```bash
pip install playwright && playwright install chromium
```

- 既定でフロントは `http://localhost:3000`。別ポートなら `AGENT_APP_BASE_URL` で指定。
- アプリへのログインは `APP_PASSWORD`（`backend/.env`）を使う。永続プロファイル
  (`agent/state/browser_profile/`) に Cookie が残るので 2 回目以降は省略される。
- `youtube_reauth` は **Google のセッションが永続プロファイルに残っていれば headless で
  自動完了**する。初回は `AGENT_BROWSER_HEADLESS=0`（画面ありモード）で一度手動ログイン
  を通しておくと、以後は無人でも再認証できる。OAuth 同意で特定アカウントを優先選択させたい
  場合は `GOOGLE_ACCOUNT_EMAIL` を設定する。
- ログイン/2FA が必要で自動完了できないときは `needs_human=True` とスクリーンショット
  (`agent/state/screenshots/`) を返すので、エージェントは `notify_user` で人に上げる。

## 定期実行（launchd 例）

`--once` を cron / launchd から定期実行するのが安全（常駐より状態がクリーン）。
30分ごとに1サイクル走らせる launchd plist を組むなら `python -m agent run youtube-growth --once`
を `StartInterval 1800` で叩く。
```

### 5.8 `agent/config.py` / `agent/core.py` / `agent/memory.py`（全文）

#### `agent/config.py`

```python
"""エージェントの設定とブートストラップ。

- repo の backend/ を import path に追加
- backend/.env を環境変数に読み込む（既存値は上書きしない）
- モデル名・ループ間隔・dry-run などの実行時設定を 1 か所に集約
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- パス ---------------------------------------------------------------
AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
DATA_DIR = REPO_ROOT / "data"
STATE_DIR = AGENT_DIR / "state"          # メモリ・ログの保存先


def bootstrap() -> None:
    """backend を import 可能にし、.env を読み込む。

    冪等。core / tools を import する前に 1 度呼べばよい。
    """
    import sys

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

    STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AgentConfig:
    """1 回の実行（run）の振る舞いを決める設定。"""

    # Claude（考える脳）。AGENT_MODEL で上書き可。
    # 現行 Sonnet（claude-sonnet-4-6）を既定にしておく。
    # 旧 claude-sonnet-4-20250514 は廃止され 404 になるため更新（2026-06-18）。
    model: str = field(default_factory=lambda: os.environ.get(
        "AGENT_MODEL", "claude-sonnet-4-6"))
    max_tokens: int = 4096

    # 1 サイクル内で Claude に許す思考↔ツールの往復回数の上限（暴走防止）
    max_steps_per_cycle: int = 25

    # ループ実行時、サイクル間で待つ秒数（既定 30 分）
    interval_seconds: int = field(default_factory=lambda: int(
        os.environ.get("AGENT_INTERVAL_SECONDS", str(30 * 60))))

    # True の場合、動画生成・アップロードなど「外に出る/重い」操作を実際には行わず
    # 何をするはずだったかだけを返す。最初の動作確認に使う。
    dry_run: bool = False

    # 対象チャンネル
    channels: tuple[str, ...] = ("scp-lab", "daily-science")

    def anthropic_api_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "")
```

#### `agent/core.py`

```python
"""自律エージェントのコア。

observe → think → act → check を Claude の tool-use ループとして実装する。
1 サイクル = 「目的＋記憶＋現在状況」を Claude に渡し、Claude が観測系/行動系ツールを
使い切って end_turn するまで回す。終わったら記憶を更新し、次サイクルまで待つ。

このクラスは YouTube に依存しない汎用部分。目的とツールを差し替えれば他プロジェクトに
転用できる。
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from datetime import datetime

from .config import AgentConfig
from .memory import Memory
from .tools.base import Tool, ToolRegistry


@dataclass
class Objective:
    """エージェントの目的。プロジェクトごとに定義する。"""

    name: str          # 例: "youtube-growth"
    mission: str       # 何を達成したいか（長文可）
    guidance: str      # 運用ルール・判断基準


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- プロンプトキャッシュ --------------------------------------------------
# リクエストは tools → system → messages の順にレンダリングされる。system の最後の
# ブロックに breakpoint を置くと tools + system がまとめてキャッシュされ、サイクルを
# またいで再利用される。会話履歴側は _roll_cache_breakpoint で 1 個だけ前進させる。
CACHE_CONTROL = {"type": "ephemeral"}


def _roll_cache_breakpoint(messages: list[dict], blocks: list[dict]) -> None:
    """履歴の breakpoint を最新の tool_result 群の末尾へ前進させる。

    breakpoint は 1 リクエスト 4 個まで。ステップごとに付け足すと上限に当たるので、
    既存のものを外してから最新ブロックに 1 つだけ付け直す。
    """
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    b.pop("cache_control", None)
    if blocks:
        blocks[-1]["cache_control"] = dict(CACHE_CONTROL)


class AutonomousAgent:
    def __init__(
        self,
        config: AgentConfig,
        objective: Objective,
        tools: list[Tool],
        memory: Memory,
    ):
        self.config = config
        self.objective = objective
        self.registry = ToolRegistry(tools)
        self.memory = memory

        import anthropic  # 遅延 import（bootstrap 後）

        api_key = config.anthropic_api_key()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY が未設定です（backend/.env を確認）")
        self.client = anthropic.Anthropic(api_key=api_key)

    # --- system prompt --------------------------------------------------
    def _system_prompt(self) -> str:
        tool_names = ", ".join(self.registry.names())
        dry = ("\n【重要】現在は DRY-RUN モードです。動画生成やアップロードなど実際に外部へ"
               "影響する操作は実行されず、何をする予定だったかだけが返ります。観測と判断は通常通り行ってください。"
               if self.config.dry_run else "")
        return f"""あなたは自律的に動く運用エージェントです。人間の代わりに「状況を見て、考えて、行動して、結果を確認する」ループを回します。

# 目的
{self.objective.mission}

# 運用ルール
{self.objective.guidance}

# 使えるツール
{tool_names}

# 動き方
1. まず観測ツールで現在の状況を把握する（憶測で動かない）。
2. 目的とルールに照らして、このサイクルで取るべき行動を決める。
3. ツールで実行し、結果を確認する。失敗したら原因を考え、fallback や再試行を自分で試みる。
4. 重要な知見は remember で、継続する作業は set_task で記録する。
5. 自力で解決できない問題（要・人間の対応）だけ notify_user で通知する。通常の成功/失敗はログに残るので通知不要。
6. このサイクルでやるべきことが無ければ、無理に行動せず「今回は対応不要」と述べて終了する。

簡潔に、要点だけテキストで説明しながらツールを使ってください。{dry}"""

    # --- ツール実行 -----------------------------------------------------
    def _execute_tool(self, name: str, tool_input: dict) -> dict:
        tool = self.registry.get(name)
        if tool is None:
            return {"error": f"unknown tool: {name}"}

        if self.config.dry_run and not tool.safe_in_dry_run:
            return {"dry_run": True,
                    "note": f"[DRY-RUN] {name} は実行されませんでした",
                    "would_call_with": tool_input}
        try:
            result = tool.func(**tool_input)
            return result if isinstance(result, dict) else {"result": result}
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-1500:]}

    # --- 1 サイクル -----------------------------------------------------
    def run_cycle(self) -> dict:
        print(f"\n{'=' * 72}\n🤖 サイクル開始 {_now_iso()}  目的: {self.objective.name}"
              f"{'  [DRY-RUN]' if self.config.dry_run else ''}\n{'=' * 72}")

        context = self.memory.recent_context()
        messages = [{
            "role": "user",
            "content": (
                "新しいサイクルを開始します。下記はこれまでの記憶です。\n\n"
                f"{context}\n\n"
                "現在の状況を観測し、目的とルールに沿って必要な行動を取ってください。"
            ),
        }]

        tool_calls = 0
        actions: list[dict] = []
        final_text = ""

        for step in range(self.config.max_steps_per_cycle):
            try:
                resp = self.client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    # 最後の system ブロックの breakpoint が tools + system を丸ごとキャッシュする
                    system=[{"type": "text",
                             "text": self._system_prompt(),
                             "cache_control": dict(CACHE_CONTROL)}],
                    tools=self.registry.specs(),
                    messages=messages,
                )
            except Exception as e:  # noqa: BLE001
                err = f"Claude API error: {type(e).__name__}: {e}"
                print(f"❌ {err}")
                self.memory.log_action("cycle_error", {"summary": err}, ts=_now_iso())
                return {"ok": False, "error": err}

            # アシスタントのテキストを表示
            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    print(f"\n💭 {block.text.strip()}")
                    final_text = block.text.strip()

            messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                break  # end_turn: このサイクル終了

            # tool_use ブロックを実行して結果を返す
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                tool_calls += 1
                print(f"\n🔧 {block.name}({json.dumps(block.input, ensure_ascii=False)[:300]})")
                result = self._execute_tool(block.name, block.input)
                ok = not result.get("error")
                print(f"   {'✅' if ok else '⚠️ '} {json.dumps(result, ensure_ascii=False, default=str)[:400]}")

                actions.append({"tool": block.name, "input": block.input, "ok": ok})
                self.memory.log_action(
                    "tool_call",
                    {"summary": f"{block.name} -> {'ok' if ok else result.get('error')}",
                     "tool": block.name, "input": block.input, "result": result},
                    ts=_now_iso(),
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

            # 次リクエストで履歴全体がキャッシュヒットするよう breakpoint を前進させる
            _roll_cache_breakpoint(messages, tool_results)
            messages.append({"role": "user", "content": tool_results})
        else:
            print("\n⚠️  max_steps に到達。サイクルを打ち切ります。")

        self.memory.log_action(
            "cycle_done",
            {"summary": final_text[:240] or "(no summary)",
             "tool_calls": tool_calls},
            ts=_now_iso(),
        )
        print(f"\n✅ サイクル終了（ツール呼び出し {tool_calls} 回）")
        return {"ok": True, "tool_calls": tool_calls, "actions": actions, "summary": final_text}

    # --- ループ ---------------------------------------------------------
    def run_loop(self, once: bool = False, max_cycles: int | None = None) -> None:
        cycle = 0
        while True:
            cycle += 1
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                print("\n👋 中断されました。")
                return
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self.memory.log_action("cycle_crash", {"summary": str(e)}, ts=_now_iso())

            if once or (max_cycles is not None and cycle >= max_cycles):
                return

            wait = self.config.interval_seconds
            print(f"\n⏳ 次のサイクルまで {wait} 秒待機… (Ctrl-C で終了)")
            try:
                time.sleep(wait)
            except KeyboardInterrupt:
                print("\n👋 終了します。")
                return
```

#### `agent/memory.py`

```python
"""永続メモリ。

3 種類を JSON で保持する（inspect しやすさ優先、SQLite は将来差し替え可）:

- actions  : 過去の行動と結果のログ（append-only）
- learnings: 学習した知見「このエラーにはこう対処した」を key→値で蓄積
- tasks    : 進行中タスク（id→状態）

`recent_context()` が Claude に渡す要約テキストを返す。これがエージェントの
「記憶を踏まえて考える」の核になる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Memory:
    def __init__(self, state_dir: Path):
        self.dir = state_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.actions_path = self.dir / "actions.jsonl"
        self.learnings_path = self.dir / "learnings.json"
        self.tasks_path = self.dir / "tasks.json"

    # --- actions（append-only ログ）------------------------------------
    def log_action(self, kind: str, detail: dict[str, Any], *, ts: str) -> None:
        rec = {"ts": ts, "kind": kind, **detail}
        with self.actions_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def recent_actions(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.actions_path.exists():
            return []
        lines = self.actions_path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    # --- learnings（知見）---------------------------------------------
    def _load_learnings(self) -> dict[str, Any]:
        if self.learnings_path.exists():
            try:
                return json.loads(self.learnings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def remember(self, key: str, value: str) -> None:
        d = self._load_learnings()
        d[key] = value
        self.learnings_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def learnings(self) -> dict[str, Any]:
        return self._load_learnings()

    # --- tasks（進行中タスク）-----------------------------------------
    def _load_tasks(self) -> dict[str, Any]:
        if self.tasks_path.exists():
            try:
                return json.loads(self.tasks_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def set_task(self, task_id: str, status: str, note: str = "") -> None:
        d = self._load_tasks()
        d[task_id] = {"status": status, "note": note}
        self.tasks_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def tasks(self) -> dict[str, Any]:
        return self._load_tasks()

    # --- Claude に渡すコンテキスト要約 --------------------------------
    def recent_context(self, action_limit: int = 15) -> str:
        parts: list[str] = []

        learnings = self.learnings()
        if learnings:
            parts.append("## 学習した知見（過去の対処法）")
            for k, v in learnings.items():
                parts.append(f"- {k}: {v}")

        tasks = self.tasks()
        open_tasks = {k: v for k, v in tasks.items()
                      if v.get("status") not in ("done", "completed", "cancelled")}
        if open_tasks:
            parts.append("\n## 進行中タスク")
            for k, v in open_tasks.items():
                parts.append(f"- [{v.get('status')}] {k}: {v.get('note', '')}")

        actions = self.recent_actions(action_limit)
        if actions:
            parts.append("\n## 直近の行動ログ（古い→新しい）")
            for a in actions:
                kind = a.get("kind")
                ts = a.get("ts", "")
                summary = a.get("summary") or a.get("result") or a.get("detail") or ""
                summary = str(summary)
                if len(summary) > 240:
                    summary = summary[:240] + "…"
                parts.append(f"- {ts} [{kind}] {summary}")

        if not parts:
            return "（まだ記憶はありません。これが最初のサイクルです。）"
        return "\n".join(parts)
```

#### `agent/__main__.py`

```python
"""CLI エントリーポイント。

  python -m agent run youtube-growth            # ループ実行（既定30分間隔）
  python -m agent run youtube-growth --once     # 1サイクルだけ
  python -m agent run youtube-growth --dry-run  # 生成/投稿せず観測と判断だけ
  python -m agent run youtube-growth --max-cycles 3 --interval 600
  python -m agent status                        # 記憶（学習/タスク/直近ログ）を表示
"""

from __future__ import annotations

import argparse
import sys

from . import config as cfg


def _build_agent(args):
    from .core import AutonomousAgent
    from .memory import Memory
    from .objectives import youtube_growth

    if args.objective != "youtube-growth":
        print(f"未知の objective: {args.objective}（現在は youtube-growth のみ）")
        sys.exit(2)

    conf = cfg.AgentConfig(dry_run=args.dry_run)
    if args.interval is not None:
        conf.interval_seconds = args.interval
    if args.model:
        conf.model = args.model

    memory = Memory(cfg.STATE_DIR)
    tools = youtube_growth.build_tools(memory)
    return AutonomousAgent(conf, youtube_growth.OBJECTIVE, tools, memory), memory


def cmd_run(args):
    agent, _ = _build_agent(args)
    agent.run_loop(once=args.once, max_cycles=args.max_cycles)


def cmd_status(args):
    from .memory import Memory

    memory = Memory(cfg.STATE_DIR)
    print("=== 学習した知見 ===")
    for k, v in (memory.learnings() or {}).items():
        print(f"- {k}: {v}")
    print("\n=== タスク ===")
    for k, v in (memory.tasks() or {}).items():
        print(f"- [{v.get('status')}] {k}: {v.get('note','')}")
    print("\n=== 直近の行動ログ ===")
    for a in memory.recent_actions(25):
        print(f"- {a.get('ts')} [{a.get('kind')}] {str(a.get('summary',''))[:160]}")


def main(argv=None):
    cfg.bootstrap()

    parser = argparse.ArgumentParser(prog="agent", description="自律 AI オーケストレーター")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="エージェントを実行")
    p_run.add_argument("objective", nargs="?", default="youtube-growth")
    p_run.add_argument("--once", action="store_true", help="1サイクルだけ実行")
    p_run.add_argument("--dry-run", action="store_true", help="生成/投稿せず観測と判断のみ")
    p_run.add_argument("--max-cycles", type=int, default=None, help="最大サイクル数")
    p_run.add_argument("--interval", type=int, default=None, help="サイクル間隔（秒）")
    p_run.add_argument("--model", default=None, help="使用する Claude モデル名")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="記憶を表示")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

#### `agent/objectives/youtube_growth.py`

```python
"""YouTube チャンネル成長の目的とツールセット。

汎用の AutonomousAgent に渡す Objective とツール一覧をここで組み立てる。
他プロジェクト用の objective を足すときはこのファイルを雛形にする。
"""

from __future__ import annotations

from ..core import Objective
from ..memory import Memory
from ..tools.base import Tool
from ..tools.browser import BROWSER_TOOLS
from ..tools.memory_tools import build_memory_tools
from ..tools.notify import NOTIFY_TOOL
from ..tools.shell import SHELL_TOOL
from ..tools.video_gen import (
    CHECK_VOICEVOX_TOOL,
    GENERATE_SHORT_TOOL,
    RESTART_VOICEVOX_TOOL,
)
from ..tools.youtube import (
    OBSERVE_STATUS_TOOL,
    REFRESH_TOKEN_TOOL,
    UPLOAD_TOOL,
)

CHANNELS = ["scp-lab", "daily-science"]

OBJECTIVE = Objective(
    name="youtube-growth",
    mission=(
        f"対象チャンネル {CHANNELS} を着実に運用し、継続的に成長させる。\n"
        "短期の最優先KPIは『各チャンネルが毎日ショートを2本、公開(public)で投稿し続けること』。"
        "中期的にはサムネ品質・台本の質・競合分析を通じて視聴数と登録者を伸ばす。"
    ),
    guidance=(
        "- 各チャンネルについて、まず observe_post_status で『今日の投稿本数(posted_today)』を確認する。1日の目標は各チャンネル2本。\n"
        "- 今日の投稿が2本未満なら: VOICEVOX 確認 → generate_short で生成 → upload_to_youtube(privacy=public, is_short=true) で投稿。残り本数ぶん繰り返す。\n"
        "- 既に今日2本投稿済みなら、その日の必須投稿は完了。余力があればサムネや競合分析の改善を検討してよいが、無理はしない。\n"
        "- 生成時に VOICEVOX が落ちていたら restart_voicevox で復旧してから再試行する。\n"
        "- アップロードで認証エラーが出たら refresh_youtube_token を試す。それでも駄目（refresh_token 失効）なら、"
        "youtube_reauth でブラウザから OAuth 連携をやり直す。自動完了できれば再びアップロードを試す。\n"
        "- youtube_reauth が needs_human を返した（Googleログイン/2FA が必要）ときだけ notify_user で『UI再認証が必要』と通知する。\n"
        "- 投稿状況やアップロード結果を UI でも確認したいときは browser_observe で /channels/{id}/config や YouTube Studio を見る。\n"
        "- 台本生成の API エラーは generate_short 内で OpenAI→Claude フォールバックと再試行が行われる。数回失敗したら原因を記録し次サイクルに回す。\n"
        "- アップロードした動画のURLは必ずログに残す（行動ログに自動記録される）。\n"
        "- 1サイクルでは『各チャンネル最大1本の投稿』までに留め、2本目は次サイクル以降に回して時間を空ける（1日の上限は2本、それを超えて過剰投稿しない）。\n"
        "- 同じ失敗を繰り返さないよう、対処できたエラーは remember に knowhow として残す。"
    ),
)


def build_tools(memory: Memory) -> list[Tool]:
    return [
        OBSERVE_STATUS_TOOL,
        CHECK_VOICEVOX_TOOL,
        RESTART_VOICEVOX_TOOL,
        GENERATE_SHORT_TOOL,
        REFRESH_TOKEN_TOOL,
        UPLOAD_TOOL,
        *BROWSER_TOOLS,
        SHELL_TOOL,
        NOTIFY_TOOL,
        *build_memory_tools(memory),
    ]
```

---

## 6. launchd 設定

`~/Library/LaunchAgents/` に4本。`launchctl list` の現況:

```
PID     Status  Label
37949	-9	com.youtube-factory.ngrok
-	0	com.youtube-factory.pdca
-	1	com.youtube-factory.backend
693	0	com.youtube-factory.agent
```

- `ngrok` = PID 37949 稼働中（Status -9 は前回シグナル終了の記録）
- `pdca` = 実行中でない（カレンダー起動待ち）、最終 exit 0
- `backend` = **実行中でない・最終 exit 1**。実プロセスは PID 49372 として launchd 外で稼働中
- `agent` = PID 693 稼働中、exit 0

### `/Users/ayukiyamazaki/Library/LaunchAgents/com.youtube-factory.agent.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youtube-factory.agent</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-u</string>
        <string>-m</string>
        <string>agent</string>
        <string>run</string>
        <string>youtube-growth</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/ayukiyamazaki/Developer/youtube-factory</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>/tmp/agent_run.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/agent_run.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
```

### `/Users/ayukiyamazaki/Library/LaunchAgents/com.youtube-factory.backend.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youtube-factory.backend</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-u</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/ayukiyamazaki/Developer/youtube-factory/backend</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>/Users/ayukiyamazaki/Developer/youtube-factory/logs/backend.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/ayukiyamazaki/Developer/youtube-factory/logs/backend.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>/Users/ayukiyamazaki</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
```

### `/Users/ayukiyamazaki/Library/LaunchAgents/com.youtube-factory.ngrok.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youtube-factory.ngrok</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/ngrok</string>
        <string>http</string>
        <string>8000</string>
        <string>--url=agreeing-corrode-shabby.ngrok-free.dev</string>
        <string>--log=stdout</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/ayukiyamazaki/Developer/youtube-factory</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>/tmp/ngrok_tunnel.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/ngrok_tunnel.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>/Users/ayukiyamazaki</string>
    </dict>
</dict>
</plist>
```

### `/Users/ayukiyamazaki/Library/LaunchAgents/com.youtube-factory.pdca.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youtube-factory.pdca</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-u</string>
        <string>backend/run_daily_pdca.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/ayukiyamazaki/Developer/youtube-factory</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>/tmp/pdca_run.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/pdca_run.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
```

---

## 7. 環境変数

### 7.1 `backend/.env`（実ファイル・シークレットのみ伏せ字）

```bash
# ============================================================
# YouTube Factory — バックエンド環境変数
# ============================================================

# --- 認証 ---
API_KEY=<REDACTED>
APP_PASSWORD=<REDACTED>

# JWT 署名シークレット（固定値。変更するとログイン済みトークンが全て無効になる）
JWT_SECRET=<REDACTED>

# --- 外部 API ---
OPENAI_API_KEY=<REDACTED>

# Claude (Anthropic) API キー — 分析・評価・採点・判断系で使用
# 未設定時は各機能がルールベースのフォールバックで動作する
ANTHROPIC_API_KEY=<REDACTED>

YOUTUBE_API_KEY=<REDACTED>

# --- CORS ---
CORS_ORIGINS=http://localhost:3000

# --- サーバー ---
PORT=8000
HOST=0.0.0.0

# --- VOICEVOX ---
VOICEVOX_URL=http://localhost:50021

# --- ngrok ---
NGROK_AUTHTOKEN=<REDACTED>
NGROK_DOMAIN=

PEXELS_API_KEY=<REDACTED>

# --- NoimosAI (clip-lab 切り抜きエンジン / mode=browser) ---
# app.noimosai.com のアカウントを人手で作ってから、以下のコメントを外して記入する。
# 記入後 data/channels/clip-lab.json の clip.engine を "local" -> "noimos" に変更。
# NOIMOS_EMAIL=
# NOIMOS_PASSWORD=<REDACTED>
# mode=cli を使う場合のみ（Pro $99/月〜の契約が必要）
# NOIMOS_API_KEY=<REDACTED>
```

**非機密の実設定値:**

| 変数 | 値 |
|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` |
| `PORT` | `8000` |
| `HOST` | `0.0.0.0` |
| `VOICEVOX_URL` | `http://localhost:50021` |
| `NGROK_DOMAIN` | （空。実際は launchd plist 側で `agreeing-corrode-shabby.ngrok-free.dev` を直接指定） |
| `NOIMOS_EMAIL` / `NOIMOS_PASSWORD` / `NOIMOS_API_KEY` | すべて**コメントアウトされ未設定**（→ clip-lab の engine は `local`） |

設定されているキー: `API_KEY`, `APP_PASSWORD`, `JWT_SECRET`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `NGROK_AUTHTOKEN`, `PEXELS_API_KEY`。

> `.env.example` にある `APP_PASSWORD_HASH` / `PIXABAY_API_KEY` / `UNSPLASH_ACCESS_KEY` / `GOOGLE_CSE_API_KEY` / `GOOGLE_CSE_ID` / `DATABASE_URL` は**実 .env には存在しない**。認証は平文の `APP_PASSWORD` にフォールバックしている。画像コレクタは Pexels のみ有効。

### 7.2 `backend/.env.example`（全文）

```bash
# ============================================================
# YouTube Factory — バックエンド環境変数
# このファイルを .env にコピーして値を設定してください
#   cp .env.example .env
# ============================================================

# --- 認証 ---
# API キー（未設定の場合、初回起動時に自動生成されます）
API_KEY=

# --- Phase 1 フロントエンド認証 ---
# パスワードハッシュ（推奨）。生成: python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode())"
# シングルクォートで囲むこと（$ がシェル展開されないように）
APP_PASSWORD_HASH='$2b$12$replace_with_real_bcrypt_hash'

# 開発用フォールバック（HASH 未設定時のみ使われる）
# APP_PASSWORD=changeme

# JWT 署名シークレット（任意のランダム文字列）。openssl rand -hex 32
JWT_SECRET=

# --- 外部 API ---
# OpenAI API キー（シナリオ生成・サムネ用イラスト生成・AB タイトル生成に使用）
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx

# Anthropic (Claude) API キー
# 分析・評価・採点・判断系（シナリオ評価 / コメント分析 / 維持率分析 /
# 成功パターン分析 / CTR 予測スコアリング）で使用。
# 未設定時はルールベースのフォールバックで動作（精度は落ちる）。
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx

# YouTube Data API キー（アナリティクス取得に使用）
YOUTUBE_API_KEY=

# --- フリー素材画像コレクタ（任意・チャンネルの image_mode が collect/mix のとき使用）---
# どれか1つ以上を設定すれば動作。auto は下記の順で最初に有効なものを使う。
# 未設定なら video_generator は AI 画像生成にフォールバック。
#
# Pixabay  ── 無料・登録のみで API キー発行 (https://pixabay.com/api/docs/)
PIXABAY_API_KEY=
# Pexels   ── 無料・登録のみで API キー発行 (https://www.pexels.com/api/)
PEXELS_API_KEY=
# Unsplash ── 無料デモ枠 50req/h、クレジット表示必須 (https://unsplash.com/developers)
UNSPLASH_ACCESS_KEY=
# Google Custom Search ── 100req/日無料、CC ライセンスでフィルタ可
GOOGLE_CSE_API_KEY=
GOOGLE_CSE_ID=

# --- CORS ---
# 許可するオリジン（カンマ区切り）
# Vercelデプロイ後のURLを追加してください
CORS_ORIGINS=https://your-project.vercel.app,http://localhost:3000

# --- サーバー ---
# バックエンドポート
PORT=8000

# バインドホスト（0.0.0.0 = 外部アクセス許可）
HOST=0.0.0.0

# --- VOICEVOX ---
# VOICEVOX エンジンの URL
VOICEVOX_URL=http://localhost:50021

# --- データベース（将来用）---
# DATABASE_URL=sqlite:///./youtube_factory.db

# --- ngrok ---
# ngrok authtoken（https://dashboard.ngrok.com/get-started/your-authtoken）
NGROK_AUTHTOKEN=

# ngrok 固定ドメイン（無料プランで1つ取得可: https://dashboard.ngrok.com/domains）
# 設定すると start-mac.sh が自動で固定URLを使います（毎回URL変わらない）
# 未設定の場合はランダムURL（再起動のたびに変わる）
NGROK_DOMAIN=
```

### 7.3 コード内のその他の環境変数

```
AGENT_APP_BASE_URL AGENT_BROWSER_HEADLESS AGENT_INTERVAL_SECONDS ANTHROPIC_API_KEY APP_PASSWORD APP_PASSWORD_HASH CLIP_CHANNEL_ID CLIP_PRIVACY CORS_ORIGINS FORCE_REUPLOAD GOOGLE_ACCOUNT_EMAIL GOOGLE_CSE_API_KEY GOOGLE_CSE_ID ICLOUD_SYNC IMAGE_COLLECTOR_CONTACT JWT_SECRET LINE_NOTIFY_TOKEN LOG_FILE NEWSAPI_KEY NEWS_API_KEY OPENAI_API_KEY PDCA_BASE_URL PEXELS_API_KEY PIXABAY_API_KEY SHORT_FORCE_DUP SHORT_PRIVACY SHORT_SCENARIO_PATH SHORT_TARGET_SEC SHORT_THEME_ANGLE SHORT_THEME_TITLE SKIP_UPLOAD SLACK_WEBHOOK_URL THEME_QUEUE_CHECK_INTERVAL_MIN TIKTOK_CLIENT_KEY TIKTOK_CLIENT_SECRET TREND_SCORING_MODEL UNSPLASH_ACCESS_KEY VIDEO_OUTPUT_BASE VOICEVOX_URL YOUTUBE_API_KEY YOUTUBE_CLIENT_ID YOUTUBE_CLIENT_SECRET YTF_ICLOUD_SYNC YTF_OUTPUT_DIR 
```

---

## 8. 未コミットの変更

### 8.1 `git status --porcelain`（全文）

```
 M backend/main.py
 M backend/pipeline/auto_comment.py
 M backend/pipeline/auto_scenario/generator.py
 M backend/pipeline/auto_scenario/theme_queue.py
 M backend/pipeline/post_upload.py
 M backend/pipeline/video_generator.py
 M data/analytics/clip_state.json
 M data/analytics/retention_insights.json
 M data/analytics/success_patterns.json
 M data/channels/2ch-matome.json
 M data/channels/akashic-librarian.json
 M data/channels/clip-lab.json
 M data/channels/company-facts.json
 M data/channels/daily-science.json
 M data/channels/pokemon-lab.json
 M data/channels/scp-lab.json
 M data/channels/yokai-watch.json
 M data/pdca-memory/applied_changes.json
 M data/pdca-memory/channel_trends.json
 M data/pdca-memory/known_findings.json
 M data/reports/latest.md
 M data/reports/pdca_history.xlsx
 M data/scenarios/2ch-matome/archive/_index.json
 M data/scenarios/company-facts/archive/_index.json
 M data/scenarios/daily-science/archive/_index.json
 M data/scenarios/pokemon-lab/archive/_index.json
 M data/scenarios/scp-lab/archive/_index.json
 M data/scenarios/yokai-watch/archive/_index.json
 M data/series_links/2ch-matome.json
 M data/series_links/company-facts.json
 M data/series_links/daily-science.json
 M data/series_links/pokemon-lab.json
 M data/series_links/scp-lab.json
 M data/series_links/yokai-watch.json
?? _sync_test.txt
?? backend/pipeline/comment_bait_injector.py
?? backend/pipeline/completion_rate_optimizer.py
?? backend/pipeline/contrast_amplifier.py
?? backend/pipeline/cross_channel_bridge.py
?? backend/pipeline/cta_rotator.py
?? backend/pipeline/curiosity_gap_enforcer.py
?? backend/pipeline/emotional_polarity_alternator.py
?? backend/pipeline/hashtag_optimizer.py
?? backend/pipeline/hook_ab_selector.py
?? backend/pipeline/mute_safe_checker.py
?? backend/pipeline/narration_video.py
?? backend/pipeline/originality_guard.py
?? backend/pipeline/pattern_interrupt_injector.py
?? backend/pipeline/power_word_amplifier.py
?? backend/pipeline/replay_loop_seeder.py
?? backend/pipeline/retention_feedback_loop.py
?? backend/pipeline/round6_enhancer.py
?? backend/pipeline/round7_enhancer.py
?? backend/pipeline/round8_enhancer.py
?? backend/pipeline/scenario_validator.py
?? backend/pipeline/seasonal_boost.py
?? backend/pipeline/series_counter.py
?? backend/pipeline/shorts_length_guard.py
?? backend/pipeline/subscribe_trigger_optimizer.py
?? backend/pipeline/swipe_stop_injector.py
?? backend/pipeline/title_emoji_injector.py
?? backend/pipeline/viral_score_gate.py
?? backend/tests/test_growth_v3_features.py
?? backend/tests/test_narration_video.py
?? backend/tests/test_round7_features.py
?? backend/tests/test_round8_features.py
?? data/cta_history/
?? data/pending_comments.json
?? data/reports/2026-08-18/
?? data/reports/handoff_2026-08-18.md
?? "data/scenarios/2ch-matome/PC\343\203\221\343\203\274\343\203\204\345\210\260\347\235\200\346\231\202\343\201\252\343\201\234\347\256\261\343\201\240\343\201\221\345\205\210\343\201\253\345\261\212\343\201\217\343\201\256\343\201\213.json"
?? data/scenarios/2ch-matome/archive/2ch-matome_20260819_073257_scenario.md
?? data/scenarios/2ch-matome/archive/2ch-matome_20260819_093300_scenario.md
?? "data/scenarios/2ch-matome/\343\201\252\343\201\234\343\202\261\343\203\263\343\202\277\343\203\203\343\202\255\343\203\274\346\234\210\350\246\213\343\201\2573\347\247\222\343\201\247\347\247\213\343\201\256\347\265\246\346\226\231\346\227\245\343\201\253\343\201\252\343\202\213\343\201\256\343\201\213\351\243\237\343\201\271\343\201\237\346\204\237\346\203\263\343\201\202\343\201\222\343\201\246\343\201\221w.json"
?? "data/scenarios/company-facts/ASUS\343\201\256\345\271\264\345\217\216\343\201\214\346\234\254\345\275\223\343\201\257\346\260\227\343\201\253\343\201\252\343\202\213_\343\202\262\343\203\274\343\203\237\343\203\263\343\202\260\345\243\262\344\270\212\343\201\214\347\264\2044800\345\204\204\345\206\206.json"
?? data/scenarios/company-facts/archive/company-facts_20260819_071511_scenario.md
?? data/scenarios/daily-science/archive/daily-science_20260819_081745_scenario.md
?? "data/scenarios/daily-science/\343\201\252\343\201\234\346\255\243\345\272\247\343\202\222\345\264\251\343\201\227\343\201\237\347\236\254\351\226\223\343\201\240\343\201\221\343\203\223\343\203\252\343\203\223\343\203\252\343\201\231\343\202\213\343\201\256\343\201\21399\343\201\214\347\237\245\343\202\211\343\201\252\343\201\20430\347\247\222\343\201\256\346\255\243\344\275\223.json"
?? data/scenarios/pokemon-lab/archive/pokemon-lab_20260819_074759_scenario.md
?? "data/scenarios/pokemon-lab/\343\202\254\343\203\226\343\203\252\343\202\242\343\202\271\343\201\250\343\203\234\343\203\274\343\203\236\343\203\263\343\203\200\347\264\240\346\227\251\343\201\2251\343\201\247\343\201\251\343\201\243\343\201\241\343\201\214\345\213\235\343\201\244\345\220\233\343\201\257\346\260\227\343\201\245\343\201\221\343\202\213\343\201\213.json"
?? data/scenarios/scp-lab/archive/scp-lab_20260819_091824_scenario.md
?? "data/scenarios/scp-lab/\350\247\246\343\202\214\343\201\237\345\205\250\345\223\241\343\201\214\347\254\221\343\201\206\347\262\230\344\275\223\343\201\252\343\201\234Safe\343\201\252\343\201\256\343\201\213.json"
?? data/scenarios/yokai-watch/archive/yokai-watch_20260819_084812_scenario.md
?? "data/scenarios/yokai-watch/\343\201\254\343\202\211\343\202\212\343\201\262\343\202\207\343\202\223\343\201\256\346\255\243\344\275\223\343\201\214\346\200\226\343\201\231\343\201\216\343\202\213_\343\201\252\343\201\234\343\201\202\343\201\252\343\201\237\343\201\256\345\256\266\343\201\253\345\213\235\346\211\213\343\201\253\344\270\212\343\201\214\343\202\213\343\201\256\343\201\213.json"
?? data/series_counter/
?? data/trends/google_japan_2026-08-19.json
?? data/trends/youtube_JP_27_28_2026-08-19.json
?? naze_bijin_wa_tokusuru_noka.mp3
?? naze_bijin_wa_tokusuru_noka.wav
?? naze_bijin_wa_tokusuru_noka_small.mp3
?? restart_backend.command
```

### 8.2 `git diff --stat`（追跡ファイルの変更）

```
 backend/main.py                                  |  45 ++
 backend/pipeline/auto_comment.py                 | 151 +++++-
 backend/pipeline/auto_scenario/generator.py      | 159 +++++-
 backend/pipeline/auto_scenario/theme_queue.py    |  39 ++
 backend/pipeline/post_upload.py                  |  23 +
 backend/pipeline/video_generator.py              |  31 +-
 data/analytics/clip_state.json                   |  16 +
 data/analytics/retention_insights.json           | 609 +++++++++--------------
 data/analytics/success_patterns.json             | 257 +++++-----
 data/channels/2ch-matome.json                    |   6 +-
 data/channels/akashic-librarian.json             |   2 +
 data/channels/clip-lab.json                      |  19 +-
 data/channels/company-facts.json                 |  10 +-
 data/channels/daily-science.json                 |  40 +-
 data/channels/pokemon-lab.json                   |  33 +-
 data/channels/scp-lab.json                       |  33 +-
 data/channels/yokai-watch.json                   |  33 +-
 data/pdca-memory/applied_changes.json            |  83 +++
 data/pdca-memory/channel_trends.json             |  50 ++
 data/pdca-memory/known_findings.json             |  30 ++
 data/reports/latest.md                           | 171 ++++---
 data/reports/pdca_history.xlsx                   | Bin 16619 -> 16901 bytes
 data/scenarios/2ch-matome/archive/_index.json    |  28 ++
 data/scenarios/company-facts/archive/_index.json |  14 +
 data/scenarios/daily-science/archive/_index.json |  14 +
 data/scenarios/pokemon-lab/archive/_index.json   |  14 +
 data/scenarios/scp-lab/archive/_index.json       |  14 +
 data/scenarios/yokai-watch/archive/_index.json   |  14 +
 data/series_links/2ch-matome.json                |  14 +
 data/series_links/company-facts.json             |   7 +
 data/series_links/daily-science.json             |   7 +
 data/series_links/pokemon-lab.json               |   7 +
 data/series_links/scp-lab.json                   |   7 +
 data/series_links/yokai-watch.json               |   7 +
 34 files changed, 1351 insertions(+), 636 deletions(-)
```

### 8.3 変更内容の概要

**コード変更（6ファイル / +448行）:**

| ファイル | 変更 | 内容 |
|---|---|---|
| `backend/main.py` | +45 | Round 6 API（`/api/round6/cta-history`, `/viral-score`, `/mute-check`）の追加 |
| `backend/pipeline/auto_comment.py` | +151/-? | 予約公開待ちの保留コメントを `data/pending_comments.json` に永続化 + 15分ごと flush |
| `backend/pipeline/auto_scenario/generator.py` | +159 | Round 6/7/8 エンハンサ・scenario_validator・series_counter・seasonal_boost の呼び出し組み込み |
| `backend/pipeline/auto_scenario/theme_queue.py` | +39 | 補充ロジックの調整 |
| `backend/pipeline/post_upload.py` | +23 | series_counter 確定 + CTA ローテーション履歴の記録を追加 |
| `backend/pipeline/video_generator.py` | +31/-? | hook_caption・scenario_meta 周りの受け渡し |

**未追跡の新規モジュール（57件の `??`）** — 主に Round 6/7/8 の 18 モジュール + 補助モジュール:

```
backend/pipeline/comment_bait_injector.py
backend/pipeline/completion_rate_optimizer.py
backend/pipeline/contrast_amplifier.py
backend/pipeline/cross_channel_bridge.py
backend/pipeline/cta_rotator.py
backend/pipeline/curiosity_gap_enforcer.py
backend/pipeline/emotional_polarity_alternator.py
backend/pipeline/hashtag_optimizer.py
backend/pipeline/hook_ab_selector.py
backend/pipeline/mute_safe_checker.py
backend/pipeline/narration_video.py
backend/pipeline/originality_guard.py
backend/pipeline/pattern_interrupt_injector.py
backend/pipeline/power_word_amplifier.py
backend/pipeline/replay_loop_seeder.py
backend/pipeline/retention_feedback_loop.py
backend/pipeline/round6_enhancer.py
backend/pipeline/round7_enhancer.py
backend/pipeline/round8_enhancer.py
backend/pipeline/scenario_validator.py
backend/pipeline/seasonal_boost.py
backend/pipeline/series_counter.py
backend/pipeline/shorts_length_guard.py
backend/pipeline/subscribe_trigger_optimizer.py
backend/pipeline/swipe_stop_injector.py
backend/pipeline/title_emoji_injector.py
backend/pipeline/viral_score_gate.py
```

```
backend/tests/test_growth_v3_features.py
backend/tests/test_narration_video.py
backend/tests/test_round7_features.py
backend/tests/test_round8_features.py
```

その他の未追跡: `data/cta_history/`, `data/series_counter/`, `data/pending_comments.json`, `data/reports/2026-08-18/`, `data/reports/handoff_2026-08-18.md`, 各chの新規シナリオJSON/アーカイブmd, `data/trends/*_2026-08-19.json`, `naze_bijin_wa_tokusuru_noka.{mp3,wav}`, `restart_backend.command`, `_sync_test.txt`。

**データファイルの変更**は autopilot / PDCA の通常運転による自動更新（channel JSON のテーマキュー消費、series_links、analytics、pdca-memory、レポート）。

### 8.4 コード差分の全文

```diff
diff --git a/backend/main.py b/backend/main.py
index 8f66d60..5de4aa5 100644
--- a/backend/main.py
+++ b/backend/main.py
@@ -1598,6 +1598,51 @@ def _start_theme_queue_scheduler():
     print(f"🕒 ThemeQueue scheduler started (every {THEME_QUEUE_CHECK_INTERVAL_MIN} min)")
 
 
+# ── Round 6 API ──
+
+@app.get("/api/round6/cta-history/{channel_id}")
+async def round6_cta_history(channel_id: str):
+    """CTA ローテーション履歴を取得する。"""
+    try:
+        from pipeline.cta_rotator import _load_history, _recent_styles
+        return {
+            "channel_id": channel_id,
+            "history": _load_history(channel_id),
+            "recent_styles": _recent_styles(channel_id, n=10),
+        }
+    except Exception as e:
+        raise HTTPException(status_code=500, detail=str(e))
+
+
+@app.post("/api/round6/viral-score")
+async def round6_viral_score(request: Request):
+    """シナリオのバイラルスコアを計算する（プレビュー用）。"""
+    body = await request.json()
+    try:
+        from pipeline.viral_score_gate import score_viral_potential
+        return score_viral_potential(
+            body.get("short_scenario", []),
+            title=body.get("title", ""),
+            channel_id=body.get("channel_id", ""),
+        )
+    except Exception as e:
+        raise HTTPException(status_code=500, detail=str(e))
+
+
+@app.post("/api/round6/mute-check")
+async def round6_mute_check(request: Request):
+    """シナリオのミュート安全性をチェックする（プレビュー用）。"""
+    body = await request.json()
+    try:
+        from pipeline.mute_safe_checker import check_mute_safe
+        return check_mute_safe(
+            body.get("short_scenario", []),
+            channel_id=body.get("channel_id", ""),
+        )
+    except Exception as e:
+        raise HTTPException(status_code=500, detail=str(e))
+
+
 @app.get("/health")
 async def health():
     """Health check endpoint.
diff --git a/backend/pipeline/auto_comment.py b/backend/pipeline/auto_comment.py
index 1c3b871..46900bc 100644
--- a/backend/pipeline/auto_comment.py
+++ b/backend/pipeline/auto_comment.py
@@ -85,6 +85,111 @@ def is_enabled(channel_id: str, channel_dict: Optional[Dict[str, Any]] = None) -
 
 DEFAULT_QUESTION = "これ知ってた？コメントで教えて！"
 
+# チャンネル別のエンゲージメント質問テンプレート。
+# 競合分析の結果、具体的な二択/参加型の質問がコメント率を2〜3倍にする。
+CHANNEL_QUESTIONS: Dict[str, List[str]] = {
+    "daily-science": [
+        "これ知ってた？知ってた人は『知ってた』ってコメントして！",
+        "他にも気になる日常の謎があったらコメントで教えて！",
+        "これ友達に話したくなった？ → 保存しとくと便利だよ！",
+    ],
+    "scp-lab": [
+        "このSCPのオブジェクトクラス、何だと思う？コメントで予想してみて！",
+        "一番怖いと思ったSCPをコメントで教えて！",
+        "次に解説してほしいSCPナンバーがあったらコメントして！",
+    ],
+    "2ch-matome": [
+        "お前らならどうする？コメントで教えてくれw",
+        "似たような経験ある奴いる？w コメントで聞かせてくれ！",
+        "正直ワロタって人は『草』ってコメントしてくれw",
+    ],
+    "company-facts": [
+        "この企業で働いたことある人いますか？コメントで教えてください！",
+        "もっとヤバい企業知ってたらコメントで教えて！",
+        "次にどの企業を取り上げてほしい？コメントで教えて！",
+    ],
+    "pokemon-lab": [
+        "この事実知ってた？知ってた人はコメントで教えて！",
+        "他にも知りたいポケモンの裏設定があったらコメントして！",
+        "推しポケモンをコメントで教えて！",
+    ],
+    "yokai-watch": [
+        "この妖怪、あなたの地域にも伝承ある？コメントで教えて！",
+        "一番怖いと思った妖怪をコメントで教えて！",
+        "次に調査してほしい妖怪・都市伝説があったらコメントして！",
+    ],
+    "akashic-librarian": [
+        "この話、どう解釈する？コメントで教えてほしい。",
+        "次に開くべき記録があったらコメントで教えて。",
+    ],
+}
+
+# チャンネル別の議論誘発コメント。
+# 競合分析で「あえて議論を呼ぶコメントがエンゲージメントを2〜3倍にする」ことが確認された。
+# 直接的な誤情報ではなく、「あなたはどっち派？」型の二択/意見募集で安全に議論を誘発する。
+CHANNEL_DEBATE_COMMENTS: Dict[str, List[str]] = {
+    "daily-science": [
+        "個人的に一番驚いたのはこの数字…みんなは予想できた？",
+        "これ、周りの人に話したら何人知ってるか試してみて！",
+        "朝型の人と夜型の人で体験が違うらしい。あなたはどっち？",
+    ],
+    "scp-lab": [
+        "このSCP、SafeとEuclidどっちだと思う？理由もコメントして",
+        "正直このSCPより怖いやつ知ってる人いたらコメントで教えて…",
+        "もし自分がDクラスに配属されたら、このSCPの実験担当できる？",
+    ],
+    "2ch-matome": [
+        "正直>>1が悪いと思うやつ、手あげてみてくれw",
+        "似たような経験あるやつ絶対おるやろ。正直に言えやw",
+        "ワイはこのスレ、嘘やと思うんやけどお前らはどう思う？w",
+    ],
+    "company-facts": [
+        "この年収、高いと思う？低いと思う？正直にコメントで教えて",
+        "実際にこの企業で働いてる人・働いてた人いたらリアルを教えて！",
+        "転職するならこの企業アリ？ナシ？理由も聞きたい",
+    ],
+    "pokemon-lab": [
+        "このポケモンの種族値、予想できた人いる？コメントで教えて！",
+        "ぶっちゃけこのポケモン、パーティに入れる？入れない？",
+        "この設定知ってた人と知らなかった人、どっちが多いか気になる！",
+    ],
+    "yokai-watch": [
+        "この妖怪の元ネタ、知ってた人いる？正直にコメントして！",
+        "ゲーム版と原典、どっちの姿が好き？コメントで教えて",
+        "あなたの地域にも似た伝承ない？知ってたら教えて！",
+    ],
+    "akashic-librarian": [
+        "この記録、あなたはどう解釈する？",
+        "似た体験をしたことがある人がいたら、聞かせてほしい。",
+    ],
+}
+
+
+def build_debate_comment_text(
+    channel_id: str,
+    *,
+    title: str = "",
+    channel_dict: Optional[Dict[str, Any]] = None,
+) -> str:
+    """議論誘発コメントを組み立てる。2つ目のコメントとして投稿する。"""
+    import random
+    pool = CHANNEL_DEBATE_COMMENTS.get(channel_id, [])
+    if not pool:
+        return ""
+    question = random.choice(pool)
+    return f"🔥 {question}"
+
+
+def _pick_question(channel_id: str, cfg: Dict[str, Any]) -> str:
+    """チャンネル別の質問をランダムに選択。設定値があればそちら優先。"""
+    custom = cfg.get("question")
+    if custom:
+        return str(custom).strip()
+
+    import random
+    pool = CHANNEL_QUESTIONS.get(channel_id, [DEFAULT_QUESTION])
+    return random.choice(pool) if pool else DEFAULT_QUESTION
+
 
 def build_comment_text(
     channel_id: str,
@@ -106,7 +211,7 @@ def build_comment_text(
 
     sub_url = _desc_blocks.subscribe_url(channel_id) or ""
     ch_url = _desc_blocks.channel_url(channel_id) or ""
-    question = str(cfg.get("question") or DEFAULT_QUESTION).strip()
+    question = _pick_question(channel_id, cfg)
 
     template = cfg.get("template")
     if isinstance(template, str) and template.strip():
@@ -228,27 +333,30 @@ def enqueue(
     text: str,
     *,
     due_at: Optional[str] = None,
+    debate_text: str = "",
 ) -> None:
     """公開時刻まで待ってから投稿するコメントを保留キューに積む。
 
     Args:
         due_at: RFC3339 UTC ("2026-08-19T10:00:00Z")。未指定なら即時対象。
+        debate_text: 議論誘発コメント。メインコメント投稿成功後に続けて投稿する。
     """
     with _lock:
         items = _read_pending()
         # 同じ動画への二重登録を防ぐ
         if any(i.get("video_id") == video_id for i in items):
             return
-        items.append(
-            {
-                "channel_id": channel_id,
-                "video_id": video_id,
-                "text": text,
-                "due_at": due_at,
-                "attempts": 0,
-                "queued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
-            }
-        )
+        entry: Dict[str, Any] = {
+            "channel_id": channel_id,
+            "video_id": video_id,
+            "text": text,
+            "due_at": due_at,
+            "attempts": 0,
+            "queued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
+        }
+        if debate_text:
+            entry["debate_text"] = debate_text
+        items.append(entry)
         _write_pending(items)
     print(f"🗒️ auto_comment queued: {channel_id}/{video_id} (due {due_at or 'now'})")
 
@@ -290,6 +398,16 @@ def flush_pending() -> Dict[str, Any]:
         if res.get("ok"):
             posted += 1
             print(f"💬 auto_comment posted: {item.get('channel_id')}/{item.get('video_id')}")
+            # 議論誘発コメントも続けて投稿
+            debate = (item.get("debate_text") or "").strip()
+            if debate:
+                import time
+                time.sleep(3)  # YouTube API のレート制限回避
+                post_comment(
+                    str(item.get("channel_id") or ""),
+                    str(item.get("video_id") or ""),
+                    debate,
+                )
             continue
 
         item["attempts"] = int(item.get("attempts") or 0) + 1
@@ -348,17 +466,24 @@ def post_for_video(
     if not text:
         return {"ok": False, "skipped": "empty_text"}
 
+    debate_text = build_debate_comment_text(channel_id, title=title, channel_dict=cd)
+
     due = _parse_due(publish_at)
     if due is not None and due.timestamp() > datetime.now(timezone.utc).timestamp():
-        enqueue(channel_id, video_id, text, due_at=publish_at)
+        enqueue(channel_id, video_id, text, due_at=publish_at, debate_text=debate_text)
         return {"ok": True, "queued": True, "due_at": publish_at}
 
     res = post_comment(channel_id, video_id, text)
     if res.get("ok"):
         print(f"💬 auto_comment posted: {channel_id}/{video_id}")
+        # 2つ目のコメント（議論誘発）を投稿
+        if debate_text:
+            import time
+            time.sleep(3)  # YouTube API のレート制限回避
+            post_comment(channel_id, video_id, debate_text)
         return res
     if res.get("retryable"):
-        enqueue(channel_id, video_id, text, due_at=None)
+        enqueue(channel_id, video_id, text, due_at=None, debate_text=debate_text)
         return {"ok": True, "queued": True, "error": res.get("error")}
     print(f"⚠️ auto_comment failed {channel_id}/{video_id}: {res.get('error')}")
     return res
diff --git a/backend/pipeline/auto_scenario/generator.py b/backend/pipeline/auto_scenario/generator.py
index 8d3bcbd..1d6e677 100644
--- a/backend/pipeline/auto_scenario/generator.py
+++ b/backend/pipeline/auto_scenario/generator.py
@@ -237,6 +237,7 @@ _TELOP_PACING_RULE_SHORT = """# テンポ・ルール(完視聴率対策・絶
 # 逆に「ご視聴ありがとうございました」で閉じると、そこで確実に離脱する。
 _LOOP_RULE_SHORT = """# ループ構成ルール(再視聴率対策・絶対厳守)
 - ショートは**最後まで見ると自動で1行目に巻き戻る**。この一周を「もう一回見たい」に変えるのが目的。
+  **ループ再生率100%超（2周以上視聴）はYouTubeアルゴリズムへの最強シグナル。**
 - ✅ **最後の内容行(オチ)は1行目に意味がつながるように書く**。視聴者が1行目を聞き直したとき、
   「あ、そういう意味だったのか」と**意味が変わって聞こえる**状態を作る。
   - 伏線回収型: 1行目の問いに対して、オチで「答えの半分」だけ返す（残りは1行目に戻ると分かる）。
@@ -244,8 +245,15 @@ _LOOP_RULE_SHORT = """# ループ構成ルール(再視聴率対策・絶対厳
   - 問い返し型: オチを「じゃあ〇〇は?」で閉じ、1行目の問いに戻る輪を作る。
 - ✅ **1行目は「途中から聞いても成立する」書き方にする**。巻き戻ってきた視聴者が
   文脈なしでもう一周できるよう、冒頭で前の行を受ける指示語(「それは」「この」)を使わない。
+- ✅ **シームレスループテクニック**: 最終行の末尾を文法的に宙吊りにし、1行目の冒頭に自然に
+  接続させる。例: 最終行「…だからこそ、」→ 1行目「〇〇って不思議だよね」が繋がって聞こえる。
+  音声の切れ目を感じさせないことで、視聴者はループに気づかず2周目に入る。
+- ✅ **2周目の気づき設計**: 1行目に「ダブルミーニング」を仕込む。初見では素直に読めるが、
+  オチを知ってから聞くと別の意味に取れるフレーズを使う。これが2周目を見る動機になる。
 - ❌ **終わった感の出る締めは禁止**: 「以上です」「ご視聴ありがとうございました」
   「まとめると」「いかがでしたか」は1文字でも入れたら不合格。そこで視聴者は確実に離れる。
+- ❌ **ループを切るフレーズ禁止**: 「最後に」「結論は」「今日のまとめ」「というわけで」も
+  NG。これらが出た瞬間に視聴者は「終わり」を察知してスワイプする。
 - ※ 最終行の登録CTAは上の構成ルール通り必ず入れる。ただし**話を終わらせず**、
   オチの余韻に乗せたまま1行に収めること(CTAで話を締めくくらない)。
 """
@@ -2095,6 +2103,32 @@ class ScenarioGenerator:
             prompt = prompt + "\n\n" + competitor_addendum
             print("  🥷 Applying competitor intelligence (title patterns / hot topics / gap themes)")
 
+        # Phase S: 季節ブースト — 時期に合ったテーマ角度をプロンプトに追加
+        try:
+            from pipeline.seasonal_boost import get_seasonal_prompt_addendum
+            _seasonal_add = get_seasonal_prompt_addendum(channel.id)
+            if _seasonal_add:
+                prompt = prompt + "\n\n" + _seasonal_add
+                print(f"  🌸 Applying seasonal boost for {channel.id}")
+        except Exception as e:
+            print(f"  ⚠️ seasonal_boost failed: {e}")
+
+        # Phase T: トレンドテーマの場合、タイトルと冒頭に旬のワードを織り込む指示を注入。
+        # トレンドに乗ったコンテンツは初動 1〜3 時間のリーチが通常の 2〜3 倍になる（競合分析）。
+        if theme.get("is_trending") and theme.get("trend_match"):
+            trend_kw = theme["trend_match"]
+            trend_addendum = (
+                f"\n\n# トレンド最適化指示（このテーマはトレンドに乗っている）\n"
+                f"- 現在「{trend_kw}」がトレンド入りしている。このキーワードに関連する切り口で書く。\n"
+                f"- **タイトルに「{trend_kw}」またはその関連ワードを自然に含める**（検索流入の最大化）。\n"
+                f"- 冒頭1行目で「今話題の」「今ちょうど」「最近〇〇で話題になってる」のような\n"
+                f"  旬のシグナルを1つ入れる。ただし不自然に詰め込まず、チャンネルのトーンを守る。\n"
+                f"- サムネの hook_lines にもトレンドワードを反映する（検索＋おすすめ表示の両方に効く）。\n"
+                f"- トレンドは24〜48時間で冷めるため、鮮度の高い切り口を最優先する。\n"
+            )
+            prompt = prompt + trend_addendum
+            print(f"  🔥 Applying trend optimization: '{trend_kw}' (trend_score={theme.get('trend_score')})")
+
         # theme_override（run_*.py / batch / autopilot が題材を明示指定）時は題材を固定する。
         # 上記 analytics / competitor addendum は「過去に伸びた題材（例:SCP-5000/173）を再現せよ」と
         # 具体指示するため、1行のテーマ指定を上書きして別の題材を書かせてしまう（題材ハイジャック）。
@@ -2331,8 +2365,117 @@ class ScenarioGenerator:
             if short_avg < 30:
                 print(f"  ⚠️ short_scenario: {len(short_lines_data)} lines, {short_total} chars, avg {short_avg:.1f}/line — under 30/line, may be under 30s")
 
+        # Phase V: シナリオ構造バリデーション（フック・CTA・禁止語の検証）
+        if short_lines_data:
+            try:
+                from pipeline.scenario_validator import guard as _scenario_guard
+                _short_texts = [
+                    (e.get("text", "") if isinstance(e, dict) else str(e))
+                    for e in short_lines_data
+                ]
+                _ch_raw = {}
+                try:
+                    _ch_raw = channel._raw or {}
+                except AttributeError:
+                    pass
+                _scenario_guard(
+                    _short_texts,
+                    channel_id=channel.id,
+                    channel_dict=_ch_raw,
+                    strict=False,
+                )
+            except Exception as e:
+                print(f"  ⚠️ scenario_validator failed: {e}")
+
+        # Phase R6: Round 6 生成後最適化パイプライン
+        # (Hook A/B, Swipe-Stop, CTA Rotation, Cross-Channel Bridge,
+        #  Mute-Safe Check, Viral Score Gate)
+        if short_lines_data:
+            try:
+                from pipeline.round6_enhancer import enhance as _r6_enhance
+                _ch_raw_r6 = {}
+                try:
+                    _ch_raw_r6 = channel._raw or {}
+                except AttributeError:
+                    pass
+                _r6_result = _r6_enhance(
+                    short_lines_data,
+                    title=scenario_data.get("title", theme.get("title", "")),
+                    channel_id=channel.id,
+                    channel_dict=_ch_raw_r6,
+                    series_name=(scenario_data.get("series_name") or ""),
+                    api_key=self.api_key,
+                )
+                scenario_data["round6"] = _r6_result
+            except Exception as e:
+                print(f"  ⚠️ Round6 enhancer failed: {e}")
+
+        # Phase R7: Round 7 完走率 & リプレイ最大化パイプライン
+        # (Completion Rate Optimizer, Replay Loop Seeder, Power Word Amplifier,
+        #  Retention Feedback Loop, Originality Guard, Title Emoji Injector)
+        if short_lines_data:
+            try:
+                from pipeline.round7_enhancer import enhance as _r7_enhance
+                _ch_raw_r7 = {}
+                try:
+                    _ch_raw_r7 = channel._raw or {}
+                except AttributeError:
+                    pass
+                _r7_result = _r7_enhance(
+                    short_lines_data,
+                    title=scenario_data.get("title", theme.get("title", "")),
+                    channel_id=channel.id,
+                    channel_dict=_ch_raw_r7,
+                )
+                scenario_data["round7"] = _r7_result
+                # Round 7 の絵文字注入タイトルを反映
+                if _r7_result.get("enhanced_title"):
+                    scenario_data["title"] = _r7_result["enhanced_title"]
+            except Exception as e:
+                print(f"  ⚠️ Round7 enhancer failed: {e}")
+
+        # Phase R8: Round 8 エンゲージメント & 登録者最大化パイプライン
+        # (Curiosity Gap Enforcer, Comment Bait Injector,
+        #  Emotional Polarity Alternator, Pattern Interrupt Injector,
+        #  Subscribe Trigger Optimizer, Contrast Amplifier)
+        if short_lines_data:
+            try:
+                from pipeline.round8_enhancer import enhance as _r8_enhance
+                _ch_raw_r8 = {}
+                try:
+                    _ch_raw_r8 = channel._raw or {}
+                except AttributeError:
+                    pass
+                _r8_result = _r8_enhance(
+                    short_lines_data,
+                    title=scenario_data.get("title", theme.get("title", "")),
+                    channel_id=channel.id,
+                    channel_dict=_ch_raw_r8,
+                )
+                scenario_data["round8"] = _r8_result
+            except Exception as e:
+                print(f"  ⚠️ Round8 enhancer failed: {e}")
+
+        # Phase N: シリーズ通し番号をタイトルに付与
+        _result_title = scenario_data.get("title", theme["title"])
+        try:
+            from pipeline.series_counter import apply_series_number
+            _ch_raw_n = {}
+            try:
+                _ch_raw_n = channel._raw or {}
+            except AttributeError:
+                pass
+            _result_title = apply_series_number(
+                _result_title,
+                channel.id,
+                channel_dict=_ch_raw_n,
+                is_short=bool(scenario_data.get("short_scenario")),
+            )
+        except Exception as e:
+            print(f"  ⚠️ series_counter failed: {e}")
+
         result = {
-            "title": scenario_data.get("title", theme["title"]),
+            "title": _result_title,
             "theme": theme,
             "short_scenario": scenario_data.get("short_scenario", []),
             "full_scenario": scenario_data.get("full_scenario", []),
@@ -2344,6 +2487,9 @@ class ScenarioGenerator:
             "applied_competitor_feedback": applied_competitor,
             "generated_by": chosen_provider,
             "compete": compete_meta,
+            "round6": scenario_data.get("round6", {}),
+            "round7": scenario_data.get("round7", {}),
+            "round8": scenario_data.get("round8", {}),
         }
 
         # Phase C: AB テストでタイトル＆サムネを最適化（オプション）
@@ -2689,6 +2835,16 @@ class ScenarioGenerator:
 
         theme_priority_block = self._theme_priority_block(channel, count)
 
+        # Phase S: テーマ提案にも季節ブーストを注入
+        seasonal_block = ""
+        try:
+            from pipeline.seasonal_boost import get_seasonal_prompt_addendum
+            seasonal_block = get_seasonal_prompt_addendum(channel.id) or ""
+            if seasonal_block:
+                print(f"  🌸 Injecting seasonal boost into theme suggestions")
+        except Exception as e:
+            print(f"  ⚠️ seasonal_boost in suggest_themes failed: {e}")
+
         prompt = f"""YouTube動画テーマを{count}個提案。JSON配列のみ。
 
 # チャンネル: {channel.name} / {channel.concept} / {channel.style} / {channel.content_policy.get("tone","friendly")}
@@ -2724,6 +2880,7 @@ class ScenarioGenerator:
 - 「競合がまだカバーしていない可能性のあるテーマ」リストの内容は優先的に提案して構わない。
 {competitor_block}
 {trend_block}
+{seasonal_block}
 """
 
         messages = [
diff --git a/backend/pipeline/auto_scenario/theme_queue.py b/backend/pipeline/auto_scenario/theme_queue.py
index 16ec199..8768265 100644
--- a/backend/pipeline/auto_scenario/theme_queue.py
+++ b/backend/pipeline/auto_scenario/theme_queue.py
@@ -262,6 +262,41 @@ def reorder(channel_id: str, ordered_ids: List[str]) -> Dict[str, Any]:
     return get_status(channel_id)
 
 
+def prioritize_trending(channel_id: str) -> Dict[str, Any]:
+    """トレンドテーマをキュー先頭に移動する。
+
+    競合分析の結果、トレンドに乗ったコンテンツは初動 1〜3 時間の
+    リーチが通常の 2〜3 倍になる。FIFO では高スコアのトレンドテーマが
+    非トレンドの後ろで待たされるため、トレンドスコア順にソートする。
+
+    ソート順:
+    1. is_trending=True のアイテム（trend_score 降順）
+    2. is_trending=False のアイテム（元の順序を維持）
+
+    replenish 完了時に自動で呼ばれる。
+    """
+    with _lock_for(channel_id):
+        q = load_queue(channel_id)
+        items = q.get("items", [])
+        if not items:
+            return get_status(channel_id)
+
+        trending = [it for it in items if it.get("is_trending")]
+        non_trending = [it for it in items if not it.get("is_trending")]
+
+        # trend_score 降順（None は 0 扱い）
+        trending.sort(key=lambda x: float(x.get("trend_score") or 0), reverse=True)
+
+        q["items"] = trending + non_trending
+        save_queue(channel_id, q)
+        if trending:
+            print(
+                f"  🔥 ThemeQueue [{channel_id}] prioritized {len(trending)} trending themes "
+                f"(top: {trending[0].get('title')}, score={trending[0].get('trend_score')})"
+            )
+    return get_status(channel_id)
+
+
 # ---------------------------------------------------------------------------
 # Replenish (LLM-driven)
 # ---------------------------------------------------------------------------
@@ -350,6 +385,10 @@ def replenish(
             q["last_error"] = None
         save_queue(channel_id, q)
 
+    # トレンドテーマを先頭に移動（補充直後に並べ替え）
+    if added:
+        prioritize_trending(channel_id)
+
     status = get_status(channel_id)
     status["added"] = added
     if err and not added:
diff --git a/backend/pipeline/post_upload.py b/backend/pipeline/post_upload.py
index e25ef03..8e0e933 100644
--- a/backend/pipeline/post_upload.py
+++ b/backend/pipeline/post_upload.py
@@ -71,6 +71,29 @@ def run(
         out["series_links"] = {"ok": False, "error": str(e)}
         print(f"⚠️ post_upload series_links failed [{channel_id}] {video_id}: {e}")
 
+    # Phase N: シリーズ通し番号カウンタを確定（アップロード成功後）
+    try:
+        from pipeline.series_counter import confirm_upload, get_series_prefix
+        if get_series_prefix(channel_id, cd):
+            new_count = confirm_upload(channel_id)
+            out["series_counter"] = {"ok": True, "new_count": new_count}
+            print(f"  🔢 Series counter advanced to #{new_count} [{channel_id}]")
+    except Exception as e:
+        out["series_counter"] = {"ok": False, "error": str(e)}
+        print(f"⚠️ post_upload series_counter failed [{channel_id}]: {e}")
+
+    # Phase R6: CTA ローテーション履歴の記録（Round 6）
+    # generate() 時点で cta_rotator が履歴を書いているため、ここでは
+    # アップロード成功を確認した上で追加の後処理が必要な場合のみ動く。
+    # 現時点では generate() 側で完結しているため、ログのみ。
+    try:
+        from pipeline.cta_rotator import _recent_styles
+        recent = _recent_styles(channel_id, n=3)
+        if recent:
+            out["cta_rotation"] = {"ok": True, "recent_styles": recent}
+    except Exception:
+        pass  # CTA ローテーションは必須ではない
+
     return out
 
 
diff --git a/backend/pipeline/video_generator.py b/backend/pipeline/video_generator.py
index ed2430a..b839e4c 100644
--- a/backend/pipeline/video_generator.py
+++ b/backend/pipeline/video_generator.py
@@ -5018,10 +5018,25 @@ def _build_description_template(channel_dict, title, channel_concept):
     main_hashtags = tmpl.get("main_hashtags") or default_hashtag_str
     short_hashtags = tmpl.get("short_hashtags") or f"#shorts {default_hashtag_str}"
 
-    # YouTube はハッシュタグが 15 個を超えると全て無視し、表示されるのは先頭3個だけ。
-    # 設定側が多めに書いていても 3〜5 個に正規化してから使う。
-    main_hashtags = _desc_blocks.normalize_hashtags(main_hashtags)
-    short_hashtags = _desc_blocks.normalize_hashtags(short_hashtags, required=["shorts"])
+    # 動的ハッシュタグ最適化: タイトルとトレンドに基づいてハッシュタグを生成。
+    # hashtag_optimizer が利用可能で channel_id があれば動的版を使い、
+    # なければ従来の静的正規化にフォールバックする。
+    _channel_id = (channel_dict or {}).get("id") or ""
+    try:
+        from pipeline import hashtag_optimizer as _ho
+        if _channel_id:
+            main_hashtags = _ho.optimize_hashtags(_channel_id, title, is_short=False)
+            short_hashtags = "#shorts " + _ho.optimize_hashtags(
+                _channel_id, title, is_short=True, max_tags=4
+            )
+        else:
+            raise ImportError("no channel_id")
+    except Exception:
+        # フォールバック: 従来の静的正規化
+        # YouTube はハッシュタグが 15 個を超えると全て無視し、表示されるのは先頭3個だけ。
+        # 設定側が多めに書いていても 3〜5 個に正規化してから使う。
+        main_hashtags = _desc_blocks.normalize_hashtags(main_hashtags)
+        short_hashtags = _desc_blocks.normalize_hashtags(short_hashtags, required=["shorts"])
 
     return {
         "main_intro": main_intro,
@@ -5440,6 +5455,14 @@ def generate_all(title, prefix, short_scenario, full_scenario=None,
 
         # 2. Videos
         if gen_type in ("short", "both"):
+            # ショート尺ガード: 推定尺を検証し、範囲外なら警告（strict=False で通す）
+            try:
+                from pipeline import shorts_length_guard as _slg
+                _slg_result = _slg.guard(channel_id or "", short_scenario, strict=False)
+                results["shorts_length_check"] = _slg_result
+            except Exception as _slg_err:
+                print(f"⚠️ shorts_length_guard failed (continuing): {_slg_err}")
+
             _ck()
             results["short"] = generate_short_video(short_scenario, title, prefix, bg_video_path,
                                                      out_dir=str(out_dir), bg_type=bg_type, speed=speed,
```

---

## 9. コミット履歴

### 直近20件

```
b680410  2026-08-19 02:35  ザキ  feat(rss): 競合未登録だった5chに監視対象を登録し、RSS監視の穴を塞ぐ
beaa65a  2026-08-19 02:29  ザキ  chore(channels): 全8chに新機能の設定と初期状態を投入
ddff8f8  2026-08-19 02:29  ザキ  feat(growth): 再生リスト自動管理・シリーズ相互リンク・リクエスト募集・競合RSS監視・ショートエンドカード
ac4bf5b  2026-08-19 00:49  ザキ  test(ab): サムネAB判定指標の回帰テストを追加
f4cddab  2026-08-19 00:49  ザキ  fix(ab): サムネABテストが永久にmonitoringから動かない問題を修正
6370420  2026-08-19 00:44  ザキ  test(trends): トレンドソースの疎通に関する回帰テストを追加
db15f1d  2026-08-19 00:44  ザキ  fix(trends): トレンド検出が1件も動いていなかった3つの原因を修正
d3f595c  2026-08-19 00:39  ザキ  test(growth): タイトルCTRゲート・自動コメント・ループ構成の回帰テストを追加
364a623  2026-08-19 00:39  ザキ  chore(channels): 自動コメント設定とタイトル強語彙を全8chに追加
f380c0a  2026-08-19 00:39  ザキ  feat(comment): 投稿直後の自動コメント投稿を追加
ee9d183  2026-08-19 00:39  ザキ  feat(growth): タイトルCTR採点ゲートとショートのループ構成ルールを追加
931f7d5  2026-08-19 00:17  ザキ  chore(channels): テーマキューを補充し、サムネのアクセント色を差別化
6cd54d0  2026-08-19 00:17  ザキ  test(shorts): ショート尺・サムネ配色・連投ガードの回帰テストを追加
9ce617c  2026-08-19 00:16  ザキ  feat(thumbnail): チャンネル別の配色を反映し、文字の視認性を上げる
847c93f  2026-08-19 00:16  ザキ  fix(autopilot): スリープ復帰後の一斉発火による連投を防ぐ
786d314  2026-08-19 00:16  ザキ  fix(shorts): ショート尺を実測ベースで30〜45秒帯に戻す
6a9a2d7  2026-08-18 23:23  ザキ  test(channels): ショート解像度チェックと説明文/タグ生成の回帰テストを追加
4642ce9  2026-08-18 23:23  ザキ  chore(channels): 全8chのタグセットと投稿時間を最適化
1db63df  2026-08-18 23:22  ザキ  feat(autopilot): 投稿時刻を狙って公開する publish_lead_minutes を追加
984d15b  2026-08-18 23:22  ザキ  fix(tags): アップロード時のタグが4〜6個で頭打ちになるバグを修正
```

### 直近20件の変更ファイル統計

```
=== b680410 feat(rss): 競合未登録だった5chに監視対象を登録し、RSS監視の穴を塞ぐ
 backend/pipeline/analytics/competitor_discovery.py | 43 ++++++++++++++++++++++
 backend/pipeline/analytics/competitor_rss.py       | 22 ++++++++++-
 data/channels/2ch-matome.json                      | 11 +++++-
 data/channels/akashic-librarian.json               | 11 +++++-
 data/channels/company-facts.json                   | 11 +++++-
 data/channels/pokemon-lab.json                     | 10 ++++-
 data/channels/yokai-watch.json                     |  7 +++-
 7 files changed, 109 insertions(+), 6 deletions(-)

=== beaa65a chore(channels): 全8chに新機能の設定と初期状態を投入
 data/channels/2ch-matome.json        | 26 ++++++++++++-
 data/channels/akashic-librarian.json | 26 ++++++++++++-
 data/channels/clip-lab.json          | 26 ++++++++++++-
 data/channels/company-facts.json     | 26 ++++++++++++-
 data/channels/daily-science.json     | 26 ++++++++++++-
 data/channels/pokemon-lab.json       | 26 ++++++++++++-
 data/channels/scp-lab.json           | 26 ++++++++++++-
 data/channels/yokai-watch.json       | 26 ++++++++++++-
 data/playlists/2ch-matome.json       |  3 ++
 data/playlists/company-facts.json    |  3 ++
 data/playlists/daily-science.json    |  3 ++
 data/playlists/pokemon-lab.json      |  3 ++
 data/playlists/scp-lab.json          |  3 ++
 data/playlists/yokai-watch.json      |  3 ++
 data/series_links/2ch-matome.json    | 72 ++++++++++++++++++++++++++++++++++++
 data/series_links/company-facts.json | 65 ++++++++++++++++++++++++++++++++
 data/series_links/daily-science.json | 72 ++++++++++++++++++++++++++++++++++++
 data/series_links/pokemon-lab.json   | 72 ++++++++++++++++++++++++++++++++++++
 data/series_links/scp-lab.json       | 72 ++++++++++++++++++++++++++++++++++++
 data/series_links/yokai-watch.json   | 72 ++++++++++++++++++++++++++++++++++++
 20 files changed, 643 insertions(+), 8 deletions(-)

=== ddff8f8 feat(growth): 再生リスト自動管理・シリーズ相互リンク・リクエスト募集・競合RSS監視・ショートエンドカード
 backend/api_competitors_demands.py           |  47 +++
 backend/api_phase4.py                        | 101 +++++++
 backend/pipeline/analytics/competitor_rss.py | 325 +++++++++++++++++++++
 backend/pipeline/analytics/store.py          | 121 ++++++++
 backend/pipeline/auto_comment.py             |   9 +
 backend/pipeline/playlist_manager.py         | 377 ++++++++++++++++++++++++
 backend/pipeline/post_upload.py              |  86 ++++++
 backend/pipeline/series_links.py             | 398 +++++++++++++++++++++++++
 backend/pipeline/short_endcard.py            | 216 ++++++++++++++
 backend/pipeline/video_generator.py          |  56 ++++
 backend/pipeline/viewer_requests.py          | 157 ++++++++++
 backend/run_channel_short_upload.py          |  15 +
 backend/tests/test_growth_v2_features.py     | 417 +++++++++++++++++++++++++++
 13 files changed, 2325 insertions(+)

=== ac4bf5b test(ab): サムネAB判定指標の回帰テストを追加
 backend/tests/test_thumbnail_ab_metric.py | 127 ++++++++++++++++++++++++++++++
 1 file changed, 127 insertions(+)

=== f4cddab fix(ab): サムネABテストが永久にmonitoringから動かない問題を修正
 backend/pipeline/analytics/thumbnail_ab_test.py | 137 +++++++++++++++++++++---
 1 file changed, 125 insertions(+), 12 deletions(-)

=== 6370420 test(trends): トレンドソースの疎通に関する回帰テストを追加
 backend/tests/test_trend_sources.py | 183 ++++++++++++++++++++++++++++++++++++
 1 file changed, 183 insertions(+)

=== db15f1d fix(trends): トレンド検出が1件も動いていなかった3つの原因を修正
 backend/pipeline/analytics/trend_scanner.py | 144 ++++++++++++++++++++++++----
 backend/pipeline/trend_fetcher.py           |  65 ++++++++++++-
 2 files changed, 187 insertions(+), 22 deletions(-)

=== d3f595c test(growth): タイトルCTRゲート・自動コメント・ループ構成の回帰テストを追加
 backend/tests/test_growth_features.py | 266 ++++++++++++++++++++++++++++++++++
 1 file changed, 266 insertions(+)

=== 364a623 chore(channels): 自動コメント設定とタイトル強語彙を全8chに追加
 data/channels/2ch-matome.json        | 14 +++++++++++++-
 data/channels/akashic-librarian.json | 15 +++++++++++++--
 data/channels/clip-lab.json          | 12 ++++++++++--
 data/channels/company-facts.json     | 15 ++++++++++++++-
 data/channels/daily-science.json     | 13 ++++++++++++-
 data/channels/pokemon-lab.json       | 15 ++++++++++++++-
 data/channels/scp-lab.json           | 15 ++++++++++++++-
 data/channels/yokai-watch.json       | 14 +++++++++++++-
 8 files changed, 103 insertions(+), 10 deletions(-)

=== f380c0a feat(comment): 投稿直後の自動コメント投稿を追加
 backend/api_phase4.py            |  96 ++++++++++
 backend/pipeline/auto_comment.py | 367 +++++++++++++++++++++++++++++++++++++++
 2 files changed, 463 insertions(+)

=== ee9d183 feat(growth): タイトルCTR採点ゲートとショートのループ構成ルールを追加
 backend/pipeline/auto_scenario/generator.py | 160 ++++++++++++++++++
 backend/pipeline/title_quality.py           | 248 ++++++++++++++++++++++++++++
 2 files changed, 408 insertions(+)

=== 931f7d5 chore(channels): テーマキューを補充し、サムネのアクセント色を差別化
 data/channels/2ch-matome.json    |  97 ++++++++++++++++++++++++++++----
 data/channels/company-facts.json |  57 ++++++++++++++++++-
 data/channels/daily-science.json |  90 +++++++++++++++++++++++++++++-
 data/channels/pokemon-lab.json   | 116 +++++++++++++++++++++++++++++++++++----
 data/channels/scp-lab.json       |  22 +++++---
 data/channels/yokai-watch.json   |  75 +++++++++++++++++++++++--
 6 files changed, 420 insertions(+), 37 deletions(-)

=== 6cd54d0 test(shorts): ショート尺・サムネ配色・連投ガードの回帰テストを追加
 backend/tests/test_short_format.py | 211 +++++++++++++++++++++++++++++++++++++
 1 file changed, 211 insertions(+)

=== 9ce617c feat(thumbnail): チャンネル別の配色を反映し、文字の視認性を上げる
 backend/pipeline/thumbnail_generator.py | 125 ++++++++++++++++++++++++++------
 1 file changed, 104 insertions(+), 21 deletions(-)

=== 847c93f fix(autopilot): スリープ復帰後の一斉発火による連投を防ぐ
 backend/api_channel_autopilot.py | 72 +++++++++++++++++++++++++++++++++++++---
 1 file changed, 68 insertions(+), 4 deletions(-)

=== 786d314 fix(shorts): ショート尺を実測ベースで30〜45秒帯に戻す
 backend/pipeline/auto_scenario/generator.py | 102 +++++++++++++++++++++-------
 1 file changed, 78 insertions(+), 24 deletions(-)

=== 6a9a2d7 test(channels): ショート解像度チェックと説明文/タグ生成の回帰テストを追加
 backend/channels/config_validation.py    |  29 +++++
 backend/tests/test_description_blocks.py | 192 +++++++++++++++++++++++++++++++
 2 files changed, 221 insertions(+)

=== 4642ce9 chore(channels): 全8chのタグセットと投稿時間を最適化
 data/channels/akashic-librarian.json | 35 ++++++++++++++++++-----
 data/channels/clip-lab.json          | 54 ++++++++++++++++++++++++++++++------
 2 files changed, 73 insertions(+), 16 deletions(-)

=== 1db63df feat(autopilot): 投稿時刻を狙って公開する publish_lead_minutes を追加
 backend/api_channel_autopilot.py | 92 +++++++++++++++++++++++++++++++++++-----
 frontend/src/lib/api.ts          | 17 ++++++++
 2 files changed, 99 insertions(+), 10 deletions(-)

=== 984d15b fix(tags): アップロード時のタグが4〜6個で頭打ちになるバグを修正
 backend/_upload_existing_scp_short.py       |   2 +-
 backend/api_phase3.py                       |   3 +-
 backend/api_phase4.py                       |  38 ++++++-
 backend/channels/channel_manager.py         |  38 +++++++
 backend/channels/video_format.py            |  13 ++-
 backend/pipeline/auto_scenario/generator.py | 116 +++++++++++++++++++-
 backend/run_channel_short_upload.py         |   2 +-
 backend/run_ds_short_upload.py              |   2 +-
 backend/run_pokemon_short_upload.py         |   2 +-
 backend/run_scp_lab_3000_full.py            |   2 +-
 backend/run_scp_lab_3008_full.py            |   2 +-
 backend/run_scp_lab_full.py                 |   4 +-
 backend/run_scp_short_upload.py             |   2 +-
 data/channels/2ch-matome.json               | 158 +++++++++++++++++++++++-----
 data/channels/company-facts.json            | 135 +++++++++++++++++-------
 data/channels/daily-science.json            | 115 +++++++++++++++++---
 data/channels/pokemon-lab.json              | 122 ++++++++++++++++++---
 data/channels/scp-lab.json                  | 122 +++++++++++++++++----
 data/channels/yokai-watch.json              | 121 ++++++++++++++++++---
 19 files changed, 857 insertions(+), 142 deletions(-)
```

---

## 10. data/analytics 状態ファイル

```
total 18776
drwxr-xr-x   6 ayukiyamazaki  staff      192 Aug 19 18:32 .
drwxr-xr-x  32 ayukiyamazaki  staff     1024 Aug 19 19:15 ..
-rw-r--r--   1 ayukiyamazaki  staff  8511488 Aug 19 18:32 analytics.db
-rw-r--r--   1 ayukiyamazaki  staff     2611 Aug 19 17:45 clip_state.json
-rw-r--r--   1 ayukiyamazaki  staff    66733 Aug 18 23:04 retention_insights.json
-rw-r--r--   1 ayukiyamazaki  staff    35307 Aug 18 23:04 success_patterns.json
```

### 10.1 `analytics.db`（SQLite・8.5MB）テーブルと行数

| テーブル | 行数 | 用途 |
|---|---|---|
| `video_metrics` | 4673 | 動画ごとの再生数/いいね/維持率スナップショット（PDCA の一次データ） |
| `trend_scan_history` | 1002 | トレンドスキャンの実行履歴 |
| `competitor_rss_videos` | 972 | 競合RSS監視で拾った新着動画 |
| `model_scenario_records` | 718 | GPT vs Claude のモデル間コンペ記録 |
| `scenario_evaluations` | 342 | シナリオ6軸自動採点（scenario_evaluator） |
| `competitor_analyses` | 280 | 週次の競合チャンネル分析 |
| `channel_metrics` | 263 | チャンネル単位の日次メトリクス |
| `trend_detections` | 186 | トレンドスキャナが検出したキーワード |
| `retention_curve` | 151 | 視聴維持率カーブ（retention_analyzer の入力） |
| `series_suggestions` | 30 | バズ動画からの続編候補（PDCA の Act が承認） |
| `thumbnail_ab_tests` | 18 | サムネAB テストのライフサイクル |
| `comment_analysis` | 13 | コメントの感情/トピック分析結果（Claude） |
| `competitor_video_analyses` | 7 | 競合動画のビジュアル+内容の深掘り分析 |
| `posting_optimizer_cache` | 5 | 投稿時間最適化の算出キャッシュ |
| `sqlite_sequence` | 5 | (SQLite内部) |
| `effects_research` | 1 | 競合の画面演出リサーチ結果 |
| `ab_test_reconciliation` | 0 | AB テストの答え合わせ |
| `comment_demands` | 0 | コメントから抽出した「やってほしい」需要 |
| `competitor_candidates` | 0 | 自動検出した競合候補（承認待ち） |
| `improvement_queue` | 0 | 低CTR動画の自動改善キュー |

### 10.2 `clip_state.json`（全文）— 切り抜き済み区間の消化記録

```json
{
  "sources": {
    "daily-science::なぜか自分を『3割増し』で見せたがる人の脳内で起きている本当のこと": {
      "source_channel_id": "daily-science",
      "title": "なぜか自分を『3割増し』で見せたがる人の脳内で起きている本当のこと",
      "segments": [
        {
          "clip_id": "daily-science_1786236084_0",
          "start": 37.79,
          "end": 69.38,
          "hook": "94%の人が\n「自分は平均以上」と思い込んでいる",
          "created_at": "2026-08-09T09:41:34",
          "video_id": "ESrtjwAUJBQ",
          "url": "https://youtube.com/watch?v=ESrtjwAUJBQ"
        }
      ],
      "last_used_at": "2026-08-09T09:41:34"
    },
    "scp-lab::SCP-049の治療で死ぬのはなぜ？ペスト医師が隠し続ける『真の目的』": {
      "source_channel_id": "scp-lab",
      "title": "SCP-049の治療で死ぬのはなぜ？ペスト医師が隠し続ける『真の目的』",
      "segments": [
        {
          "clip_id": "scp-lab_1786535667_0",
          "start": 78.46,
          "end": 111.04,
          "hook": "一見すると衣装に見えるが",
          "created_at": "2026-08-12T20:54:34",
          "video_id": null,
          "url": null
        }
      ],
      "last_used_at": "2026-08-12T20:54:34"
    },
    "daily-science::なぜ空は青いのか？科学的に解明！": {
      "source_channel_id": "daily-science",
      "title": "なぜ空は青いのか？科学的に解明！",
      "segments": [
        {
          "clip_id": "daily-science_1786776946_0",
          "start": 74.83,
          "end": 105.75,
          "hook": "私たちの目には空全体が青く見えるってわけだ",
          "created_at": "2026-08-15T15:55:54",
          "video_id": null,
          "url": null
        }
      ],
      "last_used_at": "2026-08-15T15:55:54"
    },
    "daily-science::なぜ「暗い部屋でスマホ」は目が悪くなるのか？ブルーライト以外の本当にヤバい理由": {
      "source_channel_id": "daily-science",
      "title": "なぜ「暗い部屋でスマホ」は目が悪くなるのか？ブルーライト以外の本当にヤバい理由",
      "segments": [
        {
          "clip_id": "daily-science_1787129117_0",
          "start": 19.25,
          "end": 49.58,
          "hook": "実は2019年のアメリカ眼科学会の公式発表で",
          "created_at": "2026-08-19T17:45:23",
          "video_id": null,
          "url": null
        }
      ],
      "last_used_at": "2026-08-19T17:45:23"
    }
  }
}```

> `video_id: null` が3件 = 切り抜きは生成されたが **YouTube にアップロードされていない**（clip-lab は `publish_settings.auto_publish=false` のため autopilot は生成のみ）。

### 10.3 `success_patterns.json`（66KB / 5チャンネル分）

構造: `{channel_id: {channel_id, generated_at, sample_size, metrics, title_features, posting_time, success_videos, gpt_insights, gpt_skipped_reason}}`。
対象: `daily-science`, `scp-lab`, `pokemon-lab`, `yokai-watch`, `2ch-matome`。

各チャンネルの計測サマリ:

| channel | 総数 | 成功動画 | 成功avg再生 | その他avg再生 | 成功avg視聴率 | その他avg視聴率 | GPT分析 |
|---|---|---|---|---|---|---|---|
| `daily-science` | 169 | 43 | 958.7 | 532.2 | 86.08% | 26.44% | ANTHROPIC_API_KEY が無効（認証エラー） |
| `scp-lab` | 159 | 41 | 709.3 | 492.3 | 63.81% | 27.4% | ANTHROPIC_API_KEY が無効（認証エラー） |
| `pokemon-lab` | 24 | 7 | 1455.9 | 1293.5 | 86.11% | 50.17% | ANTHROPIC_API_KEY が無効（認証エラー） |
| `yokai-watch` | 23 | 7 | 1420.1 | 1165.0 | 77.0% | 42.84% | ANTHROPIC_API_KEY が無効（認証エラー） |
| `2ch-matome` | 15 | 5 | 1342.8 | 402.6 | 75.95% | 14.62% | ANTHROPIC_API_KEY が無効（認証エラー） |

### 10.4 `retention_insights.json`（65KB / 5チャンネル分）

構造: `{channel_id: {channel_id, generated_at, analyzed_videos, aggregate_drops_by_bucket, per_video, gpt_insights, gpt_skipped_reason}}`。
`per_video[]` は動画ごとに、離脱が大きかった区間（`ratio_from`/`ratio_to`/`drop`/`bucket`）と、**そこで喋られていたシナリオ行**（`scenario_line`: index/speaker/text/mood）を紐付けている。

| channel | 分析動画数 | intro | early | middle | late | ending | GPT分析 |
|---|---|---|---|---|---|---|---|
| `daily-science` | 7 | 0.0059 | 0.0242 | 0.0048 | 0.0074 | 0.0026 | ANTHROPIC_API_KEY が無効（認証エラー） |
| `scp-lab` | 7 | 0.0084 | 0.0223 | 0.0042 | 0.0064 | 0.0067 | ANTHROPIC_API_KEY が無効（認証エラー） |
| `pokemon-lab` | 8 | 0.0058 | 0.0208 | 0.0045 | 0.0113 | 0.0038 | ANTHROPIC_API_KEY が無効（認証エラー） |
| `yokai-watch` | 7 | 0.0076 | 0.0235 | 0.0049 | 0.0059 | 0.0037 | ANTHROPIC_API_KEY が無効（認証エラー） |
| `2ch-matome` | 2 | 0.0053 | 0.0154 | 0.0101 | 0.0103 | 0.0033 | ANTHROPIC_API_KEY が無効（認証エラー） |

> **全10エントリ（5ch × 2ファイル）で `gpt_skipped_reason: "ANTHROPIC_API_KEY が無効（認証エラー）"`、`gpt_insights` は空。**
> 数値集計（維持率カーブ・離脱地点・タイトル特徴量）はルールベースで動いているが、**Claude による示唆生成は全滅している**。

### 10.5 その他のデータストア

```
-rw-r--r--    1 ayukiyamazaki  staff  1087530 Aug 19 18:46 api_usage.jsonl
-rw-r--r--    1 ayukiyamazaki  staff    24576 May 11 14:11 improvement_feedback.db
-rw-r--r--    1 ayukiyamazaki  staff  7528428 Aug 19 18:37 job_queue.json
-rw-r--r--    1 ayukiyamazaki  staff      628 Aug 19 19:15 pending_comments.json
-rw-r--r--    1 ayukiyamazaki  staff    28672 May 10 14:29 phase4.db
-rw-r--r--    1 ayukiyamazaki  staff    28672 Jul  3 22:13 tiktok_tokens.db
-rw-r--r--    1 ayukiyamazaki  staff    20480 Jun  7 17:35 video_publish.db
-rw-r--r--    1 ayukiyamazaki  staff    40960 Aug 19 18:37 youtube_tokens.db
-rw-r--r--    1 ayukiyamazaki  staff    28672 May 21 22:50 youtube_tokens.db.bak_20260520_223338
-rw-r--r--    1 ayukiyamazaki  staff    28672 May 23 09:20 youtube_tokens.db.bak_20260523_092041
-rw-r--r--    1 ayukiyamazaki  staff    28672 May 30 15:04 youtube_tokens.db.before_scp_restore_20260530_150454
```

| ファイル | サイズ | 内容 |
|---|---|---|
| `data/youtube_tokens.db` | 40KB | YouTube OAuth トークン（Fernet 暗号化）。第15章参照 |
| `data/tiktok_tokens.db` | 28KB | TikTok OAuth トークン |
| `data/job_queue.json` | 7.5MB | JobQueue の永続化（ジョブ履歴込み） |
| `data/api_usage.jsonl` | 1.0MB | OpenAI/Anthropic のトークン・費用ログ |
| `data/improvement_feedback.db` | 24KB | いいね率改善フィードバック |
| `data/video_publish.db` | 20KB | 公開状態 |
| `data/phase4.db` | 28KB | スケジュール・テンプレート・通知設定・ABバリアント |
| `data/pending_comments.json` | 1.3KB | 予約公開待ちの保留自動コメント（未コミット・新規） |
| `data/youtube_tokens.db.bak_*` ×3 | 各28KB | トークンDBのバックアップ（2026-05-20 / 05-23 / 05-30 SCP復旧前） |

---

## 11. 動画生成の全ステップ

テーマ選定 → シナリオ生成 → 動画生成 → アップロードまでの一気通貫フロー。

```
[APScheduler cron 発火]  api_channel_autopilot._run_autopilot(channel_id, target_hm)
        │
        ├─(0) 連投ガード _burst_guard_ok — 前回発火から90分未満ならこの発火を捨てる
        ├─(0') gen_type == "clip" なら _run_clip_autopilot へ分岐（第12章）
        ├─(0'') auto_optimize_schedule=true なら posting_optimizer で枠の妥当性チェック→必要なら枠移行
        │
        ├─(1) テーマ取得   _pop_or_refill_theme(channel_id)
        │        キュー先頭から pop。空なら ScenarioGenerator.suggest_themes でAI補充
        │
        ├─(2) シナリオ生成 ScenarioGenerator.generate(ch, theme_override=theme,
        │                                             target_duration=max(60, duration_min*60))
        │        └→ save_scenario()
        │
        ├─(3) キュー投入   JobQueue.submit(channel_id, scenario_data, priority=5, gen_type)
        │
        └─(4) 自動公開マーカー付与 api_phase4._attach_auto_publish_marker(
                     queue, job_id, f"autopilot:{channel_id}", True,
                     publish_at=_next_publish_at(target_hm))

[JobQueue ワーカー（max_workers=2）]  → video_generator.generate_all(...)
        │
[生成完了]  JobQueue.on_job_complete → api_phase4.on_generation_complete(job)
        │
        └→ youtube_pair_publisher / 単体公開 → post_upload.run_async(...)
```

### 11.1 テーマ選定

**2系統のキューが並存**している:

1. `autopilot.theme_queue`（チャンネル JSON 内・**ライブで使われるのはこちら**）— `api_channel_autopilot._pop_or_refill_theme`
2. `pipeline/auto_scenario/theme_queue.py` の `ThemeQueue` モジュール — `main.py` の 30分ごとの `_theme_queue_periodic_job` が `check_all_channels()` で在庫不足チャンネルを補充

重複排除は `pipeline/auto_scenario/theme_dedup.py` の**2段構え**（語彙段 + 意味段）。`generate()` の中でも最終ゲートが効く（下記）。

### 11.2 シナリオ生成 — `ScenarioGenerator.generate()`（`generator.py:1991`）

シグネチャ:

```python
def generate(
    self,
    channel,  # ChannelProfile
    theme_override: Optional[Dict] = None,
    target_duration: Optional[int] = None,
    improvement_feedback: Optional[List[Dict[str, Any]]] = None,
    run_ab_test: bool = False,
    avoid_duplicate_theme: bool = True,
) -> Dict[str, Any]:
```

docstring 原文（抜粋）:

> ANTHROPIC_API_KEY が設定されていれば GPT と Claude の両方で並列生成し、ブラインド評価で勝者を採用する（"AI モデル間コンペ"）。未設定なら GPT のみ。
> `avoid_duplicate_theme`: True（既定）なら、選択/指定されたテーマが既存動画・過去シナリオとほぼ同一（類似度 ≥ THEME_DUP_BLOCK_THRESHOLD）か、チャンネルの theme_blacklist / genre_blacklist に該当する場合、別テーマへ自動で差し替える。さらに生成後の最終タイトルが既存とほぼ同一（≥ TITLE_DUP_REJECT_THRESHOLD）ならタイトルだけ作り直す。theme_override 経由（autopilot / run_*.py / batch）でも必ず適用される重複量産の最終ゲート。

戻り値:

```python
{
    "title": str,
    "theme": {"title": ..., "angle": ...},
    "short_scenario": [...],
    "full_scenario": [...],
    "thumb_info": {...},
    "channel_id": str,
    "style": str,
    "applied_feedback": [<video_id list>],
    "generated_by": "gpt" | "claude",
    "compete": {...} or None,
}
```

内部の実行順（コード内のフェーズコメントより）:

```
① テーマ選択
   theme_override があればそれ。無ければ _pick_seed_avoiding_past()。
   直近30日に同一タイトルがあれば最大3回引き直す（"♻️ Theme … used within 30d — re-picking"）
② テーマ重複の最終ゲート _dedupe_theme()
③ プロンプト addendum の積み上げ
   - improvement_feedback（いいね率改善ループ）        feedback_store.build_prompt_addendum
   - Phase B: Analytics ベース（成功パターン/維持率/コメント要望）  scenario_feedback
   - Phase F-2: 競合分析からの差別化指示               competitor_intelligence
   - Phase S: 季節ブースト                            seasonal_boost.get_seasonal_prompt_addendum
   - Phase T: トレンドテーマなら旬ワードの織り込み指示
   - ★ 最後に「題材ロック」を付ける（theme_override 時）
④ 採用方針決定（strategy decision）
⑤ 生成本体
   ANTHROPIC_API_KEY があれば GPT と Claude を並列生成 → ブラインド評価で勝者採用
   （現状 Claude が 401 なので実質 GPT 単独 + "Only gpt produced a valid scenario — using it"）
   長尺はセクション分割生成（7セクション × 平均8.6行 = 60行 → 約12.8分@VOICEVOX1.3x）
⑥ 行数/文字数チェック（警告のみ、ブロックしない）
⑦ Phase V: scenario_validator.guard()  — フック・CTA・禁止語の検証
⑧ Phase R6: round6_enhancer.enhance()  — Hook A/B ほか6モジュール
⑨ Phase R7: round7_enhancer.enhance()  — 完走率 & リプレイ6モジュール
⑩ Phase R8: round8_enhancer.enhance()  — エンゲージメント & 登録者6モジュール
⑪ Phase N: series_counter.apply_series_number()  — タイトルに通し番号
⑫ Phase C: AB テストでタイトル＆サムネ最適化（run_ab_test=True 時のみ）
⑬ 最終タイトルの重複ゲート（AB でタイトルが差し替わった後に置く）
⑭ CTR 品質ゲート _enforce_title_quality()（title_quality.py）
```

### 11.3 動画生成 — `video_generator.generate_all()`（`video_generator.py:5278`）

引数（原文）:

```python
def generate_all(title, prefix, short_scenario, full_scenario=None,
                 bg_video_path=None, output_dir=None, gen_type="both", bg_type="auto",
                 thumb_info=None, speed=None, target_duration=None, video_title=None,
                 style="yukkuri", use_illustrations=True,
                 channel_format=None, char_config=None, channel_dict=None,
                 bgm_volume=None,
                 image_mode="generate", image_collect_settings=None,
                 cancel_check=None, scenario_meta=None):
```

処理順:

```
1. ファイルディスクリプタ上限を 2048 に引き上げ（大きいシナリオ対策）
2. 出力ディレクトリ決定（output_dir/title または get_output_dir(title)）
3. video_title / short_title を生成（未指定時）
4. hook_caption を thumb_info / scenario_meta から取り出す（冒頭0〜3秒の中央テロップ）
5. シナリオアーカイブ  analytics.scenario_archive.archive_scenario(...)
      → data/scenarios/<channel_id>/archive/<prefix>_<YYYYmmdd_HHMMSS>_scenario.md
6. スタイル分岐（style）:
   ├ "facts_overlay"  → generate_facts_overlay_short()
   │                     縦型ショート専用。立ち絵・対話・DALL-Eカードを使わない。
   │                     長尺は未対応（警告してスキップ）
   ├ "monologue"      → _generate_html_thumbnail() / generate_thumbnail()
   │                     + generate_monologue_video() / generate_monologue_short()
   └ "yukkuri"(既定)  → generate_full_video() / generate_short_video()
                         + generate_thumbnail() / generate_short_thumbnail()
7. 説明文生成 generate_descriptions()（description_blocks でシリーズリンク/リクエスト募集等を合成）
```

音声・演出まわりの実装は同ファイル内:

| 機能 | 関数 |
|---|---|
| VOICEVOX 合成 | `synthesize_voicevox()` / 死活 `check_voicevox()` / モック `synthesize_mock()` |
| 読み補正 | `_tts_force_name_readings()` / `_tts_normalize()` |
| BGM | `_load_bgm_mapping()` / `_resolve_bgm_for_mood()` / `_build_bgm_track_per_scene()` / `_mix_bgm()` |
| イラスト | `_call_openai_image()` / `_build_illustration_prompt()` / `generate_illustration()` / `plan_illustrations()` / `plan_short_illustrations()` |
| フレーム描画 | `FrameRenderer` / `ShortFrameRenderer` / `MonologueFrameRenderer` / `MonologueShortRenderer` / `FactsOverlayShortRenderer` |
| ショート背景 | `_short_bg_query()` / `_collect_short_bg()` / `_portrait_bg_variant()` |
| サムネ | `generate_thumbnail()` / `generate_short_thumbnail()` / `_generate_html_thumbnail()`（Playwright HTML+CSS） |

### 11.4 ジョブキュー — `pipeline/scheduler/job_queue.py`

```
JobQueue(max_workers=2)   # デフォルト2並列: VOICEVOXがボトルネック
状態: pending → running → completed / failed / cancelled
自動リトライ 1回、優先度 1(最高)〜10、PriorityQueue + ThreadPoolExecutor
永続化: data/job_queue.json （プロセス再起動をまたいで復元）
JobCancelled 例外はリトライしない
```

### 11.5 アップロード — `api_phase4.on_generation_complete(job)`（`api_phase4.py:399`）

```
1. job.scenario_data["_options"] の auto_publish を見る
     False → 生成完了通知だけ出して終了
2. ChannelProfile から publish_settings / youtube_channel_id を取得
   投稿先: ch.wants_youtube_post() / ch.wants_tiktok_post()
3. publishAt の決定（優先順）
     a) opts["publish_at"]（autopilot の絶対時刻指定）を _valid_future_publish_at で検証
     b) opts["publish_offset_minutes"] からの相対オフセット
4. TikTok 投稿は独立スレッドで先に起動（_start_tiktok_publish）
5. YouTube 未連携なら通知して中断
6. main + short が揃っていれば youtube_pair_publisher でペア時差公開、
   揃っていなければ単体公開（_start_single_main_publish / _start_single_short_publish）にフォールバック
7. 公開後 → post_upload.run_async(...) と auto_comment
```

自動コメントは「予約公開の解除待ち」があるため `post_upload` ではなく api_phase4 側から個別に呼ばれ、投稿できなかったぶんは `data/pending_comments.json` に積まれて **15分ごとの `auto_comment:flush_pending` ジョブ**が拾う。

---

## 12. clip-lab の仕組み（gen_type=clip）

切り抜きチャンネルは**台本生成もテーマキューも使わない**完全な別系統。素材は自社の既存長尺動画。

### 12.1 発火フロー（`api_channel_autopilot._run_clip_autopilot`、`:599`）

```python
def _run_clip_autopilot(channel_id: str) -> None:
    """切り抜きチャンネルの発火。

    切り抜きは台本生成もテーマキューも使わない（素材は既存の長尺動画）。
    ScenarioGenerator / JobQueue を経由せず clip_factory を直接叩く。
    レンダリングが数十秒かかるのでスケジューラスレッドは塞がず別スレッドで回す。
    """
    def _work() -> None:
        from pipeline.clip_factory import generate_clip
        ...
        auto_publish = bool((raw.get("publish_settings") or {}).get("auto_publish"))
        res = generate_clip(channel_id, count=1, upload=auto_publish)
        ...
    threading.Thread(target=_work, name=f"clip-autopilot-{channel_id}", daemon=True).start()
```

**`clip-lab` の `publish_settings.auto_publish` は `false`** → `upload=False`。つまり**生成だけして投稿していない**（`clip_state.json` の `video_id: null` 3件がその証拠）。

### 12.2 clip_factory のオーケストレーション（`clip_factory/pipeline.py:1`）

```
在庫探索 → 元動画を1本選ぶ → エンジンで切り抜き生成 → メタ生成
→ （任意で）YouTube 投稿 → 消化済み区間を記録

エンジンは差し替え可能（local / noimos）。noimos が使えない環境では
clip.fallback_engine に自動で落ちるので、autopilot は止まらない。
```

| モジュール | 役割 |
|---|---|
| `sources.py` | 在庫管理。「ローカルに残っている長尺 mp4」＋「その台本 JSON」のペアを探す |
| `align.py` | 「どの秒に台本のどの行が喋られているか」を復元。video_generator は行タイムコードを残さないため、字幕帯のシーン検出 + DP で逆算する |
| `segments.py` | どこを切り抜くか決定。スコアは2系統（retention ピーク / 台本スコア） |
| `renderer.py` | 縦型レンダリング。レイアウトは `data/research/clip_shorts_visual_analysis.json` の横断分析に準拠 |
| `engines/local.py` | 内製エンジン（既定）。アライメント→区間選定→縦型レンダリングを自前で回す |
| `engines/noimos.py` | NoimosAI（SaaS）にクリエイティブエージェントとして任せる。`browser`（Playwright）と `cli` の2モード |

### 12.3 `clip-lab.json` の `clip` セクション（現在値・全文）

```json
{
  "engine": "local",
  "fallback_engine": "local",
  "sources": [
    {"channel_id": "scp-lab",       "weight": 2, "credit_name": "SCPラボ"},
    {"channel_id": "daily-science", "weight": 3, "credit_name": "デイリーサイエンス"}
  ],
  "clips_per_video": 3,
  "target_duration_sec": 50,
  "min_duration_sec": 30,
  "max_duration_sec": 59,
  "segment_selection": {
    "prefer_retention_peaks": true,
    "retention_weight": 0.5,
    "script_weight": 0.5,
    "exclude_head_sec": 8,
    "exclude_tail_sec": 15,
    "min_gap_sec": 30
  },
  "noimos": {
    "workspace_id": "cmsnzc4ed032j01s6dxpwfrdo",
    "cli_bin": "noimosai",
    "timeout_sec": 900,
    "mode": "browser",
    "base_url": "https://app.noimosai.com",
    "workspace_url": "https://app.noimosai.com/workspaces/cmsnzc4ed032j01s6dxpwfrdo",
    "headless": true,
    "nav_timeout_sec": 120,
    "agent_wait_sec": 900,
    "poll_interval_sec": 5,
    "storage_state": "~/.youtube-factory/noimos_session.json",
    "selectors": {}
  }
}
```

`engine` も `fallback_engine` も `local`。`.env` の `NOIMOS_EMAIL`/`NOIMOS_PASSWORD` はコメントアウトされたままなので **noimos 経路は未使用**。

`layout_spec` は `canvas` / `fps` / `source_crop_bottom_ratio` のみ（9:16 にクロップせず、上部に16:9のまま置いて下に字幕帯を敷く構成）。

### 12.4 REST API（`api_clips.py`）

```
GET  /api/clips/{channel_id}/sources   切り抜ける元動画の在庫
GET  /api/clips/{channel_id}/state     消化済み区間の状態
POST /api/clips/generate               手動生成
```

---

## 13. `post_upload.py`

アップロード直後に走る共通処理。自動公開（api_phase4）と手動アップロードスクリプト（`run_*_upload.py`）の**両方から同じ入口を呼べる**ようにまとめたもの。**ここでの失敗は投稿を壊さない**（全て try/except で握り潰してログに落とす）。

自動コメント（auto_comment）は「予約公開の解除待ち」という別の都合があるため、ここには含まれず api_phase4 側から個別に呼ばれる。post_upload が扱うのは**公開状態に依存しない処理だけ**（private/予約公開でも通る）。

処理順:

```
1. playlist_manager.add_video_to_playlists(...)   再生リストへ投入
2. series_links.link_and_record(...)              シリーズ相互リンク（前回/次回）
3. series_counter.confirm_upload(...)             シリーズ通し番号を確定（get_series_prefix があるチャンネルのみ）
4. cta_rotator._recent_styles(channel_id, n=3)    CTA ローテーション履歴のログ出力のみ
```

`run_async(**kwargs)` はアップロードスレッドを塞がない fire-and-forget ラッパ（daemon スレッド `"post-upload"`）。

**全文:**

```python
"""アップロード直後に走る共通処理（再生リスト投入 / シリーズ相互リンク）。

自動公開（api_phase4）と手動アップロードスクリプト（run_*_upload.py）の
両方から同じ入口を呼べるようにまとめる。ここでの失敗は投稿を壊さない。

自動コメント（auto_comment）は「予約公開の解除待ち」という別の都合があるため
従来どおり api_phase4 側から個別に呼ぶ。ここでは公開状態に依存しない
（private/予約公開でも通る）処理だけを扱う。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"


def _load_channel(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run(
    *,
    channel_id: str,
    video_id: Optional[str],
    title: str = "",
    url: str = "",
    is_short: bool = True,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """再生リスト投入 → シリーズリンクの順に実行し、結果をまとめて返す。"""
    if not video_id:
        return {"ok": False, "skipped": "no_video_id"}

    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    video_url = url or f"https://youtube.com/watch?v={video_id}"
    out: Dict[str, Any] = {"channel_id": channel_id, "video_id": video_id}

    try:
        from . import playlist_manager

        out["playlists"] = playlist_manager.add_video_to_playlists(
            channel_id, video_id, title=title, is_short=is_short, channel_dict=cd
        )
    except Exception as e:
        out["playlists"] = {"ok": False, "error": str(e)}
        print(f"⚠️ post_upload playlists failed [{channel_id}] {video_id}: {e}")

    try:
        from . import series_links

        out["series_links"] = series_links.link_and_record(
            channel_id,
            video_id,
            title=title,
            url=video_url,
            is_short=is_short,
            channel_dict=cd,
        )
    except Exception as e:
        out["series_links"] = {"ok": False, "error": str(e)}
        print(f"⚠️ post_upload series_links failed [{channel_id}] {video_id}: {e}")

    # Phase N: シリーズ通し番号カウンタを確定（アップロード成功後）
    try:
        from pipeline.series_counter import confirm_upload, get_series_prefix
        if get_series_prefix(channel_id, cd):
            new_count = confirm_upload(channel_id)
            out["series_counter"] = {"ok": True, "new_count": new_count}
            print(f"  🔢 Series counter advanced to #{new_count} [{channel_id}]")
    except Exception as e:
        out["series_counter"] = {"ok": False, "error": str(e)}
        print(f"⚠️ post_upload series_counter failed [{channel_id}]: {e}")

    # Phase R6: CTA ローテーション履歴の記録（Round 6）
    # generate() 時点で cta_rotator が履歴を書いているため、ここでは
    # アップロード成功を確認した上で追加の後処理が必要な場合のみ動く。
    # 現時点では generate() 側で完結しているため、ログのみ。
    try:
        from pipeline.cta_rotator import _recent_styles
        recent = _recent_styles(channel_id, n=3)
        if recent:
            out["cta_rotation"] = {"ok": True, "recent_styles": recent}
    except Exception:
        pass  # CTA ローテーションは必須ではない

    return out


def run_async(**kwargs: Any) -> None:
    """アップロードスレッドを塞がない fire-and-forget ラッパ。"""

    def _work() -> None:
        try:
            run(**kwargs)
        except Exception as e:
            print(f"⚠️ post_upload thread failed: {e}")

    threading.Thread(target=_work, name="post-upload", daemon=True).start()
```

> 未コミット差分（+23行）は「Phase N: series_counter」と「Phase R6: CTA ローテーション」の2ブロック。

---

## 14. スケジューラの仕組み

**cron は使っていない。** 2層構造:

1. **アプリ内 APScheduler**（`BackgroundScheduler(timezone="Asia/Tokyo")`）— バックエンドプロセス内で全ての定期処理を持つ。所有者は `api_phase4`（`_ensure_scheduler()`）。autopilot・改善ループ・トレンド・競合スキャン等が全部これに相乗り。
2. **macOS launchd** — バックエンド/agent/ngrok の常駐（KeepAlive）と、プロセス外バッチ（日次 PDCA 23:00）。

### 14.1 APScheduler 上のジョブ一覧

| ジョブID | トリガー | 内容 | 登録元 |
|---|---|---|---|
| `autopilot:{channel_id}:{slot}` | Cron（曜日 + 時刻、`publish_lead_minutes` ぶん前倒し） | チャンネル別フルオート投稿 | `api_channel_autopilot._refresh_channel_job` |
| `sched:{schedule_id}` | Cron | UI から作った任意スケジュール投稿 | `api_phase4._register_schedule_job` |
| `auto_comment:flush_pending` | `CronTrigger(minute="*/15")` | 予約公開が解除された動画への保留コメント投稿 | `api_phase4:1735` |
| `thumbnail_ab_test:check_all` | `CronTrigger(minute=0)`（毎時0分） | サムネABテストの CTR 監視・自動差し替え | `api_phase4:1785` |
| `trend_scanner:scan_all` | `CronTrigger(hour="0,6,12,18", minute=30)` | Google Trends / News / YouTube 急上昇スキャン | `api_phase4:1818` |
| `competitor_analyzer:scan_all` | `CronTrigger(day_of_week="sun", hour=3, minute=0)` | 週次の競合チャンネル分析 | `api_phase4:1862` |
| `competitor_discovery:discover_all` | `CronTrigger(day=1, hour=4, minute=0)` | 月次の競合チャンネル自動発見 | `api_phase4:1901` |
| `competitor_rss:scan_all` | `CronTrigger(hour="*/3", minute=10)` | 競合RSS監視（APIクォータ0） | `api_phase4:1944` |
| 改善ループ日次チェック | `CronTrigger(hour=6, minute=0)` | いいね率チェック→改善フィードバック生成 | `api_improvement:363` |
| `theme-queue-check-all` | `IntervalTrigger(minutes=30)`、起動直後にも1回 | 在庫不足チャンネルのテーマ自動補充 | `main.py:1578`（**別の BackgroundScheduler インスタンス**） |

`THEME_QUEUE_CHECK_INTERVAL_MIN` は環境変数で上書き可（既定 30）。

### 14.2 autopilot ジョブの登録ロジック（`_refresh_channel_job`）

```
1. 既存の autopilot:{channel_id}* ジョブを全削除（新旧ID両形式）
2. enabled=false → 登録せず終了
3. schedule.days_of_week が空 → 登録せず終了
4. _resolve_time_slots(schedule) で発火スロットを列挙
     times[] があればそれ。無ければ hour/minute の単一スロット
5. 各スロットについて:
     slot_days = slot.days_of_week or schedule.days_of_week
     lead = publish_lead_minutes（0〜720にクランプ）
     fire_h, fire_m, day_shift = _shift_time(slot.hour, slot.minute, -lead)
     日をまたいだら曜日も day_shift ぶんずらす
     CronTrigger(day_of_week=…, hour=fire_h, minute=fire_m, timezone="Asia/Tokyo")
     add_job(_run_autopilot, args=[channel_id, target_hm if lead>0 else None],
             id=f"autopilot:{channel_id}:{idx}",
             misfire_grace_time=_misfire_grace_seconds(lead))
```

`misfire_grace_time` を短くした理由（コード内コメント原文）:

```python
# 1時間だと、スリープ復帰時に直前1時間ぶんの未発火ジョブが全部
# まとめて発火して連投になる（2026-08-17 の 09:27〜09:28 に4本）。
# publish_lead_minutes 運用では「公開時刻を過ぎてから生成開始」しても
# 予約公開が成立しないので、リード時間の範囲内に収める。
```

### 14.3 予約公開時刻の算出（`_next_publish_at`）

```python
def _next_publish_at(target_hm: Optional[str]) -> Optional[str]:
    """"HH:MM" (JST) を次に迎える時刻の RFC3339 UTC 文字列にする。

    すでに過ぎていれば翌日扱い。YouTube の publishAt は未来である必要があるため、
    現在時刻から2分以内なら None（即時公開）を返す。
    """
```

### 14.4 launchd 層

| ラベル | トリガー | 内容 |
|---|---|---|
| `com.youtube-factory.backend` | RunAtLoad + KeepAlive、ThrottleInterval 30 | `python3 -m uvicorn main:app --host 0.0.0.0 --port 8000`。**現在停止（exit 1）** |
| `com.youtube-factory.agent` | RunAtLoad + KeepAlive、ThrottleInterval 30 | `python3 -u -m agent run youtube-growth` |
| `com.youtube-factory.ngrok` | RunAtLoad + KeepAlive | `ngrok http 8000 --url=agreeing-corrode-shabby.ngrok-free.dev` |
| `com.youtube-factory.pdca` | `StartCalendarInterval` 23:00、RunAtLoad=false | `python3 -u backend/run_daily_pdca.py` |

### 14.5 日次 PDCA（`backend/run_daily_pdca.py`）

設計方針（docstring 原文）:

> 動画投稿のオートパイロットと同様、テーマキューや analytics.db を持つのは「ライブのバックエンドサーバ（localhost:8000）」である。channel_manager は `_raw` をメモリにキャッシュしており、外部から `data/channels/*.json` を直接書くとサーバ側の保存と競合してテーマが消える（過去に dup-flood を起こした経路）。
> そのため本ランナーは **すべての更新系をライブサーバの HTTP API 経由で行う**。

実行内容（`analytics.enabled=true` のチャンネルのみ）:

```
1. Check : POST /api/analytics/sync/{id}
             → YouTube から再生数・いいね・維持率を取得して analytics.db へ。
               付随してサーバ側 PDCA チェーン（シナリオ評価 / AB答え合わせ /
               改善キュー / シリーズ検出 / コメント需要抽出）も走る。
2. 分析  : pdca-report / videos / optimal-posting-time / series を取得し、
           動画ごとの再生数推移・ジャンル別成績・投稿時間帯×再生数の相関・
           テーマ重複チェックをまとめる。
3. Act   : バズ動画からの続編候補（series_suggestions）を、一定の絶対再生数を
           超えたものだけ自動承認してテーマキュー先頭へ投入。
           低再生ジャンルは抑制候補としてレポートに記載（破壊的操作はしない）。
4. 保存  : data/reports/YYYY-MM-DD/ に JSON + Markdown、latest.md、pdca_history.xlsx
```

Act のガード定数:

```python
MIN_VIRAL_VIEWS = 30       # この絶対再生数を超えたバズ動画の続編のみ自動投入
MIN_VIRAL_RATIO = 1.5      # チャンネル平均比
MAX_APPROVALS_PER_RUN = 2  # 1チャンネル/日あたりの自動投入上限
DEDUP_SIM_THRESHOLD = 0.62 # テーマ重複とみなす類似度
BASE_URL = os.environ.get("PDCA_BASE_URL", "http://localhost:8000")
```

最新実行（2026-08-18分）のログ末尾:

```
⚠️ claude_client call failed (retention_analysis): Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'API key is invalid.'}, 'request_id': None}
    retention insights ok — 0 tips
  [Act] promote viral sequels...
    approved: 0
  [xlsx] 履歴更新: data/reports/pdca_history.xlsx （5ch / 2026-08-18）
✅ レポート出力: data/reports/2026-08-18/report.md
```

---

## 15. YouTube OAuth 認証の状態

### 15.1 保存先とスキーマ

`data/youtube_tokens.db`（SQLite・40KB）。テーブル3つ:

```
oauth_tokens  (channel_id, account_email, youtube_channel_id, youtube_channel_name,
               token_data, expires_at, updated_at)
oauth_state   (state, channel_id, redirect_uri, created_at, code_verifier)
oauth_clients (channel_id, client_data, updated_at)
```

`token_data` は **Fernet 暗号化**されている（先頭が `F:gAAAAA…`）。鍵は `backend/.env` の `JWT_SECRET` から導出されるので、**トークンを読む診断スクリプトは必ず `.env` を先に読み込む必要がある**。

実装は `backend/pipeline/youtube_oauth.py`（25KB）。チャンネル（内部 channel_id）ごとに独立した OAuth フローを持つ。

### 15.2 現在のトークン状態（2026-08-19 19時時点）

| channel_id | YouTube Channel ID | 表示名 | expires_at | 最終更新 |
|---|---|---|---|---|
| `clip-lab` | UCbWZ5quEFE2VpHPh5TGyPCw | 切り抜きLab | 2026-08-19 06:31:27 | 2026-08-19 14:31:28 |
| `company-facts` | UCB07OOxWeKK6v86KsSYgnNA | 企業のホンネ | 2026-08-19 08:19:41 | 2026-08-19 16:19:42 |
| `daily-science` | UC1OckVkZahT3_fM6W8hD6dg | リコとマコトのゆっくり日常科学 | 2026-08-19 09:21:30 | 2026-08-19 17:21:31 |
| `yokai-watch` | UCYf2lsHuHUXbj_HGmqojkUw | ゆっくり妖怪ラボ | 2026-08-19 09:55:31 | 2026-08-19 17:55:32 |
| `pokemon-lab` | UCGgc5REGTWRLnBiSeXXkJ5w | ゆっくりポケラボ | 2026-08-19 09:59:59 | 2026-08-19 18:00:00 |
| `scp-lab` | UCXEyJqJt9Ug94iOHdpd5a8w | 異常存在SCPゆっくり解説ラボ | 2026-08-19 10:24:56 | 2026-08-19 18:24:57 |
| `2ch-matome` | UCqvn5FC_B1nj2VhlFTFw8CA | ゆっくり2chスレまとめ劇場 | 2026-08-19 10:37:42 | 2026-08-19 18:37:43 |

- **`akashic-librarian` の行は存在しない = YouTube 未連携。**（同チャンネルは `autopilot.enabled=false`）
- 7チャンネル全ての `updated_at` が**今日（2026-08-19）の投稿スロット直後**に並んでおり、アクセストークンの自動リフレッシュが正常に回っていることを示す（`expires_at` は表示上 8時間ずれているが、更新時刻の順序は各チャンネルの投稿スロット順と一致）。
- `account_email` は全て `NULL`（記録されていない）。
- `oauth_clients` には7チャンネル分の client_data が登録済み（最終更新: scp-lab/daily-science 2026-06-15、pokemon-lab/yokai-watch 2026-07-25、company-facts 2026-07-29、clip-lab 2026-08-04、2ch-matome 2026-08-04）。

### 15.3 既知の制約

- **scp-lab はカスタムサムネイル設定が 403**（チャンネルが電話番号未確認）。アップロード自体は成功し、サムネ設定だけ失敗する警告が出る。
- トークン DB のバックアップが3世代残っている（`.bak_20260520_223338` / `.bak_20260523_092041` / `.before_scp_restore_20260530_150454`）。

---

## 付録: 全体の依存と外部サービス

| サービス | 用途 | 状態 |
|---|---|---|
| OpenAI API | シナリオ生成、DALL-E イラスト、AB タイトル | 稼働 |
| Anthropic Claude API | 分析・評価・採点・判断、agent の思考 | **401 invalid（停止中）** |
| YouTube Data API v3 | アップロード、統計、コメント | 稼働 |
| YouTube Analytics API v2 | 再生数・維持率（**impressions/CTR は取得不可**） | 稼働 |
| VOICEVOX (localhost:50021) | 音声合成 | ローカル |
| Pexels API | フリー素材画像収集 | 稼働 |
| TikTok Content Posting API | 並行投稿 | 実装済み |
| NoimosAI | 切り抜き SaaS エンジン | **未設定（local エンジン使用）** |
| ngrok | 外部公開トンネル | 稼働（固定ドメイン） |
| Vercel | フロントエンド（Next.js） | 別リポジトリ配下 |
