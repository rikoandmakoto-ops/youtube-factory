"""切り抜き元素材の調達。

現行の `sources.py` は **自社チャンネルの長尺 mp4 がローカルに残っていること**を
前提にしていて、在庫は自社の過去動画に限られる。本モジュールはそこに
**外部からの素材調達**を足す。

════════════════════════════════════════════════════════════════════
■ 大前提：ライセンスゲート（ここを飛ばすと権利侵害になる）
════════════════════════════════════════════════════════════════════

「YouTube のトレンド動画やニュースを切り抜く」は、**そのままやると著作権侵害**。
YouTube の標準ライセンス（`youtube` = All Rights Reserved）の動画を切り出して
自チャンネルに再アップロードする行為は、二次利用の許諾が無い限り違法であり、
実務上も Content ID による収益剥奪・著作権警告・チャンネル削除に直結する。
報道映像は特に権利者の追及が厳しい。

そこで本モジュールは、調達した候補を必ず2つに仕分ける。

  clippable  … 切り抜いて再アップロードしてよい
                - `creativeCommon` ライセンス（CC BY）の YouTube 動画
                - 自社チャンネルの動画
                - 明示的に許諾済みとして allowlist に登録したチャンネル
  theme_only … 切り抜いてはいけない。**題材（テーマ）としてだけ使う**
                - 標準ライセンスのトレンド動画・ニュース

════════════════════════════════════════════════════════════════════
■ 許諾文言ゲート（allowlist を「信用」で終わらせない）
════════════════════════════════════════════════════════════════════

allowlist は「このチャンネルは許諾済み」と人間が宣言する仕組みなので、
それだけだと宣言が正しいかを機械が確かめられない。そこで allowlist の各
エントリに `permission_phrases` を持たせ、**その動画自身の説明欄に許諾文言が
実在すること**を追加条件にする（既定で必須）。

    岡田斗司夫ゼミ … 説明欄に「この動画の切り抜きを黙認します」
    ひろゆき      … 説明欄に「切り抜き用にガジェ通クリエイターベータベース…」

こうすると「チャンネル単位では許諾していても、この回だけゲスト権利の都合で
文言を外している」といったケースを自動で拾って除外できる。判定に使った文言は
`reason` に残るので、後から監査できる。

メール等で個別に許諾を得た場合は説明欄に文言が無いので、その entry だけ
`require_permission_phrase: false` にして `permission_note` に根拠を書く。

`theme_only` の候補は動画としては一切触らず、「今この話題が伸びている」という
シグナルとしてテーマキューに流す。これなら権利問題なしにトレンドを取り込める。
切り抜きラボの `content_policy.guidelines`（「切り抜き元は自社チャンネルの動画に
限定する」）とも矛盾しない — 自社動画 + CC + 許諾済みだけが素材になる。

════════════════════════════════════════════════════════════════════
■ 調達経路
════════════════════════════════════════════════════════════════════

| 経路 | API | 既定の扱い |
| --- | --- | --- |
| 急上昇 | `videos.list(chart=mostPopular, regionCode=JP)` | theme_only |
| CC検索 | `search.list(videoLicense=creativeCommon)` | clippable |
| 許諾済みch | `search.list(channelId=...)` | clippable（allowlist 記載時のみ） |
| 自社ch | `sources.discover_sources` | clippable |

ダウンロードは `yt_dlp`（Python モジュール）を使う。CLI バイナリは PATH に
無くてもモジュールが入っていれば動く。

════════════════════════════════════════════════════════════════════
■ チャンネル JSON での設定例
════════════════════════════════════════════════════════════════════

```jsonc
"clip": {
  "external_sources": {
    "enabled": false,              // 既定 off。自社動画だけで回っている間は不要
    "region_code": "JP",
    "max_candidates": 25,
    "min_duration_sec": 180,
    "max_duration_sec": 3600,
    "download_dir": null,          // 既定 <OUTPUT_BASE>/_clip_sources
    "trending": {
      "enabled": true,
      "category_ids": ["28", "24"],  // 科学技術 / エンタメ
      "use_as": "theme_only"
    },
    "creative_commons": {
      "enabled": true,
      "queries": ["科学 解説", "宇宙 ドキュメンタリー"],
      "use_as": "clippable"
    },
    "allowlist_channels": [
      {
        "channel_id": "UC...",
        "name": "許諾済みch",
        "permission_phrases": ["この動画の切り抜きを黙認します"],
        "permission_note": "2026-08-21 公式動画の説明欄で確認",
        "permission_source_url": "https://www.youtube.com/watch?v=...",
        "credit_name": "○○チャンネル"
      }
    ]
  }
}
```
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .sources import PROJECT_ROOT

#: 調達した外部素材の置き場（自社出力と混ざらないように分ける）
#:
#: ⚠️ **~/Desktop の下に置いてはいけない。** OUTPUT_BASE は既定で
#: ~/Desktop/動画出力用 だが、macOS の TCC は launchd 配下のプロセスに対して
#: Desktop へのアクセスを拒否する。しかも yt-dlp は映像と音声の結合に ffmpeg
#: （Homebrew の別バイナリ）を使うため、許可ダイアログを出せない launchd 下では
#: **エラーも出さずに永久にハングする**（renderer 側で実測済み: CPU 0.02 秒の
#: まま15分以上）。手で叩くと通るので「autopilot だけ静かに死ぬ」形になる。
#: そのため ~/Movies（TCC 保護外）を既定にする。`external_sources.download_dir`
#: で上書きできる。
DEFAULT_DOWNLOAD_DIR = Path(
    os.environ.get("CLIP_EXTERNAL_DOWNLOAD_DIR")
    or (Path.home() / "Movies" / "yf_clip_downloads")
)

#: 調達履歴（同じ動画を何度も落とさない）
ACQUISITION_STATE = PROJECT_ROOT / "data" / "analytics" / "clip_acquisition.json"

#: YouTube が返すライセンス値。creativeCommon 以外は再利用不可とみなす
LICENSE_CREATIVE_COMMONS = "creativeCommon"
LICENSE_STANDARD = "youtube"

USE_CLIPPABLE = "clippable"
USE_THEME_ONLY = "theme_only"


@dataclass
class ExternalCandidate:
    """外部から見つけた切り抜き元の候補。"""

    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: str
    duration_sec: float
    view_count: int
    license: str
    #: clippable / theme_only
    use_as: str
    #: なぜその扱いになったか（監査用に必ず残す）
    reason: str
    origin: str = ""
    local_path: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    #: 説明欄。許諾文言の判定に使うので候補に持たせておく
    description: str = ""
    #: 説明欄で実際に一致した許諾文言（監査用。無許諾なら空）
    permission_phrase: str = ""
    #: 表示用のクレジット名（allowlist で上書きできる）
    credit_name: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "channel_id": self.channel_id,
            "channel_title": self.channel_title,
            "published_at": self.published_at,
            "duration_sec": round(self.duration_sec, 1),
            "view_count": self.view_count,
            "license": self.license,
            "use_as": self.use_as,
            "reason": self.reason,
            "origin": self.origin,
            "local_path": self.local_path,
            "url": self.url,
            "tags": self.tags,
            "permission_phrase": self.permission_phrase,
            "credit_name": self.credit_name or self.channel_title,
        }


# ---------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------

def _cfg(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return clip_cfg.get("external_sources") or {}


def is_enabled(clip_cfg: Dict[str, Any]) -> bool:
    return bool(_cfg(clip_cfg).get("enabled"))


def _allowlist(clip_cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for entry in _cfg(clip_cfg).get("allowlist_channels") or []:
        cid = str(entry.get("channel_id") or "").strip()
        if cid:
            out[cid] = entry
    return out


# ---------------------------------------------------------------------
# ライセンスゲート
# ---------------------------------------------------------------------

def classify(
    *,
    license_value: str,
    channel_id: str,
    clip_cfg: Dict[str, Any],
    requested_use: str = USE_CLIPPABLE,
    description: str = "",
) -> tuple:
    """(use_as, reason, permission_phrase) を返す。切り抜き可否の唯一の判定箇所。

    ここを緩めると権利侵害が起きる。緩めるときは必ず許諾の根拠を
    `allowlist_channels[].permission_note` に書くこと。

    Args:
        description: 対象動画の説明欄。allowlist の `permission_phrases` が
            ここに実在するかを確かめる。空文字を渡すと（＝説明欄を取れて
            いない）許諾文言は当然見つからないので theme_only に落ちる。
    """
    entry = _allowlist(clip_cfg).get(channel_id)
    if entry:
        phrases = [str(p) for p in (entry.get("permission_phrases") or []) if str(p).strip()]
        require = bool(entry.get("require_permission_phrase", True))
        if not require:
            note = str(entry.get("permission_note") or "許諾済みとして登録")
            return USE_CLIPPABLE, f"allowlist 登録チャンネル（{note}）", ""
        if not phrases:
            # 「許諾文言で確かめる」設定なのに文言が無い＝根拠が空。通さない。
            return USE_THEME_ONLY, (
                "allowlist 登録チャンネルだが permission_phrases が空のため許諾を"
                "確認できない。文言を設定するか require_permission_phrase=false に"
                "して permission_note に根拠を書くこと"
            ), ""
        hit = next((p for p in phrases if p in (description or "")), None)
        if hit:
            return USE_CLIPPABLE, f"説明欄に許諾文言『{hit}』を確認（allowlist 登録チャンネル）", hit
        return USE_THEME_ONLY, (
            "allowlist 登録チャンネルだが、この動画の説明欄に許諾文言が無いため"
            "切り抜き不可（回ごとに権利が違う可能性がある）"
        ), ""

    if license_value == LICENSE_CREATIVE_COMMONS:
        return USE_CLIPPABLE, "Creative Commons (CC BY) ライセンス。帰属表示を付けて再利用可", ""

    if requested_use == USE_THEME_ONLY:
        return USE_THEME_ONLY, "急上昇からの話題収集。標準ライセンスなので映像は使わない", ""

    return USE_THEME_ONLY, (
        f"標準ライセンス（{license_value or '不明'}）のため切り抜き不可。"
        "テーマのシグナルとしてのみ使用する"
    ), ""


# ---------------------------------------------------------------------
# YouTube Data API
# ---------------------------------------------------------------------

def _youtube_client():
    api_key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY が未設定です。")
    from googleapiclient.discovery import build  # type: ignore
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _parse_iso8601_duration(text: str) -> float:
    """PT1H2M3S → 秒。"""
    if not text or not text.startswith("PT"):
        return 0.0
    num = ""
    total = 0.0
    for ch in text[2:]:
        if ch.isdigit():
            num += ch
        elif ch in "HMS" and num:
            total += int(num) * {"H": 3600, "M": 60, "S": 1}[ch]
            num = ""
        else:
            num = ""
    return total


def _videos_details(yt, video_ids: List[str]) -> List[Dict[str, Any]]:
    """videos.list を 50件ずつ叩いて contentDetails / status を取る。"""
    out: List[Dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            res = yt.videos().list(
                part="snippet,contentDetails,statistics,status",
                id=",".join(batch), maxResults=50,
            ).execute()
        except Exception as e:
            print(f"⚠️ videos.list 失敗: {e}")
            continue
        out.extend(res.get("items") or [])
    return out


def _matched_exclude_pattern(entry: Dict[str, Any], title: str) -> str:
    """allowlist の `exclude_title_patterns` に当たったパターンを返す（無ければ空）。

    ゲスト回・コラボ回を落とすための素朴なタイトル照合。自動字幕には話者情報が
    無いので、区間だけを見て「これはゲストの発言」と判別する手段が無い。
    タイトルは「誰が出ている回か」をチャンネル側が明示している唯一の場所なので、
    ここで回ごと落とすのが現実的なゲート。

    content_policy.avoid の『ゲストの発言が主役の部分（ゲスト側の許諾が別途必要）』
    を機械的に効かせるための仕組み。
    """
    patterns = [str(p) for p in (entry.get("exclude_title_patterns") or []) if str(p).strip()]
    if not patterns:
        return ""
    for p in patterns:
        try:
            if re.search(p, title):
                return p
        except re.error:
            # 設定ミスの正規表現で調達全体を止めない。素の部分一致に落とす
            if p in title:
                return p
    return ""


def _to_candidate(item: Dict[str, Any], *, clip_cfg: Dict[str, Any],
                  requested_use: str, origin: str) -> Optional[ExternalCandidate]:
    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    stats = item.get("statistics") or {}
    status = item.get("status") or {}

    video_id = str(item.get("id") or "")
    if not video_id:
        return None

    license_value = str(status.get("license") or "")
    channel_id = str(snippet.get("channelId") or "")
    description = str(snippet.get("description") or "")
    use_as, reason, phrase = classify(
        license_value=license_value, channel_id=channel_id,
        clip_cfg=clip_cfg, requested_use=requested_use,
        description=description,
    )
    entry = _allowlist(clip_cfg).get(channel_id) or {}

    # 許諾とは別軸の「その回を切り抜きに使ってよいか」フィルタ。
    # 権利判定は classify() が唯一の窓口なので、ここでは *通ったものを更に絞る*
    # 方向にしか働かせない（theme_only を clippable に昇格させない）。
    title = str(snippet.get("title") or "")
    if use_as == USE_CLIPPABLE:
        pattern = _matched_exclude_pattern(entry, title)
        if pattern:
            use_as = USE_THEME_ONLY
            reason = (f"許諾はあるが exclude_title_patterns『{pattern}』に該当するため"
                      "切り抜き対象から除外（ゲスト回・コラボ回など）")

    return ExternalCandidate(
        video_id=video_id,
        title=str(snippet.get("title") or ""),
        channel_id=channel_id,
        channel_title=str(snippet.get("channelTitle") or ""),
        published_at=str(snippet.get("publishedAt") or ""),
        duration_sec=_parse_iso8601_duration(str(content.get("duration") or "")),
        view_count=int(stats.get("viewCount") or 0),
        license=license_value,
        use_as=use_as,
        reason=reason,
        origin=origin,
        tags=list(snippet.get("tags") or [])[:15],
        description=description,
        permission_phrase=phrase,
        credit_name=str(entry.get("credit_name") or ""),
    )


def fetch_trending(clip_cfg: Dict[str, Any], yt=None) -> List[ExternalCandidate]:
    """急上昇（chart=mostPopular）を拾う。既定では theme_only 扱い。"""
    cfg = _cfg(clip_cfg)
    tcfg = cfg.get("trending") or {}
    if not tcfg.get("enabled", True):
        return []

    yt = yt or _youtube_client()
    region = str(cfg.get("region_code") or "JP")
    requested = str(tcfg.get("use_as") or USE_THEME_ONLY)
    max_results = int(cfg.get("max_candidates") or 25)
    categories = [str(c) for c in (tcfg.get("category_ids") or [""])]

    out: List[ExternalCandidate] = []
    for cat in categories:
        params: Dict[str, Any] = {
            "part": "snippet,contentDetails,statistics,status",
            "chart": "mostPopular",
            "regionCode": region,
            "maxResults": min(50, max_results),
        }
        if cat:
            params["videoCategoryId"] = cat
        try:
            res = yt.videos().list(**params).execute()
        except Exception as e:
            print(f"⚠️ 急上昇の取得に失敗 (category={cat or 'all'}): {e}")
            continue
        for item in res.get("items") or []:
            cand = _to_candidate(item, clip_cfg=clip_cfg, requested_use=requested,
                                 origin=f"trending:{region}:{cat or 'all'}")
            if cand:
                out.append(cand)
    return out


def search_creative_commons(clip_cfg: Dict[str, Any], yt=None) -> List[ExternalCandidate]:
    """CC ライセンスの動画だけを検索する（切り抜いてよい外部素材）。"""
    cfg = _cfg(clip_cfg)
    ccfg = cfg.get("creative_commons") or {}
    if not ccfg.get("enabled", True):
        return []

    queries = [str(q) for q in (ccfg.get("queries") or []) if str(q).strip()]
    if not queries:
        return []

    yt = yt or _youtube_client()
    region = str(cfg.get("region_code") or "JP")
    per_query = max(1, int(cfg.get("max_candidates") or 25) // len(queries))

    video_ids: List[str] = []
    for q in queries:
        try:
            res = yt.search().list(
                part="id", q=q, type="video",
                videoLicense="creativeCommon",   # ← ここが権利面の要
                videoDuration="long",            # 20分超（切り抜き元向き）
                regionCode=region, relevanceLanguage="ja",
                order="viewCount", maxResults=min(50, per_query),
            ).execute()
        except Exception as e:
            print(f"⚠️ CC検索に失敗 (q={q!r}): {e}")
            continue
        for item in res.get("items") or []:
            vid = ((item.get("id") or {}).get("videoId"))
            if vid:
                video_ids.append(str(vid))

    if not video_ids:
        return []

    out: List[ExternalCandidate] = []
    for item in _videos_details(yt, video_ids):
        cand = _to_candidate(item, clip_cfg=clip_cfg, requested_use=USE_CLIPPABLE,
                             origin="creative_commons")
        # search の videoLicense を信用せず videos.list の status.license で再検証する
        if cand and cand.use_as == USE_CLIPPABLE:
            out.append(cand)
        elif cand:
            print(f"  ⚠️ CC検索で出たが status.license={cand.license} のため除外: {cand.title[:40]}")
    return out


def fetch_allowlist_channels(clip_cfg: Dict[str, Any], yt=None) -> List[ExternalCandidate]:
    """許諾済み（allowlist）チャンネルの新着動画を拾う。

    `search.list` は 1 回 100 クォータ消費するので使わない。uploads 再生リストを
    `playlistItems.list`（1 クォータ）で辿ってから `videos.list` で詳細を取る。
    切り抜きラボは毎日回るので、ここをケチらないと投稿分のクォータを食い潰す。
    """
    cfg = _cfg(clip_cfg)
    entries = [e for e in (cfg.get("allowlist_channels") or [])
               if str(e.get("channel_id") or "").strip()]
    if not entries:
        return []

    yt = yt or _youtube_client()
    per_channel = int(cfg.get("videos_per_channel") or 15)

    out: List[ExternalCandidate] = []
    for entry in entries:
        cid = str(entry["channel_id"]).strip()
        if entry.get("enabled") is False:
            print(f"  ⏭️ allowlist 無効化中のためスキップ: {entry.get('name') or cid}")
            continue
        try:
            ch = yt.channels().list(part="contentDetails", id=cid).execute()
            items = ch.get("items") or []
            if not items:
                print(f"  ⚠️ チャンネルが見つかりません: {cid}")
                continue
            uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except Exception as e:
            print(f"⚠️ uploads 再生リストの取得に失敗 ({cid}): {e}")
            continue

        video_ids: List[str] = []
        token = None
        while len(video_ids) < per_channel:
            try:
                res = yt.playlistItems().list(
                    part="contentDetails", playlistId=uploads,
                    maxResults=min(50, per_channel - len(video_ids)), pageToken=token,
                ).execute()
            except Exception as e:
                print(f"⚠️ playlistItems 取得に失敗 ({cid}): {e}")
                break
            for it in res.get("items") or []:
                vid = (it.get("contentDetails") or {}).get("videoId")
                if vid:
                    video_ids.append(str(vid))
            token = res.get("nextPageToken")
            if not token:
                break

        if not video_ids:
            continue
        for item in _videos_details(yt, video_ids):
            cand = _to_candidate(item, clip_cfg=clip_cfg, requested_use=USE_CLIPPABLE,
                                 origin=f"allowlist:{entry.get('name') or cid}")
            if cand:
                out.append(cand)
    return out


# ---------------------------------------------------------------------
# 調達履歴
# ---------------------------------------------------------------------

def load_acquisition_state() -> Dict[str, Any]:
    if not ACQUISITION_STATE.exists():
        return {"videos": {}}
    try:
        return json.loads(ACQUISITION_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"videos": {}}


def save_acquisition_state(state: Dict[str, Any]) -> None:
    ACQUISITION_STATE.parent.mkdir(parents=True, exist_ok=True)
    ACQUISITION_STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def record_acquisition(cand: ExternalCandidate) -> None:
    state = load_acquisition_state()
    state.setdefault("videos", {})[cand.video_id] = {
        **cand.to_dict(),
        "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_acquisition_state(state)


# ---------------------------------------------------------------------
# ダウンロード
# ---------------------------------------------------------------------

#: yt-dlp に渡す player_client。既定の web は 2026-08 時点で
#: 「The page needs to be reloaded.」を返して失敗するため android を先に試す。
#: yt-dlp を上げると解消することがあるので、channel JSON で差し替えられるようにする。
DEFAULT_PLAYER_CLIENTS = ["android", "web"]

VIDEO_EXTS = (".mp4", ".mkv", ".webm")


def _player_clients(clip_cfg: Dict[str, Any]) -> List[str]:
    clients = _cfg(clip_cfg).get("player_clients")
    if isinstance(clients, list) and clients:
        return [str(c) for c in clients if str(c).strip()]
    return list(DEFAULT_PLAYER_CLIENTS)


def _ytdlp_base(clip_cfg: Dict[str, Any]) -> List[str]:
    clients = ",".join(_player_clients(clip_cfg))
    return [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist", "--no-progress", "--no-warnings",
        "--extractor-args", f"youtube:player_client={clients}",
    ]


def _require_clippable(cand: ExternalCandidate) -> None:
    if cand.use_as != USE_CLIPPABLE:
        raise PermissionError(
            f"切り抜き不可の素材を取得しようとしました: {cand.title!r}（{cand.reason}）"
        )


def fetch_subtitles(
    cand: ExternalCandidate,
    *,
    clip_cfg: Dict[str, Any],
    dest_dir: Optional[Path] = None,
    langs: Sequence[str] = ("ja-orig", "ja"),
    timeout: int = 300,
) -> Optional[Path]:
    """字幕だけを落とす（映像はダウンロードしない）。

    3時間の配信を丸ごと落としてから「どこを切るか」を決めるのは現実的でない
    （数GB・数十分）。字幕は数百KBなので、**先に字幕だけ取って区間を決め、
    決まった区間だけ落とす**という順にする。

    Returns:
        取得できた VTT のパス。手動字幕があればそちらを優先する。
    """
    _require_clippable(cand)
    dest_dir = Path(dest_dir or DEFAULT_DOWNLOAD_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)

    existing = _find_subtitle(dest_dir, cand.video_id, langs)
    if existing:
        return existing

    cmd = _ytdlp_base(clip_cfg) + [
        "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", ",".join(langs),
        "--sub-format", "vtt",
        "-o", str(dest_dir / "%(id)s.%(ext)s"),
        cand.url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    got = _find_subtitle(dest_dir, cand.video_id, langs)
    if not got:
        print(f"  ⚠️ 字幕を取得できません（{cand.video_id}）: "
              f"{(proc.stderr or '').strip()[-300:]}")
        return None
    return got


def _find_subtitle(dest_dir: Path, video_id: str,
                   langs: Sequence[str]) -> Optional[Path]:
    """優先言語順に既存の VTT を探す。"""
    for lang in langs:
        hit = dest_dir / f"{video_id}.{lang}.vtt"
        if hit.exists():
            return hit
    found = sorted(dest_dir.glob(f"{video_id}.*.vtt"))
    return found[0] if found else None


def download_section(
    cand: ExternalCandidate,
    *,
    start: float,
    end: float,
    clip_cfg: Dict[str, Any],
    dest_dir: Optional[Path] = None,
    max_height: int = 1080,
    margin_sec: float = 3.0,
    timeout: int = 1800,
) -> Tuple[Path, float]:
    """指定区間だけを落とす。

    Returns:
        (落としたファイル, そのファイルの 0 秒が元動画の何秒に当たるか)。
        呼び出し側は `絶対秒 - offset` でファイル内の秒に変換する。

    `--force-keyframes-at-cuts` を付けないと、切り出し位置が直前のキーフレームに
    ずれて冒頭に無関係な数秒が入る。切り抜きは冒頭2秒が勝負なので必須。
    """
    _require_clippable(cand)
    dest_dir = Path(dest_dir or DEFAULT_DOWNLOAD_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)

    offset = max(0.0, start - margin_sec)
    stop = min(cand.duration_sec or end + margin_sec, end + margin_sec)
    stem = f"{cand.video_id}_{int(offset)}_{int(stop)}"

    existing = [p for p in sorted(dest_dir.glob(f"{stem}.*"))
                if p.suffix.lower() in VIDEO_EXTS]
    if existing:
        cand.local_path = str(existing[0])
        return existing[0], offset

    cmd = _ytdlp_base(clip_cfg) + [
        "-f", f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]",
        "--merge-output-format", "mp4",
        "--download-sections", f"*{offset:.2f}-{stop:.2f}",
        "--force-keyframes-at-cuts",
        "-o", str(dest_dir / f"{stem}.%(ext)s"),
        cand.url,
    ]
    print(f"  ⬇️ 区間取得: {cand.title[:40]} [{offset:.0f}s〜{stop:.0f}s]")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    got = [p for p in sorted(dest_dir.glob(f"{stem}.*"))
           if p.suffix.lower() in VIDEO_EXTS]
    if proc.returncode != 0 or not got:
        raise RuntimeError(
            f"区間ダウンロードに失敗しました（{cand.video_id}）: "
            f"{(proc.stderr or '').strip()[-600:]}"
        )
    cand.local_path = str(got[0])
    record_acquisition(cand)
    return got[0], offset


def download_candidate(
    cand: ExternalCandidate,
    *,
    dest_dir: Optional[Path] = None,
    max_height: int = 1080,
    clip_cfg: Optional[Dict[str, Any]] = None,
) -> Path:
    """clippable な候補を丸ごと落とす。theme_only は絶対に落とさない。

    長尺配信では `download_section` を使うこと。こちらは短い動画の検証用。
    """
    _require_clippable(cand)

    dest_dir = Path(dest_dir or DEFAULT_DOWNLOAD_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(dest_dir / f"{cand.video_id}.%(ext)s")

    existing = sorted(dest_dir.glob(f"{cand.video_id}.*"))
    existing = [p for p in existing if p.suffix.lower() in VIDEO_EXTS]
    if existing:
        cand.local_path = str(existing[0])
        return existing[0]

    cmd = _ytdlp_base(clip_cfg or {}) + [
        "-f", f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]",
        "--merge-output-format", "mp4",
        "-o", out_tpl, cand.url,
    ]
    print(f"  ⬇️ 取得中: {cand.title[:50]} ({cand.duration_sec:.0f}s / {cand.license})")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp が失敗しました: {proc.stderr[-600:]}")

    got = sorted(dest_dir.glob(f"{cand.video_id}.*"))
    got = [p for p in got if p.suffix.lower() in VIDEO_EXTS]
    if not got:
        raise RuntimeError(f"ダウンロード後にファイルが見つかりません: {cand.video_id}")
    cand.local_path = str(got[0])
    record_acquisition(cand)
    return got[0]


# ---------------------------------------------------------------------
# 帰属表示
# ---------------------------------------------------------------------

def attribution_text(cand: ExternalCandidate) -> str:
    """出典表示。説明欄にそのまま貼れる文字列を作る。

    CC BY は帰属表示が**義務**。許諾チャンネルの切り抜きも、義務ではなくても
    出典を出さないと視聴者・権利者の双方から無断転載に見えるので必ず付ける。
    """
    if cand.license == LICENSE_CREATIVE_COMMONS:
        return (
            f"出典: 「{cand.title}」（{cand.channel_title}）\n"
            f"{cand.url}\n"
            "ライセンス: クリエイティブ・コモンズ 表示ライセンス (CC BY 3.0)"
        )
    return f"出典: 「{cand.title}」（{cand.channel_title}）\n{cand.url}"


# ---------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------

def acquire(clip_cfg: Dict[str, Any], *, download: bool = False,
            limit: int = 5) -> Dict[str, Any]:
    """外部素材を調達する。

    Returns:
        {"clippable": [...], "theme_only": [...], "downloaded": [...]}
    """
    if not is_enabled(clip_cfg):
        return {"clippable": [], "theme_only": [], "downloaded": [],
                "skipped": "external_sources.enabled = false"}

    cfg = _cfg(clip_cfg)
    min_sec = float(cfg.get("min_duration_sec") or 180)
    max_sec = float(cfg.get("max_duration_sec") or 3600)

    try:
        yt = _youtube_client()
    except Exception as e:
        return {"clippable": [], "theme_only": [], "downloaded": [], "error": str(e)}

    candidates: List[ExternalCandidate] = []
    # 許諾済みチャンネルが本命。トレンド/CC はその補助なので後ろに置く
    candidates.extend(fetch_allowlist_channels(clip_cfg, yt))
    candidates.extend(fetch_trending(clip_cfg, yt))
    candidates.extend(search_creative_commons(clip_cfg, yt))

    seen = set()
    clippable: List[ExternalCandidate] = []
    theme_only: List[ExternalCandidate] = []
    # 尺で落とした分は必ず数える。黙って捨てると「許諾済みなのに候補0本」の
    # 原因が分からなくなる（配信は2〜6時間あるので既定の3600秒では全部落ちる）。
    too_short: List[ExternalCandidate] = []
    too_long: List[ExternalCandidate] = []
    for c in candidates:
        if c.video_id in seen:
            continue
        seen.add(c.video_id)
        if c.use_as == USE_CLIPPABLE:
            if c.duration_sec < min_sec:
                too_short.append(c)
                continue
            if c.duration_sec > max_sec:
                too_long.append(c)
                continue
            clippable.append(c)
        else:
            theme_only.append(c)

    if too_long:
        print(f"  ℹ️ 許諾ありだが max_duration_sec({max_sec:.0f}s) 超で除外: "
              f"{len(too_long)} 本（最長 {max(c.duration_sec for c in too_long):.0f}s）")
    if too_short:
        print(f"  ℹ️ 許諾ありだが min_duration_sec({min_sec:.0f}s) 未満で除外: "
              f"{len(too_short)} 本")

    clippable.sort(key=lambda c: -c.view_count)
    theme_only.sort(key=lambda c: -c.view_count)

    downloaded: List[str] = []
    if download:
        for c in clippable[:limit]:
            try:
                downloaded.append(str(download_candidate(c, clip_cfg=clip_cfg)))
            except Exception as e:
                print(f"  ⚠️ 取得失敗 ({c.video_id}): {e}")

    return {
        "clippable": [c.to_dict() for c in clippable],
        "theme_only": [c.to_dict() for c in theme_only],
        "downloaded": downloaded,
        "excluded_by_duration": {
            "too_long": [c.to_dict() for c in too_long],
            "too_short": [c.to_dict() for c in too_short],
        },
    }
