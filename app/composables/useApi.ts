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

  function triggerDiscover(yamlBody: string): Promise<DiscoverJobResponse> {
    return $fetch(url('/api/v1/discover'), {
      method: 'POST',
      body: yamlBody,
      headers: { 'Content-Type': 'application/x-yaml' },
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

  // ── orb-agent config ──────────────────────────────────────────────────────

  function getOrbAgentConfig(): Promise<{ yaml: string; path: string; container: string }> {
    return $fetch(url('/api/v1/orb-agent/config'))
  }

  function setOrbAgentConfig(yamlBody: string): Promise<{ detail: string }> {
    return $fetch(url('/api/v1/orb-agent/config'), {
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
    getOrbAgentConfig,
    setOrbAgentConfig,
  }
}

// ── Standard orb API (netboxlabs/orb-discovery) ──────────────────────────────

import * as jsYaml from 'js-yaml'

// Maps orbweaver collector names → standard NAPALM driver names
const COLLECTOR_TO_DRIVER: Record<string, string> = {
  cisco_ios: 'ios',
  napalm: 'ios', // generic fallback
}

// ssh_config_file path inside the standard orb container
const SSH_CONFIG = '/opt/orb/ssh-napalm.conf'

/**
 * Transform an orbweaver policy YAML into standard-orb-compatible YAML:
 * - Replace `collector: <name>` with the equivalent NAPALM `driver:`
 * - Add `optional_args.ssh_config_file` to every scope entry
 */
function toOrbYaml(yamlStr: string): string {
  const doc = jsYaml.load(yamlStr) as Record<string, unknown>
  if (!doc?.policies) throw new Error('No policies found in YAML')

  const policies = doc.policies as Record<string, Record<string, unknown>>
  for (const policyData of Object.values(policies)) {
    const scope = policyData.scope as Record<string, unknown>[] | undefined
    if (!Array.isArray(scope) || scope.length === 0)
      throw new Error('Policy has no scope entries — add at least one device')
    for (const entry of scope) {
      if (!entry.hostname || String(entry.hostname).trim() === '')
        throw new Error('One or more devices has no hostname — fill in the form first')
      // Map collector → driver
      if (entry.collector) {
        const driver = COLLECTOR_TO_DRIVER[entry.collector as string] ?? 'ios'
        if (!entry.driver) entry.driver = driver
        delete entry.collector
      }
      // Inject ssh_config_file unless already set
      const optArgs = (entry.optional_args ?? {}) as Record<string, unknown>
      if (!optArgs.ssh_config_file) optArgs.ssh_config_file = SSH_CONFIG
      entry.optional_args = optArgs
    }
  }
  return jsYaml.dump(doc, { lineWidth: -1 })
}

export function useOrbApi() {
  const config = useRuntimeConfig()
  const orbweaverBase = config.public.apiBase as string
  const proxyBase = '/api/orb'

  /** GET /api/v1/status via CORS proxy (status check only) */
  function getOrbStatus(): Promise<Record<string, unknown>> {
    return $fetch(`${proxyBase}/status`)
  }

  /**
   * Trigger an immediate run of the orb-agent:
   * 1. Transform YAML to standard-orb format (collector→driver, ssh_config_file)
   * 2. POST to orbweaver backend /api/v1/orb-agent/trigger, which uses
   *    docker exec to reach the orb-agent's internal API
   */
  async function triggerOrbPolicy(yamlStr: string): Promise<void> {
    const orbYaml = toOrbYaml(yamlStr)
    await $fetch(`${orbweaverBase}/api/v1/orb-agent/trigger`, {
      method: 'POST',
      body: orbYaml,
      headers: { 'Content-Type': 'application/x-yaml' },
    })
  }

  return { getOrbStatus, triggerOrbPolicy }
}
