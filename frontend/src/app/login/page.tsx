import LoginForm from './LoginForm';

export default function LoginPage({
  searchParams,
}: {
  searchParams: { next?: string };
}) {
  return (
    <main className="min-h-screen flex items-center justify-center px-5">
      <div className="w-full max-w-sm card p-7 shadow-2xl">
        <h1 className="text-2xl font-bold text-accent text-center">
          🎬 YouTube Factory
        </h1>
        <p className="text-center text-sm text-slate-400 mt-1 mb-6">
          動画生成管理パネル
        </p>
        <LoginForm next={searchParams?.next} />
        <p className="text-center text-xs text-slate-500 mt-5">
          🔒 認証付き・外部アクセス対応
        </p>
        <p className="text-center text-xs text-slate-600 mt-1">
          iPhone対応 モバイルファースト設計
        </p>
      </div>
    </main>
  );
}
