import serial
import sys
import datetime

def printf(format, *args):
    sys.stdout.write(format % args)

not_zero = False
with serial.Serial('/dev/ttyUSB0', 115200) as ser:
    while(True):
        c = ser.read()
        c = c[0]
        if not not_zero and not c:
            printf("%s %02x ", datetime.datetime.now().time(), c)
        if c:
            printf("%02x ", c)
        if (not_zero and not c):
            print()
        not_zero = c
