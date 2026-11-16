import { get } from '@vercel/blob';
import { readFile } from 'node:fs/promises';

export async function loadJson<T>(pathname: string): Promise<T | null> {
  try {
    if (process.env.LOCAL_DATA) {
      // Local preview only: read sample files instead of the Blob store.
      const text = await readFile(`${process.env.LOCAL_DATA}/${pathname.split('/').pop()}`, 'utf8');
      return JSON.parse(text) as T;
    }
    const res = await get(pathname, { access: 'private' });
    if (!res) return null;
    const text = await new Response(res.stream).text();
    return text ? (JSON.parse(text) as T) : null;
  } catch (e) {
    console.error(`could not load ${pathname}`, e);
    return null;
  }
}

export const berlin = (iso: string, opts: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }) =>
  new Date(iso).toLocaleString('de-DE', { timeZone: 'Europe/Berlin', ...opts });
