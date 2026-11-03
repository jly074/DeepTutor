import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { writeAppTypeDeclarations } from 'next/dist/lib/typescript/writeAppTypeDeclarations'

test('installed Next dev declaration generator preserves the checked-in declaration', async () => {
  const original = await readFile(path.resolve(process.cwd(), 'next-env.d.ts'), 'utf8')
  const directory = await mkdtemp(path.join(tmpdir(), 'next-declaration-'))
  try {
    // Preserve checkout EOL, including on Windows, without mutating the checkout.
    await writeFile(path.join(directory, 'next-env.d.ts'), original)
    await writeAppTypeDeclarations({ baseDir: directory, distDir: '.next/dev',
      imageImportsEnabled: true, hasPagesDir: false, hasAppDir: true,
      strictRouteTypes: false, typedRoutes: false })
    assert.equal(await readFile(path.join(directory, 'next-env.d.ts'), 'utf8'), original)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})
