import { getAirport } from './data/airports'

export interface DriveTimeResult {
  origin: string
  destination: string
  destinationFull: string
  durationMinutes: number
  durationInTrafficMinutes: number
  distanceMiles: number
  departureTime: string | null
  retrievedAt: string
}

interface RoutesApiResponse {
  routes?: Array<{
    duration?: string        // e.g. "1500s"
    staticDuration?: string  // e.g. "1200s"
    distanceMeters?: number
    legs?: Array<{
      duration?: string
      staticDuration?: string
      distanceMeters?: number
    }>
  }>
  error?: {
    code: number
    message: string
    status: string
  }
}

function parseSeconds(duration: string | undefined): number {
  if (!duration) return 0
  // Format is like "1500s"
  return parseInt(duration.replace('s', ''), 10) || 0
}

function metersToMiles(meters: number): number {
  return Math.round((meters * 0.000621371) * 10) / 10
}

function secondsToMinutes(seconds: number): number {
  return Math.round(seconds / 60)
}

export async function getDriveTime(
  originAddress: string,
  airportCode: string,
  departureTime?: string,
): Promise<DriveTimeResult> {
  const apiKey = process.env.GOOGLE_ROUTES_API_KEY
  if (!apiKey) {
    throw new Error('GOOGLE_ROUTES_API_KEY is not set. Add it to your .env file.')
  }

  const airport = getAirport(airportCode)
  if (!airport) {
    throw new Error(
      `Unknown airport code: "${airportCode}". Use a supported code like BOS, JFK, LAX, etc.`
    )
  }

  const body: Record<string, unknown> = {
    origin: { address: originAddress },
    destination: { address: airport.address },
    travelMode: 'DRIVE',
    routingPreference: 'TRAFFIC_AWARE',
  }

  if (departureTime) {
    body.departureTime = departureTime
  }

  const fieldMask = [
    'routes.duration',
    'routes.staticDuration',
    'routes.distanceMeters',
    'routes.legs.duration',
    'routes.legs.staticDuration',
    'routes.legs.distanceMeters',
  ].join(',')

  const response = await fetch(
    'https://routes.googleapis.com/directions/v2:computeRoutes',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': apiKey,
        'X-Goog-FieldMask': fieldMask,
      },
      body: JSON.stringify(body),
    },
  )

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(
      `Google Routes API error (${response.status}): ${errorText}`
    )
  }

  const data: RoutesApiResponse = await response.json()

  if (data.error) {
    throw new Error(
      `Google Routes API error (${data.error.code}): ${data.error.message}`
    )
  }

  if (!data.routes || data.routes.length === 0) {
    throw new Error(
      'No routes found. Check that the origin address and airport code are valid.'
    )
  }

  const route = data.routes[0]

  // duration = traffic-aware duration, staticDuration = normal traffic duration
  const trafficSeconds = parseSeconds(route.duration)
  const staticSeconds = parseSeconds(route.staticDuration)
  const distanceMeters = route.distanceMeters ?? 0

  return {
    origin: originAddress,
    destination: airportCode.toUpperCase(),
    destinationFull: `${airport.name}, ${airport.address.split(', ').slice(-2).join(', ')}`,
    durationMinutes: secondsToMinutes(staticSeconds),
    durationInTrafficMinutes: secondsToMinutes(trafficSeconds),
    distanceMiles: metersToMiles(distanceMeters),
    departureTime: departureTime ?? null,
    retrievedAt: new Date().toISOString(),
  }
}
