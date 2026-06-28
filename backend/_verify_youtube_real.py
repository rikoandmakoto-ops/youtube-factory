"""実YouTube APIで「アップロード済みと主張する動画」の真の状態を検証する。"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent
load_dotenv(BACKEND / ".env")  # Fernet/JWT_SECRET 必須
sys.path.insert(0, str(BACKEND))

from googleapiclient.discovery import build  # noqa: E402
from pipeline import youtube_oauth  # noqa: E402

DATA = BACKEND.parent / "data"

CLAIMED = {
    "scp-lab": ["gfloIrscKgU", "ibVSmMw2vGs", "mM_dE54Adlo", "KiyikS_Yg0Q"],
    "daily-science": ["xnJ0XMpVpx4", "IhAWD2x3lAM"],
}

for ch in ["scp-lab", "daily-science"]:
    print(f"\n{'='*70}\n■ {ch}\n{'='*70}")
    conf = json.loads((DATA / "channels" / f"{ch}.json").read_text())
    cfg_cid = conf.get("youtube_channel_id")
    print(f"  config youtube_channel_id: {cfg_cid}")

    creds = youtube_oauth.get_credentials_for(ch)
    if creds is None:
        print("  ❌ creds None — トークン失効。再認証必要")
        continue
    # 実際にrefreshが通るか
    try:
        from google.auth.transport.requests import Request
        if not getattr(creds, "valid", False):
            creds.refresh(Request())
        print(f"  creds.valid={creds.valid}")
    except Exception as e:
        print(f"  ❌ creds.refresh 失敗: {type(e).__name__}: {e}")
        continue

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    # 1) トークンが実際に支配するチャンネル
    try:
        me = yt.channels().list(part="snippet,contentDetails,status", mine=True).execute()
        for it in me.get("items", []):
            real_cid = it["id"]
            title = it["snippet"]["title"]
            uploads = it["contentDetails"]["relatedPlaylists"]["uploads"]
            match = "✅一致" if real_cid == cfg_cid else "❌不一致!!"
            print(f"  トークンの実チャンネル: {real_cid} ({title}) {match}")
            print(f"    uploads playlist: {uploads}")
    except Exception as e:
        print(f"  ❌ channels.list(mine) 失敗: {type(e).__name__}: {e}")

    # 2) 主張した動画IDの真の状態
    print("  -- 主張アップロード動画の実ステータス --")
    ids = CLAIMED.get(ch, [])
    try:
        vresp = yt.videos().list(part="status,snippet,processingDetails", id=",".join(ids)).execute()
        found = {v["id"]: v for v in vresp.get("items", [])}
        for vid in ids:
            v = found.get(vid)
            if not v:
                print(f"    {vid}: ❌ 存在しない(削除/別チャンネル/無効)")
                continue
            st = v.get("status", {})
            print(f"    {vid}: upload={st.get('uploadStatus')} privacy={st.get('privacyStatus')} "
                  f"reject={st.get('rejectionReason')} pub={v['snippet'].get('publishedAt')} "
                  f"owner_ch={v['snippet'].get('channelId')}")
    except Exception as e:
        print(f"    ❌ videos.list 失敗: {type(e).__name__}: {e}")

    # 3) 実uploadsプレイリストの直近5本（真実）
    print("  -- 実uploads直近5本 --")
    try:
        up = "UU" + cfg_cid[2:]
        pl = yt.playlistItems().list(part="snippet,contentDetails", playlistId=up, maxResults=5).execute()
        for it in pl.get("items", []):
            cd = it.get("contentDetails", {})
            print(f"    {cd.get('videoId')}  {cd.get('videoPublishedAt')}  {it['snippet'].get('title','')[:40]}")
    except Exception as e:
        print(f"    ❌ playlistItems 失敗: {type(e).__name__}: {e}")
