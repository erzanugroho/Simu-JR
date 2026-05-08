import json, re, os

PAT = re.compile(r"<\|im_start\|>(system|user|assistant)\n(.*?)<\|im_end\|>", re.DOTALL)

def extract_parts(text):
    matches = PAT.findall(text)
    sys_t = usr_t = ast_t = ""
    for role, content in matches:
        content = content.strip()
        if role == "system":
            sys_t = content
        elif role == "user":
            usr_t = content
        elif role == "assistant":
            ast_t = content
    return sys_t, usr_t, ast_t

def main():
    dd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    for src, dst in [("train_filtered.jsonl", "train_gemma4_columns.jsonl"), ("val_filtered.jsonl", "val_gemma4_columns.jsonl")]:
        sp = os.path.join(dd, src)
        dp = os.path.join(dd, dst)
        if not os.path.exists(sp):
            print("Skip:", src)
            continue
        c = 0
        with open(sp, "r", encoding="utf-8") as fin, open(dp, "w", encoding="utf-8") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                s, u, a = extract_parts(obj.get("text", ""))
                rec = {"system": s, "user": u, "assistant": a}
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                c += 1
        print(src, "->", dst, ":", c, "rows")
        print("  File:", dp, "Size:", os.path.getsize(dp))

if __name__ == "__main__":
    main()