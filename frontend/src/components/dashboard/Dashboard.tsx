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
const percentFormat = new Intl.NumberFormat(undefined, {
  style: 'percent',
  maximumFractionDigits: 1,
})

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
              {/* The headline for an observability view: everything else is
                  volume, this is health. Shows a dash rather than 0% or NaN
                  before any call has been recorded. */}
              <StatTile
                label="Success rate"
                value={stats.total_calls === 0 ? '—' : percentFormat.format(stats.success_calls / stats.total_calls)}
                meter={stats.total_calls === 0 ? null : stats.success_calls / stats.total_calls}
              />
              <StatTile label="LLM calls" value={numberFormat.format(stats.total_calls)} />
              <StatTile label="Avg latency" value={numberFormat.format(stats.avg_latency_ms)} unit="ms" />
              <StatTile label="Succeeded" value={numberFormat.format(stats.success_calls)} swatch="ok" />
              <StatTile label="Failed" value={numberFormat.format(stats.failed_calls)} swatch="fail" />
              <StatTile label="Input tokens" value={numberFormat.format(stats.total_prompt_tokens)} />
              <StatTile label="Output tokens" value={numberFormat.format(stats.total_completion_tokens)} />
              <StatTile label="Total tokens" value={numberFormat.format(stats.total_tokens)} />
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

      {/* The peak gives the bars a scale — without it the tallest column could
          be three calls or three hundred. One hairline rather than a grid: the
          exact numbers live in the tooltip and the table below. */}
      <div className="chart-plot">
        <div className="chart-peak" aria-hidden="true">
          <span className="chart-peak-label">{numberFormat.format(peak)}</span>
        </div>

        <div className="chart" role="img" aria-label={`Calls per hour over the last ${HOURS} hours`}>
          {buckets.map((bucket, index) => {
            const failedHeight = (bucket.failed / peak) * 100
            const okHeight = ((bucket.calls - bucket.failed) / peak) * 100
            // The tooltip is anchored to its column, so the first and last few
            // would overflow the plot if they stayed centred.
            const edge = index < 3 ? ' chart-col-start' : index > HOURS - 4 ? ' chart-col-end' : ''
            return (
              <div
                key={bucket.at}
                className={(bucket.calls === 0 ? 'chart-col chart-col-empty' : 'chart-col') + edge}
              >
                <span className="chart-tip" aria-hidden="true">
                  <span className="chart-tip-hour">{hourTitle.format(bucket.at)}</span>
                  <span className="chart-tip-row">
                    <span className="chart-swatch chart-swatch-ok" />
                    {bucket.calls - bucket.failed} succeeded
                  </span>
                  <span className="chart-tip-row">
                    <span className="chart-swatch chart-swatch-fail" />
                    {bucket.failed} failed
                  </span>
                </span>

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

interface StatTileProps {
  label: string
  value: string
  unit?: string
  /** 0–1: draws a meter under the value. `null` renders the track empty. */
  meter?: number | null
  /** Ties the tile to a chart series. The label always says which, so this
      is a second channel rather than colour carrying the meaning alone. */
  swatch?: 'ok' | 'fail'
}

function StatTile({ label, value, unit, meter, swatch }: StatTileProps) {
  return (
    <div className="stat-tile">
      <span className="stat-label">
        {swatch && <span className={`stat-swatch chart-swatch-${swatch}`} aria-hidden="true" />}
        {label}
      </span>
      <span className="stat-value">
        {value}
        {unit && <span className="stat-unit"> {unit}</span>}
      </span>
      {meter !== undefined && (
        <span className="stat-meter" aria-hidden="true">
          <span className="stat-meter-fill" style={{ width: `${(meter ?? 0) * 100}%` }} />
        </span>
      )}
    </div>
  )
}
