# Kugou CLI

用于从酷狗搜索和下载音乐的 Python 命令行工具。

## 环境要求

- Python 3.10+

## 使用方法

`keyword` 参数支持搜索关键词或酷狗链接（`mixsong`、`album/info`）。

```bash
python kugou_cli.py search "pleaseeedontcry"
python kugou_cli.py download "SCENE SCENE SCENE pleaseeedontcry" --index 1
python kugou_cli.py search "https://www.kugou.com/mixsong/..."
python kugou_cli.py download "https://www.kugou.com/album/info/..."
python kugou_cli.py download "https://www.kugou.com/album/info/..." --index 1 2 3
```

### `search`

```bash
python kugou_cli.py search "歌手或歌曲" --limit 30
```

| 参数        | 说明                                                         |
|-------------|--------------------------------------------------------------|
| `keyword`   | 歌手名、歌曲名、搜索关键词，或支持的酷狗链接                |
| `--limit`   | 筛选前检索的原始结果数量                                     |

### `download`

```bash
python kugou_cli.py download "歌手或歌曲" --index 1 2 --output downloads --limit 30
python kugou_cli.py download "https://www.kugou.com/album/info/..." --output downloads
```

| 参数        | 说明                                                         |
|-------------|--------------------------------------------------------------|
| `keyword`   | 歌手名、歌曲名、搜索关键词，或支持的酷狗链接                |
| `--index`   | 搜索结果中的一个或多个编号；对专辑链接可省略，省略时默认下载整张专辑 |
| `--output`  | 文件保存目录（默认：`downloads/`）                           |
| `--limit`   | 筛选前检索的原始结果数量                                     |

## 备注

- 部分结果显示 `unknown kbps`，因为上游 API 并非总是返回比特率信息。
- 文件名重复时会自动添加 ` (2)`、` (3)` 等后缀，不会覆盖已有文件。
- 可用内容和元数据完全取决于上游服务。
- 部分专辑虽然可以解析成功，但如果酷狗将整张专辑都标记为付费内容，仍然无法下载。

## 致谢

部分代码源自 [CreateDownloader/KugouDownloaderNew](https://github.com/CreateDownloader/KugouDownloaderNew)（EPL-2.0）和 [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi)（MIT）。本项目以 [EPL-2.0](https://www.eclipse.org/legal/epl-2.0/) 发布。

## 免责声明

请合理使用。确保您搜索和下载的内容在您所在司法管辖区内合法，并符合相关内容的权利要求。
