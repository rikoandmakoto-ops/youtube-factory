"""海外バイラル動画の調達（Reddit / 直リンク）。

`acquisition.py`（YouTube の許諾済みチャンネル）と同じ位置づけのモジュールだが、
狙う素材が違うので調達経路と門番が別になる。

    acquisition.py … YouTube Data API + 説明欄の許諾文言ゲート（clip-lab 17:45 枠）
    viral_sources.py … Reddit の公開 JSON + 内容ゲート（clip-lab 20:45 枠）

2026-08-30 の運用決定で、海外バイラルは専用チャンネル（旧 clip-viral）を作らず
**既存の clip-lab に同居**する。設定は `clip.viral_sources` 配下にまとまっていて、
尺・説明欄・レイアウトなど国内切り抜きと食い違うものは、この配下の
`output` / `metadata` / `layout_spec` が上書きする（`clip.*` は国内枠の値）。

════════════════════════════════════════════════════════════════════
■ なぜ Reddit を一次ソースにするか
════════════════════════════════════════════════════════════════════

「TikTok / Instagram Reels から自動収集」は経路として現実的でない。両社とも
公開の検索 API を出しておらず、Web スクレイピングは短命（DOM とトークンが
頻繁に変わる）で ToS 違反にも当たる。一方 **Reddit は TikTok / IG のバイラルが
数時間で転載されて集まる場所**で、公開 JSON エンドポイント（`/r/<sub>/top.json`）
が認証なしで叩ける。スコア・コメント数という「既にウケた」証拠まで付いてくる。

そのため:

  - 自動収集は **Reddit のみ**（サブレディットは channel JSON で差し替え可能）
  - TikTok / IG / X の個別 URL は `manual_urls`（JSONL の投入キュー）で受ける。
    yt-dlp がその手の URL を解決できるので、URL さえ入れば同じ流れに乗る。

════════════════════════════════════════════════════════════════════
■ 内容ゲート（このモジュールの本体）
════════════════════════════════════════════════════════════════════

狙いは「ちょいエロ・面白い」だが、**YouTube のコミュニティガイドライン上
アウトな素材を1本でも上げるとチャンネルごと飛ぶ**。ここが唯一の防波堤なので
既定は厳しく倒してある:

  1. `over_18`（Reddit の NSFW フラグ）は既定で **全部落とす**。
     r/NSFW 系サブレディットを subreddits に足しても、この既定のままなら
     1本も通らない。通したいなら channel JSON で明示的に開ける。
  2. タイトル・本文の禁止語（`block_title_patterns`）。
  3. 音声の書き起こしに対する禁止語（`block_transcript_patterns`）は
     engines/viral.py 側で ASR 後に効かせる（ここでは持つだけ）。
  4. `require_manual_review` が true なら、出来上がった動画は private で上がる。
     **2026-08-30 の運用決定で false（レビューなし・直接 public）**。
     1〜3 の機械ゲートだけで守る構成なので、①②③を緩めるときは慎重に。

権利面について。切り抜き元の権利者から個別に許諾を取る運用ではない、という
判断は利用者（運営者）が済ませている前提でこのモジュールは動く。ただし
**元投稿へのクレジット（サブレディット名・投稿者名・パーマリンク）は必ず
説明欄に載せる**（`attribution_text`）。出典なしは無断転載と区別が付かない。
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .sources import PROJECT_ROOT, SourceVideo

#: 調達した素材の置き場。`~/Desktop` の下に置いてはいけない理由は
#: acquisition.DEFAULT_DOWNLOAD_DIR の注記と同じ（launchd 配下の TCC で
#: ffmpeg の書き込みが無言でハングする）。
DEFAULT_DOWNLOAD_DIR = Path(
    os.environ.get("VIRAL_DOWNLOAD_DIR")
    or (Path.home() / "Movies" / "yf_viral_downloads")
)

#: 一度見た投稿を覚えておく（同じ動画を二度作らない）
VIRAL_STATE = PROJECT_ROOT / "data" / "analytics" / "viral_acquisition.json"

#: 手動投入キュー。TikTok / IG / X の URL を1行1件で置くと次回の実行で拾う。
#:   {"url": "https://www.tiktok.com/@x/video/123", "note": "任意メモ"}
MANUAL_QUEUE = PROJECT_ROOT / "data" / "analytics" / "viral_manual_queue.jsonl"

#: Reddit は既定の UA（python-urllib）を 429 で弾く。名乗れば通る。
DEFAULT_USER_AGENT = (
    "youtube-factory:clip-lab:1.0 (contact via channel description)"
)

#: yt-dlp が解決できる、動画として扱えるホスト。ここに無いドメインの投稿は
#: 画像・記事リンクなので候補にしない。
VIDEO_HOSTS = (
    "v.redd.it", "redgifs.com", "streamable.com", "gfycat.com",
    "imgur.com", "i.imgur.com", "youtube.com", "youtu.be",
    "tiktok.com", "instagram.com", "twitter.com", "x.com",
)

VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov")

#: 既定の禁止語。channel JSON の `block_title_patterns` で置き換えられるが、
#: **こちらは常に併用する**（設定ミスでゲートが空になるのを防ぐ）。
#: 性的に露骨・未成年・暴力・実在の事件を狙って落とす。
HARD_BLOCK_PATTERNS = (
    r"(?i)\b(porn|nsfw|nude|nudes|naked|sex tape|hentai|onlyfans|blowjob|"
    r"masturbat|orgasm|creampie|anal|dildo|escort)\b",
    r"(?i)\b(child|kid|teen|minor|underage|loli|shota)\b.{0,20}"
    r"\b(sexy|hot|nude|naked|porn)\b",
    r"(?i)\b(gore|beheading|murder|suicide|shooting|dead body|corpse|"
    r"execution|torture)\b",
    r"(?i)\b(rape|assault|abuse|molest)\b",
)


@dataclass
class ViralCandidate:
    """海外バイラル動画の候補1本。"""

    post_id: str
    platform: str
    title: str
    #: 動画そのものの URL（yt-dlp に渡す）
    media_url: str
    #: 出典として示す投稿ページ URL
    permalink: str
    community: str = ""          # subreddit 名など
    author: str = ""
    score: int = 0
    num_comments: int = 0
    created_utc: float = 0.0
    duration_sec: float = 0.0
    over_18: bool = False
    #: over_18 を Reddit の API で確かめられたか。RSS 経路では False になり、
    #: 「NSFW ではない」ではなく「分からない」を意味する。
    nsfw_verified: bool = True
    origin: str = ""
    local_path: Optional[str] = None
    #: ゲートの判定結果（監査用に必ず残す）
    gate_ok: bool = True
    gate_reason: str = ""

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.post_id}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "title": self.title,
            "media_url": self.media_url,
            "permalink": self.permalink,
            "community": self.community,
            "author": self.author,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc,
            "duration_sec": round(self.duration_sec, 1),
            "over_18": self.over_18,
            "nsfw_verified": self.nsfw_verified,
            "origin": self.origin,
            "local_path": self.local_path,
            "gate_ok": self.gate_ok,
            "gate_reason": self.gate_reason,
        }


# ---------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------

def cfg(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return clip_cfg.get("viral_sources") or {}


def is_enabled(clip_cfg: Dict[str, Any]) -> bool:
    return bool(cfg(clip_cfg).get("enabled"))


def gate_cfg(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg(clip_cfg).get("content_gate") or {}


def download_dir(clip_cfg: Dict[str, Any]) -> Path:
    raw = cfg(clip_cfg).get("download_dir")
    if raw:
        return Path(str(raw)).expanduser()
    return DEFAULT_DOWNLOAD_DIR


def requires_review(clip_cfg: Dict[str, Any]) -> bool:
    """出来上がりを人が見るまで private に留めるか。既定 true（安全側）。

    運用としては 2026-08-30 の決定で **false（レビューなし・直接 public）**。
    既定値を true のまま残してあるのは、設定を書き忘れた新しいチャンネルが
    いきなり公開されないようにするため。切り替えは channel JSON の
    `clip.viral_sources.content_gate.require_manual_review` の1箇所。
    """
    return bool(gate_cfg(clip_cfg).get("require_manual_review", True))


def output_cfg(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """海外枠だけの出力設定（尺・CTA・ウォーターマーク）。

    `clip-lab` に国内切り抜きと同居しているため、`clip.min_duration_sec` 等を
    そのまま使うと国内向けの値（30〜59秒）に引っ張られる。海外バイラルは
    10〜25 秒が多数派なので、ここで別の帯を持つ。
    """
    return cfg(clip_cfg).get("output") or {}


def asr_cfg(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Whisper の設定。海外枠専用（`clip.viral_sources.asr`）を優先する。"""
    return cfg(clip_cfg).get("asr") or clip_cfg.get("asr") or {}


def metadata_cfg(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """タイトル・説明欄・タグの海外枠向け上書き（`clip.viral_sources.metadata`）。

    同居先の `clip-lab` の説明欄テンプレートは「▼ この切り抜きの本編はこちら」で、
    Reddit の投稿ページを指すと意味が通らない。文面だけ差し替える。
    """
    return cfg(clip_cfg).get("metadata") or {}


# ---------------------------------------------------------------------
# 内容ゲート
# ---------------------------------------------------------------------

def _compiled(patterns: Sequence[str]) -> List["re.Pattern[str]"]:
    out: List[re.Pattern[str]] = []
    for p in patterns:
        p = str(p).strip()
        if not p:
            continue
        try:
            out.append(re.compile(p))
        except re.error as e:
            print(f"  ⚠️ 禁止語の正規表現が不正なので無視します: {p!r} ({e})")
    return out


def title_patterns(clip_cfg: Dict[str, Any]) -> List["re.Pattern[str]"]:
    """タイトルに効かせる禁止語。既定のハードブロックは必ず含む。"""
    extra = gate_cfg(clip_cfg).get("block_title_patterns") or []
    return _compiled(list(HARD_BLOCK_PATTERNS) + [str(p) for p in extra])


def transcript_patterns(clip_cfg: Dict[str, Any]) -> List["re.Pattern[str]"]:
    """書き起こしに効かせる禁止語（ASR 後に engines/viral.py が使う）。

    タイトルは投稿者が書いた宣伝文なので、内容の露骨さを必ずしも表さない。
    実際に何を喋っているかは書き起こしにしか出ないので、二段で見る。
    """
    extra = gate_cfg(clip_cfg).get("block_transcript_patterns") or []
    return _compiled(list(HARD_BLOCK_PATTERNS) + [str(p) for p in extra])


def check_text(text: str, patterns: Sequence["re.Pattern[str]"]) -> str:
    """当たった禁止語を返す（無ければ空文字）。"""
    for r in patterns:
        m = r.search(text or "")
        if m:
            return m.group(0)
    return ""


def apply_gate(cand: ViralCandidate, clip_cfg: Dict[str, Any]) -> ViralCandidate:
    """候補に内容ゲートを掛ける。落ちた理由は候補に書き戻す。"""
    g = gate_cfg(clip_cfg)

    allow_over_18 = bool(g.get("allow_over_18", False))
    if cand.over_18 and not allow_over_18:
        cand.gate_ok = False
        cand.gate_reason = (
            "Reddit の NSFW フラグ（over_18）付き。"
            "content_gate.allow_over_18 が false のため除外"
        )
        return cand

    # RSS 経路は NSFW フラグを取れない。SFW サブレディット前提の保険経路なので
    # 既定では通すが、厳しくしたい運用のために閉められるようにしておく。
    if (not cand.nsfw_verified and not allow_over_18
            and not g.get("allow_unverified_nsfw_flag", True)):
        cand.gate_ok = False
        cand.gate_reason = (
            "NSFW フラグを検証できない経路（RSS）で取得した候補。"
            "content_gate.allow_unverified_nsfw_flag が false のため除外"
        )
        return cand

    blocked_communities = {str(s).lower()
                           for s in (g.get("block_communities") or [])}
    if cand.community.lower() in blocked_communities:
        cand.gate_ok = False
        cand.gate_reason = f"block_communities に登録された投稿元（{cand.community}）"
        return cand

    hit = check_text(cand.title, title_patterns(clip_cfg))
    if hit:
        cand.gate_ok = False
        cand.gate_reason = f"タイトルに禁止語『{hit}』"
        return cand

    cand.gate_ok = True
    cand.gate_reason = "内容ゲート通過（NSFWフラグなし・禁止語なし）"
    return cand


# ---------------------------------------------------------------------
# 調達履歴
# ---------------------------------------------------------------------

def load_state() -> Dict[str, Any]:
    if not VIRAL_STATE.exists():
        return {"posts": {}}
    try:
        return json.loads(VIRAL_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"posts": {}}


def save_state(state: Dict[str, Any]) -> None:
    VIRAL_STATE.parent.mkdir(parents=True, exist_ok=True)
    VIRAL_STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def record(cand: ViralCandidate, *, status: str, note: str = "") -> None:
    """調達・採用・不採用を記録する。

    ここに残っている投稿は二度と候補にしない。「作った」だけでなく
    「ゲートで落とした」も残すのが要点で、そうしないと毎日同じ NSFW 投稿に
    Reddit API とダウンロード帯域を使い続ける。
    """
    state = load_state()
    state.setdefault("posts", {})[cand.key] = {
        **cand.to_dict(),
        "status": status,
        "note": note,
        "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_state(state)


def seen_keys() -> set:
    return set(load_state().get("posts", {}).keys())


# ---------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------

def _http_json(url: str, *, user_agent: str, timeout: int = 30,
               token: Optional[str] = None, quiet: bool = False) -> Optional[Any]:
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if not quiet:
            print(f"  ⚠️ Reddit が {e.code} を返しました: {url}")
    except Exception as e:
        if not quiet:
            print(f"  ⚠️ Reddit 取得に失敗: {type(e).__name__}: {e}")
    return None


# ---------------------------------------------------------------------
# Reddit の認証（2026-08 時点で匿名 .json は 403）
# ---------------------------------------------------------------------
#
# 昔は `https://www.reddit.com/r/<sub>/top.json` が認証なしで叩けたが、
# 2026-08-30 に実測したところ **UA を名乗っても 403（bot wall の HTML）** が返る。
# old.reddit.com はログインへリダイレクトされる。使える経路は2つ:
#
#   oauth : 公式 API。reddit.com/prefs/apps でアプリを1つ作って
#           REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET を backend/.env に置く。
#           score・over_18・動画の尺まで全部取れるので **これが本命**。
#   rss   : `https://www.reddit.com/r/<sub>/top.rss` は今も 200 を返す。
#           ただし score も over_18 も入っていない（タイトルとリンクだけ）。
#           キーが無い日に autopilot を落とさないための保険。
#
# `auth_mode: "auto"`（既定）は oauth → public → rss の順に落ちる。

_TOKEN_CACHE: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def reddit_credentials() -> tuple:
    return (
        (os.environ.get("REDDIT_CLIENT_ID") or "").strip(),
        (os.environ.get("REDDIT_CLIENT_SECRET") or "").strip(),
    )


def reddit_token(*, user_agent: str) -> Optional[str]:
    """アプリ専用 OAuth トークンを取る（ユーザーのログインは不要）。

    confidential client（script / web app）は client_credentials、
    secret を持たない installed app は installed_client グラントを使う。
    どちらも読み取り専用の公開データにしかアクセスしない。
    """
    client_id, client_secret = reddit_credentials()
    if not client_id:
        return None
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now + 60:
        return str(_TOKEN_CACHE["token"])

    import base64
    if client_secret:
        body = "grant_type=client_credentials"
    else:
        body = ("grant_type=https%3A%2F%2Foauth.reddit.com%2Fgrants%2F"
                "installed_client&device_id=DO_NOT_TRACK_THIS_DEVICE")
    basic = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=body.encode("utf-8"),
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": user_agent,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        print(f"  ⚠️ Reddit のトークン取得に失敗（{e.code}）: "
              f"REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET を確認してください")
        return None
    except Exception as e:
        print(f"  ⚠️ Reddit のトークン取得に失敗: {type(e).__name__}: {e}")
        return None

    token = str(data.get("access_token") or "")
    if not token:
        return None
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = now + float(data.get("expires_in") or 3600)
    return token


# ---------------------------------------------------------------------
# RSS フォールバック
# ---------------------------------------------------------------------

_RSS_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
_RSS_LINK_RE = re.compile(r'<link[^>]*href="([^"]+)"')
_RSS_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_RSS_AUTHOR_RE = re.compile(r"<name>/u/([^<]+)</name>")
_RSS_ID_RE = re.compile(r"/comments/([0-9a-z]+)/")
#: RSS の本文に埋まっている Reddit ホスト動画の ID。
#: `https://v.redd.it/<id>/HLSPlaylist.m3u8` は **認証なしで取れる**（実測
#: 2026-08-30）ので、投稿ページ（yt-dlp が認証を要求する）を避けてここを使う。
_V_REDD_RE = re.compile(r"v\.redd\.it/([A-Za-z0-9]+)")
#: 外部動画ホストへのリンク投稿
_RSS_EXT_VIDEO_RE = re.compile(
    r"https?://[^\"'&<\s]*(?:tiktok\.com|streamable\.com|redgifs\.com|"
    r"gfycat\.com|youtube\.com|youtu\.be|imgur\.com)[^\"'&<\s]*")


def _unescape(text: str) -> str:
    import html
    return html.unescape(html.unescape(text or "")).strip()


def fetch_subreddit_rss(
    subreddit: str, *, sort: str, time_filter: str, user_agent: str,
) -> List[ViralCandidate]:
    """RSS から候補を作る（score / over_18 は取れない）。

    ⚠️ **NSFW フラグを検証できない経路**なので、SFW 前提のサブレディットに
    しか使ってはいけない。タイトル禁止語ゲートと Claude の安全判定は
    通常どおり効くが、Reddit 側のフラグによる一次ゲートは掛からない。
    """
    name = str(subreddit).strip().lstrip("r/").strip("/")
    url = f"https://www.reddit.com/r/{name}/{sort}.rss?t={time_filter}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})

    # RSS は認証なしぶん枠が厳しく、1秒間隔でも 429 が返る（実測 2026-08-30:
    # 8サブ連続で2件目以降が全部 429）。素直に待って数回だけ粘る。
    body = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                wait = 5.0 * (attempt + 1)
                print(f"  ⏳ r/{name}: 429 のため {wait:.0f} 秒待って再試行します")
                time.sleep(wait)
                continue
            print(f"  ⚠️ RSS 取得に失敗 (r/{name}): HTTP {e.code}")
            return []
        except Exception as e:
            print(f"  ⚠️ RSS 取得に失敗 (r/{name}): {type(e).__name__}: {e}")
            return []
    if not body:
        return []

    out: List[ViralCandidate] = []
    for chunk in _RSS_ENTRY_RE.findall(body):
        link_m = _RSS_LINK_RE.search(chunk)
        if not link_m:
            continue
        permalink = _unescape(link_m.group(1))
        id_m = _RSS_ID_RE.search(permalink)
        if not id_m:
            continue
        # 動画の実体 URL を本文から拾う。投稿ページを yt-dlp に渡すと
        # Reddit エクストラクタが「Account authentication is required」で
        # 落ちるので、CDN の直リンクだけを使う（v.redd.it は認証不要）。
        vid = _V_REDD_RE.search(chunk)
        if vid:
            media_url = f"https://v.redd.it/{vid.group(1)}/HLSPlaylist.m3u8"
        else:
            ext = _RSS_EXT_VIDEO_RE.search(_unescape(chunk))
            if not ext:
                continue          # 画像・テキスト投稿。動画ではない
            media_url = ext.group(0)

        title_m = _RSS_TITLE_RE.search(chunk)
        author_m = _RSS_AUTHOR_RE.search(chunk)
        out.append(ViralCandidate(
            post_id=id_m.group(1),
            platform="reddit",
            title=_unescape(title_m.group(1) if title_m else ""),
            media_url=media_url,
            permalink=permalink,
            community=f"r/{name}",
            author=_unescape(author_m.group(1)) if author_m else "",
            over_18=False,
            nsfw_verified=False,
            origin=f"reddit_rss:{name}",
        ))
    print(f"  📥 r/{name}（RSS）: {len(out)} 件 "
          f"※スコア・NSFWフラグ・動画URLは取得できません")
    return out


def _post_to_candidate(data: Dict[str, Any], *, subreddit: str) -> Optional[ViralCandidate]:
    """Reddit の post データを候補にする。動画でなければ None。"""
    post_id = str(data.get("id") or "")
    if not post_id:
        return None

    url = str(data.get("url_overridden_by_dest") or data.get("url") or "")
    duration = 0.0
    media_url = ""

    media = (data.get("secure_media") or data.get("media") or {}) or {}
    rv = media.get("reddit_video") or {}
    if not rv:
        # クロスポストは元投稿側に動画がぶら下がる
        for parent in (data.get("crosspost_parent_list") or []):
            pm = (parent.get("secure_media") or parent.get("media") or {}) or {}
            rv = pm.get("reddit_video") or {}
            if rv:
                break

    if rv:
        duration = float(rv.get("duration") or 0.0)
        # 投稿ページ URL は渡さない。yt-dlp の Reddit エクストラクタは
        # 2026-08-30 時点で「Account authentication is required」を返す
        # （匿名の .json が 403 になったのと同じ bot wall）。
        # HLS プレイリストは v.redd.it の CDN 直で、認証なしで取れるうえ
        # 音声トラックも含む。ここを使えばエクストラクタを通らずに済む。
        media_url = str(rv.get("hls_url") or rv.get("fallback_url") or "")
        if not media_url:
            return None
    elif any(h in url for h in VIDEO_HOSTS):
        media_url = url
    else:
        return None

    return ViralCandidate(
        post_id=post_id,
        platform="reddit",
        title=str(data.get("title") or ""),
        media_url=media_url,
        permalink="https://www.reddit.com" + str(data.get("permalink") or ""),
        community=f"r/{data.get('subreddit') or subreddit}",
        author=str(data.get("author") or ""),
        score=int(data.get("score") or 0),
        num_comments=int(data.get("num_comments") or 0),
        created_utc=float(data.get("created_utc") or 0.0),
        duration_sec=duration,
        over_18=bool(data.get("over_18")),
        origin=f"reddit:{subreddit}",
    )


def fetch_subreddit(
    subreddit: str,
    *,
    sort: str = "top",
    time_filter: str = "day",
    limit: int = 50,
    user_agent: str = DEFAULT_USER_AGENT,
    auth_mode: str = "auto",
) -> List[ViralCandidate]:
    """1つのサブレディットから動画投稿を拾う。

    `sort=top&t=day` が「今日ウケたもの」。切り抜き素材としてはこれが一番素直
    （`hot` は伸び途中なので外れが多く、`week` は同じ動画を何日も掴む）。

    Args:
        auth_mode: "auto" | "oauth" | "public" | "rss"。auto は
            oauth → public → rss の順に落ちる。
    """
    name = str(subreddit).strip().lstrip("r/").strip("/")
    if not name:
        return []
    limit = min(100, max(1, limit))
    mode = (auth_mode or "auto").strip().lower()

    if mode in ("auto", "oauth"):
        token = reddit_token(user_agent=user_agent)
        if token:
            url = (f"https://oauth.reddit.com/r/{name}/{sort}"
                   f"?t={time_filter}&limit={limit}&raw_json=1")
            data = _http_json(url, user_agent=user_agent, token=token)
            got = _children_to_candidates(data, name)
            if got is not None:
                print(f"  📥 r/{name}: 動画投稿 {len(got)} 件")
                return got
        elif mode == "oauth":
            print(f"  ⚠️ r/{name}: OAuth 指定だが REDDIT_CLIENT_ID が未設定です")
            return []

    if mode in ("auto", "public"):
        url = (f"https://www.reddit.com/r/{name}/{sort}.json"
               f"?t={time_filter}&limit={limit}&raw_json=1")
        data = _http_json(url, user_agent=user_agent, quiet=(mode == "auto"))
        got = _children_to_candidates(data, name)
        if got is not None:
            print(f"  📥 r/{name}: 動画投稿 {len(got)} 件")
            return got
        if mode == "public":
            return []

    return fetch_subreddit_rss(name, sort=sort, time_filter=time_filter,
                               user_agent=user_agent)


def _children_to_candidates(
    data: Optional[Any], subreddit: str,
) -> Optional[List[ViralCandidate]]:
    """listing レスポンスを候補列にする。取得失敗（None）と 0 件を区別する。"""
    if not isinstance(data, dict):
        return None
    children = ((data.get("data") or {}).get("children") or [])
    out: List[ViralCandidate] = []
    for child in children:
        cand = _post_to_candidate(child.get("data") or {}, subreddit=subreddit)
        if cand:
            out.append(cand)
    return out


def _manual_candidates() -> List[ViralCandidate]:
    """手動投入キュー（TikTok / IG / X の URL）を候補にする。"""
    if not MANUAL_QUEUE.exists():
        return []
    out: List[ViralCandidate] = []
    for line in MANUAL_QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:
            row = {"url": line}
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        # URL 自体を ID にする（同じ URL を二度作らない）
        post_id = re.sub(r"[^0-9A-Za-z]", "_", url)[-60:]
        out.append(ViralCandidate(
            post_id=post_id,
            platform="manual",
            title=str(row.get("title") or row.get("note") or url),
            media_url=url,
            permalink=url,
            community=str(row.get("community") or ""),
            score=int(row.get("score") or 0),
            origin="manual_queue",
        ))
    if out:
        print(f"  📥 手動キュー: {len(out)} 件")
    return out


# ---------------------------------------------------------------------
# ダウンロード
# ---------------------------------------------------------------------

def _ytdlp_base() -> List[str]:
    # CLI バイナリが PATH に無くてもモジュールが入っていれば動く
    return [sys.executable, "-m", "yt_dlp",
            "--no-playlist", "--no-progress", "--no-warnings"]


#: yt-dlp が「ログインしろ」と言ってきたときのメッセージ。Reddit / TikTok /
#: Instagram は匿名アクセスを塞ぐことがあり、そのときはこの形で返る。
AUTH_REQUIRED_MARKERS = (
    "authentication is required", "Sign in to confirm", "login required",
    "requires authentication", "cookies",
)


def probe_metadata(cand: ViralCandidate, *,
                   timeout: int = 120) -> Tuple[Dict[str, Any], str]:
    """ダウンロードせずに尺・解像度だけ取る。

    Reddit ホストの動画は投稿 JSON に duration が入っているが、TikTok や
    redgifs の転載は入っていない。尺が分からないと「30〜60秒に収まるか」を
    判定できないので、候補を絞る段階でここだけ叩く。

    Returns:
        (メタデータ, エラー文字列)。取得できたらエラーは空文字。
    """
    cmd = _ytdlp_base() + ["--dump-single-json", "--skip-download", cand.media_url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {}, "timeout"
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}, (proc.stderr or "").strip()[-300:]
    try:
        return json.loads(proc.stdout), ""
    except Exception as e:
        return {}, f"JSON parse error: {e}"


def is_auth_error(message: str) -> bool:
    low = (message or "").lower()
    return any(m.lower() in low for m in AUTH_REQUIRED_MARKERS)


def download(
    cand: ViralCandidate,
    *,
    dest_dir: Optional[Path] = None,
    max_height: int = 1080,
    timeout: int = 900,
) -> Path:
    """候補を丸ごと落とす。

    バイラル動画は数十秒・数MBなので分割取得（acquisition.download_section）は
    要らない。丸ごと落として、必要なら engines/viral.py 側で切る。
    """
    dest_dir = Path(dest_dir or DEFAULT_DOWNLOAD_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{cand.platform}_{cand.post_id}"

    existing = [p for p in sorted(dest_dir.glob(f"{stem}.*"))
                if p.suffix.lower() in VIDEO_EXTS]
    if existing:
        cand.local_path = str(existing[0])
        return existing[0]

    cmd = _ytdlp_base() + [
        "-f", f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
        "--merge-output-format", "mp4",
        "-o", str(dest_dir / f"{stem}.%(ext)s"),
        cand.media_url,
    ]
    print(f"  ⬇️ 取得中: {cand.title[:50]} ({cand.community})")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    got = [p for p in sorted(dest_dir.glob(f"{stem}.*"))
           if p.suffix.lower() in VIDEO_EXTS]
    if proc.returncode != 0 or not got:
        err = (proc.stderr or "").strip()
        if is_auth_error(err):
            raise RuntimeError(
                f"素材の取得が認証で弾かれました（{cand.key}）。"
                "Reddit なら REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET を設定して "
                "OAuth 経路にしてください（HLS の直リンクが取れるようになります）。"
                f"詳細: {err[-300:]}")
        raise RuntimeError(
            f"ダウンロードに失敗しました（{cand.key}）: {err[-600:]}")
    cand.local_path = str(got[0])
    return got[0]


# ---------------------------------------------------------------------
# 出典表示
# ---------------------------------------------------------------------

def attribution_text(cand: ViralCandidate) -> str:
    """説明欄に貼る出典。投稿ページと投稿者を必ず出す。"""
    parts = [f"Source: {cand.permalink}"]
    if cand.community:
        who = f"{cand.community}"
        if cand.author:
            who += f" / u/{cand.author}"
        parts.append(f"Original post: {who}")
    parts.append("元投稿者の方で削除をご希望の場合はコメントでご連絡ください。")
    return "\n".join(parts)


# ---------------------------------------------------------------------
# 調達エントリポイント
# ---------------------------------------------------------------------

def acquire(clip_cfg: Dict[str, Any], *, include_seen: bool = False) -> Dict[str, Any]:
    """候補を集めてゲートを掛ける（ダウンロードはしない）。

    Returns:
        {"ok": [...], "blocked": [...], "skipped_seen": n, "excluded_by_duration": {...}}
    """
    if not is_enabled(clip_cfg):
        return {"ok": [], "blocked": [], "skipped_seen": 0,
                "error": "viral_sources.enabled = false"}

    c = cfg(clip_cfg)
    ua = str(c.get("user_agent") or DEFAULT_USER_AGENT)
    sort = str(c.get("sort") or "top")
    time_filter = str(c.get("time_filter") or "day")
    per_sub = int(c.get("limit_per_subreddit") or 50)
    min_score = int(c.get("min_score") or 0)
    min_sec = float(c.get("min_duration_sec") or 5)
    max_sec = float(c.get("max_duration_sec") or 180)

    subs = [s for s in (c.get("subreddits") or [])]
    raw: List[ViralCandidate] = []
    for entry in subs:
        if isinstance(entry, str):
            name, weight, enabled = entry, 1.0, True
        else:
            name = str(entry.get("name") or "")
            weight = float(entry.get("weight") or 1.0)
            enabled = entry.get("enabled") is not False
        if not name or not enabled:
            continue
        found = fetch_subreddit(name, sort=sort, time_filter=time_filter,
                                limit=per_sub, user_agent=ua,
                                auth_mode=str(c.get("auth_mode") or "auto"))
        for f in found:
            f.origin = f"{f.origin}:w{weight:g}"
        raw.extend(found)
        # 公開エンドポイントを連打しない（1 サブレディットにつき 1 リクエスト）
        time.sleep(float(c.get("request_interval_sec") or 1.0))

    raw.extend(_manual_candidates())

    seen = set() if include_seen else seen_keys()
    ok: List[ViralCandidate] = []
    blocked: List[ViralCandidate] = []
    too_short: List[ViralCandidate] = []
    too_long: List[ViralCandidate] = []
    skipped_seen = 0
    dedup: set = set()

    for cand in raw:
        if cand.key in dedup:
            continue
        dedup.add(cand.key)
        if cand.key in seen:
            skipped_seen += 1
            continue
        # RSS 経路はスコアが取れない（常に0）。ここで足切りすると RSS 保険が
        # 丸ごと死ぬので、スコアを持っている候補にだけ適用する。
        has_score = not cand.origin.startswith("reddit_rss")
        if has_score and cand.platform == "reddit" and cand.score < min_score:
            continue
        apply_gate(cand, clip_cfg)
        if not cand.gate_ok:
            blocked.append(cand)
            continue
        # 尺は分かっている分だけここで判定する。0（未取得）は後段で probe する
        if cand.duration_sec:
            if cand.duration_sec < min_sec:
                too_short.append(cand)
                continue
            if cand.duration_sec > max_sec:
                too_long.append(cand)
                continue
        ok.append(cand)

    # 「既にウケた度合い」で並べる。コメント数はスコアより荒れにくい指標なので
    # 少し混ぜる（bot 票はスコアに乗るがコメントには乗りにくい）。
    ok.sort(key=lambda c: -(c.score + c.num_comments * 3))

    if blocked:
        print(f"  🚫 内容ゲートで除外: {len(blocked)} 件")
    if skipped_seen:
        print(f"  ⏭️ 既出（調達済み）: {skipped_seen} 件")
    if too_long or too_short:
        print(f"  ℹ️ 尺で除外: 長すぎ {len(too_long)} / 短すぎ {len(too_short)} 件")

    max_candidates = int(c.get("max_candidates") or 40)
    return {
        "ok": [x.to_dict() for x in ok[:max_candidates]],
        "blocked": [x.to_dict() for x in blocked],
        "skipped_seen": skipped_seen,
        "excluded_by_duration": {
            "too_long": [x.to_dict() for x in too_long],
            "too_short": [x.to_dict() for x in too_short],
        },
    }


def rehydrate(d: Dict[str, Any]) -> ViralCandidate:
    """acquire() が返した dict を ViralCandidate に戻す。"""
    return ViralCandidate(
        post_id=str(d.get("post_id") or ""),
        platform=str(d.get("platform") or "reddit"),
        title=str(d.get("title") or ""),
        media_url=str(d.get("media_url") or ""),
        permalink=str(d.get("permalink") or ""),
        community=str(d.get("community") or ""),
        author=str(d.get("author") or ""),
        score=int(d.get("score") or 0),
        num_comments=int(d.get("num_comments") or 0),
        created_utc=float(d.get("created_utc") or 0.0),
        duration_sec=float(d.get("duration_sec") or 0.0),
        over_18=bool(d.get("over_18")),
        nsfw_verified=bool(d.get("nsfw_verified", True)),
        origin=str(d.get("origin") or ""),
        local_path=d.get("local_path"),
        gate_ok=bool(d.get("gate_ok", True)),
        gate_reason=str(d.get("gate_reason") or ""),
    )


# ---------------------------------------------------------------------
# SourceVideo への変換
# ---------------------------------------------------------------------

VIRAL_CHANNEL_PREFIX = "viral_"


def viral_channel_key(community: str) -> str:
    """source_channel_id。`:` `/` はファイル名に入るので潰す。

    external.py と同じ理由（ffmpeg が `xx:` をプロトコルと解釈して落ちる）。
    """
    safe = re.sub(r"[^0-9A-Za-z_\-]", "_", community or "unknown")
    return f"{VIRAL_CHANNEL_PREFIX}{safe}"


def _make_materializer(cand: ViralCandidate, clip_cfg: Dict[str, Any]):
    dest = download_dir(clip_cfg)
    max_height = int(cfg(clip_cfg).get("max_height") or 1080)

    def materialize(start: float, end: float) -> Tuple[Path, float]:
        # 丸ごと落とすのでオフセットは常に 0。区間の切り出しは renderer が行う
        return download(cand, dest_dir=dest, max_height=max_height), 0.0

    return materialize


def build_source(cand: ViralCandidate, clip_cfg: Dict[str, Any]) -> SourceVideo:
    """候補を SourceVideo にする。

    字幕（timings）はこの時点では作らない。海外動画には字幕が無いので
    engines/viral.py が ASR → 翻訳で作る。ここではメタデータだけ載せる。
    """
    return SourceVideo(
        source_channel_id=viral_channel_key(cand.community or cand.platform),
        title=cand.title or cand.post_id,
        video_path=None,                      # materializer が落とす
        scenario={
            "video_title": cand.title,
            "full_scenario": [],              # ASR 前なので空
            "channel_id": cand.community,
        },
        duration=cand.duration_sec,
        youtube_video_id=None,
        used_segments=[],
        is_external=True,
        timings=None,
        credit_name=cand.community or cand.platform,
        attribution=attribution_text(cand),
        # 海外バイラルに「下部の焼き込み字幕帯」は無い。切ると中身が欠ける
        crop_bottom_ratio=0.0,
        materializer=_make_materializer(cand, clip_cfg),
        permission={
            "use_as": "viral",
            "reason": cand.gate_reason,
            "platform": cand.platform,
            "community": cand.community,
            "author": cand.author,
            "url": cand.permalink,
            "score": cand.score,
            "over_18": cand.over_18,
            "post_id": cand.post_id,
        },
    )


def discover_viral_sources(
    clip_cfg: Dict[str, Any],
    *,
    limit: int = 3,
) -> List[SourceVideo]:
    """バイラル素材から切り抜き元を集める（pipeline._collect_sources から呼ばれる）。

    Args:
        limit: 尺の実測（yt-dlp のメタ取得）まで進める本数の上限。
            使うのは1本なので、上位数本だけ確かめる。
    """
    if not is_enabled(clip_cfg):
        return []

    res = acquire(clip_cfg)
    if res.get("error"):
        print(f"⚠️ バイラル素材の調達をスキップ: {res['error']}")
        return []

    pool = [rehydrate(d) for d in (res.get("ok") or [])]
    if not pool:
        print("ℹ️ 条件を満たすバイラル動画が0本でした")
        return []

    c = cfg(clip_cfg)
    min_sec = float(c.get("min_duration_sec") or 5)
    max_sec = float(c.get("max_duration_sec") or 180)

    found: List[SourceVideo] = []
    auth_blocked = 0
    for cand in pool:
        if len(found) >= limit:
            break
        if not cand.duration_sec:
            meta, err = probe_metadata(cand)
            cand.duration_sec = float(meta.get("duration") or 0.0)
            if not cand.duration_sec:
                if is_auth_error(err):
                    # 匿名アクセスが塞がれている。他の候補も同じ結果になるので
                    # 何十本も yt-dlp を叩き続けない（1本 10 秒かかる）。
                    auth_blocked += 1
                    if auth_blocked >= 2:
                        print(
                            "  🛑 素材の取得が認証で弾かれています。"
                            "Reddit の匿名アクセスは 2026-08 に塞がれたので、"
                            "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET を "
                            "backend/.env に設定してください"
                            "（RSS 経路では動画そのものに到達できません）")
                        break
                    continue
                print(f"  ⚠️ 尺を取得できないので除外: {cand.title[:40]}")
                record(cand, status="skipped", note=f"尺を取得できない: {err[:120]}")
                continue
        if not (min_sec <= cand.duration_sec <= max_sec):
            record(cand, status="skipped",
                   note=f"尺 {cand.duration_sec:.0f}s が範囲外")
            continue
        found.append(build_source(cand, clip_cfg))

    print(f"🔥 バイラル素材 {len(found)} 本を候補に用意しました")
    return found
