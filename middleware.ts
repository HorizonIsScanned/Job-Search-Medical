import { NextRequest, NextResponse } from 'next/server';

// Password protection via HTTP Basic Auth. Set BOARD_PASSWORD in Vercel.
// Any user name works; only the password is checked.
export function middleware(req: NextRequest) {
  const password = process.env.BOARD_PASSWORD;
  if (!password) {
    return new NextResponse('BOARD_PASSWORD is not set', { status: 503 });
  }
  const auth = req.headers.get('authorization') ?? '';
  const [scheme, encoded] = auth.split(' ');
  if (scheme === 'Basic' && encoded) {
    const decoded = atob(encoded);
    const given = decoded.slice(decoded.indexOf(':') + 1);
    if (given.length === password.length && timingSafeEqual(given, password)) {
      return NextResponse.next();
    }
  }
  return new NextResponse('Passwort erforderlich', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Jobboard", charset="UTF-8"' },
  });
}

function timingSafeEqual(a: string, b: string) {
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export const config = { matcher: '/((?!_next/static|favicon.ico).*)' };
