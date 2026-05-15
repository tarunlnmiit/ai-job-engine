import json
import re

path = "/Users/tarungupta/.gemini/antigravity/brain/b1833e78-fcdd-4247-8150-fcdbf49b9016/.system_generated/steps/41/output.txt"
with open(path) as f:
    data = json.load(f)

html = data.get("html", "")
links = re.findall(r'href=["\']([^"\']+)["\']', html)
print(f"Total links: {len(links)}")

for link in sorted(list(set(links))):
    if "job" in link.lower() or "role" in link.lower() or "position" in link.lower():
        print(link)
