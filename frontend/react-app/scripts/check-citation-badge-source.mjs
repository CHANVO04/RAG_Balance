import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const sourcePath = resolve('src/components/chat/CitationBadge.tsx')
const source = await readFile(sourcePath, 'utf8')

assert.match(
  source,
  /CitationBadge\(\{\s*sourceId,\s*source\s*\}/,
  'CitationBadge should accept the message-owned SourceInfo object, not only a global source id.',
)

assert.doesNotMatch(
  source,
  /useStore\(s\s*=>\s*s\.sources\)/,
  'CitationBadge should not depend on global sources because old messages keep their own citations.',
)

console.log('CitationBadge source ownership checks passed')
