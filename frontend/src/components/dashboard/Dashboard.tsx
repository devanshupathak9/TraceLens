import { useEffect, useState } from 'react'
import { getDashboardStats } from '@/api/dashboard'
import { Banner } from '@/components/ui/Banner'
import { Spinner } from '@/components/ui/Spinner'
import { MenuIcon } from '@/components/ui/Icons'
import type { DashboardStats } from '@/types'

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
