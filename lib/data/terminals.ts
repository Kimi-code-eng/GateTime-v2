import type { Terminal } from '../types'

export const TERMINALS: Terminal[] = [
  { id: 'term-a', code: 'A', name: 'Terminal A', airportCode: 'BOS' },
  { id: 'term-b', code: 'B', name: 'Terminal B', airportCode: 'BOS' },
  { id: 'term-c', code: 'C', name: 'Terminal C', airportCode: 'BOS' },
  { id: 'term-e', code: 'E', name: 'Terminal E', airportCode: 'BOS' },
]

export function getTerminal(code: string) {
  return TERMINALS.find(t => t.code === code)
}

export function getTerminalById(id: string) {
  return TERMINALS.find(t => t.id === id)
}
