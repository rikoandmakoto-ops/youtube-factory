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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    from pipeline import api_usage
except ImportError:  # pragma: no cover — running as a script
    api_usage = None

try:
    from pipeline import claude_client
except Exception:  # pragma: no cover — module not yet importable
    claude_client = None  # type: ignore

# GPT models. Main scenario keeps gpt-4o (long-form Japanese, strict length rules).
# Theme suggestion uses gpt-4o-mini (~16x cheaper, low quality risk for short JSON).
GPT_MODEL = "gpt-4o"
GPT_MODEL_LIGHT = "gpt-4o-mini"
CLAUDE_MODEL = "claude-sonnet-4-20250514"


class ScenarioGenerator:
    """GPT APIを使ったシナリオ自動生成"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        # Set by callers to attribute usage to a channel
        self._current_channel_id: Optional[str] = None
        self._current_purpose: Optional[str] = None

    def _call_gpt(self, messages: List[Dict], temperature: float = 0.8, max_tokens: int = 8000, model: Optional[str] = None) -> str:
        """GPT API呼び出し"""
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

        use_model = model or GPT_MODEL
        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps({
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST",
                                     headers={
                                         "Content-Type": "application/json",
                                         "Authorization": f"Bearer {self.api_key}",
                                     })
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())

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
        temperature: float = 0.85,
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

        return f"""ゆっくり解説動画のシナリオを生成。JSONのみ出力。

# チャンネル: {channel.name} / {channel.concept} / トーン:{tone} / CTA:{cta_style}
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
  1行目=**強フック**: 「えっ、そうなの!?」「実は…」「知ってた?」など意外性で始める。常識を覆す問い or 衝撃の事実で視聴者の指を止める。
  2行目=**ツカミ展開**: フックの答えに繋がる前振り or 共感ポイント。
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

# その他ルール
- text内は1〜2文で完結。文末「。」直後に改行 `\\n` を入れる(例:"...だ。\\nだから...")。
- **speaker欄は必ず漢字「{c0}」「{c1}」を使う**(カタカナ「リコ」「マコト」を speaker に書くと crash する)。
- text本文のキャラ名はカタカナ「リコ」「マコト」(漢字はTTS誤読のため text 内では禁止)。
- expression: {c0}は{expr0}から / {c1}は{expr1}から選ぶ。
- 科学的・エビデンスベース。冒頭で驚き→なぜ→解説→意外な結論。
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

        return f"""ドキュメンタリー風ナレーション動画のシナリオを生成。JSONのみ出力。

# チャンネル: {channel.name} / {channel.concept} / トーン:{tone}
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
- 冒頭で共感フック→本題→意外な結論。科学的エビデンスベース。
- **ショートは「浅い豆知識」NG**: 誰でも知っている一般論ではなく、具体性のある事実・数字・固有名詞でフックを作ること。
- CTA配置: {cta_pos}
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
        for attempt in range(2):
            try:
                if provider == "gpt":
                    raw = self._call_gpt(msgs, temperature=0.85)
                else:
                    raw = self._call_claude_text(msgs, temperature=0.85)
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
    ) -> Dict[str, Any]:
        """
        チャンネルプロファイルからシナリオを自動生成。

        ANTHROPIC_API_KEY が設定されていれば GPT と Claude の両方で並列生成し、
        ブラインド評価で勝者を採用する（"AI モデル間コンペ"）。未設定なら GPT のみ。

        Args:
            improvement_feedback: いいね率改善ループからの未消費フィードバック。
                pipeline.analytics.feedback_store.get_pending_for_channel(...) の戻り値
                をそのまま渡す想定。GPT プロンプトに改善方針として注入される。

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
        else:
            raise ValueError(f"No theme_seeds for channel {channel.id}")

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
        if channel.style == "monologue":
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

        # フル動画の最低行数 + 最低総文字数 + 1行あたり最低平均文字数
        ABSOLUTE_FLOOR_CHARS = 4800  # 10分 × 8.0文字/秒
        ABSOLUTE_FLOOR_LINES = 55
        MIN_AVG_CHARS_PER_LINE = 90
        if duration >= 120:
            min_full_lines = max(ABSOLUTE_FLOOR_LINES, int((duration / 60) * 4.6))
            max_full_lines = max(72, int((duration / 60) * 6.5))
            min_full_chars = max(ABSOLUTE_FLOOR_CHARS, int(duration * 8.0))
            min_avg_chars = MIN_AVG_CHARS_PER_LINE
        else:
            min_full_lines = 5
            max_full_lines = 999
            min_full_chars = 0
            min_avg_chars = 0

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
            ("まとめ + 次回予告 + 締めCTA", 7, "今日の内容を簡潔にまとめ → **『次回は〇〇を解説するよ』のような次回予告を必ず1〜2行入れる(身近な体の不思議・日常の違和感系から提案)** → 高評価/登録CTA。次回予告は登録率改善のため絶対省略禁止。", "emotional"),
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

# speaker欄は必ず漢字「{c0}」「{c1}」を使う(カタカナ「リコ」「マコト」を speaker に書くと crash する)。
# text本文のキャラ名はカタカナ「リコ」「マコト」(漢字はTTS誤読のため text 内では禁止)。

[
 {{"speaker":"{c0}","text":"...","expression":"normal","mood":"{sec_mood}"}},
 {{"speaker":"{c1}","text":"...","expression":"normal","mood":"{sec_mood}"}}
]
"""
            messages = [
                {"role": "system", "content": "JSON配列のみ。各行90〜120字。89字以下も121字以上も不可。speaker欄は必ず漢字。"},
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

    def suggest_themes(
        self,
        channel,
        count: int = 5,
        *,
        include_trends: bool = True,
    ) -> List[Dict[str, str]]:
        """GPT にチャンネルコンセプトに合う新テーマを提案させる。

        既存の theme_seeds と、過去に生成済みのシナリオに含まれるテーマの両方を考慮し、
        - 完全な新規テーマ、または
        - 過去テーマの「続編・発展系・別角度・深掘り」（parent_title 付き）
        を提案させる。重複・言い換えは禁止。

        Phase C: include_trends=True なら Google Trends / YouTube 急上昇を取得して
        プロンプトに注入し、トレンドに乗ったテーマには ``is_trending: true`` を付与する。
        """
        seed_titles = [s["title"] for s in channel.theme_seeds if s.get("title")]
        past_themes = self._collect_past_themes(channel.id, limit=40)
        past_titles = [t["title"] for t in past_themes]

        seen = set()
        excluded: List[str] = []
        for t in seed_titles + past_titles:
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

# テーマ優先順位ルール(必須・CTR/維持率改善のため絶対厳守)
- 最優先カテゴリ(視聴者が今日体験している現象 = 高CTR・高維持率):
  1. 「身近な体の不思議」: 自分の声・骨伝導・痛覚・記憶・睡眠・くしゃみ・あくび・しゃっくり・耳鳴り・夢など、視聴者自身の体で起きる現象
  2. 「日常の違和感」: なぜそうなる? と一度は感じたことのある身近な現象(水たまり・信号・電車・スマホ・冷蔵庫など、毎日目にするもの)
- {count}件のうち**3件以上**は上記カテゴリから提案すること(必須)。
- 良い例(参考):
  - 「自分の声が録音だと変に聞こえる本当の理由 — 骨伝導の謎」
  - 「暗い部屋でスマホが目に悪い『本当の』理由」
  - 「もし地球から1秒だけ酸素が消えたら何が起こるのか」
  - 「アイスで頭がキーンとする現象が長年解明されていなかった理由」
  - 「夢で見たことを朝には忘れてしまう本当の理由」
- 抽象的・遠い話題(宇宙の起源・量子論の数式・古代文明の謎)は{count}件中最大1件まで。視聴者の手の届く範囲の現象を優先する。
- タイトルは「なぜ〇〇なのか」「〇〇の本当の理由」のような疑問型・意外性重視で書く。結論をタイトルに含めない。

# バズる条件: 「なぜ〇〇なのか」系 / 意外性 / 日常と科学のギャップ / 数字データ / 視聴者自身の体験との接続

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
        raw = self._call_gpt(messages, temperature=0.9, max_tokens=2000, model=GPT_MODEL_LIGHT)
        themes = self._extract_json(raw)

        if isinstance(themes, list):
            excluded_lower = {t.lower() for t in excluded}
            filtered = [
                t for t in themes
                if isinstance(t, dict) and (t.get("title") or "").strip().lower() not in excluded_lower
            ]
            if filtered:
                themes = filtered

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
        """テキストからJSON部分を抽出"""
        # コードブロック内のJSON
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        # 直接JSONの場合
        text = text.strip()
        return json.loads(text)

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
