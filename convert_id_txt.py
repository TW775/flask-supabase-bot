with open("id_list.txt", "r") as f:
    ids = [line.strip() for line in f if line.strip()]

with open("id_whitelist.json", "w") as f:
    import json
    json.dump(ids, f, ensure_ascii=False)

print("✅ 已生成 id_whitelist.json")
