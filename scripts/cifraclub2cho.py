#!/usr/bin/env python3
"""
cifraclub2cho.py

Download a chord/lyrics page from CifraClub or Ultimate Guitar and convert
it to ChordPro (.cho) format.

    python cifraclub2cho.py <url> [-o output.cho]

Note on copyright: this is a generic scraping/reformatting tool. Chord
charts on these sites are fan transcriptions, and the underlying songs are
usually still copyrighted even when they feel "free" to grab off the web.
Only run this against material you actually have the right to use -- e.g.
genuinely public-domain songs, or your own licensed sheets.

Dependencies:
    pip install requests beautifulsoup4
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Matches a single chord token: C, G#m7, Bb, F#m/A, Asus4, Cdim7, N.C., etc.
CHORD_TOKEN_RE = re.compile(
    r"^\(?[A-G](#|b)?(maj|min|m|dim|aug|sus|add)?\d*(\/[A-G](#|b)?\d*)?\)?$"
)


def fetch_html(url: str) -> str:
    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_metadata(soup: BeautifulSoup) -> dict:
    meta = {"title": None, "artist": None, "key": None, "composer": None, "year": None}

    # There are usually two <h1> tags on a CifraClub song page: the site
    # logo ("Cifra Club") in the header, and the actual song title further
    # down. find("h1") grabs whichever comes first in the DOM, which is
    # often the logo -- so explicitly skip that one.
    for h1 in soup.find_all("h1"):
        candidate = h1.get_text(strip=True)
        if candidate and candidate.lower() != "cifra club":
            meta["title"] = candidate
            break

    h2 = soup.find("h2")
    if h2:
        a = h2.find("a")
        meta["artist"] = a.get_text(strip=True) if a else h2.get_text(strip=True)

    # Fallback: <title>Song - Artist - Cifra Club</title>
    if not meta["title"] or not meta["artist"]:
        title_tag = soup.find("title")
        if title_tag:
            parts = [p.strip() for p in title_tag.get_text().split(" - ")]
            if len(parts) >= 2:
                meta["title"] = meta["title"] or parts[0]
                meta["artist"] = meta["artist"] or parts[1]

    text = soup.get_text("\n")

    # Key is shown near the top as "tom: G" (or "Tom: Gm", etc.)
    m = re.search(r"[Tt]om:\s*([A-G][#b]?m?)", text)
    if m:
        meta["key"] = m.group(1)

    # CifraClub sometimes shows a single, undifferentiated songwriting
    # credit like "Composição de Alan Menken / David Zippel." -- it doesn't
    # separate composer from lyricist, so we surface it as "composer" only.
    m = re.search(r"Composi[cç][aã]o de[:]?\s*([^.\n]+)\.", text)
    if m:
        meta["composer"] = m.group(1).strip()

    # A real release year is essentially never published on these pages;
    # left as None (and therefore omitted) unless a 4-digit year turns up
    # right next to the songwriting credit.
    if meta["composer"]:
        y = re.search(r"\b(19|20)\d{2}\b", text[: text.find(meta["composer"]) + 200])
        if y:
            meta["year"] = y.group(0)

    return meta


def extract_firstline(raw_text: str) -> str:
    """First genuine lyric line: skip blanks, section headers, and chord-only lines."""
    for line in raw_text.split("\n"):
        if not line.strip():
            continue
        if is_section_header(line) or is_chord_line(line):
            continue
        return line.strip()
    return None


def extract_cifra_text(soup: BeautifulSoup) -> str:
    """
    The chords+lyrics live inside a <pre> block on CifraClub pages, with
    chords wrapped in <b> tags. The whitespace text nodes between tags
    already contain the real newlines/indentation used for alignment, so
    we must NOT pass our own separator to get_text() -- doing so double-
    inserts newlines and breaks a chord line away from the lyric line
    directly beneath it.
    """
    pre = soup.find("pre")
    if not pre:
        raise ValueError(
            "Couldn't find the chord/lyrics block (<pre> tag) on this "
            "page. CifraClub may have changed its page layout, or this "
            "isn't a chord-chart page."
        )
    return pre.get_text()


def is_chord_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    tokens = stripped.split()
    return all(CHORD_TOKEN_RE.match(tok) for tok in tokens)


def is_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or is_chord_line(stripped):
        return False
    return bool(re.match(r"^[A-Za-zÀ-ÿ0-9 ]+:$", stripped))


def merge_chord_and_lyric(chord_line: str, lyric_line: str) -> str:
    """
    Insert [Chord] markers into the lyric line at the column position where
    each chord starts. We walk right-to-left so earlier insertions don't
    shift the string offsets of chords that come after them.
    """
    positions = [(m.start(), m.group()) for m in re.finditer(r"\S+", chord_line)]
    if not positions:
        return lyric_line

    max_len = max(p for p, _ in positions)
    if len(lyric_line) < max_len:
        lyric_line = lyric_line + " " * (max_len - len(lyric_line))

    result = lyric_line
    for pos, chord in sorted(positions, key=lambda x: -x[0]):
        result = result[:pos] + f"[{chord}]" + result[pos:]
    return result


def chordify(raw_text: str) -> list:
    lines = raw_text.split("\n")
    out = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        if not line.strip():
            out.append("")
            i += 1
            continue

        if is_section_header(line):
            out.append("{comment: %s}" % line.strip().rstrip(":"))
            i += 1
            continue

        if is_chord_line(line):
            # Normally the lyric is on the very next line. Tolerate a single
            # stray blank line in between (defensive, in case of markup
            # quirks), but don't reach further than that.
            lookahead = i + 1
            if lookahead < n and not lines[lookahead].strip():
                lookahead += 1

            has_lyric_below = (
                lookahead < n
                and lines[lookahead].strip()
                and not is_chord_line(lines[lookahead])
                and not is_section_header(lines[lookahead])
            )
            if has_lyric_below:
                out.append(merge_chord_and_lyric(line, lines[lookahead]))
                i = lookahead + 1
            else:
                # Instrumental / chord-only line
                out.append(" ".join(f"[{tok}]" for tok in line.split()))
                i += 1
            continue

        # Plain lyric line with no chords above it
        out.append(line)
        i += 1

    return out


def to_chordpro(meta: dict, body_lines: list) -> str:
    header = []
    if meta.get("title"):
        header.append(f"{{title: {meta['title']}}}")
    if meta.get("artist"):
        header.append(f"{{artist: {meta['artist']}}}")
    if meta.get("composer"):
        header.append(f"{{composer: {meta['composer']}}}")
    header.append(f"{{year: {meta['year']}}}" if meta.get("year") else "{year: ????}")
    if meta.get("key"):
        header.append(f"{{key: {meta['key']}}}")
    header.append('{define: "First note" base-fret 1 frets x x x x}')
    if meta.get("firstline"):
        header.append(f"{{meta: firstline {meta['firstline']}}}")

    lead_in = ["", "", "[<hidden>First note</hidden>]", ""]

    return "\n".join(header + lead_in + body_lines).rstrip() + "\n"


def convert_cifraclub(html: str) -> tuple:
    soup = BeautifulSoup(html, "html.parser")
    meta = extract_metadata(soup)
    raw_text = extract_cifra_text(soup)
    meta["firstline"] = extract_firstline(raw_text)
    body_lines = chordify(raw_text)
    return meta, to_chordpro(meta, body_lines)


def extract_ug_data(html: str) -> dict:
    """
    Ultimate Guitar renders its tab pages client-side, but the initial
    HTML response still embeds the full song data as JSON inside a
    <div class="js-store" data-content="..."> attribute. BeautifulSoup
    already HTML-unescapes attribute values, so the string is valid JSON
    as-is.
    """
    soup = BeautifulSoup(html, "html.parser")
    store_div = soup.find("div", class_="js-store")
    if not store_div or not store_div.get("data-content"):
        raise ValueError(
            'Couldn\'t find Ultimate Guitar\'s embedded song data (looking '
            'for <div class="js-store">). The site may have changed its '
            "layout, or this isn't a chords/tab page."
        )
    try:
        return json.loads(store_div["data-content"])
    except json.JSONDecodeError as e:
        raise ValueError(f"Couldn't parse Ultimate Guitar's embedded song data: {e}")


def process_ug_content(content: str) -> list:
    """
    Ultimate Guitar already inlines chords into the lyric line using
    [ch]Chord[/ch] markers (no reconstruction needed, unlike CifraClub's
    separate-line layout), and wraps the whole thing in [tab]...[/tab].
    Section markers look like "[Verse 1]" on their own line.
    """
    content = content.replace("[tab]", "").replace("[/tab]", "")
    content = re.sub(r"\[ch\](.*?)\[/ch\]", r"[\1]", content)

    lines = content.split("\n")
    out = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        header_match = re.match(r"^\[([^\[\]]+)\]$", stripped)
        is_lone_bracket_chord = header_match and CHORD_TOKEN_RE.match(header_match.group(1).strip())

        # A section header like "[Verse 1]" -- but not a lone chord hit
        # like "[E]", which looks the same shape but is a real chord.
        if header_match and not is_lone_bracket_chord:
            out.append("{comment: %s}" % header_match.group(1).strip())
            i += 1
            continue

        if is_bracket_chord_line(line):
            # UG sometimes stacks chords on their own line above the lyric
            # (like CifraClub) instead of inlining them into the text.
            # Tolerate a single stray blank line in between, same as the
            # CifraClub parser does.
            lookahead = i + 1
            if lookahead < n and not lines[lookahead].strip():
                lookahead += 1

            next_stripped = lines[lookahead].strip() if lookahead < n else ""
            has_lyric_below = (
                lookahead < n
                and next_stripped
                and not is_bracket_chord_line(lines[lookahead])
                and not re.match(r"^\[([^\[\]]+)\]$", next_stripped)
            )
            if has_lyric_below:
                out.append(merge_bracket_chord_line(line, lines[lookahead]))
                i = lookahead + 1
            else:
                out.append(line)
                i += 1
            continue

        out.append(line)
        i += 1

    return out


def is_bracket_chord_line(line: str) -> bool:
    """True if every token on the line is a bracketed chord, e.g. '[F]  [G]'."""
    stripped = line.strip()
    if not stripped:
        return False
    tokens = stripped.split()
    for tok in tokens:
        m = re.match(r"^\[([^\[\]]+)\]$", tok)
        if not m or not CHORD_TOKEN_RE.match(m.group(1)):
            return False
    return True


def merge_bracket_chord_line(chord_line: str, lyric_line: str) -> str:
    """Same idea as merge_chord_and_lyric, but the tokens are already bracketed."""
    positions = [(m.start(), m.group()) for m in re.finditer(r"\[[^\[\]]+\]", chord_line)]
    if not positions:
        return lyric_line

    max_len = max(p for p, _ in positions)
    if len(lyric_line) < max_len:
        lyric_line = lyric_line + " " * (max_len - len(lyric_line))

    result = lyric_line
    for pos, token in sorted(positions, key=lambda x: -x[0]):
        result = result[:pos] + token + result[pos:]
    return result


def extract_ug_firstline(body_lines: list) -> str:
    for line in body_lines:
        if not line.strip() or line.strip().startswith("{comment:"):
            continue
        plain = re.sub(r"\[[^\[\]]+\]", "", line).strip()
        if plain:
            return plain
    return None


def convert_ultimate_guitar(html: str) -> tuple:
    data = extract_ug_data(html)
    try:
        page_data = data["store"]["page"]["data"]
    except (KeyError, TypeError):
        raise ValueError("Unexpected data shape in Ultimate Guitar's embedded JSON.")

    tab = page_data.get("tab") or {}
    tab_view = page_data.get("tab_view") or {}
    wiki_tab = tab_view.get("wiki_tab") or {}
    tv_meta = tab_view.get("meta") or {}

    meta = {
        "title": tab.get("song_name"),
        "artist": tab.get("artist_name"),
        "key": tv_meta.get("tonality") or None,
        "composer": None,
        "year": None,
    }

    songwriters = tv_meta.get("songwriters")
    if songwriters:
        meta["composer"] = " / ".join(songwriters) if isinstance(songwriters, list) else str(songwriters)

    content = wiki_tab.get("content") or ""
    if not content:
        raise ValueError(
            "This Ultimate Guitar page doesn't seem to have chord/lyric "
            "content (wiki_tab.content was empty)."
        )

    body_lines = process_ug_content(content)
    meta["firstline"] = extract_ug_firstline(body_lines)

    return meta, to_chordpro(meta, body_lines)


def convert(source: str) -> tuple:
    """
    `source` can be a URL (fetched over the network) or a path to an HTML
    file already saved from your browser -- useful when a site's bot
    protection blocks direct requests. Either way, the backend (CifraClub
    vs Ultimate Guitar) is picked by inspecting the page content itself,
    not the URL, so a saved file works the same way a live fetch would.
    """
    local_path = Path(source)
    if local_path.is_file():
        html = local_path.read_text(encoding="utf-8", errors="replace")
    else:
        html = fetch_html(source)

    soup = BeautifulSoup(html, "html.parser")
    if soup.find("div", class_="js-store"):
        return convert_ultimate_guitar(html)
    return convert_cifraclub(html)


def main():
    parser = argparse.ArgumentParser(
        description="Convert a CifraClub or Ultimate Guitar chord page to ChordPro (.cho)"
    )
    parser.add_argument(
        "url",
        help=(
            "CifraClub or Ultimate Guitar song URL, or a path to an HTML "
            "file saved from your browser (useful if the site blocks "
            "direct requests)"
        ),
    )
    parser.add_argument("-o", "--output", help="Output .cho path (default: derived from title)")
    args = parser.parse_args()

    try:
        meta, chordpro = convert(args.url)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        print(f"Error fetching URL: {e}", file=sys.stderr)
        if status == 403:
            print(
                "\nA 403 usually means the site's bot protection blocked "
                "this request rather than anything wrong with the script "
                "itself. Workaround: open the page in your normal browser, "
                "save it (e.g. Cmd/Ctrl+S, 'Webpage, HTML only'), and run "
                "this script again pointing at that saved .html file "
                "instead of the URL.",
                file=sys.stderr,
            )
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing page: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
    else:
        safe_title = re.sub(r"[^\w\-]+", "_", meta.get("title") or "song").strip("_")
        out_path = Path(f"{safe_title}.cho")

    out_path.write_text(chordpro, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
