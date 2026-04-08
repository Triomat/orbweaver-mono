<script setup lang="ts">
import { ref } from 'vue'

const { policy, yaml, jsonText, activeTab, tabError, discovering, discoverError, switchTab, addDevice, removeDevice, triggerDiscover } = useConfig()
const api = useApi()

const { data: capData } = await useAsyncData('collectors', () => api.listCollectors())
const collectors = computed(() => capData.value?.collectors ?? [])

const showPasswords = ref<boolean[]>([])
function togglePassword(index: number) {
  showPasswords.value[index] = !showPasswords.value[index]
}
</script>

<template>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    <!-- Left: Editor -->
    <div>
      <h1 class="mb-4 text-2xl font-semibold">Discover Devices</h1>

      <!-- Tab bar -->
      <div class="mb-4 flex border-b">
        <button
          class="px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'form'
            ? 'border-b-2 border-primary text-primary'
            : 'text-muted-foreground hover:text-foreground'"
          @click="switchTab('form')"
        >
          Form
        </button>
        <button
          class="px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'yaml'
            ? 'border-b-2 border-primary text-primary'
            : 'text-muted-foreground hover:text-foreground'"
          @click="switchTab('yaml')"
        >
          YAML
        </button>
        <button
          class="px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'json'
            ? 'border-b-2 border-primary text-primary'
            : 'text-muted-foreground hover:text-foreground'"
          @click="switchTab('json')"
        >
          JSON
        </button>
      </div>

      <!-- Tab error banner -->
      <div
        v-if="tabError"
        class="mb-3 rounded-md bg-destructive/10 border border-destructive/30 p-3 text-xs text-destructive"
      >
        {{ tabError }}
      </div>

      <!-- Form tab -->
      <div v-if="activeTab === 'form'" class="space-y-5">
        <!-- Policy name -->
        <div>
          <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">Policy Name</label>
          <input
            v-model="policy.name"
            type="text"
            class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="my-discovery"
          />
        </div>

        <!-- Defaults -->
        <div class="rounded-lg border p-4 space-y-3">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Defaults</p>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Site</label>
              <input
                v-model="policy.defaults.site"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="DC1"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Role</label>
              <input
                v-model="policy.defaults.role"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="switch"
              />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Tenant</label>
              <input
                v-model="policy.defaults.tenant"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="acme-corp"
              />
            </div>
          </div>
          <div>
            <label class="mb-1 block text-xs text-muted-foreground">Tags (comma-separated)</label>
            <input
              v-model="policy.defaults.tags"
              type="text"
              class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="prod, discovered"
            />
          </div>

          <div class="flex items-start justify-between rounded-md border px-3 py-2.5">
            <div>
              <p class="text-sm font-medium leading-none">Auto-ingest</p>
              <p class="mt-1 text-xs text-muted-foreground">Skip review — discovered devices are sent directly to NetBox</p>
            </div>
            <button
              type="button"
              role="switch"
              :aria-checked="policy.autoIngest"
              class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              :class="policy.autoIngest ? 'bg-primary' : 'bg-input'"
              @click="policy.autoIngest = !policy.autoIngest"
            >
              <span
                class="pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg transition-transform"
                :class="policy.autoIngest ? 'translate-x-4' : 'translate-x-0'"
              />
            </button>
          </div>
        </div>

        <!-- Devices -->
        <div class="space-y-3">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Devices</p>

          <div
            v-for="(device, index) in policy.devices"
            :key="index"
            class="rounded-lg border p-4 space-y-3"
          >
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-muted-foreground">Device {{ index + 1 }}</span>
              <button
                class="text-xs text-destructive hover:underline"
                @click="removeDevice(index)"
              >
                Remove
              </button>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs text-muted-foreground">Hostname *</label>
                <input
                  v-model="device.hostname"
                  type="text"
                  class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="192.168.1.1"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs text-muted-foreground">Username *</label>
                <input
                  v-model="device.username"
                  type="text"
                  class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="admin"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Password *</label>
              <div class="relative">
                <input
                  v-model="device.password"
                  :type="showPasswords[index] ? 'text' : 'password'"
                  class="w-full rounded-md border bg-background px-3 py-2 pr-16 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  class="absolute inset-y-0 right-2 flex items-center text-xs text-muted-foreground hover:text-foreground"
                  @click="togglePassword(index)"
                >
                  {{ showPasswords[index] ? 'Hide' : 'Show' }}
                </button>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs text-muted-foreground">Collector</label>
                <select
                  v-model="device.collector"
                  class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="">— none (use driver) —</option>
                  <option v-for="c in collectors" :key="c.name" :value="c.name">{{ c.name }}</option>
                </select>
              </div>
              <div v-if="!device.collector">
                <label class="mb-1 block text-xs text-muted-foreground">Driver (NAPALM)</label>
                <input
                  v-model="device.driver"
                  type="text"
                  class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="ios"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs text-muted-foreground">Timeout (s)</label>
                <input
                  v-model.number="device.timeout"
                  type="number"
                  min="1"
                  class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </div>
          </div>

          <button
            class="w-full rounded-md border border-dashed py-2 text-sm text-muted-foreground hover:border-primary hover:text-primary transition-colors"
            @click="addDevice"
          >
            + Add device
          </button>
        </div>
      </div>

      <!-- YAML tab -->
      <div v-if="activeTab === 'yaml'">
        <label class="mb-1 block text-sm font-medium">Policy YAML</label>
        <YamlEditor v-model="yaml" :rows="22" />
      </div>

      <!-- JSON tab -->
      <div v-if="activeTab === 'json'">
        <label class="mb-1 block text-sm font-medium">Policy JSON</label>
        <JsonEditor v-model="jsonText" :rows="22" />
      </div>

      <!-- Discover error -->
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

    <!-- Right: reference -->
    <div class="space-y-4">
      <div class="rounded-lg border bg-muted/30 p-4">
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
        <p class="mt-3 text-xs text-muted-foreground border-t pt-3">
          <span class="font-medium">Auto-ingest</span> skips steps 3–4: all devices are accepted and pushed to NetBox immediately. The session is still recorded for audit.
        </p>
      </div>
    </div>
  </div>
</template>
