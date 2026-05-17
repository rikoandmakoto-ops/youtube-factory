"""
SCP ジャンルの YouTube チャンネルから人気動画をピックし、
competitor_video_analyzer.py で「サムネ + ランダム 3 フレーム + 字幕」を分析、
画面演出パターンを横断的にまとめて data/research/scp_visual_analysis.json に書き出す。

実行:
  python3 scripts/scp_visual_research.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# プロジェクトルート
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# .env をロード（YOUTUBE_API_KEY / ANTHROPIC_API_KEY を環境に流し込む）
# 親シェルで空文字に上書きされている可能性があるため、.env に値があれば優先する。
ENV_PATH = ROOT / "backend" / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        cur = os.environ.get(k, "")
        if v and not cur.strip():
            os.environ[k] = v


# 競合分析ヘルパ
from pipeline.analytics import competitor_video_analyzer as cva  # noqa: E402
from pipeline import claude_client  # noqa: E402


CHANNEL_ID_FOR_ANALYSIS = "scp-research"  # 分析結果保存用の架空チャネル ID
DATA_OUT = ROOT / "data" / "research" / "scp_visual_analysis.json"

SEARCH_QUERIES = [
    "SCP 解説 ゆっくり",
    "SCP解説 ゆっくり",
    "ゆっくりSCP紹介",
    "SCP-",
    "SCP 財団 解説",
    "SCP 異常存在 解説",
]

MAX_VIDEOS_PER_QUERY = 15        # search で取る件数
TARGET_CHANNELS = 7              # 最終的に分析するチャンネル数
VIDEOS_PER_CHANNEL = 2           # 1 チャンネルあたり分析する動画数
SHORTS_DURATION_THRESHOLD = 90   # 90s 以下は Shorts として除外
# タイトル / チャンネル名のどちらかにこの単語が無いものは弾く
SCP_TOKEN = "SCP"
# 弾きたいゲーム実況系のキーワード (kids / minecraft / roblox 等)
GAME_BLACKLIST = ("マイクラ", "ROBLOX", "ロブロックス", "GMOD", "アンパンマン", "Minecraft")


def _yt_client():
    from googleapiclient.discovery import build  # type: ignore

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing in env")
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _iso_duration_to_seconds(dur: str) -> int:
    """PT#H#M#S → seconds."""
    import re

    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    h, mn, s = m.groups()
    return int(h or 0) * 3600 + int(mn or 0) * 60 + int(s or 0)


def search_scp_videos() -> List[Dict[str, Any]]:
    """SEARCH_QUERIES で動画を集めて dedupe。"""
    yt = _yt_client()
    seen: Dict[str, Dict[str, Any]] = {}
    for q in SEARCH_QUERIES:
        try:
            resp = (
                yt.search()
                .list(
                    q=q,
                    type="video",
                    part="snippet",
                    maxResults=MAX_VIDEOS_PER_QUERY,
                    regionCode="JP",
                    relevanceLanguage="ja",
                    order="viewCount",
                    videoDuration="medium",  # 4-20 分（Shorts/超長尺除外）
                )
                .execute()
            )
        except Exception as e:
            print(f"⚠️ search failed for '{q}': {e}")
            continue
        for item in resp.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            sn = item.get("snippet") or {}
            if not vid or vid in seen:
                continue
            seen[vid] = {
                "video_id": vid,
                "title": sn.get("title", ""),
                "channel_id": sn.get("channelId", ""),
                "channel_title": sn.get("channelTitle", ""),
                "published_at": sn.get("publishedAt", ""),
            }
        time.sleep(0.3)
    print(f"🔎 search hit {len(seen)} unique videos")
    return list(seen.values())


def enrich_with_stats(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """videos.list で再生数 / 尺を取得。"""
    yt = _yt_client()
    out: List[Dict[str, Any]] = []
    ids = [v["video_id"] for v in videos]
    by_id = {v["video_id"]: v for v in videos}
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        try:
            resp = (
                yt.videos()
                .list(part="contentDetails,statistics", id=",".join(chunk))
                .execute()
            )
        except Exception as e:
            print(f"⚠️ videos.list failed: {e}")
            continue
        for item in resp.get("items", []):
            vid = item["id"]
            base = by_id.get(vid)
            if not base:
                continue
            cd = item.get("contentDetails") or {}
            st = item.get("statistics") or {}
            dur = _iso_duration_to_seconds(cd.get("duration", ""))
            base["duration_seconds"] = dur
            base["views"] = int(st.get("viewCount") or 0)
            base["likes"] = int(st.get("likeCount") or 0)
            out.append(base)
    print(f"📊 enriched {len(out)} videos with stats")
    return out


def pick_per_channel(
    videos: List[Dict[str, Any]],
    *,
    target_channels: int,
    per_channel: int,
) -> List[Tuple[str, str, List[Dict[str, Any]]]]:
    """チャンネルごとに再生数 TOP per_channel を選ぶ。target_channels チャンネル分。

    SCP 文字列をタイトル / チャンネル名に含まない動画と、ゲーム実況キーワードを
    含む動画は除外する。
    """
    # Shorts 除外 + SCP 関連性フィルタ + 日本語チャンネル優先
    def _has_japanese(s: str) -> bool:
        for ch in s:
            # ひらがな / カタカナ / CJK 漢字
            if "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿":
                return True
        return False

    def _scp_relevant(v: Dict[str, Any]) -> bool:
        title = v.get("title") or ""
        ch = v.get("channel_title") or ""
        if v.get("duration_seconds", 0) < SHORTS_DURATION_THRESHOLD:
            return False
        if any(bw.lower() in title.lower() for bw in GAME_BLACKLIST):
            return False
        if SCP_TOKEN.lower() not in (title + " " + ch).lower():
            return False
        # 日本語コンテンツ優先（タイトル or チャンネル名のいずれかに日本語）
        if not (_has_japanese(title) or _has_japanese(ch)):
            return False
        return True

    videos = [v for v in videos if _scp_relevant(v)]
    # チャンネル別グルーピング
    by_channel: Dict[str, List[Dict[str, Any]]] = {}
    titles: Dict[str, str] = {}
    for v in videos:
        cid = v["channel_id"]
        if not cid:
            continue
        by_channel.setdefault(cid, []).append(v)
        titles[cid] = v.get("channel_title") or titles.get(cid, "")

    # チャンネル別の合計再生数で並べる
    ranked = sorted(
        by_channel.items(),
        key=lambda kv: sum(int(x.get("views") or 0) for x in kv[1]),
        reverse=True,
    )
    out: List[Tuple[str, str, List[Dict[str, Any]]]] = []
    for cid, vs in ranked[:target_channels]:
        vs_sorted = sorted(vs, key=lambda x: int(x.get("views") or 0), reverse=True)
        chosen = vs_sorted[:per_channel]
        out.append((cid, titles.get(cid, cid), chosen))
    return out


def run_analysis(
    selection: List[Tuple[str, str, List[Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    """ピックアップした動画に対して analyze_one_video を回す。"""
    results: List[Dict[str, Any]] = []
    for cid, ctitle, videos in selection:
        print(f"\n── 📺 {ctitle} ({cid}) ── {len(videos)} videos")
        for v in videos:
            print(f"  ▶ {v['title'][:60]}  views={v.get('views'):,}")
            try:
                r = cva.analyze_one_video(
                    CHANNEL_ID_FOR_ANALYSIS,
                    cid,
                    {
                        "video_id": v["video_id"],
                        "title": v["title"],
                        "views": v.get("views"),
                        "published_at": v.get("published_at"),
                        "duration": v.get("duration_seconds"),
                    },
                    competitor_title=ctitle,
                    frame_count=3,
                )
            except Exception as e:
                r = {"ok": False, "error": str(e), "video_id": v["video_id"]}
            r["channel_title"] = ctitle
            r["channel_id"] = cid
            r["views"] = v.get("views")
            r["title"] = v["title"]
            results.append(r)
            print(f"    → frames={r.get('frame_count')}  "
                  f"transcript={r.get('transcript_source')}  "
                  f"visual={'Y' if r.get('visual_insights') else 'N'}  "
                  f"content={'Y' if r.get('content_insights') else 'N'}")
    return results


def aggregate_patterns(
    results: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Claude にメタ分析させて全体パターンを抽出。"""
    # 各動画の visual_insights / content_insights を圧縮して連結
    pieces: List[str] = []
    for r in results:
        if not r.get("ok"):
            continue
        v = r.get("visual_insights") or {}
        c = r.get("content_insights") or {}
        if not v and not c:
            continue
        pieces.append(
            json.dumps(
                {
                    "channel": r.get("channel_title"),
                    "title": r.get("title"),
                    "views": r.get("views"),
                    "visual": v,
                    "content": c,
                },
                ensure_ascii=False,
            )
        )
    if not pieces:
        return None

    joined = "\n\n".join(pieces)[:18000]  # コスト抑制
    user = (
        "以下は SCP 解説系 YouTube チャンネルの人気動画を 1 本ずつ分析した結果の JSON 配列です。\n"
        "サムネ + 本編 3 フレームの視覚分析と、字幕を読んだ内容分析が入っています。\n\n"
        f"--- 個別分析 ---\n{joined}\n--- ここまで ---\n\n"
        "これらを横断的に俯瞰し、「画面演出（ビジュアルプロダクション）パターン」"
        "を抽出してください。以下の JSON だけを返してください。\n\n"
        "{\n"
        "  \"pixel_art\": {\n"
        "    \"used\": \"普及度（high|medium|low|none）\",\n"
        "    \"how\": \"どう動かしているか（静止/微振動/歩行/口パク等）\",\n"
        "    \"examples\": [\"具体例\", ...]\n"
        "  },\n"
        "  \"background_motion\": {\n"
        "    \"techniques\": [\"パン\", \"ズーム\", \"パーティクル\", ...],\n"
        "    \"frequency\": \"頻度の傾向\",\n"
        "    \"notes\": \"恐怖演出としての使い方など\"\n"
        "  },\n"
        "  \"image_appearance\": {\n"
        "    \"entrance\": [\"スライドイン\", \"フェード\", \"ズームイン\", ...],\n"
        "    \"exit\": [\"フェードアウト\", \"スライドアウト\", ...],\n"
        "    \"emphasis\": [\"ピン留め\", \"枠線パルス\", \"ハイライト\"]\n"
        "  },\n"
        "  \"text_effects\": {\n"
        "    \"styles\": [\"テロップ\", \"字幕\", \"見出しオーバーレイ\"],\n"
        "    \"animation\": [\"タイプライタ\", \"ポップ\", \"フェード\", \"カラーパルス\"],\n"
        "    \"role\": \"テロップが担っている情報設計上の役割\"\n"
        "  },\n"
        "  \"scene_transition\": {\n"
        "    \"types\": [\"カット\", \"ホワイト/ブラック フラッシュ\", \"スワイプ\", \"グリッチ\", ...],\n"
        "    \"pacing\": \"カット割り頻度の傾向\"\n"
        "  },\n"
        "  \"character_motion\": {\n"
        "    \"idle\": \"アイドル時の動き（揺れ・呼吸）\",\n"
        "    \"talking\": \"発話中の口パク等\",\n"
        "    \"reaction\": \"驚き・恐怖・笑いリアクションの表現\"\n"
        "  },\n"
        "  \"horror_specific\": {\n"
        "    \"screen_shake\": \"画面揺れの使い所\",\n"
        "    \"color_grading\": \"赤フラッシュ・色相シフト等\",\n"
        "    \"glitch_noise\": \"ノイズ・グリッチ系の演出\",\n"
        "    \"sound_design_hints\": \"BGM/SE が画面演出と連動している傾向\"\n"
        "  },\n"
        "  \"common_patterns\": [\"全チャンネル共通で頻出する演出（簡潔に箇条書き）\", ...],\n"
        "  \"differentiators\": [\"チャンネルごとに特徴的な演出\", ...],\n"
        "  \"recommendations_for_scp_lab\": [\n"
        "    \"自チャンネル(scp-lab)に取り入れるべき具体演出（実装難度低めから順に）\", ...\n"
        "  ]\n"
        "}\n"
        "JSON のみを返してください。"
    )
    print("\n🧠 aggregating cross-channel patterns via Claude ...")
    return claude_client.call_claude_json(
        system=(
            "あなたは YouTube 解説動画の演出ディレクター。"
            "複数チャンネルの分析データを俯瞰して、再現可能な演出パターンを抽出する。"
        ),
        user=user,
        temperature=0.4,
        max_tokens=3500,
        channel_id=CHANNEL_ID_FOR_ANALYSIS,
        purpose="scp_visual_meta_analysis",
    )


def main():
    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)

    print("=== SCP visual research ===")
    print(f"output: {DATA_OUT}")

    raw = search_scp_videos()
    if not raw:
        print("❌ no videos found, abort")
        return
    enriched = enrich_with_stats(raw)

    selection = pick_per_channel(
        enriched,
        target_channels=TARGET_CHANNELS,
        per_channel=VIDEOS_PER_CHANNEL,
    )
    if not selection:
        print("❌ no channels selected")
        return

    print("\n📌 selected channels:")
    for cid, ctitle, vs in selection:
        total = sum(int(v.get("views") or 0) for v in vs)
        print(f"  · {ctitle}  (videos={len(vs)}, total_views={total:,})")

    started = time.time()
    results = run_analysis(selection)
    elapsed = time.time() - started

    aggregated = aggregate_patterns(results)

    out = {
        "generated_at": int(time.time()),
        "elapsed_seconds": int(elapsed),
        "queries": SEARCH_QUERIES,
        "channels_analyzed": [
            {
                "channel_id": cid,
                "channel_title": ctitle,
                "video_ids": [v["video_id"] for v in vs],
            }
            for cid, ctitle, vs in selection
        ],
        "per_video_results": results,
        "aggregated_patterns": aggregated,
    }
    DATA_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ wrote {DATA_OUT}  ({DATA_OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
