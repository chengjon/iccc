<template>
  <div class="app">
    <header class="header">
      <div class="container">
        <h1>🤖 iCCC Dashboard</h1>
        <div class="status">
          <span :class="['status-indicator', wsConnected ? 'connected' : 'disconnected']"></span>
          {{ wsConnected ? 'Connected' : 'Disconnected' }}
        </div>
      </div>
    </header>

    <main class="main">
      <div class="container">
        <div class="grid">
          <!-- Stats Cards -->
          <div class="card">
            <h3>Total Events</h3>
            <div class="stat">{{ stats.totalEvents || 0 }}</div>
          </div>

          <div class="card">
            <h3>Active Agents</h3>
            <div class="stat">{{ activeAgents.length }}</div>
          </div>

          <div class="card">
            <h3>Tasks Pending</h3>
            <div class="stat">{{ stats.pendingTasks || 0 }}</div>
          </div>

          <div class="card">
            <h3>Completion Rate</h3>
            <div class="stat">{{ completionRate }}%</div>
          </div>
        </div>

        <!-- AI Summary -->
        <div v-if="latestSummary" class="card summary-card">
          <h3>🧠 AI Summary</h3>
          <p class="summary-text">{{ latestSummary }}</p>
          <small class="summary-time">{{ summaryTime }}</small>
        </div>

        <!-- Event Stream -->
        <EventStream :events="recentEvents" />

        <!-- Agent Status -->
        <div class="card">
          <h3>Agent Activity</h3>
          <div v-if="activeAgents.length === 0" class="empty-state">
            No active agents
          </div>
          <div v-else class="agent-list">
            <div v-for="agent in activeAgents" :key="agent.id" class="agent-item">
              <span class="agent-icon">🤖</span>
              <span class="agent-name">{{ agent.name }}</span>
              <span :class="['agent-status', agent.status]">{{ agent.status }}</span>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script>
import EventStream from './components/EventStream.vue'
import { ref, onMounted, onUnmounted, computed } from 'vue'

export default {
  name: 'App',
  components: {
    EventStream
  },
  setup() {
    const wsConnected = ref(false)
    const recentEvents = ref([])
    const stats = ref({})
    const activeAgents = ref([])
    const latestSummary = ref('')
    const summaryTime = ref('')

    let ws = null

    const completionRate = computed(() => {
      const total = (stats.value.completedTasks || 0) + (stats.value.pendingTasks || 0)
      if (total === 0) return 0
      return Math.round(((stats.value.completedTasks || 0) / total) * 100)
    })

    const connectWebSocket = () => {
      ws = new WebSocket('ws://localhost:8000/ws')

      ws.onopen = () => {
        console.log('WebSocket connected')
        wsConnected.value = true
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === 'events_batch') {
            // Add new events to the beginning
            recentEvents.value = [...data.events, ...recentEvents.value].slice(0, 100)

            if (data.summary) {
              latestSummary.value = data.summary
              summaryTime.value = new Date().toLocaleTimeString()
            }
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        wsConnected.value = false

        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000)
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }
    }

    const fetchStats = async () => {
      try {
        const response = await fetch('/api/stats')
        const data = await response.json()
        stats.value = data.storage || {}
      } catch (e) {
        console.error('Failed to fetch stats:', e)
      }
    }

    const fetchEvents = async () => {
      try {
        const response = await fetch('/api/events?limit=50')
        const data = await response.json()
        recentEvents.value = data.events || []
      } catch (e) {
        console.error('Failed to fetch events:', e)
      }
    }

    onMounted(() => {
      connectWebSocket()
      fetchStats()
      fetchEvents()

      // Refresh stats every 10 seconds
      const interval = setInterval(fetchStats, 10000)

      onUnmounted(() => {
        clearInterval(interval)
        if (ws) {
          ws.close()
        }
      })
    })

    return {
      wsConnected,
      recentEvents,
      stats,
      activeAgents,
      latestSummary,
      summaryTime,
      completionRate
    }
  }
}
</script>

<style scoped>
.app {
  min-height: 100vh;
  background: #0f172a;
}

.header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 2rem 0;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.header .container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header h1 {
  color: white;
  font-size: 2rem;
  font-weight: 700;
}

.status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: white;
  font-size: 0.875rem;
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

.status-indicator.connected {
  background: #10b981;
}

.status-indicator.disconnected {
  background: #ef4444;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.main {
  padding: 2rem 0;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 2rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.card {
  background: #1e293b;
  border-radius: 0.75rem;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.card h3 {
  color: #94a3b8;
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.stat {
  color: #e2e8f0;
  font-size: 2.5rem;
  font-weight: 700;
  line-height: 1;
}

.summary-card {
  margin-bottom: 2rem;
}

.summary-text {
  color: #cbd5e1;
  line-height: 1.6;
  margin-bottom: 0.5rem;
}

.summary-time {
  color: #64748b;
  font-size: 0.75rem;
}

.empty-state {
  color: #64748b;
  text-align: center;
  padding: 2rem;
  font-style: italic;
}

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.agent-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #0f172a;
  border-radius: 0.5rem;
}

.agent-icon {
  font-size: 1.5rem;
}

.agent-name {
  flex: 1;
  color: #e2e8f0;
  font-weight: 500;
}

.agent-status {
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.agent-status.busy {
  background: #fbbf2433;
  color: #fbbf24;
}

.agent-status.idle {
  background: #10b98133;
  color: #10b981;
}
</style>
