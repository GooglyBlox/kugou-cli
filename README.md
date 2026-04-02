# Kugou CLI

A Python CLI for searching and downloading tracks from Kugou.

## Requirements

- Python 3.10+

## Usage

The `keyword` argument accepts a search phrase or a supported Kugou URL (`mixsong`, `album/info`).

```bash
python kugou_cli.py search "pleaseeedontcry"
python kugou_cli.py download "SCENE SCENE SCENE pleaseeedontcry" --index 1
python kugou_cli.py search "https://www.kugou.com/mixsong/..."
python kugou_cli.py download "https://www.kugou.com/album/info/..." --index 1 2 3
```

### `search`

```bash
python kugou_cli.py search "artist or song" --limit 30
```

| Argument    | Description                                                  |
|-------------|--------------------------------------------------------------|
| `keyword`   | Artist, song title, search phrase, or supported Kugou URL    |
| `--limit`   | Number of raw results to inspect before filtering            |

### `download`

```bash
python kugou_cli.py download "artist or song" --index 1 2 --output downloads --limit 30
```

| Argument    | Description                                                  |
|-------------|--------------------------------------------------------------|
| `keyword`   | Artist, song title, search phrase, or supported Kugou URL    |
| `--index`   | One or more result numbers from the search list              |
| `--output`  | Folder to save files into (default: `downloads/`)            |
| `--limit`   | Number of raw results to inspect                             |

## Notes

- Some results show `unknown kbps`, as the upstream API doesn't always return bitrate info.
- Duplicate filenames get a ` (2)`, ` (3)`, etc. suffix instead of being overwritten.
- Availability and metadata depend entirely on the upstream service.

## Credit

Derived in part from [CreateDownloader/KugouDownloaderNew](https://github.com/CreateDownloader/KugouDownloaderNew) (EPL-2.0) and [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi) (MIT). This project is distributed under [EPL-2.0](https://www.eclipse.org/legal/epl-2.0/).

## Disclaimer

Use responsibly. Make sure what you download is permitted in your jurisdiction and under the rights attached to the content.
