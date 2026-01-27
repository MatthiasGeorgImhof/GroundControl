import asyncio
import os
import pycyphal
import pycyphal.application.file
from pathlib import Path

async def main():
    # 1. CONFIGURE VIA ENVIRONMENT (Registers)
    # This tells PyCyphal to use the serial transport and sets the Node-ID
    os.environ["UAVCAN__SERIAL__IFACE"] = "/dev/ttyUSB0"  # Change to your port
    os.environ["UAVCAN__SERIAL__BAUDRATE"] = "115200"     # Set baudrate
    os.environ["UAVCAN__NODE__ID"] = "42"                 # Fixed ID (0-127)

    # 2. INITIALIZE THE NODE
    # make_node() reads the environment variables above automatically
    node = pycyphal.application.make_node(
        pycyphal.application.NodeInfo(name="org.example.serial_file_server"),
        "registers.db" # Persistent storage for settings
    )
    node.start()

    # 3. DEFINE ROOTS & START FILE SERVER
    # The server will listen for uavcan.file.Write requests on the serial bus
    roots = [Path("./shared_files")]
    file_server = pycyphal.application.file.FileServer(node, roots)
    
    print(f"FileServer running on Serial Node {node.id}. Listening for writes...")

    try:
        await asyncio.get_running_loop().create_future()  # Run forever
    finally:
        node.close()

if __name__ == "__main__":
    asyncio.run(main())
