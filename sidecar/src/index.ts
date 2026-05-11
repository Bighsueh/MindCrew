import express from 'express'
import { WebSocketServer, WebSocket } from 'ws'
import http from 'http'
import * as Y from 'yjs'
import * as encoding from 'lib0/encoding'
import * as decoding from 'lib0/decoding'
import { canvasRouter } from './canvas-api.js'
import { getOrCreateDoc, getOrCreateDocSync } from './yjs-utils.js'

const PORT = parseInt(process.env.SIDECAR_PORT || '4000', 10)

const app = express()
app.use(express.json({ limit: '10mb' }))

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' })
})

// Ensure doc listener is registered and persistence loaded for HTTP API requests
app.use('/api', async (req, _res, next) => {
  const match = req.path.match(/^\/projects\/([^/]+)/)
  if (match) {
    await getOrCreateDoc(match[1])  // ensures persistence is loaded
    ensureDocListener(match[1])
  }
  next()
}, canvasRouter)

const server = http.createServer(app)

// --- Yjs WebSocket Sync Protocol ---
// Simplified implementation of y-websocket sync protocol

const MSG_SYNC = 0
const MSG_AWARENESS = 1
const SYNC_STEP1 = 0
const SYNC_STEP2 = 1
const SYNC_UPDATE = 2

const wss = new WebSocketServer({ noServer: true })
const docConnections = new Map<string, Set<WebSocket>>()

function getConnections(projectId: string): Set<WebSocket> {
  let conns = docConnections.get(projectId)
  if (!conns) {
    conns = new Set()
    docConnections.set(projectId, conns)
  }
  return conns
}

function send(ws: WebSocket, msg: Uint8Array) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(msg)
  }
}

function sendSyncStep1(doc: Y.Doc, ws: WebSocket) {
  const encoder = encoding.createEncoder()
  encoding.writeVarUint(encoder, MSG_SYNC)
  encoding.writeVarUint(encoder, SYNC_STEP1)
  const sv = Y.encodeStateVector(doc)
  encoding.writeVarUint8Array(encoder, sv)
  send(ws, encoding.toUint8Array(encoder))
}

function sendSyncStep2(doc: Y.Doc, ws: WebSocket, sv: Uint8Array) {
  const encoder = encoding.createEncoder()
  encoding.writeVarUint(encoder, MSG_SYNC)
  encoding.writeVarUint(encoder, SYNC_STEP2)
  const update = Y.encodeStateAsUpdate(doc, sv)
  encoding.writeVarUint8Array(encoder, update)
  send(ws, encoding.toUint8Array(encoder))
}

function broadcastUpdate(projectId: string, update: Uint8Array, origin: WebSocket | null) {
  const encoder = encoding.createEncoder()
  encoding.writeVarUint(encoder, MSG_SYNC)
  encoding.writeVarUint(encoder, SYNC_UPDATE)
  encoding.writeVarUint8Array(encoder, update)
  const msg = encoding.toUint8Array(encoder)

  const conns = getConnections(projectId)
  for (const conn of conns) {
    if (conn !== origin) {
      send(conn, msg)
    }
  }
}

function handleSyncMessage(projectId: string, ws: WebSocket, decoder: decoding.Decoder) {
  const doc = getOrCreateDocSync(projectId)
  const syncType = decoding.readVarUint(decoder)

  switch (syncType) {
    case SYNC_STEP1: {
      // Client sends state vector, we respond with missing updates
      const sv = decoding.readVarUint8Array(decoder)
      sendSyncStep2(doc, ws, sv)
      break
    }
    case SYNC_STEP2:
    case SYNC_UPDATE: {
      // Client sends updates, we apply and broadcast
      const update = decoding.readVarUint8Array(decoder)
      Y.applyUpdate(doc, update, ws)
      break
    }
  }
}

// Listen for doc updates (from HTTP API or WS clients) and broadcast
const docListeners = new Set<string>()

function ensureDocListener(projectId: string) {
  if (docListeners.has(projectId)) return
  docListeners.add(projectId)

  const doc = getOrCreateDocSync(projectId)
  doc.on('update', (update: Uint8Array, origin: unknown) => {
    const wsOrigin = origin instanceof WebSocket ? origin : null
    broadcastUpdate(projectId, update, wsOrigin)
  })
}

wss.on('connection', async (ws: WebSocket, projectId: string) => {
  const doc = await getOrCreateDoc(projectId)
  const conns = getConnections(projectId)
  conns.add(ws)
  ensureDocListener(projectId)

  // Initiate sync: send our state vector so client sends us their updates
  sendSyncStep1(doc, ws)

  ws.on('message', (data: Buffer) => {
    try {
      const msg = new Uint8Array(data)
      const decoder = decoding.createDecoder(msg)
      const messageType = decoding.readVarUint(decoder)

      if (messageType === MSG_SYNC) {
        handleSyncMessage(projectId, ws, decoder)
      } else if (messageType === MSG_AWARENESS) {
        // Broadcast awareness to all other clients
        for (const conn of conns) {
          if (conn !== ws) send(conn, msg)
        }
      }
    } catch (err) {
      console.error(`Error handling message for ${projectId}:`, err)
    }
  })

  ws.on('close', () => {
    conns.delete(ws)
  })

  ws.on('error', (err) => {
    console.error(`WS error for ${projectId}:`, err)
    conns.delete(ws)
  })
})

// HTTP upgrade handler: /yjs/:projectId
server.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url || '', `http://localhost:${PORT}`)
  const match = url.pathname.match(/^\/yjs\/(.+)$/)

  if (match) {
    const projectId = match[1]
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit('connection', ws, projectId)
    })
  } else {
    socket.destroy()
  }
})

server.listen(PORT, () => {
  console.log(`Yjs sidecar listening on port ${PORT}`)
  console.log(`  WebSocket: ws://localhost:${PORT}/yjs/:projectId`)
  console.log(`  HTTP API:  http://localhost:${PORT}/api/projects/:id/...`)
})
