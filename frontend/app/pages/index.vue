<script setup lang="ts">
import type { BackendStatus } from '~/types/api'

const api = useApi()

// ── Orbweaver status ──────────────────────────────────────────────────────
const orbweaverStatus = ref<BackendStatus | null>(null)
const orbweaverError = ref(false)

async function fetchOrbweaver() {
  try {
    orbweaverStatus.value = await api.getStatus()
    orbweaverError.value = false
  } catch {
    orbweaverError.value = true
  }
}

// ── Orbweaver last discovery ──────────────────────────────────────────────
const { data: reviewsData } = await useAsyncData('home-reviews', () => api.listReviews())
const latestReview = computed(() => {
  const reviews = reviewsData.value?.reviews ?? []
  return reviews[0] ?? null
})

// ── Polling ──────────────────────────────────────────────────────────────
let timer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await fetchOrbweaver()
  timer = setInterval(() => {
    fetchOrbweaver()
  }, 15_000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

// ── Helpers ──────────────────────────────────────────────────────────────
function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold mb-6">Dashboard</h1>

    <div class="grid gap-6">
      <!-- ── Orbweaver card ──────────────────────────────────────────── -->
      <div class="rounded-lg border bg-card p-6">
        <div class="flex items-center gap-3 mb-4">
          <span
            class="h-2.5 w-2.5 rounded-full"
            :class="orbweaverError ? 'bg-red-500' : 'bg-green-500'"
          />
          <h2 class="text-lg font-semibold">Orbweaver</h2>
          <span class="ml-auto text-xs text-muted-foreground">vendor collectors + review</span>
        </div>

        <div v-if="orbweaverError" class="text-sm text-destructive">
          Backend unreachable
        </div>

        <div v-else-if="orbweaverStatus" class="space-y-3 text-sm">
          <div class="grid grid-cols-2 gap-x-4 gap-y-2">
            <span class="text-muted-foreground">Status</span>
            <span>
              <span
                class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                :class="orbweaverStatus.dry_run
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-green-100 text-green-800'"
              >
                {{ orbweaverStatus.dry_run ? 'dry-run' : 'live' }}
              </span>
            </span>

            <span class="text-muted-foreground">Uptime</span>
            <span>{{ formatUptime(orbweaverStatus.up_time_seconds) }}</span>

            <span class="text-muted-foreground">Diode</span>
            <span class="font-mono text-xs truncate">{{ orbweaverStatus.diode_target ?? 'none' }}</span>
          </div>

          <!-- Review counts -->
          <div class="border-t pt-3 mt-3">
            <p class="text-xs text-muted-foreground mb-2">Review sessions</p>
            <div class="flex gap-3 flex-wrap">
              <span class="inline-flex items-center gap-1 text-xs">
                <span class="h-1.5 w-1.5 rounded-full bg-blue-500" />
                {{ orbweaverStatus.reviews.ready }} ready
              </span>
              <span class="inline-flex items-center gap-1 text-xs">
                <span class="h-1.5 w-1.5 rounded-full bg-yellow-500" />
                {{ orbweaverStatus.reviews.pending }} pending
              </span>
              <span class="inline-flex items-center gap-1 text-xs">
                <span class="h-1.5 w-1.5 rounded-full bg-green-500" />
                {{ orbweaverStatus.reviews.ingested }} ingested
              </span>
              <span class="inline-flex items-center gap-1 text-xs">
                <span class="h-1.5 w-1.5 rounded-full bg-red-500" />
                {{ orbweaverStatus.reviews.failed }} failed
              </span>
            </div>
          </div>

          <!-- Latest review -->
          <div v-if="latestReview" class="border-t pt-3 mt-3">
            <p class="text-xs text-muted-foreground mb-1">Latest discovery</p>
            <div class="flex items-center gap-2">
              <NuxtLink
                :to="`/review/${latestReview.id}`"
                class="text-primary hover:underline text-xs font-mono"
              >
                {{ latestReview.policy_name }}
              </NuxtLink>
              <span
                class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                :class="{
                  'bg-blue-100 text-blue-800': latestReview.status === 'ready',
                  'bg-green-100 text-green-800': latestReview.status === 'ingested',
                  'bg-yellow-100 text-yellow-800': latestReview.status === 'pending',
                  'bg-red-100 text-red-800': latestReview.status === 'failed',
                }"
              >
                {{ latestReview.status }}
              </span>
              <span class="text-xs text-muted-foreground">
                {{ latestReview.device_count }} device{{ latestReview.device_count !== 1 ? 's' : '' }}
              </span>
            </div>
            <p class="text-xs text-muted-foreground mt-1">
              {{ formatTime(latestReview.created_at) }}
            </p>
          </div>
        </div>

        <div class="mt-4 flex gap-2">
          <NuxtLink
            to="/config"
            class="inline-flex items-center rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            New Discovery
          </NuxtLink>
          <NuxtLink
            to="/reviews"
            class="inline-flex items-center rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-accent"
          >
            Reviews
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>
