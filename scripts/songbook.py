#!python3

import os
import re
import subprocess
import time

# perl ~/src/tools/chordpro/script/chordpro --config Disney/config.json --filelist songs.txt --output

# Where chordpro is in your system (if in doubt run `which chordpro`)
CHORDPRO = "/Users/dfelinto/src/tools/chordpro/script/chordpro"

TITLE = "Ukulella"
SUBTITLE = "Disney Ukulele Songs"

# Songs folder relative to the repository root
SONGS = ["Disney/songs_EN/", "Disney/songs_ptBR"]
TARGETS = [
    {
        "description": "Ukulele on iPad Mini",
        "config": "Disney/config.json",
        "output": "Disney.pdf",
    },
    {
        "description": "Ukulele on the Web",
        "config": "Disney/config.json",
        "output": "Disney.html",
    },
]


def get_filepath_from_root(relative_path):
    return os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", relative_path)
        )


def get_output(filename):
    timestr = time.strftime("%Y-%m-%d")
    output = get_filepath_from_root(filename)
    return "{0}_{2}.{1}".format(*output.rsplit('.', 1) + [timestr])


def get_all_files():
    files = []

    for songs in SONGS:
        songs_dir = get_filepath_from_root(songs)

        for (dirpath, dirnames, filenames) in os.walk(songs_dir):
            for filename in filenames:
                if not filename.endswith(".cho"):
                    continue
                filepath = os.path.join(dirpath, filename)
                files.append(filepath)
    return files


_TITLE_RE = re.compile(r'^\{title:\s*(.*?)\}\s*$', re.IGNORECASE)
_SORTTITLE_RE = re.compile(r'^\{sorttitle:\s*(.*?)\}\s*$', re.IGNORECASE)
_META_RE = re.compile(r'^\{meta:\s*([^\s:]+):?\s*(.*?)\}\s*$', re.IGNORECASE)
_FIRST_NOTE_RE = re.compile(r'^\[<hidden>.*?</hidden>\]', re.IGNORECASE)


def sort_files(files):
    """Sort the files based on a better grouping than alphabetical only.
     
    Sorting criteria:
      * movie meta-data
      * sorttitle 
      * language (if title_ptBR it should go after all the other songs)
      """

    def _read_song_metadata(filepath):
        """Pull title, sorttitle, movie and title_ptBR out of a chordpro file."""
        info = {'title': '', 'sorttitle': '', 'movie': '', 'title_ptbr': ''}

        try:
            with open(filepath, encoding='utf-8') as fh:
                lines = fh.readlines()
        except OSError:
            return info

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith('#') or not line.startswith('{'):
                continue

            m = _TITLE_RE.match(line)
            if m:
                info['title'] = m.group(1).strip()
                continue

            m = _SORTTITLE_RE.match(line)
            if m:
                info['sorttitle'] = m.group(1).strip()
                continue

            m = _META_RE.match(line)
            if m:
                key = m.group(1).strip().lower()
                value = m.group(2).strip()
                if key == 'movie':
                    info['movie'] = value
                elif key == 'title_ptbr':
                    info['title_ptbr'] = value
                continue

            # The First Note mark when the song begins and the meta-data is over.
            m = _FIRST_NOTE_RE.match(line)
            if m:
                break

        return info

    def sort_key(filepath):
        info = _read_song_metadata(filepath)
        has_ptbr = 1 if info['title_ptbr'] else 0
        movie = info['movie'].casefold()
        title_for_sort = (info['sorttitle'] or info['title']).casefold()
        title = info['title'].casefold()
        return (has_ptbr, movie, title_for_sort, title, filepath)

    return sorted(files, key=sort_key)


def main():
    files = get_all_files()
    files = sort_files(files)

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as tmp:
        tmp.write("\n".join(files))
        tmp.flush()

        for target in TARGETS:
            config = get_filepath_from_root(target["config"])
            output = get_output(target["output"])

            try:
                result = subprocess.run(
                    ["perl", CHORDPRO,
                    "--config", config,
                    "--filelist", tmp.name,
                    "--output", output])

                if result.returncode == 0:
                    print("Created: {} ({})".format(output, target["description"]))
                else:
                    print("Error: Problem creating {} ({})".format(output, target["description"]))

            except subprocess.CalledProcessError as e:
                print("Error: Problem creating {} ({})".format(output, target["description"]))


if __name__ == "__main__":
    main()
