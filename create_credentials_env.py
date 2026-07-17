"""
Script to convert credentials.json into a base64-encoded string for Render.com environment variable.
Run this script and copy the output as GOOGLE_CREDENTIALS_B64 on Render.com
"""
import json
import sys
import base64

def encode_credentials_for_env(filepath: str) -> str:
    """Read credentials.json and return as base64 string for environment variable."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Convert to JSON string
        json_str = json.dumps(data)
        
        # Encode to base64
        b64_encoded = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        
        return b64_encoded
    
    except FileNotFoundError:
        print(f"Error: credentials.json not found at {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in credentials.json - {e}")
        sys.exit(1)

if __name__ == "__main__":
    credentials_path = "credentials.json"
    if len(sys.argv) > 1:
        credentials_path = sys.argv[1]
    
    b64_string = encode_credentials_for_env(credentials_path)
    
    print("=" * 80)
    print("BASE64 ENCODED CREDENTIALS FOR RENDER.COM")
    print("=" * 80)
    print()
    print("Set environment variable:")
    print(f"  Key:   GOOGLE_CREDENTIALS_B64")
    print(f"  Value: {b64_string}")
    print()
    print("=" * 80)
    print("REPLACE YOUR-CREDENTIALS-BASE64-STRING with the output above on Render.com")
    print("=" * 80)
    print()
    print(f"GOOGLE_CREDENTIALS_B64={b64_string}")