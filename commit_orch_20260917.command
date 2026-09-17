#!/bin/bash
# =====================================================================
#  YouTube Factory 指揮者 — 2026-09-17 config コミット
#
#  指揮者(サンドボックスVM)から git commit できなかったため、
#  Mac 側でこのファイルをダブルクリックして実行してください。
#
#  原因: .git/HEAD.lock が 2026-09-16 23:17 の時点で size 0 のまま
#        残っている（前夜の git プロセスが異常終了した残骸）。
#        VM 側のマウントは自分が作っていないファイルを unlink できず
#        （Operation not permitted）、ロックを外せませんでした。
#
#  config の変更そのものは data/channels/*.json に書き込み済みです。
#  未実施なのは「git へのコミット」だけです。
# =====================================================================
set -u
cd "$(dirname "$0")" || exit 1

echo "▼ 残骸ロックを削除します"
ls -la .git/HEAD.lock 2>/dev/null && rm -f .git/HEAD.lock
ls -la .git/index.lock 2>/dev/null && rm -f .git/index.lock

echo
echo "▼ 変更内容"
git status --short data/channels/ scripts/ reports/

echo
echo "▼ コミットします"
git add \
  data/channels/scp-lab.json \
  data/channels/daily-science.json \
  data/channels/yokai-watch.json \
  data/channels/company-facts.json \
  data/channels/2ch-matome.json \
  data/channels/socio-rx.json \
  scripts/orch_data_20260917.py \
  scripts/orch_apply_20260917.py \
  scripts/orch_apply_20260917b.py \
  scripts/orch_xlsx_build_20260917.py \
  reports/orch_config_changes_20260917.json \
  reports/_orch_20260917_data.json \
  reports/youtube-analysis-2026-09-17.xlsx

git commit -F - <<'MSG'
指揮者 2026-09-17: 投稿枠・タイトルゲートを09-16スナップショットの実測で更新

根拠（すべて 2026-09-16 スナップショット・稼働5ch・views>=200・公開08-01以降）:
- 疑問型（なぜ/のか/？）が ch内対照で 4/4ch すべて自ch平均超。ch内一致が
  測定可能な全chで取れたタイトル指標は初。プールでも 0.708(n=65) vs 0.499(n=118)。
  比較: 正体/真相 1/4ch・実は 2/3ch・理由/わけ 2/3ch はいずれも一致せず。
- 13時は ch固定効果で 3/3ch すべて自ch平均割れ（中央値0.50・加重0.42）＝全時刻最下位。
- 17時は 5/5ch で測定でき中央値1.67倍＝全時刻最良。
- 早朝6-10ブロックは 5ch中4chで最下位（プール 0.299(n=23) vs 夕 0.695(n=89)）。

変更:
- scp-lab       投稿枠 13:00 → 12:45 / theme_queue を疑問型優先へ並べ替え
- daily-science 投稿枠 07:30 → 19:00（当初16:30を適用したが連投ガード90分に抵触。
                並走runが19:00へ訂正。_schedule_changes を実態に訂正済み）
- 5ch           require_any_of.words に「のか」を追加（ゲートを緩める方向）。
                「…は何だったのか」等の実測最良パターンが answer-marker 違反として
                再生成に回されていた。キュー違反 scp-lab 5→4 / company-facts 4→2。
- company-facts キュー内の規約違反タイトルを事前修正（publish_blocked 予防）
- yokai-watch / socio-rx  変更しない理由を config に明記

変更しない判断:
- 2ch-matome の投稿枠・autopilotフラグ: 09-16 の再有効化が一度も発火しておらず
  効果測定が未成立（原因はスケジューラ未登録。並走runがコード修正済み・要再起動）
- OAuth失効7ch: スナップショットが09-06〜09-08で凍結。同一データでの二重判断を避ける

⚠️ 本日は並走 run と二重に Phase3 を実行した（マーカーファイル未設置のため検知不能）。
   変更は加算的で矛盾なしだが鉄則違反。スケジュール側で run を1本に寄せること。

検算: 全6ch で連投ガード最小間隔 >=90分 を確認（最小120分）/ JSON妥当性 OK
MSG

echo
echo "▼ 結果"
git log --oneline -3
echo
echo "完了しました。ウィンドウを閉じて構いません。"
