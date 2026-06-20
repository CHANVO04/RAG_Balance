import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import ts from 'typescript'

async function importSegments() {
  const sourcePath = resolve('src/lib/messageSegments.ts')
  const source = await readFile(sourcePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText

  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`)
}

const api = await importSegments()

assert.deepEqual(
  api.mergeAdjacentTextSegments([
    { type: 'text', content: 'D' },
    { type: 'text', content: 'ư' },
    { type: 'text', content: 'ới đây là ' },
    { type: 'cite', content: 'abc1' },
    { type: 'text', content: ' nội dung.' },
  ]),
  [
    { type: 'text', content: 'Dưới đây là ' },
    { type: 'cite', content: 'abc1' },
    { type: 'text', content: ' nội dung.' },
  ],
)

assert.deepEqual(
  api.appendMergedSegments(
    [{ type: 'text', content: 'Hello' }],
    [{ type: 'text', content: ' world' }],
  ),
  [{ type: 'text', content: 'Hello world' }],
)

console.log('message segment merge checks passed')
