import { Check } from 'lucide-react'

export const t = {
  bg: 'var(--c-bg)',
  panel: 'var(--c-panel)',
  panel2: 'var(--c-panel2)',
  panel3: 'var(--c-panel3)',
  border: 'var(--c-border)',
  borderHover: 'var(--c-border-hover)',
  text: 'var(--c-text)',
  muted: 'var(--c-muted)',
  dim: 'var(--c-dim)',
  accent: 'var(--c-accent)',
  accentDim: 'var(--c-accent-dim)',
  bull: 'var(--c-bull)',
  bullSoft: 'var(--c-bull-soft)',
  bullBorder: 'var(--c-bull-border)',
  bear: 'var(--c-bear)',
  bearSoft: 'var(--c-bear-soft)',
  bearBorder: 'var(--c-bear-border)',
  success: 'var(--c-success)',
  warning: 'var(--c-warning)',
  error: 'var(--c-error)',
  inputBg: 'var(--c-input-bg)',
  mono: 'var(--font-mono)',
  ui: 'var(--font-ui)',
}

const badgeDefs = {
  idle:        { color: t.dim,     bg: 'rgba(100,116,139,0.08)',  label: 'Idle',       dot: t.dim },
  pending:     { color: t.warning, bg: 'rgba(245,158,11,0.08)',   label: 'Pending',    dot: t.warning },
  running:     { color: t.accent,  bg: 'var(--c-accent-dim)',   label: 'Running',    dot: t.accent },
  completed:   { color: t.bull,    bg: 'var(--c-bull-soft)',    label: 'Completed',  dot: t.bull },
  failed:      { color: t.bear,    bg: 'var(--c-bear-soft)',    label: 'Failed',     dot: t.bear },
  complete:    { color: t.bull,    bg: 'var(--c-bull-soft)',    label: 'Complete',   dot: t.bull },
  ready:       { color: t.bull,    bg: 'var(--c-bull-soft)',    label: 'Ready',      dot: t.bull },
  'no report': { color: t.dim,     bg: 'rgba(100,116,139,0.08)', label: 'No Report',  dot: t.dim },
}

export function Eyebrow({ children }) {
  return (
    <span style={{
      fontFamily: t.mono,
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      color: t.muted,
    }}>
      {children}
    </span>
  )
}

export function Badge({ status }) {
  const s = badgeDefs[status] ?? badgeDefs.idle
  return (
    <span
      className={status === 'running' ? 'badge-running' : undefined}
      style={{
        fontFamily: t.mono,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        color: s.color,
        background: s.bg,
        border: `1px solid color-mix(in srgb, ${s.color} 20%, transparent)`,
        borderRadius: 4,
        padding: '2px 8px',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
      }}
    >
      <span style={{
        width: 5,
        height: 5,
        borderRadius: '50%',
        background: s.dot,
        flexShrink: 0,
      }} />
      {s.label}
    </span>
  )
}

export function CardHeader({ eyebrow, badge }) {
  return (
    <div className="card-hdr">
      <span className="card-title">{eyebrow}</span>
      {badge && <Badge status={badge} />}
    </div>
  )
}

export function Btn({ onClick, disabled, loading, children, variant = 'primary', type, style: extra }) {
  const base = {
    fontFamily: t.ui,
    fontWeight: 600,
    fontSize: 13,
    padding: '7px 16px',
    borderRadius: 5,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.4 : 1,
    border: 'none',
    letterSpacing: '0.01em',
  }
  const variants = {
    primary:   { ...base, background: t.panel3, color: t.text, border: `1px solid ${t.borderStrong ?? 'var(--c-border-strong)'}` },
    secondary: { ...base, background: t.panel2, color: t.text, border: `1px solid ${t.border}` },
    ghost:     { ...base, background: 'transparent', color: t.muted, border: `1px solid var(--c-border)` },
  }
  return (
    <button className="btn" onClick={onClick} disabled={disabled} type={type} style={{ ...variants[variant], ...extra }}>
      {loading ? `${children}\u2026` : children}
    </button>
  )
}

const msgColors = {
  error:   { color: t.error,   bg: 'var(--c-error-bg)',   border: 'var(--c-error-border)' },
  warning: { color: t.warning, bg: 'var(--c-warning-bg)', border: 'var(--c-warning-border)' },
  success: { color: t.success, bg: 'var(--c-success-bg)', border: 'var(--c-success-border)' },
  info:    { color: t.accent,  bg: 'var(--c-accent-dim)',  border: 'var(--c-border-strong)' },
}

export function InlineMsg({ type, message, onDismiss }) {
  if (!message) return null
  const c = msgColors[type] ?? msgColors.info
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      padding: '7px 10px',
      borderRadius: 5,
      background: c.bg,
      border: `1px solid ${c.border}`,
      color: c.color,
      fontSize: 12,
      fontFamily: t.mono,
      marginBottom: 10,
    }}>
      <span>{message}</span>
      {onDismiss && (
        <button
          className="btn"
          type="button"
          onClick={onDismiss}
          style={{ background: 'none', border: 'none', color: c.color, cursor: 'pointer', marginLeft: 10, fontWeight: 700, fontSize: 14, lineHeight: 1, padding: 0 }}
        >
          x
        </button>
      )}
    </div>
  )
}

export function WorkflowSteps({ steps, current, completed }) {
  return (
    <div className="wf-steps" style={{ flexShrink: 0 }}>
      {steps.map((label, i) => {
        const stepNum = i + 1
        const isDone = completed[i]
        const isActive = stepNum === current
        const cls = isDone ? 'wf-step is-done' : isActive ? 'wf-step is-active' : 'wf-step'
        return (
          <div key={label} style={{ display: 'flex', alignItems: 'center' }}>
            {i > 0 && <div className={`wf-conn${completed[i - 1] ? ' is-done' : ''}`} />}
            <div className={cls}>
              {isDone
                ? <Check size={12} />
                : <span style={{ fontFamily: t.mono, fontSize: 11, fontWeight: 600 }}>{stepNum}</span>}
              <span>{label}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function SegmentControl({ value, onChange, options }) {
  return (
    <div className="segment-ctrl">
      {options.map(opt => (
        <button
          key={opt}
          type="button"
          className={`segment-opt${value === opt ? ' active' : ''}`}
          onClick={() => onChange(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}
