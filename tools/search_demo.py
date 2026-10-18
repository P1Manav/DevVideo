#!/usr/bin/env python3
"""Lightweight TF-IDF search demo (<80 lines). Usage: python tools/search_demo.py out/ 'query'"""
import json, math, re, sys
from collections import Counter
from pathlib import Path

def tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-z0-9_]{2,}\b", text.lower())

def search_index(index_path: Path, query: str, top_k: int = 3) -> list[tuple[float, dict]]:
    if not index_path.exists():
        return []
    records = [json.loads(l) for l in index_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not records:
        return []
    doc_tokens = [tokenize(f"{r.get('text', '')} {r.get('caption', '')}") for r in records]
    df = Counter(t for tokens in doc_tokens for t in set(tokens))
    n_docs = len(records)
    q_counts = Counter(tokenize(query))
    results = []
    for rec, tokens in zip(records, doc_tokens):
        d_counts = Counter(tokens)
        score, q_norm, d_norm = 0.0, 0.0, 0.0
        for t, qc in q_counts.items():
            idf = math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0
            qw = (qc / max(len(q_counts), 1)) * idf
            q_norm += qw * qw
            if t in d_counts:
                dw = (d_counts[t] / max(len(tokens), 1)) * idf
                score += qw * dw
        for t, dc in d_counts.items():
            idf = math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0
            dw = (dc / max(len(tokens), 1)) * idf
            d_norm += dw * dw
        cosine = score / (math.sqrt(q_norm) * math.sqrt(d_norm) + 1e-9) if score > 0 else 0.0
        if cosine > 0.0:
            results.append((cosine, rec))
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_k]

def main():
    if len(sys.argv) < 3:
        print("Usage: python tools/search_demo.py <out_dir_or_index_jsonl> <query>")
        sys.exit(1)
    target = Path(sys.argv[1])
    index_file = target if target.is_file() else target / "index.jsonl"
    query = " ".join(sys.argv[2:])
    matches = search_index(index_file, query)
    if not matches:
        print(f"No matching video segments found for: '{query}'")
        return
    print(f"Top video timestamps for '{query}':")
    for score, rec in matches:
        s, e = rec.get("start_seconds", 0.0), rec.get("end_seconds", 0.0)
        print(f"  [{score:.3f}] {s:05.1f}s - {e:05.1f}s | {rec.get('scene_id', 'scene').upper():<10} | {rec.get('text', '')}")

if __name__ == "__main__":
    main()
