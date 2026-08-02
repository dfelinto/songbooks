#!python3

import os
import subprocess

# perl ~/src/tools/chordpro/script/chordpro --config Disney/config.json --filelist songs.txt --output

# Where chordpro is in your system (if in doubt run `which chordpro`)
CHORDPRO = "/Users/dfelinto/src/tools/chordpro/script/chordpro"

TITLE = "Ukulella"
SUBTITLE = "Disney Ukulele Songs"

# Songs folder relative to the repository root
SONGS = ["Disney/songs_EN/", "Disney/songs_ptBR"]
CONFIG = "Disney/config.json"
OUTPUT = "Disney.pdf"


def get_filepath_from_root(relative_path):
    return os.path.join(os.path.dirname(__file__), "..", relative_path)


def get_output():
    filename = OUTPUT
    import time
    timestr = time.strftime("%Y-%m-%d")
    output = get_filepath_from_root(OUTPUT)
    return "{0}_{2}.{1}".format(*filename.rsplit('.', 1) + [timestr])




def get_all_files():
    from os import walk

    files = []

    for songs in SONGS:
        songs_dir = get_filepath_from_root(songs)

        for (dirpath, dirnames, filenames) in walk(songs_dir):
            files.extend(filename for filename in filenames if filename.endswith(".cho"))
    return files


def main():
    files = get_all_files()

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as tmp:
        tmp.write("\n".join(files))

        output_file = get_output()

        subprocess.run(
            ["perl", CHORDPRO,
             "--config", get_filepath_from_root(CONFIG),
             "--filelist", tmp.name,
             "--output", output_file]) 

    print("Created: " + output_file)


if __name__ == "__main__":
    main()
