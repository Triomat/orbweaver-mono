/**
 * Thin $fetch wrapper for the orbweaver REST API.
 *
 * All methods return the raw response data (throws on HTTP error).
 */

import type {
  BackendStatus,
  CollectorInfo,
  DiscoverJobResponse,
  IngestRequest,
  IngestResponse,
  ItemStatus,
  ReviewItem,
  ReviewSession,
  ReviewSummary,
  SeedResult,
} from '~/types/api'

export function useApi() {
  const config = useRuntimeConfig()
  const base = config.public.apiBase as string

  function url(path: string) {
    return `${base}${path}`
  }

  // ── Status ───────────────────────────────────────────────────────────────

  function getStatus(): Promise<BackendStatus> {
    return $fetch(url('/api/v1/status'))
  }

  // ── Capabilities ────────────────────────────────────────────────────────

  function listCollectors(): Promise<{ collectors: CollectorInfo[] }> {
    return $fetch(url('/api/v1/collectors'))
  }

  // ── Discover ────────────────────────────────────────────────────────────

  function triggerDiscover(body: string, contentType: string = 'application/x-yaml'): Promise<DiscoverJobResponse> {
    return $fetch(url('/api/v1/discover'), {
      method: 'POST',
      body,
      headers: { 'Content-Type': contentType },
    })
  }

  function pollDiscoverJob(jobId: string): Promise<ReviewSummary> {
    return $fetch(url(`/api/v1/discover/${jobId}`))
  }

  // ── Reviews ─────────────────────────────────────────────────────────────

  function listReviews(): Promise<{ reviews: ReviewSummary[] }> {
    return $fetch(url('/api/v1/reviews'))
  }

  function getReview(id: string): Promise<ReviewSession> {
    return $fetch(url(`/api/v1/reviews/${id}`))
  }

  function deleteReview(id: string): Promise<{ detail: string }> {
    return $fetch(url(`/api/v1/reviews/${id}`), { method: 'DELETE' })
  }

  function patchDeviceItem(
    reviewId: string,
    index: number,
    body: { status?: ItemStatus; data?: Record<string, unknown> },
  ): Promise<ReviewItem> {
    return $fetch(url(`/api/v1/reviews/${reviewId}/items/devices/${index}`), {
      method: 'PATCH',
      body,
    })
  }

  function bulkUpdate(
    reviewId: string,
    action: ItemStatus,
    indices?: number[],
  ): Promise<{ updated: number }> {
    return $fetch(url(`/api/v1/reviews/${reviewId}/bulk`), {
      method: 'POST',
      body: { action, ...(indices !== undefined ? { indices } : {}) },
    })
  }

  function ingest(reviewId: string, opts: IngestRequest = {}): Promise<IngestResponse> {
    return $fetch(url(`/api/v1/reviews/${reviewId}/ingest`), {
      method: 'POST',
      body: opts,
    })
  }

  // ── Seed ──────────────────────────────────────────────────────────────────

  function seedInfrastructure(yamlBody: string): Promise<SeedResult> {
    return $fetch(url('/api/v1/seed'), {
      method: 'POST',
      body: yamlBody,
      headers: { 'Content-Type': 'application/x-yaml' },
    })
  }

  return {
    getStatus,
    listCollectors,
    triggerDiscover,
    pollDiscoverJob,
    listReviews,
    getReview,
    deleteReview,
    patchDeviceItem,
    bulkUpdate,
    ingest,
    seedInfrastructure,
  }
}
