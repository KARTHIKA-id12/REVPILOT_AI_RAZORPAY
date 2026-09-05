import re
path = 'app/db/seed_data/technest_catalog.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

def replacer(m):
    return '"price_amount": ' + str(int(m.group(1)) // 5)

content = re.sub(r'"price_amount":\s*(\d+)', replacer, content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
