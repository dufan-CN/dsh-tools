#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md-page —— 把 markdown 转成手机上好读的单文件网页。

一句话：**不拉框架、不建站点、不装依赖**，一个 .md 进去，一个能直接打开的 .html 出来。

为什么写它：2026-11-18，日记写了十几万字，可它躺在 .md 里，
手机上根本打不开——要看得先有编辑器。要的不是「发布博客」，
是「这一页现在就能在手机上看」。所以它只做这一件事。

用法：

    # 单篇
    python md-page.py note.md -o note.html

    # 整个目录（每个 md 一篇，另生成一个索引）
    python md-page.py diary/ -o out/ --title "我的日记"

    # 索引标题用文件名，另加几页外链
    python md-page.py notes/ -o out/ --title "笔记" --extra "读书记:reading.html"

支持的 markdown 只挑实际会用的那些：
    # ## ###       标题
    > 引用          连续多行会合并成一个 blockquote
    - 或 * 列表     无序
    1. 列表         有序
    **粗体**  `代码`  [文字](链接)
    空行            分段

别的语法一律按普通段落处理 —— 宁可少认，不要认错。
"""
import argparse
import glob
import html as ht
import os
import re
import sys

CSS = """
  :root { --bg:#fbfaf7; --fg:#23262b; --muted:#6b7280; --line:#ddd9d1; --accent:#2b6cb0; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:17px/1.9 "PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
         -webkit-text-size-adjust:100%; }
  .wrap { max-width:720px; margin:0 auto; padding:28px 18px 96px; }
  h1 { font-size:22px; margin:0 0 22px; letter-spacing:.5px; }
  h2 { font-size:18px; margin:34px 0 12px; padding-bottom:8px; border-bottom:1px solid var(--line); }
  h3 { font-size:15px; color:var(--accent); margin:22px 0 8px; }
  p { margin:0 0 14px; }
  blockquote { margin:0 0 16px; padding:12px 16px; background:#fff;
               border-left:3px solid var(--accent); border-radius:0 8px 8px 0; }
  blockquote p:last-child { margin-bottom:0; }
  ul,ol { margin:0 0 14px; padding-left:22px; }
  li { margin:4px 0; }
  code { font-family:ui-monospace,Consolas,monospace; font-size:14px;
         background:#eeede9; padding:1px 5px; border-radius:4px; }
  a { color:var(--accent); }
  .nav { font-size:14px; margin-bottom:20px; }
  .nav a { text-decoration:none; }
  .list { list-style:none; padding:0; }
  .list li { border-bottom:1px solid var(--line); padding:13px 0; }
  .list a { text-decoration:none; color:var(--fg); font-size:16px; }
  .list .meta { color:var(--muted); font-size:12.5px; margin-top:3px; }
  .foot { margin-top:60px; padding-top:16px; border-top:1px solid var(--line);
          color:var(--muted); font-size:12.5px; }
"""


def inline(s):
    """行内：先转义，再按 markdown 造标签。
    顺序很要紧 —— 先 escape 再替换，否则用户写的 < 会被当成标签。"""
    s = ht.escape(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    s = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', s)
    return s


def convert(md_text):
    """状态机：不引第三方库，因为要支持的语法就这几样。"""
    out = []
    lines = md_text.splitlines()
    i = 0
    in_ul = False
    in_ol = False
    in_quote = False

    def close():
        nonlocal in_ul, in_ol, in_quote
        if in_ul:
            out.append('</ul>')
            in_ul = False
        if in_ol:
            out.append('</ol>')
            in_ol = False
        if in_quote:
            out.append('</blockquote>')
            in_quote = False

    while i < len(lines):
        s = lines[i].rstrip().strip()

        if not s:
            close()
            i += 1
            continue

        if s.startswith('### '):
            close()
            out.append(f'<h3>{inline(s[4:])}</h3>')
        elif s.startswith('## '):
            close()
            out.append(f'<h2>{inline(s[3:])}</h2>')
        elif s.startswith('# '):
            close()
            out.append(f'<h1>{inline(s[2:])}</h1>')
        elif s.startswith('>'):
            if in_ul:
                out.append('</ul>')
                in_ul = False
            if in_ol:
                out.append('</ol>')
                in_ol = False
            if not in_quote:
                out.append('<blockquote>')
                in_quote = True
            body = s[1:].strip()
            if body:
                out.append(f'<p>{inline(body)}</p>')
        elif re.match(r'^[-*]\s+', s):
            if in_quote:
                out.append('</blockquote>')
                in_quote = False
            if in_ol:
                out.append('</ol>')
                in_ol = False
            if not in_ul:
                out.append('<ul>')
                in_ul = True
            item = re.sub(r'^[-*]\s+', '', s)
            out.append('<li>' + inline(item) + '</li>')
        elif re.match(r'^\d+[.)]\s+', s):
            if in_quote:
                out.append('</blockquote>')
                in_quote = False
            if in_ul:
                out.append('</ul>')
                in_ul = False
            if not in_ol:
                out.append('<ol>')
                in_ol = True
            item = re.sub(r'^\d+[.)]\s+', '', s)
            out.append('<li>' + inline(item) + '</li>')
        else:
            close()
            out.append(f'<p>{inline(s)}</p>')
        i += 1

    close()
    return '\n'.join(out)


def page(title, body, nav='', foot=''):
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{ht.escape(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">{nav}{body}
<div class="foot">{ht.escape(foot)}</div>
</div></body></html>
"""


def build_index(entries, title, extra_links=()):
    """entries: [(name, href, meta), ...]"""
    items = []
    for name, href, meta in entries:
        items.append(
            f'<li><a href="{href}">{ht.escape(name)}</a>'
            f'<div class="meta">{ht.escape(meta)}</div></li>')
    extra = ''
    if extra_links:
        extra = '<h2>另外几页</h2><ul class="list">' + ''.join(
            f'<li><a href="{href}">{ht.escape(name)}</a>'
            f'<div class="meta">{ht.escape(meta)}</div></li>'
            for name, href, meta in extra_links) + '</ul>'
    return page(title,
                f'<h1>{ht.escape(title)}</h1><ul class="list">' + ''.join(items) + '</ul>' + extra)


def parse_extra(specs):
    out = []
    for spec in specs or ():
        name, _, href = spec.partition(':')
        if href:
            out.append((name, href, ''))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='markdown → 单文件网页')
    ap.add_argument('src', help='一个 .md 文件，或者一个装着 .md 的目录')
    ap.add_argument('-o', '--out', help='输出文件，或输出目录（批量时必须给）')
    ap.add_argument('--title', default='', help='页面标题；批量时是索引页的标题')
    ap.add_argument('--no-index', action='store_true', help='批量时不要索引页')
    ap.add_argument('--extra', action='append',
                    help='索引页额外链接，格式「名字:文件.html」，可重复')
    args = ap.parse_args(argv)

    if os.path.isdir(args.src):
        if not args.out:
            ap.error('批量模式要给 -o 输出目录')
        os.makedirs(args.out, exist_ok=True)
        files = sorted(glob.glob(os.path.join(args.src, '*.md')))
        if not files:
            print('这个目录里没有 .md。', file=sys.stderr)
            return 2
        title = args.title or os.path.basename(os.path.normpath(args.src))
        entries = []
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            md = open(f, encoding='utf-8').read()
            body = convert(md)
            nav = '' if args.no_index else '<div class="nav"><a href="index.html">← 全部</a></div>'
            html = page(f'{name} · {title}', body, nav, foot=title)
            dest = os.path.join(args.out, name + '.html')
            open(dest, 'w', encoding='utf-8').write(html)
            entries.append((name, name + '.html', f'{len(md)} 字'))
        if not args.no_index:
            idx = build_index(entries[::-1], title, parse_extra(args.extra))
            open(os.path.join(args.out, 'index.html'), 'w', encoding='utf-8').write(idx)
            print(f'{len(files)} 篇 + index.html')
        else:
            print(f'{len(files)} 篇')
        return 0

    # 单篇
    md = open(args.src, encoding='utf-8').read()
    name = os.path.splitext(os.path.basename(args.src))[0]
    title = args.title or name
    html = page(title, convert(md), foot=title)
    dest = args.out or (os.path.splitext(args.src)[0] + '.html')
    open(dest, 'w', encoding='utf-8').write(html)
    print(f'{dest}  {len(html.encode("utf-8"))} 字节  {len(md)} 字')
    return 0


if __name__ == '__main__':
    sys.exit(main())
