import json, os

def main():
    dd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    for src, dst in [
        ("train_gemma4_columns.jsonl", "train_gemma4_sorted.jsonl"),
        ("val_gemma4_columns.jsonl", "val_gemma4_sorted.jsonl"),
    ]:
        sp = os.path.join(dd, src)
        dp = os.path.join(dd, dst)
        if not os.path.exists(sp):
            print("Skip:", src)
            continue

        with open(sp, "r", encoding="utf-8") as f:
            data = [json.loads(line) for line in f if line.strip()]

        # Sort by total word count DESCENDING (panjang duluan)
        data.sort(key=lambda x: len((x.get("system", "") + " " + x.get("user", "") + " " + x.get("assistant", "")).split()), reverse=True)

        with open(dp, "w", encoding="utf-8") as f:
            for d in data:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

        lengths = [len((d.get("system","")+" "+d.get("user","")+" "+d.get("assistant","")).split()) for d in data]
        n = len(lengths)
        print(f"{src} -> {dst}: {n} rows")
        print(f"  Min: {lengths[0]}, Median: {lengths[n//2]}, Max: {lengths[-1]}")
        print(f"  First 5 lengths: {lengths[:5]}")
        print(f"  Last 5 lengths: {lengths[-5:]}")
        print(f"  Size: {os.path.getsize(dp):,} bytes")

if __name__ == "__main__":
    main()