import { NextRequest, NextResponse } from 'next/server'

export interface TsaCheckpoint {
  checkpointName: string
  waitMinutes: number
  preCheckMinutes: number | null
}

export interface TsaAirportData {
  airportCode: string
  checkpoints: TsaCheckpoint[]
  airportAvgMinutes: number
  airportPreCheckMinutes: number | null
  fetchedAt: string
}

// Normalize the TSAWaitTimes.com JSON response into our internal format.
// The API returns a single object with rightnow (current wait), user_reported,
// precheck (boolean flag), and precheck_checkpoints by terminal.
function normalize(airportCode: string, raw: unknown): TsaAirportData {
  const fetchedAt = new Date().toISOString()
  const data = raw as Record<string, unknown>

  const rightnow = typeof data.rightnow === 'number' ? data.rightnow : 0

  // Build per-terminal checkpoints from precheck_checkpoints if available
  const checkpoints: TsaCheckpoint[] = []
  const precheckCheckpoints = data.precheck_checkpoints as Record<string, Record<string, string>> | undefined
  if (precheckCheckpoints) {
    for (const [terminal, lanes] of Object.entries(precheckCheckpoints)) {
      const terminalName = terminal.replace(/^Terminal\s*/i, 'Terminal ')
      const openLanes = Object.values(lanes).filter(status => status === 'Open').length
      checkpoints.push({
        checkpointName: terminalName,
        waitMinutes: Math.round(rightnow),
        preCheckMinutes: openLanes > 0 ? Math.round(rightnow * 0.4) : null,
      })
    }
  }

  // Fallback: single airport-level entry
  if (checkpoints.length === 0) {
    checkpoints.push({
      checkpointName: 'Main Checkpoint',
      waitMinutes: Math.round(rightnow),
      preCheckMinutes: data.precheck === 1 ? Math.round(rightnow * 0.4) : null,
    })
  }

  return {
    airportCode,
    checkpoints,
    airportAvgMinutes: Math.round(rightnow),
    airportPreCheckMinutes: data.precheck === 1 ? Math.round(rightnow * 0.4) : null,
    fetchedAt,
  }
}

export async function GET(req: NextRequest) {
  const airport = req.nextUrl.searchParams.get('airport')?.toUpperCase()
  if (!airport) {
    return NextResponse.json({ error: 'airport query param required (e.g. ?airport=BOS)' }, { status: 400 })
  }

  // Prefer the direct TSAWaitTimes.com key; fall back to TSA_API_KEY
  const directKey = process.env.TSA_DIRECT_API_KEY
  const rapidKey  = process.env.TSA_API_KEY
  const activeKey = directKey || rapidKey

  if (!activeKey || activeKey === 'your_key_here') {
    return NextResponse.json({ error: 'No TSA API key configured' }, { status: 503 })
  }

  const debug = req.nextUrl.searchParams.get('debug') === '1'

  let raw: unknown
  try {
    // If we have a direct TSAWaitTimes.com key, use their URL directly (key in path).
    // Otherwise fall back to RapidAPI with header auth.
    const url = directKey
      ? `https://www.tsawaittimes.com/api/airport/${directKey}/${airport}/json`
      : `https://tsa-wait-times.p.rapidapi.com/airports/${airport}?APIKEY=${activeKey}`

    const headers: Record<string, string> = directKey
      ? {}
      : { 'x-rapidapi-key': rapidKey!, 'x-rapidapi-host': 'tsa-wait-times.p.rapidapi.com', 'Content-Type': 'application/json' }

    const res = await fetch(url, { headers, next: { revalidate: 60 } })
    if (!res.ok) {
      const body = await res.text()
      return NextResponse.json({ error: `Upstream error ${res.status}`, body }, { status: 502 })
    }
    raw = await res.json()
  } catch (err) {
    return NextResponse.json({ error: 'Failed to reach TSAWaitTimes.com', detail: String(err) }, { status: 502 })
  }

  if (debug) return NextResponse.json({ raw })
  return NextResponse.json(normalize(airport, raw))
}
