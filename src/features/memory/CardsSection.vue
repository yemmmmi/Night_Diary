<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut, PhMagnifyingGlass, PhXCircle } from '@phosphor-icons/vue'

import CardTypeBadge from '@/features/card/CardTypeBadge.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { memoryCopy as copy } from '@/shared/copy/memory'
import { useCardStore } from '@/stores/card'
import { searchCards, type CardSearchResult, type MemoryCard } from '@/shared/api/card'
import { formatApiError } from '@/shared/utils/apiError'

const router = useRouter()
const cardStore = useCardStore()

const searchQuery = ref('')
const searchResults = ref<CardSearchResult[]>([])
const searchLoading = ref(false)
const searchActive = ref(false)
const error = ref<string | null>(null)

const displayCards = computed<MemoryCard[]>(() =>
  searchActive.value ? searchResults.value : cardStore.cards,
)

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    clearSearch()
    return
  }
  searchLoading.value = true
  searchActive.value = true
  error.value = null
  try {
    const result = await searchCards(q, 20)
    searchResults.value = result.results
  } catch (err) {
    error.value = formatApiError(err, '搜索失败')
  } finally {
    searchLoading.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchActive.value = false
  searchResults.value = []
}

/** 账簿小字时间：08/25 21:00（不依赖 locale）。 */
function formatTime(card: MemoryCard): string {
  return `${card.created_at.slice(5, 10).replace('-', '/')} ${card.created_at.slice(11, 16)}`
}

async function expandCard(card: MemoryCard) {
  error.value = null
  try {
    const result = await cardStore.expandCard(card.card_id)
    await cardStore.loadCards()
    router.push(`/write/${result.diary_id}`)
  } catch (err) {
    error.value = formatApiError(err, '展开卡片失败')
  }
}

async function deleteCard(card: MemoryCard) {
  error.value = null
  try {
    await cardStore.removeCard(card.card_id)
    if (searchActive.value) {
      searchResults.value = searchResults.value.filter((r) => r.card_id !== card.card_id)
    }
  } catch (err) {
    error.value = formatApiError(err, '删除卡片失败')
  }
}
</script>

<template>
  <div class="cards-section">
    <p v-if="error" class="cards-section__error">{{ error }}</p>

    <div class="cards-section__search">
      <div class="cards-section__search-row">
        <PhMagnifyingGlass :size="16" class="cards-section__search-icon" />
        <input
          v-model="searchQuery"
          class="cards-section__search-input"
          :placeholder="copy.cardsSearchPlaceholder"
          @keydown.enter="doSearch"
        />
        <button v-if="searchQuery" class="cards-section__search-clear" @click="clearSearch">
          <PhXCircle :size="14" />
        </button>
      </div>
      <GameButton
        variant="ghost"
        :disabled="!searchQuery.trim() || searchLoading"
        @click="doSearch"
      >
        {{ searchLoading ? copy.cardsSearching : copy.cardsSearch }}
      </GameButton>
    </div>

    <p
      v-if="searchActive && !searchLoading && searchResults.length === 0"
      class="cards-section__empty"
    >
      {{ copy.cardsSearchEmpty }}
    </p>

    <div v-if="!searchActive && cardStore.cards.length === 0" class="cards-section__empty">
      <p>{{ copy.cardsEmpty }}</p>
      <p class="cards-section__empty-hint">{{ copy.cardsEmptyHint }}</p>
    </div>

    <!-- 记忆卡片细线行：无卡片底，只以底线分隔 -->
    <div
      v-for="card in displayCards"
      :key="card.card_id"
      class="cards-section__row"
    >
      <div class="cards-section__row-head">
        <EmotionChips :emotions="card.emotions" :emotion="card.emotion" />
        <CardTypeBadge :card-type="card.card_type" />
      </div>
      <p v-if="card.event_summary" class="cards-section__row-summary font-diary">
        {{ card.event_summary }}
      </p>
      <div v-if="card.tags.length > 0" class="cards-section__row-tags">
        <span v-for="tag in card.tags" :key="tag" class="cards-section__row-tag">
          {{ tag }}
        </span>
      </div>
      <div class="cards-section__row-footer">
        <span class="cards-section__row-time">{{ formatTime(card) }}</span>
        <div class="cards-section__item-actions">
          <button
            v-if="!card.diary_id"
            class="cards-section__action-btn"
            :title="copy.cardsExpandToDiary"
            @click="expandCard(card)"
          >
            <PhArrowSquareOut :size="14" />
          </button>
          <button
            class="cards-section__action-btn cards-section__action-btn--danger"
            :title="copy.cardsDelete"
            @click="deleteCard(card)"
          >
            &times;
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cards-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.cards-section__error {
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-seal);
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
  font-size: 0.8125rem;
  margin: 0;
}
.cards-section__search {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.cards-section__search-row {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-button);
  background: var(--color-bg-elevated);
}
.cards-section__search-icon {
  color: var(--color-text-secondary);
  flex-shrink: 0;
}
.cards-section__search-input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  font-family: var(--font-ui);
}
.cards-section__search-clear {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0;
  display: inline-flex;
}
.cards-section__empty {
  text-align: center;
  padding: 1.25rem 1rem;
  color: var(--color-text-faint);
  font-size: 0.8125rem;
  margin: 0;
}
.cards-section__empty-hint {
  font-size: 0.75rem;
  margin: 0.375rem 0 0;
  opacity: 0.85;
}

/* 卡片细线行 */
.cards-section__row {
  padding: 0.75rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-bottom: 1px solid var(--color-line);
}
.cards-section__row:last-child {
  border-bottom: none;
}
.cards-section__row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.cards-section__row-summary {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.8;
  color: var(--color-text-primary);
}
.cards-section__row-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.cards-section__row-tag {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
}
.cards-section__row-tag::before {
  content: '#';
}
.cards-section__row-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.cards-section__row-time {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}
.cards-section__item-actions {
  display: flex;
  gap: 0.25rem;
}
.cards-section__action-btn {
  border: none;
  background: transparent;
  color: var(--color-text-faint);
  cursor: pointer;
  padding: 0.25rem;
  border-radius: var(--radius-seal);
  display: inline-flex;
  font-size: 1rem;
  line-height: 1;
  transition: color var(--dur-fast) var(--ease-out-quart);
}
.cards-section__action-btn:hover {
  color: var(--color-text-primary);
}
.cards-section__action-btn--danger:hover {
  color: var(--color-danger);
}
</style>
