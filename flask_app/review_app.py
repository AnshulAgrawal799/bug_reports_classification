"""
Minimal Flask UI to label and merge clusters.
- Atomically updates CSV/JSON
- Robust to concurrent edits
- Shows clusters, allows labeling/merging
- Argparse, logging
"""
import argparse
import csv
import json
import logging
import os
from flask import Flask, render_template_string, request, redirect, url_for
from threading import Lock

app = Flask(__name__)
lock = Lock()

CSV_PATH = None
CLUSTERS_JSON_PATH = None
IMAGES_ROOT = None

TEMPLATE = """
<!doctype html>
<title>Cluster Review</title>
<h1>Screenshot Clusters</h1>
<form method="post" action="/merge">
<table border=1>
<tr><th>Cluster</th><th>IDs</th><th>Label</th><th>Merge Into</th></tr>
{% for cid, ids in clusters.items() %}
<tr>
<td>{{ cid }}</td>
<td>{{ ids|length }}<br>{{ ids|join(', ') }}</td>
<td><input name="label_{{ cid }}" value="{{ labels.get(cid, '') }}"></td>
<td><input name="merge_{{ cid }}" value=""></td>
</tr>
{% endfor %}
</table>
<input type="submit" value="Update">
</form>
"""


def load_clusters():
    with open(CLUSTERS_JSON_PATH, encoding='utf-8') as f:
        clusters = json.load(f)
    return clusters


def load_labels():
    labels = {}
    if os.path.exists(CLUSTERS_JSON_PATH + '.labels'):
        with open(CLUSTERS_JSON_PATH + '.labels', encoding='utf-8') as f:
            labels = json.load(f)
    return labels


def save_labels(labels):
    with lock:
        tmp = CLUSTERS_JSON_PATH + '.labels.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(labels, f, indent=2)
        os.replace(tmp, CLUSTERS_JSON_PATH + '.labels')


def merge_clusters(merge_map):
    with lock:
        with open(CLUSTERS_JSON_PATH, encoding='utf-8') as f:
            clusters = json.load(f)
        new_clusters = {}
        for cid, ids in clusters.items():
            target = merge_map.get(cid, cid)
            new_clusters.setdefault(target, []).extend(ids)
        # Remove duplicates and sort
        for k in new_clusters:
            new_clusters[k] = sorted(set(new_clusters[k]))
        tmp = CLUSTERS_JSON_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(new_clusters, f, indent=2)
        os.replace(tmp, CLUSTERS_JSON_PATH)
        # Update CSV cluster_id
        with open(CSV_PATH, encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            for old, new in merge_map.items():
                if row.get('cluster_id') == old:
                    row['cluster_id'] = new
        tmp_csv = CSV_PATH + '.tmp'
        with open(tmp_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        os.replace(tmp_csv, CSV_PATH)


@app.route('/', methods=['GET'])
def index():
    clusters = load_clusters()
    labels = load_labels()
    return render_template_string(TEMPLATE, clusters=clusters, labels=labels)


@app.route('/merge', methods=['POST'])
def merge():
    clusters = load_clusters()
    labels = load_labels()
    merge_map = {}
    for cid in clusters:
        label = request.form.get(f'label_{cid}', '').strip()
        if label:
            labels[cid] = label
        merge_target = request.form.get(f'merge_{cid}', '').strip()
        if merge_target and merge_target != cid:
            merge_map[cid] = merge_target
    save_labels(labels)
    if merge_map:
        merge_clusters(merge_map)
    return redirect(url_for('index'))


def main():
    global CSV_PATH, CLUSTERS_JSON_PATH, IMAGES_ROOT
    parser = argparse.ArgumentParser(
        description='Review and merge screenshot clusters')
    parser.add_argument('--csv', required=True, help='Path to fixed CSV')
    parser.add_argument('--clusters-json', required=True,
                        help='Path to clusters.json')
    parser.add_argument(
        '--images-root', default='input_screenshots', help='Root directory for images')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Host for Flask app')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port for Flask app')
    args = parser.parse_args()
    CSV_PATH = args.csv
    CLUSTERS_JSON_PATH = args.clusters_json
    IMAGES_ROOT = args.images_root
    logging.info('Starting Flask app for cluster review...')
    print(
        f'Open http://{args.host}:{args.port}/ in your browser to review clusters.')
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
