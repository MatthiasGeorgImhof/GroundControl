async def main():
    # --------------------------------------------------------
    # CLI argument parsing
    # --------------------------------------------------------
    parser = argparse.ArgumentParser(description="Cyphal File Server")
    parser.add_argument("--iface", help="Serial interface")
    parser.add_argument("--baud", help="Baud rate")
    parser.add_argument("--id", help="Local node-ID")
    parser.add_argument("--logfile", help="Optional log file")
    parser.add_argument("--loglevel", help="Logging level (INFO/DEBUG/WARNING)")
    args = parser.parse_args()

    # --------------------------------------------------------
    # Resolve configuration priority:
    # CLI > ENV > DEFAULTS
    # --------------------------------------------------------
    iface = args.iface or os.environ.get("UAVCAN__SERIAL__IFACE") or DEFAULT_IFACE
    baud = args.baud or os.environ.get("UAVCAN__SERIAL__BAUDRATE") or DEFAULT_BAUD
    node_id = args.id or os.environ.get("UAVCAN__NODE__ID") or DEFAULT_NODE_ID

    log_file = args.logfile or os.environ.get("FILESERVER_LOG") or DEFAULT_LOGFILE
    log_level = args.loglevel or os.environ.get("FILESERVER_LOGLEVEL") or DEFAULT_LOGLEVEL

    # Apply to environment so PyCyphal picks them up
    os.environ["UAVCAN__SERIAL__IFACE"] = iface
    os.environ["UAVCAN__SERIAL__BAUDRATE"] = baud
    os.environ["UAVCAN__NODE__ID"] = node_id

    # --------------------------------------------------------
    # Logging setup
    # --------------------------------------------------------
    level = getattr(logging, log_level.upper())
    global log
    log = setup_logging(log_file=log_file, level=level)

    log.info(f"Starting Cyphal node on {iface}:{baud} with Node-ID {node_id}")

    # --------------------------------------------------------
    # Create node (registers.db)
    # --------------------------------------------------------
    node = pycyphal.application.make_node(
        pycyphal.application.NodeInfo(name="org.example.serial_file_server"),
        "registers.db",
    )
    node.start()

    log.info("Node started: id=%s", node.id)
    log.info("Transport: %s", node.presentation.transport)

    # --------------------------------------------------------
    # File server
    # --------------------------------------------------------
    root = Path(RECEIVER_FOLDER)
    root.mkdir(parents=True, exist_ok=True)

    file_server = LoggingFileServer(node, [root])
    log.info("FileServer ready. Root directory: %s", root)

    # --------------------------------------------------------
    # Run forever
    # --------------------------------------------------------
    try:
        await asyncio.get_running_loop().create_future()
    finally:
        node.close()
        log.info("Node closed")
