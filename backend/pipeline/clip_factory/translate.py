"""海外バイラル動画の日本語化（翻訳・フック文・最終安全判定）を Claude に任せる。

════════════════════════════════════════════════════════════════════
■ なぜ Claude 固定なのか
════════════════════════════════════════════════════════════════════

運用ルールで **台本・テキスト生成は Claude**（OpenAI API は画像生成のみ）と
決まっている。切り抜きの字幕とフック文は「台本」そのものなので、ここは
Claude 以外にフォールバックしない。`segments.refine_with_claude` は歴史的経緯で
GPT へ落ちるが、このモジュールは落ちない。Claude が使えなければ **止める**。

止めるのは意地ではなく実利で、翻訳を機械的なフォールバック（辞書置換など）で
埋めると、意味の通らない日本語字幕が付いた動画がそのまま公開される。
「その日1本落とす」より損害が大きい。

════════════════════════════════════════════════════════════════════
■ 3段目の安全ゲート
════════════════════════════════════════════════════════════════════

  1段目 viral_sources.apply_gate   … NSFW フラグ・タイトルの禁止語
  2段目 engines/viral の書き起こしゲート … 発話内容の禁止語
  3段目 ここ                        … 文脈を読んだ Claude の判定

1・2段は正規表現なので「言葉は綺麗だが映像・文脈がアウト」を拾えない。
Claude には**翻訳のついでに** YouTube のコミュニティガイドライン観点で
可否を返させる。これは追加コストがほぼゼロで効く（同じ1回の呼び出し）。

════════════════════════════════════════════════════════════════════
■ 失敗したら再試行する（スキップしない）
════════════════════════════════════════════════════════════════════

2026-08-30 の運用決定で **翻訳の失敗はスキップせず再試行**する。
`call_claude_json` は例外を投げずに None を返す設計なので、None を「失敗」と
みなして `TRANSLATE_MAX_ATTEMPTS` 回まで指数バックオフで叩き直す
（1回目の待機 `TRANSLATE_BACKOFF_BASE_SEC` 秒 → 2倍 → 4倍…）。

効くのは 429（レート制限）・529（overloaded）・タイムアウト・JSON が壊れて
返ってきた場合。逆に **待っても直らない失敗では即座に打ち切る**
（キー未設定・認証エラー・クレジット残高不足）。これらで3回待つと、
autopilot のスロットを何十秒も無駄に塞ぐだけで結果は同じになる。

════════════════════════════════════════════════════════════════════
■ それでも Claude が使えないとき
════════════════════════════════════════════════════════════════════

再試行を使い切ったら `TranslationUnavailable` を投げ、
併せて **依頼書を `data/analytics/viral_translation_pending/` に書き出す**。
Claude Code のセッション（＝API キー不要の Claude 系統）から後追いで
埋められるようにするため。`load_pending_result` がその結果を読み戻す。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .asr import SpeechSegment
from .sources import PROJECT_ROOT

#: Claude が使えないときの依頼書置き場（人／Claude Code セッションが埋める）
PENDING_DIR = PROJECT_ROOT / "data" / "analytics" / "viral_translation_pending"

#: フック帯は 13文字 × 2〜3行（renderer_overseas.OverseasLayout）。読み切れる上限。
HOOK_CHAR_LIMIT = 28
#: 字幕1行の目安。renderer が実測で折り返すので、ここは「1チャンクの上限」。
SUBTITLE_CHAR_LIMIT = 34

#: 翻訳呼び出しの試行回数（初回 + リトライ2回）。
TRANSLATE_MAX_ATTEMPTS = 3
#: 指数バックオフの基準秒。2回目は ×2、3回目は ×4 待つ。
TRANSLATE_BACKOFF_BASE_SEC = 4.0


class TranslationUnavailable(RuntimeError):
    """Claude を呼べなかった（キー未設定・認証エラー・残高不足など）。"""


class TranslationRejected(RuntimeError):
    """Claude が「公開すべきでない」と判定した。"""


@dataclass
class TranslatedLine:
    index: int
    start: float
    end: float
    text_ja: str
    text_src: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "start": round(self.start, 3),
                "end": round(self.end, 3), "ja": self.text_ja,
                "src": self.text_src}


@dataclass
class TranslatedClip:
    hook: str
    lines: List[TranslatedLine] = field(default_factory=list)
    title_ja: str = ""
    summary: str = ""
    safety_ok: bool = True
    safety_reason: str = ""
    source: str = "claude"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hook": self.hook,
            "title_ja": self.title_ja,
            "summary": self.summary,
            "safety_ok": self.safety_ok,
            "safety_reason": self.safety_reason,
            "source": self.source,
            "lines": [l.to_dict() for l in self.lines],
        }


# ---------------------------------------------------------------------
# プロンプト
# ---------------------------------------------------------------------

_SYSTEM = (
    "あなたは海外のバイラル動画を日本語のショート動画に仕立てる編集者。"
    "翻訳は直訳せず、日本語のショート字幕として一読で意味が通る言い回しにする。"
    "同時に、その動画を YouTube に公開してよいかを厳しめに判定する。"
)


def _build_prompt(
    lines: Sequence[SpeechSegment],
    *,
    source_title: str,
    community: str,
    style_rules: Sequence[str],
    hook_limit: int,
    subtitle_limit: int,
    silent: bool,
) -> str:
    payload = [
        {"id": s.index, "start": round(s.start, 1),
         "sec": round(s.duration, 1), "text": s.text}
        for s in lines
    ]
    rules = "\n".join(f"- {r}" for r in style_rules if str(r).strip())

    body = [
        "海外の話題動画を日本語字幕付きのショート動画にします。",
        f"元タイトル（原語）: {source_title}",
        f"元の投稿元: {community or '不明'}",
        "",
    ]
    if silent:
        body += [
            "この動画には**音声（発話）がありません**。映像だけで見せる動画です。",
            "元タイトルから内容を読み取り、フック文だけを作ってください。",
            "発話が無いので lines は空配列で返してください。",
        ]
    else:
        body += [
            "以下は音声認識（Whisper）で起こした発話です。誤認識が混じります。",
            "文脈から明らかな誤認識は自然な形に直して構いませんが、"
            "**発言者が言っていない内容を足すことは禁止**です。",
            "",
            json.dumps(payload, ensure_ascii=False),
            "",
            "各 id について日本語字幕を作ってください。条件:",
            f"- 1件あたり全角{subtitle_limit}文字以内。長い発話は要点に絞る。",
            "- 話し言葉。硬い翻訳調にしない。",
            "- 意味の取れない誤認識だらけの id は ja を空文字にする（字幕を出さない）。",
        ]

    body += [
        "",
        "フック文（画面上部に常時出す1文）の条件:",
        f"- 全角{hook_limit}文字以内。",
        "- 何が起きる動画なのかを言い切る。疑問形にしない。",
        "- 釣りではなく、実際に映っていることを書く。",
        "- 過度に性的・下品な語を使わない（YouTube の広告に不利なため）。",
    ]
    if rules:
        body += ["", "チャンネル固有のルール:", rules]

    body += [
        "",
        "最後に安全判定をしてください。次のいずれかに当たるなら safety_ok=false:",
        "- 性行為・性器・裸体の露出、それを示唆する行為が映っている",
        "- 未成年が性的な文脈で扱われている",
        "- 流血・死体・暴力・事故被害者が映っている",
        "- 特定個人への攻撃・晒し・差別的表現",
        "- 本人の同意なく撮影されたと明らかに分かる盗撮的な内容",
        "判断に迷ったら safety_ok=false にしてください（公開しない方が安全）。",
        "",
        "次の JSON のみを返す:",
        '{"hook": "", "title_ja": "", "summary": "", "safety_ok": true, '
        '"safety_reason": "", "lines": [{"id": 0, "ja": ""}]}',
    ]
    return "\n".join(body)


# ---------------------------------------------------------------------
# 依頼書（Claude API が使えないとき）
# ---------------------------------------------------------------------

def write_pending_request(
    request_id: str,
    *,
    prompt: str,
    meta: Dict[str, Any],
) -> Path:
    """Claude Code セッションから埋められる依頼書を書き出す。"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    path = PENDING_DIR / f"{request_id}.json"
    path.write_text(json.dumps({
        "request_id": request_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "system": _SYSTEM,
        "prompt": prompt,
        "meta": meta,
        "result": None,
        "_how_to_fill": (
            "Claude Code のセッションで prompt を読み、指示どおりの JSON を "
            "result に入れて保存すると、次回の実行がこれを拾って続きから作ります。"
        ),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_pending_result(request_id: str) -> Optional[Dict[str, Any]]:
    """依頼書に結果が書き込まれていれば返す。"""
    path = PENDING_DIR / f"{request_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    result = data.get("result")
    return result if isinstance(result, dict) else None


# ---------------------------------------------------------------------
# 本体
# ---------------------------------------------------------------------

def _tidy_hook(text: str, limit: int) -> str:
    """改行や連続空白を潰す。

    フック文はタイトルにも流用される（pipeline.build_title）。改行が残ると
    YouTube API がタイトルを弾く。
    """
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _parse_result(
    res: Dict[str, Any],
    lines: Sequence[SpeechSegment],
    *,
    hook_limit: int,
    subtitle_limit: int,
    source: str,
) -> TranslatedClip:
    by_index = {s.index: s for s in lines}
    out_lines: List[TranslatedLine] = []
    for row in (res.get("lines") or []):
        try:
            idx = int(row.get("id"))
        except Exception:
            continue
        seg = by_index.get(idx)
        if seg is None:
            continue
        ja = re.sub(r"\s+", " ", str(row.get("ja") or "")).strip()
        if not ja:
            continue
        out_lines.append(TranslatedLine(
            index=len(out_lines), start=seg.start, end=seg.end,
            text_ja=ja[:subtitle_limit * 3], text_src=seg.text,
        ))

    return TranslatedClip(
        hook=_tidy_hook(res.get("hook"), hook_limit),
        lines=out_lines,
        title_ja=_tidy_hook(res.get("title_ja"), 90),
        summary=str(res.get("summary") or "").strip(),
        safety_ok=bool(res.get("safety_ok", True)),
        safety_reason=str(res.get("safety_reason") or "").strip(),
        source=source,
    )


def translate_clip(
    lines: Sequence[SpeechSegment],
    *,
    source_title: str,
    community: str = "",
    channel_id: str = "clip-lab",
    style_rules: Sequence[str] = (),
    hook_limit: int = HOOK_CHAR_LIMIT,
    subtitle_limit: int = SUBTITLE_CHAR_LIMIT,
    request_id: Optional[str] = None,
) -> TranslatedClip:
    """発話を日本語字幕・フック文にして、安全判定まで返す。

    Raises:
        TranslationUnavailable: Claude を呼べなかった（依頼書は書き出す）。
        TranslationRejected: Claude が公開不可と判定した。
    """
    silent = not lines
    prompt = _build_prompt(
        lines, source_title=source_title, community=community,
        style_rules=style_rules, hook_limit=hook_limit,
        subtitle_limit=subtitle_limit, silent=silent,
    )
    request_id = request_id or f"viral_{int(time.time())}"

    # 先に「後から埋められた依頼書」を見る。前回 Claude が使えずに止まった分を
    # 人／Claude Code が埋めていれば、そのまま続きから作れる。
    pending = load_pending_result(request_id)
    if pending:
        clip = _parse_result(pending, lines, hook_limit=hook_limit,
                             subtitle_limit=subtitle_limit, source="pending")
    else:
        res = _call_claude_with_retry(prompt, channel_id)
        if res is None:
            path = write_pending_request(request_id, prompt=prompt, meta={
                "source_title": source_title, "community": community,
                "channel_id": channel_id, "line_count": len(lines),
                "attempts": TRANSLATE_MAX_ATTEMPTS,
            })
            raise TranslationUnavailable(
                f"{_claude_reason()}（{TRANSLATE_MAX_ATTEMPTS} 回試行）。"
                f"翻訳を機械任せにすると意味の通らない字幕が"
                f"そのまま公開されるので中止します。依頼書: {path}")
        clip = _parse_result(res, lines, hook_limit=hook_limit,
                             subtitle_limit=subtitle_limit, source="claude")

    if not clip.safety_ok:
        raise TranslationRejected(
            f"Claude の安全判定で公開不可: {clip.safety_reason or '理由未記載'}")
    if not clip.hook:
        raise TranslationUnavailable(
            "Claude からフック文が返りませんでした（hook が空）")
    return clip


def _call_claude(prompt: str, channel_id: str) -> Optional[Dict[str, Any]]:
    try:
        from pipeline import claude_client  # type: ignore
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None
    return claude_client.call_claude_json(
        system=_SYSTEM, user=prompt, temperature=0.4, max_tokens=4000,
        channel_id=channel_id, purpose="viral_clip_translation",
    )


#: 待っても直らない失敗。ここに当たったら再試行せず即座に諦める。
_PERMANENT_FAILURES = (
    "未設定",              # ANTHROPIC_API_KEY が無い
    "sdk 未導入",          # anthropic パッケージが入っていない
    "認証エラー",          # キーが無効
    "残高不足",            # クレジット切れ
)


def _is_retryable() -> bool:
    """直近の失敗理由を見て、待って叩き直す価値があるかを判定する。"""
    reason = (_claude_reason() or "").lower()
    return not any(marker in reason for marker in _PERMANENT_FAILURES)


def _call_claude_with_retry(
    prompt: str,
    channel_id: str,
    *,
    max_attempts: int = TRANSLATE_MAX_ATTEMPTS,
    base_sleep: float = TRANSLATE_BACKOFF_BASE_SEC,
    sleep: Any = time.sleep,
) -> Optional[Dict[str, Any]]:
    """Claude を指数バックオフで叩き直す。全部失敗したら None。

    翻訳の失敗はスキップせず再試行する（2026-08-30 の運用決定）。1本落とすと
    その日の枠が丸ごと消えるが、429 や 529 は数秒待てば通ることが多い。

    Args:
        sleep: テストから待ち時間を潰すための注入口。既定は `time.sleep`。
    """
    for attempt in range(1, max_attempts + 1):
        res = _call_claude(prompt, channel_id)
        if res is not None:
            if attempt > 1:
                print(f"  ✅ 翻訳リトライ成功（{attempt}/{max_attempts} 回目）")
            return res
        reason = _claude_reason()
        if not _is_retryable():
            print(f"  ⛔ 翻訳を再試行しません（待っても直らない失敗）: {reason}")
            return None
        if attempt >= max_attempts:
            break
        wait = base_sleep * (2 ** (attempt - 1))
        print(f"  ⏳ 翻訳に失敗（{attempt}/{max_attempts}）: {reason} "
              f"→ {wait:.0f}秒待って再試行")
        sleep(wait)
    return None


def _claude_reason() -> str:
    try:
        from pipeline import claude_client  # type: ignore
        return claude_client.unavailable_reason() or "Claude を呼べませんでした"
    except Exception:
        return "claude_client を読み込めません"
