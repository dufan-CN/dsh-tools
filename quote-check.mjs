#!/usr/bin/env node
// quote-check —— 核一段引文是不是真在那本书里。
//
// 为什么写它：2026-11-10 想逐句核对读书笔记，连着三次「搜不到」，
// 三次都是工具的错，不是引文假：
//   ① 原文用弯引号 ’ 和 ”，我拿直引号 ' " 去搜 —— 当然搜不到；
//   ② 句子在原文里跨行，单行 grep 是逐行匹配的，跨行就断；
//   ③ 用 \u2026 去 split 省略号，PowerShell 的正则不认这个转义，
//      整段带着省略号去搜，报出「27 条不匹配」—— 全是假警报。
// 这个工具只做一件事：**把匹配做对**。匹配不上，才轮到怀疑引文。
//
// 用法：
//   node quote-check.mjs --source book.txt "要查的一句话"
//   node quote-check.mjs --source book.txt --page notes.html
//   node quote-check.mjs --source book.txt --page notes.html --strict
//
//   --source  <file>   原文（必填）
//   --page    <file>   含 <blockquote> 的 HTML，批量核每一条
//   --strict           分段必须一字不差（默认允许「开头 30 字对得上」）
//
// 退出码：0 = 全找得到 / 1 = 有找不到的 / 2 = 参数错

import fs from 'node:fs';

// ---------- 归一化：这是全部的重点 ----------
// 2026-11-21 修过一个要命的 bug：原来写 .replace(/<[^>]+>/g, '')，
// 碰到 OCR 把 enemies 拆成 "ene<nies" 这种，会从那个 < 一路吃到后面唯一的 >，
// 把整本书 85% 吞掉（431192 → 65477 字符），于是什么引文都「找不到」。
// 改成只认真正的标签名，正文里的 < 不动。
const TAG_RE = /<\/?(?:br|p|div|span|em|strong|b|i|u|s|a|blockquote|h[1-6]|li|ul|ol|table|thead|tbody|tr|td|th|img|hr|pre|code|sup|sub)\b[^<>]{0,300}?\/?>/gi;

export function norm(s) {
  return s
    .replace(/<br\s*\/?>/gi, ' / ')      // <br> 当分隔符：两句之间要有断点，不然并成一句就搜不到
    .replace(/<\/p>/gi, ' / ')
    .replace(TAG_RE, '')                 // 只去真标签，正文里的裸 < 留着
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/[\u2018\u2019\u201B\u2032]/g, "'")   // ‘ ’ ‛ ′
    .replace(/[\u201C\u201D\u2033]/g, '"')         // “ ” ″
    .replace(/[\u2014\u2013]/g, '-')               // — –
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

// 引文可能带省略号，也可能因为 <br> 被拆成两半，所以按分隔符切开、逐段比。
// 单行 grep 的毛病就在这儿：跨行的一句，逐行匹配永远搜不到。
const SPLIT = /\u2026|\.{3}|\s\/\s/g;

export function segments(quote, minLen = 12) {
  return norm(quote)
    .split(SPLIT)
    .map((p) => p.replace(/^["'\u2026\s]+/, '').replace(/["'\u2026\s]+$/, '').trim())
    .filter((p) => p.length > minLen);
}

// 去掉句末标点再比一次。
// 引文常把原文的逗号改写成句号（原文 "...patience," said Conseil → 引文 "patience."），
// 这不是引文假，是抄的时候顺手断句。不认这一层，就会把七条真引文报成假。
const stripEnds = (s) => s.replace(/^[\s"'.-]+|[\s"'.,;:!?-]+$/g, '');

// 三级判据：一字不差 / 只差句末标点 / 开头 30 字对得上 / 真找不到
export function checkOne(quote, bookFlat, { minLen = 12, headLen = 30 } = {}) {
  const parts = segments(quote, minLen);
  if (!parts.length) return { verdict: 'skip', parts, bad: [] };

  let exact = true;
  let trimmed = true;
  let loose = true;
  const bad = [];

  for (const p of parts) {
    if (bookFlat.includes(p)) continue;
    exact = false;

    const t = stripEnds(p);
    if (t && bookFlat.includes(t)) continue;             // 只差标点
    trimmed = false;

    if (bookFlat.includes(p.slice(0, headLen))) continue; // 开头在，句子是真的
    loose = false;
    bad.push(p);
  }

  const verdict = exact ? 'exact' : trimmed ? 'trimmed' : loose ? 'loose' : 'missing';
  return { verdict, parts, bad };
}

// 反查行号（只对单条查询有用）
export function locate(part, lines) {
  const head = part.slice(0, Math.min(25, part.length));
  if (!head) return null;
  const i = lines.findIndex((l) => norm(l).includes(head));
  return i < 0 ? null : i + 1;
}

// ---------- CLI ----------
function main(argv) {
  const args = { source: null, page: null, strict: false, quote: '' };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--source') args.source = argv[++i];
    else if (a === '--page') args.page = argv[++i];
    else if (a === '--strict') args.strict = true;
    else if (a === '--help' || a === '-h') {
      console.log('node quote-check.mjs --source <原文> ["引文"] [--page <HTML>] [--strict]');
      return 0;
    } else if (!a.startsWith('--')) args.quote = args.quote ? args.quote + ' ' + a : a;
  }

  if (!args.source) { console.error('缺 --source <原文文件>'); return 2; }

  const bookRaw = fs.readFileSync(args.source, 'utf8');
  const bookFlat = norm(bookRaw);
  const lines = bookRaw.split(/\r?\n/);

  // 单条模式
  if (args.quote) {
    const r = checkOne(args.quote, bookFlat, { minLen: 8 });
    if (r.verdict === 'skip') { console.log('（引文太短，没法判）'); return 0; }
    const lineNo = locate(segments(args.quote, 8)[0] || '', lines);
    const where = lineNo ? `约第 ${lineNo} 行` : '行号没定位到';
    if (r.verdict === 'exact') console.log(`✓ 一字不差（${where}）`);
    else if (r.verdict === 'loose') console.log(`~ 开头对得上，中段或标点有出入（${where}）`);
    else { console.log('✗ 找不到：'); for (const b of r.bad) console.log('   ' + b.slice(0, 90)); }
    return r.verdict === 'missing' ? 1 : 0;
  }

  // 批量模式
  if (!args.page) { console.error('要么给一句引文，要么给 --page <HTML>'); return 2; }

  const pageRaw = fs.readFileSync(args.page, 'utf8');
  const quotes = [...pageRaw.matchAll(/<blockquote>([\s\S]*?)<\/blockquote>/g)].map((m) => m[1]);
  if (!quotes.length) { console.log('这个页面里没有 <blockquote>。'); return 0; }

  const stat = { exact: 0, trimmed: 0, loose: 0, missing: 0, skip: 0 };
  const missingAll = [];

  for (const q of quotes) {
    const r = checkOne(q, bookFlat, { minLen: 12 });
    stat[r.verdict]++;
    if (r.verdict === 'missing') missingAll.push(...r.bad);
  }

  const total = quotes.length;
  const good = stat.exact + stat.trimmed;
  console.log(`blockquote 总数:            ${total}`);
  console.log(`一字不差:                    ${stat.exact} / ${total}`);
  console.log(`只差句末标点（逗号↔句号）:   ${stat.trimmed} / ${total}`);
  console.log(`开头对得上（中段有出入）:    ${stat.loose} / ${total}`);
  console.log(`真找不到:                    ${stat.missing} / ${total}`);
  if (stat.skip) console.log(`太短没判:                    ${stat.skip}`);
  console.log(`\n可用（前两项）: ${good} / ${total}`);

  const fails = [...new Set(missingAll)];
  if (fails.length) {
    console.log(`\n连开头都找不到的 ${fails.length} 段 —— 这几条才是真问题：`);
    for (const f of fails) console.log(' - ' + f.slice(0, 110));
    return 1;
  }

  console.log('\n每一条都至少能在原文里找到出处。');
  return args.strict && (stat.trimmed + stat.loose) > 0 ? 1 : 0;
}

const isMain = import.meta.url === `file://${process.argv[1].replace(/\\/g, '/')}`
  || process.argv[1]?.endsWith('quote-check.mjs');
if (isMain) process.exit(main(process.argv.slice(2)));
