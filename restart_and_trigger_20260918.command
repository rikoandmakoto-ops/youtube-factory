#!/bin/bash
# =====================================================================
#  YouTube Factory 指揮者 — 2026-09-18 実行スクリプト
#
#  指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ到達
#  できない。Phase 4（制作指示）はこのスクリプトを Mac 上でダブルクリック
#  して実行する必要がある。
#
#  ─────────────────────────────────────────────────────────────────
#  ★★ あなたにしかできない作業が2件（どちらも数日放置されている） ★★
#  ─────────────────────────────────────────────────────────────────
#
#  【1】カスタムサムネイルが 852 回連続で失敗している（成功 71 回）
#
#    logs のエラー:
#      HttpError 403 "The authenticated user doesn't have permissions to
#      upload and set custom video thumbnails."
#
#    失敗の内訳: company-facts 38 / scp-lab 37 / yokai-watch 32 /
#                pokemon-lab 21 / 2ch-matome 21 / fake-paper 14
#    ＝ moviepy 系 6ch すべてで、作ったサムネが1枚も付いていない。
#    いま視聴者が見ているサムネは YouTube が動画から自動生成したコマ。
#    「サムネ品質最優先」の方針に対して、パイプラインの手前で全部
#    捨てられている状態なので、ここを直さない限り改善は反映されない。
#
#    原因はコードではなくアカウント側の権限です。403 の reason が
#    "forbidden" / location "Authorization" で、これはカスタムサムネイル
#    機能が未開放のアカウントに出るものです。
#
#    あなたの作業:
#      https://www.youtube.com/verify で電話番号による確認を完了する
#      （各チャンネルのアカウントごとに必要）。
#      完了後、YouTube Studio で任意の動画にサムネを手動設定できるか
#      確認してください。手動で設定できれば API 側も通ります。
#
#    ※ 指揮者は認証・アカウント設定の変更は行いません（方針）。
#
#  【2】pokemon-lab が 8 日間停止している（OAuth 失効）
#
#    autopilot.enabled=false のまま 09-14 から復帰していません。
#    09-10 07:43 を最後にトークンが更新されておらず、09-17 の指揮者も
#    同じ依頼を出しています。再認可が通るまで投稿ゼロが続きます。
#
#    あなたの作業: pokemon-lab の OAuth 再認可。
#    通ったら以下を実行して autopilot を戻してください:
#      python3 - <<'PY'
#      import json,pathlib
#      for b in ("data/channels","data/channels_orchestrator"):
#          p=pathlib.Path(b)/"pokemon-lab.json"
#          d=json.loads(p.read_text(encoding="utf-8"))
#          d["autopilot"]["enabled"]=True
#          p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
#      print("pokemon-lab autopilot 再開")
#      PY
#
#  ─────────────────────────────────────────────────────────────────
#  ★ 今日のコンフィグ変更（すべて 09-17 スナップショットの実測）
#  ─────────────────────────────────────────────────────────────────
#
#  【A】読み上げ速度の校正が 1.28 倍ずれていたのを直した（コード修正）
#
#    backend/pipeline/shorts_length_guard.py
#      VOICEVOX_CHARS_PER_SEC: 8.9 → 6.95
#      CHANNEL_CHARS_PER_SEC に実測値を ch ごとに追加
#        company-facts 5.44 / daily-science 7.24 / yokai-watch 7.15
#        scp-lab 6.94 / socio-rx 6.20
#
#    検証方法: data/scenarios/<ch>/*.json の short_scenario 実文字数と、
#    公開後の実尺（avg_view_duration ÷ 維持率）を突き合わせた（n=31, 5ch）。
#      company-facts  204字 → 実尺 41.3s （設計値 26s）
#      daily-science  223字 → 実尺 34.3s （設計値 26s）
#      yokai-watch    220字 → 実尺 33.7s （設計値 26s）
#      scp-lab        197字 → 実尺 31.1s （設計値 26s）
#
#    8.9字/秒 は机上値で、一度も実尺と照合されていませんでした。この過大
#    評価のせいで「175〜225字＝26秒」という設計値が実際には 27〜35秒の
#    動画を生んでおり、しかもガードは「帯に収まっている」と報告し続けるので
#    誰も気づけない構造になっていました。
#
#  【B】その 27〜35秒 の上側が、実測で負け群だった
#
#    成熟コホート（公開 08-10〜09-10・200再生以上）の ch 内対照で、
#    推定尺 <33秒 と >=33秒 の 登録/千再生:
#      yokai-watch    1.19 vs 0.41 (2.92倍) ※再生中央値も 1002 vs 612
#      daily-science  1.14 vs 0.42 (2.71倍)
#      scp-lab        0.94 vs 0.77 (1.21倍)
#      2ch-matome     0.18 vs 0.20 (0.88倍) ← 当chのみ長尺が僅かに優位
#
#    → 3ch の文字数帯の上限を、実効速度換算で 30秒に収まる位置へ下げた:
#         daily-science 175〜225 → 165〜195 字（推定 26.2〜30.3秒）
#         yokai-watch   175〜225 → 165〜195 字（推定 26.5〜30.7秒）
#         scp-lab       165〜210 → 160〜195 字（推定 26.5〜31.5秒）
#
#    company-facts は据え置き（165〜210字＝33.7〜42.0秒）。当chだけは
#    尺三分位で 52秒 群が 登録0.64 と最良（41秒群 0.46）で、維持率の肩も
#    50%地点 0.59 と 6ch 中で突出して高く、短尺化が逆効果になるため。
#
#  【C】15〜25% の「崖」対策を打ち切った（5回改訂して効果ゼロ）
#
#    retention_curve n=509 を公開日で3期に分け、10%→25%地点の落差を
#    ch内中央値で比較:
#      daily-science 0.452(n76) → 0.433(n6) → 0.450(n5)
#      scp-lab       0.403(n40) → 0.375(n3) → 0.451(n3)
#      yokai-watch   0.407(n36) → 0.384(n5)
#      company-facts 0.395(n11) → 0.490(n3)
#      2ch-matome    0.438(n22) → 0.514(n5)
#    5ch のいずれも改善せず、2ch は悪化。09-07 以降「2行目に実数を置く」
#    改訂を5回重ねましたが、崖は全ch・全期間で 0.38〜0.51 のまま動きません。
#    ショート視聴者の通常の離脱プロファイルであって台本の欠陥ではないと
#    判断し、この方向の改訂は本日で終了します。
#    （維持率四分位 → 登録/千再生 が 0.317/0.667/0.788/0.674 と非単調で、
#      そもそも維持率は登録を説明しない、という既存の結論とも整合します）
#
#  【D】2ch-matome を 3枠/日 → 1枠/日（17:30 のみ）に縮小
#
#    成熟コホートの 登録/千再生 0.189 は 6ch 最下位で scp-lab の 0.22倍。
#    公開後4日時点の週次コホートでは
#      高評価率 08/03週 0.22% → 09/07週 0.11%（半減）
#      登録/千  09/07週 0.00（n=6）
#      再生     1356 → 738（-46%）
#    さらに当chだけ「高評価率が高い群のほうが登録/千が低い」(0.41倍) と
#    逆転していて、他5chで5回再現している関係が成立しません。08-08 以降の
#    型変更5回でも反転しませんでした。
#    → 1本に絞って検証を続けます。**他chへの増枠はしません**（増枠が
#      リーチを比例して増やす証拠が無く、今日は希釈リスクを取らない）。
#    復帰条件: 1枠運用で 登録/千再生 が2週連続 0.4 以上。
#
#  ─────────────────────────────────────────────────────────────────
#  ★ 変更していないもの（理由つき）
#    ・テーマキュー補充: 在庫 6.5〜12.3 日あり不足なし（本日 dispatch-proxy-13
#      によるコンセプト外テーマの隔離が別途実施済み）。水増し補充はしない。
#    ・投稿時刻: 今日の変更（尺・枠）と交絡するため据え置き。
#    ・voice_style: 崖対策の打ち切りに伴い、維持率を理由とした調整はしない。
#    ・company-facts の帯: 上記 B のとおり当chだけ長尺が優位のため据え置き。
#      （ただし当chは高評価率 0.42%→0.28%、登録/千 0.86→0.42 と低下中。
#        尺ではなく高評価CTA側の問題として 09-25 に再評価する）
#  =====================================================================

set -u
cd "$(dirname "$0")" || exit 1
REPO="$(pwd)"
echo "================================================================"
echo " YouTube Factory 指揮者 2026-09-18"
echo " repo: $REPO"
echo "================================================================"

# ---------------------------------------------------------------
# 1. backend の稼働確認（起動していなければ再起動を促すだけ）
# ---------------------------------------------------------------
echo ""
echo "▶ backend 稼働確認 ..."
if curl -s -m 5 -o /dev/null -w "" http://localhost:8000/health 2>/dev/null; then
  echo "  ✅ backend は稼働中"
else
  echo "  ⚠️ backend が応答しません。先に restart-backend.command を実行してください。"
  echo "     （このスクリプトは backend を落としません）"
  read -n 1 -s -r -p "  何かキーを押すと終了します..."
  exit 1
fi

# ---------------------------------------------------------------
# 2. コンフィグ再読込
#    09-17 に入れた reload フックにより、指揮者がファイルを直接書いても
#    autopilot スケジューラへ自動同期されるはず。念のため health を叩いて
#    ChannelManager の _refresh_if_changed を発火させる。
# ---------------------------------------------------------------
echo ""
echo "▶ コンフィグ反映確認 ..."
curl -s -m 10 http://localhost:8000/api/channels 2>/dev/null \
  | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
except Exception:
    print('  (channels API の形式を読めませんでした。スキップします)'); sys.exit(0)
items = d if isinstance(d,list) else (d.get('channels') or d.get('items') or [])
for it in items:
    if not isinstance(it,dict): continue
    cid=it.get('id') or it.get('channel_id')
    if cid=='2ch-matome':
        ap=it.get('autopilot') or {}
        ts=(ap.get('schedule') or {}).get('times') or ap.get('times') or []
        print(f'  2ch-matome 枠数={len(ts)} (期待値 1)  enabled={ap.get(\"enabled\")}')
" 2>/dev/null || echo "  (確認をスキップしました)"

# ---------------------------------------------------------------
# 3. 制作指示（moviepy 系）
#    pokemon-lab は OAuth 失効中のため対象外。
#    clip-lab（凍結）/ akashic-librarian（OAuth未連携）も対象外。
# ---------------------------------------------------------------
CHANNELS=(daily-science scp-lab yokai-watch company-facts 2ch-matome)

echo ""
echo "▶ 制作指示を送ります: ${CHANNELS[*]}"
echo "  （pokemon-lab は OAuth 失効中のためスキップ）"
echo ""

for ch in "${CHANNELS[@]}"; do
  printf "  %-16s ... " "$ch"
  code=$(curl -s -m 120 -o /tmp/yt_trig_$ch.json -w "%{http_code}" \
         -X POST "http://localhost:8000/api/autopilot/${ch}/trigger" 2>/dev/null)
  if [ "$code" = "200" ] || [ "$code" = "202" ]; then
    echo "✅ 受理 (HTTP $code)"
  else
    echo "❌ HTTP $code"
    head -c 300 /tmp/yt_trig_$ch.json 2>/dev/null; echo ""
  fi
  sleep 3
done

echo ""
echo "================================================================"
echo " 完了。次の指揮者実行までに、上の【1】【2】をお願いします。"
echo "   【1】https://www.youtube.com/verify で電話確認（サムネ403の解除）"
echo "   【2】pokemon-lab の OAuth 再認可"
echo "================================================================"
echo ""
read -n 1 -s -r -p "何かキーを押すと閉じます..."
