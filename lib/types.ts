export type SegmentType = 'check_in' | 'security' | 'lounge'
export type TimeBucket = 'early_morning' | 'morning' | 'midday' | 'afternoon' | 'evening'
export type TerminalCode = 'A' | 'B' | 'C' | 'E'

export interface Terminal {
  id: string
  code: TerminalCode
  name: string
  airportCode?: string
}

export interface Airline {
  id: string
  name: string
  code: string
  terminalId: string
  terminalCode: TerminalCode
  isInternational: boolean
  displayOrder: number
}

export interface WalkTime {
  terminalId: string
  gateArea: string
  gatePrefix: string
  walkMinutes: number
}

export interface SeedEstimate {
  terminalId: string
  segment: SegmentType
  dayOfWeek: number   // 0=Sun
  timeBucket: TimeBucket
  avgMinutes: number
}

export interface Reporter {
  id: string
  nickname: string
  totalPoints: number
  totalReports: number
  currentStreak: number
  longestStreak: number
  lastReportDate: string | null  // YYYY-MM-DD
  rankTitle: string
}

export interface UserReport {
  id: string
  terminalId: string
  terminalCode: TerminalCode
  reporterId: string | null
  segment: SegmentType
  waitMinutes: number
  reportedAt: string   // ISO
  airline?: string
  notes?: string
  pointsEarned: number
}

export interface SegmentEstimate {
  minutes: number
  isLive: boolean
  liveCount: number
}

export interface TerminalEstimate {
  check_in: SegmentEstimate
  security: SegmentEstimate
  lounge: SegmentEstimate
  walk: number
  totalMinutes: number
  hasLiveData: boolean
  totalLiveReports: number
}
