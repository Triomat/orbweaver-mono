/**
 * Review state management composable.
 *
 * Wraps useApi() with reactive state, optimistic updates, and polling.
 */

import type { IngestRequest, ItemStatus, ReviewSession } from '~/types/api'

export function useReview(reviewId: Ref<string>) {
  const api = useApi()

  const session = ref<ReviewSession | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const polling = ref(false)

  // ── Fetch ────────────────────────────────────────────────────────────────

  async function fetchReview() {
    loading.value = true
    error.value = null
    try {
      session.value = await api.getReview(reviewId.value)
    } catch (e: unknown) {
      error.value = (e as Error).message ?? 'Failed to load review'
    } finally {
      loading.value = false
    }
  }

  // ── Polling (while status = pending) ─────────────────────────────────────

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function startPolling(intervalMs = 3000) {
    if (pollTimer) return
    polling.value = true
    pollTimer = setInterval(async () => {
      try {
        const summary = await api.pollDiscoverJob(reviewId.value)
        if (summary.status !== 'pending') {
          stopPolling()
          await fetchReview()
        } else {
          if (session.value) {
            session.value.status = summary.status
          }
        }
      } catch {
        stopPolling()
      }
    }, intervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    polling.value = false
  }

  onUnmounted(() => stopPolling())

  // ── Item status ──────────────────────────────────────────────────────────

  async function setDeviceStatus(index: number, status: ItemStatus) {
    if (!session.value) return
    // Optimistic update
    const old = session.value.devices[index].status
    session.value.devices[index].status = status
    try {
      await api.patchDeviceItem(reviewId.value, index, { status })
    } catch (e: unknown) {
      // Rollback on error
      session.value.devices[index].status = old
      error.value = (e as Error).message ?? 'Failed to update item'
    }
  }

  async function acceptAll() {
    if (!session.value) return
    const indices = session.value.devices.map((_, i) => i)
    await api.bulkUpdate(reviewId.value, 'accepted', indices)
    await fetchReview()
  }

  async function rejectAll() {
    if (!session.value) return
    const indices = session.value.devices.map((_, i) => i)
    await api.bulkUpdate(reviewId.value, 'rejected', indices)
    await fetchReview()
  }

  // ── Ingest ────────────────────────────────────────────────────────────────

  const ingestLoading = ref(false)
  const ingestResult = ref<Awaited<ReturnType<typeof api.ingest>> | null>(null)

  async function runIngest(opts: IngestRequest = {}) {
    ingestLoading.value = true
    ingestResult.value = null
    error.value = null
    try {
      const result = await api.ingest(reviewId.value, opts)
      ingestResult.value = result
      if (!opts.dry_run) {
        await fetchReview()
      }
    } catch (e: unknown) {
      error.value = (e as Error).message ?? 'Ingest failed'
    } finally {
      ingestLoading.value = false
    }
  }

  // ── Computed helpers ─────────────────────────────────────────────────────

  const acceptedCount = computed(
    () => session.value?.devices.filter(d => d.status === 'accepted').length ?? 0,
  )
  const rejectedCount = computed(
    () => session.value?.devices.filter(d => d.status === 'rejected').length ?? 0,
  )
  const pendingCount = computed(
    () => session.value?.devices.filter(d => d.status === 'pending').length ?? 0,
  )

  return {
    session,
    loading,
    error,
    polling,
    fetchReview,
    startPolling,
    stopPolling,
    setDeviceStatus,
    acceptAll,
    rejectAll,
    runIngest,
    ingestLoading,
    ingestResult,
    acceptedCount,
    rejectedCount,
    pendingCount,
  }
}
