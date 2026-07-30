import { useState } from "react";

const COLORS = {
  bg: "#f8f7f4",
  card: "#ffffff",
  primary: "#e24b4a",
  primaryLight: "#fcebeb",
  accent: "#1D9E75",
  accentLight: "#E1F5EE",
  text: "#1a1a1a",
  textSec: "#6b6b6b",
  textMuted: "#999",
  border: "#eee",
  gold: "#eda100",
};

const parties = [
  { id: 1, name: "金曜ナイト飲み", area: "渋谷", venue: "炭火居酒屋 山", people: 3, time: "20:00〜", treat: "奢り", points: 500, gender: "女性", tags: ["20代", "社会人"], avatar: "🍻" },
  { id: 2, name: "週末カジュアル会", area: "六本木", venue: "Bar LUNA", people: 2, time: "21:00〜", treat: "割り勘", points: 200, gender: "女性", tags: ["25〜30歳", "お酒好き"], avatar: "🌙" },
  { id: 3, name: "仕事終わりの一杯", area: "新宿", venue: "和食ダイニング 花", people: 4, time: "19:30〜", treat: "奢り", points: 400, gender: "女性", tags: ["社会人", "まったり"], avatar: "🌸" },
  { id: 4, name: "土曜ワイン会", area: "恵比寿", venue: "Wine & Dine CAVA", people: 2, time: "19:00〜", treat: "割り勘", points: 300, gender: "女性", tags: ["ワイン好き", "大人"], avatar: "🍷" },
];

const Badge = ({ children, color, bg }) => (
  <span style={{ fontSize: 11, fontWeight: 500, color, background: bg, padding: "2px 8px", borderRadius: 12, whiteSpace: "nowrap" }}>{children}</span>
);

const TabBar = ({ active, onTab }) => (
  <div style={{ display: "flex", borderTop: `1px solid ${COLORS.border}`, background: COLORS.card, padding: "6px 0 2px" }}>
    {[
      { key: "home", icon: "🏠", label: "ホーム" },
      { key: "create", icon: "✏️", label: "会を作る" },
      { key: "chat", icon: "💬", label: "チャット" },
      { key: "points", icon: "💎", label: "ポイント" },
      { key: "mypage", icon: "👤", label: "マイページ" },
    ].map(t => (
      <button key={t.key} onClick={() => onTab(t.key)} style={{ flex: 1, background: "none", border: "none", padding: "4px 0", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
        <span style={{ fontSize: 20 }}>{t.icon}</span>
        <span style={{ fontSize: 10, color: active === t.key ? COLORS.primary : COLORS.textMuted, fontWeight: active === t.key ? 600 : 400 }}>{t.label}</span>
      </button>
    ))}
  </div>
);

const PartyCard = ({ p, onTap }) => (
  <div onClick={onTap} style={{ background: COLORS.card, borderRadius: 16, padding: 16, marginBottom: 12, border: `1px solid ${COLORS.border}`, cursor: "pointer" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <span style={{ fontSize: 28 }}>{p.avatar}</span>
        <div>
          <div style={{ fontWeight: 600, fontSize: 15, color: COLORS.text }}>{p.name}</div>
          <div style={{ fontSize: 12, color: COLORS.textSec, marginTop: 2 }}>{p.venue} / {p.area}</div>
        </div>
      </div>
      <Badge color={p.treat === "奢り" ? "#854F0B" : "#0C447C"} bg={p.treat === "奢り" ? "#FAEEDA" : "#E6F1FB"}>{p.treat}</Badge>
    </div>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
      {p.tags.map(t => <Badge key={t} color={COLORS.textSec} bg="#f0f0f0">{t}</Badge>)}
    </div>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ display: "flex", gap: 16, fontSize: 12, color: COLORS.textSec }}>
        <span>👥 {p.people}人</span>
        <span>🕐 {p.time}</span>
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.primary }}>{p.points}pt</div>
    </div>
  </div>
);

const HomeScreen = ({ onDetail }) => (
  <div>
    <div style={{ padding: "16px 20px 8px" }}>
      <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 8 }}>
        {["渋谷", "新宿", "六本木", "恵比寿", "池袋"].map((a, i) => (
          <button key={a} style={{ padding: "6px 16px", borderRadius: 20, border: i === 0 ? "none" : `1px solid ${COLORS.border}`, background: i === 0 ? COLORS.primary : COLORS.card, color: i === 0 ? "#fff" : COLORS.textSec, fontSize: 13, fontWeight: 500, cursor: "pointer", whiteSpace: "nowrap" }}>{a}</button>
        ))}
      </div>
    </div>
    <div style={{ padding: "0 20px 20px" }}>
      <div style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 12 }}>近くで募集中の会 · {parties.length}件</div>
      {parties.map(p => <PartyCard key={p.id} p={p} onTap={() => onDetail(p)} />)}
    </div>
  </div>
);

const DetailScreen = ({ party, onBack }) => (
  <div>
    <div style={{ padding: "0 20px 20px" }}>
      <button onClick={onBack} style={{ background: "none", border: "none", fontSize: 14, color: COLORS.primary, cursor: "pointer", padding: "12px 0", fontWeight: 500 }}>← 戻る</button>
      <div style={{ background: COLORS.card, borderRadius: 16, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <span style={{ fontSize: 36 }}>{party.avatar}</span>
            <Badge color={party.treat === "奢り" ? "#854F0B" : "#0C447C"} bg={party.treat === "奢り" ? "#FAEEDA" : "#E6F1FB"}>{party.treat}</Badge>
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 4px", color: COLORS.text }}>{party.name}</h2>
          <p style={{ fontSize: 13, color: COLORS.textSec, margin: "0 0 20px" }}>{party.gender}グループ · {party.tags.join(" · ")}</p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
            {[
              { label: "場所", value: `${party.venue}（${party.area}）`, icon: "📍" },
              { label: "時間", value: party.time, icon: "🕐" },
              { label: "人数", value: `${party.people}人`, icon: "👥" },
              { label: "必要ポイント", value: `${party.points}pt / 人`, icon: "💎" },
            ].map(item => (
              <div key={item.label} style={{ background: "#f8f7f4", borderRadius: 12, padding: 12 }}>
                <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 4 }}>{item.icon} {item.label}</div>
                <div style={{ fontSize: 14, fontWeight: 500, color: COLORS.text }}>{item.value}</div>
              </div>
            ))}
          </div>

          <div style={{ background: COLORS.primaryLight, borderRadius: 12, padding: 14, marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: "#791F1F", marginBottom: 4 }}>合計必要ポイント</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: COLORS.primary }}>{party.points * party.people}pt</div>
            <div style={{ fontSize: 11, color: "#A32D2D" }}>{party.points}pt × {party.people}人</div>
          </div>

          <button style={{ width: "100%", padding: "14px 0", background: COLORS.primary, color: "#fff", border: "none", borderRadius: 12, fontSize: 16, fontWeight: 600, cursor: "pointer" }}>
            リクエストを送る
          </button>
        </div>
      </div>
    </div>
  </div>
);

const CreateScreen = () => {
  const [treat, setTreat] = useState("奢り");
  return (
    <div style={{ padding: "8px 20px 20px" }}>
      <h2 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 16px", color: COLORS.text }}>会を作成</h2>
      <div style={{ background: COLORS.card, borderRadius: 16, border: `1px solid ${COLORS.border}`, padding: 20 }}>
        {[
          { label: "会の名前", placeholder: "例: 金曜ナイト飲み" },
          { label: "お店", placeholder: "店舗を検索" },
          { label: "エリア", placeholder: "例: 渋谷" },
        ].map(f => (
          <div key={f.label} style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 13, fontWeight: 500, color: COLORS.textSec, display: "block", marginBottom: 6 }}>{f.label}</label>
            <input placeholder={f.placeholder} style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: `1px solid ${COLORS.border}`, fontSize: 14, outline: "none", boxSizing: "border-box" }} />
          </div>
        ))}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500, color: COLORS.textSec, display: "block", marginBottom: 6 }}>人数</label>
            <select style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: `1px solid ${COLORS.border}`, fontSize: 14, background: "#fff" }}>
              {[1,2,3,4,5].map(n => <option key={n}>{n}人</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500, color: COLORS.textSec, display: "block", marginBottom: 6 }}>時間</label>
            <input type="time" defaultValue="20:00" style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: `1px solid ${COLORS.border}`, fontSize: 14, boxSizing: "border-box" }} />
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, fontWeight: 500, color: COLORS.textSec, display: "block", marginBottom: 6 }}>お会計</label>
          <div style={{ display: "flex", gap: 8 }}>
            {["奢り", "割り勘"].map(t => (
              <button key={t} onClick={() => setTreat(t)} style={{ flex: 1, padding: "10px 0", borderRadius: 10, border: treat === t ? `2px solid ${COLORS.primary}` : `1px solid ${COLORS.border}`, background: treat === t ? COLORS.primaryLight : COLORS.card, color: treat === t ? COLORS.primary : COLORS.textSec, fontSize: 14, fontWeight: 500, cursor: "pointer" }}>{t}</button>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 13, fontWeight: 500, color: COLORS.textSec, display: "block", marginBottom: 6 }}>必要ポイント（1人あたり）</label>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="number" defaultValue={300} style={{ flex: 1, padding: "10px 12px", borderRadius: 10, border: `1px solid ${COLORS.border}`, fontSize: 14, boxSizing: "border-box" }} />
            <span style={{ fontSize: 14, color: COLORS.textSec }}>pt</span>
          </div>
        </div>

        <button style={{ width: "100%", padding: "14px 0", background: COLORS.primary, color: "#fff", border: "none", borderRadius: 12, fontSize: 16, fontWeight: 600, cursor: "pointer" }}>会を作成する</button>
      </div>
    </div>
  );
};

const PointsScreen = () => {
  const [tab, setTab] = useState("buy");
  return (
    <div style={{ padding: "8px 20px 20px" }}>
      <div style={{ background: `linear-gradient(135deg, ${COLORS.primary}, #c93030)`, borderRadius: 16, padding: 24, marginBottom: 16, color: "#fff" }}>
        <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>ポイント残高</div>
        <div style={{ fontSize: 36, fontWeight: 700, marginBottom: 4 }}>2,450<span style={{ fontSize: 16, fontWeight: 400 }}>pt</span></div>
        <div style={{ fontSize: 12, opacity: 0.7 }}>有効期限: 2027/01/23</div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {[{ key: "buy", label: "購入" }, { key: "convert", label: "オリパpt変換" }, { key: "history", label: "履歴" }].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{ flex: 1, padding: "8px 0", borderRadius: 10, border: tab === t.key ? `2px solid ${COLORS.primary}` : `1px solid ${COLORS.border}`, background: tab === t.key ? COLORS.primaryLight : COLORS.card, color: tab === t.key ? COLORS.primary : COLORS.textSec, fontSize: 13, fontWeight: 500, cursor: "pointer" }}>{t.label}</button>
        ))}
      </div>

      {tab === "buy" && (
        <div style={{ background: COLORS.card, borderRadius: 16, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16, color: COLORS.text }}>ポイントを購入</div>
          {[
            { amount: 500, price: 500, bonus: 0 },
            { amount: 1100, price: 1000, bonus: 100 },
            { amount: 2400, price: 2000, bonus: 400, popular: true },
            { amount: 5500, price: 5000, bonus: 500 },
            { amount: 12000, price: 10000, bonus: 2000 },
          ].map(p => (
            <div key={p.price} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: `1px solid ${COLORS.border}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>{p.amount.toLocaleString()}pt</span>
                {p.bonus > 0 && <Badge color="#085041" bg="#E1F5EE">+{p.bonus}ボーナス</Badge>}
                {p.popular && <Badge color="#854F0B" bg="#FAEEDA">人気</Badge>}
              </div>
              <button style={{ padding: "8px 16px", borderRadius: 10, border: "none", background: COLORS.primary, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>¥{p.price.toLocaleString()}</button>
            </div>
          ))}
        </div>
      )}

      {tab === "convert" && (
        <div style={{ background: COLORS.card, borderRadius: 16, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16, color: COLORS.text }}>オリパポイントに変換</div>
          <div style={{ background: "#f8f7f4", borderRadius: 12, padding: 16, marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>変換元</div>
                <div style={{ fontSize: 20, fontWeight: 600, color: COLORS.text }}>1,000<span style={{ fontSize: 13 }}>pt</span></div>
              </div>
              <span style={{ fontSize: 24 }}>→</span>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>変換先（オリパpt）</div>
                <div style={{ fontSize: 20, fontWeight: 600, color: COLORS.accent }}>850<span style={{ fontSize: 13 }}>pt</span></div>
              </div>
            </div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, textAlign: "center" }}>変換レート: 1pt → 0.85オリパpt（手数料15%）</div>
          </div>
          <input type="range" min={100} max={2450} step={50} defaultValue={1000} style={{ width: "100%", marginBottom: 16 }} />
          <button style={{ width: "100%", padding: "14px 0", background: COLORS.accent, color: "#fff", border: "none", borderRadius: 12, fontSize: 16, fontWeight: 600, cursor: "pointer" }}>変換する</button>
        </div>
      )}

      {tab === "history" && (
        <div style={{ background: COLORS.card, borderRadius: 16, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16, color: COLORS.text }}>取引履歴</div>
          {[
            { date: "7/22", desc: "ポイント購入", amount: "+2,400pt", color: COLORS.accent },
            { date: "7/21", desc: "相席マッチ（渋谷）", amount: "-1,500pt", color: COLORS.primary },
            { date: "7/20", desc: "オリパpt変換", amount: "-500pt", color: COLORS.textSec },
            { date: "7/18", desc: "ポイント購入", amount: "+1,100pt", color: COLORS.accent },
          ].map((h, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: i < 3 ? `1px solid ${COLORS.border}` : "none" }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 500, color: COLORS.text }}>{h.desc}</div>
                <div style={{ fontSize: 11, color: COLORS.textMuted }}>{h.date}</div>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: h.color }}>{h.amount}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ChatScreen = () => (
  <div style={{ padding: "8px 20px 20px" }}>
    <h2 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 16px", color: COLORS.text }}>チャット</h2>
    {[
      { name: "金曜ナイト飲み", last: "じゃあ20時に集合で!", time: "18:32", unread: 2, avatar: "🍻" },
      { name: "週末カジュアル会", last: "お店変更になりました", time: "昨日", unread: 0, avatar: "🌙" },
    ].map((c, i) => (
      <div key={i} style={{ display: "flex", gap: 12, alignItems: "center", padding: 14, background: COLORS.card, borderRadius: 14, border: `1px solid ${COLORS.border}`, marginBottom: 8, cursor: "pointer" }}>
        <span style={{ fontSize: 32 }}>{c.avatar}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
            <span style={{ fontWeight: 600, fontSize: 14, color: COLORS.text }}>{c.name}</span>
            <span style={{ fontSize: 11, color: COLORS.textMuted }}>{c.time}</span>
          </div>
          <div style={{ fontSize: 13, color: COLORS.textSec, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.last}</div>
        </div>
        {c.unread > 0 && <span style={{ background: COLORS.primary, color: "#fff", fontSize: 11, fontWeight: 600, width: 20, height: 20, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center" }}>{c.unread}</span>}
      </div>
    ))}
  </div>
);

const MyPageScreen = () => (
  <div style={{ padding: "8px 20px 20px" }}>
    <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 20 }}>
      <div style={{ width: 56, height: 56, borderRadius: 28, background: COLORS.primaryLight, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24 }}>👤</div>
      <div>
        <div style={{ fontWeight: 600, fontSize: 18, color: COLORS.text }}>ザキ</div>
        <div style={{ fontSize: 13, color: COLORS.textSec }}>東京 · 28歳</div>
      </div>
    </div>
    <div style={{ background: COLORS.card, borderRadius: 16, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
      {[
        { icon: "💎", label: "ポイント残高", value: "2,450pt" },
        { icon: "📊", label: "相席回数", value: "12回" },
        { icon: "⭐", label: "評価", value: "4.8" },
        { icon: "⚙️", label: "設定" },
        { icon: "📋", label: "利用規約" },
        { icon: "🚪", label: "ログアウト" },
      ].map((item, i) => (
        <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 20px", borderBottom: i < 5 ? `1px solid ${COLORS.border}` : "none", cursor: "pointer" }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span>{item.icon}</span>
            <span style={{ fontSize: 14, color: COLORS.text }}>{item.label}</span>
          </div>
          {item.value && <span style={{ fontSize: 14, fontWeight: 500, color: COLORS.primary }}>{item.value}</span>}
        </div>
      ))}
    </div>
  </div>
);

export default function App() {
  const [tab, setTab] = useState("home");
  const [detail, setDetail] = useState(null);

  const renderScreen = () => {
    if (detail) return <DetailScreen party={detail} onBack={() => setDetail(null)} />;
    switch (tab) {
      case "home": return <HomeScreen onDetail={setDetail} />;
      case "create": return <CreateScreen />;
      case "chat": return <ChatScreen />;
      case "points": return <PointsScreen />;
      case "mypage": return <MyPageScreen />;
      default: return <HomeScreen onDetail={setDetail} />;
    }
  };

  return (
    <div style={{ maxWidth: 390, margin: "0 auto", background: COLORS.bg, minHeight: 700, borderRadius: 24, overflow: "hidden", border: `1px solid ${COLORS.border}`, display: "flex", flexDirection: "column", fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif" }}>
      <div style={{ background: COLORS.card, padding: "14px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 20, fontWeight: 700, color: COLORS.primary }}>相席</span>
        <span style={{ fontSize: 12, color: COLORS.textMuted }}>🔔</span>
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {renderScreen()}
      </div>
      <TabBar active={tab} onTab={(t) => { setTab(t); setDetail(null); }} />
    </div>
  );
}
