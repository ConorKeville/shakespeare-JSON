#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';

const ROOT = process.cwd();               // scan the whole repo by default
const OUT  = path.join(ROOT, 'index.json');

const SKIP_DIRS  = new Set(['.git', '.github', 'node_modules', 'dist']);
const SKIP_FILES = new Set(['index.json']);

const toPosix = p => p.split(path.sep).join('/');

function isSceneJson(obj){
  return obj?.meta?.unit?.type &&
         String(obj.meta.unit.type).toLowerCase() === 'scene';
}

function numFrom(v){
  if (v === null || v === undefined) return null;
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  const s = String(v).trim();
  if (!s) return null;
  if (/^\d+$/.test(s)) return parseInt(s,10);
  const ROM = {I:1,V:5,X:10,L:50,C:100,D:500,M:1000};
  let t = s.toUpperCase(); if (!/^[IVXLCDM]+$/.test(t)) return null;
  let total = 0, prev = 0;
  for (let i=t.length-1;i>=0;i--){ const val = ROM[t[i]]; total += (val<prev)?-val:val; prev=val; }
  return total;
}

async function walk(dir){
  const out = [];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const e of entries){
    const p = path.join(dir, e.name);
    if (e.isDirectory()){
      if (SKIP_DIRS.has(e.name)) continue;
      out.push(...await walk(p));
    } else if (e.isFile()){
      if (!e.name.endsWith('.json')) continue;
      if (SKIP_FILES.has(e.name)) continue;
      out.push(p);
    }
  }
  return out;
}

async function main(){
  const files = await walk(ROOT);
  const plays = new Map();

  for (const abs of files){
    try{
      const raw  = await fs.readFile(abs, 'utf8');
      const data = JSON.parse(raw);
      if (!isSceneJson(data)) continue;

      const playId    = data.meta?.play?.id
        || (data.meta?.play?.title || '').toLowerCase().replace(/\s+/g,'-').replace(/[^\w-]/g,'');
      const playTitle = data.meta?.play?.title || playId;
      const act       = data.meta?.unit?.act ?? null;
      const scene     = data.meta?.unit?.scene ?? null;
      const title     = data.meta?.unit?.title || data.meta?.unit?.label || null;

      const relPath   = toPosix(path.relative(ROOT, abs));

      if (!plays.has(playId)) plays.set(playId, { id: playId, title: playTitle, scenes: [] });
      plays.get(playId).scenes.push({ act, scene, title, path: relPath });
    } catch { /* ignore unreadable/bad JSON */ }
  }

  const out = { plays: [] };
  for (const p of plays.values()){
    p.scenes.sort((a,b)=>{
      const aa = numFrom(a.act), bb = numFrom(b.act);
      if ((aa ?? Infinity) !== (bb ?? Infinity)) return (aa ?? Infinity) - (bb ?? Infinity);
      const as = numFrom(a.scene), bs = numFrom(b.scene);
      return (as ?? Infinity) - (bs ?? Infinity);
    });
    p.scene_count = p.scenes.length;
    out.plays.push(p);
  }
  out.plays.sort((a,b)=>a.title.localeCompare(b.title));

  await fs.writeFile(OUT, JSON.stringify(out, null, 2));
  console.log(`Wrote ${OUT} with ${out.plays.length} plays, ${out.plays.reduce((n,p)=>n+p.scene_count,0)} scenes.`);
}

main().catch(e => { console.error(e); process.exit(1); });
