import { useEffect, useState } from 'react'
import { getDashboardStats } from '@/api/dashboard'
import { Banner } from '@/components/ui/Banner'
import { Spinner } from '@/components/ui/Spinner'
import { MenuIcon } from '@/components/ui/Icons'
import type { DashboardStats, ThroughputPoint } from '@/types'

interface DashboardProps {
  onOpenSidebar: () => void
}

const numberFormat = new Intl.NumberFormat()

export function Dashboard({ onOpenSidebar }: DashboardProps) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getDashboardStats(controller.signal)
      .then(setStats)
      .catch((cause) => {
        if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
          setError(cause instanceof Error ? cause.message : 'Could not load the dashboard.')
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="chat-window">
      <header className="chat-header">
        <button
          type="button"
          className="icon-button chat-menu-button"
          onClick={onOpenSidebar}
          aria-label="Open sidebar"
        >
          <MenuIcon />
        </button>
        <h1 className="chat-title">Dashboard</h1>
      </header>

      {error && <Banner message={error} onDismiss={() => setError(null)} />}

      {!stats && !error && (
        <div className="centered-state">
          <Spinner label="Loading stats" />
        </div>
      )}

      {stats && (
        <div className="dashboard-scroll">
          <div className="dashboard">
            <section className="stat-grid" aria-label="Inference totals">
              <StatTile label="LLM calls" value={numberFormat.format(stats.total_calls)} />
              <StatTile label="Avg latency" value={numberFormat.format(stats.avg_latency_ms)} unit="ms" />
              <StatTile label="Input tokens" value={numberFormat.format(stats.total_prompt_tokens)} />
              <StatTile label="Output tokens" value={numberFormat.format(stats.total_completion_tokens)} />
              <StatTile label="Succeeded" value={numberFormat.format(stats.success_calls)} />
              <StatTile label="Failed" value={numberFormat.format(stats.failed_calls)} />
            </section>

            <section aria-label="Throughput">
              <h2 className="dashboard-section-title">Calls per hour (last 24h)</h2>
              <Throughput points={stats.throughput} />
            </section>

            <section aria-label="Usage by model">
              <h2 className="dashboard-section-title">By model</h2>
              {stats.models.length === 0 ? (
                <p className="dashboard-empty">
                  No LLM calls recorded yet — send a chat message and refresh.
                </p>
              ) : (
                <div className="dashboard-table-wrap">
                  <table className="dashboard-table">
                    <thead>
                      <tr>
                        <th scope="col">Model</th>
                        <th scope="col">Calls</th>
                        <th scope="col">Avg latency</th>
                        <th scope="col">Input tokens</th>
                        <th scope="col">Output tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.models.map((row) => (
                        <tr key={row.model}>
                          <th scope="row">{row.model}</th>
                          <td>{numberFormat.format(row.calls)}</td>
                          <td>{numberFormat.format(row.avg_latency_ms)} ms</td>
                          <td>{numberFormat.format(row.prompt_tokens)}</td>
                          <td>{numberFormat.format(row.completion_tokens)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </main>
  )
}

const HOURS = 24
const hourLabel = new Intl.DateTimeFormat(undefined, { hour: 'numeric' })
const hourTitle = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/**
 * Hourly call volume, succeeded and failed stacked per bucket.
 *
 * The server returns only buckets that had calls, so the 24 slots are filled in
 * here — a gap has to read as "no traffic", not as a narrower chart.
 */
function Throughput({ points }: { points: ThroughputPoint[] }) {
  const byHour = new Map<number, ThroughputPoint>()
  for (const point of points) byHour.set(new Date(point.bucket).setMinutes(0, 0, 0), point)

  const now = new Date().setMinutes(0, 0, 0)
  const buckets = Array.from({ length: HOURS }, (_, index) => {
    const at = now - (HOURS - 1 - index) * 3_600_000
    const point = byHour.get(at)
    return { at, calls: point?.calls ?? 0, failed: point?.failed ?? 0 }
  })

  const peak = Math.max(1, ...buckets.map((bucket) => bucket.calls))

  if (points.length === 0) {
    return <p className="dashboard-empty">No calls in the last 24 hours.</p>
  }

  return (
    <>
      {/* Legend, not colour alone: two series always carry a key. */}
      <p className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-swatch chart-swatch-ok" aria-hidden="true" />
          Succeeded
        </span>
        <span className="chart-legend-item">
          <span className="chart-swatch chart-swatch-fail" aria-hidden="true" />
          Failed
        </span>
      </p>

      <div className="chart" role="img" aria-label={`Calls per hour over the last ${HOURS} hours`}>
        {buckets.map((bucket) => {
          const failedHeight = (bucket.failed / peak) * 100
          const okHeight = ((bucket.calls - bucket.failed) / peak) * 100
          return (
            <div
              key={bucket.at}
              className={bucket.calls === 0 ? 'chart-col chart-col-empty' : 'chart-col'}
              title={`${hourTitle.format(bucket.at)} — ${bucket.calls} call${
                bucket.calls === 1 ? '' : 's'
              }, ${bucket.failed} failed`}
            >
              {bucket.failed > 0 && (
                <div className="chart-seg chart-seg-fail" style={{ height: `${failedHeight}%` }} />
              )}
              {bucket.calls - bucket.failed > 0 && (
                <div className="chart-seg chart-seg-ok" style={{ height: `${okHeight}%` }} />
              )}
            </div>
          )
        })}
      </div>

      {/* Every sixth hour is labelled; the rest are spacers keeping the columns
          aligned, so labels can't collide on a narrow screen. */}
      <div className="chart-axis" aria-hidden="true">
        {buckets.map((bucket, index) => (
          <span key={bucket.at}>{index % 6 === 0 ? hourLabel.format(bucket.at) : ''}</span>
        ))}
      </div>

      {/* The bars are colour and geometry; this is the same data as text, so the
          chart isn't the only way to read it. */}
      <table className="sr-only">
        <caption>Calls per hour, last {HOURS} hours</caption>
        <thead>
          <tr>
            <th scope="col">Hour</th>
            <th scope="col">Calls</th>
            <th scope="col">Failed</th>
          </tr>
        </thead>
        <tbody>
          {buckets
            .filter((bucket) => bucket.calls > 0)
            .map((bucket) => (
              <tr key={bucket.at}>
                <th scope="row">{hourTitle.format(bucket.at)}</th>
                <td>{bucket.calls}</td>
                <td>{bucket.failed}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </>
  )
}

function StatTile({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="stat-tile">
      <span className="stat-label">{label}</span>
      <span className="stat-value">
        {value}
        {unit && <span className="stat-unit"> {unit}</span>}
      </span>
    </div>
  )
}
