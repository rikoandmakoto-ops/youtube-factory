#!/usr/bin/env python3
"""
ジョブウォッチャー: jobs/ フォルダを監視して動画生成を自動実行
Claudeがjobファイルを書くと自動で実行される

Usage: python3 watcher.py
"""
import os, sys, json, time, traceback
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.pipeline.video_generator import generate_all, ASSETS_DIR

JOBS_DIR = Path(__file__).parent / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

def find_bg():
    for candidate in [
        ASSETS_DIR / "backgrounds" / "ocean_waves.mp4",
        ASSETS_DIR / "bg" / "ocean_waves.mp4",
    ]:
        if candidate.exists():
            return str(candidate)
    return None

def process_job(job_path):
    """Process a single job file."""
    print(f"\n📋 ジョブ検出: {job_path.name}")
    try:
        with open(job_path, "r", encoding="utf-8") as f:
            job = json.load(f)

        # Mark as processing
        status_path = job_path.with_suffix(".status")
        with open(status_path, "w") as f:
            f.write("processing")

        results = generate_all(
            title=job["title"],
            prefix=job.get("prefix", "video"),
            short_scenario=job["short_scenario"],
            full_scenario=job.get("full_scenario"),
            bg_video_path=job.get("bg") or find_bg(),
            output_dir=job.get("output_dir"),
            gen_type=job.get("gen_type", "both"),
        )

        # Write results
        result_path = job_path.with_suffix(".result")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        with open(status_path, "w") as f:
            f.write("done")

        # Move job to done
        done_path = job_path.with_suffix(".done")
        job_path.rename(done_path)

        print(f"✅ ジョブ完了: {results.get('output_dir', '?')}")

    except Exception as e:
        print(f"❌ ジョブ失敗: {e}")
        traceback.print_exc()
        status_path = job_path.with_suffix(".status")
        with open(status_path, "w") as f:
            f.write(f"error: {e}")

def main():
    print("👀 ジョブウォッチャー起動")
    print(f"   監視フォルダ: {JOBS_DIR}")
    print(f"   ジョブファイル(.json)を配置すると自動で動画生成します")
    print(f"   停止: Ctrl+C")
    print()

    while True:
        try:
            for f in sorted(JOBS_DIR.glob("*.json")):
                process_job(f)
            time.sleep(2)
        except KeyboardInterrupt:
            print("\n停止しました")
            break

if __name__ == "__main__":
    main()
