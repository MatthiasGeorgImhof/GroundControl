import asyncio
import pycyphal
import pycyphal.application.file
from uavcan.si.sample.voltage import Scalar_1_0 as Voltage  # Example DSDL

class GroundControlStation:
    def __init__(self):
        # 1. Setup the Node (Identity & Transport)
        self.node = pycyphal.application.make_node(
            pycyphal.application.NodeInfo(name="com.yourcompany.gcs"),
            "gcs_registers.db"
        )
        
        # 2. Add File Server Capability (Background Service)
        # Allows drones to upload flight logs to the GCS
        self.file_server = pycyphal.application.file.FileServer(
            self.node, 
            roots=[Path("./drone_logs")]
        )

        # 3. Add Telemetry Subscribers
        self.batt_sub = self.node.make_subscriber(Voltage, "battery_telemetry")
        
        # 4. Add Command Publishers
        self.cmd_pub = self.node.make_publisher(Voltage, "emergency_throttle_cutoff")

    async def run(self):
        self.node.start()
        
        # Start the telemetry processing loop
        asyncio.create_task(self._telemetry_listener())
        
        # Keep the application alive
        await asyncio.get_running_loop().create_future()

    async def _telemetry_listener(self):
        async for message, metadata in self.batt_sub:
            # Update your UI or database here
            print(f"Received Voltage from Node {metadata.source_node_id}: {message.volt}")

    def send_command(self, value: float):
        # Example of sending a command out to the fleet
        msg = Voltage(volt=value)
        self.cmd_pub.publish_soon(msg)

    def close(self):
        self.node.close()
