<script setup lang="ts">
import type { CableResolutionSummary } from '~/types/api'

const props = defineProps<{
  summary: CableResolutionSummary | null
}>()

const discovered = computed(() => props.summary?.discovered ?? 0)
const created = computed(() => props.summary?.created ?? 0)
const skipped = computed(() => props.summary?.skipped ?? 0)
const unresolvable = computed(() => props.summary?.unresolvable ?? 0)
const ratio = computed(() => {
  if (!discovered.value) return 0
  return Math.round((created.value / discovered.value) * 100)
})
</script>

<template>
  <div class="rounded-lg border p-4">
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded-md border p-3 text-center">
        <div class="text-xl font-semibold">{{ discovered }}</div>
        <div class="text-xs text-muted-foreground mt-0.5">Discovered</div>
      </div>
      <div class="rounded-md border p-3 text-center">
        <div class="text-xl font-semibold text-green-700">{{ created }}</div>
        <div class="text-xs text-muted-foreground mt-0.5">Created</div>
      </div>
      <div class="rounded-md border p-3 text-center">
        <div class="text-xl font-semibold text-yellow-700">{{ skipped }}</div>
        <div class="text-xs text-muted-foreground mt-0.5">Skipped</div>
      </div>
      <div class="rounded-md border p-3 text-center">
        <div class="text-xl font-semibold text-red-700">{{ unresolvable }}</div>
        <div class="text-xs text-muted-foreground mt-0.5">Unresolvable</div>
      </div>
    </div>

    <div class="mt-4">
      <div class="mb-1 flex justify-between text-xs text-muted-foreground">
        <span>Created / Discovered</span>
        <span>{{ ratio }}%</span>
      </div>
      <div class="h-2 rounded bg-muted">
        <div class="h-2 rounded bg-primary transition-all" :style="{ width: `${ratio}%` }" />
      </div>
    </div>

    <details v-if="props.summary?.skip_entries?.length" class="mt-4">
      <summary class="cursor-pointer text-sm font-medium">Skip Details ({{ props.summary.skip_entries.length }})</summary>
      <div class="mt-3 overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-left text-muted-foreground border-b">
              <th class="py-2 pr-3">Local Device</th>
              <th class="py-2 pr-3">Local Interface</th>
              <th class="py-2 pr-3">Neighbor</th>
              <th class="py-2 pr-3">Reason</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(entry, idx) in props.summary.skip_entries" :key="idx" class="border-b last:border-0">
              <td class="py-2 pr-3 font-mono">{{ entry.local_device }}</td>
              <td class="py-2 pr-3">{{ entry.local_interface }}</td>
              <td class="py-2 pr-3">{{ entry.neighbor_hostname }}</td>
              <td class="py-2 pr-3 text-red-700">{{ entry.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>
