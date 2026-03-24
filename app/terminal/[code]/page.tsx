'use client'
import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { Plus, Flame, Plane, ChevronDown } from 'lucide-react'
import { getTerminal } from '../../../lib/data/terminals'
import { getAirlinesForTerminal } from '../../../lib/data/airlines'
import { calculateLeaveBy } from '../../../lib/calculator'
import { format } from 'date-fns'
import { getTerminalEstimate } from '../../../lib/estimates'
import { getRecentReports, ensureSeeded, getReporter } from '../../../lib/storage'
import { fetchTsaWait } from '../../../lib/tsaApi'
import { PEAK_TIPS } from '../../../lib/data/seedEstimates'
import SegmentBar from '../../../components/SegmentBar'
import ConfidenceBadge from '../../../components/ConfidenceBadge'
import RecentReports from '../../../components/RecentReports'
import TopNav from '../../../components/TopNav'
import Footer from '../../../components/Footer'
import type { TerminalEstimate, UserReport } from '../../../lib/types'

export default function TerminalPage() {
  const { code } = useParams<{ code: string }>()
  const router = useRouter()
  const terminal = getTerminal(code)

  const [estimate, setEstimate] = useState<TerminalEstimate | null>(null)
  const [reports, setReports]   = useState<UserReport[]>([])
  const [includeLounge, setIncludeLounge] = useState(false)
  const [apiSecurityMinutes, setApiSecurityMinutes] = useState<number | undefined>(undefined)
  const reporter = typeof window !== 'undefined' ? getReporter() : null

  // Inline departure calculator state
  const [calcAirlineId, setCalcAirlineId] = useState('')
  const [calcHour, setCalcHour] = useState('8')
  const [calcMin, setCalcMin] = useState('00')
  const [calcAmpm, setCalcAmpm] = useState<'AM' | 'PM'>('AM')
  const [calcGate, setCalcGate] = useState('')
  const [calcResult, setCalcResult] = useState<ReturnType<typeof calculateLeaveBy>>(null)

  const refresh = useCallback((latestApiMinutes?: number) => {
    if (!terminal) return
    setEstimate(getTerminalEstimate(terminal.id, undefined, includeLounge, undefined, latestApiMinutes))
    setReports(getRecentReports(terminal.id, undefined, 2))
  }, [terminal, includeLounge])

  useEffect(() => {
    ensureSeeded()

    // Fetch real-time TSA data then refresh estimates
    fetchTsaWait(terminal.airportCode ?? 'BOS').then(data => {
      const mins = data?.airportAvgMinutes ?? undefined
      setApiSecurityMinutes(mins)
      refresh(mins)
    })

    refresh(apiSecurityMinutes)
    const id = setInterval(() => {
      fetchTsaWait(terminal.airportCode ?? 'BOS').then(data => {
        const mins = data?.airportAvgMinutes ?? undefined
        setApiSecurityMinutes(mins)
        refresh(mins)
      })
    }, 60_000) // refresh TSA data every 60 s
    return () => clearInterval(id)
  }, [refresh]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!terminal) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F5F6F8]">
        <div className="text-center">
          <p className="text-gray-500 mb-4">Terminal not found</p>
          <Link href="/" className="text-[#34D399] text-sm font-semibold">← Back</Link>
        </div>
      </div>
    )
  }

  const airlines = getAirlinesForTerminal(terminal.id)
  const tip = PEAK_TIPS[terminal.id]
  const totalMins = estimate?.totalMinutes ?? '—'

  return (
    <>
      <TopNav />
      <div className="min-h-screen bg-[#F5F6F8]">
        {/* Breadcrumb */}
        <nav className="max-w-[1200px] mx-auto px-6 lg:px-10 pt-6">
          <div className="flex items-center gap-2 text-sm">
            <Link href="/" className="text-[#003B71] hover:underline">Home</Link>
            <span className="text-[#6B7280]">/</span>
            <span className="text-[#6B7280]">{terminal.name}</span>
          </div>
        </nav>

        {/* Two-column layout */}
        <main className="max-w-[1200px] mx-auto px-6 lg:px-10 py-8">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-8 items-start">

            {/* Left column */}
            <div className="lg:col-span-3">
              {/* Terminal header card */}
              <div className="card p-8">
                <h1 className="num text-2xl font-bold text-[#1A1A2E]">{terminal.name}</h1>
                <p className="text-sm text-[#6B7280] mt-1">
                  {airlines.slice(0, 6).map(a => a.name).join(' · ')}
                  {airlines.length > 6 ? ' ···' : ''}
                </p>

                <div className="mt-6">
                  <span
                    className="num font-bold text-[#1A1A2E] leading-none block"
                    style={{ fontSize: 'clamp(3rem,10vw,5rem)' }}
                  >
                    {totalMins}
                  </span>
                  <span className="text-[#6B7280] text-sm uppercase tracking-wider font-semibold">
                    entrance to gate
                  </span>
                </div>

                {estimate && (
                  <div className="mt-4">
                    <ConfidenceBadge isLive={estimate.hasLiveData} liveCount={estimate.totalLiveReports} />
                  </div>
                )}
              </div>

              {/* Segment breakdown card */}
              {estimate && (
                <div className="card p-6 mt-5">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Breakdown</span>
                    <button
                      onClick={() => setIncludeLounge(v => !v)}
                      className={`text-[11px] font-bold px-3 py-1.5 rounded-full border transition-all ${
                        includeLounge
                          ? 'bg-purple-50 border-purple-300 text-purple-600'
                          : 'bg-gray-50 border-gray-200 text-gray-400 hover:border-gray-300'
                      }`}
                    >
                      + Lounge {estimate.lounge.minutes}m
                    </button>
                  </div>
                  <SegmentBar estimate={estimate} includeLounge={includeLounge} />
                </div>
              )}

              {/* Quick departure calculator card */}
              {terminal && (
                <div className="card p-6 mt-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Plane size={14} className="text-[#0A0F1E]" />
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">When should I arrive?</span>
                  </div>
                  <div className="space-y-2.5">
                    <div className="relative">
                      <select
                        value={calcAirlineId}
                        onChange={e => { setCalcAirlineId(e.target.value); setCalcResult(null) }}
                        className="w-full bg-white border border-gray-200 rounded-xl px-3 py-2 text-sm text-gray-900 appearance-none focus:outline-none focus:border-[#34D399] transition-colors"
                      >
                        <option value="">Select airline…</option>
                        {airlines.map(a => (
                          <option key={a.id} value={a.id}>{a.name}</option>
                        ))}
                      </select>
                      <ChevronDown size={12} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                    </div>
                    <div className="flex gap-2">
                      <div className="flex items-center bg-white border border-gray-200 rounded-xl overflow-hidden flex-1">
                        <select value={calcHour} onChange={e => setCalcHour(e.target.value)}
                          className="bg-transparent px-2 py-2 text-sm text-gray-900 font-mono font-bold appearance-none focus:outline-none focus:border-[#34D399] w-12 text-center">
                          {Array.from({length: 12}, (_, i) => i + 1).map(h => (
                            <option key={h} value={String(h)}>{String(h).padStart(2, '0')}</option>
                          ))}
                        </select>
                        <span className="text-gray-400 font-mono font-bold">:</span>
                        <select value={calcMin} onChange={e => setCalcMin(e.target.value)}
                          className="bg-transparent px-2 py-2 text-sm text-gray-900 font-mono font-bold appearance-none focus:outline-none focus:border-[#34D399] w-12 text-center">
                          {['00','05','10','15','20','25','30','35','40','45','50','55'].map(m => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </div>
                      <button onClick={() => setCalcAmpm(v => v === 'AM' ? 'PM' : 'AM')}
                        className="num bg-white border border-gray-200 rounded-xl px-3 text-sm font-bold text-[#0A0F1E] hover:border-[#34D399] transition-colors">
                        {calcAmpm}
                      </button>
                      <input type="text" value={calcGate} onChange={e => setCalcGate(e.target.value)}
                        placeholder="Gate" maxLength={6}
                        className="w-16 bg-white border border-gray-200 rounded-xl px-2 py-2 text-sm font-mono text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-[#34D399] transition-colors text-center" />
                    </div>
                    <button
                      onClick={() => {
                        if (!calcAirlineId) return
                        const now = new Date()
                        let h = parseInt(calcHour) % 12
                        if (calcAmpm === 'PM') h += 12
                        const flight = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, parseInt(calcMin))
                        if (flight < now) flight.setDate(flight.getDate() + 1)
                        setCalcResult(calculateLeaveBy(flight, calcAirlineId, calcGate || undefined))
                      }}
                      disabled={!calcAirlineId}
                      className="w-full py-2.5 bg-[#34D399] hover:bg-[#2bc48a] disabled:opacity-30 disabled:cursor-not-allowed text-[#0A0F1E] font-bold text-sm rounded-xl transition-colors"
                    >
                      Calculate
                    </button>
                  </div>
                  {calcResult && (
                    <div className="mt-3 pt-3 border-t border-gray-200 animate-slide-up">
                      <p className="text-[10px] text-gray-400 uppercase tracking-widest font-semibold mb-0.5">Arrive at airport by</p>
                      <span className="num text-3xl font-bold text-[#0A0F1E] leading-none">{format(calcResult.arriveBy, 'h:mm a')}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Right column */}
            <div className="lg:col-span-2">
              {/* Report CTA */}
              <button
                onClick={() => router.push(`/report?terminal=${terminal.code}`)}
                className="w-full py-4 bg-[#34D399] hover:bg-[#2bc48a] active:bg-[#22b07a] text-[#0A0F1E] font-bold text-sm rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                <Plus size={16} strokeWidth={3} />
                Report Wait Time
                {reporter && reporter.currentStreak >= 2 && (
                  <span className="flex items-center gap-1 text-xs font-semibold text-[#0A0F1E]/70">
                    <Flame size={12} /> {reporter.currentStreak}-day streak
                  </span>
                )}
              </button>

              {/* Recent reports */}
              <div className="card p-6 mt-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Recent Reports</span>
                  <span className="text-[11px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">Last 2h</span>
                </div>
                <RecentReports reports={reports} />
              </div>

              {/* Tip */}
              {tip && (
                <div className="mt-5 flex items-start gap-3 bg-[#F59E0B]/5 border-l-4 border-l-[#F59E0B] rounded-xl px-5 py-4">
                  <span className="text-[#F59E0B] text-sm mt-0.5 flex-shrink-0">◐</span>
                  <p className="text-[12px] text-gray-700 leading-relaxed font-medium">{tip}</p>
                </div>
              )}
            </div>

          </div>
        </main>
      </div>
      <Footer />
    </>
  )
}
