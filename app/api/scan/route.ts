import { NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

export async function POST() {
  const scriptsDir = path.join(process.cwd(), 'scripts')
  const scriptPath = path.join(scriptsDir, 'email_flight_scanner.py')

  // Read ANTHROPIC_API_KEY from scripts/.env directly
  let anthropicKey = process.env.ANTHROPIC_API_KEY || ''
  try {
    const envPath = path.join(scriptsDir, '.env')
    if (fs.existsSync(envPath)) {
      const envContent = fs.readFileSync(envPath, 'utf-8')
      const match = envContent.match(/ANTHROPIC_API_KEY=(.+)/)
      if (match) anthropicKey = match[1].trim()
    }
  } catch { /* ignore */ }

  const env = {
    ...process.env,
    ANTHROPIC_API_KEY: anthropicKey,
  }

  return new Promise((resolve) => {
    exec(
      `py "${scriptPath}"`,
      { cwd: scriptsDir, env, timeout: 120000 },
      (error, stdout, stderr) => {
        if (error) {
          console.error('Scan error:', error.message)
          resolve(NextResponse.json({
            success: false,
            error: 'Scanner failed — only works on local dev server',
            detail: error.message,
          }, { status: 500 }))
        } else {
          resolve(NextResponse.json({
            success: true,
            output: stdout,
          }))
        }
      }
    )
  })
}
