#!/bin/bash
# =====================================================================
#  YouTube Factory 指揮者 — 2026-09-17 実行スクリプト
#
#  指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ到達
#  できない。Phase 4（制作指示）はこのスクリプトを Mac 上でダブルクリック
#  して実行する必要がある。
#
#  ★★ 今日いちばん大事なこと ★★
#  【バグを1件直した。反映には backend 再起動が必須。】
#    2ch-matome は 09-16 の指揮者が autopilot.enabled=true に直しているのに、
#    09-13 以降 1 度も発火していない（logs/backend.log の "Autopilot fired" に
#    2ch-matome が 09-13 11:30 を最後に出てこない）。
#
#    原因: ChannelManager は data/channels/*.json のディスク変更を検知して
#    メモリを読み直すが（_refresh_if_changed）、APScheduler のジョブは
#    _refresh_channel_job でしか変わらず、それは
#      (a) 起動時の restore_all()
#      (b) autopilot API 経由の書き込み
#    の2経路からしか呼ばれていなかった。指揮者はファイルを直接書くので、
#    どちらも通らない。つまり **指揮者が書いた enabled / schedule.times は
#    backend を再起動するまで一切効かない**。09-14 に入れた 2ch-matome の
#    投稿枠移設（9:00/21:00 → 7:30/17:30）も、同じ理由で効いていない。
#
#    修正: ChannelManager にリロードフックを追加し（add_reload_hook）、
#    ディスク由来の読み直し直後に autopilot のスケジューラを同じ内容へ
#    同期させた。autopilot の中身が実際に変わったときだけ add_job する
#    （指紋比較。毎回登録すると next_run_time が押し出されるため）。
#      backend/channels/channel_manager.py  … フック機構
#      backend/api_channel_autopilot.py     … _on_channel_config_reloaded を登録
#    ※ この修正自体を読み込ませるために、今回だけは再起動が要る。
#      以降は指揮者がファイルを書いた時点で自動的に反映される。
#
#  ★ 今日のコンフィグ変更（すべて ch 内対照の実測。n と倍率つき）
#    コーパス: 公開 2026-08-15〜09-10 / 300再生以上 / 195本 / 指標 = 登録者÷千再生
#
#    「答え提示語」を、実測で勝っている語へ ch ごとに付け替えた。
#    横断ゲートの答え提示語上限は 6本/日なので「なぜ」主軸は 2ch までに収めた。
#
#    daily-science : repair_with ["正体"] → ["なぜ","正体"]
#                    なぜ 0.675(n=27) vs 非該当 0.203 = 3.33倍。正体は 0.92倍で中立だった。
#                    ★さらに「なぜ〜？」0.658(n=26) vs 「なぜ〜のか」0.275(n=13) = 2.4倍。
#                      09-11 に全ch共通で入れた【最優先】「なぜ〇〇なのか」型は
#                      当chでは逆効果なので、短い疑問符止めへ読み替えさせた。
#    yokai-watch   : repair_with ["正体","わけ","理由"] → ["なぜ","正体"]
#                    なぜ 1.375(n=7) = 3.99倍 / 正体 0.788(n=6) = 1.60倍。
#                    ★「理由」は 0.195(n=7) vs 0.748 = 0.26倍の明確な負け語で、
#                      それが repair_with に入っていた。words からも除外した。
#    scp-lab       : repair_with ["真相","裏側","実態"] → ["理由","なぜ"]
#                    理由 1.496(n=4) = 2.17倍 / なぜ 1.226(n=11) = 2.25倍。
#                    旧3語はいずれも n<3 で実測の裏付けが無かった。
#    company-facts : repair_with ["実態","裏側"] → ["実は","裏側"]
#                    実は 0.963(n=11) = 2.04倍 / 裏側 0.840(n=7) = 1.36倍。
#                    ★「実態」は 0.362(n=11) vs 0.776 = 0.47倍の負け語で、第一に置かれていた。
#    2ch-matome    : repair_with ["理由","わけ"] → ["理由","なぜ"]
#                    理由 7.75倍 / なぜ 6.20倍 / 正体 0.000(n=3) は words から除外。
#
#    ※ 負け語を words から外したことで不適合になった既存テーマ 10 件は、
#      題材を変えずに勝ち語へ言い換え済み（例「コストコの利益が会費で決まる実態」
#      →「コストコの利益、実は会費で決まる」）。
#
#    【全5ch共通】視聴維持の離脱は尺の 12〜25% に集中していた。
#      early 0.0217〜0.0247 に対し middle 0.0047〜0.0055（約4〜5倍）、
#      intro 0.0096〜0.0128 よりも大きい。冒頭3秒は持っていて、本題直後で切られている。
#      離脱行はいずれも「たとえるなら〜」で始まる2文つなぎの長行だった。
#      → short_format.retention_rule_20260917 に、この区間は1行1文・たとえ話禁止・
#        新事実を必ず1つ、という制約を入れた。
#
#    【daily-science】投稿枠 16:30 → 19:00。
#      本スクリプト作成より前の同日実行が 7:30 → 16:30 へ移していたが、16:30 は 17:00 枠と
#      30分しか離れていない。publish_lead_minutes=45 なので生成発火は 15:45 と 16:15 の
#      30分差となり、連投ガード（_MIN_FIRE_INTERVAL_MINUTES=90）で **毎日どちらか1本が
#      黙って捨てられる**。backend/tests の test_autopilot_slots_respect_the_burst_guard も
#      これを検出していた。夕方が強いという判断自体は実測どおり（当ch 17時台 0.766・n=19 が
#      最良）なので撤回せず、19:00 へ移して 15:00 / 17:00 / 19:00 の 120分間隔に揃えた。
#
#    【全5ch共通】維持率を目的関数にしないことを明記した。
#      維持 75.6% で登録0人、維持 122.8% で登録0人、維持 22.8% で 5.63 の本がある。
#      維持率は「離脱の原因を探す道具」であって、最適化の対象ではない。
#
#  ★ 検証済み
#    backend/tests: 着手前 653 passed / 11 failed → 変更後 654 passed / 10 failed。
#    解消2件（1979年のハードルール違反 / 16:30 の連投ガード違反）、新規失敗ゼロ。
#    残る10件のうち9件は sandbox に moviepy・PIL が無い環境起因（変更前から同じ）。
#    残り1件（scp-lab の blacklist に SCP-173 が無い）は git HEAD 時点でも同じで、
#    今日の変更が原因ではない。設定ドリフトとして次回に持ち越す。
#    リロードフックは専用テストで、ディスク変更時のみ1回発火し、
#    フック内 get() で再入しないことを確認した。
#    xlsx は 数式72本・エラー0 で recalc 済み。
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")" || exit 1

BASE="http://localhost:8000"
# pokemon-lab は OAuth 失効中（後述）のため、今日も対象外にしている。
# clip-lab は凍結中、akashic-librarian は OAuth 未連携でスキップ。
ACTIVE_CH=(daily-science scp-lab yokai-watch company-facts 2ch-matome)

echo "================================================================"
echo " YouTube Factory 指揮者 — 2026-09-17"
echo "================================================================"
echo

# ---------------------------------------------------------------------
# 1. バックエンド再起動（スケジューラ同期バグの修正を読み込ませるため必須）
# ---------------------------------------------------------------------
echo "[1/5] バックエンド再起動..."
if [ -x ./restart-backend.command ]; then
  ./restart-backend.command || echo "  ⚠️ 再起動スクリプトが異常終了しました（続行します）"
else
  echo "  ⚠️ restart-backend.command が見つかりません。手動で再起動してください。"
fi
echo "  ...起動待ち 20秒"
sleep 20

# ---------------------------------------------------------------------
# 2. ヘルスチェック
# ---------------------------------------------------------------------
echo
echo "[2/5] ヘルスチェック..."
CODE="000"
for i in $(seq 1 10); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$BASE/health" || echo "000")
  if [ "$CODE" = "200" ]; then echo "  ✅ backend 応答 OK"; break; fi
  echo "  ...待機中 ($i/10) code=$CODE"; sleep 5
done
if [ "$CODE" != "200" ]; then
  echo "  ❌ backend が応答しません。以降はスキップします。"
  echo "     start_server.command を手動で実行してから再実行してください。"
  exit 1
fi

# ---------------------------------------------------------------------
# 3. ★最重要★ 2ch-matome のジョブが登録されたか確認
# ---------------------------------------------------------------------
echo
echo "[3/5] 2ch-matome の autopilot ジョブ登録を確認..."
echo "  （今日直したバグが効いていれば、ここに 07:30 / 12:15 / 17:30 が出る）"
if grep -aq "Autopilot scheduled for 2ch-matome" logs/backend.log 2>/dev/null; then
  tail -400 logs/backend.log | grep -a "Autopilot scheduled for 2ch-matome" | tail -3 \
    || echo "  ⚠️ 直近ログに登録行が見つかりません"
else
  echo "  ⚠️ ログを確認できませんでした"
fi
echo
echo "  起動時サマリ:"
tail -400 logs/backend.log 2>/dev/null | grep -a "Autopilot restored" | tail -1 \
  || echo "  ⚠️ restore サマリが見つかりません"

# ---------------------------------------------------------------------
# 4. 制作指示
# ---------------------------------------------------------------------
echo
echo "[4/5] 制作指示（稼働中5ch）..."
OK=0; NG=0
for ch in "${ACTIVE_CH[@]}"; do
  printf "  %-16s ... " "$ch"
  RESP=$(curl -s -m 180 -X POST "$BASE/api/autopilot/$ch/trigger" \
           -H "Content-Type: application/json" -d '{}' 2>&1)
  if echo "$RESP" | grep -qiE '"(ok|success)"[[:space:]]*:[[:space:]]*true|job_id|queued|started'; then
    echo "✅"; OK=$((OK+1))
  else
    echo "❌  $(echo "$RESP" | head -c 200)"; NG=$((NG+1))
  fi
  sleep 3
done

# ---------------------------------------------------------------------
# 5. OAuth 健康診断
# ---------------------------------------------------------------------
echo
echo "[5/5] OAuth トークン健康診断..."
if [ -f scripts/oauth_health_check.py ]; then
  python3 scripts/oauth_health_check.py 2>/dev/null || echo "  ⚠️ 診断スクリプトが実行できませんでした"
else
  python3 - <<'PYEOF' 2>/dev/null || echo "  ⚠️ 診断できませんでした"
import sqlite3, datetime
now = datetime.datetime.now()
c = sqlite3.connect('data/youtube_tokens.db')
for ch, upd in c.execute("select channel_id, updated_at from oauth_tokens order by updated_at"):
    try:
        u = datetime.datetime.fromisoformat(str(upd).replace('Z', ''))
    except Exception:
        continue
    d = (now - u).total_seconds() / 86400
    mark = '失効' if d > 7 else ('まもなく失効' if d > 5.5 else 'OK')
    print(f'  {ch:20} 最終更新 {u:%m-%d %H:%M}  経過 {d:4.1f}日  {mark}')
PYEOF
fi

echo
echo "================================================================"
echo " 完了: 成功 $OK ch / 失敗 $NG ch"
echo "================================================================"
echo
echo "▼ 生成後に目視で確認すること（本日の変更の合否）"
echo "  1. daily-science のタイトルが「なぜ〜？」の短い疑問符止めになっているか"
echo "     （「なぜ〜のか」の長い形になっていたら、この変更は効いていない）"
echo "  2. yokai-watch のタイトルから「理由」が消え「なぜ」が入っているか"
echo "  3. company-facts のタイトルから「実態」が消え「実は」が入っているか"
echo "  4. 全chの台本の 7〜12 行目が 1行1文で、たとえ話が入っていないか"
echo
echo "▼ 反証の期限: 2026-09-24（1週間）"
echo "  (a) 付け替えた答え提示語の ch 内 登録/千再生 が、旧語の実績を下回れば戻す"
echo "  (b) daily-science の「なぜ〜？」型が 0.658 を下回れば「なぜ〜のか」へ戻す"
echo "  (c) early バケットの離脱率が 0.022 を下回らなければ、行分割は無効として撤回"
echo
echo "▼ 積み残し（指揮者では解決できない・ユーザー操作が必要）"
echo "  ★1. pokemon-lab の OAuth 再認可（09-10 07:43 が最終更新＝7.1日経過で失効）"
echo "       09-15・09-16 の公開実績は 0 本。autopilot は enabled=false にしてあるので"
echo "       レンダリングの無駄は出ていないが、チャンネルは完全に止まっている。"
echo "  ★2. Google OAuth 同意画面を「テスト」→「本番」へ切り替える"
echo "       テストのままだとリフレッシュトークンの寿命は 7 日。"
echo "       09-16 22:30 に更新された 5ch は、このままだと 09-23 前後にまた一斉に止まる。"
echo "       これが今もいちばん効く一手で、人手でしか実行できない。"
echo "  3. 失効したまま放置の 6ch: clip-animal(10.5日) fake-paper(10.0日)"
echo "     akashic-librarian(9.8日) clip-fukada/clip-kaneko/clip-lab(8.5日)"
echo "     いずれも autopilot=false なので無駄は出ていないが、復帰には再認可が要る。"
echo "  4. yokai-watch / company-facts / pokemon-lab は retention_curve が 1 本も"
echo "     保存されておらず、離脱分析ができない。yokai-watch は登録転換が全ch最良"
echo "     (1.312) なのに、なぜ効いているのかを維持率側から検証できていない。"
echo
