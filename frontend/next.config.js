/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The app has no `'use server'` actions, so the previous
  // `experimental.serverActions.allowedOrigins: ['localhost:3000']` block was
  // dead config — and would have rejected actions from the Vercel origin the
  // moment one was added.
  //
  // The backend lives behind a tunnel, so every route is dynamic and nothing is
  // cached at the CDN. Keep the response small on the wire instead.
  compress: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
};

module.exports = nextConfig;
