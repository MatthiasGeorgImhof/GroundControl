import asyncio
import pycyphal
import pycyphal.application.file
from pathlib import Path

async def main():
    # 1. Initialize your node (ensure it has a fixed node-ID)
    # The node handles background tasks like heartbeats and RPC dispatching
    node = pycyphal.application.make_node(
        pycyphal.application.NodeInfo(name="org.example.file_server"),
        "registers.db"
    )
    node.start()

    # 2. Define the directories the server can access
    # Any client 'write' request will be relative to these roots
    roots = [Path("./shared_files"), Path("/tmp/cyphal_uploads")]
    
    # 3. Start the FileServer
    # This automatically registers uavcan.file.Write, Read, etc.
    file_server = pycyphal.application.file.FileServer(node, roots)
    
    print(f"FileServer running on Node {node.id}. Roots: {roots}")

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        node.close()

if __name__ == "__main__":
    asyncio.run(main())
