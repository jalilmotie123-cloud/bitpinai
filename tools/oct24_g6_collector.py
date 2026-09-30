# -*- coding: utf-8 -*-
"""
OCT24 G6 signal history collector.

- Prompts for the user's Bearer token without echoing it.
- Paginates /v1/g6/signals/history in pages of 100.
- On the first run, collects the complete history until the API returns <100 items.
- On later runs, starts from page 1 and appends only unseen signal IDs, stopping
  after the newest pages are already known.
- Stores data as JSONL chunks under data/g6/live/.
- Writes a manifest with counts/timestamps.
- Optionally commits and pushes with the user's existing local Git credentials.
- NEVER stores the Bearer token.
Compatible with Python 3.8.
"""

import getpass
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(REPO_ROOT, "data", "g6", "live")
CHUNK_SIZE = 5000
PAGE_SIZE = 100
REQUEST_DELAY = 0.35
MAX_PAGES = 0  # 0 = no limit
BASE_URL = "https://api.oct24.ai/v1/g6/signals/history"

os.makedirs(DATA_DIR, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    p = subprocess.run(
        ["git"] + list(args),
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return p.returncode, p.stdout.strip()


def load_seen_ids():
    seen = set()
    files = sorted(
        f for f in os.listdir(DATA_DIR)
        if f.startswith("g6_signals_") and f.endswith(".jsonl")
    )
    for name in files:
        path = os.path.join(DATA_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    sid = obj.get("id")
                    if sid is not None:
                        seen.add(str(sid))
                except Exception:
                    pass
    return seen, files


def next_chunk_state(files):
    if not files:
        return 1, 0, None

    name = files[-1]
    try:
        idx = int(name.split("_")[-1].split(".")[0])
    except Exception:
        idx = len(files)

    path = os.path.join(DATA_DIR, name)
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            count = sum(1 for line in fh if line.strip())
    except Exception:
        count = 0

    if count >= CHUNK_SIZE:
        return idx + 1, 0, None

    return idx, count, path


def append_items(items, chunk_idx, chunk_count, chunk_path):
    for item in items:
        if chunk_path is None or chunk_count >= CHUNK_SIZE:
            chunk_path = os.path.join(
                DATA_DIR, "g6_signals_{:06d}.jsonl".format(chunk_idx)
            )
            chunk_idx += 1
            chunk_count = 0

        with open(chunk_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
            fh.write("\n")
        chunk_count += 1

    return chunk_idx, chunk_count, chunk_path


def write_manifest(total_unique, first_id, last_id, pages, new_count):
    manifest = {
        "source": "OCT24 G6 signals history API",
        "endpoint": BASE_URL,
        "page_size": PAGE_SIZE,
        "total_unique_stored": total_unique,
        "new_records_this_run": new_count,
        "first_id_seen_in_storage": first_id,
        "last_id_seen_in_storage": last_id,
        "pages_requested_this_run": pages,
        "updated_at_utc": now_iso(),
        "token_stored": False,
    }
    path = os.path.join(DATA_DIR, "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return path


def main():
    print("OCT24 G6 collector")
    print("Repo:", REPO_ROOT)
    print("Data:", DATA_DIR)
    token = getpass.getpass("Bearer token (input hidden): ").strip()
    if not token:
        print("ERROR: token is empty")
        return 2

    seen, files = load_seen_ids()
    chunk_idx, chunk_count, chunk_path = next_chunk_state(files)
    print("EXISTING_UNIQUE_IDS=", len(seen))

    session = requests.Session()
    session.headers.update({
        "accept": "application/json, text/plain, */*",
        "authorization": "Bearer " + token,
    })

    page = 1
    new_count = 0
    pages = 0
    consecutive_all_seen_pages = 0
    first_id = None
    last_id = None

    while True:
        if MAX_PAGES and pages >= MAX_PAGES:
            print("STOP: MAX_PAGES reached")
            break

        url = "{}?page={}&limit={}".format(BASE_URL, page, PAGE_SIZE)
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException as exc:
            print("NETWORK_ERROR:", exc)
            return 1

        pages += 1
        if r.status_code != 200:
            print("HTTP_STATUS=", r.status_code)
            print("BODY=", r.text[:1000])
            return 1

        try:
            payload = r.json()
        except ValueError:
            print("INVALID_JSON")
            print(r.text[:1000])
            return 1

        items = payload.get("data", {}).get("items", [])
        if not isinstance(items, list):
            print("ERROR: data.items is not a list")
            return 1

        page_new = []
        for item in items:
            sid = item.get("id")
            if sid is None:
                continue
            key = str(sid)
            if key not in seen:
                seen.add(key)
                page_new.append(item)

        if page_new:
            chunk_idx, chunk_count, chunk_path = append_items(
                page_new, chunk_idx, chunk_count, chunk_path
            )
            new_count += len(page_new)
            consecutive_all_seen_pages = 0
        else:
            consecutive_all_seen_pages += 1

        if items:
            p_first = items[0].get("id")
            p_last = items[-1].get("id")
            print(
                "PAGE={}; COUNT={}; NEW={}; FIRST_ID={}; LAST_ID={}".format(
                    page, len(items), len(page_new), p_first, p_last
                )
            )
            if first_id is None:
                first_id = p_first
            last_id = p_last
        else:
            print("PAGE={}; COUNT=0".format(page))

        if not items:
            break

        # Full initial backfill ends when the API returns a short page.
        if len(items) < PAGE_SIZE:
            break

        # Incremental runs stop after a page contains no unseen IDs.
        if len(seen) > len(page_new) and consecutive_all_seen_pages >= 1:
            # There may be one page of overlap; the next page is not needed for
            # normal incremental collection because API results are newest-first.
            if new_count > 0:
                break

        page += 1
        time.sleep(REQUEST_DELAY)

    manifest_path = write_manifest(
        total_unique=len(seen),
        first_id=first_id,
        last_id=last_id,
        pages=pages,
        new_count=new_count,
    )

    print("========== RESULT ==========")
    print("PAGES_REQUESTED=", pages)
    print("NEW_RECORDS=", new_count)
    print("TOTAL_UNIQUE_STORED=", len(seen))
    print("DATA_DIR=", DATA_DIR)
    print("MANIFEST=", manifest_path)

    # Git operations use the user's configured Git credentials; no token from
    # OCT24 is passed to Git.
    rc, out = git(
        "add",
        "data/g6/live",
    )
    if rc != 0:
        print("GIT_ADD_ERROR=", out)
        return 1

    status_rc, status = git("status", "--short")
    if status_rc != 0:
        print("GIT_STATUS_ERROR=", status)
        return 1

    if not status:
        print("GIT: no changes to commit")
        return 0

    msg = "Update OCT24 G6 signal history ({})".format(
        datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    rc, out = git("commit", "-m", msg)
    if rc != 0:
        print("GIT_COMMIT_ERROR=", out)
        return 1

    rc, out = git("push")
    if rc != 0:
        print("GIT_PUSH_ERROR=", out)
        print("Data is saved locally; run git push after fixing Git authentication.")
        return 1

    print("GIT_PUSH=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
