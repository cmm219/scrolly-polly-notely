"""Pasted images must survive moving the data folder (config stores absolute paths)."""
import json
import os
from pathlib import Path

import labels
from PIL import Image
from test_note_safety import manager  # noqa: F401  shared temporary-storage fixture


def test_load_config_finds_images_after_data_folder_move(manager):
    os.makedirs(labels.IMAGE_DIR, exist_ok=True)
    name = 'img_moved_10x10.png'
    Image.new('RGB', (10, 10)).save(os.path.join(labels.IMAGE_DIR, name))
    os.makedirs(os.path.join(labels.IMAGE_DIR, 'img_folder.png'))  # a directory is never an image
    old_dir = os.path.join(labels.DATA_DIR, 'old-location', 'pasted-images')
    old, gone = os.path.join(old_dir, name), os.path.join(old_dir, 'img_missing.png')
    folder = os.path.join(old_dir, 'img_folder.png')
    image = {'path': old, 'original_path': old, 'position': '1.0'}
    Path(labels.CONFIG_PATH).write_text(json.dumps({
        'last_session': [{'text': 'x', 'images': [dict(image), {'path': gone, 'position': '1.1'},
                                                   {'path': folder, 'position': '1.2'}]}],
        'stash': [{'text': 'y', 'images': [dict(image)]}],
        'minimized_groups': {'Saved': {'labels': [{'text': 'z', 'images': [dict(image)]}]}},
        'unrelated': {'path': old, 'original_path': old},  # not an image record: never rewritten
    }), encoding='utf-8')

    config = labels.load_config()

    moved = os.path.join(labels.IMAGE_DIR, name)
    first = config['last_session'][0]['images']
    assert first[0]['path'] == first[0]['original_path'] == moved
    assert first[1]['path'] == gone  # nothing to recover: left exactly as saved
    assert first[2]['path'] == folder
    assert config['stash'][0]['images'][0]['path'] == moved
    assert config['minimized_groups']['Saved']['labels'][0]['images'][0]['path'] == moved
    assert config['unrelated'] == {'path': old, 'original_path': old}
