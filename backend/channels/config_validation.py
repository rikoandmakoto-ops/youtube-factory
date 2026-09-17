"""チャンネル設定（data/channels/*.json）の整合性チェック。

過去の事故:
    scp-lab の publish_settings.default_privacy が "private" のまま放置され、
    フルオート（autopilot）で投稿されたショートが全部 *非公開* になっていた。
    投稿は成功しているように見えるのに誰にも届かない、という気付きにくいミス。

このモジュールは「フルオート有効 × 非公開設定」のような *矛盾した組み合わせ* を
一箇所で検知する。読み込み時（ChannelManager.reload）・ヘルスチェック（/health）・
設定変更API（autopilot 有効化）の3経路から呼び出して再発を防ぐ。

純粋関数のみ。FastAPI 等への依存を持たないので単体テストしやすい。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# YouTube が受け付ける公開ステータス
VALID_PRIVACY = ("public", "private", "unlisted")

# YouTube ショートの推奨解像度（9:16）。パイプラインもこの値で描画している。
SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920

# レベル
LEVEL_ERROR = "error"      # 放置すると確実に事故る（投稿が非公開になる等）
LEVEL_WARNING = "warning"  # 意図的かもしれないが要確認


@dataclass
class ConfigIssue:
    """1件の整合性問題。"""

    channel_id: str
    level: str          # LEVEL_ERROR | LEVEL_WARNING
    code: str           # 機械可読なコード（テスト・UI判定用）
    message: str        # 人間向けの説明（日本語）
    field: Optional[str] = None  # 問題のあるフィールドパス
    fix: Optional[str] = None    # 推奨される直し方

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "fix": self.fix,
        }

    @property
    def is_error(self) -> bool:
        return self.level == LEVEL_ERROR


def is_autopilot_enabled(raw: Dict[str, Any]) -> bool:
    """フルオートが有効か。"""
    return bool((raw.get("autopilot") or {}).get("enabled"))


def get_default_privacy(raw: Dict[str, Any]) -> str:
    """publish_settings.default_privacy（欠損時は public）。"""
    ps = raw.get("publish_settings") or {}
    return ps.get("default_privacy") or "public"


def validate_channel_config(
    raw: Dict[str, Any], channel_id: Optional[str] = None
) -> List[ConfigIssue]:
    """1チャンネル分の生JSON（dict）を検証して問題リストを返す。

    raw: data/channels/<id>.json をパースした dict
    channel_id: 明示したいとき。省略時は raw["id"]。
    """
    cid = channel_id or raw.get("id") or "?"
    issues: List[ConfigIssue] = []

    privacy = get_default_privacy(raw)
    autopilot_on = is_autopilot_enabled(raw)

    # 1) そもそも privacy 値が不正
    if privacy not in VALID_PRIVACY:
        issues.append(
            ConfigIssue(
                channel_id=cid,
                level=LEVEL_ERROR,
                code="invalid_privacy",
                message=(
                    f"default_privacy が不正な値です: '{privacy}' "
                    f"(有効: {', '.join(VALID_PRIVACY)})"
                ),
                field="publish_settings.default_privacy",
                fix="publish_settings.default_privacy を 'public' に設定してください",
            )
        )
        # 値が不正なら以降の組み合わせ判定はスキップ（誤検知防止）
        return issues

    # 2) フルオート有効 × 非公開 = 事故（投稿が誰にも届かない）
    if autopilot_on and privacy == "private":
        issues.append(
            ConfigIssue(
                channel_id=cid,
                level=LEVEL_ERROR,
                code="autopilot_private",
                message=(
                    "フルオート（autopilot）が有効なのに default_privacy が 'private' です。"
                    "自動投稿された動画がすべて非公開になります。"
                ),
                field="publish_settings.default_privacy",
                fix="publish_settings.default_privacy を 'public' に変更してください",
            )
        )

    # 3) フルオート有効 × 限定公開 = 多くの場合は意図しない（要確認）
    if autopilot_on and privacy == "unlisted":
        issues.append(
            ConfigIssue(
                channel_id=cid,
                level=LEVEL_WARNING,
                code="autopilot_unlisted",
                message=(
                    "フルオート（autopilot）が有効で default_privacy が 'unlisted'（限定公開）です。"
                    "自動投稿された動画はリンクを知る人しか見られません。意図的か確認してください。"
                ),
                field="publish_settings.default_privacy",
                fix="一般公開したい場合は publish_settings.default_privacy を 'public' に変更してください",
            )
        )

    # 4) ショートの解像度が 1080x1920 (9:16) でない
    #    YouTube がショート棚に載せる条件は「縦長（アスペクト比 <= 1）かつ 3分以内」。
    #    1080x1920 から外れると横帯が入ったり画質が落ちたりして初速が死ぬ。
    res = (raw.get("video_format") or {}).get("resolution") or {}
    sw = res.get("short_width", SHORT_WIDTH)
    sh = res.get("short_height", SHORT_HEIGHT)
    if (sw, sh) != (SHORT_WIDTH, SHORT_HEIGHT):
        issues.append(
            ConfigIssue(
                channel_id=cid,
                level=LEVEL_WARNING,
                code="short_resolution",
                message=(
                    f"ショートの解像度が {sw}x{sh} です "
                    f"(推奨: {SHORT_WIDTH}x{SHORT_HEIGHT} = 9:16)。"
                    "縦長比率から外れるとショート棚に載らない可能性があります。"
                ),
                field="video_format.resolution.short_width / short_height",
                fix=(
                    f"video_format.resolution.short_width={SHORT_WIDTH}, "
                    f"short_height={SHORT_HEIGHT} に設定してください"
                ),
            )
        )

    # 5) theme_seeds に dict でない要素（素の文字列）が混ざっている
    #    読み込み側（ChannelManager.normalize_theme_seeds）が吸収するので動作は
    #    止まらないが、JSON を直す合図として必ず見えるようにする。09-11 に
    #    daily-science 6件 / scp-lab 3件がこれで suggest_themes を落としていた。
    seeds = raw.get("theme_seeds")
    if seeds is not None and not isinstance(seeds, list):
        issues.append(ConfigIssue(
            channel_id=cid, level=LEVEL_WARNING, code="theme_seeds_not_list",
            message=f"theme_seeds がリストではありません（{type(seeds).__name__}）。無視されます。",
            field="theme_seeds",
            fix='theme_seeds を [{"title": "...", "angle": "..."}] の配列にしてください',
        ))
    elif isinstance(seeds, list):
        bad = [i for i, s in enumerate(seeds)
               if not (isinstance(s, dict) and str(s.get("title") or "").strip())]
        if bad:
            issues.append(ConfigIssue(
                channel_id=cid, level=LEVEL_WARNING, code="theme_seeds_shape",
                message=(f"theme_seeds の {len(bad)} 件が {{\"title\": ...}} 形式ではありません"
                         f"（index: {bad[:6]}）。文字列は読み込み時に dict へ正規化されます。"),
                field="theme_seeds",
                fix='各要素を {"title": "...", "angle": "..."} の dict にしてください',
            ))

    # 6) theme_seeds / autopilot.theme_queue が theme_blacklist と衝突している
    #    衝突した seed は pop 時の最終ゲートで**無言で捨てられる**（枠が空撃ちに
    #    なるだけでエラーは出ない）。設定した本人が気づけるよう読み込み時に出す。
    #    照合は実運用と同じ blacklist_match（re:/= 接頭辞・数字境界も同一規則）。
    blacklist = raw.get("theme_blacklist") or []
    if isinstance(blacklist, list) and blacklist:
        try:
            from pipeline.auto_scenario.theme_dedup import blacklist_match
        except Exception:
            blacklist_match = None  # 単体テスト等で pipeline が無い環境は黙って省略
        if blacklist_match is not None:
            def _titles(items):
                out = []
                for s in (items or []):
                    if isinstance(s, dict):
                        t = str(s.get("title") or "").strip()
                    else:
                        t = str(s or "").strip()
                    if t:
                        out.append(t)
                return out

            for field_name, titles in (
                ("theme_seeds", _titles(seeds if isinstance(seeds, list) else [])),
                ("autopilot.theme_queue",
                 _titles((raw.get("autopilot") or {}).get("theme_queue"))),
            ):
                hits = []
                for t in titles:
                    try:
                        term = blacklist_match(t, blacklist)
                    except Exception:
                        continue
                    if term:
                        hits.append((t, term))
                if hits:
                    sample = " / ".join(f"「{t}」←『{term}』" for t, term in hits[:3])
                    issues.append(ConfigIssue(
                        channel_id=cid, level=LEVEL_WARNING,
                        code="seed_blacklist_collision",
                        message=(f"{field_name} の {len(hits)} 件が theme_blacklist に"
                                 f"該当します（pop 時に無言で捨てられ、枠が空撃ちに"
                                 f"なります）: {sample}"),
                        field=field_name,
                        fix="seed を差し替えるか、theme_blacklist の該当語を見直してください",
                    ))

    return issues


def validate_channels(
    raws: List[Dict[str, Any]],
) -> List[ConfigIssue]:
    """複数チャンネルをまとめて検証。"""
    issues: List[ConfigIssue] = []
    for raw in raws:
        issues.extend(validate_channel_config(raw))
    return issues


def summarize(issues: List[ConfigIssue]) -> Dict[str, Any]:
    """ヘルスチェック等で返しやすい形に要約。"""
    errors = [i for i in issues if i.level == LEVEL_ERROR]
    warnings = [i for i in issues if i.level == LEVEL_WARNING]
    return {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": [i.to_dict() for i in issues],
    }
