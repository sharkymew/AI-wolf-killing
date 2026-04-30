<template>
  <div class="conversation" ref="scrollContainer" @scroll="onScroll">
    <div v-if="!gameStarted && messages.length === 0" class="empty-state">
      <div class="empty-icon">🐺</div>
      <div class="empty-text">点击下方按钮开始游戏</div>
      <div class="empty-sub">AI 模型将自动进行狼人杀对局</div>
    </div>
    <template v-for="(msg, i) in messages" :key="i">
      <SystemBanner v-if="msg.type === 'banner'" :type="msg.bannerType" :text="msg.text" />
      <ChatBubble
        v-else-if="msg.type === 'speech'"
        :player="msg.player"
        :speech="msg.speech"
        :thinking="msg.thinking"
      />
    </template>
    <div ref="bottom" />
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import SystemBanner from './SystemBanner.vue'
import ChatBubble from './ChatBubble.vue'

const props = defineProps({
  messages: Array,
  gameStarted: Boolean,
})

const scrollContainer = ref(null)
const bottom = ref(null)
const userScrolled = ref(false)

function scrollToBottom() {
  if (!userScrolled.value) {
    nextTick(() => bottom.value?.scrollIntoView({ behavior: 'smooth' }))
  }
}

function onScroll() {
  const el = scrollContainer.value
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  userScrolled.value = dist > 80
}

watch(() => props.messages.length, scrollToBottom)
onMounted(scrollToBottom)
</script>

<style scoped>
.conversation {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0 16px;
}
.empty-state {
  text-align: center;
  padding: 80px 20px;
}
.empty-icon { font-size: 64px; margin-bottom: 16px; }
.empty-text { font-size: 18px; color: #aaa; margin-bottom: 8px; }
.empty-sub { font-size: 14px; color: #666; }
.conversation::-webkit-scrollbar { width: 6px; }
.conversation::-webkit-scrollbar-track { background: transparent; }
.conversation::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
</style>
