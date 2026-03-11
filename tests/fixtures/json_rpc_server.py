import json
import sys
import time

message = {"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1}
print(json.dumps(message))
sys.stdout.flush()
time.sleep(10)  # Keeps the process alive for 10 seconds
