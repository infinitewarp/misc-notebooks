#!/usr/bin/env python3
"""
A crude script for manually capturing 5 key points for each picture in a directory.
Output is saved next to each image in a similarly-named .txt file.

For face photos, good point candidates would be:

1. left pupil
2. left tear duct
3. right tear duct
4. right pupil
5. bottom between top incisors

(wherein left and right are from the camera's perspective)
"""
import glob
import os
import sys
import tkinter as tk
from functools import partial

import cv2
import numpy as np


# def get_screen_dimensions():
#     """Dirty hack, but it wind of works?"""
#     root = tk.Tk()
#     screen_width = root.winfo_screenwidth()
#     screen_height = root.winfo_screenheight()
#     # root.destroy()
#     return screen_width, screen_height

# screen_width, screen_height = get_screen_dimensions()
# window_width, window_height = screen_width - 40, screen_height - 40
window_width, window_height = 1000, 1000

def add_coordinate(img, coordslist, event, x, y, flags, param):
    """Mouse callback function."""
    # if event == cv2.EVENT_LBUTTONDBLCLK:
    if event == cv2.EVENT_LBUTTONDOWN:
        cv2.circle(img, center=(x, y), radius=2, color=(0, 255, 255), thickness=-1)
        coordslist.append((x, y))


def draw_existing_coords(img, old_coords):
    for x, y in old_coords:
        print((x, y))
        cv2.circle(img, center=(x, y), radius=2, color=(255, 255, 0), thickness=-1)


def initialize_window(img, coordslist):
    # # Create a black image, a window and bind the function to window
    # img = np.zeros(shape=(512,512,3), dtype=np.uint8)
    # cv2.destroyAllWindows()
    cv2.namedWindow('image', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('image', width=window_width, height=window_height)


def gather_coords_for_image(img, old_coords, first_time):
    new_coords = []
    mat = img.copy()
    if first_time:
        initialize_window(mat, new_coords)
    draw_existing_coords(mat, old_coords)
    cv2.setMouseCallback(
        window_name='image',
        on_mouse=partial(add_coordinate, mat, new_coords))

    capturing = True
    while(capturing):
        cv2.imshow(winname='image', mat=mat)
        k = cv2.waitKey(delay=20) & 0xFF  # delay is milliseconds
        if len(new_coords) == 5:
            break
        if k == ord('r'):  # r is for reset!
            mat = img.copy()
            draw_existing_coords(mat, old_coords)
            cv2.setMouseCallback(
                window_name='image',
                on_mouse=partial(add_coordinate, mat, new_coords))
            new_coords.clear()
        elif k in (27, ord('n')):  # 27 is escape key
            break

    # cv2.destroyAllWindows()
    return new_coords


def process_jpg(jpg_path, old_coords, first_time):
    img = cv2.imread(jpg_path);
    img = np.float32(img) / 255.0;
    new_coords = gather_coords_for_image(img, old_coords, first_time)

    print(jpg_path)
    for coords in new_coords:
        print(f'{coords[0]} {coords[1]}')

    return new_coords


def load_old_coords_for_image(jpg_path):
    coords_path = jpg_path[:-4] + '.txt'
    old_coords = []
    if os.path.isfile(coords_path):
        with open(coords_path) as f:
            for line in f:
                coords = line.split(' ')[:2]
                x, y = int(coords[0]), int(coords[1])
                old_coords.append((x, y))
    return old_coords


def save_new_coords_for_image(jpg_path, new_coords):
    coords_path = jpg_path[:-4] + '.txt'
    with open(coords_path, 'w') as f:
        for x, y in new_coords:
            f.write(f'{x} {y}\n')


def process_directory(dir_path):
    first_time = True
    for jpg_path in glob.glob(os.path.join(dir_path, "*.jpg")):
        old_coords = load_old_coords_for_image(jpg_path)
        new_coords = process_jpg(jpg_path, old_coords, first_time)
        if len(new_coords) == 5:
            save_new_coords_for_image(jpg_path, new_coords)
        first_time = False

if __name__ == '__main__':
    dir_path = sys.argv[1]
    process_directory(dir_path)
