#!/usr/bin/env python3

import argparse
import select
import socket
import sys
import termios
import time
import tty


SERIAL_DEVICE = "/dev/ttyUSB0"
SERIAL_BAUD = 115200
SERIAL_TIMEOUT = 0.1

SPD_HOST = "10.0.0.69"
SPD_PORT = 5025
SPD_TIMEOUT = 3.0
CH1_MASK = 0x10

CTRL_C = b"\x03"
AUTOBOOT_MARKER = b"Press Ctrl+C to abort autoboot"
PROMPT_MARKERS = (b"ath>", b"=>", b"IPQ806x#")


class ToolError(Exception):
    pass


def spd_recv_line(sock: socket.socket) -> str:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break
    if not data:
        raise ToolError("no response from SPD3303X")
    return data.decode("ascii", errors="replace").strip()


def spd_query(sock: socket.socket, command: str) -> str:
    sock.sendall(f"{command}\n".encode("ascii"))
    return spd_recv_line(sock)


def spd_write(sock: socket.socket, command: str) -> None:
    sock.sendall(f"{command}\n".encode("ascii"))


def get_ch1_state(sock: socket.socket) -> bool:
    raw = spd_query(sock, "SYST:STAT?")
    try:
        mask = int(raw, 0)
    except ValueError as exc:
        raise ToolError(f"unexpected SYST:STAT? response: {raw!r}") from exc
    return bool(mask & CH1_MASK)


def set_ch1(sock: socket.socket, enabled: bool) -> None:
    spd_write(sock, f"OUTP CH1,{'ON' if enabled else 'OFF'}")


def power_cycle_ch1(off_seconds: float, on_settle_seconds: float) -> None:
    with socket.create_connection((SPD_HOST, SPD_PORT), timeout=SPD_TIMEOUT) as sock:
        sock.settimeout(SPD_TIMEOUT)
        idn = spd_query(sock, "*IDN?")
        print(f"[psu] {idn}")
        before = get_ch1_state(sock)
        print(f"[psu] CH1 before: {'ON' if before else 'OFF'}")
        if before:
            set_ch1(sock, False)
            print(f"[psu] CH1 -> OFF, waiting {off_seconds:.1f}s")
            time.sleep(off_seconds)
        set_ch1(sock, True)
        print(f"[psu] CH1 -> ON, waiting {on_settle_seconds:.1f}s")
        time.sleep(on_settle_seconds)


def open_serial(device: str, baud: int):
    fd = open(device, "r+b", buffering=0)
    attrs = termios.tcgetattr(fd.fileno())
    tty.setraw(fd.fileno())
    attrs = termios.tcgetattr(fd.fileno())

    baud_attr = getattr(termios, f"B{baud}", None)
    if baud_attr is None:
        fd.close()
        raise ToolError(f"unsupported baud rate: {baud}")

    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = baud_attr
    attrs[5] = baud_attr
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd.fileno(), termios.TCSANOW, attrs)
    termios.tcflush(fd.fileno(), termios.TCIOFLUSH)
    return fd


def monitor_for_uboot(device: str, baud: int, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    saw_autoboot = False
    sent_interrupt = False
    prompt_seen = False
    carry = b""

    with open_serial(device, baud) as ser:
        print(f"[serial] monitoring {device} @ {baud} 8N1")
        while time.monotonic() < deadline:
            remaining = max(0.0, min(SERIAL_TIMEOUT, deadline - time.monotonic()))
            ready, _, _ = select.select([ser], [], [], remaining)
            if not ready:
                continue

            chunk = ser.read(4096)
            if not chunk:
                continue

            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()

            search = carry + chunk
            carry = search[-256:]

            if not saw_autoboot and AUTOBOOT_MARKER in search:
                saw_autoboot = True
                print("\n[serial] autoboot prompt detected, sending Ctrl+C once", flush=True)
                ser.write(CTRL_C)
                ser.flush()
                sent_interrupt = True

            if sent_interrupt and any(marker in search for marker in PROMPT_MARKERS):
                prompt_seen = True
                print("\n[serial] U-Boot prompt detected", flush=True)
                return 0

        if not saw_autoboot:
            print("\n[serial] timed out before seeing autoboot prompt", file=sys.stderr)
            return 2
        if not prompt_seen:
            print("\n[serial] sent Ctrl+C but did not confirm a U-Boot prompt", file=sys.stderr)
            return 3
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch serial output for the autoboot prompt and interrupt into U-Boot."
    )
    parser.add_argument("--device", default=SERIAL_DEVICE)
    parser.add_argument("--baud", type=int, default=SERIAL_BAUD)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--power-cycle", action="store_true")
    parser.add_argument("--off-seconds", type=float, default=2.0)
    parser.add_argument("--settle-seconds", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.power_cycle:
            power_cycle_ch1(args.off_seconds, args.settle_seconds)
        return monitor_for_uboot(args.device, args.baud, args.timeout)
    except (OSError, socket.timeout, ToolError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
