<template>
  <div class="flex flex-col items-center justify-center py-24 text-center">
    <h1 class="text-3xl font-semibold mb-3">orbweaver UI</h1>
    <p class="text-muted-foreground mb-8 max-w-md">
      Discover network devices, review the results, and ingest into NetBox via Diode.
    </p>
    <div class="flex gap-3">
      <NuxtLink
        to="/config"
        class="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        New Discovery
      </NuxtLink>
      <NuxtLink
        to="/reviews"
        class="inline-flex items-center rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
      >
        View Reviews
      </NuxtLink>
    </div>
  </div>
</template>
