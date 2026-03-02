import urllib.request, re

js_urls = [
    "https://www.se.com/us/en/locate/_svelte_app/immutable/nodes/2.5d336efd.js",
    "https://www.se.com/us/en/locate/_svelte_app/immutable/entry/app.69005946.js",
    "https://www.se.com/us/en/locate/_svelte_app/immutable/chunks/index.d931679e.js",
    "https://www.se.com/us/en/locate/_svelte_app/immutable/chunks/Website.949d4b7d.js",
]
hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

for url in js_urls:
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=15) as r:
            src = r.read().decode("utf-8", errors="ignore")
        patterns = re.findall(r"[\"'](/[^\"']*locate[^\"']*api[^\"']+|[^\"']*partners[^\"']+)[\"']", src)
        keywords = re.findall(r"[\"'](id-list|pageSize|pageNumber|offset|countryCode|configurationId)[\"']", src)
        if patterns or keywords:
            print(f"\nIn {url.split('/')[-1]}:")
            for p in sorted(set(patterns))[:20]:
                print(f"  PATH: {p}")
            for k in sorted(set(keywords)):
                print(f"  KEY:  {k}")
    except Exception as e:
        print(f"Error {url}: {e}")
