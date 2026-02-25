#!/usr/bin/env python3
import asyncio
import argparse
import os
from pathlib import Path

import cyclic_tid_patch
import pycyphal
import pycyphal.application
import pycyphal.application.file

from uavcan.file.Read_1_1 import Request as ReadReq
from uavcan.file.Write_1_1 import Request as WriteReq

CHUNK = 256


# ------------------------------------------------------------
# FILE TRANSFER IMPLEMENTATIONS
# ------------------------------------------------------------
async def write_file(node, remote_path: str, local_path: Path, node_id: int):
    client = node.make_client(pycyphal.application.file.Write, node_id)

    data = local_path.read_bytes()
    offset = 0

    while offset < len(data):
        chunk = data[offset:offset+CHUNK]
        req = WriteReq(
            path=pycyphal.application.file.Path(remote_path),
            offset=offset,
            data=chunk,
        )
        resp = await client.call(req)
        if resp is None or resp.error.value != 0:
            raise RuntimeError(f"Write failed at offset {offset}, err={resp.error.value}")

        offset += len(chunk)
        print(f"Wrote {offset}/{len(data)} bytes")

    print("WRITE COMPLETE")


async def read_file(node, remote_path: str, local_path: Path, node_id: int):
    client = node.make_client(pycyphal.application.file.Read, node_id)

    offset = 0
    out = bytearray()

    while True:
        req = ReadReq(
            path=pycyphal.application.file.Path(remote_path),
            offset=offset,
            size=CHUNK,
        )
        resp = await client.call(req)
        if resp is None or resp.error.value != 0:
            raise RuntimeError(f"Read failed at offset {offset}, err={resp.error.value}")

        chunk = bytes(resp.data.value)
        if not chunk:
            break

        out.extend(chunk)
        offset += len(chunk)
        print(f"Read {offset} bytes")

    local_path.write_bytes(out)
    print("READ COMPLETE")


# ------------------------------------------------------------
# NODE CREATION (identical to your server)
# ------------------------------------------------------------
def make_node(registers_db: str, name: str):
    node = pycyphal.application.make_node(
        pycyphal.application.NodeInfo(name=name),
        registers_db,
    )
    node.start()
    return node


# ------------------------------------------------------------
# CLI ENTRY POINT
# ------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(description="Cyphal File Client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # write
    w = sub.add_parser("write")
    w.add_argument("local")
    w.add_argument("remote")
    w.add_argument("--node", type=int, required=True)

    # read
    r = sub.add_parser("read")
    r.add_argument("remote")
    r.add_argument("local")
    r.add_argument("--node", type=int, required=True)

    args = parser.parse_args()

    # Node uses environment variables + registers.db
    node = make_node("client_registers.db", "org.example.file_client")

    if args.cmd == "write":
        await write_file(node, args.remote, Path(args.local), args.node)

    elif args.cmd == "read":
        await read_file(node, args.remote, Path(args.local), args.node)

    await asyncio.sleep(0.1)
    node.close()


if __name__ == "__main__":
    asyncio.run(main())
