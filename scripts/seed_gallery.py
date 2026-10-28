#!/usr/bin/env python3
"""
Seed script for synthetic gallery faces (§7.1, §8.7, Step B11).
Ingests synthetic face images received from Person A into the gallery.
Uses authenticated API endpoint with real ML embedding.
Safe to rerun: skips existing faces by label.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed synthetic face images into Velora gallery.")
    parser.add_argument(
        "--images-dir",
        type=str,
        required=True,
        help="Path to directory containing synthetic face images.",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=os.environ.get("BACKEND_URL", "http://localhost:8000/api/v1"),
        help="Base URL of backend API (default: http://localhost:8000/api/v1).",
    )
    parser.add_argument(
        "--admin-user",
        type=str,
        default=os.environ.get("ADMIN_USERNAME", "admin"),
        help="Admin username (default: admin).",
    )
    parser.add_argument(
        "--admin-pass",
        type=str,
        default=os.environ.get("SEED_PASSWORD_ADMIN", "admin_pass_123"),
        help="Admin password.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate images without actually uploading them.",
    )
    parser.add_argument(
        "--max-faces",
        type=int,
        default=250,
        help="Maximum number of faces to seed (target: ~200).",
    )
    return parser.parse_args()


def get_auth_token(base_url: str, username: str, password: str) -> str:
    login_url = f"{base_url.rstrip('/')}/auth/login"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(login_url, json={"username": username, "password": password})
            if resp.status_code != 200:
                print(f"Error: Admin login failed (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
                sys.exit(1)
            token = resp.json().get("access_token")
            if not token:
                print("Error: No access token in login response.", file=sys.stderr)
                sys.exit(1)
            return str(token)
    except Exception as exc:
        print(f"Error connecting to backend API at {login_url}: {exc}", file=sys.stderr)
        sys.exit(1)


def get_existing_labels(base_url: str, token: str) -> set[str]:
    gallery_url = f"{base_url.rstrip('/')}/gallery"
    try:
        with httpx.Client(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {token}"}
            resp = client.get(gallery_url, headers=headers)
            if resp.status_code != 200:
                print(f"Warning: Could not fetch existing gallery faces: {resp.text}", file=sys.stderr)
                return set()
            data = resp.json()
            if isinstance(data, list):
                return {item.get("label") for item in data if item.get("label")}
            return set()
    except Exception as exc:
        print(f"Warning: Failed querying gallery faces: {exc}", file=sys.stderr)
        return set()


def upload_face(base_url: str, token: str, image_path: Path, label: str) -> dict[str, Any] | None:
    upload_url = f"{base_url.rstrip('/')}/gallery/faces"
    try:
        with httpx.Client(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {token}"}
            with open(image_path, "rb") as f:
                files = {"file": (image_path.name, f, "image/png")}
                data = {
                    "label": label,
                    "source": "synthetic",
                }
                resp = client.post(upload_url, files=files, data=data, headers=headers)
                if resp.status_code == 201:
                    return resp.json()
                print(
                    f"Failed uploading {image_path.name} (HTTP {resp.status_code}): {resp.text}",
                    file=sys.stderr,
                )
                return None
    except Exception as exc:
        print(f"Error uploading {image_path.name}: {exc}", file=sys.stderr)
        return None


def main() -> None:
    args = parse_args()
    images_dir = Path(args.images_dir)

    if not images_dir.exists() or not images_dir.is_dir():
        print(
            f"Error: Synthetic image directory does not exist: {images_dir}\n"
            "Please provide a valid directory containing synthetic face images received from Person A.\n"
            "Usage: python scripts/seed_gallery.py --images-dir <path/to/images>",
            file=sys.stderr,
        )
        sys.exit(1)

    all_images = [p for p in sorted(images_dir.iterdir()) if p.suffix.lower() in ALLOWED_EXTENSIONS]
    if not all_images:
        print(
            f"Error: No supported images (.png, .jpg, .webp) found in directory: {images_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found {len(all_images)} candidate images in {images_dir}")

    # Authenticate with backend API
    token = get_auth_token(args.api_url, args.admin_user, args.admin_pass)
    existing_labels = get_existing_labels(args.api_url, token)
    print(f"Current gallery contains {len(existing_labels)} existing face records.")

    to_upload: list[Path] = []
    skipped = 0
    for img_path in all_images:
        label = img_path.stem
        if label in existing_labels:
            skipped += 1
        else:
            to_upload.append(img_path)
        if len(to_upload) >= args.max_faces:
            break

    print(f"Planning to upload {len(to_upload)} new images ({skipped} already exist in gallery).")

    if args.dry_run:
        print("Dry run completed. No images were uploaded.")
        sys.exit(0)

    inserted = 0
    errors = 0
    for idx, img_path in enumerate(to_upload, start=1):
        label = img_path.stem
        res = upload_face(args.api_url, token, img_path, label)
        if res:
            inserted += 1
            if inserted % 25 == 0 or inserted == len(to_upload):
                print(f"Progress: [{idx}/{len(to_upload)}] uploaded {label}")
        else:
            errors += 1

    print(
        f"Seeding completed: {inserted} inserted, {skipped} skipped, "
        f"{errors} errors (total candidates evaluated: {len(all_images)})."
    )


if __name__ == "__main__":
    main()
