"""YouTube チャンネル成長の目的とツールセット。

汎用の AutonomousAgent に渡す Objective とツール一覧をここで組み立てる。
他プロジェクト用の objective を足すときはこのファイルを雛形にする。
"""

from __future__ import annotations

from ..core import Objective
from ..memory import Memory
from ..tools.base import Tool
from ..tools.browser import BROWSER_TOOLS
from ..tools.memory_tools import build_memory_tools
from ..tools.notify import NOTIFY_TOOL
from ..tools.shell import SHELL_TOOL
from ..tools.video_gen import (
    CHECK_VOICEVOX_TOOL,
    GENERATE_SHORT_TOOL,
    RESTART_VOICEVOX_TOOL,
)
from ..tools.youtube import (
    OBSERVE_STATUS_TOOL,
    REFRESH_TOKEN_TOOL,
    UPLOAD_TOOL,
)

CHANNELS = ["scp-lab", "daily-science"]

OBJECTIVE = Objective(
    name="youtube-growth",
    mission=(
        f"対象チャンネル {CHANNELS} を着実に運用し、継続的に成長させる。\n"
        "短期の最優先KPIは『各チャンネルが毎日ショートを1本以上、公開(public)で投稿し続けること』。"
        "中期的にはサムネ品質・台本の質・競合分析を通じて視聴数と登録者を伸ばす。"
    ),
    guidance=(
        "- 各チャンネルについて、まず observe_post_status で『今日まだ投稿していないか』を確認する。\n"
        "- 今日未投稿なら: VOICEVOX 確認 → generate_short で生成 → upload_to_youtube(privacy=public, is_short=true) で投稿。\n"
        "- 既に今日投稿済みなら、その日の必須投稿は完了。余力があればサムネや競合分析の改善を検討してよいが、無理はしない。\n"
        "- 生成時に VOICEVOX が落ちていたら restart_voicevox で復旧してから再試行する。\n"
        "- アップロードで認証エラーが出たら refresh_youtube_token を試す。それでも駄目（refresh_token 失効）なら、"
        "youtube_reauth でブラウザから OAuth 連携をやり直す。自動完了できれば再びアップロードを試す。\n"
        "- youtube_reauth が needs_human を返した（Googleログイン/2FA が必要）ときだけ notify_user で『UI再認証が必要』と通知する。\n"
        "- 投稿状況やアップロード結果を UI でも確認したいときは browser_observe で /channels/{id}/config や YouTube Studio を見る。\n"
        "- 台本生成の API エラーは generate_short 内で OpenAI→Claude フォールバックと再試行が行われる。数回失敗したら原因を記録し次サイクルに回す。\n"
        "- アップロードした動画のURLは必ずログに残す（行動ログに自動記録される）。\n"
        "- 1サイクルでは『各チャンネル最大1本の投稿』までに留め、過剰投稿しない。\n"
        "- 同じ失敗を繰り返さないよう、対処できたエラーは remember に knowhow として残す。"
    ),
)


def build_tools(memory: Memory) -> list[Tool]:
    return [
        OBSERVE_STATUS_TOOL,
        CHECK_VOICEVOX_TOOL,
        RESTART_VOICEVOX_TOOL,
        GENERATE_SHORT_TOOL,
        REFRESH_TOKEN_TOOL,
        UPLOAD_TOOL,
        *BROWSER_TOOLS,
        SHELL_TOOL,
        NOTIFY_TOOL,
        *build_memory_tools(memory),
    ]
