/**
 * Config editor state composable.
 *
 * Manages the YAML policy editor content and validation state.
 */

import type { DiscoverJobResponse } from '~/types/api'

const DEFAULT_YAML = `policies:
  my-discovery:
    config:
      defaults:
        site: ""
        role: ""
    scope:
      - hostname: 192.168.1.1
        username: admin
        password: ""
        collector: cisco_ios
`

export function useConfig() {
  const api = useApi()
  const router = useRouter()

  const yaml = ref(DEFAULT_YAML)
  const discovering = ref(false)
  const discoverError = ref<string | null>(null)
  const lastJob = ref<DiscoverJobResponse | null>(null)

  async function triggerDiscover() {
    discovering.value = true
    discoverError.value = null
    lastJob.value = null
    try {
      const result = await api.triggerDiscover(yaml.value)
      lastJob.value = result
      // Navigate to the review page immediately; it will poll for status
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
    yaml,
    discovering,
    discoverError,
    lastJob,
    triggerDiscover,
  }
}
