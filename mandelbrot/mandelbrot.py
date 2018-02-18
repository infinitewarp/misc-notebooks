#!/usr/bin/env python3
"""Mandelbrot drawing script."""
import argparse
import tkinter as tk

import matplotlib.pyplot as plt
import numba
import numpy as np
from infinitewarp_utils import timing
from PIL import Image, ImageTk


@numba.jit
def iterate(c_real, c_imag, max_iters):
    """Perform iterative mandelbrot determination using complex numbers."""
    c = complex(c_real, c_imag)
    z = 0.0j
    for count in range(max_iters):
        z = z**2 + c
        if abs(z) > 2.0:
            return count
    return max_iters


@numba.jit
def iterate_fake_complex(c_real, c_imag, max_iters):
    """Perform iterative mandelbrot determination using real numbers.

    This effectively derives and calculates the real and imaginary
    components of the complex number separately.
    """
    real = 0.0
    imag = 0.0
    for step in range(max_iters):
        real2 = real * real
        imag2 = imag * imag
        if real2 + imag2 > 4.0:
            break
        imag = 2 * real * imag + c_imag
        real = real2 - imag2 + c_real
    return step


def _create_pil_image(values):
    with timing.Timer(action='PIL', verbose=True):
        return Image.fromarray(np.swapaxes(values, 0, 1))


def display_pil(values):
    _create_pil_image(values).show()


def display_matplotlib(values, bounds):
    with timing.Timer(action='matplotlib', verbose=True):
        plt.xlabel('real')
        plt.ylabel('imaginary')
        plt.imshow(np.swapaxes(values, 0, 1),
                   extent=bounds,
                   cmap='hot',
                   interpolation='bicubic')
    plt.show()


def display_tkinter(values, width, height, use_pil=True):
    with timing.Timer(action='tkinter setup', verbose=True):
        window = tk.Tk()
        canvas = tk.Canvas(window, width=width, height=height, bg='#000000')
        canvas.pack()

    if use_pil:
        with timing.Timer(action='tkinter canvas from pil', verbose=True):
            pil_im = _create_pil_image(values)
            image = ImageTk.PhotoImage(pil_im)
            canvas.create_image(width/2, height/2, image=image)
    else:
        # don't go this route. it's crazy slow.
        with timing.Timer(action='tkinter built photoimage', verbose=True):
            img = tk.PhotoImage(width=width, height=height)
            canvas.create_image((width/2, height/2), image=img, state='normal')
            with timing.Timer(action='img.put', verbose=True):
                for index, v in np.ndenumerate(values.astype(int)):
                    img.put('#{:02X}{:02X}{:02X}'.format(v, v, v), index)

    tk.mainloop()


def normalize(values, scaler=255, hide_max=False):
    """Normalize values by stretching to fit min-max value domain."""
    with timing.Timer(action='normalize', verbose=True):
        min_val = np.min(values)
        values = values - min_val + 1
        max_val = np.max(values)
        if hide_max:
            # Drop values inside the set to zero, and recalculate the max
            # respective to the values outside of the set.
            values[values == max_val] = 0
            max_val = np.max(values)
        else:
            # Because values inside the set always hit the iteration limit,
            # let's drop them to one-off from the actual max outside the set.
            values[values == max_val] = -1
            max_val = np.max(values) + 1
            values[values == -1] = max_val

        if max_val == 0:
            return values
        return values * scaler / max_val


def calculate(args):
    """Calculate 2d numpy array of values counting to mandelbrot escape."""
    pixel_width = args.width
    pixel_height = args.height

    imag_scale = args.imag_scale  # like y_scale
    real_scale = 1.0 * pixel_width / pixel_height * imag_scale

    imag_min = args.imag_min  # like y_min
    imag_max = imag_min + imag_scale # like y_max
    real_min = args.real_min  # like x_min
    real_max = real_min + real_scale  # like x_max

    iterator = iterate_fake_complex if args.fake_complex else iterate

    with timing.Timer(action='linspace and zeros', verbose=True):
        real_range = np.linspace(real_min, real_max, pixel_width)
        imag_range = np.linspace(imag_min, imag_max, pixel_height)
        values = np.empty((pixel_width, pixel_height), dtype=int)

    with timing.Timer(action='iterations', verbose=True):
        for x_loc in range(pixel_width):
            for y_loc in range(pixel_height):
                real = real_range[x_loc]
                imag = imag_range[y_loc]
                values[x_loc, y_loc] = iterator(real, imag, args.max_iters)

    bounds = (real_min, real_max, imag_min, imag_max)
    return values, bounds


def display(values, bounds, mode, width, height):
    if mode == 'matplotlib':
        display_matplotlib(values, bounds)
    elif mode == 'pil':
        display_pil(values)
    elif mode == 'tkinter':
        display_tkinter(values, width, height)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Mandelbrot set image generator.',
        formatter_class = argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('-d', '--display',
                        choices=['matplotlib', 'pil', 'tkinter'],
                        default='pil',
                        help='which library to use for image display')
    parser.add_argument('-m', '--max_iters', type=int, default=50,
                        help='max iterations to perform for each position '
                             'when determining if in the mandelbrot set')
    parser.add_argument('-W', '--width', type=int, default=2000,
                        help='output image pixel width')
    parser.add_argument('-H', '--height', type=int, default=2000,
                        help='output image pixel height')
    parser.add_argument('-r', '--real_min', type=float, default=-1.5,
                        help='minimum real axis value on the '
                             'complex plane')
    parser.add_argument('-i', '--imag_min', type=float, default=-1.0,
                        help='minimum imaginary axis value on the '
                             'complex plane')
    parser.add_argument('-s', '--imag_scale', type=float, default=2.0,
                        help='size to limit render on the imaginary axis')
    parser.add_argument('-R', '--fake_complex', action='store_true',
                        help='calculate without using native Python complex '
                             'number objects')
    return parser.parse_args()


def main():
    args = parse_args()
    values, bounds = calculate(args)
    print(f'performed {values.sum()} mandelbrot iterations')
    values = normalize(values)
    display(values, bounds, args.display, args.width, args.height)


if __name__ == '__main__':
    main()
