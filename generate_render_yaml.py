"""Generate .render.yaml with embedded credentials."""
import json
import base64

# Read credentials
with open('credentials.json', 'r') as f:
    creds = json.load(f)

# Convert to compact JSON (no spaces, newlines preserved in private_key)
creds_json = json.dumps(creds, separators=(',', ':'))

# Base64 encode for safe embedding
creds_b64 = base64.b64encode(creds_json.encode()).decode()

render_yaml = f'''services:
  - type: web
    name: portfolio-app
    env: python
    region: oregon
    plan: starter
    buildCommand: |
      pip install -r requirements.txt
      python -c "import base64; open('credentials.json','w').write(base64.b64decode('{creds_b64}').decode())"
    startCommand: streamlit run main.py --server.port $PORT --server.address 0.0.0.0
    envVars:
      - key: PORT
        value: 8080
      - key: SHEET_ID
        sync: false
      - key: TICKERTAPE_USERNAME
        sync: false
      - key: TICKERTAPE_PASSWORD
        sync: false
'''

with open('.render.yaml', 'w') as f:
    f.write(render_yaml)

print("Generated .render.yaml with embedded credentials")
print(f"Base64 length: {len(creds_b64)} characters")