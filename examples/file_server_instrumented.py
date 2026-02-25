#!/usr/bin/env python3
import asyncio
import os
import logging
from pathlib import Path

import cyclic_tid_patch
import pycyphal
import pycyphal.application
import pycyphal.application.file

RECEIVER_FOLDER = "/tmp/received"

# ------------------------------------------------------------
# GLOBAL LOGGING SETUP
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    filename="/tmp/server.log",
    filemode="w",
)
log = logging.getLogger("FileServer")


# ------------------------------------------------------------
# INSTRUMENTED FILE SERVER
# ------------------------------------------------------------
class LoggingFileServer(pycyphal.application.file.FileServer):

    async def _serve_wr(self, request, meta):

        try:
            path = request.path.path.tobytes().decode(errors="ignore")
        except Exception:
            path = "<decode-error>"

        log.info(
            "WRITE REQUEST: path=%s offset=%d size=%d from=%s",
            path,
            int(request.offset),
            len(request.data.value),
            getattr(meta, "client_node_id", None),
        )

        # Correct handling of locate()
        root, rel = self.locate(request.path)
        full_path = root / rel

        if request.offset == 0:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(b"")

        if (not full_path.is_file()):
            log.error("WRITE REQUEST: file %s does not exist", full_path)
        else:
            log.error("WRITE REQUEST: file %s does exists", full_path)

        result = await super()._serve_wr(request, meta)

        log.info("WRITE RESPONSE: error=%s", result.error.value)
        return result

    async def _serve_rd(self, request, meta):
        try:
            path = request.path.path.tobytes().decode(errors="ignore")
        except Exception:
            path = "<decode-error>"

        log.info(
            "READ REQUEST: path=%s offset=%d size=%d from=%s",
            path,
            int(request.offset),
            int(request.size),
            getattr(meta, "client_node_id", None),
        )

        result = await super()._serve_rd(request, meta)

        log.info(
            "READ RESPONSE: error=%s returned_size=%d",
            result.error.value,
            len(result.data.value),
        )
        return result


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
async def main():
    # --------------------------------------------------------
    # 1. Configure transport via environment (registers)
    # --------------------------------------------------------
    os.environ["UAVCAN__SERIAL__IFACE"] = ("/dev/ttyUSB0")
    os.environ["UAVCAN__SERIAL__BAUDRATE"] = "115200"
    os.environ["UAVCAN__NODE__ID"] = "121"

    log.info("Starting Cyphal node on /dev/ttyUSB0:115200 with Node-ID 121")

    # --------------------------------------------------------
    # 2. Create node
    # --------------------------------------------------------
    node = pycyphal.application.make_node(
        pycyphal.application.NodeInfo(name="org.example.serial_file_server"),
        "registers.db",
    )
    node.start()

    log.info("Node started: id=%s", node.id)
    log.info("Transport: %s", node.presentation.transport)

    transport = node.presentation.transport
    log.info(f"Transport modulo = {transport.protocol_parameters.transfer_id_modulo}")

    # --------------------------------------------------------
    # 3. Start instrumented file server
    # --------------------------------------------------------
    root = Path(RECEIVER_FOLDER)
    root.mkdir(parents=True, exist_ok=True)

    file_server = LoggingFileServer(node, [root])

    log.info("FileServer ready. Root directory: %s", root)
    log.info("Listening for uavcan.file.Write and uavcan.file.Read")

    # --------------------------------------------------------
    # 4. Run forever
    # --------------------------------------------------------
    try:
        await asyncio.get_running_loop().create_future()
    finally:
        node.close()
        log.info("Node closed")


# ------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(main())
