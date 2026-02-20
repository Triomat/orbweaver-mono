<script setup lang="ts">
import type { ReviewSummary } from '~/types/api'

const api = useApi()

const { data, refresh, pending } = await useAsyncData('reviews', () => api.listReviews())
const reviews = computed<ReviewSummary[]>(() => data.value?.reviews ?? [])

const statusColor: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  ready: 'bg-blue-100 text-blue-800',
  ingested: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
}

async function remove(id: string) {
  await api.deleteReview(id)
  refresh()
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Reviews</h1>
      <NuxtLink
        to="/config"
        class="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        New Discovery
      </NuxtLink>
    </div>

    <div v-if="pending" class="text-muted-foreground">Loading…</div>

    <div v-else-if="reviews.length === 0" class="rounded-lg border border-dashed py-16 text-center text-muted-foreground">
      No reviews yet. Start a discovery from the Discover tab.
    </div>

    <div v-else class="rounded-lg border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b bg-muted/40">
            <th class="px-4 py-3 text-left font-medium">Policy</th>
            <th class="px-4 py-3 text-left font-medium">Status</th>
            <th class="px-4 py-3 text-right font-medium">Devices</th>
            <th class="px-4 py-3 text-right font-medium">Accepted</th>
            <th class="px-4 py-3 text-right font-medium">Rejected</th>
            <th class="px-4 py-3 text-left font-medium">Created</th>
            <th class="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in reviews"
            :key="r.id"
            class="border-b last:border-0 hover:bg-muted/30"
          >
            <td class="px-4 py-3 font-mono text-xs">
              <NuxtLink :to="`/review/${r.id}`" class="text-primary hover:underline">
                {{ r.policy_name }}
              </NuxtLink>
            </td>
            <td class="px-4 py-3">
              <span
                class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                :class="statusColor[r.status] ?? 'bg-gray-100 text-gray-800'"
              >
                {{ r.status }}
              </span>
            </td>
            <td class="px-4 py-3 text-right">{{ r.device_count }}</td>
            <td class="px-4 py-3 text-right text-green-700">{{ r.accepted }}</td>
            <td class="px-4 py-3 text-right text-red-700">{{ r.rejected }}</td>
            <td class="px-4 py-3 text-xs text-muted-foreground">
              {{ new Date(r.created_at).toLocaleString() }}
            </td>
            <td class="px-4 py-3 text-right">
              <button
                class="text-xs text-destructive hover:underline"
                @click="remove(r.id)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
