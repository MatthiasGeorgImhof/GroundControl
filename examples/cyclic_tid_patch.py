"""
Cyclic 5-bit Transfer-ID patch for PyCyphal high-overhead transports.

This module monkey-patches TransferReassembler.process_frame()
to interpret transfer-IDs cyclically (CAN-style) instead of strictly monotonic.
It enables correct handling of 31 → 0 → 1 → 2 → … sequences.

Import this module BEFORE importing pycyphal or yakut.
"""

from pycyphal.transport.serial import SerialTransport
SerialTransport.TRANSFER_ID_MODULO = 32

import pycyphal.transport.commons.high_overhead_transport._transfer_reassembler as tr
_original_process_frame = tr.TransferReassembler.process_frame


def fudge_frame_tid(frame_tid, transfer_tid):
    """
    Convert a cyclic 5-bit transfer-ID into a monotonic-compatible value
    based on the cyclic distance between transfer_tid and frame_tid.
    """
    delta = (transfer_tid - frame_tid) & 0x1f
    if delta > 16:
        frame_tid = frame_tid + 32
    return frame_tid


def _patched_process_frame(self, timestamp, frame, transfer_id_timeout):
    # Apply cyclic TID adjustment
    original = self._transfer_id
    self._transfer_id = fudge_frame_tid(frame.transfer_id, self._transfer_id)
    print(f"_patched_process_frame {original} {self._transfer_id} {frame.transfer_id}")

    return _original_process_frame(self, timestamp, frame, transfer_id_timeout)

# def _patched_process_frame(self, timestamp, frame, transfer_id_timeout):
#     print(f"_patched_process_frame {self._transfer_id} {frame.transfer_id}")
#     return _original_process_frame(self, timestamp, frame, transfer_id_timeout)


# Apply patch
tr.TransferReassembler.process_frame = _patched_process_frame
print("[cyclic_tid_patch] Cyclic 5-bit Transfer-ID patch applied.")

# ----------------------------------------------------------------------
# TEST HARNESS
# ----------------------------------------------------------------------
def main():
    print("transfer_tid, frame_tid_before, fudge_tid_result")
    for transfer_tid in range(32):
        for frame_tid in range(32):
            result = _patched_process_frame(transfer_tid, frame_tid)
            print(f"{transfer_tid:2d}, {frame_tid:2d} -> {result:3d}")


if __name__ == "__main__":
    main()
