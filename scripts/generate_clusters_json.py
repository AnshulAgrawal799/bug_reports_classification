"""
Generates clusters.json from fixed reports.csv.
- Computes CLIP embeddings (openai/clip-vit-base-patch32 via transformers+torch) in batches for uncertain rows (screen_confidence < 0.8)
- Clusters uncertain rows deterministically (AgglomerativeClustering)
- Assigns cluster ids: clip_0, clip_1, ...
- Generates sorted clusters.json mapping
- Atomic write, idempotent
- Argparse, logging, next steps
"""
import argparse
import csv
import json
import logging
import os
from tempfile import NamedTemporaryFile
from sklearn.cluster import AgglomerativeClustering
import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

MODEL_NAME = 'openai/clip-vit-base-patch32'


def compute_clip_embeddings(image_paths, batch_size=16):
    model = CLIPModel.from_pretrained(MODEL_NAME)
    processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    embeddings = []
    for i in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[i:i+batch_size]
        images = []
        for p in batch_paths:
            try:
                images.append(Image.open(p).convert('RGB'))
            except Exception as e:
                logging.warning(f'Could not open image {p}: {e}')
                images.append(Image.new('RGB', (224, 224)))
        inputs = processor(images=images, return_tensors="pt", padding=True)
        with torch.no_grad():
            emb = model.get_image_features(**inputs).cpu().numpy()
        embeddings.extend(emb)
    return embeddings


def generate_clusters_json(fixed_csv, images_root, clusters_json, batch_size=16):
    rows = []
    uncertain_rows = []
    uncertain_paths = []
    with open(fixed_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            if float(row.get('screen_confidence', 0)) < 0.8:
                img_path = os.path.abspath(
                    os.path.join(images_root, row['filename']))
                uncertain_rows.append(row)
                uncertain_paths.append(img_path)
    if not uncertain_rows:
        logging.info('No uncertain rows to cluster.')
        clusters = {}
    else:
        logging.info(
            f'Computing CLIP embeddings for {len(uncertain_rows)} images...')
        embeddings = compute_clip_embeddings(uncertain_paths, batch_size)
        n_clusters = min(len(embeddings), max(2, len(embeddings)//10))
        clustering = AgglomerativeClustering(
            n_clusters=n_clusters, metric='cosine', linkage='average')
        labels = clustering.fit_predict(embeddings)
        # Assign cluster ids
        for i, row in enumerate(uncertain_rows):
            row['cluster_id'] = f'clip_{labels[i]}'
        clusters = {}
        for i, row in enumerate(uncertain_rows):
            cid = row['cluster_id']
            clusters.setdefault(cid, []).append(row['id'])
    # Sorted clusters.json
    sorted_clusters = {k: sorted(v) for k, v in sorted(clusters.items())}
    # Atomic write
    with NamedTemporaryFile('w', delete=False, encoding='utf-8') as tf:
        json.dump(sorted_clusters, tf, indent=2)
        tempname = tf.name
    os.replace(tempname, clusters_json)
    logging.info('clusters.json written to %s', clusters_json)
    print('Next: Review clusters with Flask UI (review_app.py)')


def main():
    parser = argparse.ArgumentParser(
        description='Generate clusters.json from fixed reports.csv')
    parser.add_argument('--fixed-csv', required=True, help='Path to fixed CSV')
    parser.add_argument(
        '--images-root', default='input_screenshots', help='Root directory for images')
    parser.add_argument('--clusters-json', required=True,
                        help='Path to output clusters.json')
    parser.add_argument('--batch-size', type=int, default=16,
                        help='Batch size for CLIP embedding')
    args = parser.parse_args()
    generate_clusters_json(args.fixed_csv, args.images_root,
                           args.clusters_json, args.batch_size)


if __name__ == '__main__':
    main()
