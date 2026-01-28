import serial
import sys
import datetime

import sys
import serial

def printf(fmt, *args):
    sys.stdout.write(fmt % args)
    sys.stdout.flush()

with serial.Serial('/dev/ttyUSB0', 115200, timeout=None) as ser:
    count = 0
    while True:
        c = ser.read(1)          # read exactly one byte
        if c:
            printf("%02x ", c[0])
            if (count % 16)==0:
                print()
            count+=1
