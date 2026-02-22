import subprocess, os

logos = {
    "percept-full-dark.html": """<!DOCTYPE html><html><head><style>body{margin:0;}</style></head><body>
<svg width="400" height="400" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
<rect width="400" height="400" fill="#111111"/>
<circle cx="200" cy="200" r="180" fill="none" stroke="#e8453c" stroke-width="3" opacity="0.2"/>
<circle cx="200" cy="200" r="130" fill="none" stroke="#e8453c" stroke-width="4" opacity="0.4"/>
<circle cx="200" cy="200" r="80" fill="none" stroke="#e8453c" stroke-width="5" opacity="0.7"/>
<circle cx="200" cy="200" r="24" fill="#e8453c"/>
</svg></body></html>""",

    "percept-full-white.html": """<!DOCTYPE html><html><head><style>body{margin:0;}</style></head><body>
<svg width="400" height="400" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
<rect width="400" height="400" fill="#ffffff"/>
<circle cx="200" cy="200" r="180" fill="none" stroke="#e8453c" stroke-width="3" opacity="0.25"/>
<circle cx="200" cy="200" r="130" fill="none" stroke="#e8453c" stroke-width="4" opacity="0.45"/>
<circle cx="200" cy="200" r="80" fill="none" stroke="#e8453c" stroke-width="5" opacity="0.7"/>
<circle cx="200" cy="200" r="24" fill="#e8453c"/>
</svg></body></html>""",

    "percept-full-transparent.html": """<!DOCTYPE html><html><head><style>body{margin:0;background:transparent;}</style></head><body>
<svg width="400" height="400" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
<circle cx="200" cy="200" r="180" fill="none" stroke="#e8453c" stroke-width="3" opacity="0.2"/>
<circle cx="200" cy="200" r="130" fill="none" stroke="#e8453c" stroke-width="4" opacity="0.4"/>
<circle cx="200" cy="200" r="80" fill="none" stroke="#e8453c" stroke-width="5" opacity="0.7"/>
<circle cx="200" cy="200" r="24" fill="#e8453c"/>
</svg></body></html>""",

    "percept-avatar-dark.html": """<!DOCTYPE html><html><head><style>body{margin:0;}</style></head><body>
<svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
<rect width="200" height="200" fill="#111111"/>
<circle cx="100" cy="100" r="85" fill="none" stroke="#e8453c" stroke-width="3" opacity="0.2"/>
<circle cx="100" cy="100" r="60" fill="none" stroke="#e8453c" stroke-width="3.5" opacity="0.4"/>
<circle cx="100" cy="100" r="38" fill="none" stroke="#e8453c" stroke-width="4" opacity="0.7"/>
<circle cx="100" cy="100" r="12" fill="#e8453c"/>
</svg></body></html>""",

    "percept-avatar-white.html": """<!DOCTYPE html><html><head><style>body{margin:0;}</style></head><body>
<svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
<rect width="200" height="200" fill="#ffffff"/>
<circle cx="100" cy="100" r="85" fill="none" stroke="#e8453c" stroke-width="3" opacity="0.25"/>
<circle cx="100" cy="100" r="60" fill="none" stroke="#e8453c" stroke-width="3.5" opacity="0.45"/>
<circle cx="100" cy="100" r="38" fill="none" stroke="#e8453c" stroke-width="4" opacity="0.7"/>
<circle cx="100" cy="100" r="12" fill="#e8453c"/>
</svg></body></html>""",

    "percept-wordmark-dark.html": """<!DOCTYPE html><html><head><style>body{margin:0;}</style></head><body>
<svg width="500" height="100" viewBox="0 0 500 100" xmlns="http://www.w3.org/2000/svg">
<rect width="500" height="100" fill="#111111"/>
<circle cx="50" cy="50" r="40" fill="none" stroke="#e8453c" stroke-width="2" opacity="0.2"/>
<circle cx="50" cy="50" r="28" fill="none" stroke="#e8453c" stroke-width="2.5" opacity="0.4"/>
<circle cx="50" cy="50" r="17" fill="none" stroke="#e8453c" stroke-width="3" opacity="0.7"/>
<circle cx="50" cy="50" r="6" fill="#e8453c"/>
<text x="110" y="62" font-family="-apple-system,system-ui,sans-serif" font-weight="600" font-size="42" fill="#e8e8e8" letter-spacing="3">PERCEPT</text>
</svg></body></html>""",
}

for name, html in logos.items():
    with open(name, 'w') as f:
        f.write(html)
    print(f"Created {name}")

print("Done creating HTML files")
