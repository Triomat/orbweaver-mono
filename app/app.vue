<template>
  <div class="min-h-screen bg-background text-foreground">
    <header class="border-b bg-card">
      <div class="container mx-auto flex h-14 items-center gap-4 px-4">
        <NuxtLink to="/" class="flex items-center gap-2 font-semibold text-primary">
          <span class="text-lg">🕷 orbweaver</span>
        </NuxtLink>
        <nav class="flex gap-4 text-sm">
          <NuxtLink
            to="/config"
            class="text-muted-foreground transition-colors hover:text-foreground"
            active-class="text-foreground font-medium"
          >
            Discover
          </NuxtLink>
          <NuxtLink
            to="/reviews"
            class="text-muted-foreground transition-colors hover:text-foreground"
            active-class="text-foreground font-medium"
          >
            Reviews
          </NuxtLink>
        </nav>
      </div>
    </header>
    <main class="container mx-auto px-4 py-6">
      <NuxtPage />
    </main>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono&display=swap');

:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --card: 0 0% 100%;
  --card-foreground: 222.2 84% 4.9%;
  --popover: 0 0% 100%;
  --popover-foreground: 222.2 84% 4.9%;
  --primary: 221.2 83.2% 53.3%;
  --primary-foreground: 210 40% 98%;
  --secondary: 210 40% 96.1%;
  --secondary-foreground: 222.2 47.4% 11.2%;
  --muted: 210 40% 96.1%;
  --muted-foreground: 215.4 16.3% 46.9%;
  --accent: 210 40% 96.1%;
  --accent-foreground: 222.2 47.4% 11.2%;
  --destructive: 0 84.2% 60.2%;
  --destructive-foreground: 210 40% 98%;
  --border: 214.3 31.8% 91.4%;
  --input: 214.3 31.8% 91.4%;
  --ring: 221.2 83.2% 53.3%;
  --radius: 0.5rem;
}

body {
  font-family: 'Inter', sans-serif;
}
</style>
