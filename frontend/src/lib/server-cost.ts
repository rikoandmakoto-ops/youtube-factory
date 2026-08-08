import 'server-only';
import { cache } from 'react';
import { getCostSummary, type CostSummary } from './api';

/**
 * Request-scoped dedupe for the cost summary.
 *
 * `HeaderCostBadge` and `MonthlyCostSummary` both render on the dashboard and
 * both need the same payload. `getCostSummary` passes `cache: 'no-store'`, so
 * Next's own fetch memoization is off and each component would open its own
 * round-trip to the backend — doubling a call that sits directly on the page's
 * TTFB. React's `cache()` collapses them into one per render pass.
 *
 * This module is `server-only` on purpose: `cache()` has no meaning in a client
 * bundle, and `api.ts` is imported by client components too, so the wrapper
 * cannot live there.
 */
export const getCostSummaryCached = cache(
  async (): Promise<CostSummary> => getCostSummary()
);
