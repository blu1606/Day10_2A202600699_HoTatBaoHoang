"""Trace: xem retrieval trả về gì cho gq_d10_06 và các câu tương tự."""
import json, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import chromadb
from chromadb.utils import embedding_functions

ROOT = Path(__file__).resolve().parent
db_path = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
collection_name = os.environ.get("CHROMA_COLLECTION", "day10_kb")
model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

client = chromadb.PersistentClient(path=db_path)
emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
col = client.get_collection(name=collection_name, embedding_function=emb)

# Query gq_d10_06 với top-k cao hơn để tìm chunk escalation ở vị trí nào
query = "Nếu không có phản hồi với ticket P1 sau bao lâu thì hệ thống auto escalate?"
res = col.query(query_texts=[query], n_results=15)

print(f"=== Query: {query}")
print(f"=== Total docs in collection: {col.count()}")
print()

docs = res["documents"][0]
metas = res["metadatas"][0]
distances = res["distances"][0]

for i, (doc, meta, dist) in enumerate(zip(docs, metas, distances)):
    has_10min = "10 phút" in doc.lower()
    marker = " <<<< CONTAINS '10 phút'" if has_10min else ""
    print(f"  [{i+1}] dist={dist:.4f} doc_id={meta.get('doc_id','')} {marker}")
    print(f"      {doc[:150]}")
    print()

# Cũng kiểm tra: chunk escalation có thực sự trong DB không?
print("=== Tìm trực tiếp chunk chứa '10 phút' trong DB ===")
all_data = col.get(include=["documents", "metadatas"])
for doc_text, meta in zip(all_data["documents"], all_data["metadatas"]):
    if "10 phút" in doc_text:
        print(f"  doc_id={meta.get('doc_id','')} text={doc_text[:150]}")
