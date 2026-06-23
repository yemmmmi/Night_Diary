<script setup lang="ts">
import { PhTrash } from '@phosphor-icons/vue'
import type { Conversation } from '@/shared/api/conversation'

defineProps<{
  conversations: Conversation[]
  activeId: string | null
}>()

defineEmits<{
  select: [id: string]
  delete: [id: string]
}>()
</script>

<template>
  <aside class="conv-list">
    <div
      v-for="conv in conversations"
      :key="conv.id"
      class="conv-item"
      :class="{ 'is-active': conv.id === activeId }"
    >
      <button type="button" class="conv-item__body" @click="$emit('select', conv.id)">
        <span class="conv-item__title">{{ conv.title }}</span>
      </button>
      <button
        type="button"
        class="conv-item__delete"
        title="删除会话"
        @click="$emit('delete', conv.id)"
      >
        <PhTrash :size="13" />
      </button>
    </div>

    <div v-if="conversations.length === 0" class="conv-list__empty">
      <p>暂无会话</p>
    </div>
  </aside>
</template>

<style scoped>
.conv-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding-right: 0.25rem;
  overflow-y: auto;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  border-radius: 0.5rem;
  transition: background var(--motion-duration) var(--motion-ease);
}

.conv-item:hover {
  background: var(--color-bg-elevated-2);
}

.conv-item.is-active {
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.conv-item__body {
  flex: 1;
  text-align: left;
  border: none;
  background: none;
  padding: 0.5rem 0.625rem;
  cursor: pointer;
  overflow: hidden;
}

.conv-item__title {
  display: block;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-item__delete {
  display: none;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  flex-shrink: 0;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.conv-item:hover .conv-item__delete {
  display: inline-flex;
}

.conv-item__delete:hover {
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
}

.conv-list__empty {
  padding: 1rem 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-align: center;
}
</style>
