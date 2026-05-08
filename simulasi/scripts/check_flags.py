import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rag.retriever import RAGRetriever

r = RAGRetriever()
coll = r.collection

results = coll.get(
    where={"jenis_dokumen": {"$eq": "putusan"}},
    limit=500,
    include=["metadatas"]
)
metas = results["metadatas"]
with_flag = [m for m in metas if "flag_priority" in m]
priority_true = [m for m in with_flag if str(m.get("flag_priority","")).lower() == "true"]

print(f"Total putusan diambil : {len(metas)}")
print(f"Sudah ada flag_priority : {len(with_flag)}")
print(f"flag_priority = true  : {len(priority_true)}")
if priority_true:
    print("\nContoh dokumen prioritas:")
    for p in priority_true[:3]:
        print(f"  - {p.get('source_file','?')} | klaster: {p.get('klaster','N/A')} | amar: {p.get('amar','N/A')}")
