# blog.shiyao.pro

我的个人技术博客 — 一个**全静态、纯 HTML、由 Claude Code 协助撰写**的小站。

🔗 **在线访问**：<https://blog.shiyao.pro/>

## 这个仓库是什么

这里存放 [blog.shiyao.pro](https://blog.shiyao.pro/) 的全部源文件 + 部署相关脚本和 nginx 配置。
博客本身没有任何运行时（没有数据库、没有 SSG、没有 JS 框架）—
只是 nginx 静态文件 + 一个 bash 发布脚本。

之所以"轻"，是因为我把 AI 内容生成这一环节放在云端 Claude Code 里完成，
本地不需要构建工具。详情见文章 [Happy + Claude Code：让 AI 编程助手 7×24 在线](https://blog.shiyao.pro/happy-claude-247)。

## 仓库结构

```
.
├── index.html               # 博客首页(文章列表)
├── *.html                   # 各篇文章,文件名即 URL slug
├── scripts/
│   └── publish-blog         # 一键发布脚本(放到 /usr/local/bin/)
├── nginx/
│   └── blog.shiyao.pro.conf # nginx 站点配置参考
└── README.md
```

## 发布链路

```
本地 / 服务器写好 HTML
       ↓
publish-blog ./foo.html --tag DevOps
       ↓
拷贝到 /var/www/blog.shiyao.pro/ → chown nginx:nginx → chmod 644
       ↓
自动从 HTML 提取 <title> / <meta description>,插入首页文章列表
       ↓
访问 https://blog.shiyao.pro/foo (得益于 try_files,无需 .html 后缀)
```

## AI Daily 自动更新

`ai-daily.html` 是稳定入口，每天北京时间 10:00 由 GitHub Actions 自动更新：

```bash
python3 scripts/generate-ai-daily.py
```

更新 workflow：`.github/workflows/update-ai-daily.yml`。它会抓取 OpenAI / TechCrunch / The Verge 的 AI RSS，以及 GitHub daily trending，生成新的 `ai-daily.html` 并提交回 `main`；随后现有 deploy workflow 自动同步到 nginx。

本地生图面板需要先启动 helper：

```bash
python3 scripts/local-image-helper
```

服务器部署时，页面默认请求同域 HTTPS 接口 `/ai-image/generate-image`，由 nginx 反代到本机 helper。公网访问必须填写 token，token 存在服务器本地：

```bash
cat .local-ai-images/image-token
```

默认 helper 会调用本机 `codex exec`，要求 Codex 把图片保存成 PNG。若本地 Codex 没有生图工具，可用 `AI_IMAGE_COMMAND` 接自己的生图 CLI：

```bash
AI_IMAGE_COMMAND='my-image-cli --prompt "{prompt}" --output "{output}"' \
  python3 scripts/local-image-helper
```

## 写一篇新文章

1. 复制一个现有 HTML 当模板（比如 `happy-claude-247.html`）。
2. 改 `<title>`、`<meta name="description">`、正文内容。
3. 保存为 `your-slug.html`，slug 仅允许 `[a-zA-Z0-9_-]`。
4. 部署：
   ```bash
   publish-blog ./your-slug.html --tag 笔记
   ```
5. 提交进仓库：
   ```bash
   git add your-slug.html index.html
   git commit -m "post: 标题"
   git push
   ```

## `publish-blog` 用法

```
publish-blog <file.html> [选项]

  --slug NAME       自定义 URL slug (默认: 文件名去掉 .html)
  --title TEXT      指定标题 (默认: 从 <title> 提取)
  --summary TEXT    指定摘要 (默认: 从 <meta name="description"> 提取)
  --tag TEXT        标签 (DevOps / AI / 笔记 ...)
  --no-index        只发布,不更新首页列表
  --force           已存在时强制覆盖(幂等)
  -h, --help        显示帮助
```

特性:

- 校验 slug，防路径穿越
- 自动从 HTML 提取标题和摘要
- 权限对齐 `nginx:nginx` 644
- 幂等的首页插入（多次 `--force` 不重复）
- 无需 reload nginx

## 服务器架构

- **域名**: `blog.shiyao.pro` → 阿里云 ECS（美国弗吉尼亚节点）
- **OS**: Alibaba Cloud Linux 4
- **Web Server**: nginx + HTTP/2
- **TLS**: 阿里云免费证书
- **TLS 协议**: TLSv1.2 / TLSv1.3
- **HTML 缓存策略**: `Cache-Control: no-cache`（新内容立即可见）
- **静态资源**: 30 天浏览器缓存
- **DNS**: A 记录直接指向 ECS 公网 IP

## 文章列表

- [今日 AI 趋势看板：资讯、GitHub 趋势与生图工具](ai-daily.html) — 每日 10:00 自动更新
- [今日 AI 榜单：资讯、GitHub 趋势、X 推荐热门](ai-daily-rankings-2026-06-05.html) — 2026-06-05
- [Claude Opus 4.8 Workflow 原理：动态工作流、架构图与代码逻辑](claude-opus-48-workflow.html) — 2026-06-05
- [html-video 使用指南：Agent 写 HTML，本地导出 MP4](html-video-guide.html) — 2026-06-05
- [全静态博客的 GitHub Actions 自动部署 — 写一篇 push 一次](blog-ci-github-actions.html) — 2026-06-04
- [Happy + Claude Code：让 AI 编程助手 7×24 在线](happy-claude-247.html) — 2026-06-04

## License

文章内容（`*.html` 文本） © shiyao，保留所有权利。
脚本（`scripts/`）和配置（`nginx/`）按 **MIT** 提供，可自由参考改造。
