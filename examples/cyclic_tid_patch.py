"""
Cyclic 5-bit Transfer-ID patch for PyCyphal high-overhead transports.

This module monkey-patches TransferReassembler.process_frame()
to interpret transfer-IDs cyclically (CAN-style) instead of strictly monotonic.
It enables correct handling of 31 → 0 → 1 → 2 → … sequences.

Import this module BEFORE importing pycyphal or yakut.
"""

IO_MODULO = 32
IO_MASK = IO_MODULO - 1
IO_MODULO_2 = IO_MODULO // 2

from pycyphal.transport.serial import SerialTransport
SerialTransport.TRANSFER_ID_MODULO = IO_MODULO

import pycyphal.transport.commons.high_overhead_transport._transfer_reassembler as tr
_original_process_frame = tr.TransferReassembler.process_frame


def unwrap_tid(frame_tid, self_tid):
    """
    Choose the representative of self_tid (mod 32) that is closest to frame_tid.
    """
    raw = self_tid - frame_tid
    delta = ((raw + IO_MODULO_2) & IO_MASK) - IO_MODULO_2
    out = frame_tid + delta

    # print(f"{frame_tid:2d}, {self_tid:2d} ({delta:+2d}) -> {out:3d}")
    return out

def _patched_process_frame(self, timestamp, frame, transfer_id_timeout):
    # Apply cyclic TID adjustment
    original = self._transfer_id
    self._transfer_id = unwrap_tid(frame.transfer_id, self._transfer_id)
    print(f"_patched_process_frame {original} {self._transfer_id} {frame.transfer_id}")

    return _original_process_frame(self, timestamp, frame, transfer_id_timeout)

# Apply patch
tr.TransferReassembler.process_frame = _patched_process_frame
print("[cyclic_tid_patch] Cyclic 5-bit Transfer-ID patch applied.")

# ----------------------------------------------------------------------
# TEST HARNESS
# ----------------------------------------------------------------------
def main():
    # print("frame_tid, self_tid_before, self_tid_result")
    for base_tid in range(0, 32, 1):
        for diff_tid in range(-4, 32, 1):
            frame_tid = base_tid
            self_tid = (base_tid + diff_tid)
            result2 = unwrap_tid(frame_tid, self_tid)
            print()
        print()


if __name__ == "__main__":
    main()
