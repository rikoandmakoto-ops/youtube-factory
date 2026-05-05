import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-4 px-5 text-center">
      <h1 className="text-2xl font-bold">チャンネルが見つかりません</h1>
      <p className="text-sm text-slate-400">
        指定されたチャンネルIDは存在しません。
      </p>
      <Link href="/" className="btn-primary">
        ダッシュボードに戻る
      </Link>
    </main>
  );
}
