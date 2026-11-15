// Download/upload the board state to the private Vercel Blob store.
// Usage: node scripts/blob.mjs get|put [file]   (needs BLOB_READ_WRITE_TOKEN)
import { get, put } from '@vercel/blob';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';

const [cmd, file = 'data/state.json'] = process.argv.slice(2);
const PATHNAME = 'board/state.json';

if (!process.env.BLOB_READ_WRITE_TOKEN) {
  console.log('BLOB_READ_WRITE_TOKEN not set: test run without stored state');
  if (cmd === 'get') {
    await mkdir(dirname(file), { recursive: true });
    await writeFile(file, '');
  }
  process.exit(0);
}

if (cmd === 'get') {
  await mkdir(dirname(file), { recursive: true });
  const res = await get(PATHNAME, { access: 'private', useCache: false });
  if (!res) {
    console.log('no state yet, starting empty');
    await writeFile(file, '');
  } else {
    const text = await new Response(res.stream).text();
    await writeFile(file, text);
    console.log(`state downloaded (${text.length} bytes)`);
  }
} else if (cmd === 'put') {
  const body = await readFile(file);
  // Keep a dated copy as backup, then overwrite the current state.
  const day = new Date().toISOString().slice(0, 10);
  await put(`board/history/${day}.json`, body, { access: 'private', allowOverwrite: true, contentType: 'application/json' });
  await put(PATHNAME, body, { access: 'private', allowOverwrite: true, addRandomSuffix: false, contentType: 'application/json' });
  console.log(`state uploaded (${body.length} bytes)`);
} else {
  console.error('usage: blob.mjs get|put [file]');
  process.exit(2);
}
