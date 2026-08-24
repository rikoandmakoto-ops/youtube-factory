"""CTA Rotation System — CTA疲労防止のスタイルローテーション（Round 6）。

狙い:
    毎回「チャンネル登録よろしく！」だけだと視聴者が免疫を持ち、
    CTA効果が減衰する（バナーブラインドネスと同じ現象）。

    6種類のCTAスタイルをローテーションし、各回で異なる行動を促すことで:
    - CTA効果の減衰を防ぐ
    - 登録以外のエンゲージメント（保存・共有・コメント）も獲得
    - YouTubeアルゴリズムが重視する多面的なエンゲージメントを稼ぐ

既存モジュールとの違い:
    - auto_comment: コメント欄に投稿するCTA → シナリオ本文のCTAは対象外
    - scenario_validator._check_cta: CTAの「有無」検証 → スタイルの多様性は見ない
    - description_blocks.build_subscribe_block: 説明文のCTA → シナリオ最終行は対象外
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CTA_HISTORY_DIR = PROJECT_ROOT / "data" / "cta_history"

# CTA スタイル定義
# 各スタイルに複数のテンプレートを用意（{series}はシリーズ名で置換）
CTA_STYLES: Dict[str, Dict[str, Any]] = {
    "subscribe": {
        "label": "チャンネル登録",
        "weight": 3,  # 出現頻度の重み（高いほど多い）
        "templates": {
            "daily-science": [
                "気になった人はチャンネル登録して、明日の科学も見逃さないでね！",
                "この謎、まだまだあるよ。登録して一緒に解明していこう！",
            ],
            "scp-lab": [
                "次のSCPはもっとヤバい。登録して備えておけ。",
                "この財団の記録、まだ続くぞ。チャンネル登録して追え。",
            ],
            "2ch-matome": [
                "もっと面白いスレ見たいやつは登録しとけw",
                "毎日くだらないスレまとめてるから、登録して待っとけやw",
            ],
            "company-facts": [
                "もっとヤバい企業のホンネが知りたい人はチャンネル登録！",
                "次の企業はもっと衝撃的。登録して待っててね。",
            ],
            "pokemon-lab": [
                "まだまだ闇設定あるよ。チャンネル登録して見逃すな！",
                "次のポケモンの裏設定も気になる人は登録しておいてね！",
            ],
            "yokai-watch": [
                "次の妖怪はもっと怖い。登録して確かめてくれ。",
                "まだまだ恐ろしい伝承があるぞ。チャンネル登録して待て。",
            ],
            "akashic-librarian": [
                "この記録はまだ閉じられていない。登録して、続きを読め。",
                "次の記録が開かれるのを、待て。",
            ],
        },
    },
    "like": {
        "label": "高評価",
        "weight": 2,
        "templates": {
            "daily-science": [
                "面白かったら高評価で教えてね！次の科学ネタの参考にする！",
                "「へぇ〜」ってなった人は高評価ポチッとお願い！",
            ],
            "scp-lab": [
                "怖かったやつ、高評価で報告してくれ。",
                "このSCPがヤバいと思ったら高評価で知らせろ。",
            ],
            "2ch-matome": [
                "草生えたやつは高評価で教えてくれw",
                "ワロタって思ったら高評価頼むわw",
            ],
            "company-facts": [
                "参考になったら高評価で教えてください！",
                "この情報ヤバいと思ったら高評価で広めて！",
            ],
            "pokemon-lab": [
                "知らなかった人は高評価で教えてね！",
                "この設定衝撃だった人は高評価ポチッと！",
            ],
            "yokai-watch": [
                "怖かったら高評価で教えてくれ。",
                "この妖怪ヤバいと思ったら高評価で知らせて！",
            ],
            "akashic-librarian": [
                "この記録が気になったなら、高評価で残せ。",
                "真実に近づきたいなら、高評価を。",
            ],
        },
    },
    "save": {
        "label": "保存",
        "weight": 2,
        "templates": {
            "daily-science": [
                "友達に話したくなったら保存しておいてね！",
                "あとで見返したい人は保存ボタンをタップ！",
            ],
            "scp-lab": [
                "この報告書、保存して何度も読み返せ。",
                "後で思い出して怖くなるぞ。保存しておけ。",
            ],
            "2ch-matome": [
                "後で友達に見せたいやつは保存しとけw",
                "これ保存して飲み会のネタにしろやw",
            ],
            "company-facts": [
                "転職活動中の人は保存しておいて！",
                "この情報、保存して周りにも教えてあげて！",
            ],
            "pokemon-lab": [
                "ポケモン好きの友達に見せたい人は保存！",
                "この裏設定、保存してじっくり読み返して！",
            ],
            "yokai-watch": [
                "夜中に見返す勇気があるなら、保存しておけ。",
                "この伝承、保存して他の人にも教えてくれ。",
            ],
            "akashic-librarian": [
                "この記録は、保存しておく価値がある。",
                "忘れないうちに保存を。この記録は消えるかもしれない。",
            ],
        },
    },
    "share": {
        "label": "共有",
        "weight": 1,
        "templates": {
            "daily-science": [
                "「え、マジで？」ってなった人は友達にも共有して！",
                "これ知らなかった人、周りにもシェアしてあげて！",
            ],
            "scp-lab": [
                "一人で怖がるな。友達にも共有して道連れにしろ。",
                "このSCP、友達に送りつけてやれ。",
            ],
            "2ch-matome": [
                "草生えたら友達にも送りつけろやw",
                "これ面白かったら共有してくれw 再生数で生活してるんだわw",
            ],
            "company-facts": [
                "就活中の友達がいたらこの動画を送ってあげて！",
                "この企業の話、知り合いにも共有して！",
            ],
            "pokemon-lab": [
                "ポケモン好きの友達にこの衝撃を共有して！",
                "これ知らない人多いから、友達にも教えてあげて！",
            ],
            "yokai-watch": [
                "怖がりの友達に送りつけてやれ。",
                "この伝承、地元の友達に聞いてみてくれ。共有して！",
            ],
            "akashic-librarian": [
                "この記録を、誰かに伝えてほしい。",
                "一人で抱えるな。共有して、一緒に考えてくれ。",
            ],
        },
    },
    "comment": {
        "label": "コメント",
        "weight": 2,
        "templates": {
            "daily-science": [
                "他にも気になる「なんで？」があったらコメントで教えて！",
                "あなたの日常の謎もコメントで聞かせて！次の動画にするかも！",
            ],
            "scp-lab": [
                "次に解説してほしいSCPをコメントで教えてくれ。",
                "このSCPの解釈、コメントで聞かせてくれ。",
            ],
            "2ch-matome": [
                "似たような体験あるやつはコメントで聞かせてくれやw",
                "お前らの感想コメントで聞かせろやw",
            ],
            "company-facts": [
                "実際にこの企業で働いてた人、コメントでリアルを教えて！",
                "次にどの企業を暴いてほしいかコメントで教えて！",
            ],
            "pokemon-lab": [
                "他にも知りたい裏設定があったらコメントで教えて！",
                "推しポケモンの闇設定も知りたい人はコメントで！",
            ],
            "yokai-watch": [
                "あなたの地域にも似た伝承があったらコメントで教えて！",
                "次に調べてほしい妖怪をコメントで教えてくれ。",
            ],
            "akashic-librarian": [
                "この記録について、あなたの解釈をコメントで教えてほしい。",
                "次に開くべき記録があれば、コメントで伝えてくれ。",
            ],
        },
    },
    "notify": {
        "label": "通知ON",
        "weight": 1,
        "templates": {
            "daily-science": [
                "通知をONにしておけば、明日の科学も見逃さないよ！",
                "ベルマーク押して通知ONにしておいてね！毎日投稿してるよ！",
            ],
            "scp-lab": [
                "通知ONにしておけ。次の報告書がいつ公開されるか分からないぞ。",
                "ベルマークを押せ。次のSCPを見逃すな。",
            ],
            "2ch-matome": [
                "通知ONにしとけば毎日笑えるぞw",
                "ベルマーク押しとけw 毎日くだらないスレまとめてるからw",
            ],
            "company-facts": [
                "通知ONで、次の企業の暴露も見逃さないで！",
                "ベルマークONにしておいてください！次回はもっとヤバい企業です！",
            ],
            "pokemon-lab": [
                "通知ONにして、次の闇設定も見逃すな！",
                "ベルマーク押しておいてね！次のポケモンはもっとヤバいよ！",
            ],
            "yokai-watch": [
                "通知ONにしておけ。次の妖怪はもっと恐ろしい。",
                "ベルマークを押して、次の伝承に備えろ。",
            ],
            "akashic-librarian": [
                "通知をONにせよ。次の記録が開かれる日は、誰にも分からない。",
                "ベルマークを押しておけ。この記録庫は、まだ閉じていない。",
            ],
        },
    },
}


# =====================================================================
# 履歴管理
# =====================================================================

def _history_path(channel_id: str) -> Path:
    return CTA_HISTORY_DIR / f"{channel_id}.json"


def _load_history(channel_id: str) -> List[Dict[str, str]]:
    path = _history_path(channel_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_history(channel_id: str, history: List[Dict[str, str]]) -> None:
    CTA_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _history_path(channel_id)
    # 直近30件のみ保持
    trimmed = history[-30:]
    path.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def _recent_styles(channel_id: str, n: int = 5) -> List[str]:
    """直近n件で使ったCTAスタイルを取得。"""
    history = _load_history(channel_id)
    return [h.get("style", "") for h in history[-n:]]


# =====================================================================
# ローテーション選択
# =====================================================================

def _select_style(channel_id: str) -> str:
    """最近使っていないCTAスタイルを重み付きで選択。"""
    recent = _recent_styles(channel_id, n=5)

    # 各スタイルの選択確率を計算
    candidates: List[tuple] = []
    for style_id, style_def in CTA_STYLES.items():
        base_weight = style_def.get("weight", 1)

        # 直近で使ったスタイルは重みを下げる
        recency_penalty = 0
        for i, used in enumerate(reversed(recent)):
            if used == style_id:
                recency_penalty = max(recency_penalty, 5 - i)  # 直近ほど重いペナルティ

        adjusted = max(0.1, base_weight - recency_penalty)
        candidates.append((style_id, adjusted))

    # 重み付きランダム選択
    styles = [c[0] for c in candidates]
    weights = [c[1] for c in candidates]
    return random.choices(styles, weights=weights, k=1)[0]


def _pick_template(style_id: str, channel_id: str) -> str:
    """スタイルとチャンネルに基づいてテンプレートを選択。"""
    style_def = CTA_STYLES.get(style_id, CTA_STYLES["subscribe"])
    templates = style_def.get("templates", {})
    pool = templates.get(channel_id, templates.get("daily-science", ["チャンネル登録よろしく！"]))
    return random.choice(pool)


# =====================================================================
# メインエントリポイント
# =====================================================================

def rotate_cta(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
    series_name: str = "",
) -> Dict[str, Any]:
    """CTAスタイルをローテーションし、最終行のCTAを差し替える。

    Args:
        short_scenario: シナリオ行リスト。
        channel_id: チャンネルID。
        series_name: シリーズ名（あれば含める）。

    Returns:
        {
            "modified": bool,
            "style": str,            # 選択されたスタイル
            "original_cta": str,     # 元のCTA
            "new_cta": str,          # 新しいCTA
        }
    """
    if not short_scenario:
        return {"modified": False, "reason": "empty_scenario"}

    # 最終行を探す（CTAパターンに合致する行）
    last_idx = len(short_scenario) - 1
    last_entry = short_scenario[last_idx]
    text_key = "text" if "text" in last_entry else "line"
    original_cta = (last_entry.get(text_key) or "").strip()

    # CTAパターンに合致しない場合はスキップ
    is_cta = bool(re.search(
        r"チャンネル登録|登録.*よろしく|フォロー|登録.*待|見逃さない",
        original_cta,
    ))
    if not is_cta:
        return {"modified": False, "reason": "last_line_is_not_cta"}

    # スタイル選択
    style_id = _select_style(channel_id)
    new_cta = _pick_template(style_id, channel_id)

    # シリーズ名があれば先頭に追加
    if series_name:
        new_cta = f"{series_name}シリーズ、{new_cta}"

    # 差し替え
    last_entry[text_key] = new_cta

    # 履歴に記録
    history = _load_history(channel_id)
    history.append({
        "style": style_id,
        "cta": new_cta[:80],
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    _save_history(channel_id, history)

    label = CTA_STYLES[style_id]["label"]
    print(f"  🔄 CTARotator [{channel_id}]: {label}型 → {new_cta[:40]}…")

    return {
        "modified": True,
        "style": style_id,
        "style_label": label,
        "original_cta": original_cta,
        "new_cta": new_cta,
    }


def get_cta_hint_for_prompt(channel_id: str) -> str:
    """プロンプトに追加するCTAスタイルヒント。

    生成時に「今回はこのスタイルのCTAにして」と指示するためのテキスト。
    generate() のプロンプト組み立て時に使う。
    """
    style_id = _select_style(channel_id)
    label = CTA_STYLES[style_id]["label"]

    hint_map = {
        "subscribe": "今回の最終行CTAは「チャンネル登録」を促す形にして。",
        "like": "今回の最終行CTAは「高評価」を促す形にして。「いいね」「高評価」を自然に入れる。",
        "save": "今回の最終行CTAは「保存」を促す形にして。「保存」「あとで見返す」を自然に入れる。",
        "share": "今回の最終行CTAは「共有」を促す形にして。「友達に送る」「シェア」を自然に入れる。",
        "comment": "今回の最終行CTAは「コメント」を促す形にして。意見や体験を聞く形。",
        "notify": "今回の最終行CTAは「通知ON」を促す形にして。「ベルマーク」「通知」を自然に入れる。",
    }

    return hint_map.get(style_id, hint_map["subscribe"])
