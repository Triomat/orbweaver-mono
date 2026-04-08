/**
 * Config editor state composable.
 *
 * Manages the policy form state and YAML editor content.
 * The form is the source of truth while the Form tab is active.
 * Switching tabs serializes/deserializes between form and YAML.
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

function formToYaml(policy: PolicyForm): string {
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
  if (policy.defaults.site) defaults.site = policy.defaults.site
  if (policy.defaults.role) defaults.role = policy.defaults.role
  if (policy.defaults.tags) {
    defaults.tags = policy.defaults.tags.split(',').map((t) => t.trim()).filter(Boolean)
  }
  if (policy.defaults.tenant) defaults.tenant = policy.defaults.tenant

  const configObj: Record<string, unknown> = {}
  if (policy.autoIngest) configObj.auto_ingest = true
  if (Object.keys(defaults).length > 0) configObj.defaults = defaults

  const policyObj: Record<string, unknown> = { scope }
  if (Object.keys(configObj).length > 0) policyObj.config = configObj

  return jsYaml.dump({ policies: { [policy.name]: policyObj } }, { lineWidth: -1 })
}

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

export function useConfig() {
  const api = useApi()
  const router = useRouter()

  // Use useState so state survives navigation between pages
  const policy = useState<PolicyForm>('config-policy', () => defaultPolicy())
  const yaml = useState<string>('config-yaml', () => formToYaml(defaultPolicy()))
  const activeTab = useState<'form' | 'yaml'>('config-tab', () => 'form')
  const tabError = ref<string | null>(null)
  const discovering = ref(false)
  const discoverError = ref<string | null>(null)
  const lastJob = ref<DiscoverJobResponse | null>(null)

  function switchTab(tab: 'form' | 'yaml') {
    tabError.value = null
    if (tab === 'yaml') {
      yaml.value = formToYaml(policy.value)
      activeTab.value = 'yaml'
    } else {
      const parsed = yamlToForm(yaml.value)
      if (parsed === null) {
        tabError.value = 'Could not parse YAML — fix errors before switching to Form view.'
        return
      }
      policy.value = parsed
      activeTab.value = 'form'
    }
  }

  function addDevice() {
    policy.value.devices.push(defaultDevice())
  }

  function removeDevice(index: number) {
    policy.value.devices.splice(index, 1)
  }

  function getYamlForSubmit(): string {
    if (activeTab.value === 'form') {
      return formToYaml(policy.value)
    }
    return yaml.value
  }

  async function triggerDiscover() {
    discovering.value = true
    discoverError.value = null
    lastJob.value = null
    try {
      const result = await api.triggerDiscover(getYamlForSubmit())
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
    activeTab,
    tabError,
    discovering,
    discoverError,
    lastJob,
    switchTab,
    addDevice,
    removeDevice,
    triggerDiscover,
    getYamlForSubmit,
  }
}
