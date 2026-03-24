/**
 * Test script for the drive time estimation module.
 * Run with: npx tsx test-drive-time.ts
 */

import { getDriveTime } from './lib/driveTime'
import { getAllAirports } from './lib/data/airports'

// Load .env file
import { readFileSync } from 'fs'
import { resolve } from 'path'

// Simple .env loader (no extra dependency needed)
try {
  const envPath = resolve(__dirname, '.env')
  const envContent = readFileSync(envPath, 'utf-8')
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eqIndex = trimmed.indexOf('=')
    if (eqIndex === -1) continue
    const key = trimmed.slice(0, eqIndex).trim()
    const value = trimmed.slice(eqIndex + 1).trim()
    if (!process.env[key]) {
      process.env[key] = value
    }
  }
} catch {
  // .env file might not exist in CI
}

async function main() {
  console.log('=== GateTime Drive Time Module Test ===\n')

  // Show available airports
  const airports = getAllAirports()
  console.log(`Loaded ${airports.length} airports:`)
  for (const a of airports) {
    console.log(`  ${a.code} — ${a.name}`)
  }
  console.log()

  // Test 1: Basic drive time (no departure time)
  console.log('--- Test 1: Boston to BOS (no departure time) ---')
  try {
    const result = await getDriveTime('123 Main St, Boston, MA', 'BOS')
    console.log(JSON.stringify(result, null, 2))
  } catch (err) {
    console.error('Error:', (err as Error).message)
  }
  console.log()

  // Test 2: Drive time with specific departure time
  console.log('--- Test 2: Manhattan to JFK (with departure time) ---')
  try {
    const result = await getDriveTime(
      '350 Fifth Avenue, New York, NY 10118',
      'JFK',
      '2026-03-25T08:00:00Z',
    )
    console.log(JSON.stringify(result, null, 2))
  } catch (err) {
    console.error('Error:', (err as Error).message)
  }
  console.log()

  // Test 3: Invalid airport code
  console.log('--- Test 3: Invalid airport code ---')
  try {
    await getDriveTime('123 Main St, Boston, MA', 'XYZ')
    console.log('ERROR: Should have thrown')
  } catch (err) {
    console.log('Correctly threw:', (err as Error).message)
  }
  console.log()

  console.log('=== Tests complete ===')
}

main()
