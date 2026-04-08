/**
 * Config editor state composable.
 *
 * Manages the policy form state and the three editor representations:
 * Form, YAML, and JSON. Each tab is the source of truth while active;
 * switching tabs converts the current content to the target format.
 *
 * Sync graph (asymmetric):
 *   Form ──→ YAML ↔ JSON
 *     ↑______________|
 *        (lossy parse)
 */

import * as jsYaml from 'js-yaml'
import type { DiscoverJobResponse } from '~/types/api'

export interface DeviceEntry {
  hostname: string
  username: string
  password: string
  collector: string
  driver: string
  timeout: number
}

export interface PolicyForm {
  name: string
  defaults: { site: string; role: string; tags: string; tenant: string }
  autoIngest: boolean
  devices: DeviceEntry[]
}

function defaultDevice(): DeviceEntry {
  return { hostname: '', username: '', password: '', collector: 'cisco_ios', driver: '', timeout: 60 }
}

function defaultPolicy(): PolicyForm {
  return {
    name: 'my-discovery',
    defaults: { site: '', role: '', tags: '', tenant: '' },
    autoIngest: false,
    devices: [defaultDevice()],
  }
}

// ── Shared object builder ─────────────────────────────────────────────────────

function _buildPolicyObject(policy: PolicyForm): Record<string, unknown> {
  const scope = policy.devices.map((d) => {
    const entry: Record<string, unknown> = {
      hostname: d.hostname,
      username: d.username,
      password: d.password,
      timeout: d.timeout,
    }
    if (d.collector) {
      entry.collector = d.collector
    } else if (d.driver) {
      entry.driver = d.driver
    }
    return entry
  })

  const defaults: Record<string, unknown> = {}
  if (policy.defaults.site)   defaults.site   = policy.defaults.site
  if (policy.defaults.role)   defaults.role   = policy.defaults.role
  if (policy.defaults.tenant) defaults.tenant = policy.defaults.tenant
  if (policy.defaults.tags) {
    defaults.tags = policy.defaults.tags.split(',').map((t) => t.trim()).filter(Boolean)
  }

  const configObj: Record<string, unknown> = {}
  if (policy.autoIngest) configObj.auto_ingest = true
  if (Object.keys(defaults).length > 0) configObj.defaults = defaults

  const policyObj: Record<string, unknown> = { scope }
  if (Object.keys(configObj).length > 0) policyObj.config = configObj

  return { policies: { [policy.name]: policyObj } }
}

// ── Serialisers ───────────────────────────────────────────────────────────────

function formToYaml(policy: PolicyForm): string {
  return jsYaml.dump(_buildPolicyObject(policy), { lineWidth: -1 })
}

function formToJson(policy: PolicyForm): string {
  return JSON.stringify(_buildPolicyObject(policy), null, 2)
}

function yamlToJson(yamlStr: string): string | null {
  try {
    const doc = jsYaml.load(yamlStr)
    if (doc == null) return null
    return JSON.stringify(doc, null, 2)
  } catch {
    return null
  }
}

function jsonToYaml(jsonStr: string): string | null {
  try {
    return jsYaml.dump(JSON.parse(jsonStr), { lineWidth: -1 })
  } catch {
    return null
  }
}

// ── Form parser ───────────────────────────────────────────────────────────────

function yamlToForm(yamlStr: string): PolicyForm | null {
  try {
    const doc = jsYaml.load(yamlStr) as Record<string, unknown>
    if (!doc || typeof doc !== 'object') return null
    const policies = doc.policies as Record<string, unknown> | undefined
    if (!policies || typeof policies !== 'object') return null
    const policyNames = Object.keys(policies)
    if (policyNames.length === 0) return null
    const name = policyNames[0]
    const policyData = policies[name] as Record<string, unknown> | undefined
    if (!policyData) return null

    const config = policyData.config as Record<string, unknown> | undefined
    const defaults = (config?.defaults as Record<string, unknown> | undefined) ?? {}
    const tagsRaw = defaults.tags
    const tags = Array.isArray(tagsRaw) ? tagsRaw.join(', ') : (typeof tagsRaw === 'string' ? tagsRaw : '')

    const scope = policyData.scope as Record<string, unknown>[] | undefined
    const devices: DeviceEntry[] = (scope ?? []).map((d) => ({
      hostname: String(d.hostname ?? ''),
      username: String(d.username ?? ''),
      password: String(d.password ?? ''),
      collector: String(d.collector ?? ''),
      driver: String(d.driver ?? ''),
      timeout: typeof d.timeout === 'number' ? d.timeout : 60,
    }))

    return {
      name,
      defaults: {
        site: String(defaults.site ?? ''),
        role: String(defaults.role ?? ''),
        tags,
        tenant: String(defaults.tenant ?? ''),
      },
      autoIngest: config?.auto_ingest === true,
      devices: devices.length > 0 ? devices : [defaultDevice()],
    }
  } catch {
    return null
  }
}

// ── Composable ────────────────────────────────────────────────────────────────

export function useConfig() {
  const api = useApi()
  const router = useRouter()

  // Use useState so state survives navigation between pages
  const policy   = useState<PolicyForm>('config-policy', () => defaultPolicy())
  const yaml     = useState<string>('config-yaml', () => formToYaml(defaultPolicy()))
  // 'jsonText' avoids shadowing the global JSON object
  const jsonText = useState<string>('config-json', () => formToJson(defaultPolicy()))
  const activeTab = useState<'form' | 'yaml' | 'json'>('config-tab', () => 'form')
  const tabError = ref<string | null>(null)
  const discovering = ref(false)
  const discoverError = ref<string | null>(null)
  const lastJob = ref<DiscoverJobResponse | null>(null)

  function switchTab(tab: 'form' | 'yaml' | 'json') {
    tabError.value = null
    const from = activeTab.value
    if (from === tab) return

    // ── leaving Form ──────────────────────────────────────────────────────────
    if (from === 'form') {
      // Form is always valid — eagerly populate both text editors
      yaml.value     = formToYaml(policy.value)
      jsonText.value = formToJson(policy.value)
      activeTab.value = tab
      return
    }

    // ── leaving YAML ──────────────────────────────────────────────────────────
    if (from === 'yaml') {
      if (tab === 'json') {
        const j = yamlToJson(yaml.value)
        if (j === null) {
          tabError.value = 'Could not parse YAML — fix errors before switching to JSON view.'
          return
        }
        jsonText.value = j
      } else {
        const p = yamlToForm(yaml.value)
        if (p === null) {
          tabError.value = 'Could not parse YAML — fix errors before switching to Form view.'
          return
        }
        policy.value = p
      }
      activeTab.value = tab
      return
    }

    // ── leaving JSON ──────────────────────────────────────────────────────────
    if (from === 'json') {
      if (tab === 'yaml') {
        const y = jsonToYaml(jsonText.value)
        if (y === null) {
          tabError.value = 'Could not parse JSON — fix errors before switching to YAML view.'
          return
        }
        yaml.value = y
      } else {
        // JSON → Form: convert via YAML to reuse the single yamlToForm mapping
        const y = jsonToYaml(jsonText.value)
        if (y === null) {
          tabError.value = 'Could not parse JSON — fix errors before switching to Form view.'
          return
        }
        const p = yamlToForm(y)
        if (p === null) {
          tabError.value = 'Could not map JSON to form fields — fix errors before switching to Form view.'
          return
        }
        policy.value = p
      }
      activeTab.value = tab
      return
    }
  }

  function addDevice() {
    policy.value.devices.push(defaultDevice())
  }

  function removeDevice(index: number) {
    policy.value.devices.splice(index, 1)
  }

  function getBodyForSubmit(): { body: string; contentType: string } {
    if (activeTab.value === 'json')
      return { body: jsonText.value, contentType: 'application/json' }
    if (activeTab.value === 'yaml')
      return { body: yaml.value, contentType: 'application/x-yaml' }
    return { body: formToYaml(policy.value), contentType: 'application/x-yaml' }
  }

  async function triggerDiscover() {
    discovering.value = true
    discoverError.value = null
    lastJob.value = null
    try {
      const { body, contentType } = getBodyForSubmit()
      const result = await api.triggerDiscover(body, contentType)
      lastJob.value = result
      await router.push(`/review/${result.id}`)
    } catch (e: unknown) {
      const err = e as { data?: { detail?: string }; message?: string }
      discoverError.value = err.data?.detail
        ? JSON.stringify(err.data.detail, null, 2)
        : (err.message ?? 'Discover failed')
    } finally {
      discovering.value = false
    }
  }

  return {
    policy,
    yaml,
    jsonText,
    activeTab,
    tabError,
    discovering,
    discoverError,
    lastJob,
    switchTab,
    addDevice,
    removeDevice,
    triggerDiscover,
    getBodyForSubmit,
  }
}
