export interface AirportInfo {
  code: string
  name: string
  address: string
}

const airports: Record<string, AirportInfo> = {
  BOS: {
    code: 'BOS',
    name: 'Boston Logan International Airport',
    address: 'Boston Logan International Airport, 1 Harborside Dr, Boston, MA 02128',
  },
  JFK: {
    code: 'JFK',
    name: 'John F. Kennedy International Airport',
    address: 'John F. Kennedy International Airport, Queens, NY 11430',
  },
  LGA: {
    code: 'LGA',
    name: 'LaGuardia Airport',
    address: 'LaGuardia Airport, Queens, NY 11371',
  },
  EWR: {
    code: 'EWR',
    name: 'Newark Liberty International Airport',
    address: 'Newark Liberty International Airport, 3 Brewster Rd, Newark, NJ 07114',
  },
  LAX: {
    code: 'LAX',
    name: 'Los Angeles International Airport',
    address: 'Los Angeles International Airport, 1 World Way, Los Angeles, CA 90045',
  },
  SFO: {
    code: 'SFO',
    name: 'San Francisco International Airport',
    address: 'San Francisco International Airport, San Francisco, CA 94128',
  },
  ORD: {
    code: 'ORD',
    name: "O'Hare International Airport",
    address: "O'Hare International Airport, 10000 W O'Hare Ave, Chicago, IL 60666",
  },
  ATL: {
    code: 'ATL',
    name: 'Hartsfield-Jackson Atlanta International Airport',
    address: 'Hartsfield-Jackson Atlanta International Airport, 6000 N Terminal Pkwy, Atlanta, GA 30320',
  },
  DFW: {
    code: 'DFW',
    name: 'Dallas/Fort Worth International Airport',
    address: 'Dallas/Fort Worth International Airport, 2400 Aviation Dr, DFW Airport, TX 75261',
  },
  DEN: {
    code: 'DEN',
    name: 'Denver International Airport',
    address: 'Denver International Airport, 8500 Peña Blvd, Denver, CO 80249',
  },
  MIA: {
    code: 'MIA',
    name: 'Miami International Airport',
    address: 'Miami International Airport, 2100 NW 42nd Ave, Miami, FL 33126',
  },
  SEA: {
    code: 'SEA',
    name: 'Seattle-Tacoma International Airport',
    address: 'Seattle-Tacoma International Airport, 17801 International Blvd, SeaTac, WA 98158',
  },
}

export function getAirport(code: string): AirportInfo | undefined {
  return airports[code.toUpperCase()]
}

export function getAllAirports(): AirportInfo[] {
  return Object.values(airports)
}
