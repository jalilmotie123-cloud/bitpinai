# OCT24 G6 Live History

The collector at `tools/oct24_g6_collector.py` collects the authenticated G6 signal history from:

`https://api.oct24.ai/v1/g6/signals/history`

## Windows 7 / Python 3.8

From the repository root:

```cmd
python tools\oct24_g6_collector.py
```

The script prompts for the OCT24 Bearer token with hidden input. The token is not written to disk and is not sent to Git.

It stores signal records as JSONL chunks of up to 5,000 records in `data/g6/live/`, updates `manifest.json`, then runs:

```text
git add data/g6/live
git commit ...
git push
```

Git push uses the user's existing Git credentials. If push authentication is not configured, the data remains safely saved locally and can be pushed after Git authentication is fixed.

Repeated runs are incremental: page 1 is checked first, and already-stored IDs are skipped. The collector never stores the OCT24 token.
