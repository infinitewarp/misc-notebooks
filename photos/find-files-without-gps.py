#!/usr/bin/env python3
import argparse
import glob
import multiprocessing
import os
import subprocess

import tqdm


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Find images that do not have EXIF-embedded GPS coordinates.',
    )
    parser.add_argument('path', nargs='+',
                        help='one or more paths to check recursively for images')
    return parser.parse_args()


def filepath_needs_gps(filepath, exiftool_only=True):
    if not os.path.isfile(filepath):
        return False
    if exiftool_only:
        cmd = ('exiftool', '-XMP:GPSLongitude', '-GPSLongitude', filepath)
        exiftool_out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return len(exiftool_out.stdout) == 0
    else:
        # alternate solution pipes the output into grep:
        # this is less efficient but could be interesting.
        exiftool_out = subprocess.run(('exiftool', filepath), stdout=subprocess.PIPE)
        grep_out = subprocess.run(('grep', '-q', 'GPS'), input=exiftool_out.stdout)
        if grep_out.returncode == 0:
            return False
        return True


def do_scans(paths, use_multiprocessing=True):
    filepaths = paths
    for path in paths:
        filepaths += glob.glob(os.path.join(path, '**/*.*'), recursive=True)
    if use_multiprocessing:
        with multiprocessing.Pool(processes=4) as pool:
            results = [
                (pool.apply_async(filepath_needs_gps, (filepath,)), filepath) for filepath in filepaths
            ]
            filepaths_needs = [
                (filepath, res.get()) for res, filepath in tqdm.tqdm(results)
            ]
    else:
        filepaths_needs = [
            (filepath, filepath_needs_gps(filepath)) for filepath in tqdm.tqdm(filepaths)
        ]
    return [filepath for filepath, needs in filepaths_needs if needs is True]


def main():
    args = parse_args()
    files_that_need_gps = do_scans(args.path)
    for filepath in files_that_need_gps:
        print(filepath)


if __name__ == '__main__':
    main()
