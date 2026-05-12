import Link from 'next/link';

export default function Header({
  title = '🎬 YouTube Factory',
  back,
  actions,
  showNav = false,
}: {
  title?: React.ReactNode;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
  showNav?: boolean;
}) {
  return (
    <header className="px-5 pt-5 pb-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          {back && (
            <Link
              href={back.href}
              className="block text-sm text-slate-400 hover:text-slate-200 mb-1"
            >
              ← {back.label}
            </Link>
          )}
          <h1 className="text-xl font-bold text-accent truncate">{title}</h1>
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
      {showNav && (
        <nav className="mt-3 flex gap-2 overflow-x-auto -mx-1 px-1 pb-1">
          <NavLink href="/" emoji="🏠" label="ホーム" />
          <NavLink href="/generate" emoji="🎬" label="生成" />
          <NavLink href="/schedule" emoji="⏰" label="スケジュール" />
          <NavLink href="/analytics" emoji="📈" label="分析" />
          <NavLink href="/history" emoji="📊" label="履歴" />
          <NavLink href="/archives" emoji="📚" label="アーカイブ" />
          <NavLink href="/logs" emoji="📜" label="ログ" />
          <NavLink href="/settings" emoji="⚙️" label="設定" />
        </nav>
      )}
    </header>
  );
}

function NavLink({
  href,
  emoji,
  label,
}: {
  href: string;
  emoji: string;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold bg-bg-elev border border-border text-slate-300 hover:bg-slate-700 hover:text-white transition"
    >
      {emoji} {label}
    </Link>
  );
}
