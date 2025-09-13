import pandas as pd
from rapidfuzz import fuzz, process

# Example known screens dictionary (expand as needed)
KNOWN_SCREENS = {
    'home': ['home', 'main', 'dashboard'],
    'login': ['login', 'sign in', 'signin'],
    'profile': ['profile', 'my account'],
    'settings': ['settings', 'preferences'],
    # Add more canonical screen names and variants here
}

# Flatten for fuzzy matching
ALL_SCREEN_LABELS = []
LABEL_TO_SCREEN = {}
for screen_id, labels in KNOWN_SCREENS.items():
    for label in labels:
        ALL_SCREEN_LABELS.append(label)
        LABEL_TO_SCREEN[label] = screen_id


def classify_screen(text, threshold=80):
    # Exact match
    for label, screen_id in LABEL_TO_SCREEN.items():
        if text == label:
            return screen_id, 1.0
    # Fuzzy match
    match, score, _ = process.extractOne(
        text, ALL_SCREEN_LABELS, scorer=fuzz.ratio)
    if score >= threshold:
        return LABEL_TO_SCREEN[match], score/100.0
    return 'uncertain', score/100.0


def classify_csv(input_csv, output_csv):
    df = pd.read_csv(input_csv)
    screen_ids = []
    confidences = []
    for text in df['normalized_text']:
        screen_id, conf = classify_screen(text)
        screen_ids.append(screen_id)
        confidences.append(conf)
    df['predicted_screen_id'] = screen_ids
    df['screen_confidence'] = confidences
    df.to_csv(output_csv, index=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True,
                        help='Input CSV with normalized_text')
    parser.add_argument('--output', required=True,
                        help='Output CSV with screen classification')
    args = parser.parse_args()
    classify_csv(args.input, args.output)
