<script setup lang="ts">
import * as jsYaml from 'js-yaml'

const api = useApi()

const yamlContent = ref('')
const path = ref('')
const container = ref('')
const loading = ref(true)
const saving = ref(false)
const triggering = ref(false)
const message = ref<{ type: 'success' | 'error'; text: string } | null>(null)

async function load() {
  loading.value = true
  message.value = null
  try {
    const data = await api.getOrbAgentConfig()
    yamlContent.value = data.yaml
    path.value = data.path
    container.value = data.container
  }
  catch (e: unknown) {
    const msg = (e as { data?: { detail?: string }; message?: string })?.data?.detail
      ?? (e as { message?: string })?.message
      ?? 'Could not load config'
    message.value = { type: 'error', text: msg }
  }
  finally {
    loading.value = false
  }
}

async function apply() {
  saving.value = true
  message.value = null
  try {
    const result = await api.setOrbAgentConfig(yamlContent.value)
    message.value = { type: 'success', text: result.detail }
  }
  catch (e: unknown) {
    const msg = (e as { data?: { detail?: string }; message?: string })?.data?.detail
      ?? (e as { message?: string })?.message
      ?? 'Failed to apply config'
    message.value = { type: 'error', text: msg }
  }
  finally {
    saving.value = false
  }
}

/**
 * Extract the first policy from agent.yml and convert it into standalone
 * policy YAML (policies: { name: { config: { defaults }, scope } }).
 * Strips the schedule so the orb-agent runs it as a one-time job.
 */
function agentYamlToPolicyYaml(agentYaml: string): string {
  const doc = jsYaml.load(agentYaml) as Record<string, unknown>
  const orbPolicies = (doc?.orb as Record<string, unknown>)?.policies as Record<string, unknown> | undefined
  const ddPolicies = (orbPolicies?.device_discovery ?? {}) as Record<string, Record<string, unknown>>
  const entries = Object.entries(ddPolicies)
  if (entries.length === 0) throw new Error('No policies found in agent.yml')

  const policies: Record<string, unknown> = {}
  for (const [name, policyData] of entries) {
    const config = policyData.config as Record<string, unknown> | undefined
    const defaults = (config?.defaults ?? {}) as Record<string, unknown>
    const scope = policyData.scope as unknown[]
    policies[name] = {
      ...(Object.keys(defaults).length ? { config: { defaults } } : {}),
      scope: scope ?? [],
    }
  }
  return jsYaml.dump({ policies }, { lineWidth: -1 })
}

async function triggerNow() {
  triggering.value = true
  message.value = null
  try {
    const policyYaml = agentYamlToPolicyYaml(yamlContent.value)
    await $fetch(`${useRuntimeConfig().public.apiBase}/api/v1/orb-agent/trigger`, {
      method: 'POST',
      body: policyYaml,
      headers: { 'Content-Type': 'application/x-yaml' },
    })
    message.value = { type: 'success', text: 'Triggered — orb-agent is running discovery now.' }
  }
  catch (e: unknown) {
    const msg = (e as { data?: { detail?: string }; message?: string })?.data?.detail
      ?? (e as { message?: string })?.message
      ?? 'Trigger failed'
    message.value = { type: 'error', text: msg }
  }
  finally {
    triggering.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="max-w-3xl">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold">orb-agent Config</h1>
        <p v-if="path" class="mt-0.5 text-xs text-muted-foreground font-mono">{{ path }}</p>
      </div>
      <button
        class="text-xs text-muted-foreground hover:text-foreground"
        @click="load"
      >
        Reload from disk
      </button>
    </div>

    <div v-if="loading" class="text-sm text-muted-foreground">Loading…</div>

    <template v-else>
      <textarea
        v-model="yamlContent"
        class="w-full rounded-md border bg-background font-mono text-xs p-3 focus:outline-none focus:ring-2 focus:ring-ring resize-none"
        rows="30"
        spellcheck="false"
      />

      <div
        v-if="message"
        class="mt-3 rounded-md p-3 text-xs"
        :class="message.type === 'success'
          ? 'bg-green-500/10 border border-green-500/30 text-green-700'
          : 'bg-destructive/10 border border-destructive/30 text-destructive'"
      >
        {{ message.text }}
      </div>

      <div class="mt-3 flex gap-2">
        <button
          :disabled="triggering"
          class="flex-1 rounded-md border py-2 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
          @click="triggerNow"
        >
          {{ triggering ? 'Triggering…' : 'Trigger orb-agent now' }}
        </button>
        <button
          :disabled="saving"
          class="flex-1 rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          @click="apply"
        >
          {{ saving ? `Restarting ${container}…` : `Apply & Restart ${container}` }}
        </button>
      </div>
    </template>
  </div>
</template>
