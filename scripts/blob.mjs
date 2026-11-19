// Download/upload the board state and the run log to the private Vercel Blob store.
// Usage: node scripts/blob.mjs get|put   (needs BLOB_READ_WRITE_TOKEN)
import { get, put } from '@vercel/blob';
import { readFile, writeFile, mkdir, access } from 'node:fs/promises';

const FILES = [
  { local: 'data/state.json', remote: 'board/state.json', backup: true },
  { local: 'data/runs.json', remote: 'board/runs.json', backup: false },
  // Every posting that passed the cheap rules in the last run, with full text, for the laptop's local model.
  { local: 'data/pool.json', remote: 'board/pool.json', backup: false, uploadOnly: true },
];
const cmd = process.argv[2];

await mkdir('data', { recursive: true });

if (!process.env.BLOB_READ_WRITE_TOKEN) {
  console.log('BLOB_READ_WRITE_TOKEN not set: test run without stored state');
  if (cmd === 'get') for (const f of FILES) await writeFile(f.local, '');
  process.exit(0);
}

if (cmd === 'get') {
  for (const f of FILES.filter((x) => !x.uploadOnly)) {
    // A failed read of the state must stop the run, so it is never overwritten with an empty one.
    const res = f.backup
      ? await get(f.remote, { access: 'private', useCache: false })
      : await get(f.remote, { access: 'private', useCache: false }).catch(() => null);
    if (!res) {
      console.log(`${f.remote}: nothing stored yet, starting empty`);
      await writeFile(f.local, '');
      continue;
    }
    const text = await new Response(res.stream).text();
    await writeFile(f.local, text);
    console.log(`${f.remote} downloaded (${text.length} bytes)`);
  }
} else if (cmd === 'put') {
  const day = new Date().toISOString().slice(0, 10);
  for (const f of FILES) {
    try {
      await access(f.local);
    } catch {
      continue;
    }
    const body = await readFile(f.local);
    if (!body.length) continue;
    if (f.backup) {
      await put(`board/history/${day}.json`, body, { access: 'private', allowOverwrite: true, contentType: 'application/json' });
    }
    await put(f.remote, body, { access: 'private', allowOverwrite: true, addRandomSuffix: false, contentType: 'application/json' });
    console.log(`${f.remote} uploaded (${body.length} bytes)`);
  }
} else {
  console.error('usage: blob.mjs get|put');
  process.exit(2);
}
