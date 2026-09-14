"""entity_gate — 実在人物名・第三者キャラ IP をテーマ／タイトルから弾く機械ゲート。

背景（2026-09-14）:
    scp-lab で『なぜ堀大輔は72時間眠らないのか？睡眠不足の恐怖』が公開された。
    トレンド語「ショートスリーパー」から trend_scanner が
    「ショートスリーパー堀大輔とSCP: 睡眠不足の恐怖」を theme_queue の先頭に差し込み、
    生成側はテーマをロックして書くので、**実在の著者を SCP オブジェクトとして扱う**
    動画がそのまま出た。theme_blacklist は事後対応で、次のトレンド語には効かない。

設計:
    - 判定は決定論的（辞書＋パターン）。LLM に頼らない（Claude が落ちている日でも効く）。
        1) 敬称・肩書き付きの名前（「◯◯氏」「◯◯選手」「◯◯社長」「◯◯容疑者」…）
        2) ラテン文字のフルネーム（「Elon Musk」）。中黒つきカタカナは「ドン・キホーテ」と
           区別できないので使わない（海外の著名人は辞書と敬称で拾う）
        3) 日本人の姓（頻出 ~200）＋名の連なり（「堀大輔」「田中角栄」）。地名・団体名の
           語尾（県/市/大学/社…）で終わる語は除外し、頻出の一般語は個別に除外する。
        4) 既知の著名人・YouTuber・第三者キャラ IP の辞書
    - 通す場所（テーマが入る全経路）:
        trend_scanner._queue_theme / queue_detection（自動・手動キュー投入）
        comment_demand._queue_theme（コメント要望からの投入）
        generator._dedupe_theme（硬い却下。seeds や手入力のキューも含めて最終ゲート）
        generator の最終タイトル（→ publish_blocked。題材に無くても LLM が名前を足す）
    - チャンネル側の許可: `entity_gate.allow` に "person" / "ip" を列挙すると、その種別は
      通す（切り抜き ch は本人の動画なので person を許す等）。

公開 API:
    check(text, channel_dict=None) -> Optional[Hit]   # 当たれば (kind, matched, reason)
    is_blocked(text, channel_dict=None) -> bool
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Set


class Hit(NamedTuple):
    kind: str      # "person" | "ip"
    matched: str   # 当たった文字列
    reason: str    # 人が読める理由


# ---------------------------------------------------------------------
# 辞書
# ---------------------------------------------------------------------

# 日本人の姓（頻出）。名を伴って現れたときだけ人名とみなす（単独では判定しない）。
SURNAMES: frozenset = frozenset("""
佐藤 鈴木 高橋 田中 伊藤 渡辺 山本 中村 小林 加藤 吉田 山田 佐々木 山口 松本 井上 木村 林 斎藤 清水
山崎 森 池田 橋本 阿部 石川 山下 中島 石井 小川 前田 岡田 長谷川 藤田 後藤 近藤 村上 遠藤 青木 坂本
斉藤 福田 太田 西村 藤井 金子 岡本 藤原 中野 三浦 原田 松田 竹内 中川 中山 小野 田村 竹田 和田 石田
上田 森田 原 柴田 酒井 工藤 横山 宮崎 宮本 内田 高木 安藤 島田 谷口 大野 高田 丸山 今井 河野 藤本
村田 武田 上野 杉山 増田 小島 平野 大塚 千葉 久保 松井 岩崎 桜井 野口 松尾 野村 木下 菊地 佐野 大西
杉本 新井 浜田 菅原 市川 水野 小松 島崎 古川 小山 高野 渡部 本田 服部 中田 川口 平田 永井 吉川 岡
関 松岡 川崎 星野 内藤 荒木 大久保 早川 望月 福島 川上 大島 土屋 堀 樋口 尾崎 篠原 秋山 松下 石原
熊谷 堀内 松浦 荒井 川村 菊池 岩田 土井 岡崎 東 松村 平井 岩本 松永 白石 三宅 堀田 黒田 児玉 沢田
西田 中西 片山 大石 北村 安田 榎本 前川 中島 小池 宮田 小沢 矢野 秋元 五十嵐 神田 出口 柳 牧野 田口
""".split())

# 姓＋名のように見えても人名ではない語（地名・一般語）。姓リストで拾ってしまう頻出語。
_NOT_A_NAME: frozenset = frozenset("""
森林 林業 林道 原因 原理 原発 原子 原稿 原点 原則 原料 原作 東京 東北 東西 東洋 東海 東部 東側 東日本
関係 関連 関心 関東 関西 関節 堀内 岡山 山口県 中島 中野区 柳川 森永 星野源 大西洋 小島 金子
上田市 太田市 松本市 高橋 岡本 石川県 山田線 中田 岡田 平野 平井 平田 大野 大島 大石 東大 東映
""".split())

# 地名・組織・施設の語尾。これで終わる漢字連は人名ではない。
_PLACE_SUFFIX_RE = re.compile(
    r"(?:都|道|府|県|市|区|町|村|郡|駅|港|空港|大学|高校|中学|小学校|学園|学院|病院|銀行|証券|"
    r"製薬|商事|工業|電機|重工|物産|不動産|建設|運輸|鉄道|放送|新聞|出版|書店|神社|寺|城|山|川|"
    r"湖|島|岬|峠|海|湾|平野|盆地|高原|温泉|公園|球場|会館|会社|株式|協会|連盟|財団|党|省|庁|局|署|"
    r"隊|軍|藩|家|流|派|式|法|論|学|教|道|術|症|病|菌|素|体|質|力|性|的|化|率|数|量|時代|文化|"
    r"社会|経済|技術|研究|効果|理論|現象|問題|事件|事故|制度|政策|戦争|革命|運動|主義|世紀)$"
)

# 敬称・肩書き。直前の 2〜8 字（漢字/カナ/英字）を人名とみなす。
# 「さん/くん/ちゃん/先生」は入れない — 妖怪・2ch の題材（トイレの花子さん、コマさん、
# 上司さん）で誤爆する。実在人物なら KNOWN_PERSONS か姓＋名の規則で拾う。
_HONORIFIC_RE = re.compile(
    r"([一-龥々ァ-ヶーA-Za-z]{2,8})"
    r"(?:氏|教授|博士|選手|監督|コーチ|社長|会長|CEO|代表|部長|"
    r"議員|首相|総理|大臣|知事|市長|長官|総裁|党首|大統領|陛下|殿下|容疑者|被告|受刑者|"
    r"アナ|アナウンサー|記者|師匠|親方|力士|横綱|棋士|名人|俳優|女優|歌手|芸人|声優|作家|"
    r"YouTuber|ユーチューバー|インフルエンサー|配信者|VTuber)(?![一-龥ァ-ヶ])"
)

# ラテン文字のフルネーム（Elon Musk）。カタカナの中黒形は使わない（→ _person_hits）。
_LATIN_FULLNAME_RE = re.compile(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b")

# 既知の著名人・YouTuber（トレンドに乗りやすく、辞書ヒューリスティックで拾えない表記）。
KNOWN_PERSONS: frozenset = frozenset("""
ヒカキン HIKAKIN はじめしゃちょー ヒカル コムドット 東海オンエア 水溜りボンド フィッシャーズ
中田敦彦 ホリエモン 堀江貴文 ひろゆき 西村博之 DaiGo メンタリストDaiGo 成田悠輔 岡田斗司夫
大谷翔平 久保建英 三笘薫 藤井聡太 羽生結弦 池江璃花子 井上尚弥 松山英樹 山本由伸 佐々木朗希
石破茂 岸田文雄 安倍晋三 麻生太郎 小泉進次郎 高市早苗 玉木雄一郎 山本太郎 蓮舫 小池百合子
トランプ プーチン ゼレンスキー イーロン・マスク マスク氏 ジョブズ ビル・ゲイツ ザッカーバーグ
堀大輔 深田えいみ 金子みゆ 松本人志 明石家さんま ビートたけし タモリ 有吉弘行
星野源 米津玄師 藤井風 YOASOBI Ado 新垣結衣 橋本環奈 綾瀬はるか 北川景子 目黒蓮 大泉洋
""".split())

# 第三者のキャラクター IP・作品名。チャンネルが自分の題材として持っているもの
# （pokemon-lab の「ポケモン」等）は `entity_gate.allow: ["ip"]` か `own_ip` で許す。
THIRD_PARTY_IP: frozenset = frozenset("""
ゼルダ マリオ ルイージ カービィ ピクミン スプラトゥーン どうぶつの森 あつ森 ポケモン ポケカ
ドラクエ ドラゴンクエスト ファイナルファンタジー FF7 FF14 モンハン モンスターハンター
鬼滅の刃 鬼滅 ワンピース ONEPIECE ドラゴンボール ナルト NARUTO 呪術廻戦 進撃の巨人 ハイキュー
スラムダンク 名探偵コナン コナン ドラえもん クレヨンしんちゃん サザエさん ちびまる子 アンパンマン
ジブリ トトロ ナウシカ 千と千尋 ディズニー ミッキー アナ雪 ピクサー マーベル アベンジャーズ
スターウォーズ ハリーポッター ガンダム エヴァンゲリオン エヴァ プリキュア 仮面ライダー ウルトラマン
戦隊 妖怪ウォッチ ちいかわ サンリオ ハローキティ キティ すみっコぐらし リラックマ 原神 ウマ娘
フォートナイト マインクラフト マイクラ Apex エーペックス スマブラ 推しの子 チェンソーマン
SPY×FAMILY スパイファミリー 東京リベンジャーズ ブルーロック 葬送のフリーレン フリーレン ダンダダン
""".split())

# チャンネルが自分の題材として持つ IP（ここに載る語はその ch では弾かない）。
OWN_IP_BY_CHANNEL: Dict[str, Set[str]] = {
    "pokemon-lab": {"ポケモン", "ポケカ"},
    # 妖怪ラボは伝承の元ネタと「妖怪ウォッチ」の設定を比較する題材を意図的に持つ
    # （09-13 時点でキューに 6 件）。作品評論なので通す。
    "yokai-watch": {"妖怪ウォッチ"},
}

_KANJI_RUN_RE = re.compile(r"[一-龥々]{2,7}")

# 名（下の名前）によく使われる漢字。「姓＋名」と判定するには名の側にこのどれかが要る。
# 「森林」「原因」「関西」「林業」のような一般語を姓＋名と誤認しないための条件。
GIVEN_NAME_KANJI: frozenset = frozenset(
    "太郎一二三四五六七八九十郎介助輔亮涼翔大介祐佑優悠裕勇勇健賢謙拓卓琢拓也哉弥矢弘浩宏博紘"
    "寛広光晃幸孝考幸吉吉義善良朗郎明昭彰章秀英栄栄雄夫男生真慎伸信新伸進晋司志史誌士嗣"
    "隆崇貴喜嘉樹稔稔実豊智知友朋和一樹陽春夏秋冬雅正政匡将勝征成茂重恵慶圭桂啓敬佳"
    "子美恵香奈菜菜穂帆遥陽葉子絵衣衣里理莉梨李麻真由結愛彩綾綺希望未来紗沙咲花華瞳眞乃"
    "角栄純潤淳順治春夫朝道守護俊駿峻竜龍辰達徹哲鉄浩司勇気元源亜杏杏央桜楓凛凜"
)


# ---------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------

def _allowed_kinds(channel_dict: Optional[Dict[str, Any]]) -> Set[str]:
    raw = channel_dict or {}
    cfg = raw.get("entity_gate")
    allow: Set[str] = set()
    if isinstance(cfg, dict):
        for k in (cfg.get("allow") or []):
            k = str(k or "").strip().lower()
            if k in ("person", "ip"):
                allow.add(k)
        if cfg.get("enabled") is False:
            allow |= {"person", "ip"}
    # 切り抜き ch は本人の動画を扱うので人物名は前提（設定が無くても許す）
    style = str(raw.get("style") or "").lower()
    if style == "clip" or raw.get("clip"):
        allow.add("person")
    return allow


def _own_ips(channel_dict: Optional[Dict[str, Any]]) -> Set[str]:
    raw = channel_dict or {}
    own: Set[str] = set(OWN_IP_BY_CHANNEL.get(str(raw.get("id") or ""), set()))
    cfg = raw.get("entity_gate")
    if isinstance(cfg, dict):
        own |= {str(x).strip() for x in (cfg.get("own_ip") or []) if str(x or "").strip()}
    return own


def _looks_like_japanese_name(run: str) -> bool:
    """漢字連が「頻出の姓＋名」の形か。"""
    if run in _NOT_A_NAME or _PLACE_SUFFIX_RE.search(run):
        return False
    for n in (2, 3, 1):  # 姓は 2 字が最多、次に 3 字、最後に 1 字（堀/林/森/原/関/東/岡/柳）
        sur, given = run[:n], run[n:]
        if sur not in SURNAMES or not (1 <= len(given) <= 3):
            continue
        # 1 字姓（堀・林・森・原…）は一般語と衝突しやすいので、名は 2 字ちょうどに限る
        if n == 1 and len(given) != 2:
            continue
        # 名の側に「名前らしい漢字」が 1 つも無ければ一般語（森林・原因・関西・林業）
        if not any(ch in GIVEN_NAME_KANJI for ch in given):
            continue
        return True
    return False


def _person_hits(text: str) -> List[Hit]:
    out: List[Hit] = []
    for name in KNOWN_PERSONS:
        if name and name in text:
            out.append(Hit("person", name, f"著名人『{name}』"))
    for m in _HONORIFIC_RE.finditer(text):
        out.append(Hit("person", m.group(0), f"敬称・肩書き付きの人名『{m.group(0)}』"))
    # 中黒つきカタカナ（ドナルド・トランプ）は「ドン・キホーテ」「オールド・マン」のような
    # ブランド名・作中呼称と形が同じで区別できないため、人名の根拠にはしない。
    # 海外の著名人は KNOWN_PERSONS と敬称（大統領/氏）で拾う。
    for m in _LATIN_FULLNAME_RE.finditer(text):
        out.append(Hit("person", m.group(0), f"英字のフルネーム『{m.group(0)}』"))
    for m in _KANJI_RUN_RE.finditer(text):
        run = m.group(0)
        if _looks_like_japanese_name(run):
            out.append(Hit("person", run, f"姓＋名の形『{run}』"))
    return out


def _ip_pattern(ip: str) -> "re.Pattern[str]":
    """IP 名の照合パターン。カタカナ語はカタカナ連の境界で切る
    （「ピグマリオン効果」の中の「マリオ」を拾わない）。"""
    esc = re.escape(ip)
    if re.fullmatch(r"[ァ-ヶー]+", ip):
        return re.compile(rf"(?<![ァ-ヶー]){esc}(?![ァ-ヶー])")
    if re.fullmatch(r"[A-Za-z0-9×]+", ip):
        return re.compile(rf"(?<![A-Za-z0-9]){esc}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(esc)


_IP_PATTERNS = [(ip, _ip_pattern(ip)) for ip in sorted(THIRD_PARTY_IP, key=len, reverse=True)]


def _ip_hits(text: str, own: Set[str]) -> List[Hit]:
    out: List[Hit] = []
    for ip, pat in _IP_PATTERNS:
        if ip in own:
            continue
        if pat.search(text):
            out.append(Hit("ip", ip, f"第三者IP『{ip}』"))
    return out


def check(text: Optional[str], channel_dict: Optional[Dict[str, Any]] = None) -> Optional[Hit]:
    """text（テーマ題名・タイトル）に実在人物／第三者IPが含まれれば最初の Hit を返す。"""
    s = (text or "").strip()
    if not s:
        return None
    allowed = _allowed_kinds(channel_dict)
    hits: List[Hit] = []
    if "person" not in allowed:
        hits += _person_hits(s)
    if "ip" not in allowed:
        hits += _ip_hits(s, _own_ips(channel_dict))
    return hits[0] if hits else None


def is_blocked(text: Optional[str], channel_dict: Optional[Dict[str, Any]] = None) -> bool:
    return check(text, channel_dict) is not None


def filter_titles(titles: Iterable[str], channel_dict: Optional[Dict[str, Any]] = None) -> List[str]:
    """通るものだけを順序保持で返す（バッチ用）。"""
    return [t for t in titles if t and not is_blocked(t, channel_dict)]
