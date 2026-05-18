import { describe, it, expect } from 'vitest'
import { parseAuthor } from '../NoteAuthorOverlay'

describe('parseAuthor', () => {
  it('parses string with ai suffix', () => {
    expect(parseAuthor('Alice(ai)')).toEqual({ name: 'Alice', type: 'ai' })
  })

  it('parses string with human suffix', () => {
    expect(parseAuthor('Bob(human)')).toEqual({ name: 'Bob', type: 'human' })
  })

  it('falls back to ai type for plain string', () => {
    expect(parseAuthor('Charlie')).toEqual({ name: 'Charlie', type: 'ai' })
  })

  it('falls back when string is empty', () => {
    expect(parseAuthor('')).toEqual({ name: '?', type: 'ai' })
  })

  it('handles object form with name and type', () => {
    expect(parseAuthor({ name: 'Dave', type: 'human' })).toEqual({
      name: 'Dave',
      type: 'human',
    })
  })

  it('handles object form with name but unknown type defaults to ai', () => {
    expect(parseAuthor({ name: 'Eve', type: 'bogus' })).toEqual({
      name: 'Eve',
      type: 'ai',
    })
  })

  it('returns safe fallback for null', () => {
    expect(parseAuthor(null)).toEqual({ name: '?', type: 'ai' })
  })

  it('returns safe fallback for number', () => {
    expect(parseAuthor(42)).toEqual({ name: '?', type: 'ai' })
  })

  it('returns safe fallback for undefined', () => {
    expect(parseAuthor(undefined)).toEqual({ name: '?', type: 'ai' })
  })
})
