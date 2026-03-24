import type { TsaAirportData } from '../app/api/tsa-wait/route'

export type { TsaAirportData }

// Cache per airport code so we don't spam the API on every re-render
const cache = new Map<string, { data: TsaAirportData; expiresAt: number }>()
const CACHE_TTL_MS = 60_000 // 1 minute

export async function fetchTsaWait(airportCode: string): Promise<TsaAirportData | null> {
  const key = airportCode.toUpperCase()
  const cached = cache.get(key)
  if (cached && Date.now() < cached.expiresAt) return cached.data

  try {
    const res = await fetch(`/api/tsa-wait?airport=${key}`)
    if (!res.ok) return null
    const data: TsaAirportData = await res.json()
    cache.set(key, { data, expiresAt: Date.now() + CACHE_TTL_MS })
    return data
  } catch {
    return null
  }
}
