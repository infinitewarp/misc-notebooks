#!/usr/bin/env python3
"""
Script to align photos using center points of pupils and mouth.

Usage:
    python align.py /Users/bradsmith/projects/opencv/brad-shrunk/ /Users/bradsmith/projects/opencv/brad-out/

Tests:
    python -m doctest align.py

"""
import glob
import math
import os
import sys
from functools import lru_cache

import cv2
import numpy as np

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Precalculate these for calculate_third_equilateral_point to stay DRY.
PI3 = math.pi / 3.0  # one angle of an equilateral triangle is pi/3
SIN_PI3 = math.sin(PI3)
COS_PI3 = math.cos(PI3)


def load_coords_for_image(jpg_path):
    """
    Load coordinates from corresponding txt file for jpg_path.
    """
    coords_path = jpg_path[:-4] + '.txt'
    coords = []

    if os.path.isfile(coords_path):
        with open(coords_path) as f:
            for line in f:
                x, y = line.split(' ')[:2]
                coords.append((np.float32(x), np.float32(y)))

    return coords


def load_data(dir_path):
    """
    Load all the jpg images and txt coords in dir_path.
    """
    all_images = []
    all_coords = []

    for jpg_path in glob.glob(os.path.join(dir_path, "*.jpg")):
        coords = load_coords_for_image(jpg_path)

        if len(coords) < 5:
            logger.info('skipping %s; not enough coords (%s)', jpg_path, len(coords))
            continue

        img = cv2.imread(jpg_path)
        img = np.float32(img)  # always use numpy types
        img /= np.float32(255.0)  # convert scale for cv2 (0.0 to 1.0)

        all_images.append(img)
        all_coords.append(coords)

    return all_images, all_coords


@lru_cache()
def calculate_third_equilateral_point(a, b):
    """
    Calculate the third point in an equilateral triangle.

    How does this magic work? See:

    https://en.wikipedia.org/wiki/Transformation_matrix#Rotation

    What's with all the extra addition and subtraction here?
    This effectively translates the shape so the first point is at the origin,
    does the rotation around the origin, and translates back by the starting
    position.

    >>> x, y = calculate_third_equilateral_point((0,0), (2,0))
    >>> round(x, 3), round(y, 3)
    (1.0, -1.732)

    >>> x, y = calculate_third_equilateral_point((0,0), (0,2))
    >>> round(x, 3), round(y, 3)
    (1.732, 1.0)

    >>> x, y = calculate_third_equilateral_point((2,2), (4,2))
    >>> round(x, 3), round(y, 3)
    (3.0, 0.268)
    """
    a_x, a_y = a
    b_x, b_y = b
    new_x = (COS_PI3 * (a_x - b_x)) - (SIN_PI3 * (a_y - b_y)) + b_x
    new_y = (SIN_PI3 * (a_x - b_x)) + (COS_PI3 * (a_y - b_y)) + b_y
    return new_x, new_y


def calculate_transform(starting_point, target_point):
    """
    Calculate a matrix to transform the starting point to the target point.

    https://en.wikipedia.org/wiki/Affine_transformation
    https://en.wikipedia.org/wiki/Rigid_transformation

    OpenCV needs three coplanar points, not two. So, conditionally generate a
    third point by projecting an equilateral triangle from the known two points.
    """
    if len(starting_point) == 2:
        starting_point = list(starting_point)
        starting_third = calculate_third_equilateral_point(*starting_point)
        starting_point.append(starting_third)

    if len(target_point) == 2:
        target_point = list(target_point)
        target_third = calculate_third_equilateral_point(*target_point)
        target_point.append(target_third)

    transform = cv2.estimateRigidTransform(
        np.array(starting_point, np.float32()),
        np.array(target_point, np.float32()),
        fullAffine=False
    )
    return transform


def calculate_pupil_points(output_width, output_height):
    """
    Calculate where pupils should go in the output image.
    """
    pupil_ratio_from_top = 0.4
    pupil_ratio_from_left = 0.35
    left_pupil_coords = (
        int(output_width * pupil_ratio_from_left),
        int(output_height * 0.4)
    )
    right_pupil_coords = (
        int(output_width * (1.0 - pupil_ratio_from_left)),
        int(output_height * 0.4)
    )
    return left_pupil_coords, right_pupil_coords


def main(in_dir_path, out_dir_path):
    output_width = 600
    output_height = 800

    pupil_points = calculate_pupil_points(output_width, output_height)

    all_images, all_images_points = load_data(in_dir_path)

    # transform points to alight the eyes
    all_transforms, transformed_images_points = [], []
    for image_points in all_images_points:
        transform = calculate_transform((image_points[0], image_points[3]), pupil_points)
        new_image_points = []
        for point in image_points:
            new_image_points.append(transform.dot(np.array([point[0], point[1], 1])))
        transformed_images_points.append(new_image_points)
        all_transforms.append(transform)

    # average each of the points across the transformed data
    averaged_points = np.average(np.array(transformed_images_points, np.float32()), axis=0)

    # second transform uses averaged center of mouth as third triangulation point
    all_transforms2 = []
    for image_points, transform in zip(transformed_images_points, all_transforms):
        second_transform = calculate_transform(
            (image_points[0], image_points[3], image_points[4]),
            (averaged_points[0], averaged_points[3], averaged_points[4])
        )
        all_transforms2.append(second_transform)

    average_image = np.zeros((output_height, output_width, 3), np.float32)

    # build a single final transformation from the original input points to the average out
    all_transforms3 = []
    destination_triangle = [averaged_points[0], averaged_points[3], averaged_points[4]]
    for image_points in all_images_points:
        source_triangle = [image_points[0], image_points[3], image_points[4]]
        third_transform = cv2.getAffineTransform(np.float32(source_triangle), np.float32(destination_triangle))
        all_transforms3.append(third_transform)

    image_count = len(all_images)
    for image, transform3, n in zip(all_images, all_transforms3, range(image_count)):
        new_image = cv2.warpAffine(image, transform3, (output_width, output_height))
        cv2.imshow('image', new_image)
        cv2.waitKey(0)

        out_file_path = os.path.join(out_dir_path, f'{n:03}.jpg')
        cv2.imwrite(out_file_path, new_image * 255)

        average_image +=  new_image / image_count

    cv2.imshow('image', average_image)
    out_file_path = os.path.join(out_dir_path, 'average.jpg')
    cv2.imwrite(out_file_path, average_image * 255)
    cv2.waitKey(0)


if __name__ == '__main__':
    in_dir_path = sys.argv[1]
    out_dir_path = sys.argv[2]
    main(in_dir_path, out_dir_path)
