<template>
  <div class="app">
    <PhaseBanner
      :turn="turn" :phase="phase" :winner="winner"
      @toggleDetail="detailOpen = !detailOpen"
    />
    <ConversationView :messages="messages" :gameStarted="gameStarted" />
    <div class="controls" v-if="!connected">
      <button @click="connect" class="btn-connect">连接服务器</button>
    </div>
    <div class="controls" v-else-if="!gameStarted">
      <button @click="startGame" class="btn-start">{{ winner ? '再来一局' : '开始游戏' }}</button>
    </div>
    <DetailPanel
      :open="detailOpen"
      :players="players"
      :events="rawEvents"
      @close="detailOpen = false"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import PhaseBanner from './components/PhaseBanner.vue'
import ConversationView from './components/ConversationView.vue'
import DetailPanel from './components/DetailPanel.vue'

const connected = ref(false)
const gameStarted = ref(false)
const detailOpen = ref(false)
const turn = ref(0)
const phase = ref('')
const winner = ref('')
const players = ref([])
const messages = ref([])
const rawEvents = ref([])

let ws = null
const pendingThinking = {}

function connect() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${location.hostname}:8000/ws`)

  ws.onopen = () => { connected.value = true }
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    handleEvent(msg.type, msg.data)
  }
  ws.onclose = () => { connected.value = false; gameStarted.value = false }
}

function startGame() {
  players.value = []
  messages.value = []
  rawEvents.value = []
  turn.value = 0
  phase.value = ''
  winner.value = ''
  for (const k in pendingThinking) delete pendingThinking[k]
  ws.send(JSON.stringify({ action: 'start', config: 'config/game_config.yaml' }))
  gameStarted.value = true
}

function addBanner(type, text) {
  messages.value.push({ type: 'banner', bannerType: type, text })
}

function addSpeech(player, speech, interaction = null) {
  const thinking = pendingThinking[player.id]
  delete pendingThinking[player.id]
  messages.value.push({ type: 'speech', player, speech, thinking: thinking || '', interaction })
}

function addRawEvent(type, message) {
  rawEvents.value.unshift({ type, message, time: Date.now() })
}

function handleEvent(type, data) {
  switch (type) {
    case 'game_init':
      players.value = data.players
      break

    case 'phase':
      phase.value = data.phase
      turn.value = data.turn
      if (data.phase === 'night') addBanner('phase', `🌙 第 ${data.turn} 天 夜晚降临`)
      else addBanner('phase', `☀️ 第 ${data.turn} 天 天亮了`)
      addRawEvent('phase', `第${data.turn}天 ${data.phase === 'night' ? '夜晚' : '白天'}`)
      break

    case 'player_thinking':
      pendingThinking[data.player_id] = data.text
      break

    case 'night_wolf_vote': {
      const p = players.value.find(p => p.id === data.wolf_id)
      const label = data.round === 0 ? '盲选' : `协商第${data.round}轮`
      const speech = `🎯 选择了玩家 ${data.target} (${label})`
      if (p) {
        addSpeech(p, speech)
      } else {
        addBanner('wolf', `🐺 玩家${data.wolf_id} ${speech}`)
      }
      addRawEvent('wolf', `狼人${data.wolf_id} 选择目标: ${data.target} (${label})`)
      break
    }

    case 'night_wolf_kill':
      addBanner('wolf', `🐺 狼人击杀了玩家 ${data.target}`)
      addRawEvent('wolf', `狼人击杀玩家${data.target}`)
      break

    case 'night_witch': {
      if (data.save) { addBanner('witch', `🧪 女巫救活了玩家 ${data.save}`); addRawEvent('witch', `女巫救活玩家${data.save}`) }
      if (data.poison) { addBanner('witch', `☠️ 女巫毒杀了玩家 ${data.poison}`); addRawEvent('witch', `女巫毒杀玩家${data.poison}`) }
      if (!data.save && !data.poison) addRawEvent('witch', '女巫未使用药水')
      break
    }

    case 'night_witch_action': {
      const p = players.value.find(p => p.id === data.player_id)
      let speech = ''
      if (data.save_id) speech = `🧪 使用解药，救活了玩家 ${data.save_id}`
      if (data.poison_id) speech = `☠️ 使用毒药，毒杀了玩家 ${data.poison_id}`
      if (!data.save_id && !data.poison_id) speech = '选择不使用药水'
      if (p) addSpeech(p, speech)
      break
    }

    case 'night_guard':
      addBanner('guard', `🛡️ 守卫守护了玩家 ${data.target}`)
      addRawEvent('guard', `守卫(${data.guard_id})守护玩家${data.target}`)
      break

    case 'night_guard_action': {
      const p = players.value.find(p => p.id === data.player_id)
      if (p) addSpeech(p, `🛡️ 守护了玩家 ${data.target}`)
      break
    }

    case 'night_seer':
      addBanner('seer', `🔮 预言家查验玩家 ${data.target}: ${data.result}`)
      addRawEvent('seer', `预言家查验玩家${data.target}: ${data.result}`)
      break

    case 'night_seer_action': {
      const p = players.value.find(p => p.id === data.player_id)
      if (p) addSpeech(p, `🔮 查验了玩家 ${data.target}，结果是: ${data.result}`)
      break
    }

    case 'night_result':
      if (data.dead && data.dead.length > 0) {
        addBanner('death', `💀 夜晚死亡: 玩家 ${data.dead.join(', ')}`)
      } else {
        addBanner('death', '✨ 昨晚是平安夜')
      }
      addRawEvent('death', data.dead?.length ? `夜晚死亡: ${data.dead.join(',')}` : '平安夜')
      break

    case 'day_speech': {
      const p = players.value.find(p => p.id === data.player_id)
      if (p) addSpeech(p, data.statement, data.interaction)
      addRawEvent('speech', `玩家${data.player_id}: ${data.statement}`)
      break
    }

    case 'day_vote': {
      const parts = Object.entries(data.votes)
        .map(([v, t]) => `#${v}→${t === -1 ? '弃' : '#' + t}`)
        .join('  ')
      addBanner('vote', `🗳️ 投票: ${parts}`)
      addRawEvent('vote', `投票: ${parts}`)
      break
    }

    case 'idiot_reveal':
      addBanner('idiot', `🤡 玩家 ${data.player_id} 是白痴！亮明身份留在场上`)
      addRawEvent('idiot', `白痴${data.player_id}亮明身份`)
      break

    case 'day_execute':
      addBanner('execute', `⚰️ 玩家 ${data.player_id} (${data.role_name}) 被投票处决`)
      addRawEvent('execute', `玩家${data.player_id}(${data.role_name})被处决`)
      break

    case 'hunter_shoot':
      addBanner('hunter', `🔫 猎人 ${data.hunter_id} 开枪带走了玩家 ${data.target_id}`)
      addRawEvent('hunter', `猎人${data.hunter_id}带走玩家${data.target_id}`)
      break

    case 'player_dead': {
      const p = players.value.find(p => p.id === data.player_id)
      if (p) p.is_alive = false
      addRawEvent('death', `玩家${data.player_id}(${data.role_name})死亡`)
      break
    }

    case 'token_usage': {
      const p = players.value.find(p => p.id === data.player_id)
      if (p) Object.assign(p, data)
      break
    }

    case 'game_over':
      winner.value = data.winner
      gameStarted.value = false
      addBanner('game_over', `🏆 游戏结束！获胜方: ${data.winner}`)
      addRawEvent('game_over', `游戏结束, 获胜: ${data.winner}`)
      break

    case 'error':
      addBanner('error', `❌ ${data.message}`)
      addRawEvent('error', data.message)
      break
  }
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f1a; color: #eee; }
.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  max-width: 800px;
  margin: 0 auto;
  border-left: 1px solid #1a1a2e;
  border-right: 1px solid #1a1a2e;
}
.controls {
  text-align: center;
  padding: 16px 20px;
  border-top: 1px solid #1a1a2e;
  flex-shrink: 0;
}
button {
  padding: 12px 36px;
  font-size: 16px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: bold;
}
.btn-connect { background: #4a9eff; color: white; }
.btn-start { background: #e94560; color: white; animation: pulse 1.5s infinite; }
@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
button:hover { opacity: 0.9; }
</style>
