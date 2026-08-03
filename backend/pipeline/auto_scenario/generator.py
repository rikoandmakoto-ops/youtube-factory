"""
ScenarioGenerator — GPT APIでシナリオを自動生成

Usage:
    from channels import ChannelManager
    from pipeline.auto_scenario import ScenarioGenerator

    cm = ChannelManager()
    ch = cm.get("daily-science")
    gen = ScenarioGenerator(api_key="sk-...")

    # theme_seedsからランダム選択して生成
    result = gen.generate(ch)
    # result = {"title": "...", "short_scenario": [...], "full_scenario": [...], "thumb_info": {...}}

    # 特定テーマ指定
    result = gen.generate(ch, theme_override={"title": "なぜ宝くじを買う人がいるのか", "angle": "プロスペクト理論"})
"""

import json
import os
import random
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from pipeline import openai_compat

try:
    from pipeline import api_usage
except ImportError:  # pragma: no cover — running as a script
    api_usage = None

try:
    from pipeline import claude_client
except Exception:  # pragma: no cover — module not yet importable
    claude_client = None  # type: ignore

# GPT models. Main scenario uses gpt-5.6-terra (long-form Japanese, strict length rules)。
# gpt-4.1 系からの更新 (2026-08-02)。terra は 5.6 系の中間モデルで、
# コスト($2.50/$15 per M tokens)と指示追従（尺・行数・タイトル規則）のバランスが良い。
# Theme suggestion uses gpt-5.6-luna (最安・最速、短い JSON なので品質リスク低)。
GPT_MODEL = "gpt-5.6-terra"
GPT_MODEL_LIGHT = "gpt-5.6-luna"
CLAUDE_MODEL = "claude-sonnet-4-6"  # 旧 claude-sonnet-4-20250514 は廃止され 404 (2026-06-18)

# テーマ重複の「生成ブロック」しきい値。既存動画/過去シナリオのタイトルと
# この類似度以上なら「実質同じ動画」とみなし、別テーマに差し替える。
# theme_dedup の既定(0.55) より緩く設定 — 切り口違いの正常な連作まで潰さず、
# ほぼ同一のタイトル量産（SCP-173 の 23 連投・録音の声/酸素消失 の重複）だけを弾く。
# PDCA レポートの提案（2026-07-25）に基づき、類似テーマの再生産をより厳格に
# ブロックするため 0.7 → 0.8 に引き上げた。
THEME_DUP_BLOCK_THRESHOLD = 0.8

# 生成後タイトルの「自動リジェクト」しきい値。テーマ段のゲート
# (THEME_DUP_BLOCK_THRESHOLD) を通っても、LLM が出す最終タイトルが既存動画と
# ほぼ同一になるケースがある（レポートの重複ペアはこの最終タイトル同士）。
# ここを超えたらタイトルだけを作り直す。テーマ段より高いのは意図的で、
# シナリオ本体は既に生成済みのため「ほぼ確実に同じ動画」だけを対象にする。
TITLE_DUP_REJECT_THRESHOLD = 0.9


class ScenarioGenerator:
    """GPT APIを使ったシナリオ自動生成"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        # Set by callers to attribute usage to a channel
        self._current_channel_id: Optional[str] = None
        self._current_purpose: Optional[str] = None

    def _call_gpt(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 8000,
                  model: Optional[str] = None, max_retries: int = 4) -> str:
        """GPT API呼び出し。

        429 (rate limit) / 5xx (一時障害) は指数バックオフでリトライする。
        OpenAI が `Retry-After` ヘッダを返した場合はそれを優先して待つ。
        リトライを使い切ったら最後の例外を送出する（呼び出し側で Claude フォールバック等）。
        """
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

        use_model = model or GPT_MODEL
        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps(openai_compat.build_chat_payload(
            use_model, messages, temperature=temperature, max_tokens=max_tokens))

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST",
                                         headers={
                                             "Content-Type": "application/json",
                                             "Authorization": f"Bearer {self.api_key}",
                                         })
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                break
            except urllib.error.HTTPError as e:
                last_exc = e
                retryable = e.code == 429 or 500 <= e.code < 600
                if not retryable or attempt == max_retries - 1:
                    raise
                # Retry-After ヘッダ優先、無ければ指数バックオフ (5s,15s,45s...) + ジッタ
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(retry_after) if retry_after else 0.0
                except (TypeError, ValueError):
                    wait = 0.0
                if wait <= 0:
                    wait = 5.0 * (3 ** attempt) + random.uniform(0, 2.0)
                print(f"  ⏳ OpenAI {e.code} (attempt {attempt+1}/{max_retries}) — retrying in {wait:.0f}s")
                time.sleep(wait)
            except urllib.error.URLError as e:
                # ネットワーク一時障害も控えめにリトライ
                last_exc = e
                if attempt == max_retries - 1:
                    raise
                wait = 3.0 * (2 ** attempt) + random.uniform(0, 1.0)
                print(f"  ⏳ OpenAI network error (attempt {attempt+1}/{max_retries}): {e} — retrying in {wait:.0f}s")
                time.sleep(wait)
        else:  # pragma: no cover — break で抜ける想定
            raise last_exc or RuntimeError("OpenAI call failed")

        if api_usage is not None:
            usage = data.get("usage", {}) or {}
            try:
                api_usage.record_chat_usage(
                    model=use_model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    channel_id=self._current_channel_id,
                    purpose=self._current_purpose or "scenario",
                )
            except Exception as e:
                print(f"⚠️ usage recording failed: {e}")

        return data["choices"][0]["message"]["content"]

    def _call_claude_text(
        self,
        messages: List[Dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        model: Optional[str] = None,
    ) -> str:
        """Claude Messages API を OpenAI 風 messages 配列で呼んで応答テキストを返す。"""
        try:
            from anthropic import Anthropic  # type: ignore
        except Exception as e:
            raise RuntimeError(f"anthropic SDK not available: {e}")
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        # system は最初の system role を結合し、それ以外を messages に積む
        system_parts: List[str] = []
        user_assistant: List[Dict[str, str]] = []
        for m in messages:
            role = (m.get("role") or "").lower()
            content = m.get("content") or ""
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                user_assistant.append({"role": "assistant", "content": content})
            else:
                user_assistant.append({"role": "user", "content": content})
        system_full = "\n\n".join(p for p in system_parts if p) or "JSON のみ出力。"

        use_model = model or CLAUDE_MODEL
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=use_model,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            system=system_full,
            messages=user_assistant or [{"role": "user", "content": ""}],
        )

        # usage 記録
        if api_usage is not None:
            try:
                usage = getattr(resp, "usage", None)
                in_t = int(getattr(usage, "input_tokens", 0) or 0)
                out_t = int(getattr(usage, "output_tokens", 0) or 0)
                api_usage.record_chat_usage(
                    model=use_model,
                    prompt_tokens=in_t,
                    completion_tokens=out_t,
                    channel_id=self._current_channel_id,
                    purpose=self._current_purpose or "scenario_claude",
                )
            except Exception:
                pass

        parts: List[str] = []
        for block in getattr(resp, "content", []) or []:
            t = getattr(block, "text", None)
            if t:
                parts.append(t)
        return "".join(parts)

    def _call_text_with_fallback(
        self,
        messages: List[Dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        gpt_model: Optional[str] = None,
    ) -> str:
        """GPT を試し、失敗（429 リトライ枯渇・quota・障害）したら Claude にフォールバック。

        テーマ提案・意味重複判定など「短い JSON を返させる軽量タスク」用。
        Claude が即時フォールバックとして使えるので、GPT 側のリトライは少なめ
        (既定 2 回) に抑え、429 が続く時に長時間バックオフで待たされないようにする。
        どちらも使えない場合のみ例外を送出する。
        """
        gpt_retries = 2 if os.environ.get("ANTHROPIC_API_KEY", "").strip() else 4
        try:
            return self._call_gpt(messages, temperature=temperature, max_tokens=max_tokens,
                                  model=gpt_model, max_retries=gpt_retries)
        except Exception as gpt_err:
            print(f"  ⚠️ GPT call failed ({gpt_err}) — falling back to Claude")
            if not (os.environ.get("ANTHROPIC_API_KEY", "").strip()):
                raise
            return self._call_claude_text(messages, temperature=temperature, max_tokens=max_tokens)

    def _scenarios_dir_for(self, channel_id: str) -> Path:
        # generator.py → backend/pipeline/auto_scenario/ → backend/pipeline/ → backend/ → repo_root
        return Path(__file__).resolve().parent.parent.parent.parent / "data" / "scenarios" / channel_id

    def _collect_past_themes(self, channel_id: str, limit: int = 50) -> List[Dict[str, str]]:
        """過去に生成済みの scenario JSON からテーマ（title/angle）を新しい順に収集。"""
        base = self._scenarios_dir_for(channel_id)
        if not base.exists():
            return []
        past: List[Dict[str, str]] = []
        files = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            th = data.get("theme") if isinstance(data, dict) else None
            title = ""
            angle = ""
            if isinstance(th, dict):
                title = (th.get("title") or "").strip()
                angle = (th.get("angle") or "").strip()
            if not title and isinstance(data, dict):
                title = (data.get("title") or "").strip()
            if title:
                past.append({"title": title, "angle": angle})
        return past

    def _recent_theme_titles(self, channel_id: str, days: int = 30) -> set:
        """直近 days 日以内に生成した scenario JSON のテーマタイトル集合（normalize: lower+strip）。

        生成時刻はファイル mtime を代用する（scenario JSON に統一の生成時刻フィールドが無いため）。
        """
        base = self._scenarios_dir_for(channel_id)
        if not base.exists():
            return set()
        cutoff = time.time() - days * 86400
        titles: set = set()
        for f in base.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    continue
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            th = data.get("theme") if isinstance(data, dict) else None
            title = ""
            if isinstance(th, dict):
                title = (th.get("title") or "").strip()
            if not title and isinstance(data, dict):
                title = (data.get("title") or "").strip()
            if title:
                titles.add(title.lower())
        return titles

    def _existing_titles_for_dedup(self, channel_id: str, within_days: int = 90) -> List[str]:
        """テーマ重複判定の基準となる既存タイトル群を集める。

        3 系統をマージ（順序保持・重複除去）:
          1. 過去シナリオの theme.title（`past_theme_titles`）
          2. 過去シナリオの生成タイトル（バズるタイトル）— theme.title が同じでも
             実タイトルが割れているケースを両側から拾う。
          3. 公開済み動画のタイトル（analytics store）— レポート側 `_dup_check` と
             同じ published メトリクスを参照するので判定基準が揃う。
        """
        from pipeline.auto_scenario import theme_dedup as _td
        titles: List[str] = list(_td.past_theme_titles(channel_id, within_days=within_days))
        seen = {t.lower() for t in titles}

        def _add(t: str) -> None:
            t = (t or "").strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                titles.append(t)

        # 2) 過去シナリオの生成タイトル
        base = self._scenarios_dir_for(channel_id)
        if base.exists():
            cutoff = time.time() - within_days * 86400
            for f in base.glob("*.json"):
                try:
                    if f.stat().st_mtime < cutoff:
                        continue
                    data = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(data, dict):
                    _add(data.get("title") or "")

        # 3) 公開済み動画タイトル
        try:
            from pipeline.analytics import store as _store
            for v in (_store.list_video_metrics(channel_id, limit=200) or []):
                _add((v.get("title") or "") if isinstance(v, dict) else "")
        except Exception as e:
            print(f"  ⚠️ published-title fetch for dedup skipped: {e}")

        return titles

    def _channel_theme_blacklist(self, channel) -> List[str]:
        """チャンネルJSONのテーマ除外設定（`theme_blacklist`）を返す。

        値は「正規化後に部分一致したら弾く」語/フレーズの配列。過剰生産で
        止めたい題材（例: "SCP-173"、"録音した自分の声"）を運用側で明示指定する。
        `theme_priority.avoid_categories` は提案プロンプトへの注入で既に効いているため
        ここでは扱わない（カテゴリ説明文なので部分一致に不向き）。
        """
        raw = getattr(channel, "_raw", {}) or {}
        bl = raw.get("theme_blacklist") or []
        return [x.strip() for x in bl if isinstance(x, str) and x.strip()]

    def _channel_genre_blacklist(self, channel) -> List[str]:
        """チャンネルJSONの生成停止ジャンル（`genre_blacklist`）を返す。

        値は `pipeline.auto_scenario.genre` のジャンル名（日次 PDCA レポートの
        「テーマ（ジャンル）別の成績」に出る名前）の配列。レポートで平均再生が
        死んでいるジャンル（daily-science の「宇宙・天体」= 6本すべて0再生、
        scp-lab の「オブジェクトクラス」= 平均5再生）を運用側で止めるための設定。

        `theme_blacklist` が「個別の題材」を語句一致で弾くのに対し、こちらは
        「系統ごと」を分類器経由で弾く。両方に該当してもどちらかで落ちればよい。
        """
        raw = getattr(channel, "_raw", {}) or {}
        bl = raw.get("genre_blacklist") or []
        return [x.strip() for x in bl if isinstance(x, str) and x.strip()]

    def _genre_blacklisted_reason(self, channel_id: str, title: str,
                                  genre_blacklist: List[str]) -> Optional[str]:
        """title の分類ジャンルが genre_blacklist に含まれれば、そのジャンル名を返す。"""
        if not genre_blacklist:
            return None
        try:
            from pipeline.auto_scenario.genre import classify_genre
        except Exception as e:
            print(f"  ⚠️ genre blacklist skipped (classifier unavailable): {e}")
            return None
        g = classify_genre(channel_id, title)
        return g if g in genre_blacklist else None

    def _blacklisted_reason(self, title: str, blacklist: List[str]) -> Optional[str]:
        """title が blacklist のいずれかに（正規化部分一致で）該当すれば、その語を返す。"""
        if not blacklist:
            return None
        from pipeline.auto_scenario import theme_dedup as _td
        norm = _td.normalize_title(title)
        if not norm:
            return None
        for term in blacklist:
            nt = _td.normalize_title(term)
            if nt and nt in norm:
                return term
        return None

    def _dedupe_theme(self, channel, theme: Dict) -> Dict:
        """選択済みテーマが既存動画/過去シナリオと重複していれば別テーマへ差し替える。

        全生成経路の最終ゲート。`theme_override`（autopilot / run_*.py / batch）でも
        必ずここを通るので、generator 内の再抽選をバイパスする経路の重複量産を止める。

        判定:
          - チャンネルの theme_blacklist に一致 → 除外
          - チャンネルの genre_blacklist のジャンルに分類される → 除外
          - 既存タイトルとの類似度 >= THEME_DUP_BLOCK_THRESHOLD → 重複として除外
        差し替え順: suggest_themes（語彙/意味 dedup 込み）→ seed 再抽選。
        代替が見つからなければ元テーマのまま続行（投稿 skip より重複投稿の方がマシ）。
        """
        try:
            from pipeline.auto_scenario import theme_dedup as _td
        except Exception as e:
            print(f"  ⚠️ theme dedup guard disabled: {e}")
            return theme

        existing = self._existing_titles_for_dedup(channel.id)
        blacklist = self._channel_theme_blacklist(channel)
        genre_blacklist = self._channel_genre_blacklist(channel)

        def _reject_reason(title: str) -> Optional[str]:
            title = (title or "").strip()
            if not title:
                return None
            bl = self._blacklisted_reason(title, blacklist)
            if bl:
                return f"blacklist『{bl}』"
            gb = self._genre_blacklisted_reason(channel.id, title, genre_blacklist)
            if gb:
                return f"停止ジャンル『{gb}』"
            hit = _td.find_lexical_duplicate(
                title, existing, threshold=THEME_DUP_BLOCK_THRESHOLD)
            if hit is not None:
                return f"既存『{hit[0][:24]}』に類似({hit[1]:.2f})"
            return None

        reason = _reject_reason(theme.get("title"))
        if not reason:
            return theme

        print(f"  ♻️ Theme '{theme.get('title')}' rejected — {reason}. 別テーマを選び直します")
        tried = {(theme.get("title") or "").strip().lower()}

        # 1) AI 提案（内部で除外リスト+語彙+意味 dedup 済み）から重複しない最初の1件
        try:
            for s in (self.suggest_themes(channel, count=6) or []):
                if not isinstance(s, dict):
                    continue
                t = (s.get("title") or "").strip()
                if not t or t.lower() in tried:
                    continue
                tried.add(t.lower())
                if not _reject_reason(t):
                    print(f"  ✅ Replaced with AI-suggested theme: {t}")
                    return {
                        "title": t,
                        "angle": s.get("angle", "") or "",
                        "parent_title": s.get("parent_title"),
                    }
        except Exception as e:
            print(f"  ⚠️ AI theme replacement failed: {e}")

        # 2) seed 再抽選（過去回避つき）
        for _ in range(6):
            try:
                cand = self._pick_seed_avoiding_past(channel)
            except Exception:
                break
            t = (cand.get("title") or "").strip()
            if t and t.lower() not in tried and not _reject_reason(t):
                print(f"  ✅ Replaced with seed theme: {t}")
                return cand
            tried.add(t.lower())

        print(f"  ⚠️ 非重複の代替テーマが見つからず、元の '{theme.get('title')}' で続行します")
        return theme

    def _regenerate_title(self, channel, theme: Dict, forbidden: List[str],
                          scenario_data: Dict[str, Any]) -> Optional[str]:
        """既存タイトルと衝突した最終タイトルだけを作り直す（軽量モデル）。

        シナリオ本体は使い回すので、コストは1回の短い呼び出しのみ。
        `forbidden` には衝突相手を含む既存タイトル（上位のみ）を渡し、
        「この言い換えも禁止」と明示する。
        """
        hook_lines: List[str] = []
        for line in (scenario_data.get("short_scenario") or scenario_data.get("full_scenario") or [])[:4]:
            text = line.get("text") if isinstance(line, dict) else ""
            if text:
                hook_lines.append(str(text))
        forbid_block = "\n".join(f"  - {t}" for t in forbidden[:20]) or "  (なし)"
        prompt = (
            f"YouTubeショートのタイトルを1つだけ作り直してください。\n\n"
            f"# チャンネル\n{channel.name}（{channel.concept}）\n\n"
            f"# 動画のテーマ\n{theme.get('title', '')}\n"
            f"切り口: {theme.get('angle', '') or '(指定なし)'}\n\n"
            f"# 本編の冒頭\n" + ("\n".join(hook_lines) or "(なし)") + "\n\n"
            f"# 禁止タイトル（これらと同じ・言い換え・語順違いはすべて不可）\n{forbid_block}\n\n"
            f"# 条件\n"
            f"- 禁止リストとは**別の切り口・別の単語**で書くこと（同じ現象でも着眼点を変える）。\n"
            f"- 40文字以内。疑問型か意外性のある断定。結論は書かない。\n"
            f"- タイトル本文のみを出力（前置き・引用符・番号なし）。\n"
        )
        try:
            self._current_channel_id = channel.id
            self._current_purpose = "title_regen"
            raw = self._call_text_with_fallback(
                [
                    {"role": "system", "content": "タイトル1行のみ出力。説明・引用符は不要。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.95,
                max_tokens=200,
                gpt_model=GPT_MODEL_LIGHT,
            )
        except Exception as e:
            print(f"  ⚠️ title regeneration failed: {e}")
            return None
        title = (raw or "").strip().splitlines()[0].strip() if (raw or "").strip() else ""
        return title.strip("「」\"'　 ") or None

    def _reject_duplicate_title(self, channel, theme: Dict, result: Dict[str, Any],
                                scenario_data: Dict[str, Any]) -> None:
        """生成された最終タイトルが既存とほぼ同一なら自動リジェクトして作り直す。

        テーマ段のゲート（`_dedupe_theme`）を通っても、LLM が既存動画と実質同じ
        タイトルを出すことがある — PDCA レポートで 4 日連続 15 件出ていた重複ペア
        （類似 0.98〜1.0）はまさにこの最終タイトル同士の衝突だった。
        シナリオ本体は再利用し、タイトルだけを最大2回作り直す。
        どうしても解消しなければ元タイトルで続行し、`title_duplicate` に記録を残す
        （投稿を止めるより、重複を可視化して次回の PDCA で拾う方を選ぶ）。
        """
        try:
            from pipeline.auto_scenario import theme_dedup as _td
        except Exception as e:
            print(f"  ⚠️ title dedup guard disabled: {e}")
            return

        existing = self._existing_titles_for_dedup(channel.id)
        if not existing:
            return

        title = (result.get("title") or "").strip()
        hit = _td.find_lexical_duplicate(title, existing, threshold=TITLE_DUP_REJECT_THRESHOLD)
        if hit is None:
            return

        print(f"  🚫 生成タイトル '{title}' が既存『{hit[0][:28]}』と重複({hit[1]:.2f}) — 作り直します")
        forbidden = [hit[0]] + [t for t in existing[:20] if t != hit[0]]
        for attempt in range(2):
            cand = self._regenerate_title(channel, theme, forbidden, scenario_data)
            if not cand:
                break
            again = _td.find_lexical_duplicate(
                cand, existing, threshold=TITLE_DUP_REJECT_THRESHOLD)
            if again is None:
                print(f"  ✅ タイトルを差し替えました: {cand}")
                # AB テストが既に original_title を入れている場合は「最初のタイトル」を守る
                result.setdefault("original_title", title)
                result["title"] = cand
                result["title_duplicate"] = {
                    "resolved": True,
                    "rejected_title": title,
                    "matched": hit[0],
                    "score": round(hit[1], 3),
                }
                return
            print(f"  ↻ 再生成タイトルもまだ重複({again[1]:.2f}) — attempt {attempt + 1}/2")
            forbidden = [cand] + forbidden

        print(f"  ⚠️ 非重複タイトルを作れず、元の '{title}' で続行します")
        result["title_duplicate"] = {
            "resolved": False,
            "rejected_title": title,
            "matched": hit[0],
            "score": round(hit[1], 3),
        }

    def _pick_seed_avoiding_past(self, channel) -> Dict:
        """theme_seeds から過去に使ったものを除外して選ぶ。

        全シードが消化済みなら AI に新規（または発展系）を提案させ、そこから1件選ぶ。
        最終フォールバックは従来のランダム選択。

        競合動画タイトルとの語彙重なりが大きいシードは weight を下げて選ばれにくくする
        （完全排除はしない — 同じテーマでも切り口で差別化できるため）。
        """
        past_titles = {t["title"].lower() for t in self._collect_past_themes(channel.id, limit=80)}
        unused = [s for s in channel.theme_seeds if (s.get("title") or "").lower() not in past_titles]
        if unused:
            return self._weighted_seed_choice(channel, unused)
        try:
            suggestions = self.suggest_themes(channel, count=3)
            if isinstance(suggestions, list) and suggestions:
                pick = random.choice(suggestions)
                if isinstance(pick, dict) and pick.get("title"):
                    print(f"  💡 All seeds used — using AI-suggested theme: {pick['title']}")
                    return {"title": pick["title"], "angle": pick.get("angle", "") or ""}
        except Exception as e:
            print(f"  ⚠️ AI fresh-theme fallback failed: {e}")
        return self._weighted_seed_choice(channel, channel.theme_seeds)

    def _weighted_seed_choice(self, channel, seeds: List[Dict]) -> Dict:
        """競合動画と語彙が被るシードの weight を下げて選ぶ。

        競合データが空 / 取得失敗時は通常の random.choice にフォールバック。
        """
        if not seeds:
            raise ValueError("no seeds to choose from")
        if len(seeds) == 1:
            return seeds[0]
        try:
            from pipeline.analytics.competitor_intelligence import (
                competitor_video_titles, theme_overlap_score,
            )
            comp_titles = competitor_video_titles(channel.id)
        except Exception:
            comp_titles = []
        if not comp_titles:
            return random.choice(seeds)
        weights: List[float] = []
        annotated: List[Tuple[float, Dict]] = []
        for s in seeds:
            title = (s.get("title") or "") if isinstance(s, dict) else ""
            score = theme_overlap_score(title, comp_titles)
            # 0.0 (被りなし) → 1.0、0.5 以上 (高被り) → 0.25 まで下げる
            w = max(0.25, 1.0 - score)
            weights.append(w)
            annotated.append((score, s))
        try:
            picked = random.choices(seeds, weights=weights, k=1)[0]
        except Exception:
            return random.choice(seeds)
        if isinstance(picked, dict):
            picked_score = next(
                (sc for sc, s in annotated if s is picked), 0.0
            )
            if picked_score >= 0.3:
                print(
                    f"  ⚠️ Picked theme has competitor overlap {picked_score:.2f} — "
                    f"prompt will instruct on differentiation"
                )
        return picked

    def _next_video_hint(self, channel) -> str:
        """次回予告で提案するべきジャンル指示をチャンネルから抽出する。

        - 明示的に `next_video_genre_hint` が設定されていればそれを使う。
        - 未設定なら channel.theme_seeds のタイトルからサンプルを3つほど抽出して
          「このチャンネルの他テーマ」に閉じた次回予告を促す。
        - どちらも無ければ空文字（呼び出し側で適度なデフォルトを採用）。
        """
        try:
            explicit = (channel._raw or {}).get("next_video_genre_hint")
        except AttributeError:
            explicit = None
        if explicit:
            return explicit.strip()
        seeds = getattr(channel, "theme_seeds", None) or []
        titles = [s.get("title") for s in seeds if isinstance(s, dict) and s.get("title")]
        if titles:
            sample = "、".join(f"『{t}』" for t in titles[:3])
            return (
                f"次回テーマは必ず本チャンネルの世界観・ジャンルに閉じたものを選ぶ"
                f"（このチャンネルが扱う題材の例: {sample} など）。"
                f"チャンネルのジャンルから外れたテーマ（例: 日常科学・身近な雑学）は絶対に提案しない。"
            )
        return (
            f"次回テーマは必ず本チャンネル「{channel.name}」のコンセプト"
            f"（{channel.concept}）と地続きのジャンルに閉じて選ぶ。チャンネルのジャンルから外れたテーマは絶対に提案しない。"
        )

    def _persona_block(self, channel) -> str:
        """video_format.persona から差し込むプロンプトブロックを返す。

        未設定なら空文字。設定があれば「# ターゲット視聴者ペルソナ ...」を返す。
        後段の policy / 構成ルールより前に置く想定。
        """
        try:
            persona = channel.video_format.persona
        except AttributeError:
            return ""
        block = persona.to_prompt_block() if persona else ""
        return f"\n{block}\n" if block else ""

    def _voice_style_block(self, channel) -> str:
        """channel.voice_style からシナリオプロンプト冒頭に差し込むブロックを返す。

        未設定 / 空dict なら空文字（=従来通り）。設定があれば
        トーン・語り手ペルソナ・冒頭フック例・禁止要素をまとめた
        「# このチャンネルの語り口」ブロックを返す。
        """
        vs = getattr(channel, "voice_style", None) or {}
        if not vs:
            return ""
        lines = ["# このチャンネルの語り口（最優先・全文を通して厳守）"]
        tone = vs.get("tone")
        if tone:
            lines.append(f"- トーン: {tone}")
        persona = vs.get("narrator_persona")
        if persona:
            lines.append(f"- 語り手: {persona}")
        hooks = vs.get("opening_hooks") or []
        if hooks:
            sample = " / ".join(f"「{h}」" for h in hooks)
            lines.append(f"- 冒頭フック例（雰囲気を真似る・丸ごとコピペは不可）: {sample}")
        forbidden = vs.get("forbidden") or []
        if forbidden:
            lines.append(f"- 使用禁止ワード/要素: {', '.join(forbidden)}")
        style_rules = vs.get("style_rules") or []
        if style_rules:
            lines.append("- 厳守する語りのルール:")
            for r in style_rules:
                lines.append(f"  - {r}")
        return "\n".join(lines) + "\n\n"

    def _build_yukkuri_prompt(self, channel, theme: Dict, target_duration: int) -> str:
        """ゆっくり対話スタイルのシナリオ生成プロンプト"""
        char_names = list(channel.characters.keys())
        c0 = char_names[0]
        c1 = char_names[1] if len(char_names) > 1 else c0
        char_lines = "\n".join(f"- {n}: {cfg.get('role','')}" for n, cfg in channel.characters.items())

        policy_parts = []
        for g in channel.policy_guidelines():
            policy_parts.append(f"- {g}")
        for a in channel.policy_avoid():
            policy_parts.append(f"- 避ける: {a}")
        policy_text = "\n".join(policy_parts) if policy_parts else "(なし)"
        persona_block = self._persona_block(channel)
        next_video_hint = self._next_video_hint(channel)

        target_lines = max(58, min(64, round(target_duration / 12)))
        target_chars = int(target_duration * 8.0)
        max_chars = int(target_duration * 9.0)  # 上限: 約12分の音声を超えない
        floor_lines = 55
        floor_chars = 4800
        short_target_chars = 230  # 6行 × 平均38字 = 約30秒
        cta_style = channel.content_policy.get("cta_style", "casual")
        tone = channel.content_policy.get("tone", "friendly")
        expr0 = channel.characters[c0].get("expressions", ["normal"])
        expr1 = channel.characters[c1].get("expressions", ["normal"])

        voice_block = self._voice_style_block(channel)

        return f"""ゆっくり解説動画のシナリオを生成。JSONのみ出力。

{voice_block}# チャンネル: {channel.name} / {channel.concept} / トーン:{tone} / CTA:{cta_style}
# キャラ:
{char_lines}
# テーマ: {theme["title"]} / 切り口:{theme.get("angle","自由")}
{persona_block}# ポリシー:
{policy_text}

# 出力JSON
{{
 "title":"バズるタイトル",
 "thumb_info":{{"hook_lines":["1行","2行"],"subtitle":"...","tagline":"..."}},
 "short_scenario":[{{"speaker":"{c0}","text":"...","expression":"normal","mood":"bright"}}, ...全6行],
 "full_scenario":[{{"speaker":"{c0}","text":"...","expression":"normal","mood":"calm"}}, ...{floor_lines}〜{target_lines+4}行]
}}

# タイトルルール(超重要・CTR改善のため絶対厳守)
- ❌ NG: 「【ゆっくり解説】〇〇とは？」「【ゆっくり解説】〇〇の謎、解けます！」など「【ゆっくり解説】+結論」型は禁止。CTRが大幅に下がる。
- ❌ NG: 結論・答えをタイトルにバラす(例:「水たまりの謎、解けます！」)。
- ✅ OK: 「なぜアスファルトだけ？水たまりが『あそこ』にしかできない本当の理由」のように、答えではなく「なぜ？」という謎・違和感だけを置く疑問型・意外性重視。
- 「【ゆっくり解説】」のような定型プレフィックスは絶対に付けない。タイトル先頭にカギ括弧プレフィックスを付けない。
- 「本当の理由」「実は」「あそこ」「なぜか」「だけ」「〇〇すぎる」など意外性を匂わせるワードを必ず1つ以上入れる。
- 視聴者が「気になる、答えを知りたい」と感じる謎の提示で止めるのが正解。結論はサムネ・本編で初めて出す。

# 尺ルール(絶対厳守・違反は不合格)
- **full_scenarioは必ず{floor_lines}〜{target_lines+4}行**(目標{target_lines}行)。{floor_lines}行未満も{target_lines+5}行以上も不合格。
- **各行は90〜120字**(目標100字、上限120字)。89字以下も121字以上も不合格。
- **総文字数は{target_chars}〜{max_chars}字**(最低{floor_chars}字、上限{max_chars}字)。約{target_duration/60:.1f}分目標。
- 各行に研究データ・具体的数字・例え話・歴史エピソードを必ず盛る。短い相槌のみ(「うん」「そうだね」)禁止。
- VOICEVOX1.3x≒7.8字/秒。{target_chars}字で約{target_duration/60:.1f}分、{max_chars}字で約{max_chars/7.8/60:.1f}分。

# ショート尺ルール(絶対厳守)
- **short_scenarioは必ず6行**(1〜5行目は30〜45字目標38字、6行目のみ45〜70字を許容)。
- **総文字数は必ず{short_target_chars-30}〜{short_target_chars+50}字**(目標{short_target_chars+20}字)で**約30〜35秒**を実現。
- 構成(6行固定):
  1行目=**衝撃フック(0〜3秒で指を止める・最重要)**: 視聴者が「え?なにそれ?」と脳がバグる一言から始める。挨拶・自己紹介・テーマ説明・前置きは完全禁止(1文字でもあれば不合格)。短く断定的に(目安15〜30字)、まだ答えは言わず「続きが気になる」状態だけを作る。以下のいずれかの型を必ず使う:
    - 常識破壊型: 「実は〇〇、ぜんぶ間違いでした」「〇〇してる人、今すぐやめて」「〇〇は嘘です」
    - 衝撃数字型: 「99%の人が知らないんだけど」「たった3秒で〇〇が変わる話」「世界に〇人しかいない」
    - 禁断・警告型: 「これ言うと怒られるかもだけど」「閲覧注意。〇〇の正体」「知らない方が幸せだったかも」
    - 違和感の問い型: 「なんで〇〇だけ〇〇なの?考えたことある?」「〇〇、よく見ると変じゃない?」
  2行目=**追い打ちフック**: 1行目の謎をさらに煽るか、相手役が「えっ、どういうこと!?」と食いつくリアクションで視聴者の「気になる」を代弁する。ここでもまだ答えは出さない(情報を出し惜しみして"続きを見る理由"を作る)。
  3〜4行目=**核となる事実**: ここに**具体的な数字・年号・%・研究データ・固有名詞のいずれか1つ以上を必ず含める**(例:「実は97%の人が…」「1923年に…」「東大の研究で…」)。「へぇ!」と感心させる中身を入れる。抽象論・一般論だけはNG。
  5行目=**納得のオチ**: 短くスパッと結論。投げっぱなし禁止。
  6行目=**登録誘導+関連動画誘導CTA(必須・絶対省略禁止・順番厳守)**: 必ず「①チャンネル登録誘導 → ②関連動画誘導」の順で1行に2つのCTAを連結する。
    - ①登録CTA: 「チャンネル登録者1万人を目指して毎日投稿中なので、応援よろしくね!」のニュアンスを必ず入れる(「毎日投稿中」「1万人目標」「応援よろしく」の3要素で、視聴者の応援したい気持ちを引き出して登録率を上げる)。
    - ②関連動画CTA: 必ず「関連動画」というワードを含め、ショート離脱者を長尺へ送る(「本編」より「関連動画」を優先)。
    - 例:「チャンネル登録者1万人目指して毎日投稿中!応援よろしくね!もっと詳しい話は関連動画から見てね!」「1万人目指して毎日投稿中だから登録お願い!続きは関連動画でチェック!」
    - **6行目のみ45〜70字を許容**(2つのCTAを連結するため、通常の30〜45字制限を超えてよい)。
- 浅い感想・誰でも言える一般論(「すごいね」「びっくりだね」だけ)で行を埋めるのは不合格。1本のショートで最低1つは「初めて知った」と思わせる具体情報を入れること。

# 構成(full): 冒頭フック(3行) → 問題提起+本編宣言(3行) → 基本メカニズム(12行) → 詳細&研究データ(12行) → 意外な事実&歴史(10行) → 応用Tips(8行) → まとめ+次回予告+締めCTA(7行) = 計55行(目標{target_lines}行に届くまで各セクションを伸ばす)

# 冒頭フックルール(超重要・冒頭5秒離脱対策・絶対厳守)
- ❌ NG: 「みなさんこんにちは」「今日は〇〇について解説します」「ゆっくり霊夢です」など定型の挨拶・自己紹介・チャンネル説明は完全禁止。視聴者は最初の5秒で離脱を判断する。
- ❌ NG: 「今回のテーマは〜」のような前置きから入る構成。
- ✅ 1行目(0〜3秒): 視聴者の共感を呼ぶ問いかけ + 結論のヒントを即提示する。例:「雨の日、なぜか気分が沈みませんか? 実はそれ、ある『物質』のせいなんです」「自分の声、録音で聞くと変じゃないですか? 実は耳の構造に秘密があります」。
- ✅ 2〜3行目(3〜10秒): 「今回はその正体を暴きます」「この動画で、その謎を完全に解き明かします」のような本編宣言で、すぐ本編へ突入する。
- 1行目で「あ、自分の話だ」と思わせる共感ワード(あなた・〜したことありませんか・なぜか〜)を必ず入れる。

# エンディング+次回予告ルール(登録率改善・絶対厳守)
- 締めCTA(高評価・登録)の直前または直後に「次回は〇〇を解説するよ」のような次回予告を必ず1〜2行入れる。
- {next_video_hint}
- 「次回も気になる」と思わせて登録への心理的ハードルを下げるのが目的。次回予告を省略した動画は不合格。

# 雰囲気タグ(mood)ルール — シーンごとのBGM切替に使用
- 各行に必ず "mood" を付与する。値は次の6種類のいずれか:
  - "calm"(穏やか・落ち着いた解説)
  - "bright"(明るい・楽しい・元気な導入や応用Tips)
  - "tense"(緊張・問題提起・「えっ!?」となる衝撃の事実)
  - "emotional"(感動・しみじみ・ストーリー的なエピソード)
  - "funny"(コミカル・ボケツッコミ・笑える脱線)
  - "mysterious"(ミステリアス・「謎」「不思議」「未解明」を扱うセクション)
- 同じmoodは連続させて2〜10行ほどの「シーン」を作る(1行ごとに毎回切替えない)。フル尺で4〜8シーンを目安。
- 構成と雰囲気の対応例: CTA+導入="bright"、問題提起="tense"、基本解説="calm"、研究データ="calm"or"mysterious"、意外な事実="tense"or"mysterious"、応用Tips="bright"、締めCTA="emotional"or"bright"。
- ショート(short_scenario)は2〜3シーン程度。フック="tense"or"bright"、展開="calm"、オチ="bright"or"emotional"が基本パターン。

# 序盤セリフ運びルール(冒頭離脱対策・絶対厳守)
- 対象は**序盤=full_scenarioの最初の25%区間**（先頭から全体の1/4の行）。ショートは1〜3行目が該当。ここは視聴者が「見続けるか」を決める最重要ゾーン。
- ❌ NG: 序盤で「感想・まとめ調」の落ち着いた（mood="calm"）セリフを**2連続**させること。「〜なんだね」「〜ということか」「なるほどね」のような噛み砕き・まとめの相槌が続くと、話が停滞して離脱される。
- ✅ 序盤の各セリフは、原則**疑問文（「なぜ〜？」「〜って何？」「じゃあ〜はどうなるの？」）で次の行へ橋渡し**し、視聴者の「続きが気になる」を切らさない。
- ✅ どうしても落ち着いた説明（calm）が続きそうなときは、**calmとcalmの間に必ず1行、驚き役（expression="surprise"）や食いつき役（expression="think"／mood="tense"or"mysterious"）のセリフを挟む**。「えっ、それどういうこと!?」のように視聴者の疑問を代弁して、テンポと引きを維持する。
- この序盤ルールは「冒頭フックルール」と併用する（フック直後の展開が感想の連打にならないよう特に注意）。

# その他ルール
- text内は1〜2文で完結。文末「。」直後に改行 `\\n` を入れる(例:"...だ。\\nだから...")。
- **speaker欄は必ず「{c0}」「{c1}」(このチャンネルのキャラ名そのまま)を使う**。他の表記揺れは crash の原因になる。
- text本文内で相手を呼ぶときも上記の「{c0}」「{c1}」と完全一致の表記を使い、別の漢字・別表記に置き換えない。
- expression: {c0}は{expr0}から / {c1}は{expr1}から選ぶ。
- 本チャンネルのトーン（{tone}）と上記「このチャンネルの語り口」を最優先で守る。冒頭で驚き→なぜ→深掘り→意外な結論の構成は流用しつつ、語彙・世界観はチャンネルに合わせる。
- **ショートは「浅い豆知識」NG**: ChatGPTでもすぐ出てくるような薄い情報ではなく、視聴者が思わず人に話したくなる具体性のある「ネタ」を入れること。
"""

    def _build_monologue_prompt(self, channel, theme: Dict, target_duration: int) -> str:
        """モノローグスタイルのシナリオ生成プロンプト"""
        narrator = channel.characters.get("narrator", {})

        policy_parts = []
        for g in channel.policy_guidelines():
            policy_parts.append(f"- {g}")
        for a in channel.policy_avoid():
            policy_parts.append(f"- 避ける: {a}")
        policy_text = "\n".join(policy_parts) if policy_parts else "(なし)"
        persona_block = self._persona_block(channel)
        next_video_hint = self._next_video_hint(channel)

        target_lines = max(50, min(58, round(target_duration / 13)))
        target_chars = int(target_duration * 8.0)
        max_chars = int(target_duration * 9.0)
        floor_lines = 48
        floor_chars = 4800
        short_target_chars = 230
        tone = channel.content_policy.get("tone", "serious_documentary")
        cta_pos = channel.content_policy.get("cta_position", "end_only")

        voice_block = self._voice_style_block(channel)

        return f"""ドキュメンタリー風ナレーション動画のシナリオを生成。JSONのみ出力。

{voice_block}# チャンネル: {channel.name} / {channel.concept} / トーン:{tone}
# ナレーター: {narrator.get("role", "冷静な男性ナレーター")}
# テーマ: {theme["title"]} / 切り口:{theme.get("angle","自由")}
{persona_block}# ポリシー:
{policy_text}

# 出力JSON
{{
 "title":"バズるタイトル",
 "thumb_info":{{"hook_lines":["1行","2行"],"subtitle":"...","tagline":"..."}},
 "short_scenario":[{{"text":"...","chapter_title":null,"mood":"tense"}}, ...全6行],
 "full_scenario":[
   {{"chapter_title":"第1章: 導入","mood":"mysterious"}},
   {{"text":"...","mood":"mysterious"}},
   ...テキスト行を{floor_lines}〜{target_lines+4}行(章は3〜5章)
 ]
}}

# タイトルルール(超重要・CTR改善のため絶対厳守)
- ❌ NG: 「【ゆっくり解説】〇〇」「〇〇の謎、解けます！」など、定型プレフィックスや結論を含むタイトルは禁止。CTRが大幅に下がる。
- ❌ NG: 結論・答えをタイトルにバラす。
- ✅ OK: 「なぜアスファルトだけ？水たまりが『あそこ』にしかできない本当の理由」のように、答えではなく「なぜ？」という謎・違和感だけを置く疑問型・意外性重視。
- 「【〇〇解説】」のような定型プレフィックスは絶対に付けない。
- 「本当の理由」「実は」「あそこ」「なぜか」「だけ」「〇〇すぎる」など意外性を匂わせるワードを必ず1つ以上入れる。
- 視聴者が「気になる、答えを知りたい」と感じる謎の提示で止める。結論はサムネ・本編で初めて出す。

# 尺ルール(絶対厳守・違反は不合格)
- **テキストは必ず{floor_lines}〜{target_lines+4}行**(目標{target_lines}行)。
- **各行は90〜120字**(目標100字、上限120字)。89字以下も121字以上も不合格。
- **総文字数は{target_chars}〜{max_chars}字**(約{target_duration/60:.1f}分目標、{max_chars}字で約{max_chars/7.8/60:.1f}分)。
- 各行に研究データ・数字・事例を必ず盛る。

# ショート尺ルール(絶対厳守)
- **short_scenarioは必ず6行**(1〜5行目は30〜45字目標38字、6行目のみ45〜70字を許容)。
- **総文字数は必ず{short_target_chars-30}〜{short_target_chars+50}字**(目標{short_target_chars+20}字)で**約30〜35秒**を実現。
- 構成(6行固定):
  1行目=**強フック**: 「これは衝撃の事実だ」「あなたは知らない」など、意外性・謎・問題提起で視聴者を引き込む。
  2行目=**ツカミ展開**: フックを受けた前振り・状況説明。
  3〜4行目=**核となる事実**: ここに**具体的な数字・年号・%・研究データ・固有名詞のいずれか1つ以上を必ず含める**(例:「実は97%が…」「1923年の…」「ハーバード大の研究では…」)。視聴者が「初めて知った」と感じる中身を入れる。抽象論だけはNG。
  5行目=**納得のオチ**: スパッと結論を提示。投げっぱなし禁止。
  6行目=**登録誘導+関連動画誘導CTA(必須・絶対省略禁止・順番厳守)**: 必ず「①チャンネル登録誘導 → ②関連動画誘導」の順で1行に2つのCTAを連結する。
    - ①登録CTA: 「チャンネル登録者1万人を目指して毎日投稿中なので、応援よろしく」のニュアンスを必ず入れる(「毎日投稿中」「1万人目標」「応援」の3要素で、視聴者の応援したい気持ちを引き出して登録率を上げる)。
    - ②関連動画CTA: 必ず「関連動画」というワードを含め、ショート離脱者を長尺へ送る(「本編」より「関連動画」を優先)。
    - 例:「チャンネル登録者1万人を目指して毎日投稿中だ。応援よろしく。もっと詳しい話は関連動画で語っている。」
    - **6行目のみ45〜70字を許容**(2つのCTAを連結するため、通常の30〜45字制限を超えてよい)。
- 一般論・感想のみで埋めるのは不合格。1本につき最低1つは「へぇ」と思わせる具体情報を入れること。

# 雰囲気タグ(mood)ルール — シーンごとのBGM切替に使用
- 各行(章タイトル含む)に必ず "mood" を付与する。値は次の6種類のいずれか:
  - "calm"(穏やか) / "bright"(明るい) / "tense"(緊張・衝撃)
  - "emotional"(感動) / "funny"(コミカル) / "mysterious"(ミステリアス)
- 同じmoodを2〜10行ほど連続させて「シーン」を作る(毎行切替えない)。1章 = 1〜2シーン目安。
- 章タイトル行のmoodは、その章の主軸となる雰囲気と一致させる。

# 序盤セリフ運びルール(冒頭離脱対策・絶対厳守)
- 対象は**序盤=full_scenarioの最初の25%区間**（本文行の先頭から全体の1/4）。ショートは1〜3行目が該当。ここは視聴者が「見続けるか」を決める最重要ゾーン。
- ❌ NG: 序盤で「感想・まとめ調」の落ち着いた（mood="calm"）ナレーションを**2連続**させること。淡々とした総括・言い換えが続くと話が停滞し離脱される。
- ✅ 序盤の各行は、原則**疑問・問いかけ（「なぜ〜のか」「〜とは何なのか」「では〜はどうなるのか」）で次の行へ橋渡し**し、視聴者の「続きが気になる」を切らさない。
- ✅ どうしても落ち着いた説明（calm）が続きそうなときは、**calmとcalmの間に必ず1行、驚き・緊張の一撃（mood="tense"）か謎の提示（mood="mysterious"）を挟む**。「だが、ここで奇妙なことが起きる」のように緊張を差し込み、テンポと引きを維持する。
- この序盤ルールは「冒頭フックルール」と併用する（フック直後の展開が総括の連打にならないよう特に注意）。

# 冒頭フックルール(超重要・冒頭5秒離脱対策・絶対厳守)
- ❌ NG: 「これからお話するのは〜」「みなさんは〜をご存知だろうか」のような長い導入・前置きから入る構成は禁止。視聴者は最初の5秒で離脱を判断する。
- ❌ NG: 自己紹介・チャンネル説明・章タイトルの読み上げから始めない。
- ✅ 第1章の最初の本文行(0〜3秒): 視聴者の共感を呼ぶ問いかけ + 結論のヒントを即提示。例:「雨の日、なぜか気分が沈むことはないだろうか。実はそれ、ある『物質』が原因なのだ」。
- ✅ 第1章2〜3行目(3〜10秒): 「今回はその正体を暴く」「この映像で、その謎を完全に解き明かす」のような本編宣言で、すぐ本題へ突入する。
- 1行目に「あなた」「〜したことがあるはずだ」のような共感を呼ぶ語りを必ず入れる。

# エンディング+次回予告ルール(登録率改善・絶対厳守)
- 最終章の締めCTA(高評価・登録)の直前または直後に「次回は〇〇を解説する」のような次回予告を必ず1〜2行入れる。
- {next_video_hint}
- 「次回も気になる」と思わせて登録への心理的ハードルを下げるのが目的。次回予告を省略した動画は不合格。

# その他ルール
- text内は1〜2文。文末「。」直後に `\\n` 挿入(例:"...だ。\\n...だ。")。
- 章タイトルで3〜5章に分割。
- 冒頭で共感フック→本題→意外な結論。本チャンネルのトーン（{tone}）と上記「このチャンネルの語り口」を最優先で守り、語彙・世界観はチャンネルに合わせる。
- **ショートは「浅い豆知識」NG**: 誰でも知っている一般論ではなく、具体性のある事実・数字・固有名詞でフックを作ること。
- CTA配置: {cta_pos}
"""

    def _build_facts_overlay_prompt(self, channel, theme: Dict, target_duration: int) -> str:
        """ファクトオーバーレイ（企業のホンネ）スタイルのシナリオ生成プロンプト。

        出力は対話ではなく「1画面 = 1ファクト」のリスト。各行が
        画面に出す文字（fact_header / fact_main / fact_sub）と
        読み上げナレーション（text）を同時に持つ。
        """
        policy_parts = []
        for g in channel.policy_guidelines():
            policy_parts.append(f"- {g}")
        for a in channel.policy_avoid():
            policy_parts.append(f"- 避ける: {a}")
        policy_text = "\n".join(policy_parts) if policy_parts else "(なし)"
        persona_block = self._persona_block(channel)
        voice_block = self._voice_style_block(channel)
        tone = channel.content_policy.get("tone", "データ重視")

        fo = {}
        try:
            fo = channel.video_format.facts_overlay or {}
        except AttributeError:
            fo = {}
        default_badge = ((fo.get("header_badge") or {}).get("text") or "超ホワイト企業")
        cta_cfg = fo.get("cta") or {}
        cta_headline = cta_cfg.get("headline") or "他の企業もチェック"
        cta_sub = cta_cfg.get("sub") or "プロフィールから見れます"

        # 45秒 ≒ 7ファクト + CTA。尺に合わせてファクト数だけスケールさせる。
        fact_count = max(5, min(9, round(target_duration / 6.0)))

        return f"""縦型ショート「ファクトオーバーレイ動画」のシナリオを生成。JSONのみ出力。
対話形式ではない。1人のナレーションと、画面に叩き込む数字ファクトで構成する。

{voice_block}# チャンネル: {channel.name} / {channel.concept} / トーン:{tone}
# テーマ: {theme["title"]} / 切り口:{theme.get("angle","自由")}
{persona_block}# ポリシー:
{policy_text}

# 出力JSON
{{
 "title":"企業名を含むバズるタイトル",
 "company_name":"扱う企業の正式名称（背景写真の検索に使う）",
 "thumb_info":{{"hook_lines":["1行","2行"],"subtitle":"...","tagline":"..."}},
 "short_scenario":[
   {{"fact_header":"{default_badge}","fact_main":"平均年収 850万円","fact_sub":"業界平均の1.5倍",
     "text":"読み上げるナレーション","bg_query":"企業名 店舗 外観","duration":5,"mood":"bright"}},
   ...ファクトを{fact_count}個、最後に必ずCTA行(下記)を1個
 ],
 "full_scenario":[]
}}

# 各フィールドの意味（絶対厳守）
- fact_header: 画面上部の赤帯バッジ。**動画を通してほぼ固定**（例:「{default_badge}」「年収がヤバい企業」）。
  2〜3行目以降は省略可（省略すると直前の値を引き継ぐ）。10文字以内。
- fact_main: 画面中央の白い大文字。**1画面で読み切れる短さ（最大20文字）**。
  **必ず具体的な数字を1つ入れる**（例:「平均年収 850万円」「有給消化率 100%」「離職率 3%」）。
  数字だけ自動で黄色に強調表示されるので、数字と単位はくっつけて書く（「850万円」）。
- fact_sub: 画面下部の赤い補足。25文字以内。比較・出典・注意点を書く（例:「業界平均は420万円」「口コミサイト調べ」）。
- text: 読み上げナレーション。**40〜70文字**。fact_main の数字を必ず声でも言う。
  画面の文字をそのまま読むだけにせず、驚き・理由・比較を足して価値を出す。
- bg_query: その画面の背景写真を探す日本語検索クエリ。**必ず企業名で始める**
  （例:「ニトリ 店舗 外観」「ニトリ 売り場」）。画面ごとに違うクエリにして写真を切り替える。
- duration: その画面の最低表示秒数（4〜7）。実際の尺はナレーション音声に合わせて自動で伸びる。
- mood: BGM切替タグ。"bright"(明るい) / "tense"(衝撃) / "calm"(落ち着き) のいずれか。

# 構成（{fact_count}ファクト + CTA、合計約{target_duration}秒）
1. **1個目=最強フック**: 企業名 + 最もインパクトのある数字を即出し（例:「ニトリ 平均年収850万円」）。
   冒頭3秒で企業名と数字が画面に出ていない構成は不合格。
2. 2〜{fact_count-1}個目: 年収→ボーナス→有給/残業→離職率→福利厚生 の順でテンポよく数字を連打する。
   同じ指標を2回出さない。毎回ちがう切り口の数字にする。
3. {fact_count}個目=**バランス行**: ネガティブ or 注意点を必ず1つ入れる
   （例:「ただし1年目は力仕事」「店舗配属は土日出勤」）。持ち上げるだけの動画は不合格。
4. 最後=**CTA行**（必須・省略禁止）: 次の形で1行だけ足す。
   {{"is_cta":true,"fact_main":"{cta_headline}","fact_sub":"{cta_sub}",
     "text":"気になったらプロフィールから他の企業もチェックしてね。","mood":"bright"}}
   CTA行には fact_header と bg_query を付けない（専用の全画面デザインになる）。

# full_scenario について
- このチャンネルは**ショート専用**。long-form は作らないので `"full_scenario": []`（空配列）でよい。

# データの扱い（訴訟リスク回避・絶対厳守）
- 数字は有価証券報告書・公式IR・大手口コミサイトなど**公開情報から実在する値**を使う。
- 出典が口コミサイトの数字は fact_sub か text に「口コミサイト調べ」と明記する。
- 未上場・非公開の数字は「推定」と明記する。断定しない。
- 特定企業を貶める表現、個人が特定できる情報、アフィリエイト誘導は禁止。

# タイトルルール
- 企業名を必ず入れる。数字を1つ入れる。「【解説】」のような定型プレフィックスは付けない。
- 例:「ニトリの年収がヤバい 平均850万円の実態」「任天堂の離職率3%、辞めない理由」
"""

    def _wrap_for_blind(
        self,
        scenario_data: Dict[str, Any],
        theme: Dict,
        channel,
    ) -> Dict[str, Any]:
        """blind_compare に渡しやすい形に整形（title / scenarios / thumb）。"""
        return {
            "title": scenario_data.get("title") or theme.get("title") or "",
            "short_scenario": scenario_data.get("short_scenario") or [],
            "full_scenario": scenario_data.get("full_scenario") or [],
            "thumb_info": scenario_data.get("thumb_info") or {},
            "channel_id": channel.id,
        }

    def _record_compete(
        self,
        *,
        channel_id: str,
        run_id: str,
        gpt_data: Optional[Dict[str, Any]],
        claude_data: Optional[Dict[str, Any]],
        blind_result: Optional[Dict[str, Any]],
        chosen: str,
        selected_by: str,
    ) -> None:
        """model_scenario_records に gpt / claude 双方の候補を書き込む。"""
        try:
            from pipeline.analytics import store as analytics_store
        except Exception as e:
            print(f"  ⚠️ compete record store import failed: {e}")
            return

        mapping = (blind_result or {}).get("mapping") or {}
        scores_a = (blind_result or {}).get("scores_a") or {}
        scores_b = (blind_result or {}).get("scores_b") or {}
        winner_letter = (blind_result or {}).get("winner")

        def _scores_for(model: str) -> Tuple[Dict[str, Any], bool, Optional[float]]:
            if not blind_result:
                return ({}, False, None)
            ab = next((k for k, v in mapping.items() if v == model), None)
            if ab is None:
                return ({}, False, None)
            sc = scores_a if ab == "A" else scores_b
            won = ab == winner_letter
            overall = sc.get("overall") if isinstance(sc, dict) else None
            try:
                overall_f = float(overall) if overall is not None else None
            except Exception:
                overall_f = None
            return (sc, won, overall_f)

        for model_name, data in (("gpt", gpt_data), ("claude", claude_data)):
            if data is None:
                continue
            scores, won, overall = _scores_for(model_name)
            try:
                analytics_store.insert_model_scenario_record(
                    channel_id=channel_id,
                    model_name=model_name,
                    run_id=run_id,
                    title=data.get("title"),
                    selected=(model_name == chosen),
                    selected_by=(selected_by if model_name == chosen else None),
                    won_blind_eval=won,
                    blind_overall=overall,
                    blind_scores=scores,
                )
            except Exception as e:
                print(f"  ⚠️ compete record insert failed ({model_name}): {e}")

    def _run_generation_loop(
        self,
        messages: List[Dict[str, str]],
        *,
        provider: str,
        channel,
        theme: Dict,
        duration: int,
        min_full_lines: int,
        max_full_lines: int,
        min_full_chars: int,
        min_avg_chars: int,
    ) -> Optional[Dict[str, Any]]:
        """1 つのプロバイダ (gpt | claude) でシナリオ生成 → 行数 / 文字数バリデーション。

        失敗時は None。messages はこの関数内でコピーされて使われる（呼び出し側不変）。
        """
        msgs = [dict(m) for m in messages]
        provider_label = "GPT" if provider == "gpt" else "Claude"
        self._current_purpose = f"scenario_{provider}"

        def _line_text(entry):
            if isinstance(entry, dict):
                return entry.get("text", "")
            return ""

        scenario_data: Optional[Dict[str, Any]] = None
        last_full_count = 0
        last_total_chars = 0
        last_avg_chars = 0.0
        # 出力トークン枠を要求文字数から見積もる。既定 8000 のままだと 10 分超（min_full_chars
        # ≥5760）のシナリオが JSON 途中で打ち切られ、"Unterminated string" で全 attempt が
        # 落ちてセクション拡張の短い本文に化ける。日本語は概ね 1 文字 ≒ 1 トークン、さらに
        # speaker/mood/括弧などの JSON 骨組みと short_scenario・thumb_info の分を上乗せする。
        # 上限 16000 は安全側の据え置き（gpt-5.6-terra の出力上限はこれより大きい）。
        gen_max_tokens = max(8000, min(16000, int(min_full_chars * 1.6) + 4000))
        # GPT は例外時に即 None（OpenAI quota切れ等のfail-fast）。
        # Claude は単独採用される場面が多いので検証リトライを1回多く与え、
        # "Both GPT and Claude failed" の取りこぼしを減らす。
        max_attempts = 3 if provider == "claude" else 2
        for attempt in range(max_attempts):
            try:
                if provider == "gpt":
                    raw = self._call_gpt(msgs, temperature=0.7, max_tokens=gen_max_tokens)
                else:
                    raw = self._call_claude_text(msgs, temperature=0.7, max_tokens=gen_max_tokens)
            except Exception as e:
                print(f"  ⚠️ {provider_label} call failed on attempt {attempt+1}: {e}")
                return None
            try:
                scenario_data = self._extract_json(raw)
            except Exception as e:
                print(f"  ⚠️ {provider_label} JSON parse error on attempt {attempt+1}: {e}")
                continue
            full_lines = scenario_data.get("full_scenario", [])
            last_full_count = len(full_lines)
            last_total_chars = sum(len(_line_text(e)) for e in full_lines)
            last_avg_chars = (last_total_chars / last_full_count) if last_full_count > 0 else 0.0
            ok_lines = last_full_count >= min_full_lines
            ok_chars = last_total_chars >= min_full_chars
            ok_avg = last_avg_chars >= min_avg_chars
            if ok_lines and ok_chars and ok_avg:
                print(f"  ✅ {provider_label} full_scenario: {last_full_count} lines, {last_total_chars} chars, avg {last_avg_chars:.1f}/line")
                break
            issue = []
            if not ok_lines:
                issue.append(f"行数 {last_full_count}（目標 {min_full_lines}〜{max_full_lines}）")
            if not ok_chars:
                issue.append(f"総文字数 {last_total_chars}（目標 ≥{min_full_chars}）")
            if not ok_avg:
                issue.append(f"平均 {last_avg_chars:.1f}（目標 ≥{min_avg_chars}）")
            print(f"  ⚠️ {provider_label} {' / '.join(issue)} — Retrying...")
            msgs.append({"role": "assistant", "content": raw})
            msgs.append({
                "role": "user",
                "content": (
                    f"full不足({' / '.join(issue)})。{min_full_lines}〜{max_full_lines}行/計{min_full_chars}字以上/平均{min_avg_chars}字以上に増量。"
                    f"各行90〜150字、データ/数字/例え必須。89字以下禁止。JSONのみ再出力。"
                )
            })

        if scenario_data is None:
            return None

        # GPT のみ sectional expansion を持っている（Claude では諦めて受け入れる）
        if (
            provider == "gpt"
            and duration >= 300
            and (last_full_count < min_full_lines or last_total_chars < min_full_chars or last_avg_chars < min_avg_chars)
        ):
            print(f"  🔁 GPT sectional expansion (current: {last_full_count} lines, {last_total_chars} chars, avg {last_avg_chars:.1f}/line)")
            try:
                scenario_data = self._expand_via_sections(channel, theme, scenario_data, duration, min_full_lines, min_full_chars)
                full_lines = scenario_data.get("full_scenario", [])
                last_full_count = len(full_lines)
                last_total_chars = sum(len(_line_text(e)) for e in full_lines)
                last_avg_chars = (last_total_chars / last_full_count) if last_full_count > 0 else 0.0
                print(f"  ✅ After expansion: {last_full_count} lines, {last_total_chars} chars, avg {last_avg_chars:.1f}/line")
            except Exception as e:
                print(f"  ⚠️ Sectional expansion failed: {e}")

        return scenario_data

    def generate(
        self,
        channel,  # ChannelProfile
        theme_override: Optional[Dict] = None,
        target_duration: Optional[int] = None,
        improvement_feedback: Optional[List[Dict[str, Any]]] = None,
        run_ab_test: bool = False,
        avoid_duplicate_theme: bool = True,
    ) -> Dict[str, Any]:
        """
        チャンネルプロファイルからシナリオを自動生成。

        ANTHROPIC_API_KEY が設定されていれば GPT と Claude の両方で並列生成し、
        ブラインド評価で勝者を採用する（"AI モデル間コンペ"）。未設定なら GPT のみ。

        Args:
            improvement_feedback: いいね率改善ループからの未消費フィードバック。
                pipeline.analytics.feedback_store.get_pending_for_channel(...) の戻り値
                をそのまま渡す想定。GPT プロンプトに改善方針として注入される。
            avoid_duplicate_theme: True（既定）なら、選択/指定されたテーマが既存動画・
                過去シナリオとほぼ同一（類似度 ≥ THEME_DUP_BLOCK_THRESHOLD）か、チャンネル
                の theme_blacklist / genre_blacklist に該当する場合、別テーマへ自動で
                差し替える。さらに生成後の最終タイトルが既存とほぼ同一
                （≥ TITLE_DUP_REJECT_THRESHOLD）ならタイトルだけ作り直す。theme_override
                経由（autopilot / run_*.py / batch）でも必ず適用される重複量産の最終ゲート。
                意図的に同一テーマを再生成したい手動実行では False を渡す。

        Returns:
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
        """
        # テーマ選択 — auto モード時は過去に生成済みのテーマを避けて選ぶ
        if theme_override:
            theme = theme_override
        elif channel.theme_seeds:
            theme = self._pick_seed_avoiding_past(channel)
            # 直近30日に同一タイトルがあれば別候補を引き直す（最大3回、ダメなら続行）
            recent = self._recent_theme_titles(channel.id, days=30)
            for _ in range(3):
                if (theme.get("title") or "").strip().lower() not in recent:
                    break
                print(f"  ♻️ Theme '{theme.get('title')}' used within 30d — re-picking")
                theme = self._pick_seed_avoiding_past(channel)
        else:
            raise ValueError(f"No theme_seeds for channel {channel.id}")

        # テーマ重複の最終ゲート。theme_override（autopilot / run_*.py / batch）でも
        # 必ずここを通す。既存動画/過去シナリオとほぼ同一のテーマなら別テーマへ差し替える。
        if avoid_duplicate_theme:
            theme = self._dedupe_theme(channel, theme)

        duration = target_duration or channel.get_target_duration()

        feedback_addendum = ""
        applied_feedback_ids: List[str] = []
        if improvement_feedback:
            try:
                from pipeline.analytics.feedback_store import build_prompt_addendum
                feedback_addendum = build_prompt_addendum(improvement_feedback)
                applied_feedback_ids = [
                    fb.get("video_id") for fb in improvement_feedback if fb.get("video_id")
                ]
            except Exception as e:
                print(f"  ⚠️ improvement feedback addendum failed: {e}")

        # Phase B: Analytics ベースのフィードバック（成功パターン / 維持率 / コメント要望）
        analytics_addendum = ""
        applied_analytics = False
        try:
            from pipeline.analytics.scenario_feedback import build_analytics_addendum
            analytics_addendum = build_analytics_addendum(channel.id) or ""
            applied_analytics = bool(analytics_addendum)
        except Exception as e:
            print(f"  ⚠️ analytics feedback addendum failed: {e}")

        # Phase F-2: 競合分析からの差別化指示
        competitor_addendum = ""
        applied_competitor = False
        try:
            from pipeline.analytics.competitor_intelligence import build_competitor_addendum
            competitor_addendum = build_competitor_addendum(channel.id) or ""
            applied_competitor = bool(competitor_addendum)
        except Exception as e:
            print(f"  ⚠️ competitor intelligence addendum failed: {e}")

        # スタイル別プロンプト生成
        if channel.style == "facts_overlay":
            prompt = self._build_facts_overlay_prompt(channel, theme, duration)
        elif channel.style == "monologue":
            prompt = self._build_monologue_prompt(channel, theme, duration)
        else:
            prompt = self._build_yukkuri_prompt(channel, theme, duration)

        if feedback_addendum:
            prompt = prompt + "\n\n" + feedback_addendum
            print(
                f"  💡 Applying improvement feedback from {len(applied_feedback_ids)} prior video(s)"
            )
        if analytics_addendum:
            prompt = prompt + "\n\n" + analytics_addendum
            print("  📊 Applying analytics-derived feedback (success patterns / retention / viewer requests)")
        if competitor_addendum:
            prompt = prompt + "\n\n" + competitor_addendum
            print("  🥷 Applying competitor intelligence (title patterns / hot topics / gap themes)")

        # theme_override（run_*.py / batch / autopilot が題材を明示指定）時は題材を固定する。
        # 上記 analytics / competitor addendum は「過去に伸びた題材（例:SCP-5000/173）を再現せよ」と
        # 具体指示するため、1行のテーマ指定を上書きして別の題材を書かせてしまう（題材ハイジャック）。
        # 全 addendum の後（＝最後に読む指示）に最優先の題材ロックを付け、addendum の適用範囲を
        # 文体・構成・タイトルの型に限定して題材そのものの差し替えを禁止する。
        if theme_override:
            _lock_title = theme.get("title", "")
            _lock_angle = theme.get("angle", "")
            prompt = prompt + (
                f"\n\n# 【最優先・題材ロック】(絶対厳守・他のどの指示より優先)\n"
                f"- この動画の題材は「{_lock_title}」に固定する。切り口: {_lock_angle}\n"
                f"- 上の『分析データに基づく改善指示』『競合チャンネル分析』は、文体・構成・"
                f"タイトルの型・サムネの作り方についてのみ適用する。題材（扱うSCPオブジェクト／番号）"
                f"を変える指示としては一切採用しない。\n"
                f"- 他のSCP番号やオブジェクト（例: SCP-5000 / SCP-173 / SCP-1730 / SCP-096 など）を"
                f"主題にすることを固く禁止する。title・thumb_info・short_scenario・full_scenario は"
                f"すべて「{_lock_title}」についてのみ書くこと。\n"
                f"- 過去の成功パターンに引きずられて別の題材へ乗り換えた出力は不合格。"
            )
            print(f"  🔒 Theme lock enforced (override): {_lock_title}")

        # フル動画の最低行数 + 最低総文字数 + 1行あたり最低平均文字数
        ABSOLUTE_FLOOR_CHARS = 4800  # 10分 × 8.0文字/秒
        ABSOLUTE_FLOOR_LINES = 55
        MIN_AVG_CHARS_PER_LINE = 90
        if channel.style == "facts_overlay":
            # ショート専用スタイル。full_scenario は空で正しいので長さ検証をかけない
            # （かけると毎回「full不足」で無駄なリトライが走る）。
            min_full_lines = 0
            max_full_lines = 0
            min_full_chars = 0
            min_avg_chars = 0
        elif duration >= 120:
            min_full_lines = max(ABSOLUTE_FLOOR_LINES, int((duration / 60) * 4.6))
            max_full_lines = max(72, int((duration / 60) * 6.5))
            min_full_chars = max(ABSOLUTE_FLOOR_CHARS, int(duration * 8.0))
            min_avg_chars = MIN_AVG_CHARS_PER_LINE
        else:
            min_full_lines = 5
            max_full_lines = 999
            min_full_chars = 0
            min_avg_chars = 0

        if channel.style == "facts_overlay":
            system_msg = (
                "縦型ショートのファクト動画構成作家。JSONのみ出力。"
                "1画面=1ファクトで、画面文字(fact_main)は20字以内かつ具体的な数字を必ず含める。"
                "ナレーション(text)は40〜70字。対話形式は不合格。"
            )
        else:
            system_msg = (
                f"YouTube動画シナリオライター。JSONのみ出力。"
                f"full:{min_full_lines}〜{max_full_lines}行、各行90字以上(目安90〜150)、計{min_full_chars}字以上、平均{min_avg_chars}字以上。"
                f"89字以下や相槌のみは不合格。"
            )
        base_messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        # Track usage per channel
        self._current_channel_id = channel.id
        self._current_purpose = "scenario"

        # ─── 採用方針決定 ───
        claude_available = bool(claude_client and claude_client.has_api_key())
        compete_meta: Optional[Dict[str, Any]] = None
        scenario_data: Optional[Dict[str, Any]] = None
        chosen_provider: str = "gpt"

        if claude_available:
            try:
                from pipeline.analytics.model_compete import (
                    blind_compare as _blind_compare,
                    decide_selection_strategy as _decide_strategy,
                )
                strategy = _decide_strategy(channel.id)
            except Exception as e:
                print(f"  ⚠️ strategy decision failed: {e}")
                strategy = {"mode": "blind", "reason": "fallback", "leader": None, "margin": 0.0}

            print(
                f"🤖 Dual scenario gen (gpt + claude) — theme: {theme['title']} "
                f"({channel.style}, {duration}s, {min_full_lines}-{max_full_lines} lines, "
                f"strategy={strategy['mode']})"
            )

            # 並列で両方生成
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_gpt = pool.submit(
                    self._run_generation_loop,
                    base_messages,
                    provider="gpt",
                    channel=channel,
                    theme=theme,
                    duration=duration,
                    min_full_lines=min_full_lines,
                    max_full_lines=max_full_lines,
                    min_full_chars=min_full_chars,
                    min_avg_chars=min_avg_chars,
                )
                fut_claude = pool.submit(
                    self._run_generation_loop,
                    base_messages,
                    provider="claude",
                    channel=channel,
                    theme=theme,
                    duration=duration,
                    min_full_lines=min_full_lines,
                    max_full_lines=max_full_lines,
                    min_full_chars=min_full_chars,
                    min_avg_chars=min_avg_chars,
                )
                gpt_data = fut_gpt.result()
                claude_data = fut_claude.result()

            # 候補が両方揃っていればブラインド比較、片方なら自動採用
            run_id = f"compete_{int(time.time())}_{random.randint(1000,9999)}"
            blind_result: Optional[Dict[str, Any]] = None
            blind_winner_model: Optional[str] = None
            selected_by = "only_one"

            if gpt_data and claude_data:
                blind_result = _blind_compare(
                    self._wrap_for_blind(gpt_data, theme, channel),
                    self._wrap_for_blind(claude_data, theme, channel),
                    channel_id=channel.id,
                    model_a="gpt",
                    model_b="claude",
                )
                if blind_result:
                    blind_winner_model = blind_result.get("winner_model")
                    selected_by = "blind_eval"
                    print(
                        f"  🥊 Blind compare: winner={blind_winner_model} "
                        f"(A/B mapping={blind_result.get('mapping')})"
                    )
                else:
                    # 比較失敗時は GPT を採用（fallback）
                    blind_winner_model = "gpt"
                    selected_by = "only_one"
                    print("  ⚠️ Blind compare unavailable — falling back to GPT")

                # 実績バイアス補正
                final_model = blind_winner_model
                if (
                    blind_result
                    and strategy.get("mode") in ("prefer_gpt", "prefer_claude")
                ):
                    forced = "gpt" if strategy["mode"] == "prefer_gpt" else "claude"
                    if forced != blind_winner_model:
                        print(
                            f"  📊 Performance bias override: blind picked {blind_winner_model}, "
                            f"but {forced} leads by {strategy.get('margin', 0)*100:.1f}% → using {forced}"
                        )
                        final_model = forced
                        selected_by = "performance"

                chosen_provider = final_model or "gpt"
                scenario_data = gpt_data if chosen_provider == "gpt" else claude_data

                # 記録
                self._record_compete(
                    channel_id=channel.id,
                    run_id=run_id,
                    gpt_data=gpt_data,
                    claude_data=claude_data,
                    blind_result=blind_result,
                    chosen=chosen_provider,
                    selected_by=selected_by,
                )
                compete_meta = {
                    "run_id": run_id,
                    "blind_eval": blind_result,
                    "selected_by": selected_by,
                    "strategy": strategy,
                    "candidates": {
                        "gpt": {"title": gpt_data.get("title")},
                        "claude": {"title": claude_data.get("title")},
                    },
                }
            elif gpt_data or claude_data:
                # 片方しか取れなかった → 取れた方をそのまま採用、それでも記録は残す
                chosen_provider = "gpt" if gpt_data else "claude"
                scenario_data = gpt_data or claude_data
                self._record_compete(
                    channel_id=channel.id,
                    run_id=run_id,
                    gpt_data=gpt_data,
                    claude_data=claude_data,
                    blind_result=None,
                    chosen=chosen_provider,
                    selected_by="only_one",
                )
                compete_meta = {
                    "run_id": run_id,
                    "blind_eval": None,
                    "selected_by": "only_one",
                    "strategy": strategy,
                    "candidates": {
                        "gpt": {"title": gpt_data.get("title")} if gpt_data else None,
                        "claude": {"title": claude_data.get("title")} if claude_data else None,
                    },
                }
                print(f"  ⚠️ Only {chosen_provider} produced a valid scenario — using it")
            else:
                raise ValueError("Both GPT and Claude failed to produce valid scenarios")
        else:
            # Claude 未設定: 従来通り GPT 単独
            print(f"🤖 GPT generating scenario: {theme['title']} ({channel.style}, target {duration}s, {min_full_lines}-{max_full_lines} lines)")
            scenario_data = self._run_generation_loop(
                base_messages,
                provider="gpt",
                channel=channel,
                theme=theme,
                duration=duration,
                min_full_lines=min_full_lines,
                max_full_lines=max_full_lines,
                min_full_chars=min_full_chars,
                min_avg_chars=min_avg_chars,
            )
            if scenario_data is None:
                raise ValueError("GPT failed to produce valid JSON after 2 attempts")
            chosen_provider = "gpt"

        # Short scenario check (warning only — doesn't block)
        short_lines_data = scenario_data.get("short_scenario", [])
        if short_lines_data:
            short_total = sum(
                len(e.get("text", "") if isinstance(e, dict) else "")
                for e in short_lines_data
            )
            short_avg = short_total / len(short_lines_data)
            if short_avg < 30:
                print(f"  ⚠️ short_scenario: {len(short_lines_data)} lines, {short_total} chars, avg {short_avg:.1f}/line — under 30/line, may be under 30s")

        result = {
            "title": scenario_data.get("title", theme["title"]),
            "theme": theme,
            "short_scenario": scenario_data.get("short_scenario", []),
            "full_scenario": scenario_data.get("full_scenario", []),
            "thumb_info": scenario_data.get("thumb_info", {}),
            "channel_id": channel.id,
            "style": channel.style,
            "applied_feedback": applied_feedback_ids,
            "applied_analytics_feedback": applied_analytics,
            "applied_competitor_feedback": applied_competitor,
            "generated_by": chosen_provider,
            "compete": compete_meta,
        }

        # Phase C: AB テストでタイトル＆サムネを最適化（オプション）
        if run_ab_test and self.api_key:
            try:
                from pipeline.ab_test_generator import generate_ab_test
                # シナリオ冒頭6行を要約として渡す（コスト圧縮）
                summary_lines: List[str] = []
                for line in (result["full_scenario"] or [])[:6]:
                    text = line.get("text") if isinstance(line, dict) else ""
                    if text:
                        summary_lines.append(text)
                scenario_summary = "\n".join(summary_lines)
                ab = generate_ab_test(
                    theme_title=result["title"],
                    theme_angle=theme.get("angle", "") or "",
                    channel_id=channel.id,
                    scenario_summary=scenario_summary,
                    save=True,
                )
                best = ab.get("best") or {}
                if best.get("title"):
                    # 既存のタイトル / thumb_info を上書きしつつ、元のタイトルも保持
                    result["original_title"] = result["title"]
                    result["title"] = best["title"]
                    thumb_copy = best.get("thumb_copy") or []
                    if thumb_copy and isinstance(result.get("thumb_info"), dict):
                        result["thumb_info"]["hook_lines"] = thumb_copy[:2] or result["thumb_info"].get("hook_lines", [])
                result["ab_test"] = {
                    "test_id": ab.get("test_id"),
                    "best_pattern": best.get("pattern"),
                    "best_score": best.get("score"),
                    "variant_count": len(ab.get("variants") or []),
                }
                print(
                    f"  🎯 AB test ({ab.get('test_id')}): "
                    f"best={best.get('pattern')} score={best.get('score')}"
                )
            except Exception as e:
                print(f"  ⚠️ AB test generation failed: {e}")
                result["ab_test"] = {"error": str(e)}

        # 最終タイトルの重複ゲート。AB テストがタイトルを差し替えた後に置くことで、
        # 「どの経路で決まったタイトルであれ」既存動画とほぼ同一なら作り直す。
        if avoid_duplicate_theme:
            self._reject_duplicate_title(channel, theme, result, scenario_data)

        return result

    def _expand_via_sections(
        self,
        channel,
        theme: Dict,
        base_scenario: Dict,
        duration: int,
        target_lines: int,
        target_chars: int,
    ) -> Dict:
        """
        ベースのfull_scenarioを章ごとに拡張する。
        既存のシナリオを土台にして、各章で具体的な解説・数字・例え話を追加。
        ゆっくり対話スタイルのみ対応。
        """
        if channel.style != "yukkuri":
            return base_scenario

        char_names = list(channel.characters.keys())
        existing_full = base_scenario.get("full_scenario", [])

        # セクション定義: (タイトル, 行数目安, 内容ガイド, mood)
        # 7セクション × 平均8.6行 = 60行、各行100字 → 6000文字 → 約12.8分(VOICEVOX1.3x)
        # 9セクション×12行=96行で19.9分の過剰生成を起こした反省。7セクションに削減し各行120字上限。
        sections = [
            ("冒頭フック + 本編宣言", 6, "**挨拶・自己紹介・チャンネル説明は完全禁止**。1行目で『あなた〜したことありませんか?』のような共感を呼ぶ問いかけ + 結論のヒントを即提示(0〜3秒で視聴者を捕まえる)。2〜3行目で『今回はその正体を暴く』と宣言してすぐ本編へ。「【ゆっくり解説】」のような定型は禁止。", "bright"),
            ("基本メカニズム解説", 9, "テーマの基本原理を分かりやすく説明。専門用語は噛み砕く", "calm"),
            ("具体的な仕組み・研究データ", 10, "研究データ・具体的な数字・パーセンテージ・代表的な実験", "calm"),
            ("背景・歴史的経緯", 9, "発見・研究の経緯、歴史的エピソードや人物", "mysterious"),
            ("意外な事実・補足知識", 10, "視聴者が驚く意外な情報や雑学・トリビア", "tense"),
            ("日常への応用・実践Tips", 9, "視聴者が今日から使える実践的なTips・応用例", "bright"),
            ("まとめ + 次回予告 + 締めCTA", 7, "今日の内容を簡潔にまとめ → **『次回は〇〇を解説するよ』のような次回予告を必ず1〜2行入れる(必ず本チャンネル『" + channel.name + "』のジャンル・世界観に閉じたテーマから提案。他ジャンルへの飛び火禁止)** → 高評価/登録CTA。次回予告は登録率改善のため絶対省略禁止。", "emotional"),
        ]
        # 合計目標: 6+9+10+9+10+9+7 = 60行

        c0 = char_names[0]
        c1 = char_names[1] if len(char_names) > 1 else c0
        all_lines = []
        for sec_idx, (sec_title, sec_lines, sec_guide, sec_mood) in enumerate(sections):
            print(f"    📝 Section {sec_idx+1}/{len(sections)}: {sec_title} ({sec_lines}行, mood={sec_mood})")
            section_prompt = f"""ゆっくり解説1セクションのセリフをJSON配列のみで出力。

# チャンネル: {channel.name} / {channel.concept}
# キャラ: {c0} と {c1} を交互
# テーマ: {theme["title"]} / 切り口:{theme.get("angle","")}
# セクション: {sec_title}
# 内容: {sec_guide}
# 雰囲気(mood): "{sec_mood}" — このセクション全行で必ず "mood":"{sec_mood}" を付与する。
# 行数: 厳密に{sec_lines}行(過不足不可)
# 各行: 90〜120字(目標100字、上限120字)。89字以下も121字以上も不合格。研究データ/数字/例え/歴史を盛る。短い相槌のみ禁止。

# speaker欄は必ず「{c0}」「{c1}」(このチャンネルのキャラ名そのまま)を使う。他の表記揺れは crash の原因になる。
# text本文内で相手を呼ぶときも上記の「{c0}」「{c1}」と完全一致の表記を使う。

[
 {{"speaker":"{c0}","text":"...","expression":"normal","mood":"{sec_mood}"}},
 {{"speaker":"{c1}","text":"...","expression":"normal","mood":"{sec_mood}"}}
]
"""
            messages = [
                {"role": "system", "content": f"JSON配列のみ。各行90〜120字。89字以下も121字以上も不可。speaker欄は必ず「{c0}」または「{c1}」のいずれか(表記揺れ禁止)。"},
                {"role": "user", "content": section_prompt},
            ]
            self._current_purpose = f"section_{sec_idx+1}"
            try:
                raw = self._call_gpt(messages, temperature=0.8, max_tokens=3000)
                lines = self._extract_json(raw)
                if isinstance(lines, list):
                    for ln in lines:
                        if isinstance(ln, dict) and not ln.get("mood"):
                            ln["mood"] = sec_mood
                    all_lines.extend(lines)
            except Exception as e:
                print(f"      ⚠️ Section {sec_idx+1} failed: {e}")
                continue

        # If sectional generation produced enough, replace; otherwise merge with original
        new_chars = sum(len(l.get("text", "")) for l in all_lines if isinstance(l, dict))
        if len(all_lines) >= target_lines * 0.8 and new_chars >= target_chars * 0.8:
            base_scenario["full_scenario"] = all_lines
        elif new_chars > sum(len(l.get("text", "")) for l in existing_full if isinstance(l, dict)):
            # Use whichever is longer
            base_scenario["full_scenario"] = all_lines

        return base_scenario

    def generate_batch(
        self,
        channel,
        count: int = 3,
        exclude_themes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """複数テーマを一括生成"""
        exclude = set(exclude_themes or [])
        available = [s for s in channel.theme_seeds if s["title"] not in exclude]

        if not available:
            raise ValueError(f"No available themes for channel {channel.id}")

        selected = random.sample(available, min(count, len(available)))
        results = []
        for theme in selected:
            try:
                result = self.generate(channel, theme_override=theme)
                results.append(result)
                print(f"  ✅ Generated: {result['title']}")
            except Exception as e:
                print(f"  ❌ Failed: {theme['title']} — {e}")
        return results

    def _theme_priority_block(self, channel, count: int) -> str:
        """チャンネルごとの「テーマ優先順位ルール」ブロックを構築する。

        `channel._raw["theme_priority"]` の dict から組み立てる。形式:
          {
            "label": "SCP財団題材",            # 必須カテゴリの呼び名
            "categories": ["...", "..."],      # 最優先カテゴリ群
            "required_count_per_batch": 3,     # count 件中最低この数を上記から
            "good_examples": ["...", "..."],   # ✅ お手本
            "avoid_categories": ["..."],       # ❌ このチャンネルでは禁止
            "title_style": "...",              # 任意・タイトル書式の指示
            "viral_hooks": "..."               # 任意・バズる条件の言い換え
          }

        未設定なら「チャンネルコンセプトから絶対にズレない」だけの最小ルールを返す
        （以前のように汎用デフォルトで日常科学を強制しない）。
        """
        cfg = {}
        try:
            cfg = (channel._raw or {}).get("theme_priority") or {}
        except AttributeError:
            cfg = {}

        if not cfg:
            return (
                "# テーマ優先順位ルール(必須・絶対厳守)\n"
                f"- 本チャンネル「{channel.name}」のコンセプト（{channel.concept}）から"
                "ジャンルがズレるテーマは一切提案しない。\n"
                "- 競合や過去テーマの題材レンジに収まる新しい切り口だけを選ぶ。\n"
                "- タイトルは疑問型・意外性重視で、結論はサムネ・本編で初めて出す。\n"
            )

        label = cfg.get("label") or "本チャンネルのコア題材"
        categories = cfg.get("categories") or []
        good_examples = cfg.get("good_examples") or []
        avoid_categories = cfg.get("avoid_categories") or []
        required = cfg.get("required_count_per_batch")
        title_style = cfg.get("title_style") or (
            "タイトルは疑問型・意外性重視で書く。結論をタイトルに含めない。"
        )
        viral = cfg.get("viral_hooks") or (
            "「なぜ〇〇なのか」系 / 意外性 / 数字データ / 視聴者の好奇心への接続"
        )

        cat_lines = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(categories)) or "  (未指定)"
        good_lines = "\n".join(f"  - 「{g}」" for g in good_examples)
        avoid_lines = "\n".join(f"  - {a}" for a in avoid_categories)

        parts: List[str] = []
        parts.append("# テーマ優先順位ルール(必須・絶対厳守)")
        parts.append(f"- 最優先カテゴリ（{label}）:")
        parts.append(cat_lines)
        if required and required > 0:
            parts.append(
                f"- {count}件のうち**{required}件以上**は上記カテゴリから提案すること(必須)。"
            )
        else:
            parts.append("- 提案テーマは原則すべて上記カテゴリの範囲内に収める。")
        if good_lines:
            parts.append("- ✅ 良い例(参考・そのまま使わず切り口だけ参考にする):")
            parts.append(good_lines)
        if avoid_lines:
            parts.append("- ❌ 本チャンネルでは禁止カテゴリ(提案したら不合格):")
            parts.append(avoid_lines)
        parts.append(f"- {title_style}")
        parts.append("")
        parts.append(f"# バズる条件: {viral}")
        return "\n".join(parts) + "\n"

    def suggest_themes(
        self,
        channel,
        count: int = 5,
        *,
        include_trends: bool = True,
        extra_excluded: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """GPT にチャンネルコンセプトに合う新テーマを提案させる。

        既存の theme_seeds と、過去に生成済みのシナリオに含まれるテーマの両方を考慮し、
        - 完全な新規テーマ、または
        - 過去テーマの「続編・発展系・別角度・深掘り」（parent_title 付き）
        を提案させる。重複・言い換えは禁止。

        Phase C: include_trends=True なら Google Trends / YouTube 急上昇を取得して
        プロンプトに注入し、トレンドに乗ったテーマには ``is_trending: true`` を付与する。

        Args:
            extra_excluded: 追加で除外したいタイトル群（ThemeQueue 内の未消費ストック等）。
        """
        seed_titles = [s["title"] for s in channel.theme_seeds if s.get("title")]
        past_themes = self._collect_past_themes(channel.id, limit=40)
        past_titles = [t["title"] for t in past_themes]
        extras = [t for t in (extra_excluded or []) if isinstance(t, str) and t.strip()]

        seen = set()
        excluded: List[str] = []
        for t in seed_titles + past_titles + extras:
            key = t.lower()
            if key and key not in seen:
                seen.add(key)
                excluded.append(t)

        excluded_block = "\n".join(f"- {t}" for t in excluded) if excluded else "(なし)"
        past_seen = set()
        past_unique: List[str] = []
        for t in past_themes:
            key = t["title"].lower()
            if key not in past_seen:
                past_seen.add(key)
                past_unique.append(t["title"])
            if len(past_unique) >= 20:
                break
        past_block = "\n".join(f"- {t}" for t in past_unique) if past_unique else "(なし)"

        # Phase F-2: 競合のホット動画 / gap_topics を提案プロンプトへ注入
        competitor_block = ""
        try:
            from pipeline.analytics.competitor_intelligence import build_competitor_context
            ctx = build_competitor_context(channel.id)
            if ctx.get("available"):
                parts: List[str] = []
                hot = ctx.get("competitor_hot_topics") or []
                if hot:
                    parts.append("# 競合の最近の人気動画（被りを避け、切り口で差別化）")
                    for h in hot[:8]:
                        views = h.get("views") or 0
                        parts.append(f"- 「{h['title']}」（{views:,} 再生 / {h.get('competitor','')}）")
                gaps = ctx.get("gap_topics") or []
                if gaps:
                    parts.append("")
                    parts.append("# 競合がまだカバーしていない可能性のあるテーマ（優先的に提案）")
                    for g in gaps[:6]:
                        parts.append(f"- {g}")
                if parts:
                    parts.insert(0, "")
                    competitor_block = "\n".join(parts)
                    print(
                        f"  🥷 Injecting competitor signals "
                        f"(hot:{len(hot)}, gaps:{len(gaps)})"
                    )
        except Exception as e:
            print(f"  ⚠️ competitor signal injection failed: {e}")

        # Phase C: トレンド情報を取得してプロンプトへ注入
        trend_block = ""
        trend_keywords: List[str] = []
        if include_trends:
            try:
                from pipeline.trend_fetcher import fetch_combined_trends, build_prompt_block
                combined = fetch_combined_trends(channel)
                trend_block = build_prompt_block(combined) or ""
                trend_keywords = (
                    list(combined.get("relevant_to_channel") or [])
                    + list(combined.get("google_trends") or [])
                    + list(combined.get("youtube_keywords") or [])
                )
                if trend_block:
                    print(
                        f"  📈 Injecting trends (sources: {combined.get('sources_used')}, "
                        f"relevant: {len(combined.get('relevant_to_channel') or [])})"
                    )
            except Exception as e:
                print(f"  ⚠️ trend fetch failed: {e}")

        theme_priority_block = self._theme_priority_block(channel, count)

        prompt = f"""YouTube動画テーマを{count}個提案。JSON配列のみ。

# チャンネル: {channel.name} / {channel.concept} / {channel.style} / {channel.content_policy.get("tone","friendly")}

# 重複回避ルール（厳守）
- 下記「除外リスト」と同じ／実質同じ（言い換えだけ）テーマは禁止。
- ただし、過去テーマを「続編・発展系・別角度・深掘り」として明確に進化させる場合に限り、関連トピックを扱ってよい。
  - その場合、`parent_title` に元の過去テーマのタイトルを入れる。
  - `title` には元と被らない新しい切り口を必ず含める（例: 元「なぜ空は青いのか」→ 新「なぜ夕焼けは赤いのか — 空の色シリーズ続編」）。
- {count}件のうち最大2件まで「過去テーマの発展系（parent_title 付き）」を含めてよい。残りは完全新規のテーマで提案する。
- 完全新規のテーマは `parent_title` を null にする。

# 除外リスト（重複・言い換え禁止）
{excluded_block}

# 直近の過去テーマ（続編・発展系の元ネタとして参照可）
{past_block}

# 出力フォーマット
[
 {{"title": "テーマ", "angle": "切り口", "parent_title": null, "is_trending": false, "trend_match": null}},
 {{"title": "テーマ", "angle": "切り口", "parent_title": "元の過去テーマのタイトル", "is_trending": true, "trend_match": "該当トレンドワード"}}
]

# トレンド連動ルール
- 後述「現在のトレンド」セクションのキーワードと自然に結びつくテーマは `is_trending: true` にし、`trend_match` に該当キーワードを入れる。
- 結びつかない／無理な場合は `is_trending: false`, `trend_match: null`。

{theme_priority_block}
# 競合との差別化ルール
- 上記「競合の最近の人気動画」と完全に同じテーマは禁止。
- 競合が扱っている話題に乗る場合は、必ず別角度・別データ・別の意外な切り口を `angle` に明記。
- 「競合がまだカバーしていない可能性のあるテーマ」リストの内容は優先的に提案して構わない。
{competitor_block}
{trend_block}
"""

        messages = [
            {"role": "system", "content": "JSON配列のみ。除外リストとの重複・言い換えは厳禁。"},
            {"role": "user", "content": prompt},
        ]

        self._current_channel_id = channel.id
        self._current_purpose = "theme_suggest"
        # 429 / quota 切れに強くするため GPT→Claude フォールバック付きで呼ぶ。
        # 件数に応じて max_tokens を確保（多数提案時の末尾切れ＝JSON parse 失敗を防ぐ）。
        suggest_tokens = max(2000, 320 * count + 800)
        raw = self._call_text_with_fallback(messages, temperature=0.9, max_tokens=suggest_tokens, gpt_model=GPT_MODEL_LIGHT)
        themes = self._extract_json(raw)

        if isinstance(themes, list):
            from pipeline.auto_scenario import theme_dedup as _td

            # 1) 語彙的重複フィルタ — 除外リスト（seed/過去/キュー）と言い回し違いも弾く
            kept: List[Dict[str, Any]] = []
            for t in themes:
                if not isinstance(t, dict):
                    continue
                title = (t.get("title") or "").strip()
                if not title:
                    continue
                hit = _td.find_lexical_duplicate(title, excluded)
                # 候補同士の重複も畳む（同一バッチ内の言い換え重複を防ぐ）
                if hit is None:
                    hit = _td.find_lexical_duplicate(title, [k["title"] for k in kept])
                if hit is not None:
                    print(f"  ♻️ lexical dup dropped: '{title}' ≈ '{hit[0]}' ({hit[1]:.2f})")
                    continue
                kept.append(t)
            themes = kept

            # 2) 意味的重複フィルタ — 語彙が違うのに実質同義のものを LLM で弾く
            #    （過去テーマに対してのみ。バッチ内重複は語彙段で概ね畳めている）
            if themes and past_unique:
                try:
                    themes, dropped = _td.semantic_filter(
                        themes, past_unique,
                        llm_call=lambda msgs: self._call_text_with_fallback(
                            msgs, temperature=0.0, max_tokens=1500, gpt_model=GPT_MODEL_LIGHT),
                    )
                    for cand, matched in dropped:
                        print(f"  ♻️ semantic dup dropped: '{cand.get('title')}' ≈ '{matched}'")
                except Exception as e:
                    print(f"  ⚠️ semantic dedup skipped: {e}")

            # Phase C: トレンドスコアを付与（GPT が is_trending を返さなくても局所判定で埋める）
            if trend_keywords:
                try:
                    from pipeline.trend_fetcher import score_theme_against_trends
                    for t in themes:
                        if not isinstance(t, dict):
                            continue
                        title = (t.get("title") or "").strip()
                        score = score_theme_against_trends(title, trend_keywords)
                        t["trend_score"] = score
                        # is_trending が未指定なら自動補完
                        if "is_trending" not in t:
                            t["is_trending"] = score >= 0.34
                        # trend_match 未指定 & スコアが付いたら、最初に被ったキーワードを記録
                        if t.get("is_trending") and not t.get("trend_match"):
                            from pipeline.trend_fetcher import _tokens
                            ttoks = set(_tokens(title))
                            for kw in trend_keywords:
                                if set(_tokens(kw)) & ttoks:
                                    t["trend_match"] = kw
                                    break
                except Exception as e:
                    print(f"  ⚠️ trend scoring failed: {e}")
        return themes

    @staticmethod
    def _extract_json(text: str) -> Any:
        """テキストからJSON部分を抽出（コードフェンス欠落・前置き・末尾切れに耐性）。"""
        import re as _re

        if text is None:
            raise ValueError("empty response")
        raw = text.strip()

        # 1) コードフェンスがあれば中身を取り出す（閉じフェンスが無くても可）
        candidate = raw
        fence = _re.search(r"```(?:json)?\s*", candidate, _re.IGNORECASE)
        if fence:
            inner = candidate[fence.end():]
            close = inner.find("```")
            candidate = (inner[:close] if close != -1 else inner).strip()

        # 2) まずそのまま試す
        try:
            return json.loads(candidate)
        except Exception:
            pass

        # 3) 最初の JSON 配列 / オブジェクトを貪欲に抽出して試す
        for pattern in (r"\[.*\]", r"\{.*\}"):
            m = _re.search(pattern, candidate, _re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    continue

        # 4) 全部失敗 — 元テキストでの json.loads エラーを送出
        return json.loads(candidate)

    def save_scenario(self, result: Dict, output_dir: str = None) -> str:
        """生成されたシナリオをJSONファイルとして保存"""
        from pathlib import Path
        import re

        if output_dir is None:
            base = Path(__file__).parent.parent.parent.parent / "data" / "scenarios" / result["channel_id"]
        else:
            base = Path(output_dir)

        base.mkdir(parents=True, exist_ok=True)

        # ファイル名: タイトルをサニタイズ
        safe_title = re.sub(r'[^\w\s-]', '', result["title"])[:50].strip()
        safe_title = re.sub(r'\s+', '_', safe_title)
        file_path = base / f"{safe_title}.json"

        # 重複回避
        counter = 1
        while file_path.exists():
            file_path = base / f"{safe_title}_{counter}.json"
            counter += 1

        file_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"💾 Scenario saved: {file_path}")
        return str(file_path)
