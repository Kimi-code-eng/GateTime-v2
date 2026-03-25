'use client'
import { useState } from 'react'
import { Search, Loader2, CheckCircle, AlertCircle } from 'lucide-react'

export default function ScanButton() {
  const [status, setStatus] = useState<'idle' | 'scanning' | 'done' | 'error'>('idle')
  const [output, setOutput] = useState('')

  const triggerScan = async () => {
    setStatus('scanning')
    setOutput('')
    try {
      const res = await fetch('/api/scan', { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setStatus('done')
        setOutput(data.output || 'Scan complete!')
      } else {
        setStatus('error')
        setOutput(data.error || 'Scan failed')
      }
    } catch {
      setStatus('error')
      setOutput('Could not reach scanner. Make sure the local dev server is running.')
    }
  }

  return (
    <div className="bg-white rounded-xl shadow p-6 text-center">
      <h3 className="font-semibold text-lg text-[#1A1A2E] mb-2" style={{ fontFamily: 'Poppins, sans-serif' }}>
        Flight Scanner
      </h3>
      <p className="text-sm text-[#6B7280] mb-4">
        Scan Gmail for flight confirmations and send departure reminders
      </p>

      <button
        onClick={triggerScan}
        disabled={status === 'scanning'}
        className="inline-flex items-center gap-2 px-6 py-3 bg-[#34D399] hover:bg-[#2CC38A] disabled:opacity-50 text-[#0A0F1E] font-bold text-sm rounded-xl transition-colors"
        style={{ fontFamily: 'Poppins, sans-serif' }}
      >
        {status === 'scanning' ? (
          <><Loader2 size={16} className="animate-spin" /> Scanning inbox...</>
        ) : status === 'done' ? (
          <><CheckCircle size={16} /> Scan again</>
        ) : (
          <><Search size={16} /> Scan for flights</>
        )}
      </button>

      {status === 'done' && (
        <div className="mt-4 bg-[#34D399]/10 rounded-lg p-3">
          <p className="text-[#059669] text-xs font-medium">Scan complete! Check inbox for reminders.</p>
          <pre className="text-[10px] text-[#6B7280] mt-2 text-left whitespace-pre-wrap max-h-32 overflow-y-auto">
            {output}
          </pre>
        </div>
      )}
      {status === 'error' && (
        <div className="mt-4 bg-red-50 rounded-lg p-3">
          <div className="flex items-center gap-1.5 justify-center">
            <AlertCircle size={12} className="text-red-500" />
            <p className="text-red-500 text-xs font-medium">{output}</p>
          </div>
        </div>
      )}
    </div>
  )
}
