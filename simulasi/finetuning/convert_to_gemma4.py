import json, re, os

PAT = re.compile(r"<\|im_start\|>(system|user|assistant)\n(.*?)<\|im_end\|>", re.DOTALL)

def convert(text):
    matches = PAT.findall(text)
    if not matches:
        return None
    parts = []
    for role, content in matches:
        content = content.strip()
        if role == "system":
            parts.append(("user", content))
        elif role == "user":
            parts.append(("user", content))
        elif role == "assistant":
            parts.append(("model", content))
    merged = []
    for role, content in parts:
        if merged and merged[-1][0] == role:
            merged[-1] = (role, merged[-1][1] + "\n\n" + content)
        else:
            merged.append((role, content))
    if not merged or merged[0][0] != "user":
        return None
    lines = []
    for role, content in merged:
        lines.append("<start_of_turn>" + role + "\n" + content + "<end_of_turn>")
    return "\n".join(lines)

def main():
    dd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    pairs = [("train_filtered.jsonl", "train_gemma4.jsonl"), ("val_filtered.jsonl", "val_gemma4.jsonl")]
    for src, dst in pairs:
        sp = os.path.join(dd, src)
        dp = os.path.join(dd, dst)
        if not os.path.exists(sp):
            print("Skip:", src, "not found")
            continue
        c = 0
        sk = 0
        with open(sp, "r", encoding="utf-8") as fin, open(dp, "w", encoding="utf-8") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                nt = convert(obj.get("text", ""))
                if nt:
                    fout.write(json.dumps({"text": nt}, ensure_ascii=False) + "\n")
                    c += 1
                else:
                    sk += 1
        print(src, "->", dst, ":", c, "converted,", sk, "skipped")

if __name__ == "__main__":
    main()