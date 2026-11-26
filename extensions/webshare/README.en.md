# webshare

Turn a pi session or any file into a public temporary link. The built-in `/share` uses a GitHub gist / Radius and needs `gh` CLI; this extension uses a self-hosted `share.duanz.xin` with no file-size limit.

## Usage

- `/webshare` — share the current session (JSONL rendered as readable dark HTML, tool calls collapsible)
- `/webshare <path>` — share any file as-is (images, PDFs, archives)
- `/webshare --list` — list live shares
- `/webshare --rm <token>` — remove a share (token or full URL)

## Requirements

`~/.pi/agent/bin/share` installed locally, and the public entry for `share.duanz.xin` configured.
