import React, { useState, useRef, useEffect } from 'react'
import { useChatStore, useSettingsStore, useSceneStore, useUIStore } from '../store'
import { sendChatMessage, buildSceneContext } from '../modules/api'

// ─── Ghost AI icon ────────────────────────────────────────────────────────────
function GhostIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <path d="M4 30 L4 16 C4 8 9 3 16 3 C23 3 28 8 28 16 L28 30 L24 27 L20 30 L16 27 L12 30 L8 27 Z"
            fill="#050D05" stroke="#39FF14" strokeWidth="0.8" opacity="0.9"/>
      <path d="M7 28 L7 17 C7 11 11 6 16 6 C21 6 25 11 25 17 L25 28 L22 26 L16 28 L10 26 Z"
            fill="#010301"/>
      <ellipse cx="12.5" cy="17" rx="2.2" ry="1.6" fill="#39FF14"
        style={{ filter: 'drop-shadow(0 0 3px #39FF14)' }}/>
      <ellipse cx="19.5" cy="17" rx="2.2" ry="1.6" fill="#39FF14"
        style={{ filter: 'drop-shadow(0 0 3px #39FF14)' }}/>
      <ellipse cx="12.5" cy="17" rx="1" ry="0.8" fill="#B8FFB8" opacity="0.8"/>
      <ellipse cx="19.5" cy="17" rx="1" ry="0.8" fill="#B8FFB8" opacity="0.8"/>
    </svg>
  )
}

// ─── Simple markdown formatter ────────────────────────────────────────────────
function FormattedContent({ content }) {
  if (!content) return <span style={{ opacity: 0.3, fontFamily: 'monospace' }}>…</span>

  const parts = content.split(/(```[\s\S]*?```)/g)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('```')) {
          const code = part.replace(/^```\w*\n?/, '').replace(/```$/, '')
          return (
            <pre key={i} style={{
              background: 'var(--gf-bg-base)',
              border: '1px solid var(--gf-border)',
              borderLeft: '2px solid var(--gf-neon-dim)',
              borderRadius: 'var(--gf-radius-sm)',
              padding: '8px 10px',
              fontSize: 10,
              overflowX: 'auto',
              margin: '6px 0',
              fontFamily: "'Courier New', monospace",
              color: 'var(--gf-neon)',
              textShadow: '0 0 4px rgba(57,255,20,0.3)',
              boxShadow: 'inset 0 0 10px rgba(57,255,20,0.03)',
            }}>
              {code}
            </pre>
          )
        }
        const bold = part.replace(/\*\*(.*?)\*\*/g, '<strong style="color:var(--gf-neon-bright)">$1</strong>')
        return <span key={i} dangerouslySetInnerHTML={{ __html: bold }} />
      })}
    </>
  )
}

// ─── Message bubble ───────────────────────────────────────────────────────────
function Message({ message }) {
  const isUser   = message.role === 'user'
  const isSystem = message.role === 'system'
  if (isSystem) return null

  return (
    <div style={{
      padding: '5px 12px',
      animation: 'slideInRight 0.2s ease',
    }}>
      {/* Role header */}
      <div style={{
        fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
        textTransform: 'uppercase', fontFamily: 'monospace',
        color: isUser ? 'var(--gf-text-3)' : 'var(--gf-neon-dim)',
        marginBottom: 4,
        display: 'flex', alignItems: 'center', gap: 5,
      }}>
        {isUser ? (
          <>
            <span style={{ color: 'var(--gf-text-4)' }}>&gt;</span>
            USER_INPUT
          </>
        ) : (
          <>
            <GhostIcon size={12} />
            GHOST_AI
            <span style={{
              fontSize: 8, color: 'var(--gf-text-4)',
              background: 'var(--gf-bg-3)',
              border: '1px solid var(--gf-border)',
              padding: '0 4px', borderRadius: 1,
              fontWeight: 400, letterSpacing: '0.05em',
            }}>MCP-READY</span>
          </>
        )}
      </div>

      {/* Message content */}
      <div style={{
        fontSize: 11,
        color: isUser ? 'var(--gf-text-2)' : 'var(--gf-text)',
        lineHeight: 1.75,
        background: isUser ? 'var(--gf-bg-3)' : 'transparent',
        border: isUser ? '1px solid var(--gf-border)' : 'none',
        borderLeft: isUser ? '2px solid var(--gf-text-3)' : 'none',
        borderRadius: isUser ? '0 var(--gf-radius-sm) var(--gf-radius-sm) var(--gf-radius-sm)' : 0,
        padding: isUser ? '7px 10px' : '0',
        userSelect: 'text',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontFamily: 'monospace',
      }}>
        <FormattedContent content={message.content} />
      </div>
    </div>
  )
}

// ─── Typing dots ──────────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 5, alignItems: 'center', height: 24, paddingLeft: 2 }}>
      <span style={{ fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace', marginRight: 4 }}>
        &gt; computing
      </span>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 5, height: 5, borderRadius: '50%',
          background: 'var(--gf-neon)',
          boxShadow: '0 0 5px var(--gf-neon)',
          animation: `pulse 1.2s ease ${i * 0.22}s infinite`,
        }}/>
      ))}
    </div>
  )
}

// ─── Welcome state ────────────────────────────────────────────────────────────
const STARTERS = [
  "Unwrap the UVs on my selected model",
  "Generate a rusted iron texture",
  "How do I reduce texture stretching?",
  "Best UV workflow for a character?",
  "Generate a 3D model from my reference image",
  "Apply a cyberpunk neon texture",
]

function WelcomeMessage({ hasKey, onSettings }) {
  return (
    <div style={{ padding: '20px 14px', animation: 'fadeIn 0.3s ease' }}>
      {/* Ghost logo */}
      <div style={{ textAlign: 'center', marginBottom: 18 }}>
        <div className="animate-eye-glow" style={{ display: 'inline-block', marginBottom: 10 }}>
          <GhostIcon size={44} />
        </div>
        <div style={{
          fontSize: 13, fontWeight: 700, fontFamily: 'monospace',
          letterSpacing: '0.08em', textTransform: 'uppercase',
          color: 'var(--gf-neon)',
          textShadow: '0 0 10px var(--gf-neon)',
          marginBottom: 4,
        }}>
          GHOST_AI
        </div>
        <div style={{
          fontSize: 9, color: 'var(--gf-text-3)',
          fontFamily: 'monospace', lineHeight: 1.9,
          letterSpacing: '0.06em',
        }}>
          // Full scene awareness — MCP protocol<br/>
          // UV · Texture · Model · Workflow
        </div>
      </div>

      {!hasKey ? (
        <div style={{
          background: 'rgba(57,255,20,0.04)',
          border: '1px solid rgba(57,255,20,0.2)',
          borderRadius: 'var(--gf-radius-sm)',
          padding: '14px 12px', textAlign: 'center',
        }}>
          <div style={{
            fontSize: 10, color: 'var(--gf-text-2)',
            fontFamily: 'monospace', marginBottom: 10,
            letterSpacing: '0.06em',
          }}>
            &gt; NEURAL_LINK: NOT_ESTABLISHED<br/>
            <span style={{ color: 'var(--gf-text-3)', fontSize: 9 }}>
              // Add API key to activate AI
            </span>
          </div>
          <button onClick={onSettings} style={{
            padding: '7px 18px',
            background: 'rgba(57,255,20,0.1)',
            border: '1px solid var(--gf-neon-dim)',
            borderRadius: 'var(--gf-radius-sm)',
            color: 'var(--gf-neon)',
            fontSize: 10, fontWeight: 700,
            fontFamily: 'monospace', letterSpacing: '0.1em',
            cursor: 'pointer', textTransform: 'uppercase',
            textShadow: '0 0 6px var(--gf-neon)',
            boxShadow: '0 0 10px #39FF1420',
            transition: 'all 0.1s',
          }}>
            &gt; CONFIGURE_KEY
          </button>
          <div style={{
            fontSize: 8, color: 'var(--gf-text-4)',
            marginTop: 8, fontFamily: 'monospace',
            letterSpacing: '0.08em',
          }}>
            // OpenAI · Anthropic · Ollama · Custom
          </div>
        </div>
      ) : (
        <>
          <div style={{
            fontSize: 9, color: 'var(--gf-text-3)',
            marginBottom: 8, fontFamily: 'monospace',
            letterSpacing: '0.08em', textAlign: 'center',
          }}>
            // SUGGEST_QUERY:
          </div>
          {STARTERS.map(s => (
            <StarterChip key={s} text={s} />
          ))}
        </>
      )}
    </div>
  )
}

function StarterChip({ text }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      onClick={() => {
        const ta = document.querySelector('textarea[data-ghostforge-input]')
        if (ta) {
          // Update via React controlled input
          const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
          nativeInputValueSetter.call(ta, text)
          ta.dispatchEvent(new Event('input', { bubbles: true }))
          ta.focus()
        }
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        padding: '6px 9px',
        background: hover ? 'rgba(57,255,20,0.06)' : 'var(--gf-bg-2)',
        border: `1px solid ${hover ? 'var(--gf-neon-dim)' : 'var(--gf-border-h)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        fontSize: 10, color: hover ? 'var(--gf-text)' : 'var(--gf-text-2)',
        cursor: 'pointer', marginBottom: 5,
        transition: 'all 0.1s', fontFamily: 'monospace',
        boxShadow: hover ? '0 0 6px #39FF1420' : 'none',
        display: 'flex', alignItems: 'center', gap: 6,
      }}
    >
      <span style={{ color: 'var(--gf-neon-dim)', flexShrink: 0 }}>&gt;</span>
      {text}
    </div>
  )
}

// ─── Icon button ──────────────────────────────────────────────────────────────
function IconBtn({ children, onClick, title, highlight }) {
  const [hover, setHover] = useState(false)
  return (
    <button onClick={onClick} title={title}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: 24, height: 24,
        background: hover ? 'var(--gf-bg-3)' : 'transparent',
        border: `1px solid ${(highlight || hover) ? 'var(--gf-border-h)' : 'transparent'}`,
        borderRadius: 'var(--gf-radius-sm)', cursor: 'pointer',
        color: hover ? 'var(--gf-neon)' : highlight ? 'var(--gf-neon-dim)' : 'var(--gf-text-3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.1s',
        boxShadow: hover ? '0 0 5px #39FF1430' : 'none',
      }}
    >
      {children}
    </button>
  )
}

// ─── Main ChatPanel ───────────────────────────────────────────────────────────
export default function ChatPanel() {
  const { messages, isLoading, addMessage, setLoading, setError, clearChat } = useChatStore()
  const { aiApiKey, aiModel, aiBaseUrl } = useSettingsStore()
  const { objects, activeJob } = useSceneStore()
  const { toggleSettings } = useUIStore()

  const [input, setInput]       = useState('')
  const [streaming, setStreaming] = useState(false)
  const abortRef   = useRef(null)
  const bottomRef  = useRef(null)
  const inputRef   = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streaming])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || streaming) return
    if (!aiApiKey) { toggleSettings(); return }

    setInput('')
    addMessage({ role: 'user', content: text })
    setStreaming(true)

    const systemPrompt = buildSceneContext(objects, activeJob)
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    const fullMessages = [
      { role: 'system', content: systemPrompt },
      ...history,
      { role: 'user', content: text },
    ]

    const assistantId = Date.now()
    addMessage({ id: assistantId, role: 'assistant', content: '' })

    try {
      abortRef.current = new AbortController()
      const stream = await sendChatMessage({
        messages: fullMessages,
        apiKey: aiApiKey,
        model: aiModel,
        baseUrl: aiBaseUrl,
        signal: abortRef.current.signal,
      })

      let full = ''
      for await (const chunk of stream) {
        full += chunk
        useChatStore.setState(s => ({
          messages: s.messages.map(m =>
            m.id === assistantId ? { ...m, content: full } : m
          )
        }))
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        useChatStore.setState(s => ({
          messages: s.messages.map(m =>
            m.id === assistantId
              ? { ...m, content: `[ERR] ${e.message}` }
              : m
          )
        }))
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
    setStreaming(false)
  }

  return (
    <div style={{
      width: 'var(--chat-panel-w)',
      background: 'var(--gf-bg-1)',
      borderLeft: '1px solid var(--gf-border)',
      boxShadow: '-1px 0 0 #39FF1408',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0, overflow: 'hidden',
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: '0 12px',
        height: 42,
        borderBottom: '1px solid var(--gf-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0,
        background: 'var(--gf-bg-1)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Ghost icon with glow */}
          <div className="animate-eye-glow" style={{
            width: 26, height: 26,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <GhostIcon size={22} />
          </div>
          <div>
            <div style={{
              fontSize: 11, fontWeight: 700, fontFamily: 'monospace',
              letterSpacing: '0.08em', textTransform: 'uppercase',
              color: 'var(--gf-neon)',
              textShadow: '0 0 6px var(--gf-neon)',
              lineHeight: 1.2,
            }}>
              GHOST_AI
            </div>
            <div style={{
              fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.06em',
              color: aiApiKey ? 'var(--gf-neon-dim)' : 'var(--gf-text-4)',
              lineHeight: 1,
            }}>
              {aiApiKey ? `// ${aiModel}` : '// NO_API_KEY'}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 3 }}>
          {messages.length > 0 && (
            <IconBtn onClick={clearChat} title="Clear chat">
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4">
                <path d="M1 3h10M4 3V2h4v1M9 3l-.5 7H3.5L3 3"/>
              </svg>
            </IconBtn>
          )}
          {!aiApiKey && (
            <IconBtn onClick={toggleSettings} title="Configure API key" highlight>
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4">
                <circle cx="6" cy="6" r="2"/>
                <path d="M6 1v1M6 10v1M1 6h1M10 6h1M2.64 2.64l.71.71M8.65 8.65l.71.71M2.64 9.36l.71-.71M8.65 3.35l.71-.71"/>
              </svg>
            </IconBtn>
          )}
        </div>
      </div>

      {/* ── Messages ── */}
      <div style={{ flex: 1, overflow: 'auto', padding: '10px 0' }}>
        {messages.length === 0 ? (
          <WelcomeMessage hasKey={!!aiApiKey} onSettings={toggleSettings} />
        ) : (
          messages.map(msg => <Message key={msg.id || Math.random()} message={msg} />)
        )}
        {streaming && (
          <div style={{ padding: '4px 12px' }}>
            <TypingDots />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input area ── */}
      <div style={{
        padding: '10px 10px 12px',
        borderTop: '1px solid var(--gf-border)',
        flexShrink: 0,
        background: 'var(--gf-bg-1)',
      }}>
        {/* Scene context badge */}
        {objects.length > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 5,
            marginBottom: 8, padding: '4px 8px',
            background: 'rgba(57,255,20,0.04)',
            border: '1px solid rgba(57,255,20,0.15)',
            borderRadius: 'var(--gf-radius-sm)',
          }}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%',
              background: 'var(--gf-neon)',
              boxShadow: '0 0 4px var(--gf-neon)',
              flexShrink: 0,
            }}/>
            <span style={{
              fontSize: 9, color: 'var(--gf-neon-dim)',
              fontFamily: 'monospace', letterSpacing: '0.06em',
            }}>
              SCENE: {objects.length} OBJECT{objects.length !== 1 ? 'S' : ''} LOADED
            </span>
          </div>
        )}

        {/* Text input */}
        <div style={{
          display: 'flex', gap: 6, alignItems: 'flex-end',
          background: 'var(--gf-bg-3)',
          border: `1px solid ${streaming ? 'var(--gf-neon-dim)' : 'var(--gf-border-h)'}`,
          borderRadius: 'var(--gf-radius-sm)',
          padding: '6px 6px 6px 10px',
          transition: 'border-color 0.15s',
          boxShadow: streaming ? '0 0 8px #39FF1418' : 'none',
        }}>
          <textarea
            ref={inputRef}
            data-ghostforge-input="true"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              aiApiKey
                ? '> query_ghost_ai…  (Enter=send, Shift+Enter=newline)'
                : '> add_api_key in Settings to activate'
            }
            disabled={!aiApiKey || streaming}
            rows={1}
            style={{
              flex: 1, background: 'transparent', border: 'none',
              color: 'var(--gf-text)', fontSize: 11,
              resize: 'none', outline: 'none',
              fontFamily: "'Courier New', monospace",
              lineHeight: 1.5, maxHeight: 120,
              overflow: 'auto', userSelect: 'text',
            }}
            onInput={e => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
          />

          {streaming ? (
            <button onClick={handleStop} title="Stop" style={{
              width: 28, height: 28, flexShrink: 0,
              background: 'rgba(255,45,85,0.12)',
              border: '1px solid var(--gf-danger)',
              borderRadius: 'var(--gf-radius-sm)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.1s',
            }}>
              <div style={{ width: 8, height: 8, background: 'var(--gf-danger)', borderRadius: 1 }}/>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || !aiApiKey}
              title="Send (Enter)"
              style={{
                width: 28, height: 28, flexShrink: 0,
                background: input.trim() && aiApiKey ? 'rgba(57,255,20,0.15)' : 'transparent',
                border: `1px solid ${input.trim() && aiApiKey ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
                borderRadius: 'var(--gf-radius-sm)',
                cursor: input.trim() && aiApiKey ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.1s',
                boxShadow: input.trim() && aiApiKey ? '0 0 6px #39FF1430' : 'none',
              }}
            >
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none"
                   stroke={input.trim() && aiApiKey ? 'var(--gf-neon)' : 'var(--gf-text-3)'}
                   strokeWidth="1.5"
                   style={{ filter: input.trim() && aiApiKey ? 'drop-shadow(0 0 3px var(--gf-neon))' : 'none' }}>
                <path d="M1 11 L11 6 L1 1 L1 5 L8 6 L1 7 Z"/>
              </svg>
            </button>
          )}
        </div>

        <div style={{
          fontSize: 8, color: 'var(--gf-text-4)',
          marginTop: 5, textAlign: 'center',
          fontFamily: 'monospace', letterSpacing: '0.08em',
        }}>
          // SCENE_CONTEXT: ACTIVE · MCP_PROTOCOL: READY
        </div>
      </div>
    </div>
  )
}
