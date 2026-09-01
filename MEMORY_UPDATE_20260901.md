# メモリ更新差分 — 2026-09-01（youtube-orchestrator 定期実行）

> ⛔ `~/.auto-memory/` は接続フォルダ外のため直接書き込めなかった（08-31 と同じ）。
> 接続済みは `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つ。
> 恒久対応として `~/.auto-memory` を Cowork の接続フォルダに追加するのが早い。

---

## project_youtube_factory.md 反映分

### 運用上の確定事項（今後の判断基準にする）

- **登録者を増やすレバーは高評価率であり、終盤維持率ではない。**
  n=322 の高評価率4分位 × 登録/1000再生 = 0.17 / 0.32 / 0.53 / 1.07（単調・最下位の6.3倍）。
  終盤維持率(90-100%)は 0.41 / 0.26 / 0.42 / 0.30 で**無相関**。
  チャンネルJSONに残っていた旧記録「2.16倍」は過小評価だったため、全6chで6.3倍に更新済み。
  → 「維持率を上げれば登録が増える」という仮説は今後採用しない。

- **チャンネル別の登録転換（14日・channel_metrics）**
  scp-lab 0.82 ＞ daily-science 0.59 ＞ yokai-watch 0.29 ＞ pokemon-lab 0.24 ＞ 2ch-matome 0.12。
  2ch-matome は最も再生を集める（14日で24,198）が最も登録に繋がっていない。最優先の改善対象。

- **台本の「実体」はフルシナリオではなくショートシナリオ節。**
  scenario の .md には `## ショートシナリオ` と `## フルシナリオ（セクション別）` があり、
  ショートに実際に載るのは前者。08-31 に「CTA遵守100%」と読めたのは後者を見ていたため。
  遵守率を測るときは必ず `## ショートシナリオ` 節の最終行を見ること（`scripts/verify_cta_20260901.py` がそれをやる）。

- **`cta_rotator` / `replay_loop_seeder` は 13ch中12ch で無効**（`script_enhancers.disabled`）。
  有効なのは 2ch-matome のみ（`script_enhancers` ブロック自体が無いため既定で有効）。
  → これらのモジュールを直しても他の12chには反映されない。この罠に08-31も今回もかかった。

- **style によってレンダリング経路が違う。**
  `facts_overlay`（company-facts）/ `monologue`（akashic-librarian, socio-rx）/ `yukkuri`（その他）。
  ショート共通の処理は**必ず style 分岐より前**に置くこと。yukkuri分岐の中に置くと
  company-facts だけ対象外になる。08-30 の尺ガード、今回のCTA強制ともこの失敗をした。

### 本日の変更

| 種別 | 内容 |
|---|---|
| 新規 | `backend/pipeline/cta_enforcer.py` — ショート最終行に「高評価→登録」を決定論的に保証。ループ誘導句除去・シリーズ重複解消・上限100字。 |
| 接続 | `video_generator.py` の **style分岐/archiveより前**で呼ぶ。archiveが補正後になるため遵守率を実測できる。 |
| 強化 | `scenario_validator.py` に `LIKE_PATTERNS` 追加、`_check_cta` を高評価+登録の両方必須へ。 |
| テスト | `backend/tests/test_cta_enforcer.py` 57件。 |
| 設定 | 6ch×2ディレクトリ: yokai-watch の `8行目`→`6行目`、根拠を6.3倍へ、`cta_fallback` 追加、company-facts の6行目と画面CTAカード修正。 |
| 生成物 | `reports/youtube_analysis_20260901.xlsx`（5シート・数式1,542件エラー0）、`pdca_summary_0901.md`、`restart_and_trigger_20260901.command`、`scripts/verify_cta_20260901.py`、`scripts/apply_pdca_20260901.py`、`scripts/build_report_20260901.py` |

### 未解決ブロッカー

1. **company-facts が `video_metrics` に1本も取り込まれていない**（`video_reach_daily` には24本ある）。
   実績が測れないチャンネルが1つある状態。取り込み経路の調査が必要。
2. `scenario_validator` は基礎点50・減点最大-25・閾値60のため、CTA欠落でも生成を止めない。
   無人実行で閾値を上げると生成本数がゼロになる恐れがあり、意図的に据え置いた。
   強制は `cta_enforcer` 側（決定論的）で担保している。
3. clip-fukada / clip-kaneko の OAuth リフレッシュトークン revoked、`client_secret.json` 不在（08-31 から未解消）。

## 作業環境について（毎回引っかかるので記録）

- **指揮者のサンドボックスから Mac の `localhost:8000` には到達できない。**
  `host.docker.internal` / `host.lima.internal` / `192.168.65.254` いずれも経路なし。
  Phase 4 の制作指示は `.command` ファイルとして生成し、ユーザーが実行する運用にしている。
- `reports/` の `.~lock.*.xlsx#` はサンドボックスから削除できない（Operation not permitted）。
  LibreOffice 再計算がハングする原因になるため、xlsx は `/tmp` にコピーして再計算し、
  結果を書き戻す手順が確実。
- sandbox には `moviepy` / `fastapi` が無いので、`video_generator.py` や api モジュールは
  import できない。構文確認は `py_compile`、ロジック確認は pipeline 単体モジュールで行う。

## 次サイクルで最初にやること

```bash
python3 scripts/verify_cta_20260901.py 2026-09-01   # 期待値: 両方100%（基準 19%）
grep '📣 CTA補正' logs/backend.log | tail -20
```

1週間後の目標: 全体の高評価率 0.404% → 0.6%、登録/1000再生 0.43 → 0.7、2ch-matome の高評価率 0.253% → 0.40%。
