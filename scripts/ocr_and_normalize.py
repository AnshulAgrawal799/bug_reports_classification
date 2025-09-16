import os
import pytesseract
from PIL import Image
import re


def ocr_image(image_path, lang='tam+eng'):
    try:
        img = Image.open(image_path)
        ocr_result = pytesseract.image_to_data(
            img, lang=lang, output_type=pytesseract.Output.DICT)
        text = ' '.join([
            ocr_result['text'][i]
            for i in range(len(ocr_result['text']))
            if str(ocr_result['conf'][i]).isdigit() and int(ocr_result['conf'][i]) > 0
        ])
        confidences = [
            int(conf) for conf in ocr_result['conf'] if str(conf).isdigit()
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        return text, avg_conf
    except Exception as e:
        print(f"OCR failed for {image_path}: {e}")
        return '', 0


def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)  # Remove symbols
    text = re.sub(r'\s+', ' ', text)      # Normalize whitespace
    text = text.strip()
    return text


def process_folder(input_dir, output_csv):
    import pandas as pd
    results = []
    for fname in os.listdir(input_dir):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            img_path = os.path.join(input_dir, fname)
            text, conf = ocr_image(img_path)
            norm_text = normalize_text(text)
            results.append({'filename': fname, 'ocr_text': text,
                           'ocr_confidence': conf, 'normalized_text': norm_text})
    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True,
                        help='Input cropped headers folder')
    parser.add_argument('--output', required=True, help='Output CSV file')
    args = parser.parse_args()
    process_folder(args.input, args.output)
