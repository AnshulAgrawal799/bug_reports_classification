"""
Utility to compute CLIP embeddings and cluster screenshots from a CSV.
- Batch, deterministic, robust
- Argparse, logging
"""
import argparse
import csv
import logging
import os
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


def clip_cluster(input_csv, images_root, output_csv, batch_size=16, min_cluster_size=2):
    rows = []
    image_paths = []
    for row in csv.DictReader(open(input_csv, encoding='utf-8')):
        rows.append(row)
        img_path = os.path.abspath(os.path.join(images_root, row['filename']))
        image_paths.append(img_path)
    logging.info(f'Computing CLIP embeddings for {len(image_paths)} images...')
    embeddings = compute_clip_embeddings(image_paths, batch_size)
    n_clusters = min(len(embeddings), max(
        min_cluster_size, len(embeddings)//10))
    clustering = AgglomerativeClustering(
        n_clusters=n_clusters, metric='cosine', linkage='average')
    labels = clustering.fit_predict(embeddings)
    for i, row in enumerate(rows):
        row['clip_cluster'] = f'clip_{labels[i]}'
    # Write output
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    logging.info(f'Clustered CSV written to {output_csv}')
    print('Next: Use clusters for review or downstream tasks.')


def main():
    parser = argparse.ArgumentParser(
        description='Compute CLIP clusters for screenshots in CSV')
    parser.add_argument('--input-csv', required=True, help='Input CSV file')
    parser.add_argument(
        '--images-root', default='input_screenshots', help='Root directory for images')
    parser.add_argument('--output-csv', required=True,
                        help='Output CSV file with clusters')
    parser.add_argument('--batch-size', type=int, default=16,
                        help='Batch size for CLIP embedding')
    parser.add_argument('--min-cluster-size', type=int,
                        default=2, help='Minimum number of clusters')
    args = parser.parse_args()
    clip_cluster(args.input_csv, args.images_root, args.output_csv,
                 args.batch_size, args.min_cluster_size)


if __name__ == '__main__':
    main()
