"""
SCP 系ゆっくり / 解説チャンネルの **ショート動画** だけを集めて、
competitor_video_analyzer.py で深掘り分析し、ショート特有の演出パターンを
data/research/scp_shorts_visual_analysis.json に書き出すスクリプト。

メイン動画版 (scp_visual_research.py) とは違い:
  - YouTube API の videoDuration="short" を使い、加えて 90 秒以下のものを残す
  - チャンネル数は少なめ、1 チャンネル当たり最大 3 本まで
  - 集計プロンプトを「縦型 9:16・フック・テンポ・テロップ」中心に書き換え

実行:
  python3 scripts/scp_shorts_visual_research.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

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


from pipeline.analytics import competitor_video_analyzer as cva  # noqa: E402
from pipeline import claude_client  # noqa: E402


CHANNEL_ID_FOR_ANALYSIS = "scp-shorts-research"
DATA_OUT = ROOT / "data" / "research" / "scp_shorts_visual_analysis.json"

SEARCH_QUERIES = [
    "SCP shorts",
    "SCP ショート",
    "SCP 解説 ショート",
    "ゆっくりSCP shorts",
    "SCP-173 shorts",
    "SCP-049 shorts",
    "SCP 財団 shorts",
]

MAX_VIDEOS_PER_QUERY = 25
TARGET_CHANNELS = 6
VIDEOS_PER_CHANNEL = 3
MAX_SHORT_DURATION = 90  # 90s 以下のみ採用
MIN_SHORT_DURATION = 10  # 10s 未満は弾く（実質ループ動画など）
SCP_TOKEN = "SCP"
GAME_BLACKLIST = ("マイクラ", "ROBLOX", "ロブロックス", "GMOD", "アンパンマン", "Minecraft")


def _yt_client():
    from googleapiclient.discovery import build  # type: ignore

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing in env")
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _iso_duration_to_seconds(dur: str) -> int:
    import re

    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    h, mn, s = m.groups()
    return int(h or 0) * 3600 + int(mn or 0) * 60 + int(s or 0)


def search_scp_shorts() -> List[Dict[str, Any]]:
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
                    videoDuration="short",  # YT API: <4min
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
    print(f"🔎 search hit {len(seen)} unique candidate shorts")
    return list(seen.values())


def enrich_with_stats(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
    def _has_japanese(s: str) -> bool:
        for ch in s:
            if "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿":
                return True
        return False

    def _is_short_and_scp(v: Dict[str, Any]) -> bool:
        title = v.get("title") or ""
        ch = v.get("channel_title") or ""
        dur = v.get("duration_seconds", 0)
        if dur <= 0 or dur > MAX_SHORT_DURATION or dur < MIN_SHORT_DURATION:
            return False
        if any(bw.lower() in title.lower() for bw in GAME_BLACKLIST):
            return False
        if SCP_TOKEN.lower() not in (title + " " + ch).lower():
            return False
        if not (_has_japanese(title) or _has_japanese(ch)):
            return False
        return True

    videos = [v for v in videos if _is_short_and_scp(v)]
    by_channel: Dict[str, List[Dict[str, Any]]] = {}
    titles: Dict[str, str] = {}
    for v in videos:
        cid = v["channel_id"]
        if not cid:
            continue
        by_channel.setdefault(cid, []).append(v)
        titles[cid] = v.get("channel_title") or titles.get(cid, "")

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
    results: List[Dict[str, Any]] = []
    for cid, ctitle, videos in selection:
        print(f"\n── 📺 {ctitle} ({cid}) ── {len(videos)} shorts")
        for v in videos:
            print(f"  ▶ {v['title'][:60]}  views={v.get('views'):,}  {v.get('duration_seconds')}s")
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
                    frame_count=4,  # 縦動画は短いがカット多いので 4 フレーム
                )
            except Exception as e:
                r = {"ok": False, "error": str(e), "video_id": v["video_id"]}
            r["channel_title"] = ctitle
            r["channel_id"] = cid
            r["views"] = v.get("views")
            r["title"] = v["title"]
            r["duration_seconds"] = v.get("duration_seconds")
            results.append(r)
            print(f"    → frames={r.get('frame_count')}  "
                  f"transcript={r.get('transcript_source')}  "
                  f"visual={'Y' if r.get('visual_insights') else 'N'}  "
                  f"content={'Y' if r.get('content_insights') else 'N'}")
    return results


def aggregate_patterns(
    results: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
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
                    "duration_seconds": r.get("duration_seconds"),
                    "visual": v,
                    "content": c,
                },
                ensure_ascii=False,
            )
        )
    if not pieces:
        return None

    joined = "\n\n".join(pieces)[:18000]
    user = (
        "以下は SCP 解説系 YouTube チャンネルの **人気ショート動画 (9:16, 90 秒以下)** を"
        " 1 本ずつ分析した結果の JSON 配列です。\n"
        "サムネ + 本編 4 フレームの視覚分析と、字幕の内容分析が入っています。\n\n"
        f"--- 個別分析 ---\n{joined}\n--- ここまで ---\n\n"
        "ショート動画特有の演出パターンを抽出してください。"
        "重要: メイン動画ではなく『縦型ショート』としての特性に絞ること。"
        "以下の JSON のみを返してください。\n\n"
        "{\n"
        "  \"vertical_layout\": {\n"
        "    \"safe_area\": \"中央〜上 60% に主要情報を置いているか、下 25% を字幕領域にしているか、など\",\n"
        "    \"character_placement\": \"キャラ立ち絵 / アイコンの配置パターン\",\n"
        "    \"background_strategy\": \"ベタ色 / 画像 / 動画 / Pexels 風 B-roll / SCP オブジェ画像、など\"\n"
        "  },\n"
        "  \"hook_seconds\": {\n"
        "    \"first_three_seconds\": \"冒頭 3 秒で何を見せているか（疑問形ハロ / 衝撃画像 / 数字 / REDACTED 演出 など）\",\n"
        "    \"opening_text\": \"冒頭テロップの定型句\",\n"
        "    \"audio_hook\": \"効果音・声色の入り方\"\n"
        "  },\n"
        "  \"pacing\": {\n"
        "    \"avg_cut_per_second\": \"1 秒あたりのカット数の感触\",\n"
        "    \"text_swap_rate\": \"テロップ差し替えの頻度\",\n"
        "    \"length_distribution\": \"30s / 45s / 60s / 90s のどこに集中しているか\"\n"
        "  },\n"
        "  \"text_overlay\": {\n"
        "    \"font_style\": \"ゴシック / ホラー / 明朝 / 手描き 等\",\n"
        "    \"animation\": [\"出現演出（ポップ / タイプ / グリッチ / シェイク）\", ...],\n"
        "    \"color_palette\": [\"主要色\", ...],\n"
        "    \"hierarchy\": \"見出し / 補足の階層設計\"\n"
        "  },\n"
        "  \"horror_specific\": {\n"
        "    \"redacted_motif\": \"REDACTED 黒バー / 機密スタンプ / 公文書風レイアウトの使い方\",\n"
        "    \"jump_scare\": \"ジャンプスケアやフラッシュ演出の有無 / 強度\",\n"
        "    \"color_grading\": \"赤フラッシュ・グリーンノイズ・暗部強調などの色設計\",\n"
        "    \"sound_design_hints\": \"BGM / SE のホラー演出ヒント\"\n"
        "  },\n"
        "  \"narrative_structure\": {\n"
        "    \"template\": \"オープニング → ボディ → クライマックス → CTA など、よくある構成\",\n"
        "    \"cta\": \"続きはメイン動画 / チャンネル登録 などの誘導の入れ方\",\n"
        "    \"hook_to_payoff_seconds\": \"フックから核ネタまでの時間\"\n"
        "  },\n"
        "  \"common_patterns\": [\"全ショート共通で頻出する演出\", ...],\n"
        "  \"differentiators\": [\"チャンネルごとの特徴的な演出\", ...],\n"
        "  \"recommendations_for_scp_lab_shorts\": [\n"
        "    \"自チャンネル (scp-lab) のショートに導入すべき具体演出（実装難度の低い順に。 \"\n"
        "    \"背景演出 / テロップ / 構成 / SE / カット割り など）\", ...\n"
        "  ]\n"
        "}\n"
        "JSON のみを返してください。"
    )
    print("\n🧠 aggregating cross-channel short patterns via Claude ...")
    return claude_client.call_claude_json(
        system=(
            "あなたは YouTube ショート専門の演出ディレクター。"
            "縦型 9:16 / 短尺の特殊な制約下での演出選択を分析し、再現可能なパターンに落とし込む。"
        ),
        user=user,
        temperature=0.4,
        max_tokens=3500,
        channel_id=CHANNEL_ID_FOR_ANALYSIS,
        purpose="scp_shorts_visual_meta_analysis",
    )


def main():
    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)

    print("=== SCP shorts visual research ===")
    print(f"output: {DATA_OUT}")

    raw = search_scp_shorts()
    if not raw:
        print("❌ no shorts found, abort")
        return
    enriched = enrich_with_stats(raw)

    selection = pick_per_channel(
        enriched,
        target_channels=TARGET_CHANNELS,
        per_channel=VIDEOS_PER_CHANNEL,
    )
    if not selection:
        print("❌ no channels selected (filters too strict?)")
        return

    print("\n📌 selected channels:")
    for cid, ctitle, vs in selection:
        total = sum(int(v.get("views") or 0) for v in vs)
        print(f"  · {ctitle}  (shorts={len(vs)}, total_views={total:,})")

    started = time.time()
    results = run_analysis(selection)
    elapsed = time.time() - started

    aggregated = aggregate_patterns(results)

    out = {
        "generated_at": int(time.time()),
        "elapsed_seconds": int(elapsed),
        "queries": SEARCH_QUERIES,
        "max_short_duration": MAX_SHORT_DURATION,
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
