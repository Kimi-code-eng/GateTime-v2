'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Clock, MessageSquare, Plane } from 'lucide-react'
import TopNav from '../components/TopNav'
import Footer from '../components/Footer'
import DepartureCalculator from '../components/DepartureCalculator'
import LeaderboardPreview from '../components/LeaderboardPreview'
import GmailConnect from '../components/GmailConnect'
import { getTerminalEstimate } from '../lib/estimates'
import { ensureSeeded } from '../lib/storage'
import { getAirlinesForTerminal } from '../lib/data/airlines'
import { TERMINALS } from '../lib/data/terminals'
import { fetchTsaWait } from '../lib/tsaApi'
import Link from 'next/link'

const TERMINAL_COLORS: Record<string, string> = {
  A: '#3B82F6',
  B: '#EF4444',
  C: '#22C55E',
  E: '#8B5CF6',
}

function TerminalCard({
  terminalCode,
  terminalName,
  airlines,
  accentColor,
}: {
  terminalCode: string
  terminalName: string
  airlines: string[]
  accentColor: string
}) {
  const router = useRouter()
  const [waitMinutes, setWaitMinutes] = useState<number | null>(null)

  useEffect(() => {
    ensureSeeded()
    const terminal = TERMINALS.find(t => t.code === terminalCode)
    if (!terminal) return
    fetchTsaWait(terminal.airportCode ?? 'BOS').then(data => {
      const apiMins = data?.airportAvgMinutes
      const est = getTerminalEstimate(terminal.id, undefined, false, undefined, apiMins)
      setWaitMinutes(est.totalMinutes)
    })
  }, [terminalCode])

  const getStatusColor = (mins: number | null) => {
    if (mins === null) return '#9CA3AF'
    if (mins <= 20) return '#22C55E'
    if (mins <= 40) return '#F59E0B'
    return '#EF4444'
  }

  return (
    <div
      className="bg-white rounded-xl shadow hover:shadow-lg hover:-translate-y-0.5 transition-all cursor-pointer p-6"
      onClick={() => router.push(`/terminal/${terminalCode}`)}
    >
      <div className="num text-3xl font-bold" style={{ color: accentColor }}>
        {terminalCode}
      </div>
      <div className="text-sm font-semibold text-[#1A1A2E] mt-1">{terminalName}</div>
      <div className="text-xs text-[#6B7280] mt-2">{airlines.join(', ')}</div>
      <div className="flex items-center gap-2 mt-3">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ backgroundColor: getStatusColor(waitMinutes) }}
        />
        <span className="num text-2xl font-bold" style={{ color: getStatusColor(waitMinutes) }}>
          {waitMinutes !== null ? `${waitMinutes} min` : '...'}
        </span>
      </div>
      <div className="text-[#003B71] text-xs font-medium mt-3 hover:underline">
        View details &rarr;
      </div>
    </div>
  )
}

export default function Home() {
  return (
    <>
      <TopNav />

      {/* Hero Banner */}
      <section
        className="w-full"
        style={{ background: 'linear-gradient(135deg, #0A0F1E 0%, #1A2340 100%)' }}
      >
        <div className="max-w-[1200px] mx-auto px-6 lg:px-10 py-16 lg:py-20">
          <div className="flex flex-col lg:flex-row items-center gap-10 lg:gap-16">
            {/* Left side */}
            <div className="flex-1 text-center lg:text-left">
              <span className="text-[#C5A255] uppercase tracking-widest text-xs font-bold">
                [BOS]
              </span>
              <h1 className="num text-5xl font-bold text-white mt-3">GateTime</h1>
              <p className="text-white/70 text-lg mt-2">
                Know your wait. Plan your departure.
              </p>
            </div>
            {/* Right side */}
            <div className="flex-1 w-full max-w-md lg:max-w-none">
              <DepartureCalculator />
            </div>
          </div>
        </div>
      </section>

      {/* Current Wait Times */}
      <section className="bg-[#F5F6F8]">
        <div className="max-w-[1200px] mx-auto px-6 lg:px-10 py-12">
          <h2 className="num font-semibold text-2xl text-[#1A1A2E] mb-2">
            Current wait times at Logan
          </h2>
          <p className="text-[#6B7280] text-sm mb-8">
            Real-time estimates from fellow travelers
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {TERMINALS.map(t => (
              <TerminalCard
                key={t.code}
                terminalCode={t.code}
                terminalName={t.name}
                airlines={getAirlinesForTerminal(t.id).map(a => a.name)}
                accentColor={TERMINAL_COLORS[t.code] || '#3B82F6'}
              />
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="bg-white py-16">
        <div className="max-w-[1200px] mx-auto px-6 lg:px-10">
          <h2 className="num font-semibold text-2xl text-[#1A1A2E] mb-10 text-center">
            How GateTime works
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="w-12 h-12 rounded-xl bg-[#0A0F1E]/5 flex items-center justify-center mx-auto mb-4">
                <Clock className="w-5 h-5 text-[#0A0F1E]" />
              </div>
              <div className="font-semibold text-[#1A1A2E] text-base mb-2">Check wait times</div>
              <p className="text-sm text-[#6B7280] leading-relaxed">
                See real-time estimates from fellow travelers before heading to the airport
              </p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 rounded-xl bg-[#0A0F1E]/5 flex items-center justify-center mx-auto mb-4">
                <MessageSquare className="w-5 h-5 text-[#0A0F1E]" />
              </div>
              <div className="font-semibold text-[#1A1A2E] text-base mb-2">Report your experience</div>
              <p className="text-sm text-[#6B7280] leading-relaxed">
                Share your wait times in 15 seconds and earn points on the leaderboard
              </p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 rounded-xl bg-[#0A0F1E]/5 flex items-center justify-center mx-auto mb-4">
                <Plane className="w-5 h-5 text-[#0A0F1E]" />
              </div>
              <div className="font-semibold text-[#1A1A2E] text-base mb-2">Plan your departure</div>
              <p className="text-sm text-[#6B7280] leading-relaxed">
                Enter your flight details and get a personalized arrival time
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Flight Reminders CTA */}
      <section className="bg-white py-16">
        <div className="max-w-[1200px] mx-auto px-6 lg:px-10">
          <GmailConnect />
        </div>
      </section>

      {/* Leaderboard Preview */}
      <section className="bg-[#F5F6F8]">
        <div className="max-w-[1200px] mx-auto px-6 lg:px-10 py-12">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
            <div className="lg:col-span-3">
              <LeaderboardPreview />
            </div>
            <div className="lg:col-span-2">
              <div className="bg-white p-6 rounded-xl shadow text-center">
                <h3 className="num font-semibold text-lg text-[#1A1A2E] mb-3">
                  Join the community
                </h3>
                <p className="text-sm text-[#6B7280] mb-6 leading-relaxed">
                  Start reporting wait times to earn points and climb the leaderboard
                </p>
                <Link
                  href="/report"
                  className="inline-block bg-[#22C55E] hover:bg-[#16A34A] text-white font-semibold text-sm px-6 py-3 rounded-lg transition-colors"
                >
                  Report a wait time
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </>
  )
}
