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
import re
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

# ファクトオーバーレイ（company-facts）の尺モデル。
# 1画面 = ナレーション 25〜40字（VOICEVOX 1.3x の実効 8.9字/秒で 2.8〜4.5秒）+ 間 ≒ 5秒。
# 末尾の CTA 画面は固定文言なので約6秒で見積もる。
# fact_count と1画面の文字数をこの2定数から逆算して、指定尺と実尺のズレを潰す。
_FACTS_SECONDS_PER_SCREEN = 5.0
_FACTS_CTA_SECONDS = 6.0

# ショートの最適尺。これを外れた値が渡ってきたら丸める。
# 【2026-08-25 実測により 30/50/40 から変更】08-19 の 786d314 で 30〜50 秒帯に広げた結果、
# 実尺が 42〜55 秒に膨らみ、維持率が 54% → 29% に半減、リーチも全ch で 24〜80% 減少した。
# 平均視聴秒数は前後どちらも 15〜16 秒で不変（＝視聴者は尺に関係なく 15 秒で離脱する）ため、
# 尺を伸ばした分がそのまま維持率の希釈になっていた。20〜34 秒帯（既定 26 秒）に戻す。
SHORT_DURATION_MIN = 20
SHORT_DURATION_MAX = 34
SHORT_DURATION_DEFAULT = 26


def _clamp_short_duration(channel, target_duration: Optional[int]) -> int:
    """ショート専用スタイルの目標尺を 20〜34 秒に丸める。

    autopilot は長尺用の `duration_minutes`（既定12分）から target_duration=720 を
    渡してくるので、ショート専用チャンネルではそのまま使えない。チャンネルの
    `defaults.target_duration` がショート帯なら優先し、無ければ既定 26 秒。
    """
    try:
        configured = int((channel.defaults or {}).get("target_duration") or 0)
    except (AttributeError, TypeError, ValueError):
        configured = 0
    for cand in (target_duration or 0, configured):
        if SHORT_DURATION_MIN <= int(cand) <= SHORT_DURATION_MAX:
            return int(cand)
    return SHORT_DURATION_DEFAULT

# =====================================================================
# early 区間（15〜25%地点）の離脱対策ルール
#
# 2026-08-04 の日次 PDCA レポートで、両チャンネルとも視聴維持率の谷が
# 冒頭フック直後の early 区間（動画全体の 15〜25% 地点）に出ていた。
# 「フックで掴む → 直後に説明が続いて失速」が離脱の主因なので、
#   1. 20% 地点に必ず第二フック（驚き・反転・予告）を置く
#   2. 相槌だけの行を作らない（必ず新情報か問いかけを添える）
#   3. 1セリフ = 1事実に絞る（1行に情報を詰め込むと処理落ちして離脱する）
# の 3 点を全生成経路（yukkuri / monologue / セクション拡張）で共有する。
#
# 2026-08-11 追記: 序盤 1〜3割地点で「専門用語の説明の直後」に 5〜10% の離脱が
# 出ていた（daily-science / scp-lab 共通）。用語解説で失速させないため、
#   4. 専門用語の説明は 1 文以内に収め、直後に具体例か驚きの事実を置く
#   5. 最も衝撃的な事実を冒頭 30% 以内に配置する
# を _TERM_PACING_RULE_* として同じく全生成経路で共有する。
# =====================================================================

_SECOND_HOOK_RULE_YUKKURI = """# 第二フックルール(early区間の離脱対策・絶対厳守)
- 視聴維持率の谷は**冒頭フックの直後（動画全体の15〜25%地点）**に出る。フックで掴んだ視聴者はここで落ちる。
- ✅ **full_scenarioの20%地点(先頭から全体の1/5あたりの行)に必ず「第二フック」を1行入れる**。ここは説明を止めて、次のいずれかを必ず置く:
  - 驚き型: 「実はこれ、〇〇でも同じことが起きてるんだ」のような想定外の飛び火。
  - 反転型: 「ここまで説明したけど、実はこれ、半分は間違いなんだ」のような前言のひっくり返し。
  - 予告型: 「そしてこの話、最後にとんでもないオチが待ってる」のような後半への引き。
- ✅ **ショート(short_scenario)は2行目が第二フック**。1行目の謎をさらに深くするか、「えっ、どういうこと!?」の食いつきで"まだ答えが出ていない"状態を強化する。
- ❌ 20%地点が「〜ということなんだね」「なるほど、つまり〜」のような要約・納得で埋まっているのは不合格。納得させると視聴者はそこで離脱する。

# 相槌ルール(絶対厳守)
- ❌ 相槌だけの行を作らない。「なるほど」「すごいね」「へぇ、そうなんだ」だけで終わる行は不合格。
- ✅ 相槌には**必ず「新情報」か「問いかけ」のどちらかを添える**。
  - 新情報つき: 「そうなんだ。でも確か〇〇のときは逆だったよね?」（自分の知識・体験を足す）
  - 問いかけつき: 「へぇ。じゃあ〇〇の場合はどうなるの?」（次の行への橋渡しを作る）
- リスナー役の行は、視聴者が今ちょうど抱いている疑問を代弁する場所であって、話を止める場所ではない。

# 1セリフ1事実ルール(絶対厳守)
- **1つのセリフで扱う事実は1つだけ**に絞る。1行に「数字」「研究」「歴史」「例え」を全部詰め込むと、聞いている側の処理が追いつかず離脱する。
- 事実が2つあるなら2行に割る。相手役のリアクションを挟んでから次の事実へ進む。
- 「A、そしてB、さらにC」のような列挙で1行を埋めない。1行 = 1メッセージ。字数は満たしつつ、内容は1点に集中させる(具体例・言い換え・例え話で厚みを出す)。
"""

_SECOND_HOOK_RULE_MONOLOGUE = """# 第二フックルール(early区間の離脱対策・絶対厳守)
- 視聴維持率の谷は**冒頭フックの直後（動画全体の15〜25%地点）**に出る。フックで掴んだ視聴者はここで落ちる。
- ✅ **本文の20%地点(先頭から全体の1/5あたりの行)に必ず「第二フック」を1行入れる**。説明を一度止めて、次のいずれかを置く:
  - 驚き型: 「だが、同じ現象は〇〇でも記録されている」
  - 反転型: 「ここまでが公式の記録だ。だが、その記録自体が書き換えられていた」
  - 予告型: 「そしてこの話には、最後に語られていない結末がある」
- ✅ **ショート(short_scenario)は2行目が第二フック**。答えを出さずに謎を一段深くする。
- ❌ 20%地点が総括・言い換え・納得で埋まっているのは不合格。

# 1行1事実ルール(絶対厳守)
- **1行で扱う事実は1つだけ**に絞る。数字・年号・証言・解釈を1行に詰め込まない。
- 事実が2つあるなら2行に割り、間に緊張や問いを挟んでから次へ進む。
- 「A、そしてB、さらにC」の列挙で行を埋めない。1行 = 1メッセージ。
"""

_SECOND_HOOK_RULE_SECTION = (
    "第二フック: このセクションが動画の20%地点にかかる場合、"
    "説明を止めて『驚き・反転・予告』のいずれかの一撃を必ず1行入れる。 / "
    "相槌だけの行は禁止(必ず新情報か問いかけを添える) / "
    "1セリフ1事実(1行に事実を詰め込まない。2つあるなら2行に割る)"
)

_TERM_PACING_RULE_YUKKURI = """# 専門用語ルール(序盤1〜3割の離脱対策・絶対厳守)
- **専門用語の説明は1文以内に収める**。用語の定義を2文以上かけて説明した時点で不合格。
- **説明した直後の同じ行、または次の1行以内に、必ず「具体例」か「驚きの事実」を置く**。
  - 具体例型: 「〇〇っていうのは要するに△△のことだよ。たとえば君がいま座ってる椅子でも同じことが起きてる」
  - 驚き型: 「〇〇は△△って意味なんだ。この〇〇、実は1日に3000回も起きてる」
- ❌ NG: 用語の定義 → その補足 → さらに前提知識、と説明が3行以上続く展開。序盤1〜3割はここで5〜10%が離脱する。
- 用語を出すたびにこの「1文の説明 + 具体例/驚き」のセットを守る。説明しきれない用語は**そもそも使わない**(日常語に言い換える)。

# 最強ファクト配置ルール(絶対厳守)
- **その動画で最も衝撃的な事実(いちばん『えっ!?』となる数字・結末・逆転)を、冒頭30%以内に必ず配置する**。
- ❌ NG: 最大のインパクトを終盤の「意外な事実」セクションまで温存すること。そこまで視聴者は残らない。
- ✅ 前半で最強の事実を出し切り、後半はその「なぜ」「その先」を掘る構成にする。出し惜しみは離脱を招くだけで、引きにはならない。
- ショート(short_scenario)では1〜2行目がこれに該当する。最強の事実を最初に置く。
"""

_TERM_PACING_RULE_MONOLOGUE = """# 専門用語ルール(序盤1〜3割の離脱対策・絶対厳守)
- **専門用語の説明は1文以内に収める**。定義を2文以上かけて語った時点で不合格。
- **説明した直後の同じ行、または次の1行以内に、必ず「具体例」か「驚きの事実」を置く**。
  - 具体例型: 「〇〇とは△△を指す。たとえば、いま読者が立っているその床でも同じことが起きている」
  - 驚き型: 「〇〇とは△△のことだ。そしてこの現象は、1日に3000回記録されている」
- ❌ NG: 定義 → 補足 → 前提知識、と説明が3行以上続く展開。序盤1〜3割はここで離脱が出る。
- 説明しきれない用語はそもそも使わない(平易な語に言い換える)。

# 最強ファクト配置ルール(絶対厳守)
- **最も衝撃的な事実(いちばん『えっ!?』となる数字・結末・逆転)を、冒頭30%以内に必ず配置する**。
- ❌ NG: 最大のインパクトを終盤まで温存すること。そこまで視聴者は残らない。
- ✅ 前半で最強の事実を出し切り、後半はその「なぜ」「その先」を掘る構成にする。
- ショート(short_scenario)では1〜2行目がこれに該当する。
"""

_TERM_PACING_RULE_SECTION = (
    "専門用語: 用語の説明は1文以内に収め、直後(同じ行か次の1行以内)に必ず"
    "具体例か驚きの事実を置く。定義の説明を3行以上続けない。 / "
    "最強ファクト: このセクションが動画の冒頭30%以内にかかる場合、"
    "動画で最も衝撃的な事実(数字・逆転・結末)をここで出し切る(終盤へ温存しない)"
)

# =====================================================================
# 2026 年のショート・アルゴリズム対策（全チャンネル共通）
#
# 調査結果:
#   - 冒頭 3 秒で「見続けるか」がほぼ決まる。1 行目は「問い」か「驚き」以外は無効。
#   - 30〜45 秒が最も伸びる（15 秒未満はリーチが激減する）。
#   - 1.5〜2 秒ごとの視覚変化（カット / ズーム / テロップ）で完視聴率が上がる。
#   - 画面中央の「10 文字以内・特大テロップ」がスクロールを止める最短の手段。
#   - 答えを 6 割だけ見せるクリフハンガーがチャンネル回遊 → 登録に効く。
#
# 冒頭 3 秒ルールとテロップ（hook_caption）ルールは全生成経路で共有する。
# クリフハンガー / シリーズ化はチャンネル JSON でのオプトイン。
# =====================================================================

_HOOK_3SEC_RULE = """# 冒頭3秒ルール(最重要・これを外した時点で不合格)
- ショートは**最初の3秒**で視聴継続がほぼ決まる。1行目は必ず「問い」か「驚き」から始める。
- ❌ 挨拶・自己紹介・チャンネル説明・テーマ紹介・前置き・「今回は〜」は1文字でも入れたら不合格。
- ✅ 1行目には**題材の固有名(現象・物・人物・番号の名前)を必ず入れる**。「これ」「ある〇〇」で名前を伏せない(フィードの視聴者にタイトルは見えていない)。
- ✅ 1行目は**次の4型のいずれかで書く**(型を丸写しせず、テーマに合わせて言い換える):
  1. 【これ知ってた?型】「これ知ってた? 〇〇って実は△△なんだ」— 共感と好奇心を同時に取る
  2. 【実は〇〇型】「実は〇〇、△△だったんだ」「〇〇してる人、今すぐやめて」— 常識をひっくり返す
  3. 【〇〇した結果型】「〇〇した結果、とんでもないことになった」— 結果を伏せて"続き"を作る
  4. 【違和感の問い型】「なんで〇〇だけ〇〇なの?」— 言われて初めて気づく違和感を突く
- 1行目は**15〜30字で断定的に**。ここで答えを言わない(答えを言うと3行目以降を見る理由が消える)。
- 「あなた」「君」「お前ら」など視聴者を直接指す語を1行目に入れると指が止まりやすい。
- ※ 上の「ショート尺ルール」で1行目の書式がチャンネル固有に指定されている場合はそちらを優先する。
  その書式のまま、中身が「問い」か「驚き」になるように言葉を選ぶこと(型の名前より役割を守る)。
"""

_HOOK_CAPTION_RULE = """# 冒頭テロップ(hook_caption)ルール(絶対厳守)
- thumb_info.hook_caption に**全角10文字以内**の超短文を必ず入れる。冒頭0〜3秒の**画面中央に特大テロップ**として自動で焼き込まれる。
- 1行目フックの"核"だけを抜いて言い切る。例:「実は逆でした」「99%が誤解」「触れたら終わり」「答えは3秒」。
- ❌ 句読点・カギ括弧・ハッシュタグ・絵文字は入れない。❌ 1行目の全文コピーも禁止。❌ 説明文にしない。
- 11文字以上は画面で縮んで読めなくなる。**必ず10文字以内**、短いほど強い(4〜8文字が理想)。
"""

# --- サムネ文字の長さゲート（2026-08-23 追加）---------------------------------
# プロンプトは以前から「hook_lines は各行8文字以内」と指示していたが、生成済み
# thumb_info 535 件を実測したところ 320 件（60%）が 10 文字超、subtitle は 231 件
# （43%）が 17 文字超だった。サムネ描画側は 1080px 幅に固定サイズで描いていたため、
# これらは画面外にはみ出して両端が切れていた（描画側も自動縮小するよう修正済み）。
# ここでは「そもそも長すぎるコピーを作らせない」側の担保として、生成直後に
# 自然な区切りで詰める。区切りが見つからない行は切らずに残す（意味を壊さない）。
_THUMB_HOOK_MAX = 14        # hook_lines 1行あたり（描画時 74px 相当まで確保できる長さ）
_THUMB_SUBTITLE_MAX = 24
_THUMB_TAGLINE_MAX = 26
_THUMB_TRIM_BREAKS = "、。！？!?・…　 —-"


def _trim_at_break(text: str, limit: int) -> str:
    """limit 以下で最後の自然な区切りまで詰める。区切りが無ければ原文のまま返す。"""
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    head = s[:limit]
    for i in range(len(head) - 1, max(limit // 2, 3), -1):
        if head[i] in _THUMB_TRIM_BREAKS:
            return head[:i].strip()
    return s


def _sanitize_regenerated_title(title: Optional[str]) -> Optional[str]:
    """LLM が作り直したタイトルの壊れを弾く。通せないものは None（＝元題を使う）。

    【2026-09-11 夜】company-facts で
    『個人向け国債、年0.05%でも元本割れしにくい仕組み、】【の実態』という題が
    実際に生成され、出力フォルダ名・サムネ・説明文まで `】【` を含んだまま
    レンダリングされた（job 1a6e3105）。作り直し後のタイトルは
    `.strip("「」")` しか通っておらず、括弧の破片や末尾の読点を誰も見ていない。

    【2026-09-12】実体は pipeline/title_gate.py に移した。タイトルが確定する経路は
    8段あり（本生成→絵文字→通し番号→AB→重複→CTR→規約→横断語）、段ごとに
    直しても別の段が壊れた値を持ち込める。作り直しはすべて `title_gate.llm_title`
    で受け、最終値は `generate()` の出口で `title_gate.finalize` を必ず通す。
    """
    from pipeline import title_gate as _tg
    return _tg.llm_title(title)


class ThemeRejectedError(ValueError):
    """テーマが運用側の停止設定（theme_blacklist / genre_blacklist）に当たり、
    代替も見つからなかった。生成を止める（止めないと設定が無意味になる）。"""


def _normalize_thumb_info(thumb_info) -> None:
    """thumb_info をサムネで読める長さに整える（in-place）。"""
    if not isinstance(thumb_info, dict):
        return
    hooks = thumb_info.get("hook_lines")
    if isinstance(hooks, list) and hooks:
        trimmed = [_trim_at_break(str(h), _THUMB_HOOK_MAX) for h in hooks[:2]]
        trimmed = [t for t in trimmed if t]
        if trimmed and trimmed != [str(h).strip() for h in hooks[:2]]:
            print(f"  ✂️ サムネ hook_lines を短縮: {hooks[:2]} → {trimmed}")
        if trimmed:
            thumb_info["hook_lines"] = trimmed
    for key, limit in (("subtitle", _THUMB_SUBTITLE_MAX), ("tagline", _THUMB_TAGLINE_MAX)):
        val = thumb_info.get(key)
        if isinstance(val, str) and len(val.strip()) > limit:
            new = _trim_at_break(val, limit)
            if new != val.strip():
                print(f"  ✂️ サムネ {key} を短縮: {len(val)}字 → {len(new)}字")
                thumb_info[key] = new


_TELOP_PACING_RULE_SHORT = """# テンポ・ルール(完視聴率対策・絶対厳守)
- ショートは**1行=1テロップ**。1行が長いほど画面が固まって離脱する。各行は3〜4秒で読み切れる長さに収める。
- 1行に接続詞を重ねて2つ以上の話を詰め込まない(「〜で、しかも〜だから〜」は不合格)。1行=1メッセージ。
- 行が進むごとに話の角度を変える(問い→驚き→数字→理由→意外な展開→オチ)。同じ調子の行を2つ続けない。
"""

# 2026-08-19 追加: ショートは自動ループ再生される。最終行から1行目へ意味が
# 繋がっていると視聴者が「もう一周」してしまい、再生回数と平均視聴時間が
# 1本あたり 1.3〜2 倍に伸びる（ループはアルゴリズム上「完視聴」として効く）。
# 逆に「ご視聴ありがとうございました」で閉じると、そこで確実に離脱する。
_LOOP_RULE_SHORT = """# ループ構成ルール(再視聴率対策・絶対厳守)
- ショートは**最後まで見ると自動で1行目に巻き戻る**。この一周を「もう一回見たい」に変えるのが目的。
  **ループ再生率100%超（2周以上視聴）はYouTubeアルゴリズムへの最強シグナル。**
- ✅ **最後の内容行(オチ)は1行目に意味がつながるように書く**。視聴者が1行目を聞き直したとき、
  「あ、そういう意味だったのか」と**意味が変わって聞こえる**状態を作る。
  - 伏線回収型: 1行目の問いの答えをオチで言い切る。答えを知ってから1行目を聞くと別の意味に聞こえるようにする。
  - 前提逆転型: オチで前提をひっくり返し、1行目が別の意味に読めるようにする。
  - 問い返し型: オチを「じゃあ〇〇は?」で閉じ、1行目の問いに戻る輪を作る。
- ✅ **1行目は「途中から聞いても成立する」書き方にする**。巻き戻ってきた視聴者が
  文脈なしでもう一周できるよう、冒頭で前の行を受ける指示語(「それは」「この」)を使わない。
- ❌ 最後の内容行を文の途中で止めない（「…だからこそ、」のような宙吊り）。最終行は登録CTAなので、
  宙吊りにしても1行目には繋がらず、内容行が尻切れに聞こえるだけになる。輪はオチの中身で作る。
- ❌ **終わった感の出る締めは禁止**: 「以上です」「ご視聴ありがとうございました」
  「まとめると」「いかがでしたか」は1文字でも入れたら不合格。そこで視聴者は確実に離れる。
- ❌ **ループを切るフレーズ禁止**: 「最後に」「結論は」「今日のまとめ」「というわけで」も
  NG。これらが出た瞬間に視聴者は「終わり」を察知してスワイプする。
- ※ 最終行の登録CTAは上の構成ルール通り必ず入れる。ただし**話を終わらせず**、
  オチの余韻に乗せたまま1行に収めること(CTAで話を締めくくらない)。
"""


# =====================================================================
# ショート品質バー（2026-10-03 追加）
#
# 比較対象として、同ジャンルで実際に伸びたショート8本を実測した
# （scratchpad/loop/bench。数値は 2026-10-03 時点）:
#   化け学のふしぎ「ネズミにモンスター磁石を近づけたらどうなる？」848万回
#   化け学のふしぎ「なぜか硬く結んでも100%解ける靴紐問題」215万回
#   ぽへチャンネル「マッシブーンは虫タイプの中で…」155万回
#   なぞはな「ザシアンは設定上、メスしかいない」52万回
#   サクトシ「正体が判明した日本の妖怪3選」248万回
#   はにわ「名古屋の熱田の海に奇妙な妖怪が」20万回 ほか
# 8本とも 0〜1秒の時点で「題材の名前」と「具体的な物・数字・場所」が出ていた。
# 一方こちらの台本は、pokemon-lab の 27本中16本が「このポケモンのモデル、
# 実は〇〇なんだよ！」で始まり、名前を伏せたうえに、種族値の話にまで
# 根拠のない「モデル」を付けていた（例: ガブリアス「モデル、実は4倍の弱点
# まで背負ってる」）。pokemon-lab は登録/千再生 0.06・高評価/千再生 2.53 と
# 4ch で最低（09-12〜09-29 公開分の実測）。ほかの3ch も、伏せた謎を最後まで
# 明かさない台本（scp-lab「47人が全員同じ言葉を残した」→ 言葉が出てこない）や、
# 同じ事実を言い換えるだけの行が残っていた。
# 以下はチャンネル固有の構成（short_format）に「重ねる」共通の下限。
# =====================================================================
_SHORT_QUALITY_BAR_RULE = """# ショート品質バー(実在の上位ショートに負けないための下限・チャンネル固有の構成より優先・絶対厳守)
- 比較対象: 「ネズミにモンスター磁石を近づけたらどうなる？」(848万回) / 「なぜか硬く結んでも100%解ける靴紐問題」(215万回) / 「マッシブーンは虫タイプの中で…」(155万回) / 「ザシアンは設定上、メスしかいない」(52万回) / 「もしあなたの周りで『カチカチ』という音が聞こえたら、もう助かりません」(19万回)。どれも0秒目から題材の名前と具体的な物・数字が出ていて、前置きが1文字もない。
1. **1行目の最初の語は題材の固有名か具体物**(ポケモン名・SCP番号・妖怪名・現象や物の名前)。フィードの視聴者にタイトルは見えていない。「このポケモン」「この妖怪」「このSCP」「これ」「ある〇〇」で名前を伏せない。「これ知ってた？」「知ってた？」「実は」のような前置きから始めない(上位8本は1本も使っていない。前置きで0.5〜1秒を失う)。
   - ✕「これ知ってた？百目は…」→ ○「百々目鬼は、盗みを重ねた女の腕に無数の目が生えた妖怪だ」
2. **1行目は次の3つの型のどれかで書く**(数字・場所・物の名前・具体的な行為のどれかを必ず含める):
   (a) 結果が予想できない問い: 「〇〇を△△したらどうなる？」「なぜ〇〇だけ△△なのか」。画面に出せる物と、具体的な条件を入れる。
   (b) 視聴者を当事者にする言い切り: 「〇〇が聞こえたら、もう助からない」「あなたの〇〇、実は△△している」。
   (c) 1文目がもう意外な事実: 「ザシアンは設定上、メスしかいない」のように、題材名＋覆る事実を言い切る。
   - ❌ 定義の読み上げ(「SCP-252は、〇〇するテレビだ」)、抽象語だけ(「正体」「真相」「秘密」)、予防線(「〜ことがある」「〜かも」)は1行目に入れない。
   - ❌ 1行目に学術用語・内部用語を入れない。視聴者が普段使う言葉で言う(✕「緊張時の手掌発汗」→ ○「緊張すると手のひらだけ汗をかく」)。
3. **1本に別々の具体的事実を4つ以上入れる**。下の『行の役割』で事実を運ぶ行(1行目と、解説役・語りの行)に、それぞれ**違う**事実(数字・固有名詞・出典・目に見える出来事)を1つずつ置く。どの行がどの事実かを各行の "fact" に F番号で書く(同じF番号を2行で使わない)。上位ショートは21秒で4個(ザシアン)、56秒で6個(マッシブーン)。
   - ❌ 同じ事実を言い方だけ変えた行、たとえ話だけの行、雰囲気だけの行(「記録はそこで途切れている」「見方が変わるはず」)は1本に0行。たとえを使うなら、新しい事実の行の後ろに10字程度で添える。
4. **張った謎は台本の中で中身ごと回収する**。「同じ言葉」「ある物質」「消えた理由」のように伏せたら、オチの行までにその中身(実際の言葉・物質名・理由)を言う。
5. **言い切る。自分のフックを自分で打ち消さない**。「〜ことがある」「〜とも読める」「〜かもしれない」「定かでない」「諸説ある」「ただし〜でも変わる」で主張を弱めるのは不合格。確証のない主張は**ぼかして残さず、丸ごと削り、確証のある別の事実に差し替える**。伝承・設定・報告書の中身は、出典を主語にして言い切る(「『今昔画図続百鬼』には〜と書かれている」「報告書には〜とある」「図鑑には〜とある」)。
   - ❌ 動画の答えを否定形にしない(「専用の反射ではなく〜」「原典では空白」「勝敗固定なし」)。答えは「〜だ」「〜が原因だ」で言える事実にする。否定形は、肯定の答えを言った後の前フリにだけ使う。
   - ❌ 検証の過程を台本で語らない。「〜は原典にない」「本文には書かれていない」「確認できない」「答えは一意じゃない」「条件次第」のように、テーマや俗説を否定する行・答えを出さない行は不合格。言えないことは言わずに、言える事実だけで話を組む。
6. **事実は確認できるものだけ**。種族値・タイプ・技の効果・特性・図鑑の記述・SCP番号・オブジェクトクラス・文献名と刊行年・地名は公式/原典どおりに書く。下の『使ってよい事実』がある場合は、そこにある事実だけを使う。型に合わせるためにテーマに無い主張(例: 種族値の話に「モデルは〇〇」を足す)を作らない。
   - 「勝つ」「最強」「唯一」「全員」「必ず」の断定は、反証になる条件(タイプ相性・特性・定番の対策技・例外の記録)を確かめて成り立つものだけ。条件付きでしか成り立たないなら条件ごと言う。詳しい視聴者ほど誤りに気付き、高評価も登録もしない。
7. **最後の内容行(オチ・CTAの直前)は次のどれかで終える**: 冒頭の問い・音・物に戻る二人称の問い(「あなたの後ろの音、今止まりませんでしたか」) / 前提をひっくり返す最後の事実 / 視聴者がコメントで答えたくなる一言(「あなたはどっちだと思う？」)。但し書き・余韻だけ・教訓で終えない。
8. **各行は文として言い切る**。「〜なり。」「〜やすく。」「〜して。」のような途中で切れた形で終えない。
"""


# ショート専用プロンプトで、長尺向けの「序盤25%ルール」「第二フック(full 20%地点)」
# 「専門用語ルール」の代わりに入れる短い版。中身はそれぞれのショート該当部分だけ。
_SHORT_ONLY_DIALOGUE_RULES = """# 掛け合いルール(ショート・絶対厳守)
- 聞き役の行は次の3つのどれかだけ: ①驚く ②ツッコむ ③視聴者がいま抱く疑問を代わりに言う。**8〜18字**で、問い返しの形にする。
- **聞き役が口にしてよい具体語(数字・固有名詞・物の名前)は、それより前の行で解説役がもう言ったものだけ**。新しい数字・年号・書名・仕組みの名前を聞き役が先に言うのは不合格(機械で検査して差し戻す)。
  - ✕(1行目で「SCP-1025」「百科事典」しか出ていないのに)「百科事典を読んだだけで、病気の症状が出るのか？」← 答えを先に言っている
  - ✕(書名が出る前に)「え、1910年の本にあるの？」　✕「涙は涙点から涙小管、涙嚢を通るんだね？」← 解説の中身を聞き役が言っている
  - ○「えっ、読むだけで!?」「ネズミが逃げるの!?」「じゃあ毒タイプには効かないの？」
- ツッコミの語(「いや」「〜でしょ！」「〜じゃん」「!?」)は聞き役の行にだけ置く。解説役の行には入れない。
- ❌ ジャンル外の連想やたとえ(「教室の窓100枚みたい」)、キャラが好き・可愛いの感想は不合格。
- 解説役の行は**1行に事実1つ・34字以内**。事実が2つなら1つを捨てる(次の行に回さない)。
- 専門用語(ゲーム内部用語・学術名・分類名)は出すなら1本に1回だけ、その行の中で10字以内の言い換えを添える(例:「Keter(収容がほぼ不可能)」)。『鼻腔流入』のような教科書の言葉は普段の言葉にする(『涙が鼻に流れ込む』)。
- その動画でいちばん『えっ』となる事実は3行目までに出す。終盤に温存しない。
- moodはショート全体で2〜3シーン(フック="tense"or"bright"、展開="calm"or"mysterious"、オチ="bright"or"emotional")。
- 最終行(高評価+登録)の expression は "normal" か "happy"。sad / angry / surprise で頼むと、言葉と顔が食い違う。

"""

# モノローグ（ナレーター1人）版。掛け合いの聞き役ルールの代わりに、語りの行のルールを置く。
_SHORT_ONLY_NARRATION_RULES = """# 語りのルール(ショート・絶対厳守)
- 総括・言い換えだけの行は禁止。各行に新情報(数字・固有名詞・目に見える出来事)を入れる。
- 1行で扱う事実は1つ。1行に2つ以上の話を詰め込まない(事実が2つなら行を分ける)。
- 専門用語(学術名・分類名)は出すなら1本に1回だけ、その行の中で10字以内の言い換えを添える。
- その動画でいちばん『えっ』となる事実は3行目までに出す。終盤に温存しない。
- moodはショート全体で2〜3シーン(フック="tense"or"mysterious"、展開="calm"or"mysterious"、オチ="tense"or"emotional")。

"""


# 主張を自分で弱める言い回し（予防線）。第1周の生成で self-review が「確認できない」ものを
# 削らずにぼかした結果、「〜ことがある」「〜とも読める」「元伝承は定かでない」「ただし〜でも
# 変わる」の行が残り、フックを自分で打ち消していた（daily-science・yokai-watch）。
# 比較対象の上位ショート8本の文字起こしには、この型の文は1つも無い。
_HEDGE_RE = re.compile(
    r"(ことがある|こともある|とも読める|とも言える|かもしれ|定かでない|定かではない|"
    r"諸説ある|諸説あり|はっきりしない|分かっていない|わかっていない|確認できない|"
    r"^ただし|。ただし|場合もある|とされることも|一意じゃない|一意ではない|一概に|場合による|条件次第|"
    r"記していない|記載はない|記載がない|本文にない|原典にない|書かれていない|固定なし|決まらない|"
    r"確認されない|確認されていない|不明だった|不明なまま|詳しいことは不明)"
)


# LLM の1行出力に混じるゴミ（第2周の生成で実測: 冒頭フック修復が「…水中グリップ】【。」、
# タイトルに「ステロの盲点ાન્યの真相」（グジャラート文字）を返した）。
_FOREIGN_SCRIPT_RE = re.compile(r"[\u0590-\u08FF\u0900-\u0DFF\u0E00-\u0FFF\u1000-\u109F\uAC00-\uD7AF]")
_STRAY_BRACKETS_RE = re.compile(r"(?:】\s*【|【\s*】|「\s*」|『\s*』|[【】]+(?=[。！？!?]?$))")


def _clean_llm_line(text: str) -> str:
    """LLM が返した台本1行から、別言語の文字と中身のない括弧を取り除く。"""
    t = _FOREIGN_SCRIPT_RE.sub("", str(text or ""))
    t = _STRAY_BRACKETS_RE.sub("", t)
    t = re.sub(r"[、，]\s*。", "。", t)
    return t.strip()


def _find_hedges(texts: List[str]) -> List[str]:
    """予防線の言い回しを含む行を「L番号:該当句」で返す。"""
    out: List[str] = []
    for i, t in enumerate(texts):
        m = _HEDGE_RE.search(str(t or ""))
        if m:
            out.append(f"L{i + 1}:{m.group(0).lstrip('。')}")
    return out


def _fact_sheet_text(sheet: Optional[Dict[str, Any]]) -> str:
    """ファクトシートをプロンプト用の箇条書きにする（無ければ空文字）。"""
    if not isinstance(sheet, dict):
        return ""
    facts = [f for f in (sheet.get("facts") or []) if isinstance(f, dict) and f.get("fact")]
    if not facts:
        return ""
    lines = []
    if sheet.get("subject"):
        lines.append(f"- 題材の正式名: {sheet['subject']}")
    if sheet.get("core_answer"):
        lines.append(f"- テーマの答え(3行目までに言い切る): {sheet['core_answer']}")
    if sheet.get("grounded"):
        lines.append(f"- 原典: {sheet.get('source_url', '')}（下の確かな事実は、原典本文に同じ文言があることを機械で照合済み）")
    sure = _sure_facts(sheet)
    unsure = [f for f in facts if f.get("sure") is not True]
    for i, f in enumerate(sure):
        src = f" [出典: {f['source']}]" if f.get("source") else ""
        lines.append(f"- F{i + 1} 確かな事実: {f['fact']}{src}")
    for f in unsure:
        lines.append(f"- 確証なし(台本に入れない・その数字も使わない): {f['fact']}")
    if sheet.get("hook"):
        lines.append(f"- 1行目の案(原則これを語り口に合わせて使う。学術用語は普段の言葉に言い換える): {sheet['hook']}")
    if sheet.get("punchline"):
        lines.append(f"- オチの案(原則これを最後の内容行に使う): {sheet['punchline']}")
    for p in (sheet.get("pitfalls") or [])[:5]:
        lines.append(f"- 取り違えに注意: {p}")
    return "\n".join(lines)


# ファクトシートの hook / punchline の書き方（ファクトシート作成と原典照合の両方で使う）。
# 第2周の1行目は「泣いた涙は鼻の奥へ流れる？4つの涙点がカギです。」（問いと答えを同時に言い、
# 誰も気にしない数字を餌にした）、「ジガルデはHP半分で完全体になるって本当？」（自分の
# フックを疑う形）、「SCP-1025を読んだらどうなる？医療百科事典の外見だ。」（番号では物が
# 浮かばず、後半が尻すぼみ）で、比較対象 01「ネズミにモンスター磁石を近づけたらどうなる？」・
# 03「もしあなたの周りで『カチカチ』という音が聞こえたら、もう助かりません」に負けた。
_HOOK_SPEC = (
    "- hook には1行目の案を1つ書く(30字以内)。次のどれか:"
    "(a) 画面に出せる物と具体的な条件で、結果が予想できない問い『ネズミにモンスター磁石を近づけたらどうなる？』"
    "(b) 視聴者を当事者にする言い切り『この百科事典で「肺がん」のページを読むと、あなたは咳が止まらなくなる』"
    "(c) 1文目がもう意外な事実『ザシアンは設定上、メスしかいない』。"
    "題材は番号や名前だけで終わらせず、物として浮かぶ言葉を添える(✕『SCP-1025を読んだら』→○『SCP-1025という病気の百科事典を読むと』)。"
    "❌ 問いの後ろに答えや説明を続けない(✕『涙は鼻へ流れる？4つの涙点がカギです』)。"
    "❌ 『〜って本当？』『〜なの？』のように自分の主張を疑う形にしない。"
    "❌ 驚きの中心でない数字(涙点の数・ページ数)を餌にしない。数字を使うなら驚きの中心になっている数字だけ。"
    "❌ 学術用語(『鼻腔流入』『反磁性』)は1行目に入れない。\n"
    "- punchline には、最後に置くと冒頭の意味が変わる確かな事実か、冒頭へ戻る二人称の問いを1つ書く"
    "(『あなたの後ろの音、今止まりませんでしたか』)。\n"
)


def _sure_facts(sheet: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ファクトシートの確かな事実（sure=True）。並び順が F1, F2, … の番号になる。"""
    if not isinstance(sheet, dict):
        return []
    return [f for f in (sheet.get("facts") or [])
            if isinstance(f, dict) and f.get("fact") and f.get("sure") is True]


# =====================================================================
# 原典照合（2026-10-03 第3周）
#
# 第2周までの sure は GPT の自己申告で、自信満々の誤りを止められなかった
# （第2周サンプルで実測）:
#   - scp-lab「本には300種類以上の病気」「閲覧はレベル3許可制」
#       → SCP-1025 の日本語版本文は「約1500ページ」「更なる研究にはO5の承認」。どちらも本文に無い。
#   - yokai-watch「遠野物語第59話に送り狼と『休ませて下さい』」
#       → ja.wikipedia「送り犬」（送り狼はここへ転送）に遠野物語の記述は無い。
#         本文にあるのは「転んでも『どっこいしょ』と座ったように見せかけ…休憩をとる振り」。
#   - pokemon-lab「セル100個で完全体を組み立てる」
#       → ポケモンWikiのジガルデの記事では、パーフェクトフォルムは特性スワームチェンジで
#         HPが半分以下になったときに戦闘中だけ変わる姿。
# そこで、題材の原典テキスト（SCP財団Wiki本文・ポケモンWikiの記事・Wikipedia）を取得し、
# 「原典の本文に同じ文言がある」ことを機械で確かめた事実だけを sure にする。
# 取得できないとき（オフライン・記事なし）は従来どおり GPT の申告で続ける（止めない）。
# =====================================================================
_SOURCE_UA = "Mozilla/5.0 (Macintosh; youtube-factory fact-check)"
_SOURCE_MAX_CHARS = 9000


def _http_get_text(url: str, timeout: float = 12.0) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _SOURCE_UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if getattr(r, "status", 200) != 200:
                return ""
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _html_to_text(html: str) -> str:
    import html as _html
    m = re.search(r'<div id="page-content">(.*?)<div class="page-tags"', html, re.S)
    body = m.group(1) if m else html
    body = re.sub(r"<(script|style)\b.*?</\1>", "", body, flags=re.S)
    # 取り消し線の部分（「Keter Safe」の Keter など、訂正前の値）は事実として拾わない
    body = re.sub(r'<span style="text-decoration:\s*line-through;?">.*?</span>', "", body, flags=re.S)
    body = re.sub(r"<(del|s|strike)\b[^>]*>.*?</\1>", "", body, flags=re.S)
    body = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", body)
    body = re.sub(r"<[^>]+>", "", body)
    body = _html.unescape(body)
    return re.sub(r"\n\s*\n+", "\n", body).strip()


def _wikitext_to_text(wt: str) -> str:
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", wt, flags=re.S)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    return t


def _source_kind(channel) -> Optional[str]:
    """原典照合に使う資料の種類。対応していないジャンルは None（照合しない）。"""
    cid = (getattr(channel, "id", "") or "").lower()
    concept = f"{getattr(channel, 'name', '')} {getattr(channel, 'concept', '')}"
    if "scp" in cid or "SCP" in concept:
        return "scp"
    if "pokemon" in cid or "ポケモン" in concept:
        return "pokemon"
    if "yokai" in cid or "妖怪" in concept or "伝承" in concept:
        return "wikipedia"
    if "science" in cid or "科学" in concept:
        return "wikipedia"
    return None


def _scp_numbers(*texts: str) -> List[str]:
    out: List[str] = []
    for t in texts:
        for m in re.finditer(r"SCP[-‐－ー]?(\d{3,4})(-JP|－JP)?", _nfkc(t or ""), re.I):
            key = f"scp-{m.group(1)}" + ("-jp" if m.group(2) else "")
            if key not in out:
                out.append(key)
    return out


def _fetch_source(kind: str, candidates: List[str]) -> Tuple[str, str]:
    """(本文テキスト, URL) を返す。取れなければ ("", "")。"""
    import urllib.parse as _up
    for cand in candidates:
        cand = (cand or "").strip()
        if not cand:
            continue
        if kind == "scp":
            for host in ("scp-jp.wikidot.com", "scp-wiki.wikidot.com"):
                url = f"https://{host}/{cand}"
                txt = _html_to_text(_http_get_text(url))
                if len(txt) > 400 and cand.split("-")[1] in txt:
                    return txt, url
        elif kind == "pokemon":
            url = ("https://wiki.xn--rckteqa2e.com/w/index.php?title="
                   f"{_up.quote(cand)}&action=raw")
            wt = _http_get_text(url)
            if "ポケモン図鑑基本情報" in wt or "ポケモン図鑑前後" in wt:
                return _wikitext_to_text(wt), f"https://wiki.xn--rckteqa2e.com/wiki/{_up.quote(cand)}"
        elif kind == "wikipedia":
            url = ("https://ja.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1"
                   f"&redirects=1&format=json&titles={_up.quote(cand)}")
            raw = _http_get_text(url)
            try:
                pages = (json.loads(raw).get("query") or {}).get("pages") or {}
            except Exception:
                pages = {}
            for pid, pg in pages.items():
                ext = (pg or {}).get("extract") or ""
                if pid != "-1" and len(ext) > 300:
                    title = pg.get("title") or cand
                    return ext, f"https://ja.wikipedia.org/wiki/{_up.quote(title)}"
    return "", ""


def _wikipedia_search(query: str, limit: int = 3) -> List[str]:
    """日本語版 Wikipedia の全文検索で記事名を返す（失敗時は空）。"""
    import urllib.parse as _up
    q = re.sub(r"[？?！!「」『』（）()、。]", " ", query or "").strip()
    if not q:
        return []
    raw = _http_get_text("https://ja.wikipedia.org/w/api.php?action=query&list=search&format=json"
                         f"&srlimit={limit}&srsearch={_up.quote(q)}")
    try:
        return [h["title"] for h in (json.loads(raw).get("query") or {}).get("search") or [] if h.get("title")]
    except Exception:
        return []


def _relevant_excerpt(text: str, keywords: List[str], limit: int = _SOURCE_MAX_CHARS) -> str:
    """長い原典から、冒頭と、テーマの語を多く含む段落を limit 字まで抜き出す（原文の順で）。"""
    if len(text) <= limit:
        return text
    paras = [p for p in re.split(r"\n+", text) if p.strip()]
    head_budget = limit // 4
    chosen, used = set(), 0
    for i, p in enumerate(paras):
        if used + len(p) > head_budget:
            break
        chosen.add(i)
        used += len(p)
    kws = [k for k in keywords if k and len(k) >= 2]
    scored = sorted(
        ((sum(p.count(k) for k in kws), i) for i, p in enumerate(paras) if i not in chosen),
        reverse=True,
    )
    for score, i in scored:
        if score <= 0 or used >= limit:
            break
        if used + len(paras[i]) > limit:
            continue
        chosen.add(i)
        used += len(paras[i])
    return "\n".join(paras[i] for i in sorted(chosen))


def _nfkc(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", str(s or ""))


def _squash(s: str) -> str:
    """照合用: NFKC・空白と記号の揺れを落とす。"""
    t = _nfkc(s)
    t = re.sub(r"[\s「」『』\"'“”‘’()（）\[\]【】・、,。.:：;；!！?？~〜ー\-–—|*=]", "", t)
    return t.lower()


def _numbers_in(s: str) -> List[str]:
    """文中の数字（算用数字）。「1」「2」のような1桁は、助数詞付きのときだけ数える。"""
    t = _nfkc(s)
    out = []
    for m in re.finditer(r"\d+(?:\.\d+)?", t):
        n = m.group(0)
        if n not in out:
            out.append(n)
    return out


# 台本の具体語（照合・重複判定用）: 漢字2字以上・カタカナ3字以上・英字2字以上・数字
_TOKEN_RE = re.compile(r"[一-鿿々〆]{2,}|[ァ-ヺー]{3,}|[A-Za-z]{2,}|\d+(?:\.\d+)?")
# 聞き役が新しく言っても「答え」にならない語
_LISTENER_FREE_WORDS = {
    "本当", "全部", "全員", "自分", "普通", "一体", "意味", "絶対", "結局", "最強", "大丈夫",
    "一番", "一瞬", "最後", "最初", "秘密", "正体", "理由", "本気", "無理", "危険", "安全",
    "簡単", "説明", "質問", "待って", "マジ", "ヤバ", "ヤバい", "今日", "何回", "何度", "僕達",
    "冗談", "怖い", "可哀想", "納得", "反則", "強すぎ", "最悪", "最高", "不思議",
}


def _tokens(s: str) -> List[str]:
    out = []
    for m in _TOKEN_RE.finditer(_nfkc(s)):
        tok = m.group(0)
        if tok not in out:
            out.append(tok)
    return out


def _seen(tok: str, prior: str) -> bool:
    """tok が先行テキストに出ているか（部分一致・NFKC）。漢字語は2字の部分一致まで許す。"""
    p = _nfkc(prior)
    if re.fullmatch(r"\d+(?:\.\d+)?", tok):
        return tok in _numbers_in(p)
    if tok in p:
        return True
    if re.fullmatch(r"[一-鿿々〆]{3,}", tok):
        return any(tok[i:i + 2] in p for i in range(len(tok) - 1))
    return False


def _verify_quote(quote: str, source_sq: str) -> bool:
    q = _squash(quote)
    if len(q) < 6:
        return False
    if q in source_sq:
        return True
    # 引用が長いと GPT が途中の1〜2字を変えることがある。前半・後半（各12字以上）が
    # どちらも原文にあり、しかも原文の中で近く（120字以内）に並んでいれば可。
    if len(q) >= 24:
        half = len(q) // 2
        a, b = source_sq.find(q[:half]), source_sq.find(q[half:])
        return a >= 0 and b >= 0 and 0 <= b - a <= half + 120
    return False


# =====================================================================
# ショート台本の機械検査（2026-10-03 第3周）
#
# 第2周はルールをプロンプトに書くだけで、4本すべてに違反が残った（批評で指摘・実物で確認）:
#   - 同じ事実の言い直し: pokemon-lab の1・2・4行目がすべて「HP半分」
#   - 聞き役が先に答えを言う: scp-lab 2行目「百科事典を読んだだけで、病気の症状が出るのか？」
#   - 1行目が自分のフックを疑う: 「ジガルデはHP半分で完全体になるって本当？」
#     （Phase V2 の冒頭フック修復が「〜んだよ！」をこの形に書き換えていた）
#   - 48字の行、解説役の「いや強すぎでしょ！」、解説役の3連続
#   - オチが説明文: scp-lab「読者は感染せず、病気の症状だけを発現する。」
# 生成後にこれらを機械で検査し、違反を具体的に書いて GPT に差し戻す（_short_lint_repair）。
# =====================================================================
_TSUKKOMI_RE = re.compile(r"(?:^|[、。！!？?\s])いや[、!！\s]|でしょ[！!]|じゃん[！!。]?$|[!！][?？]|[?？][!！]|マジで?[？?]|(?:^|[、。！!\s])えっ?[、!！]")
_SECOND_PERSON_RE = re.compile(r"(あなた|君|きみ|キミ|お前|おまえ|みんな)")
_QUOTED_RE = re.compile(r"『[^』]*』|「[^」]*」")
_DANGLING_RE = re.compile(r"(?:なり|やすく|にくく|ており|ながら|つつ|ことが|ことも)[。．]")
# 重い違反（直らなければ比較対象に確実に負ける型）は 3点、それ以外は 1点
_LINT_WEIGHT = {
    "listener_preempt": 3, "dup": 3, "unverified_number": 3, "hook_doubt": 3,
    "hook_answer": 3, "hook_subject": 3, "hook_type": 3, "punch": 3, "speaker": 3, "line_count": 3,
    "drift": 3, "cta": 3, "tsukkomi": 2, "run": 2, "len": 2, "total": 2, "len_short": 2, "total_short": 2,
}


# 1字の漢字の重なりで言い直しを見るとき、どの文にも出る字は数えない
_KANJI_STOP = set("出見言思行来上下中大小人時日一二三今何前後気知方事物所者生的性化手")


def _kanji_bag(text: str, subject: str = "") -> set:
    """1字の漢字の集合（題材名の字と、どの文にも出る字を除く）。「血」「汗」「涙」のような
    1字の名詞は _tokens（漢字2字以上）では拾えないので、言い直しの判定に足す。"""
    sub = set(re.findall(r"[\u4e00-\u9fff]", subject or ""))
    return {c for c in re.findall(r"[\u4e00-\u9fff]", _QUOTED_RE.sub("", text))
            if c not in sub and c not in _KANJI_STOP}


_CTA_BENEFIT_RE = re.compile(r"(届|続き|次の|次も|毎日|シリーズ|ファイル|見られ|読める)")


def _cta_problem(text: str) -> str:
    """CTA 行の問題（無ければ空文字）。登録の理由（何が届くか）が無い CTA は登録に効かない。"""
    t = str(text or "")
    try:
        from pipeline import cta_enforcer as _ce
        if not (_ce.has_like(t) and _ce.has_subscribe(t)):
            return "CTAに『高評価』と『登録』の両方を入れる"
    except Exception:
        pass
    if not _CTA_BENEFIT_RE.search(t):
        return "CTAに、登録すると何が届くか（このチャンネルの題材で）を入れる（例『登録で次のファイルも届く』）"
    if len(t) > 36:
        return f"CTAが{len(t)}字。36字以内にする"
    return ""


def _lint_score(viol: List[Dict[str, Any]]) -> int:
    return sum(_LINT_WEIGHT.get(v.get("code"), 1) for v in viol)


def _lint_short(lines: List[Dict[str, Any]], *, explainer: str, listener: str, dialogue: bool,
                sheet: Optional[Dict[str, Any]], theme: Dict, chars_max: int = 0,
                check_subject: bool = True, chars_min: int = 0) -> List[Dict[str, Any]]:
    """ショート台本（最終行=CTA）を検査し、違反を [{"line","code","msg"}] で返す。"""
    viol: List[Dict[str, Any]] = []

    def add(i: Optional[int], code: str, msg: str) -> None:
        viol.append({"line": (i + 1) if i is not None else None, "code": code,
                     "msg": (f"L{i + 1}: {msg}" if i is not None else msg)})

    texts = [str((e or {}).get("text") or "") for e in lines]
    speakers = [str((e or {}).get("speaker") or "") for e in lines]
    if len(texts) < 3:
        return [{"line": None, "code": "line_count", "msg": f"行数が{len(texts)}行しかない"}]
    body = texts[:-1]
    sheet = sheet if isinstance(sheet, dict) else {}
    subject = re.sub(r"[（(][^）)]*[）)]", "", str(sheet.get("subject") or "")).strip()
    sub_toks = set(_tokens(subject)) | set(_numbers_in(subject))
    sure = _sure_facts(sheet)
    sure_facts_txt = " ".join(str(f.get("fact") or "") for f in sure)
    sure_all_txt = sure_facts_txt + " " + " ".join(str(f.get("quote") or "") for f in sure)
    sure_nums = set(_numbers_in(sure_all_txt))
    ttl = str(theme.get("title") or "")
    is_listener = [dialogue and speakers[i] == listener for i in range(len(body))]

    # 構成（掛け合い: 解説・聞き・解説・解説・聞き・解説 ＋ CTA）
    if dialogue:
        if len(body) != len(SHORT_DIALOGUE_SPEAKERS):
            add(None, "line_count", f"本文は6行（解説役・聞き役・解説役・解説役・聞き役・解説役）＋CTAの7行にする（今は{len(texts)}行）")
        else:
            for i, role in enumerate(SHORT_DIALOGUE_SPEAKERS):
                want = explainer if role == 0 else listener
                if speakers[i] != want:
                    add(i, "speaker", f"この行の話者は{want}（{'解説役' if role == 0 else '聞き役'}）にする")
        run = 1
        for i in range(1, len(body)):
            run = run + 1 if speakers[i] == speakers[i - 1] else 1
            if run == 3:
                add(i, "run", "同じ話者が3行続いている。間に聞き役の短い一言（8〜18字）を入れる")

    # 長さ
    for i, t in enumerate(body):
        if is_listener[i]:
            if len(t) > 20:
                add(i, "len", f"聞き役の行が{len(t)}字。18字以内の驚き・問い返しにする")
        elif len(t) > 36:
            add(i, "len", f"{len(t)}字ある。34字以内にし、事実が2つ入っていれば1つを捨てる")
        elif len(t) < (15 if i == 0 else 22):
            add(i, "len_short", f"{len(t)}字しかない。確かな事実の具体（数字・名前・目に見える出来事）を入れて26〜34字にする")
    total = sum(len(t) for t in texts)
    if chars_max and total > chars_max:
        add(None, "total", f"総字数{total}字が上限{chars_max}字を超えている。解説役の行を短くする")
    elif chars_min and total < chars_min - 10:
        add(None, "total_short", f"総字数{total}字が下限{chars_min}字に足りない。解説役の行を24〜34字にして、確かな事実の具体を足す")

    # 聞き役が先に事実を言う
    for i, t in enumerate(body):
        if not is_listener[i]:
            continue
        prior = "".join(texts[:i])
        new_nums = [n for n in _numbers_in(t) if n not in _nfkc(prior)]
        new_words = [w for w in _tokens(t) if not re.fullmatch(r"\d+(?:\.\d+)?", w)
                     and w not in _LISTENER_FREE_WORDS and not _seen(w, prior)]
        if new_nums or len(new_words) >= 2:
            add(i, "listener_preempt",
                f"聞き役が、解説役より先に新しい事実（{'・'.join(new_nums + new_words)}）を言っている。"
                "前の行に出た語だけで驚く・問い返す形にする")

    # ツッコミが解説役の行にある
    if dialogue:
        for i, t in enumerate(body):
            if speakers[i] == explainer and _TSUKKOMI_RE.search(t):
                add(i, "tsukkomi", "ツッコミの言い回し（いや／〜でしょ！／!?）が解説役の行にある。解説役の行は事実だけにし、ツッコミは聞き役の行へ")

    # 同じ事実の言い直し（事実を運ぶ行どうし）
    fact_idx = [i for i in range(len(body)) if not is_listener[i]]

    def ftoks(t: str) -> List[str]:
        return [w for w in _tokens(t) if w not in sub_toks and w not in _LISTENER_FREE_WORDS
                and not any(w in s or s in w for s in sub_toks if len(s) >= 2)]

    for x in range(len(fact_idx)):
        for y in range(x + 1, len(fact_idx)):
            a, b = fact_idx[x], fact_idx[y]
            ta, tb = ftoks(texts[a]), ftoks(texts[b])
            shared = [w for w in ta if _seen(w, texts[b])] if (ta and tb) else []
            ka, kb = _kanji_bag(texts[a], subject), _kanji_bag(texts[b], subject)
            kshared = ka & kb
            if a == 0 and b == fact_idx[-1]:
                # オチは冒頭へ戻る問いで終えるので、問いの部分は除き、事実の文だけで比べる。
                # 事実の文の漢字がすべて1行目にあれば言い直し（「血も出ないとされる」）。
                stmt = re.sub(r"[^。！!]*[？?][」』]?\s*$", "", texts[b])
                kb2 = _kanji_bag(stmt, subject)
                if kb2 and kb2 <= ka:
                    add(b, "dup", f"L1と同じ事実（{'・'.join(sorted(kb2))}）の言い直し。オチの前半には新しい事実を置く")
                continue
            if shared and len(shared) >= 2 and len(shared) >= 0.5 * min(len(ta), len(tb)):
                add(b, "dup", f"L{a + 1}と同じ事実（{'・'.join(shared)}）の言い直し。ファクトシートのまだ使っていない事実に替える")
            elif not (a == 0 and b == fact_idx[1] and re.search(r"[？?]", texts[0])) \
                    and min(len(ka), len(kb)) >= 2 and len(kshared) >= 2 \
                    and len(kshared) >= 0.6 * min(len(ka), len(kb)):
                add(b, "dup", f"L{a + 1}と同じ事実（{'・'.join(sorted(kshared))}）の言い直し。ファクトシートのまだ使っていない事実に替える")
    ids = {}
    for i in fact_idx:
        fid = str((lines[i] or {}).get("fact") or "").strip().upper()
        if re.fullmatch(r"F\d+", fid):
            if fid in ids:
                add(i, "dup", f"L{ids[fid] + 1}と同じ事実（{fid}）を使っている。まだ使っていないF番号の事実に替える")
            else:
                ids[fid] = i

    # 確かな事実に無い数字
    if sure:
        for i, t in enumerate(body):
            bad = [n for n in _numbers_in(t) if n not in sure_nums and n not in sub_toks]
            if bad:
                add(i, "unverified_number", f"数字（{'・'.join(bad)}）がファクトシートの確かな事実に無い。消すか、確かな事実の数字に替える")

    # 1行目
    t0 = texts[0]
    if re.search(r"本当[？?]|本当なの|ほんと[？?]|マジ[!?！？]|マジで[!?！？]|知って(?:た|る)[？?]|だった[？?]", t0):
        add(0, "hook_doubt", "『本当？』『〜だった？』『知ってた？』で自分のフックを疑っている。言い切るか、結果が予想できない問い（〜したらどうなる？）にする")
    if not (re.search(r"[？?]", t0) or _SECOND_PERSON_RE.search(t0) or re.search(r"\d", _nfkc(t0))
            or re.search(r"(しか|だけ|唯一|一度も|全員|誰も|絶対|必ず|たら|すると|ると、|れば)", t0)):
        add(0, "hook_type", "1行目が説明文になっている。結果が予想できない問い（〜したらどうなる？）、"
            "あなたを当事者にする言い切り、限定・数字で覆す事実（〜しかいない）のどれかにする")
    m = re.search(r"[？?]", t0)
    if m and not re.search(r"なぜ|なんで|どうな|どう|何|誰|どこ|どれ|どっち|いつ|いくつ|(?:たら|れば|ると)[？?]", t0[:m.end()]):
        add(0, "hook_doubt", "言い切りの事実に『？』を付けただけの問いになっている。言い切るか、"
            "『〜したらどうなる？』『なぜ〜なのか』のように答えが予想できない問いにする")
    if m and len(re.sub(r"[\s。！!…、]", "", t0[m.end():])) >= 6:
        add(0, "hook_answer", "問いの後ろに答え・説明を続けている。問いで止める（後ろの内容は3行目へ）")
    if subject and check_subject:
        keys = [k for k in (_scp_numbers(subject) or [])] or [w for w in _tokens(subject) if len(w) >= 2]
        keys = [k.upper().replace("SCP-", "") if k.startswith("scp-") else k for k in keys]
        # テーマを差し替えたときは subject が古いことがあるので、今の題名の固有名（カタカナ・SCP番号）も認める
        keys += [k.upper().replace("SCP-", "") for k in _scp_numbers(ttl)]
        keys += re.findall(r"[\u30a1-\u30faー]{3,}", _nfkc(ttl))
        if keys and not any(k in _nfkc(t0) for k in keys):
            add(0, "hook_subject", f"1行目に題材名（{subject}）が無い")

    # オチ（最後の内容行）
    punch = body[-1].strip()
    if not (re.search(r"[？?][」』）)]?[。！!…]*$", punch) or _SECOND_PERSON_RE.search(punch)):
        add(len(body) - 1, "punch", "オチが説明文で終わっている。冒頭へ戻る二人称の問い（『あなたの〜、今〜していませんか』）か、"
            "コメントで答えたくなる問いで終える")

    # CTA（最終行）: 高評価・登録・登録で何が届くか、36字以内
    cta_bad = _cta_problem(texts[-1])
    if cta_bad:
        add(len(texts) - 1, "cta", cta_bad)

    # 予防線・途中で切れた文
    for i, t in enumerate(body):
        h = _HEDGE_RE.search(t) or re.search(r"(考えです|と考えられ|説があ|説もあ|と指摘され|やすいという)", t)
        if h:
            add(i, "hedge", f"予防線（{h.group(0).lstrip('。')}）で主張を弱めている。確かな事実で言い切る")
        if _DANGLING_RE.search(t.strip()):
            add(i, "dangling", "文が途中で切れている（〜なり。など）。言い切りにする")

    # テーマ差し替え前の語の残り
    gate = theme.get("assert_gate") or {}
    old = f"{gate.get('reframed_title_from') or ''} {gate.get('reframed_angle_from') or ''}".strip()
    if old:
        new_ctx = f"{ttl} {theme.get('angle') or ''} {sure_all_txt}"
        drift = [w for w in _tokens(old) if not re.fullmatch(r"\d+(?:\.\d+)?", w) and len(w) >= 3
                 and w not in sub_toks and not _seen(w, new_ctx)]
        for i, t in enumerate(body):
            hit = [w for w in drift if w in _nfkc(t)]
            if hit:
                add(i, "drift", f"差し替え前のテーマの語（{'・'.join(hit)}）が残っている。今のテーマ『{ttl}』の事実だけにする")

    # 学術語（漢字4字以上で、題名・題材名・確かな事実の文に無いもの）
    # 固有名の多いジャンル（SCP・ポケモン・妖怪）は確かな事実の語も認める。科学は題名と題材名だけ
    # （事実の文に「精神性発汗」のような教科書の語が入っていることがあるため）。
    allowed = f"{ttl} {subject} {sure_facts_txt if check_subject else ''}"
    for i, t in enumerate(body):
        bare = _QUOTED_RE.sub("", t)
        jar = []
        for m in re.finditer(r"[\u4e00-\u9fff々]{4,}", bare):
            w = m.group(0)
            # 「進化先知ってる」のように、最後の字が送り仮名つきの動詞・形容詞なら外す
            if re.match(r"[っるらりれろいうえかきくけこさしすせそたちつてとまみむめもわ]", bare[m.end():m.end() + 1]):
                w = w[:-1]
            if len(w) >= 4 and w not in allowed:
                jar.append(w)
        if jar:
            add(i, "jargon", f"教科書の言葉（{'・'.join(jar)}）を普段の言葉に言い換える")
    return viol


# 名前を伏せた主語の例文（「知ってた？ このポケモン実は」など）。voice_style の常套句・
# 冒頭フック例にあると、GPT が1行目にそのまま使う（pokemon-lab 27本中16本が「このポケモンの
# モデル、実は…」で始まっていた）。
_PLACEHOLDER_QUOTE_RE = re.compile(
    # 「 / 」区切りの例文リストの1項目だけを対象にする（ルール本文中の引用は残す）
    r"(?:(?<=: )|(?<=/ ))「[^「」]{0,40}(?:このポケモン|この妖怪|このSCP|この2匹|この報告書|知ってた)[^「」]{0,40}」"
    r"(?:[ \t]*/[ \t]*)?"
)


def _sanitize_voice_block(block: str) -> str:
    """ショート専用: 語り口ブロックから、品質バーと衝突する指定を外す。

    - 例文リストから、名前を伏せた主語の例文を消す。
    - 「1行目は必ず『これ知ってた？』…で始める」「締めは…余韻で終える」のような、
      行の役割と食い違う文を落とす（_sanitize_short_rules と同じ規則）。
    """
    if not block:
        return block
    block = _PLACEHOLDER_QUOTE_RE.sub("", block)
    block = re.sub(r"[ \t]*/[ \t]*$", "", block, flags=re.M)
    # 例文がすべて消えた「冒頭フック例（…）: 」の行は落とす
    block = "\n".join(l for l in block.split("\n") if not re.search(r"[:：]\s*$", l)
                      or l.lstrip().startswith("- 厳守") or l.lstrip().startswith("- 禁止"))
    return _sanitize_short_rules(block)


# ショート専用の行の役割。チャンネル固有の構成(short_format.structure)の後ろに置き、
# 食い違うところはこちらを優先させる。
# 【2026-10-03 第2周】4ch の short_format は「4行目=言い換えで自分ゴト化（新情報の追加は
# 禁止）」「5行目=2つ目の事実を新しく足さない／『記録はここで途切れている』系の余韻」と
# 指定していて、本文5行のうち事実を運ぶのが 1〜3行目だけになっていた（第1周サンプル4本で
# 実質の情報は2〜3個、比較対象の上位ショートは 4〜6個）。この指定は 09-07 の「15〜25%の崖」
# 対策として入ったが、channel JSON 自身が 09-18 に「5回の改訂を経ても効果なし＝打ち切り」と
# 記録している。channel JSON は書き換えず（patch_channel_file を通す運用のため）、
# ショート専用プロンプトの中でだけ、その文を外して下の役割に置き換える。
_SHORT_LINE_ROLES = """# 行の役割(ショート・上の構成と食い違うときはこちらを優先)
- 1行目: 題材名＋事実①(品質バー2の型)。まだ答えは言わない。
- 2行目: 1行目を受けた驚きか、視聴者の疑問の代弁。答えは言わない。
- 3行目: 1行目の答えの核を言い切る。事実②(数字・出典・仕組みの名前)を入れる。
- 4行目: 事実③。3行目の裏付けになる別の数字・記録か、意外な飛び火(別の場面・別の作品・別の実験)。3行目の言い換え・たとえだけの行にしない。
- 5行目: 事実④でオチ(品質バー7のどれか)。
- 最終行: 高評価+登録のCTA(下の指定どおり短く)。
"""

# 掛け合い（解説役＋聞き役）チャンネルのショート専用の行の役割（2026-10-03 第3周）。
# 第2周の6行構成（解説・聞き・解説・解説・解説・CTA）は、事実を4つ運ぶために3〜5行目が
# 解説役の3連続になり、pokemon-lab では聞き役が消えて解説役がツッコミ（「いや強すぎでしょ！」）
# まで言っていた。比較対象の掛け合い型（化け学のふしぎ 848万・215万）は、聞き役の短い
# 一言（「いや引き寄せられんのかい」「なんで？」）が数行おきに入る。そこで聞き役の行を
# 8〜18字に縮めて2回入れ、本文6行＋CTA の7行にする（総字数の帯は変えない）。
SHORT_DIALOGUE_LINE_COUNT = 7
# 本文6行の話者（0=解説役, 1=聞き役）と、事実を運ぶ行か
SHORT_DIALOGUE_SPEAKERS = (0, 1, 0, 0, 1, 0)
SHORT_DIALOGUE_FACT_LINES = (0, 2, 3, 5)
_SHORT_LINE_ROLES_DIALOGUE = """# 行の役割(掛け合いショート・全7行・上の構成と食い違うときはこちらを優先)
- 1行目(解説役・20〜32字): 題材名＋事実①(品質バー2の型)。問いで終えるなら、問いの後ろに答えや説明を続けない。
- 2行目(聞き役・8〜18字): 1行目への驚きか、視聴者の疑問の代弁。1行目に出た語だけを使う。答えは言わない。
- 3行目(解説役・26〜34字): 1行目の答えの核を言い切る。事実②。
- 4行目(解説役・26〜34字): 「しかも」「なんと」「恐ろしいことに」「ちなみに」でつなぎ、事実③。3行目の裏付けになる別の数字・記録か、意外な飛び火(別の場面・別の作品・別の実験)。3行目の言い換えにしない。
- 5行目(聞き役・8〜18字): ツッコミか「なんで？」「じゃあ〜は？」の問い。1〜4行目に出た語だけを使う。
- 6行目(解説役・26〜34字): 5行目の問いに事実④で答え、そのまま品質バー7の型(冒頭へ戻る二人称の問い／コメントしたくなる問い)で終える。説明文で終えない。
- 7行目: 高評価+登録のCTA(下の指定どおり短く)。
- 各行の "fact" に、その行で使ったファクトシートの番号(例 "F1")を書く。聞き役の行とCTAは null。同じF番号を2行で使わない。
- 行どうしは会話としてつながる: 聞き役の問いに次の行が答え、解説役の行は前の行を受けて「しかも」「実は」で積み上げる。事実を箇条書きのように並べるだけの台本は不合格。
- 「〜という記録。」「〜なんだ。」の同じ語尾を3行続けない。

# お手本(実在の上位ショートの書き起こし。言い回しは真似せず、流れ・密度・つなぎ方を真似る)
- 化け学のふしぎ(848万回・掛け合い): 「ネズミにモンスター磁石を近づけたらどうなる？」→「この磁石の下では、離れたコインが縦に積み上がる」→「では、この磁石をネズミに近づけていこう」→(聞き役)「いや引き寄せられんのかい」「そもそもなんでネズミが磁石から離れるの？」→「実は全ての物質は反磁性を持つからなんだ」→(聞き役)「ネズミの何が反発してるの？」→「特に細胞に含まれる水分子が反発するんだ」
- じゆ(19万回・SCP): 「もしあなたの周りで『カチカチ』という音が聞こえたら、もう助かりません」→「SCP-4975は、首の骨を鳴らして獲物に宣告する捕食者です」→「恐ろしいことに、地球の裏側に逃げても、音は常にすぐ後ろから聞こえます」→ …最後に「あなたの後ろの音、今止まりませんでしたか」
- なぞはな(52万回・ポケモン21秒): 「ザシアンは設定上、メスしかいない」→「『妖精王の剣』と恐れられた」→「ザマゼンタは『格闘王の盾』」→「兄弟でもありライバルでもある」
"""

# ショート専用のときに channel JSON の構成文から外す文（上の _SHORT_LINE_ROLES と衝突する指定）。
_SHORT_STRUCTURE_DROP = (
    "足してはならない", "足さない", "追加は禁止", "好きな人多い", "キャラ愛",
    "系で終える", "系の前向きな余韻", "系の警告で終える", "だけを伝える",
    "これ知ってた", "余韻", "懐かしい",
    # 第3周: 「同じ行の後半に必ず数字を置く」（聞き役に新しい数字を言わせる指定）と
    # 「4行目でたとえ話に落とし」（事実を運ばない行を作る指定）
    "同じ行の後半に必ず", "たとえ話に落とし", "たとえ話で自分ゴト化",
)


def _sanitize_short_rules(block: str, replace_numbered: bool = False) -> str:
    """ショート構成ルールの文から、行の役割と衝突する指定だけを外す。

    - 「N行目=…」の構成行に衝突語があれば、その行は丸ごと
      「N行目=下の『行の役割』のN行目に従う。」に置き換える（引用の中の「。」で
      文を割ると、例文の断片だけが残るため）。
    - それ以外の行（extra_rules など）は「。」で文に分け、衝突語を含む文だけ落とす。
    """
    out = []
    for line in block.split("\n"):
        m = re.match(r"^(\s*)(\d+)行目=", line)
        if m and replace_numbered:
            # 行の数・役割そのものを差し替える（掛け合い7行構成）ときは、チャンネル固有の
            # 「N行目=…」を全部、行の役割への参照にする。
            out.append(f"{m.group(1)}{m.group(2)}行目=下の『行の役割』の{m.group(2)}行目に従う。")
            continue
        if not any(k in line for k in _SHORT_STRUCTURE_DROP):
            out.append(line)
            continue
        if m:
            out.append(f"{m.group(1)}{m.group(2)}行目=下の『行の役割』の{m.group(2)}行目に従う。")
            continue
        prefix = re.match(r"^\s*(?:[-・*]\s*)?", line).group(0)
        sents = [x for x in re.split(r"(?<=。)", line[len(prefix):]) if x]
        kept = [x for x in sents if not any(k in x for k in _SHORT_STRUCTURE_DROP)]
        joined = "".join(kept).strip()
        if len(joined) >= 20:  # 短い残り（「この切り替わり自体を…」）は文脈が無いので捨てる
            out.append(prefix + joined)
    return "\n".join(out)


# 実績で負けている冒頭の型（channel JSON の voice_style.hook_patterns から抽選しない）。
# yokai-watch「キャラ愛型」(「〇〇、好きな人多いよね。でも元ネタを知ると…」):
#   09-12〜09-29 公開 50本のうち 28本がこの型（または同系の元ネタ明かし）で始まり、
#   再生中央値 253・900回以上 4/28。それ以外の 22本は中央値 855・7/22。
#   再生 2〜6 回の下位3本はすべてこの型（scratchpad/loop/tools/perf.py の集計）。
_RETIRED_HOOK_PATTERNS: Dict[str, Dict[str, str]] = {
    "yokai-watch": {"キャラ愛型": "中央値253 vs 855（09-12〜09-29）"},
}

def _validator_channel_dict(channel, short_only: bool, n_lines: int) -> Dict[str, Any]:
    """scenario_validator に渡す channel dict。

    掛け合いのショート専用は 7行（聞き役の行は 8〜18字）にしたので、channel JSON の
    short_format.line_count=6 / 行の下限字数のままだと、正しい台本に毎回「行数」「字数」の
    警告が出る。channel JSON は書き換えず、検証に渡す写しだけ合わせる。
    """
    try:
        raw = channel._raw or {}
    except AttributeError:
        raw = {}
    if not (short_only and isinstance(raw, dict)
            and len(getattr(channel, "characters", {}) or {}) >= 2
            and n_lines == SHORT_DIALOGUE_LINE_COUNT):
        return raw
    out = dict(raw)
    sf = dict(out.get("short_format") or {})
    sf["line_count"] = SHORT_DIALOGUE_LINE_COUNT
    sf["line_min_chars"] = 8
    sf["line_max_chars"] = 36
    out["short_format"] = sf
    return out


def _short_only_mode(channel, explicit: Optional[bool] = None) -> bool:
    """このチャンネルの台本がショートだけで使われるか（=長尺台本を作らないか）。

    13ch すべてが autopilot.gen_type = "short" で、長尺は1本もレンダリングされて
    いないのに、プロンプトは毎回 full_scenario を 55〜64 行・4,800字以上要求し、
    行数・字数が足りないと GPT を再呼び出し → 7セクションの拡張まで走っていた
    （2026-10-03 実測: daily-science 1本 152.6 秒、うち長尺分の再試行2回＋拡張7回）。
    長尺の指示がショートの指示と同じプロンプトに並ぶため、長尺用の
    「冒頭5秒で本編宣言」「次回予告を必ず」もショートに混ざっていた。

    explicit が渡されればそれに従う。環境変数 SCENARIO_FORCE_FULL=1 で長尺を強制
    （run_scp_lab_3000_full.py のような手動の長尺レンダリング用）。それ以外は
    channel JSON の autopilot.gen_type（無ければ video_format.output.gen_type）が
    "short" のときだけ True。
    """
    if explicit is not None:
        return bool(explicit)
    if os.environ.get("SCENARIO_FORCE_FULL", "").strip() in ("1", "true", "yes"):
        return False
    try:
        raw = channel._raw or {}
    except AttributeError:
        return False
    if not isinstance(raw, dict):
        return False
    gen_type = (raw.get("autopilot") or {}).get("gen_type")
    if not gen_type:
        gen_type = ((raw.get("video_format") or {}).get("output") or {}).get("gen_type")
    return gen_type == "short"


def _series_hint_block(channel) -> str:
    """シリーズ化（連作ブランディング）の指示ブロック。

    `theme_priority.series_lineup`（シリーズ名のリスト）か、無ければ
    `short_series_name` を使う。どちらも無ければ空文字＝従来通り。
    """
    try:
        raw = channel._raw or {}
    except AttributeError:
        raw = {}
    lineup = ((raw.get("theme_priority") or {}).get("series_lineup") or [])
    series = (raw.get("short_series_name") or "").strip()
    if not lineup and not series:
        return ""
    lines = [
        "# シリーズ化ルール(チャンネル回遊・登録率対策)",
        "- 本チャンネルのショートは単発ではなく**連作シリーズ**として見せる。"
        "今回のテーマが属するシリーズ名を `series_name` に出力する。",
        "- 最終行のCTAで**必ずシリーズ名に触れる**。ただし別の句として足さず、"
        "「登録すると何が届くか」をシリーズ名で言う形に溶かす"
        "（例:「登録で〇〇シリーズの次も届く」）。最終行の字数指定を超えないこと。"
        "「このチャンネルには同じ系統の動画がまだある」と伝えるのが目的。",
    ]
    if lineup:
        joined = " / ".join(f"「{s}」" for s in lineup[:8])
        lines.append(f"- シリーズ候補（テーマに一番近いものを1つ選ぶ）: {joined}")
        lines.append("- どれにも当てはまらない場合だけ、同じ粒度で新しいシリーズ名を作ってよい。")
    else:
        lines.append(f"- シリーズ名: 「{series}」（このチャンネル共通の連作名）。")
    return "\n".join(lines) + "\n\n"


def _cliffhanger_block(channel, *, last_content_line: str = "オチ") -> str:
    """クリフハンガー（答えを6割だけ見せる）指示ブロック（オプトイン）。

    `content_policy.cliffhanger` を宣言したチャンネルだけに効く:
      {"enabled": true, "wording": "続きはチャンネルの他の動画で"}
    """
    try:
        cfg = (channel.content_policy or {}).get("cliffhanger") or {}
    except AttributeError:
        cfg = {}
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return ""
    wording = (cfg.get("wording") or "続きはチャンネルの他の動画で").strip()
    return (
        "# クリフハンガー・ルール(チャンネル回遊・登録率対策・絶対厳守)\n"
        f"- **{last_content_line}では核心の6割だけ明かし、残り4割は『まだ語られていない謎』として残す**。\n"
        "- 答えの手前で止める一言を必ず1つ置く。例:「実はこの話、まだ続きがあるんだ」"
        "「本当にヤバいのはこの後なんだけど」「その理由は、もっと怖い」。\n"
        f"- そのうえで最終行のCTAで「{wording}」のニュアンスに接続する。\n"
        "- ❌ 全部説明しきって満足させて終わるのは不合格（満足した視聴者は登録しない）。\n"
        "- ❌ 逆に何も答えないのも不合格。**6割は必ず答える**"
        "（0%だと釣り扱いされて低評価が付く）。\n\n"
    )


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
            # シナリオ生成は system が固定・user だけ変わるので、system 末尾に breakpoint
            system=[{"type": "text",
                     "text": system_full,
                     "cache_control": {"type": "ephemeral"}}],
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
        """title が blacklist のいずれかに該当すれば、その語を返す。

        照合規則は `theme_dedup.blacklist_match`（数字境界を守る部分一致 +
        `re:` 正規表現 / `=` 完全一致）。素の部分一致だと `SCP-173` が
        `SCP-1730`〜`1739` の10体を巻き添えにしていた。
        """
        if not blacklist:
            return None
        from pipeline.auto_scenario import theme_dedup as _td
        return _td.blacklist_match(title, blacklist)

    def _dedupe_theme(self, channel, theme: Dict) -> Dict:
        """選択済みテーマが既存動画/過去シナリオと重複していれば別テーマへ差し替える。

        全生成経路の最終ゲート。`theme_override`（autopilot / run_*.py / batch）でも
        必ずここを通るので、generator 内の再抽選をバイパスする経路の重複量産を止める。

        判定:
          - チャンネルの theme_blacklist に一致 → 除外（**硬い**却下）
          - チャンネルの genre_blacklist のジャンルに分類される → 除外（**硬い**却下）
          - 既存タイトルとの類似度 >= THEME_DUP_BLOCK_THRESHOLD → 重複として除外（柔らかい却下）
        差し替え順: suggest_themes（語彙/意味 dedup 込み）→ seed 再抽選。

        代替が見つからなかったときの扱い（2026-09-12 に分けた）:
          - 重複（柔らかい却下）… 元テーマのまま続行（投稿 skip より重複投稿の方がマシ）
          - blacklist / genre_blacklist（硬い却下）… `ThemeRejectedError` で止める。
            運用側が「この系統は 0 再生なので作るな」と明示した設定であり、
            それを黙って無視して作るのは設定が無いのと同じ。09-11 に scp-lab
            『財団組織・職員』が、suggest_themes の例外（seed の形式エラー）を
            ここで握り潰した結果**そのまま採用**されていた。
        代替探索の失敗（LLM 落ち・seed 枯渇）は握り潰さず `theme_gate` に記録する。
        """
        try:
            from pipeline.auto_scenario import theme_dedup as _td
        except Exception as e:
            print(f"  ⚠️ theme dedup guard disabled: {e}")
            return theme

        existing = self._existing_titles_for_dedup(channel.id)
        blacklist = self._channel_theme_blacklist(channel)
        genre_blacklist = self._channel_genre_blacklist(channel)
        # 型語の自動抽出は existing に対して1回だけ
        stop = _td.corpus_stopwords(existing)

        def _reject_reason(title: str) -> Tuple[Optional[str], bool]:
            """(理由, 硬い却下か)。理由 None なら通過。"""
            title = (title or "").strip()
            if not title:
                return None, False
            bl = self._blacklisted_reason(title, blacklist)
            if bl:
                return f"blacklist『{bl}』", True
            gb = self._genre_blacklisted_reason(channel.id, title, genre_blacklist)
            if gb:
                return f"停止ジャンル『{gb}』", True
            # 実在人物名・第三者IP（→ pipeline/entity_gate）。09-14 に scp-lab で
            # 実在の著者を SCP 扱いした動画が公開された。seeds / 手入力キューも通る
            # ここで硬く止める（代替が無ければ ThemeRejectedError）。
            eh = self._entity_hit(channel, title)
            if eh:
                return f"実在人物/第三者IP『{eh.matched}』", True
            hit = _td.find_lexical_duplicate(
                title, existing, threshold=THEME_DUP_BLOCK_THRESHOLD, stopwords=stop)
            if hit is not None:
                return f"既存『{hit[0][:24]}』に類似({hit[1]:.2f})", False
            return None, False

        reason, hard = _reject_reason(theme.get("title"))
        if not reason:
            return theme

        print(f"  ♻️ Theme '{theme.get('title')}' rejected — {reason}. 別テーマを選び直します")
        tried = {(theme.get("title") or "").strip().lower()}
        errors: List[str] = []

        # 1) AI 提案（内部で除外リスト+語彙+意味 dedup 済み）から重複しない最初の1件
        try:
            for s in (self.suggest_themes(channel, count=6) or []):
                if not isinstance(s, dict):
                    continue
                t = (s.get("title") or "").strip()
                if not t or t.lower() in tried:
                    continue
                tried.add(t.lower())
                r, _ = _reject_reason(t)
                if not r:
                    print(f"  ✅ Replaced with AI-suggested theme: {t}")
                    return {
                        "title": t,
                        "angle": s.get("angle", "") or "",
                        "parent_title": s.get("parent_title"),
                        "theme_gate": {"replaced": theme.get("title"), "reason": reason},
                    }
        except Exception as e:
            # 握り潰さない。理由を残して次の手段へ（seed 再抽選）。
            errors.append(f"suggest_themes: {type(e).__name__}: {e}")
            print(f"  ⚠️ AI theme replacement failed: {e}")

        # 2) seed 再抽選（過去回避つき）
        for _ in range(6):
            try:
                cand = self._pick_seed_avoiding_past(channel)
            except Exception as e:
                errors.append(f"seed re-pick: {type(e).__name__}: {e}")
                break
            t = (cand.get("title") or "").strip()
            r, _ = _reject_reason(t)
            if t and t.lower() not in tried and not r:
                print(f"  ✅ Replaced with seed theme: {t}")
                cand = dict(cand)
                cand["theme_gate"] = {"replaced": theme.get("title"), "reason": reason}
                return cand
            tried.add(t.lower())

        if hard:
            # 運用側の停止設定に当たったテーマを、代替が無いからといって作らない。
            msg = (f"テーマ '{theme.get('title')}' は {reason} に該当し、代替テーマも"
                   f"見つかりませんでした（試行 {len(tried)} 件"
                   + (f" / 失敗: {' | '.join(errors)}" if errors else "") + "）")
            print(f"  ⛔ {msg}")
            raise ThemeRejectedError(msg)

        print(f"  ⚠️ 非重複の代替テーマが見つからず、元の '{theme.get('title')}' で続行します"
              + (f"（代替探索の失敗: {' | '.join(errors)}）" if errors else ""))
        out = dict(theme)
        out["theme_gate"] = {"kept_despite": reason, "errors": errors}
        return out

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
        return _sanitize_regenerated_title(title.strip("「」\"'　 "))

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

    def _regenerate_title_for_ctr(
        self,
        channel,
        theme: Dict,
        scenario_data: Dict[str, Any],
        weak_title: str,
        advice: List[str],
    ) -> Optional[str]:
        """CTR が弱いタイトルを、具体的な改善指示つきで作り直す。

        `_regenerate_title`（重複対策）と違い、禁止リストではなく
        「何が足りないか」を渡す。落第の理由が数字欠落なのか説明語尾なのかは
        `title_quality.score_title` が判定済みなので、それをそのまま指示にする。
        """
        hook_lines: List[str] = []
        for line in (scenario_data.get("short_scenario")
                     or scenario_data.get("full_scenario") or [])[:4]:
            text = line.get("text") if isinstance(line, dict) else ""
            if text:
                hook_lines.append(str(text))
        advice_block = "\n".join(f"  - {a}" for a in advice) or "  - より強いフックにする"
        prompt = (
            f"YouTubeショートのタイトルを1つだけ作り直してください。\n\n"
            f"# チャンネル\n{channel.name}（{channel.concept}）\n\n"
            f"# 動画のテーマ\n{theme.get('title', '')}\n"
            f"切り口: {theme.get('angle', '') or '(指定なし)'}\n\n"
            f"# 本編の冒頭\n" + ("\n".join(hook_lines) or "(なし)") + "\n\n"
            f"# 今のタイトル（クリック率が弱いので却下）\n「{weak_title}」\n\n"
            f"# 必ず直すこと\n{advice_block}\n\n"
            f"# 条件\n"
            f"- 内容の意味は変えず、クリックしたくなる言い方に変える。\n"
            f"- 48文字以内。結論・答えは書かない（伏せたまま気にさせる）。\n"
            f"- 先頭に【】のプレフィックスを付けない。\n"
            f"- タイトル本文のみを出力（前置き・引用符・番号なし）。\n"
        )
        try:
            self._current_channel_id = channel.id
            self._current_purpose = "title_ctr_regen"
            raw = self._call_text_with_fallback(
                [
                    {"role": "system", "content": "タイトル1行のみ出力。説明・引用符は不要。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_tokens=200,
                gpt_model=GPT_MODEL_LIGHT,
            )
        except Exception as e:
            print(f"  ⚠️ CTR title regeneration failed: {e}")
            return None
        title = (raw or "").strip().splitlines()[0].strip() if (raw or "").strip() else ""
        return _sanitize_regenerated_title(title.strip("「」\"'　 "))

    def _enforce_title_quality(self, channel, theme: Dict, result: Dict[str, Any],
                               scenario_data: Dict[str, Any]) -> None:
        """最終タイトルの CTR スコアが基準未満なら作り直す。

        プロンプト（`_title_rule_block`）で数字・感情ワード・疑問形を要求しているが、
        LLM はしばしば落とす。生成後に決定論的に採点し、落第したら最大2回まで
        作り直して「候補の中で最高スコア」を採用する（作り直しが全部弱ければ
        元のタイトルのまま進む — 投稿を止めるより弱いタイトルの方がマシ）。

        `content_policy.title_quality_gate: false` を宣言したチャンネルは無効化できる。
        """
        try:
            from pipeline import title_quality as _tq
        except Exception as e:
            print(f"  ⚠️ title quality gate disabled: {e}")
            return

        try:
            if (channel.content_policy or {}).get("title_quality_gate") is False:
                return
        except AttributeError:
            pass

        try:
            raw = channel._raw or {}
        except AttributeError:
            raw = {}

        title = (result.get("title") or "").strip()
        if not title:
            return

        detail = _tq.score_title(title, raw)
        result["title_quality"] = {
            "score": detail["score"],
            "passed": detail["passed"],
            "reasons": detail["reasons"],
        }
        if detail["passed"]:
            print(f"  ✅ タイトルCTRスコア {detail['score']}: {title}")
            return

        print(
            f"  📉 タイトルCTRスコア {detail['score']} (<{_tq.PASS_SCORE}) — "
            f"{' / '.join(detail['reasons'])} → 作り直します"
        )

        candidates = [title]
        advice = detail["advice"]
        for attempt in range(2):
            cand = self._regenerate_title_for_ctr(
                channel, theme, scenario_data, candidates[-1], advice
            )
            if not cand:
                break
            candidates.append(cand)
            cand_detail = _tq.score_title(cand, raw)
            print(f"  ↻ 再生成 {attempt + 1}/2: [{cand_detail['score']}] {cand}")
            if cand_detail["passed"]:
                break
            advice = cand_detail["advice"]

        best = _tq.best_of(candidates, raw)
        if best["title"] and best["title"] != title:
            result.setdefault("original_title", title)
            result["title"] = best["title"]
            print(f"  ✅ タイトルを差し替えました [{best['score']}]: {best['title']}")
        result["title_quality"] = {
            "score": best["score"],
            "passed": best["score"] >= _tq.PASS_SCORE,
            "reasons": best["detail"]["reasons"],
            "rejected_title": title if best["title"] != title else None,
            "attempts": len(candidates) - 1,
        }

    def _regenerate_title_with_bans(
        self,
        channel,
        theme: Dict,
        scenario_data: Dict[str, Any],
        rejected: str,
        advice: List[str],
    ) -> Optional[str]:
        """規約違反タイトルを、違反内容を明示して作り直す。

        `_regenerate_title_for_ctr` と違い、渡すのは「守らなければ却下される
        機械ルール」。自然文の"お願い"では守られないことが実測で分かっているので、
        ここで作り直したものも必ず再検査する（プロンプトは保証ではない）。
        """
        hook_lines: List[str] = []
        for line in (scenario_data.get("short_scenario")
                     or scenario_data.get("full_scenario") or [])[:4]:
            text = line.get("text") if isinstance(line, dict) else ""
            if text:
                hook_lines.append(str(text))
        advice_block = "\n".join(f"  - {a}" for a in advice) or "  - 規約に合わせる"
        prompt = (
            f"YouTubeショートのタイトルを1つだけ作り直してください。\n\n"
            f"# チャンネル\n{channel.name}（{channel.concept}）\n\n"
            f"# 動画のテーマ\n{theme.get('title', '')}\n"
            f"切り口: {theme.get('angle', '') or '(指定なし)'}\n\n"
            f"# 本編の冒頭\n" + ("\n".join(hook_lines) or "(なし)") + "\n\n"
            f"# 却下されたタイトル\n「{rejected}」\n\n"
            f"# 絶対に守る規則（1つでも破ると再び却下されます）\n{advice_block}\n\n"
            f"# 条件\n"
            f"- 内容の意味は変えず、規則を満たす言い方に変える。\n"
            f"- 48文字以内。結論・答えは書かない。\n"
            f"- 先頭に【】のプレフィックスを付けない。\n"
            f"- タイトル本文のみを出力（前置き・引用符・番号なし）。\n"
        )
        try:
            self._current_channel_id = channel.id
            self._current_purpose = "title_constraint_regen"
            raw = self._call_text_with_fallback(
                [
                    {"role": "system", "content": "タイトル1行のみ出力。説明・引用符は不要。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_tokens=200,
                gpt_model=GPT_MODEL_LIGHT,
            )
        except Exception as e:
            print(f"  ⚠️ constraint title regeneration failed: {e}")
            return None
        title = (raw or "").strip().splitlines()[0].strip() if (raw or "").strip() else ""
        return _sanitize_regenerated_title(title.strip("「」\"'　 "))

    def _enforce_title_constraints(self, channel, theme: Dict, result: Dict[str, Any],
                                   scenario_data: Dict[str, Any]) -> None:
        """タイトルの機械ゲート（`title_rules.hard_constraints`）を適用する。

        自然文ルールが無視される問題への対処なので、ここは「通らなければ通るまで
        直す」。LLM 再生成 2 回 → それでも違反なら決定論的に書き換える。
        """
        try:
            from pipeline import title_constraints as _tc
        except Exception as e:
            print(f"  ⚠️ title constraint gate disabled: {e}")
            return

        try:
            raw = channel._raw or {}
        except AttributeError:
            raw = {}
        if not _tc.is_enforced(raw):
            return

        title = (result.get("title") or "").strip()
        if not title:
            return

        verdict = _tc.check(title, raw)
        if verdict["ok"]:
            result["title_constraints"] = {"ok": True, "violations": []}
            return

        print(f"  🚫 タイトル規約違反: {_tc.violation_summary(verdict)} → 作り直します（{title}）")
        original = title
        current = title
        for attempt in range(2):
            cand = self._regenerate_title_with_bans(
                channel, theme, scenario_data, current, verdict["advice"])
            if not cand:
                break
            cand_verdict = _tc.check(cand, raw)
            print(f"  ↻ 規約再生成 {attempt + 1}/2: "
                  f"[{'OK' if cand_verdict['ok'] else _tc.violation_summary(cand_verdict)}] {cand}")
            current = cand
            verdict = cand_verdict
            if cand_verdict["ok"]:
                break

        if not verdict["ok"]:
            repaired = _tc.repair(current, raw)
            re_verdict = _tc.check(repaired, raw)
            print(f"  🔧 機械修復: 「{current}」→「{repaired}」"
                  f"（{'OK' if re_verdict['ok'] else '未解消: ' + _tc.violation_summary(re_verdict)}）")
            current, verdict = repaired, re_verdict

        if current and current != original:
            result.setdefault("original_title", original)
            result["title"] = current
        result["title_constraints"] = {
            "ok": verdict["ok"],
            "violations": verdict["violations"],
            "rejected_title": original if current != original else None,
        }

    def _entity_hit(self, channel, text: str):
        """実在人物名・第三者IP の判定（→ pipeline/entity_gate）。モジュール不在なら None。"""
        try:
            from pipeline import entity_gate as _eg
        except Exception as e:
            print(f"  ⚠️ entity_gate unavailable: {e}")
            return None
        try:
            raw = channel._raw or {}
        except AttributeError:
            raw = {}
        return _eg.check(text, raw)

    def _enforce_entity_gate(self, channel, theme: Dict, result: Dict[str, Any],
                             scenario_data: Dict[str, Any]) -> None:
        """最終タイトルに実在人物名・第三者IPが入っていたら作り直し、駄目なら公開を止める。

        テーマ段のゲートを通っても、LLM が本文の固有名詞をタイトルへ持ち上げることがある
        （09-14: 題材「ショートスリーパーの異常性」→ 題名「なぜ堀大輔は72時間眠らないのか」）。
        再生成 2 回で解消しなければ `publish_blocked` を立てる（→ generate() の末尾）。
        """
        title = (result.get("title") or "").strip()
        if not title:
            return
        hit = self._entity_hit(channel, title)
        if hit is None:
            result["entity_gate"] = {"ok": True}
            return
        print(f"  🚫 タイトルに{hit.reason} → 作り直します（{title}）")
        original, current = title, title
        for attempt in range(2):
            advice = [
                f"「{hit.matched}」のような実在の人物名・他社のキャラクター/作品名を"
                f"タイトルに一切入れないこと（一般名詞・現象名で言い換える）。",
            ]
            cand = self._regenerate_title_with_bans(channel, theme, scenario_data, current, advice)
            if not cand:
                break
            current = cand
            hit = self._entity_hit(channel, current)
            print(f"  ↻ 人名/IP除去の再生成 {attempt + 1}/2: "
                  f"[{'OK' if hit is None else hit.matched}] {current}")
            if hit is None:
                break
        if current != original and hit is None:
            result.setdefault("original_title", original)
            result["title"] = current
        result["entity_gate"] = {
            "ok": hit is None,
            "matched": hit.matched if hit else None,
            "reason": hit.reason if hit else None,
            "rejected_title": original if current != original else None,
        }
        if hit is not None:
            print(f"  ⛔ タイトルから{hit.reason}を外せませんでした → 公開を止めます")

    def _enforce_fact_consistency(self, channel, result: Dict[str, Any]) -> None:
        """同じ会社の同じ指標を回ごとに違う数字で出さないための機械ゲート。

        09-05 に 日本マクドナルドの年収を 576万円（2023年有報）と 670万円
        （2024年12月期）で別々に公開した。どちらも出典上は正しいが、視聴者には
        同じ会社の年収が食い違って見える。有報を根拠にするチャンネルなので
        信頼に直接効く。テーマ重複ゲートはタイトルの語彙しか見ないので通ってしまう。

        期が違うだけなら画面に期を注記して両立させ（値には触らない）、
        同じ期で値が食い違うときだけ矛盾として記録・警告する。
        """
        try:
            from pipeline import fact_ledger as _fl
        except Exception as e:
            print(f"  ⚠️ fact consistency gate disabled: {e}")
            return

        try:
            raw = channel._raw or {}
        except AttributeError:
            raw = {}
        if not _fl.is_enforced(raw):
            return

        try:
            issues = _fl.check(channel.id, result)
            disclosed = _fl.disclose_period(result, issues)
            conflicts = [i for i in issues if i["kind"] == "conflict"]
            for i in conflicts:
                print(
                    f"  🚨 数値の矛盾: {i['entity']} の{i['metric']}が "
                    f"{i['old_value']}{i['unit']}（{i['old_period'] or '期不明'}・"
                    f"既存『{i['old_title'][:20]}』）と "
                    f"{i['new_value']}{i['unit']}（{i['new_period'] or '期不明'}）で食い違っています"
                )
            if disclosed:
                print(f"  📅 期を注記して両立させました: {disclosed} 行")
            # 【2026-09-28】conflict がある台本は公開されない（autopilot が枠ごと
            # 落とす）のに record していたため、視聴者が見ていない数字が台帳に積まれ、
            # 以後の生成がその幻の数字と矛盾して連鎖ブロックする自家中毒が起きていた
            # （09-28 company-facts 投稿0本の一因）。公開に進む台本だけ台帳に積む。
            if not conflicts:
                _fl.record(channel.id, result, source="generator")
            result["fact_consistency"] = {
                "ok": not conflicts,
                "conflicts": conflicts,
                "disclosed": disclosed,
            }
        except Exception as e:
            print(f"  ⚠️ fact consistency check failed: {e}")

    def _enforce_cross_channel_keywords(self, channel, theme: Dict, result: Dict[str, Any],
                                        scenario_data: Dict[str, Any]) -> None:
        """同日に全ch横断で同じキーワードが並ぶのを防ぐ（→ cross_channel_gate）。

        09-03 に「正体」を全chの強語に入れた結果、同じ日に5chが同時に「正体」
        入りのタイトルを出した。chごとの重複ゲートは全て素通りするので、
        最終タイトルの段階で横断的に見る。
        """
        try:
            from pipeline.auto_scenario import cross_channel_gate as _ccg
        except Exception as e:
            print(f"  ⚠️ cross-channel keyword gate disabled: {e}")
            return

        title = (result.get("title") or "").strip()
        if not title:
            return

        # 【2026-09-08】テーマ取り出し時（api_channel_autopilot）と同じ key を使う。
        # ここは LLM が書き直した題名で予約するので、key が無いと同じ1本が
        # 別物として2枠を食い、上限2の横断ゲートが1本で埋まる。
        key = _ccg.reservation_key(channel.id, (theme or {}).get("title") or title)

        hit = _ccg.blocking_keyword(channel.id, title, key=key)
        if hit is None:
            _ccg.reserve(channel.id, title, key=key)
            result["cross_channel_keywords"] = {"ok": True}
            return

        original = title
        current = title
        for attempt in range(2):
            advice = [
                f"「{hit[0]}」という語をタイトルに使わないこと"
                f"（本日すでに他チャンネルで{hit[1]}本使われている）。",
                "別の切り口の言葉で同じ興味を引くこと。",
            ]
            cand = self._regenerate_title_with_bans(
                channel, theme, scenario_data, current, advice)
            if not cand:
                break
            current = cand
            hit = _ccg.blocking_keyword(channel.id, current, key=key)
            print(f"  ↻ 横断語の再生成 {attempt + 1}/2: "
                  f"[{'OK' if hit is None else hit[0]}] {current}")
            if hit is None:
                break

        if hit is not None:
            # 直せなかった場合は投稿を止めず、そのまま通す（重複より欠測の方が痛い）。
            print(f"  ⚠️ 横断語「{hit[0]}」を解消できませんでした。そのまま公開します。")

        # 規約ゲートを再通過させてから確定する（言い換えで数字等が混入しうる）。
        try:
            from pipeline import title_constraints as _tc
            raw = channel._raw or {}
            if _tc.is_enforced(raw) and not _tc.check(current, raw)["ok"]:
                current = _tc.repair(current, raw)
        except Exception as e:
            print(f"  ⚠️ 横断語の言い換え後の規約再検査に失敗（そのまま確定）: {e}")
            result.setdefault("gate_failures", []).append(
                {"gate": "cross_channel_keywords/recheck", "error": f"{type(e).__name__}: {e}"})

        if current and current != original:
            result.setdefault("original_title", original)
            result["title"] = current
        _ccg.reserve(channel.id, result.get("title") or original, key=key)
        result["cross_channel_keywords"] = {
            "ok": hit is None,
            "blocked_keyword": hit[0] if hit else None,
            "rejected_title": original if current != original else None,
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

    def _title_rule_block(self, channel) -> str:
        """タイトル生成ルールのブロックを返す。

        `theme_priority.title_style` が設定されているチャンネルは、その勝ちパターンを
        タイトル書式として最優先で使う。従来はここが「なぜ〇〇？＋本当の理由」型の
        日常科学向け文面でハードコードされていて、チャンネル JSON 側で宣言した
        title_style はテーマ提案時（_theme_priority_block）にしか効いていなかった。
        その結果、2chまとめのように「発言引用＋『→』で結果を匂わせる」型が勝ち筋の
        チャンネルでも疑問型タイトルが生成されていた。

        title_style 未設定のチャンネルは従来のデフォルト文面のまま。
        """
        try:
            raw = channel._raw or {}
        except AttributeError:
            raw = {}
        tp = raw.get("theme_priority") or {}
        title_style = tp.get("title_style")

        # 投稿時タイトルは「[シリーズ名]タイトル 末尾ハッシュタグ」を YouTube の
        # 100 文字上限に収める（video_generator.generate_short_title）。
        # ここでその残り文字数を伝えて、切り詰めが起きないようにする。
        tags = (raw.get("defaults") or {}).get("short_title_hashtags") or "#shorts #ゆっくり解説"
        series = (raw.get("short_series_name") or "").strip()
        hard_cap = 100 - len(tags) - 1 - len(series)

        common = [
            "# タイトルルール(超重要・CTR改善のため絶対厳守)",
            "- ❌ NG: 「【ゆっくり解説】」のような定型プレフィックスを付ける。"
            "タイトル先頭にカギ括弧プレフィックスを付けない。",
            "- ❌ NG: 結論・答えをタイトルにバラす(例:「水たまりの謎、解けます！」)。"
            "結論はサムネ・本編で初めて出す。",
            # 2026-08-18: タイトルは「内容の説明」ではなく「タップの衝動」を作る。
            # 説明的タイトル（〜について/〜とは/〜の解説）は CTR が落ちる。
            "- ✅ タイトルは**「説明」ではなく「衝動」**を作る。"
            "読んだ瞬間に「え、なんで?」「見なきゃ」と指が動く一文にする。"
            "「〜について」「〜とは」「〜を解説」のような説明語尾は禁止。",
            "- ✅ **感情を動かす語を必ず1つ以上**入れる: "
            "実は / なぜ / だけ / 本当は / 知らない / やめて / ヤバい / 全員 / 99% / 3秒。",
            # 2026-08-19: 生成タイトルを CTR 採点（pipeline.title_quality）に通すように
            # したので、採点で加点される要素をプロンプト側でも明示して基準を揃える。
            # 数字はクリック率に効くわりに落とされやすいので独立した項目にする。
            "- ✅ **具体的な数字を必ず1つ入れる**: 「99%」「3秒」「5つ」「2倍」「17件」など。"
            "体感できる小さい数字ほど強い（「たくさん」「多くの」のような曖昧な量は不可）。",
            "- ✅ 「あなた」「君」など**視聴者を直接指す語**を入れると自分ゴト化して伸びる。",
            # 【2026-08-31】従来は「ハッシュタグを足しても切られない上限」＝約75字を
            # 提示していたが、これは「切れない上限」であって「成績が良い長さ」ではない。
            # 08-19以降のコホート(n=66)を長さ別に見ると:
            #   30字未満 維持率 50.4% / 30-40字 31.9% / 40-50字 36.2% / 50字超 30.1%
            # 長いタイトルはショートのフィード上で読み切られず、視聴判断の前に
            # スワイプされている。実効上限として30字を明示する。
            f"- **全角30文字以内**（技術上の上限は{hard_cap}字だが、実測で30字未満の"
            "維持率が50.4%、50字超は30.1%と大きく下回る。短く言い切ること）。",
            "- ❌ NG: 絵文字をタイトルに入れる。実測で絵文字ありは維持率32.7%・"
            "1000再生あたり登録0.33、絵文字なしは38.7%・0.49で、いずれも絵文字なしが上回る。",
            "- ❌ NG: 「#12：」のような連番プレフィックスや、"
            "「〇〇に隠された3つの秘密」「あなたは〜知ってる？」のような毎回同じ構文のテンプレ。"
            "実測で連番テンプレ型は維持率29.7%、自然文型は41.2%。",
            "- ※ 出力後にクリック率スコアで自動採点され、基準未満だと作り直しになる。"
            "「数字」「感情ワード」「疑問形(答えを伏せる)」の3点を最初から満たすこと。",
        ]

        if title_style:
            lines = common + [
                "- ✅ 本チャンネルの勝ちパターン（この書式を最優先で守る）:",
                f"  {title_style}",
            ]
            good = tp.get("good_examples") or []
            if good:
                lines.append("- ✅ 書式のお手本(型だけ真似る。文言をそのまま流用しない):")
                lines += [f"  - 「{g}」" for g in good[:5]]
            return "\n".join(lines) + "\n"

        return "\n".join(common + [
            "- ✅ OK: 「なぜアスファルトだけ？水たまりが『あそこ』にしかできない本当の理由」のように、"
            "答えではなく「なぜ？」という謎・違和感だけを置く疑問型・意外性重視。",
            "- 「本当の理由」「実は」「あそこ」「なぜか」「だけ」「〇〇すぎる」など"
            "意外性を匂わせるワードを必ず1つ以上入れる。",
            "- 視聴者が「気になる、答えを知りたい」と感じる謎の提示で止めるのが正解。",
        ]) + "\n"

    def _short_end_line_block(self, channel, line_no: int = 7) -> str:
        """short_scenario の最終行（締めCTA）の指示ブロックを返す。

        `line_no` は締めCTAが何行目かを表す（既定の構成は6行 = 6行目、
        channel JSON の short_format を持つチャンネルはその line_count）。

        既定は従来どおり「①登録CTA → ②関連動画CTA」。ただし長尺を作らない
        ショート専用チャンネル（autopilot.gen_type = "short"）で関連動画へ送ると、
        存在しない本編へ誘導してしまう。`content_policy.short_end_line` で上書きできる:

          {
            "omit_related_video": true,          # ②関連動画CTA を外す
            "wording": "お前らならどうする？",     # 代わりに置く締めの一言（任意）
            "subscribe_wording": "...",          # 登録CTAの言い回し（任意）
            "line_chars": "28〜36字"              # 最終行の字数（任意）
          }

        `subscribe_wording` を省くと既定の「登録すると次に何が届くか」の1句になる
        （2026-10-03 までは「1万人目標・毎日投稿中・応援よろしく」の3要素だった）。
        omit_related_video の最終行は既定 22〜36字（line_chars で上書き可）。
        """
        try:
            cfg = (channel.content_policy or {}).get("short_end_line") or {}
        except AttributeError:
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}

        custom_chars = (cfg.get("line_chars") or "").strip()

        def sub_cta(num: str) -> str:
            sub_wording = (cfg.get("subscribe_wording") or "").strip()
            if sub_wording:
                return (
                    f"    - {num}登録CTA: 「{sub_wording}」のニュアンスで登録を促す"
                    "(そのままコピペせず、その回の内容と地続きにする)。"
                    "このチャンネルの語り口を守り、叫ばない・煽らない・強い依頼にしない。\n"
                )
            # 【2026-10-03】既定を「1万人目標・毎日投稿中・応援よろしく」の3要素から
            # 「登録すると何が届くか」の1句に変えた。3要素版は最終行を 51〜63字に
            # 膨らませ（4ch 全部・本文5行の平均約140字に対し CTA が約28%）、
            # 「1万人」「応援」はチャンネル側の事情で視聴者の得を何も言っていない。
            # 実測では 3要素入りの 09-29 公開4本の登録はすべて 0。
            return (
                f"    - {num}登録CTA: 「チャンネル登録」か「登録すれば/登録で」の形で、"
                "**登録すると次に何が届くか**を、このチャンネルが毎回扱う題材で1句にする"
                "(例:「登録すれば次の1体の裏設定も届くよ」「登録で次のファイルも届く」)。"
                "❌「1万人目標」「応援よろしく」のようなチャンネル側の事情は書かない"
                "(視聴者の得にならず、字数だけ食う)。\n"
            )

        if cfg.get("omit_related_video"):
            end_chars = custom_chars or "22〜36字"
            wording = (cfg.get("wording") or "").strip()
            hint = (
                f"    - 「{wording}」は②で何が届くかを言うときのヒントにしてよい"
                "(そのまま足すと長くなるので、入れるなら②に溶かす)。\n"
                if wording else ""
            )
            return (
                f"  {line_no}行目=**高評価+登録CTA(必須・絶対省略禁止・1行で短く)**: "
                "「①高評価のお願い → ②登録すると何が届くか」の順で1行にまとめる。\n"
                "    - ①高評価: 「高評価」の語を必ず入れ、この回の中身に一言で触れる"
                "(例:「知らなかったら高評価」「この記録が届いたなら高評価を」)。\n"
                f"{sub_cta('②')}"
                f"{hint}"
                "    - ❌ 「関連動画」「本編」「フル動画」への誘導は禁止。"
                "本チャンネルは長尺を作らないため、存在しない動画へ送ることになる。\n"
                f"    - **{line_no}行目は{end_chars}**。チャンネル固有の構成に「最終行のみ40〜55字を許容」と"
                "あっても、それは上限であって目標ではない。平均視聴は11〜15秒で、"
                "26〜30秒のショートの最終行まで届く人は少ない。浮いた字数は本文の具体的な事実に回す。\n"
            )

        end_chars = custom_chars or "45〜70字"
        return (
            f"  {line_no}行目=**登録誘導+関連動画誘導CTA(必須・絶対省略禁止・順番厳守)**: "
            "必ず「①チャンネル登録誘導 → ②関連動画誘導」の順で1行に2つのCTAを連結する。\n"
            f"{sub_cta('①')}"
            "    - ②関連動画CTA: 必ず「関連動画」というワードを含め、"
            "ショート離脱者を長尺へ送る(「本編」より「関連動画」を優先)。\n"
            "    - 例:「登録すれば次の謎も届くよ。もっと詳しい話は関連動画から見てね!」\n"
            f"    - **{line_no}行目は{end_chars}**(2つのCTAを連結するため、"
            "通常の字数制限と異なってよい)。\n"
        )

    def _end_cta_block(self, channel, short_only: bool = False) -> str:
        """動画末尾の「チャンネル登録導線」ブロックを返す（オプトイン）。

        `content_policy.end_cta` が設定されているチャンネルだけに効く。形式:
          {
            "enabled": true,
            "wording": "チャンネル登録よろしくね",   # 任意・チャンネルのトーンに合わせた言い回し
            "reason": "毎日投稿してるから"           # 任意・登録する理由づけ
          }

        2026-08-04 の PDCA レポートで daily-science は週5,300再生に対し登録+2人と
        再生→登録の転換が異常に低く、締めが「今日試せる Tips」で終わって登録導線が
        無い回があった。そこで**最終行を必ず登録CTAにする**制約を明示的に足す。
        """
        try:
            cfg = (channel.content_policy or {}).get("end_cta") or {}
        except AttributeError:
            cfg = {}
        if not isinstance(cfg, dict) or not cfg.get("enabled"):
            return ""

        wording = (cfg.get("wording") or "チャンネル登録よろしく").strip()
        reason = (cfg.get("reason") or "").strip()
        if short_only:
            # ショート専用: full_scenario は作らないので full の指示を出さない。
            # 理由づけは長文のまま入れると最終行が 60字前後に膨らむ（2026-10-03 実測:
            # daily-science の最終行 61〜63字）ので「一言で」に縛る。
            reason_short = (
                f"- 登録の理由は「{reason}」を**一言(10字前後)に縮めて**添える"
                "(例:「毎日1つ届く」)。理由を文章で説明しない。\n"
                if reason else ""
            )
            return (
                "# 動画末尾の登録導線(登録転換率改善・絶対厳守)\n"
                "- **short_scenarioの最終行は必ず『高評価+チャンネル登録CTA』で終える**。"
                "オチ・余韻で終えて登録に触れないのは不合格。\n"
                f"- 言い回しはチャンネルのトーンに合わせて「{wording}」のニュアンスで書く"
                "（テンプレの棒読みにしない。その回の内容と地続きの一言にする）。\n"
                f"{reason_short}"
                "- 最終行の字数は上のショート構成ルールの指定に従う(長いCTAは本文の尺を奪う)。\n"
                "\n"
            )
        reason_line = (
            f"- 登録の理由づけとして「{reason}」のニュアンスを必ず添える"
            "（理由のない『登録お願いします』は登録率が上がらない）。\n"
            if reason else ""
        )
        return (
            "# 動画末尾の登録導線(登録転換率改善・絶対厳守)\n"
            "- **full_scenarioの最終行、short_scenarioの最終行は必ず"
            "『チャンネル登録CTA』で終える**。まとめ・Tips・余韻で終わって登録に触れずに終わるのは不合格。\n"
            f"- 言い回しはチャンネルのトーンに合わせて「{wording}」のニュアンスで書く"
            "（テンプレの棒読みにしない。その回の内容と地続きの一言にする）。\n"
            f"{reason_line}"
            "- 実践Tips・次回予告で締めたい場合も、**その直後に登録CTAを1行足して最後に置く**。"
            "順番は「まとめ → 次回予告 → 登録CTA」で固定する。\n"
            "\n"
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

        2026-08-18 追加のチャンネル差別化フィールド（すべて任意）:
          - speech_signature: 語尾・一人称・口癖など「声の指紋」
          - signature_phrases: そのチャンネルらしい常套句（自然に混ぜる）
          - reaction_style:   リスナー役のリアクションの作り方
          - pacing:           テンポ・間の取り方
          - banned_phrasing:  語り口として禁止する言い回し（forbidden は単語、こちらは言い方）
        いずれも未設定チャンネルでは出力に一切影響しない（挙動不変）。
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
        speech = vs.get("speech_signature")
        if speech:
            lines.append(f"- 声の指紋（語尾・一人称・口癖／他チャンネルと絶対に混ぜない）: {speech}")
        pacing = vs.get("pacing")
        if pacing:
            lines.append(f"- テンポ・間の取り方: {pacing}")
        sig = vs.get("signature_phrases") or []
        if sig:
            joined = " / ".join(f"「{p}」" for p in sig)
            lines.append(
                f"- このチャンネルらしい常套句（毎回2〜3個を自然に混ぜる・全部並べるのは不可）: {joined}"
            )
        reaction = vs.get("reaction_style")
        if reaction:
            lines.append(f"- リアクション役の作り方: {reaction}")
        hooks = vs.get("opening_hooks") or []
        if hooks:
            sample = " / ".join(f"「{h}」" for h in hooks)
            lines.append(
                f"- 冒頭フック例（雰囲気を真似る・丸ごとコピペは不可。例の「このポケモン」"
                f"「この妖怪」「このSCP」のような名前を伏せた主語は、実際の題材名に置き換える）: {sample}"
            )
        forbidden = vs.get("forbidden") or []
        if forbidden:
            lines.append(f"- 使用禁止ワード/要素: {', '.join(forbidden)}")
        banned = vs.get("banned_phrasing") or []
        if banned:
            lines.append("- 禁止する言い回し（1つでも出たら不合格）:")
            for b in banned:
                lines.append(f"  - {b}")
        style_rules = vs.get("style_rules") or []
        if style_rules:
            lines.append("- 厳守する語りのルール:")
            for r in style_rules:
                lines.append(f"  - {r}")
        return "\n".join(lines) + "\n\n"

    def _hook_variant_block(self, channel, line_label: str = "1行目") -> str:
        """今回の動画で使う「冒頭3秒の型」を1つ抽選してプロンプトブロックを返す。

        共通の `_HOOK_3SEC_RULE` は4型（これ知ってた?型 / 実は型 / した結果型 /
        違和感の問い型）を全チャンネルに配っているため、どのチャンネルも冒頭
        3秒の言い回しが同じになり、チャンネルの個性が最初の1行で消えていた。

        `voice_style.hook_patterns` を宣言したチャンネルでは、そのチャンネル
        固有の型（3〜5個）から**1本ごとにランダムで1型を選び**、その型に固定
        して書かせる。生成のたびに型が変わるので、同じチャンネル内でも冒頭が
        テンプレ化しない。

        hook_patterns の要素は dict / str のどちらでもよい::

            {"name": "体感再現型",
             "template": "「今すぐ〇〇してみて」で始め、視聴者の体で再現させる",
             "example": "今すぐ耳をふさいでみて。ゴーって音、あれ血液の音なんだ"}

        未設定なら空文字を返し、呼び出し側は従来の共通ルールを使う（挙動不変）。
        """
        vs = getattr(channel, "voice_style", None) or {}
        patterns = vs.get("hook_patterns") or []
        if not patterns:
            return ""

        norm: List[Dict[str, str]] = []
        for p in patterns:
            if isinstance(p, dict):
                name = str(p.get("name") or "").strip()
                if not name:
                    continue
                norm.append({
                    "name": name,
                    "template": str(p.get("template") or "").strip(),
                    "example": str(p.get("example") or "").strip(),
                })
            elif isinstance(p, str) and p.strip():
                norm.append({"name": p.strip(), "template": "", "example": ""})
        if not norm:
            return ""

        retired = _RETIRED_HOOK_PATTERNS.get(getattr(channel, "id", "") or "", {})
        active = [p for p in norm if p["name"] not in retired]
        if active and len(active) < len(norm):
            print(f"🎣 実績の悪い型を除外: {', '.join(p['name'] for p in norm if p['name'] in retired)}")
            norm = active

        chosen = random.choice(norm)
        others = [p["name"] for p in norm if p["name"] != chosen["name"]]
        print(f"🎣 冒頭3秒の型: 【{chosen['name']}】 (候補{len(norm)}型から抽選)")

        lines = [
            "# 冒頭3秒ルール(最重要・これを外した時点で不合格)",
            f"- ショートは**最初の3秒**で視聴継続がほぼ決まる。{line_label}は必ず「問い」か「驚き」から始める。",
            "- ❌ 挨拶・自己紹介・チャンネル説明・テーマ紹介・前置き・「今回は〜」は1文字でも入れたら不合格。",
            f"- ✅ **今回の動画の{line_label}は必ず【{chosen['name']}】で書く**"
            "（このチャンネル専用の型。今回はこの型に固定し、他の型に逃げない）。",
        ]
        if chosen["template"]:
            lines.append(f"  - 型の作り方: {chosen['template']}")
        if chosen["example"]:
            lines.append(f"  - 参考例（丸写し禁止・テーマに合わせて言い換える）: 「{chosen['example']}」")
        lines += [
            f"- **{line_label}には題材の固有名(ポケモン名・SCP番号・妖怪名・現象や物の名前)を必ず入れる**。"
            "型や参考例にある「このポケモン」「この妖怪」「このSCP」「これ」は、実際の名前に置き換えて書く"
            "(フィードで流れてきた視聴者にはタイトルが見えていない)。",
            "- 型は言い回しではなく役割(問い/驚き)を借りるもの。型の言い回しがテーマに合わないとき"
            "(例: 元ネタ型なのにテーマが元ネタの話ではない)は、型の言い回しを捨ててテーマの事実で書く。"
            "型に合わせるためにテーマに無い主張を作るのは不合格。",
            f"- {line_label}は**15〜30字で断定的に**。ここで答えを言わない(答えを言うと以降を見る理由が消える)。",
            f"- このチャンネルの語り口（上記の声の指紋・語尾・一人称）を{line_label}から守る。"
            "型だけ合っていても語り口が他チャンネル風なら不合格。",
        ]
        if others:
            lines.append(
                f"- ※ このチャンネルの他の型（今回は使わない）: {', '.join(others)}"
            )
        lines.append(
            "- ※ 上の「ショート尺ルール」で1行目の書式がチャンネル固有に指定されている場合はそちらを優先し、"
            "その書式のまま今回の型の役割を満たすこと。"
        )
        return "\n".join(lines) + "\n"

    # ショート台本の目標総文字数。
    # 【2026-08-25 実測により 310 → 200 に差し戻し】
    # 08-19 の 786d314 で「ショートは30〜45秒が最も伸びる／30秒未満はリーチが激減する」
    # という仮説のもと 250 → 310 字に引き上げたが、6日分の実データがこの仮説を否定した。
    #   生成台本の実測: 08-18まで中央 193字/6行 → 08-20以降 中央 372字/8行
    #   維持率中央値  : 08-18 54.3% → 08-19 40.3% → 08-20 29.8% → 08-21 29.3%
    #   平均視聴秒数  : 前後どちらも 15〜16 秒で不変
    #   公開3日後の再生中央値: 全5chで 24〜80% 減（yokai-watch 1696→344 が最大の下げ）
    # 日次集計（n=14日）で 台本字数 × 維持率 の相関は r = -0.849、
    # 回帰式 維持率 = 89.0 - 0.1612 × 字数 は 370字→29.4%（実測29.3〜29.8%）、
    # 180字→60.0%（実測60.2〜72.2%）を再現する。維持率が最も高かったのは 173〜202 字帯。
    # VOICEVOX 1.3x の実効 8.9 字/秒 + 固定オーバーヘッド約6.5秒 で 200字 ≒ 29秒。
    SHORT_TARGET_CHARS = 200

    def _short_rules_block(self, channel, short_target_chars: int,
                           short_end_block: str) -> Optional[str]:
        """ショート構成ルールを channel JSON で差し替える（未設定なら None）。

        既定のショート構成ルールは日常科学系の「研究データ・数字・固有名詞を必ず
        入れる解説ショート」向けにハードコードされている。大喜利・参加型スレのような
        エンタメ系チャンネルでは voice_style をいくら口語にしても、この構成ルールが
        「核となる事実に数字を入れろ」と要求し続けるため、語尾だけ2ch風の解説動画に
        なってしまう。`channel._raw["short_format"]` を宣言したチャンネルだけ、この
        ブロックを丸ごと自前の構成に差し替える:

          "short_format": {
            "line_count": 6,
            "line_chars": "1〜5行目は20〜38字...",
            "total_chars_min": 190, "total_chars_max": 260,
            "structure": ["1行目=...", "2行目=..."],
            "extra_rules": ["..."]
          }

        未設定チャンネル（daily-science / scp-lab など）は None が返り、従来の
        文面がそのまま使われる（挙動不変）。
        """
        try:
            raw = channel._raw or {}
        except AttributeError:
            raw = {}
        sf = raw.get("short_format") or {}
        structure = sf.get("structure") or []
        if not isinstance(sf, dict) or not structure:
            return None

        n = sf.get("line_count", 7)
        line_chars = sf.get("line_chars") or "1行あたり24〜36字、最終行のみ45〜70字を許容"
        lo = sf.get("total_chars_min", short_target_chars - 30)
        hi = sf.get("total_chars_max", short_target_chars + 40)

        lines = [
            "# ショート尺ルール(絶対厳守)",
            f"- **short_scenarioは必ず{n}行**({line_chars})。",
            f"- **総文字数は必ず{lo}〜{hi}字**で**約24〜30秒**に収める"
            "(2026-08-25 実測: 台本を193字→372字に伸ばした結果、維持率が54%→29%に半減し"
            "リーチも全chで24〜80%減少した。平均視聴秒数は15〜16秒で変わらないため、"
            "尺を伸ばすほど維持率が薄まるだけになる。字数上限は絶対に超えないこと)。",
            f"- 構成({n}行固定):",
        ]
        lines += [f"  {s}" for s in structure]
        block = "\n".join(lines) + "\n" + short_end_block
        for r in (sf.get("extra_rules") or []):
            block += f"- {r}\n"
        return block

    def _build_yukkuri_prompt(self, channel, theme: Dict, target_duration: int,
                              short_only: bool = False) -> str:
        """ゆっくり対話スタイルのシナリオ生成プロンプト

        short_only=True（ショート専用チャンネル）のときは full_scenario を要求せず、
        長尺専用のルール（尺・構成・冒頭5秒の本編宣言・次回予告・full の序盤/第二フック）
        を出さない。代わりにショート品質バー（_SHORT_QUALITY_BAR_RULE）を入れる。
        """
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
        # 7行 × 平均36字 + CTA行58字 ≒ 310字 ≒ 35秒（ショート最適尺 30〜45秒）。
        # 行を増やして1行を短くしたのは、テロップの切替を 3〜4 秒ごとに起こして
        # 完視聴率を上げるため（2026 ショート・アルゴリズム対策）。
        short_target_chars = self.SHORT_TARGET_CHARS
        cta_style = channel.content_policy.get("cta_style", "casual")
        tone = channel.content_policy.get("tone", "friendly")
        expr0 = channel.characters[c0].get("expressions", ["normal"])
        expr1 = channel.characters[c1].get("expressions", ["normal"])

        voice_block = self._voice_style_block(channel)
        # 冒頭3秒の型はチャンネル固有の hook_patterns から1本ごとに抽選する。
        # 未設定チャンネルは従来どおり共通4型ルール。
        hook_rule_block = self._hook_variant_block(channel) or _HOOK_3SEC_RULE
        end_cta_block = self._end_cta_block(channel, short_only=short_only)
        title_rule_block = self._title_rule_block(channel)
        try:
            _sf = (channel._raw or {}).get("short_format") or {}
        except AttributeError:
            _sf = {}
        # 既定構成は6行(5本編+CTA)。channel JSON の short_format.line_count で上書き可。
        # 【2026-08-25】8行→6行に差し戻し。行を増やすと台本字数=実尺が伸びるが、
        # 平均視聴秒数(15〜16秒)は変わらないため維持率だけが落ちることが実測で判明した。
        short_line_count = int(_sf.get("line_count") or 6)
        # 掛け合いのショート専用は 本文6行(解説・聞き・解説・解説・聞き・解説)＋CTA の7行。
        dialogue_short = short_only and len(char_names) >= 2
        if dialogue_short:
            short_line_count = SHORT_DIALOGUE_LINE_COUNT
        short_end_block = self._short_end_line_block(channel, short_line_count)
        series_block = _series_hint_block(channel)
        cliffhanger_block = _cliffhanger_block(
            channel, last_content_line=f"{short_line_count - 1}行目のオチ")

        short_rules_block = self._short_rules_block(
            channel, short_target_chars, short_end_block
        ) or f"""# ショート尺ルール(絶対厳守)
- **short_scenarioは必ず6行**(1〜5行目は26〜34字目標30字、6行目のみ40〜55字を許容)。
- **総文字数は必ず{short_target_chars-25}〜{short_target_chars+25}字**(目標{short_target_chars}字)で**約24〜30秒**に収める。**字数上限を超えたら不合格**。2026-08-25の実測で、台本193字→372字に伸ばした回は維持率が54%→29%に半減しリーチも24〜80%落ちた。平均視聴秒数は15〜16秒で変わらないため、行を足すほど維持率が薄まるだけになる。
- **1行=1テロップ**。各行は3〜4秒で読み切れる長さに収め、画面の文字が次々入れ替わるテンポを作る。
- 構成(6行固定):
  1行目=**3秒フック(最重要)**: 後述の「冒頭3秒ルール」で今回指定された型で書く。挨拶・自己紹介・テーマ説明・前置きは1文字でも入れたら不合格。15〜28字で断定的に、まだ答えは言わない。
  2行目=**追い打ちフック**: 1行目の謎をさらに煽るか、相手役が「えっ、どういうこと!?」と食いつくリアクションで視聴者の「気になる」を代弁する。ここでもまだ答えは出さない(出し惜しみして"続きを見る理由"を作る)。
  3行目=**核となる事実＋理由**: **具体的な数字・年号・%・研究データ・固有名詞のいずれか1つ以上を必ず含める**(例:「実は97%の人が…」「1923年に…」「東大の研究で…」)。抽象論・一般論だけはNG。「なぜ」は**1つだけ**添えて全部は明かさない。
  4行目=**自分ゴト化**: 3行目を視聴者の日常の場面に言い換える(「だから朝イチの一杯が…」「今この瞬間もあなたの…」)。ここで「自分にも起きてる」と思わせて中盤の離脱を止める。新しい事実は足さない。
  5行目=**意外な展開→オチ**: 「しかも」「ところが」で角度を変える一撃を置き、そのまま短くスパッと結論まで言い切る。投げっぱなし禁止。
{short_end_block}- 浅い感想・誰でも言える一般論(「すごいね」「びっくりだね」だけ)で行を埋めるのは不合格。1本のショートで最低1つは「初めて知った」と思わせる具体情報を入れること。
"""

        if short_only:
            if dialogue_short:
                short_rules_block = _sanitize_short_rules(short_rules_block, replace_numbered=True)
                short_rules_block = re.sub(
                    r"\*\*short_scenarioは必ず\d+行\*\*[(（][^)）]*[)）]",
                    f"**short_scenarioは必ず{short_line_count}行**(解説役の行は24〜34字、聞き役の行は8〜18字、"
                    f"{short_line_count}行目のCTAは22〜36字)",
                    short_rules_block)
                short_rules_block = re.sub(r"構成[(（]\d+行固定[)）]", f"構成({short_line_count}行固定)",
                                           short_rules_block)
                short_rules_block += "\n" + _SHORT_LINE_ROLES_DIALOGUE
            else:
                short_rules_block = _sanitize_short_rules(short_rules_block) + "\n" + _SHORT_LINE_ROLES
            voice_block = _sanitize_voice_block(voice_block)
            full_json_spec = '"full_scenario":[]'
            full_length_block = ""
            full_structure_block = ""
            early_rules_block = _SHORT_ONLY_DIALOGUE_RULES
            quality_bar_block = _SHORT_QUALITY_BAR_RULE
            task_line = "ゆっくり対話形式のYouTubeショート台本を生成。JSONのみ出力。長尺(full_scenario)は作らない（空配列）。"
        else:
            full_json_spec = (
                f'"full_scenario":[{{"speaker":"{c0}","text":"...","expression":"normal","mood":"calm"}}, '
                f'...{floor_lines}〜{target_lines+4}行]'
            )
            full_length_block = f"""# 尺ルール(絶対厳守・違反は不合格)
- **full_scenarioは必ず{floor_lines}〜{target_lines+4}行**(目標{target_lines}行)。{floor_lines}行未満も{target_lines+5}行以上も不合格。
- **各行は90〜120字**(目標100字、上限120字)。89字以下も121字以上も不合格。
- **総文字数は{target_chars}〜{max_chars}字**(最低{floor_chars}字、上限{max_chars}字)。約{target_duration/60:.1f}分目標。
- 各行に研究データ・具体的数字・例え話・歴史エピソードを必ず盛る。短い相槌のみ(「うん」「そうだね」)禁止。
- VOICEVOX1.3x≒7.8字/秒。{target_chars}字で約{target_duration/60:.1f}分、{max_chars}字で約{max_chars/7.8/60:.1f}分。

"""
            full_structure_block = f"""# 構成(full): 冒頭フック(3行) → 問題提起+本編宣言(3行) → 基本メカニズム(12行) → 詳細&研究データ(12行) → 意外な事実&歴史(10行) → 応用Tips(8行) → まとめ+次回予告+締めCTA(7行) = 計55行(目標{target_lines}行に届くまで各セクションを伸ばす)

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

"""
            early_rules_block = f"""# 序盤セリフ運びルール(冒頭離脱対策・絶対厳守)
- 対象は**序盤=full_scenarioの最初の25%区間**（先頭から全体の1/4の行）。ショートは1〜3行目が該当。ここは視聴者が「見続けるか」を決める最重要ゾーン。
- ❌ NG: 序盤で「感想・まとめ調」の落ち着いた（mood="calm"）セリフを**2連続**させること。「〜なんだね」「〜ということか」「なるほどね」のような噛み砕き・まとめの相槌が続くと、話が停滞して離脱される。
- ✅ 序盤の各セリフは、原則**疑問文（「なぜ〜？」「〜って何？」「じゃあ〜はどうなるの？」）で次の行へ橋渡し**し、視聴者の「続きが気になる」を切らさない。
- ✅ どうしても落ち着いた説明（calm）が続きそうなときは、**calmとcalmの間に必ず1行、驚き役（expression="surprise"）や食いつき役（expression="think"／mood="tense"or"mysterious"）のセリフを挟む**。「えっ、それどういうこと!?」のように視聴者の疑問を代弁して、テンポと引きを維持する。
- この序盤ルールは「冒頭フックルール」と併用する（フック直後の展開が感想の連打にならないよう特に注意）。

{_SECOND_HOOK_RULE_YUKKURI}
{_TERM_PACING_RULE_YUKKURI}
"""
            quality_bar_block = ""
            task_line = "ゆっくり解説動画のシナリオを生成。JSONのみ出力。"

        short_entry_spec = (
            f'{{"speaker":"{c0}","text":"...","expression":"normal","mood":"bright","fact":"F1"}}'
            if dialogue_short else
            f'{{"speaker":"{c0}","text":"...","expression":"normal","mood":"bright"}}'
        )
        return f"""{task_line}

{voice_block}# チャンネル: {channel.name} / {channel.concept} / トーン:{tone} / CTA:{cta_style}
# キャラ:
{char_lines}
# テーマ: {theme["title"]} / 切り口:{theme.get("angle","自由")}
{persona_block}# ポリシー:
{policy_text}

# 出力JSON
{{
 "title":"バズるタイトル",
 "series_name":"このテーマが属するシリーズ名(該当なしなら空文字)",
 "thumb_info":{{"hook_lines":["1行","2行"],"hook_caption":"10文字以内","subtitle":"...","tagline":"..."}},
 "short_scenario":[{short_entry_spec}, ...全{short_line_count}行],
 {full_json_spec}
}}

{title_rule_block}
{_HOOK_CAPTION_RULE}
# サムネ文字(thumb_info.hook_lines)ルール
- hook_lines は**2行**。**各行8文字以内**の短い言い切りにする(長い説明文はサムネで読めない)。
- 助詞で切らず、単語で区切る(例:「触れた瞬間」「全員消えた」)。2行合わせて1つの謎になるように書く。

{full_length_block}{short_rules_block}
{quality_bar_block}{hook_rule_block}
{_TELOP_PACING_RULE_SHORT}
{_LOOP_RULE_SHORT}
{cliffhanger_block}{series_block}{full_structure_block}# 雰囲気タグ(mood)ルール — シーンごとのBGM切替に使用
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

{early_rules_block}{end_cta_block}# その他ルール
- text内は1〜2文で完結。文末「。」直後に改行 `\\n` を入れる(例:"...だ。\\nだから...")。
- **speaker欄は必ず「{c0}」「{c1}」(このチャンネルのキャラ名そのまま)を使う**。他の表記揺れは crash の原因になる。
- text本文内で相手を呼ぶときも上記の「{c0}」「{c1}」と完全一致の表記を使い、別の漢字・別表記に置き換えない。
- expression: {c0}は{expr0}から / {c1}は{expr1}から選ぶ。
- 本チャンネルのトーン（{tone}）と上記「このチャンネルの語り口」を最優先で守る。冒頭で驚き→なぜ→深掘り→意外な結論の構成は流用しつつ、語彙・世界観はチャンネルに合わせる。
- **ショートは「浅い豆知識」NG**: ChatGPTでもすぐ出てくるような薄い情報ではなく、視聴者が思わず人に話したくなる具体性のある「ネタ」を入れること。
"""

    def _build_monologue_prompt(self, channel, theme: Dict, target_duration: int,
                                short_only: bool = False) -> str:
        """モノローグスタイルのシナリオ生成プロンプト

        short_only=True のときは _build_yukkuri_prompt と同じく長尺の指示を外す。
        """
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
        short_target_chars = self.SHORT_TARGET_CHARS
        tone = channel.content_policy.get("tone", "serious_documentary")
        cta_pos = channel.content_policy.get("cta_position", "end_only")

        voice_block = self._voice_style_block(channel)
        hook_rule_block = self._hook_variant_block(channel) or _HOOK_3SEC_RULE
        end_cta_block = self._end_cta_block(channel, short_only=short_only)
        try:
            _sf = (channel._raw or {}).get("short_format") or {}
        except AttributeError:
            _sf = {}
        # 既定構成は6行(5本編+CTA)。channel JSON の short_format.line_count で上書き可。
        # 【2026-08-25】8行→6行に差し戻し。行を増やすと台本字数=実尺が伸びるが、
        # 平均視聴秒数(15〜16秒)は変わらないため維持率だけが落ちることが実測で判明した。
        short_line_count = int(_sf.get("line_count") or 6)
        short_end_block = self._short_end_line_block(channel, short_line_count)
        series_block = _series_hint_block(channel)
        cliffhanger_block = _cliffhanger_block(channel, last_content_line="5行目のオチ")

        # ゆっくり系と同じく channel JSON の short_format / content_policy.short_end_line を
        # 反映させる。未設定チャンネルは従来の文面（下の既定ブロック）がそのまま使われる。
        short_rules_block = self._short_rules_block(
            channel, short_target_chars, short_end_block
        ) or f"""# ショート尺ルール(絶対厳守)
- **short_scenarioは必ず6行**(1〜5行目は26〜34字目標30字、6行目のみ40〜55字を許容)。
- **総文字数は必ず{short_target_chars-25}〜{short_target_chars+25}字**(目標{short_target_chars}字)で**約24〜30秒**に収める。**字数上限を超えたら不合格**。2026-08-25の実測で、台本193字→372字に伸ばした回は維持率が54%→29%に半減しリーチも24〜80%落ちた。平均視聴秒数は15〜16秒で変わらないため、行を足すほど維持率が薄まるだけになる。
- **1行=1テロップ**。各行は3〜4秒で読み切れる長さに収める。
- 構成(6行固定):
  1行目=**3秒フック(最重要)**: 後述の「冒頭3秒ルール」で今回指定された型で書く。前置き・状況説明から入るのは不合格。15〜28字で断定的に。
  2行目=**追い打ちフック**: 謎を一段深くする。ここでも答えを出さない。
  3行目=**核となる事実＋理由**: **具体的な数字・年号・%・研究データ・固有名詞のいずれか1つ以上を必ず含める**(例:「実は97%が…」「1923年の…」「ハーバード大の研究では…」)。抽象論だけはNG。「なぜ」は1つだけ添える。
  4行目=**現場の生々しいディテール**: 記録・証言・数字のうち1つを"その場にいたような"具体で置く(時刻、場所、残された物、担当者の一言)。ここで視聴者を引き戻して中盤の離脱を止める。新事実の追加ではなく解像度を上げる行。
  5行目=**意外な展開→オチ**: 「だが」「ところが」で角度を変える一撃を置き、そのままスパッと結論まで言い切る。投げっぱなし禁止。
{short_end_block}- 一般論・感想のみで埋めるのは不合格。1本につき最低1つは「へぇ」と思わせる具体情報を入れること。
"""

        if short_only:
            short_rules_block = _sanitize_short_rules(short_rules_block) + "\n" + _SHORT_LINE_ROLES
            voice_block = _sanitize_voice_block(voice_block)
            full_json_spec = '"full_scenario":[]'
            full_length_block = ""
            full_structure_block = ""
            early_rules_block = _SHORT_ONLY_NARRATION_RULES
            quality_bar_block = _SHORT_QUALITY_BAR_RULE
            task_line = "ドキュメンタリー風ナレーションのYouTubeショート台本を生成。JSONのみ出力。長尺(full_scenario)は作らない（空配列）。"
        else:
            full_json_spec = (
                '"full_scenario":[\n'
                '   {"chapter_title":"第1章: 導入","mood":"mysterious"},\n'
                '   {"text":"...","mood":"mysterious"},\n'
                f'   ...テキスト行を{floor_lines}〜{target_lines+4}行(章は3〜5章)\n'
                ' ]'
            )
            full_length_block = f"""# 尺ルール(絶対厳守・違反は不合格)
- **テキストは必ず{floor_lines}〜{target_lines+4}行**(目標{target_lines}行)。
- **各行は90〜120字**(目標100字、上限120字)。89字以下も121字以上も不合格。
- **総文字数は{target_chars}〜{max_chars}字**(約{target_duration/60:.1f}分目標、{max_chars}字で約{max_chars/7.8/60:.1f}分)。
- 各行に研究データ・数字・事例を必ず盛る。

"""
            early_rules_block = f"""# 序盤セリフ運びルール(冒頭離脱対策・絶対厳守)
- 対象は**序盤=full_scenarioの最初の25%区間**（本文行の先頭から全体の1/4）。ショートは1〜3行目が該当。ここは視聴者が「見続けるか」を決める最重要ゾーン。
- ❌ NG: 序盤で「感想・まとめ調」の落ち着いた（mood="calm"）ナレーションを**2連続**させること。淡々とした総括・言い換えが続くと話が停滞し離脱される。
- ✅ 序盤の各行は、原則**疑問・問いかけ（「なぜ〜のか」「〜とは何なのか」「では〜はどうなるのか」）で次の行へ橋渡し**し、視聴者の「続きが気になる」を切らさない。
- ✅ どうしても落ち着いた説明（calm）が続きそうなときは、**calmとcalmの間に必ず1行、驚き・緊張の一撃（mood="tense"）か謎の提示（mood="mysterious"）を挟む**。「だが、ここで奇妙なことが起きる」のように緊張を差し込み、テンポと引きを維持する。
- この序盤ルールは「冒頭フックルール」と併用する（フック直後の展開が総括の連打にならないよう特に注意）。

{_SECOND_HOOK_RULE_MONOLOGUE}
{_TERM_PACING_RULE_MONOLOGUE}
"""
            full_structure_block = f"""# 冒頭フックルール(超重要・冒頭5秒離脱対策・絶対厳守)
- ❌ NG: 「これからお話するのは〜」「みなさんは〜をご存知だろうか」のような長い導入・前置きから入る構成は禁止。視聴者は最初の5秒で離脱を判断する。
- ❌ NG: 自己紹介・チャンネル説明・章タイトルの読み上げから始めない。
- ✅ 第1章の最初の本文行(0〜3秒): 視聴者の共感を呼ぶ問いかけ + 結論のヒントを即提示。例:「雨の日、なぜか気分が沈むことはないだろうか。実はそれ、ある『物質』が原因なのだ」。
- ✅ 第1章2〜3行目(3〜10秒): 「今回はその正体を暴く」「この映像で、その謎を完全に解き明かす」のような本編宣言で、すぐ本題へ突入する。
- 1行目に「あなた」「〜したことがあるはずだ」のような共感を呼ぶ語りを必ず入れる。

# エンディング+次回予告ルール(登録率改善・絶対厳守)
- 最終章の締めCTA(高評価・登録)の直前または直後に「次回は〇〇を解説する」のような次回予告を必ず1〜2行入れる。
- {next_video_hint}
- 「次回も気になる」と思わせて登録への心理的ハードルを下げるのが目的。次回予告を省略した動画は不合格。

"""
            quality_bar_block = ""
            task_line = "ドキュメンタリー風ナレーション動画のシナリオを生成。JSONのみ出力。"

        return f"""{task_line}

{voice_block}# チャンネル: {channel.name} / {channel.concept} / トーン:{tone}
# ナレーター: {narrator.get("role", "冷静な男性ナレーター")}
# テーマ: {theme["title"]} / 切り口:{theme.get("angle","自由")}
{persona_block}# ポリシー:
{policy_text}

# 出力JSON
{{
 "title":"バズるタイトル",
 "series_name":"このテーマが属するシリーズ名(該当なしなら空文字)",
 "thumb_info":{{"hook_lines":["1行","2行"],"hook_caption":"10文字以内","subtitle":"...","tagline":"..."}},
 "short_scenario":[{{"text":"...","chapter_title":null,"mood":"tense"}}, ...全{short_line_count}行],
 {full_json_spec}
}}

# タイトルルール(超重要・CTR改善のため絶対厳守)
- ❌ NG: 「【ゆっくり解説】〇〇」「〇〇の謎、解けます！」など、定型プレフィックスや結論を含むタイトルは禁止。CTRが大幅に下がる。
- ❌ NG: 結論・答えをタイトルにバラす。
- ✅ OK: 「なぜアスファルトだけ？水たまりが『あそこ』にしかできない本当の理由」のように、答えではなく「なぜ？」という謎・違和感だけを置く疑問型・意外性重視。
- 「【〇〇解説】」のような定型プレフィックスは絶対に付けない。
- 「本当の理由」「実は」「あそこ」「なぜか」「だけ」「〇〇すぎる」など意外性を匂わせるワードを必ず1つ以上入れる。
- 視聴者が「気になる、答えを知りたい」と感じる謎の提示で止める。結論はサムネ・本編で初めて出す。
- タイトルは「説明」ではなく「衝動」を作る。読んだ瞬間に指が止まる語（実は/なぜ/だけ/本当は/やめて）を必ず入れる。

{_HOOK_CAPTION_RULE}
# サムネ文字(thumb_info.hook_lines)ルール
- hook_lines は**2行**。**各行8文字以内**の短い言い切りにする(長い説明文はサムネで読めない)。

{full_length_block}{short_rules_block}
{quality_bar_block}{hook_rule_block}
{_TELOP_PACING_RULE_SHORT}
{_LOOP_RULE_SHORT}
{cliffhanger_block}{series_block}# 雰囲気タグ(mood)ルール — シーンごとのBGM切替に使用
- 各行(章タイトル含む)に必ず "mood" を付与する。値は次の6種類のいずれか:
  - "calm"(穏やか) / "bright"(明るい) / "tense"(緊張・衝撃)
  - "emotional"(感動) / "funny"(コミカル) / "mysterious"(ミステリアス)
- 同じmoodを2〜10行ほど連続させて「シーン」を作る(毎行切替えない)。1章 = 1〜2シーン目安。
- 章タイトル行のmoodは、その章の主軸となる雰囲気と一致させる。

{early_rules_block}{end_cta_block}

{full_structure_block}# その他ルール
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
        # このスタイルでは「1個目のファクトのナレーション」が冒頭3秒に当たる。
        hook_rule_block = self._hook_variant_block(
            channel, line_label="1個目のファクトの text（ナレーション）"
        )
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

        # このスタイルはショート専用（full_scenario は常に空）。ところが呼び出し側の
        # autopilot は長尺用の autopilot.duration_minutes(=12) から target_duration=720秒
        # を渡してくるため、プロンプトに「合計約720秒」と書かれ、実測 76〜97秒まで
        # 膨らんでいた（company-facts の投稿済み9本すべてが1分超）。
        # ショート最適尺（30〜45秒）に丸めてからファクト数と文字数を逆算する。
        target_duration = _clamp_short_duration(channel, target_duration)

        # 1画面 ≒ 5秒（ナレーション 25〜40字 ≒ 3〜4.5秒 + 間）、CTA に約6秒。
        # 旧式は fact_count = target_duration/6 で最大9画面まで許し、かつ 1画面あたりの
        # ナレーションを 40〜70字（5〜8秒）としていたため、45秒指定でも実測 76〜97秒に
        # 膨らんでいた（company-facts の投稿済み9本すべてが 1分超）。
        # 画面数と1画面の文字数の両方を尺から逆算して整合させる。
        fact_seconds = max(20, target_duration - _FACTS_CTA_SECONDS)
        fact_count = max(5, min(8, round(fact_seconds / _FACTS_SECONDS_PER_SCREEN)))
        series_block = _series_hint_block(channel)

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
 "series_name":"このテーマが属するシリーズ名(該当なしなら空文字)",
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
- text: 読み上げナレーション。**25〜40文字（厳守。41文字以上は不合格）**。fact_main の数字を必ず声でも言う。
  画面の文字をそのまま読むだけにせず、驚き・理由・比較を足して価値を出す。
- bg_query: その画面の背景写真を探す日本語検索クエリ。**必ず企業名で始める**
  （例:「ニトリ 店舗 外観」「ニトリ 売り場」）。画面ごとに違うクエリにして写真を切り替える。
- duration: その画面の最低表示秒数（**3〜5**）。実際の尺はナレーション音声に合わせて自動で伸びる。
- mood: BGM切替タグ。"bright"(明るい) / "tense"(衝撃) / "calm"(落ち着き) のいずれか。

# 構成（{fact_count}ファクト + CTA、合計{target_duration}秒 ※30〜45秒が最も伸びる。30秒未満も45秒超も不合格）
# ※ 全画面の text を合計して**{int(fact_count * 40)}文字を超えたら不合格**。超えたら各行を削って書き直す。
#    ファクト数を増やして尺を伸ばすのは禁止（画面数は{fact_count}個で固定）。
1. **1個目=最強フック**: 企業名 + 最もインパクトのある数字を即出し（例:「ニトリ 平均年収850万円」）。
   冒頭3秒で企業名と数字が画面に出ていない構成は不合格。
   さらに1個目の text（ナレーション）は**「問い」か「驚き」で始める**
   （例:「この会社の平均年収、いくらだと思う?」「実はこの数字、業界1位なんだ」）。
   淡々と数字を読み上げるだけの入りは不合格。
2. 2〜{fact_count-1}個目: 年収→ボーナス→有給/残業→離職率→福利厚生 の順でテンポよく数字を連打する。
   同じ指標を2回出さない。毎回ちがう切り口の数字にする。
   **1画面は3〜5秒**。ここが長いと画面が固まって離脱するので、text は短く言い切る。
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
- タイトルは「説明」ではなく「衝動」を作る。読んだ瞬間に指が止まる語（実は/ヤバい/本当は/知らない）を必ず1つ入れる。
- 例:「ニトリの年収がヤバい 平均850万円の実態」「任天堂の離職率3%、辞めない理由」

{hook_rule_block}
# 冒頭テロップ(1個目の fact_main)ルール
- このスタイルでは**1個目の fact_main がそのまま冒頭0〜3秒の画面中央テロップ**になる。
  **10文字前後**まで削って「企業名＋数字」だけを残す(例:「ニトリ 年収850万」)。
  修飾語・説明・句読点を入れると読み切れず、スクロールを止められない。

# サムネ文字(thumb_info.hook_lines)ルール
- hook_lines は**2行**、**各行8文字以内**（例:「平均850万」「辞めない会社」）。長い説明文は読めないので不可。

{series_block}"""

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
        short_only: Optional[bool] = None,
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
            short_only: True ならショート台本だけを作る（full_scenario は空）。
                None（既定）は `_short_only_mode()` が channel JSON の gen_type から
                判定する。長尺を作りたい手動実行は False を渡すか、
                環境変数 SCENARIO_FORCE_FULL=1 を付ける。

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
        short_only = (
            channel.style != "facts_overlay" and _short_only_mode(channel, short_only)
        )
        fact_sheet: Optional[Dict[str, Any]] = None
        if short_only:
            print("  ✂️ ショート専用チャンネル: full_scenario（長尺台本）は生成しない")
            # 台本の前に事実を洗い出し、言い切れない題材なら切り口/題材を差し替える。
            theme, fact_sheet = self._assertable_short_theme(
                channel, theme, avoid_duplicate_theme=avoid_duplicate_theme)
        if channel.style == "facts_overlay":
            prompt = self._build_facts_overlay_prompt(channel, theme, duration)
        elif channel.style == "monologue":
            prompt = self._build_monologue_prompt(channel, theme, duration, short_only=short_only)
        else:
            prompt = self._build_yukkuri_prompt(channel, theme, duration, short_only=short_only)
        _sheet_txt = _fact_sheet_text(fact_sheet)
        if _sheet_txt:
            prompt += (
                "\n\n# 使ってよい事実(ファクトシート・台本の事実はここの『確かな事実』からだけ取る)\n"
                "- 『確証なし』の話は台本に入れない(ぼかして入れるのも不可)。"
                "数字・名前・出典は書いてあるとおりに使う。\n"
                f"{_sheet_txt}\n"
            )

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

        # Phase S: 季節ブースト — 時期に合ったテーマ角度をプロンプトに追加
        try:
            from pipeline.seasonal_boost import get_seasonal_prompt_addendum
            _seasonal_add = get_seasonal_prompt_addendum(channel.id)
            if _seasonal_add:
                prompt = prompt + "\n\n" + _seasonal_add
                print(f"  🌸 Applying seasonal boost for {channel.id}")
        except Exception as e:
            print(f"  ⚠️ seasonal_boost failed: {e}")

        # Phase T: トレンドテーマの場合、タイトルと冒頭に旬のワードを織り込む指示を注入。
        # トレンドに乗ったコンテンツは初動 1〜3 時間のリーチが通常の 2〜3 倍になる（競合分析）。
        if theme.get("is_trending") and theme.get("trend_match"):
            trend_kw = theme["trend_match"]
            trend_addendum = (
                f"\n\n# トレンド最適化指示（このテーマはトレンドに乗っている）\n"
                f"- 現在「{trend_kw}」がトレンド入りしている。このキーワードに関連する切り口で書く。\n"
                f"- **タイトルに「{trend_kw}」またはその関連ワードを自然に含める**（検索流入の最大化）。\n"
                f"- 冒頭1行目で「今話題の」「今ちょうど」「最近〇〇で話題になってる」のような\n"
                f"  旬のシグナルを1つ入れる。ただし不自然に詰め込まず、チャンネルのトーンを守る。\n"
                f"- サムネの hook_lines にもトレンドワードを反映する（検索＋おすすめ表示の両方に効く）。\n"
                f"- トレンドは24〜48時間で冷めるため、鮮度の高い切り口を最優先する。\n"
            )
            prompt = prompt + trend_addendum
            print(f"  🔥 Applying trend optimization: '{trend_kw}' (trend_score={theme.get('trend_score')})")

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
        if channel.style == "facts_overlay" or short_only:
            # ショート専用（facts_overlay か gen_type=short）。full_scenario は空で
            # 正しいので長さ検証をかけない（かけると毎回「full不足」で無駄なリトライと
            # セクション拡張が走る）。
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
        elif short_only:
            system_msg = (
                "YouTubeショート(縦型・30秒前後)の台本作家。JSONのみ出力。"
                "short_scenario だけを書き、full_scenario は空配列。"
                "1行目で題材の名前と具体的な事実を出し、各行に新しい具体(数字・固有名詞・描写)を1つ入れ、"
                "伏せた謎は台本内で中身ごと回収する。事実は公式・原典で確認できるものだけ。"
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

        # ショート専用: 生成直後に1回だけ自己レビュー（事実・回収・具体性）をかける。
        if short_only and scenario_data.get("short_scenario"):
            if fact_sheet:
                scenario_data["short_fact_sheet"] = fact_sheet
            try:
                self._short_self_review(channel, theme, scenario_data)
            except Exception as e:
                print(f"  ⚠️ short self-review failed: {e}")
            try:
                self._short_focus_rewrite(channel, theme, scenario_data)
            except Exception as e:
                print(f"  ⚠️ short focus rewrite failed: {e}")
            try:
                self._short_lint_repair(channel, theme, scenario_data)
            except Exception as e:
                print(f"  ⚠️ short lint failed: {e}")
            try:
                scenario_data["short_postfix"] = self._short_postfix(channel, scenario_data)
            except Exception as e:
                print(f"  ⚠️ short postfix failed: {e}")

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

        # Phase V: シナリオ構造バリデーション（フック・CTA・禁止語の検証）
        if short_lines_data:
            try:
                from pipeline.scenario_validator import guard as _scenario_guard
                _short_texts = [
                    (e.get("text", "") if isinstance(e, dict) else str(e))
                    for e in short_lines_data
                ]
                _ch_raw = _validator_channel_dict(channel, short_only, len(_short_texts))
                _scenario_guard(
                    _short_texts,
                    channel_id=channel.id,
                    channel_dict=_ch_raw,
                    strict=False,
                )
            except Exception as e:
                print(f"  ⚠️ scenario_validator failed: {e}")

        # Phase R6: Round 6 生成後最適化パイプライン
        # (Hook A/B, Swipe-Stop, CTA Rotation, Cross-Channel Bridge,
        #  Mute-Safe Check, Viral Score Gate)
        if short_lines_data:
            try:
                from pipeline.round6_enhancer import enhance as _r6_enhance
                _ch_raw_r6 = {}
                try:
                    _ch_raw_r6 = channel._raw or {}
                except AttributeError:
                    pass
                _r6_result = _r6_enhance(
                    short_lines_data,
                    title=scenario_data.get("title", theme.get("title", "")),
                    channel_id=channel.id,
                    channel_dict=_ch_raw_r6,
                    series_name=(scenario_data.get("series_name") or ""),
                    api_key=self.api_key,
                )
                scenario_data["round6"] = _r6_result
            except Exception as e:
                print(f"  ⚠️ Round6 enhancer failed: {e}")

        # Phase R7: Round 7 完走率 & リプレイ最大化パイプライン
        # (Completion Rate Optimizer, Replay Loop Seeder, Power Word Amplifier,
        #  Retention Feedback Loop, Originality Guard, Title Emoji Injector)
        if short_lines_data:
            try:
                from pipeline.round7_enhancer import enhance as _r7_enhance
                _ch_raw_r7 = {}
                try:
                    _ch_raw_r7 = channel._raw or {}
                except AttributeError:
                    pass
                _r7_result = _r7_enhance(
                    short_lines_data,
                    title=scenario_data.get("title", theme.get("title", "")),
                    channel_id=channel.id,
                    channel_dict=_ch_raw_r7,
                )
                scenario_data["round7"] = _r7_result
                # Round 7 の絵文字注入タイトルを反映
                if _r7_result.get("enhanced_title"):
                    scenario_data["title"] = _r7_result["enhanced_title"]
            except Exception as e:
                print(f"  ⚠️ Round7 enhancer failed: {e}")

        # Phase R8: Round 8 エンゲージメント & 登録者最大化パイプライン
        # (Curiosity Gap Enforcer, Comment Bait Injector,
        #  Emotional Polarity Alternator, Pattern Interrupt Injector,
        #  Subscribe Trigger Optimizer, Contrast Amplifier)
        if short_lines_data:
            try:
                from pipeline.round8_enhancer import enhance as _r8_enhance
                _ch_raw_r8 = {}
                try:
                    _ch_raw_r8 = channel._raw or {}
                except AttributeError:
                    pass
                _r8_result = _r8_enhance(
                    short_lines_data,
                    title=scenario_data.get("title", theme.get("title", "")),
                    channel_id=channel.id,
                    channel_dict=_ch_raw_r8,
                )
                scenario_data["round8"] = _r8_result
            except Exception as e:
                print(f"  ⚠️ Round8 enhancer failed: {e}")

        # Phase L: 最終尺強制（2026-08-30 追加 / 全エンハンサーの「後」に置くこと）
        # Round6/7/8 の injector は short_scenario を in-place で加筆するため、
        # 生成直後の字数チェックを通過した台本でも、ここに来る時点では 24〜103字
        # 積み増されている（08-26〜29 実測: 全5ch 中央値 238〜304字 / 上限 210〜225字）。
        # 実測回帰 維持率=89.0-0.1612×字数 では 300字→40.6%、200字→56.8%。
        # 08-19 以降の維持率半減（54.3%→29.8%）はこの超過が主因なので、ここで
        # 決定論的に帯へ戻す。再生成ではなくトリムにしているのは、無人実行で
        # 生成本数がゼロになるリスクを避けるため。
        if short_lines_data:
            try:
                from pipeline import shorts_length_guard as _slg_final
                scenario_data["shorts_length_enforced"] = _slg_final.enforce_band(
                    channel.id, short_lines_data,
                )
            except Exception as e:
                print(f"  ⚠️ ShortsLengthGuard enforce_band failed: {e}")

        # Phase V2: 最終状態の再検証と修復（2026-10-03）
        # Phase V の検証は R6〜R8・尺強制の「前」に走る助言で、エンハンサーが
        # 加筆・トリムした最終状態は誰も検証していなかった（検証failの台本が
        # そのまま放送されていた）。ここで最終 short_scenario を再検証し、
        #   - CTA 欠落 → cta_enforcer.enforce_final_cta で決定的に修復
        #   - 冒頭フック不合格 → 1回だけ GPT で先頭行をフック型に書き直し
        # それでも不合格なら final_validation に記録して PDCA で追えるようにする
        # （無人運転で生成ゼロを避けるため、公開自体は止めない）。
        if short_lines_data:
            try:
                from pipeline.scenario_validator import guard as _guard_final
                _ch_raw_v2 = _validator_channel_dict(channel, short_only, len(short_lines_data))

                def _texts():
                    return [(e.get("text", "") if isinstance(e, dict) else str(e))
                            for e in short_lines_data]

                _vres = _guard_final(_texts(), channel_id=channel.id,
                                     channel_dict=_ch_raw_v2, strict=False)
                _issues = " / ".join(_vres.get("issues") or [])
                if not _vres["passed"] and "CTA" in _issues:
                    from pipeline import cta_enforcer as _cta_fix
                    _fix = _cta_fix.enforce_final_cta(channel.id, short_lines_data,
                                                      channel_dict=_ch_raw_v2)
                    if _fix.get("applied"):
                        print(f"  🔧 最終CTA修復: {_fix.get('after', '')[:40]}")
                    _vres = _guard_final(_texts(), channel_id=channel.id,
                                         channel_dict=_ch_raw_v2, strict=False)
                    _issues = " / ".join(_vres.get("issues") or [])
                # ショート専用は 1行目を _short_lint_repair（題材名・問いで止める・『本当？』禁止・
                # 原典照合済みの事実）で検査済み。ここの GPT 書き直しは validator の正規表現しか
                # 見ないため、第2周では「ジガルデ、HP半分で完全体になるんだよ！」を
                # 「ジガルデはHP半分で完全体になるって本当？」（自分のフックを疑う形）に変えていた。
                if short_only and (not _vres["passed"]) and "冒頭フック" in _issues:
                    print("  ⏭️ 冒頭フック修復はショート専用では行わない（short lint で検査済み）")
                elif (not _vres["passed"]) and "冒頭フック" in _issues \
                        and short_lines_data and isinstance(short_lines_data[0], dict):
                    _first = (short_lines_data[0].get("text") or "").strip()
                    if _first:
                        try:
                            _hook_raw = self._call_gpt(
                                [{"role": "system",
                                  "content": "あなたはYouTubeショートの冒頭フック職人。出力は書き直した1行のみ。"},
                                 {"role": "user",
                                  "content": (
                                      "次のショート動画の1行目を、意味を保ったまま視聴者が止まる"
                                      "フック型（疑問形・意外な断定・数字の提示のいずれか）に書き直して。"
                                      "題材の固有名と、元の行にある具体(数字・場所・物・行為)は必ず残す。"
                                      "「〜の意外な理由とは？」のような中身のない問いにしない。"
                                      "元の行の主張の向きを変えない(肯定を否定にしない)。"
                                      "40字以内、絵文字・ハッシュタグ禁止、出力はその1行だけ。\n"
                                      f"タイトル: {scenario_data.get('title', '')}\n"
                                      f"現在の1行目: {_first}")}],
                                temperature=0.7, max_tokens=120,
                                model=GPT_MODEL_LIGHT, max_retries=1,
                            ).strip().split("\n")[0].strip()
                        except Exception as _he:
                            _hook_raw = ""
                            print(f"  ⚠️ フック書き直し失敗: {_he}")
                        _hook_raw = _clean_llm_line(_hook_raw)
                        if re.search(r"(とは[？?]?$|理由とは|正体とは)", _hook_raw or ""):
                            print(f"  ⚠️ フック書き直しを不採用（中身のない問い）: {_hook_raw[:40]}")
                            _hook_raw = ""
                        if _hook_raw and 12 <= len(_hook_raw) <= 60:
                            short_lines_data[0]["text"] = _hook_raw
                            print(f"  🔧 冒頭フック修復: {_first[:25]} → {_hook_raw[:40]}")
                            _vres = _guard_final(_texts(), channel_id=channel.id,
                                                 channel_dict=_ch_raw_v2, strict=False)
                scenario_data["final_validation"] = {
                    "passed": bool(_vres.get("passed")),
                    "score": _vres.get("score"),
                    "issues": _vres.get("issues") or [],
                }
                if short_only:
                    # エンハンサー・尺強制・CTA修復の後の最終状態でもう一度検査して記録する
                    _final_lint = _lint_short(
                        short_lines_data, sheet=scenario_data.get("short_fact_sheet"),
                        theme=theme, **self._short_lint_ctx(channel))
                    scenario_data["final_validation"]["short_lint"] = [v["msg"] for v in _final_lint]
            except Exception as e:
                print(f"  ⚠️ final validation failed: {e}")

        # Phase N: シリーズ通し番号をタイトルに付与
        _result_title = scenario_data.get("title", theme["title"])
        try:
            from pipeline.series_counter import apply_series_number
            _ch_raw_n = {}
            try:
                _ch_raw_n = channel._raw or {}
            except AttributeError:
                pass
            _result_title = apply_series_number(
                _result_title,
                channel.id,
                channel_dict=_ch_raw_n,
                is_short=bool(scenario_data.get("short_scenario")),
            )
        except Exception as e:
            print(f"  ⚠️ series_counter failed: {e}")

        result = {
            "title": _result_title,
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
            "round6": scenario_data.get("round6", {}),
            "round7": scenario_data.get("round7", {}),
            "round8": scenario_data.get("round8", {}),
            "short_self_review": scenario_data.get("short_self_review"),
            "short_fact_sheet": scenario_data.get("short_fact_sheet"),
            "short_postfix": scenario_data.get("short_postfix"),
            "short_lint": scenario_data.get("short_lint"),
            "short_focus_rewrite": scenario_data.get("short_focus_rewrite"),
            "final_validation": scenario_data.get("final_validation"),
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

        # ── タイトルのゲート群 ──
        # 各ゲートは自分の直後の値しか見ない。ゲート自体が落ちたら print だけで
        # 先へ進む設計だが、「落ちた」事実を result に残さないと PDCA で追えない
        # （09-11 の genre_blacklist 無効化はこれで1日気づかれなかった）。
        # 各ゲートの例外は _run_gate が result["gate_failures"] に積む。
        result["gate_failures"] = []

        # 最終タイトルの重複ゲート。AB テストがタイトルを差し替えた後に置くことで、
        # 「どの経路で決まったタイトルであれ」既存動画とほぼ同一なら作り直す。
        if avoid_duplicate_theme:
            self._run_gate(result, "title_duplicate",
                           self._reject_duplicate_title, channel, theme, result, scenario_data)

        # CTR 品質ゲート。重複ゲートの後に置く（重複解消で入れ替わったタイトルも採点する）。
        self._run_gate(result, "title_quality",
                       self._enforce_title_quality, channel, theme, result, scenario_data)

        # 機械ゲート（title_rules.hard_constraints）。CTR ゲートの後に置くのは、
        # CTR 再生成が規約違反タイトルを持ち込みうるため。順序を入れ替えないこと。
        self._run_gate(result, "title_constraints",
                       self._enforce_title_constraints, channel, theme, result, scenario_data)

        # 実在人物名・第三者IP のゲート。規約ゲートの後（言い換えで名前が入りうる）。
        self._run_gate(result, "entity_gate",
                       self._enforce_entity_gate, channel, theme, result, scenario_data)

        # ch 横断の同語ゲート。最終タイトルが確定した後に1回だけ見る。
        self._run_gate(result, "cross_channel_keywords",
                       self._enforce_cross_channel_keywords, channel, theme, result, scenario_data)

        # 数値の整合ゲート（→ fact_ledger）。台本本文が確定した後に見る。
        self._run_gate(result, "fact_consistency",
                       self._enforce_fact_consistency, channel, result)

        # サムネ文字の長さゲート。AB テストが hook_lines を差し替えた後に置く。
        _normalize_thumb_info(result.get("thumb_info"))

        # 【2026-09-12】タイトル衛生の**最終出口**。上のどの段が何を持ち込んでも、
        # ここを通らずに result["title"] が外へ出ることはない（→ pipeline/title_gate）。
        # 括弧の破片・二重マーカー・制御文字・長さ超過を機械的に落とす。掃除して
        # 使えなければテーマ題名に戻し、それも駄目なら例外（壊れたまま公開しない）。
        self._finalize_title(channel, theme, result)

        # 【2026-09-14】ゲートが「未解消（ok: false）」で終わった動画は公開しない。
        # 従来は記録だけ残して公開していたため、規約違反タイトル・実在人物名・
        # 数値矛盾がそのまま出ていた。ここで publish_blocked を立て、autopilot は
        # ジョブを投入せず、on_generation_complete は公開をスキップする。
        result["publish_blocked"] = self._publish_block_reasons(result)
        if result["publish_blocked"]:
            print("  ⛔ publish_blocked: " + " / ".join(result["publish_blocked"]))

        return result

    @staticmethod
    def _publish_block_reasons(result: Dict[str, Any]) -> List[str]:
        """公開を止めるべき理由の一覧（空なら公開してよい）。

        止めるもの: 規約違反が未解消（title_constraints.ok=False）、実在人物名/第三者IP
        （entity_gate.ok=False）、同じ会社の同じ指標が食い違う（fact_consistency の
        conflicts）。横断語（cross_channel_keywords）は当日の並びの問題なので止めない。
        """
        reasons: List[str] = []
        tc = result.get("title_constraints") or {}
        if tc and tc.get("ok") is False:
            # 実効文字数の下限（min_effective_chars）だけは止めない。これは CTR の
            # 目安であって規約・権利の問題ではなく、機械修復もできない（水増しになる）。
            # 数字・禁止語・接頭辞・必須語・上限文字数の未解消は止める。
            try:
                from pipeline import title_constraints as _tc
                soft = set(_tc.UNREPAIRABLE_RULES)
            except Exception:
                soft = {"min_effective_chars"}
            v = [x for x in (tc.get("violations") or [])
                 if isinstance(x, dict) and x.get("rule") not in soft]
            if v:
                reasons.append("タイトル規約違反が未解消: " + " / ".join(
                    f"{x.get('label')}({x.get('detail')})" for x in v))
        eg = result.get("entity_gate") or {}
        if eg and eg.get("ok") is False:
            reasons.append(f"タイトルに実在人物/第三者IP: {eg.get('reason') or eg.get('matched')}")
        fc = result.get("fact_consistency") or {}
        if fc and fc.get("ok") is False and fc.get("conflicts"):
            c = fc["conflicts"][0]
            reasons.append(f"数値の矛盾: {c.get('entity')} の {c.get('metric')} "
                           f"{c.get('old_value')}→{c.get('new_value')}{c.get('unit', '')}")
        return reasons

    def _run_gate(self, result: Dict[str, Any], name: str, fn, *args) -> None:
        """ゲート関数を1つ実行する。落ちても生成は止めないが、必ず記録する。"""
        try:
            fn(*args)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            print(f"  ⚠️ gate '{name}' failed (recorded, continuing): {msg}")
            result.setdefault("gate_failures", []).append({"gate": name, "error": msg})

    def _finalize_title(self, channel, theme: Dict, result: Dict[str, Any]) -> None:
        from pipeline import title_gate as _tg
        try:
            raw = channel._raw or {}
        except AttributeError:
            raw = {}
        before = result.get("title")
        final = _tg.finalize(before, raw, fallback=(theme or {}).get("title"))
        problems = _tg.validate(before, max_chars=_tg.YOUTUBE_TITLE_MAX)
        if final != (before or "").strip() or problems:
            print(f"  🧼 title gate: 「{before}」→「{final}」"
                  + (f"（{' / '.join(problems)}）" if problems else ""))
            result.setdefault("original_title", before)
            result["title"] = final
            result["title_gate"] = {"cleaned": True, "before": before, "problems": problems}
        else:
            result["title_gate"] = {"cleaned": False}

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
            ("基本メカニズム解説", 9, "テーマの基本原理を分かりやすく説明。専門用語は噛み砕く。**このセクションは動画全体の20%地点にあたる離脱の谷なので、冒頭2行以内に必ず『第二フック』を1行入れる**(驚き=『実は〇〇でも同じことが起きてる』／反転=『でもこれ、半分は間違いなんだ』／予告=『この話、最後にとんでもないオチがある』のいずれか)。説明だけで始めない。", "calm"),
            ("具体的な仕組み・研究データ", 10, "研究データ・具体的な数字・パーセンテージ・代表的な実験", "calm"),
            ("背景・歴史的経緯", 9, "発見・研究の経緯、歴史的エピソードや人物", "mysterious"),
            ("意外な事実・補足知識", 10, "視聴者が驚く意外な情報や雑学・トリビア", "tense"),
            ("日常への応用・実践Tips", 9, "視聴者が今日から使える実践的なTips・応用例", "bright"),
            ("まとめ + 次回予告 + 締めCTA", 7, "今日の内容を簡潔にまとめ → **『次回は〇〇を解説するよ』のような次回予告を必ず1〜2行入れる(必ず本チャンネル『" + channel.name + "』のジャンル・世界観に閉じたテーマから提案。他ジャンルへの飛び火禁止)** → 高評価/登録CTA。次回予告は登録率改善のため絶対省略禁止。", "emotional"),
        ]
        # 合計目標: 6+9+10+9+10+9+7 = 60行

        c0 = char_names[0]
        c1 = char_names[1] if len(char_names) > 1 else c0
        end_cta_block = self._end_cta_block(channel)
        all_lines = []
        for sec_idx, (sec_title, sec_lines, sec_guide, sec_mood) in enumerate(sections):
            print(f"    📝 Section {sec_idx+1}/{len(sections)}: {sec_title} ({sec_lines}行, mood={sec_mood})")
            # 登録CTA は最終セクション（まとめ+次回予告+締めCTA）だけに効かせる
            sec_end_cta = (
                "# 登録導線(必須): このセクションの**最終行は必ずチャンネル登録CTA**で終える"
                "（まとめ → 次回予告 → 登録CTA の順）。余韻やTipsで終わって登録に触れないのは不合格。\n"
                if (end_cta_block and sec_idx == len(sections) - 1) else ""
            )
            section_prompt = f"""ゆっくり解説1セクションのセリフをJSON配列のみで出力。

# チャンネル: {channel.name} / {channel.concept}
# キャラ: {c0} と {c1} を交互
# テーマ: {theme["title"]} / 切り口:{theme.get("angle","")}
# セクション: {sec_title}
# 内容: {sec_guide}
# 雰囲気(mood): "{sec_mood}" — このセクション全行で必ず "mood":"{sec_mood}" を付与する。
# 行数: 厳密に{sec_lines}行(過不足不可)
# 各行: 90〜120字(目標100字、上限120字)。89字以下も121字以上も不合格。研究データ/数字/例え/歴史を盛る。短い相槌のみ禁止。
# 離脱対策(全セクション共通・厳守): {_SECOND_HOOK_RULE_SECTION}
# 序盤離脱対策(全セクション共通・厳守): {_TERM_PACING_RULE_SECTION}
{sec_end_cta}
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
        # シリーズ連作（登録動機になる「次も見たい」を作る）。
        lineup = cfg.get("series_lineup") or []
        if lineup:
            parts.append(
                "- 本チャンネルは**シリーズ連作**で運用している。"
                "提案する各テーマは必ず次のいずれかのシリーズに属するものにし、"
                "1バッチの中で同じシリーズに偏らせない:")
            parts.append("\n".join(f"  - 「{s}」" for s in lineup))
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
        # 【2026-09-11 夜】seed に素の文字列が混ざると `s.get` で
        # 'str' object has no attribute 'get' を投げ、suggest_themes 全体が
        # 落ちていた。呼び出し元（_reject_reason の差し替え）は例外を握り潰して
        # **却下したはずのテーマをそのまま採用する**ので、genre_blacklist が
        # 無効化される。ここで形を吸収して、設定の書き方で機能が死なないようにする。
        seed_titles = []
        for s in (channel.theme_seeds or []):
            t = s if isinstance(s, str) else (s.get("title") if isinstance(s, dict) else None)
            if t and str(t).strip():
                seed_titles.append(str(t).strip())
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
        # 【2026-10-01】theme_blacklist をプロンプトに注入する。これまで補充AIは
        # 禁止語を知らされておらず、「あくび」「寝言」等の停止済み題材を補充のたびに
        # 再提案 → pop/最終ゲートで弾かれるループになっていた（daily-science で
        # seed_blacklist_collision 警告が2日連続）。正規表現指定（re:）は表示だけ
        # パターンを示し、確実な除去は下の返却前フィルタが担う。
        _suggest_blacklist = self._channel_theme_blacklist(channel)
        blacklist_block = "\n".join(
            f"- {w[3:] if w.startswith('re:') else w}" for w in _suggest_blacklist
        ) if _suggest_blacklist else "(なし)"
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

        # Phase S: テーマ提案にも季節ブーストを注入
        seasonal_block = ""
        try:
            from pipeline.seasonal_boost import get_seasonal_prompt_addendum
            seasonal_block = get_seasonal_prompt_addendum(channel.id) or ""
            if seasonal_block:
                print(f"  🌸 Injecting seasonal boost into theme suggestions")
        except Exception as e:
            print(f"  ⚠️ seasonal_boost in suggest_themes failed: {e}")

        prompt = f"""YouTube動画テーマを{count}個提案。JSON配列のみ。

# チャンネル: {channel.name} / {channel.concept} / {channel.style} / {channel.content_policy.get("tone","friendly")}

# 重複回避ルール（厳守）
- 下記「除外リスト」と同じ／実質同じ（言い換えだけ）テーマは禁止。
- ただし、過去テーマを「続編・発展系・別角度・深掘り」として明確に進化させる場合に限り、関連トピックを扱ってよい。
  - その場合、`parent_title` に元の過去テーマのタイトルを入れる。
  - `title` には元と被らない新しい切り口を必ず含める（例: 元「なぜ空は青いのか」→ 新「なぜ夕焼けは赤いのか、空の色シリーズ続編」）。
  - タイトルの区切りに全角ダッシュ「—」を使わない（2026-08-23 のCTR実測でscp-labにおいて0.71倍・95%CI 0.61-0.84と有意に逆効果。区切りは読点「、」を使う）。チャンネル側の title_style に別途指定がある場合はそちらを優先する。
- {count}件のうち最大2件まで「過去テーマの発展系（parent_title 付き）」を含めてよい。残りは完全新規のテーマで提案する。
- 完全新規のテーマは `parent_title` を null にする。

# 除外リスト（重複・言い換え禁止）
{excluded_block}

# 禁止題材（運用側で停止中の語。これらを含む／これらを題材にするテーマは提案禁止）
{blacklist_block}

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
{seasonal_block}
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
                # theme_blacklist はプロンプト注入（上）だけでは守られないことがある
                # ので、返却前にも硬く弾く（正規表現 re: もここで効く）。
                bl_hit = self._blacklisted_reason(title, _suggest_blacklist)
                if bl_hit:
                    print(f"  ⛔ suggest filtered by blacklist『{bl_hit}』: '{title}'")
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

    # ファクトシートの「確かな事実」がこれ未満なら、その題材では言い切れる台本が書けない。
    # 比較対象の上位ショートは1本に4〜6個の具体的事実を入れている（ザシアン21秒で4個）。
    SHORT_MIN_SURE_FACTS = 4

    def _short_fact_sheet(self, channel, theme: Dict) -> Optional[Dict[str, Any]]:
        """台本を書く前に、その題材で使える事実を集めて確度を付ける（ショート専用）。

        【2026-10-03 第2周】第1周のサンプル4本は、事実の誤り（百目を『画図百鬼夜行』の妖怪と
        した／ドヒドイデへのつららばりの通りを無視）と、確かめられない話を self-review が
        ぼかした予防線（「定かでない」「〜ことがある」）で、比較対象に負けていた。台本の前に
        事実だけを別の呼び出しで洗い出し、確証のあるものだけを台本に渡す。
        返り値: {"subject", "answerable", "core_answer", "facts":[{"fact","source","sure"}],
                 "pitfalls", "reframe"}。失敗時は None（台本生成はそのまま続ける）。
        """
        genre_hint = (
            "- ポケモン: ゲーム内データ(種族値・タイプ・特性・技の威力と効果)、図鑑テキスト、公式設定。"
            "世代で変わった仕様は世代を書く。メガシンカ・リージョンフォーム・テラスタル後のタイプ/特性を通常の姿と混同しない"
            "(例: ボスゴドラははがね・いわ、はがね単タイプ＋フィルターはメガボスゴドラ)。"
            "対戦の勝敗はタイプ相性・特性・定番の対策技まで確かめる。\n"
            "- SCP: SCP財団Wiki(英語本家・日本語訳)の該当番号の記事本文にある、タイトル・オブジェクトクラス・"
            "特別収容プロトコル・説明・補遺の内容。番号の取り違えと、記事に無い設定の創作をしない。\n"
            "- 妖怪・伝承: 文献名・作者・刊行年・地域の記録。似た名前の別の妖怪や別の画集と取り違えない"
            "(例: 『百々目鬼』は鳥山石燕『今昔画図続百鬼』(1779)。『画図百鬼夜行』(1776)ではない)。\n"
            "- 科学・身体: 教科書や査読研究で確立した知見(研究者名・年・数値)。\n"
        )
        prompt = (
            "YouTubeショート(約25秒・5行の本文)を作る前に、台本に使える事実を集めてください。\n"
            f"チャンネル: {channel.name} / {getattr(channel, 'concept', '')}\n"
            f"テーマ: {theme.get('title', '')}\n切り口: {theme.get('angle', '')}\n"
            "ルール:\n"
            "- 書くのは、公式資料・原典で確かめられる事実だけ。題材ごとの拠り所:\n" + genre_hint +
            "- sure=true は『間違っていたら詳しい視聴者にすぐ指摘される』水準で確かなものだけ。"
            "少しでも記憶があいまいなら sure=false にする(数を稼ぐために true にしない)。\n"
            "- 事実は1つずつ短く(40字以内)、数字・固有名詞・目に見える出来事を含める。同じ事実の言い換えを並べない。\n"
            "- facts は**『友達に話したくなる意外さ』の高い順**に並べる。教科書の用語説明(『〇〇は△△神経に支配される』"
            "『〇〇のタイプは△△』)や、出典の書誌情報だけの事実(『〇〇年の本に載っている』)のような、聞いても驚かない事実は入れない。"
            "各 fact は、数字(量・倍率・時間・順位・年)か、目に見える出来事(誰が何をしてどうなった)のどちらかを必ず含む。比較対象の上位ショートの事実はこの水準: "
            "『ザシアンは設定上メスしかいない』『磁石を近づけるとネズミが離れていく(反磁性)』"
            "『靴紐は走ると足の振りで少しずつ緩む(スタンフォード大の研究)』『百々目鬼は盗んだ銭が腕の目になった女』。\n"
            "- テーマの問いに、確かな事実で言い切れる答えがあるかを answerable で答える。"
            "テーマ文が確かめられない前提(『正体は〇〇だった』『12名が消えた』など)に立っているなら false にし、"
            "同じ題材で、確かな事実だけで言い切れる切り口を reframe に1文で、その切り口の動画テーマ名を reframe_title に書く"
            "(30字以内・確かめられない数字を入れない)。reframe は facts のうち**いちばん意外な事実を主役**にし、"
            "肯定形で言える答えを持つ切り口にする。『〜ではない』『説明がない』『空白』『勝敗は決まらない』のような"
            "否定・不在を主題にした切り口や、『検証』『再検証』の形は不可。"
            "作品の外側の話(SCPの著者・投稿時期・Wikiの構成、ゲームの開発秘話の噂)にもしない。"
            "作中・伝承の中で起きる出来事として語れる切り口にする。\n"
            "- core_answer も肯定形で書く(『〜だ』『〜が原因だ』)。否定形(『〜ではない』『〜は確認できない』)は答えにしない。\n"
            + _HOOK_SPEC +
            "- よくある取り違え(似た名前・別の文献・世代差・別番号)を pitfalls に書く。\n"
            "- source_titles には、この題材の原典を引ける見出し語を2〜3個書く"
            "(ポケモンは日本語の正式名『ジガルデ』、SCPは『SCP-1025』、妖怪・科学は日本語版Wikipediaの記事名『送り犬』『涙』)。\n"
            '出力はJSONのみ: {"subject":"題材の正式名","source_titles":["..."],"answerable":true,'
            '"core_answer":"テーマの問いへの答え(1文で言い切る)",'
            '"facts":[{"fact":"...","source":"...","sure":true}, ...6〜8個],'
            '"hook":"...","punchline":"...",'
            '"pitfalls":["..."],"reframe":"","reframe_title":""}'
        )
        try:
            raw = self._call_gpt(
                [{"role": "system", "content": "事実確認の担当。確証の無いことは確証が無いと書く。JSONのみ出力。"},
                 {"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=1800, max_retries=2,
            )
            data = self._extract_json(raw)
        except Exception as e:
            print(f"  ⚠️ fact sheet failed: {e}")
            return None
        if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
            return None
        data["facts"] = [f for f in data["facts"] if isinstance(f, dict) and f.get("fact")][:10]
        n_sure = sum(1 for f in data["facts"] if f.get("sure") is True)
        print(f"  📚 fact sheet: 確かな事実 {n_sure}/{len(data['facts'])} 件"
              f" / answerable={data.get('answerable')}")
        try:
            data = self._ground_fact_sheet(channel, theme, data)
        except Exception as e:
            print(f"  ⚠️ 原典照合に失敗（GPTの申告のまま続行）: {e}")
        return data

    def _ground_fact_sheet(self, channel, theme: Dict, sheet: Dict[str, Any]) -> Dict[str, Any]:
        """ファクトシートの事実を原典の本文と照合し、照合できたものだけ sure にする。

        1. 題材の原典（SCP財団Wiki本文／ポケモンWiki記事／日本語版Wikipedia）を取得する。
        2. GPT に、原典の抜粋から事実を選ばせ、各事実に原文の引用(quote)を付けさせる。
        3. quote が原典本文に実在し（NFKC・空白記号の揺れだけ吸収）、事実の数字がすべて
           quote に含まれるときだけ sure=True。GPT の申告は使わない。
        原典が取れないジャンル・題材では sheet をそのまま返す（grounded=False）。
        """
        sheet["grounded"] = False
        kind = _source_kind(channel)
        if not kind:
            return sheet
        subject = str(sheet.get("subject") or "")
        titles = [str(t) for t in (sheet.get("source_titles") or []) if isinstance(t, str)]
        ttl, ang = str(theme.get("title") or ""), str(theme.get("angle") or "")
        if kind == "scp":
            cands = _scp_numbers(ttl, ang, subject, *titles)
        elif kind == "pokemon":
            cands = []
            for c in titles + [subject] + re.findall(r"[ァ-ヺー]{2,}", ttl):
                m = re.match(r"[ァ-ヺー]{2,}", _nfkc(c).strip()) if c else None
                if m and m.group(0) not in cands:
                    cands.append(m.group(0))
        else:
            cands = []
            # 題材の正式名（「化け狸」）を先に引く。見出し語の候補には一般語（「タヌキ」）が
            # 混じり、そちらを先に引くと妖怪の話が動物の生態の話にすり替わる（第3周の試行で実測）。
            for c in [subject] + titles:
                c = re.sub(r"[（(].*?[）)]", "", c or "").strip()
                if c and c not in cands:
                    cands.append(c)
        text, url = _fetch_source(kind, cands[:5])
        if text and kind == "wikipedia":
            # 2本目の記事も足して、選べる事実の幅を広げる（例: 送り犬＋遠野物語）
            rest = [c for c in cands[:5] if c not in url and _nfkc(c) not in text[:80]]
            text2, url2 = _fetch_source(kind, rest[:3]) if rest else ("", "")
            if text2 and url2 != url:
                text = text + "\n" + text2
        if not text and kind == "wikipedia":
            # 見出し語が学術語（「睡眠慣性」など）で記事が無いときは、Wikipedia の全文検索で記事を探す
            found = _wikipedia_search(subject or ttl) or _wikipedia_search(ttl)
            if found:
                text, url = _fetch_source(kind, found[:2])
        if not text:
            print(f"  ⚠️ 原典を取得できず（{kind}: {cands[:5]}）— GPTの申告のまま続行")
            sheet["source_missing"] = cands[:5]
            return sheet
        draft = "\n".join(f"- {f.get('fact')}" for f in (sheet.get("facts") or []) if isinstance(f, dict))
        excerpt = _relevant_excerpt(text, _tokens(f"{ttl} {ang} {subject} {draft}"))
        prompt = (
            "YouTubeショートの台本に使う事実を、下の『原典』に書いてあることだけから選んでください。\n"
            f"チャンネル: {channel.name}\nテーマ: {ttl}\n切り口: {ang}\n"
            f"下書きの事実(原典に裏付けがあるものだけ残す。無いものは捨てる):\n{draft}\n"
            "ルール:\n"
            "- facts は6〜8個。各事実に、原典の本文から**1文字も変えずに写した**引用 quote(15〜60字)を付ける。"
            "quote に無い数字・話数・許可レベル・作品名・人数は fact に書かない。\n"
            "- 事実は1つずつ短く(40字以内)、普段の言葉で書く(学術用語は言い換える)。同じ事実の言い換えを並べない。\n"
            "- 各事実に surprise(1〜5)を付ける。5=『ザシアンは設定上メスしかいない』『磁石を近づけるとネズミが離れていく』"
            "級で、聞いた人が思わず誰かに話す。1=用語の定義・分類・書誌情報(聞いても誰も驚かない)。"
            "facts は surprise の高い順に並べ、surprise 2以下は入れない。hook と punchline は surprise 4以上の事実から作る。\n"
            "- 原典が伝承・設定・報告書なら、『〜と言われる』『報告書には〜とある』のように出典の中の話として書く。\n"
            "- SCPなら、オブジェクトクラスを言い換え付きで1つの事実に入れる(例『Safe(鍵をかければ収容できる)』)。"
            "取り消し線で消された古い値は本文から除いてある。\n"
            "- answerable: テーマの問いに、facts だけで肯定形で言い切れる答えがあるか。"
            "無ければ false にし、facts のいちばん意外な事実を主役にした切り口を reframe(1文)と"
            "reframe_title(30字以内のテーマ名)に書く。否定・不在を主題にした切り口、作品の外側の話は不可。\n"
            "- core_answer: テーマの問いへの答えを facts だけで1文で言い切る(肯定形)。\n"
            + _HOOK_SPEC +
            "- hook と punchline に入れる数字・固有名詞は facts にあるものだけ。\n"
            '出力はJSONのみ: {"answerable":true,"core_answer":"...",'
            '"facts":[{"fact":"...","quote":"原典からそのまま","surprise":5}, ...],'
            '"hook":"...","punchline":"...","reframe":"","reframe_title":""}\n\n'
            f"# 原典({url})\n{excerpt}\n"
        )
        raw = self._call_gpt(
            [{"role": "system", "content": "原典に書いてあることだけを扱う事実確認の担当。JSONのみ出力。"},
             {"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=6000, max_retries=2,
        )
        try:
            data = self._extract_json(raw)
        except Exception:
            data = None
        if not isinstance(data, dict):
            # 出力が途中で切れることがある（第3周で 789字で途切れたのを実測）。1回だけ取り直す。
            try:
                raw = self._call_gpt(
                    [{"role": "system", "content": "原典に書いてあることだけを扱う事実確認の担当。JSONのみ出力。簡潔に。"},
                     {"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=6000, max_retries=1,
                )
                data = self._extract_json(raw)
            except Exception:
                data = None
        if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
            print(f"  ⚠️ 原典照合: 出力を読めず（{len(raw or '')}字: {(raw or '')[:80]!r}）— GPTの申告のまま続行")
            sheet["source_url"] = url
            return sheet
        src_sq = _squash(text)
        src_nf = _nfkc(text)
        grounded: List[Dict[str, Any]] = []
        rejected: List[str] = []
        for f in data["facts"]:
            if not isinstance(f, dict) or not f.get("fact"):
                continue
            fact, quote = str(f["fact"]).strip(), str(f.get("quote") or "").strip()
            q_ok = _verify_quote(quote, src_sq)
            nums_ok = all(n in _nfkc(quote) for n in _numbers_in(fact))
            ok = q_ok and nums_ok
            if not ok:
                rejected.append(f"{fact}（{'引用が原典に無い' if not q_ok else '数字が引用に無い'}）")
            try:
                sp = int(f.get("surprise") or 3)
            except (TypeError, ValueError):
                sp = 3
            grounded.append({"fact": fact, "quote": quote, "source": "原典", "sure": ok, "surprise": sp})
        # 照合できた事実を先に、その中は意外さの高い順（同点は元の順）
        grounded = (sorted([g for g in grounded if g["sure"]], key=lambda g: -g["surprise"])
                    + [g for g in grounded if not g["sure"]])
        sure_nums = set()
        for g in grounded:
            if g["sure"]:
                sure_nums.update(_numbers_in(g["fact"]))
        out = dict(sheet)
        out.update({
            "facts": grounded[:10],
            "grounded": True,
            "source_url": url,
            "source_kind": kind,
            "grounding_rejected": rejected,
            "draft_facts": [f.get("fact") for f in (sheet.get("facts") or []) if isinstance(f, dict)],
        })
        for k in ("answerable", "core_answer", "reframe", "reframe_title"):
            if k in data:
                out[k] = data[k]
        for k in ("hook", "punchline", "core_answer"):
            v = str(data.get(k) or "")
            bad = [n for n in _numbers_in(v) if n not in sure_nums]
            out[k] = "" if bad else v
        n_sure = sum(1 for g in grounded if g["sure"])
        print(f"  🔎 原典照合: {url} — 照合できた事実 {n_sure}/{len(grounded)} 件"
              + (f"（不採用 {len(rejected)}）" if rejected else ""))
        return out

    def _assertable_short_theme(self, channel, theme: Dict,
                                avoid_duplicate_theme: bool = True) -> Tuple[Dict, Optional[Dict]]:
        """ファクトシートを作り、言い切れない題材なら切り口の差し替え→題材の差し替えを行う。

        - 確かな事実が SHORT_MIN_SURE_FACTS 件以上で answerable → そのまま
        - 確かな事実は足りるが、テーマ文の前提が確かめられない（「12名が消えた」のような
          作られた数字・「正体は監視の怪異」のような立証できない結論）→ 同じ題材のまま
          テーマ名と切り口を reframe_title / reframe に替える。テーマ名を残すと、台本が
          「12名の消失は本文にない」のように自分の題名を否定する検証話法になる
          （第2周の初回生成で scp-lab・yokai-watch・pokemon-lab の3本がそうなった）。
        - 確かな事実が足りない → theme_seeds（運用側が選んだ題材）→ AI 提案の順に最大3件試す。
          見つからなければ元のテーマで続け、theme["assert_gate"] に記録する。
        """
        sheet = self._short_fact_sheet(channel, theme)
        if sheet is None:
            return theme, None

        def _n_sure(sh):
            return sum(1 for f in (sh.get("facts") or []) if f.get("sure") is True)

        def _apply_reframe(th: Dict, sh: Dict, gate: Dict) -> Dict:
            out = dict(th)
            if sh.get("answerable") is False:
                rt = (sh.get("reframe_title") or "").strip()
                ra = (sh.get("reframe") or "").strip()
                if rt:
                    gate["reframed_title_from"] = th.get("title", "")
                    out["title"] = rt
                if ra:
                    gate["reframed_angle_from"] = th.get("angle", "")
                    out["angle"] = ra
                if rt or ra:
                    gate.setdefault("reason", "テーマ文の前提を確かな事実で言い切れない")
                    print(f"  🧭 言い切れない前提のためテーマを差し替え: {out.get('title')} / {out.get('angle', '')[:40]}")
            if gate:
                out["assert_gate"] = gate
            return out

        if _n_sure(sheet) >= self.SHORT_MIN_SURE_FACTS:
            if sheet.get("answerable") is False and sheet.get("grounded"):
                # 【第3周】原典で答えが言い切れない題材を、原典の別の事実へ切り口ごと差し替えると、
                # 「なぜ雨の前に関節が重い？」→「空気の重み、気圧の正体」のように、題材の形
                # （問い・正体・答え合わせ）が抜けた百科事典の話になった（試行で実測）。
                # 比較対象の上位は題材の形が勝因なので、先に運用側の theme_seeds から
                # 原典で答えが言い切れる題材を探し、無いときだけ切り口を差し替える。
                tried0 = {(theme.get("title") or "").strip().lower()}
                for _ in range(2):
                    try:
                        c = self._pick_seed_avoiding_past(channel)
                    except Exception:
                        break
                    t = ((c or {}).get("title") or "").strip() if isinstance(c, dict) else ""
                    if not t or t.lower() in tried0:
                        continue
                    tried0.add(t.lower())
                    c = dict(c)
                    if avoid_duplicate_theme:
                        c = self._dedupe_theme(channel, c)
                    sh = self._short_fact_sheet(channel, c)
                    if sh and sh.get("answerable") is not False and _n_sure(sh) >= self.SHORT_MIN_SURE_FACTS:
                        print(f"  ✅ 原典で答えが言い切れる題材に差し替え: {c.get('title')}")
                        return _apply_reframe(c, sh, {"replaced": theme.get("title"),
                                                      "reason": "原典で答えを言い切れない"}), sh
            return _apply_reframe(theme, sheet, {}), sheet

        reason = f"確かな事実が {_n_sure(sheet)} 件しかない"
        print(f"  ♻️ Theme '{theme.get('title')}' — {reason}。言い切れる題材を探します")
        tried = {(theme.get("title") or "").strip().lower()}
        cands: List[Dict] = []
        for _ in range(4):
            try:
                c = self._pick_seed_avoiding_past(channel)
            except Exception:
                break
            if isinstance(c, dict) and (c.get("title") or "").strip().lower() not in tried \
                    and all(c.get("title") != x.get("title") for x in cands):
                cands.append(dict(c))
            if len(cands) >= 2:
                break
        try:
            for c in (self.suggest_themes(channel, count=3) or []):
                if isinstance(c, dict) and c.get("title"):
                    cands.append({"title": c["title"], "angle": c.get("angle", "") or "",
                                  "parent_title": c.get("parent_title")})
                    break
        except Exception as e:
            print(f"  ⚠️ suggest_themes failed: {e}")
        for cand in cands[:3]:
            t = (cand.get("title") or "").strip()
            if not t or t.lower() in tried:
                continue
            tried.add(t.lower())
            if avoid_duplicate_theme:
                cand = self._dedupe_theme(channel, cand)
            sh = self._short_fact_sheet(channel, cand)
            if sh and _n_sure(sh) >= self.SHORT_MIN_SURE_FACTS:
                print(f"  ✅ 言い切れる題材に差し替え: {cand.get('title')}")
                return _apply_reframe(cand, sh, {"replaced": theme.get("title"), "reason": reason}), sh
        out = dict(theme)
        out["assert_gate"] = {"kept_despite": reason}
        return out, sheet

    @staticmethod
    def _short_lint_ctx(channel) -> Dict[str, Any]:
        """_lint_short に渡すチャンネル側の条件（話者・掛け合いか・字数上限・題材名の検査）。"""
        names = list((getattr(channel, "characters", None) or {}).keys())
        dialogue = len(names) >= 2 and getattr(channel, "style", "") != "monologue"
        chars_min = chars_max = 0
        try:
            from pipeline import shorts_length_guard as _slg
            chars_min, chars_max = (int(x) for x in _slg.char_band_for(channel.id))
        except Exception:
            pass
        kind = _source_kind(channel)
        cid = (getattr(channel, "id", "") or "").lower()
        return {
            "explainer": names[0] if names else "",
            "listener": names[1] if len(names) > 1 else "",
            "dialogue": dialogue,
            "chars_max": chars_max,
            "chars_min": chars_min,
            # 固有名のある題材（SCP番号・ポケモン名・妖怪名）だけ、1行目の題材名を検査する
            "check_subject": kind in ("scp", "pokemon") or "yokai" in cid,
        }

    def _short_lint_repair(self, channel, theme: Dict, scenario_data: Dict[str, Any],
                           max_rounds: int = 3) -> None:
        """機械検査で見つかった違反を具体的に書いて差し戻し、良くなった書き直しだけ採用する（in-place）。

        採用条件: 違反の重み付き合計が下がること。CTA（最終行）は元のまま残す。
        直りきらなくても止めない（無人運転で台本ゼロを避ける）。残った違反は
        scenario_data["short_lint"] に残し、PDCA で追えるようにする。
        """
        lines = scenario_data.get("short_scenario") or []
        if not lines or not all(isinstance(e, dict) for e in lines):
            return
        ctx = self._short_lint_ctx(channel)
        sheet = scenario_data.get("short_fact_sheet")

        def lint(ls):
            return _lint_short(ls, sheet=sheet, theme=theme, **ctx)

        viol = lint(lines)
        before = [v["msg"] for v in viol]
        rounds: List[Dict[str, Any]] = []
        for r in range(max_rounds):
            if not viol:
                break
            print(f"  🧪 short lint: 違反 {len(viol)}件（重み {_lint_score(viol)}）→ 差し戻し {r + 1}/{max_rounds}")
            for v in viol[:12]:
                print(f"     - {v['msg'][:90]}")
            try:
                bad_lines = {v["line"] for v in viol}
                if None not in bad_lines and len(bad_lines) <= 2 \
                        and not any(v["code"] in ("line_count", "speaker", "run") for v in viol):
                    # 違反が1〜2行に収まっているときは、その行だけを書き直させて差し込む
                    # （全体を書き直させると、直した行の代わりに別の行が崩れた。第3周で実測）
                    cand = self._short_line_fix_call(channel, theme, lines, viol, ctx, sheet,
                                                     temperature=0.4 + 0.2 * r)
                else:
                    # 不採用が続いたら少し温度を上げて別の書き方を出させる
                    cand = self._short_repair_call(channel, theme, lines, viol, ctx, sheet,
                                                   temperature=0.4 + 0.2 * r)
            except Exception as e:
                print(f"  ⚠️ short lint repair failed: {e}")
                break
            if not cand:
                rounds.append({"round": r + 1, "accepted": False, "reason": "出力不正"})
                continue
            new_viol = lint(cand)
            if _lint_score(new_viol) < _lint_score(viol):
                lines[:] = cand
                rounds.append({"round": r + 1, "accepted": True,
                               "score": [_lint_score(viol), _lint_score(new_viol)]})
                viol = new_viol
            else:
                rounds.append({"round": r + 1, "accepted": False,
                               "score": [_lint_score(viol), _lint_score(new_viol)]})
        scenario_data["short_lint"] = {
            "violations_before": before,
            "violations_after": [v["msg"] for v in viol],
            "rounds": rounds,
        }
        print(f"  🧪 short lint: 残り {len(viol)}件" + (f" {[v['code'] for v in viol]}" if viol else " — 合格"))

    def _short_repair_call(self, channel, theme: Dict, lines: List[Dict[str, Any]],
                           viol: List[Dict[str, Any]], ctx: Dict[str, Any],
                           sheet: Optional[Dict[str, Any]],
                           temperature: float = 0.4) -> Optional[List[Dict[str, Any]]]:
        """違反リストを渡して台本全体を書き直させる。返り値は short_scenario 形式（不正なら None）。"""
        cta = lines[-1]
        cur = "\n".join(
            f"{i + 1}. [{e.get('speaker')}] ({len(str(e.get('text') or ''))}字) {e.get('text')}"
            + (f"  (fact={e.get('fact')})" if e.get("fact") else "")
            for i, e in enumerate(lines)
        )
        if ctx["dialogue"]:
            n_out = SHORT_DIALOGUE_LINE_COUNT
            layout = _SHORT_LINE_ROLES_DIALOGUE.replace("上の構成と食い違うときはこちらを優先", "厳守")
            spk = [ctx["explainer"] if r == 0 else ctx["listener"] for r in SHORT_DIALOGUE_SPEAKERS]
            spk_note = "本文6行の話者は順に " + "・".join(spk) + "。"
        else:
            n_out = len(lines)
            layout = _SHORT_LINE_ROLES
            spk_note = "話者は元のまま。"
        if _cta_problem(cta.get("text")):
            spk_note += ("最終行(CTA)は書き直す: 『高評価』(この回の中身に一言) → 『登録で〇〇が届く』"
                         "(このチャンネルの題材で)。22〜36字。")
        else:
            spk_note += f"最終行(CTA)は元の「{cta.get('text')}」をそのまま返す。"
        voice = (getattr(channel, "voice_style", None) or {}).get("speech_signature") or ""
        prompt = (
            "次のYouTubeショート台本には、機械検査で見つかった違反があります。違反を全部直した台本を返してください。\n"
            "# 違反\n" + "\n".join(f"- {v['msg']}" for v in viol) + "\n\n"
            f"# 行の構成\n{layout}\n{spk_note}\n"
            "# 守ること\n"
            "- 事実はファクトシートの『確かな事実』(F番号)からだけ取る。確かな事実に無い数字・話数・作品名・許可レベルは書かない。\n"
            "- 事実を運ぶ行どうしで同じ事実を言い直さない。同じF番号を2行で使わない。\n"
            "- 聞き役の行は8〜18字。前の行で解説役が言った語だけを使って、驚く・ツッコむ・問い返す。\n"
            "- 1行目は題材名＋事実で、問いなら問いで止める。『本当？』は使わない。\n"
            "- 最後の内容行(CTAの直前)は、冒頭へ戻る二人称の問いか、コメントで答えたくなる問いで終える。\n"
            "- 教科書の言葉は普段の言葉に言い換える。予防線(〜かもしれない・諸説ある)を入れない。\n"
            "- 解説役の行は24〜34字。短くしすぎない(短い行は具体が抜けて比較対象に負ける)。\n"
            f"- 総字数{ctx.get('chars_min') or 165}〜{ctx['chars_max'] or 200}字。語り口: {voice}\n"
            f"テーマ: {theme.get('title', '')} / 切り口: {theme.get('angle', '')}\n"
            f"ファクトシート:\n{_fact_sheet_text(sheet) or '(なし)'}\n\n"
            f"# 今の台本\n{cur}\n\n"
            f'出力はJSONのみ: {{"lines":[{{"speaker":"...","text":"...","fact":"F1 または null"}}, ...全{n_out}行]}}'
        )
        raw = self._call_gpt(
            [{"role": "system", "content": "YouTubeショート台本の書き直し担当。検査の違反を残さない。JSONのみ出力。"},
             {"role": "user", "content": prompt}],
            temperature=temperature, max_tokens=1800, max_retries=2,
        )
        data = self._extract_json(raw)
        new = data.get("lines") if isinstance(data, dict) else None
        return self._normalize_short_lines(channel, ctx, new, lines, n_out)

    def _short_line_fix_call(self, channel, theme: Dict, lines: List[Dict[str, Any]],
                             viol: List[Dict[str, Any]], ctx: Dict[str, Any],
                             sheet: Optional[Dict[str, Any]],
                             temperature: float = 0.4) -> Optional[List[Dict[str, Any]]]:
        """違反のある行だけを書き直させ、元の台本に差し込んだものを返す。"""
        targets = sorted({v["line"] for v in viol if v.get("line")})
        if not targets:
            return None
        cur = "\n".join(f"{i + 1}. [{e.get('speaker')}] ({len(str(e.get('text') or ''))}字) {e.get('text')}"
                        for i, e in enumerate(lines))
        voice = (getattr(channel, "voice_style", None) or {}).get("speech_signature") or ""
        prompt = (
            "次のYouTubeショート台本の、指定した行だけを書き直してください。ほかの行はそのまま使います。\n"
            "# 違反\n" + "\n".join(f"- {v['msg']}" for v in viol) + "\n"
            f"# 書き直す行: {', '.join(f'L{n}' for n in targets)}\n"
            "- 前後の行と会話としてつながるように書く。事実はファクトシートの確かな事実からだけ取り、"
            "ほかの行と同じ事実を言い直さない。\n"
            "- 解説役の行は24〜34字、聞き役の行は8〜18字、CTAは22〜36字。\n"
            "- 1行目は、結果が予想できない問い(〜したらどうなる？／なぜ〜なのか)、あなたを当事者にする言い切り、"
            "限定・数字で覆す事実(〜しかいない)のどれか。\n"
            f"語り口: {voice}\n"
            f"テーマ: {theme.get('title', '')}\n"
            f"ファクトシート:\n{_fact_sheet_text(sheet) or '(なし)'}\n\n"
            f"# 今の台本\n{cur}\n\n"
            '出力はJSONのみ: {"lines":{"L1":"書き直した本文", ...}}'
        )
        raw = self._call_gpt(
            [{"role": "system", "content": "YouTubeショート台本の書き直し担当。指定の行だけ直す。JSONのみ出力。"},
             {"role": "user", "content": prompt}],
            temperature=temperature, max_tokens=1200, max_retries=2,
        )
        data = self._extract_json(raw)
        fixed = data.get("lines") if isinstance(data, dict) else None
        if not isinstance(fixed, dict):
            return None
        out = [dict(e) for e in lines]
        for n in targets:
            t = fixed.get(f"L{n}") or fixed.get(str(n))
            if not t or not (1 <= n <= len(out)):
                continue
            t = _clean_llm_line(re.sub(r"^\s*(?:L?\d+[.:：]\s*)?\[[^\]]{1,20}\]\s*", "", str(t)).strip())
            if n == len(out):
                if _cta_problem(t):
                    continue
            out[n - 1]["text"] = t
        return out

    @staticmethod
    def _normalize_short_lines(channel, ctx: Dict[str, Any], new: Any, ref: List[Dict[str, Any]],
                               n_out: int) -> Optional[List[Dict[str, Any]]]:
        """GPT が返した行リストを short_scenario 形式に整える。CTA（最終行）は ref のものを使う。"""
        if not isinstance(new, list) or len(new) != n_out:
            return None
        cta = dict(ref[-1])
        # 元の CTA に問題があり（届く物が無い・長すぎる）、新しい CTA が合格なら新しい方を使う
        last_new = new[-1].get("text") if isinstance(new[-1], dict) else new[-1]
        if _cta_problem(cta.get("text")) and last_new and not _cta_problem(str(last_new)):
            cta["text"] = _clean_llm_line(str(last_new))
        chars = getattr(channel, "characters", {}) or {}
        out: List[Dict[str, Any]] = []
        for i, e in enumerate(new[:-1]):
            if isinstance(e, str):
                e = {"text": e}
            if not isinstance(e, dict) or not str(e.get("text") or "").strip():
                return None
            spk = str(e.get("speaker") or "")
            if ctx["dialogue"] and i < len(SHORT_DIALOGUE_SPEAKERS):
                spk = ctx["explainer"] if SHORT_DIALOGUE_SPEAKERS[i] == 0 else ctx["listener"]
            elif not ctx["dialogue"] and i < len(ref) - 1:
                spk = str(ref[i].get("speaker") or spk)
            if spk not in chars:
                spk = ctx["explainer"] or spk
            exprs = list((chars.get(spk) or {}).get("expressions") or ["normal"])
            # 表情・mood は同じ位置・同じ話者の元の行から引き継ぐ
            src = ref[i] if i < len(ref) - 1 and ref[i].get("speaker") == spk else {}
            listener_line = ctx["dialogue"] and spk == ctx["listener"]
            expr = src.get("expression")
            if expr not in exprs:
                expr = "surprise" if (listener_line and "surprise" in exprs) else "normal"
            fid = e.get("fact")
            out.append({
                "speaker": spk,
                "text": _clean_llm_line(re.sub(r"^\s*(?:\d+\.\s*)?\[[^\]]{1,20}\]\s*", "", str(e["text"])).strip()),
                "expression": expr,
                "mood": src.get("mood") or ("tense" if i < 2 else "mysterious"),
                "fact": (str(fid).strip().upper() if fid and str(fid).lower() not in ("null", "none") else None),
            })
        out.append(cta)
        return out

    def _short_focus_rewrite(self, channel, theme: Dict, scenario_data: Dict[str, Any]) -> None:
        """事実・行の役割・お手本だけを渡した短いプロンプトで台本を書き直させ、良ければ採用する（in-place）。

        本生成のプロンプトは約1万字（チャンネル固有の構成・タイトル規則・サムネ規則・分析の追記）
        で、指示どうしが食い違う。第3周の試行では、本生成の台本を機械検査の差し戻しで直すと
        「飛騨では三人目の薬で血も痛まない」のように意味の崩れた圧縮文になった。そこで、
        台本を書く仕事だけを切り出したプロンプトで2案書かせ、機械検査の点が良い方を採る。
        元の台本より点が悪ければ採らない。
        """
        lines = scenario_data.get("short_scenario") or []
        if not lines or not all(isinstance(e, dict) for e in lines):
            return
        ctx = self._short_lint_ctx(channel)
        sheet = scenario_data.get("short_fact_sheet")
        sheet_txt = _fact_sheet_text(sheet)
        if not sheet_txt:
            return
        n_out = SHORT_DIALOGUE_LINE_COUNT if ctx["dialogue"] else len(lines)
        layout = (_SHORT_LINE_ROLES_DIALOGUE if ctx["dialogue"] else _SHORT_LINE_ROLES).replace(
            "上の構成と食い違うときはこちらを優先", "厳守")
        vs = getattr(channel, "voice_style", None) or {}
        chars = getattr(channel, "characters", {}) or {}
        char_txt = "\n".join(f"- {n}: {c.get('role', '')}" for n, c in chars.items())
        forbidden = "、".join(str(x) for x in (vs.get("forbidden") or [])[:20])
        cur = "\n".join(f"{i + 1}. [{e.get('speaker')}] {e.get('text')}" for i, e in enumerate(lines))
        prompt = (
            "YouTubeショート(縦型・約25秒)の掛け合い台本を書いてください。比較対象は、同じジャンルで"
            "19万〜848万回再生された実在のショート(下の『お手本』)です。並べて見劣りしない台本にします。\n"
            f"# チャンネル: {channel.name}\n# キャラ\n{char_txt}\n"
            f"# 語り口: {vs.get('tone', '')}\n# 声の指紋: {vs.get('speech_signature', '')}\n"
            + (f"# 使わない語: {forbidden}\n" if forbidden else "")
            + f"# テーマ: {theme.get('title', '')} / 切り口: {theme.get('angle', '')}\n"
            f"# ファクトシート(事実はここの確かな事実からだけ取る)\n{sheet_txt}\n\n"
            f"{layout}\n"
            "# 書き方\n"
            "- まず、確かな事実から4つ選んで並べ方を決める(plan)。1行目はいちばん意外な事実か、その結果を問う形。"
            "3行目でその理由・正体、4行目で『しかも』の上乗せ、6行目で冒頭へ戻る問い。\n"
            "- 話し言葉で書く。助詞を省いた見出し語(『〜の記録。』『〜という記録が残る。』)を続けない。"
            "1文で意味が通じるように、主語と述語をそろえる。\n"
            "- 数字・固有名詞・目に見える出来事を、事実の行に1つずつ入れる。\n"
            f"- 総字数は{ctx.get('chars_min') or 165}〜{ctx.get('chars_max') or 200}字"
            f"(CTAの{len(str(lines[-1].get('text') or ''))}字を含む)。\n"
            + (f"- 最終行は、今のCTA「{lines[-1].get('text')}」をそのまま使う。\n"
               if not _cta_problem(lines[-1].get("text")) else
               "- 最終行(CTA)は書き直す: 『高評価』(この回の中身に一言) → 『登録で〇〇が届く』(このチャンネルの題材で)。22〜36字。\n") +
            f"# 今の下書き(参考。良いところは残してよい)\n{cur}\n\n"
            "書き方の違う案を2つ出す。出力はJSONのみ: "
            '{"candidates":[{"plan":"F?→F?→F?→F? と狙い","lines":[{"speaker":"...","text":"...","fact":"F1 または null"}, ...全'
            f'{n_out}行]}}, {{...2案目}}]}}'
        )
        try:
            raw = self._call_gpt(
                [{"role": "system", "content": "伸びるYouTubeショートの台本作家。事実はファクトシートからだけ使う。JSONのみ出力。"},
                 {"role": "user", "content": prompt}],
                temperature=0.8, max_tokens=3000, max_retries=2,
            )
            data = self._extract_json(raw)
        except Exception as e:
            print(f"  ⚠️ short focus rewrite failed: {e}")
            return
        cands = data.get("candidates") if isinstance(data, dict) else None
        if not isinstance(cands, list):
            return

        def score(ls):
            return _lint_score(_lint_short(ls, sheet=sheet, theme=theme, **ctx))

        base = score(lines)
        best, best_score, scores = None, None, []
        for c in cands[:3]:
            ls = self._normalize_short_lines(channel, ctx, (c or {}).get("lines") if isinstance(c, dict) else None,
                                             lines, n_out)
            if not ls:
                scores.append(None)
                continue
            sc = score(ls)
            scores.append(sc)
            if best_score is None or sc < best_score:
                best, best_score = ls, sc
        accepted = best is not None and best_score <= base
        if accepted:
            scenario_data["short_draft"] = [dict(e) for e in lines]
            lines[:] = best
        scenario_data["short_focus_rewrite"] = {"base_score": base, "candidate_scores": scores,
                                                "accepted": accepted}
        print(f"  ✍️ short focus rewrite: 下書き {base}点 / 案 {scores} → {'採用' if accepted else '不採用'}（点は違反の重み、低いほど良い）")

    @staticmethod
    def _short_postfix(channel, scenario_data: Dict[str, Any]) -> List[str]:
        """プロンプトで言っても残りやすい2点を決定的に直す（ショート専用）。

        - 1行目の頭の「これ知ってた？」「知ってた？」を外す（残りが15字以上のときだけ）。
          比較対象の上位8本はどれも0秒目から題材名で入っている。
        - 最終行（高評価+登録）の表情が sad / angry / surprise なら normal に戻す。
          第1周の yokai-watch は sad の顔で「知らなかったら高評価」と頼んでいた。
        """
        lines = scenario_data.get("short_scenario") or []
        if not lines or not all(isinstance(e, dict) for e in lines):
            return []
        fixes: List[str] = []
        for i, e in enumerate(lines):
            raw_t = str(e.get("text") or "")
            cleaned = _clean_llm_line(raw_t)
            if cleaned and cleaned != raw_t.strip():
                e["text"] = cleaned
                fixes.append(f"L{i + 1} 混入文字を除去")
        first = str(lines[0].get("text") or "")
        m = re.match(r"^\s*(?:ねえ、?|ねぇ、?)?(?:これ|コレ)?知って(?:た|る|ました)[？?！!]?\s*[、,]?\s*", first)
        if m and len(first) - m.end() >= 15:
            lines[0]["text"] = first[m.end():]
            fixes.append(f"L1 前置き削除: {m.group(0).strip()}")
        last = lines[-1]
        cta = str(last.get("text") or "")
        if len(cta) > 36 and "チャンネル登録" in cta:
            # 最終行は 22〜36字（_short_end_line_block）。「チャンネル登録」→「登録」で4字縮める。
            last["text"] = cta.replace("チャンネル登録", "登録", 1)
            fixes.append(f"CTA短縮 {len(cta)}→{len(last['text'])}字")
        if str(last.get("expression") or "") in ("sad", "angry", "surprise", "scared", "fear"):
            fixes.append(f"CTA表情 {last.get('expression')}→normal")
            last["expression"] = "normal"
        if fixes:
            print(f"  🧹 short postfix: {' / '.join(fixes)}")
        return fixes

    def _short_self_review(self, channel, theme: Dict, scenario_data: Dict[str, Any]) -> None:
        """ショート台本を1回だけ見直させ、合格した書き直しだけを採用する（in-place）。

        【2026-10-03】長尺を作らなくなって浮いた API 時間（1本あたり約130秒）の一部を、
        ショート本体の見直しに使う。生成1回目の台本には、比較対象の上位ショートでは
        見られない欠陥が残っていた（いずれも 2026-10-03 の生成サンプルで確認）:
          - 事実の誤り（「ミュウは全1000種類以上の技を覚える」）
          - 張った謎の未回収（「47人が全員同じ言葉を残した」→ 言葉が出てこない）
          - 1行目の主張と結論の食い違い、同じ事実の言い換えだけの行
        書き直しは行数・話者・各行の字数帯を変えないことを条件に採用し、外れたら捨てる
        （無人運転で台本が壊れるより、元の台本で出すほうが安全）。
        """
        lines = scenario_data.get("short_scenario") or []
        if not lines or not all(isinstance(e, dict) for e in lines):
            return
        texts = [str(e.get("text", "")) for e in lines]
        speakers = [e.get("speaker") for e in lines]
        numbered = "\n".join(
            f"{i + 1}. [{speakers[i] or 'ナレーター'}] {t}" for i, t in enumerate(texts)
        )
        voice = (getattr(channel, "voice_style", None) or {}).get("speech_signature") or ""
        sheet_txt = _fact_sheet_text(scenario_data.get("short_fact_sheet"))
        hedges = _find_hedges(texts[:-1])
        prompt = (
            "次のYouTubeショート台本を、比較対象（同ジャンルで50万〜850万回再生のショート）と並べて"
            "負けない水準に直してください。直す観点は次の8つだけ:\n"
            "1. 事実の誤り・誇張（種族値・技の効果・特性・タイプ相性・設定・SCPの番号やクラス・文献名と刊行年・科学的数値）。"
            "下のファクトシートと食い違う行、sure=false の話を使っている行は、ファクトシートの確かな事実に差し替える。"
            "『勝つ』『最強』『唯一』『全員』の断定は、反証になる条件（タイプ相性・特性・定番の対策技・例外）まで確かめ、"
            "成り立たなければ条件ごと言うか、成り立つ事実に差し替える。"
            "タイプ相性の倍率を書いた行は、受ける側の2つのタイプそれぞれの倍率を掛け直して確かめる"
            "(例: むし・ゴーストへのいわ技は 2倍×1倍＝2倍。4倍ではない)。メガシンカ後の姿の特性・タイプを通常の姿のものとして書いていないか確かめる。"
            "2つの行が同じ事実を言っていたら、片方をファクトシートの未使用の事実に差し替える。\n"
            "2. 予防線・自己否定（「〜ことがある」「〜とも読める」「〜かもしれない」「定かでない」「諸説ある」「ただし〜でも変わる」）。"
            "ぼかして残さず、その行をファクトシートの確かな事実で言い切る行に書き直す。"
            "伝承・設定は出典を主語にして言い切る（「〇〇には〜と書かれている」）。"
            "テーマや俗説を否定する検証話法（「原典にない」「本文には書かれていない」「確認できない」「答えは一意じゃない」）も、"
            "確かな事実で言い切る行に書き直す。3行目の答えが否定形（「〜ではなく」「空白」「固定なし」）なら、"
            "ファクトシートの肯定形の事実（「〜だ」）を答えにする。\n"
            "3. 1行目・2行目で伏せた謎（言葉・物・理由）が、最終行の前までに中身ごと回収されているか。"
            "されていなければ回収する。1行目の問いとオチの結論が食い違っていないか。\n"
            "4. 同じ事実を言い換えただけの行・たとえ話だけの行・雰囲気だけの行・相槌だけの行を、"
            "まだ使っていない別の事実（ファクトシートから）を持つ行にする。本文に別々の事実が4つ以上あること。\n"
            "5. 1行目の最初の語が題材の固有名か具体物か（「これ知ってた？」「このポケモン」「この妖怪」「このSCP」で始めない）。"
            "定義の読み上げ（「〇〇は、△△するテレビだ」）なら、題材名＋意外な事実／結果の予想できない問い／視聴者を当事者にする言い切り、のどれかに直す。\n"
            "6. 聞き役の行が、解説役より先に答えや新しい事実(前の行に無い数字・書名・仕組みの名前)を言っていないか、"
            "ジャンル外の連想やたとえを言っていないか。聞き役は前の行に出た語だけで、驚く・ツッコむ・視聴者の疑問を代わりに言う。\n"
            "7. 最後の内容行（CTAの直前のオチ）が説明文・但し書き・余韻なら、冒頭に戻る二人称の問いか、"
            "コメントで答えたくなる問いにする。\n"
            "8. 途中で切れた文（「〜なり。」「〜やすく。」）を言い切りにする。最終行（CTA）が36字を超えていたら、"
            "『高評価』と『登録』の語を残したまま36字以内に縮める。\n"
            "守ること: 行数・各行の話者・語り口は変えない。本文だけを返し、[話者] や番号は付けない。"
            "各行の字数は元の±8字以内(1行目は34字以内)。最終行（高評価・登録のCTA）は字数を増やさない。"
            "テーマから外れた話題は足さない。直す必要がない行はそのまま返す。\n"
            + (f"この台本で見つかった予防線: {' / '.join(hedges)}\n" if hedges else "")
            + f"語り口: {voice}\n"
            f"テーマ: {theme.get('title', '')} / 切り口: {theme.get('angle', '')}\n"
            + (f"ファクトシート:\n{sheet_txt}\n" if sheet_txt else "")
            + f"台本:\n{numbered}\n\n"
            '出力はJSONのみ: {"lines": ["1行目の本文", ...], "changes": ["何をなぜ直したか", ...]}'
        )
        raw = self._call_gpt(
            [{"role": "system", "content": "YouTubeショート台本の校閲者。事実確認に厳しい。JSONのみ出力。"},
             {"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=2000, max_retries=2,
        )
        data = self._extract_json(raw)
        new = data.get("lines") if isinstance(data, dict) else None
        if not isinstance(new, list) or len(new) != len(texts):
            print("  ⚠️ short self-review: 行数が変わったので不採用")
            return
        import re as _re
        # 入力に付けた「[話者] 」をそのまま書き戻してくることがあるので剥がす
        new = [_re.sub(r"^\s*(?:\d+\.\s*)?\[[^\]]{1,20}\]\s*", "", str(t)).strip() for t in new]
        last = len(texts) - 1
        # 字数が外れた行だけ元に戻す（第1周は1行でも外れたら全体を捨てていたため、
        # 事実の修正まで一緒に失われていた）。
        reverted: List[int] = []
        for i, (a, b) in enumerate(zip(texts, new)):
            if i == last:
                # CTA は「高評価＋登録で何が届くか」を生成時に作り込んでいる。校閲で
                # 「高評価！登録も！」のように届く物が消えた（第3周の試行で実測）ので、
                # 36字を超えていて縮めるときだけ書き換えを認める。
                if not b or len(a) <= 36 or len(b) > 36:
                    if b != a:
                        new[i] = a
                        reverted.append(i + 1)
                continue
            # 1行目は 15〜34字、本文行は「元±12字」か「18〜36字」に入れば採用（長すぎる行を
            # 縮める修正まで捨てないため）。
            if i == 0:
                bad = not b or not (15 <= len(b) <= 34)
            else:
                bad = not b or not (abs(len(b) - len(a)) <= 12 or 18 <= len(b) <= 36)
            if bad:
                print(f"  ⚠️ short self-review: L{i + 1} は字数が大きく変わったので元に戻す ({len(a)}→{len(b)})")
                new[i] = a
                reverted.append(i + 1)
        try:
            from pipeline import cta_enforcer as _ce
            if not (_ce.has_like(new[-1]) and _ce.has_subscribe(new[-1])):
                print("  ⚠️ short self-review: CTA から高評価/登録が消えたので最終行だけ元に戻す")
                new[-1] = texts[-1]
        except Exception:
            new[-1] = texts[-1]
        changed = [i for i, (a, b) in enumerate(zip(texts, new)) if a != b]
        for i in changed:
            lines[i]["text"] = new[i]
        scenario_data["short_self_review"] = {
            "changed_lines": [i + 1 for i in changed],
            "before": [texts[i] for i in changed],
            "changes": (data.get("changes") or [])[:8],
            "reverted_lines": reverted,
            "hedges_before": hedges,
            "hedges_after": _find_hedges(new[:-1]),
        }
        print(f"  🔍 short self-review: {len(changed)}行を修正 {[i + 1 for i in changed]}")

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
