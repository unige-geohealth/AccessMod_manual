#!/usr/bin/env python3
"""Assemble every page of one language (in sidebar order) into a single PDF.

Usage (from the project root):  python3 tools/build_full_pdf.py [en fr]
Output: pdf/AccessMod_manual_EN.pdf, pdf/AccessMod_manual_FR.pdf
The page order and hierarchy are read from the sidebars in _quarto.yml,
so the PDF always follows the site's left menu. Requires Quarto and PyYAML.
"""
import os, re, sys, shutil, subprocess, datetime
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, '_pdf_build')
OUTDIR = os.path.join(ROOT, 'pdf')
SITE = 'https://unige-geohealth.github.io/AccessMod_manual/'
LABELS = {'en': {'title': 'AccessMod 5 user manual', 'toc': 'Contents'},
          'fr': {'title': "AccessMod 5 — manuel de l'utilisateur", 'toc': 'Table des matières'}}

cfg = yaml.safe_load(open(os.path.join(ROOT, '_quarto.yml'), encoding='utf-8'))
site = cfg.get('website', {}).get('site-url', SITE).rstrip('/') + '/'


def walk(items, depth, out):
    for it in items:
        if isinstance(it, str):
            out.append((it, depth))
            continue
        href = it.get('href')
        if href:
            out.append((href, depth))
        if it.get('contents'):
            walk(it['contents'], depth + 1, out)
    return out


def split_front(text):
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


def build(lang):
    sb = next(s for s in cfg['website']['sidebar'] if s.get('id') == lang)
    order = walk(sb['contents'], 1, [])
    slugs = {os.path.splitext(os.path.basename(h))[0] for h, _ in order}
    work = os.path.join(BUILD, lang)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    src_files = os.path.join(ROOT, lang, 'files')
    if os.path.isdir(src_files):
        shutil.copytree(src_files, os.path.join(work, 'files'))
    parts = []
    for href, depth in order:
        path = os.path.join(ROOT, href)
        slug = os.path.splitext(os.path.basename(href))[0]
        meta, body = split_front(open(path, encoding='utf-8').read())
        title = meta.get('title', slug)
        # drop the generated "In this section" list of container pages
        body = re.split(r'\n## (?:In this section|Contenu de cette section)\n', body)[0]
        # prefix explicit ids so they stay unique in the combined document
        body = re.sub(r'\{#([^}\s]+)', lambda m: '{#' + slug + '--' + m.group(1), body)

        def fix_link(m):
            text, url = m.group(1), m.group(2)
            if re.match(r'^(https?:|mailto:|files/)', url):
                return m.group(0)
            target, _, frag = url.partition('#')
            if target == '':
                return f'[{text}](#{slug}--{frag})'
            tslug = os.path.splitext(os.path.basename(target))[0]
            if target.endswith('.qmd') and not target.startswith('../') and tslug in slugs and tslug != 'index':
                return f'[{text}](#{tslug}--{frag})' if frag else f'[{text}](#{tslug})'
            if target.endswith('.qmd'):  # other language or unknown page -> web link
                rel = os.path.normpath(os.path.join(lang, target)).replace('.qmd', '.html')
                return f'[{text}]({site}{rel}' + (f'#{frag}' if frag else '') + ')'
            return m.group(0)
        body = re.sub(r'(?<!!)\[([^\]]*)\]\(([^)\s]+)\)', fix_link, body)
        shift = depth  # page title at level `depth`, its own headings below it
        def demote(m):
            hashes = '#' * min(6, len(m.group(1)) + shift - 1)
            text = m.group(2).rstrip()
            if text.endswith('}') and '{' in text:  # existing attributes
                text = text[:-1] + ' .unlisted}'
            else:
                text += ' {.unlisted}'
            return hashes + ' ' + text
        # page headings are listed in the table of contents, inner headings are not
        body = re.sub(r'^(#{1,6}) (.*)$', demote, body, flags=re.M)
        level = '#' * min(6, depth)
        cls = ' .unnumbered' if slug == 'index' else ''
        heading_title = title if slug != 'index' else ('Preface' if lang == 'en' else 'Préface')
        brk = '{{< pagebreak >}}\n\n' if depth == 1 and parts else ''
        parts.append(f'{brk}{level} {heading_title} {{#{slug}{cls}}}\n\n{body.strip()}\n')
    today = datetime.date.today().isoformat()
    front = (f'---\ntitle: "{LABELS[lang]["title"]}"\ndate: "{today}"\nlang: {lang}\n'
             f'toc: true\ntoc-depth: 2\ntoc-title: "{LABELS[lang]["toc"]}"\n'
             'format:\n  typst:\n    papersize: a4\n    margin:\n      x: 2cm\n      y: 2cm\n'
             '    fontsize: 10pt\n    keep-typ: true\n'
             f'filters:\n  - {os.path.join(ROOT, "tools", "typst-autowidth.lua")}\n---\n\n')
    open(os.path.join(work, 'manual.qmd'), 'w', encoding='utf-8').write(front + '\n'.join(parts))
    open(os.path.join(work, '_quarto.yml'), 'w').write('project:\n  type: default\n')
    subprocess.run(['quarto', 'render', 'manual.qmd', '--to', 'typst'], cwd=work, check=True)
    os.makedirs(OUTDIR, exist_ok=True)
    dst = os.path.join(OUTDIR, f'AccessMod_manual_{lang.upper()}.pdf')
    shutil.copy2(os.path.join(work, 'manual.pdf'), dst)
    print('->', dst)


for lang in (sys.argv[1:] or ['en', 'fr']):
    build(lang)
