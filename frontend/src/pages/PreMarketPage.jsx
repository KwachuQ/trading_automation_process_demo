import { useState, useEffect, useRef } from 'react'
import ManualInputForm from '../components/ManualInputForm'
import ImportantLevels from '../components/ImportantLevels'
import Scenarios from '../components/Scenarios'
import { t, CardHeader, Btn, InlineMsg } from '../components/ui'
import { usePreMarket } from '../context/premarket'
import api from '../api'

function ReportListDropdown({ reportList, activeDate, onSelect, align = 'left' }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const dropdownStyle = {
    position: 'absolute',
    top: '100%',
    marginTop: 4,
    background: t.panel,
    border: `1px solid ${t.border}`,
    borderRadius: 4,
    zIndex: 100,
    minWidth: 140,
    maxHeight: 240,
    overflowY: 'auto',
    ...(align === 'center'
      ? { left: '50%', transform: 'translateX(-50%)' }
      : { left: 0 }),
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <Btn variant="ghost" style={{ fontSize: 11, padding: '3px 10px' }} onClick={() => setOpen(v => !v)}>
        Load report
      </Btn>
      {open && (
        <div style={dropdownStyle}>
          {reportList.length === 0 ? (
            <div style={{ padding: '6px 12px', fontFamily: t.mono, fontSize: 11, color: t.dim }}>
              No reports found
            </div>
          ) : reportList.map(d => (
            <div
              key={d}
              onClick={() => { onSelect(d); setOpen(false) }}
              style={{
                padding: '5px 12px',
                fontFamily: t.mono,
                fontSize: 11,
                color: t.text,
                cursor: 'pointer',
                background: d === activeDate ? 'rgba(255,255,255,0.12)' : 'transparent',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.12)'}
              onMouseLeave={e => e.currentTarget.style.background = d === activeDate ? 'rgba(255,255,255,0.12)' : 'transparent'}
            >
              {d}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function PreMarketPage() {
  const { today, setPipelineStatus } = usePreMarket()
  const [reportStatus, setReportStatus] = useState(null)
  const [step1Done, setStep1Done] = useState(false)
  const [reportKey, setReportKey] = useState(0)
  const reportRef = useRef(null)
  const [ingestionResult, setIngestionResult] = useState(null)
  const [ingestionLoading, setIngestionLoading] = useState(false)
  const [ingestionError, setIngestionError] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportMeta, setReportMeta] = useState(null)
  const [reportError, setReportError] = useState(null)
  const [levelsKey, setLevelsKey] = useState(0)
  const [reportList, setReportList] = useState([])

  useEffect(() => {
    api.get('/report/latest')
      .then(r => setReportStatus(r.data))
      .catch(() => {})
  }, [])

  useEffect(() => {
    api.get('/report/list')
      .then(r => setReportList(r.data))
      .catch(() => {})
  }, [])

  async function runIngestion() {
    setIngestionLoading(true)
    setIngestionError(null)
    setIngestionResult(null)
    try {
      const r = await api.post('/ingestion/run')
      setIngestionResult(r.data)
      setLevelsKey(k => k + 1)
    } catch (err) {
      setIngestionError(err.response?.data?.detail ?? err.message)
    } finally {
      setIngestionLoading(false)
    }
  }

  async function generateReport() {
    setReportLoading(true)
    setReportError(null)
    setReportMeta(null)
    try {
      const r = await api.post('/report/generate')
      setReportMeta(r.data)
      setReportKey(k => k + 1)
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (err) {
      setReportError(err.response?.data?.detail ?? err.message)
    } finally {
      setReportLoading(false)
    }
  }

  const activeReport = reportMeta ?? reportStatus
  const ingestionOk = ingestionResult?.sections.every(s => s.success)
  const ingestionStatus = ingestionLoading ? 'running' : ingestionResult ? (ingestionOk ? 'completed' : 'failed') : ingestionError ? 'failed' : 'idle'
  const buildStatus = reportLoading ? 'running' : reportMeta ? 'completed' : reportError ? 'failed' : 'idle'

  useEffect(() => {
    if (reportMeta || reportStatus) setPipelineStatus('ready')
    else if (ingestionResult || step1Done) setPipelineStatus('idle')
    else setPipelineStatus('pending')
  }, [reportStatus, step1Done, ingestionResult, reportMeta, setPipelineStatus])

  return (
    <div className="pm-page">
      {/* Main grid */}
      <div className="pm-grid">
        {/* Left: Controls */}
        <div className="ctrl-col">
          <div className="card">
            <CardHeader eyebrow="Market Inputs" badge={step1Done ? 'complete' : 'pending'} />
            <ManualInputForm onComplete={() => setStep1Done(true)} />
          </div>

          <div className="card">
            <CardHeader eyebrow="Ingestion" badge={ingestionStatus} />
            <InlineMsg type="error" message={ingestionError} onDismiss={() => setIngestionError(null)} />
            <Btn onClick={runIngestion} disabled={ingestionLoading} loading={ingestionLoading}>
              {ingestionLoading ? 'Running' : 'Run Ingestion'}
            </Btn>
            {ingestionResult && (
              <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {ingestionResult.sections.map(s => (
                  <div key={s.name} className="ing-row">
                    <span className={`ing-dot ${s.success ? 'ok' : 'fail'}`} />
                    <span style={{ color: t.text, textTransform: 'capitalize' }}>
                      {s.name.replace(/_/g, ' ')}
                    </span>
                    {s.error && (
                      <span style={{ fontFamily: t.mono, fontSize: 11, color: t.error, marginLeft: 4 }}>
                        - {s.error}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <CardHeader eyebrow="Report Build" badge={buildStatus} />
            <InlineMsg type="error" message={reportError} onDismiss={() => setReportError(null)} />
            <Btn onClick={generateReport} disabled={reportLoading} loading={reportLoading}>
              {reportLoading ? 'Generating' : 'Generate Report'}
            </Btn>
            {reportMeta && (
              <div style={{ marginTop: 8 }}>
                <InlineMsg type="success" message={`Report generated for ${reportMeta.session_date}`} />
              </div>
            )}
          </div>
        </div>

        {/* Right: Report */}
        <div className="rpt-col" ref={reportRef}>
          <div className="card">
            <CardHeader eyebrow="Report Review" badge={activeReport ? 'ready' : 'no report'} />
            {activeReport ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <span style={{ fontFamily: t.mono, fontSize: 12, color: t.muted }}>
                    {activeReport.session_date}
                  </span>
                  <a
                    href={`/api/report/view/${activeReport.session_date}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ textDecoration: 'none' }}
                  >
                    <Btn variant="ghost" style={{ fontSize: 11, padding: '3px 10px' }}>Open report</Btn>
                  </a>
                  <ReportListDropdown
                    reportList={reportList}
                    activeDate={activeReport.session_date}
                    onSelect={d => { setReportMeta({ session_date: d, file_path: '' }); setReportKey(k => k + 1) }}
                  />
                </div>
                <iframe
                  src={`/api/report/view/${activeReport.session_date}?v=${reportKey}`}
                  title="Pre-Market Report Preview"
                />
              </>
            ) : (
              <div style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 10,
                border: `1px dashed ${t.border}`,
                borderRadius: 4,
                minHeight: 200,
              }}>
                <span style={{ fontFamily: t.mono, fontSize: 12, color: t.dim }}>
                  No report available. Run ingestion and generate to proceed.
                </span>
                <ReportListDropdown
                  reportList={reportList}
                  activeDate={null}
                  onSelect={d => { setReportMeta({ session_date: d, file_path: '' }); setReportKey(k => k + 1) }}
                  align="center"
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Levels strip */}
      <div className="util-strip">
        <div className="card" style={{ padding: '10px 14px' }}>
          <ImportantLevels sessionDate={today} refreshKey={levelsKey} />
        </div>
      </div>

      {/* Scenarios */}
      <div className="util-strip">
        <Scenarios sessionDate={today} />
      </div>
    </div>
  )
}

