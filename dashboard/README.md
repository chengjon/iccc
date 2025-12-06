# iCCC Dashboard

Real-time monitoring dashboard for the iCCC multi-agent orchestration system.

## Features

- 📊 **Live Event Stream**: Real-time WebSocket updates
- 🧠 **AI Summaries**: Haiku-powered event summaries
- 📈 **Statistics**: Task completion, agent activity
- 🤖 **Agent Monitoring**: Track agent status
- 🎨 **Modern UI**: Clean, dark-themed interface

## Tech Stack

- **Vue 3**: Composition API
- **Vite**: Fast build tool
- **WebSocket**: Real-time communication
- **Litestar**: Backend API server

## Setup

### Install Dependencies

```bash
cd dashboard
npm install
```

### Start Development Server

```bash
npm run dev
```

The dashboard will be available at http://localhost:5173

### Build for Production

```bash
npm run build
```

## Backend Requirements

The dashboard requires the observability API server to be running:

```bash
# Start infrastructure
docker compose up -d mongodb redis

# Start API server
cd ..
uv run python -m iccc.observability.server
```

The API server runs on http://localhost:8000

## Architecture

```
┌─────────────────┐
│  Vue Dashboard  │ (http://localhost:5173)
│   (Frontend)    │
└────────┬────────┘
         │ WebSocket /ws
         │ REST /api/*
         ▼
┌─────────────────┐
│ Litestar Server │ (http://localhost:8000)
│   (Backend)     │
└────────┬────────┘
         │
    ┌────┴────┬───────────┐
    ▼         ▼           ▼
┌────────┐ ┌──────┐ ┌─────────┐
│ SQLite │ │Redis │ │ MongoDB │
│ Events │ │ Locks│ │  Tasks  │
└────────┘ └──────┘ └─────────┘
```

## API Endpoints

- `GET /`: API info
- `GET /health`: Health check
- `GET /events?limit=100`: Get recent events
- `GET /events/session/{id}`: Get session events
- `GET /stats`: Get statistics
- `WS /ws`: WebSocket event stream

## WebSocket Protocol

### Connect

```javascript
const ws = new WebSocket('ws://localhost:8000/ws')
```

### Messages

**Connection Confirmation**:
```json
{
  "type": "connected",
  "message": "Connected to iCCC event stream",
  "timestamp": "2025-12-05T14:30:00.000Z"
}
```

**Event Batch**:
```json
{
  "type": "events_batch",
  "count": 10,
  "summary": "AI-generated summary of recent activity",
  "events": [
    {
      "id": "uuid",
      "event_type": "PreToolUse",
      "timestamp": "2025-12-05T14:30:00.000Z",
      "data": {
        "agent_id": "agent-001",
        "task_id": "uuid",
        "tool_name": "Read"
      }
    }
  ]
}
```

## Environment Variables

The dashboard uses the following proxy configuration:

- API Proxy: `/api/*` → `http://localhost:8000/*`

You can customize this in `vite.config.js`.

## Development

### File Structure

```
dashboard/
├── src/
│   ├── App.vue              # Main component
│   ├── main.js              # Entry point
│   ├── components/
│   │   └── EventStream.vue  # Event stream component
│   └── services/
│       └── api.js           # API client (optional)
├── index.html               # HTML template
├── vite.config.js           # Vite configuration
└── package.json             # Dependencies
```

### Adding New Components

Create components in `src/components/` and import them in `App.vue`:

```vue
<script>
import MyComponent from './components/MyComponent.vue'

export default {
  components: {
    MyComponent
  }
}
</script>
```

## Troubleshooting

### WebSocket Connection Failed

Ensure the API server is running:
```bash
uv run python -m iccc.observability.server
```

### CORS Errors

The API server is configured to allow `http://localhost:5173`. If you change the dev server port, update `server.py`:

```python
cors_config = CORSConfig(
    allow_origins=["http://localhost:YOUR_PORT"],
    ...
)
```

### No Events Showing

1. Check if agents are running
2. Verify events are being collected
3. Check browser console for errors

## Performance

- Events are batched for efficiency (100 events per batch)
- WebSocket updates are real-time
- Event list is capped at 100 most recent events
- AI summaries are generated in background

## Future Enhancements

- [ ] Agent detail views
- [ ] Task timeline visualization
- [ ] Performance charts
- [ ] Alert notifications
- [ ] Export event logs
- [ ] Filter and search events
