<script setup lang="ts">
import type { CableReviewItem, ItemStatus } from '~/types/api'

const props = defineProps<{
  cables: CableReviewItem[]
  readonly?: boolean
}>()

const emit = defineEmits<{
  statusChange: [index: number, status: ItemStatus]
}>()

const statusColor: Record<ItemStatus, string> = {
  pending: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  accepted: 'bg-green-50 text-green-700 border-green-200',
  rejected: 'bg-red-50 text-red-700 border-red-200',
}

function confidenceClass(confidence: string) {
  if (confidence === 'confirmed') return 'bg-green-50'
  if (confidence === 'partial') return 'bg-yellow-50'
  return 'bg-red-50'
}

function confidenceLabel(confidence: string) {
  return confidence.charAt(0).toUpperCase() + confidence.slice(1)
}
</script>

<template>
  <div class="rounded-lg border overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b bg-muted/40">
          <th class="px-4 py-3 text-left font-medium">Local Device</th>
          <th class="px-4 py-3 text-left font-medium">Local Interface</th>
          <th class="px-4 py-3 text-left font-medium">Remote Device</th>
          <th class="px-4 py-3 text-left font-medium">Remote Interface</th>
          <th class="px-4 py-3 text-left font-medium">Confidence</th>
          <th class="px-4 py-3 text-left font-medium">Skip Reason</th>
          <th class="px-4 py-3 text-center font-medium">Status</th>
          <th v-if="!readonly" class="px-4 py-3" />
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in props.cables"
          :key="item.index"
          class="border-b last:border-0"
          :class="confidenceClass(item.data.confidence)"
        >
          <td class="px-4 py-3 font-mono text-xs font-medium">{{ item.data.cable.device_a_name }}</td>
          <td class="px-4 py-3 text-xs">{{ item.data.cable.interface_a_name }}</td>
          <td class="px-4 py-3 font-mono text-xs">{{ item.data.cable.device_b_name }}</td>
          <td class="px-4 py-3 text-xs">{{ item.data.cable.interface_b_name }}</td>
          <td class="px-4 py-3 text-xs font-medium">{{ confidenceLabel(item.data.confidence) }}</td>
          <td class="px-4 py-3 text-xs">
            <span
              v-if="item.data.skip_reason"
              class="text-red-700 underline decoration-dotted cursor-help"
              :title="item.data.skip_reason"
            >
              {{ item.data.skip_reason }}
            </span>
            <span v-else class="text-muted-foreground">—</span>
          </td>
          <td class="px-4 py-3 text-center">
            <span
              class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
              :class="statusColor[item.status]"
            >
              {{ item.status }}
            </span>
          </td>
          <td v-if="!readonly" class="px-4 py-3">
            <div class="flex items-center justify-end gap-1">
              <button
                v-if="item.status !== 'accepted'"
                class="rounded px-2 py-1 text-xs text-green-700 hover:bg-green-100"
                @click="emit('statusChange', item.index, 'accepted')"
              >
                ✓
              </button>
              <button
                v-if="item.status !== 'rejected'"
                class="rounded px-2 py-1 text-xs text-red-700 hover:bg-red-100"
                @click="emit('statusChange', item.index, 'rejected')"
              >
                ✗
              </button>
              <button
                v-if="item.status !== 'pending'"
                class="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                @click="emit('statusChange', item.index, 'pending')"
              >
                ↺
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="props.cables.length === 0" class="py-12 text-center text-sm text-muted-foreground">
      No cable candidates match the current filter.
    </div>
  </div>
</template>
