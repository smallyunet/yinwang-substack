# yinwang-substack

抓取 https://yinwang1.substack.com 的文章（文本+图片）到本地，并从本地源数据生成可部署到 GitHub Pages 的静态站点。

## 目录结构

- `data/raw/`
  - `archive.json`：文章列表（来自 Substack archive API）
  - `posts/<slug>/post.json`：文章 JSON（来自 `api/v1/posts/<slug>`）
  - `posts/<slug>/body.html`：文章正文 HTML（从 `post.json.body_html` 提取）
  - `posts/<slug>/media/*`：该文章下载下来的图片
- `docs/`：静态站点输出目录（GitHub Pages 发布目录）

## 安装

本项目用 Python 虚拟环境（已在本工作区配置为 `.venv`）。

依赖：

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

## 抓取（落盘 raw 数据）

```bash
./.venv/bin/python scripts/fetch.py
```

默认会：

1) 拉取文章列表（archive API）到 `data/raw/archive.json`
2) 对列表中的每篇文章拉取 `post.json` + `body.html`
3) 解析 `body.html` 中的图片 URL 并下载到 `data/raw/posts/<slug>/media/`

### 付费/仅订阅文章说明

如果文章是付费/仅订阅可见，在未登录状态下 Substack 的 `api/v1/posts/<slug>` 很可能只返回截断 `body_html`。

如果你希望抓取你“有权限看到的全文”，可以把浏览器里访问 Substack 后的 cookie 传给脚本（只在本机使用，不会上传）：

```bash
export SUBSTACK_COOKIE='key=value; key2=value2; ...'
./.venv/bin/python scripts/fetch.py
```

## 构建静态站点（从 raw 渲染）

```bash
./.venv/bin/python scripts/build.py
```

输出在 `docs/`。

## GitHub Pages

发布方式固定为：从 `main` 分支的 `docs/` 目录发布。

在 GitHub 仓库里：Settings → Pages → Build and deployment → Source 选择 “Deploy from a branch”，然后选择 `main` / `/docs`。
# yinwang-substack
