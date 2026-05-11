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
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from pipeline import api_usage
except ImportError:  # pragma: no cover — running as a script
    api_usage = None

# GPT models. Main scenario keeps gpt-4o (long-form Japanese, strict length rules).
# Theme suggestion uses gpt-4o-mini (~16x cheaper, low quality risk for short JSON).
GPT_MODEL = "gpt-4o"
GPT_MODEL_LIGHT = "gpt-4o-mini"


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
        """
        past_titles = {t["title"].lower() for t in self._collect_past_themes(channel.id, limit=80)}
        unused = [s for s in channel.theme_seeds if (s.get("title") or "").lower() not in past_titles]
        if unused:
            return random.choice(unused)
        try:
            suggestions = self.suggest_themes(channel, count=3)
            if isinstance(suggestions, list) and suggestions:
                pick = random.choice(suggestions)
                if isinstance(pick, dict) and pick.get("title"):
                    print(f"  💡 All seeds used — using AI-suggested theme: {pick['title']}")
                    return {"title": pick["title"], "angle": pick.get("angle", "") or ""}
        except Exception as e:
            print(f"  ⚠️ AI fresh-theme fallback failed: {e}")
        return random.choice(channel.theme_seeds)

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

# 尺ルール(絶対厳守・違反は不合格)
- **full_scenarioは必ず{floor_lines}〜{target_lines+4}行**(目標{target_lines}行)。{floor_lines}行未満も{target_lines+5}行以上も不合格。
- **各行は90〜120字**(目標100字、上限120字)。89字以下も121字以上も不合格。
- **総文字数は{target_chars}〜{max_chars}字**(最低{floor_chars}字、上限{max_chars}字)。約{target_duration/60:.1f}分目標。
- 各行に研究データ・具体的数字・例え話・歴史エピソードを必ず盛る。短い相槌のみ(「うん」「そうだね」)禁止。
- VOICEVOX1.3x≒7.8字/秒。{target_chars}字で約{target_duration/60:.1f}分、{max_chars}字で約{max_chars/7.8/60:.1f}分。

# ショート尺ルール(絶対厳守)
- **short_scenarioは必ず6行**(各行30〜45字、目標38字)。
- **総文字数は必ず{short_target_chars-30}〜{short_target_chars+30}字**(目標{short_target_chars}字)で**約30秒**を実現。
- 構成(6行固定):
  1行目=**強フック**: 「えっ、そうなの!?」「実は…」「知ってた?」など意外性で始める。常識を覆す問い or 衝撃の事実で視聴者の指を止める。
  2行目=**ツカミ展開**: フックの答えに繋がる前振り or 共感ポイント。
  3〜4行目=**核となる事実**: ここに**具体的な数字・年号・%・研究データ・固有名詞のいずれか1つ以上を必ず含める**(例:「実は97%の人が…」「1923年に…」「東大の研究で…」)。「へぇ!」と感心させる中身を入れる。抽象論・一般論だけはNG。
  5行目=**納得のオチ**: 短くスパッと結論。投げっぱなし禁止。
  6行目=**本編誘導CTA(必須)**: 「詳しくは本編で解説してるよ!」「続きは本編をチェック!」「もっと深い話は本編で!」など、最後は必ず本編への誘導で締める。これは絶対省略禁止。
- 浅い感想・誰でも言える一般論(「すごいね」「びっくりだね」だけ)で行を埋めるのは不合格。1本のショートで最低1つは「初めて知った」と思わせる具体情報を入れること。

# 構成(full): CTA+導入(6行) → 問いと背景(7行) → 基本メカニズム(12行) → 詳細&研究データ(12行) → 意外な事実&歴史(10行) → 応用Tips(8行) → 締めCTA(5行) = 計60行

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

# 尺ルール(絶対厳守・違反は不合格)
- **テキストは必ず{floor_lines}〜{target_lines+4}行**(目標{target_lines}行)。
- **各行は90〜120字**(目標100字、上限120字)。89字以下も121字以上も不合格。
- **総文字数は{target_chars}〜{max_chars}字**(約{target_duration/60:.1f}分目標、{max_chars}字で約{max_chars/7.8/60:.1f}分)。
- 各行に研究データ・数字・事例を必ず盛る。

# ショート尺ルール(絶対厳守)
- **short_scenarioは必ず6行**(各行30〜45字、目標38字)。
- **総文字数は必ず{short_target_chars-30}〜{short_target_chars+30}字**(目標{short_target_chars}字)で**約30秒**を実現。
- 構成(6行固定):
  1行目=**強フック**: 「これは衝撃の事実だ」「あなたは知らない」など、意外性・謎・問題提起で視聴者を引き込む。
  2行目=**ツカミ展開**: フックを受けた前振り・状況説明。
  3〜4行目=**核となる事実**: ここに**具体的な数字・年号・%・研究データ・固有名詞のいずれか1つ以上を必ず含める**(例:「実は97%が…」「1923年の…」「ハーバード大の研究では…」)。視聴者が「初めて知った」と感じる中身を入れる。抽象論だけはNG。
  5行目=**納得のオチ**: スパッと結論を提示。投げっぱなし禁止。
  6行目=**本編誘導CTA(必須)**: 「詳しくは本編で解説しよう」「続きは本編で語る」「全貌は本編にて」など、最後は必ず本編への誘導で締める。省略禁止。
- 一般論・感想のみで埋めるのは不合格。1本につき最低1つは「へぇ」と思わせる具体情報を入れること。

# 雰囲気タグ(mood)ルール — シーンごとのBGM切替に使用
- 各行(章タイトル含む)に必ず "mood" を付与する。値は次の6種類のいずれか:
  - "calm"(穏やか) / "bright"(明るい) / "tense"(緊張・衝撃)
  - "emotional"(感動) / "funny"(コミカル) / "mysterious"(ミステリアス)
- 同じmoodを2〜10行ほど連続させて「シーン」を作る(毎行切替えない)。1章 = 1〜2シーン目安。
- 章タイトル行のmoodは、その章の主軸となる雰囲気と一致させる。

# その他ルール
- text内は1〜2文。文末「。」直後に `\\n` 挿入(例:"...だ。\\n...だ。")。
- 章タイトルで3〜5章に分割。
- 冒頭で衝撃→本題→意外な結論。科学的エビデンスベース。
- **ショートは「浅い豆知識」NG**: 誰でも知っている一般論ではなく、具体性のある事実・数字・固有名詞でフックを作ること。
- CTA配置: {cta_pos}
"""

    def generate(
        self,
        channel,  # ChannelProfile
        theme_override: Optional[Dict] = None,
        target_duration: Optional[int] = None,
        improvement_feedback: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        チャンネルプロファイルからシナリオを自動生成。

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

        # フル動画の最低行数 + 最低総文字数 + 1行あたり最低平均文字数
        # 実測: VOICEVOX 1.3x speed → 約7.8文字/秒（pause込み）
        # 720秒(12分目安) ≈ 5760文字 / 60行 → 1行平均96文字
        # 最低でも10分(600秒 / 4800文字 / 55行)を絶対に下回らないこと
        # 平均文字数チェック: 行数が足りても各行が短いと尺不足になる(例: 62行×67文字=4154文字=8.9分)
        ABSOLUTE_FLOOR_CHARS = 4800  # 10分 × 8.0文字/秒
        ABSOLUTE_FLOOR_LINES = 55
        MIN_AVG_CHARS_PER_LINE = 90  # 1行あたり平均下限
        if duration >= 120:
            min_full_lines = max(ABSOLUTE_FLOOR_LINES, int((duration / 60) * 4.6))
            max_full_lines = max(72, int((duration / 60) * 6.5))
            # 総文字数のフロア: duration秒 × 8.0文字/秒、ただし絶対に10分相当(4800)を割らない
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

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        print(f"🤖 GPT generating scenario: {theme['title']} ({channel.style}, target {duration}s, {min_full_lines}-{max_full_lines} lines)")

        # Track usage per channel
        self._current_channel_id = channel.id
        self._current_purpose = "scenario"

        def _line_text(entry):
            if isinstance(entry, dict):
                return entry.get("text", "")
            return ""

        scenario_data = None
        last_full_count = 0
        last_total_chars = 0
        last_avg_chars = 0.0
        last_short_avg = 0.0
        for attempt in range(2):
            raw = self._call_gpt(messages, temperature=0.85)
            try:
                scenario_data = self._extract_json(raw)
            except Exception as e:
                print(f"  ⚠️ JSON parse error on attempt {attempt+1}: {e}")
                continue
            full_lines = scenario_data.get("full_scenario", [])
            last_full_count = len(full_lines)
            last_total_chars = sum(len(_line_text(e)) for e in full_lines)
            last_avg_chars = (last_total_chars / last_full_count) if last_full_count > 0 else 0.0
            ok_lines = last_full_count >= min_full_lines
            ok_chars = last_total_chars >= min_full_chars
            ok_avg = last_avg_chars >= min_avg_chars
            if ok_lines and ok_chars and ok_avg:
                print(f"  ✅ full_scenario: {last_full_count} lines, {last_total_chars} chars, avg {last_avg_chars:.1f}/line (target ≥{min_full_lines} lines / ≥{min_full_chars} chars / ≥{min_avg_chars}/line)")
                break
            issue = []
            if not ok_lines:
                issue.append(f"行数 {last_full_count} 行（目標 {min_full_lines}〜{max_full_lines}）")
            if not ok_chars:
                issue.append(f"総文字数 {last_total_chars} 文字（目標 ≥{min_full_chars}）")
            if not ok_avg:
                issue.append(f"1行あたり平均 {last_avg_chars:.1f} 文字（目標 ≥{min_avg_chars}）")
            print(f"  ⚠️ {' / '.join(issue)} — Retrying...")
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": (
                    f"full不足({' / '.join(issue)})。{min_full_lines}〜{max_full_lines}行/計{min_full_chars}字以上/平均{min_avg_chars}字以上に増量。"
                    f"各行90〜150字、データ/数字/例え必須。89字以下禁止。JSONのみ再出力。"
                )
            })

        if scenario_data is None:
            raise ValueError("GPT failed to produce valid JSON after 2 attempts")

        # If we still don't meet the line/char/avg floor for long videos, expand sectionally
        if duration >= 300 and (last_full_count < min_full_lines or last_total_chars < min_full_chars or last_avg_chars < min_avg_chars):
            print(f"  🔁 Falling back to sectional expansion (current: {last_full_count} lines, {last_total_chars} chars, avg {last_avg_chars:.1f}/line)")
            try:
                scenario_data = self._expand_via_sections(channel, theme, scenario_data, duration, min_full_lines, min_full_chars)
                full_lines = scenario_data.get("full_scenario", [])
                last_full_count = len(full_lines)
                last_total_chars = sum(len(_line_text(e)) for e in full_lines)
                last_avg_chars = (last_total_chars / last_full_count) if last_full_count > 0 else 0.0
                print(f"  ✅ After expansion: {last_full_count} lines, {last_total_chars} chars, avg {last_avg_chars:.1f}/line")
            except Exception as e:
                print(f"  ⚠️ Sectional expansion failed: {e}")

        if last_full_count < min_full_lines or last_total_chars < min_full_chars or last_avg_chars < min_avg_chars:
            print(f"  ⚠️ Final: {last_full_count} lines, {last_total_chars} chars, avg {last_avg_chars:.1f}/line (wanted ≥{min_full_lines} lines / ≥{min_full_chars} chars / ≥{min_avg_chars}/line)")

        # Short scenario check (warning only — doesn't block)
        short_lines_data = scenario_data.get("short_scenario", [])
        if short_lines_data:
            short_total = sum(len(_line_text(e)) for e in short_lines_data)
            last_short_avg = short_total / len(short_lines_data)
            if last_short_avg < 30:
                print(f"  ⚠️ short_scenario: {len(short_lines_data)} lines, {short_total} chars, avg {last_short_avg:.1f}/line — under 30/line, may be under 30s")

        return {
            "title": scenario_data.get("title", theme["title"]),
            "theme": theme,
            "short_scenario": scenario_data.get("short_scenario", []),
            "full_scenario": scenario_data.get("full_scenario", []),
            "thumb_info": scenario_data.get("thumb_info", {}),
            "channel_id": channel.id,
            "style": channel.style,
            "applied_feedback": applied_feedback_ids,
        }

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
            ("CTA + 導入フック", 6, "視聴者の興味を引く問いかけ + チャンネル登録CTA", "bright"),
            ("基本メカニズム解説", 9, "テーマの基本原理を分かりやすく説明。専門用語は噛み砕く", "calm"),
            ("具体的な仕組み・研究データ", 10, "研究データ・具体的な数字・パーセンテージ・代表的な実験", "calm"),
            ("背景・歴史的経緯", 9, "発見・研究の経緯、歴史的エピソードや人物", "mysterious"),
            ("意外な事実・補足知識", 10, "視聴者が驚く意外な情報や雑学・トリビア", "tense"),
            ("日常への応用・実践Tips", 9, "視聴者が今日から使える実践的なTips・応用例", "bright"),
            ("まとめ + 締めCTA", 6, "今日の内容を簡潔にまとめ + 高評価/登録CTA", "emotional"),
        ]
        # 合計目標: 6+9+10+9+10+9+6 = 59行

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

    def suggest_themes(self, channel, count: int = 5) -> List[Dict[str, str]]:
        """GPT にチャンネルコンセプトに合う新テーマを提案させる。

        既存の theme_seeds と、過去に生成済みのシナリオに含まれるテーマの両方を考慮し、
        - 完全な新規テーマ、または
        - 過去テーマの「続編・発展系・別角度・深掘り」（parent_title 付き）
        を提案させる。重複・言い換えは禁止。
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
 {{"title": "テーマ", "angle": "切り口", "parent_title": null}},
 {{"title": "テーマ", "angle": "切り口", "parent_title": "元の過去テーマのタイトル"}}
]

# バズる条件: 「なぜ〇〇なのか」系 / 意外性 / 日常と科学のギャップ / 数字データ
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
