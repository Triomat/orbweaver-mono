<script setup lang="ts">
import { Codemirror } from 'vue-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import { indentWithTab } from '@codemirror/commands'
import { keymap } from '@codemirror/view'
import { basicSetup } from 'codemirror'

const props = defineProps<{ modelValue: string; rows?: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const extensions = [
  basicSetup,
  yaml(),
  keymap.of([indentWithTab]),
]
</script>

<template>
  <Codemirror
    :model-value="props.modelValue"
    :extensions="extensions"
    :style="{ height: `${(props.rows ?? 22) * 1.5}rem`, fontSize: '0.75rem' }"
    class="rounded-md border overflow-hidden"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
