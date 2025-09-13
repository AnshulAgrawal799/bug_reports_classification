import os
import pandas as pd
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from PIL import Image
from tqdm import tqdm
import torch
from transformers import CLIPProcessor, CLIPModel


def get_clip_embeddings(image_paths, model, processor, device):
    embeddings = []
    for img_path in tqdm(image_paths):
        image = Image.open(img_path).convert('RGB')
        inputs = processor(images=image, return_tensors="pt", padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            emb = model.get_image_features(**inputs)
        embeddings.append(emb.cpu().numpy().flatten())
    return np.array(embeddings)


def cluster_images(embeddings, n_clusters=None):
    clustering = AgglomerativeClustering(
        n_clusters=n_clusters or None, distance_threshold=0.5)
    cluster_ids = clustering.fit_predict(embeddings)
    return cluster_ids


def main(classified_csv, images_dir, reports_csv, clusters_json):
    df = pd.read_csv(classified_csv)
    uncertain = df[df['predicted_screen_id'] == 'uncertain']
    image_files = [os.path.join(images_dir, fname)
                   for fname in uncertain['filename']]
    if not image_files:
        print('No uncertain images to cluster.')
        df['cluster_id'] = -1
        df.to_csv(reports_csv, index=False)
        with open(clusters_json, 'w') as f:
            f.write('{}')
        return
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = CLIPModel.from_pretrained(
        'openai/clip-vit-base-patch32').to(device)
    processor = CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
    embeddings = get_clip_embeddings(image_files, model, processor, device)
    cluster_ids = cluster_images(embeddings)
    df.loc[uncertain.index, 'cluster_id'] = cluster_ids
    # Assign -1 for non-uncertain
    df.loc[df['predicted_screen_id'] != 'uncertain', 'cluster_id'] = -1
    import hashlib

    def compute_hash(filepath):
        with open(filepath, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()

    df['id'] = [compute_hash(os.path.join(images_dir, fname))
                for fname in df['filename']]
    # Ensure 'id' is the first column
    cols = ['id'] + [c for c in df.columns if c != 'id']
    df.to_csv(reports_csv, index=False, columns=cols)
    # Write clusters.json
    clusters = {}
    for cid in np.unique(cluster_ids):
        clusters[int(cid)] = list(uncertain[cluster_ids == cid]['filename'])
    import json
    with open(clusters_json, 'w') as f:
        json.dump(clusters, f, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--classified_csv', required=True,
                        help='CSV with screen classification')
    parser.add_argument('--images_dir', required=True,
                        help='Directory with original screenshots')
    parser.add_argument('--reports_csv', required=True,
                        help='Output reports.csv')
    parser.add_argument('--clusters_json', required=True,
                        help='Output clusters.json')
    args = parser.parse_args()
    main(args.classified_csv, args.images_dir,
         args.reports_csv, args.clusters_json)
