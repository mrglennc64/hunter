import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const artist = req.nextUrl.searchParams.get('artist') || '';
  const trackTitle = req.nextUrl.searchParams.get('track') || '';
  const isrc = req.nextUrl.searchParams.get('isrc') || '';

  if (!artist && !isrc) {
    return NextResponse.json({ error: 'Provide artist or isrc param' }, { status: 400 });
  }

  try {
    if (isrc) {
      // Look up by ISRC via MusicBrainz
      const url = `https://musicbrainz.org/ws/2/recording?query=isrc:${encodeURIComponent(isrc)}&fmt=json&limit=1`;
      const res = await fetch(url, { headers: { 'User-Agent': 'TrapRoyaltiesPro/1.0 (admin@traproyalties.com)' } });
      const data = await res.json();
      const rec = data.recordings?.[0];
      if (rec) {
        return NextResponse.json({
          isrc,
          title: rec.title,
          artist: rec['artist-credit']?.[0]?.name || '',
        });
      }
      return NextResponse.json({ error: 'ISRC not found in MusicBrainz' }, { status: 404 });
    }

    // Build Deezer query — include track title when available for precision
    const artistPart = artist.split(',')[0].trim(); // use first credited artist for search

    const tryDeezer = async (q: string) => {
      const r = await fetch(`https://api.deezer.com/search?q=${q}&limit=10`);
      return r.json();
    };

    let data = await tryDeezer(
      trackTitle
        ? encodeURIComponent(`artist:"${artistPart}" track:"${trackTitle}"`)
        : encodeURIComponent(`artist:"${artistPart}"`)
    );

    // Deezer returns "Prompt is too long" for complex queries — fall back to plain text search
    if (!data.data || data.data.length === 0) {
      const fallbackQ = trackTitle
        ? encodeURIComponent(`${artistPart} ${trackTitle}`)
        : encodeURIComponent(artistPart);
      data = await tryDeezer(fallbackQ);
    }

    if (!data.data || data.data.length === 0) {
      return NextResponse.json({ error: 'Artist not found' }, { status: 404 });
    }

    // When we have a track title, pick the closest title match
    let bestMatch = data.data[0];
    if (trackTitle) {
      const titleLower = trackTitle.toLowerCase();
      const exact = data.data.find((t: any) => t.title?.toLowerCase().includes(titleLower.split('(')[0].trim()));
      if (exact) bestMatch = exact;
    }

    const trackRes = await fetch(`https://api.deezer.com/track/${bestMatch.id}`);
    const track = await trackRes.json();

    if (!track.isrc) {
      return NextResponse.json({ error: 'No ISRC available for this track' }, { status: 404 });
    }

    return NextResponse.json({
      isrc: track.isrc,
      title: track.title,
      artist: track.artist?.name || bestMatch.artist?.name || artist,
    });
  } catch (err) {
    return NextResponse.json({ error: 'Lookup failed' }, { status: 500 });
  }
}
