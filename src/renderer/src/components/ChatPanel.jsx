import React, { useState, useRef, useEffect } from 'react'
import { useChatStore, useSettingsStore, useSceneStore, useUIStore } from '../store'
import { sendChatMessage, buildSceneContext } from '../modules/api'

export default function ChatPanel() {
  const { messages, isLoading, addMessage, setLoading, setError, clearChat } = useChatStore()
  const { aiApiKey, aiModel, aiBaseUrl } = useSettingsStore()
  const { objects, activeJob } = useSceneStore()
  const { toggleSettings } = useUIStore()

  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef(null)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || streaming) return
    if (!aiApiKey) {
      toggleSettings()
      return
    }

    setInput('')
    addMessage({ role: 'user', content: text })
    setStreaming(true)

    // Build conversation with scene context in system message
    const systemPrompt = buildSceneContext(objects, activeJob)
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    const fullMessages = [
      { role: 'system', content: systemPrompt },
      ...history,
      { role: 'user', content: text },
    ]

    // Placeholder for streaming response
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
        // Update last message content in real time
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
              ? { ...m, content: `⚠️ Error: ${e.message}` }
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
      display: 'flex', flexDirection: 'column',
      flexShrink: 0, overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '0 12px',
        height: 42,
        borderBottom: '1px solid var(--gf-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Ghost flame icon */}
          <div style={{
            width: 22, height: 22,
            background: 'linear-gradient(135deg, var(--gf-forge), #ff9a5c)',
            borderRadius: 4,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12,
          }}>👻</div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--gf-text)', lineHeight: 1.2 }}>
              GhostForge AI
            </div>
            <div style={{ fontSize: 10, color: aiApiKey ? 'var(--gf-success)' : 'var(--gf-text-3)' }}>
              {aiApiKey ? aiModel : 'No API key configured'}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {messages.length > 0 && (
            <IconBtn onClick={clearChat} title="Clear chat">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M1 3h10M4 3V2h4v1M9 3l-.5 7H3.5L3 3"/>
              </svg>
            </IconBtn>
          )}
          {!aiApiKey && (
            <IconBtn onClick={toggleSettings} title="Configure API key" highlight>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="6" cy="6" r="2"/><path d="M6 1v1M6 10v1M1 6h1M10 6h1M2.64 2.64l.71.71M8.65 8.65l.71.71M2.64 9.36l.71-.71M8.65 3.35l.71-.71"/>
              </svg>
            </IconBtn>
          )}
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 0' }}>
        {messages.length === 0 ? (
          <WelcomeMessage hasKey={!!aiApiKey} onSettings={toggleSettings} />
        ) : (
          messages.map(msg => (
            <Message key={msg.id} message={msg} />
          ))
        )}
        {/* Typing indicator */}
        {streaming && (
          <div style={{ padding: '4px 12px' }}>
            <TypingDots />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div style={{
        padding: '10px 10px 12px',
        borderTop: '1px solid var(--gf-border)',
        flexShrink: 0,
      }}>
        {/* Scene context badge */}
        {objects.length > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 5,
            marginBottom: 8, padding: '4px 8px',
            background: 'var(--gf-bg-3)', borderRadius: 4,
            border: '1px solid var(--gf-border)',
          }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--gf-forge)', flexShrink: 0 }}/>
            <span style={{ fontSize: 10, color: 'var(--gf-text-3)' }}>
              Scene: {objects.length} object{objects.length !== 1 ? 's' : ''} loaded
            </span>
          </div>
        )}

        <div style={{
          display: 'flex', gap: 6, alignItems: 'flex-end',
          background: 'var(--gf-bg-3)',
          border: `1px solid ${streaming ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
          borderRadius: 'var(--gf-radius)',
          padding: '6px 6px 6px 10px',
          transition: 'border-color 0.15s',
        }}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={aiApiKey ? "Ask GhostForge AI…  (Enter to send, Shift+Enter for newline)" : "Add API key in Settings to enable AI"}
            disabled={!aiApiKey || streaming}
            rows={1}
            style={{
              flex: 1, background: 'transparent', border: 'none',
              color: 'var(--gf-text)', fontSize: 12,
              resize: 'none', outline: 'none',
              fontFamily: 'inherit', lineHeight: 1.5,
              maxHeight: 120, overflow: 'auto',
              userSelect: 'text',
            }}
            onInput={e => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
          />

          {streaming ? (
            <button onClick={handleStop} title="Stop generating" style={{
              width: 28, height: 28, flexShrink: 0,
              background: 'rgba(239,68,68,0.15)',
              border: '1px solid var(--gf-danger)',
              borderRadius: 6, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <div style={{ width: 8, height: 8, background: 'var(--gf-danger)', borderRadius: 1 }}/>
            </button>
          ) : (
            <button onClick={handleSend}
              disabled={!input.trim() || !aiApiKey}
              title="Send (Enter)"
              style={{
                width: 28, height: 28, flexShrink: 0,
                background: input.trim() && aiApiKey ? 'var(--gf-forge)' : 'transparent',
                border: `1px solid ${input.trim() && aiApiKey ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
                borderRadius: 6, cursor: input.trim() && aiApiKey ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.15s',
              }}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"
                   stroke={input.trim() && aiApiKey ? '#fff' : 'var(--gf-text-3)'}
                   strokeWidth="1.5">
                <path d="M1 11 L11 6 L1 1 L1 5 L8 6 L1 7 Z"/>
              </svg>
            </button>
          )}
        </div>
        <div style={{ fontSize: 9, color: 'var(--gf-text-4)', marginTop: 4, textAlign: 'center' }}>
          AI has full scene context · MCP-ready
        </div>
      </div>
    </div>
  )
}

// ─── Message bubble ───────────────────────────────────────────────────────────
function Message({ message }) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  if (isSystem) return null

  return (
    <div style={{
      padding: '4px 12px',
      animation: 'fadeIn 0.2s ease',
    }}>
      {/* Role label */}
      <div style={{
        fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.5px',
        color: isUser ? 'var(--gf-text-3)' : 'var(--gf-forge)',
        marginBottom: 3,
        display: 'flex', alignItems: 'center', gap: 4,
      }}>
        {isUser ? 'You' : '👻 GhostForge AI'}
      </div>

      {/* Content */}
      <div style={{
        fontSize: 12, color: 'var(--gf-text)',
        lineHeight: 1.7,
        background: isUser ? 'var(--gf-bg-2)' : 'transparent',
        border: isUser ? '1px solid var(--gf-border)' : 'none',
        borderRadius: isUser ? 'var(--gf-radius-sm)' : 0,
        padding: isUser ? '8px 10px' : '0',
        userSelect: 'text',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        <FormattedContent content={message.content} />
      </div>
    </div>
  )
}

// Simple markdown-ish formatter
function FormattedContent({ content }) {
  if (!content) return <span style={{ opacity: 0.4 }}>…</span>

  // Split by code blocks
  const parts = content.split(/(```[\s\S]*?```)/g)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('```')) {
          const code = part.replace(/^```\w*\n?/, '').replace(/```$/, '')
          return (
            <pre key={i} style={{
              background: 'var(--gf-bg-base)', border: '1px solid var(--gf-border)',
              borderRadius: 4, padding: '8px 10px', fontSize: 11,
              overflowX: 'auto', margin: '6px 0',
              fontFamily: 'Consolas, Monaco, monospace',
              color: 'var(--gf-ghost)',
            }}>{code}</pre>
          )
        }
        // Bold
        const bold = part.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        return <span key={i} dangerouslySetInnerHTML={{ __html: bold }} />
      })}
    </>
  )
}

// ─── Welcome state ────────────────────────────────────────────────────────────
function WelcomeMessage({ hasKey, onSettings }) {
  const starters = [
    "Help me unwrap the UVs on my model",
    "Generate a rusted metal texture",
    "How do I reduce texture stretching?",
    "What's the best UV workflow for a character?",
    "Generate a 3D model from my reference image",
  ]
  return (
    <div style={{ padding: '20px 12px', animation: 'fadeIn 0.3s ease' }}>
      <div style={{ textAlign: 'center', marginBottom: 20 }}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>👻</div>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--gf-text)', marginBottom: 4 }}>
          GhostForge AI
        </div>
        <div style={{ fontSize: 11, color: 'var(--gf-text-3)', lineHeight: 1.7 }}>
          Your creative partner. I can see your scene,<br/>
          guide your workflow, and work alongside you.
        </div>
      </div>

      {!hasKey ? (
        <div style={{
          background: 'rgba(255,107,43,0.08)', border: '1px solid rgba(255,107,43,0.3)',
          borderRadius: 'var(--gf-radius)', padding: '12px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 12, color: 'var(--gf-text-2)', marginBottom: 8 }}>
            Add your API key to activate AI
          </div>
          <button onClick={onSettings} style={{
            padding: '6px 16px', background: 'var(--gf-forge)',
            border: 'none', borderRadius: 6,
            color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }}>Open Settings</button>
          <div style={{ fontSize: 10, color: 'var(--gf-text-3)', marginTop: 8 }}>
            Works with OpenAI, Anthropic, Ollama, or any OpenAI-compatible API
          </div>
        </div>
      ) : (
        <>
          <div style={{ fontSize: 11, color: 'var(--gf-text-3)', marginBottom: 10, textAlign: 'center' }}>
            Try asking:
          </div>
          {starters.map(s => (
            <StarterChip key={s} text={s} />
          ))}
        </>
      )}
    </div>
  )
}

function StarterChip({ text }) {
  const { addMessage, setLoading } = useChatStore()
  // Clicking a starter populates the input
  return (
    <div
      onClick={() => {
        // Find and focus textarea
        const ta = document.querySelector('textarea')
        if (ta) { ta.value = text; ta.dispatchEvent(new Event('input', { bubbles: true })) }
      }}
      style={{
        padding: '7px 10px', background: 'var(--gf-bg-2)',
        border: '1px solid var(--gf-border)', borderRadius: 'var(--gf-radius-sm)',
        fontSize: 11, color: 'var(--gf-text-2)', cursor: 'pointer',
        marginBottom: 6, transition: 'all 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gf-forge)'; e.currentTarget.style.color = 'var(--gf-text)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--gf-border)'; e.currentTarget.style.color = 'var(--gf-text-2)' }}
    >
      {text}
    </div>
  )
}

function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', height: 20 }}>
      {[0,1,2].map(i => (
        <div key={i} style={{
          width: 5, height: 5, borderRadius: '50%',
          background: 'var(--gf-forge)',
          animation: `pulse 1.2s ease ${i * 0.2}s infinite`,
        }}/>
      ))}
    </div>
  )
}

function IconBtn({ children, onClick, title, highlight }) {
  return (
    <button onClick={onClick} title={title} style={{
      width: 24, height: 24, background: 'transparent',
      border: `1px solid ${highlight ? 'var(--gf-forge)' : 'transparent'}`,
      borderRadius: 4, cursor: 'pointer',
      color: highlight ? 'var(--gf-forge)' : 'var(--gf-text-3)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transition: 'all 0.15s',
    }}
    onMouseEnter={e => { e.currentTarget.style.background = 'var(--gf-bg-3)'; e.currentTarget.style.color = 'var(--gf-text)' }}
    onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = highlight ? 'var(--gf-forge)' : 'var(--gf-text-3)' }}
    >
      {children}
    </button>
  )
}
