import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import ts from 'typescript'

async function importStreamBuffer() {
  const sourcePath = resolve('src/lib/streamBuffer.ts')
  const source = await readFile(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText

  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`)
}

function consumeChunks(api, chunks) {
  let state = 'normal'
  let buffer = ''
  let segments = []

  for (const chunk of chunks) {
    const result = api.processToken(chunk, state, buffer)
    state = result.newState
    buffer = result.newBuf
    segments = segments.concat(result.segments)
  }

  return segments.concat(api.flushBuffer(state, buffer))
}

const api = await importStreamBuffer()

const plainChunk = api.processToken('Hello ', 'normal', '')
assert.deepEqual(plainChunk, {
  segments: [{ type: 'text', content: 'Hello ' }],
  newState: 'normal',
  newBuf: '',
})

assert.deepEqual(
  consumeChunks(api, ['Graph fact ', '[KG-', '1', '] is relevant.']),
  [
    { type: 'text', content: 'Graph fact ' },
    { type: 'kg_cite', content: 'KG-01' },
    { type: 'text', content: ' is relevant.' },
  ],
)

assert.deepEqual(
  consumeChunks(api, ['RAG improves grounding [', '1', '] and auditability.']),
  [
    { type: 'text', content: 'RAG improves grounding ' },
    { type: 'cite', content: '1' },
    { type: 'text', content: ' and auditability.' },
  ],
)

assert.deepEqual(
  consumeChunks(api, ['Evidence [12] is available.']),
  [
    { type: 'text', content: 'Evidence ' },
    { type: 'cite', content: '12' },
    { type: 'text', content: ' is available.' },
  ],
)

console.log('streamBuffer streaming and citation checks passed')
