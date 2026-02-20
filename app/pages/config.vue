<script setup lang="ts">
const { yaml, discovering, discoverError, triggerDiscover } = useConfig()
const api = useApi()

const { data: capData } = await useAsyncData('collectors', () => api.listCollectors())
const collectors = computed(() => capData.value?.collectors ?? [])
</script>

<template>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    <!-- Left: Editor -->
    <div>
      <h1 class="mb-4 text-2xl font-semibold">Discover Devices</h1>

      <div class="mb-4 rounded-lg border bg-muted/30 p-4">
        <p class="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">
          Registered Collectors
        </p>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="c in collectors"
            :key="c.name"
            class="inline-flex items-center rounded-full border bg-background px-2 py-0.5 text-xs font-mono"
          >
            {{ c.name }}
          </span>
          <span v-if="collectors.length === 0" class="text-xs text-muted-foreground">
            (could not reach orbweaver)
          </span>
        </div>
      </div>

      <label class="mb-1 block text-sm font-medium">Policy YAML</label>
      <textarea
        v-model="yaml"
        class="w-full rounded-md border bg-background font-mono text-xs p-3 focus:outline-none focus:ring-2 focus:ring-ring resize-none"
        rows="22"
        spellcheck="false"
      />

      <div v-if="discoverError" class="mt-3 rounded-md bg-destructive/10 border border-destructive/30 p-3 text-xs text-destructive font-mono whitespace-pre-wrap">
        {{ discoverError }}
      </div>

      <button
        :disabled="discovering"
        class="mt-4 w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        @click="triggerDiscover"
      >
        {{ discovering ? 'Starting discovery…' : 'Discover Now' }}
      </button>
    </div>

    <!-- Right: YAML reference -->
    <div class="space-y-4">
      <div class="rounded-lg border p-4">
        <h2 class="mb-2 font-medium text-sm">Policy YAML format</h2>
        <pre class="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed font-mono">policies:
  &lt;name&gt;:
    config:
      defaults:
        site: "DC1"        # NetBox site name
        role: "switch"     # Device role
    scope:
      - hostname: 10.0.0.1
        username: admin
        password: secret
        collector: cisco_ios   # registered collector
        # driver: ios          # or use NAPALM driver
        timeout: 60
        optional_args:
          secret: enable_secret</pre>
      </div>

      <div class="rounded-lg border p-4">
        <h2 class="mb-3 font-medium text-sm">What happens</h2>
        <ol class="space-y-2 text-sm text-muted-foreground list-decimal list-inside">
          <li>orbweaver connects to each device via the selected collector</li>
          <li>Discovered data (device, interfaces, VLANs) is stored for review</li>
          <li>You accept/reject devices on the Review page</li>
          <li>Accepted devices are ingested into NetBox via Diode SDK</li>
        </ol>
      </div>
    </div>
  </div>
</template>
