"""NoimosAI の実 REST 契約クライアント（stdlib のみ）。

■ 経緯（2026-08-21 実測）

`docs.noimosai.com/api-reference/openapi.json` は今も Mintlify のサンプル
（Plant Store）のままで、**公開ドキュメント上の REST API は依然として無い**。
しかし公式 CLI が 2026-08-20 に **新スコープ `@noimosai/cli` 0.0.2** で再公開され
（旧 `@agos-labs/noimosai-cli` は npm から 404＝unpublish 済み）、その
`dist/lib/api-client.js` に実際に叩いている Firebase Cloud Functions の
エンドポイントが平文で入っている。本モジュールはそれを Python から直接叩く。

実測したベース: ``https://us-central1-seo-saas-970de.cloudfunctions.net``

| 用途 | メソッド・パス |
| --- | --- |
| APIキー検証 | ``POST /chatApiGateway/apiKey/validate`` |
| ワークスペース一覧 | ``GET  /chatApiGateway/workspaces`` |
| セッション一覧 | ``GET  /chatApiGateway/sessions?workspaceId=`` |
| セッションのメッセージ | ``GET  /chatApiGateway/messages?sessionId=`` |
| **メディアアップロード** | ``POST /providersPostApi/api/media/upload?workspaceId=&filename=`` |
| ツール一覧 | ``GET  /noimosToolBridge/tools`` |
| ツール実行 | ``POST /noimosToolBridge/tools/{server}/{name}`` |
| **エージェント実行** | ``POST {region}/runNoimosMainAgentHttp``（NDJSON ストリーム） |

疎通確認（2026-08-21）: 認証なしで叩くと ``401 {"error":"Invalid API key format"}``
が返る＝**エンドポイントは実在して認証ゲートだけが立っている**。

■ 08-04 調査からの決定的な差分

旧 CLI 0.0.9 には「素材動画をアップロードするエンドポイントが無い」ため
NoimosAI に長尺素材を渡す手段が無く、`docs/CLIP_CHANNEL.md` は
「無人自動化の切り抜きエンジンとしては使えない」と結論していた。
**新 CLI には `uploadMedia` があり、`postMessage` の `mediaPaths` に
そのパスを載せられる**。これで「ローカルの長尺 mp4 を渡す」経路が開通した。

■ リージョン

エージェント実行だけはリージョン解決が入る（CLI の `agent-region.js` と同じ規則）。
タイムゾーンが Asia/ Pacific/ Australia/ なら ``asia-northeast1``、他は
``us-central1``。他のエンドポイントはベースのまま。

■ 認証

``NOIMOS_API_KEY``（Bearer）。CLI は OAuth セッショントークン（``nms_sess_``
接頭辞）も使うが、無人運用では失効時に人手が要るので本クライアントは
API キーのみを扱う。
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

DEFAULT_API_ENDPOINT = "https://us-central1-seo-saas-970de.cloudfunctions.net"

#: CLI の agent-region.js と同じ既知リージョン
KNOWN_REGIONS = ("us-central1", "asia-northeast1")

#: エージェント実行の関数名（V2 が既定。V1 は runNoimosAgent）
MAIN_AGENT_FUNCTION = "runNoimosMainAgentHttp"
LEGACY_AGENT_FUNCTION = "runNoimosAgent"

#: 動画とみなす拡張子
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")

_USER_AGENT = "youtube-factory/clip_factory (noimos-api)"


class NoimosError(RuntimeError):
    """NoimosAI API 呼び出しの失敗。"""


class NoimosAuthError(NoimosError):
    """認証に失敗した（キー未設定・不正・失効）。"""


# ---------------------------------------------------------------------
# エンドポイント解決
# ---------------------------------------------------------------------

def assert_safe_endpoint(endpoint: str) -> None:
    """CLI の assertSafeApiEndpoint と同じガード。

    API キーを平文で流さないために https を強制する（loopback だけ例外）。
    """
    parsed = urllib.parse.urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise NoimosError(f"API エンドポイントが不正です: {endpoint}")
    if parsed.username or parsed.password:
        raise NoimosError(f"認証情報を埋め込んだエンドポイントは使えません: {endpoint}")
    host = (parsed.hostname or "").lower()
    loopback = host in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise NoimosError(
            f"非 HTTPS のエンドポイントは使えません（APIキーが平文で流れます）: {endpoint}"
        )


def infer_region_from_timezone() -> str:
    """CLI の inferRegionFromTimezone と同じ規則。"""
    tz = (os.environ.get("TZ") or "").strip()
    if not tz:
        try:
            # /etc/localtime -> .../zoneinfo/Asia/Tokyo
            link = os.path.realpath("/etc/localtime")
            if "zoneinfo/" in link:
                tz = link.split("zoneinfo/", 1)[1]
        except Exception:
            tz = ""
    if tz.startswith(("Asia/", "Pacific/", "Australia/")):
        return "asia-northeast1"
    return "us-central1"


def regional_endpoint(base_endpoint: str, region: str) -> str:
    """``https://<region>-<project>.cloudfunctions.net`` に付け替える。"""
    base = base_endpoint.rstrip("/")
    low = base.lower()
    if "localhost" in low or "127.0.0.1" in low:
        return base
    for r in KNOWN_REGIONS:
        prefix = f"https://{r}-"
        if low.startswith(prefix):
            rest = base[len(prefix):]
            if rest.lower().endswith(".cloudfunctions.net"):
                rest = rest[: -len(".cloudfunctions.net")]
            return f"https://{region}-{rest}.cloudfunctions.net"
    return base


def agent_endpoint(base_endpoint: str, *, version: str = "V2",
                   region: Optional[str] = None) -> str:
    fn = MAIN_AGENT_FUNCTION if str(version).upper() != "V1" else LEGACY_AGENT_FUNCTION
    base = regional_endpoint(base_endpoint, region or infer_region_from_timezone())
    return f"{base.rstrip('/')}/{fn}"


# ---------------------------------------------------------------------
# 成果物（動画URL）の抽出
# ---------------------------------------------------------------------

def looks_like_video_url(url: str) -> bool:
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        return False
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(VIDEO_EXT):
        return True
    # Firebase Storage の署名付きURLは拡張子がクエリ側に出ることがある
    lowered = url.lower()
    return any(f"{ext}?" in lowered or f"{ext}&" in lowered for ext in VIDEO_EXT)


def harvest_video_urls(payload: Any, *, _depth: int = 0) -> List[str]:
    """任意の入れ子 JSON から動画URLを再帰的に拾う。

    エージェントの応答スキーマは公開されていないので、キー名に依存せず
    「動画URLに見える文字列」と「mimeType が video/* の隣の url」を拾う。
    """
    found: List[str] = []
    if _depth > 12:
        return found

    if isinstance(payload, str):
        if looks_like_video_url(payload):
            found.append(payload)
        return found

    if isinstance(payload, dict):
        mime = str(payload.get("mimeType") or payload.get("mime_type")
                   or payload.get("contentType") or "")
        for key in ("url", "downloadUrl", "download_url", "src",
                    "videoUrl", "video_url", "mediaUrl", "media_url",
                    "publicUrl", "signedUrl"):
            val = payload.get(key)
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                if mime.startswith("video/") or looks_like_video_url(val):
                    found.append(val)
        for val in payload.values():
            found.extend(harvest_video_urls(val, _depth=_depth + 1))
        return found

    if isinstance(payload, (list, tuple)):
        for val in payload:
            found.extend(harvest_video_urls(val, _depth=_depth + 1))
    return found


def dedupe(urls: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------------------------------------------------------------------
# クライアント
# ---------------------------------------------------------------------

class NoimosClient:
    """NoimosAI Cloud Functions の薄いクライアント。"""

    def __init__(
        self,
        api_key: str,
        *,
        api_endpoint: Optional[str] = None,
        workspace_id: Optional[str] = None,
        region: Optional[str] = None,
        request_timeout: int = 120,
    ) -> None:
        if not api_key:
            raise NoimosAuthError("NOIMOS_API_KEY が空です。")
        self.api_key = api_key.strip()
        self.api_endpoint = (api_endpoint or os.environ.get("NOIMOS_API_ENDPOINT")
                             or DEFAULT_API_ENDPOINT).rstrip("/")
        assert_safe_endpoint(self.api_endpoint)
        self.workspace_id = (workspace_id or "").strip() or None
        self.region = region or infer_region_from_timezone()
        self.request_timeout = request_timeout

    # -- 低レベル ------------------------------------------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": _USER_AGENT,
        }
        headers.update(extra or {})
        return headers

    def _open(
        self,
        url: str,
        *,
        method: str = "GET",
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        context: str = "リクエスト",
    ):
        assert_safe_endpoint(url)
        req = urllib.request.Request(
            url, data=body, method=method, headers=self._headers(headers))
        try:
            return urllib.request.urlopen(req, timeout=timeout or self.request_timeout)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            if e.code in (401, 403):
                raise NoimosAuthError(
                    f"{context}が認証で拒否されました (HTTP {e.code}): {detail}"
                ) from e
            if e.code == 402:
                raise NoimosError(
                    f"{context}: クレジット不足です (HTTP 402)。NoimosAI 側で購入してください: {detail}"
                ) from e
            raise NoimosError(f"{context}に失敗 (HTTP {e.code}): {detail}") from e
        except urllib.error.URLError as e:
            raise NoimosError(f"{context}に到達できません: {e.reason}") from e

    def _json(self, url: str, *, method: str = "GET",
              payload: Optional[Dict[str, Any]] = None,
              timeout: Optional[int] = None,
              context: str = "リクエスト") -> Any:
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        with self._open(url, method=method, body=body, headers=headers,
                        timeout=timeout, context=context) as resp:
            raw = resp.read().decode("utf-8", "replace")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise NoimosError(f"{context}: JSON を解釈できません: {e}\n{raw[:300]}") from e

    # -- 認証・メタ ----------------------------------------------------

    def validate_key(self) -> Dict[str, Any]:
        """API キーが有効かを返す。"""
        data = self._json(
            f"{self.api_endpoint}/chatApiGateway/apiKey/validate",
            method="POST", payload={}, context="APIキー検証",
        )
        return data if isinstance(data, dict) else {"valid": False}

    def list_workspaces(self) -> List[Dict[str, Any]]:
        data = self._json(f"{self.api_endpoint}/chatApiGateway/workspaces",
                          context="ワークスペース一覧取得")
        return list((data or {}).get("workspaces") or [])

    def resolve_workspace_id(self) -> str:
        """workspace_id を確定する（未設定なら最初のワークスペース）。"""
        if self.workspace_id:
            return self.workspace_id
        spaces = self.list_workspaces()
        if not spaces:
            raise NoimosError("このアカウントにワークスペースがありません。")
        wid = str(spaces[0].get("id") or spaces[0].get("workspaceId") or "")
        if not wid:
            raise NoimosError(f"ワークスペースIDを取り出せません: {spaces[0]!r}")
        self.workspace_id = wid
        return wid

    # -- ツールブリッジ -------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        """呼べるツールの一覧（`[billed]` はクレジット消費）。

        クリエイティブエージェントの切り抜きツールがここに露出しているかを
        調べるための入口。カタログはサーバ側にあり認証が要る。
        """
        data = self._json(f"{self.api_endpoint}/noimosToolBridge/tools",
                          context="ツール一覧取得")
        tools = (data or {}).get("tools")
        return list(tools) if isinstance(tools, list) else []

    def run_tool(self, server: str, name: str, args: Dict[str, Any], *,
                 request_id: Optional[str] = None,
                 timeout: Optional[int] = None) -> Dict[str, Any]:
        wid = self.resolve_workspace_id()
        rid = request_id or f"yf-{int(time.time() * 1000)}"
        url = (f"{self.api_endpoint}/noimosToolBridge/tools/"
               f"{urllib.parse.quote(server, safe='')}/{urllib.parse.quote(name, safe='')}")
        return self._json(url, method="POST",
                          payload={"workspaceId": wid, "requestId": rid, "args": args},
                          timeout=timeout, context=f"ツール実行 {server}/{name}")

    # -- メディアアップロード -------------------------------------------

    def upload_media(self, path: Path, *, filename: Optional[str] = None) -> str:
        """ローカルファイルをアップロードし、agent に渡せる path を返す。

        CLI の `uploadMedia` と同じ契約：クエリに workspaceId と filename、
        本文は生バイト、Content-Type は実ファイルの MIME。
        """
        path = Path(path)
        if not path.is_file():
            raise NoimosError(f"アップロード対象がありません: {path}")
        wid = self.resolve_workspace_id()
        name = filename or path.name
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        query = urllib.parse.urlencode({"workspaceId": wid, "filename": name})
        url = f"{self.api_endpoint}/providersPostApi/api/media/upload?{query}"

        size = path.stat().st_size
        print(f"  ⬆️ NoimosAI にアップロード中: {name} ({size / (1024 * 1024):.1f} MB)")
        data = self._upload_file(url, path, mime, size)

        remote = str((data or {}).get("path") or "")
        if not remote:
            raise NoimosError(f"アップロード応答に path がありません: {str(data)[:300]}")
        print(f"  ⬆️ 完了: {remote}")
        return remote

    def _upload_file(self, url: str, path: Path, mime: str, size: int) -> Dict[str, Any]:
        # 長尺 mp4 は数百 MB になるので、全部メモリに載せずファイルから流す。
        # urllib はファイルオブジェクトを渡すと chunked にしようとするので
        # Content-Length を明示して固定長 POST にする。
        timeout = max(self.request_timeout, 900)
        with open(path, "rb") as fh:
            with self._open(url, method="POST", body=fh,
                            headers={"Content-Type": mime,
                                     "Content-Length": str(size)},
                            timeout=timeout, context="メディアアップロード") as resp:
                raw = resp.read().decode("utf-8", "replace")
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as e:
            raise NoimosError(f"アップロード応答を解釈できません: {e}\n{raw[:300]}") from e

    # -- エージェント実行（NDJSON ストリーム） ---------------------------

    def run_agent(
        self,
        query: str,
        *,
        media_paths: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        version: str = "V2",
        timeout: int = 1800,
        on_chunk: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """エージェントを走らせ、NDJSON ストリームを最後まで読む。

        戻り値は ``{"session_id", "text", "video_urls", "chunks", "error"}``。
        チャンクの型は CLI の `parseChunk` に準拠（text / final_result /
        session / workflowExecution / error / heartbeat …）。
        """
        wid = self.resolve_workspace_id()
        url = agent_endpoint(self.api_endpoint, version=version, region=self.region)
        body = json.dumps({
            "workspaceId": wid,
            "query": query,
            "sessionId": session_id,
            "mediaPaths": media_paths or [],
            "source": "CLI",
        }).encode("utf-8")

        texts: List[str] = []
        video_urls: List[str] = []
        chunks: List[Dict[str, Any]] = []
        out_session = session_id
        error: Optional[str] = None
        deadline = time.time() + timeout

        with self._open(url, method="POST", body=body,
                        headers={"Content-Type": "application/json",
                                 "Accept": "application/x-ndjson"},
                        timeout=timeout, context="エージェント実行") as resp:
            for raw_line in resp:
                if time.time() > deadline:
                    error = f"エージェントが {timeout}s 以内に終わりませんでした。"
                    break
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                chunks.append(chunk)
                if on_chunk:
                    try:
                        on_chunk(chunk)
                    except Exception:
                        pass

                ctype = chunk.get("type")
                if ctype in ("heartbeat", "alive_check"):
                    continue
                if ctype == "session" and isinstance(chunk.get("sessionId"), str):
                    out_session = chunk["sessionId"]
                elif ctype == "text" and isinstance(chunk.get("text"), str):
                    texts.append(chunk["text"])
                elif ctype == "error":
                    error = str((chunk.get("error") or {}).get("message")
                                or "エージェントがエラーを返しました")
                # 型に関係なく、どのチャンクからも動画URLは拾う
                video_urls.extend(harvest_video_urls(chunk))

        return {
            "session_id": out_session,
            "text": "".join(texts),
            "video_urls": dedupe(video_urls),
            "chunks": chunks,
            "error": error,
        }

    def get_session_messages(self, session_id: str) -> Any:
        """セッションの履歴を取る（ストリームで取りこぼした成果物の回収用）。"""
        query = urllib.parse.urlencode({"sessionId": session_id})
        return self._json(f"{self.api_endpoint}/chatApiGateway/messages?{query}",
                          context="セッション履歴取得")

    # -- ダウンロード ---------------------------------------------------

    def download(self, url: str, dest: Path, *, timeout: int = 900,
                 min_bytes: int = 10_000) -> Path:
        """成果物を落とす。まず認証付き、だめなら素で取りに行く。"""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        last_err: Optional[Exception] = None
        for headers in (self._headers(), {"User-Agent": _USER_AGENT}):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp, \
                        open(dest, "wb") as fh:
                    while True:
                        buf = resp.read(1 << 20)
                        if not buf:
                            break
                        fh.write(buf)
                size = dest.stat().st_size
                if size < min_bytes:
                    raise NoimosError(
                        f"ダウンロードしたファイルが小さすぎます: {dest} ({size} bytes)")
                return dest
            except Exception as e:  # 認証付きで弾かれる署名付きURLがあるので順に試す
                last_err = e
                continue
        raise NoimosError(f"成果物のダウンロードに失敗: {url} ({last_err})")


# ---------------------------------------------------------------------
# 便利関数
# ---------------------------------------------------------------------

def client_from_env(clip_noimos_cfg: Optional[Dict[str, Any]] = None) -> NoimosClient:
    """環境変数＋チャンネル設定から組み立てる。"""
    cfg = clip_noimos_cfg or {}
    api_key = (os.environ.get("NOIMOS_API_KEY") or "").strip()
    if not api_key:
        raise NoimosAuthError(
            "NOIMOS_API_KEY が未設定です。backend/.env に設定してください。"
        )
    return NoimosClient(
        api_key,
        api_endpoint=str(cfg.get("api_endpoint") or "") or None,
        workspace_id=(str(cfg.get("workspace_id") or "")
                      or os.environ.get("NOIMOS_WORKSPACE_ID") or None),
        region=str(cfg.get("region") or "") or None,
        request_timeout=int(cfg.get("request_timeout_sec") or 120),
    )
