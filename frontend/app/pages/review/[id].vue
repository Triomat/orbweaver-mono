<script setup lang="ts">
import type { ItemStatus } from '~/types/api'

const route = useRoute()
const reviewId = computed(() => route.params.id as string)
const {
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
} = useReview(reviewId)

await fetchReview()

// If still pending (discovery in progress), start polling
if (session.value?.status === 'pending') {
  startPolling()
}

onUnmounted(() => stopPolling())

// ── Ingest dialog state ───────────────────────────────────────────────────
const showIngest = ref(false)
const dryRun = ref(false)

async function handleIngest() {
  await runIngest({
    dry_run: dryRun.value,
    statuses: ['accepted', 'pending'],
  })
  showIngest.value = false
}

// ── Helpers ───────────────────────────────────────────────────────────────
const statusColor: Record<ItemStatus, string> = {
  pending: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  accepted: 'bg-green-50 text-green-700 border-green-200',
  rejected: 'bg-red-50 text-red-700 border-red-200',
}

const sessionStatusColor: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  ready: 'bg-blue-100 text-blue-800',
  ingested: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
}

// Search/filter
const search = ref('')
const statusFilter = ref<ItemStatus | 'all'>('all')

const filteredDevices = computed(() => {
  if (!session.value) return []
  return session.value.devices.filter(d => {
    const q = search.value.toLowerCase()
    const name: string = d.data?.name ?? ''
    const site: string = d.data?.site?.name ?? ''
    const model: string = d.data?.device_type?.model ?? ''
    const matchesSearch = !q || name.toLowerCase().includes(q) || site.toLowerCase().includes(q) || model.toLowerCase().includes(q)
    const matchesStatus = statusFilter.value === 'all' || d.status === statusFilter.value
    return matchesSearch && matchesStatus
  })
})
</script>

<template>
  <div>
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <NuxtLink to="/reviews" class="text-sm text-muted-foreground hover:text-foreground">
            ← Reviews
          </NuxtLink>
          <h1 class="text-xl font-semibold">{{ session?.policy_name ?? reviewId }}</h1>
          <span
            v-if="session"
            class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
            :class="sessionStatusColor[session.status] ?? 'bg-gray-100'"
          >
            {{ session.status }}
            <span v-if="polling" class="ml-1 animate-spin">⟳</span>
          </span>
        </div>
        <p v-if="session?.error" class="mt-1 text-xs text-destructive">
          {{ session.error }}
        </p>
      </div>
      <button
        v-if="session?.status === 'ready'"
        :disabled="ingestLoading"
        class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        @click="showIngest = true"
      >
        {{ ingestLoading ? 'Ingesting…' : 'Send to NetBox' }}
      </button>
    </div>

    <!-- Loading / error states -->
    <div v-if="loading" class="text-muted-foreground">Loading review…</div>
    <div v-else-if="error" class="rounded-md bg-destructive/10 border border-destructive/30 p-4 text-sm text-destructive">
      {{ error }}
    </div>
    <div
      v-else-if="session?.status === 'pending'"
      class="flex flex-col items-center justify-center py-24 text-center gap-3"
    >
      <div class="text-4xl animate-spin">⟳</div>
      <p class="text-muted-foreground">Discovery in progress…</p>
    </div>
    <div
      v-else-if="session?.status === 'failed'"
      class="rounded-lg border border-destructive/30 bg-destructive/5 p-6"
    >
      <h2 class="font-medium text-destructive mb-2">Discovery Failed</h2>
      <p class="text-sm text-muted-foreground">{{ session.error }}</p>
      <NuxtLink to="/config" class="mt-4 inline-block text-sm text-primary hover:underline">
        Try again →
      </NuxtLink>
    </div>

    <!-- Main review table -->
    <template v-else-if="session">
      <!-- Summary metrics -->
      <div class="mb-4 grid grid-cols-3 gap-3 sm:grid-cols-4">
        <div class="rounded-lg border p-3 text-center">
          <div class="text-2xl font-semibold">{{ session.devices.length }}</div>
          <div class="text-xs text-muted-foreground mt-0.5">Total</div>
        </div>
        <div class="rounded-lg border p-3 text-center">
          <div class="text-2xl font-semibold text-green-700">{{ acceptedCount }}</div>
          <div class="text-xs text-muted-foreground mt-0.5">Accepted</div>
        </div>
        <div class="rounded-lg border p-3 text-center">
          <div class="text-2xl font-semibold text-red-700">{{ rejectedCount }}</div>
          <div class="text-xs text-muted-foreground mt-0.5">Rejected</div>
        </div>
        <div class="rounded-lg border p-3 text-center">
          <div class="text-2xl font-semibold text-yellow-700">{{ pendingCount }}</div>
          <div class="text-xs text-muted-foreground mt-0.5">Pending</div>
        </div>
      </div>

      <!-- Toolbar -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <input
          v-model="search"
          placeholder="Search devices…"
          class="rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring w-48"
        />
        <select
          v-model="statusFilter"
          class="rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>
          <option value="accepted">Accepted</option>
          <option value="rejected">Rejected</option>
        </select>
        <div class="ml-auto flex gap-2">
          <button
            class="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-green-50 hover:border-green-300 hover:text-green-700"
            @click="acceptAll"
          >
            Accept All
          </button>
          <button
            class="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-red-50 hover:border-red-300 hover:text-red-700"
            @click="rejectAll"
          >
            Reject All
          </button>
        </div>
      </div>

      <!-- Device table -->
      <div class="rounded-lg border overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b bg-muted/40">
              <th class="px-4 py-3 text-left font-medium">Hostname</th>
              <th class="px-4 py-3 text-left font-medium">Manufacturer / Model</th>
              <th class="px-4 py-3 text-left font-medium">Platform</th>
              <th class="px-4 py-3 text-left font-medium">Site</th>
              <th class="px-4 py-3 text-left font-medium">Role</th>
              <th class="px-4 py-3 text-right font-medium">Interfaces</th>
              <th class="px-4 py-3 text-center font-medium">Status</th>
              <th class="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in filteredDevices"
              :key="item.index"
              class="border-b last:border-0 hover:bg-muted/20"
              :class="{ 'opacity-50': item.status === 'rejected' }"
            >
              <td class="px-4 py-3 font-mono text-xs font-medium">{{ item.data.name }}</td>
              <td class="px-4 py-3 text-xs">
                <template v-if="item.data.device_type">
                  {{ item.data.device_type.manufacturer?.name ?? '—' }} /
                  {{ item.data.device_type.model }}
                </template>
                <span v-else class="text-muted-foreground">—</span>
              </td>
              <td class="px-4 py-3 text-xs">
                {{ item.data.platform?.name ?? '—' }}
              </td>
              <td class="px-4 py-3 text-xs">
                {{ item.data.site?.name ?? '—' }}
              </td>
              <td class="px-4 py-3 text-xs">
                {{ item.data.role?.name ?? '—' }}
              </td>
              <td class="px-4 py-3 text-right text-xs">
                {{ item.data.interfaces?.length ?? 0 }}
              </td>
              <td class="px-4 py-3 text-center">
                <span
                  class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                  :class="statusColor[item.status]"
                >
                  {{ item.status }}
                </span>
              </td>
              <td class="px-4 py-3">
                <div class="flex items-center justify-end gap-1">
                  <button
                    v-if="item.status !== 'accepted'"
                    class="rounded px-2 py-1 text-xs text-green-700 hover:bg-green-50"
                    @click="setDeviceStatus(item.index, 'accepted')"
                  >
                    ✓
                  </button>
                  <button
                    v-if="item.status !== 'rejected'"
                    class="rounded px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                    @click="setDeviceStatus(item.index, 'rejected')"
                  >
                    ✗
                  </button>
                  <button
                    v-if="item.status !== 'pending'"
                    class="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                    @click="setDeviceStatus(item.index, 'pending')"
                  >
                    ↺
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="filteredDevices.length === 0" class="py-12 text-center text-sm text-muted-foreground">
          No devices match the current filter.
        </div>
      </div>
    </template>

    <!-- Ingest result banner -->
    <div
      v-if="ingestResult"
      class="mt-4 rounded-lg border p-4"
      :class="ingestResult.errors.length > 0 ? 'bg-yellow-50 border-yellow-200' : 'bg-green-50 border-green-200'"
    >
      <div class="flex items-center justify-between">
        <div>
          <p class="font-medium text-sm">
            {{ ingestResult.dry_run ? '(Dry run) ' : '' }}
            {{ ingestResult.ingested_count }} entities queued for ingestion,
            {{ ingestResult.skipped_count }} skipped.
          </p>
          <ul v-if="ingestResult.errors.length" class="mt-2 space-y-0.5">
            <li
              v-for="(e, i) in ingestResult.errors"
              :key="i"
              class="text-xs text-destructive"
            >
              {{ e }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Ingest confirmation modal -->
    <div
      v-if="showIngest"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="showIngest = false"
    >
      <div class="w-full max-w-sm rounded-lg border bg-card p-6 shadow-lg">
        <h2 class="mb-2 text-lg font-semibold">Send to NetBox</h2>
        <p class="text-sm text-muted-foreground mb-4">
          This will ingest
          <strong>{{ acceptedCount + pendingCount }}</strong> device(s)
          (accepted + pending) into NetBox via Diode.
        </p>
        <label class="flex items-center gap-2 text-sm mb-6">
          <input v-model="dryRun" type="checkbox" class="rounded" />
          Dry run (preview only, nothing written)
        </label>
        <div class="flex justify-end gap-3">
          <button
            class="rounded-md border px-4 py-2 text-sm hover:bg-muted"
            @click="showIngest = false"
          >
            Cancel
          </button>
          <button
            :disabled="ingestLoading"
            class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            @click="handleIngest"
          >
            {{ dryRun ? 'Preview' : 'Ingest' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
