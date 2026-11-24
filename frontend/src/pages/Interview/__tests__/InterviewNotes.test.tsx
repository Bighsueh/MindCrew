import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it, vi } from 'vitest'
import { NotePreview } from '../InterviewNotes'

vi.mock('../../../services/interviewService', () => ({}))

it('renders Markdown with HTML and remote images disabled', () => {
  const body = '# 我的筆記\n\n**重點**\n\n<script>alert(1)</script>\n\n![remote](https://example.test/tracking.png)'
  const html = renderToStaticMarkup(<NotePreview body={body} />)

  expect(html).toContain('<h1>我的筆記</h1>')
  expect(html).toContain('<strong>重點</strong>')
  expect(html).not.toMatch(/<script|alert\(1\)|<img|tracking\.png/)
})
