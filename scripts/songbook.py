#!python3

import os
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


def main():
    files = get_all_files()

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
