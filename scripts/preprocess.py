import os
import cv2
from PIL import Image


def crop_header(image_path, output_path, header_ratio=0.18):
    img = cv2.imread(image_path)
    if img is None:
        print(f"Failed to load {image_path}")
        return False
    h, w, _ = img.shape
    header_height = int(h * header_ratio)
    header_crop = img[0:header_height, :]
    cv2.imwrite(output_path, header_crop)
    return True


def process_folder(input_dir, output_dir, header_ratio=0.18):
    os.makedirs(output_dir, exist_ok=True)
    for fname in os.listdir(input_dir):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            in_path = os.path.join(input_dir, fname)
            out_path = os.path.join(output_dir, fname)
            crop_header(in_path, out_path, header_ratio)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True,
                        help='Input screenshots folder')
    parser.add_argument('--output', required=True,
                        help='Output cropped headers folder')
    parser.add_argument('--header-ratio', type=float,
                        default=0.18, help='Header crop ratio (default 0.18)')
    args = parser.parse_args()
    process_folder(args.input, args.output, args.header_ratio)
