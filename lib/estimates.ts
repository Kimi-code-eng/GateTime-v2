import type { SegmentEstimate, TerminalEstimate, SegmentType, TimeBucket } from './types'
import { getSeedEstimate, LOUNGE_MINUTES } from './data/seedEstimates'
import { getWalkTime } from './data/walkTimes'
import { getTimeBucket } from './timeBuckets'
import { getRecentReports } from './storage'

function weightedAvg(reports: { waitMinutes: number; reportedAt: string }[]): number {
  let weightSum = 0, valueSum = 0
  const now = Date.now()
  for (const r of reports) {
    const ageMin = (now - new Date(r.reportedAt).getTime()) / 60_000
    const w = Math.max(1, 121 - ageMin)
    weightSum += w
    valueSum  += w * r.waitMinutes
  }
  return Math.round(valueSum / weightSum)
}

export function getSegmentEstimate(
  terminalId: string,
  segment: SegmentType,
  timeBucket?: TimeBucket,
  apiWaitMinutes?: number,
): SegmentEstimate {
  if (segment === 'lounge') {
    return { minutes: LOUNGE_MINUTES, isLive: false, liveCount: 0 }
  }
  const recent = getRecentReports(terminalId, segment, 2)

  // Blend live API data (for security only) with user reports.
  // Treat the API value as a fresh synthetic report so it participates
  // in the same weighted average as crowd-sourced data.
  const sources: { waitMinutes: number; reportedAt: string }[] = [...recent]
  if (segment === 'security' && apiWaitMinutes !== undefined) {
    sources.push({ waitMinutes: apiWaitMinutes, reportedAt: new Date().toISOString() })
  }

  if (sources.length >= 2 || (segment === 'security' && apiWaitMinutes !== undefined)) {
    return { minutes: weightedAvg(sources), isLive: true, liveCount: recent.length }
  }
  const bucket = timeBucket ?? getTimeBucket()
  return { minutes: getSeedEstimate(terminalId, segment as 'check_in' | 'security', bucket), isLive: false, liveCount: 0 }
}

export function getTerminalEstimate(
  terminalId: string,
  gate?: string,
  includeLounge = false,
  timeBucket?: TimeBucket,
  apiSecurityMinutes?: number,
): TerminalEstimate {
  const checkIn  = getSegmentEstimate(terminalId, 'check_in', timeBucket)
  const security = getSegmentEstimate(terminalId, 'security', timeBucket, apiSecurityMinutes)
  const lounge   = getSegmentEstimate(terminalId, 'lounge',   timeBucket)
  const walk     = getWalkTime(terminalId, gate)

  const total = checkIn.minutes + security.minutes + walk + (includeLounge ? lounge.minutes : 0)
  const liveReports = checkIn.liveCount + security.liveCount

  return {
    check_in: checkIn,
    security,
    lounge,
    walk,
    totalMinutes: total,
    hasLiveData: checkIn.isLive || security.isLive,
    totalLiveReports: liveReports,
  }
}
