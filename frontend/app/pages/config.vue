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

const DEFAULT_SEED_YAML = `tenant:
  name: SVA-DEV
  slug: sva-dev

sites:
  - name: theBASEMENT
    slug: thebasement
    description: Bastel Keller
    status: active

racks:
  - name: theMAST
    site: theBASEMENT
    u_height: 42
  - name: theRACK
    site: theBASEMENT
    u_height: 42

manufacturers:
  - name: Cisco
    slug: cisco
  - name: Opengear
    slug: opengear
  - name: APC
    slug: apc
  - name: Kentix
    slug: kentix
  - name: Generic
    slug: generic

device_types:
  - manufacturer: Cisco
    model: Meraki MX67
    slug: cisco-meraki-mx67
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MR45
    slug: cisco-meraki-mr45
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MS120-8FP
    slug: cisco-meraki-ms120-8fp
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MV13
    slug: meraki-mv13
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MG21
    slug: cisco-meraki-mg21
    u_height: 1
  - manufacturer: Cisco
    model: WS-C3650-24PS
    slug: ws-c3650-24ps
    u_height: 1
  - manufacturer: Opengear
    model: OM1204-4E-L
    slug: opengear-om1204-4e-l
    u_height: 1
  - manufacturer: Opengear
    model: OM1208-8E-L
    slug: opengear-om1208-8e-l
    u_height: 1
  - manufacturer: APC
    model: SCL500
    slug: apc-scl500
    u_height: 2
  - manufacturer: Kentix
    model: KPMDU-RC-1600C13C19-2-16-H
    slug: kentix-kpmdu-rc-1600c13c19-2-16-h
    u_height: 1
  - manufacturer: Generic
    model: Rack shelf
    slug: rack-shelf
    u_height: 1
  - manufacturer: Generic
    model: Cable Duct
    slug: cable-duct
    u_height: 1

device_roles:
  - name: Switch
    slug: switch
    color: 2196f3
  - name: Firewall
    slug: firewall
    color: f44336
  - name: Console Server
    slug: console-server
    color: 9c27b0
  - name: Access Point
    slug: access-point
    color: 4caf50
  - name: PDU
    slug: pdu
    color: ff9800
  - name: UPS
    slug: ups
    color: 795548
  - name: Rack Shelf
    slug: rack-shelf
    color: 9e9e9e
  - name: Cable Duct
    slug: cable-duct
    color: 607d8b
  - name: Cam
    slug: cam
    color: 00bcd4
  - name: WAN Gateway
    slug: wan-gateway
    color: 673ab7

platforms:
  - name: Cisco IOS-XE 16.12.10a
    slug: cisco-ios-xe-161210a
    manufacturer: Cisco

devices:
  - name: DC-Rack
    device_type: OM1204-4E-L
    manufacturer: Opengear
    role: Console Server
    site: theBASEMENT
    rack: theMAST
    position: 1
    face: front
    airflow: passive
    serial: "12042503319976"
    tenant: SVA-DEV
    status: active
  - name: Duct 1
    device_type: Cable Duct
    manufacturer: Generic
    role: Cable Duct
    site: theBASEMENT
    rack: theMAST
    position: 2
    face: front
    status: active
  - name: Duct 2
    device_type: Cable Duct
    manufacturer: Generic
    role: Cable Duct
    site: theBASEMENT
    rack: theMAST
    position: 5
    face: front
    status: active
  - name: DC Rack PDU
    device_type: KPMDU-RC-1600C13C19-2-16-H
    manufacturer: Kentix
    role: PDU
    site: theBASEMENT
    rack: theMAST
    position: 6
    face: front
    airflow: passive
    serial: "3012001510294"
    tenant: SVA-DEV
    status: active
  - name: Rack Shelf 1
    device_type: Rack shelf
    manufacturer: Generic
    role: Rack Shelf
    site: theBASEMENT
    rack: theMAST
    position: 6
    face: rear
    tenant: SVA-DEV
    status: active
  - name: DC-Rack-USV
    device_type: SCL500
    manufacturer: APC
    role: UPS
    site: theBASEMENT
    rack: theMAST
    position: 8
    face: front
    airflow: passive
    serial: "5S2511T97670"
    tenant: SVA-DEV
    status: active
  - name: DC-MX
    device_type: Meraki MX67
    manufacturer: Cisco
    role: Firewall
    site: theBASEMENT
    rack: theMAST
    airflow: passive
    serial: "Q2FY-7LVE-TR23"
    tenant: SVA-DEV
    status: active
    parent_device: Rack Shelf 1
    parent_bay: Bay 1
  - name: DC-WiFi
    device_type: Meraki MR45
    manufacturer: Cisco
    role: Access Point
    site: theBASEMENT
    rack: theMAST
    airflow: passive
    serial: "Q3AA-RELF-Y97N"
    tenant: SVA-DEV
    status: active
  - name: theRACK-Rack
    device_type: OM1208-8E-L
    manufacturer: Opengear
    role: Console Server
    site: theBASEMENT
    rack: theRACK
    position: 1
    face: front
    airflow: front-to-rear
    serial: "12082104119430"
    tenant: SVA-DEV
    status: active
  - name: theRACK-theROUTER
    device_type: Meraki MX67
    manufacturer: Cisco
    role: Firewall
    site: theBASEMENT
    rack: theRACK
    airflow: passive
    serial: "Q2FY-CN7E-4K5K"
    tenant: SVA-DEV
    status: active
  - name: thRACK-theSWITCH
    device_type: Meraki MS120-8FP
    manufacturer: Cisco
    role: Switch
    site: theBASEMENT
    rack: theRACK
    face: front
    airflow: front-to-rear
    serial: "Q2CX-DJYA-EKUU"
    tenant: SVA-DEV
    status: active
  - name: theRACK-theWIFI
    device_type: Meraki MR45
    manufacturer: Cisco
    role: Access Point
    site: theBASEMENT
    rack: theRACK
    airflow: passive
    serial: "Q3AA-4JKZ-UBPS"
    tenant: SVA-DEV
    status: active
    comments: "Mounted on top of theRACK."
  - name: theRACK-theCAM
    device_type: Meraki MV13
    manufacturer: Cisco
    role: Cam
    site: theBASEMENT
    rack: theRACK
    serial: "Q4EE-5HBF-Q6F7"
    tenant: SVA-DEV
    status: active
    comments: "Mounted on the top."
  - name: theRACK-theGATEWAY
    device_type: Meraki MG21
    manufacturer: Cisco
    role: WAN Gateway
    site: theBASEMENT
    rack: theRACK
    airflow: passive
    serial: "Q2VY-UBTR-V2XH"
    tenant: SVA-DEV
    status: active
  - name: C3650
    device_type: WS-C3650-24PS
    manufacturer: Cisco
    role: Switch
    site: theBASEMENT
    platform: Cisco IOS-XE 16.12.10a
    serial: "FDO2125Q10A"
    tenant: SVA-DEV
    status: active
    primary_ip4: "192.168.12.100/24"
    tags:
      - orbweaver-2
      - prod-test
`

const seedYaml = ref(DEFAULT_SEED_YAML)
const seedExpanded = ref(false)
const seeding = ref(false)
const seedResult = ref<import('~/types/api').SeedResult | null>(null)
const seedError = ref<string | null>(null)

async function runSeed() {
  seeding.value = true
  seedResult.value = null
  seedError.value = null
  try {
    seedResult.value = await api.seedInfrastructure(seedYaml.value)
  } catch (err: unknown) {
    seedError.value = err instanceof Error ? err.message : String(err)
  } finally {
    seeding.value = false
  }
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
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Rack</label>
              <input
                v-model="policy.defaults.rack"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="Rack-A1"
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

            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Rack (override)</label>
              <input
                v-model="device.rack"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="leave blank to use default"
              />
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

    <!-- Seed Infrastructure panel (full width, below the two columns) -->
    <div class="col-span-1 lg:col-span-2 rounded-lg border">
      <button
        class="flex w-full items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/30 transition-colors"
        @click="seedExpanded = !seedExpanded"
      >
        <span>Seed Infrastructure</span>
        <span class="text-muted-foreground text-xs">{{ seedExpanded ? '▲ collapse' : '▼ expand' }}</span>
      </button>

      <div v-if="seedExpanded" class="border-t px-4 py-4 space-y-3">
        <p class="text-xs text-muted-foreground">
          Paste your infrastructure YAML below and click Seed to create sites, racks, manufacturers,
          device types, roles, and devices in NetBox via the REST API.
          Safe to run multiple times — existing objects are skipped.
        </p>

        <textarea
          v-model="seedYaml"
          rows="20"
          class="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring"
          spellcheck="false"
        />

        <div v-if="seedError" class="rounded-md bg-destructive/10 border border-destructive/30 p-3 text-xs text-destructive font-mono whitespace-pre-wrap">
          {{ seedError }}
        </div>

        <div v-if="seedResult" class="rounded-md bg-muted/30 border p-3 text-xs font-mono space-y-1">
          <p class="font-medium text-foreground">Seed complete</p>
          <p class="text-muted-foreground">
            Created — sites: {{ seedResult.created.sites }}, racks: {{ seedResult.created.racks }},
            manufacturers: {{ seedResult.created.manufacturers }},
            device types: {{ seedResult.created.device_types }},
            roles: {{ seedResult.created.device_roles }},
            devices: {{ seedResult.created.devices }}
          </p>
          <p class="text-muted-foreground">
            Skipped — sites: {{ seedResult.skipped.sites }}, devices: {{ seedResult.skipped.devices }}
          </p>
          <div v-if="seedResult.errors.length > 0" class="text-destructive mt-1">
            <p class="font-medium">Errors:</p>
            <p v-for="(e, i) in seedResult.errors" :key="i">{{ e }}</p>
          </div>
        </div>

        <button
          :disabled="seeding"
          class="w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          @click="runSeed"
        >
          {{ seeding ? 'Seeding…' : 'Seed Infrastructure' }}
        </button>
      </div>
    </div>
  </div>
</template>
