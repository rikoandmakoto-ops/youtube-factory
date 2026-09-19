#!/bin/bash
# =====================================================================
#  YouTube Factory 指揮者 — 2026-09-19 実行スクリプト
#
#  指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ
#  到達できない。Phase 4（制作指示）はこのスクリプトを Mac 上で
#  ダブルクリックして実行する必要がある。
#
#  ═══════════════════════════════════════════════════════════════════
#  ★★★ 今日いちばん大事な話：サムネの優先度を下げてください ★★★
#  ═══════════════════════════════════════════════════════════════════
#
#  「サムネ品質最優先」は方針として持っていましたし、09-18 の指揮者は
#  サムネ403（852件）を最優先の依頼として出しました。今日それを実測で
#  検証したところ、**サムネはこの6chの再生数にほぼ関係していません**。
#
#    インプレッション × CTR 由来の再生が、総再生に占める割合:
#      daily-science 0.22% / scp-lab 1.21% / yokai-watch 0.54%
#      company-facts 0.47% / 2ch-matome 0.12% / pokemon-lab 0.17%
#      ─────────────────────────────────────────
#      合計 1,427 / 296,090 = 0.48%
#
#  つまり再生の 99.5% は Shorts フィード由来で、サムネが表示される面
#  （ブラウズ・検索・関連）からは 0.5% しか来ていません。
#  ＊ Shorts フィードのインプレッションは YouTube の API が返さないため、
#    ここでの impressions は「サムネが見られる面」だけを指します。
#    だからこそ、この 0.48% がサムネの効きうる上限になります。
#
#  → 403 の解消（/verify の電話確認）は、やれば綺麗になりますが、
#    やっても再生は 0.5% の内側でしか動きません。
#    **急ぎではありません。手が空いたときで結構です。**
#    指揮者も今後サムネを最優先には置きません。
#
#  ─────────────────────────────────────────────────────────────────
#  ★ あなたにしかできない作業（1件だけ・9日放置）
#  ─────────────────────────────────────────────────────────────────
#
#  【1】pokemon-lab が OAuth 失効で 9 日間停止しています
#
#    09-10 07:43 を最後にトークン未更新 → 09-14 に autopilot.enabled=false。
#    analytics も 09-08 以降ストップしています（他5chは 09-18 まで取得済み）。
#    09-17・09-18 の指揮者も同じ依頼を出しており、まだ通っていません。
#    停止直前の登録/千は 0.360、成熟動画の 42% が 1,200 再生超という
#    **6ch中いちばん天井が高いチャンネル**なので、止めている損が大きいです。
#
#    あなたの作業: pokemon-lab の OAuth 再認可。
#    通ったら以下を実行して autopilot を戻してください:
#
#      cd ~/Developer/youtube-factory
#      python3 - <<'PY'
#      import json,pathlib
#      p=pathlib.Path("data/channels/pokemon-lab.json")   # orchestrator 側は symlink
#      d=json.loads(p.read_text(encoding="utf-8"))
#      d["autopilot"]["enabled"]=True
#      p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
#      print("pokemon-lab autopilot 再開")
#      PY
#
#  ═══════════════════════════════════════════════════════════════════
#  ★ 今日の発見：リーチが落ちたのは 08-19。原因を外しても戻っていない
#  ═══════════════════════════════════════════════════════════════════
#
#  推定尺を 26〜36秒に揃えた対照（ゆっくり系5ch・成熟動画）:
#
#    期間              n   尺中央  avp中央  再生中央  1,200超
#    ①〜08-18         83   30.0s   54.6%    1,063    29本 (35%)
#    ②08-19〜08-30    10   31.1s   40.7%      915     1本
#    ③08-31〜09-11    60   31.7s   41.5%      916     0本
#    ④09-12〜         25   33.0s   41.0%      932     0本
#
#  ・尺を揃えても avp が 54.6% → 41% に落ちている＝09-18 に直した
#    「長尺事故」は原因の一部でしかありません。
#  ・1,200再生を超える動画が 35% → **0%** になり、3週間 1本も出ていません。
#    ゆっくり系5chは全員 900〜1,100 で頭打ちです。
#  ・avp が落ちた 08-19 は、Round6〜8 の本文書き換えエンハンサーが
#    動いていた期間と一致します。ただし **08-31 に全停止した後も
#    avp は 41% のまま戻っていません**。原因を外しても戻らなかった、
#    というのが今日の一番重要な事実です。
#  ・唯一の例外が company-facts で、この期間に avp が上がり(68.5%)、
#    いまも 1,200超が出ています。フォーマットが違う（facts_overlay・
#    尺 40〜80秒）ことが効いている可能性が高い。
#
#  → 「1本ごとの台本を直す」PDCA では 3週間動きませんでした。
#    今日はその中で **確実に直せる欠陥を2つだけ** 潰します（下記 A/B）。
#    company-facts 型の移植は、効果が出るまで時間がかかるので
#    09-26 に③④の追跡結果を見てから判断します。
#
#  ─────────────────────────────────────────────────────────────────
#  ★ 今日のコンフィグ変更（すべて 09-18 スナップショット＋台本実測）
#  ─────────────────────────────────────────────────────────────────
#
#  【A】daily-science：2行目が55%で同じ文だった
#
#    data/scenarios/daily-science の全台本 n=29 を突合したところ、
#    2行目が「えっ、それ昨日あった！」×9 ＋「えっ、それ昨日やった！」×7
#    ＝ 16本(55%) でほぼ同一文でした（2行目の重複率 62%）。
#    1行目の重複は 0% なので、崩れているのは真（まこと）の相槌だけです。
#    2行目は再生位置およそ3〜6秒＝スワイプ判断の窓に当たります。
#
#    健全な company-facts は 6%、yokai-watch 7%、2ch-matome 0%。
#    当chだけ突出しています。
#
#    原因は voice_style.tone に書いてあった
#    「『あなたも昨日やったはず』の実体験から入る」という**例示文が、
#    そのまま台詞として採用されていた**ことです。指示文の例を
#    生成がコピーしていました。
#
#    → forbidden に「それ昨日あった」「それ昨日やった」を追加。
#      tone から例示文を外し、相槌は直前の台詞の具体語（数値・部位・
#      現象名）を必ず1つ拾って返す、というルールにしました。
#
#  【B】scp-lab：1行目の24%が「このSCP、実は」始まり
#
#    n=29 の1行目を先頭10字で突合: 「このSCP、実は君の…」×3 ／
#    「このSCP、実はあな…」×2 ／「なんでこのSCPだけ…」×2 ＝ 24%。
#    当chの avp 35.7% は稼働6ch中最下位です。
#    → 1行目を「このSCP、実は」で始めることを禁止。異常そのものを
#      名詞で言い切って始める形にしました。
#
#  【C】2ch-matome：エンハンサーが1chだけ有効のまま残っていた
#
#    他5chは 08-31〜09-01 に本文書き換え系13モジュールを全停止済みですが、
#    **2ch-matome だけ script_enhancers が空（＝全モジュール有効）**
#    のまま3週間放置されていました。
#    enhancer_gate.py の docstring 自身が「voice_style.forbidden の語が
#    本文に注入される」「正規表現置換で係り受けが壊れる」「尺を大きく
#    超える」と書いているモジュール群です。
#    当chは 登録/千 0.189（6ch最下位）、W37 の日次再生 2、avp 35〜38% と
#    全指標で最下位。条件を揃えないまま評価を続ける意味がないので
#    他5chと同じ設定に揃えました。判定は 10-02。
#
#  ─────────────────────────────────────────────────────────────────
#  ★ 変更しなかったもの（理由つき）
#  ─────────────────────────────────────────────────────────────────
#
#  ・テーマキュー: seeds 27〜33件で不足なし。水増し補充はしません。
#  ・尺・文字数帯: 09-18 に変更したばかり。評価は 09-25。交絡させません。
#  ・投稿時刻: 同上（09-17 に変更）。今日の台本変更と交絡します。
#  ・voice_style の維持率チューニング: 09-18 に「維持率を理由にした
#    構造改訂は打ち切る」と決めた方針を維持します。今日の A/B は
#    維持率ではなく「同一文の重複」という別の欠陥に対する修正です。
#  ・サムネ: 上記のとおり優先度を下げました。
#
# =====================================================================

set -uo pipefail
cd "$(dirname "$0")" || exit 1

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  YouTube Factory 指揮者 — 2026-09-19 Phase 4 制作指示"
echo "═══════════════════════════════════════════════════════"
echo ""

echo "▶ backend の生存確認 ..."
if curl -s -m 5 -o /dev/null -w "" http://localhost:8000/health 2>/dev/null; then
  echo "  ✅ backend は稼働中"
else
  echo "  ⚠️  backend が応答しません。先に restart-backend.command を実行してください。"
  echo "      （このスクリプトは backend を落としません）"
  read -n 1 -s -r -p "  何かキーを押すと終了します..."
  exit 1
fi
echo ""

echo "▶ 指揮者が書いたコンフィグを backend に読み直させます ..."
code=$(curl -s -m 30 -o /tmp/yt_reload.json -w "%{http_code}" \
       -X POST "http://localhost:8000/api/channels/reload" 2>/dev/null)
if [ "$code" = "200" ] || [ "$code" = "202" ]; then
  echo "  ✅ reload 受理 (HTTP $code)"
else
  echo "  ℹ️  reload エンドポイントは HTTP $code（未実装なら無視して構いません）"
  echo "      反映されない場合は restart-backend.command を実行してください。"
fi
echo ""

echo "▶ 制作指示を出します（moviepy 系）"
echo "   pokemon-lab は OAuth 失効のためスキップ（上記【1】）"
echo "   clip-lab（凍結中）/ akashic-librarian（OAuth未連携）もスキップ"
echo ""

CHANNELS="daily-science scp-lab 2ch-matome yokai-watch company-facts"
OK=0; NG=0

for ch in $CHANNELS; do
  printf "   %-16s ... " "$ch"
  code=$(curl -s -m 180 -o "/tmp/yt_trig_$ch.json" -w "%{http_code}" \
         -X POST "http://localhost:8000/api/autopilot/${ch}/trigger" 2>/dev/null)
  if [ "$code" = "200" ] || [ "$code" = "202" ]; then
    echo "✅ 受理 (HTTP $code)"
    OK=$((OK+1))
  else
    echo "❌ HTTP $code"
    head -c 300 "/tmp/yt_trig_$ch.json" 2>/dev/null; echo ""
    NG=$((NG+1))
  fi
done

echo ""
echo "─────────────────────────────────────────────"
echo "  受理 $OK ch / 失敗 $NG ch"
echo "─────────────────────────────────────────────"
echo ""

echo "▶ 今日の変更が実際に台本へ効いたかの確認方法"
echo "   生成が一巡したら（30〜60分後）、これを実行してください:"
echo ""
cat <<'CHECK'
     cd ~/Developer/youtube-factory
     python3 - <<'PY'
     import json,glob,collections,os,time
     for ch in ("daily-science","scp-lab"):
         rows=[]
         for p in glob.glob(f"data/scenarios/{ch}/**/*.json",recursive=True):
             if time.time()-os.path.getmtime(p) > 86400: continue
             try: d=json.load(open(p,encoding="utf-8"))
             except Exception: continue
             s=d if isinstance(d,list) else (d.get("short_scenario") or d.get("full_scenario"))
             if isinstance(s,str):
                 try: s=json.loads(s)
                 except Exception: continue
             if not isinstance(s,list) or len(s)<2: continue
             rows.append((s[0].get("text",""), s[1].get("text","")))
         if not rows: print(f"{ch}: 本日生成の台本なし"); continue
         c1=collections.Counter(a[:8] for a,_ in rows)
         c2=collections.Counter(b[:6] for _,b in rows)
         d1=sum(v for v in c1.values() if v>1)/len(rows)
         d2=sum(v for v in c2.values() if v>1)/len(rows)
         print(f"{ch}: n={len(rows)} 1行目重複={d1*100:.0f}% 2行目重複={d2*100:.0f}%")
         bad=[b for _,b in rows if "それ昨日あった" in b or "それ昨日やった" in b]
         print(f"   禁止フレーズ残存: {len(bad)}本")
     PY
CHECK
echo ""
echo "   期待値: daily-science の2行目重複 20%未満・禁止フレーズ 0本"
echo "           scp-lab の1行目重複 10%未満"
echo "   ここが下がっていなければ、禁止語が生成に渡っていません。"
echo "   （その場合は指揮者に『09-19の禁止語が効いていない』と伝えてください）"
echo ""
echo "▶ 次回評価日"
echo "   09-25  尺短縮3ch（09-18の変更）の登録/千・リーチ"
echo "   09-26  今日の A/B（冒頭重複）の avp: daily-science 41.0%→46%, scp-lab 35.7%→41%"
echo "   10-02  2ch-matome のエンハンサー停止の効果"
echo ""
echo "▶ バックアップ（変更前の状態）"
echo "   data/channels/{daily-science,scp-lab,2ch-matome}.json.bak_pdca_20260919_orch"
echo ""
read -n 1 -s -r -p "何かキーを押すと閉じます..."
echo ""
