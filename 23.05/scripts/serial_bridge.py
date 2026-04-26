#!/usr/bin/env python3

import os
import select
import sys
import termios
import tty

import serial


def main() -> int:
    ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=0)
    stdin_fd = sys.stdin.fileno()
    old = termios.tcgetattr(stdin_fd)
    tty.setraw(stdin_fd)
    try:
        while True:
            rlist, _, _ = select.select([stdin_fd, ser.fileno()], [], [])
            if stdin_fd in rlist:
                data = os.read(stdin_fd, 4096)
                if not data:
                    break
                ser.write(data)
            if ser.fileno() in rlist:
                data = ser.read(4096)
                if data:
                    os.write(sys.stdout.fileno(), data)
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old)
        ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
