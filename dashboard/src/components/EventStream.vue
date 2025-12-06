<template>
  <div class="event-stream card">
    <h3>📊 Event Stream</h3>

    <div v-if="events.length === 0" class="empty-state">
      No events yet. Waiting for agent activity...
    </div>

    <div v-else class="events-list">
      <div
        v-for="event in events"
        :key="event.id"
        :class="['event-item', `event-${event.event_type.toLowerCase()}`]"
      >
        <div class="event-header">
          <span class="event-type">{{ event.event_type }}</span>
          <span class="event-time">{{ formatTime(event.timestamp) }}</span>
        </div>

        <div class="event-content">
          <div v-if="event.data.agent_id" class="event-meta">
            <span class="meta-label">Agent:</span>
            <span class="meta-value">{{ event.data.agent_id }}</span>
          </div>

          <div v-if="event.data.task_id" class="event-meta">
            <span class="meta-label">Task:</span>
            <span class="meta-value">{{ event.data.task_id.substring(0, 8) }}</span>
          </div>

          <div v-if="event.data.tool_name" class="event-meta">
            <span class="meta-label">Tool:</span>
            <span class="meta-value">{{ event.data.tool_name }}</span>
          </div>

          <div v-if="event.data.error" class="event-error">
            ⚠️ {{ event.data.error }}
          </div>

          <div v-if="event.ai_summary" class="event-summary">
            🧠 {{ event.ai_summary }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'EventStream',
  props: {
    events: {
      type: Array,
      required: true
    }
  },
  methods: {
    formatTime(timestamp) {
      if (!timestamp) return ''
      try {
        const date = new Date(timestamp)
        return date.toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit'
        })
      } catch (e) {
        return timestamp
      }
    }
  }
}
</script>

<style scoped>
.event-stream {
  margin-bottom: 2rem;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 600px;
  overflow-y: auto;
}

.events-list::-webkit-scrollbar {
  width: 8px;
}

.events-list::-webkit-scrollbar-track {
  background: #0f172a;
  border-radius: 4px;
}

.events-list::-webkit-scrollbar-thumb {
  background: #475569;
  border-radius: 4px;
}

.events-list::-webkit-scrollbar-thumb:hover {
  background: #64748b;
}

.event-item {
  padding: 1rem;
  background: #0f172a;
  border-radius: 0.5rem;
  border-left: 3px solid #475569;
  transition: all 0.2s;
}

.event-item:hover {
  transform: translateX(4px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.event-pretooluse {
  border-left-color: #3b82f6;
}

.event-posttooluse {
  border-left-color: #10b981;
}

.event-notification {
  border-left-color: #f59e0b;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.event-type {
  color: #e2e8f0;
  font-weight: 600;
  font-size: 0.875rem;
}

.event-time {
  color: #64748b;
  font-size: 0.75rem;
  font-family: 'Courier New', monospace;
}

.event-content {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.event-meta {
  display: flex;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.meta-label {
  color: #94a3b8;
  font-weight: 500;
}

.meta-value {
  color: #cbd5e1;
  font-family: 'Courier New', monospace;
}

.event-error {
  color: #ef4444;
  font-size: 0.875rem;
  padding: 0.5rem;
  background: #7f1d1d33;
  border-radius: 0.25rem;
}

.event-summary {
  color: #a78bfa;
  font-size: 0.875rem;
  padding: 0.5rem;
  background: #4c1d9533;
  border-radius: 0.25rem;
  font-style: italic;
}

.empty-state {
  color: #64748b;
  text-align: center;
  padding: 3rem;
  font-style: italic;
}
</style>
