// TypeScript interfaces matching orbweaver backend models

// ── Review ────────────────────────────────────────────────────────────────

export type ReviewStatus = 'pending' | 'ready' | 'ingested' | 'failed'
export type ItemStatus = 'pending' | 'accepted' | 'rejected'
export type CableConfidence = 'confirmed' | 'partial' | 'unresolvable'

export interface ReviewItem<T = NormalizedDevice> {
  index: number
  status: ItemStatus
  data: T
}

export interface CableReviewItem extends ReviewItem<CableCandidate> { }

export interface ReviewSummary {
  id: string
  policy_name: string
  created_at: string
  updated_at: string
  status: ReviewStatus
  device_count: number
  cable_count?: number
  accepted: number
  rejected: number
  pending: number
  accepted_cables?: number
  rejected_cables?: number
  pending_cables?: number
  error: string | null
}

export interface ReviewSession extends ReviewSummary {
  defaults: Record<string, unknown>
  devices: ReviewItem[]
  cables: CableReviewItem[]
  cable_summary: CableResolutionSummary | null
}

// ── Discovery (COM) ────────────────────────────────────────────────────────

export interface NormalizedLLDPNeighbor {
  local_interface: string
  neighbor_device_name: string
  neighbor_interface: string
  neighbor_chassis_mac: string
  neighbor_mgmt_ip: string
  neighbor_system_description: string
}

export interface NormalizedCable {
  device_a_name: string
  interface_a_name: string
  device_b_name: string
  interface_b_name: string
  label?: string
  description?: string
  color?: string
}

export interface CableCandidate {
  cable: NormalizedCable
  confidence: CableConfidence
  device_a_discovered: boolean
  device_b_discovered: boolean
  skip_reason: string | null
  lldp_neighbor: NormalizedLLDPNeighbor | null
  resolution_notes: string
  lldp_direction: string
}

export interface CableSkipEntry {
  local_device: string
  local_interface: string
  neighbor_hostname: string
  reason: string
  neighbor_interface: string
  neighbor_chassis_mac: string
  neighbor_mgmt_ip: string
}

export interface CableResolutionSummary {
  discovered: number
  candidates: number
  created: number
  skipped: number
  unresolvable: number
  skip_entries: CableSkipEntry[]
  ingestion_disabled: boolean
  ingestion_error: string | null
  resolution_duration_ms?: number
  ingestion_duration_ms?: number
}

export interface NormalizedDevice {
  name: string
  serial_number: string | null
  device_type: NormalizedDeviceType | null
  platform: NormalizedPlatform | null
  site: NormalizedSite | null
  role: NormalizedDeviceRole | null
  status: string
  interfaces: NormalizedInterface[]
  vlans: NormalizedVLAN[]
  lldp_neighbors: NormalizedLLDPNeighbor[]
}

export interface NormalizedDeviceType {
  model: string
  part_number: string | null
  manufacturer: NormalizedManufacturer | null
}

export interface NormalizedManufacturer {
  name: string
}

export interface NormalizedPlatform {
  name: string
  manufacturer: NormalizedManufacturer | null
  family: string | null
  version_major: string | null
  version_minor: string | null
  version_full: string | null
}

export interface NormalizedSite {
  name: string
}

export interface NormalizedDeviceRole {
  name: string
}

export interface NormalizedInterface {
  name: string
  type: string
  enabled: boolean
  description: string
  mac_address: string | null
  mtu: number | null
  speed: number | null
  mode: string | null
  untagged_vlan: NormalizedVLAN | null
  tagged_vlans: NormalizedVLAN[]
  ip_addresses: NormalizedIPAddress[]
  lag: string | null
}

export interface NormalizedIPAddress {
  address: string
  role: string | null
  primary: boolean
}

export interface NormalizedVLAN {
  vid: number
  name: string
  status: string
}

// ── Collectors ────────────────────────────────────────────────────────────

export interface CollectorInfo {
  name: string
  vendor: string
}

// ── Ingest ────────────────────────────────────────────────────────────────

export interface IngestRequest {
  dry_run?: boolean
  statuses?: ItemStatus[]
}

export interface IngestResponse {
  review_id: string
  dry_run: boolean
  ingested_count: number
  skipped_count: number
  errors: string[]
}

export interface CableIngestResponse extends CableResolutionSummary { }

// ── Status ────────────────────────────────────────────────────────────────

export interface ReviewCounts {
  total: number
  pending: number
  ready: number
  ingested: number
  failed: number
}

export interface BackendStatus {
  version: string
  up_time_seconds: number
  diode_target: string | null
  dry_run: boolean
  reviews: ReviewCounts
  policies: PolicyStatus[]
}

export interface PolicyStatus {
  name: string
  status: string
  runs: PolicyRun[]
}

export interface PolicyRun {
  target: string
  status: string
  started_at: string
  finished_at: string | null
}

// ── Config / Policy ───────────────────────────────────────────────────────

export interface DiscoverJobResponse {
  id: string
  status: ReviewStatus
  detail: string
}

// ── Seed ──────────────────────────────────────────────────────────────────

export interface SeedCounts {
  tenants: number
  sites: number
  racks: number
  manufacturers: number
  device_types: number
  device_roles: number
  platforms: number
  devices: number
  tags: number
}

export interface SeedResult {
  created: SeedCounts
  skipped: SeedCounts
  errors: string[]
}
