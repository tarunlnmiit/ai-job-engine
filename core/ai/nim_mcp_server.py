import os
import json
import httpx
import sys
from typing import Dict, Any

# Simple MCP server for NVIDIA NIM
def main():
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print(json.dumps({"error": "NVIDIA_API_KEY not found"}))
        sys.exit(1)

    # Tool definitions
    tools = [
        {
            "name": "consult_coding_model",
            "description": "Ask a specialized coding model (Qwen3 Coder or Mistral Large) for a second opinion on code.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The coding question or code to review."},
                    "model": {"type": "string", "description": "Model to use (mistralai/mistral-large-3-675b-instruct-2512 or qwen/qwen3-coder-480b-a35b-instruct)", "default": "mistralai/mistral-large-3-675b-instruct-2512"}
                },
                "required": ["prompt"]
            }
        }
    ]

    # Simple stdio protocol
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("method") == "list_tools":
                print(json.dumps({"result": {"tools": tools}}))
            elif request.get("method") == "call_tool":
                name = request["params"]["name"]
                args = request["params"]["arguments"]
                
                if name == "consult_coding_model":
                    model = args.get("model", "mistralai/mistral-large-3-675b-instruct-2512")
                    prompt = args["prompt"]
                    
                    with httpx.Client(timeout=60.0) as client:
                        resp = client.post(
                            "https://integrate.api.nvidia.com/v1/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={
                                "model": model,
                                "messages": [{"role": "user", "content": prompt}]
                            }
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        print(json.dumps({"result": {"content": [{"type": "text", "text": content}]}}))
            sys.stdout.flush()
        except Exception as e:
            pass

if __name__ == "__main__":
    main()
