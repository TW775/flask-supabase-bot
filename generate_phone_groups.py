import json

with open("phones.txt", "r") as f:
    phones = [line.strip() for line in f if line.strip()]

groups = []
for i in range(0, len(phones), 10):
    groups.append(phones[i:i+10])

with open("phone_groups.json", "w") as f:
    json.dump(groups, f, ensure_ascii=False)

print(f"✅ 共生成 {len(groups)} 组资料，每组10个号码")
